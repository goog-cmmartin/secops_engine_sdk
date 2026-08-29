"""Tests for Chronicle SIEM Custom YARA-L Detection Rules workflows and capabilities."""

import unittest
from engine.facade import SecOpsEngine
from engine.domain import (
    RuleDetail,
    RuleDeployment,
    RuleExecutionErrorListResult,
    RuleListResult,
    RuleRevisionListResult,
    RuleSummary,
    RuleValidationResult,
)
from tests.test_helpers import get_live_engine


class TestDetectionRulesWorkflows(unittest.TestCase):
    """Test suite for Chronicle SIEM Custom Detection Rules workflows."""

    @classmethod
    def setUpClass(cls):
        cls.engine = get_live_engine()

    def test_list_rules(self):
        """Validates listing Chronicle SIEM custom detection rules."""
        res = self.engine.list_rules(page_size=10)
        self.assertIsInstance(res, RuleListResult)
        self.assertIsInstance(res.rules, list)
        if res.rules:
            r = res.rules[0]
            self.assertIsInstance(r, RuleSummary)
            self.assertTrue(bool(r.name))
            self.assertTrue(bool(r.rule_id))
            self.assertTrue(bool(r.display_name))
            self.assertIsInstance(r.allowed_run_frequencies, list)

    def test_get_rule(self):
        """Validates retrieving full details and YARA-L code of a detection rule."""
        res = self.engine.list_rules(page_size=5)
        if not res.rules:
            self.skipTest("No detection rules available in tenant to test get_rule.")

        target_rule_id = res.rules[0].rule_id
        rule_detail = self.engine.get_rule(target_rule_id)
        self.assertIsInstance(rule_detail, RuleDetail)
        self.assertEqual(rule_detail.rule_id, target_rule_id)
        self.assertTrue(bool(rule_detail.display_name))
        self.assertTrue(bool(rule_detail.text))
        self.assertEqual(rule_detail.yara_l_code, rule_detail.text)
        self.assertEqual(rule_detail.compilation_state, "SUCCEEDED")

    def test_verify_rule_syntax_valid(self):
        """Validates compiler verification of valid YARA-L 2.0 rule syntax."""
        valid_yaral = """rule test_valid_rule_syntax {
  meta:
    author = "SecOps Engine"
    description = "Test rule for syntax verification"
    severity = "Medium"
  events:
    $e.metadata.event_type = "USER_LOGIN"
  condition:
    $e
}"""
        res = self.engine.verify_rule(valid_yaral)
        self.assertIsInstance(res, RuleValidationResult)
        self.assertTrue(res.success)
        self.assertEqual(len(res.diagnostics), 0)

    def test_verify_rule_syntax_invalid(self):
        """Validates compiler diagnostics on invalid YARA-L rule syntax."""
        invalid_yaral = """rule test_invalid_rule_syntax {
  events:
    $e.metadata.event_type = "USER_LOGIN"
  condition:
    non_existent_event_variable
}"""
        res = self.engine.verify_rule(invalid_yaral)
        self.assertIsInstance(res, RuleValidationResult)
        self.assertFalse(res.success)
        self.assertGreater(len(res.diagnostics), 0)
        self.assertTrue(any("ERROR" in d.severity.upper() for d in res.diagnostics))

    def test_rule_deployment(self):
        """Validates retrieving deployment and frequency status for a rule."""
        res = self.engine.list_rules(page_size=5)
        if not res.rules:
            self.skipTest("No detection rules available in tenant to test get_rule_deployment.")

        target_rule_id = res.rules[0].rule_id
        dep = self.engine.get_rule_deployment(target_rule_id)
        self.assertIsInstance(dep, RuleDeployment)
        self.assertTrue(bool(dep.name))
        self.assertIn(dep.run_frequency, ["LIVE", "HOURLY", "DAILY", "RUN_FREQUENCY_UNSPECIFIED"])

    def test_rule_revisions(self):
        """Validates listing revisions and version history for a rule."""
        res = self.engine.list_rules(page_size=5)
        if not res.rules:
            self.skipTest("No detection rules available in tenant to test list_rule_revisions.")

        target_rule_id = res.rules[0].rule_id
        rev_res = self.engine.list_rule_revisions(target_rule_id, page_size=10)
        self.assertIsInstance(rev_res, RuleRevisionListResult)
        self.assertIsInstance(rev_res.revisions, list)

    def test_rule_execution_errors(self):
        """Validates listing rule execution/runtime errors."""
        errors_res = self.engine.list_rule_errors(page_size=5)
        self.assertIsInstance(errors_res, RuleExecutionErrorListResult)
        self.assertIsInstance(errors_res.errors, list)

    def test_rule_capabilities_registered(self):
        """Validates registration and taxonomy of all 10 rule capabilities."""
        capabilities = {c.capability_id: c for c in self.engine.list_capabilities(category="rule")}
        expected_ids = [
            "rule.list",
            "rule.get",
            "rule.verify",
            "rule.create",
            "rule.patch",
            "rule.delete",
            "rule.revisions",
            "rule.deployment.get",
            "rule.deployment.update",
            "rule.errors",
        ]
        for cap_id in expected_ids:
            self.assertIn(cap_id, capabilities, f"Capability {cap_id} missing from registry")
            self.assertEqual(capabilities[cap_id].category, "rule")


if __name__ == "__main__":
    unittest.main()
