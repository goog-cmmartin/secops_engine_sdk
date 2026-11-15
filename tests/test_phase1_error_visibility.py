"""Phase 1 tests: error visibility, telemetry availability flags, and anti-fallback guards."""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import MagicMock, patch

from adapters.google_secops import GoogleSecOpsAdapter, SecOpsApiError
from agents.core.base_adk_agent import BaseSecOpsAdkAgent
from agents.core.evidence_store import LocalFileEvidenceStore
import agents.core.evidence_store as evidence_store_mod
from engine.domain import (
    CaseAlertSummary,
    CaseInvestigation,
    CasePriority,
    CaseStatus,
    CompletenessState,
    DashboardHealthStatus,
    DashboardSummary,
    DataTable,
    DataTableColumnInfo,
    DataTableHealthStatus,
    EnterpriseIocBatch,
    InvolvedEntitySummary,
    LifecycleState,
    RuleHealthStatus,
    SearchSession,
    TriageVerdict,
)
from engine.workflows.case_ai_investigation import InvestigateCaseWithAIWorkflow
from engine.workflows.case_triage import (
    _analyze_precedents,
    _derive_verdict_and_recommendations,
)
from engine.workflows.correlate_silent_detections import CorrelateSilentDetectionsWorkflow
from engine.workflows.dashboard_health import AuditDashboardHealthWorkflow
from engine.workflows.data_table_health import AuditDataTableHealthWorkflow
from engine.workflows.entity_search import InvestigateEntityWorkflow
from engine.workflows.homepage_dashboard import (
    _format_ai_executive_summary_markdown,
    _format_tenant_health_markdown,
    fetch_tenant_health_snapshot,
)
from engine.workflows.playbook_decay import (
    AuditPlaybookDecayWorkflow,
    PlaybookBriefSynthesizer,
    PlaybookDecayReport,
    PlaybookScoringEngine,
    PlaybookTelemetry,
)
from engine.workflows.rule_audit import AuditRulesWorkflow
from engine.workflows.rule_conflict import AuditRuleConflictWorkflow
from engine.workflows.timestamp_integrity import TimestampIntegrityWorkflow


REPO_ROOT = Path(__file__).resolve().parent.parent


def _bare_adapter() -> GoogleSecOpsAdapter:
    ad = GoogleSecOpsAdapter.__new__(GoogleSecOpsAdapter)
    ad.project_id = "proj-alpha"
    ad.project_number = "123456789"
    ad.location = "us"
    ad.customer_id = "cust-1111"
    ad.api_base = "https://us-chronicle.googleapis.com"
    ad.default_timeout = 5.0
    ad._credential_provider = None
    return ad


class TestPhase1SearchSessionPropagation(unittest.TestCase):
    """Item 1: SearchSession.raise_for_failure() and composed workflow callers."""

    def test_raise_for_failure_raises_only_on_failed_lifecycle(self):
        failed = SearchSession(
            session_id="op-1",
            lifecycle=LifecycleState.FAILED,
            error="HTTP 503 backend unavailable",
        )
        with self.assertRaisesRegex(RuntimeError, "HTTP 503 backend unavailable"):
            failed.raise_for_failure()

        ok = SearchSession(
            session_id="op-2",
            lifecycle=LifecycleState.COMPLETED,
            completeness=CompletenessState.COMPLETE,
        )
        self.assertIs(ok.raise_for_failure(), ok)

    def test_correlate_silent_detections_raises_on_failed_search_session(self):
        search_wf = MagicMock()
        search_wf.execute.return_value = SearchSession(
            session_id="op-fail",
            lifecycle=LifecycleState.FAILED,
            error="UDM backend timed out",
        )
        investigate_wf = MagicMock()
        now = datetime.now(timezone.utc)
        investigate_wf.execute.return_value = SimpleNamespace(
            case_id="101",
            title="Test Case",
            created_time=now - timedelta(minutes=10),
            alerts=[
                SimpleNamespace(
                    id="a1",
                    identifier="a1",
                    name="cases/101/caseAlerts/a1",
                    rule_name="Rule 1",
                    vendor="Google Chronicle",
                    raw={"sourceSystemName": "Google Chronicle"},
                    entities=[
                        SimpleNamespace(
                            identifier="10.1.2.3",
                            entity_type="ADDRESS",
                            role="SOURCE",
                            is_internal=False,
                        )
                    ],
                )
            ],
            entities=[
                SimpleNamespace(
                    identifier="10.1.2.3",
                    entity_type="ADDRESS",
                    role="SOURCE",
                    is_internal=False,
                )
            ],
            comments=[],
        )
        wf = CorrelateSilentDetectionsWorkflow(adapter=MagicMock())
        wf.investigate_workflow = investigate_wf
        wf.search_workflow = search_wf
        with self.assertRaisesRegex(RuntimeError, "UDM backend timed out"):
            wf.execute(case_id="101", attach_to_case=False, min_case_age_seconds=0)

    def test_entity_search_raises_when_all_stages_fail_and_marks_partial(self):
        failed_sess = SearchSession(
            session_id="op-fail",
            lifecycle=LifecycleState.FAILED,
            error="permission denied",
        )
        graph_wf = MagicMock()
        graph_wf.execute.return_value = failed_sess
        udm_wf = MagicMock()
        udm_wf.execute.return_value = failed_sess
        ioc_wf = MagicMock()
        ioc_wf.execute.side_effect = RuntimeError("IoC endpoint 500")
        cases_wf = MagicMock()
        cases_wf.execute.side_effect = RuntimeError("SOAR endpoint 500")

        wf = InvestigateEntityWorkflow(
            search_graph_wf=graph_wf,
            search_from_entity_wf=udm_wf,
            search_iocs_wf=ioc_wf,
            search_cases_wf=cases_wf,
            summarize_entity_wf=MagicMock(),
        )
        with self.assertRaisesRegex(RuntimeError, "failed across all"):
            wf.execute("10.0.0.9")

        # Partial success: IoC succeeds, graph + UDM + cases fail -> partial=True, stage_errors populated
        ioc_wf.execute.side_effect = None
        ioc_wf.execute.return_value = EnterpriseIocBatch(
            searched_value="10.0.0.9",
            value_type="IP_ADDRESS",
            matches=[],
            total_count=0,
        )
        report = wf.execute("10.0.0.9")
        self.assertTrue(report.partial)
        self.assertIn("entity_graph", report.stage_errors)
        self.assertIn("udm_events", report.stage_errors)
        self.assertIn("related_cases", report.stage_errors)
        self.assertNotIn("enterprise_iocs", report.stage_errors)

    def test_case_ai_investigation_records_failed_search_sessions(self):
        failed_sess = SearchSession(
            session_id="op-hunt-fail",
            lifecycle=LifecycleState.FAILED,
            error="UDM quota exhausted",
        )
        inv_wf = MagicMock()
        inv_wf.execute.return_value = SimpleNamespace(
            alerts=[SimpleNamespace(alert_id="alert-1")],
            entities=[],
            comments=[],
            title="Compromised host 198.51.100.77",
        )
        summary_wf = MagicMock()
        summary_wf.execute.return_value = SimpleNamespace(
            state="SUCCESSFUL",
            summary="Suspicious outbound traffic from 198.51.100.77",
            reasons=["Beacon pattern"],
            next_steps=["Isolate host"],
        )
        udm_wf = MagicMock()
        udm_wf.execute.return_value = failed_sess

        wf = InvestigateCaseWithAIWorkflow(
            adapter=MagicMock(),
            investigate_workflow=inv_wf,
            case_summary_workflow=summary_wf,
            search_udm_workflow=udm_wf,
            incident_workflow=MagicMock(),
            update_alert_workflow=MagicMock(),
            add_comment_workflow=MagicMock(),
        )
        res = wf.execute(case_id="500", dry_run=True)
        self.assertEqual(res.hunt_results.get("198.51.100.77"), -1)
        self.assertIn("198.51.100.77", res.hunt_errors)
        self.assertIn("UDM quota exhausted", res.hunt_errors["198.51.100.77"])


class TestPhase1AgentChatRaisesOnFailure(unittest.IsolatedAsyncioTestCase):
    """Item 2: BaseSecOpsAdkAgent.chat() raises when all Gemini attempts fail."""

    async def test_chat_raises_instead_of_posting_fabricated_clean_message(self):
        agent = BaseSecOpsAdkAgent(
            name="Test Agent",
            handle="@test-agent",
            role="tester",
            subsystem="detections",
            description="desc",
            system_instruction="sys",
        )

        class _BrokenChats:
            def create(self, **kwargs):
                class _Sess:
                    def send_message(self, prompt):
                        raise RuntimeError("503 model overloaded")
                return _Sess()

        class _BrokenClient:
            def __init__(self, **kwargs):
                self.chats = _BrokenChats()

        fake_types = SimpleNamespace(
            GenerateContentConfig=lambda **kw: SimpleNamespace(**kw),
        )
        fake_genai = SimpleNamespace(
            Client=_BrokenClient,
            types=fake_types,
        )
        import agents.core.base_adk_agent as base_adk_mod

        with patch.object(base_adk_mod, "genai", fake_genai), patch.object(
            base_adk_mod, "types", fake_types
        ), patch.dict("os.environ", {"GEMINI_API_KEY": "test-key"}, clear=False):
            with self.assertRaisesRegex(RuntimeError, "LLM execution failed for @test-agent"):
                await agent.chat("analyze rule ru_1")


class TestPhase1WebAndDemoHygiene(unittest.TestCase):
    """Items 3 & 4: Web server disconnected adapter -> 503, clean overview, no demo data in run_tui.py."""

    def test_run_tui_has_no_inline_demo_data_or_banned_terms(self):
        run_tui_src = (REPO_ROOT / "run_tui.py").read_text(encoding="utf-8")
        self.assertLess(len(run_tui_src.splitlines()), 80)
        legacy_proj = "-".join(("sdl", "preview", "americas"))
        for banned in ("mock", "Mock", "fake", "Fake", "dummy", "Dummy", "sample_data", legacy_proj):
            self.assertNotIn(banned, run_tui_src)
        self.assertTrue((REPO_ROOT / "tests" / "tui_demo_engine.py").is_file())

    def test_web_server_has_no_inert_adapter_or_fabricated_gastown_progress(self):
        legacy_proj = "-".join(("sdl", "preview", "americas"))
        srv_src = (REPO_ROOT / "clients" / "web" / "server.py").read_text(encoding="utf-8")
        self.assertNotIn("_InertAdapterForWeb", srv_src)
        self.assertNotIn("from tests.test_helpers import", srv_src)
        for hardcoded in ('"95/100"', '"11/11"', '"91/92"', '"2m ago"', '"5m ago"', '"10m ago"', '"Just now"'):
            self.assertNotIn(hardcoded, srv_src)

        app_js = (REPO_ROOT / "clients" / "web" / "static" / "app.js").read_text(encoding="utf-8")
        self.assertNotIn(legacy_proj, app_js)

        hp_src = (REPO_ROOT / "engine" / "workflows" / "homepage_dashboard.py").read_text(encoding="utf-8")
        self.assertNotIn(legacy_proj, hp_src)

    def test_disconnected_adapter_returns_503_when_fastapi_available(self):
        try:
            from fastapi.testclient import TestClient
            import clients.web.server as web_server
        except ImportError:
            self.skipTest("fastapi not installed in test environment")

        disconnected = web_server._DisconnectedSecOpsAdapter("missing SECOPS_CUSTOMER_ID")
        with self.assertRaises(web_server.SecOpsEngineUnavailableError):
            disconnected.list_feeds()

        fake_eng = SimpleNamespace(
            adapter=disconnected,
            registry=web_server.engine.registry,
            analyze_log_costs=lambda **kw: disconnected.execute_dashboard_query(),
        )
        with patch.object(web_server, "engine", fake_eng):
            client = TestClient(
                web_server.app,
                headers={"X-SecOps-Token": web_server.WEB_API_TOKEN},
            )
            resp = client.post("/api/log_cost/analyze")
            self.assertEqual(resp.status_code, 503)
            self.assertEqual(resp.json()["status"], "UNAVAILABLE")


class TestPhase1AuditTelemetryAvailability(unittest.TestCase):
    """Item 5: Telemetry failures never masquerade as silent decay, orphan tables, or healthy 0 events."""

    def test_rule_audit_marks_unknown_instead_of_silent_decay_when_telemetry_fails(self):
        adapter = MagicMock()
        adapter.list_rule_deployments.return_value = {
            "ruleDeployments": [
                {
                    "name": "projects/p/locations/us/instances/c/rules/ru_1/deployment",
                    "enabled": True,
                    "alerting": True,
                }
            ]
        }
        adapter.list_rules.return_value = {
            "rules": [
                {
                    "name": "projects/p/locations/us/instances/c/rules/ru_1",
                    "displayName": "Active Rule",
                    "text": "rule active { events: $e.metadata.event_type = \"USER_LOGIN\" condition: $e }",
                }
            ]
        }
        adapter.list_rule_execution_errors.return_value = {"ruleExecutionErrors": []}
        adapter.execute_dashboard_query.side_effect = RuntimeError("Chronicle stats 503")

        with tempfile.TemporaryDirectory() as tmp:
            store = LocalFileEvidenceStore(base_dir=tmp)
            wf = AuditRulesWorkflow(adapter=adapter, store=store)
            report = wf.execute(include_curated=False, sync_embeddings=False, run_conflict_scan=False)

        self.assertFalse(report.telemetry_available)
        self.assertIn("Chronicle stats 503", report.telemetry_error or "")
        self.assertEqual(report.silent_decay_count, 0)
        self.assertEqual(report.unknown_count, 1)
        finding = report.findings[0]
        self.assertEqual(finding.status, RuleHealthStatus.UNKNOWN)
        self.assertEqual(finding.decay_status, "UNKNOWN")
        self.assertEqual(finding.dps_score, 100.0)

    def test_playbook_decay_skips_exec01_deduction_when_telemetry_unavailable(self):
        playbook_def = {
            "identifier": "pb-1",
            "name": "Production Playbook",
            "isEnabled": True,
            "isDebugMode": False,
            "steps": [],
            "relations": [],
        }
        unavailable_tel = PlaybookTelemetry(
            total_runs=0,
            lookback_days=30,
            telemetry_available=False,
            telemetry_error="RuntimeError: query timeout",
        )
        res = PlaybookScoringEngine.evaluate(playbook_def, unavailable_tel)
        self.assertNotIn("EXEC-01", [f.rule_id for f in res.findings])

        fake_engine = SimpleNamespace(adapter=MagicMock())
        fake_engine.adapter.execute_dashboard_query.side_effect = RuntimeError("stats offline")
        fake_engine.adapter.get_playbook_menu_cards.return_value = [
            {"identifier": "pb-1", "name": "Production Playbook", "categoryName": "Default"}
        ]
        fake_engine.adapter.get_playbook_full_info.return_value = playbook_def
        out = AuditPlaybookDecayWorkflow(fake_engine).execute(generate_brief=False, persist=False)
        self.assertFalse(out["summary"]["telemetry_available"])
        self.assertIn("stats offline", out["summary"]["telemetry_error"])

    def test_dashboard_health_marks_unknown_when_deep_inspection_fails(self):
        adapter = MagicMock()
        now_iso = datetime.now(timezone.utc).isoformat()
        adapter.list_native_dashboards.return_value = {
            "nativeDashboards": [
                {
                    "name": "projects/1/locations/us/instances/c/nativeDashboards/d1",
                    "displayName": "Custom Ops Dash",
                    "type": "CUSTOM",
                    "createTime": now_iso,
                    "updateTime": now_iso,
                }
            ]
        }
        adapter.get_native_dashboard.side_effect = RuntimeError("HTTP 403 permission denied")

        report = AuditDashboardHealthWorkflow(adapter).execute(validate_queries=True)
        self.assertEqual(report.empty_dashboard_count, 0)
        self.assertEqual(report.unknown_count, 1)
        self.assertEqual(report.findings[0].status, DashboardHealthStatus.UNKNOWN)
        self.assertIn("HTTP 403", report.findings[0].inspection_error or "")

    def test_data_table_health_marks_unknown_instead_of_orphan_when_rule_scan_fails(self):
        adapter = MagicMock()
        old_iso = (datetime.now(timezone.utc) - timedelta(days=300)).isoformat()
        adapter.list_data_tables.return_value = {
            "dataTables": [
                {
                    "name": "projects/1/locations/us/instances/c/dataTables/watchlist",
                    "displayName": "watchlist",
                    "approximateRowCount": "0",
                    "columnInfo": [
                        {"columnIndex": 0, "originalColumn": "ip", "columnType": "STRING", "keyColumn": True}
                    ],
                    "rules": [],
                    "ruleAssociationsCount": 0,
                    "createTime": old_iso,
                    "updateTime": old_iso,
                }
            ]
        }
        adapter.list_rules.side_effect = RuntimeError("rules API 500")

        report = AuditDataTableHealthWorkflow(adapter).execute(correlate_rules=True, stale_days=180)
        self.assertFalse(report.lineage_available)
        self.assertEqual(report.orphan_count, 0)
        self.assertEqual(report.unknown_count, 1)
        self.assertEqual(report.findings[0].status, DataTableHealthStatus.UNKNOWN)

    def test_case_triage_precedent_failure_never_claims_novel_detection(self):
        broken_search = MagicMock()
        broken_search.execute.side_effect = RuntimeError("search_cases 502")
        summary = _analyze_precedents(
            case_id="900",
            title="Suspicious PowerShell",
            entities=[
                InvolvedEntitySummary(
                    identifier="10.9.9.9",
                    display_name="10.9.9.9",
                    entity_type="ADDRESS",
                )
            ],
            search_workflow=broken_search,
        )
        self.assertFalse(summary.precedents_complete)
        self.assertFalse(summary.is_novel)
        self.assertIn("title_search", summary.precedent_errors)
        self.assertIn("entity:10.9.9.9", summary.precedent_errors)

        verdict, _, _, _ = _derive_verdict_and_recommendations(
            status=CaseStatus.OPEN,
            priority=CasePriority.MEDIUM,
            highest_alert_priority="MEDIUM",
            suspicious_entities=[],
            is_closed=False,
            alert_count=1,
            precedent_summary=summary,
        )
        self.assertNotEqual(verdict, TriageVerdict.NOVEL_DETECTION)

    def test_homepage_dashboard_flags_failed_udm_telemetry_instead_of_healthy_zero(self):
        adapter = MagicMock()
        adapter.project_id = ""
        adapter.project_number = ""
        adapter.location = "us"
        adapter.customer_id = "cust"
        adapter.execute_dashboard_query.side_effect = RuntimeError("UDM query 500")
        adapter.list_cases.side_effect = RuntimeError("cases 500")
        adapter.list_rules.side_effect = RuntimeError("rules 500")
        adapter.list_feeds.side_effect = RuntimeError("feeds 500")
        adapter.list_data_tables.side_effect = RuntimeError("dt 500")

        snap = fetch_tenant_health_snapshot(adapter)
        self.assertFalse(snap["udm_telemetry_available"])
        self.assertFalse(snap["telemetry_complete"])
        self.assertIn("udm_24h", snap["telemetry_errors"])

        exec_md = _format_ai_executive_summary_markdown([], [], {}, snap, "2026-11-14 15:00 UTC")
        self.assertIn("TELEMETRY UNAVAILABLE", exec_md)
        self.assertNotIn("Live tenant ingestion is healthy at **0 UDM events**", exec_md)

        pulse_md = _format_tenant_health_markdown(snap, "2026-11-14 15:00 UTC")
        self.assertIn("Unavailable", pulse_md)


class TestPhase1AdapterAndEmbeddings(unittest.TestCase):
    """Items 6 & 7: Adapter read shape validation, no hash vectors, narrative_source tracking."""

    def test_adapter_read_methods_reject_unexpected_response_shapes(self):
        ad = _bare_adapter()
        ad._request = lambda *a, **kw: "unexpected-html-string"

        for call in (
            lambda: ad.list_case_alerts("100"),
            lambda: ad.list_case_comments("100"),
            lambda: ad.search_cases("test"),
            lambda: ad.get_playbook_full_info("pb-1"),
            lambda: ad.list_integrations(),
            lambda: ad.get_native_dashboard("d-1"),
            lambda: ad.list_curated_rules(),
            lambda: ad.search_raw_logs('raw = "x"', "2026-01-01T00:00:00Z", "2026-01-02T00:00:00Z"),
        ):
            with self.assertRaises(RuntimeError):
                call()

        # Valid empty protobuf dict {} on collection endpoints still returns [] / {}
        ad._request = lambda *a, **kw: {}
        self.assertEqual(ad.list_case_alerts("100"), [])
        self.assertEqual(ad.list_integrations(), [])
        self.assertEqual(ad.search_raw_logs('raw = "x"', "2026-01-01T00:00:00Z", "2026-01-02T00:00:00Z"), [])

        # Auth errors on get_dashboard_chart are not swallowed
        def _raise_401(*a, **kw):
            raise SecOpsApiError(401, "unauthenticated")

        ad._request = _raise_401
        with self.assertRaises(SecOpsApiError):
            ad.get_dashboard_chart("chart-1")

    def test_hash_vector_fallback_removed_and_embeddings_raise_on_failure(self):
        self.assertFalse(hasattr(evidence_store_mod, "_deterministic_fallback_vector"))
        with tempfile.TemporaryDirectory() as tmp:
            store = LocalFileEvidenceStore(base_dir=tmp)
            broken_genai = SimpleNamespace(
                Client=MagicMock(side_effect=RuntimeError("no Vertex credentials"))
            )
            with patch.dict(
                "sys.modules",
                {"google": SimpleNamespace(genai=broken_genai), "google.genai": broken_genai},
            ):
                with self.assertRaisesRegex(RuntimeError, "Rule embedding generation failed"):
                    store.generate_rule_embeddings(["rule summary text"])

    def test_llm_narrative_fallbacks_record_deterministic_source_and_error(self):
        broken_genai = SimpleNamespace(
            Client=MagicMock(side_effect=RuntimeError("Gemini offline"))
        )
        with patch.dict(
            "sys.modules",
            {"google": SimpleNamespace(genai=broken_genai), "google.genai": broken_genai},
        ):
            # 1. PlaybookDecayReport
            pb_rep = PlaybookDecayReport(
                workflow_identifier="pb-1",
                numeric_id=1,
                name="PB",
                category="Default",
                is_enabled=True,
                is_debug_mode=False,
                priority=2,
                resilience_score=90,
                resilience_grade="A",
                findings=[],
                telemetry=PlaybookTelemetry(),
                mermaid_dag="flowchart TD",
            )
            brief = PlaybookBriefSynthesizer.synthesize(pb_rep, steps=[], project_id="proj")
            self.assertTrue(bool(brief))
            self.assertEqual(pb_rep.narrative_source, "deterministic_fallback")
            self.assertIn("Gemini offline", pb_rep.narrative_error or "")

            # 2. TimestampIntegrityWorkflow
            adapter = MagicMock()
            adapter.project_id = "proj"
            adapter.execute_dashboard_query.return_value = SimpleNamespace(rows=[])
            ts_rep = TimestampIntegrityWorkflow(adapter=adapter, evidence_store=None).execute(persist=False)
            self.assertEqual(ts_rep.narrative_source, "deterministic_fallback")
            self.assertIn("Gemini offline", ts_rep.narrative_error or "")
            self.assertEqual(ts_rep.to_dict()["run_metadata"]["narrative_source"], "deterministic_fallback")

            # 3. AuditRuleConflictWorkflow._compare_rules
            with tempfile.TemporaryDirectory() as tmp:
                store = LocalFileEvidenceStore(base_dir=tmp)
                rc_wf = AuditRuleConflictWorkflow(adapter=adapter, store=store)
                _, _, _, _, _, src, err = rc_wf._compare_rules(
                    target_name="Rule A",
                    target_text="",
                    target_sections={"condition": "$e"},
                    target_fields={"metadata.event_type"},
                    cand_name="Rule B",
                    cand_text="",
                    cand_sections={"condition": "$e"},
                    cand_fields={"metadata.event_type"},
                    sim_score=0.9,
                )
                self.assertEqual(src, "deterministic_fallback")
                self.assertIn("Gemini offline", err or "")


if __name__ == "__main__":
    unittest.main()
