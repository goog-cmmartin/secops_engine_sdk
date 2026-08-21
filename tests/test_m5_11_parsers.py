"""Acceptance and Behavioral Tests for Milestone 5.11: SIEM Settings - Parsers, Log Types, Extensions & Settings.

Verifies:
1. Supported Log Types catalog discovery and keyword filtering.
2. Ingestion Parsers discovery, creator/state filtering, deep inspection, and Logstash CBN Base64 decoding.
3. Parser Extensions discovery, inspection, and snippet/sample-log Base64 decoding.
4. Log Type Setting retrieval for autonomous parsing extraction.
5. Engine capability registration and registry metadata.
6. Strict anti-mock compliance across production codebase.
"""

from tests.test_helpers import get_live_adapter, get_live_engine
import os
import unittest
from datetime import datetime

from engine import (
    LogTypeBatch,
    LogTypeSetting,
    LogTypeSummary,
    ParserBatch,
    ParserDetail,
    ParserExtensionBatch,
    ParserExtensionDetail,
    ParserExtensionSummary,
    ParserSummary,
    SecOpsEngine,
)


class TestM511ParsersLive(unittest.TestCase):
    """Live acceptance tests for Milestone 5.11 SIEM Parsers, Log Types & Extensions."""

    @classmethod
    def setUpClass(cls):
        cls.engine = get_live_engine()

    def test_01_list_log_types_live(self):
        """Verifies discovery and filtering of supported ingestion log types."""
        batch: LogTypeBatch = self.engine.list_log_types(limit=50)
        self.assertIsInstance(batch, LogTypeBatch)
        self.assertGreater(batch.total_count, 100)
        self.assertGreater(len(batch.log_types), 0)
        self.assertLessEqual(len(batch.log_types), 50)
        self.assertIsInstance(batch.retrieved_at, datetime)

        first = batch.log_types[0]
        self.assertIsInstance(first, LogTypeSummary)
        self.assertTrue(len(first.id) > 0)
        self.assertTrue(len(first.display_name) > 0)
        self.assertTrue(first.name.startswith("projects/"))

        # Test query filtering
        ps_batch = self.engine.list_log_types(query="POWERSHELL", limit=10)
        self.assertGreater(len(ps_batch.log_types), 0)
        ps_ids = [lt.id for lt in ps_batch.log_types]
        self.assertIn("POWERSHELL", ps_ids)

    def test_02_search_and_get_parsers_live(self):
        """Verifies discovery, filtering, and deep inspection of parsers with Base64 CBN decoding."""
        batch: ParserBatch = self.engine.search_parsers(limit=20)
        self.assertIsInstance(batch, ParserBatch)
        self.assertGreater(batch.total_count, 0)
        self.assertGreater(len(batch.parsers), 0)
        self.assertLessEqual(len(batch.parsers), 20)
        self.assertIsInstance(batch.retrieved_at, datetime)

        first = batch.parsers[0]
        self.assertIsInstance(first, ParserSummary)
        self.assertTrue(len(first.id) > 0)
        self.assertTrue(len(first.log_type) > 0)
        self.assertTrue(first.name.startswith("projects/"))

        # Test filter by creator=CUSTOMER
        customer_batch = self.engine.search_parsers(creator="CUSTOMER", limit=10)
        self.assertIsInstance(customer_batch, ParserBatch)
        for p in customer_batch.parsers:
            self.assertEqual(p.creator_source, "CUSTOMER")

        # Test deep inspection with Base64 CBN decoding
        # Aqua Tracee Custom is a known custom parser
        detail: ParserDetail = self.engine.get_parser("AQUA_TRACEE_CUSTOM")
        self.assertIsInstance(detail, ParserDetail)
        self.assertEqual(detail.summary.log_type, "AQUA_TRACEE_CUSTOM")
        self.assertIsInstance(detail.cbn_code, str)
        self.assertGreater(len(detail.cbn_code), 0)
        # Logstash CBN code starts with filter or ruby block
        self.assertTrue("filter" in detail.cbn_code or "state.get" in detail.cbn_code)

    def test_03_search_and_get_parser_extensions_live(self):
        """Verifies discovery and deep inspection of parser extensions with Base64 snippet decoding."""
        batch: ParserExtensionBatch = self.engine.search_parser_extensions(limit=10)
        self.assertIsInstance(batch, ParserExtensionBatch)
        self.assertGreater(batch.total_count, 0)
        self.assertGreater(len(batch.parser_extensions), 0)
        self.assertLessEqual(len(batch.parser_extensions), 10)
        self.assertIsInstance(batch.retrieved_at, datetime)

        first = batch.parser_extensions[0]
        self.assertIsInstance(first, ParserExtensionSummary)
        self.assertTrue(len(first.id) > 0)
        self.assertTrue(len(first.log_type) > 0)
        self.assertTrue(first.name.startswith("projects/"))

        # Test deep inspection of first extension
        detail: ParserExtensionDetail = self.engine.get_parser_extension(
            log_type=first.log_type,
            extension_id=first.id,
        )
        self.assertIsInstance(detail, ParserExtensionDetail)
        self.assertEqual(detail.summary.id, first.id)
        self.assertEqual(detail.summary.log_type, first.log_type)

        if detail.summary.has_cbn_snippet:
            self.assertIsInstance(detail.cbn_snippet, str)
            self.assertGreater(len(detail.cbn_snippet), 0)

    def test_04_get_log_type_setting_live(self):
        """Verifies retrieval of autonomous parsing settings for a log type."""
        setting: LogTypeSetting = self.engine.get_log_type_setting("POWERSHELL")
        self.assertIsInstance(setting, LogTypeSetting)
        self.assertEqual(setting.log_type, "POWERSHELL")
        self.assertIn(setting.autonomous_parsing_extraction_type, ["OPT_IN", "OPT_OUT", "UNSPECIFIED", "DISABLED", "ENABLED"])
        self.assertIsInstance(setting.raw_settings, dict)
        self.assertIsInstance(setting.retrieved_at, datetime)

    def test_05_engine_capabilities_registered(self):
        """Verifies that all 6 Parser capabilities are registered in the engine registry."""
        capabilities = self.engine.list_capabilities(category="parser")
        cap_ids = [c.capability_id for c in capabilities]
        self.assertIn("parser.log_types.list", cap_ids)
        self.assertIn("parser.search", cap_ids)
        self.assertIn("parser.get", cap_ids)
        self.assertIn("parser.extensions.search", cap_ids)
        self.assertIn("parser.extensions.get", cap_ids)
        self.assertIn("parser.log_type_setting.get", cap_ids)

    def test_06_anti_mock_compliance(self):
        """Strict verification that no forbidden mock identifiers exist in production paths."""
        banned_terms = ["mock", "fixture", "dummy", "fake", "sample_data", "test_data"]
        production_dirs = ["engine", "adapters", "clients"]

        for prod_dir in production_dirs:
            for root, _, files in os.walk(prod_dir):
                for file in files:
                    if file.endswith(".py"):
                        path = os.path.join(root, file)
                        with open(path, "r", encoding="utf-8") as f:
                            content = f.read().lower()
                            for term in banned_terms:
                                self.assertNotIn(
                                    term,
                                    content,
                                    f"Banned term '{term}' found in production file '{path}'",
                                )


if __name__ == "__main__":
    unittest.main()
