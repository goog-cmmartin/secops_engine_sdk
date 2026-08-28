"""Unit tests for dashboard health check workflow orchestration."""

import unittest
from unittest.mock import Mock
from engine.workflows.dashboards import run_dashboard_health_check
from engine.domain import (
    DashboardSummary,
    DashboardDetail,
    DashboardChart,
    DashboardQuery,
    DashboardQueryResult,
)


class TestDashboardHealthCheckUnit(unittest.TestCase):
    def setUp(self):
        self.mock_adapter = Mock()
        self.mock_adapter.project_id = "test-project"
        self.mock_adapter.customer_id = "test-customer"
        self.mock_adapter.region = "us"

        self.sample_dashboard_raw = {
            "name": "projects/test-project/locations/us/instances/test-customer/dashboards/dash-1",
            "displayName": "My Dashboard",
            "description": "Test dashboard",
            "type": "CUSTOM",
            "createTime": "2024-01-01T00:00:00Z",
            "updateTime": "2024-01-01T00:00:00Z",
            "createUserId": "user-1",
            "updateUserId": "user-1",
            "access": "OWNER",
        }

        self.other_dashboard_raw = {
            "name": "projects/test-project/locations/us/instances/test-customer/dashboards/dash-other",
            "displayName": "Other Dashboard",
            "description": "Different dashboard",
            "type": "CUSTOM",
            "createTime": "2024-01-01T00:00:00Z",
            "updateTime": "2024-01-01T00:00:00Z",
            "createUserId": "user-1",
            "updateUserId": "user-1",
            "access": "OWNER",
        }

        self.sample_dashboard_detail_raw = {
            "name": "projects/test-project/locations/us/instances/test-customer/dashboards/dash-1",
            "displayName": "My Dashboard",
            "definition": {
                "charts": [
                    {"dashboardChart": "chart-1"},
                    {"dashboardChart": "chart-2"},
                ],
            },
        }

        self.batch_charts_response = {
            "dashboardCharts": [
                {
                    "name": "chart-1",
                    "displayName": "Chart 1",
                    "chartDatasource": {"dashboardQuery": "query-1"},
                },
                {
                    "name": "chart-2",
                    "displayName": "Chart 2",
                    "chartDatasource": {"dashboardQuery": "query-2"},
                },
            ]
        }

        self.query_response = {
            "name": "query-1",
            "queryText": "SELECT * FROM logs",
            "dialect": "SOAR_QUERY",
            "dataSources": ["logs"],
            "timeWindow": {},
        }

    def test_health_check_validates_dashboard_not_found(self):
        """Verify error handling when dashboard name doesn't match."""
        self.mock_adapter.list_native_dashboards = Mock(
            return_value={"nativeDashboards": [self.other_dashboard_raw]}
        )

        with self.assertRaises(ValueError) as ctx:
            run_dashboard_health_check(self.mock_adapter, "My Dashboard")
        self.assertIn("Dashboard 'My Dashboard' not found", str(ctx.exception))

    def test_health_check_executes_all_queries(self):
        """Verify health check executes all dashboard queries."""
        self.mock_adapter.list_native_dashboards = Mock(
            return_value={"nativeDashboards": [self.sample_dashboard_raw]}
        )
        self.mock_adapter.get_native_dashboard = Mock(return_value=self.sample_dashboard_detail_raw)
        self.mock_adapter.batch_get_dashboard_charts = Mock(return_value=self.batch_charts_response)
        self.mock_adapter.get_dashboard_query = Mock(return_value=self.query_response)
        self.mock_adapter.execute_dashboard_query = Mock(
            return_value=DashboardQueryResult(
                query_name="query-1",
                dialect="SOAR_QUERY",
                data_sources=["logs"],
                time_window={"start": "2024-01-01", "end": "2024-01-02"},
                columns=["col1"],
                rows=[{"col1": "value1"}],
                total_rows=1,
            )
        )

        # Execute health check
        result = run_dashboard_health_check(self.mock_adapter, "My Dashboard")

        # Validate structure
        self.assertIn("dashboard_id", result)
        self.assertIn("query_results", result)
        self.assertIn("summary", result)
        self.assertIn("errors", result)

        # Validate query execution
        self.assertEqual(len(result["query_results"]), 2)
        self.assertTrue(result["query_results"][0]["success"])
        self.assertEqual(result["query_results"][0]["chart_title"], "Chart 1")
        self.assertEqual(result["query_results"][1]["chart_title"], "Chart 2")

        # Validate adapter calls
        self.assertEqual(self.mock_adapter.execute_dashboard_query.call_count, 2)
        self.mock_adapter.batch_get_dashboard_charts.assert_called_once_with(["chart-1", "chart-2"])
        self.assertEqual(self.mock_adapter.get_dashboard_query.call_count, 2)
