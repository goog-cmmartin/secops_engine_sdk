"""Acceptance & Integration Tests for Milestone 5.6: Content Hub (Marketplace) Content Packs.

Validates discovery, search, multi-facet filtering, category hierarchy inspection,
and component bundle deep-inspection for Google SecOps Content Hub Content Packs.
Invariants: Strict live API provenance, zero synthetic data, explicit error visibility.
"""

from tests.test_helpers import get_live_adapter, get_live_engine
import os
import unittest

from engine.domain import (
    ContentPackBatch,
    ContentPackDetail,
    ContentPackSearchQuery,
    ContentPackSummary,
    ContentPackType,
)
from engine.facade import SecOpsEngine
from engine.registry import registry


class TestMilestone56ContentPack(unittest.TestCase):
    """Authoritative test suite for Content Hub Marketplace Content Packs."""

    @classmethod
    def setUpClass(cls):
        cls.engine = get_live_engine()

    def test_01_list_all_content_packs_live(self):
        """Verify listing all live content packs from the Google SecOps Marketplace."""
        batch: ContentPackBatch = self.engine.search_content_packs(limit=100)
        self.assertIsInstance(batch, ContentPackBatch)
        self.assertGreaterEqual(batch.total_count, 20)
        self.assertGreaterEqual(len(batch.results), 20)

        # Verify summary properties on the first pack
        sample = batch.results[0]
        self.assertIsInstance(sample, ContentPackSummary)
        self.assertTrue(sample.id)
        self.assertTrue(sample.title)
        self.assertIsInstance(sample.categories, list)
        self.assertIn(
            sample.pack_type,
            [
                ContentPackType.ONBOARDING.value,
                ContentPackType.SEC_OPS_USE_CASE.value,
                ContentPackType.SOAR_LEGACY.value,
                ContentPackType.EXTERNAL.value,
                ContentPackType.PRODUCT.value,
                ContentPackType.UNKNOWN.value,
            ],
        )

    def test_02_search_content_pack_by_keyword(self):
        """Verify keyword search returns relevant content packs."""
        batch = self.engine.search_content_packs(query="Recorded Future")
        self.assertGreaterEqual(len(batch.results), 1)
        titles = [p.title.lower() for p in batch.results]
        self.assertTrue(any("recorded future" in t for t in titles))

        # Search for Azure
        azure_batch = self.engine.search_content_packs(query="Azure")
        self.assertGreaterEqual(len(azure_batch.results), 1)
        azure_titles = [p.title.lower() for p in azure_batch.results]
        self.assertTrue(any("azure" in t for t in azure_titles))

    def test_03_filter_content_packs_by_category(self):
        """Verify multi-facet filtering by category."""
        ti_batch = self.engine.search_content_packs(category="Threat Intelligence")
        self.assertGreaterEqual(len(ti_batch.results), 5)
        for p in ti_batch.results:
            cats_lower = [c.lower() for c in p.categories]
            self.assertIn("threat intelligence", cats_lower)

        cloud_batch = self.engine.search_content_packs(category="Cloud")
        self.assertGreaterEqual(len(cloud_batch.results), 1)
        for p in cloud_batch.results:
            cats_lower = [c.lower() for c in p.categories]
            self.assertIn("cloud", cats_lower)

    def test_04_get_content_pack_deep_inspection(self):
        """Verify deep inspection of a specific content pack with bundled items."""
        # Recorded Future pack UUID
        rec_future_id = "f72e8833-a10a-49ef-a785-87b924f657c1"
        detail: ContentPackDetail = self.engine.get_content_pack(rec_future_id)

        self.assertIsInstance(detail, ContentPackDetail)
        self.assertEqual(detail.pack.identifier, rec_future_id)
        self.assertEqual(detail.pack.title, "Recorded Future")
        self.assertIn("Threat Intelligence", detail.pack.categories)

        # Verify bundled components are populated
        self.assertGreaterEqual(len(detail.playbooks), 1)
        self.assertEqual(detail.playbooks[0].item_type, "playbook")
        self.assertEqual(detail.playbooks[0].title, "Recorded Future Starting Playbook")

        self.assertGreaterEqual(len(detail.integrations), 1)
        self.assertEqual(detail.integrations[0].item_type, "integration")

        self.assertGreaterEqual(len(detail.dashboards), 1)
        self.assertEqual(detail.dashboards[0].item_type, "dashboard")

        # Verify guidance strings
        self.assertTrue(detail.pre_guidance)
        self.assertTrue(detail.post_guidance)

    def test_05_get_content_pack_by_title_resolution(self):
        """Verify retrieving content pack by exact title resolution."""
        detail: ContentPackDetail = self.engine.get_content_pack("Microsoft Azure Cloud Platform")
        self.assertIsInstance(detail, ContentPackDetail)
        self.assertEqual(detail.pack.title, "Microsoft Azure Cloud Platform")
        self.assertIn("Cloud", detail.pack.categories)
        self.assertGreaterEqual(len(detail.rulesets), 10)
        self.assertGreaterEqual(len(detail.queries), 5)

    def test_06_list_content_pack_categories(self):
        """Verify category taxonomy discovery aggregates pack counts correctly."""
        cats = self.engine.list_content_pack_categories()
        self.assertIsInstance(cats, list)
        self.assertGreaterEqual(len(cats), 20)

        cat_names = [c["category"] for c in cats]
        self.assertIn("Threat Intelligence", cat_names)
        self.assertIn("Cloud", cat_names)
        self.assertIn("EDR", cat_names)

        # All counts should be positive integers
        for c in cats:
            self.assertGreater(c["pack_count"], 0)

    def test_07_content_pack_capabilities_registered(self):
        """Verify engine registry exposes content pack capabilities."""
        caps = {c.capability_id: c for c in registry.list_capabilities(category="content_pack")}
        self.assertIn("content_pack.search", caps)
        self.assertIn("content_pack.get", caps)
        self.assertIn("content_pack.categories", caps)

        self.assertEqual(caps["content_pack.search"].category, "content_pack")
        self.assertEqual(caps["content_pack.get"].category, "content_pack")
        self.assertEqual(caps["content_pack.categories"].category, "content_pack")

    def test_08_static_anti_mock_audit_for_content_packs(self):
        """Verify production code for content packs complies with no-mock invariant."""
        banned_terms = ["mock", "Mock", "MOCK", "fixture", "Fixture", "dummy", "Dummy", "fake", "Fake", "sampleData", "sample_data"]
        target_files = [
            os.path.join(os.path.dirname(__file__), "..", "engine", "workflows", "content_pack.py"),
            os.path.join(os.path.dirname(__file__), "..", "specs", "content_pack", "content-pack-search-001.yaml"),
            os.path.join(os.path.dirname(__file__), "..", "specs", "content_pack", "content-pack-get-001.yaml"),
            os.path.join(os.path.dirname(__file__), "..", "specs", "content_pack", "content-pack-categories-001.yaml"),
        ]

        for filepath in target_files:
            if not os.path.exists(filepath):
                continue
            with open(filepath, "r", encoding="utf-8") as f:
                content = f.read()
                for term in banned_terms:
                    self.assertNotIn(
                        term,
                        content,
                        f"Banned mock term '{term}' found in production file {filepath}",
                    )


if __name__ == "__main__":
    unittest.main()
