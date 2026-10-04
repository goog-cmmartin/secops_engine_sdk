"""Generated Google ADK 2 Agent: Rule Conflict & Overlap Agent.

Auto-generated from agents/manifests/rule_conflict_agent.yaml. Do not edit directly.
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


class RuleConflictAgentAgent(BaseSecOpsAdkAgent):
    """Detection Conflict & Overlap Auditor.

    Eliminates detection sprawl, alert fatigue, and logical contradictions across the Google SecOps rule repository by semantically finding similar rules, comparing YARA-L logic blocks, computing Conflict Overlap Scores (COS: 0-100), and proposing consolidation strategies.
    """

    CAPABILITIES = ['rule.list', 'rule.get', 'rule.verify', 'rule.deployment.list', 'rule.conflict.audit', 'rule.conflict.batch_audit', 'rule.similarity.search', 'rule.embeddings.sync']

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
            name='Rule Conflict & Overlap Agent',
            handle='@rule-conflict-agent',
            role='Detection Conflict & Overlap Auditor',
            subsystem='detections',
            description='Eliminates detection sprawl, alert fatigue, and logical contradictions across the Google SecOps rule repository by semantically finding similar rules, comparing YARA-L logic blocks, computing Conflict Overlap Scores (COS: 0-100), and proposing consolidation strategies.',
            system_instruction='You are the Rule Conflict & Overlap Agent for Google SecOps (@rule-conflict-agent, alias @RuleConflictAgent).\nYour mission is to eliminate detection sprawl, alert fatigue, and logical contradictions across the Google SecOps rule repository.\n\nSpecifically, your operational protocol requires:\n1. Semantic Vector Discovery:\n   - Utilize 768-dimensional text-embedding-004 vectors synthesized from Rule Name, Description, MITRE ATT&CK Tactics/Techniques, and Severity.\n   - Query Firestore Vector Search to discover candidate rules targeting the same threat vector with anti-self-matching protections.\n2. Dual YARA-L Logic Analysis:\n   - Compare the logic structures of both rules across events:, match:, and condition: sections.\n   - Extract and compute Jaccard overlap on canonical UDM field paths.\n3. The 4 Conflict & Overlap Types:\n   - REDUNDANCY (+30 pts weight): Duplicate alerts for identical activities or matching behaviors.\n   - CONTRADICTION (+25 pts weight): Opposing criteria, mutually exclusive thresholds, or contradictory conditions.\n   - OVERLAP (+15 pts weight): Shared criteria or match conditions with minor scope/threshold differences.\n   - SCOPE GAPS (+5 pts weight): Complementary rules covering related threats leaving unmonitored bypass paths.\n4. Conflict Overlap Score (COS: 0-100):\n   - Formula: COS = (Similarity Score * 40.0) + Conflict Type Weight + Severity Weight\n   - Impact Severity: HIGH (+30 pts), MEDIUM (+15 pts), LOW (+5 pts).\n   - Classification Tiers:\n     * CRITICAL OVERLAP (COS >= 75): Immediate action required.\n     * MODERATE OVERLAP (45 <= COS < 75): Review recommended.\n     * LOW / NO OVERLAP (COS < 45): Informational.\n5. Multi-Agent Strategic Deconfliction Synergy:\n   - Check if target rule is SILENT (0 detections over 90 days via Detection Decay telemetry).\n   - If SILENT and functionally REDUNDANT with an active sibling rule, recommend Retiring / Archiving the rule instead of refactoring.\n   - Propose Gas Town consolidation proposals with unified diffs for human approval.\n6. Ambiguity & Clarification Guardrails:\n   - If the operator request does not specify target rule IDs or threat scopes, ask for clarification or run a batch audit of all active rules to identify candidate conflicts.\n7. Output Formatting & Conciseness Constraints:\n   - Present findings clearly: COS score, severity tier, conflict breakdown, and strategic remediation advice.\n   - Provide an executive summary of findings in at most 3 bullet points.',
            model='gemini-3.8-flash',
            default_stream='detections',
            default_topic='rule-conflicts',
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

        self._tools["audit_rule_conflicts"] = self.audit_rule_conflicts
        self._tools["batch_audit_rule_conflicts"] = self.batch_audit_rule_conflicts
        self._tools["find_similar_rules"] = self.find_similar_rules
        self._tools["sync_rule_embeddings"] = self.sync_rule_embeddings
        self._tools["get_stored_rule_conflict"] = self.get_stored_rule_conflict
        self._tools["list_stored_rule_conflicts"] = self.list_stored_rule_conflicts

    def audit_rule_conflicts(
        self,
        rule_id: str,
        limit: int = 6,
    ) -> Dict[str, Any]:
        """Audits detection rule for semantic overlaps, contradictions, redundancies, and computes COS (0-100).

        Args:
            rule_id: Target rule ID (e.g. 'ru_6cb5b1fe-45a7-47b2-bd74-323e20ec4e31') or resource name.
            limit: Maximum candidate similar rules to evaluate (default: 6).
        """
        if not self.engine:
            return {"status": "ERROR", "message": "SecOpsEngine not configured"}

        report = self.engine.audit_rule_conflicts(rule_id=rule_id, limit=limit)

        self.executed_tool_calls.append({
            "agent": self.handle,
            "tool": "audit_rule_conflicts",
            "capability_id": "rule.conflict.audit",
            "arguments": {"rule_id": rule_id, "limit": limit},
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })

        widget = {
            "type": "rule_conflict_card",
            "title": f"Rule Conflict Audit: {report.rule_name}",
            "rule_id": report.rule_id,
            "rule_name": report.rule_name,
            "highest_cos": report.highest_cos,
            "severity_tier": report.severity_tier,
            "is_live": report.is_live,
            "is_silent": report.is_silent,
            "strategic_recommendation": report.strategic_recommendation,
            "conflicts": [c.to_dict() for c in report.conflicts],
        }
        self.last_widget = widget

        return {
            "status": "SUCCESS",
            "rule_id": report.rule_id,
            "rule_name": report.rule_name,
            "highest_cos": report.highest_cos,
            "severity_tier": report.severity_tier,
            "is_live": report.is_live,
            "is_silent": report.is_silent,
            "strategic_recommendation": report.strategic_recommendation,
            "conflicts": [c.to_dict() for c in report.conflicts],
            "widget": widget,
        }

    def batch_audit_rule_conflicts(
        self,
        limit: int = 50,
        batch_size: int = 10,
        min_cos: float = 45.0,
    ) -> Dict[str, Any]:
        """Runs batch rule conflict and overlap discovery across tenant rules.

        Args:
            limit: Maximum active rules to scan (default: 50).
            batch_size: Batch size for chunked evaluation (default: 10).
            min_cos: Minimum COS score to flag in summary (default: 45.0).
        """
        if not self.engine:
            return {"status": "ERROR", "message": "SecOpsEngine not configured"}

        report = self.engine.batch_audit_rule_conflicts(limit=limit, batch_size=batch_size, min_cos=min_cos)

        self.executed_tool_calls.append({
            "agent": self.handle,
            "tool": "batch_audit_rule_conflicts",
            "capability_id": "rule.conflict.batch_audit",
            "arguments": {"limit": limit, "batch_size": batch_size, "min_cos": min_cos},
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })

        widget = {
            "type": "rule_conflict_batch_card",
            "title": "Tenant Detection Rule Conflict Audit",
            "total_rules_scanned": report.total_rules_scanned,
            "total_pairs_evaluated": report.total_pairs_evaluated,
            "conflict_counts": report.conflict_counts,
            "severity_counts": report.severity_counts,
            "highest_cos_rules": [r.to_dict() for r in report.highest_cos_rules],
        }
        self.last_widget = widget

        return {
            "status": "SUCCESS",
            "total_rules_scanned": report.total_rules_scanned,
            "total_pairs_evaluated": report.total_pairs_evaluated,
            "conflict_counts": report.conflict_counts,
            "severity_counts": report.severity_counts,
            "highest_cos_rules": [r.to_dict() for r in report.highest_cos_rules],
            "widget": widget,
        }

    def find_similar_rules(self, rule_id: str, limit: int = 6) -> Dict[str, Any]:
        """Finds candidate overlapping or conflicting rules via vector similarity search.

        Args:
            rule_id: Target rule ID or resource name.
            limit: Maximum candidate rules to return (default: 6).
        """
        if not self.engine:
            return {"status": "ERROR", "message": "SecOpsEngine not configured"}
        results = self.engine.find_similar_rules(rule_id=rule_id, limit=limit)
        return {"status": "SUCCESS", "count": len(results), "rules": results}

    def sync_rule_embeddings(self, batch_size: int = 50, force: bool = False) -> Dict[str, Any]:
        """Batch computes and synchronizes vector embeddings for all active tenant rules.

        Args:
            batch_size: Batch chunk size (default: 50).
            force: Whether to force refresh existing embeddings.
        """
        if not self.engine:
            return {"status": "ERROR", "message": "SecOpsEngine not configured"}
        res = self.engine.sync_rule_embeddings(batch_size=batch_size, force_refresh=force)
        return {"status": "SUCCESS", **res}

    def get_stored_rule_conflict(self, rule_id: str) -> Dict[str, Any]:
        """Retrieves a previously stored conflict audit record from Evidence Fabric."""
        if not self.evidence_store:
            return {"status": "ERROR", "message": "EvidenceFabricStore not configured"}
        doc = self.evidence_store.get_rule_conflict(rule_id)
        if not doc:
            return {"status": "NOT_FOUND", "message": f"No conflict audit record found for rule {rule_id}"}
        return {"status": "SUCCESS", "report": doc}

    def list_stored_rule_conflicts(self, min_cos: float = 0.0, limit: int = 50) -> Dict[str, Any]:
        """Lists historical rule conflict audit records from Evidence Fabric."""
        if not self.evidence_store:
            return {"status": "ERROR", "message": "EvidenceFabricStore not configured"}
        records = self.evidence_store.list_rule_conflicts(min_cos=min_cos, limit=limit)
        return {"status": "SUCCESS", "count": len(records), "records": records}
