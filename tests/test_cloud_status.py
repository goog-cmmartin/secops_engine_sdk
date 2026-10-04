"""Tests for Google Cloud SecOps Service Status Workflow, Domain Models, and Agent."""

import unittest
from datetime import datetime, timezone
from engine.domain import (
    CloudStatusIncident,
    CloudStatusLocation,
    CloudStatusReport,
    CloudStatusUpdate,
)
from engine.facade import SecOpsEngine
from engine.workflows.cloud_status import (
    audit_cloud_service_status,
    correlate_incident_with_telemetry,
    fetch_security_incidents,
)
from agents.generated.cloud_status import CloudStatusAgent
from agents.core.fleet_scheduler import DEFAULT_AGENT_SCHEDULES, FleetScheduler


class TestCloudStatusWorkflow(unittest.TestCase):
    def test_domain_model_parsing_and_serialization(self):
        raw_incident = {
            "id": "TEST_INCIDENT_01",
            "number": "2026-001",
            "begin": "2026-09-25T12:00:00+00:00",
            "end": None,
            "modified": "2026-09-25T13:00:00+00:00",
            "external_desc": "Google SecOps customers are experiencing delays in europe-west3",
            "status_impact": "SERVICE_DISRUPTION",
            "severity": "medium",
            "service_key": "FHwvkSZ6RzzDYAvDZXMM",
            "service_name": "Google SecOps",
            "affected_products": [{"title": "Google SecOps", "id": "FHwvkSZ6RzzDYAvDZXMM"}],
            "currently_affected_locations": [{"id": "europe-west3", "title": "Frankfurt (europe-west3)"}],
            "previously_affected_locations": [],
            "updates": [
                {
                    "created": "2026-09-25T12:05:00+00:00",
                    "modified": "2026-09-25T12:05:00+00:00",
                    "when": "2026-09-25T12:05:00+00:00",
                    "text": "Mitigation in progress by engineering.",
                    "status": "SERVICE_DISRUPTION",
                    "affected_locations": [{"id": "europe-west3", "title": "Frankfurt"}],
                }
            ],
            "uri": "incidents/TEST_INCIDENT_01",
        }

        incident = CloudStatusIncident.from_dict(raw_incident)
        self.assertEqual(incident.id, "TEST_INCIDENT_01")
        self.assertEqual(incident.service_name, "Google SecOps")
        self.assertTrue(incident.is_active)
        self.assertEqual(incident.public_url, "https://status.cloud.google.com/security/incidents/TEST_INCIDENT_01")
        self.assertEqual(len(incident.updates), 1)
        self.assertEqual(incident.most_recent_update.status, "SERVICE_DISRUPTION")

        # Test serialization
        d = incident.to_dict()
        self.assertEqual(d["id"], "TEST_INCIDENT_01")
        self.assertTrue(d["is_active"])
        self.assertEqual(d["public_url"], "https://status.cloud.google.com/security/incidents/TEST_INCIDENT_01")

    def test_live_fetch_security_incidents(self):
        """Fetches live incidents from status.cloud.google.com and validates schemas."""
        incidents = fetch_security_incidents(service_name="Google SecOps", lookback_days=60)
        self.assertIsInstance(incidents, list)
        self.assertGreater(len(incidents), 0, "Expected at least 1 incident in live 60-day status feed")
        first = incidents[0]
        self.assertIsInstance(first, CloudStatusIncident)
        self.assertTrue(first.id)
        self.assertTrue(first.service_name)
        self.assertTrue(first.public_url.startswith("https://status.cloud.google.com/security/incidents/"))

    def test_live_audit_cloud_service_status(self):
        """Generates comprehensive status report from live endpoint."""
        report = audit_cloud_service_status(service_name="Google SecOps", lookback_days=14)
        self.assertIsInstance(report, CloudStatusReport)
        self.assertIn(report.overall_health, ["HEALTHY", "DEGRADED", "OUTAGE", "ADVISORY"])
        self.assertIsInstance(report.active_incidents, list)
        self.assertIsInstance(report.recent_resolved, list)
        self.assertEqual(report.total_incidents, len(report.active_incidents) + len(report.recent_resolved))

    def test_correlate_incident_with_telemetry(self):
        """Tests incident correlation and operational guidance generation."""
        # Query recent resolved incident from today
        incidents = fetch_security_incidents(service_name="Google SecOps", lookback_days=3)
        if incidents:
            target_id = incidents[0].id
            res = correlate_incident_with_telemetry(target_id)
            self.assertEqual(res["incident_id"], target_id)
            self.assertIn("correlated_recommendation", res)
            self.assertTrue(res["public_url"])

    def test_engine_facade_methods(self):
        """Validates that SecOpsEngine facade exposes and executes cloud status capabilities."""
        engine = SecOpsEngine()
        incidents = engine.query_cloud_status_incidents(service_name="Google SecOps", lookback_days=14)
        self.assertIsInstance(incidents, list)

        report = engine.audit_cloud_service_status(lookback_days=14)
        self.assertIsInstance(report, CloudStatusReport)

        # Check capability registration
        cap_query = engine.registry.get("gcp_status.incidents.query")
        self.assertIsNotNone(cap_query)
        self.assertEqual(cap_query.category, "gcp_status")
        self.assertEqual(cap_query.kind, "query")
        self.assertEqual(cap_query.cardinality, "bounded")

        cap_report = engine.registry.get("gcp_status.report.audit")
        self.assertIsNotNone(cap_report)
        self.assertEqual(cap_report.category, "gcp_status")
        self.assertEqual(cap_report.kind, "query")
        self.assertEqual(cap_report.cardinality, "single")

    def test_adk_cloud_status_agent_initialization(self):
        """Validates that the generated CloudStatusAgent initializes properly with capabilities."""
        agent = CloudStatusAgent()
        self.assertEqual(agent.handle, "@cloud-status-agent")
        self.assertEqual(agent.role, "Google Cloud SecOps Service Status & Outage Specialist")
        self.assertIn("gcp_status.incidents.query", agent.CAPABILITIES)
        self.assertIn("gcp_status.report.audit", agent.CAPABILITIES)

    def test_fleet_scheduler_cloud_status_wiring(self):
        """Validates that FleetScheduler includes 30-minute schedule for @cloud-status-agent."""
        self.assertIn("@cloud-status-agent", DEFAULT_AGENT_SCHEDULES)
        sched = DEFAULT_AGENT_SCHEDULES["@cloud-status-agent"]
        self.assertEqual(sched["action"], "audit_cloud_service_status")
        self.assertEqual(sched["interval_hours"], 0.5)
        self.assertEqual(sched["stream"], "infrastructure")
        self.assertEqual(sched["topic"], "service-status")


if __name__ == "__main__":
    unittest.main()
