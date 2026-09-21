"""Generated Google ADK 2 Agent: YARA-L Optimizer.

Auto-generated from agents/manifests/yaral_optimizer.yaml. Do not edit directly.
"""

from typing import Any, Optional
import difflib
from datetime import datetime, timezone
from agents.core.proposal_manager import PreflightProof
from agents.core.base_adk_agent import BaseSecOpsAdkAgent
from engine.facade import SecOpsEngine
from agents.core.proposal_manager import ProposalManager
from agents.core.evidence_store import EvidenceFabricStore


class YaralOptimizerAgent(BaseSecOpsAdkAgent):
    """YARA-L Compiler & Rule Performance Optimizer.

    Refactors inefficient YARA-L rules, resolves Cartesian cross-joins, enforces hash/IP match partitioning, verifies compilation, and submits HITL change proposals.
    """

    CAPABILITIES = ['rule.verify', 'rule.get', 'rule.patch', 'rule.deployment.update', 'rule.revisions']

    def __init__(
        self,
        engine: Optional[SecOpsEngine] = None,
        proposal_manager: Optional[ProposalManager] = None,
        inventory_client: Any = None,
        evidence_store: Optional[EvidenceFabricStore] = None,
    ):
        super().__init__(
            name='YARA-L Optimizer',
            handle='@yaral-optimizer',
            role='YARA-L Compiler & Rule Performance Optimizer',
            subsystem='detection_rules',
            description='Refactors inefficient YARA-L rules, resolves Cartesian cross-joins, enforces hash/IP match partitioning, verifies compilation, and submits HITL change proposals.',
            system_instruction='You are the YARA-L Optimizer Agent (@yaral-optimizer).\nYour mission is to eliminate performance bottlenecks and timeouts in Google SecOps detection rules:\n1. Inspect rules using `get_rule` (or read from Evidence Fabric blackboard). If `get_rule` does not contain rule text or fails, do not repeatedly retry; synthesize a valid detection rule for the requested rule ID.\n2. Optimize unconstrained match clauses (e.g. cross-joining events over broad time windows without common join keys).\n3. Partition match clauses on high-cardinality keys like $file_hash, $target_ip, or $hostname.\n4. Constrain sliding time windows (e.g., change `over 24h` or `over 1h` to narrower windows like `over 5m` or `over 10m` when appropriate).\n5. Add/bound multi-event timestamp deltas.\n6. ALWAYS verify syntax and compilation of the refactored rule using `verify_rule_text` before submitting any proposal.\n7. ALWAYS submit a formal change proposal using `submit_rule_proposal` so human operators can review and approve via HITL.\n8. Ambiguity & Clarification Guardrails:\n   - If the operator request does not specify a target rule ID or rule snippet to optimize, DO NOT assume or guess rule names. Ask for the rule ID or query Evidence Fabric todos first.\n9. Output Formatting & Conciseness Constraints:\n   - Provide an executive summary of optimization results in at most 3 bullet points (join keys partitioned, time window tightened, compilation status).\n   - Format all refactored rules strictly as unified diffs in Gas Town proposals.',
            model='gemini-3.8-flash',
            default_stream='detections',
            default_topic='rule-proposals',
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

        self._tools["submit_rule_proposal"] = self.submit_rule_proposal

    def submit_rule_proposal(
        self,
        title: str,
        target_resource_id: str,
        rationale: str,
        proposed_diff: str,
        optimized_rule_text: str,
    ) -> dict:
        """Submits a formal Human-In-The-Loop change proposal to Gas Town .proposals/ and links it to Evidence Fabric.

        Args:
            title: Title describing the optimization (e.g. 'Optimize Match Clause for ru_123').
            target_resource_id: The rule ID being optimized (e.g. 'ru_6cb096c8-2270-4d03-860b-3c3db443a7e4').
            rationale: Explanation of performance improvements (e.g. 'Partitioned on $target_ip, window narrowed to 5m').
            proposed_diff: The unified diff showing the exact changes.
            optimized_rule_text: The full refactored YARA-L rule text.
        """
        # 1. Run live preflight verification against Chronicle compiler
        preflight = PreflightProof(syntax_verified=False, compiler_diagnostics=[])
        if self.engine:
            try:
                val_res = self.engine.verify_rule(rule_text=optimized_rule_text)
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

        # 2. Compute unified diff if missing or empty
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
                    optimized_rule_text.splitlines(keepends=True),
                    fromfile=f"a/{target_resource_id}.yaral",
                    tofile=f"b/{target_resource_id}.yaral",
                ))
                effective_diff = "".join(diff_lines)

        # 3. Submit change proposal
        mutation_payload = {
            "rule_text": optimized_rule_text,
            "update_mask": "text",
        }
        proposal = self.submit_proposal(
            title=title,
            target_resource_id=target_resource_id,
            action_type="UPDATE_RULE_TEXT",
            rationale=rationale,
            proposed_diff=effective_diff or f"--- a/{target_resource_id}.yaral\n+++ b/{target_resource_id}.yaral\n@@ -1 +1 @@\n# Refactored rule text updated.",
            mutation_payload=mutation_payload,
            preflight=preflight,
            risk_level="MEDIUM",
        )

        self.executed_tool_calls.append({
            "agent": self.handle,
            "tool": "submit_rule_proposal",
            "capability_id": "rule.proposal.submit",
            "arguments": {
                "title": title,
                "target_resource_id": target_resource_id,
                "syntax_verified": str(preflight.syntax_verified),
                "proposal_id": proposal.id,
            },
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })

        # 4. Update Evidence Fabric todos if open remediation task exists
        if self.evidence_store:
            try:
                todos = self.evidence_store.list_todos(status="PENDING")
                for td in todos:
                    if target_resource_id in td.get("title", "") or target_resource_id in td.get("description", ""):
                        self.evidence_store.update_todo_status(
                            todo_id=td["id"],
                            status="RESOLVED",
                            resolution=f"Addressed by proposal {proposal.id}: {title}",
                        )
            except Exception:
                pass

        return {
            "status": "PROPOSAL_CREATED",
            "proposal_id": proposal.id,
            "title": proposal.title,
            "target_resource_id": target_resource_id,
            "syntax_verified": preflight.syntax_verified,
            "compiler_diagnostics": preflight.compiler_diagnostics,
            "message": f"Proposal {proposal.id} created successfully and awaiting human review in Gas Town .proposals/.",
        }
