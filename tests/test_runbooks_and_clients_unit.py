"""Offline unit tests for Layer 5 (Runbooks) and Layer 6 (Clients: CLI & Desktop)."""

from argparse import Namespace
import io
from contextlib import redirect_stdout
import sys
import types
import unittest

try:
    import PySide6.QtCore  # noqa: F401
except ImportError:
    _pyside6 = types.ModuleType("PySide6")
    _qtcore = types.ModuleType("PySide6.QtCore")

    class _SignalDescriptor:
        def __init__(self, *args):
            self._name = None

        def __set_name__(self, owner, name):
            self._name = f"__signal_{name}"

        def __get__(self, instance, owner=None):
            if instance is None:
                return self
            sig = getattr(instance, self._name, None)
            if sig is None:
                sig = _BoundSignal()
                setattr(instance, self._name, sig)
            return sig

    class _BoundSignal:
        def __init__(self):
            self._callbacks = []

        def connect(self, cb):
            self._callbacks.append(cb)

        def emit(self, *args):
            for cb in list(self._callbacks):
                cb(*args)

    class _QThread:
        def __init__(self, parent=None):
            self.parent = parent

    class _QAbstractTableModel:
        def __init__(self, parent=None):
            self.parent = parent

        def beginResetModel(self):
            pass

        def endResetModel(self):
            pass

        def beginInsertRows(self, parent, first, last):
            pass

        def endInsertRows(self):
            pass

    class _QModelIndex:
        def isValid(self):
            return True

    class _Qt:
        class ItemDataRole:
            DisplayRole = 0
            UserRole = 256

        class Orientation:
            Horizontal = 1
            Vertical = 2

    _qtcore.QAbstractTableModel = _QAbstractTableModel
    _qtcore.QModelIndex = _QModelIndex
    _qtcore.QObject = _QThread
    _qtcore.Qt = _Qt
    _qtcore.QThread = _QThread
    _qtcore.Signal = _SignalDescriptor
    _pyside6.QtCore = _qtcore
    sys.modules["PySide6"] = _pyside6
    sys.modules["PySide6.QtCore"] = _qtcore

from clients.cli.secops import run_data_table_cli, run_rule_cli
from clients.desktop.models import _resolve_model_attr
from engine.domain import (
    CasePriority,
    CaseSearchBatch,
    CaseSearchResultItem,
    CompletenessState,
    CuratedDetectionMetrics,
    CuratedRuleSetDeployment,
    CuratedRuleSetSummary,
    DashboardSummary,
    DataTable,
    DataTableColumnInfo,
    EventInvestigation,
    FeedBatch,
    FeedSummary,
    IntegrationBatch,
    IntegrationSummary,
    IntegrationType,
    JobBatch,
    JobSummary,
    LifecycleState,
    ParserBatch,
    ParserSummary,
    PlaybookSummary,
    PlaybookType,
    RuleDetail,
    RuleExecutionErrorListResult,
    RuleRevisionListResult,
    SearchRequest,
    SearchSession,
    TenantRuleMetrics,
)
from runbooks.operations.curated_detections_health import (
    generate_curated_detections_health_report,
    print_curated_detections_health_console,
)
from runbooks.operations.data_table_inventory import (
    print_data_table_inventory_console,
)
from runbooks.operations.yara_l_rules_audit import (
    generate_yara_l_rules_audit_report,
    print_yara_l_rules_audit_console,
)


class _StubCuratedDetectionsAdapter:
    """Stub adapter for testing curated_detections_health error visibility and counts."""

    def list_curated_ruleset_categories(self):
        return {
            "curatedRuleSetCategories": [
                {"name": "curatedRuleSetCategories/cat-1", "displayName": "Cloud"}
            ]
        }

    def list_curated_rulesets(self, page_size=1000):
        return {
            "curatedRuleSets": [
                {
                    "name": "curatedRuleSetCategories/cat-1/curatedRuleSets/rs-1",
                    "displayName": "Cloud Threats",
                },
                {
                    "name": "curatedRuleSetCategories/cat-1/curatedRuleSets/rs-2",
                    "displayName": "Endpoint Threats",
                },
            ]
        }

    def list_curated_rules(self, page_size=1000):
        return {
            "curatedRules": [
                {
                    "name": "curatedRules/ur_1",
                    "displayName": "Rule 1",
                    "curatedRuleSet": "curatedRuleSetCategories/cat-1/curatedRuleSets/rs-1",
                    "severity": {"displayName": "HIGH"},
                    "precision": "PRECISE",
                    "createTime": "2026-01-01T00:00:00Z",
                    "updateTime": "2026-01-02T00:00:00Z",
                }
            ]
        }

    def get_curated_ruleset_deployments(self, rs_name: str):
        if rs_name.endswith("rs-2"):
            raise RuntimeError("HTTP 503 Service Unavailable")
        return {
            "curatedRuleSetDeployments": [
                {
                    "name": f"{rs_name}/curatedRuleSetDeployments/precise",
                    "enabled": False,
                    "alerting": False,
                },
                {
                    "name": f"{rs_name}/curatedRuleSetDeployments/broad",
                    "enabled": True,
                    "alerting": True,
                },
            ]
        }


class _StubCuratedDetectionsEngine:
    """Stub engine wrapping _StubCuratedDetectionsAdapter."""

    def __init__(self):
        self.adapter = _StubCuratedDetectionsAdapter()

    def get_curated_detection_metrics(self, start_time: str, end_time: str):
        return CuratedDetectionMetrics(
            tenant_metrics=TenantRuleMetrics(quota_limit=1000, quota_usage=100),
            top_firing_rulesets=[],
            time_interval={"start_time": start_time, "end_time": end_time},
        )


class _StubYaraLRulesEngine:
    """Stub engine for testing yara_l_rules_audit deployment failure handling."""

    def list_rules(self, page_size=100, filter_expr=None, view="FULL"):
        class _Batch:
            rules = [
                RuleDetail(
                    name="rules/ru_ok",
                    display_name="Healthy Rule",
                    text="rule ok {}",
                    author=None,
                    severity=None,
                    rule_type=None,
                    compilation_state="SUCCEEDED",
                ),
                RuleDetail(
                    name="rules/ru_dep_err",
                    display_name="Broken Deployment Rule",
                    text="rule dep_err {}",
                    author=None,
                    severity=None,
                    rule_type=None,
                    compilation_state="SUCCEEDED",
                ),
            ]
        return _Batch()

    def get_rule_deployment(self, rule_id: str):
        if rule_id == "ru_dep_err":
            raise RuntimeError("403 Permission Denied on deployment endpoint")

        class _Dep:
            enabled = True
            alerting = True
            archived = False
            execution_state = "RUNNING"
            run_frequency = "LIVE"
            last_alert_status_change_time = None
        return _Dep()

    def list_rule_execution_errors(self, rule_id: str, start_time: str, end_time: str, page_size: int = 20):
        return RuleExecutionErrorListResult(errors=[])

    def list_rule_errors(self, page_size: int = 100):
        return RuleExecutionErrorListResult(errors=[])


class TestRunbooksUnit(unittest.TestCase):
    """Tests for Layer 5 runbooks error visibility, counting, and None-safe formatting."""

    def test_curated_detections_health_preserves_deployment_errors_and_distinct_counts(self):
        engine = _StubCuratedDetectionsEngine()
        report = generate_curated_detections_health_report(
            engine=engine,
            days=7,
            scan_deployments=True,
        )
        summary = report.summary
        self.assertEqual(summary["total_rulesets"], 2)
        # rs-1 has 2 findings (BROAD_ALERTING_ENABLED + BROAD_ENABLED_PRECISE_DISABLED),
        # rs-2 has 1 DEPLOYMENT_FETCH_FAILED finding.
        # Both rs-1 and rs-2 are unhealthy, so healthy_rulesets_count must be 0 (not negative).
        self.assertEqual(summary["healthy_rulesets_count"], 0)
        finding_codes = [f["code"] for f in report.health_findings]
        self.assertIn("DEPLOYMENT_FETCH_FAILED", finding_codes)
        self.assertIn("BROAD_ALERTING_ENABLED", finding_codes)
        self.assertIn("BROAD_ENABLED_PRECISE_DISABLED", finding_codes)

        buf = io.StringIO()
        with redirect_stdout(buf):
            print_curated_detections_health_console(report)
        output = buf.getvalue()
        self.assertNotIn("[None]", output)
        self.assertIn("DEPLOYMENT_FETCH_FAILED", output)

    def test_yara_l_rules_audit_preserves_deployment_errors_and_formats_none_fields(self):
        engine = _StubYaraLRulesEngine()
        report = generate_yara_l_rules_audit_report(engine=engine, page_size=10)
        summary = report["summary"]
        self.assertEqual(summary["total_rules"], 2)
        self.assertEqual(summary["enabled_rules"], 1)
        self.assertEqual(summary["disabled_rules"], 0)
        self.assertEqual(summary["rules_with_errors"], 1)
        self.assertEqual(summary["healthy_rules"], 1)

        rules_by_id = {r["rule_id"]: r for r in report["rules"]}
        self.assertEqual(rules_by_id["ru_dep_err"]["health_status"], "ERROR")
        self.assertIn("403 Permission Denied", rules_by_id["ru_dep_err"]["deployment_error"])

        buf = io.StringIO()
        with redirect_stdout(buf):
            print_yara_l_rules_audit_console(report)
        output = buf.getvalue()
        self.assertIn("Broken Deployment Rule", output)
        self.assertIn("Deployment Error:", output)

    def test_data_table_inventory_console_handles_none_column_fields(self):
        report = {
            "generated_at": "2026-10-04T00:00:00Z",
            "total_tables": 1,
            "data_tables": [
                {
                    "table_id": "dt_1",
                    "display_name": "Nullable Schema Table",
                    "description": None,
                    "resource_name": "dataTables/dt_1",
                    "create_time": None,
                    "update_time": None,
                    "row_time_to_live": None,
                    "scope_info": None,
                    "column_count": 1,
                    "key_columns": [],
                    "columns": [
                        {
                            "column_index": 0,
                            "column_name": None,
                            "data_type": None,
                            "is_key_column": False,
                            "repeated_values": False,
                        }
                    ],
                    "sample_row_count": 0,
                    "sample_rows": [],
                }
            ],
        }
        buf = io.StringIO()
        with redirect_stdout(buf):
            print_data_table_inventory_console(report)
        self.assertIn("Nullable Schema Table", buf.getvalue())


class TestClientsUnit(unittest.TestCase):
    """Tests for Layer 6 desktop models, workers, and CLI None-safe formatting."""

    def test_desktop_model_attribute_resolution_matches_canonical_domain_dataclasses(self):
        case_item = CaseSearchResultItem(
            case_id="101",
            title="Suspicious Login",
            create_time="2026-10-01T00:00:00Z",
            priority=CasePriority.HIGH,
            stage="Triage",
            user_assigned="alice",
            is_closed=False,
            alerts_count=4,
            environment="Default",
        )
        self.assertEqual(_resolve_model_attr(case_item, ("case_id", "id")), "101")
        self.assertEqual(_resolve_model_attr(case_item, ("status", "is_closed")), "OPEN")
        self.assertEqual(_resolve_model_attr(case_item, ("user_assigned", "assignee")), "alice")
        self.assertEqual(_resolve_model_attr(case_item, ("alerts_count", "alert_count")), "4")
        self.assertEqual(_resolve_model_attr(case_item, ("create_time", "created_time")), "2026-10-01T00:00:00Z")

        pb_item = PlaybookSummary(
            id="pb-1",
            identifier="pb-1",
            original_identifier="pb-1",
            name="Enrich IP",
            is_enabled=True,
            is_debug_mode=False,
            priority=2,
            category_id="cat-1",
            category_name="Default",
            creator="admin",
            creator_full_name="Admin User",
            environments=["Default Environment"],
            playbook_type=PlaybookType.REGULAR,
        )
        self.assertEqual(_resolve_model_attr(pb_item, ("id", "identifier", "playbook_id")), "pb-1")
        self.assertEqual(_resolve_model_attr(pb_item, ("category_name", "category", "category_id")), "Default")
        self.assertEqual(_resolve_model_attr(pb_item, ("environments",)), "Default Environment")

        int_item = IntegrationSummary(
            identifier="int-1",
            display_name="VirusTotal",
            description="VT integration",
            version=12.0,
            custom=False,
            certified=True,
            staging=False,
            python_version="PYTHON_3_11",
            integration_type=IntegrationType.RESPONSE,
            instances_count=2,
        )
        self.assertEqual(_resolve_model_attr(int_item, ("identifier", "id", "instance_id")), "int-1")
        self.assertEqual(_resolve_model_attr(int_item, ("display_name", "name")), "VirusTotal")
        self.assertEqual(_resolve_model_attr(int_item, ("certified", "is_configured", "enabled")), "True")

        job_item = JobSummary(
            id="job-1",
            name="Sync Alerts",
            display_name="Sync Alerts",
            description="Syncs alerts",
            integration="Chronicle",
            enabled=True,
            cron_expression="*/5 * * * *",
            recurring_type="INTERVAL",
            interval=300,
        )
        self.assertEqual(_resolve_model_attr(job_item, ("id", "job_id")), "job-1")
        self.assertEqual(_resolve_model_attr(job_item, ("integration", "integration_name")), "Chronicle")
        self.assertEqual(_resolve_model_attr(job_item, ("interval", "interval_seconds")), "300")

        rs_item = CuratedRuleSetSummary(
            id="rs-1",
            title="C2 Traffic",
            description="Detects C2",
            category_id="cat-1",
            category_name="Network",
            deployments=[
                CuratedRuleSetDeployment(precision="PRECISE", enabled=True, alerting=True),
                CuratedRuleSetDeployment(precision="BROAD", enabled=False, alerting=False),
            ],
            detection_count=7,
        )
        self.assertEqual(_resolve_model_attr(rs_item, ("id", "ruleset_id")), "rs-1")
        self.assertEqual(_resolve_model_attr(rs_item, ("title", "display_name")), "C2 Traffic")
        self.assertEqual(_resolve_model_attr(rs_item, ("category_name", "category", "category_id")), "Network")
        self.assertEqual(_resolve_model_attr(rs_item, ("detection_count", "rule_count")), "7")

        feed_item = FeedSummary(
            id="f-1",
            name="feeds/f-1",
            display_name="Okta Logs",
            state="ACTIVE",
            feed_source_type="API",
            log_type="OKTA",
        )
        self.assertEqual(_resolve_model_attr(feed_item, ("id", "feed_id")), "f-1")
        self.assertEqual(_resolve_model_attr(feed_item, ("feed_source_type", "source_type")), "API")

        parser_item = ParserSummary(
            name="logTypes/OKTA/parsers/p-1",
            id="p-1",
            log_type="OKTA",
            creator_source="SYSTEM",
            create_time="2026-01-01T00:00:00Z",
            type="PREBUILT",
            state="ACTIVE",
            release_stage="RELEASE",
            version=1,
            latest_version=1,
        )
        self.assertEqual(_resolve_model_attr(parser_item, ("type", "parser_type")), "PREBUILT")
        self.assertEqual(_resolve_model_attr(parser_item, ("creator_source", "author")), "SYSTEM")

        dash_item = DashboardSummary(
            id="d-1",
            name="nativeDashboards/d-1",
            display_name="SOC Overview",
            description="Main dashboard",
            type="CURATED",
            create_time="2026-01-01T00:00:00Z",
            update_time="2026-02-01T00:00:00Z",
            charts_count=5,
        )
        self.assertEqual(_resolve_model_attr(dash_item, ("id", "dashboard_id")), "d-1")
        self.assertEqual(_resolve_model_attr(dash_item, ("type", "dashboard_type")), "CURATED")
        self.assertEqual(_resolve_model_attr(dash_item, ("charts_count", "chart_count")), "5")
        self.assertEqual(_resolve_model_attr(dash_item, ("update_time", "modified_time")), "2026-02-01T00:00:00Z")

    def test_desktop_workers_invoke_canonical_engine_signatures(self):
        from clients.desktop.workers import (
            CaseSearchWorker,
            DashboardQueryWorker,
            EnrichedEventWorker,
            FeedSearchWorker,
            IntegrationSearchWorker,
            JobSearchWorker,
            ParserSearchWorker,
            SearchWorker,
        )

        calls = {}

        class _StubDesktopEngine:
            def search_udm(self, request, on_batch=None, on_state_change=None, cancel_token=None):
                calls["cancel_token_callable"] = callable(cancel_token)
                return SearchSession(
                    request=request,
                    lifecycle=LifecycleState.FAILED,
                    completeness=CompletenessState.EMPTY,
                    error="Invalid UDM query syntax",
                )

            def investigate_event(self, event_or_id, eager_load_raw_log=False):
                calls["investigate_event"] = (event_or_id, eager_load_raw_log)
                return EventInvestigation(
                    event_id=str(event_or_id),
                    udm_event={"metadata": {"id": str(event_or_id)}},
                )

            def search_cases(
                self,
                query="",
                priorities=None,
                stages=None,
                assigned_users=None,
                start_time=None,
                end_time=None,
                page_size=50,
            ):
                calls["search_cases"] = (query, priorities, page_size)
                return CaseSearchBatch(
                    results=[
                        CaseSearchResultItem(
                            case_id="1",
                            title="Open Case",
                            create_time=None,
                            priority=CasePriority.HIGH,
                            stage="Triage",
                            is_closed=False,
                        ),
                        CaseSearchResultItem(
                            case_id="2",
                            title="Closed Case",
                            create_time=None,
                            priority=CasePriority.LOW,
                            stage="Closed",
                            is_closed=True,
                        ),
                    ],
                    total_count=2,
                    page_size=page_size,
                    page_number=0,
                )

            def search_integrations(self, query="", environment=None, is_configured=None, limit=100):
                calls["search_integrations"] = (query, environment, is_configured, limit)
                return IntegrationBatch(results=[], total_count=0)

            def search_jobs(self, query="", integration=None, enabled=None, limit=100):
                calls["search_jobs"] = (query, integration, enabled, limit)
                return JobBatch(results=[], total_count=0)

            def search_feeds(self, query="", log_type=None, state=None, feed_source_type=None, limit=100):
                calls["search_feeds"] = (query, log_type, feed_source_type, limit)
                return FeedBatch(feeds=[], total_count=0)

            def search_parsers(self, query="", state=None, creator=None, limit=100):
                calls["search_parsers"] = (query, state, creator, limit)
                return ParserBatch(parsers=[], total_count=0)

            def execute_dashboard_query(self, query_text):
                calls["execute_dashboard_query"] = query_text
                return {"results": [{"count": 42}]}

        eng = _StubDesktopEngine()

        sw = SearchWorker(
            engine=eng,
            mode="search",
            search_request=SearchRequest(query="bad", start_time="2026-01-01T00:00:00Z", end_time="2026-01-02T00:00:00Z"),
        )
        failed_msgs = []
        sw.search_failed.connect(failed_msgs.append)
        sw.run()
        self.assertTrue(calls.get("cancel_token_callable"))
        self.assertEqual(failed_msgs, ["Invalid UDM query syntax"])

        ew = EnrichedEventWorker(engine=eng, event_id="evt-123")
        ew.run()
        self.assertEqual(calls.get("investigate_event"), ("evt-123", False))

        cw = CaseSearchWorker(engine=eng, query="phishing", status="OPEN", limit=25)
        loaded_batches = []
        cw.cases_loaded.connect(loaded_batches.append)
        cw.run()
        self.assertEqual(len(loaded_batches), 1)
        self.assertEqual([c.case_id for c in loaded_batches[0].results], ["1"])

        iw = IntegrationSearchWorker(engine=eng, query="vt", limit=50)
        iw.run()
        self.assertEqual(calls.get("search_integrations"), ("vt", None, None, 50))

        jw = JobSearchWorker(engine=eng, query="sync", is_enabled=True, limit=50)
        jw.run()
        self.assertEqual(calls.get("search_jobs"), ("sync", None, True, 50))

        fw = FeedSearchWorker(engine=eng, query="okta", source_type="API", limit=50)
        fw.run()
        self.assertEqual(calls.get("search_feeds"), ("okta", None, "API", 50))

        pw = ParserSearchWorker(engine=eng, query="okta", parser_type="CUSTOM", limit=50)
        pw.run()
        self.assertEqual(calls.get("search_parsers"), ("okta", None, "CUSTOM", 50))

        dw = DashboardQueryWorker(
            engine=eng,
            query="metadata.event_type = \"USER_LOGIN\"",
            start_time="2026-01-01T00:00:00Z",
            end_time="2026-01-02T00:00:00Z",
        )
        dw.run()
        self.assertEqual(
            calls.get("execute_dashboard_query"),
            'metadata.event_type = "USER_LOGIN"',
        )

    def test_cli_data_table_and_rule_formatting_handles_none_fields(self):
        import clients.cli.secops as cli_mod

        class _StubCliEngine:
            def get_data_table(self, table_name):
                return DataTable(
                    name=f"dataTables/{table_name}",
                    id=table_name,
                    display_name=table_name,
                    column_info=[
                        DataTableColumnInfo(
                            column_index=0,
                            original_column="",
                            column_type=None,
                            key_column=True,
                        )
                    ],
                )

            def list_rules(self, page_size=50, filter_expr=None, view="FULL"):
                class _Batch:
                    rules = [
                        RuleDetail(
                            name="rules/ru_1",
                            display_name="Rule With None Fields",
                            text="rule r {}",
                            severity=None,
                            rule_type=None,
                            run_frequency=None,
                        )
                    ]
                return _Batch()

            def list_rule_revisions(self, rule_id, page_size=20):
                return RuleRevisionListResult(
                    rule_id=rule_id,
                    revisions=[
                        RuleDetail(
                            name=f"rules/{rule_id}",
                            display_name="Rev 1",
                            text="rule r {}",
                            revision_id="rev_1",
                            compilation_state=None,
                            revision_create_time=None,
                            author=None,
                        )
                    ],
                )

        orig_engine = cli_mod.SecOpsEngine
        cli_mod.SecOpsEngine = _StubCliEngine
        try:
            buf = io.StringIO()
            with redirect_stdout(buf):
                run_data_table_cli(Namespace(dt_action="get", table="dt_test", json=False))
                run_rule_cli(Namespace(rule_action="list", limit=10, filter=None, view="FULL", json=False))
                run_rule_cli(Namespace(rule_action="revisions", rule="ru_1", limit=10, json=False))
            out = buf.getvalue()
            self.assertIn("UNKNOWN", out)
            self.assertIn("Rule With None Fields", out)
            self.assertIn("rev_1", out)
        finally:
            cli_mod.SecOpsEngine = orig_engine


if __name__ == "__main__":
    unittest.main()
