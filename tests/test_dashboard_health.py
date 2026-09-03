"""Unit tests for AuditDashboardHealthWorkflow and Dashboard Health models."""

import unittest
from datetime import datetime, timezone
from typing import Any, Dict, List
from unittest.mock import MagicMock

from engine.domain import (
    DashboardHealthFinding,
    DashboardHealthReport,
    DashboardHealthStatus,
    DashboardSummary,
    DashboardDetail,
    DashboardChart,
    DashboardQuery,
    ValidationResult,
)
from engine.facade import SecOpsEngine
from engine.workflows.dashboard_health import AuditDashboardHealthWorkflow


class TestDashboardHealthWorkflow(unittest.TestCase):
    """Test suite for AuditDashboardHealthWorkflow."""

    def setUp(self):
        self.mock_adapter = MagicMock()
        self.workflow = AuditDashboardHealthWorkflow(adapter=self.mock_adapter)

    def test_capability_registration(self):
        """Verifies dashboard.audit_health capability is properly registered."""
        engine = SecOpsEngine()
        cap = engine.registry.get("dashboard.audit_health")
        self.assertIsNotNone(cap)
        self.assertEqual(cap.category, "dashboard")
        self.assertEqual(cap.domain, "dashboard")
        self.assertEqual(cap.kind, "workflow")
        self.assertTrue(cap.composed)
        self.assertIn("dashboard.search", cap.uses)
        self.assertIn("dashboard.get", cap.uses)
        self.assertIn("dashboard.validate_query", cap.uses)

    def test_healthy_dashboard_evaluation(self):
        """Verifies evaluation of healthy custom dashboard."""
        self.mock_adapter.list_native_dashboards.return_value = {
            "dashboards": [
                {
                    "name": "projects/123/locations/us/instances/abc/dashboards/d_healthy",
                    "displayName": "SOC Operations Overview",
                    "type": "CUSTOM",
                    "createTime": "2026-01-01T00:00:00Z",
                    "updateTime": "2026-01-10T00:00:00Z",
                    "createUserId": "secops_admin@altostrat.com",
                    "updateUserId": "secops_admin@altostrat.com",
                    "definition": {
                        "charts": [{"dashboardChart": "chart_1"}],
                    },
                }
            ]
        }
        self.mock_adapter.get_native_dashboard.return_value = {
            "name": "projects/123/locations/us/instances/abc/dashboards/d_healthy",
            "displayName": "SOC Operations Overview",
            "definition": {"charts": [{"dashboardChart": "chart_1"}]},
        }
        self.mock_adapter.batch_get_dashboard_charts.return_value = {
            "dashboardCharts": [
                {
                    "name": "chart_1",
                    "displayName": "Alert Volume by Severity",
                    "chartDatasource": {"dashboardQuery": "q_1"},
                }
            ]
        }
        self.mock_adapter.get_dashboard_query.return_value = {
            "name": "q_1",
            "query": "stats count(*) by metadata.event_type",
            "dialect": "DIALECT_STATS",
        }
        self.mock_adapter.validate_stats_query.return_value = ValidationResult(
            valid=True,
            dialect="DIALECT_STATS",
            raw_query_type="QUERY_TYPE_STATS_QUERY",
            error_message=None,
        )

        # Set stale threshold high so 2026-01-10 is not stale
        report = self.workflow.execute(lookback_days=14, stale_days=1000, validate_queries=True)

        self.assertEqual(report.total_dashboards_audited, 1)
        self.assertEqual(report.healthy_count, 1)
        self.assertEqual(report.broken_query_count, 0)
        self.assertEqual(report.findings[0].status, DashboardHealthStatus.HEALTHY)

    def test_recently_created_dashboard(self):
        """Verifies detection of recently created dashboards."""
        now_str = datetime.now(timezone.utc).isoformat()
        self.mock_adapter.list_native_dashboards.return_value = {
            "dashboards": [
                {
                    "name": "projects/123/locations/us/instances/abc/dashboards/d_new",
                    "displayName": "New Threat Hunt Dashboard",
                    "type": "CUSTOM",
                    "createTime": now_str,
                    "updateTime": now_str,
                    "createUserId": "analyst@altostrat.com",
                    "definition": {"charts": [{"dashboardChart": "c_1"}]},
                }
            ]
        }
        self.mock_adapter.get_native_dashboard.return_value = {
            "name": "projects/123/locations/us/instances/abc/dashboards/d_new",
            "displayName": "New Threat Hunt Dashboard",
            "definition": {"charts": [{"dashboardChart": "c_1"}]},
        }
        self.mock_adapter.batch_get_dashboard_charts.return_value = {
            "dashboardCharts": [
                {
                    "name": "c_1",
                    "displayName": "Hunt Results",
                    "chartDatasource": {"dashboardQuery": "q_new"},
                }
            ]
        }
        self.mock_adapter.get_dashboard_query.return_value = {
            "name": "q_new",
            "query": "stats count(*) by principal.ip",
            "dialect": "DIALECT_STATS",
        }
        self.mock_adapter.validate_stats_query.return_value = ValidationResult(
            valid=True,
            dialect="DIALECT_STATS",
            raw_query_type="QUERY_TYPE_STATS_QUERY",
            error_message=None,
        )

        report = self.workflow.execute(lookback_days=14, validate_queries=True)

        self.assertEqual(report.total_dashboards_audited, 1)
        self.assertEqual(report.recently_created_count, 1)
        self.assertEqual(report.findings[0].status, DashboardHealthStatus.RECENTLY_CREATED)
        self.assertIn("analyst@altostrat.com", report.findings[0].details)

    def test_broken_query_dashboard(self):
        """Verifies detection and error capture for broken widget queries."""
        self.mock_adapter.list_native_dashboards.return_value = {
            "dashboards": [
                {
                    "name": "projects/123/locations/us/instances/abc/dashboards/d_broken",
                    "displayName": "Broken Telemetry Widget",
                    "type": "CUSTOM",
                    "createTime": "2026-01-01T00:00:00Z",
                    "updateTime": "2026-01-01T00:00:00Z",
                    "createUserId": "dev@altostrat.com",
                    "definition": {"charts": [{"dashboardChart": "c_broken"}]},
                }
            ]
        }
        self.mock_adapter.get_native_dashboard.return_value = {
            "name": "projects/123/locations/us/instances/abc/dashboards/d_broken",
            "displayName": "Broken Telemetry Widget",
            "definition": {"charts": [{"dashboardChart": "c_broken"}]},
        }
        self.mock_adapter.batch_get_dashboard_charts.return_value = {
            "dashboardCharts": [
                {
                    "name": "c_broken",
                    "displayName": "Invalid Syntax Chart",
                    "chartDatasource": {"dashboardQuery": "q_broken"},
                }
            ]
        }
        self.mock_adapter.get_dashboard_query.return_value = {
            "name": "q_broken",
            "query": "stats count(*) by non_existent_field_syntax",
            "dialect": "DIALECT_STATS",
        }
        self.mock_adapter.validate_stats_query.return_value = ValidationResult(
            valid=False,
            dialect="DIALECT_STATS",
            raw_query_type=None,
            error_message="Syntax error: Unexpected identifier 'non_existent_field_syntax'",
        )

        report = self.workflow.execute(lookback_days=14, stale_days=1000, validate_queries=True)

        self.assertEqual(report.total_dashboards_audited, 1)
        self.assertEqual(report.broken_query_count, 1)
        finding = report.findings[0]
        self.assertEqual(finding.status, DashboardHealthStatus.BROKEN_QUERY)
        self.assertEqual(finding.broken_queries_count, 1)
        self.assertIn("Invalid Syntax Chart", finding.broken_query_details[0]["chart_display_name"])
        self.assertIn("Unexpected identifier", finding.broken_query_details[0]["error_message"])

    def test_empty_dashboard(self):
        """Verifies detection of empty custom dashboards."""
        self.mock_adapter.list_native_dashboards.return_value = {
            "dashboards": [
                {
                    "name": "projects/123/locations/us/instances/abc/dashboards/d_empty",
                    "displayName": "Empty Placeholder",
                    "type": "CUSTOM",
                    "createTime": "2026-01-01T00:00:00Z",
                    "updateTime": "2026-01-01T00:00:00Z",
                    "createUserId": "user@altostrat.com",
                    "definition": {"charts": []},
                }
            ]
        }

        report = self.workflow.execute(lookback_days=14, stale_days=1000, validate_queries=False)

        self.assertEqual(report.total_dashboards_audited, 1)
        self.assertEqual(report.empty_dashboard_count, 1)
        self.assertEqual(report.findings[0].status, DashboardHealthStatus.EMPTY_DASHBOARD)

    def test_stale_dashboard(self):
        """Verifies detection of stale custom dashboards (>180 days inactive)."""
        self.mock_adapter.list_native_dashboards.return_value = {
            "dashboards": [
                {
                    "name": "projects/123/locations/us/instances/abc/dashboards/d_stale",
                    "displayName": "Abandoned Dashboard 2024",
                    "type": "CUSTOM",
                    "createTime": "2024-01-01T00:00:00Z",
                    "updateTime": "2024-01-01T00:00:00Z",
                    "createUserId": "former_employee@altostrat.com",
                    "definition": {"charts": [{"dashboardChart": "c_stale"}]},
                }
            ]
        }

        report = self.workflow.execute(lookback_days=14, stale_days=180, validate_queries=False)

        self.assertEqual(report.total_dashboards_audited, 1)
        self.assertEqual(report.stale_count, 1)
        self.assertEqual(report.findings[0].status, DashboardHealthStatus.STALE)
        self.assertIn("former_employee@altostrat.com", report.findings[0].details)


if __name__ == "__main__":
    unittest.main()
