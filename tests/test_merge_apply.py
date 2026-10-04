"""Merge only claims APPLIED when something was written to SecOps (N3).

Action types with an executor are applied on merge. Action types without one
(PATCH_PARSER_CBN, REMEDIATE_FEED, ...) merge as MANUAL_APPLY_REQUIRED, leave the
linked issue open (APPROVED), and move to APPLIED only when a human marks them applied.
"""

import os
from pathlib import Path
import tempfile
import unittest

from agents.core.approval_policy import ApprovalPolicyError
from agents.core.lifecycle import SOCLifecycleManager
from agents.core.materializer import IssueMaterializer
from agents.core.proposal_manager import (
    APPLY_STATUS_ABANDONED,
    APPLY_STATUS_APPLIED,
    APPLY_STATUS_MANUAL_REQUIRED,
    APPLY_STATUS_MANUALLY_APPLIED,
    MERGED_MANUAL_APPLY_REQUIRED,
    ChangeProposal,
    PreflightProof,
    ProposalManager,
    has_executor,
)
from agents.core.work_queue import LocalWorkQueue
from engine.domain import IssueLifecycleStatus, SOCIssue
from engine.domain import FindingsRefinementSummary


class _Engine:
    def __init__(self):
        self.refinements = []
        self.patched = []

    def patch_rule(self, rule_id_or_name, rule_text, update_mask="text"):
        self.patched.append(rule_id_or_name)
        return {"name": rule_id_or_name}

    def create_findings_refinement(self, display_name, query, curated_rule_ids=None):
        self.refinements.append({"display_name": display_name, "query": query, "rules": curated_rule_ids})
        return FindingsRefinementSummary(
            id="fr_1", name="findingsRefinements/fr_1", display_name=display_name,
            type="DETECTION_EXCLUSION", query=query, curated_rule_ids=curated_rule_ids or [],
        )


class MergeApplyTests(unittest.TestCase):
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
        self.engine = _Engine()

    def tearDown(self):
        if self._prev_git is None:
            os.environ.pop("SECOPS_DISABLE_GIT_COMMITS", None)
        else:
            os.environ["SECOPS_DISABLE_GIT_COMMITS"] = self._prev_git
        self._tmp.cleanup()

    def _issue(self, issue_id="SOC-N3-1"):
        self.queue.publish_issue(SOCIssue(id=issue_id, type="parser_drop_spike"))
        self.queue.update_issue_status(issue_id, IssueLifecycleStatus.VALIDATING.value)
        return issue_id

    def _create(self, pid, action_type, payload, issue_id=None, target="WINEVTLOG"):
        self.manager.create_proposal(ChangeProposal(
            id=pid, title=f"{action_type} proposal", author="@parser-doctor", subsystem="parsers",
            target_resource_id=target, action_type=action_type, issue_id=issue_id,
            mutation_payload=payload, preflight=PreflightProof(syntax_verified=True),
        ))

    def test_executor_table(self):
        for action in ("UPDATE_RULE_TEXT", "PATCH_RULE", "DEPLOY_RULE", "GENERIC_CAPABILITY", "CREATE_FINDINGS_REFINEMENT"):
            self.assertTrue(has_executor(action), action)
        for action in ("PATCH_PARSER_CBN", "REMEDIATE_FEED", "RULE_OPTIMIZATION", ""):
            self.assertFalse(has_executor(action), action)

    def test_parser_patch_merges_as_manual_apply_and_issue_stays_open(self):
        issue_id = self._issue()
        self._create("p-cbn", "PATCH_PARSER_CBN", {"log_type": "WINEVTLOG", "cbn_snippet": "filter {}"}, issue_id)

        res = self.manager.approve_and_merge("p-cbn", engine=self.engine, merged_by="alice@corp",
                                             lifecycle_manager=self.lifecycle)

        self.assertTrue(res.success)
        self.assertEqual(res.status, MERGED_MANUAL_APPLY_REQUIRED)
        self.assertEqual(res.execution_result["status"], MERGED_MANUAL_APPLY_REQUIRED)
        merged = self.manager.get_proposal("p-cbn")
        self.assertEqual(merged.status, "MERGED")
        self.assertEqual(merged.apply_status, APPLY_STATUS_MANUAL_REQUIRED)
        self.assertIsNone(merged.applied_by)
        issue = self.queue.get_issue(issue_id)
        self.assertEqual(issue.status, IssueLifecycleStatus.APPROVED.value)
        self.assertFalse(issue.applied_change_id)

    def test_mark_manually_applied_moves_issue_to_applied(self):
        issue_id = self._issue()
        self._create("p-cbn", "PATCH_PARSER_CBN", {"log_type": "WINEVTLOG"}, issue_id)
        self.manager.approve_and_merge("p-cbn", engine=self.engine, merged_by="alice@corp",
                                       lifecycle_manager=self.lifecycle)

        with self.assertRaises(ValueError):
            self.manager.mark_manually_applied("p-cbn", applied_by="bob@corp", note="done",
                                               lifecycle_manager=self.lifecycle)
        with self.assertRaises(ApprovalPolicyError):
            self.manager.mark_manually_applied("p-cbn", applied_by="@parser-doctor",
                                               note="Applied the CBN patch in console",
                                               lifecycle_manager=self.lifecycle)

        p = self.manager.mark_manually_applied("p-cbn", applied_by="bob@corp",
                                               note="Pasted CBN patch into WINEVTLOG extension",
                                               lifecycle_manager=self.lifecycle)
        self.assertEqual(p.apply_status, APPLY_STATUS_MANUALLY_APPLIED)
        reread = self.manager.get_proposal("p-cbn")
        self.assertEqual(reread.apply_status, APPLY_STATUS_MANUALLY_APPLIED)
        self.assertEqual(reread.applied_by, "bob@corp")
        self.assertIn("WINEVTLOG", reread.apply_note)
        issue = self.queue.get_issue(issue_id)
        self.assertEqual(issue.status, IssueLifecycleStatus.APPLIED.value)
        self.assertEqual(issue.applied_change_id, "p-cbn")

        with self.assertRaises(ValueError):  # only once
            self.manager.mark_manually_applied("p-cbn", applied_by="bob@corp",
                                               note="Pasted CBN patch again", lifecycle_manager=self.lifecycle)

    def test_mark_applied_rejects_open_and_auto_applied(self):
        self._create("p-open", "PATCH_PARSER_CBN", {})
        with self.assertRaises(ValueError):
            self.manager.mark_manually_applied("p-open", applied_by="bob@corp", note="Applied it in console")
        with self.assertRaises(FileNotFoundError):
            self.manager.mark_manually_applied("p-missing", applied_by="bob@corp", note="Applied it in console")

        self._create("p-rule", "UPDATE_RULE_TEXT", {"rule_text": "rule x { condition: true }"}, target="ru_1")
        self.manager.approve_and_merge("p-rule", engine=self.engine, merged_by="alice@corp")
        self.assertEqual(self.manager.get_proposal("p-rule").apply_status, APPLY_STATUS_APPLIED)
        with self.assertRaises(ValueError):
            self.manager.mark_manually_applied("p-rule", applied_by="bob@corp", note="Applied it in console")

    def test_findings_refinement_is_written_and_issue_applied(self):
        issue_id = self._issue()
        self._create(
            "p-fr", "CREATE_FINDINGS_REFINEMENT",
            {"rule_id": "ur_abc", "tuned_rule_text": "// UDM Findings Refinement Exclusion\nprincipal.hostname = /^build-/"},
            issue_id, target="ur_abc",
        )
        res = self.manager.approve_and_merge("p-fr", engine=self.engine, merged_by="alice@corp",
                                             lifecycle_manager=self.lifecycle)

        self.assertTrue(res.success, res.error_message)
        self.assertEqual(res.status, "MERGED")
        self.assertEqual(self.engine.refinements, [{
            "display_name": "CREATE_FINDINGS_REFINEMENT proposal",
            "query": "principal.hostname = /^build-/",
            "rules": ["ur_abc"],
        }])
        self.assertEqual(self.manager.get_proposal("p-fr").apply_status, APPLY_STATUS_APPLIED)
        self.assertEqual(self.queue.get_issue(issue_id).status, IssueLifecycleStatus.APPLIED.value)

    def test_findings_refinement_without_query_fails_and_stays_open(self):
        self._create("p-fr-empty", "CREATE_FINDINGS_REFINEMENT", {"tuned_rule_text": "// header only"}, target="ur_abc")
        res = self.manager.approve_and_merge("p-fr-empty", engine=self.engine, merged_by="alice@corp")
        self.assertFalse(res.success)
        self.assertEqual(self.engine.refinements, [])
        self.assertEqual(self.manager.get_proposal("p-fr-empty").status, "OPEN")

    def test_abandon_manual_apply_returns_issue_to_human(self):
        issue_id = self._issue()
        self._create("p-cbn", "PATCH_PARSER_CBN", {"log_type": "WINEVTLOG"}, issue_id)
        self.manager.approve_and_merge("p-cbn", engine=self.engine, merged_by="alice@corp",
                                       lifecycle_manager=self.lifecycle)

        with self.assertRaises(ValueError):  # reason too short
            self.manager.abandon_manual_apply("p-cbn", abandoned_by="bob@corp", reason="nope",
                                              lifecycle_manager=self.lifecycle)
        with self.assertRaises(ApprovalPolicyError):
            self.manager.abandon_manual_apply("p-cbn", abandoned_by="@parser-doctor",
                                              reason="Vendor fixed the format upstream",
                                              lifecycle_manager=self.lifecycle)

        p = self.manager.abandon_manual_apply("p-cbn", abandoned_by="bob@corp",
                                              reason="Vendor fixed the format upstream",
                                              lifecycle_manager=self.lifecycle)
        self.assertEqual(p.apply_status, APPLY_STATUS_ABANDONED)
        reread = self.manager.get_proposal("p-cbn")
        self.assertEqual(reread.status, "MERGED")
        self.assertEqual(reread.apply_status, APPLY_STATUS_ABANDONED)
        self.assertEqual(reread.abandoned_by, "bob@corp")
        self.assertTrue(reread.abandoned_at)
        self.assertEqual(reread.abandon_reason, "Vendor fixed the format upstream")
        self.assertIsNone(reread.applied_by)

        issue = self.queue.get_issue(issue_id)
        self.assertEqual(issue.status, IssueLifecycleStatus.NEEDS_HUMAN.value)
        self.assertFalse(issue.applied_change_id)
        self.assertEqual(issue.attempts[-1]["outcome"], "CHANGE_ABANDONED")
        events = self.lifecycle.materializer.list_issue_events(issue_id)
        self.assertEqual(events[-1].transition_type, "PROPOSAL_ABANDONED")
        self.assertEqual(events[-1].details["proposal_id"], "p-cbn")
        # NEEDS_HUMAN is operator-actionable: requeue works from here.
        self.assertTrue(self.lifecycle.requeue_issue(issue_id, "bob@corp", "Try the v2 grok pattern"))

        with self.assertRaises(ValueError):  # terminal: cannot abandon or apply again
            self.manager.abandon_manual_apply("p-cbn", abandoned_by="bob@corp",
                                              reason="Vendor fixed the format upstream")
        with self.assertRaises(ValueError):
            self.manager.mark_manually_applied("p-cbn", applied_by="bob@corp", note="Applied it in console")

    def test_abandon_rejects_open_missing_and_auto_applied(self):
        self._create("p-open", "PATCH_PARSER_CBN", {})
        with self.assertRaises(ValueError):
            self.manager.abandon_manual_apply("p-open", abandoned_by="bob@corp", reason="Not needed any more")
        with self.assertRaises(FileNotFoundError):
            self.manager.abandon_manual_apply("p-missing", abandoned_by="bob@corp", reason="Not needed any more")
        self._create("p-rule", "UPDATE_RULE_TEXT", {"rule_text": "rule x { condition: true }"}, target="ru_1")
        self.manager.approve_and_merge("p-rule", engine=self.engine, merged_by="alice@corp")
        with self.assertRaises(ValueError):
            self.manager.abandon_manual_apply("p-rule", abandoned_by="bob@corp", reason="Not needed any more")

    def test_abandon_without_linked_issue(self):
        self._create("p-feed", "REMEDIATE_FEED", {"feed_id": "f1"}, target="f1")
        self.manager.approve_and_merge("p-feed", engine=self.engine, merged_by="alice@corp",
                                       lifecycle_manager=self.lifecycle)
        p = self.manager.abandon_manual_apply("p-feed", abandoned_by="bob@corp",
                                              reason="Feed was decommissioned instead",
                                              lifecycle_manager=self.lifecycle)
        self.assertEqual(p.apply_status, APPLY_STATUS_ABANDONED)

    def test_legacy_merged_proposal_without_apply_status_is_inferred(self):
        self._create("p-legacy", "REMEDIATE_FEED", {"feed_id": "f1"}, target="f1")
        self.manager.approve_and_merge("p-legacy", engine=self.engine, merged_by="alice@corp")
        path = self.manager.merged_dir / "p-legacy.md"
        path.write_text(path.read_text().replace("apply_status: MANUAL_APPLY_REQUIRED\n", ""))
        self.assertNotIn("apply_status: MANUAL", path.read_text())
        self.assertEqual(self.manager.get_proposal("p-legacy").apply_status, APPLY_STATUS_MANUAL_REQUIRED)


if __name__ == "__main__":
    unittest.main()
