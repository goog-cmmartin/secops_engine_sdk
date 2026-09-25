"""Generated Google ADK 2 Agent: Tenant Posture & Configuration Governor.

Auto-generated from agents/manifests/tenant_posture.yaml. Do not edit directly.
"""

from typing import Any, Optional
from datetime import datetime, timezone
import json
import logging
from typing import Any, Dict, List, Optional
from agents.core.evidence_store import compute_tenant_subsystem_hashes, diff_tenant_baselines
from agents.core.base_adk_agent import BaseSecOpsAdkAgent
from engine.facade import SecOpsEngine
from agents.core.proposal_manager import ProposalManager
from agents.core.evidence_store import EvidenceFabricStore


class TenantPostureAgent(BaseSecOpsAdkAgent):
    """Google SecOps Tenant Posture, Baseline & Configuration Governance Specialist.

    Audits tenant configuration posture across SIEM, SOAR, RBAC, and SOC topography, establishes persistent cryptographic baselines in Evidence Fabric, and detects configuration drift.
    """

    CAPABILITIES = ['tenant.posture.audit', 'siem.tenant.get', 'siem.agent_settings.get', 'siem.risk_config.get', 'soar.company.get', 'soar.data_retention.get', 'soar.email_settings.get', 'soar.support_settings.get', 'case_config.alert_grouping.settings.get', 'case_config.title_settings.get']

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
            name='Tenant Posture & Configuration Governor',
            handle='@tenant-posture-agent',
            role='Google SecOps Tenant Posture, Baseline & Configuration Governance Specialist',
            subsystem='configuration_governance',
            description='Audits tenant configuration posture across SIEM, SOAR, RBAC, and SOC topography, establishes persistent cryptographic baselines in Evidence Fabric, and detects configuration drift.',
            system_instruction='You are the Tenant Posture & Configuration Governor Agent for Google SecOps (@tenant-posture-agent).\nYour mission is to continuously audit, baseline, and govern configuration posture across Chronicle SIEM, SOAR, and cloud tenant infrastructure.\nSpecifically, you:\n1. Audit complete tenant posture (`tenant.posture.audit`, `snapshot_tenant_baseline`):\n   - Root tenant instance details, status, and feature flags (`secops_ui_enabled`, `data_rbac_enabled`, `triage_agent_enabled`).\n   - Gemini autonomous investigation and AI triage settings (`auto_investigation`, `alert_filter`, investigation delay).\n   - UEBA entity risk scoring defaults (detection risk score, alert risk score, weighting factors).\n   - Data processing pipelines, managed domains, and data RBAC access scopes.\n   - SOAR global settings (data retention period, company profile, support access delegation, alert grouping windows, case title formats).\n   - SOC topography (SOC roles, environments, remote agents, networks, domains, and custom entity lists).\n2. Maintain persistent baselines in the Evidence Fabric (`tenant_baselines`):\n   - Generate cryptographic SHA-256 fingerprints across each subsystem.\n   - Archive approved golden standard baselines and record operator tags.\n3. Detect and triage configuration drift (`detect_configuration_drift`):\n   - Compare current tenant configuration against historical baselines.\n   - Categorize drift severity (`CRITICAL`, `HIGH`, `MEDIUM`, `LOW`).\n   - Flag high-risk changes immediately (e.g. data retention reduced, Google support delegation enabled, RBAC scopes deleted, or Gemini autonomous triage disabled).\n   - Automatically register remediation action items (`add_todo`) in the Evidence Fabric for unauthorized drift.\n4. Ambiguity & Clarification Guardrails:\n   - If the operator request does not specify whether to compare against the latest baseline or a specific baseline ID, default to comparing against the latest recorded baseline in the Evidence Fabric.\n5. Output Formatting & Conciseness Constraints:\n   - Deliver actionable responses: provide an executive summary in at most 3 bullet points (posture status, drift count with severity breakdown, and high-risk alerts).\n   - Present parameter deltas in a clear tabular format detailing subsystem, parameter name, prior value, and new value.',
            model='gemini-3.8-flash',
            default_stream='governance',
            default_topic='tenant-posture',
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

        self._tools["audit_tenant_posture"] = self.audit_tenant_posture
        self._tools["snapshot_tenant_baseline"] = self.snapshot_tenant_baseline
        self._tools["detect_configuration_drift"] = self.detect_configuration_drift
        self._tools["query_settings_slice"] = self.query_settings_slice
        self._tools["list_historical_baselines"] = self.list_historical_baselines

    def audit_tenant_posture(
        self,
        snapshot: bool = True,
        tag: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Audits complete tenant configuration posture across SIEM, SOAR, RBAC, and SOC topography.

        Args:
            snapshot: If True, persists snapshot into the Evidence Fabric as a baseline.
            tag: Optional human-readable tag or change ticket ID (e.g. 'CHG-10492', 'Gold-Standard').
        """
        if not self.engine:
            return {"status": "ERROR", "message": "SecOpsEngine not configured"}

        # 1. Fetch live tenant settings report via composed workflow
        report = self.engine.audit_tenant_posture()
        tenant_id = report.get("tenant_id", "default")
        timestamp = report.get("timestamp") or datetime.now(timezone.utc).isoformat()

        # 2. Compute deterministic subsystem and overall hashes
        hashes = compute_tenant_subsystem_hashes(report)
        report["fingerprint"] = hashes.get("overall_fingerprint")
        report["subsystem_hashes"] = hashes
        if tag:
            report["tag"] = tag

        # 3. Retrieve prior baseline to compute drift
        prior_baseline = None
        if self.evidence_store:
            prior_baseline = self.evidence_store.get_latest_tenant_baseline(tenant_id=tenant_id)

        drift = diff_tenant_baselines(prior_baseline, report)

        snapshot_id = None
        if snapshot and self.evidence_store:
            report["snapshot_id"] = f"baseline_{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S_%f')}"
            snapshot_id = self.evidence_store.save_tenant_baseline(report)
            report["snapshot_id"] = snapshot_id

        # 4. If critical drift is detected, record a remediation todo
        if drift.get("critical_changes_count", 0) > 0 and self.evidence_store:
            try:
                self.evidence_store.add_todo(
                    assigned_to="@tenant-posture-agent",
                    title=f"Remediate Critical Tenant Drift: {drift.get('summary', '')[:80]}",
                    description=f"Automated posture audit detected {drift.get('critical_changes_count')} CRITICAL change(s). Baseline: {snapshot_id or 'current'}.",
                    stream="governance",
                    topic="tenant-posture",
                    severity="CRITICAL",
                )
            except Exception as e:
                logging.getLogger("TenantPostureAgent").warning(f"Could not add remediation todo: {e}")

        widget = {
            "type": "tenant_drift_card",
            "snapshot_id": snapshot_id or "live_audit",
            "tenant_id": tenant_id,
            "has_drift": drift.get("has_drift", False),
            "drift_status": drift.get("status"),
            "drift_summary": drift.get("summary"),
            "drift_count": drift.get("drift_count", 0),
            "critical_changes_count": drift.get("critical_changes_count", 0),
            "high_changes_count": drift.get("high_changes_count", 0),
            "medium_changes_count": drift.get("medium_changes_count", 0),
            "low_changes_count": drift.get("low_changes_count", 0),
            "subsystems_drifted": drift.get("subsystems_drifted", []),
            "changes": drift.get("changes", []),
            "current_fingerprint": report.get("fingerprint"),
            "prior_snapshot_id": drift.get("prior_snapshot_id"),
            "prior_timestamp": drift.get("prior_timestamp"),
            "timestamp": timestamp,
            "tag": tag,
        }
        self.last_widget = widget

        self.executed_tool_calls.append({
            "agent": self.handle,
            "tool": "audit_tenant_posture",
            "capability_id": "tenant.posture.audit",
            "arguments": {"snapshot": snapshot, "tag": tag},
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })

        return {
            "status": "SUCCESS",
            "tenant_id": tenant_id,
            "snapshot_id": snapshot_id,
            "fingerprint": report.get("fingerprint"),
            "drift": drift,
            "widget": widget,
        }

    def snapshot_tenant_baseline(
        self,
        tag: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Snapshots current tenant settings and archives as a baseline in Evidence Fabric.

        Args:
            tag: Optional human-readable tag or change ticket ID (e.g. 'CHG-10492', 'Gold-Standard').
        """
        return self.audit_tenant_posture(snapshot=True, tag=tag)

    def detect_configuration_drift(
        self,
        baseline_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Compares current live tenant settings against a specific or latest baseline.

        Args:
            baseline_id: Optional baseline snapshot ID to compare against. If None, compares against the latest.
        """
        if not self.engine:
            return {"status": "ERROR", "message": "SecOpsEngine not configured"}

        report = self.engine.audit_tenant_posture()
        tenant_id = report.get("tenant_id", "default")
        hashes = compute_tenant_subsystem_hashes(report)
        report["fingerprint"] = hashes.get("overall_fingerprint")
        report["subsystem_hashes"] = hashes

        prior = None
        if self.evidence_store:
            if baseline_id:
                for b in self.evidence_store.list_tenant_baselines(limit=50):
                    if b.get("snapshot_id") == baseline_id or b.get("baseline_id") == baseline_id:
                        prior = b
                        break
            if not prior:
                prior = self.evidence_store.get_latest_tenant_baseline(tenant_id=tenant_id)

        drift = diff_tenant_baselines(prior, report)

        widget = {
            "type": "tenant_drift_card",
            "snapshot_id": "live_drift_check",
            "tenant_id": tenant_id,
            "has_drift": drift.get("has_drift", False),
            "drift_status": drift.get("status"),
            "drift_summary": drift.get("summary"),
            "drift_count": drift.get("drift_count", 0),
            "critical_changes_count": drift.get("critical_changes_count", 0),
            "high_changes_count": drift.get("high_changes_count", 0),
            "medium_changes_count": drift.get("medium_changes_count", 0),
            "low_changes_count": drift.get("low_changes_count", 0),
            "subsystems_drifted": drift.get("subsystems_drifted", []),
            "changes": drift.get("changes", []),
            "current_fingerprint": report.get("fingerprint"),
            "prior_snapshot_id": drift.get("prior_snapshot_id"),
            "prior_timestamp": drift.get("prior_timestamp"),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        self.last_widget = widget

        self.executed_tool_calls.append({
            "agent": self.handle,
            "tool": "detect_configuration_drift",
            "capability_id": "tenant.posture.audit",
            "arguments": {"baseline_id": baseline_id},
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })

        return {
            "status": "SUCCESS",
            "tenant_id": tenant_id,
            "drift": drift,
            "widget": widget,
        }

    def query_settings_slice(
        self,
        section: str,
    ) -> Dict[str, Any]:
        """Queries a specific subsystem slice of tenant configuration.

        Args:
            section: Subsystem section name: 'instance', 'gemini_ai', 'ueba_risk', 'governance', 'soar_settings', or 'topography'.
        """
        if not self.engine:
            return {"status": "ERROR", "message": "SecOpsEngine not configured"}

        report = self.engine.audit_tenant_posture()
        normalized_sec = section.strip().lower()
        
        valid_sections = ["instance", "gemini_ai", "ueba_risk", "governance", "soar_settings", "topography"]
        if normalized_sec not in valid_sections:
            return {
                "status": "ERROR",
                "message": f"Invalid section '{section}'. Must be one of: {', '.join(valid_sections)}",
            }

        slice_data = report.get(normalized_sec, {})

        self.executed_tool_calls.append({
            "agent": self.handle,
            "tool": "query_settings_slice",
            "capability_id": f"siem.{normalized_sec}.get" if normalized_sec in ("instance", "gemini_ai", "ueba_risk") else f"soar.{normalized_sec}.get",
            "arguments": {"section": section},
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })

        return {
            "status": "SUCCESS",
            "section": normalized_sec,
            "data": slice_data,
        }

    def list_historical_baselines(
        self,
        limit: int = 10,
    ) -> List[Dict[str, Any]]:
        """Lists historical tenant baseline snapshots stored in Evidence Fabric.

        Args:
            limit: Maximum baselines to return (default 10).
        """
        if not self.evidence_store:
            return []

        baselines = self.evidence_store.list_tenant_baselines(limit=limit)
        results = []
        for b in baselines:
            results.append({
                "snapshot_id": b.get("snapshot_id") or b.get("baseline_id"),
                "tenant_id": b.get("tenant_id"),
                "timestamp": b.get("timestamp") or str(b.get("created_at")),
                "fingerprint": b.get("fingerprint"),
                "tag": b.get("tag"),
            })

        self.executed_tool_calls.append({
            "agent": self.handle,
            "tool": "list_historical_baselines",
            "capability_id": "tenant.posture.audit",
            "arguments": {"limit": limit},
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })

        return results
