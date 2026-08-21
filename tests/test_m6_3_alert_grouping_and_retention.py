#!/usr/bin/env python3
"""Acceptance Tests for Milestone 6.3: SOAR Alert Grouping & Data Retention Settings.

Validates end-to-end live API execution for:
- Alert Grouping Rules (discovery, category filtering, keyword search, deep inspection)
- Alert Grouping Global Settings (timeframes, limits, algorithm type)
- SOAR Data Retention Settings (retention period in months, environment policy)
- Engine Facade Capability Registrations
"""

from tests.test_helpers import get_live_adapter, get_live_engine
import unittest
from adapters.google_secops import GoogleSecOpsAdapter
from engine import (
    AlertGroupingRuleBatch,
    AlertGroupingRuleDetail,
    AlertGroupingSettingsBatch,
    DataRetentionSettingsBatch,
    SecOpsEngine,
)


class TestMilestone63AlertGroupingAndRetention(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.adapter = get_live_adapter()
        cls.engine = get_live_engine(adapter=cls.adapter)

    def test_search_alert_grouping_rules(self):
        batch = self.engine.search_alert_grouping_rules(limit=10)
        self.assertIsInstance(batch, AlertGroupingRuleBatch)
        self.assertGreater(batch.total_count, 0)
        self.assertGreater(len(batch.rules), 0)

        rule = batch.rules[0]
        self.assertTrue(bool(rule.id))
        self.assertTrue(bool(rule.name))
        self.assertTrue(bool(rule.category))
        self.assertTrue(bool(rule.grouping_type))

    def test_search_alert_grouping_rules_with_category_filter(self):
        batch = self.engine.search_alert_grouping_rules(category="ALL")
        self.assertIsInstance(batch, AlertGroupingRuleBatch)
        self.assertGreater(len(batch.rules), 0)
        for r in batch.rules:
            self.assertEqual(r.category, "ALL")

    def test_get_alert_grouping_rule_rule_1(self):
        detail = self.engine.get_alert_grouping_rule("1")
        self.assertIsInstance(detail, AlertGroupingRuleDetail)
        self.assertEqual(detail.summary.id, "1")
        self.assertEqual(detail.summary.category, "ALL")
        self.assertEqual(detail.summary.grouping_type, "ENTITIES")
        self.assertGreater(len(detail.summary.entity_types), 0)
        self.assertIn("SourceUserName", detail.summary.entity_types)

    def test_get_alert_grouping_rule_rule_17(self):
        detail = self.engine.get_alert_grouping_rule("17")
        self.assertIsInstance(detail, AlertGroupingRuleDetail)
        self.assertEqual(detail.summary.id, "17")
        self.assertEqual(detail.summary.category, "ALERT_TYPE")
        self.assertGreater(len(detail.category_details), 0)

        first_cd = detail.category_details[0]
        self.assertTrue(bool(first_cd.identifier))
        self.assertTrue(bool(first_cd.display_name))

    def test_get_alert_grouping_settings(self):
        batch = self.engine.get_alert_grouping_settings()
        self.assertIsInstance(batch, AlertGroupingSettingsBatch)
        self.assertGreater(batch.total_count, 0)
        self.assertGreater(len(batch.properties), 0)

        keys = [p.property_key for p in batch.properties]
        self.assertIn("TimeframeForGroupingInHours", keys)
        self.assertIn("GroupingAlgorithmType", keys)

    def test_get_data_retention_settings(self):
        batch = self.engine.get_data_retention_settings()
        self.assertIsInstance(batch, DataRetentionSettingsBatch)
        self.assertGreater(batch.total_count, 0)
        self.assertGreater(len(batch.properties), 0)

        keys = [p.property_key for p in batch.properties]
        self.assertIn("DataRetentionPeriodInMonths", keys)

    def test_facade_capabilities_registration(self):
        caps = self.engine.list_capabilities()
        cap_ids = [c.capability_id for c in caps]

        self.assertIn("case_config.alert_grouping.rule.search", cap_ids)
        self.assertIn("case_config.alert_grouping.rule.get", cap_ids)
        self.assertIn("case_config.alert_grouping.settings.get", cap_ids)
        self.assertIn("soar.data_retention.get", cap_ids)


if __name__ == "__main__":
    unittest.main()
