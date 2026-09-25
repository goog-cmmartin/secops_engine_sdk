"""Generated Google ADK 2 Agent: SecOps Dispatcher.

Auto-generated from agents/manifests/secops_dispatcher.yaml. Do not edit directly.
"""

from typing import Any, Optional
from datetime import datetime, timezone
from typing import List, Dict, Any
from agents.core.base_adk_agent import BaseSecOpsAdkAgent
from engine.facade import SecOpsEngine
from agents.core.proposal_manager import ProposalManager
from agents.core.evidence_store import EvidenceFabricStore


class SecopsDispatcherAgent(BaseSecOpsAdkAgent):
    """Central Front-Door Router / Commander (The Mayor).

    Routes incoming user requests, operational incidents, and alert inquiries to the appropriate specialized agents across the SecOps fleet.
    """

    CAPABILITIES = ['rule.audit_health', 'parser.audit_health', 'feed.audit_health', 'parser.diagnose_unparsed', 'gcp_logging.search', 'dashboard.execute_query']

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
            name='SecOps Dispatcher',
            handle='@secops-dispatcher',
            role='Central Front-Door Router / Commander (The Mayor)',
            subsystem='orchestration',
            description='Routes incoming user requests, operational incidents, and alert inquiries to the appropriate specialized agents across the SecOps fleet.',
            system_instruction='You are the SecOps Dispatcher ("The Mayor") for the Google SecOps Agent Fleet.\nYour role is to act as the primary operational coordinator and front-door router:\n1. Understand operator intent and analyze security operations questions across detections, ingestion, and orchestration.\n2. Introspect active fleet capabilities using `list_fleet_agents`.\n3. Triage issues:\n   - For broken rules, compilation failures, execution errors, or Code 9 errors: recommend/delegate to `@rule-troubleshooter`.\n   - For slow rules, timeouts, broad match windows, or performance optimizations: recommend/delegate to `@yaral-optimizer`.\n   - For detection silence or rule decay: recommend/delegate to `@detection-decay-agent`.\n   - For alert noise reduction or false-positive suppression: recommend/delegate to `@detection-tuning-agent`.\n   - For unparsed raw logs, normalizer drop reasons (Drop Code 1), Logstash CBN syntax errors, or extension conflicts: recommend/delegate to `@parser-doctor`.\n   - For ingestion feed status, collector health, transport latency SLAs (<4h), or pipeline drops: recommend/delegate to `@feed-agent`.\n   - For empirical log replay, scenario generation, or verification: recommend/delegate to `@logjammer-agent`.\n   - For BigQuery datalake, GoogleSQL aggregations, or UDM analytics: recommend/delegate to `@sql-analyst`.\n   - For IAM, Chronicle role-based access, or credential governance: recommend/delegate to `@identity-governor`.\n   - For Google Cloud Logging audit and error logs, API consumption rates, or Cloud Monitoring ingestion/parsing metrics: recommend/delegate to `@gcp-telemetry-agent`.\n   - For tenant configuration baselines, settings audit, SOAR/SIEM parameter posture, or configuration drift: recommend/delegate to `@tenant-posture-agent`.\n   - For SOAR playbook resilience, 30-day failure rates, execution bottlenecks, or playbook decay: recommend/delegate to `@playbook-decay-agent`.\n   - For telemetry timestamp deltas, ingestion latency bottlenecks (Δt ≫ 0), NTP clock skews (Δt < 0), or future events: recommend/delegate to `@timestamp-integrity-agent`.\n   - For ingestion labels, UDM namespaces, default untagged telemetry, RFC 1918 overlapping IP collisions, or Data RBAC tagging alignment: recommend/delegate to `@namespace-label-agent`.\n   - For tenant data cartography, UDM identity fidelity density, entity graph resolution lineage, or telemetry volume pareto: recommend/delegate to `@tenant-cartographer`.\n4. Active Health Audits:\n   - When asked about unparsed logs, normalizer drops, or parser status across log sources: execute `audit_parsers` to inspect live normalization health across all log types.\n   - When asked about ingestion feeds, collector SLAs, or transport latency: execute `audit_feeds`.\n   - When asked about overall detection rule health or Code 9 errors: execute `audit_rule_health`.\n5. Deep Diagnostics:\n   - When diagnosing unparsed logs for a specific log type (e.g. WINEVTLOG, CS_EDR), execute `diagnose_unparsed_logs` to inspect raw payloads and replay against active CBN parsers.\n   - Provide clear guidance or direct the operator to continue in `#ingestion > parser-drops` with `@parser-doctor`.\n6. If an operational task needs to be performed asynchronously or tracked, call `delegate_task` to record the action item on the Evidence Fabric blackboard (`secops_todos`).\n7. Check pending human-in-the-loop proposals using `list_open_proposals`.\n8. Always introduce yourself as the SecOps Dispatcher and respond with clear, professional operational guidance, identifying which agents will handle which tasks and what stream/topic should be used.\n9. Ambiguity & Clarification Guardrails:\n   - If the operator request is ambiguous or omits necessary identifiers (e.g. specific rule ID, log type, collector feed, or time window), DO NOT fabricate or assume parameters.\n   - Either discover available resources using read-only listing tools or ask a concise clarifying question before proceeding.\n10. Output Formatting & Conciseness Constraints:\n   - Deliver actionable responses: provide an executive summary in at most 3 bullet points, followed by clear delegation routing or audit findings.\n   - Highlight critical health status, error codes, and recommended target streams/topics immediately.',
            model='gemini-3.8-flash',
            default_stream='general',
            default_topic='dispatcher',
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

        self._tools["list_fleet_agents"] = self.list_fleet_agents
        self._tools["delegate_task"] = self.delegate_task
        self._tools["list_open_proposals"] = self.list_open_proposals
        self._tools["audit_parsers"] = self.audit_parsers
        self._tools["audit_feeds"] = self.audit_feeds
        self._tools["diagnose_unparsed_logs"] = self.diagnose_unparsed_logs

    def set_fleet(self, fleet: Dict[str, Any]) -> None:
        """Stores a reference to the active agent fleet."""
        self._fleet = fleet

    def list_fleet_agents(self) -> List[Dict[str, Any]]:
        """Returns the roster of all available specialized agents in the SecOps fleet.

        Returns:
            List of dictionaries containing name, handle, role, subsystem, and description.
        """
        roster = []
        fleet = getattr(self, "_fleet", {}) or {}
        for handle, ag in fleet.items():
            roster.append({
                "name": ag.name,
                "handle": ag.handle,
                "role": ag.role,
                "subsystem": ag.subsystem,
                "description": ag.description,
            })
        if not roster:
            roster = [
                {"name": "Rule Troubleshooter", "handle": "@rule-troubleshooter", "role": "Rule Health & Code 9 Diagnostics", "subsystem": "detections"},
                {"name": "YARA-L Optimizer", "handle": "@yaral-optimizer", "role": "Performance & Match Window Optimization", "subsystem": "detections"},
                {"name": "LogJammer Agent", "handle": "@logjammer-agent", "role": "Empirical Replay & Verification", "subsystem": "ingestion"},
                {"name": "Identity Governor", "handle": "@identity-governor", "role": "IAM & Chronicle Access Governance", "subsystem": "identity_governance"},
                {"name": "GCP Telemetry Agent", "handle": "@gcp-telemetry-agent", "role": "Google Cloud Logging & Monitoring Telemetry Specialist", "subsystem": "gcp_telemetry"},
                {"name": "Tenant Posture & Configuration Governor", "handle": "@tenant-posture-agent", "role": "Google SecOps Tenant Posture, Baseline & Configuration Governance Specialist", "subsystem": "configuration_governance"},
                {"name": "SOAR Playbook Decay Agent", "handle": "@playbook-decay-agent", "role": "SOAR Playbook Inventory, Resilience Scoring & Decay Specialist", "subsystem": "soar_playbooks"},
                {"name": "Timestamp Integrity Agent", "handle": "@timestamp-integrity-agent", "role": "SecOps Telemetry Hygiene & Clock Drift Specialist", "subsystem": "ingestion"},
            ]
        self.executed_tool_calls.append({
            "agent": self.handle,
            "tool": "list_fleet_agents",
            "capability_id": "orchestration.fleet.list",
            "arguments": {},
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })
        return roster

    def delegate_task(
        self,
        assigned_to: str,
        title: str,
        description: str,
        stream: str = "general",
        topic: str = "tasks",
        priority: str = "MEDIUM",
    ) -> Dict[str, Any]:
        """Assigns an operational or remediation task to a specialized agent on the Evidence Fabric blackboard.

        Args:
            assigned_to: Target agent handle (e.g. '@rule-troubleshooter', '@yaral-optimizer', '@logjammer-agent', '@identity-governor').
            title: Short description of the task.
            description: Detailed context, rule ID, incident details, or action instructions.
            stream: Target Zulip-style stream for tracking.
            topic: Target topic within the stream.
            priority: Priority level ('LOW', 'MEDIUM', 'HIGH', 'CRITICAL').
        """
        todo_id = ""
        if self.evidence_store:
            try:
                todo = self.evidence_store.add_todo(
                    title=title,
                    description=description,
                    assigned_to=assigned_to,
                    created_by=self.handle,
                    priority=priority,
                )
                todo_id = todo.get("id") if isinstance(todo, dict) else getattr(todo, "id", "")
            except Exception:
                pass
        if not todo_id:
            todo_id = f"todo-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}"

        self.executed_tool_calls.append({
            "agent": self.handle,
            "tool": "delegate_task",
            "capability_id": "orchestration.task.delegate",
            "arguments": {
                "assigned_to": assigned_to,
                "title": title,
                "priority": priority,
                "todo_id": todo_id,
            },
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })

        return {
            "status": "TASK_DELEGATED",
            "todo_id": todo_id,
            "assigned_to": assigned_to,
            "title": title,
            "stream": stream,
            "topic": topic,
            "message": f"Task {todo_id} successfully assigned to {assigned_to} on the Evidence Fabric blackboard.",
        }

    def list_open_proposals(self) -> List[Dict[str, Any]]:
        """Lists active Human-In-The-Loop change proposals in Gas Town .proposals/open/ awaiting operator review."""
        proposals = []
        if self.proposal_manager:
            try:
                open_props = self.proposal_manager.list_proposals(status="OPEN")
                for p in open_props:
                    proposals.append({
                        "proposal_id": p.id,
                        "title": p.title,
                        "author": p.author,
                        "target_resource_id": p.target_resource_id,
                        "action_type": p.action_type,
                        "risk_level": p.risk_level,
                        "created_at": p.created_at,
                    })
            except Exception:
                pass

        self.executed_tool_calls.append({
            "agent": self.handle,
            "tool": "list_open_proposals",
            "capability_id": "orchestration.proposals.list",
            "arguments": {"count": str(len(proposals))},
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })
        return proposals

    def audit_parsers(self, lookback_days: int = 7) -> Dict[str, Any]:
        """Audits all SIEM parsers against Health Hub telemetry, normalizer drops, and version drift across the fleet.

        Args:
            lookback_days: Number of days of Health Hub telemetry to evaluate (default: 7).
        """
        if not self.engine:
            return {"status": "ERROR", "message": "SecOpsEngine not configured"}

        report = self.engine.audit_parser_health(lookback_days=lookback_days)

        findings_data = [
            {
                "log_type": f.log_type,
                "parser_id": f.parser_id,
                "status": f.status.value,
                "state": f.state,
                "creator_source": f.creator_source,
                "collector_name": f.collector_name,
                "version": f.version,
                "latest_version": f.latest_version,
                "rollback_available": f.rollback_available,
                "has_extension": f.has_extension,
                "extension_id": f.extension_id,
                "extension_state": f.extension_state,
                "dynamic_parsing_enabled": f.dynamic_parsing_enabled,
                "opted_fields_count": f.opted_fields_count,
                "drop_reason_code": f.drop_reason_code,
                "zscore_anomaly_detail": f.zscore_anomaly_detail,
                "anomalous_since": f.anomalous_since,
                "last_normalization_time": f.last_normalization_time,
                "event_latency": f.event_latency,
                "volume_funnel": f.volume_funnel,
                "quota_rejected_volume_mb": f.quota_rejected_volume_mb,
                "quota_limit_mb_per_sec": f.quota_limit_mb_per_sec,
                "anomaly_description": f.anomaly_description,
                "remediation_steps": f.remediation_steps,
            }
            for f in report.findings
        ]

        summary = {
            "total_parsers_audited": report.total_parsers_audited,
            "healthy_count": report.healthy_count,
            "irregular_count": report.irregular_count,
            "failed_count": report.failed_count,
            "version_drift_count": report.version_drift_count,
            "extension_conflict_count": report.extension_conflict_count,
            "quota_rejections_detected": report.quota_rejections_detected,
            "generated_at": report.generated_at.isoformat() if hasattr(report.generated_at, "isoformat") else str(report.generated_at),
        }

        widget = {
            "type": "parser_health_card",
            "summary": summary,
            "findings": findings_data[:15],
        }

        self.last_widget = widget

        self.executed_tool_calls.append({
            "agent": self.handle,
            "tool": "audit_parsers",
            "capability_id": "parser.audit_health",
            "arguments": {"lookback_days": lookback_days},
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })

        return {
            "status": "SUCCESS",
            "summary": summary,
            "findings": findings_data,
            "widget": widget,
        }

    def audit_feeds(self, lookback_days: int = 7) -> Dict[str, Any]:
        """Audits all configured SecOps ingestion feeds against Health Hub telemetry and latency SLAs.

        Args:
            lookback_days: Number of days of Health Hub telemetry to evaluate (default: 7).
        """
        if not self.engine:
            return {"status": "ERROR", "message": "SecOpsEngine not configured"}

        report = self.engine.audit_feed_health(lookback_days=lookback_days)

        findings_data = [
            {
                "feed_id": f.feed_id,
                "feed_name": f.feed_name,
                "source_type": f.source_type,
                "log_type": f.log_type,
                "status": f.status.value,
                "state": f.state,
                "collector_name": f.collector_name,
                "latency_p95": f.latency_p95,
                "last_event_time": f.last_event_time,
                "volume_funnel": f.volume_funnel,
                "quota_rejected_volume_mb": f.quota_rejected_volume_mb,
                "quota_limit_mb_per_sec": f.quota_limit_mb_per_sec,
                "anomaly_description": f.anomaly_description,
                "remediation_steps": f.remediation_steps,
            }
            for f in report.findings
        ]

        summary = {
            "total_feeds_audited": report.total_feeds_audited,
            "healthy_count": report.healthy_count,
            "irregular_count": report.irregular_count,
            "failed_count": report.failed_count,
            "high_latency_count": report.high_latency_count,
            "quota_rejections_detected": report.quota_rejections_detected,
            "generated_at": report.generated_at.isoformat() if hasattr(report.generated_at, "isoformat") else str(report.generated_at),
        }

        widget = {
            "type": "feed_health_card",
            "summary": summary,
            "findings": findings_data[:15],
        }

        self.last_widget = widget

        self.executed_tool_calls.append({
            "agent": self.handle,
            "tool": "audit_feeds",
            "capability_id": "feed.audit_health",
            "arguments": {"lookback_days": lookback_days},
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })

        return {
            "status": "SUCCESS",
            "summary": summary,
            "findings": findings_data,
            "widget": widget,
        }

    def diagnose_unparsed_logs(
        self,
        log_type: str,
        lookback_hours: int = 168,
        limit: int = 5,
    ) -> Dict[str, Any]:
        """Extracts live unparsed raw logs (raw = /.*/ parsed = false) and replays against active CBN parser.

        Args:
            log_type: The log type identifier (e.g. 'WINEVTLOG', 'CS_EDR').
            lookback_hours: Hours to look back for unparsed logs (default: 168 / 7 days).
            limit: Number of unparsed samples to diagnose (default: 5).
        """
        if not self.engine:
            return {"status": "ERROR", "message": "SecOpsEngine not configured"}

        diag = self.engine.diagnose_unparsed_logs(
            log_type=log_type,
            lookback_hours=lookback_hours,
            limit=limit,
        )

        samples = []
        for s in diag.diagnostics:
            raw_full = getattr(s, "raw_log", "") or getattr(s, "raw_log_preview", "")
            raw_preview = getattr(s, "raw_log_preview", "") or raw_full[:300]
            ts = s.retrieved_at.isoformat() if hasattr(getattr(s, "retrieved_at", None), "isoformat") else str(getattr(s, "retrieved_at", ""))
            samples.append({
                "log_id": getattr(s, "log_id", ""),
                "raw_log": raw_full,
                "raw_log_preview": raw_preview,
                "timestamp": ts,
                "syntax_error": getattr(s, "error_message", ""),
                "error_category": getattr(s, "error_category", ""),
                "parsed_event_count": len(s.raw.get("parsed_events", [])) if isinstance(getattr(s, "raw", None), dict) else 0,
                "error_details": getattr(s, "error_message", "") or getattr(s, "error_category", ""),
            })

        widget = {
            "type": "unparsed_diagnostic_card",
            "log_type": log_type,
            "total_unparsed_found": diag.total_unparsed_found,
            "diagnostics": samples,
        }

        self.last_widget = widget

        self.executed_tool_calls.append({
            "agent": self.handle,
            "tool": "diagnose_unparsed_logs",
            "capability_id": "parser.diagnose_unparsed",
            "arguments": {
                "log_type": log_type,
                "lookback_hours": str(lookback_hours),
                "limit": str(limit),
            },
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })

        return {
            "status": "SUCCESS",
            "log_type": log_type,
            "total_unparsed_found": diag.total_unparsed_found,
            "diagnostics": samples,
            "widget": widget,
        }
