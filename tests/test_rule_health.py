"""Unit tests for AuditRuleHealthWorkflow and Rule Health models."""

import unittest
from datetime import datetime, timezone
from typing import Any, Dict, List
from unittest.mock import MagicMock

from engine.domain import (
    RuleHealthFinding,
    RuleHealthReport,
    RuleHealthStatus,
    RuleSummary,
    RuleExecutionError,
    DashboardDetail,
    DashboardChart,
    DashboardQueryResult,
)
from engine.facade import SecOpsEngine
from engine.workflows.rule_health import (
    AuditRuleHealthWorkflow,
    RULE_DETECTIONS_OVERVIEW_DASHBOARD_ID,
    RULE_OBSERVABILITY_DASHBOARD_ID,
)


class TestRuleHealthWorkflow(unittest.TestCase):
    """Test suite for AuditRuleHealthWorkflow."""

    def setUp(self):
        self.mock_adapter = MagicMock()
        self.workflow = AuditRuleHealthWorkflow(adapter=self.mock_adapter)

    def test_capability_registration(self):
        """Verifies rule.audit_health capability is registered with correct taxonomy and DAG edges."""
        engine = SecOpsEngine()
        cap = engine.registry.get("rule.audit_health")
        self.assertIsNotNone(cap)
        self.assertEqual(cap.category, "rule")
        self.assertEqual(cap.domain, "rule")
        self.assertEqual(cap.kind, "workflow")
        self.assertTrue(cap.composed)
        self.assertIn("rule.list", cap.uses)
        self.assertIn("rule.errors", cap.uses)
        self.assertIn("dashboard.execute_query", cap.uses)

    def test_healthy_rule_evaluation(self):
        # Setup mock rules
        self.mock_adapter.list_rules.return_value = {
            "rules": [
                {
                    "name": "projects/123/locations/us/instances/abc/rules/ru_123",
                    "displayName": "Suspicious Login Detection",
                    "severity": "HIGH",
                    "runFrequency": "LIVE",
                    "enabled": True,
                    "alerting": True,
                }
            ]
        }
        # No errors
        self.mock_adapter.list_rule_execution_errors.return_value = {"ruleExecutionErrors": []}

        # Mock dashboard calls
        self.mock_adapter.get_native_dashboard.return_value = {"name": "test_dash", "definition": {"charts": []}}
        self.mock_adapter.get_dashboard.return_value = {"name": "test_dash", "definition": {"charts": []}}
        self.mock_adapter.batch_get_dashboard_charts.return_value = {"dashboardCharts": []}
        self.mock_adapter.list_curated_rulesets.return_value = {"curatedRuleSets": []}

        report = self.workflow.execute(include_curated=False)

        self.assertEqual(report.total_rules_audited, 1)
        self.assertEqual(report.healthy_count, 1)
        self.assertEqual(report.failing_count, 0)
        self.assertEqual(report.findings[0].status, RuleHealthStatus.HEALTHY)
        self.assertEqual(report.findings[0].display_name, "Suspicious Login Detection")

    def test_execution_error_rule_evaluation(self):
        # Setup mock rules
        self.mock_adapter.list_rules.return_value = {
            "rules": [
                {
                    "name": "projects/123/locations/us/instances/abc/rules/ru_broken",
                    "displayName": "Broken Rule Syntax",
                    "severity": "CRITICAL",
                    "runFrequency": "LIVE",
                    "enabled": True,
                    "alerting": True,
                }
            ]
        }
        # Error on ru_broken
        self.mock_adapter.list_rule_execution_errors.return_value = {
            "ruleExecutionErrors": [
                {
                    "name": "err_1",
                    "rule": "projects/123/locations/us/instances/abc/rules/ru_broken",
                    "error": {"code": 3, "message": "UDM field target.user.userid not found in event window"},
                }
            ]
        }
        self.mock_adapter.get_native_dashboard.return_value = {"name": "test_dash", "definition": {"charts": []}}
        self.mock_adapter.get_dashboard.return_value = {"name": "test_dash", "definition": {"charts": []}}
        self.mock_adapter.batch_get_dashboard_charts.return_value = {"dashboardCharts": []}
        self.mock_adapter.list_curated_rulesets.return_value = {"curatedRuleSets": []}

        report = self.workflow.execute(include_curated=False)

        self.assertEqual(report.total_rules_audited, 1)
        self.assertEqual(report.failing_count, 1)
        finding = report.findings[0]
        self.assertEqual(finding.status, RuleHealthStatus.EXECUTION_ERROR)
        self.assertEqual(finding.execution_error_count, 1)
        self.assertIn("target.user.userid", finding.last_error_message)
        self.assertTrue(len(finding.remediation_steps) > 0)

    def test_high_latency_rule_evaluation(self):
        # Setup mock rules
        self.mock_adapter.list_rules.return_value = {
            "rules": [
                {
                    "name": "projects/123/locations/us/instances/abc/rules/ru_slow",
                    "displayName": "Slow Heavy Join Rule",
                    "severity": "MEDIUM",
                    "runFrequency": "LIVE",
                    "enabled": True,
                    "alerting": True,
                }
            ]
        }
        self.mock_adapter.list_rule_execution_errors.return_value = {"ruleExecutionErrors": []}

        # Mock dashboard detail for observability
        def get_dashboard_side_effect(dashboard_id_or_name: str):
            if RULE_OBSERVABILITY_DASHBOARD_ID in dashboard_id_or_name:
                return {
                    "name": "projects/123/locations/us/instances/abc/dashboards/" + RULE_OBSERVABILITY_DASHBOARD_ID,
                    "displayName": "Rule Observability",
                    "definition": {
                        "charts": [{"dashboardChart": "chart_latency_1"}],
                    },
                }
            return {"name": "test_dash", "definition": {"charts": []}}

        self.mock_adapter.get_native_dashboard.side_effect = get_dashboard_side_effect
        self.mock_adapter.get_dashboard.side_effect = get_dashboard_side_effect
        self.mock_adapter.batch_get_dashboard_charts.return_value = {
            "dashboardCharts": [
                {
                    "name": "chart_latency_1",
                    "displayName": "Per-Detection Latency Numbers - TOP 20",
                    "chartDatasource": {"dashboardQuery": "q_latency_1"},
                }
            ]
        }
        self.mock_adapter.execute_dashboard_query.return_value = DashboardQueryResult(
            query_name="q_latency_1",
            dialect="DIALECT_STATS",
            data_sources=[],
            time_window={},
            columns=["rule_name", "detect_id", "ingestion_to_detection", "event_to_deteciton"],
            rows=[
                {
                    "rule_name": "Slow Heavy Join Rule",
                    "detect_id": "d_123",
                    "ingestion_to_detection": "45.5",
                    "event_to_deteciton": "48.2",
                }
            ],
            total_rows=1,
            retrieved_at=datetime.now(timezone.utc),
        )
        self.mock_adapter.list_curated_rulesets.return_value = {"curatedRuleSets": []}

        report = self.workflow.execute(include_curated=False, latency_threshold_min=30.0)

        self.assertEqual(report.total_rules_audited, 1)
        self.assertEqual(report.latency_alert_count, 1)
        finding = report.findings[0]
        self.assertEqual(finding.status, RuleHealthStatus.HIGH_LATENCY)
        self.assertEqual(finding.ingestion_to_detection_latency_min, 45.5)
        self.assertIn("Optimize YARA-L condition window", finding.remediation_steps[0])

    def test_silent_decay_rule_evaluation(self):
        # Setup mock rules
        self.mock_adapter.list_rules.return_value = {
            "rules": [
                {
                    "name": "projects/123/locations/us/instances/abc/rules/ru_decay",
                    "displayName": "Stale Outdated Rule",
                    "severity": "LOW",
                    "runFrequency": "LIVE",
                    "enabled": True,
                    "alerting": True,
                }
            ]
        }
        self.mock_adapter.list_rule_execution_errors.return_value = {"ruleExecutionErrors": []}

        # Mock dashboard detail for overview least active
        def get_dashboard_side_effect(dashboard_id_or_name: str):
            if RULE_DETECTIONS_OVERVIEW_DASHBOARD_ID in dashboard_id_or_name:
                return {
                    "name": "projects/123/locations/us/instances/abc/dashboards/" + RULE_DETECTIONS_OVERVIEW_DASHBOARD_ID,
                    "displayName": "Rule Detections Overview",
                    "definition": {
                        "charts": [{"dashboardChart": "chart_least_1"}],
                    },
                }
            return {"name": "test_dash", "definition": {"charts": []}}

        self.mock_adapter.get_native_dashboard.side_effect = get_dashboard_side_effect
        self.mock_adapter.get_dashboard.side_effect = get_dashboard_side_effect
        self.mock_adapter.batch_get_dashboard_charts.return_value = {
            "dashboardCharts": [
                {
                    "name": "chart_least_1",
                    "displayName": "Least 10 Active Rules",
                    "chartDatasource": {"dashboardQuery": "q_least_1"},
                }
            ]
        }
        self.mock_adapter.execute_dashboard_query.return_value = DashboardQueryResult(
            query_name="q_least_1",
            dialect="DIALECT_STATS",
            data_sources=[],
            time_window={},
            columns=["Rulename"],
            rows=[
                {
                    "Rulename": "Stale Outdated Rule",
                }
            ],
            total_rows=1,
            retrieved_at=datetime.now(timezone.utc),
        )
        self.mock_adapter.list_curated_rulesets.return_value = {"curatedRuleSets": []}

        report = self.workflow.execute(include_curated=False)

        self.assertEqual(report.total_rules_audited, 1)
        self.assertEqual(report.decay_count, 1)
        finding = report.findings[0]
        self.assertEqual(finding.status, RuleHealthStatus.SILENT_DECAY)
        self.assertIn("Verify if upstream log sources", finding.remediation_steps[0])


if __name__ == "__main__":
    unittest.main()
