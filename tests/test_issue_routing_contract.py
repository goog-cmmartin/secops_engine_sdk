"""S5: every issue type the scheduler opens must be claimable by at least one real agent.

An issue is only claimable by an agent whose capability profile covers the issue's
``requires_capabilities`` in the issue's plane. A typo'd capability or a wrong plane
fails silently at runtime (the issue sits AVAILABLE forever), so it is checked here.
"""

import ast
import unittest
from pathlib import Path
from unittest import mock

from agents.core import fleet_scheduler
from agents.core.fleet_scheduler import ISSUE_ROUTING, unroutable_issue_types
from agents.core.issue_worker import ISSUE_PLAYBOOKS
from agents.generated import create_agent_fleet
from engine.domain import OperationalPlane

SCHEDULER_SOURCE = Path(fleet_scheduler.__file__)


def _scheduler_issue_types() -> set:
    """Literal ``type=`` values of every SOCIssue(...) built in fleet_scheduler.py."""
    tree = ast.parse(SCHEDULER_SOURCE.read_text())
    types = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and getattr(node.func, "id", None) == "SOCIssue":
            for kw in node.keywords:
                if kw.arg == "type" and isinstance(kw.value, ast.Constant):
                    types.add(kw.value.value)
    return types


class TestIssueRoutingContract(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.fleet = create_agent_fleet()

    def test_every_routed_issue_type_has_a_capable_agent_in_its_plane(self) -> None:
        self.assertEqual(unroutable_issue_types(self.fleet), {})

    def test_every_issue_the_scheduler_builds_is_in_the_routing_table(self) -> None:
        built = _scheduler_issue_types()
        self.assertTrue(built, "expected at least one SOCIssue(...) in fleet_scheduler.py")
        self.assertEqual(built - set(ISSUE_ROUTING), set())

    def test_scheduler_does_not_hand_write_capability_dicts(self) -> None:
        tree = ast.parse(SCHEDULER_SOURCE.read_text())
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and getattr(node.func, "id", None) == "IssueRouting":
                for kw in node.keywords:
                    if kw.arg == "requires_capabilities":
                        self.assertNotIsInstance(kw.value, ast.Dict, "use ISSUE_ROUTING, not an inline dict")

    def test_every_playbook_issue_type_is_routed(self) -> None:
        self.assertEqual(set(ISSUE_PLAYBOOKS) - set(ISSUE_ROUTING), set())

    def test_routing_entries_are_well_formed(self) -> None:
        planes = {p.value for p in OperationalPlane}
        for issue_type, spec in ISSUE_ROUTING.items():
            with self.subTest(issue_type=issue_type):
                self.assertIn(spec["plane"], planes)
                self.assertTrue(spec["requires_capabilities"], "an empty requirement set matches every agent")


class TestUnroutableDetection(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.fleet = create_agent_fleet()

    def test_flags_unknown_capability(self) -> None:
        bad = {"bogus_issue": {"plane": OperationalPlane.DATA.value, "requires_capabilities": {"cloud.audit_status": 1}}}
        with mock.patch.dict(ISSUE_ROUTING, bad, clear=True):
            problems = unroutable_issue_types(self.fleet)
        self.assertIn("bogus_issue", problems)
        self.assertIn("cloud.audit_status", problems["bogus_issue"])

    def test_flags_capability_held_only_outside_the_plane(self) -> None:
        # parser.run exists, but only on @parser-doctor in the data plane.
        bad = {"wrong_plane": {"plane": OperationalPlane.DETECTION.value, "requires_capabilities": {"parser.run": 1}}}
        with mock.patch.dict(ISSUE_ROUTING, bad, clear=True):
            self.assertIn("wrong_plane", unroutable_issue_types(self.fleet))

    def test_scheduler_logs_error_for_unroutable_type_at_startup(self) -> None:
        bad = {"bogus_issue": {"plane": OperationalPlane.DATA.value, "requires_capabilities": {"nope": 1}}}
        with mock.patch.dict(ISSUE_ROUTING, bad, clear=True), \
                self.assertLogs("agents.core.fleet_scheduler", level="ERROR") as logs:
            fleet_scheduler.FleetScheduler(fleet=self.fleet)
        self.assertTrue(any("bogus_issue" in line for line in logs.output))


if __name__ == "__main__":
    unittest.main()
