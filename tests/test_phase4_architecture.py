"""Phase 4 verification tests: engine layer isolation, registry toolset builder, and related-cases workflow."""

from __future__ import annotations

from datetime import datetime, timezone
import inspect
import sys
from types import SimpleNamespace
import unittest
from unittest import mock

from engine.agent_tools import build_registry_toolset, is_read_only_capability
from engine.domain import CasePriority, CaseStatus
from engine.facade import SecOpsEngine
from engine.workflows.playbook_decay import AuditPlaybookDecayWorkflow
from engine.workflows.playbook_health import AuditPlaybookHealthWorkflow
from engine.workflows.related_cases_by_entity import RelatedCasesByEntityWorkflow


class Phase4ArchitectureTests(unittest.TestCase):
    def test_engine_workflows_run_standalone_when_agents_and_runbooks_unavailable(self) -> None:
        adapter = mock.MagicMock()
        adapter.get_playbook_menu_cards.return_value = []
        adapter.execute_dashboard_query.return_value = mock.MagicMock(rows=[])

        with mock.patch.dict(
            sys.modules,
            {
                "agents": None,
                "agents.core": None,
                "agents.core.evidence_store": None,
                "runbooks": None,
                "runbooks.operations": None,
                "runbooks.operations.soar_playbook_health": None,
            },
        ):
            eng = SecOpsEngine(adapter=adapter)
            pb_health = AuditPlaybookHealthWorkflow(eng).execute(days=7, scan_deep=False)
            self.assertEqual(pb_health["summary"]["total_playbooks"], 0)

            pb_decay = AuditPlaybookDecayWorkflow(eng).execute(limit=5, persist=False)
            self.assertEqual(len(pb_decay["playbooks"]), 0)

    def test_build_registry_toolset_enforces_read_only_default_tool_filter_and_invariant9(self) -> None:
        adapter = mock.MagicMock()
        eng = SecOpsEngine(adapter=adapter)

        ro_tools = build_registry_toolset(eng, include_mutations=False)
        ro_names = {t.__name__ for t in ro_tools}
        self.assertGreater(len(ro_tools), 40)

        # Mutating primitives and side-effecting workflows are excluded by default
        for mut_name in (
            "add_case_comment",
            "update_case",
            "delete_rule",
            "patch_rule",
            "save_playbook",
            "delete_data_table_row",
            "find_related_cases_by_entity",
        ):
            self.assertNotIn(mut_name, ro_names)

        # Requesting a mutating capability explicitly with include_mutations=False raises PermissionError
        with self.assertRaises(PermissionError):
            build_registry_toolset(eng, capability_ids=["case.comment"], include_mutations=False)

        # Requesting with include_mutations=True exposes it cleanly
        mut_tools = build_registry_toolset(eng, capability_ids=["case.comment"], include_mutations=True)
        self.assertEqual([t.__name__ for t in mut_tools], ["add_case_comment"])

        # tool_filter restricts exposed tools strictly and preserves clean non-callback signatures
        filtered = build_registry_toolset(
            eng,
            tool_filter=["investigate_case", "list_rules"],
            include_mutations=False,
        )
        by_name = {t.__name__: t for t in filtered}
        self.assertEqual(set(by_name.keys()), {"investigate_case", "list_rules"})

        for fn in filtered:
            sig = inspect.signature(fn)
            for param in sig.parameters.values():
                self.assertNotIn("Callable", str(param.annotation))

        # Unbounded query (list_rules) enforces Invariant #9 filter requirement
        with self.assertRaisesRegex(ValueError, "cardinality='unbounded'"):
            by_name["list_rules"]()

        # Verify is_read_only_capability detects side-effecting composed workflow
        rel_cap = eng.registry.get("case.related_by_entity")
        self.assertIsNotNone(rel_cap)
        self.assertFalse(is_read_only_capability(rel_cap, eng.registry))

    def test_related_cases_by_entity_records_partial_errors_and_raises_on_total_failure(self) -> None:
        adapter = mock.MagicMock()
        wf = RelatedCasesByEntityWorkflow(adapter=adapter)
        wf.investigate_workflow = mock.MagicMock()
        wf.investigate_workflow.execute.return_value = SimpleNamespace(
            case_id="100",
            display_name="Primary Case",
            status=CaseStatus.OPEN,
            priority=CasePriority.HIGH,
            stage="Triage",
            alerts=[],
            entities=[
                SimpleNamespace(identifier="198.51.100.10", entity_type="IP", display_name="198.51.100.10", role="SOURCE", is_suspicious=True),
                SimpleNamespace(identifier="evil.example", entity_type="DOMAIN", display_name="evil.example", role="TARGET", is_suspicious=False),
            ],
            comments=[],
        )

        # Partial failure: 1 entity succeeds, 1 entity fails -> partial=True & entity_search_errors populated
        def partial_search(query):
            if "198.51.100.10" in query.query_text:
                return SimpleNamespace(
                    results=[
                        SimpleNamespace(
                            case_id="200",
                            title="Related Case",
                            priority=CasePriority.HIGH,
                            stage="Investigation",
                            is_closed=False,
                            is_incident=True,
                            is_important=False,
                            alerts_count=2,
                            create_time=datetime(2026, 10, 1, tzinfo=timezone.utc),
                            user_assigned="Unassigned",
                            environment="Default Environment",
                            products=["EDR"],
                            tags=[],
                            ticket_ids=[],
                        )
                    ],
                    total_count=1,
                )
            raise RuntimeError("search backend timeout")

        wf.search_cases_workflow = mock.MagicMock()
        wf.search_cases_workflow.execute.side_effect = partial_search

        res = wf.execute("100")
        self.assertTrue(res.partial)
        self.assertIn("evil.example", res.entity_search_errors)
        self.assertEqual(res.total_related_cases, 1)
        self.assertEqual(res.related_cases[0]["case_id"], "200")

        # Total failure across all searched entities raises RuntimeError instead of returning "0 related cases"
        wf.search_cases_workflow.execute.side_effect = RuntimeError("SOAR search unavailable")
        with self.assertRaisesRegex(RuntimeError, "All 2 entity case searches failed"):
            wf.execute("100")


if __name__ == "__main__":
    unittest.main()
