"""Unit and behavioral tests for FeedHealthAgent (@feed-agent)."""

import os
import tempfile
import unittest
from pathlib import Path

from agents.core.evidence_store import LocalFileEvidenceStore
from agents.core.proposal_manager import ProposalManager
from agents.generated.feed_health_agent import FeedHealthAgentAgent


class TestFeedHealthAgent(unittest.TestCase):
    """Verifies agent bindings, tool registration, proposal lifecycle, and ingestion checks."""

    def setUp(self):
        self._tmpdir = tempfile.TemporaryDirectory()
        self.root_dir = Path(self._tmpdir.name)
        self.evidence_store = LocalFileEvidenceStore(root_dir=self.root_dir)
        self.proposal_manager = ProposalManager(root_dir=self.root_dir)
        self.agent = FeedHealthAgentAgent(
            engine=None,
            proposal_manager=self.proposal_manager,
            evidence_store=self.evidence_store,
        )

    def tearDown(self):
        self._tmpdir.cleanup()

    def test_agent_manifest_bindings(self):
        """Verifies ADK 2 agent manifest metadata, streams, topics, and tool bindings."""
        self.assertEqual(self.agent.handle, "@feed-agent")
        self.assertEqual(self.agent.default_stream, "ingestion")
        self.assertEqual(self.agent.default_topic, "feed-health")
        self.assertIn("feed.audit_health", self.agent.CAPABILITIES)
        self.assertIn("feed.search", self.agent.CAPABILITIES)
        self.assertIn("feed.get", self.agent.CAPABILITIES)

        # Verify custom tools bound
        tools = self.agent.get_tools()
        tool_names = [getattr(t, "__name__", str(t)) for t in tools]
        self.assertIn("audit_feeds", tool_names)
        self.assertIn("get_feed_details", tool_names)
        self.assertIn("check_feed_latency", tool_names)
        self.assertIn("submit_feed_proposal", tool_names)

    def test_submit_feed_proposal_lifecycle(self):
        """Verifies feed remediation proposals enter Gas Town .proposals/ and produce HITL widgets."""
        res = self.agent.submit_feed_proposal(
            title="Adjust polling schedule for AWS CloudTrail S3 feed",
            feed_id="feed-aws-s3-prod-01",
            rationale="Feed is experiencing 6-hour P95 latency spikes due to 24-hour polling interval.",
            recommended_action="Decrease polling interval to 15 minutes and enable SQS notification queue.",
            configuration_patch={"poll_interval_seconds": 900, "use_sqs": True},
        )

        self.assertEqual(res["status"], "SUCCESS")
        proposal_id = res["proposal_id"]
        self.assertTrue(proposal_id.startswith("prop-"))

        # Verify proposal file written to .proposals/open/ via ProposalManager
        p = self.proposal_manager.get_proposal(proposal_id)
        self.assertEqual(p.id, proposal_id)
        self.assertEqual(p.target_resource_id, "feed-aws-s3-prod-01")
        self.assertEqual(p.action_type, "REMEDIATE_FEED")
        self.assertEqual(p.author, "@feed-agent")
        self.assertTrue(p.preflight.syntax_verified)

        # Verify notification posted to outbox with HITL proposal widget
        self.assertEqual(len(self.agent._outbox), 1)
        notification = self.agent._outbox[-1]
        self.assertEqual(notification.proposal_id, proposal_id)
        self.assertEqual(notification.widget["type"], "hitl_proposal_card")
        self.assertEqual(notification.widget["status"], "OPEN")

    def test_no_mock_data_audit(self):
        """CI Invariant: Ensure zero banned mock/synthetic terms in feed agent code."""
        repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        banned_terms = ["mock", "fixture", "dummy", "fake", "sample_data", "test_data"]

        prod_files = [
            os.path.join(repo_root, "agents", "generated", "feed_health_agent.py"),
            os.path.join(repo_root, "engine", "workflows", "feed.py"),
        ]

        for path in prod_files:
            if not os.path.exists(path):
                continue
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
