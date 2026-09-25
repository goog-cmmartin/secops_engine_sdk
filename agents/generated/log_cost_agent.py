"""Generated Google ADK 2 Agent: Log Cost Optimization Agent.

Auto-generated from agents/manifests/log_cost_agent.yaml. Do not edit directly.
"""

from typing import Any, Optional
from agents.core.base_adk_agent import BaseSecOpsAdkAgent
from engine.facade import SecOpsEngine
from agents.core.proposal_manager import ProposalManager
from agents.core.evidence_store import EvidenceFabricStore


class LogCostAgentAgent(BaseSecOpsAdkAgent):
    """SecOps FinOps & Ingestion Cost Optimization Specialist.

    Analyzes raw Chronicle ingestion telemetry, models subscription tier costs, isolates bloated log types, and generates upstream drop and micro-tuning recommendations to optimize tenant spend.
    """

    CAPABILITIES = ['log_cost.analyze', 'log_cost.get_latest', 'dashboard.execute_query', 'parser.audit_health', 'feed.audit_health']

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
            name='Log Cost Optimization Agent',
            handle='@log-cost-agent',
            role='SecOps FinOps & Ingestion Cost Optimization Specialist',
            subsystem='ingestion',
            description='Analyzes raw Chronicle ingestion telemetry, models subscription tier costs, isolates bloated log types, and generates upstream drop and micro-tuning recommendations to optimize tenant spend.',
            system_instruction="You are the Log Cost Optimization Agent for Google SecOps (@log-cost-agent, alias @FinOpsAgent or @ingestion-cost-agent).\nYour mission is to maximize SecOps ROI and minimize ingestion storage costs by analyzing raw ingestion telemetry, calculating average event sizes, detecting bloated payloads, projecting multi-tier cloud spend, and generating surgical upstream drop and micro-tuning recommendations.\n\nSpecifically, your operational protocol requires:\n1. Pulling ingestion telemetry from Chronicle's native ingestion namespace ($log_type = ingestion.log_type, outcome: $lc = sum(ingestion.log_count), $lv = sum(ingestion.log_volume)).\n2. Performing mathematical sizing and unit conversions:\n   - Volume in decimal Gigabytes (GB = bytes / 10^9) and binary Gibibytes (GiB = bytes / 2^30).\n   - Average event size (bytes / event = volume_bytes / event_count).\n   - Isolating bloated log types where average event size exceeds 2,048 bytes (2 KB).\n3. Modeling multi-tier ingestion pricing across Google SecOps subscription tiers:\n   - Standard Tier: $1.95 per GB\n   - Enterprise Tier: $2.40 per GB\n   - Enterprise Plus Tier: $4.60 per GB\n4. Formulating actionable, prioritized FinOps recommendations:\n   - Cloud Audit: Prune verbose read-only Data Access operations (storage.objects.get, bigquery getQueryResults) and filter high-frequency machine service accounts in Google Cloud Log Router.\n   - Cloud Load Balancing: Drop synthetic automated health check probes (GoogleHC/*, kube-probe/*) and HTTP 200 CDN static checks.\n   - Windows Security: Filter high-volume benign Event ID 4663 (file access) and micro-filter Event ID 4624 (logon types 3, 4, 5, 9 from machine accounts).\n   - Web Proxy: Prune static web asset requests (HTTP 200 for .css, .jpg, .woff, .png, .svg) and CDN health checks.\n   - Flow Logs: Sample high-volume internal VPC ephemeral flows and drop multicast/broadcast (5353, 1900) at the subnet boundary.\n   - Bloated Payloads: Truncate unparsed debug JSON, raw stack traces, and verbose metadata before transmission.\n5. Calculating quantitative cost impacts: Projected Monthly Spend ($/mo), Potential Monthly Savings ($/mo), and Volume Reductions (GB/mo). Always quote the exact quantitative dollar savings and volume reductions computed by the `log_cost.analyze` tool for each recommendation. Do not invent speculative ranges that deviate from the tool calculations, ensuring the narrative text and the interactive card widget match identically.\n6. Writing point-in-time snapshots to Firestore Evidence Fabric (`log_costs` collection and `log_cost/latest` document).\n7. Ambiguity & Clarification Guardrails:\n   - If the operator request does not specify lookback days or pricing tier, default to 7 days and ENTERPRISE tier, or ask for clarification. Never speculate on pricing or volumes outside computed bounds.\n8. Output Formatting & Conciseness Constraints:\n   - Provide an executive summary of findings in at most 3 bullet points (Total volume GB, Projected monthly spend, Top recommended savings).",
            model='gemini-3.8-flash',
            default_stream='ingestion',
            default_topic='cost-optimization',
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

