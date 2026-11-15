#!/usr/bin/env python3
"""Acceptance Tests for Milestone 6.2: SOAR Case Views, Custom Fields & Calculated Fields.

Validates end-to-end live API execution for:
- Case & Alert Views (discovery, filtering, deep layout and widget inspection)
- Custom Fields (discovery across Case/Alert scopes, type definitions, ordered values)
- Calculated Fields (formula definitions, target fields, enablement state)
- Engine Facade Capability Registrations
"""

from tests.test_helpers import get_live_adapter, get_live_engine
import unittest
from adapters.google_secops import GoogleSecOpsAdapter
from engine import (
    CalculatedFieldBatch,
    CalculatedFieldDetail,
    CaseViewBatch,
    CaseViewDetail,
    CustomFieldBatch,
    CustomFieldDetail,
    SecOpsEngine,
)


class TestMilestone62ViewsAndFields(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.adapter = get_live_adapter()
        cls.engine = get_live_engine(adapter=cls.adapter)

    def test_search_case_views(self):
        batch = self.engine.search_case_views(limit=10)
        self.assertIsInstance(batch, CaseViewBatch)
        self.assertGreater(batch.total_count, 0)
        self.assertGreater(len(batch.views), 0)

        view = batch.views[0]
        self.assertTrue(bool(view.id))
        self.assertTrue(bool(view.identifier))
        self.assertTrue(bool(view.name))

    def test_get_case_view_detail_case_overview(self):
        batch = self.engine.search_case_views(limit=10)
        if not batch.views:
            self.skipTest("No case views available in live tenant.")
        view_id = batch.views[0].identifier
        detail = self.engine.get_case_view(view_id)
        self.assertIsInstance(detail, CaseViewDetail)
        self.assertEqual(detail.summary.identifier, view_id)
        self.assertGreater(len(detail.widgets), 0)

        widget = detail.widgets[0]
        self.assertTrue(bool(widget.metadata.id))
        self.assertTrue(bool(widget.metadata.title))
        self.assertTrue(bool(widget.metadata.type))

    def test_get_case_view_detail_alert_view(self):
        batch = self.engine.search_case_views(limit=10)
        if len(batch.views) < 2:
            self.skipTest("Fewer than 2 case/alert views available in live tenant.")
        view_id = batch.views[1].identifier
        detail = self.engine.get_case_view(view_id)
        self.assertIsInstance(detail, CaseViewDetail)
        self.assertEqual(detail.summary.identifier, view_id)
        self.assertIsInstance(detail.widgets, list)

    def test_search_custom_fields(self):
        batch = self.engine.search_custom_fields(limit=20)
        self.assertIsInstance(batch, CustomFieldBatch)
        self.assertGreater(batch.total_count, 0)
        self.assertGreater(len(batch.custom_fields), 0)

        cf = batch.custom_fields[0]
        self.assertTrue(bool(cf.id))
        self.assertTrue(bool(cf.display_name))
        self.assertTrue(bool(cf.type))
        self.assertTrue(bool(cf.scopes))

    def test_get_custom_field_detail(self):
        batch = self.engine.search_custom_fields(limit=10)
        if not batch.custom_fields:
            self.skipTest("No custom fields configured in live tenant.")
        field_id = batch.custom_fields[0].id
        detail = self.engine.get_custom_field(field_id)
        self.assertIsInstance(detail, CustomFieldDetail)
        self.assertEqual(detail.summary.id, field_id)
        self.assertTrue(bool(detail.summary.display_name))
        self.assertTrue(bool(detail.summary.type))
        self.assertIsInstance(detail.ordered_values, list)

    def test_search_calculated_fields(self):
        batch = self.engine.search_calculated_fields(limit=20)
        self.assertIsInstance(batch, CalculatedFieldBatch)
        self.assertIsInstance(batch.definitions, list)
        self.assertGreaterEqual(batch.total_count, 0)

    def test_facade_capability_registration(self):
        caps = self.engine.list_capabilities(category="case_config")
        cap_ids = {c.capability_id for c in caps}

        expected_caps = [
            "case_config.view.search",
            "case_config.view.get",
            "case_config.custom_field.search",
            "case_config.custom_field.get",
            "case_config.calculated_field.search",
            "case_config.calculated_field.get",
        ]
        for ec in expected_caps:
            self.assertIn(ec, cap_ids)


if __name__ == "__main__":
    unittest.main()
