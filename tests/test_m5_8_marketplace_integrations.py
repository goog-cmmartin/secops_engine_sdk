"""Acceptance tests for Milestone 5.8: Content Hub Marketplace Response Integrations.

Tests live integration against Google SecOps Marketplace catalog, deep inspection,
commercial diff, and downstream affected dependency resolution.
"""

from tests.test_helpers import get_live_adapter, get_live_engine
import unittest
from engine.facade import SecOpsEngine
from engine.domain import (
    MarketplaceIntegrationBatch,
    MarketplaceIntegrationDetail,
    MarketplaceCommercialDiff,
    MarketplaceAffectedItems,
)


class TestMarketplaceIntegrations(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.engine = get_live_engine()

    def test_01_search_marketplace_integrations_all(self):
        """Verify discovery across entire Marketplace response integrations catalog."""
        batch = self.engine.search_marketplace_integrations(limit=20)
        self.assertIsInstance(batch, MarketplaceIntegrationBatch)
        self.assertGreater(batch.total_count, 100)
        self.assertGreaterEqual(batch.installed_count, 1)
        self.assertGreaterEqual(batch.updates_count, 0)
        self.assertEqual(len(batch.results), 20)

        # Ensure summary structures are properly hydrated
        first = batch.results[0]
        self.assertTrue(bool(first.identifier))
        self.assertTrue(bool(first.title))
        self.assertTrue(bool(first.version))
        self.assertTrue(first.resource_name.startswith("projects/"))

    def test_02_search_marketplace_integrations_filtered(self):
        """Verify keyword, category, and update-ready filtering."""
        # Updates available filter
        updates_batch = self.engine.search_marketplace_integrations(update_available=True)
        self.assertIsInstance(updates_batch, MarketplaceIntegrationBatch)
        for it in updates_batch.results:
            self.assertTrue(it.update_available)
            self.assertTrue(it.installed)

        # Category filter
        cloud_batch = self.engine.search_marketplace_integrations(category="Cloud", limit=10)
        self.assertGreater(cloud_batch.total_count, 5)
        for it in cloud_batch.results:
            self.assertTrue(any("cloud" in cat.lower() for cat in it.categories))

        # Keyword filter
        wiz_batch = self.engine.search_marketplace_integrations(query="Wiz")
        self.assertGreaterEqual(wiz_batch.total_count, 1)
        self.assertTrue(any(it.identifier == "Wiz" for it in wiz_batch.results))

    def test_03_get_marketplace_integration_wiz(self):
        """Verify deep inspection of Wiz integration with actions, jobs, and changelog."""
        detail = self.engine.get_marketplace_integration("Wiz")
        self.assertIsInstance(detail, MarketplaceIntegrationDetail)

        integ = detail.integration
        self.assertEqual(integ.identifier, "Wiz")
        self.assertEqual(integ.title, "Wiz")
        self.assertTrue(bool(integ.version))
        self.assertIsInstance(integ.installed, bool)
        if integ.installed:
            self.assertTrue(bool(integ.installed_version))
            self.assertEqual(integ.update_available, integ.installed_version != integ.version)
        self.assertTrue(integ.certified)
        self.assertIn("Cloud", integ.categories)

        # Bundled components
        self.assertGreaterEqual(len(detail.actions), 8)
        self.assertIn("Ping", detail.actions)
        self.assertGreaterEqual(len(detail.jobs), 1)
        self.assertGreaterEqual(len(detail.managers), 8)
        self.assertGreaterEqual(len(detail.release_notes), 5)

    def test_04_get_marketplace_integration_sentinelone(self):
        """Verify deep inspection of uninstalled SentinelOne Singularity integration."""
        detail = self.engine.get_marketplace_integration("SentinelOneSingularityOperationsCenter")
        self.assertIsInstance(detail, MarketplaceIntegrationDetail)

        integ = detail.integration
        self.assertEqual(integ.identifier, "SentinelOneSingularityOperationsCenter")
        self.assertIn(integ.version, ["1.0", "2.0"])
        self.assertFalse(integ.installed)
        self.assertFalse(integ.update_available)
        self.assertTrue(integ.documentation_uri.startswith("https://cloud.google.com/chronicle/docs/soar/marketplace-integrations/"))

        self.assertGreaterEqual(len(detail.actions), 3)
        self.assertIn("Ping", detail.actions)
        self.assertEqual(len(detail.connectors), 1)
        self.assertGreaterEqual(len(detail.managers), 8)

    def test_05_commercial_diff_wiz(self):
        """Verify commercial version diff calculation for an installed marketplace integration."""
        installed_batch = self.engine.search_marketplace_integrations(limit=50)
        target_id = next((it.identifier for it in installed_batch.results if it.installed), "Wiz")
        diff = self.engine.get_marketplace_integration_diff(target_id)
        self.assertIsInstance(diff, MarketplaceCommercialDiff)
        self.assertEqual(diff.integration_identifier, target_id)
        self.assertTrue(bool(diff.version))
        self.assertIsInstance(diff.actions, list)
        self.assertIsInstance(diff.managers, list)
        self.assertIsInstance(diff.diff, dict)

    def test_06_affected_items_wiz(self):
        """Verify downstream impact resolution of instances and active playbooks."""
        installed_batch = self.engine.search_marketplace_integrations(limit=50)
        target_id = next((it.identifier for it in installed_batch.results if it.installed), "Wiz")
        affected = self.engine.get_marketplace_integration_affected_items(target_id)
        self.assertIsInstance(affected, MarketplaceAffectedItems)
        self.assertEqual(affected.integration_identifier, target_id)
        self.assertIsInstance(affected.affected_instances, list)
        self.assertIsInstance(affected.affected_playbooks, list)
        for inst in affected.affected_instances:
            self.assertTrue(bool(inst.display_name or inst.identifier))

    def test_07_capability_registrations(self):
        """Verify all 4 marketplace capabilities are registered in the engine registry."""
        capabilities = self.engine.list_capabilities(category="marketplace_integration")
        self.assertEqual(len(capabilities), 4)

        cap_ids = [c.capability_id for c in capabilities]
        self.assertIn("marketplace_integration.search", cap_ids)
        self.assertIn("marketplace_integration.get", cap_ids)
        self.assertIn("marketplace_integration.diff", cap_ids)
        self.assertIn("marketplace_integration.affected_items", cap_ids)


if __name__ == "__main__":
    unittest.main()
