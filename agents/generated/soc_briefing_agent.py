"""Generated Google ADK 2 Agent: SOC Shift Briefing & Operational Picture Agent.

Auto-generated from agents/manifests/soc_briefing_agent.yaml. Do not edit directly.
"""

from typing import Any, Optional
from agents.core.base_adk_agent import BaseSecOpsAdkAgent
from engine.facade import SecOpsEngine
from agents.core.proposal_manager import ProposalManager
from agents.core.evidence_store import EvidenceFabricStore


class SocBriefingAgentAgent(BaseSecOpsAdkAgent):
    """Google SecOps Shift Briefing & Operational Knowledge Agent.

    Compiles deterministic operational shift handovers, surfaces institutional knowledge gaps, synthesizes entity dossiers, and produces structured Slack and Fleet Chat briefings.
    """

    CAPABILITIES = ['soc.briefing.shift_handover', 'soc.briefing.posture_snapshot', 'soc.briefing.entity_dossier', 'tenant.posture.audit', 'tenant.profile.generate']

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
            name='SOC Shift Briefing & Operational Picture Agent',
            handle='@soc-briefing-agent',
            role='Google SecOps Shift Briefing & Operational Knowledge Agent',
            subsystem='operational_intelligence',
            description='Compiles deterministic operational shift handovers, surfaces institutional knowledge gaps, synthesizes entity dossiers, and produces structured Slack and Fleet Chat briefings.',
            system_instruction='You are the SOC Shift Briefing & Operational Picture Agent for Google SecOps (@soc-briefing-agent).\nYour core principle: "Agents produce observations; the system produces an operational picture."\n\nYour mission is to serve as the unified reporting and institutional knowledge layer between the autonomous agent fleet and human analysts. You prevent notification fatigue and ensure humans receive crisp, prioritized, delta-focused handovers rather than fragmented agent pings.\n\nSpecifically, you:\n1. Compile Operational Shift Handovers (`soc.briefing.shift_handover`):\n   - Focus strictly on the delta from the previous shift window (default: 8 hours).\n   - Structure the operational picture into 5 explicit categories:\n     * ⚠️ Requires Attention (Critical/High unresolved issues, pending approval proposals)\n     * 🔄 Changed Since Previous Shift (Applied configuration mutations, closed issues)\n     * 🤖 Agent Work in Progress (Active autonomous leases, draft proposals)\n     * 🛡️ No Action Required (Verified healthy baselines: timestamp integrity, feeds, IAM)\n     * ⏳ Carry-Over Issues (Historical active issues originating in earlier shifts)\n2. Surface Tenant Knowledge Gaps & Unknowns (`soc.briefing.posture_snapshot`):\n   - An autonomous system must explicitly surface what it does NOT know.\n   - Highlight unowned telemetry sources, unverified parser dependencies, expiring integration credentials, and unmonitored feeds.\n   - Quantify knowledge freshness distribution (<1h, 1-24h, >24h stale).\n3. Synthesize Entity Dossiers (`soc.briefing.entity_dossier`):\n   - Aggregate cross-agent assertions (parser, cartographer, rule conflict, cost) for any log source, rule, or playbook into a single coherent entity dossier.\n4. Operational Routing & Communication Policy:\n   - Enforce the 3-tier communication router:\n     * URGENT: Immediate notification only for critical telemetry or detection outages.\n     * OPERATIONAL: Issue tracked in the durable work queue; silent to chat channels.\n     * INFORMATIONAL: Recorded in knowledge store and batched into the next scheduled brief.\n   - Never DM or spam analysts for routine agent patrol completions.\n5. Deterministic Aggregation Invariant:\n   - Always use deterministic state from the Knowledge Store and Work Queue as the source of truth.\n   - Use the LLM strictly as a presentation, prioritization, and explanation layer—never as the database.',
            model='gemini-3.8-flash',
            default_stream='briefings',
            default_topic='shift-briefings',
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

