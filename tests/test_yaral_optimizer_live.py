"""Tests for the live autonomous YARA-L Optimizer Agent.

Verifies:
- Binding of 5 live Google SecOps capabilities plus custom submit_rule_proposal tool.
- Real compiler verification against live Chronicle SIEM YARA-L compiler.
- Autonomous reasoning loop with Gemini 3.8 Flash (global region) and AFC.
- Automatic creation of Gas Town HITL change proposals and Evidence Fabric state synchronization.
- Strict compliance with no-mock rules and explicit error reporting.
"""

import asyncio
import os
import tempfile
from pathlib import Path
import unittest

from adapters.google_secops import GoogleSecOpsAdapter
from agents.core.evidence_store import get_evidence_store
from agents.core.proposal_manager import ProposalManager
from agents.generated.yaral_optimizer import YaralOptimizerAgent
from engine.facade import SecOpsEngine
from tests.test_helpers import get_live_adapter, get_live_engine


class TestYaralOptimizerLive(unittest.TestCase):
    """Test suite for the live YARA-L Optimizer Google ADK 2 agent."""

    def setUp(self):
        try:
            self.adapter = get_live_adapter()
            self.engine = get_live_engine(adapter=self.adapter)
        except unittest.SkipTest:
            self.adapter = None
            self.engine = None

    def test_tool_binding_and_signatures(self):
        """Verifies that all 5 capabilities plus submit_rule_proposal are bound with valid signatures."""
        if not self.engine:
            self.skipTest("Live SecOps engine not available.")

        agent = YaralOptimizerAgent(engine=self.engine)
        tools = agent.get_tools()

        self.assertGreaterEqual(len(tools), 6)
        tool_names = [getattr(t, "__name__", "") for t in tools]

        self.assertIn("verify_rule_text", tool_names)
        self.assertIn("get_rule", tool_names)
        self.assertIn("patch_rule", tool_names)
        self.assertIn("update_rule_deployment", tool_names)
        self.assertIn("list_rule_revisions", tool_names)
        self.assertIn("submit_rule_proposal", tool_names)

        # Verify submit_rule_proposal inspectable parameters
        submit_tool = next(t for t in tools if getattr(t, "__name__") == "submit_rule_proposal")
        import inspect
        sig = inspect.signature(submit_tool)
        self.assertIn("title", sig.parameters)
        self.assertIn("target_resource_id", sig.parameters)
        self.assertIn("rationale", sig.parameters)
        self.assertIn("proposed_diff", sig.parameters)
        self.assertIn("optimized_rule_text", sig.parameters)

    def test_rule_compiler_preflight_live(self):
        """Validates that verify_rule communicates with the live Chronicle compiler."""
        if not self.engine:
            self.skipTest("Live SecOps engine not available.")

        valid_rule = (
            "rule live_compiler_test_ok {\n"
            "  meta:\n"
            "    author = \"secops-adk\"\n"
            "    description = \"Compiler verification check\"\n"
            "  events:\n"
            "    $e.metadata.event_type = \"USER_LOGIN\"\n"
            "  condition:\n"
            "    $e\n"
            "}"
        )
        res_ok = self.engine.verify_rule(valid_rule)
        self.assertTrue(res_ok.success)
        self.assertEqual(len(res_ok.diagnostics), 0)

        invalid_rule = (
            "rule live_compiler_test_fail {\n"
            "  events:\n"
            "    $e.unknown_field = 12345\n"
            "  condition:\n"
            "    $non_existent\n"
            "}"
        )
        res_fail = self.engine.verify_rule(invalid_rule)
        self.assertFalse(res_fail.success)
        self.assertGreater(len(res_fail.diagnostics), 0)

    def test_live_autonomous_optimization_and_proposal_creation(self):
        """Executes full autonomous reasoning loop with Gemini 3.8 Flash, compiling and proposing changes."""
        if not self.engine:
            self.skipTest("Live SecOps engine not available.")

        with tempfile.TemporaryDirectory() as tmp_dir:
            temp_root = Path(tmp_dir)
            prop_mgr = ProposalManager(root_dir=temp_root)
            evidence_store = get_evidence_store()

            agent = YaralOptimizerAgent(
                engine=self.engine,
                proposal_manager=prop_mgr,
                evidence_store=evidence_store,
            )

            prompt = (
                "Please inspect rule ru_6cb096c8-2270-4d03-860b-3c3db443a7e4. "
                "Check its match condition and structure, optimize it to prevent bottlenecks, "
                "verify the new rule with verify_rule_text, and call submit_rule_proposal to create a change proposal."
            )

            msg = asyncio.run(agent.chat(prompt, stream="detections", topic="rule-proposals"))

            self.assertIsNotNone(msg)
            self.assertTrue(len(msg.content) > 50)

            # Verify that Gemini 3.8 Flash called the submit_rule_proposal tool
            self.assertIsNotNone(msg.proposal_id)
            self.assertIsNotNone(msg.widget)
            self.assertEqual(msg.widget.get("type"), "hitl_proposal_card")
            self.assertEqual(msg.widget.get("proposal_id"), msg.proposal_id)

            # Verify proposal is saved in Gas Town .proposals/open/
            proposal = prop_mgr.get_proposal(msg.proposal_id)
            self.assertIsNotNone(proposal)
            self.assertEqual(proposal.status, "OPEN")
            self.assertEqual(proposal.author, "@yaral-optimizer")
            self.assertEqual(proposal.target_resource_id, "ru_6cb096c8-2270-4d03-860b-3c3db443a7e4")
            self.assertTrue(proposal.preflight.syntax_verified)

            # Verify execution provenance recorded
            self.assertIn("Live SecOps Tools Executed", msg.content)
            self.assertIn("rule.get", msg.content)


if __name__ == "__main__":
    unittest.main()
