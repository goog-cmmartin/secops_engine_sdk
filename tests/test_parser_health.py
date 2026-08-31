"""Unit tests for Parser Health Audit Workflow."""

import unittest
from unittest.mock import MagicMock

from engine.domain import (
    ParserBatch,
    ParserExtensionBatch,
    ParserExtensionSummary,
    ParserHealthFinding,
    ParserHealthReport,
    ParserHealthStatus,
    ParserSummary,
)
from engine.facade import SecOpsEngine
from engine.workflows.health_utils import DeepDiveTelemetry
from engine.workflows.parser_health import AuditParserHealthWorkflow


class TestParserHealthAudit(unittest.TestCase):
    """Tests for AuditParserHealthWorkflow and finding classifications."""

    def setUp(self):
        self.engine = SecOpsEngine()
        self.workflow = AuditParserHealthWorkflow(self.engine.adapter)

    def test_capability_registration(self):
        """Verifies parser.audit_health capability is properly registered."""
        cap = self.engine.registry.get("parser.audit_health")
        self.assertIsNotNone(cap)
        self.assertEqual(cap.category, "parser")
        self.assertEqual(cap.domain, "parser")
        self.assertEqual(cap.kind, "workflow")
        self.assertTrue(cap.composed)
        self.assertIn("parser.search", cap.uses)
        self.assertIn("dashboard.execute_query", cap.uses)

    def test_evaluate_healthy_parser(self):
        """Verifies healthy parser classification."""
        parser = ParserSummary(
            name="projects/123/locations/us/instances/abc/logTypes/OK_LOG/parsers/1",
            id="1",
            log_type="OK_LOG",
            creator_source="GOOGLE",
            create_time="2026-01-01T00:00:00Z",
            type="LOGSTASH",
            state="ACTIVE",
            release_stage="GA",
            version="1.0",
            latest_version="1.0",
            rollback_available=False,
            raw={},
        )
        finding = self.workflow._evaluate_parser(
            log_type="OK_LOG",
            parser=parser,
            extension=None,
            telemetry={"status": "Healthy"},
            deep_dive_telemetry=DeepDiveTelemetry(),
        )
        self.assertEqual(finding.status, ParserHealthStatus.HEALTHY)
        self.assertEqual(finding.log_type, "OK_LOG")
        self.assertIn("healthy", finding.anomaly_description.lower())

    def test_evaluate_failed_parser_with_zscore(self):
        """Verifies critical/failed parser classification with z-score anomaly detail."""
        parser = ParserSummary(
            name="projects/123/locations/us/instances/abc/logTypes/FAIL_LOG/parsers/2",
            id="2",
            log_type="FAIL_LOG",
            creator_source="GOOGLE",
            create_time="2026-01-01T00:00:00Z",
            type="LOGSTASH",
            state="ACTIVE",
            release_stage="GA",
            version="1.0",
            latest_version="1.0",
            rollback_available=False,
            raw={},
        )
        deep_dive = DeepDiveTelemetry(
            parser_errors_by_log_type={
                "FAIL_LOG": [{"issue": "decreased by 100.0% relative to baseline with z-score 2.5"}]
            },
            volume_funnel_by_log_type={
                "FAIL_LOG": {"total_logs": 500, "normalized_events": 0, "parsing_error_events": 500}
            },
        )
        finding = self.workflow._evaluate_parser(
            log_type="FAIL_LOG",
            parser=parser,
            extension=None,
            telemetry={
                "status": "Critical",
                "latest_drop_reason_code": "Normalization volume ratio is unhealthy.",
                "anomalous_since": "2026-08-28 21:13:02",
            },
            deep_dive_telemetry=deep_dive,
        )
        self.assertEqual(finding.status, ParserHealthStatus.FAILED)
        self.assertEqual(finding.drop_reason_code, "Normalization volume ratio is unhealthy.")
        self.assertEqual(finding.zscore_anomaly_detail, "decreased by 100.0% relative to baseline with z-score 2.5")
        self.assertEqual(finding.volume_funnel.get("parsing_error_events"), 500)
        self.assertTrue(len(finding.remediation_steps) > 0)

    def test_evaluate_version_drift(self):
        """Verifies version drift detection when an updated Google parser is available."""
        parser = ParserSummary(
            name="projects/123/locations/us/instances/abc/logTypes/DRIFT_LOG/parsers/3",
            id="3",
            log_type="DRIFT_LOG",
            creator_source="GOOGLE",
            create_time="2026-01-01T00:00:00Z",
            type="LOGSTASH",
            state="ACTIVE",
            release_stage="GA",
            version="5.0",
            latest_version="7.0",
            rollback_available=True,
            raw={},
        )
        finding = self.workflow._evaluate_parser(
            log_type="DRIFT_LOG",
            parser=parser,
            extension=None,
            telemetry={"status": "Healthy"},
            deep_dive_telemetry=DeepDiveTelemetry(),
        )
        self.assertEqual(finding.status, ParserHealthStatus.VERSION_DRIFT)
        self.assertIn("v5.0", finding.anomaly_description)
        self.assertIn("v7.0", finding.anomaly_description)

    def test_evaluate_extension_conflict(self):
        """Verifies extension error status."""
        parser = ParserSummary(
            name="projects/123/locations/us/instances/abc/logTypes/EXT_LOG/parsers/4",
            id="4",
            log_type="EXT_LOG",
            creator_source="GOOGLE",
            create_time="2026-01-01T00:00:00Z",
            type="LOGSTASH",
            state="ACTIVE",
            release_stage="GA",
            version="1.0",
            latest_version="1.0",
            rollback_available=False,
            raw={},
        )
        ext = ParserExtensionSummary(
            name="projects/123/locations/us/instances/abc/logTypes/EXT_LOG/parserExtensions/ext-1",
            id="ext-1",
            log_type="EXT_LOG",
            state="ERROR",
            create_time="2026-01-01T00:00:00Z",
            state_last_changed_time="2026-01-01T00:00:00Z",
            has_dynamic_parsing=True,
            opted_fields_count=2,
            has_cbn_snippet=True,
            raw={},
        )
        finding = self.workflow._evaluate_parser(
            log_type="EXT_LOG",
            parser=parser,
            extension=ext,
            telemetry={"status": "Healthy"},
            deep_dive_telemetry=DeepDiveTelemetry(),
        )
        self.assertEqual(finding.status, ParserHealthStatus.EXTENSION_CONFLICT)
        self.assertTrue(finding.has_extension)
        self.assertEqual(finding.opted_fields_count, 2)


if __name__ == "__main__":
    unittest.main()
