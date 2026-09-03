"""Tests for Feed Health Audit Workflow (Milestone 8.1)."""

import unittest
from datetime import datetime, timezone
from unittest.mock import MagicMock

from engine.domain import (
    DashboardBatch,
    DashboardChart,
    DashboardDetail,
    DashboardQuery,
    DashboardQueryResult,
    DashboardSummary,
    FeedBatch,
    FeedHealthFinding,
    FeedHealthReport,
    FeedHealthStatus,
    FeedSummary,
)
from engine.facade import SecOpsEngine
from engine.workflows.feed_health import AuditFeedHealthWorkflow
from engine.workflows.health_utils import DeepDiveTelemetry
from tests.test_helpers import get_live_engine


class TestFeedHealthWorkflow(unittest.TestCase):
    """Unit tests for Feed Health evaluation and classification."""

    def test_evaluate_healthy_feed(self):
        adapter = MagicMock()
        wf = AuditFeedHealthWorkflow(adapter)

        feed = FeedSummary(
            id="feed-1",
            name="projects/1/locations/us/instances/a/feeds/feed-1",
            display_name="CrowdStrike EDR",
            state="ACTIVE",
            feed_source_type="AMAZON_S3_V2",
            log_type="CS_EDR",
            raw={"lastFeedInitiationTime": "2026-08-29T16:00:00Z"},
        )

        finding = wf._evaluate_feed(feed, telemetry_map={}, deep_dive_telemetry=DeepDiveTelemetry())
        self.assertEqual(finding.status, FeedHealthStatus.HEALTHY)
        self.assertEqual(finding.feed_name, "CrowdStrike EDR")
        self.assertIn("normal", finding.anomaly_description)

    def test_evaluate_failed_state_feed(self):
        adapter = MagicMock()
        wf = AuditFeedHealthWorkflow(adapter)

        feed = FeedSummary(
            id="feed-2",
            name="projects/1/locations/us/instances/a/feeds/feed-2",
            display_name="Failing S3 Feed",
            state="FAILED",
            feed_source_type="AMAZON_S3_V2",
            log_type="AWS_CLOUDTRAIL",
            raw={},
        )

        finding = wf._evaluate_feed(feed, telemetry_map={}, deep_dive_telemetry=DeepDiveTelemetry())
        self.assertEqual(finding.status, FeedHealthStatus.FAILED)
        self.assertIn("FAILED state", finding.anomaly_description)
        self.assertTrue(len(finding.remediation_steps) > 0)

    def test_evaluate_irregular_telemetry_feed(self):
        adapter = MagicMock()
        wf = AuditFeedHealthWorkflow(adapter)

        feed = FeedSummary(
            id="feed-3",
            name="projects/1/locations/us/instances/a/feeds/feed-3",
            display_name="Irregular PubSub Feed",
            state="ACTIVE",
            feed_source_type="HTTPS_PUSH_GOOGLE_CLOUD_PUBSUB",
            log_type="GCP_RUN",
            raw={},
        )

        telemetry_map = {
            "feed-3": {
                "chart_signals": ["IRREGULAR"],
                "latency": "5s",
                "health_status": "IRREGULAR",
                "raw_rows": [],
            }
        }

        finding = wf._evaluate_feed(feed, telemetry_map=telemetry_map, deep_dive_telemetry=DeepDiveTelemetry())
        self.assertEqual(finding.status, FeedHealthStatus.IRREGULAR)
        self.assertIn("IRREGULAR", finding.anomaly_description)

    def test_evaluate_high_latency_feed(self):
        adapter = MagicMock()
        wf = AuditFeedHealthWorkflow(adapter)

        feed = FeedSummary(
            id="feed-4",
            name="projects/1/locations/us/instances/a/feeds/feed-4",
            display_name="Delayed Syslog Feed",
            state="ACTIVE",
            feed_source_type="API",
            log_type="OKTA",
            raw={"lastFeedInitiationTime": "2026-08-29T10:00:00Z"},
        )

        telemetry_map = {
            "feed-4": {
                "chart_signals": [],
                "latency": "2 hr 15 min",
                "health_status": None,
                "raw_rows": [],
            }
        }

        finding = wf._evaluate_feed(feed, telemetry_map=telemetry_map, deep_dive_telemetry=DeepDiveTelemetry())
        self.assertEqual(finding.status, FeedHealthStatus.HIGH_LATENCY)
        self.assertIn("High ingestion latency", finding.anomaly_description)

    def test_evaluate_quota_rejection_telemetry(self):
        adapter = MagicMock()
        wf = AuditFeedHealthWorkflow(adapter)

        feed = FeedSummary(
            id="feed-5",
            name="projects/1/locations/us/instances/a/feeds/feed-5",
            display_name="High Burst Syslog",
            state="ACTIVE",
            feed_source_type="API",
            log_type="SYSLOG",
            raw={},
        )

        deep_dive = DeepDiveTelemetry(
            quota_rejected_volume_mb={"SYSLOG": 25.4},
            quota_limit_mb_per_sec={"SYSLOG": 10.0},
            volume_funnel_by_log_type={"SYSLOG": {"total_logs": 1000, "normalized_events": 900, "parsing_error_events": 100}},
        )

        finding = wf._evaluate_feed(feed, telemetry_map={}, deep_dive_telemetry=deep_dive)
        self.assertEqual(finding.quota_rejected_volume_mb, 25.4)
        self.assertEqual(finding.quota_limit_mb_per_sec, 10.0)
        self.assertEqual(finding.volume_funnel.get("total_logs"), 1000)

    def test_capability_registered_on_engine(self):
        engine = SecOpsEngine()
        cap = engine.registry.get("feed.audit_health")
        self.assertIsNotNone(cap)
        self.assertEqual(cap.category, "feed")
        self.assertEqual(cap.domain, "feed")
        self.assertEqual(cap.kind, "workflow")
        self.assertIn("feed.search", cap.uses)


if __name__ == "__main__":
    unittest.main()
