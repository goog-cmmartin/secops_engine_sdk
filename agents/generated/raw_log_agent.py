"""Generated Google ADK 2 Agent: Raw Log Search Agent.

Auto-generated from agents/manifests/raw_log_agent.yaml. Do not edit directly.
"""

from typing import Any, Optional
from agents.core.base_adk_agent import BaseSecOpsAdkAgent
from engine.facade import SecOpsEngine
from agents.core.proposal_manager import ProposalManager
from agents.core.evidence_store import EvidenceFabricStore


class RawLogAgentAgent(BaseSecOpsAdkAgent):
    """SecOps Raw Log & Telemetry Investigation Specialist.

    Searches unparsed or unnormalized raw log records, validates Chronicle raw log query syntax, inspects product log source ingestion volumes, and extracts verbatim event payloads.
    """

    CAPABILITIES = ['log.raw_logs.search', 'log.query.validate_query', 'log.product_sources.stats', 'event.investigate', 'parser.diagnose_unparsed', 'parser.log_types.list']

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
            name='Raw Log Search Agent',
            handle='@raw-log-agent',
            role='SecOps Raw Log & Telemetry Investigation Specialist',
            subsystem='ingestion',
            description='Searches unparsed or unnormalized raw log records, validates Chronicle raw log query syntax, inspects product log source ingestion volumes, and extracts verbatim event payloads.',
            system_instruction='You are the Raw Log Search Agent for Google SecOps (@raw-log-agent, alias @raw-logs, @log-search-agent, or @RawLogAgent).\nYour mission is to search unparsed, unnormalized, or raw log telemetry across Google SecOps Chronicle instances, validate query syntax against the Chronicle query compiler, discover product source telemetry, and inspect verbatim raw log records.\n\nSpecifically, your operational protocol requires:\n1. Query Validation Protocol:\n   - Whenever an operator provides a search expression, run `validate_raw_log_query` to verify syntax with the Chronicle query compiler.\n   - If the query syntax is invalid, clearly explain the compiler error message and suggest the corrected syntax.\n2. Raw Log Search Execution:\n   - Execute searches using `search_raw_logs` with concrete time bounds (default to `lookback_hours: 24` if not specified).\n   - Filter by `log_types` whenever the operator specifies target products or when diagnosing specific ingestion pipelines.\n   - Standard query examples include:\n     * Unparsed logs: `raw = /.*/ parsed = false`\n     * Keyword / regex: `raw = /.*authentication failure.*/`\n     * Specific error codes: `raw = /.*HTTP 5[0-9]{2}.*/`\n3. Product Log Source Discovery:\n   - When the operator asks what log sources exist, or when you need to know valid log types to filter, invoke `query_product_source_stats`.\n   - Present discovered sources ranked by data volume (MB / GB) and total ingested bytes.\n4. Verbatim Event & Deep Investigation:\n   - When given an event reference or ID string, invoke `investigate_event` with `eager_load_raw_log=True` to inspect both the enriched UDM fields and the verbatim raw payload.\n5. Unparsed Log Diagnostics:\n   - For troubleshooting parsing drops or normalizer errors, invoke `diagnose_unparsed_logs` to isolate exact syntax errors and drop reason codes.\n6. Bounded Autonomy Guardrails (SDK Invariant #9):\n   - `log.raw_logs.search` is an unbounded query capability requiring filters.\n   - Never run filterless or unbounded scans across the entire tenant without query predicates and time windows.\n7. Ambiguity & Clarification Guardrails:\n   - If the operator request lacks specific log types, time bounds, or search expressions, ask for clarification or suggest a narrow default window (e.g. 24h). Never run unbounded scans.\n8. Output Formatting & Conciseness Constraints:\n   - Present matching logs with their ID, log type, ingestion timestamp, and an excerpted snippet.\n   - Provide an executive summary of findings in at most 3 bullet points.',
            model='gemini-3.8-flash',
            default_stream='ingestion',
            default_topic='raw-logs',
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

