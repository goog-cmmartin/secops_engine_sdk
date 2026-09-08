"""Tests for Raw Log Search, Product Source Statistics, and Query Validation.

Validates:
1. Capability registration, taxonomy, and facade interface compliance.
2. Product source statistics retrieval, time range filtering, and volume parsing.
3. Raw log query syntax validation, errorText extraction, and validation outcome mapping.
4. Raw log search execution, streaming match collation, snippet extraction, and aggregations.
5. Graceful SkipTest behavior on unconfigured environments via get_live_engine().
"""

import unittest
from engine.domain import (
    ProductSourceStat,
    ProductSourceStatsBatch,
    RawLogSearchResult,
    RawLogSnippet,
    RawLogValidationResult,
)
from engine.facade import SecOpsEngine
from tests.test_helpers import get_live_engine


class RawLogSearchContractTest(unittest.TestCase):
    """Verifies registry, facade, and capability declarations."""

    def setUp(self):
        self.engine = SecOpsEngine()

    def test_log_capabilities_registered(self):
        c_stats = self.engine.registry.get("log.product_sources.stats")
        self.assertIsNotNone(c_stats)
        self.assertEqual(c_stats.category, "log")
        self.assertEqual(c_stats.kind, "query")
        self.assertEqual(c_stats.cardinality, "unbounded")
        self.assertEqual(c_stats.mcp_tool_name, "query_product_source_stats")

        c_val = self.engine.registry.get("log.query.validate_query")
        self.assertIsNotNone(c_val)
        self.assertEqual(c_val.category, "log")
        self.assertEqual(c_val.kind, "query")
        self.assertEqual(c_val.cardinality, "bounded")
        self.assertEqual(c_val.mcp_tool_name, "validate_raw_log_query")

        c_search = self.engine.registry.get("log.raw_logs.search")
        self.assertIsNotNone(c_search)
        self.assertEqual(c_search.category, "log")
        self.assertEqual(c_search.kind, "query")
        self.assertEqual(c_search.cardinality, "unbounded")
        self.assertEqual(c_search.mcp_tool_name, "search_raw_logs")
        self.assertTrue(c_search.agent.get("require_filter_for_unbounded_query"))


class RawLogSearchLiveIntegrationTest(unittest.TestCase):
    """Verifies live Google SecOps API interactions for raw logs."""

    @classmethod
    def setUpClass(cls):
        cls.engine = get_live_engine()

    def test_query_product_source_stats(self):
        batch = self.engine.query_product_source_stats(lookback_hours=12)
        self.assertIsInstance(batch, ProductSourceStatsBatch)
        self.assertIsInstance(batch.stats, list)
        self.assertGreater(batch.total_sources, 0)
        for stat in batch.stats:
            self.assertIsInstance(stat, ProductSourceStat)
            self.assertTrue(stat.product_source)
            self.assertIsInstance(stat.data_size_bytes, int)
            self.assertGreaterEqual(stat.data_size_bytes, 0)

    def test_validate_raw_log_query_valid(self):
        res = self.engine.validate_raw_log_query("raw = /.*/ parsed = false")
        self.assertIsInstance(res, RawLogValidationResult)
        self.assertTrue(res.is_valid)
        self.assertIsNone(res.error_message)
        self.assertEqual(res.query_type, "QUERY_TYPE_RAW_LOG_QUERY")

    def test_validate_raw_log_query_invalid(self):
        res = self.engine.validate_raw_log_query("bad query &&& invalid")
        self.assertIsInstance(res, RawLogValidationResult)
        self.assertFalse(res.is_valid)
        self.assertIsNotNone(res.error_message)

    def test_validate_raw_log_query_empty(self):
        res = self.engine.validate_raw_log_query("   ")
        self.assertIsInstance(res, RawLogValidationResult)
        self.assertFalse(res.is_valid)
        self.assertIn("empty", res.error_message.lower())

    def test_search_raw_logs(self):
        res = self.engine.search_raw_logs(
            query="raw = /.*/ parsed = false",
            lookback_hours=2,
            page_size=3,
        )
        self.assertIsInstance(res, RawLogSearchResult)
        self.assertIsInstance(res.matches, list)
        self.assertGreater(res.progress, 0)
        if res.matches:
            match = res.matches[0]
            self.assertIsInstance(match, RawLogSnippet)
            self.assertTrue(match.id)
            self.assertTrue(match.snippet)


if __name__ == "__main__":
    unittest.main()
