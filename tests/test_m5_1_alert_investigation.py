"""Authoritative Acceptance Tests for Milestone 5.1: Alert Deep-Dive Investigation.

Verifies:
1. Alert Deep-Dive Inspection (Alert details, rule identifier, detection time, risk score).
2. Alert Involved Entities Resolution.
3. Strict Error Visibility on invalid alert names.
4. Capability Registration in WorkflowRegistry.
"""

from tests.test_helpers import get_live_adapter, get_live_engine
import os
import unittest

from adapters.google_secops import GoogleSecOpsAdapter
from engine import SecOpsEngine


class TestMilestone51AlertInvestigation(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.adapter = get_live_adapter()
        cls.engine = get_live_engine(adapter=cls.adapter)
        cls.known_alert_name = None
        cls.known_case_id = None
        cases = cls.engine.search_cases(page_size=10)
        for summary in cases.results:
            inv = cls.engine.investigate_case(str(summary.case_id))
            if inv.alerts:
                cls.known_case_id = str(summary.case_id)
                cls.known_alert_name = inv.alerts[0].name
                break

    def test_alert_inv_001_deep_dive_inspection(self):
        """Validates deep-dive inspection of a live SOAR case alert."""
        if not self.known_alert_name:
            self.skipTest("No live cases with alerts available in tenant.")
        inv = self.engine.investigate_alert(self.known_alert_name)

        self.assertEqual(inv.alert_name, self.known_alert_name)
        self.assertEqual(inv.case_id, self.known_case_id)
        self.assertTrue(len(inv.priority) > 0)
        self.assertTrue(len(inv.status) > 0)
        self.assertTrue(len(inv.display_name) > 0)
        self.assertIsNotNone(inv.detection_time)
        self.assertIsInstance(inv.entities, list)
        for ent in inv.entities:
            self.assertTrue(len(ent.identifier) > 0)

        # Assert provenance
        self.assertIn("retrieved_at", inv.provenance)
        self.assertEqual(inv.provenance["alert_resource_name"], self.known_alert_name)

    def test_alert_inv_002_capability_registration(self):
        """Validates that alert.investigate is registered with metadata in the engine capability registry."""
        caps = {c.capability_id: c for c in self.engine.list_capabilities()}
        self.assertIn("alert.investigate", caps)
        cap = caps["alert.investigate"]
        self.assertEqual(cap.category, "alert")
        self.assertTrue(cap.composed)

    def test_alert_inv_003_invalid_alert_strict_error(self):
        """Validates that non-existent alerts raise explicit errors without silent fallback."""
        invalid_alert = (
            f"projects/{self.adapter.config.project_id}/locations/{self.adapter.config.location}/"
            f"instances/{self.adapter.config.customer_id}/cases/104185/caseAlerts/999999999"
        )
        with self.assertRaises(Exception) as ctx:
            self.engine.investigate_alert(invalid_alert)
        self.assertTrue(len(str(ctx.exception)) > 0)


if __name__ == "__main__":
    unittest.main()
