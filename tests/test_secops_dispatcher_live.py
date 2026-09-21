#!/usr/bin/env python3
"""Live integration tests for the autonomous @secops-dispatcher Google ADK 2 Agent.

Verifies:
1. Tool bindings & signatures (list_fleet_agents, delegate_task, list_open_proposals, audit_rule_health).
2. Inter-agent task delegation into Evidence Fabric (secops_todos).
3. Live autonomous multi-agent triage and delegation powered by Gemini 3.8 Flash.
"""

import asyncio
import os
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from agents.generated.secops_dispatcher import SecopsDispatcherAgent
from agents.core.evidence_store import get_evidence_store, LocalFileEvidenceStore
from agents.core.proposal_manager import ProposalManager
from engine.facade import SecOpsEngine
from engine.registry import WorkflowRegistry
from tests.test_helpers import get_live_engine


class SecopsDispatcherLiveTest(unittest.TestCase):
    """Test suite for @secops-dispatcher agent capabilities and autonomous coordination."""

    def setUp(self):
        self.temp_dir = TemporaryDirectory()
        self.evidence_dir = Path(self.temp_dir.name) / "evidence_store"
        self.evidence_store = LocalFileEvidenceStore(storage_dir=self.evidence_dir)

        self.proposal_manager = ProposalManager(root_dir=Path(self.temp_dir.name))

        # Initialize engine
        try:
            self.engine = get_live_engine()
        except Exception:
            self.engine = SecOpsEngine(custom_registry=WorkflowRegistry())

        self.agent = SecopsDispatcherAgent(
            engine=self.engine,
            proposal_manager=self.proposal_manager,
            evidence_store=self.evidence_store,
        )

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_tool_binding_and_signatures(self):
        """Verifies that all coordination tools and engine capabilities are properly bound."""
        tools = self.agent.get_tools()
        tool_names = [t.__name__ for t in tools]
        self.assertIn("list_fleet_agents", tool_names)
        self.assertIn("delegate_task", tool_names)
        self.assertIn("list_open_proposals", tool_names)
        self.assertIn("audit_parsers", tool_names)
        self.assertIn("audit_feeds", tool_names)
        self.assertIn("diagnose_unparsed_logs", tool_names)

        # Test list_fleet_agents
        roster = self.agent.list_fleet_agents()
        self.assertIsInstance(roster, list)
        self.assertTrue(len(roster) > 0)
        handles = [a["handle"] for a in roster]
        self.assertIn("@rule-troubleshooter", handles)
        self.assertIn("@yaral-optimizer", handles)

        # Test list_open_proposals
        props = self.agent.list_open_proposals()
        self.assertIsInstance(props, list)

    def test_delegate_task_persists_to_evidence_fabric(self):
        """Verifies that delegate_task creates a real todo in the Evidence Fabric blackboard."""
        result = self.agent.delegate_task(
            assigned_to="@yaral-optimizer",
            title="Optimize match window for ru_6cb096c8",
            description="Rule experiencing sliding window bottlenecks. Narrow window from 1h to 10m.",
            stream="detections",
            topic="rule-proposals",
            priority="HIGH",
        )

        self.assertEqual(result["status"], "TASK_DELEGATED")
        self.assertEqual(result["assigned_to"], "@yaral-optimizer")
        todo_id = result["todo_id"]
        self.assertTrue(todo_id.startswith("todo_") or todo_id.startswith("todo-"))

        # Verify persisted in evidence store
        todos = self.evidence_store.list_todos(status="PENDING")
        matching = [t for t in todos if t["id"] == todo_id]
        self.assertEqual(len(matching), 1)
        self.assertEqual(matching[0]["assigned_to"], "@yaral-optimizer")
        self.assertEqual(matching[0]["created_by"], "@secops-dispatcher")
        self.assertEqual(matching[0]["priority"], "HIGH")

        # Verify tool provenance recorded
        tool_calls = [c for c in self.agent.executed_tool_calls if c["tool"] == "delegate_task"]
        self.assertEqual(len(tool_calls), 1)
        self.assertEqual(tool_calls[0]["arguments"]["todo_id"], todo_id)

    def test_live_autonomous_triage_and_delegation(self):
        """Verifies live Gemini 3.8 Flash autonomous reasoning loop and task delegation."""
        has_creds = bool(os.getenv("GOOGLE_APPLICATION_CREDENTIALS") or os.getenv("GOOGLE_API_KEY") or os.getenv("GEMINI_API_KEY"))
        if not has_creds:
            self.skipTest("No Google credentials available for live Gemini 3.8 Flash test.")

        prompt = (
            "We have an operational alert: rule ru_6cb096c8-2270-4d03-860b-3c3db443a7e4 is running slow "
            "and needs performance optimization on its sliding match window. Please triage this issue, "
            "identify which agent handles performance optimization, and delegate the task to them."
        )

        agent_msg = asyncio.run(
            self.agent.chat(prompt, stream="detections", topic="rule-proposals")
        )

        self.assertIsNotNone(agent_msg)
        self.assertTrue(len(agent_msg.content) > 0)

        # Check if the agent called delegate_task or mentioned @yaral-optimizer
        delegated_calls = [c for c in self.agent.executed_tool_calls if c["tool"] == "delegate_task"]
        if delegated_calls:
            self.assertEqual(delegated_calls[0]["arguments"]["assigned_to"], "@yaral-optimizer")
        else:
            self.assertIn("@yaral-optimizer", agent_msg.content)

        # Verify provenance was logged
        recent_evidence = self.evidence_store.list_evidence(limit=1)
        self.assertEqual(len(recent_evidence), 1)
        self.assertEqual(recent_evidence[0]["agent_handle"], "@secops-dispatcher")


if __name__ == "__main__":
    unittest.main()
