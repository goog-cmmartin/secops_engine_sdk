"""Acceptance and unit tests for SOAR Case Orchestrated Triage Workflow (`case.orchestrate_triage` & `case.triage`)."""

import ast
import os
import unittest
from engine.domain import (
    CasePrecedentSummary,
    CasePriority,
    CaseStatus,
    CaseTriageAssessment,
    CaseTriageBatch,
    EntityPrecedentItem,
    TriageVerdict,
)
from engine.facade import SecOpsEngine
from engine.taxonomy import derive_kind, derive_domain, derive_cardinality
from engine.workflows.case_triage import (
    OrchestrateCaseTriageWorkflow,
    _derive_verdict_and_recommendations,
    _eval_highest_alert_priority,
    _generate_agent_prompt,
)
from tests.test_helpers import get_live_adapter, get_live_engine


class TestCaseTriageWorkflow(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.adapter = get_live_adapter()
        cls.engine = get_live_engine(adapter=cls.adapter)

    def test_case_triage_001_orchestrate_triage_live(self):
        """Validates batched retrieval and triage orchestration against live SecOps tenant."""
        batch = self.engine.orchestrate_case_triage(limit=3, open_only=False)

        self.assertIsInstance(batch, CaseTriageBatch)
        self.assertGreaterEqual(batch.total_cases_analyzed, 0)
        self.assertIn("workflow", batch.provenance)
        self.assertEqual(batch.provenance["workflow"], "case.orchestrate_triage")

        if batch.results:
            first = batch.results[0]
            self.assertIsInstance(first, CaseTriageAssessment)
            self.assertTrue(len(first.case_id) > 0)
            self.assertTrue(len(first.title) > 0)
            self.assertIsInstance(first.triage_verdict, TriageVerdict)
            self.assertTrue(len(first.suggested_agent_prompt) > 0)
            self.assertIn("You are a SecOps Tier-2 SOC Analyst", first.suggested_agent_prompt)
            self.assertIn(first.case_id, first.suggested_agent_prompt)

    def test_case_triage_002_triage_verdict_heuristics(self):
        """Validates deterministic scoring and prompt synthesis heuristics."""
        # Critical priority with suspicious entities -> CRITICAL_ESCALATION
        verdict, summary, recs, stage = _derive_verdict_and_recommendations(
            status=CaseStatus.OPEN,
            priority=CasePriority.CRITICAL,
            highest_alert_priority="CRITICAL",
            suspicious_entities=["192.168.1.100"],
            is_closed=False,
            alert_count=2,
        )
        self.assertEqual(verdict, TriageVerdict.CRITICAL_ESCALATION)
        self.assertEqual(stage, "Incident")
        self.assertTrue(any("Immediate host/identity containment" in r for r in recs))

        # Closed case -> CLOSED_NO_ACTION
        verdict, summary, recs, stage = _derive_verdict_and_recommendations(
            status=CaseStatus.CLOSED,
            priority=CasePriority.HIGH,
            highest_alert_priority="HIGH",
            suspicious_entities=[],
            is_closed=True,
            alert_count=1,
        )
        self.assertEqual(verdict, TriageVerdict.CLOSED_NO_ACTION)
        self.assertIsNone(stage)

        # Suspicious entities on standard case -> CONTAINMENT_REQUIRED
        verdict, summary, recs, stage = _derive_verdict_and_recommendations(
            status=CaseStatus.OPEN,
            priority=CasePriority.MEDIUM,
            highest_alert_priority="MEDIUM",
            suspicious_entities=["malicious_user@corp.com"],
            is_closed=False,
            alert_count=1,
        )
        self.assertEqual(verdict, TriageVerdict.CONTAINMENT_REQUIRED)
        self.assertEqual(stage, "Investigation")

        # Novel detection heuristic
        novel_precedents = CasePrecedentSummary(
            target_case_id="123",
            title_query="Unique Attack Vector",
            title_prior_case_count=0,
            title_prior_case_ids=[],
            title_closed_count=0,
            title_incident_count=0,
            entity_precedents=[],
            total_entity_matches=0,
            is_novel=True,
            is_repeat=False,
            repeat_case_ids=[],
            precedent_notes=["Novel detection"],
        )
        verdict, summary, recs, stage = _derive_verdict_and_recommendations(
            status=CaseStatus.OPEN,
            priority=CasePriority.MEDIUM,
            highest_alert_priority="MEDIUM",
            suspicious_entities=[],
            is_closed=False,
            alert_count=1,
            precedent_summary=novel_precedents,
        )
        self.assertEqual(verdict, TriageVerdict.NOVEL_DETECTION)
        self.assertEqual(stage, "Investigation")

        # Active campaign repeat correlation heuristic
        repeat_precedents = CasePrecedentSummary(
            target_case_id="123",
            title_query="Lateral Movement",
            title_prior_case_count=3,
            title_prior_case_ids=["100", "101", "102"],
            title_closed_count=0,
            title_incident_count=2,
            entity_precedents=[
                EntityPrecedentItem(
                    entity_identifier="bad_host",
                    entity_type="HOSTNAME",
                    prior_case_count=3,
                    recent_case_ids=["100", "101", "102"],
                    active_incident_count=2,
                    is_frequent=True,
                )
            ],
            total_entity_matches=3,
            is_novel=False,
            is_repeat=True,
            repeat_case_ids=["102", "101", "100"],
            precedent_notes=["Entity 'bad_host' in 3 prior cases"],
        )
        verdict, summary, recs, stage = _derive_verdict_and_recommendations(
            status=CaseStatus.OPEN,
            priority=CasePriority.MEDIUM,
            highest_alert_priority="MEDIUM",
            suspicious_entities=[],
            is_closed=False,
            alert_count=1,
            precedent_summary=repeat_precedents,
        )
        self.assertEqual(verdict, TriageVerdict.REPEAT_ACTIVE_CAMPAIGN)
        self.assertEqual(stage, "Investigation")

    def test_case_triage_003_prompt_generation(self):
        """Validates Antigravity subagent prompt generator."""
        prompt = _generate_agent_prompt(
            case_id="104185",
            title="Suspicious Beaconing",
            priority="CRITICAL",
            status="OPEN",
            stage="Triage",
            environment="Production",
            assignee="analyst@corp.com",
            highest_alert_priority="CRITICAL",
            alert_count=3,
            alert_names=["Alert 1", "Alert 2", "Alert 3"],
            suspicious_entities=["10.0.0.5"],
            latest_comment="Under investigation",
            verdict=TriageVerdict.CRITICAL_ESCALATION,
        )
        self.assertIn("Case #104185", prompt)
        self.assertIn("Suspicious Beaconing", prompt)
        self.assertIn("CRITICAL_ESCALATION", prompt)
        self.assertIn("10.0.0.5", prompt)
        self.assertIn("MISSION OBJECTIVES", prompt)

    def test_case_triage_004_capability_contract_and_taxonomy(self):
        """Validates registration, metadata, and DAG taxonomy for case.orchestrate_triage & case.triage."""
        cap = self.engine.registry.get("case.orchestrate_triage")
        self.assertIsNotNone(cap)
        self.assertEqual(cap.capability_id, "case.orchestrate_triage")
        self.assertEqual(cap.category, "case")
        self.assertTrue(cap.composed)
        self.assertEqual(cap.uses, ("case.search", "case.investigate", "case.get_summary"))
        self.assertEqual(cap.mcp_tool_name, "orchestrate_case_triage")
        self.assertTrue(os.path.exists(cap.evidence_path))

        self.assertEqual(cap.kind, "workflow")
        self.assertEqual(cap.domain, "case")
        self.assertIsNone(cap.cardinality)

        cap_single = self.engine.registry.get("case.triage")
        self.assertIsNotNone(cap_single)
        self.assertEqual(cap_single.capability_id, "case.triage")
        self.assertEqual(cap_single.category, "case")
        self.assertTrue(cap_single.composed)
        self.assertEqual(cap_single.uses, ("case.investigate", "case.get_summary", "case.search"))
        self.assertEqual(cap_single.mcp_tool_name, "triage_case")

    def test_case_triage_005_anti_mock_compliance(self):
        """Audits case_triage.py to guarantee strict zero-mock compliance."""
        module_path = os.path.join(
            os.path.dirname(os.path.dirname(__file__)),
            "engine",
            "workflows",
            "case_triage.py",
        )
        with open(module_path, "r", encoding="utf-8") as f:
            content = f.read()

        banned_terms = ["mock", "dummy", "fake", "fixture", "sample_data", "test_data"]
        for term in banned_terms:
            self.assertNotIn(
                term,
                content.lower(),
                f"Banned mock term '{term}' discovered in production workflow {module_path}",
            )

        # Parse AST to ensure valid Python syntax
        ast.parse(content)

    def test_case_triage_006_single_case_triage_live(self):
        """Validates single case triage against live SecOps tenant."""
        # Find a real case id from search
        search_res = self.engine.search_cases(page_size=1)
        if not search_res.results:
            self.skipTest("No cases available in live tenant.")

        target_case_id = search_res.results[0].case_id
        assessment = self.engine.triage_case(
            case_id=target_case_id,
            fetch_summary=False,  # Keep unit test fast
            search_precedents=True,
            apply_stage_update=False,
            post_comment=False,
        )
        self.assertIsInstance(assessment, CaseTriageAssessment)
        self.assertEqual(assessment.case_id, target_case_id)
        self.assertIsInstance(assessment.triage_verdict, TriageVerdict)
        self.assertIsNotNone(assessment.precedent_summary)
        self.assertTrue(assessment.is_novel or assessment.is_repeat)
        self.assertIsNotNone(assessment.timeline)
        self.assertGreaterEqual(assessment.timeline.event_count, 0)
        self.assertIsInstance(assessment.alert_playbook_statuses, list)

    def test_case_triage_007_playbook_recommendation_heuristics(self):
        """Validates playbook status surfacing in analyst recommendations."""
        from engine.domain import AlertPlaybookStatus

        pb_failed = [
            AlertPlaybookStatus(
                case_id="123",
                alert_id="a1",
                alert_display_name="Brute Force Alert",
                attached_playbook_name="User Lockout Playbook",
                status="FAILED",
                run_count=1,
            )
        ]
        verdict, summary, recs, stage = _derive_verdict_and_recommendations(
            status=CaseStatus.OPEN,
            priority=CasePriority.MEDIUM,
            highest_alert_priority="MEDIUM",
            suspicious_entities=[],
            is_closed=False,
            alert_count=1,
            alert_playbook_statuses=pb_failed,
        )
        self.assertTrue(any("[Playbook Failed]" in r and "User Lockout Playbook" in r for r in recs))

        pb_running = [
            AlertPlaybookStatus(
                case_id="123",
                alert_id="a1",
                alert_display_name="Brute Force Alert",
                attached_playbook_name="User Lockout Playbook",
                status="RUNNING",
                run_count=1,
            )
        ]
        verdict, summary, recs, stage = _derive_verdict_and_recommendations(
            status=CaseStatus.OPEN,
            priority=CasePriority.MEDIUM,
            highest_alert_priority="MEDIUM",
            suspicious_entities=[],
            is_closed=False,
            alert_count=1,
            alert_playbook_statuses=pb_running,
        )
        self.assertTrue(any("[Playbook In-Progress]" in r for r in recs))

        pb_none = [
            AlertPlaybookStatus(
                case_id="123",
                alert_id="a1",
                alert_display_name="Brute Force Alert",
                attached_playbook_name=None,
                status=None,
                run_count=0,
            )
        ]
        verdict, summary, recs, stage = _derive_verdict_and_recommendations(
            status=CaseStatus.OPEN,
            priority=CasePriority.MEDIUM,
            highest_alert_priority="MEDIUM",
            suspicious_entities=[],
            is_closed=False,
            alert_count=1,
            alert_playbook_statuses=pb_none,
        )
        self.assertTrue(any("[Playbook Missing]" in r for r in recs))

    def test_case_triage_008_timeline_generation_live(self):
        """Validates case timeline retrieval and chronological ordering against live SecOps tenant."""
        search_res = self.engine.search_cases(page_size=1)
        if not search_res.results:
            self.skipTest("No cases available in live tenant.")

        target_case_id = search_res.results[0].case_id
        timeline = self.engine.get_case_timeline(case_id=target_case_id)
        from engine.domain import CaseTimeline
        self.assertIsInstance(timeline, CaseTimeline)
        self.assertEqual(timeline.case_id, target_case_id)
        self.assertGreaterEqual(timeline.event_count, 1)

        # Verify chronological order
        timestamps = [e.timestamp for e in timeline.events if e.timestamp is not None]
        for i in range(len(timestamps) - 1):
            self.assertLessEqual(timestamps[i], timestamps[i + 1])

    def test_case_triage_009_timeline_capability_contract(self):
        """Validates capability registration for case.timeline."""
        cap = self.engine.registry.get("case.timeline")
        self.assertIsNotNone(cap)
        self.assertEqual(cap.capability_id, "case.timeline")
        self.assertEqual(cap.category, "case")
        self.assertTrue(cap.composed)
        self.assertEqual(cap.uses, ("case.investigate",))
        self.assertEqual(cap.mcp_tool_name, "get_case_timeline")

