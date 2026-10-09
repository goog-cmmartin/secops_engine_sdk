"""Tests for Chronicle ingestion metrics over Cloud Monitoring (get_chronicle_ingestion_metrics).

Pure tests use a recording adapter (no network). The live test SkipTests unless
SECOPS_LIVE_TESTS=1 and a tenant is configured (tests/test_helpers.py).
"""

import unittest
from typing import Any, Dict, List, Optional

from engine.domain import ChronicleIngestionMetricsResult, MetricPoint, TimeSeriesData
from engine.facade import SecOpsEngine
from engine.registry import WorkflowRegistry
from engine.workflows.gcp_monitoring_query import (
    GcpMonitoringQueryWorkflow,
    build_chronicle_ingestion_filter,
    parse_ingestion_series,
    resolve_chronicle_ingestion_metric,
)
from tests.test_helpers import get_live_engine


def _series(log_type: Optional[str], points: List[tuple]) -> Dict[str, Any]:
    labels = {"project_id": "p"}
    if log_type:
        labels["log_type"] = log_type
    return {
        "metric": {"type": "chronicle.googleapis.com/ingestion/log/record_count"},
        "resource": {"type": "chronicle.googleapis.com/Collector", "labels": labels},
        "metricKind": "DELTA",
        "valueType": "INT64",
        "points": [{"interval": {"startTime": s, "endTime": e}, "value": {"int64Value": str(v)}} for s, e, v in points],
    }


class _PagedMonitoringAdapter:
    """Returns pre-defined pages of Cloud Monitoring responses and records every call."""

    project_id = "proj-1"

    def __init__(self, pages: List[Dict[str, Any]]):
        self.pages = pages
        self.calls: List[Dict[str, Any]] = []

    def query_cloud_monitoring_time_series(self, **kwargs):
        self.calls.append(kwargs)
        page = self.pages[len(self.calls) - 1]
        if isinstance(page, Exception):
            raise page
        return page


class TestFilterBuilding(unittest.TestCase):
    def test_single_metric_type_no_starts_with(self):
        f = build_chronicle_ingestion_filter("ingestion/log/record_count")
        self.assertEqual(
            f,
            'metric.type = "chronicle.googleapis.com/ingestion/log/record_count" '
            'AND resource.type = "chronicle.googleapis.com/Collector"',
        )
        self.assertNotIn("starts_with", f)

    def test_log_type_uses_resource_label(self):
        f = build_chronicle_ingestion_filter("ingestion/log/bytes_count", ["WINEVTLOG"])
        self.assertIn('resource.label.log_type = "WINEVTLOG"', f)
        self.assertNotIn("metric.label.log_type", f)

    def test_multiple_log_types_use_one_of(self):
        f = build_chronicle_ingestion_filter("normalizer/log/record_count", ["A_B", "C"])
        self.assertIn('resource.label.log_type = one_of("A_B", "C")', f)

    def test_full_metric_name_accepted(self):
        self.assertEqual(
            resolve_chronicle_ingestion_metric("chronicle.googleapis.com/ingestion/log/bytes_count"),
            "chronicle.googleapis.com/ingestion/log/bytes_count",
        )

    def test_unknown_metric_rejected(self):
        with self.assertRaises(ValueError) as ctx:
            build_chronicle_ingestion_filter("agent/cpu_seconds")
        self.assertIn("Allowed", str(ctx.exception))

    def test_log_type_injection_rejected(self):
        with self.assertRaises(ValueError):
            build_chronicle_ingestion_filter("ingestion/log/record_count", ['X" OR metric.type = "y'])


class TestSeriesQueryAndParsing(unittest.TestCase):
    def test_grouped_query_parameters_pagination_and_parsing(self):
        adapter = _PagedMonitoringAdapter([
            {"timeSeries": [_series("BRO_JSON", [("t2", "t3", 30), ("t1", "t2", 10)])], "nextPageToken": "tok"},
            {"timeSeries": [_series("WINEVTLOG", [("t1", "t2", 5)]), _series("BRO_JSON", [("t3", "t4", 1)])]},
        ])
        res = GcpMonitoringQueryWorkflow(adapter).query_chronicle_ingestion_series(
            lookback_hours=6, log_types=["BRO_JSON", "WINEVTLOG"], alignment_period_s=1800
        )
        self.assertIsInstance(res, ChronicleIngestionMetricsResult)
        self.assertEqual(len(adapter.calls), 2)
        first = adapter.calls[0]
        self.assertEqual(first["alignment_period"], "1800s")
        self.assertEqual(first["per_series_aligner"], "ALIGN_SUM")
        self.assertEqual(first["cross_series_reducer"], "REDUCE_SUM")
        self.assertEqual(first["group_by_fields"], ["resource.label.log_type"])
        self.assertIsNone(first["page_token"])
        self.assertEqual(adapter.calls[1]["page_token"], "tok")

        self.assertEqual(res.pages_fetched, 2)
        self.assertEqual(res.metric_type, "chronicle.googleapis.com/ingestion/log/record_count")
        self.assertEqual(res.project_id, "proj-1")
        self.assertEqual(res.filter_applied, first["filter_str"])
        self.assertEqual([s.log_type for s in res.series], ["BRO_JSON", "WINEVTLOG"])
        bro = res.series[0]
        self.assertEqual([(p.start, p.value) for p in bro.points], [("t1", 10), ("t2", 30), ("t3", 1)])
        self.assertEqual(bro.total, 41)
        self.assertEqual(res.total_series, 3)
        self.assertEqual(res.to_dict()["series"][0]["points"][0], {"start": "t1", "end": "t2", "value": 10})

    def test_ungrouped_collapses_to_all(self):
        adapter = _PagedMonitoringAdapter([{"timeSeries": [_series(None, [("t1", "t2", 7)])]}])
        res = GcpMonitoringQueryWorkflow(adapter).query_chronicle_ingestion_series(group_by_log_type=False)
        self.assertIsNone(adapter.calls[0]["group_by_fields"])
        self.assertEqual(res.series[0].log_type, "ALL")
        self.assertEqual(res.group_by_fields, [])

    def test_parse_dedupes_duplicate_intervals(self):
        ts = TimeSeriesData(metric_type="m", resource_labels={"log_type": "X"},
                            points=[MetricPoint("a", "b", 1), MetricPoint("a", "b", 99)])
        out = parse_ingestion_series([ts], group_by_log_type=True)
        self.assertEqual([(p.start, p.value) for p in out[0].points], [("a", 1)])

    def test_api_errors_propagate(self):
        adapter = _PagedMonitoringAdapter([RuntimeError("403 monitoring.timeSeries.list denied")])
        with self.assertRaises(RuntimeError):
            GcpMonitoringQueryWorkflow(adapter).query_chronicle_ingestion_series()

    def test_facade_aliases_hours_and_log_type(self):
        adapter = _PagedMonitoringAdapter([{"timeSeries": []}])
        engine = SecOpsEngine(adapter=adapter, custom_registry=WorkflowRegistry())
        res = engine.get_chronicle_ingestion_metrics(hours=12, log_type="WINEVTLOG", metric="ingestion/log/bytes_count")
        self.assertIn('resource.label.log_type = "WINEVTLOG"', adapter.calls[0]["filter_str"])
        self.assertIn("ingestion/log/bytes_count", adapter.calls[0]["filter_str"])
        self.assertEqual(res.series, [])


class TestChronicleIngestionMetricsLive(unittest.TestCase):
    def test_live_record_count_by_log_type(self):
        engine = get_live_engine()
        res = engine.get_chronicle_ingestion_metrics(lookback_hours=24)
        self.assertEqual(res.metric_type, "chronicle.googleapis.com/ingestion/log/record_count")
        for s in res.series:
            starts = [p.start for p in s.points]
            self.assertEqual(starts, sorted(starts))
            self.assertLessEqual(len(s.points), 25)


if __name__ == "__main__":
    unittest.main()
