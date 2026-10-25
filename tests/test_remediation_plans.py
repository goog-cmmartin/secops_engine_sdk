"""Tests for Google SecOps AI-Driven Agentic Response / Remediation Plans."""

import json
import os
import unittest

from engine.domain import RemediationAction, RemediationPlan, RemediationPlanBatch
from engine.facade import SecOpsEngine
from engine.workflows.remediation_plan import parse_remediation_action, parse_remediation_plan
from tests.test_helpers import get_live_engine


class TestRemediationPlanContracts(unittest.TestCase):
    """Verifies registry capabilities, taxonomy axes, and contract rules."""

    def setUp(self):
        self.engine = SecOpsEngine()
        self.reg = self.engine.registry

    def test_capabilities_registered(self):
        cap_list = self.reg.get("case.remediation_plan.list")
        self.assertIsNotNone(cap_list)
        self.assertEqual(cap_list.category, "case")
        self.assertEqual(cap_list.kind, "query")
        self.assertEqual(cap_list.cardinality, "unbounded")
        self.assertTrue(cap_list.agent.get("require_filter_for_unbounded_query"))

        cap_get = self.reg.get("case.remediation_plan.get")
        self.assertIsNotNone(cap_get)
        self.assertEqual(cap_get.category, "case")
        self.assertEqual(cap_get.kind, "query")
        self.assertEqual(cap_get.cardinality, "single")

        cap_resp = self.reg.get("case.agentic_response_plan.get")
        self.assertIsNotNone(cap_resp)
        self.assertEqual(cap_resp.category, "case")
        self.assertEqual(cap_resp.kind, "workflow")
        self.assertTrue(cap_resp.composed)
        self.assertIn("case.remediation_plan.list", cap_resp.uses)
        self.assertIn("case.remediation_plan.get", cap_resp.uses)


class TestRemediationPlanParsing(unittest.TestCase):
    """Verifies domain parsing against live captured raw evidence payloads."""

    def test_parse_live_evidence_list_and_get(self):
        evidence_dir = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            "evidence",
            "case",
        )
        list_evidence_file = os.path.join(evidence_dir, "remediation_plan_list", "raw.json")
        get_evidence_file = os.path.join(evidence_dir, "remediation_plan_get", "raw.json")

        self.assertTrue(os.path.exists(list_evidence_file), f"Missing {list_evidence_file}")
        with open(list_evidence_file, "r", encoding="utf-8") as f:
            list_data = json.load(f)

        raw_plans = list_data.get("remediationPlans", [])
        self.assertGreater(len(raw_plans), 0)
        parsed_plan = parse_remediation_plan(raw_plans[0])
        self.assertEqual(parsed_plan.plan_id, "45")
        self.assertEqual(parsed_plan.case_id, 108188)
        self.assertEqual(parsed_plan.alert_name, "SUSPICIOUS BASH NETWORKING")
        self.assertEqual(parsed_plan.state, "REMEDIATION_PLAN_STATE_SUGGESTED")
        self.assertEqual(parsed_plan.agent_classified_use_case, "Active Malicious Process Running in Memory")

        self.assertTrue(os.path.exists(get_evidence_file), f"Missing {get_evidence_file}")
        with open(get_evidence_file, "r", encoding="utf-8") as f:
            get_data = json.load(f)

        detailed_plan = parse_remediation_plan(get_data)
        self.assertEqual(detailed_plan.plan_id, "45")
        self.assertEqual(len(detailed_plan.actions), 1)
        action = detailed_plan.actions[0]
        self.assertIsInstance(action, RemediationAction)
        self.assertEqual(action.action_id, "107")
        self.assertEqual(action.display_name, "Isolate Endpoint")
        self.assertEqual(action.integration_id, "PaloAltoCortexXDR")
        self.assertEqual(action.type, "ACTION_ORIGIN_TYPE_EXISTING")


class TestRemediationPlanLive(unittest.TestCase):
    """Executes live queries against Google SecOps for remediation plans."""

    def setUp(self):
        self.engine = get_live_engine()

    def test_live_list_and_get_remediation_plans(self):
        # Case 108188 has an existing remediation plan in the target tenant
        batch = self.engine.list_remediation_plans(case_id=108188)
        self.assertIsInstance(batch, RemediationPlanBatch)
        self.assertGreater(len(batch.plans), 0)
        top_plan = batch.plans[0]
        self.assertEqual(top_plan.case_id, 108188)

        # Retrieve detailed plan
        detailed = self.engine.get_remediation_plan(top_plan.plan_id)
        self.assertIsInstance(detailed, RemediationPlan)
        self.assertEqual(detailed.plan_id, top_plan.plan_id)
        self.assertGreater(len(detailed.actions), 0)

        # Composed agentic response plan resolution
        resolved = self.engine.get_agentic_response_plan(case_id=108188)
        self.assertIsNotNone(resolved)
        self.assertEqual(resolved.plan_id, top_plan.plan_id)
        self.assertGreater(len(resolved.actions), 0)


if __name__ == "__main__":
    unittest.main()
