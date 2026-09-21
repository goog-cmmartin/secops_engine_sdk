"""Unit and behavioral tests for ParserHealthAgent (@parser-doctor)."""

import os
import tempfile
import unittest
from pathlib import Path

from agents.core.evidence_store import LocalFileEvidenceStore
from agents.core.proposal_manager import ProposalManager
from agents.generated.parser_health_agent import ParserHealthAgentAgent


class TestParserHealthAgent(unittest.TestCase):
    """Verifies agent bindings, tool registration, proposal lifecycle, and CBN syntax tests."""

    def setUp(self):
        self._tmpdir = tempfile.TemporaryDirectory()
        self.root_dir = Path(self._tmpdir.name)
        self.evidence_store = LocalFileEvidenceStore(root_dir=self.root_dir)
        self.proposal_manager = ProposalManager(root_dir=self.root_dir)
        self.agent = ParserHealthAgentAgent(
            engine=None,
            proposal_manager=self.proposal_manager,
            evidence_store=self.evidence_store,
        )

    def tearDown(self):
        self._tmpdir.cleanup()

    def test_agent_manifest_bindings(self):
        """Verifies ADK 2 agent manifest metadata, streams, topics, and tool bindings."""
        self.assertEqual(self.agent.handle, "@parser-doctor")
        self.assertEqual(self.agent.default_stream, "ingestion")
        self.assertEqual(self.agent.default_topic, "parser-drops")
        self.assertIn("parser.audit_health", self.agent.CAPABILITIES)
        self.assertIn("parser.search", self.agent.CAPABILITIES)
        self.assertIn("parser.get", self.agent.CAPABILITIES)
        self.assertIn("parser.run", self.agent.CAPABILITIES)
        self.assertIn("parser.diagnose_unparsed", self.agent.CAPABILITIES)

        # Verify custom tools bound
        tools = self.agent.get_tools()
        tool_names = [getattr(t, "__name__", str(t)) for t in tools]
        self.assertIn("audit_parsers", tool_names)
        self.assertIn("get_parser_cbn", tool_names)
        self.assertIn("get_parser_extension", tool_names)
        self.assertIn("diagnose_unparsed_logs", tool_names)
        self.assertIn("run_parser_test", tool_names)
        self.assertIn("submit_parser_proposal", tool_names)

    def test_submit_parser_proposal_lifecycle(self):
        """Verifies parser CBN patch proposals enter Gas Town .proposals/ and produce HITL widgets."""
        res = self.agent.submit_parser_proposal(
            title="Patch Logstash CBN parser for CS_EDR to extract principal.process.command_line",
            log_type="CS_EDR",
            rationale="Unparsed raw logs showed missing JSON key 'cmd_line' causing normalization failure.",
            proposed_diff="--- a/parser.cbn\n+++ b/parser.cbn\n@@ -10,3 +10,4 @@\n+ mutate { rename => { 'cmd_line' => 'principal.process.command_line' } }",
            patched_cbn_snippet="filter { mutate { rename => { 'cmd_line' => 'principal.process.command_line' } } }",
        )

        self.assertEqual(res["status"], "SUCCESS")
        proposal_id = res["proposal_id"]
        self.assertTrue(proposal_id.startswith("prop-"))

        # Verify proposal file written to .proposals/open/ via ProposalManager
        p = self.proposal_manager.get_proposal(proposal_id)
        self.assertEqual(p.id, proposal_id)
        self.assertEqual(p.target_resource_id, "CS_EDR")
        self.assertEqual(p.action_type, "PATCH_PARSER_CBN")
        self.assertEqual(p.author, "@parser-doctor")
        self.assertTrue(p.preflight.syntax_verified)

        # Verify notification posted to outbox with HITL proposal widget
        self.assertEqual(len(self.agent._outbox), 1)
        notification = self.agent._outbox[-1]
        self.assertEqual(notification.proposal_id, proposal_id)
        self.assertEqual(notification.widget["type"], "hitl_proposal_card")
        self.assertEqual(notification.widget["status"], "OPEN")

    def test_no_mock_data_audit(self):
        """CI Invariant: Ensure zero banned mock/synthetic terms in parser agent code."""
        repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        banned_terms = ["mock", "fixture", "dummy", "fake", "sample_data", "test_data"]

        prod_files = [
            os.path.join(repo_root, "agents", "generated", "parser_health_agent.py"),
            os.path.join(repo_root, "engine", "workflows", "parser.py"),
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
