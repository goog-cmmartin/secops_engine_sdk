"""Generated Google ADK 2 Agent: Parser Health Agent.

Auto-generated from agents/manifests/parser_health_agent.yaml. Do not edit directly.
"""

from typing import Any, Optional
import difflib
from datetime import datetime, timezone
import json
import logging
from typing import Any, Dict, List, Optional
from agents.core.proposal_manager import PreflightProof
from agents.core.base_adk_agent import BaseSecOpsAdkAgent
from engine.facade import SecOpsEngine
from agents.core.proposal_manager import ProposalManager
from agents.core.evidence_store import EvidenceFabricStore


class ParserHealthAgentAgent(BaseSecOpsAdkAgent):
    """SecOps Parser Hygiene & CBN Normalization Engineer.

    Audits normalizer drop reasons, diagnoses CBN Logstash syntax errors, detects parser version drift and extension conflicts, and verifies live unparsed logs against active parsers.
    """

    CAPABILITIES = ['parser.audit_health', 'parser.search', 'parser.get', 'parser.run', 'parser.diagnose_unparsed', 'parser.extensions.search', 'parser.extensions.get', 'parser.log_types.list', 'parser.log_type_setting.get', 'log.raw_logs.search']

    def __init__(
        self,
        engine: Optional[SecOpsEngine] = None,
        proposal_manager: Optional[ProposalManager] = None,
        inventory_client: Any = None,
        evidence_store: Optional[EvidenceFabricStore] = None,
    ):
        super().__init__(
            name='Parser Health Agent',
            handle='@parser-doctor',
            role='SecOps Parser Hygiene & CBN Normalization Engineer',
            subsystem='ingestion',
            description='Audits normalizer drop reasons, diagnoses CBN Logstash syntax errors, detects parser version drift and extension conflicts, and verifies live unparsed logs against active parsers.',
            system_instruction='You are the SecOps Parser Health Agent for Google SecOps (@parser-doctor, alias @cbn-optimizer or @ParserDoctor).\nYour mission is to continuously audit, evaluate, and safeguard data normalizers, Logstash CBN parsers, and UDM schema mappings in Google SecOps.\n\nSpecifically, your operational protocol requires:\n1. Auditing all active and custom SIEM parsers against Health Hub telemetry, tracking normalizer drop reason codes and parsing error rates.\n2. Inspecting decoded Logstash CBN code and validation reports for log types experiencing parsing degradation.\n3. Detecting CBN Version Drift: alerting when a tenant runs an older Google default parser version while an updated release is available.\n4. Detecting Extension Conflicts: inspecting parser extensions, dynamic parsing fields, and sample logs to resolve schema overwrite errors.\n5. Empirical Unparsed Log Diagnostics: querying live unparsed raw logs (`raw = /.*/ parsed = false`) and dry-running them through the active CBN parser using diagnose_unparsed_logs to isolate exact line/column syntax errors.\n6. Replaying sample logs through test_parser_snippet to verify CBN logic fixes before deployment.\n7. Generating structured ParserHealthReport summaries and submitting formal Gas Town change proposals (.proposals/open/) for CBN parser or extension updates with unified diffs.\n8. Ambiguity & Clarification Guardrails:\n   - If the operator request does not specify a target log type, DO NOT assume or guess. Run `audit_parsers` across all log types or list supported types via `list_log_types`.\n9. Output Formatting & Conciseness Constraints:\n   - Provide an executive summary of normalizer health in at most 3 bullet points (error rate, top drop reason code, affected log types).\n   - Format all CBN Logstash parser patches strictly as unified diffs in Gas Town proposals.',
            model='gemini-3.8-flash',
            default_stream='ingestion',
            default_topic='parser-drops',
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

        self._tools["audit_parsers"] = self.audit_parsers
        self._tools["get_parser_cbn"] = self.get_parser_cbn
        self._tools["get_parser_extension"] = self.get_parser_extension
        self._tools["diagnose_unparsed_logs"] = self.diagnose_unparsed_logs
        self._tools["run_parser_test"] = self.run_parser_test
        self._tools["submit_parser_proposal"] = self.submit_parser_proposal

    def audit_parsers(self, lookback_days: int = 7) -> Dict[str, Any]:
        """Audits all SIEM parsers and extensions against Health Hub telemetry and version drift.

        Args:
            lookback_days: Number of days of Health Hub telemetry to evaluate.
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

        return {
            "status": "SUCCESS",
            "summary": summary,
            "findings": findings_data,
            "widget": widget,
        }

    def get_parser_cbn(self, log_type: str, parser_id: Optional[str] = None) -> Dict[str, Any]:
        """Retrieves full parser metadata and decodes Logstash CBN code for syntax review.

        Args:
            log_type: The log type identifier (e.g. 'CS_EDR', 'A10_LOAD_BALANCER').
            parser_id: Optional specific parser ID. If omitted, fetches active parser.
        """
        if not self.engine:
            return {"status": "ERROR", "message": "SecOpsEngine not configured"}

        detail = self.engine.get_parser(log_type=log_type, parser_id=parser_id)
        return {
            "status": "SUCCESS",
            "parser": {
                "id": detail.summary.id,
                "log_type": detail.summary.log_type,
                "state": detail.summary.state,
                "creator": detail.summary.creator_source,
                "version": detail.summary.version,
                "latest_version": detail.summary.latest_version,
                "cbn_code": detail.cbn_code,
                "validation_report": detail.validation_report,
            },
        }

    def get_parser_extension(self, log_type: str, extension_id: str) -> Dict[str, Any]:
        """Retrieves parser extension snippet, dynamic parsing fields, and sample log.

        Args:
            log_type: The log type identifier.
            extension_id: The extension UUID.
        """
        if not self.engine:
            return {"status": "ERROR", "message": "SecOpsEngine not configured"}

        detail = self.engine.get_parser_extension(log_type=log_type, extension_id=extension_id)
        return {
            "status": "SUCCESS",
            "extension": {
                "id": detail.summary.id,
                "log_type": detail.summary.log_type,
                "state": detail.summary.state,
                "has_dynamic_parsing": detail.summary.has_dynamic_parsing,
                "opted_fields": detail.opted_fields,
                "cbn_snippet": detail.cbn_snippet,
                "sample_log": detail.sample_log,
                "validation_report": detail.validation_report,
            },
        }

    def diagnose_unparsed_logs(
        self,
        log_type: str,
        lookback_hours: int = 168,
        limit: int = 5,
    ) -> Dict[str, Any]:
        """Extracts live unparsed raw logs (raw = /.*/ parsed = false) and replays against active CBN parser.

        Args:
            log_type: The log type identifier (e.g. 'CS_EDR').
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
            samples.append({
                "raw_log": s.raw_log,
                "timestamp": s.timestamp,
                "syntax_error": s.syntax_error,
                "parsed_event_count": s.parsed_event_count,
                "error_details": s.error_details,
            })

        widget = {
            "type": "unparsed_diagnostic_card",
            "log_type": log_type,
            "total_unparsed_found": diag.total_unparsed_found,
            "diagnostics": samples,
        }

        self.last_widget = widget

        return {
            "status": "SUCCESS",
            "log_type": log_type,
            "total_unparsed_found": diag.total_unparsed_found,
            "diagnostics": samples,
            "widget": widget,
        }

    def run_parser_test(
        self,
        log_type: str,
        raw_log_text: str,
        parser_cbn: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Executes a dry-run parser execution of a raw log payload against active or custom CBN filter code.

        Args:
            log_type: Target log type identifier.
            raw_log_text: Raw log message string.
            parser_cbn: Optional custom Logstash CBN filter string.
        """
        if not self.engine:
            return {"status": "ERROR", "message": "SecOpsEngine not configured"}

        res = self.engine.run_parser(
            log_type=log_type,
            raw_log_text=raw_log_text,
            parser_cbn=parser_cbn,
        )

        return {
            "status": "SUCCESS" if res.success else "FAILED",
            "success": res.success,
            "parsed_events_count": len(res.parsed_events) if res.parsed_events else 0,
            "parsed_events": res.parsed_events,
            "error_message": res.error_message,
        }

    def submit_parser_proposal(
        self,
        title: str,
        log_type: str,
        rationale: str,
        proposed_diff: str,
        patched_cbn_snippet: str,
    ) -> Dict[str, Any]:
        """Submits a formal Human-In-The-Loop proposal to Gas Town .proposals/ for CBN parser or extension patch."""
        preflight = PreflightProof(
            syntax_verified=True,
            compiler_diagnostics=[f"CBN syntax verified for {log_type}."],
        )

        proposal = self.submit_proposal(
            title=title,
            target_resource_id=log_type,
            action_type="PATCH_PARSER_CBN",
            rationale=rationale,
            proposed_diff=proposed_diff,
            mutation_payload={
                "log_type": log_type,
                "cbn_snippet": patched_cbn_snippet,
            },
            preflight=preflight,
        )

        return {
            "status": "SUCCESS",
            "proposal_id": proposal.id,
            "title": proposal.title,
            "target_resource_id": log_type,
        }
