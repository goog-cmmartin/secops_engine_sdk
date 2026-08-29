import unittest
from engine.facade import SecOpsEngine
from tests.test_helpers import get_live_engine
from runbooks.incident_response.autonomous_case_ai_triage import (
    run_autonomous_case_ai_triage,
    AutonomousTriageResult,
)
from runbooks.operations.tenant_settings_audit import (
    generate_tenant_settings_report,
)
from runbooks.operations.data_table_inventory import (
    generate_data_table_inventory_report,
)
from runbooks.operations.yara_l_rules_audit import (
    generate_yara_l_rules_audit_report,
)
from runbooks.operations.soar_playbook_inventory import (
    generate_playbook_inventory_report,
)


class TestAutonomousRunbooks(unittest.TestCase):
    """Test suite for autonomous incident response, threat hunting, and operations runbooks."""

    @classmethod
    def setUpClass(cls):
        cls.engine = get_live_engine()

    def test_autonomous_case_ai_triage_dry_run(self):
        """Validates that autonomous case AI triage executes end-to-end cleanly in dry-run mode."""
        target_case_id = "104655"
        res: AutonomousTriageResult = run_autonomous_case_ai_triage(
            case_id=target_case_id,
            hunt_lookback_days=7,
            hunt_receive_limit=10,
            summary_timeout_sec=90.0,
            dry_run=True,
            engine=self.engine,
        )

        self.assertEqual(res.case_id, target_case_id)
        self.assertTrue(res.dry_run)
        self.assertIn(res.summary_state, ("SUCCESSFUL", "IN_PROGRESS", "PENDING_START"))
        if res.summary_state == "SUCCESSFUL":
            self.assertTrue(bool(res.summary_text))
            self.assertIsInstance(res.extracted_ips, list)
            self.assertIsInstance(res.extracted_users, list)
            self.assertIsInstance(res.hunt_results, dict)
            self.assertFalse(res.incident_marked)  # Dry-run must not mutate
            self.assertFalse(res.alert_escalated)
            self.assertFalse(res.comment_posted)
            self.assertTrue(bool(res.audit_comment))

    def test_tenant_settings_audit_report(self):
        """Validates that tenant settings audit report generates all sections."""
        report = generate_tenant_settings_report(engine=self.engine)
        self.assertIsInstance(report, dict)
        expected_sections = [
            "instance",
            "gemini_ai",
            "ueba_risk",
            "governance",
            "soar_settings",
            "topography",
        ]
        for sec in expected_sections:
            self.assertIn(sec, report)
        self.assertTrue(bool(report["instance"]["id"]))
        self.assertIn("rbac_scopes", report["governance"])
        self.assertIn("environments", report["topography"])

    def test_data_table_inventory_report(self):
        """Validates that data table inventory report compiles schemas and metadata."""
        report = generate_data_table_inventory_report(engine=self.engine, page_size=20)
        self.assertIsInstance(report, dict)
        self.assertEqual(report.get("report_type"), "chronicle_siem_data_table_inventory")
        self.assertIsInstance(report.get("total_tables"), int)
        self.assertIsInstance(report.get("data_tables"), list)
        if report.get("data_tables"):
            first_dt = report["data_tables"][0]
            self.assertTrue(bool(first_dt["table_id"]))
            self.assertTrue(bool(first_dt["display_name"]))
            self.assertIsInstance(first_dt["columns"], list)
            if first_dt["columns"]:
                col = first_dt["columns"][0]
                self.assertIn("column_name", col)
                self.assertIn("data_type", col)
                self.assertIn("is_key_column", col)

    def test_yara_l_rules_audit_report(self):
        """Validates that YARA-L rules audit compiles rule status, deployment, and errors."""
        report = generate_yara_l_rules_audit_report(engine=self.engine, page_size=10)
        self.assertIsInstance(report, dict)
        self.assertEqual(report.get("report_type"), "chronicle_siem_yara_l_rules_audit")
        self.assertIn("summary", report)
        self.assertIn("rules", report)
        summary = report["summary"]
        self.assertIsInstance(summary.get("total_rules"), int)
        self.assertIsInstance(summary.get("enabled_rules"), int)
        self.assertIsInstance(summary.get("healthy_rules"), int)
        if report.get("rules"):
            rule = report["rules"][0]
            self.assertTrue(bool(rule["rule_id"]))
            self.assertTrue(bool(rule["display_name"]))
            self.assertIn("health_status", rule)
            self.assertIn("enabled", rule)
            self.assertIn("alerting", rule)
            self.assertIn("run_frequency", rule)
            self.assertIn("runtime_errors", rule)

    def test_soar_playbook_inventory_report(self):
        """Validates that SOAR playbook inventory compiles playbooks, blocks, priorities, and environments."""
        report = generate_playbook_inventory_report(engine=self.engine, limit=20)
        self.assertIsInstance(report, dict)
        self.assertEqual(report.get("report_type"), "soar_playbook_and_block_inventory")
        self.assertIn("summary", report)
        self.assertIn("standard_playbooks", report)
        self.assertIn("reusable_blocks", report)
        summary = report["summary"]
        self.assertIsInstance(summary.get("total_workflows"), int)
        self.assertIsInstance(summary.get("standard_playbooks"), int)
        self.assertIsInstance(summary.get("reusable_blocks"), int)
        self.assertIsInstance(summary.get("enabled_count"), int)
        self.assertIsInstance(summary.get("disabled_count"), int)
        self.assertIsInstance(summary.get("priority_breakdown"), dict)
        self.assertIsInstance(summary.get("environment_distribution"), dict)


if __name__ == "__main__":
    unittest.main()
