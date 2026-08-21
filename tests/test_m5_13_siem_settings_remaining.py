#!/usr/bin/env python3
"""Acceptance Tests for Milestone 5.13: Remaining SIEM Settings & Enrichment Controls.

Validates end-to-end live API execution for:
- Enrichment Combinations (discovery catalog)
- Deployed Enrichment Controls (search and deep inspection)
- Gemini Triage & Investigation Agent Settings
- UEBA Entity Risk Scoring Configuration
- Root Tenant Instance Details and Feature Flags
"""

from tests.test_helpers import get_live_adapter, get_live_engine
import unittest
from adapters.google_secops import GoogleSecOpsAdapter
from engine import (
    EnrichmentCombinationBatch,
    EnrichmentControlBatch,
    EnrichmentControlDetail,
    EntityRiskConfig,
    GeminiAgentSettings,
    SecOpsEngine,
    TenantInstanceDetails,
)


class TestMilestone513SiemSettingsRemaining(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.adapter = get_live_adapter()
        cls.engine = get_live_engine(adapter=cls.adapter)

    def test_list_enrichment_combinations(self):
        batch = self.engine.list_enrichment_combinations(limit=10)
        self.assertIsInstance(batch, EnrichmentCombinationBatch)
        self.assertGreater(batch.total_count, 0)
        self.assertGreater(len(batch.records), 0)

        record = batch.records[0]
        self.assertTrue(bool(record.enrichment_type))
        self.assertTrue(bool(record.target_log_type))
        self.assertTrue(bool(record.external_source or record.source_log_type))

    def test_search_enrichment_controls(self):
        batch = self.engine.search_enrichment_controls(limit=5)
        self.assertIsInstance(batch, EnrichmentControlBatch)
        self.assertGreater(batch.total_count, 0)
        self.assertGreater(len(batch.controls), 0)

        ctrl = batch.controls[0]
        self.assertTrue(bool(ctrl.id))
        self.assertTrue(bool(ctrl.enrichment_type))
        self.assertTrue(bool(ctrl.target_log_type))

    def test_get_enrichment_control_detail(self):
        # Fetch first control ID to inspect
        batch = self.engine.search_enrichment_controls(limit=1)
        self.assertGreater(len(batch.controls), 0)
        target_id = batch.controls[0].id

        detail = self.engine.get_enrichment_control(target_id)
        self.assertIsInstance(detail, EnrichmentControlDetail)
        self.assertEqual(detail.summary.id, target_id)
        self.assertIsInstance(detail.records, list)

    def test_get_gemini_agent_settings(self):
        settings = self.engine.get_agent_settings()
        self.assertIsInstance(settings, GeminiAgentSettings)
        self.assertTrue(bool(settings.name))
        self.assertIsInstance(settings.auto_investigation_enabled, bool)
        self.assertTrue(bool(settings.auto_quota_limit))

    def test_get_entity_risk_config(self):
        risk = self.engine.get_entity_risk_config()
        self.assertIsInstance(risk, EntityRiskConfig)
        self.assertTrue(bool(risk.name))
        self.assertGreaterEqual(risk.default_detection_risk_score, 0)
        self.assertGreaterEqual(risk.default_alert_risk_score, 0)

    def test_get_tenant_instance_details(self):
        tenant = self.engine.get_tenant_instance()
        self.assertIsInstance(tenant, TenantInstanceDetails)
        self.assertTrue(bool(tenant.id))
        self.assertEqual(tenant.state, "ACTIVE")
        self.assertTrue(bool(tenant.customer_code))
        self.assertGreater(len(tenant.secops_urls), 0)

    def test_facade_capability_registration(self):
        caps = self.engine.list_capabilities()
        cap_ids = [c.capability_id for c in caps]

        self.assertIn("enrichment.combination.list", cap_ids)
        self.assertIn("enrichment.control.search", cap_ids)
        self.assertIn("enrichment.control.get", cap_ids)
        self.assertIn("siem.agent_settings.get", cap_ids)
        self.assertIn("siem.risk_config.get", cap_ids)
        self.assertIn("siem.tenant.get", cap_ids)


if __name__ == "__main__":
    unittest.main()
