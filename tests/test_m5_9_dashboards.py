"""Acceptance and Behavioral Tests for Milestone 5.9: Google SecOps Dashboards.

Verifies:
1. Native Dashboard discovery, search, and type filtering against live tenant.
2. Deep composite graph assembly (dashboard + layout + batch-resolved charts + queries).
3. Live batch chart resolution using multi-value query parameter encoding.
4. Execution of dashboard widget queries and transformation from columnar to tabular records.
5. Statistical query syntax validation with compiler dialect DIALECT_STATS.
6. Engine capability registration and strict anti-mock compliance.
"""

from tests.test_helpers import get_live_adapter, get_live_engine
import os
import unittest
from datetime import datetime

from engine import (
    DashboardBatch,
    DashboardChart,
    DashboardDetail,
    DashboardQuery,
    DashboardQueryResult,
    DashboardSearchQuery,
    DashboardSummary,
    SecOpsEngine,
    ValidationResult,
)


class TestM59DashboardsLive(unittest.TestCase):
    """Live acceptance tests for Milestone 5.9 Google SecOps Dashboards."""

    @classmethod
    def setUpClass(cls):
        cls.engine = get_live_engine()
        cls.test_dashboard_id = None
        cls.test_dashboard_title = None
        cls.test_chart_names = []
        cls.test_query_id = None

        batch = cls.engine.search_dashboards(limit=15)
        for db in batch.dashboards:
            detail = cls.engine.get_dashboard(db.id, include_queries=True)
            if detail.charts:
                cls.test_dashboard_id = db.id
                cls.test_dashboard_title = db.display_name
                cls.test_chart_names = [c.name for c in detail.charts if c.name][:2]
                for c in detail.charts:
                    if c.query and c.query.id:
                        cls.test_query_id = c.query.id
                        break
                if cls.test_query_id:
                    break

    def test_01_search_native_dashboards_live(self):
        """Verifies live discovery and filtering of native SecOps dashboards."""
        batch: DashboardBatch = self.engine.search_dashboards(limit=10)
        self.assertIsInstance(batch, DashboardBatch)
        self.assertGreater(batch.total_count, 0)
        self.assertGreater(len(batch.dashboards), 0)
        self.assertLessEqual(len(batch.dashboards), 10)

        first = batch.dashboards[0]
        self.assertIsInstance(first, DashboardSummary)
        self.assertTrue(len(first.id) > 0)
        self.assertTrue(len(first.display_name) > 0)
        self.assertIn(first.type, ["CUSTOM", "DEFAULT", "CURATED", "UNKNOWN"])
        self.assertTrue(first.name.startswith("projects/"))

        # Test keyword search against a discovered dashboard title
        filtered_batch = self.engine.search_dashboards(query=first.display_name, limit=5)
        self.assertGreater(len(filtered_batch.dashboards), 0)
        matched_ids = [d.id for d in filtered_batch.dashboards]
        self.assertIn(first.id, matched_ids)

    def test_02_get_dashboard_deep_composite_live(self):
        """Verifies deep composite inspection of a live dashboard with layout and resolved charts."""
        if not self.test_dashboard_id:
            self.skipTest("No dashboards with charts available in live tenant.")
        detail: DashboardDetail = self.engine.get_dashboard(self.test_dashboard_id, include_queries=True)
        self.assertIsInstance(detail, DashboardDetail)
        self.assertEqual(detail.summary.id, self.test_dashboard_id)
        self.assertEqual(detail.summary.display_name, self.test_dashboard_title)
        self.assertGreater(len(detail.charts), 0)

        # Verify chart composition
        for chart in detail.charts:
            self.assertIsInstance(chart, DashboardChart)
            self.assertTrue(len(chart.id) > 0)
            self.assertIn(
                chart.tile_type,
                ["TILE_TYPE_VISUALIZATION", "TILE_TYPE_MARKDOWN", "TILE_TYPE_BUTTON", "TILE_TYPE_UNSPECIFIED", "UNKNOWN"],
            )

            # Verify layout grid coordinates
            if chart.layout:
                self.assertGreaterEqual(chart.layout.start_x, 0)
                self.assertGreaterEqual(chart.layout.start_y, 0)
                self.assertGreater(chart.layout.span_x, 0)
                self.assertGreater(chart.layout.span_y, 0)

            # If visualization with query, check query resolution
            if chart.tile_type == "TILE_TYPE_VISUALIZATION" and chart.query:
                self.assertIsInstance(chart.query, DashboardQuery)
                self.assertTrue(len(chart.query.id) > 0)
                self.assertTrue(len(chart.query.query_text) > 0)

    def test_03_batch_get_dashboard_charts_live(self):
        """Verifies multi-chart batch resolution using repeatable names query parameters."""
        if not self.test_chart_names:
            self.skipTest("No dashboard charts available in live tenant.")
        res = self.engine.adapter.batch_get_dashboard_charts(self.test_chart_names)
        self.assertIn("dashboardCharts", res)
        self.assertEqual(len(res["dashboardCharts"]), len(self.test_chart_names))
        resolved_names = [c.get("name") for c in res["dashboardCharts"]]
        for cn in self.test_chart_names:
            self.assertIn(cn, resolved_names)

    def test_04_execute_dashboard_query_tabular_live(self):
        """Verifies dashboard query execution and columnar to tabular row normalization."""
        if self.test_query_id:
            res: DashboardQueryResult = self.engine.execute_dashboard_query(
                query_name_or_id=self.test_query_id,
                time_value="7",
                time_unit="DAY",
            )
        else:
            res = self.engine.execute_dashboard_query(
                query_text='$log_type = metadata.log_type\nmatch:\n  $log_type\noutcome:\n  $count = count(metadata.id)\nlimit:\n  5',
                time_value="7",
                time_unit="DAY",
            )
        self.assertIsInstance(res, DashboardQueryResult)
        self.assertIsInstance(res.columns, list)
        self.assertIsInstance(res.rows, list)
        self.assertEqual(len(res.rows), res.total_rows)
        if res.rows:
            first_row = res.rows[0]
            self.assertIsInstance(first_row, dict)

    def test_05_validate_stats_query_live(self):
        """Verifies statistical syntax validation against the Google SecOps query compiler."""
        valid_query = """ingestion.component = "Ingestion API"

outcome:
    $total_gb = math.round(sum(ingestion.log_volume) / math.pow(1000, 3), 5)"""
        val_res: ValidationResult = self.engine.validate_dashboard_query(valid_query, dialect="DIALECT_STATS")
        self.assertIsInstance(val_res, ValidationResult)
        self.assertTrue(val_res.valid)
        self.assertEqual(val_res.raw_query_type, "QUERY_TYPE_STATS_QUERY")

        invalid_query = "this is not valid stats syntax !!! @@@"
        val_invalid: ValidationResult = self.engine.validate_dashboard_query(invalid_query, dialect="DIALECT_STATS")
        self.assertFalse(val_invalid.valid)

    def test_06_capabilities_and_anti_mock_audit(self):
        """Verifies capability registrations and strict anti-mock compliance."""
        caps = self.engine.list_capabilities(category="dashboard")
        cap_ids = [c.capability_id for c in caps]
        expected = [
            "dashboard.search",
            "dashboard.get",
            "dashboard.execute_query",
            "dashboard.validate_query",
        ]
        for exp in expected:
            self.assertIn(exp, cap_ids)

        # Anti-mock scan across production source code
        banned_terms = ["mock", "dummy", "fake", "fixture", "sampleData", "placeholderData"]
        src_dirs = ["engine", "adapters", "clients"]
        for src_dir in src_dirs:
            if not os.path.exists(src_dir):
                continue
            for root, _, files in os.walk(src_dir):
                for file in files:
                    if file.endswith(".py"):
                        fpath = os.path.join(root, file)
                        with open(fpath, "r", encoding="utf-8") as f:
                            content = f.read()
                            for term in banned_terms:
                                self.assertNotIn(
                                    term.lower(),
                                    content.lower(),
                                    f"Banned mock term '{term}' found in production file: {fpath}",
                                )


if __name__ == "__main__":
    unittest.main()
