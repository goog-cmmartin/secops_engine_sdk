"""Tests for lease reclamation (expired leases return to the pool) and
server-side approval policy enforcement on change proposals."""

from datetime import datetime, timedelta, timezone
import os
from pathlib import Path
import shutil
import tempfile
import unittest

from agents.core.approval_policy import ApprovalPolicyError, check_approval, required_tier
from agents.core.lifecycle import SOCLifecycleManager
from agents.core.materializer import IssueMaterializer
from agents.core.proposal_manager import ChangeProposal, PreflightProof, ProposalManager
from agents.core.work_queue import LEASE_EXPIRED_OUTCOME, LocalWorkQueue
from engine.domain import (
    AuthorityTier,
    IssueGovernance,
    IssueLifecycleStatus,
    IssueRouting,
    SOCIssue,
)


class _FakeEngine:
    def __init__(self):
        self.patched = []
        self.deployments = []

    def patch_rule(self, rule_id_or_name, rule_text, update_mask="text"):
        self.patched.append(rule_id_or_name)
        return {"name": rule_id_or_name}

    def update_rule_deployment(self, rule_id_or_name, enabled=None, alerting=None):
        self.deployments.append((rule_id_or_name, enabled))
        return {"name": rule_id_or_name, "enabled": enabled}


def _expire(queue: LocalWorkQueue, issue_id: str) -> None:
    issue = queue.get_issue(issue_id)
    issue.lease.expires_at = (datetime.now(timezone.utc) - timedelta(seconds=5)).isoformat()
    queue.publish_issue(issue)


class LeaseReclamationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.queue = LocalWorkQueue(root_dir=self.tmp)
        self.caps = {"parser.read": 1}
        self.queue.publish_issue(SOCIssue(
            id="SOC-LEASE-1",
            type="parser_drop_spike",
            routing=IssueRouting(requires_capabilities={"parser.read": 1}),
        ))

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_expired_lease_is_eligible_again(self):
        self.assertIsNotNone(self.queue.acquire_lease("SOC-LEASE-1", "@w1", duration_seconds=60))
        self.assertEqual(self.queue.find_eligible_issues(self.caps), [])

        _expire(self.queue, "SOC-LEASE-1")
        ids = [i.id for i in self.queue.find_eligible_issues(self.caps)]
        self.assertEqual(ids, ["SOC-LEASE-1"])

    def test_other_worker_can_take_over_expired_lease(self):
        self.queue.acquire_lease("SOC-LEASE-1", "@w1", duration_seconds=60)
        _expire(self.queue, "SOC-LEASE-1")

        lease = self.queue.acquire_lease("SOC-LEASE-1", "@w2", duration_seconds=60)
        self.assertIsNotNone(lease)
        self.assertEqual(lease.owner, "@w2")
        self.assertEqual(lease.generation, 2)
        issue = self.queue.get_issue("SOC-LEASE-1")
        self.assertEqual(issue.attempts[-1]["outcome"], LEASE_EXPIRED_OUTCOME)
        self.assertEqual(issue.attempts[-1]["actor"], "@w1")

    def test_reclaim_returns_issue_to_pool_and_records_attempt(self):
        self.queue.acquire_lease("SOC-LEASE-1", "@w1", duration_seconds=60)
        self.assertEqual(self.queue.reclaim_expired_leases(), [])

        _expire(self.queue, "SOC-LEASE-1")
        self.assertEqual(self.queue.reclaim_expired_leases(), ["SOC-LEASE-1"])

        issue = self.queue.get_issue("SOC-LEASE-1")
        self.assertEqual(issue.status, IssueLifecycleStatus.AVAILABLE.value)
        self.assertIsNone(issue.lease)
        self.assertIsNone(issue.routing.claimed_by)
        self.assertEqual(issue.references["lease_generation"], 1)
        self.assertEqual(issue.attempts[-1]["outcome"], LEASE_EXPIRED_OUTCOME)
        # Idempotent
        self.assertEqual(self.queue.reclaim_expired_leases(), [])
        # Generation continues monotonically after reclaim
        self.assertEqual(self.queue.acquire_lease("SOC-LEASE-1", "@w2").generation, 2)

    def test_post_work_states_are_never_reclaimed(self):
        self.queue.acquire_lease("SOC-LEASE-1", "@w1", duration_seconds=60)
        self.queue.update_issue_status("SOC-LEASE-1", IssueLifecycleStatus.VALIDATING.value)
        _expire(self.queue, "SOC-LEASE-1")

        self.assertEqual(self.queue.reclaim_expired_leases(), [])
        self.assertEqual(self.queue.find_eligible_issues(self.caps), [])
        self.assertIsNone(self.queue.acquire_lease("SOC-LEASE-1", "@w2"))
        self.assertEqual(self.queue.get_issue("SOC-LEASE-1").status, IssueLifecycleStatus.VALIDATING.value)

    def test_closed_issue_cannot_be_leased(self):
        self.queue.update_issue_status("SOC-LEASE-1", IssueLifecycleStatus.CLOSED.value)
        self.assertIsNone(self.queue.acquire_lease("SOC-LEASE-1", "@w1"))


class ApprovalPolicyUnitTests(unittest.TestCase):
    def _check(self, **kw):
        base = dict(
            author="@yaral-optimizer", approver="alice@corp", action_type="UPDATE_RULE_TEXT",
            risk_level="MEDIUM", stored_tier=None, syntax_verified=True,
        )
        base.update(kw)
        return check_approval(**base)

    def test_required_tier(self):
        self.assertEqual(required_tier("UPDATE_RULE_TEXT", "MEDIUM"), AuthorityTier.TIER_2_PEER_REVIEW.value)
        self.assertEqual(required_tier("UPDATE_RULE_TEXT", "HIGH"), AuthorityTier.TIER_3_HUMAN_APPROVAL.value)
        self.assertEqual(required_tier("DEPLOY_RULE", "LOW"), AuthorityTier.TIER_3_HUMAN_APPROVAL.value)
        self.assertEqual(required_tier("GENERIC_CAPABILITY", "LOW"), AuthorityTier.TIER_3_HUMAN_APPROVAL.value)

    def test_stored_tier_cannot_lower_computed(self):
        tier = self._check(action_type="UNDEPLOY_RULE", stored_tier=AuthorityTier.TIER_1_AUTONOMOUS.value)
        self.assertEqual(tier, AuthorityTier.TIER_3_HUMAN_APPROVAL.value)

    def test_stored_tier_can_raise(self):
        tier = self._check(stored_tier=AuthorityTier.TIER_3_HUMAN_APPROVAL.value)
        self.assertEqual(tier, AuthorityTier.TIER_3_HUMAN_APPROVAL.value)
        with self.assertRaises(ApprovalPolicyError) as ctx:
            self._check(stored_tier=AuthorityTier.TIER_3_HUMAN_APPROVAL.value, approver="@peer-agent")
        self.assertEqual(ctx.exception.code, ApprovalPolicyError.HUMAN_REQUIRED)

    def test_self_approval_blocked_case_and_at_insensitive(self):
        with self.assertRaises(ApprovalPolicyError) as ctx:
            self._check(approver="YARAL-Optimizer")
        self.assertEqual(ctx.exception.code, ApprovalPolicyError.SELF_APPROVAL)

    def test_peer_agent_may_approve_tier2(self):
        self.assertEqual(self._check(approver="@peer-agent"), AuthorityTier.TIER_2_PEER_REVIEW.value)

    def test_agent_cannot_approve_tier3(self):
        with self.assertRaises(ApprovalPolicyError) as ctx:
            self._check(approver="@peer-agent", action_type="DEPLOY_RULE")
        self.assertEqual(ctx.exception.code, ApprovalPolicyError.HUMAN_REQUIRED)

    def test_failed_preflight_blocks_without_override(self):
        with self.assertRaises(ApprovalPolicyError) as ctx:
            self._check(syntax_verified=False)
        self.assertEqual(ctx.exception.code, ApprovalPolicyError.PREFLIGHT_FAILED)

    def test_failed_preflight_override_needs_reason(self):
        with self.assertRaises(ApprovalPolicyError) as ctx:
            self._check(syntax_verified=False, override_preflight=True, override_reason="ok")
        self.assertEqual(ctx.exception.code, ApprovalPolicyError.OVERRIDE_REASON_REQUIRED)
        self._check(syntax_verified=False, override_preflight=True, override_reason="Verified manually in rule editor")

    def test_agent_cannot_override_preflight(self):
        with self.assertRaises(ApprovalPolicyError) as ctx:
            self._check(syntax_verified=False, approver="@peer", override_preflight=True,
                        override_reason="Verified manually in rule editor")
        self.assertEqual(ctx.exception.code, ApprovalPolicyError.HUMAN_REQUIRED)

    def test_preflight_not_gated_for_non_code_actions(self):
        self._check(action_type="REMEDIATE_FEED", syntax_verified=False)


class ApproveAndMergeEnforcementTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self._prev_git = os.environ.get("SECOPS_DISABLE_GIT_COMMITS")
        os.environ["SECOPS_DISABLE_GIT_COMMITS"] = "1"
        self.manager = ProposalManager(root_dir=Path(self.tmp) / "ledger")
        self.engine = _FakeEngine()
        self.queue = LocalWorkQueue(root_dir=self.tmp)
        self.lifecycle = SOCLifecycleManager(
            work_queue=self.queue,
            materializer=IssueMaterializer(root_dir=Path(self.tmp)),
            root_dir=Path(self.tmp),
        )

    def tearDown(self):
        if self._prev_git is None:
            os.environ.pop("SECOPS_DISABLE_GIT_COMMITS", None)
        else:
            os.environ["SECOPS_DISABLE_GIT_COMMITS"] = self._prev_git
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _create(self, pid, action_type="UPDATE_RULE_TEXT", syntax=True, risk="MEDIUM", issue_id=None):
        self.manager.create_proposal(ChangeProposal(
            id=pid, title="t", author="@yaral-optimizer", subsystem="detection_rules",
            target_resource_id="ru_1", action_type=action_type, risk_level=risk, issue_id=issue_id,
            mutation_payload={"rule_text": "rule x { condition: true }", "enabled": False},
            preflight=PreflightProof(syntax_verified=syntax),
        ))

    def test_tier_persisted_on_create(self):
        self._create("p-tier", action_type="UNDEPLOY_RULE")
        self.assertEqual(self.manager.get_proposal("p-tier").required_tier,
                         AuthorityTier.TIER_3_HUMAN_APPROVAL.value)

    def test_policy_violation_leaves_proposal_open_and_no_mutation(self):
        self._create("p-self")
        with self.assertRaises(ApprovalPolicyError):
            self.manager.approve_and_merge("p-self", engine=self.engine, merged_by="@yaral-optimizer")
        self.assertEqual(self.engine.patched, [])
        self.assertEqual(self.manager.get_proposal("p-self").status, "OPEN")

    def test_failed_preflight_override_recorded(self):
        self._create("p-ovr", syntax=False)
        with self.assertRaises(ApprovalPolicyError):
            self.manager.approve_and_merge("p-ovr", engine=self.engine, merged_by="alice@corp")
        res = self.manager.approve_and_merge(
            "p-ovr", engine=self.engine, merged_by="alice@corp",
            override_preflight=True, override_reason="Compiler false positive, verified in editor",
        )
        self.assertTrue(res.success)
        merged = self.manager.get_proposal("p-ovr")
        self.assertEqual(merged.preflight_override_reason, "Compiler false positive, verified in editor")
        self.assertEqual(self.engine.patched, ["ru_1"])

    def test_linked_issue_tier_raises_requirement(self):
        self.queue.publish_issue(SOCIssue(
            id="SOC-GOV-1", type="rule_decay",
            governance=IssueGovernance(required_authority_tier=AuthorityTier.TIER_3_HUMAN_APPROVAL.value),
        ))
        self._create("p-linked", issue_id="SOC-GOV-1")
        with self.assertRaises(ApprovalPolicyError) as ctx:
            self.manager.approve_and_merge("p-linked", engine=self.engine, merged_by="@peer-agent",
                                           lifecycle_manager=self.lifecycle)
        self.assertEqual(ctx.exception.code, ApprovalPolicyError.HUMAN_REQUIRED)
        res = self.manager.approve_and_merge("p-linked", engine=self.engine, merged_by="alice@corp",
                                             lifecycle_manager=self.lifecycle)
        self.assertTrue(res.success)
        self.assertEqual(self.manager.get_proposal("p-linked").required_tier,
                         AuthorityTier.TIER_3_HUMAN_APPROVAL.value)


if __name__ == "__main__":
    unittest.main()
