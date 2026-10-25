"""Unit tests for ingestion-health reliability fixes (no network).

Covers:
- Feed.State classification (INACTIVE / RUNNING / SUCCEEDED / STATE_UNSPECIFIED).
- Health Hub / Deep Dive telemetry failures surfaced on reports (feed + parser).
- Per-feed Health Hub row mapping (live column names observed 2026-10-09).
- Timestamp integrity ``persist=False`` performs no Evidence Fabric writes.
- dashboardQueries:execute DATE decoding (pareto earliest/latest_event).
"""

import unittest
from typing import Any, Dict, List, Optional
from unittest.mock import MagicMock

from adapters.google_secops import GoogleSecOpsAdapter
from engine.domain import (
    DashboardQueryResult,
    FeedHealthStatus,
    FeedSummary,
    LogSourceVolumeMetric,
    ParserHealthReport,
)
from engine.facade import SecOpsEngine
from engine.workflows.feed_health import AuditFeedHealthWorkflow
from engine.workflows.health_utils import (
    DATA_HEALTH_DEEP_DIVE_DASHBOARD_ID,
    HEALTH_HUB_DASHBOARD_ID,
    DeepDiveTelemetry,
    fetch_deep_dive_telemetry,
)
from engine.workflows.parser_health import AuditParserHealthWorkflow
from engine.workflows.timestamp_integrity import TimestampIntegrityWorkflow


def _feed(fid: str, state: str, src: str = "API", lt: str = "CS_ALERTS", raw: Optional[Dict[str, Any]] = None) -> FeedSummary:
    return FeedSummary(
        id=fid,
        name=f"projects/1/locations/us/instances/a/feeds/{fid}",
        display_name=f"Feed {fid}",
        state=state,
        feed_source_type=src,
        log_type=lt,
        reference_id=fid,
        raw=raw or {},
    )


def _result(rows: List[Dict[str, Any]]) -> DashboardQueryResult:
    return DashboardQueryResult(
        query_name="q",
        dialect="SQL",
        data_sources=[],
        time_window={},
        columns=list(rows[0].keys()) if rows else [],
        rows=rows,
        total_rows=len(rows),
    )


class _DashboardAdapter:
    """In-memory adapter exposing only the dashboard calls the health workflows make."""

    def __init__(self, dashboards: Dict[str, Dict[str, Any]], query_rows: Dict[str, Any], feeds=None):
        # dashboards: id -> {chart display name: query id}; query_rows: query id -> rows or Exception
        self.dashboards = dashboards
        self.query_rows = query_rows
        self.feeds = feeds or []
        self.executed: List[str] = []

    def list_feeds(self, page_size: int = 1000, page_token: Optional[str] = None):
        return {"feeds": self.feeds}

    def get_native_dashboard(self, dashboard_id: str):
        if dashboard_id not in self.dashboards:
            raise RuntimeError(f"404 nativeDashboards/{dashboard_id} not found")
        charts = [{"dashboardChart": f"{dashboard_id}/charts/{i}"} for i, _ in enumerate(self.dashboards[dashboard_id])]
        return {"name": f"nativeDashboards/{dashboard_id}", "displayName": dashboard_id, "definition": {"charts": charts}}

    def batch_get_dashboard_charts(self, chart_names: List[str]):
        out = []
        for name in chart_names:
            did, _, idx = name.partition("/charts/")
            display, qid = list(self.dashboards[did].items())[int(idx)]
            out.append({"name": name, "displayName": display, "chartDatasource": {"dashboardQuery": qid}})
        return {"dashboardCharts": out}

    def execute_dashboard_query(self, query_name=None, **kwargs):
        self.executed.append(query_name)
        rows = self.query_rows[query_name]
        if isinstance(rows, Exception):
            raise rows
        return _result(rows)


class TestFeedStateClassification(unittest.TestCase):
    def setUp(self):
        self.wf = AuditFeedHealthWorkflow(MagicMock())

    def _eval(self, feed, telemetry=None, available=True):
        return self.wf._evaluate_feed(feed, telemetry_map=telemetry or {}, deep_dive_telemetry=DeepDiveTelemetry(),
                                      health_hub_available=available)

    def test_inactive_feed_is_not_healthy(self):
        finding = self._eval(_feed("f1", "INACTIVE"))
        self.assertEqual(finding.status, FeedHealthStatus.INACTIVE)
        self.assertIn("not collecting", finding.anomaly_description)
        self.assertTrue(finding.remediation_steps)

    def test_legacy_disabled_maps_to_inactive(self):
        self.assertEqual(self._eval(_feed("f1", "DISABLED")).status, FeedHealthStatus.INACTIVE)

    def test_operational_states_are_healthy_without_signals(self):
        for state in ("ACTIVE", "RUNNING", "SUCCEEDED"):
            with self.subTest(state=state):
                self.assertEqual(self._eval(_feed("f1", state)).status, FeedHealthStatus.HEALTHY)

    def test_unspecified_or_unknown_state_is_unknown(self):
        for state in ("STATE_UNSPECIFIED", "UNKNOWN", "PAUSED"):
            with self.subTest(state=state):
                self.assertEqual(self._eval(_feed("f1", state)).status, FeedHealthStatus.UNKNOWN)

    def test_failed_state_includes_failure_details(self):
        raw = {"failureMsg": "AccessDenied", "failureDetails": {"errorAction": "Grant s3:GetObject"}}
        finding = self._eval(_feed("f1", "FAILED", raw=raw))
        self.assertEqual(finding.status, FeedHealthStatus.FAILED)
        self.assertIn("AccessDenied", finding.anomaly_description)
        self.assertEqual(finding.remediation_steps[0], "Grant s3:GetObject")

    def test_healthy_without_telemetry_is_marked_state_only(self):
        finding = self._eval(_feed("f1", "ACTIVE"), available=False)
        self.assertEqual(finding.status, FeedHealthStatus.HEALTHY)
        self.assertFalse(finding.telemetry_observed)
        self.assertIn("telemetry unavailable", finding.anomaly_description)


class TestFeedHealthTelemetrySurfacing(unittest.TestCase):
    FEEDS = [
        {"name": "x/feeds/f-active", "displayName": "A", "state": "ACTIVE", "details": {"feedSourceType": "API", "logType": "x/logTypes/CS_ALERTS"}},
        {"name": "x/feeds/f-inactive", "displayName": "B", "state": "INACTIVE", "details": {"feedSourceType": "API", "logType": "x/logTypes/SENTINELONE_ALERT"}},
        {"name": "x/feeds/f-slow", "displayName": "C", "state": "SUCCEEDED", "details": {"feedSourceType": "GOOGLE_CLOUD_STORAGE_V2", "logType": "x/logTypes/SENTINELONE_CF"}},
    ]

    def test_missing_dashboards_are_reported_not_healthy_by_default(self):
        adapter = _DashboardAdapter(dashboards={}, query_rows={}, feeds=self.FEEDS)
        report = AuditFeedHealthWorkflow(adapter).execute()
        self.assertFalse(report.health_hub_available)
        self.assertFalse(report.deep_dive_available)
        self.assertFalse(report.telemetry_available)
        self.assertEqual(len(report.telemetry_errors), 2)
        self.assertTrue(any("Health Hub" in e and "dashboard unavailable" in e for e in report.telemetry_errors))
        self.assertEqual(report.inactive_count, 1)
        self.assertEqual(report.healthy_count, 2)

    def test_chart_failure_recorded_and_rows_mapped_by_feed_id(self):
        adapter = _DashboardAdapter(
            dashboards={
                HEALTH_HUB_DASHBOARD_ID: {
                    "Failed Sources": "q-kpi",
                    "Health Status by Data Source": "q-status",
                    "Latency Status By Source": "q-latency",
                },
                DATA_HEALTH_DEEP_DIVE_DASHBOARD_ID: {
                    "Ingestion - Events by Status": "q-funnel",
                    "Burst Rejection Graph": "q-burst",
                },
            },
            query_rows={
                "q-kpi": [{"total_count": 2}],
                "q-status": [
                    {"feed_id": "f-active", "status": "Critical", "original_status": "CRITICAL",
                     "latest_error_code": "AUTH", "latest_issue_desc": "Credentials rejected"},
                    {"feed_id": "f-inactive", "status": "Critical", "latest_error_code": "Disabled_feed",
                     "latest_issue_desc": "Feed Config Info: Feed is disabled."},
                    {"feed_id": "", "collector_id": "c-1", "status": "Warning"},
                ],
                "q-latency": [
                    {"feed_id": "f-slow", "event_ingestion_latency_p95": "5 hr 10 min"},
                    {"feed_id": "f-active", "event_ingestion_latency_p95": "No data recorded"},
                ],
                "q-funnel": [{"log_type": "CS_ALERTS", "Total_Logs": 10.0, "Total_Normalized_Events": 9.0}],
                "q-burst": RuntimeError("500 backend error"),
            },
            feeds=self.FEEDS,
        )
        report = AuditFeedHealthWorkflow(adapter).execute()
        by_id = {f.feed_id: f for f in report.findings}

        self.assertNotIn("q-kpi", adapter.executed)  # scalar KPI tile is not queried
        self.assertTrue(report.health_hub_available)
        self.assertTrue(report.deep_dive_available)
        self.assertFalse(report.telemetry_available)
        self.assertTrue(any("Burst Rejection Graph" in e and "500 backend error" in e for e in report.telemetry_errors))
        self.assertTrue(any("log count by collector id" in e and "not found" in e for e in report.telemetry_errors))

        self.assertEqual(by_id["f-active"].status, FeedHealthStatus.FAILED)
        self.assertIn("Credentials rejected", by_id["f-active"].anomaly_description)
        self.assertIsNone(by_id["f-active"].latency_p95)
        self.assertEqual(by_id["f-active"].volume_funnel["total_logs"], 10)

        self.assertEqual(by_id["f-inactive"].status, FeedHealthStatus.INACTIVE)
        self.assertEqual(by_id["f-inactive"].health_hub_status, "Critical")
        self.assertIn("Feed is disabled", by_id["f-inactive"].anomaly_description)

        self.assertEqual(by_id["f-slow"].status, FeedHealthStatus.HIGH_LATENCY)
        self.assertTrue(by_id["f-slow"].telemetry_observed)
        self.assertEqual((report.failed_count, report.inactive_count, report.high_latency_count), (1, 1, 1))


class TestDeepDiveAndParserTelemetrySurfacing(unittest.TestCase):
    def test_deep_dive_unreadable_dashboard(self):
        telemetry = fetch_deep_dive_telemetry(_DashboardAdapter(dashboards={}, query_rows={}))
        self.assertFalse(telemetry.available)
        self.assertEqual(len(telemetry.errors), 1)
        self.assertIn("Data Health Deep Dive", telemetry.errors[0])

    def test_parser_health_reports_missing_health_hub(self):
        adapter = _DashboardAdapter(dashboards={}, query_rows={})
        adapter.list_parsers = lambda **kw: {"parsers": []}
        adapter.list_parser_extensions = lambda **kw: {"parserExtensions": []}
        report = AuditParserHealthWorkflow(adapter).execute()
        self.assertIsInstance(report, ParserHealthReport)
        self.assertFalse(report.health_hub_available)
        self.assertFalse(report.telemetry_available)
        self.assertTrue(any("Health Hub" in e for e in report.telemetry_errors))

    def test_parser_health_chart_failure_is_recorded(self):
        adapter = _DashboardAdapter(
            dashboards={HEALTH_HUB_DASHBOARD_ID: {"Health Status by Parser": "q-p", "Latency Status by Log Type": "q-l"}},
            query_rows={"q-p": [{"log_type": "OKTA", "status": "Critical", "latest_drop_reason_code": "Parse error"}],
                        "q-l": RuntimeError("deadline exceeded")},
        )
        adapter.list_parsers = lambda **kw: {"parsers": []}
        adapter.list_parser_extensions = lambda **kw: {"parserExtensions": []}
        wf = AuditParserHealthWorkflow(adapter)
        errors: List[str] = []
        telemetry = wf._collect_health_hub_parser_telemetry(errors)
        available = wf.health_hub_available
        self.assertTrue(available)
        self.assertEqual(telemetry["OKTA"]["status"], "Critical")
        self.assertEqual(len(errors), 1)
        self.assertIn("deadline exceeded", errors[0])


class _RecordingStore:
    def __init__(self, baseline=None, save_error: Optional[Exception] = None):
        self.baseline = baseline
        self.save_error = save_error
        self.saved: List[Dict[str, Any]] = []

    def get_latest_timestamp_integrity(self):
        return self.baseline

    def save_timestamp_integrity_report(self, report_dict):
        if self.save_error:
            raise self.save_error
        self.saved.append(report_dict)
        return "snap-1"


class _TimestampAdapter:
    project_id = None

    def execute_dashboard_query(self, **kwargs):
        return _result([{"log_type": "OKTA", "total": 10, "average_difference_minutes": 120.0, "cnt_lt_0_hours": 0,
                         "cnt_0_1_hours": 2, "cnt_1_2_hours": 3, "cnt_gt_2_hours": 5}])


class TestTimestampIntegrityPersistence(unittest.TestCase):
    def _wf(self, store):
        wf = TimestampIntegrityWorkflow(_TimestampAdapter(), evidence_store=store)
        wf._synthesize_brief = lambda report, project_id=None: wf._deterministic_brief_fallback(report)
        return wf

    def test_persist_false_does_not_write(self):
        store = _RecordingStore(baseline={"metrics": {"OKTA": {"average_difference_minutes": 90.0}}})
        report = self._wf(store).execute(days=1, persist=False)
        self.assertEqual(store.saved, [])
        self.assertFalse(report.persist_requested)
        self.assertFalse(report.persisted)
        self.assertTrue(report.baseline_available)
        self.assertEqual(report.log_types[0].progression_state, "PREVIOUSLY KNOWN")

    def test_default_persists_without_run_metadata(self):
        store = _RecordingStore()
        report = self._wf(store).execute(days=1)
        self.assertTrue(report.persisted)
        self.assertEqual(report.persisted_snapshot_id, "snap-1")
        self.assertEqual(len(store.saved), 1)
        self.assertNotIn("run_metadata", store.saved[0])
        self.assertTrue(report.to_dict()["run_metadata"]["persisted"])

    def test_persistence_failure_is_reported(self):
        report = self._wf(_RecordingStore(save_error=RuntimeError("firestore unavailable"))).execute(days=1)
        self.assertFalse(report.persisted)
        self.assertIn("firestore unavailable", report.persistence_error)

    def test_no_store_means_no_persistence(self):
        report = self._wf(None).execute(days=1)
        self.assertFalse(report.persisted)
        self.assertIsNotNone(report.persistence_error)

    def test_facade_threads_persist_flag(self):
        store = _RecordingStore()
        engine = SecOpsEngine(adapter=_TimestampAdapter(), evidence_store=store)
        wf = engine._timestamp_integrity_wf
        wf._synthesize_brief = lambda report, project_id=None: ""
        report = engine.audit_timestamp_integrity(days=1, persist=False)
        self.assertEqual(store.saved, [])
        self.assertFalse(report.persisted)


class TestDashboardDateDecoding(unittest.TestCase):
    def test_date_val_is_decoded_to_iso(self):
        raw = {"results": [
            {"column": "log_type", "values": [{"value": {"metadata": {}, "stringVal": "BRO_JSON"}}]},
            {"column": "event_count", "values": [{"value": {"metadata": {}, "int64Val": "13739612"}}]},
            {"column": "earliest_event", "values": [{"value": {"metadata": {}, "dateVal": {"year": 2026, "month": 10, "day": 7}}}]},
            {"column": "latest_event", "values": [{"value": {"metadata": {}, "dateVal": {"year": 2026, "month": 10, "day": 8}}}]},
        ]}
        res = GoogleSecOpsAdapter._parse_dashboard_result(object.__new__(GoogleSecOpsAdapter), raw, "q")
        metric = LogSourceVolumeMetric.from_dict(res.rows[0])
        self.assertEqual(metric.event_count, 13739612)
        self.assertEqual(metric.earliest_event, "2026-10-07")
        self.assertEqual(metric.latest_event, "2026-10-08")


if __name__ == "__main__":
    unittest.main()
