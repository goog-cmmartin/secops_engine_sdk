"""Generated Google ADK 2 Agent: Timestamp Integrity Agent.

Auto-generated from agents/manifests/timestamp_integrity.yaml. Do not edit directly.
"""

from typing import Any, Optional
from datetime import datetime, timezone
import json
import logging
from typing import Any, Dict, List, Optional
from agents.core.base_adk_agent import BaseSecOpsAdkAgent
from engine.facade import SecOpsEngine
from agents.core.proposal_manager import ProposalManager
from agents.core.evidence_store import EvidenceFabricStore


class TimestampIntegrityAgent(BaseSecOpsAdkAgent):
    """SecOps Telemetry Hygiene & Clock Drift Specialist.

    Monitors telemetry data quality, measures Δt between event and ingestion timestamps, identifies forwarder bottlenecks and NTP clock skews, tracks state progression, and maintains Evidence Fabric baselines.
    """

    CAPABILITIES = ['feed.timestamp_integrity_audit', 'feed.get_timestamp_integrity', 'dashboard.execute_query', 'feed.search', 'feed.get']

    def __init__(
        self,
        engine: Optional[SecOpsEngine] = None,
        proposal_manager: Optional[ProposalManager] = None,
        inventory_client: Any = None,
        evidence_store: Optional[EvidenceFabricStore] = None,
        work_queue: Optional[Any] = None,
        lifecycle_manager: Optional[Any] = None,
    ):
        super().__init__(
            name='Timestamp Integrity Agent',
            handle='@timestamp-integrity-agent',
            role='SecOps Telemetry Hygiene & Clock Drift Specialist',
            subsystem='ingestion',
            description='Monitors telemetry data quality, measures Δt between event and ingestion timestamps, identifies forwarder bottlenecks and NTP clock skews, tracks state progression, and maintains Evidence Fabric baselines.',
            system_instruction='You are the SecOps Timestamp Integrity Agent for Google SecOps (@timestamp-integrity-agent, aliases @timestamp-agent, @timestamp, @ntp-agent, @clock-skew-agent).\nYour mission is to continuously audit, diagnose, and safeguard telemetry data hygiene and ingestion latency across all log sources in Google SecOps.\nSpecifically, you:\n1. Audit Ingestion Timestamp Deltas (`feed.timestamp_integrity_audit`):\n   - Execute the statistical YARA-L 2 outcome query across Chronicle dashboardQueries to compute Δt = metadata.ingested_timestamp - metadata.event_timestamp.\n   - Categorize log volumes into 4 latency distribution buckets:\n     * Δt < 0 hours (Clock Skew / NTP Desynchronization / Future timestamps)\n     * 0-1 hours (Real-time ingestion flow)\n     * 1-2 hours (Moderate collector batching)\n     * >2 hours (Severe pipeline latency bottleneck)\n2. Maintain State-Aware Progression Tracking:\n   - Compare current telemetry metrics against historical baselines in Firestore Evidence Fabric (`timestamp_integrity/latest`).\n   - Classify every log type into one of 4 progression states:\n     * NEW (🔴): Anomaly appeared in the current window (average delay >60m or clock skew >0 events).\n     * PREVIOUSLY KNOWN (🟡): Persistent anomaly confirmed across consecutive evaluation runs.\n     * RESOLVED (🟢): Telemetry recovered to healthy real-time flow (<60m delay and 0 clock skew).\n     * HEALTHY (💚): Nominal real-time ingestion in both baseline and current evaluation.\n3. Retrieve Baselines & Historical Trends (`feed.get_timestamp_integrity`):\n   - Fetch current baseline and review comparative findings from Evidence Fabric Firestore collection `timestamp_integrity`.\n4. Perform Feed Deep Inspection (`feed.get`, `feed.search`):\n   - Correlate flagged log types with underlying ingestion feed configurations, collector types, and polling intervals.\n5. Synthesize GenAI Operational & Remediation Advisories:\n   - Produce structured 4-part executive briefs covering real-time flow, high-latency bottlenecks, NTP clock drifts, and host-level collector runbooks.\n6. Output Formatting & Conciseness Constraints:\n   - Provide an executive summary in at most 3 bullet points detailing total log sources audited, healthy vs anomalous count, and total clock-skewed events.\n   - Present individual feed findings in an interactive `timestamp_integrity_card` with KPI badges and distribution tables.\n7. Ambiguity & Clarification Guardrails:\n   - If the operator request does not specify a lookback window, default to evaluating the last 24 hours of ingestion telemetry.\n   - Never infer or invent log feed IDs; always discover feeds dynamically via `feed.search`.',
            model='gemini-3.8-flash',
            default_stream='ingestion',
            default_topic='timestamp-integrity',
            engine=engine,
            proposal_manager=proposal_manager,
            inventory_client=inventory_client,
            evidence_store=evidence_store,
            work_queue=work_queue,
            lifecycle_manager=lifecycle_manager,
        )

        # Bind declared capabilities from engine registry if engine is provided
        if self.engine:
            for cap_id in self.CAPABILITIES:
                cap = self.engine.registry.get(cap_id)
                if cap:
                    self.bind_capability(cap)

        self._tools["audit_timestamp_integrity"] = self.audit_timestamp_integrity
        self._tools["get_timestamp_integrity_report"] = self.get_timestamp_integrity_report
        self._tools["list_timestamp_integrity_history"] = self.list_timestamp_integrity_history

    def audit_timestamp_integrity(
        self,
        days: int = 7,
        clear_cache: bool = True,
    ) -> Dict[str, Any]:
        """Audits telemetry timestamp deltas, clock skews, and pipeline latency.

        Args:
            days: Telemetry lookback window in days (default: 7).
            clear_cache: Whether to bypass cache for live telemetry freshness.
        """
        if not self.engine:
            return {"status": "ERROR", "message": "SecOpsEngine not configured"}

        report = self.engine.audit_timestamp_integrity(
            days=days,
            clear_cache=clear_cache,
        )

        self.executed_tool_calls.append({
            "agent": self.handle,
            "tool": "audit_timestamp_integrity",
            "capability_id": "feed.timestamp_integrity_audit",
            "arguments": {"days": days, "clear_cache": clear_cache},
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })

        widget = {
            "type": "timestamp_integrity_card",
            "title": "Ingestion Timestamp Integrity & Latency Audit",
            "days": report.days,
            "summary": {
                "total_log_types": report.total_log_types_audited,
                "healthy_count": report.healthy_count,
                "new_anomalies_count": report.new_anomalies_count,
                "previously_known_count": report.previously_known_count,
                "resolved_count": report.resolved_count,
                "total_skewed_events": report.total_skewed_events,
                "total_delayed_events": report.total_delayed_events,
            },
            "comparative_findings": report.comparative_findings,
            "top_delayed": [lt.to_dict() for lt in report.top_delayed_log_types[:5]],
            "top_skewed": [lt.to_dict() for lt in report.top_skewed_log_types[:5]],
            "narrative": report.narrative,
        }
        tracking = None
        if self.evidence_store:
            skewed_events = report.total_skewed_events
            new_anomalies = report.new_anomalies_count
            todo_id = "todo_timestamp_integrity_active"
            if skewed_events > 0 or new_anomalies > 0:
                task = {
                    "todo_id": todo_id,
                    "title": f"Investigate {skewed_events:,} Future Logs & {new_anomalies} Telemetry Anomalies",
                    "target_agent": "@timestamp-integrity-agent",
                    "target_resource_id": "telemetry",
                    "action_type": "telemetry_remediation",
                    "stream": "ingestion",
                    "topic": "timestamp-integrity",
                    "priority": "HIGH" if skewed_events > 0 else "MEDIUM",
                    "status": "PENDING",
                    "action_prompt": "@timestamp-integrity-agent audit",
                    "rationale": f"Timestamp integrity audit identified {skewed_events:,} clock-skewed events (Δt < 0) and {new_anomalies} new telemetry delay anomalies.",
                }
                upserted_task, is_new = self.evidence_store.upsert_todo(todo_id, task)
                tracking = {
                    "todo_id": todo_id,
                    "is_new": is_new,
                    "sighting_count": upserted_task.get("sighting_count", 1),
                    "priority": upserted_task.get("priority", "MEDIUM"),
                    "status": upserted_task.get("status", "PENDING"),
                }
            elif skewed_events == 0 and new_anomalies == 0:
                resolved = self.evidence_store.resolve_todo(
                    todo_id,
                    reason="Timestamp integrity audit confirmed 0 clock-skewed events and 0 latency anomalies."
                )
                if resolved:
                    tracking = {
                        "todo_id": todo_id,
                        "status": "RESOLVED",
                        "auto_resolved": True,
                    }

        self.last_tracking = tracking
        widget["tracking"] = tracking
        self.last_widget = widget

        return {
            "status": "SUCCESS",
            "timestamp": report.timestamp,
            "days": report.days,
            "summary": {
                "total_log_types": report.total_log_types_audited,
                "healthy_count": report.healthy_count,
                "new_anomalies_count": report.new_anomalies_count,
                "previously_known_count": report.previously_known_count,
                "resolved_count": report.resolved_count,
                "total_skewed_events": report.total_skewed_events,
                "total_delayed_events": report.total_delayed_events,
            },
            "comparative_findings": report.comparative_findings,
            "log_types": [lt.to_dict() for lt in report.log_types],
            "top_delayed_log_types": [lt.to_dict() for lt in report.top_delayed_log_types],
            "top_skewed_log_types": [lt.to_dict() for lt in report.top_skewed_log_types],
            "narrative": report.narrative,
            "widget": widget,
            "tracking": tracking,
        }

    def get_timestamp_integrity_report(self) -> Dict[str, Any]:
        """Retrieves the latest stored timestamp integrity baseline from Evidence Fabric."""
        if not self.evidence_store:
            return {"status": "ERROR", "message": "EvidenceFabricStore not configured"}
        doc = self.evidence_store.get_latest_timestamp_integrity()
        if not doc:
            return {"status": "NOT_FOUND", "message": "No baseline timestamp integrity report found"}
        return {"status": "SUCCESS", "report": doc}

    def list_timestamp_integrity_history(self, limit: int = 50) -> Dict[str, Any]:
        """Lists historical timestamp integrity snapshots from Evidence Fabric."""
        if not self.evidence_store:
            return {"status": "ERROR", "message": "EvidenceFabricStore not configured"}
        history = self.evidence_store.list_timestamp_integrity_history(limit=limit)
        return {"status": "SUCCESS", "count": len(history), "history": history}
