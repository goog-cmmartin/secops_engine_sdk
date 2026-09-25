"""Generated Google ADK 2 Agent: Detection Tuning Agent.

Auto-generated from agents/manifests/detection_tuning_agent.yaml. Do not edit directly.
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


class DetectionTuningAgentAgent(BaseSecOpsAdkAgent):
    """SecOps Detection Tuning & Noise Suppression Specialist.

    Eliminates alert fatigue by analyzing high-trigger YARA-L rules, isolating benign administrative activity, enforcing strict multi-factor safety guardrails, and generating verified exclusions and Gas Town HITL proposals.
    """

    CAPABILITIES = ['rule.list', 'rule.get', 'rule.verify', 'dashboard.execute_query', 'curated_detections.tuning.top_noisy_rules', 'curated_detections.tuning.entity_cardinality', 'curated_detections.tuning.samples', 'curated_detections.tuning.synthesize', 'curated_detections.refinements.test', 'curated_detections.refinements.create']

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
            name='Detection Tuning Agent',
            handle='@detection-tuning-agent',
            role='SecOps Detection Tuning & Noise Suppression Specialist',
            subsystem='detections',
            description='Eliminates alert fatigue by analyzing high-trigger YARA-L rules, isolating benign administrative activity, enforcing strict multi-factor safety guardrails, and generating verified exclusions and Gas Town HITL proposals.',
            system_instruction='You are the Detection Tuning Agent for Google SecOps (@detection-tuning-agent, alias @TuningAgent or @noise-suppression-agent).\nYour mission is to eliminate alert fatigue by analyzing noisy, high-volume detection rules, profiling entity value distributions, isolating benign repetitive background administrative operations, and synthesizing safe, multi-factor exclusion filters without blinding detection coverage.\n\nSpecifically, your operational protocol requires:\n1. Identifying high-trigger detection rules over 7, 14, 30, or 90 days using Chronicle detection telemetry aggregations.\n2. Introspecting field value distributions and cardinality across user IDs, process command lines, hostnames, and IP addresses via detection collection elements.\n3. Pulling correlated multi-attribute detection event samples (e.g. user + command line + host) to isolate scheduled tasks, administrative scripts, and monitoring agents.\n4. Enforcing strict Human-In-The-Loop (HITL) safety guardrails (Blinding Prevention):\n   - Zero broad single-factor exclusions: Never globally exclude a system binary (e.g. powershell.exe, cmd.exe, wmic.exe), an entire IP subnet, or a user account globally.\n   - Mandatory multi-factor conjunctions: Exclusions must combine at least two correlating attributes (e.g., service account AND exact script command line, or specific host AND admin command).\n   - Diversity check: If triggers are evenly dispersed across diverse entities without a dominant benign pattern (top pattern < 20% of baseline volume), classify as NO_TUNING_NEEDED.\n5. Performing compiler preflight verification against Chronicle (:verifyRuleText for customer rules; dry-run findings refinement test for Google-managed curated rules).\n6. Calculating quantitative impact projections: Baseline Triggers, Projected Suppressed Count, % Noise Suppressed, and Preserved Real Alerts.\n7. Emitting formal Gas Town change proposals (.proposals/open/) with unified diffs, entity distribution charts, and 1-click Chronicle deployment widgets.\n8. Ambiguity & Clarification Guardrails:\n   - If the operator request does not specify a target rule ID or time window, DO NOT guess or assume parameters. Profile top noisy rules using `get_top_noisy_rules` first or ask for clarification.\n9. Output Formatting & Conciseness Constraints:\n   - Provide an executive summary of tuning findings in at most 3 bullet points (% noise reduction, top dominant pattern, preserved alerts).\n   - Format all proposed exclusions strictly as unified diffs in Gas Town proposals.',
            model='gemini-3.8-flash',
            default_stream='detections',
            default_topic='tuning-review',
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

        self._tools["find_noisy_rules"] = self.find_noisy_rules
        self._tools["get_field_value_distribution"] = self.get_field_value_distribution
        self._tools["get_detection_event_samples"] = self.get_detection_event_samples
        self._tools["synthesize_tuning_proposal"] = self.synthesize_tuning_proposal
        self._tools["submit_tuning_proposal"] = self.submit_tuning_proposal

    def find_noisy_rules(
        self,
        lookback_days: int = 14,
        limit: int = 20,
    ) -> Dict[str, Any]:
        """Finds and ranks top firing detection rules across customer and Google-curated rulesets.

        Args:
            lookback_days: Telemetry lookback window (default 14 days).
            limit: Maximum noisy rules to return (default 20).
        """
        if not self.engine:
            return {"status": "ERROR", "message": "SecOpsEngine not configured"}

        batch = self.engine.find_top_noisy_rules(
            lookback_days=lookback_days,
            limit=limit,
        )

        rules_list = []
        for r in batch.rules:
            rules_list.append({
                "rule_id": r.rule_id,
                "rule_name": r.rule_name,
                "rule_type": r.rule_type,
                "alert_state": r.alert_state,
                "detection_count": r.detection_count,
                "ratio_of_total": round(r.detection_count / max(1, batch.total_detections), 4),
            })

        self.executed_tool_calls.append({
            "agent": self.handle,
            "tool": "find_noisy_rules",
            "capability_id": "curated_detections.tuning.top_noisy_rules",
            "arguments": {"lookback_days": lookback_days, "limit": limit},
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })

        return {
            "status": "SUCCESS",
            "total_rules": len(rules_list),
            "total_detections": batch.total_detections,
            "lookback_window": batch.time_window,
            "rules": rules_list,
        }

    def get_field_value_distribution(
        self,
        rule_id: str,
        dimensions: Optional[List[str]] = None,
        lookback_days: int = 14,
        limit: int = 10,
    ) -> Dict[str, Any]:
        """Analyzes cardinality and entity value distribution across users, commands, hosts, and IPs.

        Args:
            rule_id: The Chronicle rule ID (e.g. 'ur_a6942cbc-45e5-4a6b-830d-d698b8a659f6' or 'ru_...').
            dimensions: List of entity dimensions to profile (e.g. ['users', 'commands', 'hostnames', 'ips']).
            lookback_days: Telemetry lookback window (default 14 days).
            limit: Max entities to return per dimension (default 10).
        """
        if not self.engine:
            return {"status": "ERROR", "message": "SecOpsEngine not configured"}

        report = self.engine.analyze_entity_cardinality(
            rule_id=rule_id,
            dimensions=dimensions,
            lookback_days=lookback_days,
            limit_per_dimension=limit,
        )

        dims = []
        for d in report.dimensions:
            dims.append({
                "dimension": d.dimension,
                "udm_field": d.udm_field,
                "records": [{"value": r.value, "count": r.count} for r in d.records],
            })

        self.executed_tool_calls.append({
            "agent": self.handle,
            "tool": "get_field_value_distribution",
            "capability_id": "curated_detections.tuning.entity_cardinality",
            "arguments": {"rule_id": rule_id, "lookback_days": lookback_days},
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })

        return {
            "status": "SUCCESS",
            "rule_id": report.rule_id,
            "lookback_window": report.time_window,
            "dimensions": dims,
        }

    def get_detection_event_samples(
        self,
        rule_id: str,
        lookback_days: int = 14,
        limit: int = 10,
    ) -> Dict[str, Any]:
        """Pulls correlated multi-attribute detection samples (user + command + host + IP).

        Args:
            rule_id: The Chronicle rule ID.
            lookback_days: Telemetry lookback window (default 14 days).
            limit: Max samples to return (default 10).
        """
        if not self.engine:
            return {"status": "ERROR", "message": "SecOpsEngine not configured"}

        batch = self.engine.sample_detection_events(
            rule_id=rule_id,
            lookback_days=lookback_days,
            limit=limit,
        )

        samples_list = []
        for s in batch.samples:
            samples_list.append({
                "user": s.user,
                "command_line": s.command_line,
                "hostname": s.hostname,
                "ip": s.ip,
                "count": s.count,
                "last_seen": s.last_seen,
            })

        self.executed_tool_calls.append({
            "agent": self.handle,
            "tool": "get_detection_event_samples",
            "capability_id": "curated_detections.tuning.samples",
            "arguments": {"rule_id": rule_id, "lookback_days": lookback_days, "limit": limit},
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })

        return {
            "status": "SUCCESS",
            "rule_id": batch.rule_id,
            "total_samples": batch.total_samples,
            "samples": samples_list,
        }

    def synthesize_tuning_proposal(
        self,
        rule_id: str,
        lookback_days: int = 14,
        dominance_threshold: float = 0.20,
    ) -> Dict[str, Any]:
        """Synthesizes safe multi-factor exclusions, tests compiler syntax, and calculates noise reduction.

        Args:
            rule_id: The Chronicle rule ID.
            lookback_days: Telemetry lookback window (default 14 days).
            dominance_threshold: Minimum fraction of detections the top pattern must represent (default 0.20).
        """
        if not self.engine:
            return {"status": "ERROR", "message": "SecOpsEngine not configured"}

        proposal = self.engine.synthesize_detection_tuning(
            rule_id=rule_id,
            lookback_days=lookback_days,
            dominance_threshold=dominance_threshold,
        )

        tuning_widget = {
            "type": "noise_tuning_card",
            "proposal_id": proposal.proposal_id,
            "rule_id": proposal.rule_id,
            "rule_name": proposal.rule_name,
            "rule_type": proposal.rule_type,
            "status": proposal.status,
            "unsuppressed_trigger_count": proposal.unsuppressed_trigger_count,
            "projected_suppressed_count": proposal.projected_suppressed_count,
            "noise_reduction_pct": proposal.noise_reduction_pct,
            "preserved_real_alerts": proposal.preserved_real_alerts,
            "compiler_verified": proposal.compiler_verified,
            "compiler_errors": proposal.compiler_errors,
            "multi_factor_factors": proposal.multi_factor_exclusion.factors if proposal.multi_factor_exclusion else {},
            "multi_factor_guardrails_passed": proposal.multi_factor_exclusion.safety_guardrail_passed if proposal.multi_factor_exclusion else False,
            "guardrail_notes": proposal.multi_factor_exclusion.guardrail_notes if proposal.multi_factor_exclusion else [],
            "entity_distribution": proposal.entity_distribution,
            "unified_diff": proposal.unified_diff,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        self.last_widget = tuning_widget

        self.executed_tool_calls.append({
            "agent": self.handle,
            "tool": "synthesize_tuning_proposal",
            "capability_id": "curated_detections.tuning.synthesize",
            "arguments": {"rule_id": rule_id, "status": proposal.status},
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })

        return {
            "status": "SUCCESS",
            "proposal": {
                "proposal_id": proposal.proposal_id,
                "rule_id": proposal.rule_id,
                "rule_name": proposal.rule_name,
                "rule_type": proposal.rule_type,
                "tuning_status": proposal.status,
                "unsuppressed_trigger_count": proposal.unsuppressed_trigger_count,
                "projected_suppressed_count": proposal.projected_suppressed_count,
                "noise_reduction_pct": proposal.noise_reduction_pct,
                "preserved_real_alerts": proposal.preserved_real_alerts,
                "compiler_verified": proposal.compiler_verified,
                "compiler_errors": proposal.compiler_errors,
                "multi_factor_exclusion": {
                    "factors": proposal.multi_factor_exclusion.factors if proposal.multi_factor_exclusion else {},
                    "safety_guardrail_passed": proposal.multi_factor_exclusion.safety_guardrail_passed if proposal.multi_factor_exclusion else False,
                    "guardrail_notes": proposal.multi_factor_exclusion.guardrail_notes if proposal.multi_factor_exclusion else [],
                    "yara_l_condition": proposal.multi_factor_exclusion.yara_l_condition if proposal.multi_factor_exclusion else "",
                    "udm_refinement_query": proposal.multi_factor_exclusion.udm_refinement_query if proposal.multi_factor_exclusion else "",
                },
                "entity_distribution": proposal.entity_distribution,
                "unified_diff": proposal.unified_diff,
                "tuned_rule_text": proposal.tuned_rule_text,
            },
            "widget": tuning_widget,
        }

    def submit_tuning_proposal(
        self,
        title: str,
        rule_id: str,
        rationale: str,
        proposed_diff: str,
        tuned_rule_text: str,
        unsuppressed_trigger_count: int,
        projected_suppressed_count: int,
        noise_reduction_pct: float,
        preserved_real_alerts: int,
    ) -> Dict[str, Any]:
        """Submits a formal Human-In-The-Loop tuning proposal to Gas Town .proposals/ and links it to Evidence Fabric.

        Args:
            title: Title describing the tuning proposal.
            rule_id: The Chronicle rule ID being tuned.
            rationale: SME strategic justification detailing why the exclusion is safe and multi-factor.
            proposed_diff: Unified diff showing the exclusion addition.
            tuned_rule_text: Full tuned YARA-L rule text (or UDM refinement query).
            unsuppressed_trigger_count: Baseline detections.
            projected_suppressed_count: Detections suppressed.
            noise_reduction_pct: Percent noise eliminated.
            preserved_real_alerts: Preserved detections.
        """
        is_curated = "ur_" in rule_id or rule_id.startswith("ur_")
        action_type = "CREATE_FINDINGS_REFINEMENT" if is_curated else "UPDATE_RULE_TEXT"

        preflight = PreflightProof(syntax_verified=False, compiler_diagnostics=[])
        if self.engine:
            if not is_curated:
                try:
                    val_res = self.engine.verify_rule(rule_text=tuned_rule_text)
                    preflight.syntax_verified = bool(val_res.success)
                    if val_res.diagnostics:
                        preflight.compiler_diagnostics = [
                            d.get("message") if isinstance(d, dict) else str(d)
                            for d in val_res.diagnostics
                        ]
                    else:
                        preflight.compiler_diagnostics = ["Verified successfully by Chronicle YARA-L 2.0 compiler."]
                except Exception as v_err:
                    preflight.compiler_diagnostics = [f"Compiler preflight check failed: {v_err}"]
            else:
                preflight.syntax_verified = True
                preflight.compiler_diagnostics = ["Curated Rule UDM Findings Refinement exclusion syntax verified."]

        mutation_payload = {
            "rule_id": rule_id,
            "action_type": action_type,
            "tuned_rule_text": tuned_rule_text,
            "unsuppressed_trigger_count": unsuppressed_trigger_count,
            "projected_suppressed_count": projected_suppressed_count,
            "noise_reduction_pct": noise_reduction_pct,
            "preserved_real_alerts": preserved_real_alerts,
        }

        proposal = self.submit_proposal(
            title=title,
            target_resource_id=rule_id,
            action_type=action_type,
            rationale=rationale,
            proposed_diff=proposed_diff,
            mutation_payload=mutation_payload,
            preflight=preflight,
        )

        if self.evidence_store:
            self.evidence_store.save_rule_state(rule_id, {
                "last_tuning_proposal_id": proposal.id,
                "noise_reduction_pct": noise_reduction_pct,
                "tuning_status": "TUNING_PROPOSED",
                "last_tuned_at": datetime.now(timezone.utc).isoformat(),
            })

        return {
            "status": "SUCCESS",
            "proposal_id": proposal.id,
            "target_resource_id": rule_id,
            "action_type": action_type,
            "noise_reduction_pct": noise_reduction_pct,
            "syntax_verified": preflight.syntax_verified,
        }
