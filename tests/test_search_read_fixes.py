"""Unit tests for the search read fixes (no network).

Covers aggregate_udm (filter grammar, injection safety, allow-list, bounds,
row parsing, truncation), find_udm_field_values / translate_udm_query parsing,
streamed-chunk dedupe in get_events / get_stats, UDM search totals/timelines/
field aggregations, more_data_available / zero-events completion, search
options, validator error visibility, raw-log validation, IoC IP value type,
and 429 retry visibility. Response shapes mirror the live observations in
discovery/observations/07_search_read_observations.md.
"""

from __future__ import annotations

import io
import logging
import unittest
import urllib.error
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional
from unittest import mock

from adapters.google_secops import (
    GoogleSecOpsAdapter,
    QueryValidationUnavailableError,
    SecOpsApiError,
    parse_validate_query_response,
)
from engine.domain import (
    CompletenessState,
    DashboardQueryResult,
    LifecycleState,
    SearchBatchResult,
    SearchRequest,
    StatsSearchRequest,
    ValidationResult,
)
from engine.entity_detector import detect_entity
from engine.workflows.entity_search import SearchEnterpriseIocsWorkflow, SummarizeEntityWorkflow
from engine.workflows.raw_log_search import ValidateRawLogQueryWorkflow
from engine.workflows.search_udm import SearchUDMWorkflow, parse_udm_search_stats
from engine.workflows.search_udm_stats import SearchUDMStatsWorkflow
from engine.workflows.udm_aggregate import (
    MAX_FILTER_COMPARISONS,
    UDM_AGGREGATE_FIELDS,
    AggregateUdmWorkflow,
    UdmFilterError,
    build_aggregate_sql,
    parse_aggregate_rows,
    resolve_aggregate_window,
    sql_string_literal,
    translate_udm_filter,
)
from engine.workflows.udm_query_assist import FindUdmFieldValuesWorkflow, TranslateUdmQueryWorkflow

BASE = "projects/1/locations/us/instances/abc"


def _adapter(responses: Optional[List[Any]] = None) -> GoogleSecOpsAdapter:
    """GoogleSecOpsAdapter without config whose _request replays canned responses."""
    ad = GoogleSecOpsAdapter.__new__(GoogleSecOpsAdapter)
    ad.project_number = "1"
    ad.project_id = "p"
    ad.location = "us"
    ad.customer_id = "abc"
    ad.api_base = "https://example.invalid"
    ad.default_timeout = 5.0
    ad.calls = []
    queue = list(responses or [])

    def _req(method, path, params=None, body=None, timeout=None):
        ad.calls.append({"method": method, "path": path, "params": params, "body": body})
        item = queue.pop(0)
        if isinstance(item, BaseException):
            raise item
        return item

    ad._request = _req
    return ad


def _ev(i: int) -> Dict[str, Any]:
    return {"event": {"metadata": {"id": f"id-{i}", "eventType": "NETWORK_CONNECTION"}}}


# ---------------------------------------------------------------------------
# aggregate_udm: filter grammar and injection safety
# ---------------------------------------------------------------------------


class TestUdmFilterTranslation(unittest.TestCase):
    def test_empty(self):
        self.assertEqual(translate_udm_filter(""), "")
        self.assertEqual(translate_udm_filter("   "), "")

    def test_scalar_and_enum(self):
        self.assertEqual(translate_udm_filter('metadata.log_type = "BRO_JSON"'), "metadata.log_type = 'BRO_JSON'")
        self.assertEqual(
            translate_udm_filter('metadata.event_type != "NETWORK_DNS"'),
            "(metadata.event_type IS NULL OR metadata.event_type != 'NETWORK_DNS')",
        )
        self.assertEqual(translate_udm_filter('principal.hostname >= "m"'), "principal.hostname >= 'm'")

    def test_repeated_and_nested(self):
        self.assertEqual(translate_udm_filter('principal.ip = "10.0.0.1"'), "'10.0.0.1' IN UNNEST(principal.ip)")
        self.assertEqual(translate_udm_filter('target.ip != "10.0.0.1"'), "'10.0.0.1' NOT IN UNNEST(target.ip)")
        sql = translate_udm_filter('security_result.action = "BLOCK"')
        self.assertIn("EXISTS(SELECT 1 FROM UNNEST(security_result) AS _fp, UNNEST(_fp.action) AS _fl WHERE _fl = 'BLOCK')", sql)
        self.assertTrue(translate_udm_filter('security_result.action != "BLOCK"').startswith("NOT EXISTS("))

    def test_boolean_precedence_and_keywords(self):
        sql = translate_udm_filter(
            'metadata.log_type = "A" or metadata.log_type = "B" AND not (principal.hostname = "h")'
        )
        self.assertEqual(
            sql,
            "(metadata.log_type = 'A' OR (metadata.log_type = 'B' AND NOT (principal.hostname = 'h')))",
        )

    def test_escaping(self):
        self.assertEqual(
            translate_udm_filter(r'principal.user.userid = "NT AUTHORITY\\SYSTEM"'),
            r"principal.user.userid = 'NT AUTHORITY\\SYSTEM'",
        )
        self.assertEqual(
            translate_udm_filter('principal.hostname = "a\\"b\'c"'),
            "principal.hostname = 'a\"b\\'c'",
        )
        self.assertEqual(sql_string_literal("x'; --"), "'x\\'; --'")

    def test_quote_breakout_stays_inside_literal(self):
        sql = translate_udm_filter('principal.hostname = "x\' OR \'1\'=\'1"')
        self.assertEqual(sql, "principal.hostname = 'x\\' OR \\'1\\'=\\'1'")
        # Value containing pipes/comments is a literal, never a new stage.
        sql = build_aggregate_sql(filter='principal.hostname = "a |> LIMIT 1 -- /* x */"', group_by=[], limit=5)
        self.assertEqual(sql.count("|>"), 4)  # WHERE, (pipe inside literal), AGGREGATE, LIMIT
        self.assertIn("'a |> LIMIT 1 -- /* x */'", sql)
        self.assertTrue(sql.rstrip().endswith("|> LIMIT 6"))

    def test_rejections(self):
        bad = [
            'metadata.log_type = "X" |> LIMIT 1',
            "metadata.log_type = 'X'",
            'metadata.log_type = "X"; DROP TABLE events',
            'metadata.log_type = "X" -- c',
            'metadata.log_type = "X" /* c */',
            'metadata.log_type = "X" # c',
            'metadata.log_type = /bro/',
            'raw = "x"',
            'metadata.nosuch = "x"',
            'Metadata.log_type = "x"',
            'metadata.log_type = "x" metadata.log_type = "y"',
            'metadata.log_type = x',
            'metadata.log_type = 5',
            'metadata.log_type "x"',
            'metadata.log_type = "unterminated',
            'metadata.log_type = "bad \\n escape"',
            'metadata.log_type = "line\nbreak"',
            'metadata.log_type = "tab\there"',
            "metadata.log_type = \"x\"\nmetadata.log_type = \"y\"",
            'metadata.log_type = "x" AND',
            '(metadata.log_type = "x"',
            'metadata.log_type = "x")',
            'metadata.event_type = "lower_case"',
            'metadata.event_type = "X\' OR 1=1"',
            'metadata.event_type > "A"',
            'principal.ip < "1"',
            'security_result.action >= "A"',
            'metadata.log_type = $placeholder',
            'LOWER(metadata.log_type) = "x"',
            'metadata.log_type = "x" nocase',
            'metadata.log_type IN ("a")',
            "`metadata`.log_type = \"x\"",
        ]
        for f in bad:
            with self.subTest(f=f):
                with self.assertRaises(UdmFilterError):
                    translate_udm_filter(f)

    def test_limits(self):
        many = " AND ".join(['metadata.log_type = "x"'] * (MAX_FILTER_COMPARISONS + 1))
        with self.assertRaises(UdmFilterError):
            translate_udm_filter(many)
        deep = "(" * 10 + 'metadata.log_type = "x"' + ")" * 10
        with self.assertRaises(UdmFilterError):
            translate_udm_filter(deep)
        with self.assertRaises(UdmFilterError):
            translate_udm_filter('metadata.log_type = "' + "a" * 600 + '"')


class TestAggregateQueryBuilder(unittest.TestCase):
    def test_log_type_by_hour(self):
        sql = build_aggregate_sql(group_by=["metadata.log_type"], time_bucket="hour", limit=500)
        self.assertEqual(
            sql,
            "FROM events\n"
            "|> AGGREGATE COUNT(1) AS agg_count GROUP BY metadata.log_type AS d0, "
            "TIMESTAMP_TRUNC(TIMESTAMP_SECONDS(metadata.event_timestamp.seconds), HOUR, 'UTC') AS bucket\n"
            "|> ORDER BY bucket DESC, agg_count DESC\n"
            "|> LIMIT 501",
        )

    def test_repeated_and_nested_group_by(self):
        sql = build_aggregate_sql(group_by=["principal.ip", "security_result.action"], limit=10)
        self.assertIn("|> LEFT JOIN UNNEST(principal.ip) AS _u0", sql)
        self.assertIn("|> LEFT JOIN UNNEST(security_result) AS _p1", sql)
        self.assertIn("|> LEFT JOIN UNNEST(_p1.action) AS _u1", sql)
        self.assertIn("GROUP BY _u0 AS d0, _u1 AS d1", sql)

    def test_filter_before_unnest_and_total(self):
        sql = build_aggregate_sql(filter='metadata.log_type = "X"', group_by=["target.ip"], limit=1)
        self.assertLess(sql.index("WHERE"), sql.index("LEFT JOIN"))
        total = build_aggregate_sql(group_by=[], limit=1)
        self.assertEqual(total, "FROM events\n|> AGGREGATE COUNT(1) AS agg_count\n|> LIMIT 2")

    def test_count_distinct(self):
        sql = build_aggregate_sql(group_by=["metadata.log_type"], metric="count_distinct", distinct_field="principal.hostname", limit=5)
        self.assertIn("COUNT(DISTINCT principal.hostname) AS agg_count", sql)
        with self.assertRaises(ValueError):
            build_aggregate_sql(metric="count_distinct")
        with self.assertRaises(ValueError):
            build_aggregate_sql(metric="count_distinct", distinct_field="principal.ip")
        with self.assertRaises(ValueError):
            build_aggregate_sql(metric="count_distinct", distinct_field="raw")
        with self.assertRaises(ValueError):
            build_aggregate_sql(distinct_field="principal.hostname")

    def test_allow_list_and_bounds(self):
        for kwargs in (
            {"group_by": ["raw"]},
            {"group_by": ["metadata.log_type; DROP"]},
            {"group_by": ["a.b", "c.d", "e.f"]},
            {"group_by": ["metadata.log_type", "metadata.event_type", "principal.hostname"]},
            {"group_by": ["metadata.log_type", "metadata.log_type"]},
            {"limit": 0},
            {"limit": 2001},
            {"limit": True},
            {"limit": "10"},
            {"time_bucket": "minute"},
            {"metric": "sum"},
        ):
            with self.subTest(kwargs=kwargs):
                with self.assertRaises(ValueError):
                    build_aggregate_sql(**kwargs)
        self.assertIn("LIMIT 2001", build_aggregate_sql(limit=2000))
        self.assertTrue(issubclass(UdmFilterError, ValueError))
        self.assertGreaterEqual(len(UDM_AGGREGATE_FIELDS), 12)

    def test_window_bounds(self):
        now = datetime(2026, 10, 10, 12, tzinfo=timezone.utc)
        s, e = resolve_aggregate_window(24, now=now)
        self.assertEqual(e - s, timedelta(hours=24))
        for lb in (0, -1, 169, True, "24"):
            with self.subTest(lb=lb):
                with self.assertRaises(ValueError):
                    resolve_aggregate_window(lb, now=now)
        with self.assertRaises(ValueError):
            resolve_aggregate_window(start_time="2026-10-01T00:00:00Z", end_time="2026-10-09T00:00:00Z")
        with self.assertRaises(ValueError):
            resolve_aggregate_window(start_time="2026-10-02T00:00:00Z", end_time="2026-10-01T00:00:00Z")
        s, e = resolve_aggregate_window(start_time="2026-10-01T00:00:00Z", end_time="2026-10-08T00:00:00Z")
        self.assertEqual(e - s, timedelta(hours=168))


class TestAggregateRowsAndWorkflow(unittest.TestCase):
    def _dq(self, rows):
        return DashboardQueryResult(
            query_name="inline_dashboard_query", dialect="SQL", data_sources=[],
            time_window={"startTime": "s", "endTime": "e"}, columns=list(rows[0].keys()) if rows else [],
            rows=rows, total_rows=len(rows), last_cache_refreshed_time="2026-10-10T16:00:00Z",
        )

    def test_parse_rows_truncation(self):
        rows = [
            {"d0": "BRO_JSON", "bucket": "2026-10-10T16:00:00Z", "agg_count": 5},
            {"d0": None, "bucket": "2026-10-10T15:00:00Z", "agg_count": "3"},
            {"d0": "X", "bucket": "2026-10-10T14:00:00Z", "agg_count": 1},
        ]
        out, truncated = parse_aggregate_rows(rows, ["metadata.log_type"], "hour", 2)
        self.assertTrue(truncated)
        self.assertEqual(len(out), 2)
        self.assertEqual(out[0].dims, {"metadata.log_type": "BRO_JSON"})
        self.assertEqual(out[0].bucket, datetime(2026, 10, 10, 16, tzinfo=timezone.utc))
        self.assertIsNone(out[1].dims["metadata.log_type"])
        self.assertEqual(out[1].count, 3)
        out, truncated = parse_aggregate_rows(rows, ["metadata.log_type"], "hour", 3)
        self.assertFalse(truncated)
        with self.assertRaises(RuntimeError):
            parse_aggregate_rows([{"d0": "x"}], ["metadata.log_type"], None, 5)
        with self.assertRaises(RuntimeError):
            parse_aggregate_rows([{"d0": "x", "agg_count": "n/a"}], ["metadata.log_type"], None, 5)

    def test_workflow_calls_dashboard_sql(self):
        test_case = self

        class _Dash:
            def __init__(self):
                self.calls = []

            def execute_dashboard_query(self, **kw):
                self.calls.append(kw)
                return test_case._dq([{"d0": "A", "agg_count": 2}, {"d0": "B", "agg_count": 1}])

        ad = _Dash()
        res = AggregateUdmWorkflow(ad).execute(group_by=["metadata.log_type"], lookback_hours=2, limit=1)
        call = ad.calls[0]
        self.assertEqual(call["dialect"], "SQL")
        self.assertTrue(call["query_text"].endswith("|> LIMIT 2"))
        s = datetime.fromisoformat(call["start_time"].replace("Z", "+00:00"))
        e = datetime.fromisoformat(call["end_time"].replace("Z", "+00:00"))
        self.assertEqual(e - s, timedelta(hours=2))
        self.assertTrue(res.truncated)
        self.assertEqual([r.dims for r in res.rows], [{"metadata.log_type": "A"}])
        self.assertEqual(res.dialect, "SQL")
        self.assertEqual(res.last_cache_refreshed_time, "2026-10-10T16:00:00Z")
        self.assertEqual(res.total_count, 2)

    def test_workflow_raises_query_errors(self):
        class _Err:
            def execute_dashboard_query(self, **kw):
                raise SecOpsApiError(400, "Grouping by expressions of type ARRAY is not allowed")

        with self.assertRaises(SecOpsApiError):
            AggregateUdmWorkflow(_Err()).execute()
        # Invalid inputs fail before any API call.
        with self.assertRaises(UdmFilterError):
            AggregateUdmWorkflow(_Err()).execute(filter="metadata.log_type = 'x'")
        with self.assertRaises(ValueError):
            AggregateUdmWorkflow(_Err()).execute(lookback_hours=500)


# ---------------------------------------------------------------------------
# findUdmFieldValues / translateUdmQuery
# ---------------------------------------------------------------------------


class TestQueryAssist(unittest.TestCase):
    def test_find_field_values(self):
        ad = _adapter([{
            "valueMatches": [
                {"fieldPath": "metadata.product_event_type", "value": "NetworkConnectIP4",
                 "ingestionTime": "2026-10-10T16:06:11.438976Z", "matchEnd": 11},
            ],
            "fieldMatchRegex": "NETWORK_CONN", "nextPageToken": "x", "hasMoreMatches": True,
        }])
        res = FindUdmFieldValuesWorkflow(ad).execute("NETWORK_CONN", page_size=5)
        self.assertEqual(ad.calls[0]["method"], "GET")
        self.assertTrue(ad.calls[0]["path"].endswith(":findUdmFieldValues"))
        self.assertEqual(ad.calls[0]["params"], {"query": "NETWORK_CONN", "pageSize": 5})
        m = res.matches[0]
        self.assertEqual((m.field_path, m.value, m.match_start, m.match_end), ("metadata.product_event_type", "NetworkConnectIP4", 0, 11))
        self.assertEqual(m.ingestion_time, datetime(2026, 10, 10, 16, 6, 11, 438976, tzinfo=timezone.utc))
        self.assertTrue(res.has_more)
        self.assertEqual(res.next_page_token, "x")
        with self.assertRaises(ValueError):
            FindUdmFieldValuesWorkflow(ad).execute(" ")
        with self.assertRaises(ValueError):
            FindUdmFieldValuesWorkflow(ad).execute("x", page_size=0)

    def test_translate(self):
        ad = _adapter([
            {"query": 'metadata.event_type = "NETWORK_CONNECTION"',
             "timeRange": {"startTime": "2026-10-10T15:34:11.488091236Z", "endTime": "2026-10-10T16:34:11.488091236Z"}},
            {"query": 'principal.hostname = "asdf"'},
            {},
        ])
        wf = TranslateUdmQueryWorkflow(ad)
        r = wf.execute("network connections in the last hour")
        self.assertEqual(ad.calls[0]["method"], "POST")
        self.assertEqual(ad.calls[0]["body"], {"text": "network connections in the last hour"})
        self.assertEqual(r.time_range[1] - r.time_range[0], timedelta(hours=1))
        r2 = wf.execute("asdf")
        self.assertIsNone(r2.time_range)
        with self.assertRaises(RuntimeError):
            wf.execute("nothing")
        with self.assertRaises(ValueError):
            wf.execute("")


# ---------------------------------------------------------------------------
# Streamed chunk dedupe (get_events / get_stats)
# ---------------------------------------------------------------------------


def _op(events, done=None, extra=None, flags=None):
    resp = {"events": {"events": events, **(flags or {})}}
    resp.update(extra or {})
    op = {"name": f"{BASE}/operations/s-udm-1", "response": resp}
    if done is not None:
        op["done"] = done
    return {"operation": op}


STATS_EXTRA = {
    "baselineEventsCount": 30000,
    "filteredEventsCount": 30000,
    "availableResultCount": 30000,
    "tooManyEvents": True,
    "timeline": {"sizeOfBucketMs": "60000", "buckets": [{"eventCount": 10, "baselineEventCount": 10}, {"entityChangedCount": {}}]},
    "activityTimeline": {"sizeOfBucketMs": "3600000", "buckets": [{"eventCount": 30000, "baselineEventCount": 30000}]},
    "fieldAggregations": {"fields": [
        {"fieldName": "metadata.log_type", "eventCount": 30000, "valueCount": 2,
         "allValues": [{"value": {"stringValue": "BRO_JSON"}, "eventCount": 29000}, {"value": {"stringValue": "SURICATA_IDS"}, "eventCount": 1000}]},
        {"fieldName": "target.ip", "eventCount": 30000, "valueCount": 101, "tooManyValues": True,
         "topValues": [{"value": {"stringValue": "8.8.8.8"}, "eventCount": 10521}],
         "bottomValues": [{"value": {"stringValue": "1.1.1.1"}, "eventCount": 1}]},
    ]},
    "groupedFieldAggregations": {"fields": [{"fieldName": "hostname", "eventCount": 5, "valueCount": 1,
                                             "allValues": [{"value": {"stringValue": "h1"}, "eventCount": 5}]}]},
    "aiOverview": {"summary": "x"},
    "detections": {},
}


class TestStreamDedupe(unittest.TestCase):
    def test_get_events_uses_final_chunk(self):
        # Observed live: chunks of (1, 100, 100 done) events for a 100-event page.
        evs = [_ev(i) for i in range(100)]
        res = [_op(evs[:1]), _op(evs, flags={"complete": True, "tooManyEvents": True}, extra=STATS_EXTRA),
               _op(evs, done=True, flags={"complete": True, "tooManyEvents": True}, extra=STATS_EXTRA)]
        ad = _adapter([res])
        b = ad.get_events(f"{BASE}/operations/s-udm-1", start_index=1, batch_size=100)
        ids = [e["event"]["metadata"]["id"] for e in b.events]
        self.assertEqual(len(ids), 100)
        self.assertEqual(len(set(ids)), 100)
        self.assertEqual(b.duplicates_dropped, 101)
        self.assertTrue(b.operation_done)
        self.assertTrue(b.more_data_available)  # full page and 30000 available
        self.assertEqual(b.search_stats_raw["availableResultCount"], 30000)
        self.assertNotIn("aiOverview", b.search_stats_raw)
        self.assertNotIn("events", b.search_stats_raw)
        self.assertEqual(ad.calls[0]["params"]["eventIndexStart"], 1)

    def test_get_events_five_zero_five(self):
        evs = [_ev(i) for i in range(5)]
        ad = _adapter([[_op(evs), _op([]), _op(evs, done=True)]])
        b = ad.get_events("s-udm-1", start_index=1, batch_size=10)
        self.assertEqual(len(b.events), 5)
        self.assertFalse(b.more_data_available)
        self.assertTrue(b.operation_done)

    def test_get_events_running_and_increments(self):
        ad = _adapter([[_op([_ev(1)], done=False)]])
        b = ad.get_events("s-udm-1", start_index=1, batch_size=10)
        self.assertIs(b.operation_done, False)
        self.assertTrue(b.more_data_available)
        # If the server ever streamed increments, nothing is lost or duplicated.
        ad = _adapter([[_op([_ev(1), _ev(2)]), _op([_ev(2), _ev(3)], done=True)]])
        b = ad.get_events("s-udm-1", start_index=1, batch_size=10)
        self.assertEqual(sorted(e["event"]["metadata"]["id"] for e in b.events), ["id-1", "id-2", "id-3"])

    def test_get_events_operation_error_raises(self):
        ad = _adapter([[{"operation": {"name": "x", "done": True, "error": {"code": 3, "message": "bad"}}}]])
        with self.assertRaises(RuntimeError):
            ad.get_events("s-udm-1", start_index=1)

    def test_get_stats_no_duplicate_rows(self):
        def stats_op(done):
            op = {"name": "x", "response": {"stats": {"totalResults": 2, "results": [
                {"column": "lt", "values": [{"value": {"stringVal": "A"}}, {"value": {"stringVal": "B"}}]},
                {"column": "c", "values": [{"value": {"int64Val": "5"}}, {"value": {"int64Val": "3"}}]},
            ]}, "complete": done}}
            if done:
                op["done"] = True
            return {"operation": op}

        ad = _adapter([[stats_op(False), stats_op(False), stats_op(True)]])
        r = ad.get_stats("s-udm-1")
        self.assertEqual(len(r.rows), 2)
        self.assertEqual(r.rows, [{"lt": "A", "c": 5}, {"lt": "B", "c": 3}])
        self.assertEqual(r.total_results, 2)
        self.assertTrue(r.complete)


# ---------------------------------------------------------------------------
# Search totals / aggregates / completion semantics
# ---------------------------------------------------------------------------


class TestSearchStatsParsing(unittest.TestCase):
    def test_parse(self):
        raw = {k: v for k, v in STATS_EXTRA.items() if k not in ("aiOverview", "detections")}
        st = parse_udm_search_stats(raw, "2026-10-10T16:06:30Z")
        self.assertEqual((st.total_matched, st.available_count, st.too_many_events), (30000, 30000, True))
        self.assertTrue(st.capped and st.aggregates_sampled)
        self.assertEqual(st.timeline_bucket_seconds, 60)
        self.assertEqual(st.timeline[0].bucket_start, datetime(2026, 10, 10, 16, 6, tzinfo=timezone.utc))
        self.assertEqual(st.timeline[1].bucket_start, datetime(2026, 10, 10, 16, 7, tzinfo=timezone.utc))
        self.assertEqual([b.count for b in st.timeline], [10, 0])
        self.assertEqual(st.activity_timeline[0].bucket_start, datetime(2026, 10, 10, 16, tzinfo=timezone.utc))
        lt = st.aggregation_for("metadata.log_type")
        self.assertEqual([(v.value, v.count) for v in lt.values], [("BRO_JSON", 29000), ("SURICATA_IDS", 1000)])
        ip = st.aggregation_for("target.ip")
        self.assertTrue(ip.too_many_values)
        self.assertEqual(ip.values[0].value, "8.8.8.8")
        self.assertEqual(ip.bottom_values[0].value, "1.1.1.1")
        self.assertEqual(st.grouped_field_aggregations[0].field, "hostname")
        sub = parse_udm_search_stats(raw, "2026-10-10T16:06:30Z", aggregation_fields=["target.ip"])
        self.assertEqual([a.field for a in sub.field_aggregations], ["target.ip"])
        self.assertIsNone(parse_udm_search_stats({}, None))
        self.assertIsNone(parse_udm_search_stats({"validBaselineQuery": True}, None))

    def test_filtered_count_preferred(self):
        st = parse_udm_search_stats({"baselineEventsCount": 50, "filteredEventsCount": 20}, None)
        self.assertEqual(st.total_matched, 20)
        self.assertFalse(st.capped)
        self.assertEqual(st.timeline, [])


class _SearchAdapter:
    """In-memory search adapter driven by a list of SearchBatchResult objects."""

    def __init__(self, batches, valid=True, validate_exc=None):
        self.batches = list(batches)
        self.valid = valid
        self.validate_exc = validate_exc
        self.start_kwargs = None
        self.get_calls = []
        self.cancelled = []

    def validate_query(self, query):
        if self.validate_exc:
            raise self.validate_exc
        return ValidationResult(valid=self.valid, error_message=None if self.valid else "bad syntax")

    def start_search(self, query, start_time, end_time, max_events=10000, case_insensitive=True,
                     generate_ai_overview=True, max_values_per_field=60, include_detections=True, include_prevalence=True):
        self.start_kwargs = dict(max_events=max_events, case_insensitive=case_insensitive,
                                 generate_ai_overview=generate_ai_overview, max_values_per_field=max_values_per_field,
                                 include_detections=include_detections, include_prevalence=include_prevalence)
        return "op-1"

    def get_events(self, operation_id, start_index, batch_size=2000):
        self.get_calls.append((start_index, batch_size))
        return self.batches.pop(0)

    def cancel_operation(self, operation_id):
        self.cancelled.append(operation_id)


def _batch(events, more=False, done=True, stats=None, dropped=0):
    return SearchBatchResult(events=events, provider_event_count=len(events), emitted_event_count=len(events),
                             more_data_available=more, search_stats_raw=stats, operation_done=done,
                             duplicates_dropped=dropped)


def _req(**kw):
    base = dict(query='metadata.event_type = "X"', start_time="2026-10-10T16:00:00Z", end_time="2026-10-10T17:00:00Z")
    base.update(kw)
    return SearchRequest(**base)


class TestSearchWorkflow(unittest.TestCase):
    def test_capped_search_is_partial_with_totals(self):
        raw = {k: v for k, v in STATS_EXTRA.items() if k not in ("aiOverview", "detections")}
        ad = _SearchAdapter([_batch([_ev(i) for i in range(3)], more=True, stats=raw, dropped=4)])
        s = SearchUDMWorkflow(ad).execute(_req(receive_limit=3, materialize_budget=3))
        self.assertEqual(s.lifecycle, LifecycleState.COMPLETED)
        self.assertEqual(s.completeness, CompletenessState.PARTIAL)
        self.assertTrue(s.more_data_available)
        self.assertEqual(s.total_matched, 30000)
        self.assertTrue(s.capped and s.aggregates_sampled)
        self.assertEqual(len(s.timeline), 2)
        self.assertEqual(s.duplicates_dropped, 4)

    def test_running_operation_is_polled_not_empty(self):
        ad = _SearchAdapter([_batch([], done=False), _batch([_ev(1)], done=False), _batch([_ev(1), _ev(2)], done=True)])
        with mock.patch("engine.workflows.search_udm.time.sleep") as sl:
            s = SearchUDMWorkflow(ad).execute(_req(receive_limit=10))
        self.assertEqual(sl.call_count, 2)
        self.assertEqual(s.received_count, 2)
        self.assertEqual(s.completeness, CompletenessState.COMPLETE)
        self.assertEqual(ad.get_calls[-1], (1, 10))

    def test_running_operation_times_out(self):
        ad = _SearchAdapter([_batch([], done=False)] * 5)
        with mock.patch("engine.workflows.search_udm.time.sleep"), \
                mock.patch("engine.workflows.search_udm.time.monotonic", side_effect=[0, 0, 500, 500, 500]):
            s = SearchUDMWorkflow(ad).execute(_req(), max_poll_seconds=10)
        self.assertEqual(s.lifecycle, LifecycleState.FAILED)
        self.assertIn("still running", s.error)
        self.assertEqual(ad.cancelled, ["op-1"])

    def test_zero_events_with_server_matches_is_partial(self):
        ad = _SearchAdapter([_batch([], stats={"baselineEventsCount": 12, "filteredEventsCount": 12})])
        s = SearchUDMWorkflow(ad).execute(_req())
        self.assertEqual(s.completeness, CompletenessState.PARTIAL)
        self.assertTrue(s.more_data_available)
        ad = _SearchAdapter([_batch([], stats={"baselineEventsCount": 0, "filteredEventsCount": 0})])
        s = SearchUDMWorkflow(ad).execute(_req())
        self.assertEqual(s.completeness, CompletenessState.COMPLETE)
        self.assertFalse(s.more_data_available)

    def test_complete_when_all_matches_received(self):
        ad = _SearchAdapter([_batch([_ev(1), _ev(2)], stats={"baselineEventsCount": 2, "filteredEventsCount": 2})])
        s = SearchUDMWorkflow(ad).execute(_req())
        self.assertEqual(s.completeness, CompletenessState.COMPLETE)
        self.assertFalse(s.more_data_available)

    def test_cross_batch_dedupe(self):
        ad = _SearchAdapter([_batch([_ev(1), _ev(2)], more=True), _batch([_ev(2), _ev(3)], more=False)])
        s = SearchUDMWorkflow(ad).execute(_req(receive_limit=10, batch_size=2))
        self.assertEqual([e["event"]["metadata"]["id"] for e in s.events], ["id-1", "id-2", "id-3"])
        self.assertEqual(s.duplicates_dropped, 1)
        self.assertEqual(ad.get_calls, [(1, 2), (3, 2)])

    def test_search_options_forwarded(self):
        ad = _SearchAdapter([_batch([])])
        SearchUDMWorkflow(ad).execute(_req(include_detections=False, include_prevalence=False, case_insensitive=False))
        self.assertEqual(ad.start_kwargs["generate_ai_overview"], False)
        self.assertEqual(ad.start_kwargs["case_insensitive"], False)
        self.assertEqual(ad.start_kwargs["include_detections"], False)
        self.assertEqual(ad.start_kwargs["include_prevalence"], False)

    def test_legacy_adapter_signature_still_works(self):
        class _Legacy(_SearchAdapter):
            def start_search(self, query, start_time, end_time, max_events=10000):
                return "op-1"

        ad = _Legacy([_batch([_ev(1)])])
        with self.assertLogs("engine.workflows.search_udm", level="WARNING") as logs:
            s = SearchUDMWorkflow(ad).execute(_req())
        self.assertEqual(s.received_count, 1)
        self.assertIn("were not applied", logs.output[0])

    def test_validation_request_failure_is_not_syntax_error(self):
        ad = _SearchAdapter([], validate_exc=SecOpsApiError(429, "Resource exhausted"))
        s = SearchUDMWorkflow(ad).execute(_req())
        self.assertEqual(s.lifecycle, LifecycleState.FAILED)
        self.assertIn("not a syntax error", s.error)
        self.assertIn("429", s.error)
        ad = _SearchAdapter([], valid=False)
        s = SearchUDMWorkflow(ad).execute(_req())
        self.assertEqual(s.error, "bad syntax")

    def test_stats_options_honoured(self):
        class _StatsAd(_SearchAdapter):
            def get_stats(self, operation_id, start_index=1, batch_size=2000):
                from engine.domain import StatsSearchResult
                return StatsSearchResult(rows=[], complete=True)

        ad = _StatsAd([])
        req = StatsSearchRequest(query="q", start_time="a", end_time="b", case_insensitive=False,
                                 generate_ai_overview=False, max_values_per_field=7, include_detections=False)
        SearchUDMStatsWorkflow(ad).execute(req)
        self.assertEqual(ad.start_kwargs, dict(max_events=10000, case_insensitive=False, generate_ai_overview=False,
                                               max_values_per_field=7, include_detections=False, include_prevalence=True))


class TestStartSearchBody(unittest.TestCase):
    def test_default_body_unchanged(self):
        ad = _adapter([[{"operation": "op"}]])
        ad.start_search("q", "s", "e", max_events=100)
        body = ad.calls[0]["body"]
        self.assertTrue(body["caseInsensitive"])
        self.assertTrue(body["generateAiOverview"])
        self.assertIn("detectionOptions", body)
        self.assertIn("prevalence", body)

    def test_lean_body(self):
        ad = _adapter([[{"operation": "op"}]])
        ad.start_search("q", "s", "e", max_events=100, case_insensitive=False, generate_ai_overview=False,
                        max_values_per_field=5, include_detections=False, include_prevalence=False)
        body = ad.calls[0]["body"]
        self.assertFalse(body["caseInsensitive"])
        self.assertFalse(body["generateAiOverview"])
        self.assertNotIn("detectionOptions", body)
        self.assertNotIn("prevalence", body)
        self.assertEqual(body["fieldAggregations"], {"maxValuesPerField": 5})


# ---------------------------------------------------------------------------
# Validator error visibility
# ---------------------------------------------------------------------------


class TestValidators(unittest.TestCase):
    def test_parse_response(self):
        ok = parse_validate_query_response({"queryType": "QUERY_TYPE_UDM_QUERY"}, "udm", ("QUERY_TYPE_UDM_QUERY",))
        self.assertTrue(ok.valid)
        bad = parse_validate_query_response({
            "errorType": "INVALID_QUERY_TYPE", "errorText": "lexer error", "queryType": "QUERY_TYPE_UDM_QUERY",
            "errorPosition": {"startLine": 1, "startColumn": 25, "endLine": 1, "endColumn": 26}}, "udm")
        self.assertFalse(bad.valid)
        self.assertEqual(bad.error_type, "INVALID_QUERY_TYPE")
        self.assertEqual(bad.error_position, {"start_line": 1, "start_column": 25, "end_line": 1, "end_column": 26})
        raw = parse_validate_query_response({"queryType": "QUERY_TYPE_RAW_LOG_QUERY"}, "udm", ("QUERY_TYPE_UDM_QUERY",))
        self.assertFalse(raw.valid)
        self.assertEqual(raw.error_type, "UNSUPPORTED_QUERY_TYPE")
        with self.assertRaises(QueryValidationUnavailableError):
            parse_validate_query_response({"errorType": "BACKEND_ERROR_TYPE", "errorText": "x"}, "udm")

    def test_transport_errors_raise(self):
        for exc in (SecOpsApiError(429, "quota"), SecOpsApiError(403, "denied"), RuntimeError("Network error connecting")):
            with self.subTest(exc=exc):
                with self.assertRaises(type(exc)):
                    _adapter([exc]).validate_query("x")
                with self.assertRaises(type(exc)):
                    _adapter([exc]).validate_stats_query("x")
                with self.assertRaises(type(exc)):
                    ValidateRawLogQueryWorkflow(_adapter([exc])).execute('raw = "x"')

    def test_compile_errors_still_invalid(self):
        resp = {"errorType": "INVALID_QUERY_TYPE", "errorText": "parser error", "queryType": "QUERY_TYPE_STATS_QUERY",
                "errorPosition": {"startLine": 3, "startColumn": 34, "endLine": 3, "endColumn": 35}}
        v = _adapter([resp]).validate_stats_query("q")
        self.assertFalse(v.valid)
        self.assertEqual(v.error_position["start_line"], 3)
        r = ValidateRawLogQueryWorkflow(_adapter([resp])).execute("sshd")
        self.assertFalse(r.is_valid)
        self.assertEqual(r.error_position["start_column"], 34)
        ok = ValidateRawLogQueryWorkflow(_adapter([{"queryType": "QUERY_TYPE_RAW_LOG_QUERY"}])).execute('raw = "sshd"')
        self.assertTrue(ok.is_valid)
        self.assertEqual(ok.query_type, "QUERY_TYPE_RAW_LOG_QUERY")

    def test_raw_log_dialect(self):
        ad = _adapter([{"queryType": "QUERY_TYPE_RAW_LOG_QUERY"}])
        ad.validate_raw_log_query('raw = "sshd"')
        self.assertEqual(ad.calls[0]["params"]["dialect"], "DIALECT_UDM_SEARCH")


# ---------------------------------------------------------------------------
# IoC / entity
# ---------------------------------------------------------------------------


class TestIocAndEntity(unittest.TestCase):
    def test_ip_value_type(self):
        self.assertEqual(detect_entity("172.16.6.110").ioc_value_type, "ASSET_IP_ADDRESS")

    def test_ioc_window(self):
        ad = _adapter([{"matches": []}, {"matches": []}])
        wf = SearchEnterpriseIocsWorkflow(ad)
        wf.execute("172.16.6.110")
        self.assertEqual(ad.calls[0]["params"]["timestampRange.startTime"], "1970-01-01T00:00:00Z")
        self.assertEqual(ad.calls[0]["params"]["fieldAndValue.valueType"], "ASSET_IP_ADDRESS")
        wf.execute("172.16.6.110", lookback_days=30)
        st = datetime.fromisoformat(ad.calls[1]["params"]["timestampRange.startTime"].replace("Z", "+00:00"))
        self.assertAlmostEqual((datetime.now(timezone.utc) - st).total_seconds(), 30 * 86400, delta=120)
        with self.assertRaises(ValueError):
            wf.execute("172.16.6.110", lookback_days=0)

    def test_summarize_by_value(self):
        ad = _adapter([{"entities": [{"entity": {"asset": {"ip": ["172.16.6.110"]}}}]}, {"entities": []}])
        wf = SummarizeEntityWorkflow(ad)
        r = wf.execute(field_value="172.16.6.110")
        p = ad.calls[0]["params"]
        self.assertEqual((p["fieldAndValue.value"], p["fieldAndValue.valueType"]), ("172.16.6.110", "ASSET_IP_ADDRESS"))
        self.assertNotIn("entityId", p)
        self.assertEqual(len(r.entities), 1)
        wf.execute(entity_id="projects/x/entities/abc")
        self.assertEqual(ad.calls[1]["params"]["entityId"], "abc")
        with self.assertRaises(ValueError):
            wf.execute()


# ---------------------------------------------------------------------------
# 429 visibility
# ---------------------------------------------------------------------------


class _Token:
    def get_token(self):
        return "t"


class _Resp:
    def __init__(self, body: bytes):
        self._b = body

    def read(self):
        return self._b

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


class TestRetryVisibility(unittest.TestCase):
    def test_429_is_logged_and_recorded(self):
        ad = GoogleSecOpsAdapter.__new__(GoogleSecOpsAdapter)
        ad.api_base = "https://example.invalid"
        ad.default_timeout = 1.0
        ad._credential_provider = _Token()
        err = urllib.error.HTTPError("https://example.invalid/x", 429, "Too Many", {}, io.BytesIO(b"{}"))
        marker = ad.retry_marker()
        with mock.patch("urllib.request.urlopen", side_effect=[err, _Resp(b'{"ok": true}')]), \
                mock.patch("adapters.google_secops.time.sleep") as sl, \
                self.assertLogs("adapters.google_secops", level=logging.WARNING) as logs:
            out = ad._request("GET", "/v1alpha/x:validateQuery", params={"a": 1})
        self.assertEqual(out, {"ok": True})
        sl.assert_called_once_with(2.5)
        retries = ad.retries_since(marker)
        self.assertEqual(len(retries), 1)
        self.assertEqual(retries[0]["status"], 429)
        self.assertEqual(retries[0]["path"], "/v1alpha/x:validateQuery")
        self.assertIn("429", logs.output[0])
        self.assertEqual(ad.retries_since(ad.retry_marker()), [])

    def test_aggregate_result_carries_retries(self):
        class _Dash:
            def __init__(self):
                self.seq = 0

            def retry_marker(self):
                return self.seq

            def retries_since(self, marker):
                return [{"status": 429, "attempt": 1}] if self.seq > marker else []

            def execute_dashboard_query(self, **kw):
                self.seq += 1
                return DashboardQueryResult(query_name="q", dialect="SQL", data_sources=[], time_window={},
                                            columns=["agg_count"], rows=[{"agg_count": 1}], total_rows=1)

        res = AggregateUdmWorkflow(_Dash()).execute(group_by=[])
        self.assertEqual(res.api_retries, [{"status": 429, "attempt": 1}])
        self.assertEqual(res.rows[0].count, 1)


class TestDashboardResultFields(unittest.TestCase):
    def test_truncation_fields_default_unknown(self):
        r = DashboardQueryResult(query_name="q", dialect="SQL", data_sources=[], time_window={}, columns=[], rows=[], total_rows=0)
        self.assertIsNone(r.truncated)
        self.assertIsNone(r.requested_limit)


if __name__ == "__main__":
    unittest.main()
