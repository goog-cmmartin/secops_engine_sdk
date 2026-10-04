"""Operator Inbox: one list of everything that stops moving until a human acts."""

import os
from pathlib import Path
import tempfile
import unittest
from unittest import mock

from fastapi.testclient import TestClient

from agents.core.lifecycle import SOCLifecycleManager
from agents.core.materializer import IssueMaterializer
from agents.core.proposal_manager import ChangeProposal, PreflightProof, ProposalManager
from agents.core.work_queue import LocalWorkQueue
from engine.domain import IssueLifecycleStatus, IssueProblem, SOCIssue
import clients.web.server as web_server


class _Engine:
    def execute(self, capability_id, **kwargs):
        return {"status": "ok"}


class InboxEndpointTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        root = Path(self._tmp.name)
        self._prev_git = os.environ.get("SECOPS_DISABLE_GIT_COMMITS")
        os.environ["SECOPS_DISABLE_GIT_COMMITS"] = "1"
        self.queue = LocalWorkQueue(root_dir=str(root))
        self.lifecycle = SOCLifecycleManager(
            work_queue=self.queue,
            materializer=IssueMaterializer(root_dir=root / "ledger"),
            root_dir=root,
        )
        self.manager = ProposalManager(root_dir=root / "ledger")
        self._patches = [
            mock.patch.object(web_server, "proposal_manager", self.manager),
            mock.patch.object(web_server, "work_queue", self.queue),
            mock.patch.object(web_server, "lifecycle_manager", self.lifecycle),
            mock.patch.object(web_server, "ESCALATION_ACKS_PATH", root / "acks.json"),
        ]
        for p in self._patches:
            p.start()
        self.client = TestClient(web_server.app)

    def tearDown(self):
        for p in reversed(self._patches):
            p.stop()
        if self._prev_git is None:
            os.environ.pop("SECOPS_DISABLE_GIT_COMMITS", None)
        else:
            os.environ["SECOPS_DISABLE_GIT_COMMITS"] = self._prev_git
        self._tmp.cleanup()

    # --- fixtures ---
    def _proposal(self, pid, action_type="GENERIC_CAPABILITY", risk="MEDIUM", created_at=None):
        p = ChangeProposal(
            id=pid, title=f"{pid} title", author="@detection-tuning-agent", subsystem="rules",
            target_resource_id=f"ru_{pid}", action_type=action_type, risk_level=risk,
            preflight=PreflightProof(syntax_verified=True),
            mutation_payload={"capability_id": "noop", "kwargs": {}},
        )
        self.manager.create_proposal(p)
        if created_at:  # create_proposal stamps "now"; backdate for ordering tests
            p.created_at = created_at
            self.manager.update_proposal(p)

    def _auto_apply(self, pid):
        res = self.manager.approve_and_merge(pid, engine=_Engine(), merged_by="alice@corp", lifecycle_manager=self.lifecycle)
        self.assertTrue(res.success, res.error_message)

    def _stuck_issue(self, issue_id, severity="MEDIUM", status=IssueLifecycleStatus.NEEDS_HUMAN.value):
        self.queue.publish_issue(SOCIssue(
            id=issue_id, type="parser_drop_spike", severity=severity,
            problem=IssueProblem(title=f"{issue_id} problem", affected_objects=["WINEVTLOG"]),
        ))
        self.queue.record_attempt(issue_id, "@parser-doctor", "ESCALATED", "3 attempts, no proposal")
        self.queue.update_issue_status(issue_id, status)

    def _inbox(self, **params):
        res = self.client.get("/api/inbox", params=params)
        self.assertEqual(res.status_code, 200, res.text)
        return res.json()

    # --- tests ---
    def test_empty_inbox(self):
        data = self._inbox()
        self.assertEqual(data["items"], [])
        self.assertEqual(data["counts"]["total"], 0)
        self.assertIsNone(data["recent"])

    def test_three_groups_in_order(self):
        self._stuck_issue("SOC-STUCK-1")
        self._proposal("p-review")
        self._proposal("p-manual", action_type="PATCH_PARSER_CBN")
        self.manager.approve_and_merge("p-manual", engine=None, merged_by="alice@corp", lifecycle_manager=self.lifecycle)

        data = self._inbox()
        self.assertEqual([i["group"] for i in data["items"]], ["decide", "apply", "unstick"])
        self.assertEqual([i["kind"] for i in data["items"]], ["proposal_review", "manual_apply", "issue_attention"])
        self.assertEqual(data["counts"]["decide"], 1)
        self.assertEqual(data["counts"]["apply"], 1)
        self.assertEqual(data["counts"]["unstick"], 1)
        self.assertEqual(data["counts"]["total"], 3)

        issue_item = data["items"][2]
        self.assertEqual(issue_item["status_label"], "Needs human")
        self.assertEqual(issue_item["agent"], "@parser-doctor")
        self.assertEqual(issue_item["target"], "WINEVTLOG")
        self.assertEqual(issue_item["issue"]["attempts"][-1]["notes"], "3 attempts, no proposal")
        self.assertEqual(data["items"][0]["proposal"]["id"], "p-review")

    def test_applied_and_non_attention_items_excluded(self):
        self._proposal("p-auto")
        self._auto_apply("p-auto")
        self.queue.publish_issue(SOCIssue(id="SOC-AVAILABLE", type="parser_drop_spike"))
        data = self._inbox()
        self.assertEqual(data["items"], [], data["items"])

    def test_severity_then_oldest_first_within_group(self):
        self._proposal("p-new-med", created_at="2026-09-20T00:00:00+00:00")
        self._proposal("p-old-med", created_at="2026-09-01T00:00:00+00:00")
        self._proposal("p-crit", risk="CRITICAL", created_at="2026-09-25T00:00:00+00:00")
        ids = [i["proposal"]["id"] for i in self._inbox()["items"]]
        self.assertEqual(ids, ["p-crit", "p-old-med", "p-new-med"])

    def test_escalated_flag_and_count(self):
        self._proposal("p-high", risk="HIGH")
        self._proposal("p-low", risk="LOW")
        data = self._inbox()
        flags = {i["proposal"]["id"]: i["escalated"] for i in data["items"]}
        self.assertEqual(flags, {"p-high": True, "p-low": False})
        self.assertEqual(data["counts"]["escalated"], 1)

    def test_snooze_hides_from_count_and_unsnooze_restores(self):
        self._proposal("p-high", risk="HIGH")
        item = self._inbox()["items"][0]
        self.assertFalse(item["snoozed"])

        res = self.client.post(f"/api/gastown/escalations/{item['snooze_key']}/ack", json={})
        self.assertEqual(res.status_code, 200)
        data = self._inbox()
        self.assertTrue(data["items"][0]["snoozed"])
        self.assertEqual(data["counts"]["total"], 0)
        self.assertEqual(data["counts"]["snoozed"], 1)

        res = self.client.delete(f"/api/gastown/escalations/{item['snooze_key']}/ack")
        self.assertEqual(res.status_code, 200)
        self.assertTrue(res.json()["removed"])
        self.assertEqual(self._inbox()["counts"]["total"], 1)

    def test_snoozed_issue_resurfaces_after_new_attempt(self):
        self._stuck_issue("SOC-STUCK-1")
        key = self._inbox()["items"][0]["snooze_key"]
        self.client.post(f"/api/gastown/escalations/{key}/ack", json={})
        self.assertEqual(self._inbox()["counts"]["total"], 0)

        # Fleet tries again and re-escalates: a new attempt makes it new again.
        self.queue.record_attempt("SOC-STUCK-1", "@parser-doctor", "ESCALATED", "still failing")
        data = self._inbox()
        self.assertEqual(data["counts"]["total"], 1)
        self.assertNotEqual(data["items"][0]["snooze_key"], key)

    def test_proposal_snooze_key_shared_with_escalations_tab(self):
        self._proposal("p-high", risk="HIGH")
        self.assertEqual(self._inbox()["items"][0]["snooze_key"], "esc_p-high")

    def test_unack_rejects_invalid_id(self):
        self.assertEqual(self.client.delete("/api/gastown/escalations/nope/ack").status_code, 400)

    def test_recent_summary_counts_since_timestamp(self):
        self._proposal("p-auto")
        self._auto_apply("p-auto")
        self._proposal("p-rej")
        self.manager.reject_proposal("p-rej", reason="not needed", rejected_by="alice@corp", lifecycle_manager=self.lifecycle)
        self._stuck_issue("SOC-CLOSED")
        self.lifecycle.close_issue_manually("SOC-CLOSED", "alice", "fixed by hand", commit=False)

        recent = self._inbox(since="2000-01-01T00:00:00Z")["recent"]
        self.assertEqual(recent["auto_applied"], 1)
        self.assertEqual(recent["rejected"], 1)
        self.assertEqual(recent["issues_closed"], 1)

        future = self._inbox(since="2999-01-01T00:00:00Z")["recent"]
        self.assertEqual(
            {k: v for k, v in future.items() if k != "since"},
            {"auto_applied": 0, "manually_applied": 0, "rejected": 0, "issues_closed": 0, "new_items": 0},
        )

    def test_bad_since_is_ignored(self):
        self.assertIsNone(self._inbox(since="yesterday")["recent"])

    def test_proposal_endpoints_include_issue_id(self):
        self._proposal("p-review")
        self.assertIn("issue_id", self.client.get("/api/proposals").json()[0])
        self.assertIn("mutation_payload", self.client.get("/api/proposals/p-review").json())


if __name__ == "__main__":
    unittest.main()
