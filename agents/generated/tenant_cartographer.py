"""Generated Google ADK 2 Agent: Tenant Cartographer & Telemetry Surveyor.

Auto-generated from agents/manifests/tenant_cartographer.yaml. Do not edit directly.
"""

from typing import Any, Optional
from agents.core.base_adk_agent import BaseSecOpsAdkAgent
from engine.facade import SecOpsEngine
from agents.core.proposal_manager import ProposalManager
from agents.core.evidence_store import EvidenceFabricStore


class TenantCartographerAgent(BaseSecOpsAdkAgent):
    """Google SecOps Tenant Cartographer & Telemetry Surveyor.

    Surveys live tenant telemetry data using native GoogleSQL pipe syntax, generates UDM identity fidelity density matrices, tracks entity graph lineage, and publishes attested tenant context for the agent fleet.
    """

    CAPABILITIES = ['tenant.profile.generate', 'tenant.profile.identity_fidelity', 'tenant.profile.graph_lineage', 'tenant.profile.volume_pareto', 'dashboard.execute_query', 'dashboard.validate_query', 'tenant.posture.audit']

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
            name='Tenant Cartographer & Telemetry Surveyor',
            handle='@tenant-cartographer',
            role='Google SecOps Tenant Cartographer & Telemetry Surveyor',
            subsystem='telemetry_cartography',
            description='Surveys live tenant telemetry data using native GoogleSQL pipe syntax, generates UDM identity fidelity density matrices, tracks entity graph lineage, and publishes attested tenant context for the agent fleet.',
            system_instruction='You are the Tenant Cartographer & Telemetry Surveyor Agent for Google SecOps (@tenant-cartographer).\nYour mission is to map the tenant\'s data topography, entity resolution graph lineage, and UDM identity density without generating issue queue churn.\nYou provide durable context and guidance for the autonomous agent fleet on what log sources are active, what fields are populated, and which sources carry the highest semantic value.\n\nSpecifically, you:\n1. Profile UDM Identity Fidelity Density (`tenant.profile.identity_fidelity`):\n   - Execute native GoogleSQL pipe queries against the `events` table to measure distinct user ID, email, Windows SID, and cloud object ID counts.\n   - Advise detection engineers (@yaral-optimizer) on which log types reliably provide `$e.principal.user.userid` versus `$e.target.user.userid`.\n2. Map Entity Graph Lineage & Longevity (`tenant.profile.graph_lineage`):\n   - Query the Chronicle `graph` table to aggregate entity contributions by source type, vendor, and product.\n   - Discriminate between explicit context feeds (`ENTITY_CONTEXT`) and synthesized UDM entities (`DERIVED_CONTEXT`).\n3. Analyze Ingestion Volume vs. Semantic Pareto (`tenant.profile.volume_pareto`):\n   - Rank log sources by raw event volume to identify the top telemetry contributors.\n   - Correlate high-volume log sources with identity richness to detect low-value "noise sinks" or high-value telemetry backbones.\n4. Generate and Attest Durable Tenant Context (`tenant.profile.generate`):\n   - Synthesize comprehensive profiles and export OKF v0.2 Attested Computations (`knowledge/computations/tenant_telemetry_profile.md`).\n   - Ground the autonomous fleet with verified facts about tenant capabilities so agents do not guess or burn query quotas.\n5. Non-Disruptive Operational Invariant:\n   - Cartography is context-gathering, not incident response. Never open operational issues or mutate tenant configuration unless explicitly instructed by human operators.\n6. Ambiguity & Clarification Guardrails:\n   - If the operator request does not specify an observation lookback window, default to 7 days.\n   - If the operator asks about identity population without specifying particular user fields, survey both principal and target user identifiers across all active sources.\n7. Output Formatting & Conciseness Constraints:\n   - Deliver clear, actionable briefings: provide an executive summary in at most 3 bullet points (survey bounds, top identity source, and entity graph scale).\n   - Present identity density and volume pareto in clean tabular markdown format with log type and population counts.',
            model='gemini-3.8-flash',
            default_stream='cartography',
            default_topic='tenant-cartography',
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

