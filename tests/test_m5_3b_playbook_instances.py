"""Authoritative Behavioral Tests for SOAR Playbook Run Instances (Milestone 5.3b).

Validates Tier-2 per-alert playbook *run instance* retrieval: the instance
cards endpoint (``legacyGetWorkflowInstancesCards``), the full-run endpoint
(``legacyGetWorkflowInstance``), and the executed step DAG.

The parser round-trip test runs offline (no credentials required) against a
frozen live-provenance response body so the DAG/definition-identifier contract
is enforced in CI. All endpoint-backed tests use live provenance with graceful
SkipTest on unconfigured environments. Invariants: zero mocks, strict error
visibility, live API provenance.
"""

from tests.test_helpers import get_live_engine
import os
import unittest

from engine import (
    PlaybookInstanceCard,
    PlaybookInstanceRelation,
    PlaybookInstanceRun,
    PlaybookInstanceStep,
)
from engine.workflows.playbook import GetAlertPlaybookInstancesWorkflow, _ms_to_dt


# Frozen live-provenance response body captured from legacyGetWorkflowInstance.
# Used only to enforce the parser contract offline; not synthetic input data.
_INSTANCE_PROVENANCE = {
    "id": "10",
    "identifier": "bd062ff5-1833-4d3f-a3d6-61af774d2a71",
    "isEnabled": True,
    "isDebugMode": True,
    "name": "SecOps Response",
    "priority": 3,
    "environments": ["*"],
    "categoryName": "Demoverse",
    "originalPlaybookIdentifier": "bd062ff5-1833-4d3f-a3d6-61af774d2a71",
    "creationTimeUnixTimeInMs": "1787421765613",
    "modificationTimeUnixTimeInMs": "1787421799226",
    "trigger": {
        "id": "428",
        "identifier": "eb4dd9c2-4b77-4967-96c0-2f0f34101ced",
        "type": "CASE_DATA",
        "logicalOperator": "OR",
        "conditions": [
            {
                "fieldName": "[Alert.DeviceVendor]",
                "value": "Chronicle",
                "matchType": "CONTAINS",
            }
        ],
        "reactionLogicalOperator": "OR",
    },
    "stepsRelations": [
        {"fromStep": "babdf100", "toStep": "003c4b50", "destinationActionStatus": "COMPLETED"},
        {"condition": "2", "fromStep": "6f0fcd33", "toStep": "14651d41", "destinationActionStatus": "NO_STATUS"},
        {"fromStep": "530644bb", "toStep": "6f0fcd33", "destinationActionStatus": "COMPLETED"},
    ],
    "steps": [
        {
            "identifier": "003c4b50",
            "name": "Get Case Details",
            "status": "COMPLETED",
            "actionName": "Get Details",
            "integration": "Siemplify",
            "isAutomatic": True,
            "startTimeUnixTimeInMs": "1787421770000",
            "endTimeUnixTimeInMs": "1787421771500",
        },
        {
            "identifier": "6f0fcd33",
            "name": "Enrich IP",
            "status": "NO_STATUS",
            "actionName": "Get IP Report",
        },
    ],
}


class TestPlaybookInstanceParser(unittest.TestCase):
    """Offline parser-contract suite (no credentials required)."""

    @classmethod
    def setUpClass(cls):
        # adapter is unused by the pure parser helpers.
        cls.wf = GetAlertPlaybookInstancesWorkflow(adapter=object())

    def test_full_run_parse_contract(self):
        """Validates the full-run parser maps the live body into PlaybookInstanceRun."""
        run = self.wf._parse_run(
            _INSTANCE_PROVENANCE, case_id="4231", alert_identifier="Rule.abc=_uuid"
        )
        self.assertIsInstance(run, PlaybookInstanceRun)
        self.assertEqual(run.identifier, "bd062ff5-1833-4d3f-a3d6-61af774d2a71")
        self.assertEqual(run.name, "SecOps Response")
        self.assertTrue(run.is_debug_mode)
        self.assertEqual(run.category_name, "Demoverse")
        self.assertEqual(run.case_id, "4231")
        self.assertEqual(run.alert_identifier, "Rule.abc=_uuid")
        self.assertEqual(
            run.original_playbook_identifier, "bd062ff5-1833-4d3f-a3d6-61af774d2a71"
        )
        # ms-epoch timestamp coercion
        self.assertIsNotNone(run.creation_time)
        self.assertEqual(run.creation_time.year, 2026)
        # raw retention
        self.assertEqual(run.raw.get("id"), "10")

    def test_definition_identifier_round_trip(self):
        """Cards -> full-run drill-down chains on definition_identifier."""
        card = self.wf._parse_card(_INSTANCE_PROVENANCE)
        run = self.wf._parse_run(
            _INSTANCE_PROVENANCE, case_id="4231", alert_identifier="x"
        )
        self.assertIsInstance(card, PlaybookInstanceCard)
        self.assertEqual(card.definition_identifier, run.identifier)

    def test_trigger_parse(self):
        """Trigger type and conditions surface as first-class fields."""
        run = self.wf._parse_run(_INSTANCE_PROVENANCE, case_id="1", alert_identifier="x")
        self.assertIsNotNone(run.trigger)
        self.assertEqual(run.trigger.trigger_type, "CASE_DATA")
        self.assertEqual(len(run.trigger.conditions), 1)
        self.assertEqual(run.trigger.conditions[0].value, "Chronicle")

    def test_execution_dag_edges(self):
        """All stepsRelations edges preserve condition + destination status."""
        run = self.wf._parse_run(_INSTANCE_PROVENANCE, case_id="1", alert_identifier="x")
        self.assertEqual(len(run.relations), 3)
        for rel in run.relations:
            self.assertIsInstance(rel, PlaybookInstanceRelation)
            self.assertTrue(rel.from_step)
            self.assertTrue(rel.to_step)
        conditional = next(r for r in run.relations if r.condition)
        self.assertEqual(conditional.condition, "2")
        self.assertEqual(conditional.from_step, "6f0fcd33")
        self.assertEqual(conditional.destination_action_status, "NO_STATUS")

    def test_step_runtime_state_and_duration(self):
        """Executed steps expose status and ms-derived duration."""
        run = self.wf._parse_run(_INSTANCE_PROVENANCE, case_id="1", alert_identifier="x")
        self.assertEqual(run.step_count, 2)
        self.assertEqual(run.completed_step_count, 1)
        completed = next(s for s in run.steps if s.status == "COMPLETED")
        self.assertIsInstance(completed, PlaybookInstanceStep)
        self.assertIsNotNone(completed.start_time)
        self.assertIsNotNone(completed.end_time)
        self.assertAlmostEqual(
            (completed.end_time - completed.start_time).total_seconds(), 1.5, places=3
        )
        pending = next(s for s in run.steps if s.status == "NO_STATUS")
        self.assertIsNone(pending.start_time)

    def test_group_identifier_heuristic(self):
        """Opaque group ids pass through; bare ids route to case-alert resolution."""
        self.assertTrue(
            self.wf._looks_like_group_identifier("Rule Name.aGFzaA==_3f2b-uuid")
        )
        self.assertFalse(self.wf._looks_like_group_identifier("9"))
        self.assertFalse(self.wf._looks_like_group_identifier(""))

    def test_ms_to_dt_helper(self):
        """ms-epoch helper is null-safe and UTC-aware."""
        self.assertIsNone(_ms_to_dt(None))
        self.assertIsNone(_ms_to_dt(""))
        dt = _ms_to_dt("1787421765613")
        self.assertIsNotNone(dt)
        self.assertIsNotNone(dt.tzinfo)


class TestPlaybookInstanceLiveCapabilities(unittest.TestCase):
    """Endpoint-backed suite; skips gracefully when tenant is unconfigured."""

    @classmethod
    def setUpClass(cls):
        cls.engine = get_live_engine()
        cls.adapter = cls.engine.adapter

    def _first_case_with_playbook(self):
        """Finds an alert carrying an attached playbook, or skips."""
        batch = self.engine.search_cases(page_size=25)
        for case in batch.results:
            statuses = self.engine.get_alert_playbook_status(case.case_id)
            for st in statuses:
                if st.attached_playbook_name:
                    return case.case_id, st
        raise unittest.SkipTest("No alert with an attached playbook found in recent cases.")

    def test_get_alert_playbook_instances(self):
        """Validates instance cards retrieval for a live alert."""
        case_id, status = self._first_case_with_playbook()
        cards = self.engine.get_alert_playbook_instances(
            case_id=case_id, alert_identifier=status.alert_group_identifier or status.alert_id
        )
        self.assertIsInstance(cards, list)
        for card in cards:
            self.assertIsInstance(card, PlaybookInstanceCard)
            self.assertTrue(card.definition_identifier)

    def test_get_alert_playbook_instance_full(self):
        """Validates full-run drill-down incl. steps and DAG for a live alert."""
        case_id, status = self._first_case_with_playbook()
        ident = status.alert_group_identifier or status.alert_id
        cards = self.engine.get_alert_playbook_instances(
            case_id=case_id, alert_identifier=ident
        )
        if not cards:
            raise unittest.SkipTest("Alert has no playbook run instances.")
        run = self.engine.get_alert_playbook_instance(
            case_id=case_id,
            alert_identifier=ident,
            definition_identifier=cards[0].definition_identifier,
        )
        self.assertIsInstance(run, PlaybookInstanceRun)
        self.assertEqual(run.identifier, cards[0].definition_identifier)
        self.assertIsInstance(run.steps, list)
        self.assertIsInstance(run.relations, list)

    def test_full_run_auto_resolves_definition_identifier(self):
        """Omitting definition_identifier resolves it from the first instance card."""
        case_id, status = self._first_case_with_playbook()
        ident = status.alert_group_identifier or status.alert_id
        cards = self.engine.get_alert_playbook_instances(
            case_id=case_id, alert_identifier=ident
        )
        if not cards:
            raise unittest.SkipTest("Alert has no playbook run instances.")
        run = self.engine.get_alert_playbook_instance(case_id=case_id, alert_identifier=ident)
        self.assertIsInstance(run, PlaybookInstanceRun)
        self.assertTrue(run.identifier)


class TestPlaybookInstanceRegistration(unittest.TestCase):
    """Capability registration + static compliance (runs fully offline)."""

    @classmethod
    def setUpClass(cls):
        from engine.facade import SecOpsEngine
        from engine.registry import WorkflowRegistry

        class _InertAdapter:
            def __getattr__(self, name):
                def _boom(*_a, **_k):
                    raise RuntimeError(f"inert adapter: {name} must not be called")
                return _boom

        cls.engine = SecOpsEngine(
            adapter=_InertAdapter(), custom_registry=WorkflowRegistry()
        )

    def test_capability_registered(self):
        """playbook.instances is registered in the Workflow Registry."""
        caps = self.engine.list_capabilities(category="playbook")
        cap_ids = [c.capability_id for c in caps]
        self.assertIn("playbook.instances", cap_ids)

    def test_static_anti_mock_audit(self):
        """Enforces the no-mock invariant across the instances implementation."""
        banned_terms = ["mock", "fixture", "dummy", "fake", "sample_data", "test_data"]
        target_files = ["engine/workflows/playbook.py"]
        base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
        for rel_path in target_files:
            full_path = os.path.join(base_dir, rel_path)
            self.assertTrue(os.path.exists(full_path), f"File missing: {rel_path}")
            with open(full_path, "r", encoding="utf-8") as f:
                lines = f.read().lower().splitlines()
            for idx, line in enumerate(lines, 1):
                for term in banned_terms:
                    if (
                        term in line
                        and "zero mock" not in line
                        and "no-mock" not in line
                        and "anti-mock" not in line
                    ):
                        self.fail(f"Banned term '{term}' found in {rel_path}:{idx}: {line}")



class TestExecutedPathTraversal(unittest.TestCase):
    """Offline DAG-collapse suite for PlaybookInstanceRun.executed_path()."""

    from datetime import datetime, timezone

    def _step(self, sid, status, secs=None):
        st = None
        if secs is not None:
            st = self.datetime(2026, 1, 1, 0, 0, secs, tzinfo=self.timezone.utc)
        return PlaybookInstanceStep(identifier=sid, name=sid, status=status, start_time=st)

    def _rel(self, f, t, cond=None):
        return PlaybookInstanceRelation(from_step=f, to_step=t, condition=cond)

    def _run(self, steps, relations):
        return PlaybookInstanceRun(
            instance_id="i", identifier="d", name="n", case_id="1",
            alert_identifier="a", steps=steps, relations=relations,
        )

    def test_empty_when_nothing_executed(self):
        run = self._run(
            [self._step("a", "NO_STATUS"), self._step("b", "PENDING")],
            [self._rel("a", "b")],
        )
        self.assertEqual(run.executed_path(), [])

    def test_linear_execution_order(self):
        run = self._run(
            [self._step("a", "COMPLETED", 1),
             self._step("b", "COMPLETED", 2),
             self._step("c", "COMPLETED", 3)],
            [self._rel("a", "b"), self._rel("b", "c")],
        )
        self.assertEqual([s.identifier for s in run.executed_path()], ["a", "b", "c"])

    def test_branch_only_taken_path_returned(self):
        # a -> {b (taken), c (not taken)} -> d
        run = self._run(
            [self._step("a", "COMPLETED", 1),
             self._step("b", "COMPLETED", 2),
             self._step("c", "NO_STATUS"),
             self._step("d", "COMPLETED", 3)],
            [self._rel("a", "b"), self._rel("a", "c"),
             self._rel("b", "d"), self._rel("c", "d")],
        )
        ids = [s.identifier for s in run.executed_path()]
        self.assertEqual(ids, ["a", "b", "d"])
        self.assertNotIn("c", ids)

    def test_failed_step_is_included(self):
        run = self._run(
            [self._step("a", "COMPLETED", 1), self._step("b", "FAILED", 2)],
            [self._rel("a", "b")],
        )
        self.assertEqual([s.identifier for s in run.executed_path()], ["a", "b"])

    def test_cycle_does_not_loop_forever(self):
        run = self._run(
            [self._step("a", "COMPLETED", 1), self._step("b", "COMPLETED", 2)],
            [self._rel("a", "b"), self._rel("b", "a")],
        )
        ids = [s.identifier for s in run.executed_path()]
        self.assertEqual(sorted(ids), ["a", "b"])
        self.assertEqual(len(ids), 2)  # no duplicates

    def test_disconnected_executed_island_appended_by_time(self):
        # x->y connected; z executed but unreachable, earliest time.
        run = self._run(
            [self._step("x", "COMPLETED", 5),
             self._step("y", "COMPLETED", 6),
             self._step("z", "COMPLETED", 1)],
            [self._rel("x", "y")],
        )
        ids = [s.identifier for s in run.executed_path()]
        # z and x are both roots (indeg 0); roots sort by start_time, so z (t=1)
        # precedes x (t=5), then x's successor y follows via the edge.
        self.assertEqual(ids, ["z", "x", "y"])



if __name__ == "__main__":
    unittest.main()
