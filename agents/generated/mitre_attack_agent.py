"""Generated Google ADK 2 Agent: MITRE ATT&CK Strategic Mapping Agent.

Auto-generated from agents/manifests/mitre_attack_agent.yaml. Do not edit directly.
"""

from typing import Any, Optional
from datetime import datetime, timezone
from typing import Dict, List, Optional, Any
from agents.core.base_adk_agent import BaseSecOpsAdkAgent
from engine.facade import SecOpsEngine
from agents.core.proposal_manager import ProposalManager
from agents.core.evidence_store import EvidenceFabricStore


class MitreAttackAgentAgent(BaseSecOpsAdkAgent):
    """MITRE ATT&CK Framework Cartographer & Gap Analyst.

    Maps tenant detection rules and live ingestion telemetry against the MITRE ATT&CK Enterprise Matrix (v18.1) across industry threat profiles (financial services, cloud native, ransomware defense). Computes contextual coverage scores, identifies single points of failure (fragile detections), isolates visibility gaps versus detection gaps, and surfaces blind tactics.
    """

    CAPABILITIES = ['mitre.sync_cache', 'mitre.analyze_coverage', 'mitre.get_technique_rules', 'mitre.list_threat_profiles', 'mitre.generate_report', 'rule.list', 'rule.get']

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
            name='MITRE ATT&CK Strategic Mapping Agent',
            handle='@mitre-attack-agent',
            role='MITRE ATT&CK Framework Cartographer & Gap Analyst',
            subsystem='threat_intelligence',
            description='Maps tenant detection rules and live ingestion telemetry against the MITRE ATT&CK Enterprise Matrix (v18.1) across industry threat profiles (financial services, cloud native, ransomware defense). Computes contextual coverage scores, identifies single points of failure (fragile detections), isolates visibility gaps versus detection gaps, and surfaces blind tactics.',
            system_instruction='You are the MITRE ATT&CK Strategic Mapping Agent for Google SecOps (@mitre-attack-agent, alias @MitreAttackAgent).\nYour mission is to map tenant detection rules and live ingestion telemetry against the MITRE ATT&CK Enterprise Matrix (v18.1) and evaluate security posture against industry-specific threat profiles.\n\nSpecifically, your operational protocol requires:\n1. MITRE ATT&CK Enterprise Matrix Alignment:\n   - Utilize the condensed Enterprise ATT&CK Matrix (691 unrevoked techniques across 14 tactics).\n   - Cross-reference custom YARA-L rules and Google Curated Rule sets by parsing T-codes (Txxxx or Txxxx.xxx) from rule display names, metadata, tags, and rule text.\n2. Telemetry Domain & Visibility Cross-Referencing:\n   - Query live tenant ingestion telemetry across EDR (Endpoint), IDENTITY (Auth & IAM), CLOUD (GCP/AWS/Azure Audit), and NETWORK (Firewall, Proxy, DNS, Netflow).\n   - Map ingested log types to their corresponding MITRE tactical visibility domains.\n3. Strategic Gap Classification Taxonomy:\n   - VISIBILITY GAP: Tactics or techniques where detection rules exist or could exist, but required telemetry is missing from the tenant.\n   - DETECTION GAP: Tactics where telemetry is ingested and available, but zero or insufficient detection rules are authored.\n   - BLIND TACTIC: Critical failure state where the tenant has NEITHER telemetry visibility NOR detection rules.\n   - CRITICAL TECHNIQUE GAP: Profile-designated high-risk techniques (weights 3 to 5) that have zero detection coverage.\n4. Contextual Coverage Scoring & Resilience:\n   - Formula: min(100.0, (Sum(Risk-Weighted Covered Techniques) + Resilience Bonus) / Total Relevant Baseline * 100).\n   - Single Point of Failure (Fragile Detections): Techniques covered by exactly 1 rule.\n   - Resilient Detections: Techniques covered by 2 or more independent rules.\n5. Multi-Profile Posture Auditing:\n   - Support evaluation across: Global Baseline, Financial Services, Cloud Native Infrastructure, Ransomware Defense, and EU Public Finance profiles.\n6. Multi-Agent Synergy:\n   - Coordinate with @yaral-optimizer to author new detection rules for critical technique gaps.\n   - Coordinate with @detection-tuning-agent to verify that noisy rules are not falsely inflating technique coverage.\n   - Coordinate with @tenant-cartographer to identify ingestion pipelines needed to close visibility gaps.\n7. Ambiguity & Clarification Guardrails:\n   - If the operator request does not specify a threat profile, default to evaluating against the "Global Baseline" profile.\n   - Never infer or guess technique mappings not directly referenced in rule syntax or verified metadata.\n8. Output Formatting & Conciseness Constraints:\n   - Present findings with clear Contextual Coverage Scores, gap distributions, resilient vs. fragile technique counts, and actionable next steps.\n   - Provide executive summary in at most 3 bullet points before providing detailed tactic breakdowns.',
            model='gemini-3.8-flash',
            default_stream='threat_intel',
            default_topic='mitre-coverage',
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

        self._tools["audit_mitre_coverage"] = self.audit_mitre_coverage
        self._tools["sync_rules_cache"] = self.sync_rules_cache
        self._tools["get_latest_assessment"] = self.get_latest_assessment

    def audit_mitre_coverage(
        self,
        profile_id: str = "global_baseline",
        time_unit: str = "DAY",
        time_value: str = "7",
    ) -> Dict[str, Any]:
        """Evaluates tenant detection rules and live ingestion telemetry against MITRE ATT&CK.

        Args:
            profile_id: Target threat profile (e.g. 'global_baseline', 'financial_services', 'cloud_native', 'ransomware_defense').
            time_unit: Lookback time unit ('DAY', 'HOUR').
            time_value: Lookback count.
        """
        if not self.engine:
            return {"status": "ERROR", "message": "SecOpsEngine not configured"}

        assessment = self.engine.analyze_mitre_coverage(
            profile_id=profile_id,
            sync_cache_if_empty=True,
            time_unit=time_unit,
            time_value=time_value,
        )

        widget = {
            "type": "mitre_coverage_card",
            "title": f"MITRE ATT&CK Coverage: {assessment.profile_name}",
            "coverage_score": assessment.coverage_score,
            "validated_technique_count": assessment.validated_technique_count,
            "total_rules_evaluated": assessment.total_rules_evaluated,
            "enabled_rules_count": assessment.enabled_rules_count,
            "visibility_tactics_count": assessment.visibility_tactics_count,
            "detection_tactics_count": assessment.detection_tactics_count,
            "blind_tactics": assessment.blind_tactics,
            "critical_techniques_count": len(assessment.critical_techniques),
            "resilient_techniques_count": len(assessment.resilient_techniques),
            "fragile_techniques_count": len(assessment.fragile_techniques),
        }
        self.last_widget = widget

        self.executed_tool_calls.append({
            "agent": self.handle,
            "tool": "audit_mitre_coverage",
            "capability_id": "mitre.analyze_coverage",
            "arguments": {"profile_id": profile_id, "time_unit": time_unit, "time_value": time_value},
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })

        return {
            "status": "SUCCESS",
            "assessment": assessment.to_dict(),
            "widget": widget,
        }

    def sync_rules_cache(
        self,
        force: bool = False,
        include_curated: bool = True,
        max_rules: Optional[int] = None,
    ) -> Dict[str, Any]:
        """Synchronizes custom and curated detection rules into Firestore with parsed MITRE technique IDs.

        Args:
            force: Force full refresh.
            include_curated: Include Google curated detection rules.
            max_rules: Limit total rules processed.
        """
        if not self.engine:
            return {"status": "ERROR", "message": "SecOpsEngine not configured"}
        res = self.engine.sync_mitre_rules(
            force_refresh=force,
            include_curated=include_curated,
            max_rules=max_rules,
        )
        return {"status": "SUCCESS", **res}

    def get_latest_assessment(self) -> Dict[str, Any]:
        """Retrieves the latest cached MITRE ATT&CK assessment from Evidence Fabric."""
        if not self.evidence_store:
            return {"status": "ERROR", "message": "EvidenceFabricStore not configured"}
        assessment = self.evidence_store.get_latest_mitre_assessment()
        if not assessment:
            return {"status": "NOT_FOUND", "message": "No MITRE assessment found in Evidence Fabric"}
        return {"status": "SUCCESS", "assessment": assessment}
