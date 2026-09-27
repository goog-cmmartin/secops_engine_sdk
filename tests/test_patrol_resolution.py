"""Patrols close issues whose problem cleared on its own (N2); cloud status is information only (A5)."""

from typing import Any, Dict, List, Optional, Tuple
import unittest

from agents.core.fleet_scheduler import LEGACY_CLOUD_STATUS_ISSUE_ID, FleetScheduler
from agents.core.issue_worker import OUTCOME_ESCALATED
from engine.domain import (
    IssueLifecycleStatus,
    IssueProblem,
    IssueRouting,
    OperationalPlane,
    SOCIssue,
    VerificationProof,
)
from tests.test_issue_worker import IssueWorkerTestBase, _parser_issue

PARSER_ISSUE_ID = "SOC-DATA-PARSER-WINEVTLOG"
NOW = "2026-09-26T12:00:00+00:00"
PARSER_SCHED = {"action": "audit_parsers"}
CLOUD_SCHED = {"action": "audit_cloud_service_status"}
HEALTHY_PARSER = {"findings": [{"log_type": "WINEVTLOG", "status": "HEALTHY", "unparsed_log_count": 0}]}
INCIDENT = {
    "overall_health": "DEGRADED",
    "active_incidents": [{"severity": "medium", "external_desc": "Chronicle ingestion delays", "service_name": "chronicle"}],
}


class _TodoStore:
    def __init__(self) -> None:
        self.todos: Dict[str, Dict[str, Any]] = {}
        self.resolved: List[str] = []

    def upsert_todo(self, todo_id: str, task: Dict[str, Any]) -> Tuple[Dict[str, Any], bool]:
        self.todos[todo_id] = task
        return task, True

    def resolve_todo(self, todo_id: str, reason: str = "") -> Optional[Dict[str, Any]]:
        self.resolved.append(todo_id)
        return self.todos.pop(todo_id, None)


class _Base(IssueWorkerTestBase):
    def setUp(self) -> None:
        super().setUp()
        self.todos = _TodoStore()
        self.scheduler = FleetScheduler(
            fleet={},
            evidence_store=self.todos,
            lifecycle_manager=self.lifecycle,
            work_queue=self.queue,
        )

    def patrol(self, handle: str, result: Dict[str, Any], sched: Dict[str, Any]) -> List[str]:
        return self.scheduler._auto_create_patrol_beads(handle, result, sched, NOW)

    def status(self, issue_id: str) -> Optional[str]:
        issue = self.queue.get_issue(issue_id)
        return issue.status if issue else None

    def events(self, issue_id: str) -> List[str]:
        return [e.transition_type for e in self.lifecycle.materializer.list_issue_events(issue_id)]


class TestParserSelfResolution(_Base):
    def test_available_issue_closes_when_parser_recovers(self) -> None:
        self.lifecycle.open_issue(_parser_issue(), commit=False)
        self.patrol("@parser-doctor", HEALTHY_PARSER, PARSER_SCHED)
        self.assertEqual(self.status(PARSER_ISSUE_ID), IssueLifecycleStatus.CLOSED.value)
        self.assertEqual(self.events(PARSER_ISSUE_ID)[-1], "RESOLVED_WITHOUT_CHANGE")
        # Nobody can claim it any more.
        self.assertIsNone(self.lifecycle.claim_issue(PARSER_ISSUE_ID, "@parser-doctor"))

    def test_needs_human_issue_closes_when_parser_recovers(self) -> None:
        self.lifecycle.open_issue(_parser_issue(), commit=False)
        worker = self.worker(self.agent("decline"), retry_cooldown_seconds=0, max_attempts=2)
        for _ in range(3):
            self.run_cycle(worker)
        issue = self.queue.get_issue(PARSER_ISSUE_ID)
        self.assertEqual(issue.status, IssueLifecycleStatus.NEEDS_HUMAN.value)
        self.assertTrue(any(a.get("outcome") == OUTCOME_ESCALATED for a in issue.attempts))

        self.patrol("@parser-doctor", HEALTHY_PARSER, PARSER_SCHED)
        self.assertEqual(self.status(PARSER_ISSUE_ID), IssueLifecycleStatus.CLOSED.value)

    def test_claimed_issue_is_left_to_its_agent(self) -> None:
        self.lifecycle.open_issue(_parser_issue(), commit=False)
        self.assertIsNotNone(self.lifecycle.claim_issue(PARSER_ISSUE_ID, "@parser-doctor"))
        self.patrol("@parser-doctor", HEALTHY_PARSER, PARSER_SCHED)
        issue = self.queue.get_issue(PARSER_ISSUE_ID)
        self.assertEqual(issue.status, IssueLifecycleStatus.LEASED.value)
        self.assertEqual(issue.lease.owner, "@parser-doctor")

    def test_applied_issue_still_verified_and_closed(self) -> None:
        self.lifecycle.open_issue(_parser_issue(), commit=False)
        self.queue.update_issue_status(PARSER_ISSUE_ID, IssueLifecycleStatus.APPLIED.value)
        self.patrol("@parser-doctor", HEALTHY_PARSER, PARSER_SCHED)
        self.assertEqual(self.status(PARSER_ISSUE_ID), IssueLifecycleStatus.CLOSED.value)
        self.assertNotIn("RESOLVED_WITHOUT_CHANGE", self.events(PARSER_ISSUE_ID))

    def test_resolve_without_change_ignores_closed(self) -> None:
        self.lifecycle.open_issue(_parser_issue(), commit=False)
        self.lifecycle.verify_and_close(
            PARSER_ISSUE_ID,
            VerificationProof(verification_id="v1", change_id="", issue_id=PARSER_ISSUE_ID, verifier_actor="t"),
            commit=False,
        )
        self.assertFalse(self.lifecycle.resolve_without_change(PARSER_ISSUE_ID, "t", "r", commit=False))
        self.assertFalse(self.lifecycle.resolve_without_change("missing", "t", "r", commit=False))


class TestCloudStatusInformationOnly(_Base):
    def test_incident_raises_todo_but_no_issue(self) -> None:
        created = self.patrol("@cloud-status-agent", INCIDENT, CLOUD_SCHED)
        self.assertEqual(created, ["todo_cloud_status_active"])
        self.assertIn("todo_cloud_status_active", self.todos.todos)
        self.assertIsNone(self.queue.get_issue(LEGACY_CLOUD_STATUS_ISSUE_ID))
        self.assertEqual(self.queue.list_issues(), [])

    def test_legacy_issue_is_retired_once(self) -> None:
        legacy = SOCIssue(
            id=LEGACY_CLOUD_STATUS_ISSUE_ID,
            type="upstream_cloud_disruption",
            plane=OperationalPlane.DATA.value,
            problem=IssueProblem(title="Upstream Google Cloud Disruption"),
            routing=IssueRouting(requires_capabilities={"cloud.audit_status": 1}),
        )
        self.lifecycle.open_issue(legacy, commit=False)

        self.patrol("@cloud-status-agent", INCIDENT, CLOUD_SCHED)
        self.assertEqual(self.status(LEGACY_CLOUD_STATUS_ISSUE_ID), IssueLifecycleStatus.CLOSED.value)
        self.patrol("@cloud-status-agent", {"active_incidents": []}, CLOUD_SCHED)
        self.assertEqual(self.events(LEGACY_CLOUD_STATUS_ISSUE_ID).count("OPERATOR_CLOSED"), 1)
        self.assertIn("todo_cloud_status_active", self.todos.resolved)


if __name__ == "__main__":
    unittest.main()
