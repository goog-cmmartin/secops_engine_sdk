#!/usr/bin/env python3
"""Live integration tests for the autonomous @logjammer-agent Google ADK 2 Agent.

Verifies:
1. Tool bindings & signatures (list_available_log_types, generate_scenario_logs, replay_to_secops, verify_proposal_with_replay, learn_log_schema).
2. Playbook discovery across 35 built-in guides from goog-cmmartin/logjammer.
3. Authentic multi-source scenario log generation via LogJammer SDK.
4. Gas Town change proposal preflight proof stamping (PreflightProof.replay_verified).
5. Live autonomous reasoning and verification loop powered by Gemini 3.8 Flash.
"""

import asyncio
import os
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from agents.generated.logjammer_agent import LogjammerAgentAgent
from agents.core.evidence_store import LocalFileEvidenceStore
from agents.core.proposal_manager import ProposalManager, ChangeProposal, PreflightProof
from engine.facade import SecOpsEngine
from engine.registry import WorkflowRegistry
from tests.test_helpers import get_live_engine


class LogjammerAgentLiveTest(unittest.TestCase):
    """Test suite for @logjammer-agent empirical replay and preflight verification."""

    def setUp(self):
        self.temp_dir = TemporaryDirectory()
        self.evidence_dir = Path(self.temp_dir.name) / "evidence_store"
        self.evidence_store = LocalFileEvidenceStore(storage_dir=self.evidence_dir)

        self.proposal_manager = ProposalManager(root_dir=Path(self.temp_dir.name))

        try:
            self.engine = get_live_engine()
        except Exception:
            self.engine = SecOpsEngine(custom_registry=WorkflowRegistry())

        self.agent = LogjammerAgentAgent(
            engine=self.engine,
            proposal_manager=self.proposal_manager,
            evidence_store=self.evidence_store,
        )

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_tool_bindings_and_playbook_discovery(self):
        """Verifies that all empirical replay tools are bound and discover 35 guides."""
        tools = self.agent.get_tools()
        tool_names = [t.__name__ for t in tools]
        self.assertIn("list_available_log_types", tool_names)
        self.assertIn("generate_scenario_logs", tool_names)
        self.assertIn("replay_to_secops", tool_names)
        self.assertIn("verify_proposal_with_replay", tool_names)
        self.assertIn("learn_log_schema", tool_names)

        # Introspect available playbooks
        playbooks = self.agent.list_available_log_types()
        self.assertIsInstance(playbooks, list)
        self.assertGreaterEqual(len(playbooks), 30)
        self.assertIn("WINDOWS_SYSMON", playbooks)
        self.assertIn("AUDITD", playbooks)
        self.assertIn("AWS_CLOUDTRAIL", playbooks)
        self.assertIn("PAN_FIREWALL", playbooks)

    def test_generate_scenario_logs(self):
        """Verifies scenario generation produces authentic structured logs."""
        result = self.agent.generate_scenario_logs(
            scenario="SSH brute force attack followed by privilege escalation to root via /bin/su",
            log_types=["AUDITD"],
        )
        self.assertIn("scenario_id", result)
        self.assertIn("logs", result)
        self.assertGreater(result["total_log_count"], 0)
        auditd_logs = result["logs"].get("AUDITD", [])
        self.assertGreater(len(auditd_logs), 0)

    def test_verify_proposal_with_replay_stamps_preflight_proof(self):
        """Verifies that verify_proposal_with_replay updates PreflightProof on an open proposal."""
        # 1. Create candidate proposal
        initial_proposal = ChangeProposal(
            id="prop-audit-su-001",
            title="Detect Unauthorized Root Escalation via SU",
            author="@yaral-optimizer",
            subsystem="detections",
            target_resource_id="ru_audit_su_test",
            action_type="UPDATE_RULE_TEXT",
            rationale="Rule optimized with tightened match window and auditd condition.",
            mutation_payload={
                "rule_text": "rule audit_su_escalation { condition: true }",
            },
            preflight=PreflightProof(syntax_verified=True),
        )
        prop_id = self.proposal_manager.create_proposal(initial_proposal)
        self.assertEqual(prop_id, "prop-audit-su-001")

        # 2. Replay & verify proposal
        res = self.agent.verify_proposal_with_replay(
            proposal_id="prop-audit-su-001",
            scenario="Simulated su command execution by non-wheel user",
            log_types=["AUDITD"],
        )
        self.assertEqual(res["status"], "PREFLIGHT_VERIFIED")
        self.assertTrue(res["replay_verified"])
        self.assertGreater(res["replayed_events"], 0)

        # 3. Reload proposal from disk and verify preflight proof is stamped
        reloaded = self.proposal_manager.get_proposal("prop-audit-su-001")
        self.assertTrue(reloaded.preflight.replay_verified)
        self.assertEqual(reloaded.preflight.replay_log_count, res["replayed_events"])
        self.assertIn("AUDITD", reloaded.preflight.replay_summary)
        self.assertIsNotNone(reloaded.preflight.replay_target_tenant)

    def test_live_autonomous_chat_reasoning(self):
        """Verifies that Gemini 3.8 Flash autonomously uses tools during chat."""
        api_key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
        if not api_key:
            self.skipTest("No GEMINI_API_KEY / GOOGLE_API_KEY set.")

        async def _run_chat():
            prompt = (
                "@logjammer-agent what security and cloud log playbooks are available for replay? "
                "Can you confirm whether WINDOWS_SYSMON and AUDITD are supported?"
            )
            resp = await self.agent.chat(prompt, stream="testing", topic="logjammer-replays")
            self.assertIsNotNone(resp)
            self.assertIn("WINDOWS_SYSMON", resp.content.upper())
            self.assertIn("AUDITD", resp.content.upper())

            # Check tool invocation
            called_tools = [c["tool"] for c in self.agent.executed_tool_calls]
            self.assertIn("list_available_log_types", called_tools)

        asyncio.run(_run_chat())


if __name__ == "__main__":
    unittest.main()
