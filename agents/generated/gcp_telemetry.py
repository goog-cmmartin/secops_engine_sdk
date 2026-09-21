"""Generated Google ADK 2 Agent: GCP Telemetry Agent.

Auto-generated from agents/manifests/gcp_telemetry.yaml. Do not edit directly.
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


class GcpTelemetryAgent(BaseSecOpsAdkAgent):
    """Google Cloud Logging & Monitoring Telemetry Specialist.

    Investigates Google Cloud Logging audit and error logs for Chronicle & SOAR, queries Cloud Monitoring time series for ingestion, normalizer throughput, API consumption, and forwarder agent telemetry.
    """

    CAPABILITIES = ['gcp_logging.search', 'gcp_monitoring.time_series']

    def __init__(
        self,
        engine: Optional[SecOpsEngine] = None,
        proposal_manager: Optional[ProposalManager] = None,
        inventory_client: Any = None,
        evidence_store: Optional[EvidenceFabricStore] = None,
    ):
        super().__init__(
            name='GCP Telemetry Agent',
            handle='@gcp-telemetry-agent',
            role='Google Cloud Logging & Monitoring Telemetry Specialist',
            subsystem='gcp_telemetry',
            description='Investigates Google Cloud Logging audit and error logs for Chronicle & SOAR, queries Cloud Monitoring time series for ingestion, normalizer throughput, API consumption, and forwarder agent telemetry.',
            system_instruction='You are the GCP Telemetry Agent for Google SecOps (@gcp-telemetry-agent).\nYour mission is to monitor, query, analyze, and diagnose Google Cloud Logging and Google Cloud Monitoring telemetry for Google SecOps (Chronicle SIEM & SOAR).\nSpecifically, you:\n1. Query Google Cloud Monitoring time series (`gcp_monitoring.time_series`, `query_metrics`):\n   - Ingestion volume & counts (`chronicle.googleapis.com/collector/ingestion/...`).\n   - Normalizer throughput (`chronicle.googleapis.com/normalizer/throughput/...`).\n   - API request volume & error rates (`serviceruntime.googleapis.com/api/request_count` for service `chronicle.googleapis.com`).\n   - Forwarder agent performance (`chronicle.googleapis.com/agent/cpu_seconds`, queue size).\n2. Query Google Cloud Logging entries (`gcp_logging.search`, `search_audit_logs`):\n   - Cloud Audit activity and policy change logs (`cloudaudit.googleapis.com`).\n   - Forwarder error logs and connectivity warnings.\n   - SOAR execution and playbook errors.\n3. Execute cross-correlated telemetry audits (`audit_chronicle_telemetry`):\n   - Automatically correlate metric anomalies (e.g. ingestion volume drops) with corresponding Cloud Logging error entries over the same time window.\n4. Ambiguity & Clarification Guardrails:\n   - If the operator request does not specify a lookback time window or target log_type / project / service, DO NOT assume or fabricate parameters. Default to the last 24 hours or ask a concise clarifying question before guessing.\n5. Output Formatting & Conciseness Constraints:\n   - Deliver actionable responses: provide an executive summary in at most 3 bullet points (ingestion health, normalizer throughput, and error/audit count).\n   - Present metric counts and error findings clearly with timestamps and severity indicators.',
            model='gemini-3.8-flash',
            default_stream='telemetry',
            default_topic='logs-and-metrics',
            engine=engine,
            proposal_manager=proposal_manager,
            inventory_client=inventory_client,
            evidence_store=evidence_store,
        )

        # Bind declared capabilities from engine registry if engine is provided
        if self.engine:
            for cap_id in self.CAPABILITIES:
                cap = self.engine.registry.get(cap_id)
                if cap:
                    self.bind_capability(cap)

        self._tools["audit_chronicle_telemetry"] = self.audit_chronicle_telemetry
        self._tools["query_metrics"] = self.query_metrics
        self._tools["search_audit_logs"] = self.search_audit_logs

    def audit_chronicle_telemetry(
        self,
        hours: int = 24,
        log_type: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Audits Chronicle telemetry by cross-correlating Cloud Monitoring metrics with Cloud Logging errors.

        Args:
            hours: Lookback window in hours (default: 24).
            log_type: Optional log type filter (e.g. WINEVTLOG, PAN_FIREWALL).
        """
        if not self.engine:
            return {"status": "ERROR", "message": "SecOpsEngine not configured"}

        # 1. Fetch Cloud Monitoring metrics across streams
        ingestion = self.engine.get_chronicle_ingestion_metrics(hours=hours, log_type=log_type)
        normalizer = self.engine.get_chronicle_normalizer_metrics(hours=hours, log_type=log_type)
        api = self.engine.get_chronicle_api_metrics(hours=hours)

        # 2. Fetch high-severity Cloud Logging error events
        error_filter = 'severity >= WARNING AND (resource.type = "chronicle.googleapis.com" OR logName : "cloudaudit.googleapis.com" OR logName : "chronicle.googleapis.com")'
        if log_type:
            error_filter += f' AND "{log_type}"'

        logs_res = self.engine.query_cloud_logging(
            filter_str=error_filter,
            page_size=25,
        )

        # 3. Format telemetry streams
        ingestion_streams = []
        for s in ingestion.time_series:
            latest_val = s.points[0].value if s.points else 0
            ingestion_streams.append({
                "metric_type": s.metric_type,
                "labels": s.metric_labels,
                "latest_value": latest_val,
                "points_count": len(s.points),
            })

        normalizer_streams = []
        for s in normalizer.time_series:
            latest_val = s.points[0].value if s.points else 0
            normalizer_streams.append({
                "metric_type": s.metric_type,
                "labels": s.metric_labels,
                "latest_value": latest_val,
                "points_count": len(s.points),
            })

        api_streams = []
        for s in api.time_series:
            latest_val = s.points[0].value if s.points else 0
            api_streams.append({
                "metric_type": s.metric_type,
                "labels": s.metric_labels,
                "latest_value": latest_val,
                "points_count": len(s.points),
            })

        error_entries = [
            {
                "log_name": e.log_name,
                "severity": e.severity,
                "timestamp": e.timestamp,
                "summary": e.text_payload or (e.json_payload.get("message") if e.json_payload else "API Error"),
                "resource_type": e.resource_type,
            }
            for e in logs_res.entries[:10]
        ]

        summary = {
            "hours": hours,
            "log_type": log_type or "ALL",
            "ingestion_streams_count": ingestion.total_series,
            "normalizer_streams_count": normalizer.total_series,
            "api_streams_count": api.total_series,
            "error_logs_count": len(logs_res.entries),
            "generated_at": datetime.now(timezone.utc).isoformat(),
        }

        widget = {
            "type": "gcp_telemetry_card",
            "summary": summary,
            "ingestion_streams": ingestion_streams[:5],
            "normalizer_streams": normalizer_streams[:5],
            "api_streams": api_streams[:5],
            "recent_errors": error_entries,
        }

        self.last_widget = widget

        self.executed_tool_calls.append({
            "agent": self.handle,
            "tool": "audit_chronicle_telemetry",
            "capability_id": "gcp_monitoring.time_series",
            "arguments": {"hours": hours, "log_type": log_type},
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })

        return {
            "status": "SUCCESS",
            "summary": summary,
            "ingestion_streams": ingestion_streams,
            "normalizer_streams": normalizer_streams,
            "api_streams": api_streams,
            "error_entries": error_entries,
            "widget": widget,
        }

    def query_metrics(
        self,
        filter_str: str,
        hours: int = 24,
        alignment_period: str = "3600s",
        per_series_aligner: str = "ALIGN_SUM",
        cross_series_reducer: Optional[str] = None,
        group_by_fields: Optional[List[str]] = None,
        page_size: int = 50,
    ) -> Dict[str, Any]:
        """Queries Google Cloud Monitoring time series data directly.

        Args:
            filter_str: Cloud Monitoring filter expression.
            hours: Lookback window in hours (default: 24).
            alignment_period: Time window to align data (default: 3600s).
            per_series_aligner: Aligner across points (default: ALIGN_SUM).
            cross_series_reducer: Optional reducer across streams.
            group_by_fields: Optional grouping fields.
            page_size: Maximum time series to return.
        """
        if not self.engine:
            return {"status": "ERROR", "message": "SecOpsEngine not configured"}

        result = self.engine.query_cloud_monitoring(
            filter_str=filter_str,
            hours=hours,
            alignment_period=alignment_period,
            per_series_aligner=per_series_aligner,
            cross_series_reducer=cross_series_reducer,
            group_by_fields=group_by_fields,
            page_size=page_size,
        )

        series_data = [
            {
                "metric_type": s.metric_type,
                "labels": s.metric_labels,
                "resource_type": s.resource_type,
                "points": [{"end_time": p.end_time, "value": p.value} for p in s.points[:10]],
            }
            for s in result.time_series
        ]

        self.executed_tool_calls.append({
            "agent": self.handle,
            "tool": "query_metrics",
            "capability_id": "gcp_monitoring.time_series",
            "arguments": {"filter_str": filter_str, "hours": hours},
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })

        return {
            "status": "SUCCESS",
            "total_series": result.total_series,
            "time_interval": result.time_interval,
            "filter_applied": result.filter_applied,
            "time_series": series_data,
        }

    def search_audit_logs(
        self,
        hours: int = 24,
        filter_str: Optional[str] = None,
        human_only: bool = False,
        page_size: int = 50,
    ) -> Dict[str, Any]:
        """Queries Google Cloud Logging for Chronicle and SecOps audit activity logs.

        Args:
            hours: Lookback window in hours (default: 24).
            filter_str: Optional custom Cloud Logging filter.
            human_only: If True, filters out automated service accounts.
            page_size: Maximum log entries to retrieve.
        """
        if not self.engine:
            return {"status": "ERROR", "message": "SecOpsEngine not configured"}

        if filter_str:
            result = self.engine.query_cloud_logging(
                filter_str=filter_str,
                page_size=page_size,
            )
        else:
            result = self.engine.query_secops_audit_logs(
                hours=hours,
                human_only=human_only,
                page_size=page_size,
            )

        entries = [
            {
                "log_name": e.log_name,
                "severity": e.severity,
                "timestamp": e.timestamp,
                "principal": e.principal_email,
                "method_name": e.method_name,
                "resource_type": e.resource_type,
            }
            for e in result.entries
        ]

        self.executed_tool_calls.append({
            "agent": self.handle,
            "tool": "search_audit_logs",
            "capability_id": "gcp_logging.search",
            "arguments": {"hours": hours, "human_only": human_only},
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })

        return {
            "status": "SUCCESS",
            "total_entries": len(entries),
            "filter_applied": result.filter_applied,
            "entries": entries,
        }
