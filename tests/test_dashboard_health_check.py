"""Tests for dashboard health check workflow (Milestone 5.9)."""

import os
import unittest

from tests.test_helpers import get_live_engine
from engine import SecOpsEngine


class TestDashboardHealthCheckLive(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.live_engine = get_live_engine()

    @unittest.skipIf(
        os.environ.get("RUN_SLOW_E2E") != "1",
        "Slow live E2E: serially executes every widget query on a large "
        "dashboard and can exceed short CI timeouts. Set RUN_SLOW_E2E=1 to run.",
    )
    def test_dashboard_health_check_e2e(self):
        """E2E verification that health check workflow executes all dashboard queries."""
        # Target the "Data Ingestion and Health" dashboard
        result = self.live_engine.run_dashboard_health_check(
            dashboard_name="Data Ingestion and Health"
        )

        # Verify structure
        self.assertIn("dashboard_id", result)
        self.assertIn("query_results", result)
        self.assertIn("summary", result)
        self.assertIn("errors", result)

        # Verify at least one query executed
        self.assertGreater(len(result["query_results"]), 0)

        # Verify query result structure
        for qr in result["query_results"]:
            self.assertIn("query_name", qr)
            self.assertIn("chart_title", qr)
            self.assertIn("success", qr)

            if qr["success"]:
                self.assertIn("row_count", qr)
                self.assertIn("columns", qr)
            else:
                self.assertIn("error", qr)

        # Verify summary format
        self.assertIn("Dashboard Health Check:", result["summary"])
        self.assertIn("Total Queries:", result["summary"])
        self.assertIn("Successful:", result["summary"])

    def test_dashboard_not_found(self):
        """Verify error handling when dashboard doesn't exist."""
        with self.assertRaises(ValueError) as ctx:
            self.live_engine.run_dashboard_health_check(dashboard_name="NonexistentDashboard")
        self.assertIn("not found", str(ctx.exception).lower())

    def test_health_check_capability_registered(self):
        """Verify health check is properly registered in capability registry."""
        cap = self.live_engine.registry.get("dashboard.health_check")

        self.assertIsNotNone(cap)
        self.assertEqual(cap.category, "dashboard")
        self.assertTrue(cap.composed)
        self.assertEqual(cap.mcp_tool_name, "run_dashboard_health_check")
