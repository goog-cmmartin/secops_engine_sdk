"""Acceptance and unit tests for Autonomous AI Case Investigation (`case.ai_investigate`)."""

import os
import unittest
from engine.domain import (
    CaseAiInvestigationResult,
)
from engine.facade import SecOpsEngine
from engine.workflows.case_ai_investigation import (
    InvestigateCaseWithAIWorkflow,
    extract_indicators,
)
from tests.test_helpers import get_live_adapter, get_live_engine


class TestCaseAiInvestigationWorkflow(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.adapter = get_live_adapter()
        cls.engine = get_live_engine(adapter=cls.adapter)

    def test_extract_indicators_heuristic(self):
        """Validates indicator extraction across IP addresses, user emails, and entity bracket tags."""
        sample_text = (
            "Detected suspicious activity from [[[10.0.4.15|ADDRESS|12345]]] targeting user "
            "[[[victim_user@corp.example.com|USERUNIQNAME|67890]]]. Additional inbound connections "
            "from 198.51.100.24 and 2001:db8::1. Excluded broadcast 0.0.0.0 and 255.255.255.255. "
            "File hash was 44d88612fea8a8f36de82e1278abb02f."
        )
        ips, users, hashes = extract_indicators(sample_text)

        self.assertIn("10.0.4.15", ips)
        self.assertIn("198.51.100.24", ips)
        self.assertIn("2001:db8::1", ips)
        self.assertNotIn("0.0.0.0", ips)
        self.assertNotIn("255.255.255.255", ips)

        self.assertIn("victim_user@corp.example.com", users)
        self.assertIn("44d88612fea8a8f36de82e1278abb02f", hashes)

    def test_capability_contract_and_taxonomy(self):
        """Validates registry entry, DAG dependencies, and taxonomy derivation for case.ai_investigate."""
        cap = self.engine.registry.get("case.ai_investigate")
        self.assertIsNotNone(cap)
        self.assertEqual(cap.capability_id, "case.ai_investigate")
        self.assertEqual(cap.name, "Autonomous AI Case Investigation")
        self.assertEqual(cap.category, "case")
        self.assertEqual(cap.mcp_tool_name, "ai_investigate_case")
        self.assertTrue(cap.composed)
        self.assertEqual(
            set(cap.uses),
            {"case.investigate", "case.get_summary", "search.udm", "case.comment"},
        )
        self.assertEqual(cap.kind, "workflow")
        self.assertEqual(cap.domain, "case")

    def test_live_ai_investigate_dry_run(self):
        """Validates autonomous AI investigation against live SecOps tenant in dry-run mode."""
        target_case_id = "104655"
        res = self.engine.ai_investigate_case(
            case_id=target_case_id,
            hunt_lookback_days=7,
            hunt_receive_limit=10,
            summary_timeout_sec=90.0,
            escalate_incident=True,
            escalate_alert_priority="PRIORITY_CRITICAL",
            post_comment=True,
            dry_run=True,
        )

        self.assertIsInstance(res, CaseAiInvestigationResult)
        self.assertEqual(res.case_id, target_case_id)
        self.assertTrue(res.dry_run)
        self.assertIn(res.summary_state, ("SUCCESSFUL", "IN_PROGRESS", "PENDING_START"))
        self.assertIsInstance(res.extracted_ips, list)
        self.assertIsInstance(res.extracted_users, list)
        self.assertIsInstance(res.extracted_hashes, list)
        self.assertIsInstance(res.hunt_results, dict)
        # Mutations must be skipped in dry-run
        self.assertFalse(res.incident_marked)
        self.assertFalse(res.alert_escalated)
        self.assertFalse(res.comment_posted)
        self.assertTrue(bool(res.audit_comment))
        self.assertIn("workflow", res.provenance)
        self.assertEqual(res.provenance["workflow"], "case.ai_investigate")

    def test_anti_mock_compliance_production_code(self):
        """CI invariant audit: ensures case_ai_investigation.py has zero banned terms."""
        path = os.path.join(
            os.path.dirname(__file__),
            "..",
            "engine",
            "workflows",
            "case_ai_investigation.py",
        )
        with open(path, "r", encoding="utf-8") as f:
            code = f.read()

        banned = [
            "mock", "Mock", "MOCK",
            "dummy", "Dummy",
            "fake", "Fake",
            "sample_data", "sampleData",
            "placeholder_data", "placeholderData",
            "test_data", "testData",
        ]
        for term in banned:
            self.assertNotIn(term, code, f"Banned identifier '{term}' found in {path}")


if __name__ == "__main__":
    unittest.main()
