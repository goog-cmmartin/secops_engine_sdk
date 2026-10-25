"""Unit tests for the detection-rule read fixes (no network).

Covers the new read primitives (bulk curated deployments, bucketed detection
series, rule -> SOAR environment join, pagination helpers) and the
error-visibility fixes in rule_decay / rule_health / detection_rules /
curated_detections / detection_tuning / mitre_attack / rule_conflict /
evidence_store. Response shapes mirror the live tenant observations recorded
in discovery/observations/06_detection_read_observations.md.
"""

from __future__ import annotations

import logging
import os
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from typing import Any, Dict, List, Optional
from unittest import mock

from engine.domain import DashboardQueryResult, RuleHealthStatus
from engine.pagination import PaginationError, collect_pages
from engine.workflows import curated_detections as cd
from engine.workflows import detection_rules as dr
from engine.workflows import detection_tuning as dt
from engine.workflows import rule_decay as rd
from engine.workflows.rule_health import AuditRuleHealthWorkflow

BASE = "projects/1/locations/us/instances/abc"


def _dq(rows: List[Dict[str, Any]], columns: Optional[List[str]] = None) -> DashboardQueryResult:
    return DashboardQueryResult(
        query_name="inline_dashboard_query",
        dialect="YL2",
        data_sources=[],
        time_window={},
        columns=columns or (list(rows[0].keys()) if rows else []),
        rows=rows,
        total_rows=len(rows),
        retrieved_at=datetime.now(timezone.utc),
    )


class PagedAdapter:
    """Serves list endpoints from in-memory pages keyed by page token."""

    def __init__(self, pages: Dict[str, List[Dict[str, Any]]], key: str):
        self.pages = pages  # token ("" = first) -> response dict
        self.key = key
        self.calls: List[Optional[str]] = []

    def page(self, page_token: Optional[str]):
        self.calls.append(page_token)
        return self.pages[page_token or ""]


def _rule(rid: str, name: str, text: str = "", sev: Optional[str] = "Low") -> Dict[str, Any]:
    raw: Dict[str, Any] = {"name": f"{BASE}/rules/{rid}", "displayName": name, "type": "SINGLE_EVENT"}
    if sev is not None:
        raw["severity"] = {"displayName": sev}
    if text:
        raw["text"] = text
    return raw


def _dep(rid: str, enabled: bool, alerting: bool = False, archived: bool = False, freq: Optional[str] = "LIVE"):
    raw: Dict[str, Any] = {"name": f"{BASE}/rules/{rid}/deployment"}
    if enabled:
        raw["enabled"] = True
    if alerting:
        raw["alerting"] = True
    if archived:
        raw["archived"] = True
    if freq:
        raw["runFrequency"] = freq
    return raw


# ---------------------------------------------------------------------------
# Pagination
# ---------------------------------------------------------------------------


class TestCollectPages(unittest.TestCase):
    def test_walks_full_chain(self):
        pages = {None: ([1, 2], "a"), "a": ([3], "b"), "b": ([4], None)}
        items, tok, n = collect_pages(lambda t: pages[t])
        self.assertEqual(items, [1, 2, 3, 4])
        self.assertIsNone(tok)
        self.assertEqual(n, 3)

    def test_max_results_truncates_and_returns_resume_token(self):
        pages = {None: ([1, 2], "a"), "a": ([3, 4], "b"), "b": ([5], None)}
        items, tok, n = collect_pages(lambda t: pages[t], max_results=3)
        self.assertEqual(items, [1, 2, 3])
        self.assertEqual(tok, "b")
        self.assertEqual(n, 2)

    def test_repeated_token_raises(self):
        with self.assertRaises(PaginationError):
            collect_pages(lambda t: ([1], "same"))

    def test_page_cap_returns_remaining_token(self):
        counter = {"n": 0}

        def fetch(t):
            counter["n"] += 1
            return [counter["n"]], f"t{counter['n']}"

        items, tok, n = collect_pages(fetch, max_pages=3)
        self.assertEqual(n, 3)
        self.assertEqual(tok, "t3")

    def test_non_string_token_ends_chain(self):
        items, tok, _ = collect_pages(lambda t: ([1], mock.MagicMock()))
        self.assertEqual(items, [1])
        self.assertIsNone(tok)


# ---------------------------------------------------------------------------
# detection_rules mappers + list helpers
# ---------------------------------------------------------------------------


class TestRuleMappers(unittest.TestCase):
    def test_revision_parsed_from_name(self):
        detail = dr._map_rule_detail({"name": f"{BASE}/rules/ru_x@v_1700000000_123456789", "text": "rule x {}"})
        self.assertEqual(detail.revision_id, "v_1700000000_123456789")
        self.assertEqual(detail.revision_create_time, "2023-11-14T22:13:20.123456Z")
        self.assertEqual(detail.rule_id, "ru_x")

    def test_explicit_revision_fields_win(self):
        detail = dr._map_rule_detail(
            {"name": f"{BASE}/rules/ru_x@v_1_0", "revisionId": "v_9_9", "revisionCreateTime": "2026-01-01T00:00:00Z"}
        )
        self.assertEqual(detail.revision_id, "v_9_9")
        self.assertEqual(detail.revision_create_time, "2026-01-01T00:00:00Z")

    def test_absent_fields_are_unknown_not_healthy(self):
        detail = dr._map_rule_detail({"name": f"{BASE}/rules/ru_x"})
        self.assertEqual(detail.compilation_state, "UNKNOWN")
        self.assertEqual(detail.run_frequency, "UNKNOWN")
        self.assertEqual(detail.severity, "UNKNOWN")
        dep = dr._map_rule_deployment({"name": f"{BASE}/rules/ru_x/deployment"})
        self.assertEqual(dep.run_frequency, "UNKNOWN")
        self.assertFalse(dep.enabled)

    def test_present_fields_preserved(self):
        detail = dr._map_rule_detail(
            {"name": f"{BASE}/rules/ru_x", "compilationState": "FAILED", "runFrequency": "HOURLY"}
        )
        self.assertEqual(detail.compilation_state, "FAILED")
        self.assertEqual(detail.run_frequency, "HOURLY")

    def test_severity_normalised(self):
        for raw in ({"displayName": "Low"}, {"displayName": "low"}, {"displayName": "LOW "}, "Low"):
            self.assertEqual(dr.normalize_severity(raw), "LOW")
        self.assertEqual(dr.normalize_severity(None), "UNKNOWN")
        self.assertEqual(dr.normalize_severity({}), "UNKNOWN")
        summary = dr._map_rule_summary(_rule("ru_a", "A", sev="Medium"))
        self.assertEqual(summary.severity, "MEDIUM")

    def test_parse_rfc3339_nanoseconds(self):
        dt_ = dr.parse_rfc3339("2026-10-08T12:00:00.123456789Z")
        self.assertEqual(dt_, datetime(2026, 10, 8, 12, 0, 0, 123456, tzinfo=timezone.utc))
        self.assertIsNone(dr.parse_rfc3339("not a time"))
        self.assertIsNone(dr.parse_rfc3339(""))


class TestRuleListPagination(unittest.TestCase):
    def _adapter(self):
        pages = {
            "": {"rules": [_rule("ru_1", "One"), _rule("ru_2", "Two")], "nextPageToken": "p2"},
            "p2": {"rules": [_rule("ru_3", "Three")], "nextPageToken": "p3"},
            "p3": {"rules": [_rule("ru_4", "Four")]},
        }
        src = PagedAdapter(pages, "rules")
        adapter = SimpleNamespace(list_rules=lambda page_size, page_token, filter_expr, view: src.page(page_token))
        return adapter, src

    def test_default_is_single_page(self):
        adapter, src = self._adapter()
        res = dr.ListRulesWorkflow(adapter).execute()
        self.assertEqual(len(res.rules), 2)
        self.assertEqual(res.next_page_token, "p2")
        self.assertEqual(src.calls, [None])

    def test_all_pages(self):
        adapter, src = self._adapter()
        res = dr.ListRulesWorkflow(adapter).execute(all_pages=True)
        self.assertEqual([r.rule_id for r in res.rules], ["ru_1", "ru_2", "ru_3", "ru_4"])
        self.assertIsNone(res.next_page_token)
        self.assertEqual(res.provenance["pages"], 3)

    def test_max_results(self):
        adapter, _ = self._adapter()
        res = dr.ListRulesWorkflow(adapter).execute(max_results=3)
        self.assertEqual(len(res.rules), 3)
        self.assertEqual(res.next_page_token, "p3")

    def test_deployments_all_pages(self):
        pages = {"": {"ruleDeployments": [_dep("ru_1", True)], "nextPageToken": "x"}, "x": {"ruleDeployments": [_dep("ru_2", False)]}}
        src = PagedAdapter(pages, "ruleDeployments")
        adapter = SimpleNamespace(list_rule_deployments=lambda page_size, page_token: src.page(page_token))
        res = dr.ListRuleDeploymentsWorkflow(adapter).execute(all_pages=True)
        self.assertEqual([d.rule_id for d in res.deployments], ["ru_1", "ru_2"])


class TestRuleErrorsSince(unittest.TestCase):
    def _adapter(self):
        def err(rid, end):
            e = {"rule": f"{BASE}/rules/{rid}@v_1_0", "error": {"code": 9, "message": "limited"}}
            if end:
                e["timeRange"] = {"startTime": end, "endTime": end}
            return e

        pages = {
            "": {"ruleExecutionErrors": [err("ru_old", "2025-11-01T00:00:00Z"), err("ru_new", "2026-10-08T12:00:00.123456789Z")], "nextPageToken": "n"},
            "n": {"ruleExecutionErrors": [err("ru_nodate", None), err("ru_new2", "2026-10-09T00:00:00Z")]},
        }
        src = PagedAdapter(pages, "ruleExecutionErrors")
        return SimpleNamespace(
            list_rule_execution_errors=lambda rule_id_or_name, page_size, page_token: src.page(page_token)
        ), src

    def test_since_windows_and_walks_all_pages(self):
        adapter, src = self._adapter()
        res = dr.ListRuleErrorsWorkflow(adapter).execute(since="2026-10-01T00:00:00Z")
        ids = sorted(e.rule_resource_name.split("/")[-1].split("@")[0] for e in res.errors)
        self.assertEqual(ids, ["ru_new", "ru_new2", "ru_nodate"])
        self.assertEqual(src.calls, [None, "n"])
        self.assertEqual(res.provenance["fetched"], 4)
        self.assertEqual(res.provenance["undated"], 1)

    def test_since_accepts_datetime_and_max_results_after_window(self):
        adapter, _ = self._adapter()
        res = dr.ListRuleErrorsWorkflow(adapter).execute(
            since=datetime(2026, 10, 1, tzinfo=timezone.utc), max_results=1
        )
        self.assertEqual(len(res.errors), 1)

    def test_invalid_since_raises(self):
        adapter, _ = self._adapter()
        with self.assertRaises(ValueError):
            dr.ListRuleErrorsWorkflow(adapter).execute(since="yesterday")


# ---------------------------------------------------------------------------
# A2: detection series + detection counts error visibility
# ---------------------------------------------------------------------------


class TestDetectionCountsRaise(unittest.TestCase):
    def test_query_failure_propagates(self):
        adapter = mock.MagicMock()
        adapter.execute_dashboard_query.side_effect = RuntimeError("quota")
        with self.assertRaises(RuntimeError):
            rd.QueryRuleDetectionCountsWorkflow(adapter).execute(lookback_days=1)

    def test_renamed_rule_rows_are_summed(self):
        adapter = mock.MagicMock()
        adapter.execute_dashboard_query.return_value = _dq(
            [
                {"rule_id": "ru_a", "rule_name": "new", "count": 3, "first_seen": "", "last_seen": ""},
                {"rule_id": "ru_a", "rule_name": "old", "count": 2, "first_seen": "", "last_seen": ""},
            ]
        )
        res = rd.QueryRuleDetectionCountsWorkflow(adapter).execute(lookback_days=1)
        self.assertEqual(res["ru_a"]["count"], 5)


class TestDetectionSeries(unittest.TestCase):
    ROWS = [
        {"rule_id": "ur_1", "rule_name": "Curated", "bucket": "2026-10-09T14", "count": 2},
        {"rule_id": "ru_1", "rule_name": "Custom", "bucket": "2026-10-09T15", "count": 1},
        {"rule_id": "ur_1", "rule_name": "Curated", "bucket": "2026-10-09T13", "count": 10},
    ]

    def test_query_shape(self):
        q = rd.build_detection_series_query("hour")
        self.assertIn('"%Y-%m-%dT%H"', q)
        self.assertIn("limit: 10000", q)
        self.assertNotIn("/^", q)
        q1 = rd.build_detection_series_query("day", rule_id="ru_1")
        self.assertIn('$rule_id = "ru_1"', q1)
        self.assertIn('"%Y-%m-%d"', q1)
        with self.assertRaises(ValueError):
            rd.build_detection_series_query("week")
        with self.assertRaises(ValueError):
            rd.build_detection_series_query("hour", rule_id='x" or 1')

    def test_parse_oldest_first_and_totals(self):
        series, total = rd.parse_detection_series_rows(self.ROWS, "hour")
        self.assertEqual(total, 13)
        by = {s.rule_id: s for s in series}
        self.assertEqual(series[0].rule_id, "ur_1")  # sorted by volume
        self.assertEqual(
            [(b.bucket_start.hour, b.count) for b in by["ur_1"].buckets], [(13, 10), (14, 2)]
        )
        self.assertEqual(by["ur_1"].buckets[0].bucket_start.tzinfo, timezone.utc)
        self.assertEqual(by["ru_1"].rule_name, "Custom")

    def test_parse_unexpected_bucket_raises(self):
        with self.assertRaises(ValueError):
            rd.parse_detection_series_rows([{"rule_id": "x", "bucket": "2026-10-09", "count": 1}], "hour")

    def test_workflow_uses_hour_window_and_client_filter(self):
        adapter = mock.MagicMock()
        adapter.execute_dashboard_query.return_value = _dq(self.ROWS)
        res = rd.QueryRuleDetectionSeriesWorkflow(adapter).execute(lookback_hours=24, rule_ids=["ru_1", "ru_2"])
        kwargs = adapter.execute_dashboard_query.call_args.kwargs
        self.assertEqual((kwargs["time_unit"], kwargs["time_value"]), ("HOUR", "24"))
        self.assertNotIn('$rule_id = "', kwargs["query_text"])  # 2 ids -> client-side
        self.assertEqual([s.rule_id for s in res.series], ["ru_1"])
        self.assertEqual(res.total_detections, 1)
        self.assertFalse(res.provenance["truncated"])

    def test_workflow_raises_on_query_error(self):
        adapter = mock.MagicMock()
        adapter.execute_dashboard_query.side_effect = RuntimeError("boom")
        with self.assertRaises(RuntimeError):
            rd.QueryRuleDetectionSeriesWorkflow(adapter).execute()

    def test_invalid_lookback(self):
        with self.assertRaises(ValueError):
            rd.QueryRuleDetectionSeriesWorkflow(mock.MagicMock()).execute(lookback_hours=0)


# ---------------------------------------------------------------------------
# A3: rule -> environment join, case cross-reference
# ---------------------------------------------------------------------------


class TestRuleCaseEnvironments(unittest.TestCase):
    def test_query_has_no_regex_and_env_field(self):
        q = dt.RULE_CASE_ENVIRONMENTS_QUERY
        self.assertIn("case.environment", q)
        self.assertIn("count_distinct(case.name)", q)
        self.assertNotIn("/^", q)

    def test_parse_and_merge(self):
        rows = [
            {"rule_id": "ur_a", "rule_name": "A", "env": "Demoverse", "cases": 153},
            {"rule_id": "ru_b", "rule_name": "B", "env": "S1", "cases": 2},
            {"rule_id": "ur_a", "rule_name": "A (old)", "env": "Demoverse", "cases": 4},
            {"rule_id": "ur_a", "rule_name": "A", "env": "Default Environment", "cases": 1},
        ]
        pairs, merged = dt.parse_rule_case_environment_rows(rows)
        self.assertEqual(merged, 1)
        self.assertEqual((pairs[0].rule_id, pairs[0].environment, pairs[0].case_count), ("ur_a", "Demoverse", 157))
        adapter = mock.MagicMock()
        adapter.execute_dashboard_query.return_value = _dq(rows)
        res = dt.QueryRuleCaseEnvironmentsWorkflow(adapter).execute(lookback_days=30)
        self.assertEqual(res.environments_by_rule()["ur_a"], {"Demoverse": 157, "Default Environment": 1})
        self.assertEqual(adapter.execute_dashboard_query.call_args.kwargs["time_value"], "30")

    def test_raises_on_error(self):
        adapter = mock.MagicMock()
        adapter.execute_dashboard_query.side_effect = RuntimeError("x")
        with self.assertRaises(RuntimeError):
            dt.QueryRuleCaseEnvironmentsWorkflow(adapter).execute()

    def test_cross_reference_env_and_soar_id(self):
        adapter = mock.MagicMock()
        adapter.execute_dashboard_query.return_value = _dq(
            [{
                "case_name": "555f9906-6fa7-46f4-b7b0-d2f050a8bfd2",
                "case_display_name": "GTI High Severity File Download",
                "case_status": "OPENED",
                "case_closure_details_reason": "",
                "case_closure_details_root_cause": "",
                "case_environment": "Demoverse",
                "soar_case_id": "19950",
                "response_platform_type": "RESPONSE_PLATFORM_TYPE_SIEMPLIFY",
                "rule_id": "ur_c5",
            }]
        )
        res = dt.CrossReferenceRuleCasesWorkflow(adapter).execute("ur_c5", environment="Demoverse")
        q = adapter.execute_dashboard_query.call_args.kwargs["query_text"]
        self.assertIn('$case_environment = "Demoverse"', q)
        self.assertIn("case.response_platform_info.response_platform_id", q)
        self.assertEqual((res.cases[0].environment, res.cases[0].soar_case_id), ("Demoverse", "19950"))
        with self.assertRaises(ValueError):
            dt.CrossReferenceRuleCasesWorkflow(adapter).execute("ur_c5", environment='x"y')


# ---------------------------------------------------------------------------
# A1: curated deployments, resolution, curated detail
# ---------------------------------------------------------------------------


CAT = "110fa43d-7165-2355-1985-a63b7cdf90e8"


def _cdep(rs: str, prec: str, enabled: bool, alerting: bool = False):
    raw: Dict[str, Any] = {
        "name": f"{BASE}/curatedRuleSetCategories/{CAT}/curatedRuleSets/{rs}/curatedRuleSetDeployments/{prec.lower()}",
        "precision": prec,
    }
    if enabled:
        raw["enabled"] = True
    if alerting:
        raw["alerting"] = True
    return raw


def _crs(rs: str, title: str):
    return {"name": f"{BASE}/curatedRuleSetCategories/{CAT}/curatedRuleSets/{rs}", "displayName": title}


class TestCuratedDeployments(unittest.TestCase):
    def _adapter(self, rulesets_error: Optional[Exception] = None):
        adapter = mock.MagicMock()
        pages = {
            None: {"curatedRuleSetDeployments": [_cdep("rs1", "BROAD", True), _cdep("rs1", "PRECISE", True, True)], "nextPageToken": "t"},
            "t": {"curatedRuleSetDeployments": [_cdep("rs2", "BROAD", False), _cdep("rs2", "PRECISE", False)]},
        }
        adapter.list_curated_ruleset_deployments.side_effect = lambda page_size, page_token: pages[page_token]
        if rulesets_error:
            adapter.list_curated_rulesets.side_effect = rulesets_error
        else:
            adapter.list_curated_rulesets.return_value = {"curatedRuleSets": [_crs("rs1", "Azure - Network"), _crs("rs2", "Windows")]}
        return adapter

    def test_records_and_join(self):
        res = cd.ListCuratedRuleSetDeploymentsWorkflow(self._adapter()).execute()
        self.assertEqual(len(res.deployments), 4)
        self.assertEqual(res.pages_fetched, 2)
        first = res.deployments[1]
        self.assertEqual((first.rule_set_id, first.category_id, first.precision), ("rs1", CAT, "PRECISE"))
        self.assertTrue(first.armed)
        self.assertEqual(first.display_name, "Azure - Network")
        self.assertFalse(res.deployments[2].enabled)  # proto3-omitted false
        self.assertTrue(res.provenance["display_names_joined"])

    def test_join_failure_is_recorded(self):
        res = cd.ListCuratedRuleSetDeploymentsWorkflow(self._adapter(RuntimeError("403"))).execute()
        self.assertEqual(res.deployments[0].display_name, "")
        self.assertIn("403", res.provenance["display_name_error"])

    def test_list_failure_raises(self):
        adapter = mock.MagicMock()
        adapter.list_curated_ruleset_deployments.side_effect = RuntimeError("500")
        with self.assertRaises(RuntimeError):
            cd.ListCuratedRuleSetDeploymentsWorkflow(adapter).execute()


class TestCuratedResolution(unittest.TestCase):
    ITEMS = [_crs("rs1", "Windows"), _crs("rs2", "Windows Defender"), _crs("rs3", "Windows Sysmon"), _crs("rs4", "Okta")]

    def test_exact_title_beats_substring(self):
        self.assertEqual(cd.resolve_by_identifier(self.ITEMS, "windows", "X")["name"].split("/")[-1], "rs1")

    def test_unique_substring(self):
        self.assertEqual(cd.resolve_by_identifier(self.ITEMS, "defender", "X")["name"].split("/")[-1], "rs2")

    def test_ambiguous_substring_raises(self):
        with self.assertRaisesRegex(ValueError, "ambiguous"):
            cd.resolve_by_identifier(self.ITEMS + [_crs("rs5", "Windows Server")], "Windows S", "X")

    def test_not_found(self):
        with self.assertRaisesRegex(ValueError, "not found"):
            cd.resolve_by_identifier(self.ITEMS, "Linux", "X")

    def test_id_match(self):
        self.assertEqual(cd.resolve_by_identifier(self.ITEMS, "RS4", "X")["displayName"], "Okta")


class TestCuratedRuleSetDetail(unittest.TestCase):
    def test_direct_get_no_catalog_scan_and_errors_recorded(self):
        adapter = mock.MagicMock()
        adapter.list_curated_ruleset_categories.return_value = {"curatedRuleSetCategories": []}
        adapter.get_curated_ruleset.return_value = _crs("00ad672e-ebb3-0dd1-2a4d-99bd7c5e5f93", "Azure - Network")
        adapter.get_curated_ruleset_deployments.side_effect = RuntimeError("deployments 503")
        adapter.count_curated_ruleset_detections.return_value = {
            "curatedRuleSetCounts": [{"curatedRuleSet": f"{BASE}/curatedRuleSetCategories/-/curatedRuleSets/00ad672e-ebb3-0dd1-2a4d-99bd7c5e5f93", "count": "7"}]
        }
        res = cd.GetCuratedRuleSetDetailWorkflow(adapter).execute(
            "00ad672e-ebb3-0dd1-2a4d-99bd7c5e5f93", include_rules=False
        )
        adapter.list_curated_rulesets.assert_not_called()
        adapter.list_curated_rules.assert_not_called()
        self.assertEqual(res.detection_count, 7)
        self.assertFalse(res.rules_checked)
        self.assertEqual(len(res.errors), 1)
        self.assertIn("deployments 503", res.errors[0])

    def test_title_falls_back_to_catalog_on_404(self):
        class NotFound(RuntimeError):
            status = 404

        adapter = mock.MagicMock()
        adapter.list_curated_ruleset_categories.return_value = {"curatedRuleSetCategories": []}
        adapter.get_curated_ruleset.side_effect = NotFound("404")
        adapter.list_curated_rulesets.return_value = {"curatedRuleSets": [_crs("rs1", "Okta"), _crs("rs2", "Okta Extended")]}
        adapter.get_curated_ruleset_deployments.return_value = {"curatedRuleSetDeployments": []}
        adapter.count_curated_ruleset_detections.return_value = {}
        adapter.list_curated_rules.return_value = {"curatedRules": []}
        res = cd.GetCuratedRuleSetDetailWorkflow(adapter).execute("Okta")
        self.assertEqual(res.rule_set.id, "rs1")
        self.assertTrue(res.rules_checked)
        self.assertEqual(res.errors, [])

    def test_other_api_errors_propagate(self):
        class Forbidden(RuntimeError):
            status = 403

        adapter = mock.MagicMock()
        adapter.list_curated_ruleset_categories.return_value = {}
        adapter.get_curated_ruleset.side_effect = Forbidden("403")
        with self.assertRaises(Forbidden):
            cd.GetCuratedRuleSetDetailWorkflow(adapter).execute("rs1")


# ---------------------------------------------------------------------------
# rule_decay audit
# ---------------------------------------------------------------------------


class DecayAdapter:
    def __init__(self, verify: Dict[str, Any], counts_error: Optional[Exception] = None, verify_error: Optional[Exception] = None):
        self.verify = verify
        self.counts_error = counts_error
        self.verify_error = verify_error
        self.verified: List[str] = []
        self.rule_pages = {
            "": {"rules": [_rule("ru_live", "Live Rule", "rule live { events: $e.metadata.event_type = \"X\" condition: $e }")], "nextPageToken": "2"},
            "2": {"rules": [_rule("ru_off", "Disabled Rule", "rule off { condition: $e }"), _rule("ru_arch", "Archived", "rule a {}")]},
        }

    def execute_dashboard_query(self, **kwargs):
        if self.counts_error:
            raise self.counts_error
        return _dq([])

    def list_rule_deployments(self, page_size=1000, page_token=None):
        return {"ruleDeployments": [_dep("ru_live", True, True), _dep("ru_off", False), _dep("ru_arch", False, archived=True)]}

    def list_rules(self, page_size=100, page_token=None, view=None, filter_expr=None):
        return self.rule_pages[page_token or ""]

    def verify_rule_text(self, rule_text):
        self.verified.append(rule_text)
        if self.verify_error:
            raise self.verify_error
        return self.verify


class TestRuleDecayAudit(unittest.TestCase):
    def test_parse_verify_response(self):
        self.assertEqual(rd.parse_verify_response({"success": True, "compilationDiagnostics": [{"message": "warn"}]}), (True, []))
        ok, errs = rd.parse_verify_response({"compilationDiagnostics": [{"message": "syntax error at 3:1"}]})
        self.assertFalse(ok)
        self.assertEqual(errs, ["syntax error at 3:1"])
        with self.assertRaises(ValueError):
            rd.parse_verify_response(SimpleNamespace(success=True))

    def test_compile_check_runs_on_text_and_names_use_display_name(self):
        adapter = DecayAdapter({"success": True})
        rep = rd.AuditRuleDecayWorkflow(adapter).execute(check_population=False, max_workers=1)
        self.assertEqual(rep.total_audited, 2)  # archived skipped, both pages read
        self.assertEqual(len(adapter.verified), 2)
        self.assertEqual(rep.compile_checked_count, 2)
        names = {a.rule_id: a.rule_name for a in rep.assessments}
        self.assertEqual(names, {"ru_live": "Live Rule", "ru_off": "Disabled Rule"})
        live = next(a for a in rep.assessments if a.rule_id == "ru_live")
        self.assertIn("SILENT", live.decay_flags)  # telemetry ran and was empty
        self.assertTrue(rep.telemetry_available)

    def test_broken_compilation_fires(self):
        adapter = DecayAdapter({"success": False, "compilationDiagnostics": [{"message": "unknown field"}]})
        rep = rd.AuditRuleDecayWorkflow(adapter).execute(check_population=False, max_workers=2)
        self.assertEqual(rep.broken_compilation_count, 2)
        self.assertTrue(all("BROKEN_COMPILATION" in a.decay_flags for a in rep.assessments))
        self.assertEqual(rep.assessments[0].compiler_errors, ["unknown field"])

    def test_telemetry_failure_is_not_silence(self):
        adapter = DecayAdapter({"success": True}, counts_error=RuntimeError("dashboard 429"))
        rep = rd.AuditRuleDecayWorkflow(adapter).execute(check_population=False, max_workers=1)
        self.assertFalse(rep.telemetry_available)
        self.assertEqual(rep.silent_count, 0)
        self.assertIn("dashboard 429", rep.telemetry_errors[0])
        self.assertTrue(all("TELEMETRY_UNAVAILABLE" in a.decay_flags for a in rep.assessments))

    def test_verify_api_error_is_not_broken_compilation(self):
        adapter = DecayAdapter({}, verify_error=RuntimeError("verify 503"))
        rep = rd.AuditRuleDecayWorkflow(adapter).execute(check_population=False, max_workers=1)
        self.assertEqual(rep.broken_compilation_count, 0)
        self.assertEqual(rep.compile_checked_count, 0)
        self.assertEqual(len(rep.check_errors), 2)
        self.assertIn("verify 503", rep.assessments[0].compile_check_error)

    def test_population_errors_not_counted_unpopulated(self):
        adapter = DecayAdapter({"success": True})
        with mock.patch.object(
            rd.AuditUdmFieldPopulationWorkflow,
            "execute",
            return_value={"metadata.event_type": {"populated": False, "count": 0, "is_array": False, "error": "bad field"}},
        ):
            rep = rd.AuditRuleDecayWorkflow(adapter).execute(check_population=True, max_workers=1)
        live = next(a for a in rep.assessments if a.rule_id == "ru_live")
        self.assertEqual(live.unpopulated_fields, [])
        self.assertEqual(live.population_check_errors, {"metadata.event_type": "bad field"})

    def test_population_query_is_statement_form(self):
        wf = rd.AuditUdmFieldPopulationWorkflow(adapter=None)
        q = wf._build_field_population_query("principal.hostname", vendor_product="Windows Event Log")
        self.assertNotIn("events:", q)
        lines = q.splitlines()
        self.assertLess(lines.index('$e.principal.hostname != ""'), lines.index("match:"))
        self.assertIn('$e.metadata.product_name = "Windows Event Log"', lines)

    def test_population_array_retry_uses_builder(self):
        adapter = mock.MagicMock()
        adapter.execute_dashboard_query.side_effect = [
            RuntimeError("field is repeated"),
            _dq([{"field_val": "10.0.0.1", "count": 3}]),
        ]
        res = rd.AuditUdmFieldPopulationWorkflow(adapter).execute(["principal.ip"])
        self.assertTrue(res["principal.ip"]["populated"])
        self.assertTrue(res["principal.ip"]["is_array"])
        retry_q = adapter.execute_dashboard_query.call_args_list[1].kwargs["query_text"]
        self.assertIn("$e.principal.ip = /.+/", retry_q)
        self.assertNotIn("events:", retry_q)

    def test_rule_listing_failure_raises(self):
        adapter = DecayAdapter({"success": True})
        adapter.list_rules = mock.Mock(side_effect=RuntimeError("rules 500"))
        with self.assertRaises(RuntimeError):
            rd.AuditRuleDecayWorkflow(adapter).execute(check_population=False)

    def test_calculate_decay_score_telemetry_flag(self):
        _, flags, _, _ = rd.calculate_decay_score({}, None, is_live=True, telemetry_available=False)
        self.assertIn("TELEMETRY_UNAVAILABLE", flags)
        self.assertNotIn("SILENT", flags)


# ---------------------------------------------------------------------------
# rule_health audit
# ---------------------------------------------------------------------------


class HealthAdapter:
    """Minimal adapter for AuditRuleHealthWorkflow with live-shaped payloads."""

    def __init__(self, counts_rows=None, counts_error=None, dashboard_error=None, curated_dep_error=None):
        self.counts_rows = counts_rows if counts_rows is not None else []
        self.counts_error = counts_error
        self.dashboard_error = dashboard_error
        self.curated_dep_error = curated_dep_error
        now = datetime.now(timezone.utc)
        self.recent = (now - timedelta(days=1)).strftime("%Y-%m-%dT%H:%M:%SZ")
        self.old = (now - timedelta(days=200)).strftime("%Y-%m-%dT%H:%M:%SZ")

    def list_rules(self, page_size=100, page_token=None, filter_expr=None, view=None):
        if not page_token:
            return {"rules": [_rule("ru_fire", "Firing Rule")], "nextPageToken": "p2"}
        return {"rules": [_rule("ru_quiet", "Quiet Rule"), _rule("ru_err", "Old Error Rule")]}

    def list_rule_execution_errors(self, rule_id_or_name=None, page_size=100, page_token=None):
        if not page_token:
            return {"ruleExecutionErrors": [], "nextPageToken": "e2"}
        return {"ruleExecutionErrors": [{
            "rule": f"{BASE}/rules/ru_err@v_1_0",
            "error": {"code": 9, "message": "limited"},
            "timeRange": {"startTime": self.old, "endTime": self.old},
        }]}

    def list_rule_deployments(self, page_size=1000, page_token=None):
        return {"ruleDeployments": [_dep("ru_fire", True, True), _dep("ru_quiet", True, True), _dep("ru_err", True, True)]}

    def execute_dashboard_query(self, query_text=None, query_name=None, **kwargs):
        if query_text and "detection.detection.rule_id" in query_text:
            if self.counts_error:
                raise self.counts_error
            return _dq(self.counts_rows)
        if self.dashboard_error:
            raise self.dashboard_error
        return _dq([])

    def get_native_dashboard(self, dashboard_id_or_name):
        if self.dashboard_error:
            raise self.dashboard_error
        return {"name": "d", "definition": {"charts": []}}

    get_dashboard = get_native_dashboard

    def batch_get_dashboard_charts(self, *args, **kwargs):
        return {"dashboardCharts": []}

    def list_curated_ruleset_deployments(self, page_size=1000, page_token=None):
        if self.curated_dep_error:
            raise self.curated_dep_error
        return {"curatedRuleSetDeployments": [
            _cdep("rs1", "BROAD", True), _cdep("rs1", "PRECISE", True, True),
            _cdep("rs2", "BROAD", False), _cdep("rs2", "PRECISE", False),
        ]}

    def list_curated_rulesets(self, category_id=None, page_size=1000, page_token=None):
        return {"curatedRuleSets": [_crs("rs1", "Azure - Network"), _crs("rs2", "Windows")]}

    def count_curated_ruleset_detections(self, start, end, timeout=120.0):
        return {"curatedRuleSetCounts": [{"curatedRuleSet": f"{BASE}/curatedRuleSetCategories/{CAT}/curatedRuleSets/rs1", "count": "11"}]}


class TestRuleHealthAudit(unittest.TestCase):
    ROWS = [
        {"rule_id": "ru_fire", "rule_name": "Firing Rule", "count": 7, "first_seen": "", "last_seen": ""},
        {"rule_id": "ur_x", "rule_name": "Curated X", "count": 5, "first_seen": "", "last_seen": ""},
    ]

    def test_full_audit(self):
        rep = AuditRuleHealthWorkflow(HealthAdapter(counts_rows=self.ROWS)).execute()
        by = {f.rule_id: f for f in rep.findings}
        self.assertEqual(rep.custom_rules_audited, 3)  # both rule pages
        self.assertEqual(rep.execution_errors_considered, 1)  # both error pages
        self.assertEqual(by["ru_fire"].detection_count_recent, 7)
        self.assertEqual(rep.total_detections_24h, 12)  # custom + curated, not a top-10 sum
        self.assertEqual(rep.rules_firing_24h, 2)
        self.assertEqual(by["ru_err"].status, RuleHealthStatus.EXECUTION_ERROR)
        self.assertTrue(rep.detection_counts_available)
        # curated from real deployments
        self.assertEqual(rep.curated_rulesets_audited, 2)
        self.assertEqual(by["rs1"].status, RuleHealthStatus.HEALTHY)
        self.assertTrue(by["rs1"].alerting)
        self.assertEqual(by["rs1"].display_name, "Azure - Network")
        self.assertEqual(by["rs1"].detection_count_recent, 11)
        self.assertEqual(by["rs2"].status, RuleHealthStatus.DISABLED)
        self.assertTrue(rep.curated_available)

    def test_error_lookback_days(self):
        rep = AuditRuleHealthWorkflow(HealthAdapter(counts_rows=self.ROWS)).execute(error_lookback_days=7)
        by = {f.rule_id: f for f in rep.findings}
        self.assertEqual(rep.execution_errors_considered, 0)
        self.assertNotEqual(by["ru_err"].status, RuleHealthStatus.EXECUTION_ERROR)

    def test_telemetry_failures_are_reported(self):
        rep = AuditRuleHealthWorkflow(
            HealthAdapter(counts_error=RuntimeError("counts 429"), dashboard_error=RuntimeError("dash 403"))
        ).execute(include_curated=False)
        self.assertFalse(rep.detection_counts_available)
        self.assertFalse(rep.overview_dashboard_available)
        self.assertFalse(rep.observability_dashboard_available)
        self.assertFalse(rep.telemetry_available)
        joined = " | ".join(rep.telemetry_errors)
        self.assertIn("counts 429", joined)
        self.assertIn("dash 403", joined)

    def test_curated_deployment_failure_not_disabled(self):
        rep = AuditRuleHealthWorkflow(HealthAdapter(curated_dep_error=RuntimeError("cur 500"))).execute()
        self.assertFalse(rep.curated_available)
        self.assertEqual(rep.curated_rulesets_audited, 0)
        self.assertTrue(any("cur 500" in e for e in rep.telemetry_errors))

    def test_missing_deployment_is_unknown(self):
        adapter = HealthAdapter(counts_rows=self.ROWS)
        adapter.list_rule_deployments = lambda page_size=1000, page_token=None: {"ruleDeployments": []}
        rep = AuditRuleHealthWorkflow(adapter).execute(include_curated=False)
        self.assertEqual(rep.unknown_count, 3)


# ---------------------------------------------------------------------------
# detection_tuning error visibility
# ---------------------------------------------------------------------------


class TestTuningVisibility(unittest.TestCase):
    def test_noisy_query_has_limit(self):
        adapter = mock.MagicMock()
        adapter.execute_dashboard_query.return_value = _dq([])
        dt.FindTopNoisyRulesWorkflow(adapter).execute()
        self.assertIn("limit: 10000", adapter.execute_dashboard_query.call_args.kwargs["query_text"])

    def test_samples_primary_failure_recorded(self):
        adapter = mock.MagicMock()
        adapter.execute_dashboard_query.side_effect = [
            RuntimeError("primary 400"),
            _dq([{"user": "alice", "ip": "10.0.0.1", "count": "3", "last_seen": ""}]),
        ]
        res = dt.SampleDetectionEventsWorkflow(adapter).execute("ru_1")
        self.assertEqual(res.total_samples, 1)
        self.assertIn("primary 400", res.query_errors[0])

    def test_samples_all_fail_raise(self):
        adapter = mock.MagicMock()
        adapter.execute_dashboard_query.side_effect = RuntimeError("down")
        with self.assertRaises(RuntimeError):
            dt.SampleDetectionEventsWorkflow(adapter).execute("ru_1")

    def test_cardinality_errors_recorded_and_all_fail_raise(self):
        adapter = mock.MagicMock()
        adapter.execute_dashboard_query.side_effect = [RuntimeError("bad dim"), _dq([{"val": "h1", "count": "2"}])]
        rep = dt.AnalyzeEntityCardinalityWorkflow(adapter).execute("ru_1", dimensions=["principal_ip", "principal_hostname"])
        self.assertEqual(rep.dimensions[0].error, "RuntimeError: bad dim")
        self.assertEqual(len(rep.query_errors), 1)
        self.assertEqual(rep.dimensions[1].total_distinct_values, 1)
        self.assertEqual(rep.items, rep.dimensions)
        adapter.execute_dashboard_query.side_effect = RuntimeError("down")
        with self.assertRaises(RuntimeError):
            dt.AnalyzeEntityCardinalityWorkflow(adapter).execute("ru_1", dimensions=["principal_ip"])

    def test_refinements_all_pages(self):
        adapter = mock.MagicMock()
        pages = {
            None: {"findingsRefinements": [{"name": f"{BASE}/findingsRefinements/a"}], "nextPageToken": "n"},
            "n": {"findingsRefinements": [{"name": f"{BASE}/findingsRefinements/b"}]},
        }
        adapter.list_findings_refinements.side_effect = lambda page_size, page_token: pages[page_token]
        res = dt.ManageFindingsRefinementsWorkflow(adapter).list_refinements(all_pages=True)
        self.assertEqual([r.id for r in res.refinements], ["a", "b"])
        single = dt.ManageFindingsRefinementsWorkflow(adapter).list_refinements()
        self.assertEqual(len(single.refinements), 1)


# ---------------------------------------------------------------------------
# Read-only modes and evidence store visibility
# ---------------------------------------------------------------------------


class TestReadOnlyModes(unittest.TestCase):
    def test_find_similar_rules_no_persist(self):
        from engine.workflows.rule_conflict import FindSimilarRulesWorkflow

        store = mock.MagicMock()
        store.find_similar_rules.side_effect = [[], [{"rule_id": "ru_b", "score": 0.9}]]
        store.generate_rule_embeddings.return_value = [[0.1, 0.2]]
        adapter = mock.MagicMock()
        adapter.get_rule.return_value = {"name": f"{BASE}/rules/ru_a", "text": "rule a {}"}
        res = FindSimilarRulesWorkflow(adapter, store=store).execute("ru_a", persist=False)
        self.assertEqual(res, [{"rule_id": "ru_b", "score": 0.9}])
        store.save_rule_embeddings.assert_not_called()

    def test_find_similar_rules_no_auto_embed(self):
        from engine.workflows.rule_conflict import FindSimilarRulesWorkflow

        store = mock.MagicMock()
        store.find_similar_rules.return_value = []
        res = FindSimilarRulesWorkflow(mock.MagicMock(), store=store).execute("ru_a", auto_embed=False)
        self.assertEqual(res, [])
        store.generate_rule_embeddings.assert_not_called()
        store.save_rule_embeddings.assert_not_called()

    def test_mitre_coverage_persist_false_writes_nothing(self):
        from engine.workflows.mitre_attack import AnalyzeMitreCoverageWorkflow

        store = mock.MagicMock()
        store.list_rule_states.return_value = []
        adapter = mock.MagicMock()
        adapter.execute_dashboard_query.return_value = _dq([])
        with mock.patch("engine.workflows.mitre_attack.SyncMitreRulesWorkflow") as sync_cls:
            AnalyzeMitreCoverageWorkflow(adapter, store=store).execute(persist=False)
            sync_cls.assert_not_called()
        store.save_mitre_assessment.assert_not_called()
        store.batch_save_rule_states.assert_not_called()

    def test_mitre_coverage_default_still_persists(self):
        from engine.workflows.mitre_attack import AnalyzeMitreCoverageWorkflow

        store = mock.MagicMock()
        store.list_rule_states.return_value = [{"rule_id": "ru_a", "mitre_techniques": ["T1059"]}]
        adapter = mock.MagicMock()
        adapter.execute_dashboard_query.return_value = _dq([])
        AnalyzeMitreCoverageWorkflow(adapter, store=store).execute()
        store.save_mitre_assessment.assert_called_once()

    def test_evidence_store_fallback_is_flagged_and_logged_once(self):
        from agents.core import evidence_store as es

        with tempfile.TemporaryDirectory() as tmp, mock.patch.dict(os.environ, {"SECOPS_DISABLE_FIRESTORE": "1"}):
            es._FALLBACK_WARNED.discard("SECOPS_DISABLE_FIRESTORE=1")
            with self.assertLogs(es.logger, level=logging.WARNING) as logs:
                store = es.get_evidence_store(root_dir=tmp)
                store2 = es.get_evidence_store(root_dir=tmp)
            self.assertTrue(store.is_fallback)
            self.assertEqual(store.fallback_reason, "SECOPS_DISABLE_FIRESTORE=1")
            self.assertTrue(store2.is_fallback)
            self.assertEqual(sum("falling back" in m for m in logs.output), 1)


class TestFacadeAndRegistry(unittest.TestCase):
    def setUp(self):
        from engine.facade import SecOpsEngine

        self.engine = SecOpsEngine(adapter=mock.MagicMock())

    def test_new_capabilities_taxonomy(self):
        reg = self.engine.registry
        series = reg.get("rule.detection_series")
        env = reg.get("rule.case_environments")
        deps = reg.get("curated_detections.deployments.list")
        for cap in (series, env):
            self.assertEqual((cap.kind, cap.cardinality), ("query", "bounded"))
        self.assertEqual((deps.kind, deps.cardinality), ("query", "unbounded"))
        self.assertTrue(deps.agent.get("require_filter_for_unbounded_query"))
        for cid in ("curated_detections.rulesets.list", "curated_detections.rules.list"):
            self.assertEqual(reg.get(cid).kind, "query")
        self.assertIn("curated_detections.deployments.list", reg.get("rule.audit_health").uses)

    def test_facade_methods_backward_compatible(self):
        import inspect

        e = self.engine
        self.assertEqual(list(inspect.signature(e.list_rules).parameters)[:4], ["page_size", "page_token", "filter_expr", "view"])
        self.assertEqual(inspect.signature(e.list_rules).parameters["all_pages"].default, False)
        self.assertEqual(inspect.signature(e.list_rule_errors).parameters["since"].default, None)
        self.assertEqual(inspect.signature(e.analyze_mitre_coverage).parameters["persist"].default, True)
        self.assertEqual(inspect.signature(e.find_similar_rules).parameters["auto_embed"].default, True)
        self.assertEqual(inspect.signature(e.get_rule_detection_series).parameters["bucket"].default, "hour")


if __name__ == "__main__":
    unittest.main()
