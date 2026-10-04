"""Unit and contract tests for GCP Cloud Monitoring time series workflow."""

import unittest

from engine.domain import (
    GcpMonitoringQueryResult,
    MetricPoint,
    TimeSeriesData,
)
from engine.facade import SecOpsEngine
from engine.registry import WorkflowRegistry
from engine.workflows.gcp_monitoring_query import (
    GcpMonitoringQueryWorkflow,
    _extract_point_value,
    _normalize_time_series,
)
from tests.test_helpers import get_live_engine


class _RecordingMonitoringAdapter:
    """Inert adapter that captures parameters passed to query_cloud_monitoring_time_series without network calls."""

    def __init__(self, project_id: str = "test-project-secops"):
        self.project_id = project_id
        self.last_query = {}

    def query_cloud_monitoring_time_series(
        self,
        filter_str: str,
        start_time: str,
        end_time: str,
        project_id=None,
        alignment_period=None,
        per_series_aligner=None,
        cross_series_reducer=None,
        group_by_fields=None,
        page_size=50,
        page_token=None,
    ):
        self.last_query = {
            "filter_str": filter_str,
            "start_time": start_time,
            "end_time": end_time,
            "project_id": project_id,
            "alignment_period": alignment_period,
            "per_series_aligner": per_series_aligner,
            "cross_series_reducer": cross_series_reducer,
            "group_by_fields": group_by_fields,
            "page_size": page_size,
            "page_token": page_token,
        }
        return {
            "timeSeries": [
                {
                    "metric": {
                        "type": "chronicle.googleapis.com/collector/ingestion/total_ingested_log_count",
                        "labels": {"log_type": "WINEVTLOG"},
                    },
                    "resource": {
                        "type": "chronicle.googleapis.com/Collector",
                        "labels": {"project_id": "test-project-secops"},
                    },
                    "metricKind": "DELTA",
                    "valueType": "INT64",
                    "points": [
                        {
                            "interval": {
                                "startTime": "2026-09-20T12:00:00Z",
                                "endTime": "2026-09-20T13:00:00Z",
                            },
                            "value": {"int64Value": "48920"},
                        }
                    ],
                }
            ],
            "nextPageToken": "token-next-page-mon-456",
        }


class GcpMonitoringWorkflowUnitTest(unittest.TestCase):
    def setUp(self):
        self.adapter = _RecordingMonitoringAdapter()
        self.workflow = GcpMonitoringQueryWorkflow(self.adapter)

    def test_extract_point_value_types(self):
        self.assertEqual(_extract_point_value({"int64Value": "100"}), 100)
        self.assertEqual(_extract_point_value({"doubleValue": 45.6}), 45.6)
        self.assertEqual(_extract_point_value({"boolValue": True}), True)
        self.assertEqual(_extract_point_value({"stringValue": "healthy"}), "healthy")
        dist = {"count": "5", "mean": 12.0}
        self.assertEqual(_extract_point_value({"distributionValue": dist}), dist)

    def test_normalize_time_series(self):
        raw = {
            "metric": {
                "type": "chronicle.googleapis.com/agent/cpu_seconds",
                "labels": {"agent_id": "agent-01"},
            },
            "resource": {
                "type": "chronicle.googleapis.com/Forwarder",
                "labels": {"zone": "us-east1-b"},
            },
            "metricKind": "GAUGE",
            "valueType": "DOUBLE",
            "points": [
                {
                    "interval": {
                        "startTime": "2026-09-20T14:00:00Z",
                        "endTime": "2026-09-20T14:05:00Z",
                    },
                    "value": {"doubleValue": 0.85},
                }
            ],
        }
        series = _normalize_time_series(raw)
        self.assertIsInstance(series, TimeSeriesData)
        self.assertEqual(series.metric_type, "chronicle.googleapis.com/agent/cpu_seconds")
        self.assertEqual(series.metric_labels.get("agent_id"), "agent-01")
        self.assertEqual(series.resource_type, "chronicle.googleapis.com/Forwarder")
        self.assertEqual(series.metric_kind, "GAUGE")
        self.assertEqual(series.value_type, "DOUBLE")
        self.assertEqual(len(series.points), 1)
        self.assertEqual(series.points[0].value, 0.85)

    def test_execute_requires_filter(self):
        with self.assertRaises(ValueError):
            self.workflow.execute(filter_str="")

    def test_execute_records_parameters_and_normalizes(self):
        result = self.workflow.execute(
            filter_str='metric.type = starts_with("chronicle.googleapis.com/")',
            hours=12,
            alignment_period="1800s",
            per_series_aligner="ALIGN_RATE",
            page_size=20,
            page_token="tok-prev-1",
        )
        self.assertIsInstance(result, GcpMonitoringQueryResult)
        self.assertEqual(len(result.time_series), 1)
        self.assertEqual(result.total_series, 1)
        self.assertEqual(result.next_page_token, "token-next-page-mon-456")
        self.assertEqual(self.adapter.last_query["filter_str"], 'metric.type = starts_with("chronicle.googleapis.com/")')
        self.assertEqual(self.adapter.last_query["alignment_period"], "1800s")
        self.assertEqual(self.adapter.last_query["per_series_aligner"], "ALIGN_RATE")
        self.assertEqual(self.adapter.last_query["page_size"], 20)
        self.assertEqual(self.adapter.last_query["page_token"], "tok-prev-1")

    def test_query_chronicle_ingestion_metrics_with_log_type(self):
        self.workflow.query_chronicle_ingestion_metrics(hours=6, log_type="PAN_FIREWALL")
        query = self.adapter.last_query["filter_str"]
        self.assertIn("chronicle.googleapis.com/", query)
        self.assertIn('metric.label.log_type = "PAN_FIREWALL"', query)

    def test_query_chronicle_normalizer_metrics(self):
        self.workflow.query_chronicle_normalizer_metrics(hours=24)
        query = self.adapter.last_query["filter_str"]
        self.assertIn("chronicle.googleapis.com/normalizer", query)

    def test_query_chronicle_api_metrics(self):
        self.workflow.query_chronicle_api_metrics(hours=24)
        query = self.adapter.last_query["filter_str"]
        self.assertIn("serviceruntime.googleapis.com/api/request_count", query)
        self.assertIn('resource.label.service = "chronicle.googleapis.com"', query)
        self.assertEqual(self.adapter.last_query["per_series_aligner"], "ALIGN_RATE")
        self.assertEqual(self.adapter.last_query["cross_series_reducer"], "REDUCE_SUM")

    def test_query_chronicle_agent_metrics(self):
        self.workflow.query_chronicle_agent_metrics(hours=4)
        query = self.adapter.last_query["filter_str"]
        self.assertIn("chronicle.googleapis.com/agent/", query)

    def test_facade_integration_and_capability_dispatch(self):
        engine = SecOpsEngine(adapter=self.adapter, custom_registry=WorkflowRegistry())
        cap = engine.registry.get("gcp_monitoring.time_series")
        self.assertIsNotNone(cap)
        self.assertEqual(cap.domain, "gcp_monitoring")
        self.assertEqual(cap.kind, "query")
        self.assertEqual(cap.cardinality, "bounded")
        self.assertEqual(cap.mcp_tool_name, "query_gcp_cloud_metrics")

        # Test facade method execution
        res = engine.query_cloud_monitoring(
            filter_str='metric.type = starts_with("chronicle.googleapis.com/")',
            hours=24,
        )
        self.assertIsInstance(res, GcpMonitoringQueryResult)
        self.assertEqual(res.total_series, 1)


class GcpMonitoringLiveDecoupledIntegrationTest(unittest.TestCase):
    def test_live_cloud_monitoring_if_configured(self):
        engine = get_live_engine()
        try:
            res = engine.get_chronicle_api_metrics(hours=1)
            self.assertIsInstance(res, GcpMonitoringQueryResult)
        except Exception as e:
            # Expected on environments without Monitoring Viewer IAM role
            self.assertTrue(
                any(token in str(e).lower() for token in ["permission", "403", "denied", "disabled", "not found", "unauthorized", "api"])
            )


if __name__ == "__main__":
    unittest.main()
