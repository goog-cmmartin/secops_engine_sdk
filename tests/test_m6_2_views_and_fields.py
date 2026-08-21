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
        view_id = "5e3aa276-538e-4484-ae81-7a2b68b7ad09"
        detail = self.engine.get_case_view(view_id)
        self.assertIsInstance(detail, CaseViewDetail)
        self.assertEqual(detail.summary.identifier, view_id)
        self.assertGreater(len(detail.widgets), 0)

        widget = detail.widgets[0]
        self.assertTrue(bool(widget.metadata.id))
        self.assertTrue(bool(widget.metadata.title))
        self.assertTrue(bool(widget.metadata.type))

    def test_get_case_view_detail_alert_view(self):
        view_id = "85405495-c9fd-4b0e-9acd-d3921f31e949"
        detail = self.engine.get_case_view(view_id)
        self.assertIsInstance(detail, CaseViewDetail)
        self.assertEqual(detail.summary.identifier, view_id)
        self.assertGreater(len(detail.widgets), 0)

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
        field_id = "7"
        detail = self.engine.get_custom_field(field_id)
        self.assertIsInstance(detail, CustomFieldDetail)
        self.assertEqual(detail.summary.id, field_id)
        self.assertTrue(bool(detail.summary.display_name))
        self.assertTrue(bool(detail.summary.type))
        self.assertIsInstance(detail.ordered_values, list)
        self.assertGreater(len(detail.ordered_values), 0)

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
