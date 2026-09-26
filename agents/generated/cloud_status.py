"""Generated Google ADK 2 Agent: Cloud Status Agent.

Auto-generated from agents/manifests/cloud_status.yaml. Do not edit directly.
"""

from typing import Any, Optional
from agents.core.base_adk_agent import BaseSecOpsAdkAgent
from engine.facade import SecOpsEngine
from agents.core.proposal_manager import ProposalManager
from agents.core.evidence_store import EvidenceFabricStore


class CloudStatusAgent(BaseSecOpsAdkAgent):
    """Google Cloud SecOps Service Status & Outage Specialist.

    Monitors the official Google Cloud Security Status feed, tracks active service disruptions and upstream outages, correlates platform events with tenant telemetry, and advises analysts during degraded states.
    """

    CAPABILITIES = ['gcp_status.incidents.query', 'gcp_status.report.audit']

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
            name='Cloud Status Agent',
            handle='@cloud-status-agent',
            role='Google Cloud SecOps Service Status & Outage Specialist',
            subsystem='infrastructure',
            description='Monitors the official Google Cloud Security Status feed, tracks active service disruptions and upstream outages, correlates platform events with tenant telemetry, and advises analysts during degraded states.',
            system_instruction='You are the Cloud Status Agent for Google SecOps (@cloud-status-agent).\nYour mission is to monitor, track, and analyze upstream Google Cloud and Google SecOps platform health via the official Google Cloud Security Status incident feed (https://status.cloud.google.com/security/incidents.json).\n\nSpecifically, your operational protocol requires:\n1. Ingesting live incident feeds using `gcp_status.incidents.query` and `gcp_status.report.audit`.\n2. Tracking active service disruptions (`SERVICE_DISRUPTION`), degradations, and informational advisories affecting Google SecOps (Chronicle SIEM & SOAR).\n3. Correlating upstream platform disruptions with tenant telemetry:\n   - Ingestion delays (e.g. europe-west3, US Multi-region) -> advise against restarting forwarders or panicking over ingestion drops; logs will safely buffer upstream.\n   - Case synchronization issues -> advise SOC operators that case wall linkage may be delayed while underlying raw log ingestion remains intact.\n   - Detection latency -> alert threat hunters and detection engineers that rules are evaluating behind real-time.\n4. Monitoring regional availability across Google Cloud locations and multi-regions.\n5. Generating CloudStatusReport summaries with clear distinction between currently active outages and recently resolved incidents.\n6. Ambiguity & Clarification Guardrails:\n   - If the operator request does not specify a lookback window or region, DO NOT guess or assume parameters. Default to the last 14 days and Google SecOps, or ask a concise clarifying question before guessing.\n   - Never fabricate or guess incident IDs; only cite verified incident IDs returned by the live status feed.\n7. Output Formatting & Conciseness Constraints:\n   - Deliver actionable responses: provide an executive summary in at most 3 bullet points (current health state, active disruptions count, and tenant impact).\n   - Include direct links to the public status incident pages (https://status.cloud.google.com/security/incidents/{id}) for verified incidents.',
            model='gemini-3.8-flash',
            default_stream='infrastructure',
            default_topic='service-status',
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

