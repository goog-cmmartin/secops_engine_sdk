"""Milestone 1.2 Regression Suite: server-side materialization budget decoupling.

Offline, deterministic coverage for the defect where a small client-side
``receive_limit`` (e.g. 1, as used by entity/investigation workflows) was
forwarded verbatim as ``eventList.maxReturnedEvents`` into
``legacyFetchUdmSearchView``. Because that server window is shared with
prevalence/aggregation/AI-overview assembly, tiny values starved the event list
and returned zero events for queries that otherwise had matches.

The fix (engine/workflows/search_udm.py) floors the server budget via
MATERIALIZE_BUDGET_FLOOR and honors an explicit request.materialize_budget,
while the retrieval loop continues to trim delivered events to receive_limit.

These tests use a spy adapter (no live tenant required) to assert the exact
value handed to start_search and to prove receive_limit is still enforced.
"""

import unittest
from typing import Any, Dict, List, Optional

from engine import (
    CompletenessState,
    LifecycleState,
    SearchBatchResult,
    SearchRequest,
    SearchSession,
    SecOpsEngine,
)
from engine.domain import ValidationResult
from engine.workflows.search_udm import MATERIALIZE_BUDGET_FLOOR


class _SpyAdapter:
    """Minimal in-memory adapter that records the max_events start_search receives.

    Serves ``total_available`` synthetic events across batches so the workflow's
    streaming loop and receive_limit trimming exercise real code paths.
    """

    def __init__(self, total_available: int = 5000):
        self.total_available = total_available
        self.captured_max_events: Optional[int] = None
        self.start_search_calls = 0

    def validate_query(self, query: str, dialect: str = "udm") -> ValidationResult:
        return ValidationResult(valid=True, dialect="udm", raw_query_type="QUERY_TYPE_UDM_QUERY")

    def start_search(self, query: str, start_time: str, end_time: str, max_events: int = 10000) -> str:
        self.captured_max_events = max_events
        self.start_search_calls += 1
        # Never serve more than the server window we were told to materialize.
        self._materialized = min(self.total_available, max_events)
        return "projects/p/locations/us/instances/c/operations/s-udm-spy"

    def get_events(self, operation_id: str, start_index: int, batch_size: int = 2000) -> SearchBatchResult:
        # start_index is 1-based in this workflow's contract.
        begin = start_index - 1
        end = min(begin + batch_size, self._materialized)
        events: List[Dict[str, Any]] = [
            {"event": {"metadata": {"eventType": "USER_LOGIN"}, "_i": i}}
            for i in range(begin, max(begin, end))
        ]
        more = end < self._materialized
        return SearchBatchResult(
            events=events,
            provider_event_count=len(events),
            emitted_event_count=len(events),
            more_data_available=more,
            operation_id=operation_id,
            requested_start_index=start_index,
            requested_end_index=start_index + batch_size - 1,
        )


def _make_engine(adapter: _SpyAdapter) -> SecOpsEngine:
    return SecOpsEngine(adapter=adapter)


class TestMaterializeBudgetDecoupling(unittest.TestCase):
    def _run(self, req: SearchRequest, adapter: _SpyAdapter) -> SearchSession:
        collected: List[SearchBatchResult] = []
        return _make_engine(adapter).search_udm(
            req, on_batch=lambda b, s: collected.append(b)
        )

    def test_udm_exec_010_low_receive_limit_does_not_starve_server_budget(self):
        """UDM-EXEC-010: receive_limit=1 must floor server max_events, not forward 1.

        This is the core regression: the defect forwarded receive_limit verbatim.
        """
        adapter = _SpyAdapter(total_available=5000)
        req = SearchRequest(
            query='metadata.event_type = "USER_LOGIN"',
            start_time="2026-08-16T00:00:00.000Z",
            end_time="2026-08-17T00:00:00.000Z",
            receive_limit=1,
            batch_size=2000,
        )
        session = self._run(req, adapter)

        # Server budget was floored, NOT set to the client's receive_limit of 1.
        self.assertEqual(adapter.captured_max_events, MATERIALIZE_BUDGET_FLOOR)
        self.assertGreater(adapter.captured_max_events, req.receive_limit)

        # Client still receives exactly receive_limit events (loop trims correctly).
        self.assertEqual(session.received_count, 1)
        self.assertEqual(len(session.events), 1)
        self.assertEqual(session.lifecycle, LifecycleState.COMPLETED)
        # More matches existed than delivered -> PARTIAL completeness.
        self.assertEqual(session.completeness, CompletenessState.PARTIAL)

    def test_udm_exec_011_large_receive_limit_passes_through_above_floor(self):
        """UDM-EXEC-011: receive_limit above the floor is used as the server budget."""
        adapter = _SpyAdapter(total_available=50000)
        req = SearchRequest(
            query='metadata.event_type = "USER_LOGIN"',
            start_time="2026-08-16T00:00:00.000Z",
            end_time="2026-08-17T00:00:00.000Z",
            receive_limit=8000,
            batch_size=2000,
        )
        session = self._run(req, adapter)

        self.assertEqual(adapter.captured_max_events, 8000)
        self.assertEqual(session.received_count, 8000)

    def test_udm_exec_012_explicit_materialize_budget_is_honored(self):
        """UDM-EXEC-012: an explicit materialize_budget overrides the derived floor."""
        adapter = _SpyAdapter(total_available=5000)
        req = SearchRequest(
            query='metadata.event_type = "USER_LOGIN"',
            start_time="2026-08-16T00:00:00.000Z",
            end_time="2026-08-17T00:00:00.000Z",
            receive_limit=1,
            batch_size=2000,
            materialize_budget=3000,
        )
        session = self._run(req, adapter)

        # Explicit budget wins over both receive_limit and the floor.
        self.assertEqual(adapter.captured_max_events, 3000)
        # Client cap still honored.
        self.assertEqual(session.received_count, 1)

    def test_udm_exec_013_explicit_budget_below_floor_is_respected(self):
        """UDM-EXEC-013: explicit budget is taken as-authored, even below the floor.

        The floor only governs the *derived* default; an explicit caller value is
        intentional and must not be silently raised.
        """
        adapter = _SpyAdapter(total_available=5000)
        req = SearchRequest(
            query='metadata.event_type = "USER_LOGIN"',
            start_time="2026-08-16T00:00:00.000Z",
            end_time="2026-08-17T00:00:00.000Z",
            receive_limit=5,
            batch_size=2000,
            materialize_budget=10,
        )
        session = self._run(req, adapter)

        self.assertEqual(adapter.captured_max_events, 10)
        self.assertEqual(session.received_count, 5)


if __name__ == "__main__":
    unittest.main()
