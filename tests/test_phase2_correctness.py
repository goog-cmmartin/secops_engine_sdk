"""Phase 2 verification tests: confirmed correctness bugs across adapter, engine, and agents."""

from __future__ import annotations

import ast
import io
import json
from pathlib import Path
import symtable
import tempfile
import threading
import unittest
from unittest import mock
import urllib.error

from adapters.google_secops import GoogleSecOpsAdapter, SecOpsApiError
from agents.core.proposal_manager import ChangeProposal, PreflightProof, ProposalManager
from engine.domain import LifecycleState, SearchRequest, StatsSearchResult, ValidationResult
from engine.facade import SecOpsEngine
from engine.registry import registry as global_catalog_registry
from engine.workflows.case_actions import AssignCaseWorkflow
from engine.workflows.dashboards import run_dashboard_health_check
from engine.workflows.job import UpdateJobInstanceWorkflow, UpdateJobWorkflow
from engine.workflows.playbook import UpdatePlaybookWidgetWorkflow
from engine.workflows.rule_conflict import (
    AuditRuleConflictWorkflow,
    BatchAuditRuleConflictsWorkflow,
    FindSimilarRulesWorkflow,
    SyncRuleEmbeddingsWorkflow,
)
from engine.workflows.search_udm import SearchUDMWorkflow


class _DummyCreds:
    def get_token(self) -> str:
        return "tok-test"

    def invalidate(self) -> None:
        pass


class _BytesResp:
    def __init__(self, payload: bytes = b"{}") -> None:
        self._payload = payload

    def read(self) -> bytes:
        return self._payload

    def __enter__(self) -> "_BytesResp":
        return self

    def __exit__(self, *args: object) -> bool:
        return False


def _bare_adapter() -> GoogleSecOpsAdapter:
    ad = GoogleSecOpsAdapter.__new__(GoogleSecOpsAdapter)
    ad.project_id = "proj-test"
    ad.project_number = "123456789"
    ad.location = "us"
    ad.customer_id = "00000000-0000-0000-0000-000000000001"
    ad.api_base = "https://us-chronicle.googleapis.com"
    ad.default_timeout = 5.0
    ad._credential_provider = _DummyCreds()
    return ad


class Phase2CorrectnessTests(unittest.TestCase):
    def test_repo_has_zero_undefined_names_via_symtable(self) -> None:
        import builtins

        repo_root = Path(__file__).resolve().parent.parent
        builtin_names = set(dir(builtins)) | {
            "__file__",
            "__name__",
            "__package__",
            "__doc__",
            "__spec__",
            "__path__",
            "__cached__",
            "__builtins__",
            "__annotations__",
        }

        def walk_symtable(st: symtable.SymbolTable, enclosing: set[str], out: list[tuple[str, str]]) -> None:
            local_defs = {
                s.get_name()
                for s in st.get_symbols()
                if s.is_local() or s.is_parameter() or s.is_imported() or s.is_declared_global()
            }
            visible = enclosing if st.get_type() == "class" else (enclosing | local_defs)
            for s in st.get_symbols():
                if s.is_global() and not s.is_declared_global() and not s.is_imported() and not s.is_local():
                    name = s.get_name()
                    if name not in visible and name not in builtin_names:
                        out.append((st.get_name(), name))
            next_enclosing = enclosing if st.get_type() == "class" else (enclosing | local_defs)
            for child in st.get_children():
                walk_symtable(child, next_enclosing, out)

        missing: list[str] = []
        for py_file in sorted(repo_root.rglob("*.py")):
            if any(part.startswith(".") or part == "__pycache__" for part in py_file.relative_to(repo_root).parts):
                continue
            src = py_file.read_text(encoding="utf-8")
            # Comment out postponed annotations so annotation expressions are symbol-checked too.
            lines = [
                ("# " + line if line.strip() == "from __future__ import annotations" else line)
                for line in src.splitlines()
            ]
            top = symtable.symtable("\n".join(lines), str(py_file), "exec")
            top_defs = {s.get_name() for s in top.get_symbols() if s.is_local() or s.is_imported()}
            file_undefs: list[tuple[str, str]] = []
            walk_symtable(top, top_defs, file_undefs)
            for scope, sym in file_undefs:
                missing.append(f"{py_file.relative_to(repo_root)}:{scope}:{sym}")

        self.assertEqual(missing, [], f"Undefined symbols detected: {missing}")

        import clients.cli.secops as cli_mod

        self.assertIs(cli_mod.json, json)

    def test_dashboard_health_check_uses_and_restores_adapter_location(self) -> None:
        ad = _bare_adapter()
        self.assertFalse(hasattr(ad, "region"))
        seen_locations: list[str] = []

        def fake_list_dashboards(page_size: int = 1000) -> dict:
            seen_locations.append(ad.location)
            return {
                "nativeDashboards": [
                    {
                        "name": "projects/123456789/locations/europe-west2/instances/00000000-0000-0000-0000-000000000001/nativeDashboards/d1",
                        "displayName": "Overview",
                        "type": "CUSTOM",
                    }
                ]
            }

        def fake_get_dashboard(dashboard_id: str) -> dict:
            return {
                "name": "projects/123456789/locations/europe-west2/instances/00000000-0000-0000-0000-000000000001/nativeDashboards/d1",
                "displayName": "Overview",
                "definition": {"charts": []},
            }

        ad.list_native_dashboards = fake_list_dashboards  # type: ignore[method-assign]
        ad.get_native_dashboard = fake_get_dashboard  # type: ignore[method-assign]
        res = run_dashboard_health_check(ad, "Overview", region="europe-west2")
        self.assertEqual(seen_locations, ["europe-west2"])
        self.assertTrue(res.dashboard_id.endswith("/d1"))
        self.assertEqual(ad.location, "us")

        # Also verify restoration on exception
        def boom_list(page_size: int = 1000) -> dict:
            raise RuntimeError("API failure")

        ad.list_native_dashboards = boom_list  # type: ignore[method-assign]
        with self.assertRaises(RuntimeError):
            run_dashboard_health_check(ad, "Overview", region="asia-southeast1")
        self.assertEqual(ad.location, "us")

    def test_stats_query_poll_loop_enforces_deadline_and_cancels(self) -> None:
        cancelled_ops: list[str] = []

        class _NeverCompleteStatsAdapter:
            def validate_query(self, query: str) -> ValidationResult:
                return ValidationResult(valid=True, raw_query_type="QUERY_TYPE_STATS_QUERY")

            def start_search(self, **kwargs: object) -> str:
                return "operations/stats-hang-1"

            def get_stats(self, operation_id: str, **kwargs: object) -> StatsSearchResult:
                return StatsSearchResult(complete=False, progress=0.25)

            def cancel_operation(self, operation_id: str) -> None:
                cancelled_ops.append(operation_id)

        wf = SearchUDMWorkflow(adapter=_NeverCompleteStatsAdapter())  # type: ignore[arg-type]
        req = SearchRequest(
            query="metadata.event_type = \"NETWORK_CONNECTION\" | stats count = count()",
            start_time="2026-10-01T00:00:00Z",
            end_time="2026-10-02T00:00:00Z",
        )
        fake_clock = iter([100.0, 100.2, 101.5, 102.0])
        with mock.patch("engine.workflows.search_udm.time.monotonic", side_effect=lambda: next(fake_clock)), \
                mock.patch("engine.workflows.search_udm.time.sleep"):
            session = wf.execute(req, poll_interval=0.1, max_poll_seconds=1.0)

        self.assertEqual(session.lifecycle, LifecycleState.FAILED)
        self.assertIn("timed out", session.error or "")
        self.assertEqual(cancelled_ops, ["operations/stats-hang-1"])

    def test_rule_conflict_workflows_accept_raw_dict_adapter_responses(self) -> None:
        class _DictRuleAdapter:
            def list_rule_deployments(self, page_size: int = 1000) -> dict:
                return {
                    "ruleDeployments": [
                        {
                            "name": "projects/p/locations/us/instances/c/rules/ru_1/deployment",
                            "enabled": True,
                            "alerting": True,
                        },
                        {
                            "name": "projects/p/locations/us/instances/c/rules/ru_2/deployment",
                            "enabled": True,
                            "alerting": False,
                        },
                    ]
                }

            def list_rules(self, page_size: int = 1000, view: str = "FULL") -> dict:
                return {
                    "rules": [
                        {
                            "name": "projects/p/locations/us/instances/c/rules/ru_1",
                            "displayName": "Rule One",
                            "text": 'rule RuleOne { events: $e.metadata.event_type = "PROCESS_LAUNCH" condition: $e }',
                            "revisionId": "v_1",
                        },
                        {
                            "name": "projects/p/locations/us/instances/c/rules/ru_2",
                            "displayName": "Rule Two",
                            "text": 'rule RuleTwo { events: $e.metadata.event_type = "PROCESS_LAUNCH" condition: $e }',
                            "revisionId": "v_2",
                        },
                    ]
                }

            def list_featured_content_rules(self, page_size: int = 1000) -> dict:
                return {"featuredContentRules": []}

            def get_rule(self, rule_id: str, view: str = "FULL") -> dict:
                return {
                    "name": f"projects/p/locations/us/instances/c/rules/{rule_id}",
                    "displayName": f"Display {rule_id}",
                    "text": f'rule {rule_id} {{ events: $e.metadata.event_type = "PROCESS_LAUNCH" condition: $e }}',
                    "revisionId": "v_1",
                }

        class _InMemoryStore:
            def __init__(self) -> None:
                self.saved_batches: list[dict] = []

            def get_rule_state(self, rule_id: str) -> None:
                return None

            def generate_rule_embeddings(self, texts: list[str]) -> list[list[float]]:
                return [[0.5, 0.5] for _ in texts]

            def batch_save_rule_embeddings(self, records: list[dict]) -> None:
                self.saved_batches.extend(records)

            def save_rule_embeddings(self, rule_id: str, vec: list[float], meta: dict) -> None:
                self.saved_batches.append({"rule_id": rule_id, "embedding": vec, **meta})

            def save_rule_conflict(self, rule_id: str, data: dict) -> None:
                pass

            def upsert_todo(self, *args: object, **kwargs: object) -> None:
                pass

            def find_similar_rules(
                self, target_rule_id: str, embedding: list[float] | None = None, limit: int = 6
            ) -> list[dict]:
                return [
                    {
                        "rule_id": "ru_2",
                        "rule_name": "Rule Two",
                        "similarity_score": 0.94,
                    }
                ]

        adapter = _DictRuleAdapter()
        store = _InMemoryStore()

        sync_res = SyncRuleEmbeddingsWorkflow(adapter, store=store).execute(include_curated=False)
        self.assertEqual(sync_res["embedded_count"], 2)
        self.assertEqual(store.saved_batches[0]["rule_id"], "ru_1")

        sim_res = FindSimilarRulesWorkflow(adapter, store=store).execute(rule_id="ru_1", auto_embed=False)
        self.assertEqual(len(sim_res), 1)
        self.assertEqual(sim_res[0]["rule_id"], "ru_2")

        with mock.patch.object(
            AuditRuleConflictWorkflow,
            "_compare_rules",
            return_value=("OVERLAP", "MEDIUM", "Shared fields", "Parameterize", "Keep separate", "deterministic_fallback", None),
        ):
            audit_res = AuditRuleConflictWorkflow(adapter, store=store).execute(rule_id="ru_1")
            self.assertEqual(audit_res.rule_id, "ru_1")
            self.assertTrue(audit_res.is_live)
            self.assertEqual(len(audit_res.conflicts), 1)

            batch_res = BatchAuditRuleConflictsWorkflow(adapter, store=store).execute(min_cos=0.0)
            self.assertEqual(batch_res.total_rules_scanned, 2)
            self.assertGreaterEqual(batch_res.total_pairs_evaluated, 1)

    def test_adapter_segment_and_filter_escaping_blocks_injection(self) -> None:
        ad = _bare_adapter()

        for bad_id in ("", "-", ".", "..", "cases/../other", "123?updateMask=*", "123#frag", "123\n456"):
            with self.assertRaises(ValueError, msg=f"Expected rejection for {bad_id!r}"):
                ad.get_case(bad_id)

        with self.assertRaises(ValueError):
            ad.list_remediation_plans(case_id="123 OR caseId > 0")

        with self.assertRaises(ValueError):
            ad.list_case_wall_records(case_id="123 OR 1=1")

        captured_urls: list[str] = []

        def fake_urlopen(req: urllib.request.Request, timeout: float = 5.0) -> _BytesResp:
            captured_urls.append(req.full_url)
            return _BytesResp(b'{"remoteAgents": [], "integrationInstances": []}')

        with mock.patch("urllib.request.urlopen", side_effect=fake_urlopen):
            ad.list_remote_agents(state_filter='ACTIVE" OR agentState != "')
            ad.list_integration_instances(environment="Prod' OR '1'='1")

        self.assertEqual(len(captured_urls), 2)
        decoded_0 = urllib.parse.unquote_plus(captured_urls[0])
        decoded_1 = urllib.parse.unquote_plus(captured_urls[1])
        self.assertIn('agentState = "ACTIVE\\" OR agentState != \\""', decoded_0)
        self.assertIn("environment = 'Prod\\' OR \\'1\\'=\\'1'", decoded_1)

    def test_request_retries_only_idempotent_calls_and_respects_budget(self) -> None:
        ad = _bare_adapter()

        # Non-idempotent POST (create_case_comment) must NOT retry on 503 or TimeoutError
        calls = 0

        def fail_503(req: urllib.request.Request, timeout: float = 5.0) -> _BytesResp:
            nonlocal calls
            calls += 1
            raise urllib.error.HTTPError(req.full_url, 503, "Unavailable", {}, io.BytesIO(b"{}"))

        with mock.patch("urllib.request.urlopen", side_effect=fail_503), \
                mock.patch("adapters.google_secops.time.sleep") as sleep_mock:
            with self.assertRaises(SecOpsApiError):
                ad.create_case_comment("101", "hello")
        self.assertEqual(calls, 1)
        sleep_mock.assert_not_called()

        # Idempotent POST (:validateQuery) retries when within retry budget, then stops once budget is exceeded
        ad.max_retry_budget_seconds = 3.0
        calls = 0
        clock = iter([0.0, 0.2, 2.8])  # 1st sleep 2.5s fits (0.2+2.5<=3.0); 2nd sleep 5.0s exceeds (2.8+5.0>3.0)

        with mock.patch("urllib.request.urlopen", side_effect=fail_503), \
                mock.patch("adapters.google_secops.time.monotonic", side_effect=lambda: next(clock)), \
                mock.patch("adapters.google_secops.time.sleep") as sleep_mock:
            with self.assertRaises(SecOpsApiError):
                ad._request("POST", "/v1alpha/projects/p/locations/us/instances/c:validateQuery", body={"query": "x"})
        self.assertEqual(calls, 2)
        sleep_mock.assert_called_once_with(2.5)

    def test_mutation_workflows_reject_unsafe_wildcards_and_empty_updates(self) -> None:
        adapter = mock.MagicMock(spec=GoogleSecOpsAdapter)
        adapter.get_playbook_full_info.return_value = {
            "id": 10,
            "identifier": "pb-uuid-10",
            "name": "Two Widgets PB",
            "steps": [{"identifier": "step-1", "name": "Step One", "parameters": []}],
            "viewsTemplates": [
                {
                    "cards": [
                        {
                            "title": "Widget A",
                            "stepIdentifier": "step-1",
                            "type": 3,
                            "widgetDefinition": json.dumps({"title": "Widget A", "htmlContent": "<p>A</p>"}),
                        },
                        {
                            "title": "Widget B",
                            "stepIdentifier": "step-2",
                            "type": 3,
                            "widgetDefinition": json.dumps({"title": "Widget B", "htmlContent": "<p>B</p>"}),
                        },
                    ]
                }
            ],
        }

        pb_wf = UpdatePlaybookWidgetWorkflow(adapter=adapter)
        # Missing step_name_or_id must raise ValueError rather than overwriting all widgets
        with self.assertRaisesRegex(ValueError, "not found in playbook"):
            pb_wf.execute("pb-uuid-10", "<p>new</p>", step_name_or_id="Nonexistent Step")
        # Out-of-range widget_index must raise ValueError rather than falling back to all cards
        with self.assertRaises(ValueError):
            pb_wf.execute("pb-uuid-10", "<p>new</p>", widget_index=99)
        with self.assertRaises(ValueError):
            pb_wf.execute("pb-uuid-10", "<p>new</p>", widget_index=-1)
        # Unscoped update on multi-widget playbook must raise ValueError
        with self.assertRaisesRegex(ValueError, "contains 2 HTML widgets"):
            pb_wf.execute("pb-uuid-10", "<p>new</p>")
        adapter.save_playbook.assert_not_called()

        # Empty UpdateJobWorkflow / UpdateJobInstanceWorkflow must raise ValueError instead of wiping script
        with self.assertRaisesRegex(ValueError, "At least one job field"):
            UpdateJobWorkflow(adapter).execute(integration="Int", job_id="1")
        with self.assertRaisesRegex(ValueError, "At least one job instance field"):
            UpdateJobInstanceWorkflow(adapter).execute(integration="Int", job_id="1", instance_id="2")
        adapter.update_job.assert_not_called()
        adapter.update_job_instance.assert_not_called()

        # AssignCaseWorkflow: ambiguous users and lookup errors raise instead of silently picking users[0] or raw email
        adapter.list_soar_users.return_value = {
            "legacySoarUsers": [
                {"id": "u-1", "displayName": "guid-1", "email": "alice@corp.example"},
                {"id": "u-2", "displayName": "guid-2", "email": "alice@corp.example"},
            ]
        }
        assign_wf = AssignCaseWorkflow(adapter=adapter)
        with self.assertRaisesRegex(ValueError, "Ambiguous SOAR user match"):
            assign_wf.execute("500", "alice@corp.example")

        adapter.list_soar_users.side_effect = RuntimeError("SOAR directory offline")
        with self.assertRaisesRegex(RuntimeError, "SOAR directory offline"):
            assign_wf.execute("500", "alice@corp.example")
        adapter.update_case.assert_not_called()

    def test_proposal_manager_parsing_unique_ids_and_atomic_locking(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            mgr = ProposalManager(root_dir=Path(tmp))

            # 1. Sub-second auto-generated IDs never collide, and --- / ``` inside content round-trips cleanly
            p1 = ChangeProposal(
                id="",
                title="Tune Rule --- High Volume",
                author="@yaral-optimizer",
                subsystem="detection_rules",
                target_resource_id="ru_1",
                action_type="PATCH_RULE",
                rationale="Line with --- separator\nand ```inline code``` block.",
                proposed_diff="--- a/rule.yaral\n+++ b/rule.yaral\n@@ -1 +1 @@\n-// ```note```\n+// fixed",
                preflight=PreflightProof(syntax_verified=True),
                mutation_payload={"rule_text": "rule r { condition: true }"},
            )
            p2 = ChangeProposal(
                id="",
                title="Second Proposal Same Second",
                author="@yaral-optimizer",
                subsystem="detection_rules",
                target_resource_id="ru_2",
                action_type="PATCH_RULE",
                preflight=PreflightProof(syntax_verified=True),
                mutation_payload={"rule_text": "rule r2 { condition: true }"},
            )
            id1 = mgr.create_proposal(p1)
            id2 = mgr.create_proposal(p2)
            self.assertNotEqual(id1, id2)

            parsed = mgr.get_proposal(id1)
            self.assertEqual(parsed.title, "Tune Rule --- High Volume")
            self.assertIn("--- separator", parsed.rationale)
            self.assertIn("// ```note```", parsed.proposed_diff)
            self.assertIn("+ // fixed".replace("+ ", "+"), parsed.proposed_diff)

            # Duplicate explicit ID is rejected instead of clobbering
            with self.assertRaisesRegex(ValueError, "already exists"):
                mgr.create_proposal(
                    ChangeProposal(
                        id=id1,
                        title="Clobber Attempt",
                        author="@yaral-optimizer",
                        subsystem="detection_rules",
                        target_resource_id="ru_9",
                        action_type="PATCH_RULE",
                    )
                )

            # 2. Concurrent approve_and_merge calls cannot double-apply the mutation
            barrier = threading.Barrier(2)
            apply_calls = 0
            apply_lock = threading.Lock()

            class _SlowEngine:
                def patch_rule(self, rule_id_or_name: str, rule_text: str, update_mask: str = "text") -> dict:
                    nonlocal apply_calls
                    with apply_lock:
                        apply_calls += 1
                    return {"name": rule_id_or_name}

            outcomes: list[object] = []

            def worker() -> None:
                barrier.wait()
                try:
                    res = mgr.approve_and_merge(id2, engine=_SlowEngine(), merged_by="lead@corp.example")
                    outcomes.append(res.status)
                except ValueError as exc:
                    outcomes.append(f"ERR:{exc}")

            t1 = threading.Thread(target=worker)
            t2 = threading.Thread(target=worker)
            t1.start()
            t2.start()
            t1.join()
            t2.join()

            self.assertEqual(apply_calls, 1)
            self.assertEqual(outcomes.count("MERGED"), 1)
            self.assertEqual(sum(1 for o in outcomes if str(o).startswith("ERR:")), 1)

    def test_global_registry_is_not_mutated_by_engine_instances(self) -> None:
        cap_before = global_catalog_registry.get("search_udm")
        self.assertIsNotNone(cap_before)

        sentinel_adapter = _bare_adapter()
        eng = SecOpsEngine(adapter=sentinel_adapter)
        cap_after = global_catalog_registry.get("search_udm")

        self.assertIs(cap_before, cap_after)
        self.assertFalse(hasattr(cap_after.handler, "__self__"))
        self.assertIs(getattr(eng.registry.get("search_udm").handler, "__self__", None), eng)

        with self.assertRaisesRegex(RuntimeError, "unbound module catalog"):
            global_catalog_registry.execute("search_udm", query="x")


if __name__ == "__main__":
    unittest.main()
