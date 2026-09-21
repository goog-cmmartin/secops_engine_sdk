"""Unit and behavioral tests for FleetScheduler and Proactive Deacon Patrols."""

import asyncio
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Any

from agents.core.fleet_scheduler import FleetScheduler, DEFAULT_AGENT_SCHEDULES
from agents.core.evidence_store import LocalFileEvidenceStore
from clients.web.chat_engine import ChatStore


class PatrolAgentFixture:
    """Agent implementation for testing Deacon patrol sweeps."""

    def __init__(self, name: str, handle: str):
        self.name = name
        self.handle = handle
        self.executed_tool_calls = []

    def audit_feeds(self, lookback_days: int = 7):
        return {
            "status": "SUCCESS",
            "summary": {
                "total_feeds_audited": 4,
                "healthy_count": 3,
                "irregular_count": 0,
                "failed_count": 1,
                "high_latency_count": 1,
                "quota_rejections_detected": False,
            },
            "findings": [
                {
                    "feed_id": "feed_azure_activedirectory_99",
                    "feed_name": "Azure AD Ingestion",
                    "log_type": "AZURE_AD",
                    "status": "FAILED",
                    "latency_p95": 5.2,
                    "anomaly_description": "HTTP 503 Service Unavailable on transport endpoint",
                }
            ],
            "widget": None,
        }

    def audit_parsers(self, lookback_days: int = 7):
        return {
            "status": "SUCCESS",
            "summary": {
                "total_parsers_audited": 3,
                "healthy_count": 2,
                "failed_count": 1,
                "irregular_count": 0,
                "version_drift_count": 1,
                "extension_conflict_count": 0,
            },
            "findings": [
                {
                    "log_type": "WINEVTLOG",
                    "status": "FAILED",
                    "drop_reason_code": "DROP_CODE_1",
                    "unparsed_count": 420,
                }
            ],
            "widget": None,
        }

    def find_noisy_rules(self, lookback_days: int = 14, limit: int = 20):
        return {
            "status": "SUCCESS",
            "total_rules": 1,
            "total_detections": 8500,
            "lookback_window": "14 days",
            "rules": [
                {
                    "rule_id": "ru_suspicious_powershell_encoded",
                    "rule_name": "Suspicious Encoded PowerShell Execution",
                    "rule_type": "SINGLE_EVENT",
                    "alert_state": "ALERTING",
                    "detection_count": 8500,
                    "ratio_of_total": 0.65,
                }
            ],
        }

    def run_decay_synchronization(self, lookback_days: int = 90):
        return {
            "status": "SUCCESS",
            "total_rules": 25,
            "broken_count": 2,
            "silent_count": 5,
            "average_dps": 0.4,
            "widget": None,
        }

    def run_identity_drift_audit(self):
        return {
            "status": "SUCCESS",
            "total_users": 150,
            "total_groups": 12,
            "custom_roles_count": 4,
            "project_id": "secops-prod-99",
            "drift": {
                "has_drift": True,
                "summary": "Unsanctioned roles/owner grant detected for svc-pipeline@external",
            },
            "widget": None,
        }

    def audit_tenant_posture(self, snapshot: bool = True):
        return {
            "status": "SUCCESS",
            "tenant_id": "PREVIEWAMERICASSDL",
            "snapshot_id": "baseline_test_123",
            "fingerprint": "21cbdba884ef5de272b8bbe670210fbe73f225decd08e2ffc3af93c6f2b44e48",
            "has_drift": True,
            "drift_count": 1,
            "critical_changes_count": 0,
            "high_changes_count": 1,
            "subsystems_drifted": ["governance"],
            "drift_summary": "Data RBAC enabled altered from False to True",
            "widget": None,
        }


class TestFleetScheduler(unittest.IsolatedAsyncioTestCase):
    """Verifies agent schedule management and periodic Deacon patrol triggers."""

    async def test_scheduler_lifecycle_and_all_default_patrols(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root_dir = Path(tmpdir)
            evidence_store = LocalFileEvidenceStore(root_dir=root_dir)
            chat_store = ChatStore(root_dir=root_dir)

            scheduler = FleetScheduler(
                fleet={},
                evidence_store=evidence_store,
                chat_store=chat_store,
                poll_interval_seconds=1,
            )

            # Verify all 6 default domain patrol schedules are present and enabled
            expected_handles = [
                "@feed-agent",
                "@parser-doctor",
                "@detection-tuning-agent",
                "@detection-decay-agent",
                "@identity-governor",
                "@tenant-posture-agent",
            ]
            for handle in expected_handles:
                sched = scheduler.get_schedule(handle)
                self.assertIsNotNone(sched, f"Schedule missing for {handle}")
                self.assertTrue(sched.get("enabled"), f"Schedule not enabled for {handle}")
                self.assertIn("action", sched)
                self.assertIn("interval_hours", sched)
                self.assertIn("stream", sched)
                self.assertIn("topic", sched)

            # Check Deacon Status
            status = scheduler.get_deacon_status()
            self.assertEqual(status["active_patrols"], 6)
            self.assertEqual(status["total_patrols_run"], 0)
            self.assertIn("Active", status["deacon_heartbeat"])

            # Update schedule
            updated = scheduler.update_schedule(
                "@detection-decay-agent",
                {"interval_hours": 12, "lookback_days": 60},
            )
            self.assertEqual(updated["interval_hours"], 12)
            self.assertEqual(updated["lookback_days"], 60)

            # Verify persisted to evidence store
            loaded = evidence_store.get_agent_config("@detection-decay-agent")
            self.assertEqual(loaded.get("interval_hours"), 12)

            # Trigger immediate run on unconfigured fleet member gracefully
            result = await scheduler.trigger_run_now("@unknown-agent")
            self.assertEqual(result.get("status"), "ERROR")
            self.assertIn("not found", result.get("message", "").lower())

    async def test_patrol_execution_and_bead_creation(self):
        """Verifies that running patrols creates beads in Evidence Fabric and posts to ChatStore."""
        with tempfile.TemporaryDirectory() as tmpdir:
            root_dir = Path(tmpdir)
            evidence_store = LocalFileEvidenceStore(root_dir=root_dir)
            chat_store = ChatStore(root_dir=root_dir)

            fleet = {
                "@feed-agent": PatrolAgentFixture("Feed Health Agent", "@feed-agent"),
                "@parser-doctor": PatrolAgentFixture("Parser Doctor", "@parser-doctor"),
                "@detection-tuning-agent": PatrolAgentFixture("Detection Tuning Agent", "@detection-tuning-agent"),
                "@detection-decay-agent": PatrolAgentFixture("Detection Decay Agent", "@detection-decay-agent"),
                "@identity-governor": PatrolAgentFixture("Identity Governor", "@identity-governor"),
                "@tenant-posture-agent": PatrolAgentFixture("Tenant Posture Governor", "@tenant-posture-agent"),
            }

            scheduler = FleetScheduler(
                fleet=fleet,
                evidence_store=evidence_store,
                chat_store=chat_store,
                poll_interval_seconds=1,
            )

            # 1. Run @feed-agent patrol -> should detect failed feed and sling an ingestion bead
            feed_res = await scheduler.trigger_run_now("@feed-agent")
            self.assertEqual(feed_res["status"], "SUCCESS")
            created_feed_beads = feed_res.get("created_beads", [])
            self.assertGreater(len(created_feed_beads), 0)
            self.assertTrue(created_feed_beads[0].startswith("todo_feed_"))

            # Verify bead stored in Evidence Fabric
            saved_feed_todo = evidence_store.get_todo(created_feed_beads[0])
            self.assertIsNotNone(saved_feed_todo)
            self.assertEqual(saved_feed_todo["target_agent"], "@feed-agent")
            self.assertEqual(saved_feed_todo["action_type"], "remediate_feed")

            # 2. Run @parser-doctor patrol -> should detect WINEVTLOG drop and sling a parser bead
            parser_res = await scheduler.trigger_run_now("@parser-doctor")
            self.assertEqual(parser_res["status"], "SUCCESS")
            created_parser_beads = parser_res.get("created_beads", [])
            self.assertGreater(len(created_parser_beads), 0)
            self.assertTrue(created_parser_beads[0].startswith("todo_parser_winevtlog_"))

            # 3. Run @detection-tuning-agent patrol -> should flag noisy rule and generate data_table widget
            tuning_res = await scheduler.trigger_run_now("@detection-tuning-agent")
            self.assertEqual(tuning_res["status"], "SUCCESS")
            created_tuning_beads = tuning_res.get("created_beads", [])
            self.assertGreater(len(created_tuning_beads), 0)

            # 4. Run @detection-decay-agent patrol
            decay_res = await scheduler.trigger_run_now("@detection-decay-agent")
            self.assertEqual(decay_res["status"], "SUCCESS")

            # 5. Run @identity-governor patrol -> should flag IAM drift
            iam_res = await scheduler.trigger_run_now("@identity-governor")
            self.assertEqual(iam_res["status"], "SUCCESS")

            # 6. Run @tenant-posture-agent patrol -> should flag posture drift and sling posture bead
            posture_res = await scheduler.trigger_run_now("@tenant-posture-agent")
            self.assertEqual(posture_res["status"], "SUCCESS")
            created_posture_beads = posture_res.get("created_beads", [])
            self.assertGreater(len(created_posture_beads), 0)
            self.assertTrue(created_posture_beads[0].startswith("todo_posture_drift_"))

            # Verify bead stored in Evidence Fabric
            saved_posture_todo = evidence_store.get_todo(created_posture_beads[0])
            self.assertIsNotNone(saved_posture_todo)
            self.assertEqual(saved_posture_todo["target_agent"], "@tenant-posture-agent")
            self.assertEqual(saved_posture_todo["action_type"], "posture_remediation")

            # Verify ChatStore has messages with domain formatters
            feed_msgs = chat_store.list_messages("ingestion", "feed-health")
            self.assertGreater(len(feed_msgs), 0)
            self.assertIn("Deacon Autonomous Patrol: Feed Health Agent", feed_msgs[-1].content)
            self.assertIn("Audited Ingestion Feeds", feed_msgs[-1].content)

            parser_msgs = chat_store.list_messages("ingestion", "parser-drops")
            self.assertGreater(len(parser_msgs), 0)
            self.assertIn("Deacon Autonomous Patrol: Parser Doctor", parser_msgs[-1].content)

            posture_msgs = chat_store.list_messages("governance", "tenant-posture")
            self.assertGreater(len(posture_msgs), 0)
            self.assertIn("Deacon Autonomous Patrol: Tenant Posture Governor", posture_msgs[-1].content)
            self.assertIn("Baseline Snapshot", posture_msgs[-1].content)

            # Verify Deacon telemetry
            deacon_status = scheduler.get_deacon_status()
            self.assertEqual(deacon_status["total_patrols_run"], 6)
            self.assertEqual(len(deacon_status["recent_patrols"]), 6)

    async def test_trigger_patrol_all(self):
        """Verifies bulk fleet sweep executes across all 6 agents."""
        with tempfile.TemporaryDirectory() as tmpdir:
            root_dir = Path(tmpdir)
            evidence_store = LocalFileEvidenceStore(root_dir=root_dir)
            chat_store = ChatStore(root_dir=root_dir)

            fleet = {
                "@feed-agent": PatrolAgentFixture("Feed Health Agent", "@feed-agent"),
                "@parser-doctor": PatrolAgentFixture("Parser Doctor", "@parser-doctor"),
                "@detection-tuning-agent": PatrolAgentFixture("Detection Tuning Agent", "@detection-tuning-agent"),
                "@detection-decay-agent": PatrolAgentFixture("Detection Decay Agent", "@detection-decay-agent"),
                "@identity-governor": PatrolAgentFixture("Identity Governor", "@identity-governor"),
                "@tenant-posture-agent": PatrolAgentFixture("Tenant Posture Governor", "@tenant-posture-agent"),
            }

            scheduler = FleetScheduler(
                fleet=fleet,
                evidence_store=evidence_store,
                chat_store=chat_store,
                poll_interval_seconds=1,
            )

            bulk_res = await scheduler.trigger_patrol_all()
            self.assertEqual(bulk_res["status"], "SUCCESS")
            self.assertEqual(bulk_res["executed_count"], 6)
            self.assertEqual(len(bulk_res["results"]), 6)
            self.assertEqual(bulk_res["deacon_status"]["total_patrols_run"], 6)


if __name__ == "__main__":
    unittest.main()
