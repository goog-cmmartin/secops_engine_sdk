"""Unit tests for the Gas Town-inspired ProposalManager."""

import tempfile
from pathlib import Path
import unittest

from agents.core.proposal_manager import (
    ChangeProposal,
    PreflightProof,
    ProposalManager,
)


class _RecordingEngine:
    """Engine that tracks mutation invocations during proposal testing."""

    def __init__(self):
        self.patched_rules = []
        self.updated_deployments = []

    def patch_rule(self, rule_id_or_name: str, rule_text: str, update_mask: str = "text"):
        self.patched_rules.append({
            "rule_id": rule_id_or_name,
            "rule_text": rule_text,
            "update_mask": update_mask,
        })
        return {"name": rule_id_or_name, "revision_id": "rev-test-1"}

    def update_rule_deployment(self, rule_id_or_name: str, enabled=None, alerting=None):
        self.updated_deployments.append({
            "rule_id": rule_id_or_name,
            "enabled": enabled,
            "alerting": alerting,
        })
        return {"name": rule_id_or_name, "enabled": enabled, "alerting": alerting}


class _RecordingInventoryClient:
    """Inventory client tracking snapshot requests."""

    def __init__(self):
        self.snapshots = []

    def trigger_snapshot(self, reason: str):
        self.snapshots.append(reason)


class ProposalManagerTest(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root_path = Path(self.temp_dir.name)
        self.manager = ProposalManager(root_dir=self.root_path)
        self.engine = _RecordingEngine()
        self.inventory = _RecordingInventoryClient()

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_create_and_get_proposal(self):
        proposal = ChangeProposal(
            id="prop-test-001",
            title="Optimize YARA-L Cartesian Join",
            author="@yaral-optimizer",
            subsystem="detection_rules",
            target_resource_id="ru_12345678",
            action_type="PATCH_RULE",
            risk_level="MEDIUM",
            rationale="Unbounded match clause caused 36 timeout errors.",
            proposed_diff="--- old\n+++ new\n- $u over 1m\n+ $file_hash over 5m",
            preflight=PreflightProof(
                syntax_verified=True,
                replay_verified=True,
                replay_log_count=5000,
                replay_summary="0 timeouts over 5000 events replayed",
            ),
            mutation_payload={
                "rule_text": "rule test_rule { condition: true }",
                "update_mask": "text",
            },
        )

        pid = self.manager.create_proposal(proposal)
        self.assertEqual(pid, "prop-test-001")

        # Verify file written to open/
        open_file = self.manager.open_dir / "prop-test-001.md"
        self.assertTrue(open_file.is_file())

        # Retrieve and verify round-trip parsing
        retrieved = self.manager.get_proposal("prop-test-001")
        self.assertEqual(retrieved.id, "prop-test-001")
        self.assertEqual(retrieved.status, "OPEN")
        self.assertEqual(retrieved.author, "@yaral-optimizer")
        self.assertEqual(retrieved.subsystem, "detection_rules")
        self.assertEqual(retrieved.target_resource_id, "ru_12345678")
        self.assertTrue(retrieved.preflight.syntax_verified)
        self.assertEqual(retrieved.preflight.replay_log_count, 5000)
        self.assertIn("Cartesian Join", retrieved.title)
        self.assertIn("$file_hash over 5m", retrieved.proposed_diff)

    def test_list_proposals_filtering(self):
        p1 = ChangeProposal(
            id="prop-01",
            title="Detection Fix",
            author="@yaral-optimizer",
            subsystem="detection_rules",
            target_resource_id="ru_1",
            action_type="PATCH_RULE",
        )
        p2 = ChangeProposal(
            id="prop-02",
            title="Ingestion Setting",
            author="@ingestion-agent",
            subsystem="ingestion",
            target_resource_id="feed_1",
            action_type="GENERIC_CAPABILITY",
        )
        self.manager.create_proposal(p1)
        self.manager.create_proposal(p2)

        all_open = self.manager.list_proposals(status="OPEN")
        self.assertEqual(len(all_open), 2)

        detection_only = self.manager.list_proposals(subsystem="detection_rules")
        self.assertEqual(len(detection_only), 1)
        self.assertEqual(detection_only[0].id, "prop-01")

    def test_reject_proposal(self):
        proposal = ChangeProposal(
            id="prop-reject-me",
            title="Bad Change",
            author="@yaral-optimizer",
            subsystem="detection_rules",
            target_resource_id="ru_999",
            action_type="PATCH_RULE",
        )
        self.manager.create_proposal(proposal)

        rejected = self.manager.reject_proposal(
            "prop-reject-me",
            reason="Will suppress valid high severity alerts",
            rejected_by="soc-lead@company.com",
        )

        self.assertEqual(rejected.status, "REJECTED")
        self.assertIn("soc-lead@company.com", rejected.rejection_reason)
        self.assertFalse((self.manager.open_dir / "prop-reject-me.md").is_file())
        self.assertTrue((self.manager.rejected_dir / "prop-reject-me.md").is_file())

    def test_approve_and_merge_proposal(self):
        proposal = ChangeProposal(
            id="prop-merge-me",
            title="Fix Throttling",
            author="@yaral-optimizer",
            subsystem="detection_rules",
            target_resource_id="ru_0e378636",
            action_type="PATCH_RULE",
            mutation_payload={
                "rule_text": "rule optimized_rule { condition: true }",
                "update_mask": "text",
            },
        )
        self.manager.create_proposal(proposal)

        merge_res = self.manager.approve_and_merge(
            proposal_id="prop-merge-me",
            engine=self.engine,
            merged_by="secops-engineer@company.com",
            inventory_client=self.inventory,
        )

        self.assertTrue(merge_res.success)
        self.assertEqual(merge_res.status, "MERGED")
        self.assertEqual(len(self.engine.patched_rules), 1)
        self.assertEqual(self.engine.patched_rules[0]["rule_id"], "ru_0e378636")
        self.assertEqual(len(self.inventory.snapshots), 1)

        # File moved from open to merged
        self.assertFalse((self.manager.open_dir / "prop-merge-me.md").is_file())
        self.assertTrue((self.manager.merged_dir / "prop-merge-me.md").is_file())

        merged_prop = self.manager.get_proposal("prop-merge-me")
        self.assertEqual(merged_prop.status, "MERGED")
        self.assertEqual(merged_prop.merged_by, "secops-engineer@company.com")

    def test_approve_and_merge_update_rule_text(self):
        proposal = ChangeProposal(
            id="prop-update-text-me",
            title="Update Rule Text",
            author="@yaral-optimizer",
            subsystem="detection_rules",
            target_resource_id="ru_6cb096c8-2270-4d03-860b-3c3db443a7e4",
            action_type="UPDATE_RULE_TEXT",
            mutation_payload={
                "rule_text": "rule updated_rule { condition: true }",
                "update_mask": "text",
            },
        )
        self.manager.create_proposal(proposal)

        merge_res = self.manager.approve_and_merge(
            proposal_id="prop-update-text-me",
            engine=self.engine,
            merged_by="secops-operator",
        )

        self.assertTrue(merge_res.success)
        self.assertEqual(merge_res.status, "MERGED")
        self.assertEqual(len(self.engine.patched_rules), 1)
        self.assertEqual(self.engine.patched_rules[0]["rule_id"], "ru_6cb096c8-2270-4d03-860b-3c3db443a7e4")
        self.assertEqual(self.engine.patched_rules[0]["rule_text"], "rule updated_rule { condition: true }")


if __name__ == "__main__":
    unittest.main()
