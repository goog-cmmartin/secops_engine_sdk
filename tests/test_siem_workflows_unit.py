"""Unit tests for Layer 4a SIEM workflow fixes."""

import unittest
from datetime import timezone
from unittest.mock import MagicMock

from engine.config import SecOpsConfigurationError
from engine.domain import (
    CaseSearchBatch,
    DimensionCardinality,
    EnterpriseIocBatch,
    EntityCardinalityRecord,
    EntityCardinalityReport,
    EntitySummaryResult,
    EntityType,
    FindingsRefinementTestResult,
    RuleCaseHistoryBatch,
    SearchSession,
)
from engine.workflows.dashboard_health import _parse_timestamp as parse_dash_ts
from engine.workflows.data_tables import _parse_timestamp as parse_dt_ts
from engine.workflows.detection_tuning import (
    DiagnoseAndTuneDetectionWorkflow,
    translate_to_udm_refinement,
)
from engine.workflows.entity_search import (
    InvestigateEntityWorkflow,
    SearchEntityGraphWorkflow,
)
from engine.workflows.raw_log_search import ValidateRawLogQueryWorkflow
from engine.workflows.refine_search import SearchFromEntityWorkflow
from engine.workflows.siem_settings import GetLogProcessingPipelineDetailWorkflow


class TestSiemWorkflowsUnit(unittest.TestCase):
    """Unit tests covering Layer 4a SIEM workflow edge cases."""

    def test_translate_to_udm_refinement_preserves_leading_e(self):
        """Fields starting with 'e' must not have their leading character stripped."""
        self.assertEqual(
            translate_to_udm_refinement("extensions.auth.type", "AUTHTYPE_UNSPECIFIED", is_regex=False),
            '(extensions.auth.type = "AUTHTYPE_UNSPECIFIED")',
        )
        self.assertEqual(
            translate_to_udm_refinement("$e.principal.ip", "10.0.0.1", is_regex=True),
            "(principal.ip = /10.0.0.1/)",
        )
        self.assertEqual(
            translate_to_udm_refinement("$e1.event.idm.read_only_udm.target.hostname", "host.corp", is_regex=True),
            "(target.hostname = /host.corp/)",
        )
        self.assertEqual(
            translate_to_udm_refinement("target.process.command_line", 'C:\\temp\\"cmd.exe"', is_regex=False),
            '(target.process.command_line = "C:\\\\temp\\\\\\"cmd.exe\\"")',
        )

    def test_diagnose_and_tune_dimension_fallback_mappings(self):
        """Fallback dimension mappings distinguish src_ip, src_hostname, and target_user."""
        adapter = MagicMock()
        adapter.get_curated_rule.return_value = {
            "displayName": "Test Curated Rule",
            "text": "rule test {}",
        }
        cardinality_wf = MagicMock()
        cardinality_wf.execute.return_value = EntityCardinalityReport(
            rule_id="ur_123",
            rule_name="Test Curated Rule",
            dimensions=[
                DimensionCardinality(
                    dimension="src_ip",
                    subfield_path="",
                    records=[EntityCardinalityRecord(value="192.0.2.99", count=42)],
                    total_distinct_values=1,
                ),
                DimensionCardinality(
                    dimension="target_user",
                    subfield_path="",
                    records=[EntityCardinalityRecord(value="svc-admin", count=10)],
                    total_distinct_values=1,
                ),
            ],
        )
        case_wf = MagicMock()
        case_wf.execute.return_value = RuleCaseHistoryBatch(
            rule_id="ur_123", cases=[], total_cases=0
        )
        test_wf = MagicMock()
        test_wf.execute.return_value = FindingsRefinementTestResult(
            curated_rule_id="ur_123",
            query="(src.ip = /192.0.2.99/)",
            total_detections=50,
            excluded_detections=42,
            suppression_ratio=0.84,
        )

        wf = DiagnoseAndTuneDetectionWorkflow(adapter, cardinality_wf, case_wf, test_wf)
        report = wf.execute(rule_id="ur_123", lookback_days=7)
        self.assertEqual(report.proposed_refinement_query, "(src.ip = /192.0.2.99/)")

    def test_search_from_entity_file_type_and_default_times(self):
        """SearchFromEntityWorkflow supports EntityType.FILE, string coercion, and default time windows."""
        q = SearchFromEntityWorkflow.build_entity_query("file", 'C:\\Windows\\System32\\cmd.exe')
        self.assertIn('target.file.full_path = "C:\\\\Windows\\\\System32\\\\cmd.exe"', q)

        search_udm_wf = MagicMock()
        wf = SearchFromEntityWorkflow(search_udm_wf)
        wf.execute(entity_type=EntityType.FILE, entity_value="/usr/bin/curl")
        self.assertTrue(search_udm_wf.execute.called)
        req = search_udm_wf.execute.call_args.kwargs["request"]
        self.assertIsNotNone(req.start_time)
        self.assertIsNotNone(req.end_time)

    def test_investigate_entity_populates_udm_events_and_summary(self):
        """InvestigateEntityWorkflow resolves default times and invokes summarize_entity_wf."""
        search_graph_wf = MagicMock()
        graph_session = MagicMock(spec=SearchSession)
        graph_session.events = [{"metadata": {"entityId": "ent-999"}}]
        search_graph_wf.execute.return_value = graph_session

        search_from_entity_wf = MagicMock()
        udm_session = MagicMock(spec=SearchSession)
        udm_session.events = [{"metadata": {"id": "ev-1"}}]
        search_from_entity_wf.execute.return_value = udm_session

        search_iocs_wf = MagicMock()
        search_iocs_wf.execute.return_value = EnterpriseIocBatch(
            matches=[], total_count=0, searched_value="8.8.8.8", value_type="ARTIFACT_INDICATOR_VALUE_ASSET_IP"
        )

        search_cases_wf = MagicMock()
        search_cases_wf.execute.return_value = CaseSearchBatch(
            results=[], total_count=0, page_size=20, page_number=0
        )

        summarize_entity_wf = MagicMock()
        expected_summary = EntitySummaryResult(
            entity_id="ent-999",
            entity_type="ASSET",
            timeline=[],
            prevalence={},
            file_metadata={},
            entities=[],
            raw={},
        )
        summarize_entity_wf.execute.return_value = expected_summary

        wf = InvestigateEntityWorkflow(
            search_graph_wf=search_graph_wf,
            search_from_entity_wf=search_from_entity_wf,
            search_iocs_wf=search_iocs_wf,
            search_cases_wf=search_cases_wf,
            summarize_entity_wf=summarize_entity_wf,
        )
        report = wf.execute("8.8.8.8")
        self.assertEqual(report.udm_events_count, 1)
        self.assertIsNotNone(report.entity_summary)
        self.assertEqual(report.entity_summary.entity_id, "ent-999")
        # Ensure search_from_entity_wf received non-None start_time and end_time
        call_kwargs = search_from_entity_wf.execute.call_args.kwargs
        self.assertIsNotNone(call_kwargs["start_time"])
        self.assertIsNotNone(call_kwargs["end_time"])

    def test_search_entity_graph_escapes_backslashes(self):
        """SearchEntityGraphWorkflow escapes backslashes when value is supplied."""
        search_udm_wf = MagicMock()
        wf = SearchEntityGraphWorkflow(search_udm_wf)
        wf.execute("file.full_path", value='C:\\Temp\\"evil.exe"')
        req = search_udm_wf.execute.call_args.kwargs["request"]
        self.assertEqual(req.query, 'graph.entity.file.full_path = "C:\\\\Temp\\\\\\"evil.exe\\""')

    def test_validate_raw_log_query_propagates_config_errors(self):
        """ValidateRawLogQueryWorkflow re-raises SecOpsConfigurationError."""
        adapter = MagicMock()
        adapter.validate_raw_log_query.side_effect = SecOpsConfigurationError("Missing customer_id")
        wf = ValidateRawLogQueryWorkflow(adapter)
        with self.assertRaises(SecOpsConfigurationError):
            wf.execute("raw = /test/")

        adapter.validate_raw_log_query.side_effect = RuntimeError("Syntax error at token 1")
        res = wf.execute("raw = /test/")
        self.assertFalse(res.is_valid)
        self.assertIn("Syntax error", res.error_message)

    def test_parse_timestamp_with_fractional_seconds_and_offset(self):
        """_parse_timestamp handles both Z and +00:00 with fractional seconds."""
        for parser_fn in (parse_dash_ts, parse_dt_ts):
            dt1 = parser_fn("2026-09-01T12:30:45.123456+00:00")
            self.assertIsNotNone(dt1)
            self.assertEqual(dt1.tzinfo, timezone.utc)
            self.assertEqual(dt1.microsecond, 123456)

            dt2 = parser_fn("2026-09-01T12:30:45.5Z")
            self.assertIsNotNone(dt2)
            self.assertEqual(dt2.tzinfo, timezone.utc)
            self.assertEqual(dt2.microsecond, 500000)

    def test_get_log_processing_pipeline_skips_list_for_full_resource_name(self):
        """GetLogProcessingPipelineDetailWorkflow does not list pipelines when given a projects/... path."""
        adapter = MagicMock()
        adapter.get_log_processing_pipeline.return_value = {
            "name": "projects/p/locations/us/instances/c/logProcessingPipelines/short-id",
            "displayName": "My Pipeline",
            "processors": [],
        }
        wf = GetLogProcessingPipelineDetailWorkflow(adapter)
        detail = wf.execute("projects/p/locations/us/instances/c/logProcessingPipelines/short-id")
        self.assertEqual(detail.summary.id, "short-id")
        adapter.list_log_processing_pipelines.assert_not_called()
        adapter.get_log_processing_pipeline.assert_called_once_with("short-id")


if __name__ == "__main__":
    unittest.main()
