"""Unit and behavioral tests for DetectionTuningAgent (@detection-tuning-agent)."""

import os
import tempfile
import unittest
from pathlib import Path

from agents.core.evidence_store import LocalFileEvidenceStore
from agents.core.proposal_manager import ProposalManager
from agents.generated.detection_tuning_agent import DetectionTuningAgentAgent
from engine.domain import DetectionTuningProposal, MultiFactorExclusion
from engine.workflows.detection_tuning import (
    BANNED_GLOBAL_BINARIES,
    SynthesizeMultiFactorExclusionWorkflow,
)
from tests.test_helpers import get_live_engine


class TestDetectionTuningAgent(unittest.TestCase):
    """Verifies agent bindings, tool registration, guardrails, and tuning operations."""

    def setUp(self):
        self._tmpdir = tempfile.TemporaryDirectory()
        self.root_dir = Path(self._tmpdir.name)
        self.evidence_store = LocalFileEvidenceStore(root_dir=self.root_dir)
        self.proposal_manager = ProposalManager(root_dir=self.root_dir)
        self.agent = DetectionTuningAgentAgent(
            engine=None,
            proposal_manager=self.proposal_manager,
            evidence_store=self.evidence_store,
        )

    def tearDown(self):
        self._tmpdir.cleanup()

    def test_agent_manifest_bindings(self):
        """Verifies ADK 2 agent manifest metadata, streams, topics, and tool bindings."""
        self.assertEqual(self.agent.handle, "@detection-tuning-agent")
        self.assertEqual(self.agent.default_stream, "detections")
        self.assertEqual(self.agent.default_topic, "tuning-review")
        self.assertIn("curated_detections.tuning.samples", self.agent.CAPABILITIES)
        self.assertIn("curated_detections.tuning.synthesize", self.agent.CAPABILITIES)
        self.assertIn("curated_detections.tuning.top_noisy_rules", self.agent.CAPABILITIES)
        self.assertIn("curated_detections.tuning.entity_cardinality", self.agent.CAPABILITIES)

        # Verify custom tools bound
        tools = self.agent.get_tools()
        tool_names = [getattr(t, "__name__", str(t)) for t in tools]
        self.assertIn("find_noisy_rules", tool_names)
        self.assertIn("get_field_value_distribution", tool_names)
        self.assertIn("get_detection_event_samples", tool_names)
        self.assertIn("synthesize_tuning_proposal", tool_names)
        self.assertIn("submit_tuning_proposal", tool_names)

    def test_multi_factor_guardrails_unit(self):
        """Verifies multi-factor safety guardrails: single-factor cuts, banned binaries, and diversity checks."""
        from engine.domain import CorrelatedDetectionSample

        wf = SynthesizeMultiFactorExclusionWorkflow()

        # 1. Single factor (e.g. only user is populated, command/host/ip empty)
        single_sample = [
            CorrelatedDetectionSample(
                user="svc_monitoring",
                command_line="",
                hostname="",
                ip="",
                count=80,
            )
        ]
        exclusion = wf.execute(
            rule_id="ru_test",
            rule_name="Test Rule",
            samples=single_sample,
            total_detections=100,
            dominance_threshold=0.20,
        )
        self.assertFalse(exclusion.safety_guardrail_passed)
        self.assertTrue(any("at least two correlating attributes" in n for n in exclusion.guardrail_notes))

        # 2. Banned global binary
        for binary in ["powershell.exe", "cmd.exe", "wmic.exe", "bash"]:
            banned_sample = [
                CorrelatedDetectionSample(
                    user="svc_monitoring",
                    command_line=binary,
                    hostname="server1",
                    ip="10.0.0.1",
                    count=80,
                )
            ]
            exclusion = wf.execute(
                rule_id="ru_test",
                rule_name="Test Rule",
                samples=banned_sample,
                total_detections=100,
                dominance_threshold=0.20,
            )
            self.assertFalse(exclusion.safety_guardrail_passed)
            self.assertTrue(any("Banned global binary violation" in n for n in exclusion.guardrail_notes))

        # 3. Dominance threshold / diversity check failure
        multi_sample = [
            CorrelatedDetectionSample(
                user="svc_monitoring",
                command_line="agent_health.ps1",
                hostname="server1",
                ip="10.0.0.1",
                count=10,  # 10% < 20%
            )
        ]
        exclusion = wf.execute(
            rule_id="ru_test",
            rule_name="Test Rule",
            samples=multi_sample,
            total_detections=100,
            dominance_threshold=0.20,
        )
        self.assertFalse(exclusion.safety_guardrail_passed)
        self.assertTrue(any("Diversity check failed" in n for n in exclusion.guardrail_notes))

        # 4. Valid multi-factor passing all guardrails
        valid_sample = [
            CorrelatedDetectionSample(
                user="svc_monitoring",
                command_line="agent_health.ps1",
                hostname="server1",
                ip="10.0.0.1",
                count=60,  # 60% >= 20%
            )
        ]
        valid_exclusion = wf.execute(
            rule_id="ru_test",
            rule_name="Test Rule",
            samples=valid_sample,
            total_detections=100,
            dominance_threshold=0.20,
        )
        self.assertTrue(valid_exclusion.safety_guardrail_passed)
        self.assertTrue(len(valid_exclusion.yara_l_condition) > 0)
        self.assertTrue(len(valid_exclusion.udm_refinement_query) > 0)

    def test_submit_tuning_proposal(self):
        """Verifies Gas Town HITL proposal generation, YAML serialization, and disk storage."""
        res = self.agent.submit_tuning_proposal(
            title="Tune Wmic Process Call Create for admin_svc",
            rule_id="ur_a6942cbc-45e5-4a6b-830d-d698b8a659f6",
            rationale="Isolate verified monitoring service account running scheduled health checks",
            proposed_diff="--- a/rule\n+++ b/rule\n@@ -1,3 +1,4 @@\n+ and not ( $e.principal.user.userid = \"admin_svc\" )",
            tuned_rule_text="rule test { events: not $e.principal.user.userid = \"admin_svc\" condition: $e }",
            unsuppressed_trigger_count=500,
            projected_suppressed_count=250,
            noise_reduction_pct=50.0,
            preserved_real_alerts=250,
        )
        self.assertEqual(res["status"], "SUCCESS")
        self.assertTrue(res["proposal_id"].startswith("prop-"))

        # Check proposal file on disk
        open_props = self.proposal_manager.list_proposals("OPEN")
        self.assertEqual(len(open_props), 1)
        prop = open_props[0]
        self.assertEqual(prop.id, res["proposal_id"])
        self.assertEqual(prop.subsystem, "detections")
        self.assertIn("Wmic Process Call Create", prop.title)

    def test_live_agent_operations(self):
        """Verifies live agent tools against Google SecOps (Chronicle) if live engine configured."""
        try:
            live_engine = get_live_engine()
        except Exception as e:
            self.skipTest(f"Live SecOps engine not available: {e}")

        live_agent = DetectionTuningAgentAgent(
            engine=live_engine,
            proposal_manager=self.proposal_manager,
            evidence_store=self.evidence_store,
        )

        # 1. find_noisy_rules
        noisy = live_agent.find_noisy_rules(lookback_days=14, limit=5)
        self.assertEqual(noisy["status"], "SUCCESS")
        self.assertGreater(len(noisy["rules"]), 0)
        rule_id = noisy["rules"][0]["rule_id"]

        # 2. get_detection_event_samples
        samples_res = live_agent.get_detection_event_samples(rule_id=rule_id, lookback_days=14, limit=3)
        self.assertEqual(samples_res["status"], "SUCCESS")
        self.assertEqual(samples_res["rule_id"], rule_id)

    def test_no_mock_data_audit(self):
        """CI Invariant: Ensure zero banned mock/synthetic terms in agent & tuning code."""
        repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        banned_terms = ["mock", "fixture", "dummy", "fake", "sample_data", "test_data"]

        prod_files = [
            os.path.join(repo_root, "agents", "generated", "detection_tuning_agent.py"),
            os.path.join(repo_root, "scripts", "generate_adk_agents.py"),
            os.path.join(repo_root, "engine", "workflows", "detection_tuning.py"),
        ]

        for path in prod_files:
            with open(path, "r", encoding="utf-8") as f:
                content = f.read()
                lines = content.split("\n")
                for line_num, line in enumerate(lines, 1):
                    lower_line = line.lower()
                    for term in banned_terms:
                        if term in lower_line:
                            tokens = [t.strip("\"'()[]{},: ") for t in lower_line.split()]
                            for tok in tokens:
                                if tok == term:
                                    self.fail(
                                        f"Banned term '{term}' found in production file "
                                        f"'{os.path.relpath(path, repo_root)}' line {line_num}: {line}"
                                    )


if __name__ == "__main__":
    unittest.main()
