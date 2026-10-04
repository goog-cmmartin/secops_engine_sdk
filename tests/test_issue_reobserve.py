"""Re-observing an open issue must not reset its lifecycle (N1), and agents land in the right plane (S1)."""

from pathlib import Path
import re
import unittest

from agents.core.base_adk_agent import SUBSYSTEM_PLANES
from agents.core.issue_worker import OUTCOME_ESCALATED, failed_attempt_count
from agents.core.work_queue import REOPENED_OUTCOME
from engine.domain import IssueLifecycleStatus, IssueSeverity, OperationalPlane, VerificationProof
from tests.test_issue_worker import IssueWorkerTestBase, _parser_issue

ISSUE_ID = "SOC-DATA-PARSER-WINEVTLOG"
GENERATED_DIR = Path(__file__).resolve().parent.parent / "agents" / "generated"


class TestReobserveKeepsProgress(IssueWorkerTestBase):
    def _escalate(self) -> None:
        self.lifecycle.open_issue(_parser_issue(), commit=False)
        worker = self.worker(self.agent("decline"), retry_cooldown_seconds=0, max_attempts=2)
        for _ in range(3):
            self.run_cycle(worker)
        issue = self.queue.get_issue(ISSUE_ID)
        self.assertEqual(issue.status, IssueLifecycleStatus.NEEDS_HUMAN.value)

    def test_patrol_rerun_keeps_needs_human_and_attempts(self) -> None:
        self._escalate()
        before = self.queue.get_issue(ISSUE_ID)

        fresh = _parser_issue()
        fresh.severity = IssueSeverity.HIGH.value
        fresh.problem.observed_state = {"unparsed_count": 999}
        self.lifecycle.open_issue(fresh, deacon_id="deacon.parser_patrol", commit=False)

        after = self.queue.get_issue(ISSUE_ID)
        self.assertEqual(after.status, IssueLifecycleStatus.NEEDS_HUMAN.value)
        self.assertEqual(len(after.attempts), len(before.attempts))
        self.assertEqual(failed_attempt_count(after), failed_attempt_count(before))
        self.assertTrue(any(a.get("outcome") == OUTCOME_ESCALATED for a in after.attempts))
        # Problem definition is refreshed from the patrol.
        self.assertEqual(after.problem.observed_state, {"unparsed_count": 999})
        self.assertEqual(after.severity, IssueSeverity.HIGH.value)
        self.assertEqual(after.created_at, before.created_at)

    def test_patrol_rerun_keeps_active_lease(self) -> None:
        self.lifecycle.open_issue(_parser_issue(), commit=False)
        lease = self.lifecycle.claim_issue(ISSUE_ID, "@parser-doctor")
        self.assertIsNotNone(lease)

        self.lifecycle.open_issue(_parser_issue(), commit=False)

        after = self.queue.get_issue(ISSUE_ID)
        self.assertEqual(after.status, IssueLifecycleStatus.LEASED.value)
        self.assertIsNotNone(after.lease)
        self.assertEqual(after.lease.owner, "@parser-doctor")
        self.assertEqual(after.lease.generation, lease.generation)
        # Nobody else can grab it.
        self.assertIsNone(self.lifecycle.claim_issue(ISSUE_ID, "@someone-else"))

    def test_rerun_does_not_rematerialize_observed_event(self) -> None:
        self.lifecycle.open_issue(_parser_issue(), commit=False)
        self.lifecycle.open_issue(_parser_issue(), commit=False)
        events = self.lifecycle.materializer.list_issue_events(ISSUE_ID)
        self.assertEqual([e.transition_type for e in events], ["OBSERVED"])

    def test_closed_issue_reopens_with_fresh_budget(self) -> None:
        self._escalate()
        self.lifecycle.verify_and_close(
            ISSUE_ID,
            VerificationProof(verification_id="v1", change_id="", issue_id=ISSUE_ID, verifier_actor="deacon.parser_patrol"),
            commit=False,
        )
        self.assertEqual(self.queue.get_issue(ISSUE_ID).status, IssueLifecycleStatus.CLOSED.value)

        self.lifecycle.open_issue(_parser_issue(), deacon_id="deacon.parser_patrol", commit=False)

        after = self.queue.get_issue(ISSUE_ID)
        self.assertEqual(after.status, IssueLifecycleStatus.AVAILABLE.value)
        self.assertIsNone(after.closed_at)
        self.assertIsNone(after.lease)
        self.assertEqual(after.attempts[-1]["outcome"], REOPENED_OUTCOME)
        self.assertEqual(failed_attempt_count(after), 0)
        events = self.lifecycle.materializer.list_issue_events(ISSUE_ID)
        self.assertEqual(events[-1].transition_type, "REOPENED")

    def test_new_issue_is_available(self) -> None:
        opened = self.lifecycle.open_issue(_parser_issue(), commit=False)
        self.assertEqual(opened.status, IssueLifecycleStatus.AVAILABLE.value)
        self.assertEqual(self.queue.get_issue(ISSUE_ID).status, IssueLifecycleStatus.AVAILABLE.value)


class TestSubsystemPlanes(unittest.TestCase):
    EXPECTED = {
        "detection_tuning_agent.py": OperationalPlane.DETECTION.value,
        "detection_decay_agent.py": OperationalPlane.DETECTION.value,
        "rule_troubleshooter.py": OperationalPlane.DETECTION.value,
        "playbook_decay.py": OperationalPlane.AUTOMATION.value,
        "tenant_posture.py": OperationalPlane.GOVERNANCE.value,
        "cloud_status.py": OperationalPlane.EXTERNAL.value,
        "parser_health_agent.py": OperationalPlane.DATA.value,
    }

    @staticmethod
    def _subsystem(filename: str) -> str:
        src = (GENERATED_DIR / filename).read_text(encoding="utf-8")
        m = re.search(r"subsystem=['\"]([a-z_]+)['\"]", src)
        assert m, f"no subsystem= in {filename}"
        return m.group(1)

    def test_worker_agents_map_to_their_plane(self) -> None:
        for filename, plane in self.EXPECTED.items():
            with self.subTest(agent=filename):
                self.assertEqual(SUBSYSTEM_PLANES.get(self._subsystem(filename)), plane)

    def test_identity_governor_is_governance(self) -> None:
        self.assertEqual(SUBSYSTEM_PLANES["identity_governance"], OperationalPlane.GOVERNANCE.value)


if __name__ == "__main__":
    unittest.main()
