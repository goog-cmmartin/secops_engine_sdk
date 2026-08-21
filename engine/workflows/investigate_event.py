from typing import Any, Dict, Optional, Union

from engine.domain import (
    EventInvestigation,
    EventReference,
    InvestigationProvenance,
    RawLogPayload,
)


class InvestigateEventWorkflow:
    """Orchestrates event investigation and raw log retrieval workflow."""

    def __init__(self, adapter: Optional[Any] = None):
        if adapter is None:
            from adapters.google_secops import GoogleSecOpsAdapter
            adapter = GoogleSecOpsAdapter()
        self.adapter = adapter

    def execute(
        self,
        event_ref: Union[EventReference, Dict[str, Any], str],
        eager_load_raw_log: bool = False,
    ) -> EventInvestigation:
        """Executes event investigation to produce an EventInvestigation domain entity."""
        event_id: str = ""
        log_token: Optional[str] = None
        structured_event: Optional[Dict[str, Any]] = None

        if isinstance(event_ref, EventReference):
            event_id = event_ref.event_id
            log_token = event_ref.log_token
            structured_event = event_ref.structured_event
        elif isinstance(event_ref, str):
            event_id = event_ref.strip()
        elif isinstance(event_ref, dict):
            if "event" in event_ref:
                structured_event = event_ref.get("event", {})
                log_token = event_ref.get("eventLogToken")
                event_id = (
                    structured_event.get("metadata", {}).get("id")
                    or event_ref.get("id", "")
                )
            elif "udm" in event_ref:
                structured_event = event_ref.get("udm", {})
                event_id = structured_event.get("metadata", {}).get("id", "")
            else:
                structured_event = event_ref
                event_id = structured_event.get("metadata", {}).get("id", "")

        if not event_id:
            raise ValueError(f"Cannot investigate event: unable to determine event_id from reference: {event_ref}")

        # If no structured event provided in memory, fetch enriched event from provider
        if not structured_event:
            structured_event = self.adapter.fetch_enriched_event(event_id)

        raw_log_payload: Optional[RawLogPayload] = None
        if eager_load_raw_log:
            raw_log_payload = self.adapter.get_raw_log(event_id=event_id, log_token=log_token)

        provenance = InvestigationProvenance(
            provider="google_secops",
            workflow_id="event.investigate",
            event_id=event_id,
        )

        return EventInvestigation(
            event_id=event_id,
            event=structured_event,
            log_token=log_token,
            raw_log=raw_log_payload,
            provenance=provenance,
            adapter=self.adapter,
        )
