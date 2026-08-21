"""Acceptance and Behavioral Tests for Milestone 5.10: SIEM Settings, Feeds, Pipelines, and Feed Schemas.

Verifies:
1. Retrieval of approved managed email domain settings.
2. Ingestion Feeds discovery, multi-criteria filtering, and deep configuration inspection.
3. Data Processing Pipelines discovery, stream filtering, transform inspection, and Bindplane SaaS links.
4. Feed Source Type Schemas discovery.
5. Feed Log Type Schemas discovery with lean payload optimization.
6. Engine capability registration and strict anti-mock compliance.
"""

import os
import unittest
from datetime import datetime

from engine import (
    FeedBatch,
    FeedDetail,
    FeedLogTypeBatch,
    FeedLogTypeSchema,
    FeedSourceTypeBatch,
    FeedSourceTypeSchema,
    FeedSummary,
    LogProcessingPipelineBatch,
    LogProcessingPipelineDetail,
    LogProcessingPipelineSummary,
    ManagedDomain,
    ManagedDomainSettings,
    SecOpsEngine,
)


class TestM510SiemSettingsLive(unittest.TestCase):
    """Live acceptance tests for Milestone 5.10 SIEM Settings, Feeds & Pipelines."""

    @classmethod
    def setUpClass(cls):
        cls.engine = SecOpsEngine()

    def test_01_get_managed_domain_settings_live(self):
        """Verifies retrieval of approved email domains configured for reports and alerts."""
        settings: ManagedDomainSettings = self.engine.get_managed_domain_settings()
        self.assertIsInstance(settings, ManagedDomainSettings)
        self.assertIsInstance(settings.domains, list)
        self.assertIsInstance(settings.retrieved_at, datetime)

        if settings.domains:
            first = settings.domains[0]
            self.assertIsInstance(first, ManagedDomain)
            self.assertTrue(len(first.domain) > 0)
            self.assertTrue(len(first.added_time) > 0)

    def test_02_search_and_get_feeds_live(self):
        """Verifies discovery, filtering, and deep inspection of ingestion feeds."""
        batch: FeedBatch = self.engine.search_feeds(limit=10)
        self.assertIsInstance(batch, FeedBatch)
        self.assertGreater(batch.total_count, 0)
        self.assertGreater(len(batch.feeds), 0)
        self.assertLessEqual(len(batch.feeds), 10)

        first = batch.feeds[0]
        self.assertIsInstance(first, FeedSummary)
        self.assertTrue(len(first.id) > 0)
        self.assertTrue(len(first.display_name) > 0)
        self.assertTrue(first.name.startswith("projects/"))
        self.assertNotEqual(first.feed_source_type, "")
        self.assertNotEqual(first.log_type, "")

        # Test deep inspection
        detail: FeedDetail = self.engine.get_feed(first.id)
        self.assertIsInstance(detail, FeedDetail)
        self.assertEqual(detail.summary.id, first.id)
        self.assertIsInstance(detail.details, dict)

    def test_03_search_and_get_log_processing_pipelines_live(self):
        """Verifies discovery, stream inspection, and Bindplane links for Data Processing Pipelines."""
        batch: LogProcessingPipelineBatch = self.engine.search_log_processing_pipelines(limit=10)
        self.assertIsInstance(batch, LogProcessingPipelineBatch)
        self.assertGreater(batch.total_count, 0)
        self.assertGreater(len(batch.pipelines), 0)
        self.assertLessEqual(len(batch.pipelines), 10)

        first = batch.pipelines[0]
        self.assertIsInstance(first, LogProcessingPipelineSummary)
        self.assertTrue(len(first.id) > 0)
        self.assertTrue(len(first.display_name) > 0)
        self.assertTrue(first.name.startswith("projects/"))
        self.assertIsInstance(first.streams, list)

        # Test deep inspection
        detail: LogProcessingPipelineDetail = self.engine.get_log_processing_pipeline(first.id)
        self.assertIsInstance(detail, LogProcessingPipelineDetail)
        self.assertEqual(detail.summary.id, first.id)
        self.assertIsInstance(detail.processors, list)
        if detail.summary.bindplane_url:
            self.assertTrue(detail.summary.bindplane_url.startswith("https://app.bindplane.com/"))

    def test_04_list_feed_source_type_schemas_live(self):
        """Verifies discovery of supported feed source type schemas."""
        batch: FeedSourceTypeBatch = self.engine.list_feed_source_type_schemas(limit=50)
        self.assertIsInstance(batch, FeedSourceTypeBatch)
        self.assertGreater(batch.total_count, 0)
        self.assertGreater(len(batch.source_types), 0)

        source_names = [s.feed_source_type for s in batch.source_types]
        self.assertIn("AMAZON_S3", source_names)
        self.assertIn("GOOGLE_CLOUD_STORAGE", source_names)

        first = batch.source_types[0]
        self.assertIsInstance(first, FeedSourceTypeSchema)
        self.assertTrue(len(first.feed_source_type) > 0)
        self.assertTrue(len(first.display_name) > 0)

    def test_05_list_feed_log_type_schemas_live(self):
        """Verifies discovery of log type schemas for a feed source with lean payload optimization."""
        batch: FeedLogTypeBatch = self.engine.list_feed_log_type_schemas(
            feed_source_type="AMAZON_S3",
            limit=20,
            include_field_schemas=False,
        )
        self.assertIsInstance(batch, FeedLogTypeBatch)
        self.assertEqual(batch.feed_source_type, "AMAZON_S3")
        self.assertGreater(batch.total_count, 0)
        self.assertGreater(len(batch.log_types), 0)
        self.assertLessEqual(len(batch.log_types), 20)

        first = batch.log_types[0]
        self.assertIsInstance(first, FeedLogTypeSchema)
        self.assertTrue(len(first.log_type) > 0)
        self.assertTrue(len(first.display_name) > 0)
        # Verify lean payload: detailsFieldSchemas omitted but count recorded
        self.assertIsNone(first.details_field_schemas)
        self.assertGreaterEqual(first.details_field_schemas_count, 0)

    def test_06_capabilities_and_anti_mock_audit(self):
        """Verifies all SIEM settings capabilities are registered and no mocks exist in production."""
        caps = self.engine.list_capabilities()
        cap_ids = [c.capability_id for c in caps]

        expected_caps = [
            "siem.managed_domains.get",
            "feed.search",
            "feed.get",
            "pipeline.search",
            "pipeline.get",
            "feed_schema.list_sources",
            "feed_schema.list_log_types",
        ]
        for ec in expected_caps:
            self.assertIn(ec, cap_ids, f"Missing capability: {ec}")

        # Scan production source trees for forbidden mock terms
        banned_terms = [
            "mock", "dummy", "fake", "fixture",
            "sample_data", "sampledata",
            "placeholder_data", "placeholderdata",
        ]
        prod_dirs = ["engine", "adapters", "clients"]
        for pdir in prod_dirs:
            if not os.path.exists(pdir):
                continue
            for root, _, files in os.walk(pdir):
                if "__pycache__" in root:
                    continue
                for f in files:
                    if f.endswith(".py"):
                        fpath = os.path.join(root, f)
                        with open(fpath, "r", encoding="utf-8") as fh:
                            content = fh.read().lower()
                            for term in banned_terms:
                                self.assertNotIn(
                                    f" {term} ",
                                    content,
                                    f"Banned mock term '{term}' found in production file: {fpath}",
                                )


if __name__ == "__main__":
    unittest.main()
