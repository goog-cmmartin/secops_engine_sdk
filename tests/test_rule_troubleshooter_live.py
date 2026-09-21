"""Tests for the live autonomous Rule Troubleshooter Agent.

Verifies:
- Binding of 5 live Google SecOps capabilities to Gemini-compatible tool functions.
- Serialization of live Chronicle dataclasses for LLM function calling.
- Live autonomous agent reasoning and tool invocation against Google SecOps.
- Strict compliance with no-mock rules and explicit error reporting.
"""

import asyncio
import os
import unittest
from unittest.mock import patch

from adapters.google_secops import GoogleSecOpsAdapter
from agents.core.base_adk_agent import _serialize_for_llm
from agents.core.evidence_store import get_evidence_store
from agents.generated.rule_troubleshooter import RuleTroubleshooterAgent
from engine.facade import SecOpsEngine
from tests.test_helpers import get_live_adapter, get_live_engine


class TestRuleTroubleshooterLive(unittest.TestCase):
    """Test suite for the live Rule Troubleshooter Google ADK 2 agent."""

    def setUp(self):
        try:
            self.adapter = get_live_adapter()
            self.engine = get_live_engine(adapter=self.adapter)
        except unittest.SkipTest:
            self.adapter = None
            self.engine = None

    def test_tool_binding_and_signatures(self):
        """Verifies that all 5 capabilities are bound with valid inspectable signatures."""
        if not self.engine:
            self.skipTest("Live SecOps engine not available.")

        agent = RuleTroubleshooterAgent(engine=self.engine)
        tools = agent.get_tools()

        self.assertEqual(len(tools), 6)
        tool_names = [getattr(t, "__name__", "") for t in tools]

        self.assertIn("get_rule", tool_names)
        self.assertIn("get_rule_deployment", tool_names)
        self.assertIn("list_rule_errors", tool_names)
        self.assertIn("audit_rule_health", tool_names)
        self.assertIn("query_gcp_cloud_logging", tool_names)
        self.assertIn("get_task_status", tool_names)

        # Verify get_rule wrapper exposes required parameter
        rule_get_tool = next(t for t in tools if getattr(t, "__name__") == "get_rule")
        sig = getattr(rule_get_tool, "__signature__", None)
        self.assertIsNotNone(sig)
        self.assertIn("rule_id_or_name", sig.parameters)

    def test_serialization_for_llm(self):
        """Verifies dataclass and domain object serialization for Gemini context."""
        if not self.engine:
            self.skipTest("Live SecOps engine not available.")

        rule_detail = self.engine.get_rule("ru_6cb096c8-2270-4d03-860b-3c3db443a7e4")
        serialized = _serialize_for_llm(rule_detail)

        self.assertIsInstance(serialized, dict)
        self.assertIn("display_name", serialized)
        self.assertIn("text", serialized)
        self.assertIn("rule_text", serialized)
        self.assertEqual(serialized["display_name"], "IngestionLatencyDataShape")

    def test_missing_api_key_reports_explicit_error(self):
        """Ensures missing API key yields an explicit error message, never silent mocks."""
        if not self.engine:
            self.skipTest("Live SecOps engine not available.")

        agent = RuleTroubleshooterAgent(engine=self.engine)

        with patch.dict(os.environ, {"GOOGLE_API_KEY": "", "GEMINI_API_KEY": ""}, clear=True), \
             patch("google.genai.Client", side_effect=Exception("No credentials available")):
            msg = asyncio.run(agent.chat("Analyze rule ru_6cb096c8-2270-4d03-860b-3c3db443a7e4"))
            self.assertIn("Agent Configuration Error", msg.content)
            self.assertIn("requires Google Cloud ADC", msg.content)

    def test_live_autonomous_rule_troubleshooter(self):
        """Executes full autonomous reasoning loop against live Chronicle SIEM and Gemini."""
        if not self.engine:
            self.skipTest("Live SecOps engine not available.")

        api_key = os.getenv("GOOGLE_API_KEY") or os.getenv("GEMINI_API_KEY")
        if not api_key:
            self.skipTest("GOOGLE_API_KEY not set in environment.")

        evidence_store = get_evidence_store()
        agent = RuleTroubleshooterAgent(engine=self.engine, evidence_store=evidence_store)

        prompt = (
            "Please inspect rule ru_6cb096c8-2270-4d03-860b-3c3db443a7e4 and verify its deployment state."
        )

        msg = asyncio.run(agent.chat(prompt, stream="detections", topic="rule-health"))

        self.assertIsNotNone(msg)
        self.assertTrue(len(msg.content) > 50)
        # Content should reflect real rule analysis
        self.assertTrue(
            any(k in msg.content.lower() for k in ["latency", "ingestion", "ru_6cb096c8", "deployment", "rule"])
        )
        # Provenance trace must show live tools were executed
        self.assertIn("Live SecOps Tools Executed", msg.content)
        self.assertTrue("rule.get" in msg.content or "rule.deployment.get" in msg.content)

        # Verify state persistence into Evidence Fabric Blackboard
        state = evidence_store.get_rule_state("ru_6cb096c8-2270-4d03-860b-3c3db443a7e4")
        self.assertIsNotNone(state)
        self.assertEqual(state.get("last_inspected_by"), "@rule-troubleshooter")
        self.assertIn("last_rule_get", state)


if __name__ == "__main__":
    unittest.main()
