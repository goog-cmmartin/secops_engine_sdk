"""Stale-target protection: proposals record the target's state and refuse to
apply if it changed before approval."""

import os
import shutil
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from agents.core.proposal_manager import ChangeProposal, PreflightProof, ProposalManager
from agents.core.target_baseline import (
    StaleTargetError,
    capture_baseline,
    verify_unchanged,
)


class _FakeEngine:
    """Minimal engine: one rule with mutable text/revision and deployment state."""

    def __init__(self, text="rule r { condition: true }", revision="rev-1", enabled=True, alerting=False):
        self.text = text
        self.revision = revision
        self.enabled = enabled
        self.alerting = alerting
        self.fail_reads = False
        self.patched = []
        self.deployments = []

    def get_rule(self, rule_id_or_name, view="FULL"):
        if self.fail_reads:
            raise RuntimeError("503 backend unavailable")
        return SimpleNamespace(text=self.text, revision_id=self.revision)

    def get_rule_deployment(self, rule_id_or_name):
        if self.fail_reads:
            raise RuntimeError("503 backend unavailable")
        return SimpleNamespace(enabled=self.enabled, alerting=self.alerting)

    def patch_rule(self, rule_id_or_name, rule_text, update_mask=None):
        self.patched.append(rule_text)
        self.text = rule_text
        return {"name": rule_id_or_name}

    def update_rule_deployment(self, rule_id_or_name, enabled=None, alerting=None):
        self.deployments.append((enabled, alerting))
        return {"name": rule_id_or_name}


class BaselineUnitTest(unittest.TestCase):
    def test_capture_rule_text(self):
        base = capture_baseline(_FakeEngine(), "UPDATE_RULE_TEXT", "ru_1")
        self.assertEqual(base["kind"], "rule_text")
        self.assertEqual(base["revision_id"], "rev-1")
        self.assertEqual(len(base["text_sha256"]), 64)
        self.assertIn("captured_at", base)

    def test_capture_unsupported_or_unreadable_returns_none(self):
        self.assertIsNone(capture_baseline(_FakeEngine(), "GENERIC_CAPABILITY", "ru_1"))
        self.assertIsNone(capture_baseline(None, "UPDATE_RULE_TEXT", "ru_1"))
        eng = _FakeEngine()
        eng.fail_reads = True
        self.assertIsNone(capture_baseline(eng, "UPDATE_RULE_TEXT", "ru_1"))

    def test_no_baseline_is_not_checked(self):
        self.assertFalse(verify_unchanged(_FakeEngine(), "UPDATE_RULE_TEXT", "ru_1", None))

    def test_unchanged_passes(self):
        eng = _FakeEngine()
        base = capture_baseline(eng, "UPDATE_RULE_TEXT", "ru_1")
        self.assertTrue(verify_unchanged(eng, "UPDATE_RULE_TEXT", "ru_1", base))

    def test_text_change_is_stale(self):
        eng = _FakeEngine()
        base = capture_baseline(eng, "UPDATE_RULE_TEXT", "ru_1")
        eng.text = "rule r { condition: false }"
        with self.assertRaises(StaleTargetError) as ctx:
            verify_unchanged(eng, "UPDATE_RULE_TEXT", "ru_1", base)
        self.assertEqual(ctx.exception.code, StaleTargetError.STALE_TARGET)
        self.assertNotEqual(ctx.exception.expected["text_sha256"], ctx.exception.current["text_sha256"])

    def test_new_revision_with_same_text_is_stale(self):
        eng = _FakeEngine()
        base = capture_baseline(eng, "UPDATE_RULE_TEXT", "ru_1")
        eng.revision = "rev-2"
        with self.assertRaises(StaleTargetError):
            verify_unchanged(eng, "UPDATE_RULE_TEXT", "ru_1", base)

    def test_missing_revision_falls_back_to_hash(self):
        eng = _FakeEngine(revision="")
        base = capture_baseline(eng, "UPDATE_RULE_TEXT", "ru_1")
        self.assertTrue(verify_unchanged(eng, "UPDATE_RULE_TEXT", "ru_1", base))
        eng.text = "changed"
        with self.assertRaises(StaleTargetError):
            verify_unchanged(eng, "UPDATE_RULE_TEXT", "ru_1", base)

    def test_deployment_change_is_stale(self):
        eng = _FakeEngine(enabled=True)
        base = capture_baseline(eng, "UNDEPLOY_RULE", "ru_1")
        self.assertTrue(verify_unchanged(eng, "UNDEPLOY_RULE", "ru_1", base))
        eng.enabled = False
        with self.assertRaises(StaleTargetError) as ctx:
            verify_unchanged(eng, "UNDEPLOY_RULE", "ru_1", base)
        self.assertEqual(ctx.exception.current["enabled"], False)

    def test_unreadable_target_is_unverifiable(self):
        eng = _FakeEngine()
        base = capture_baseline(eng, "UPDATE_RULE_TEXT", "ru_1")
        eng.fail_reads = True
        with self.assertRaises(StaleTargetError) as ctx:
            verify_unchanged(eng, "UPDATE_RULE_TEXT", "ru_1", base)
        self.assertEqual(ctx.exception.code, StaleTargetError.TARGET_UNVERIFIABLE)
        with self.assertRaises(StaleTargetError) as ctx:
            verify_unchanged(None, "UPDATE_RULE_TEXT", "ru_1", base)
        self.assertEqual(ctx.exception.code, StaleTargetError.TARGET_UNVERIFIABLE)


class ProposalManagerBaselineTest(unittest.TestCase):
    def setUp(self):
        self._prev_git = os.environ.get("SECOPS_DISABLE_GIT_COMMITS")
        os.environ["SECOPS_DISABLE_GIT_COMMITS"] = "1"
        self.tmp = tempfile.mkdtemp()
        self.manager = ProposalManager(root_dir=Path(self.tmp))
        self.engine = _FakeEngine()

    def tearDown(self):
        if self._prev_git is None:
            os.environ.pop("SECOPS_DISABLE_GIT_COMMITS", None)
        else:
            os.environ["SECOPS_DISABLE_GIT_COMMITS"] = self._prev_git
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _create(self, pid, action_type="UPDATE_RULE_TEXT", engine="default"):
        self.manager.create_proposal(ChangeProposal(
            id=pid, title="t", author="@yaral-optimizer", subsystem="detection_rules",
            target_resource_id="ru_1", action_type=action_type,
            mutation_payload={"rule_text": "rule r { condition: false }", "enabled": False},
            preflight=PreflightProof(syntax_verified=True),
        ), engine=self.engine if engine == "default" else engine)

    def test_baseline_persisted(self):
        self._create("p-persist")
        p = self.manager.get_proposal("p-persist")
        self.assertEqual(p.base_revision["kind"], "rule_text")
        self.assertEqual(p.base_revision["revision_id"], "rev-1")

    def test_merge_when_unchanged(self):
        self._create("p-ok")
        res = self.manager.approve_and_merge("p-ok", engine=self.engine, merged_by="alice@corp")
        self.assertTrue(res.success)
        self.assertEqual(self.engine.patched, ["rule r { condition: false }"])
        self.assertTrue(self.manager.get_proposal("p-ok").base_verified_at_merge)

    def test_stale_rule_refused_and_left_open(self):
        self._create("p-stale")
        self.engine.text = "rule r { condition: $human_edit }"
        with self.assertRaises(StaleTargetError):
            self.manager.approve_and_merge("p-stale", engine=self.engine, merged_by="alice@corp")
        self.assertEqual(self.engine.patched, [])
        self.assertEqual(self.engine.text, "rule r { condition: $human_edit }")
        self.assertEqual(self.manager.get_proposal("p-stale").status, "OPEN")

    def test_stale_deployment_refused(self):
        self._create("p-dep", action_type="UNDEPLOY_RULE")
        self.engine.enabled = False
        with self.assertRaises(StaleTargetError):
            self.manager.approve_and_merge("p-dep", engine=self.engine, merged_by="alice@corp")
        self.assertEqual(self.engine.deployments, [])

    def test_legacy_proposal_without_baseline_still_merges(self):
        self._create("p-legacy", engine=None)
        self.assertIsNone(self.manager.get_proposal("p-legacy").base_revision)
        res = self.manager.approve_and_merge("p-legacy", engine=self.engine, merged_by="alice@corp")
        self.assertTrue(res.success)
        self.assertFalse(self.manager.get_proposal("p-legacy").base_verified_at_merge)

    def test_policy_checked_before_baseline(self):
        from agents.core.approval_policy import ApprovalPolicyError
        self._create("p-order")
        self.engine.fail_reads = True
        with self.assertRaises(ApprovalPolicyError):
            self.manager.approve_and_merge("p-order", engine=self.engine, merged_by="@yaral-optimizer")


if __name__ == "__main__":
    unittest.main()
