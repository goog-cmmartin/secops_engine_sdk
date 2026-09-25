"""Generated Google ADK 2 Agent: SOAR Playbook Inventory & Decay Agent.

Auto-generated from agents/manifests/playbook_decay.yaml. Do not edit directly.
"""

from typing import Any, Optional
from datetime import datetime, timezone
import json
import logging
from typing import Any, Dict, List, Optional
from agents.core.base_adk_agent import BaseSecOpsAdkAgent
from engine.facade import SecOpsEngine
from agents.core.proposal_manager import ProposalManager
from agents.core.evidence_store import EvidenceFabricStore


class PlaybookDecayAgent(BaseSecOpsAdkAgent):
    """Google SecOps SOAR Playbook Inventory, Resilience Scoring & Decay Specialist.

    Audits Google SecOps SOAR playbooks and modular nested blocks for 100-pt static resilience, 30-day execution telemetry, Mermaid DAG synthesis, and Firestore persistence.
    """

    CAPABILITIES = ['playbook.decay_audit', 'playbook.search', 'playbook.get', 'playbook.categories', 'playbook.instances', 'playbook.audit_health', 'dashboard.execute_query']

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
            name='SOAR Playbook Inventory & Decay Agent',
            handle='@playbook-decay-agent',
            role='Google SecOps SOAR Playbook Inventory, Resilience Scoring & Decay Specialist',
            subsystem='soar_automation',
            description='Audits Google SecOps SOAR playbooks and modular nested blocks for 100-pt static resilience, 30-day execution telemetry, Mermaid DAG synthesis, and Firestore persistence.',
            system_instruction='You are the SOAR Playbook Inventory & Decay Agent for Google SecOps (@playbook-decay-agent).\nYour mission is to continuously audit, evaluate, and safeguard automation resilience across Chronicle SOAR playbooks and modular nested blocks.\nSpecifically, you:\n1. Ingest and Discover Playbooks (`playbook.search`, `playbook.get`, `playbook.categories`):\n   - Ingest active playbooks, categories, step definitions, and relation transition DAGs from Google SecOps REST endpoints.\n   - Inspect step execution configurations, retry policies, and autoSkipOnFailure flags.\n2. Audit 100-Point Resilience Scoring & Decay (`playbook.decay_audit`):\n   - Production Hygiene (HYG-01): Flag active production playbooks running with debugMode enabled (-15 pts).\n   - Step Resilience (ERR-01): Identify action connector steps missing automated retry configurations (-2 pts/step, max -10 pts).\n   - Error Boundaries (ERR-02): Detect enrichment actions (VirusTotal, IP/Domain lookup) lacking auto-skip or FAULTED fallbacks (-5 pts).\n   - Containment Integrity (ERR-03): Flag critical containment actions (isolate, block, quarantine) with silent auto-skip (-3 pts).\n   - Single Points of Failure (ERR-04): Detect critical action steps with no retries, no auto-skip, and no FAULTED path (-8 pts).\n   - Lifecycle Decay (MAINT-01, MAINT-02): Identify stale active playbooks unmodified for >90-365 days and un-tuned initial configurations.\n   - Execution Priority (PRIO-01, PRIO-02, PRIO-03): Flag shadowing risks and global wildcard interception, identify master orchestrator patterns.\n   - Human Governance (HITL-01, HITL-OBS): Check for manual approval steps and verify SLA timeout configurations.\n3. Correlate 30-Day Execution Telemetry (`dashboard.execute_query`):\n   - Query Chronicle dashboardQueries to aggregate execution counts, failure rates, and duration metrics over 30 days.\n   - Deduct points for silent playbooks with 0 runs (EXEC-01), high failure rates >20% (EXEC-02), and rate-limit warnings (EXEC-03).\n4. Generate DAG Flowcharts & Synthesize GenAI Architectural Briefs:\n   - Produce clean, interactive Mermaid.js flowchart DAGs highlighting trigger scopes, conditions, actions, and faulted branches.\n   - Synthesize 4-part architectural executive briefs covering Intent, Data Pipeline, Decision Branches, and Containment.\n5. Persist State in Evidence Fabric Firestore (`soar_playbooks`):\n   - Persist comprehensive audit reports into collection `soar_playbooks` using workflow UUIDs as document keys.\n   - Strictly enforce 1MB document sanitization safeguards by stripping bloated UI templates and debug traces.\n6. Ambiguity & Clarification Guardrails:\n   - If the operator request does not specify whether to audit a specific playbook or the entire tenant catalog, default to auditing the top 20 active playbooks across the catalog with a 30-day telemetry window.\n   - If a playbook name or UUID is ambiguous, search for matching playbooks via `playbook.search` and request explicit disambiguation.\n7. Output Formatting & Conciseness Constraints:\n   - Provide an executive summary in at most 3 bullet points detailing total playbooks audited, average resilience score, and degraded count.\n   - Present individual playbook findings in a structured card with letter grade, score, 30-day failure rate, and top deduction breakdown.',
            model='gemini-3.8-flash',
            default_stream='soar',
            default_topic='playbook-health',
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

        self._tools["audit_playbook_decay"] = self.audit_playbook_decay
        self._tools["get_playbook_decay_report"] = self.get_playbook_decay_report
        self._tools["list_playbook_reports"] = self.list_playbook_reports

    def audit_playbook_decay(
        self,
        workflow_identifier: Optional[str] = None,
        category: Optional[str] = None,
        lookback_days: int = 30,
        generate_brief: bool = True,
        persist: bool = True,
        limit: int = 20,
    ) -> Dict[str, Any]:
        """Audits SOAR playbooks and modular nested blocks for 100-pt static resilience, 30-day telemetry, and decay.

        Args:
            workflow_identifier: Optional specific playbook UUID to audit.
            category: Optional category filter.
            lookback_days: Chronicle telemetry evaluation window in days (default: 30).
            generate_brief: Whether to synthesize the GenAI 4-part architectural brief.
            persist: Whether to persist reports to Evidence Fabric Firestore soar_playbooks.
            limit: Maximum playbooks to audit when scanning catalog (default: 20).
        """
        if not self.engine:
            return {"status": "ERROR", "message": "SecOpsEngine not configured"}

        report = self.engine.audit_playbook_decay(
            workflow_identifier=workflow_identifier,
            category=category,
            lookback_days=lookback_days,
            generate_brief=generate_brief,
            persist=persist,
            limit=limit,
        )

        self.executed_tool_calls.append({
            "agent": self.handle,
            "tool": "audit_playbook_decay",
            "capability_id": "playbook.decay_audit",
            "arguments": {
                "workflow_identifier": workflow_identifier,
                "category": category,
                "lookback_days": lookback_days,
            },
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })

        return {
            "status": "SUCCESS",
            "summary": report.get("summary", {}),
            "playbooks": report.get("playbooks", []),
            "widget": {
                "type": "playbook_health_card",
                "title": "SOAR Playbook Resilience & Decay Report",
                "summary": report.get("summary", {}),
                "playbooks": report.get("playbooks", []),
            },
        }

    def get_playbook_decay_report(self, workflow_identifier: str) -> Dict[str, Any]:
        """Retrieves a persistent playbook analysis report from Evidence Fabric."""
        if not self.evidence_store:
            return {"status": "ERROR", "message": "EvidenceFabricStore not configured"}
        doc = self.evidence_store.get_playbook_analysis(workflow_identifier)
        if not doc:
            return {"status": "NOT_FOUND", "message": f"No audit report found for playbook {workflow_identifier}"}
        return {"status": "SUCCESS", "report": doc}

    def list_playbook_reports(self, limit: int = 100) -> Dict[str, Any]:
        """Lists recent playbook decay reports from Evidence Fabric."""
        if not self.evidence_store:
            return {"status": "ERROR", "message": "EvidenceFabricStore not configured"}
        reports = self.evidence_store.list_playbook_analyses(limit=limit)
        return {"status": "SUCCESS", "count": len(reports), "reports": reports}
