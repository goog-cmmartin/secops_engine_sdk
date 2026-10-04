"""Unit and behavioral tests for DetectionDecayAgent."""

import tempfile
import unittest
from pathlib import Path

from agents.generated.detection_decay_agent import DetectionDecayAgentAgent
from agents.core.evidence_store import LocalFileEvidenceStore
from agents.core.proposal_manager import ProposalManager


class TestDetectionDecayAgent(unittest.TestCase):
    """Verifies agent bindings, tool registration, and decay review operations."""

    def setUp(self):
        self._tmpdir = tempfile.TemporaryDirectory()
        self.root_dir = Path(self._tmpdir.name)
        self.evidence_store = LocalFileEvidenceStore(root_dir=self.root_dir)
        self.proposal_manager = ProposalManager(root_dir=self.root_dir)
        self.agent = DetectionDecayAgentAgent(
            engine=None,
            proposal_manager=self.proposal_manager,
            evidence_store=self.evidence_store,
        )

    def tearDown(self):
        self._tmpdir.cleanup()

    def test_agent_manifest_bindings(self):
        self.assertEqual(self.agent.handle, "@detection-decay-agent")
        self.assertEqual(self.agent.default_stream, "detections")
        self.assertEqual(self.agent.default_topic, "decay-review")
        self.assertIn("rule.decay.audit", self.agent.CAPABILITIES)
        self.assertIn("rule.decay.telemetry", self.agent.CAPABILITIES)

        # Verify custom tools bound
        tools = self.agent.get_tools()
        tool_names = [getattr(t, "__name__", str(t)) for t in tools]
        self.assertIn("run_decay_synchronization", tool_names)
        self.assertIn("audit_single_rule_decay", tool_names)
        self.assertIn("check_udm_field_population", tool_names)
        self.assertIn("submit_decay_proposal", tool_names)
        self.assertIn("list_decay_queue", tool_names)

    def test_list_decay_queue_empty_and_populated(self):
        # Empty
        queue = self.agent.list_decay_queue()
        self.assertEqual(queue, [])

        # Save state to evidence fabric
        self.evidence_store.save_rule_state("ru_test_1", {
            "rule_id": "ru_test_1",
            "rule_name": "Test Rule 1",
            "dps_score": 85,
            "decay_flags": ["BROKEN_COMPILATION", "SILENT"],
            "detection_count_90d": 0,
            "days_stale": 120,
            "is_live": True,
        })
        self.evidence_store.save_rule_state("ru_test_2", {
            "rule_id": "ru_test_2",
            "rule_name": "Test Rule 2",
            "dps_score": 40,
            "decay_flags": ["STALE"],
            "detection_count_90d": 12,
            "days_stale": 100,
            "is_live": False,
        })

        queue = self.agent.list_decay_queue(min_dps=50)
        self.assertEqual(len(queue), 1)
        self.assertEqual(queue[0]["rule_id"], "ru_test_1")
        self.assertEqual(queue[0]["dps_score"], 85)

    def test_submit_decay_proposal_creates_gas_town_proposal(self):
        res = self.agent.submit_decay_proposal(
            title="Remediate broken syntax in ru_test_1",
            target_resource_id="ru_test_1",
            rationale="Fix regex syntax error in events condition",
            proposed_diff="--- a/ru_test_1.yaral\n+++ b/ru_test_1.yaral\n@@ -1 +1 @@\n- bad\n+ good\n",
            refactored_rule_text="rule ru_test_1 { condition: true }",
        )
        self.assertEqual(res.get("status"), "PROPOSAL_CREATED")
        proposal_id = res.get("proposal_id")
        self.assertTrue(proposal_id.startswith("prop-"))

        # Verify proposal exists in ProposalManager
        p = self.proposal_manager.get_proposal(proposal_id)
        self.assertEqual(p.target_resource_id, "ru_test_1")
        self.assertEqual(p.author, "@detection-decay-agent")


if __name__ == "__main__":
    unittest.main()
