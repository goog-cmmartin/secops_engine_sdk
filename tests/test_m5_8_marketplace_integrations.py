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
        self.assertGreater(batch.total_count, 350)
        self.assertGreater(batch.installed_count, 50)
        self.assertGreaterEqual(batch.updates_count, 1)
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
        self.assertGreaterEqual(len(updates_batch.results), 2)
        update_identifiers = [it.identifier for it in updates_batch.results]
        self.assertIn("Wiz", update_identifiers)
        self.assertIn("HTTP", update_identifiers)

        for it in updates_batch.results:
            self.assertTrue(it.update_available)
            self.assertTrue(it.installed)

        # Category filter
        cloud_batch = self.engine.search_marketplace_integrations(category="Cloud", limit=10)
        self.assertGreater(cloud_batch.total_count, 10)
        for it in cloud_batch.results:
            self.assertTrue(any("cloud" in cat.lower() for cat in it.categories))

        # Keyword filter
        wiz_batch = self.engine.search_marketplace_integrations(query="Wiz")
        self.assertGreaterEqual(wiz_batch.total_count, 1)
        self.assertTrue(any(it.identifier == "Wiz" for it in wiz_batch.results))

    def test_03_get_marketplace_integration_wiz(self):
        """Verify deep inspection of installed Wiz integration with actions, jobs, and changelog."""
        detail = self.engine.get_marketplace_integration("Wiz")
        self.assertIsInstance(detail, MarketplaceIntegrationDetail)

        integ = detail.integration
        self.assertEqual(integ.identifier, "Wiz")
        self.assertEqual(integ.title, "Wiz")
        self.assertIn(integ.version, ["9.0", "10.0"])
        self.assertEqual(integ.installed_version, "8.0")
        self.assertTrue(integ.installed)
        self.assertTrue(integ.update_available)
        self.assertTrue(integ.certified)
        self.assertIn("Cloud", integ.categories)

        # Bundled components
        self.assertGreaterEqual(len(detail.actions), 8)
        self.assertIn("Resolve Issue", detail.actions)
        self.assertIn("Ignore Issue", detail.actions)
        self.assertIn("Ping", detail.actions)

        self.assertEqual(len(detail.jobs), 1)
        self.assertEqual(detail.jobs[0], "Wiz and Google SecOps Bi-directional Sync Job")

        self.assertGreaterEqual(len(detail.managers), 10)
        self.assertIn("api_client", detail.managers)
        self.assertIn("query_builder", detail.managers)

        # Release notes / changelogs
        self.assertGreaterEqual(len(detail.release_notes), 9)
        v9_notes = [rn for rn in detail.release_notes if rn.version in ["9.0", "10.0"]]
        self.assertGreaterEqual(len(v9_notes), 1)
        self.assertTrue(any("Bi-directional Sync" in cl for rn in detail.release_notes for cl in rn.changelog_items))

    def test_04_get_marketplace_integration_sentinelone(self):
        """Verify deep inspection of uninstalled SentinelOne Singularity integration."""
        detail = self.engine.get_marketplace_integration("SentinelOneSingularityOperationsCenter")
        self.assertIsInstance(detail, MarketplaceIntegrationDetail)

        integ = detail.integration
        self.assertEqual(integ.identifier, "SentinelOneSingularityOperationsCenter")
        self.assertEqual(integ.version, "1.0")
        self.assertFalse(integ.installed)
        self.assertFalse(integ.update_available)
        self.assertTrue(integ.documentation_uri.startswith("https://cloud.google.com/chronicle/docs/soar/marketplace-integrations/"))

        self.assertGreaterEqual(len(detail.actions), 3)
        self.assertIn("Ping", detail.actions)
        self.assertEqual(len(detail.connectors), 1)
        self.assertGreaterEqual(len(detail.managers), 8)

    def test_05_commercial_diff_wiz(self):
        """Verify commercial version diff calculation between installed v8.0 and marketplace v9.0/v10.0."""
        diff = self.engine.get_marketplace_integration_diff("Wiz")
        self.assertIsInstance(diff, MarketplaceCommercialDiff)
        self.assertEqual(diff.integration_identifier, "Wiz")
        self.assertIn(diff.version, ["9", "9.0", "10", "10.0"])
        self.assertEqual(diff.python_version, "V3_11")
        self.assertEqual(len(diff.actions), 8)
        self.assertEqual(len(diff.managers), 10)

        diff_manifest = diff.diff
        self.assertIn("actions", diff_manifest)
        self.assertIn("override", diff_manifest["actions"])

    def test_06_affected_items_wiz(self):
        """Verify downstream impact resolution of instances and active playbooks for Wiz."""
        affected = self.engine.get_marketplace_integration_affected_items("Wiz")
        self.assertIsInstance(affected, MarketplaceAffectedItems)
        self.assertEqual(affected.integration_identifier, "Wiz")

        # Affected instance check
        self.assertEqual(len(affected.affected_instances), 1)
        self.assertEqual(affected.affected_instances[0].display_name, "System Default Instance")
        self.assertEqual(affected.affected_instances[0].environment, "Default Environment")

        # Affected playbook check
        self.assertEqual(len(affected.affected_playbooks), 1)
        self.assertEqual(affected.affected_playbooks[0].display_name, "Wiz ADK Response")
        self.assertIn("Default Environment", affected.affected_playbooks[0].environments)

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
