from datetime import datetime, timezone
from typing import Any, Callable, Optional

from engine.domain import (
    CompletenessState,
    LifecycleState,
    SearchBatchResult,
    SearchRequest,
    SearchSession,
)


# Minimum server-side result window (eventList.maxReturnedEvents) requested from
# SecOps regardless of how small the caller's client-side receive_limit is.
# Prevents low limits (e.g. receive_limit=1 from entity/investigation workflows)
# from starving the operation's event list, which is shared with prevalence/
# aggregation/AI-overview assembly. The retrieval loop still trims delivered
# events to receive_limit, so this never causes over-delivery to the caller.
MATERIALIZE_BUDGET_FLOOR = 1000


def _is_cancelled(token: Any) -> bool:
    if token is None:
        return False
    if callable(token):
        return bool(token())
    if hasattr(token, "is_set"):
        return bool(token.is_set())
    return bool(token)


class SearchUDMWorkflow:

    def __init__(self, adapter: Optional[Any] = None):
        if adapter is None:
            from adapters.google_secops import GoogleSecOpsAdapter
            adapter = GoogleSecOpsAdapter()
        self.adapter = adapter

    def execute(
        self,
        request: SearchRequest,
        on_batch: Optional[Callable[[SearchBatchResult, SearchSession], None]] = None,
        on_state_change: Optional[
            Callable[[LifecycleState, CompletenessState, SearchSession], None]
        ] = None,
        cancel_token: Optional[Any] = None,
    ) -> SearchSession:
        """Executes the SearchUDM workflow synchronously, streaming batches via callbacks."""
        session = SearchSession(
            request=request,
            lifecycle=LifecycleState.VALIDATING,
            completeness=CompletenessState.EMPTY,
            started_at=datetime.now(timezone.utc),
        )


        def _notify_state():
            if on_state_change:
                on_state_change(session.lifecycle, session.completeness, session)

        _notify_state()

        # Step 1: Query Validation
        val_res = self.adapter.validate_query(request.query)
        if not val_res.valid:
            session.lifecycle = LifecycleState.FAILED
            session.completeness = CompletenessState.EMPTY
            session.error = val_res.error_message or "Query validation failed: invalid UDM syntax"
            session.completed_at = datetime.now(timezone.utc)
            _notify_state()
            return session

        # Check early cancellation
        if _is_cancelled(cancel_token):
            session.lifecycle = LifecycleState.CANCELLED
            session.completed_at = datetime.now(timezone.utc)
            _notify_state()
            return session

        # Step 2: Initiate Search Operation
        session.lifecycle = LifecycleState.STARTING
        _notify_state()

        try:
            # Decouple the server-side materialization budget from the client-side
            # receive_limit. Honor an explicit request.materialize_budget when set;
            # otherwise floor the derived budget so tiny receive_limits don't starve
            # the shared event list. The loop below still enforces receive_limit.
            materialize_budget = (
                request.materialize_budget
                if request.materialize_budget is not None
                else max(request.receive_limit, MATERIALIZE_BUDGET_FLOOR)
            )
            operation_id = self.adapter.start_search(
                query=request.query,
                start_time=request.start_time,
                end_time=request.end_time,
                max_events=materialize_budget,
            )
            session.session_id = operation_id
        except Exception as e:
            session.lifecycle = LifecycleState.FAILED
            session.completeness = CompletenessState.EMPTY
            session.error = f"Search initiation failed: {e}"
            session.completed_at = datetime.now(timezone.utc)
            _notify_state()
            return session

        # Step 3: Incremental Retrieval Loop
        session.lifecycle = LifecycleState.RUNNING
        _notify_state()

        while session.more_data_available and session.received_count < request.receive_limit:
            # Check cancellation before requesting batch
            if _is_cancelled(cancel_token):
                session.lifecycle = LifecycleState.CANCELLING
                _notify_state()
                self.adapter.cancel_operation(session.session_id)
                session.lifecycle = LifecycleState.CANCELLED
                session.completeness = (
                    CompletenessState.PARTIAL if session.received_count > 0 else CompletenessState.EMPTY
                )
                session.completed_at = datetime.now(timezone.utc)
                _notify_state()
                return session

            batch_limit = min(request.batch_size, request.receive_limit - session.received_count)
            try:
                batch_res = self.adapter.get_events(
                    operation_id=session.session_id,
                    start_index=session.next_index,
                    batch_size=batch_limit,
                )
            except Exception as e:
                session.lifecycle = LifecycleState.FAILED
                session.completeness = (
                    CompletenessState.PARTIAL if session.received_count > 0 else CompletenessState.EMPTY
                )
                session.error = f"Stream retrieval failed at index {session.next_index}: {e}"
                session.completed_at = datetime.now(timezone.utc)
                _notify_state()
                return session

            # Strict enforcement of receive_limit
            remaining_quota = request.receive_limit - session.received_count
            events_to_add = batch_res.events[:remaining_quota]
            session.events.extend(events_to_add)
            session.received_count += len(events_to_add)
            session.next_index += len(events_to_add)

            # Check if there is still more data available or if we capped before stream exhausted
            stream_has_more = (
                batch_res.more_data_available or len(batch_res.events) > len(events_to_add)
            )
            session.more_data_available = stream_has_more

            # Emit batch with the actual added events
            if on_batch:
                trimmed_batch = SearchBatchResult(
                    events=events_to_add,
                    provider_event_count=batch_res.provider_event_count,
                    emitted_event_count=len(events_to_add),
                    more_data_available=stream_has_more,
                    provider=batch_res.provider,
                    workflow_id=batch_res.workflow_id,
                    operation_id=batch_res.operation_id,
                    requested_start_index=batch_res.requested_start_index,
                    requested_end_index=batch_res.requested_end_index,
                    returned_start_index=batch_res.returned_start_index,
                    returned_end_index=batch_res.returned_start_index + len(events_to_add) - 1
                    if events_to_add
                    else batch_res.returned_start_index,
                    retrieved_at=batch_res.retrieved_at,
                    raw_response=batch_res.raw_response,
                )
                on_batch(trimmed_batch, session)

            _notify_state()

            # Break if quota met or no more events
            if session.received_count >= request.receive_limit or len(events_to_add) == 0 or not batch_res.more_data_available:
                break

        # Step 4: Completion
        session.lifecycle = LifecycleState.COMPLETED
        if session.received_count == 0:
            session.completeness = CompletenessState.COMPLETE
        elif session.more_data_available:
            session.completeness = CompletenessState.PARTIAL
        else:
            session.completeness = CompletenessState.COMPLETE

        session.completed_at = datetime.now(timezone.utc)
        _notify_state()
        return session
