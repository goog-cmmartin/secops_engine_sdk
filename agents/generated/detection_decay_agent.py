"""Generated Google ADK 2 Agent: Detection Decay Agent.

Auto-generated from agents/manifests/detection_decay_agent.yaml. Do not edit directly.
"""

from typing import Any, Optional
import difflib
from datetime import datetime, timezone
import json
import logging
from typing import Any, Dict, List, Optional
from agents.core.proposal_manager import PreflightProof
from engine.workflows.rule_decay import (
    calculate_decay_score,
    extract_udm_fields_from_yaral,
)
from agents.core.base_adk_agent import BaseSecOpsAdkAgent
from engine.facade import SecOpsEngine
from agents.core.proposal_manager import ProposalManager
from agents.core.evidence_store import EvidenceFabricStore


class DetectionDecayAgentAgent(BaseSecOpsAdkAgent):
    """SecOps Detection Lifecycle & Decay Auditor.

    Continuously audits, diagnoses, and remediates underperforming, silent, stale, or broken YARA-L detection rules across Google SecOps using Decay Prioritization Scoring (DPS), 90-day telemetry aggregations, live UDM population checks, and Gas Town HITL change proposals.
    """

    CAPABILITIES = ['rule.list', 'rule.get', 'rule.verify', 'rule.errors', 'dashboard.execute_query', 'rule.decay.audit', 'rule.decay.telemetry']

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
            name='Detection Decay Agent',
            handle='@detection-decay-agent',
            role='SecOps Detection Lifecycle & Decay Auditor',
            subsystem='detections',
            description='Continuously audits, diagnoses, and remediates underperforming, silent, stale, or broken YARA-L detection rules across Google SecOps using Decay Prioritization Scoring (DPS), 90-day telemetry aggregations, live UDM population checks, and Gas Town HITL change proposals.',
            system_instruction='You are the Detection Decay Agent for Google SecOps (@detection-decay-agent, alias @DecayAgent).\nYour mission is to continuously audit, diagnose, prioritize, and remediate decaying, silent, stale, or broken YARA-L detection rules.\n\nSpecifically, your operational protocol requires:\n1. Synchronizing rule inventory and aggregating 90-day detection telemetry using the native Chronicle detection namespace (detection.detection.rule_id).\n2. Calculating the Decay Prioritization Score (DPS: 0-100) combining:\n   - Base weights: Broken Compilation (+40), Silent/0 detections (+30), Unpopulated UDM fields (+20), Healthy (+5).\n   - Operational weight: Live/Enabled rule (+30).\n   - Staleness bonus: >365 days unrevised (+30), >180 days (+15), >90 days (+5).\n3. Diagnosing live telemetry for silent or underperforming rules by auditing UDM field population over the last 30 days, scoped to relevant vendor/products, handling repeated/array fields (= /.+/), and utilizing the self-healing udm_schema cache.\n4. Performing compilation preflight verification against the live Chronicle YARA-L 2.0 compiler (:verifyRuleText).\n5. Generating comprehensive SME strategic recommendations covering Threat Relevance, Telemetry Health, Fragility Analysis, and Action Plan (Keep, Refactor, or Archive).\n6. Submitting formal Human-In-The-Loop (HITL) change proposals to Gas Town .proposals/open/ complete with unified diffs and interactive review widgets.\n7. Ambiguity & Clarification Guardrails:\n   - If the operator request does not specify a target rule ID or scope, DO NOT guess or assume parameters. List candidate decaying rules from the audit first or ask for clarification.\n8. Output Formatting & Conciseness Constraints:\n   - Provide an executive summary of findings in at most 3 bullet points (DPS score, primary decay driver, recommended action).\n   - Format all suggested rule modifications strictly as unified diffs in Gas Town proposals.',
            model='gemini-3.8-flash',
            default_stream='detections',
            default_topic='decay-review',
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

        self._tools["run_decay_synchronization"] = self.run_decay_synchronization
        self._tools["audit_single_rule_decay"] = self.audit_single_rule_decay
        self._tools["check_udm_field_population"] = self.check_udm_field_population
        self._tools["submit_decay_proposal"] = self.submit_decay_proposal
        self._tools["list_decay_queue"] = self.list_decay_queue

    def run_decay_synchronization(
        self,
        lookback_days: int = 90,
    ) -> Dict[str, Any]:
        """Runs full tenant-wide detection rule synchronization and calculates Decay Prioritization Scores (DPS).

        Args:
            lookback_days: Telemetry lookback window for native Chronicle detections (default 90 days).
        """
        if not self.engine:
            return {"status": "ERROR", "message": "SecOpsEngine not configured"}

        # 1. Fetch 90-day detection telemetry
        telemetry_map = self.engine.get_rule_detection_counts(lookback_days=lookback_days)

        # 2. Fetch rule deployments for live status and archive filtering
        deployment_map = {}
        try:
            deployments_res = self.engine.list_rule_deployments(page_size=1000)
            raw_deps = getattr(deployments_res, "deployments", []) or []
            for d in raw_deps:
                d_id = getattr(d, "rule_id", "") or (d.name.split("/")[-2] if hasattr(d, "name") and "/" in d.name else "")
                if d_id:
                    deployment_map[d_id] = d
        except Exception as dep_err:
            pass

        # 3. List rules
        rules_res = self.engine.list_rules(page_size=100, view="FULL")
        rules = getattr(rules_res, "rules", []) or []

        # 4. Process rules, compute DPS, and persist to Evidence Fabric
        candidates = []
        texts_to_embed = []
        rule_ids_to_embed = []
        broken_count = 0
        silent_count = 0
        stale_count = 0

        for r in rules:
            r_id = (
                getattr(r, "rule_id", "")
                or getattr(r, "id", "")
                or (r.get("rule_id") if isinstance(r, dict) else "")
                or (r.get("id") if isinstance(r, dict) else "")
            )
            if not r_id:
                raw_name = getattr(r, "name", "") or (r.get("name") if isinstance(r, dict) else "")
                if raw_name:
                    r_id = raw_name.split("/")[-1].split("@")[0]

            dep = deployment_map.get(r_id)
            is_archived = False
            if dep:
                is_archived = bool(getattr(dep, "archived", False) or (dep.raw.get("archived", False) if hasattr(dep, "raw") else False))
            if not is_archived:
                is_archived = bool(getattr(r, "archived", False) or (r.get("archived", False) if isinstance(r, dict) else False))

            if is_archived:
                continue

            # Accurate is_live status
            is_live = False
            if dep:
                is_live = bool(
                    getattr(dep, "enabled", False)
                    or getattr(dep, "alerting", False)
                    or getattr(dep, "run_frequency", "") == "LIVE"
                    or getattr(dep, "execution_state", "") == "ACTIVE"
                )
            else:
                is_live = bool(getattr(r, "live_mode_enabled", False) or (r.get("live_mode_enabled") if isinstance(r, dict) else False))

            r_name = (
                getattr(r, "display_name", "")
                or (r.get("display_name") if isinstance(r, dict) else "")
                or getattr(r, "name", "")
                or (r.get("name") if isinstance(r, dict) else "")
            )
            r_text = getattr(r, "rule_text", "") or getattr(r, "text", "") or (r.get("rule_text", "") if isinstance(r, dict) else "")

            syntax_verified = True
            comp_diags = []
            if r_text:
                try:
                    val_res = self.engine.verify_rule(rule_text=r_text)
                    syntax_verified = bool(getattr(val_res, "success", True))
                    comp_diags = [str(d) for d in getattr(val_res, "diagnostics", [])]
                except Exception as c_err:
                    syntax_verified = False
                    comp_diags = [str(c_err)]

            t_data = telemetry_map.get(r_id, {})
            dps, flags, rec, days_stale = calculate_decay_score(
                rule_detail=r,
                detection_telemetry_90d=t_data,
                syntax_verified=syntax_verified,
                compiler_diagnostics=comp_diags,
                is_live=is_live,
            )

            if "BROKEN_COMPILATION" in flags:
                broken_count += 1
            if "SILENT" in flags:
                silent_count += 1
            if "STALE" in flags:
                stale_count += 1

            det_count = t_data.get("count", 0)

            state_doc = {
                "rule_id": r_id,
                "rule_name": r_name,
                "dps_score": dps,
                "decay_flags": flags,
                "is_live": is_live,
                "days_stale": days_stale,
                "detection_count_90d": det_count,
                "first_seen": t_data.get("first_seen"),
                "last_seen": t_data.get("last_seen"),
                "recommendation": rec,
                "rule_text": r_text,
                "compiler_errors": comp_diags if not syntax_verified else [],
                "synced_at": datetime.now(timezone.utc).isoformat(),
            }

            if self.evidence_store:
                self.evidence_store.save_rule_state(r_id, state_doc)

            candidates.append(state_doc)
            if r_text:
                texts_to_embed.append(f"{r_name}\n{r_text}")
                rule_ids_to_embed.append(r_id)

        # Batch generate embeddings if store is available
        if self.evidence_store and texts_to_embed:
            try:
                embeddings = self.evidence_store.generate_rule_embeddings(texts_to_embed)
                for rid, emb in zip(rule_ids_to_embed, embeddings):
                    self.evidence_store.save_rule_state(rid, {"embedding_768": emb})
            except Exception as emb_err:
                pass

        candidates.sort(key=lambda x: x["dps_score"], reverse=True)
        avg_dps = round(sum(c["dps_score"] for c in candidates) / len(candidates), 1) if candidates else 0.0

        # Deduplicate top_candidates by display name so top slots highlight distinct rules
        seen_names = set()
        top_candidates = []
        for c in candidates:
            norm_name = (c.get("rule_name") or "").strip().lower()
            if norm_name and norm_name not in seen_names:
                seen_names.add(norm_name)
                top_candidates.append(c)
            elif not norm_name:
                top_candidates.append(c)
            if len(top_candidates) >= 5:
                break

        seen_ret_names = set()
        top_return_candidates = []
        for c in candidates:
            norm_name = (c.get("rule_name") or "").strip().lower()
            if norm_name and norm_name not in seen_ret_names:
                seen_ret_names.add(norm_name)
                top_return_candidates.append(c)
            elif not norm_name:
                top_return_candidates.append(c)
            if len(top_return_candidates) >= 10:
                break

        widget = {
            "type": "decay_sync_card",
            "total_rules": len(candidates),
            "broken_count": broken_count,
            "silent_count": silent_count,
            "stale_count": stale_count,
            "average_dps": avg_dps,
            "top_candidates": top_candidates,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        self.last_widget = widget

        self.executed_tool_calls.append({
            "agent": self.handle,
            "tool": "run_decay_synchronization",
            "capability_id": "rule.decay.audit",
            "arguments": {"lookback_days": lookback_days},
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })

        return {
            "status": "SUCCESS",
            "total_rules": len(candidates),
            "broken_count": broken_count,
            "silent_count": silent_count,
            "stale_count": stale_count,
            "average_dps": avg_dps,
            "top_candidates": top_return_candidates,
            "widget": widget,
        }

    def audit_single_rule_decay(
        self,
        rule_id: str,
        lookback_days: int = 90,
    ) -> Dict[str, Any]:
        """Performs a deep-dive decay audit on a single rule, including 30-day UDM population checks.

        Args:
            rule_id: The Chronicle rule ID (e.g. 'ru_6cb096c8-2270-4d03-860b-3c3db443a7e4').
            lookback_days: Detection telemetry lookback days (default 90).
        """
        if not self.engine:
            return {"status": "ERROR", "message": "SecOpsEngine not configured"}

        report = self.engine.audit_rule_decay(
            rule_id=rule_id,
            lookback_days=lookback_days,
            check_population=True,
            schema_cache=self.evidence_store,
        )

        if not report.assessments:
            return {"status": "ERROR", "message": f"Rule {rule_id} not found or could not be audited"}

        assessment = report.assessments[0]

        decay_widget = {
            "type": "decay_audit_card",
            "rule_id": assessment.rule_id,
            "rule_name": assessment.rule_name,
            "dps_score": assessment.dps_score,
            "decay_flags": assessment.decay_flags,
            "is_live": assessment.is_live,
            "days_stale": assessment.days_stale,
            "detection_count_90d": assessment.detection_count_90d,
            "first_seen": assessment.first_seen,
            "last_seen": assessment.last_seen,
            "unpopulated_fields": assessment.unpopulated_fields,
            "compiler_errors": assessment.compiler_errors,
            "recommendation": assessment.recommendation,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        self.last_widget = decay_widget

        if self.evidence_store:
            self.evidence_store.save_rule_state(assessment.rule_id, {
                "dps_score": assessment.dps_score,
                "decay_flags": assessment.decay_flags,
                "days_stale": assessment.days_stale,
                "detection_count_90d": assessment.detection_count_90d,
                "unpopulated_fields": assessment.unpopulated_fields,
                "recommendation": assessment.recommendation,
                "last_audited_at": datetime.now(timezone.utc).isoformat(),
            })

        self.executed_tool_calls.append({
            "agent": self.handle,
            "tool": "audit_single_rule_decay",
            "capability_id": "rule.decay.audit",
            "arguments": {"rule_id": rule_id, "dps": assessment.dps_score},
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })

        return {
            "status": "SUCCESS",
            "rule_id": assessment.rule_id,
            "rule_name": assessment.rule_name,
            "dps_score": assessment.dps_score,
            "decay_flags": assessment.decay_flags,
            "days_stale": assessment.days_stale,
            "detection_count_90d": assessment.detection_count_90d,
            "unpopulated_fields": assessment.unpopulated_fields,
            "compiler_errors": assessment.compiler_errors,
            "recommendation": assessment.recommendation,
            "widget": decay_widget,
        }

    def check_udm_field_population(
        self,
        field_paths: List[str],
        vendor_product: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Checks whether given UDM fields contain values in live events over the last 30 days.

        Args:
            field_paths: List of UDM field paths (e.g. ['principal.process.file.full_path']).
            vendor_product: Optional product filter to scope telemetry (e.g. 'okta', 'windows_sysmon').
        """
        if not self.engine:
            return {"status": "ERROR", "message": "SecOpsEngine not configured"}

        results = self.engine.audit_udm_field_population(
            field_paths=field_paths,
            vendor_product=vendor_product,
            lookback_days=30,
            schema_cache=self.evidence_store,
        )
        return {"status": "SUCCESS", "fields": results}

    def submit_decay_proposal(
        self,
        title: str,
        target_resource_id: str,
        rationale: str,
        proposed_diff: str,
        refactored_rule_text: str,
    ) -> Dict[str, Any]:
        """Submits a formal Human-In-The-Loop change proposal to Gas Town .proposals/ and links it to Evidence Fabric.

        Args:
            title: Title describing the remediation (e.g. 'Fix unpopulated UDM path in ru_123').
            target_resource_id: The rule ID being remediated.
            rationale: SME strategic analysis explaining why the change is safe and effective.
            proposed_diff: Unified diff showing the remediation.
            refactored_rule_text: The complete refactored YARA-L rule text.
        """
        preflight = PreflightProof(syntax_verified=False, compiler_diagnostics=[])
        if self.engine:
            try:
                val_res = self.engine.verify_rule(rule_text=refactored_rule_text)
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

        effective_diff = proposed_diff
        if not effective_diff or effective_diff.strip() == "":
            orig_text = ""
            if self.engine:
                try:
                    r_detail = self.engine.get_rule(target_resource_id, view="FULL")
                    orig_text = getattr(r_detail, "rule_text", "") or getattr(r_detail, "text", "")
                except Exception:
                    pass
            if orig_text:
                diff_lines = list(difflib.unified_diff(
                    orig_text.splitlines(keepends=True),
                    refactored_rule_text.splitlines(keepends=True),
                    fromfile=f"a/{target_resource_id}.yaral",
                    tofile=f"b/{target_resource_id}.yaral",
                ))
                effective_diff = "".join(diff_lines)

        mutation_payload = {
            "rule_text": refactored_rule_text,
            "update_mask": "text",
        }
        proposal = self.submit_proposal(
            title=title,
            target_resource_id=target_resource_id,
            action_type="UPDATE_RULE_TEXT",
            rationale=rationale,
            proposed_diff=effective_diff or f"--- a/{target_resource_id}.yaral\\n+++ b/{target_resource_id}.yaral\\n@@ -1 +1 @@\\n# Refactored rule text updated.",
            mutation_payload=mutation_payload,
            preflight=preflight,
            risk_level="MEDIUM",
        )

        self.executed_tool_calls.append({
            "agent": self.handle,
            "tool": "submit_decay_proposal",
            "capability_id": "rule.proposal.submit",
            "arguments": {
                "title": title,
                "target_resource_id": target_resource_id,
                "syntax_verified": str(preflight.syntax_verified),
                "proposal_id": proposal.id,
            },
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })

        return {
            "status": "PROPOSAL_CREATED",
            "proposal_id": proposal.id,
            "title": proposal.title,
            "target_resource_id": target_resource_id,
            "syntax_verified": preflight.syntax_verified,
            "compiler_diagnostics": preflight.compiler_diagnostics,
            "message": f"Remediation proposal {proposal.id} created successfully and awaiting review in Gas Town .proposals/.",
        }

    def list_decay_queue(
        self,
        min_dps: int = 0,
        limit: int = 20,
    ) -> List[Dict[str, Any]]:
        """Retrieves the ranked rule decay review queue from Evidence Fabric.

        Args:
            min_dps: Minimum DPS score threshold (0-100).
            limit: Maximum candidates to return (default 20).
        """
        if not self.evidence_store:
            return []
        return self.evidence_store.list_decay_candidates(min_dps=min_dps, limit=limit)
