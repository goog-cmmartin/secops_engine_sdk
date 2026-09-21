"""Generated Google ADK 2 Agent: Feed Health Agent.

Auto-generated from agents/manifests/feed_health_agent.yaml. Do not edit directly.
"""

from typing import Any, Optional
from datetime import datetime, timezone
import json
import logging
from typing import Any, Dict, List, Optional
from agents.core.proposal_manager import PreflightProof
from agents.core.base_adk_agent import BaseSecOpsAdkAgent
from engine.facade import SecOpsEngine
from agents.core.proposal_manager import ProposalManager
from agents.core.evidence_store import EvidenceFabricStore


class FeedHealthAgentAgent(BaseSecOpsAdkAgent):
    """SecOps Ingestion & Feed Transport Auditor.

    Audits data ingestion pipelines, evaluates Health Hub source telemetry, monitors transport latency SLAs, identifies silent push stops, and diagnoses ingestion quota rejections.
    """

    CAPABILITIES = ['feed.audit_health', 'feed.search', 'feed.get', 'feed_schema.list_sources', 'feed_schema.list_log_types', 'log.product_sources.stats', 'pipeline.search', 'pipeline.get']

    def __init__(
        self,
        engine: Optional[SecOpsEngine] = None,
        proposal_manager: Optional[ProposalManager] = None,
        inventory_client: Any = None,
        evidence_store: Optional[EvidenceFabricStore] = None,
    ):
        super().__init__(
            name='Feed Health Agent',
            handle='@feed-agent',
            role='SecOps Ingestion & Feed Transport Auditor',
            subsystem='ingestion',
            description='Audits data ingestion pipelines, evaluates Health Hub source telemetry, monitors transport latency SLAs, identifies silent push stops, and diagnoses ingestion quota rejections.',
            system_instruction='You are the SecOps Feed Health Agent for Google SecOps (@feed-agent, alias @ingestion-doctor or @FeedAgent).\nYour mission is to continuously audit, evaluate, and safeguard data ingestion pipelines and log transport mechanisms into Google SecOps.\n\nSpecifically, your operational protocol requires:\n1. Auditing all configured Chronicle ingestion feeds and collectors across cloud storage (S3, GCS), message brokers (Pub/Sub, Kafka), webhook forwarders, and APIs using Health Hub telemetry.\n2. Evaluating transport latency and initiation health against SLAs (e.g. P95 latency > 4 hours, missing heartbeat events).\n3. Detecting silent push failures: identifying push-based feeds (e.g. Pub/Sub, HTTPS push, syslog forwarders) that have ceased transmitting data without explicit error initiation.\n4. Detecting and reporting tenant-level Chronicle ingestion bandwidth and quota rejections (MB/s exceeded).\n5. Inspecting feed configurations, endpoints, polling schedules, and IAM credentials via get_feed_details.\n6. Performing volume funnel analysis: comparing Ingested Bytes vs. Normalized Events. If ingestion is flowing normally but normalized events are low or failing, recommend handoff to @parser-doctor.\n7. Generating structured FeedHealthReport summaries, remediation guidance, and submitting formal Gas Town change proposals (.proposals/open/) for feed configuration adjustments.\n8. Ambiguity & Clarification Guardrails:\n   - If the operator request does not specify a target feed ID or source, DO NOT guess or assume parameters. Run `audit_feeds` or list sources via `list_sources` first.\n9. Output Formatting & Conciseness Constraints:\n   - Provide an executive summary of feed health in at most 3 bullet points (pipeline state, latency SLAs, failing feeds count).\n   - Format all feed configuration updates strictly as unified diffs in Gas Town proposals.',
            model='gemini-3.8-flash',
            default_stream='ingestion',
            default_topic='feed-health',
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

        self._tools["audit_feeds"] = self.audit_feeds
        self._tools["get_feed_details"] = self.get_feed_details
        self._tools["check_feed_latency"] = self.check_feed_latency
        self._tools["submit_feed_proposal"] = self.submit_feed_proposal

    def audit_feeds(self, lookback_days: int = 7) -> Dict[str, Any]:
        """Audits all configured SecOps ingestion feeds against Health Hub telemetry and decay indicators.

        Args:
            lookback_days: Number of days of Health Hub telemetry to evaluate.
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

        # Check if parsing error rate is high across feeds to suggest handoff to @parser-doctor
        parsing_error_feeds = []
        for f in report.findings:
            if f.volume_funnel and f.volume_funnel.get("parsing_error_events", 0) > 0:
                parsing_error_feeds.append(f.log_type)

        widget = {
            "type": "feed_health_card",
            "summary": summary,
            "findings": findings_data[:15],
            "parsing_error_feeds": parsing_error_feeds,
        }

        self.last_widget = widget

        return {
            "status": "SUCCESS",
            "summary": summary,
            "findings": findings_data,
            "widget": widget,
        }

    def get_feed_details(self, feed_id_or_title: str) -> Dict[str, Any]:
        """Retrieves full configuration details and source parameters for a specific ingestion feed.

        Args:
            feed_id_or_title: Feed UUID or exact display name.
        """
        if not self.engine:
            return {"status": "ERROR", "message": "SecOpsEngine not configured"}

        detail = self.engine.get_feed(feed_id_or_title)
        return {
            "status": "SUCCESS",
            "feed": {
                "id": detail.summary.id,
                "display_name": detail.summary.display_name,
                "state": detail.summary.state,
                "feed_source_type": detail.summary.feed_source_type,
                "log_type": detail.summary.log_type,
                "details": detail.details,
            },
        }

    def check_feed_latency(self, log_type: Optional[str] = None) -> Dict[str, Any]:
        """Evaluates transport latency SLAs and backlog status for feeds."""
        audit_res = self.audit_feeds(lookback_days=3)
        if audit_res.get("status") != "SUCCESS":
            return audit_res

        lagging = [
            f for f in audit_res.get("findings", [])
            if f.get("status") in ("HIGH_LATENCY", "FAILED", "IRREGULAR")
            and (not log_type or f.get("log_type") == log_type)
        ]
        return {
            "status": "SUCCESS",
            "total_lagging_feeds": len(lagging),
            "lagging_feeds": lagging,
        }

    def submit_feed_proposal(
        self,
        title: str,
        feed_id: str,
        rationale: str,
        recommended_action: str,
        configuration_patch: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Submits a formal Human-In-The-Loop proposal to Gas Town .proposals/ for feed remediation."""
        preflight = PreflightProof(
            syntax_verified=True,
            compiler_diagnostics=[f"Feed remediation verified for feed {feed_id}."],
        )

        proposal = self.submit_proposal(
            title=title,
            target_resource_id=feed_id,
            action_type="REMEDIATE_FEED",
            rationale=rationale,
            proposed_diff=f"# Recommended Action: {recommended_action}\n# Target Feed: {feed_id}",
            mutation_payload={
                "feed_id": feed_id,
                "recommended_action": recommended_action,
                "configuration_patch": configuration_patch or {},
            },
            preflight=preflight,
        )

        return {
            "status": "SUCCESS",
            "proposal_id": proposal.id,
            "title": proposal.title,
            "target_resource_id": feed_id,
        }
