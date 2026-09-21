"""Unit and behavioral tests for Rule Decay calculation and workflows."""

import unittest
from engine.workflows.rule_decay import (
    calculate_decay_score,
    extract_udm_fields_from_yaral,
    QueryRuleDetectionCountsWorkflow,
    AuditUdmFieldPopulationWorkflow,
)


class TestRuleDecayWorkflow(unittest.TestCase):
    """Verifies decay scoring logic, field extraction, and workflow definitions."""

    def test_calculate_decay_score_broken_live(self):
        rule = {
            "id": "ru_12345",
            "name": "Test Broken Live Rule",
            "live_mode_enabled": True,
            "revision_create_time": "2024-01-01T00:00:00Z",
        }
        score, flags, recommendation, days_stale = calculate_decay_score(
            rule_detail=rule,
            detection_telemetry_90d={"count": 0},
            syntax_verified=False,
            compiler_diagnostics=["Syntax error at line 12"],
        )
        self.assertIn("BROKEN_COMPILATION", flags)
        self.assertIn("SILENT", flags)
        self.assertIn("STALE", flags)
        self.assertEqual(recommendation, "REFACTOR")
        # 40 (broken) + 30 (live) + 30 (silent) + 30 (stale) = 130 -> clamped to 100
        self.assertEqual(score, 100)
        self.assertGreater(days_stale, 90)

    def test_calculate_decay_score_healthy(self):
        rule = {
            "id": "ru_healthy",
            "name": "Active Firing Rule",
            "live_mode_enabled": True,
            "revision_create_time": "2026-09-01T00:00:00Z",
        }
        score, flags, recommendation, days_stale = calculate_decay_score(
            rule_detail=rule,
            detection_telemetry_90d={"count": 520, "last_seen": "2026-09-18T10:00:00Z"},
            syntax_verified=True,
            compiler_diagnostics=[],
        )
        self.assertIn("HEALTHY", flags)
        self.assertEqual(recommendation, "KEEP_ACTIVE")
        # 5 (healthy) + 30 (live) = 35
        self.assertEqual(score, 35)

    def test_extract_udm_fields_from_yaral(self):
        yaral = """
rule suspicious_process_execution {
  meta:
    author = "SecOps SME"
    description = "Detects cmd execution"
  events:
    $e.metadata.event_type = "PROCESS_LAUNCH"
    $e.principal.process.file.full_path = /.*cmd\\.exe/
    $e.target.process.command_line = /.*whoami.*/
    $e.target.user.userid != ""
  condition:
    $e
}
"""
        fields = extract_udm_fields_from_yaral(yaral)
        self.assertIn("metadata.event_type", fields)
        self.assertIn("principal.process.file.full_path", fields)
        self.assertIn("target.process.command_line", fields)
        self.assertIn("target.user.userid", fields)
        self.assertNotIn("e.principal", fields)
        self.assertNotIn("author", fields)

    def test_udm_population_query_format(self):
        wf = AuditUdmFieldPopulationWorkflow(adapter=None)
        q = wf._build_field_population_query("principal.user.userid", vendor_product="okta", is_array=False)
        self.assertIn('$count = count_distinct($e.metadata.id)', q)
        self.assertIn('principal.user.userid != ""', q)
        self.assertIn('metadata.product_name = "okta"', q)

    def test_udm_population_array_field_query(self):
        wf = AuditUdmFieldPopulationWorkflow(adapter=None)
        q = wf._build_field_population_query("security_result.category", vendor_product=None, is_array=True)
        self.assertIn('security_result.category = /.+/', q)


if __name__ == "__main__":
    unittest.main()
