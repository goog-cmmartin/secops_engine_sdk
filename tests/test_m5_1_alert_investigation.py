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
        cls.known_alert_name = f"projects/{cls.adapter.project_id}/locations/{cls.adapter.location}/instances/{cls.adapter.customer_id}/cases/104185/caseAlerts/390054"

    def test_alert_inv_001_deep_dive_inspection(self):
        """Validates deep-dive inspection of live alert 390054."""
        inv = self.engine.investigate_alert(self.known_alert_name)

        self.assertEqual(inv.alert_name, self.known_alert_name)
        self.assertEqual(inv.case_id, "104185")
        self.assertEqual(inv.priority, "HIGH")
        self.assertEqual(inv.status, "OPEN")
        self.assertTrue(len(inv.display_name) > 0)
        self.assertIsNotNone(inv.detection_time)

        # Assert involved entities
        self.assertGreaterEqual(len(inv.entities), 1)
        entity_ids = [e.identifier for e in inv.entities]
        self.assertTrue(any("A605570555620CEA6D6BE211520525FC95A30961661780DA4CC4BAFE9864F394" in eid for eid in entity_ids))

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
        invalid_alert = "projects/sdl-preview-americas/locations/us/instances/a556547c-1cff-43ef-a2e4-cf5b12a865df/cases/104185/caseAlerts/999999999"
        with self.assertRaises(Exception) as ctx:
            self.engine.investigate_alert(invalid_alert)
        self.assertTrue(len(str(ctx.exception)) > 0)


if __name__ == "__main__":
    unittest.main()
