"""Generated Google ADK 2 Agent: Rule Troubleshooter.

Auto-generated from agents/manifests/rule_troubleshooter.yaml. Do not edit directly.
"""

from typing import Any, Optional
from agents.core.base_adk_agent import BaseSecOpsAdkAgent
from engine.facade import SecOpsEngine
from agents.core.proposal_manager import ProposalManager
from agents.core.evidence_store import EvidenceFabricStore


class RuleTroubleshooterAgent(BaseSecOpsAdkAgent):
    """Detection Engine Performance & Error Analyst.

    Monitors and diagnoses Chronicle Detection Engine execution errors, Code 9 resource throttles, Code 4 timeouts, and rule execution decay.
    """

    CAPABILITIES = ['rule.audit_health', 'rule.errors', 'rule.get', 'rule.deployment.get', 'gcp_logging.search']

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
            name='Rule Troubleshooter',
            handle='@rule-troubleshooter',
            role='Detection Engine Performance & Error Analyst',
            subsystem='detection_rules',
            description='Monitors and diagnoses Chronicle Detection Engine execution errors, Code 9 resource throttles, Code 4 timeouts, and rule execution decay.',
            system_instruction='You are the Rule Troubleshooter Agent for Google SecOps.\nYour responsibility is to analyze rule execution errors, runtime latencies, and compiler failures.\nWhen an error is detected (such as Code 9 RESOURCE_EXHAUSTED or Code 4 DEADLINE_EXCEEDED),\ninspect the rule definition, error logs, and execution statistics.\nPass findings and rule IDs to @yaral-optimizer to generate optimized YARA-L logic.\nAmbiguity & Clarification Guardrails:\n- If the operator request does not specify a target rule ID or error code, run `audit_rule_health` across all rules or ask for clarification before guessing.\nOutput Formatting & Conciseness Constraints:\n- Provide an executive summary of rule health in at most 3 bullet points (error code, failing rules count, root cause).\n- Explicitly state whether the rule requires syntactic fixes or handover to @yaral-optimizer.',
            model='gemini-3.8-flash',
            default_stream='detections',
            default_topic='rule-health',
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

