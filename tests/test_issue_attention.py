"""Issues needing a human (NEEDS_HUMAN, BLOCKED, ...): operator requeue/close and board visibility."""

import unittest

from fastapi.testclient import TestClient

from agents.core.issue_worker import OUTCOME_ESCALATED
from agents.core.work_queue import OPERATOR_REQUEUED_OUTCOME
from engine.domain import IssueLifecycleStatus
from tests.test_issue_worker import IssueWorkerTestBase, _parser_issue

ISSUE_ID = "SOC-DATA-PARSER-WINEVTLOG"


class TestOperatorRequeue(IssueWorkerTestBase):
    def _escalate(self, max_attempts: int = 2):
        self.lifecycle.open_issue(_parser_issue(), commit=False)
        agent = self.agent("decline")
        worker = self.worker(agent, retry_cooldown_seconds=0, max_attempts=max_attempts)
        for _ in range(max_attempts + 1):
            self.run_cycle(worker)
        self.assertEqual(self.queue.get_issue(ISSUE_ID).status, IssueLifecycleStatus.NEEDS_HUMAN.value)
        return agent, worker

    def test_requeue_resets_retry_budget_and_records_guidance(self) -> None:
        agent, worker = self._escalate()

        self.assertTrue(self.lifecycle.requeue_issue(ISSUE_ID, "alice", "check the EU collector", commit=False))
        issue = self.queue.get_issue(ISSUE_ID)
        self.assertEqual(issue.status, IssueLifecycleStatus.AVAILABLE.value)
        self.assertEqual(issue.attempts[-1]["outcome"], OPERATOR_REQUEUED_OUTCOME)
        self.assertEqual(issue.attempts[-1]["notes"], "check the EU collector")

        # Fresh budget: the worker picks it up again instead of re-escalating immediately.
        self.assertEqual(self.run_cycle(worker), [ISSUE_ID])
        self.assertEqual(len(agent.prompts), 3)

    def test_requeue_ledger_event(self) -> None:
        self._escalate()
        self.lifecycle.requeue_issue(ISSUE_ID, "alice", "", commit=False)
        events = self.lifecycle.materializer.list_issue_events(ISSUE_ID)
        self.assertEqual(events[-1].transition_type, "OPERATOR_REQUEUED")
        self.assertEqual(events[-1].details["previous_status"], IssueLifecycleStatus.NEEDS_HUMAN.value)

    def test_requeue_refuses_issue_not_needing_attention(self) -> None:
        self.lifecycle.open_issue(_parser_issue(), commit=False)
        self.assertFalse(self.lifecycle.requeue_issue(ISSUE_ID, "alice", commit=False))

    def test_close_manually(self) -> None:
        self._escalate()
        self.assertTrue(self.lifecycle.close_issue_manually(ISSUE_ID, "alice", "fixed parser by hand", commit=False))
        issue = self.queue.get_issue(ISSUE_ID)
        self.assertEqual(issue.status, IssueLifecycleStatus.CLOSED.value)
        self.assertIsNotNone(issue.closed_at)
        self.assertEqual(self.lifecycle.materializer.list_issue_events(ISSUE_ID)[-1].transition_type, "OPERATOR_CLOSED")
        # Idempotent: already closed.
        self.assertFalse(self.lifecycle.close_issue_manually(ISSUE_ID, "alice", "again", commit=False))


class TestAttentionEndpoints(unittest.TestCase):
    """Overview must surface escalated issues (board column + escalations) and expose requeue/close."""

    def setUp(self) -> None:
        from clients.web import server
        self.server = server
        self.client = TestClient(server.app)
        self.issue_id = "SOC-TEST-ATTENTION-ENDPOINTS"
        issue = _parser_issue(self.issue_id)
        issue.priority_score = 0  # lowest priority: must still survive the overview's top-N cut
        server.lifecycle_manager.open_issue(issue, commit=False)
        server.work_queue.record_attempt(self.issue_id, "fleet-worker", OUTCOME_ESCALATED, "3 attempts, no proposal")
        server.work_queue.update_issue_status(self.issue_id, IssueLifecycleStatus.NEEDS_HUMAN.value)

    def tearDown(self) -> None:
        issue = self.server.work_queue.get_issue(self.issue_id)
        if issue and issue.status != IssueLifecycleStatus.CLOSED.value:
            self.server.lifecycle_manager.close_issue_manually(self.issue_id, "test", "cleanup", commit=False)

    def test_overview_includes_needs_human_issue(self) -> None:
        data = self.client.get("/api/gastown/overview").json()
        ids = [i["issue_id"] for i in data["soc_issues"]]
        self.assertIn(self.issue_id, ids)
        self.assertGreaterEqual(data["summary"]["needs_attention_count"], 1)
        esc = [e for e in data["escalations"] if e.get("issue_id") == self.issue_id]
        self.assertEqual(len(esc), 1)
        self.assertTrue(esc[0]["soc_issue"])
        self.assertIn("Needs human", esc[0]["title"])
        self.assertEqual(esc[0]["details"], "3 attempts, no proposal")

    def test_requeue_endpoint(self) -> None:
        res = self.client.post(f"/api/soc/issues/{self.issue_id}/requeue", json={"guidance": "try again"})
        self.assertEqual(res.status_code, 200, res.text)
        self.assertEqual(self.server.work_queue.get_issue(self.issue_id).status, "AVAILABLE")
        # Second requeue: no longer needs attention.
        self.assertEqual(self.client.post(f"/api/soc/issues/{self.issue_id}/requeue", json={}).status_code, 409)

    def test_close_endpoint_requires_reason(self) -> None:
        self.assertEqual(self.client.post(f"/api/soc/issues/{self.issue_id}/close", json={"reason": ""}).status_code, 422)
        res = self.client.post(f"/api/soc/issues/{self.issue_id}/close", json={"reason": "resolved manually"})
        self.assertEqual(res.status_code, 200, res.text)
        self.assertEqual(self.server.work_queue.get_issue(self.issue_id).status, "CLOSED")

    def test_unknown_issue_404(self) -> None:
        self.assertEqual(self.client.post("/api/soc/issues/NOPE/requeue", json={}).status_code, 404)
        self.assertEqual(self.client.post("/api/soc/issues/NOPE/close", json={"reason": "whatever"}).status_code, 404)


if __name__ == "__main__":
    unittest.main()
