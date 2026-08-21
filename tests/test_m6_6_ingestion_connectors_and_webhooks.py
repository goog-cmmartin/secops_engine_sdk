"""Acceptance Tests for Milestone 6.6: SOAR Ingestion Connectors and Webhooks.

Verifies live Google SecOps API interactions, engine workflows, domain models,
and capability registrations against live tenant endpoints.
"""

from tests.test_helpers import get_live_adapter, get_live_engine
import unittest
from engine.facade import SecOpsEngine
from engine.domain import (
    SoarIngestionConnectorSummary,
    SoarIngestionConnectorDetail,
    SoarIngestionConnectorBatch,
    SoarWebhookSummary,
    SoarWebhookDetail,
    SoarWebhookBatch,
)


class TestMilestone66IngestionConnectorsAndWebhooks(unittest.TestCase):
    """Live acceptance tests for Milestone 6.6 SOAR Ingestion Connectors and Webhooks."""

    @classmethod
    def setUpClass(cls):
        cls.engine = get_live_engine()

    # 1. SOAR Ingestion Connectors
    def test_search_soar_ingestion_connectors(self):
        """Verifies searching and listing SOAR ingestion connector instances."""
        batch = self.engine.search_soar_ingestion_connectors(limit=50)
        self.assertIsInstance(batch, SoarIngestionConnectorBatch)
        self.assertGreaterEqual(batch.total_count, 1)
        self.assertGreaterEqual(len(batch.connectors), 1)

        first_c = batch.connectors[0]
        self.assertIsInstance(first_c, SoarIngestionConnectorSummary)
        self.assertTrue(first_c.id)
        self.assertTrue(first_c.name)
        self.assertTrue(first_c.display_name)
        self.assertTrue(first_c.integration)
        self.assertIsInstance(first_c.enabled, bool)
        self.assertIsInstance(first_c.remote, bool)
        self.assertIsInstance(first_c.interval_seconds, int)

        # Test query filtering
        filtered = self.engine.search_soar_ingestion_connectors(query="DTM", limit=10)
        self.assertIsInstance(filtered, SoarIngestionConnectorBatch)
        for c in filtered.connectors:
            self.assertTrue(
                "dtm" in c.display_name.lower()
                or "dtm" in c.identifier.lower()
                or "dtm" in c.integration.lower()
            )

    def test_get_soar_ingestion_connector(self):
        """Verifies deep inspection of a single SOAR ingestion connector instance."""
        batch = self.engine.search_soar_ingestion_connectors(limit=1)
        self.assertGreaterEqual(len(batch.connectors), 1)
        target = batch.connectors[0]

        detail = self.engine.get_soar_ingestion_connector(
            instance_id=target.id,
            integration=target.integration or "-",
            connector_id=target.connector_id or "-",
        )
        self.assertIsInstance(detail, SoarIngestionConnectorDetail)
        self.assertIsInstance(detail.summary, SoarIngestionConnectorSummary)
        self.assertEqual(detail.summary.id, target.id)
        self.assertTrue(detail.summary.display_name)
        self.assertIsInstance(detail.parameters, list)
        self.assertIsInstance(detail.status, str)
        self.assertTrue(detail.raw)
        self.assertIsNotNone(detail.retrieved_at)

    # 2. SOAR Ingestion Webhooks
    def test_search_soar_webhooks(self):
        """Verifies searching and listing SOAR event ingestion webhooks."""
        batch = self.engine.search_soar_webhooks(limit=50)
        self.assertIsInstance(batch, SoarWebhookBatch)
        self.assertGreaterEqual(batch.total_count, 1)
        self.assertGreaterEqual(len(batch.webhooks), 1)

        first_wh = batch.webhooks[0]
        self.assertIsInstance(first_wh, SoarWebhookSummary)
        self.assertTrue(first_wh.id)
        self.assertTrue(first_wh.name)
        self.assertTrue(first_wh.display_name)
        self.assertIsInstance(first_wh.enabled, bool)

        # Test query filtering
        filtered = self.engine.search_soar_webhooks(query="Demoverse", limit=10)
        self.assertIsInstance(filtered, SoarWebhookBatch)
        for wh in filtered.webhooks:
            self.assertTrue(
                "demoverse" in wh.display_name.lower()
                or "demoverse" in wh.description.lower()
                or "demoverse" in wh.id.lower()
            )

    def test_get_soar_webhook(self):
        """Verifies deep inspection and JSON schema mapping for a single SOAR event ingestion webhook."""
        batch = self.engine.search_soar_webhooks(limit=1)
        self.assertGreaterEqual(len(batch.webhooks), 1)
        target_id = batch.webhooks[0].id

        detail = self.engine.get_soar_webhook(target_id)
        self.assertIsInstance(detail, SoarWebhookDetail)
        self.assertIsInstance(detail.summary, SoarWebhookSummary)
        self.assertEqual(detail.summary.id, target_id)
        self.assertTrue(detail.summary.display_name)
        self.assertIsInstance(detail.webhook_mapping, dict)
        self.assertTrue(detail.raw)
        self.assertIsNotNone(detail.retrieved_at)

    # 3. Capability Registrations
    def test_capability_registrations(self):
        """Verifies that all Milestone 6.6 capabilities are properly registered in the registry."""
        capabilities = self.engine.list_capabilities(category="soar_settings")
        cap_ids = [c.capability_id for c in capabilities]

        expected_caps = [
            "soar.ingestion_connector.search",
            "soar.ingestion_connector.get",
            "soar.webhook.search",
            "soar.webhook.get",
        ]

        for exp in expected_caps:
            self.assertIn(exp, cap_ids, f"Expected capability '{exp}' was not registered.")


if __name__ == "__main__":
    unittest.main()
