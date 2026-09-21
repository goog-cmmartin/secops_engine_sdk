"""Unit tests for the Google ADK 2 SecOps Agent Fleet."""

from pathlib import Path
import tempfile
import unittest

from agents.core.base_adk_agent import BaseSecOpsAdkAgent
from agents.core.proposal_manager import PreflightProof, ProposalManager
from agents.generated import create_agent_fleet
from agents.generated.yaral_optimizer import YaralOptimizerAgent
from engine.facade import SecOpsEngine
from engine.registry import WorkflowRegistry


class _InertAdapterForFleetTest:
    def __getattr__(self, name: str):
        def _no_op(*args, **kwargs):
            return {"status": "ok", "mock_check": False}
        return _no_op


class AgentFleetTest(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root_path = Path(self.temp_dir.name)
        self.proposal_mgr = ProposalManager(root_dir=self.root_path)

        self.engine = SecOpsEngine(
            adapter=_InertAdapterForFleetTest(),
            custom_registry=WorkflowRegistry(),
        )
        self.fleet = create_agent_fleet(
            engine=self.engine,
            proposal_manager=self.proposal_mgr,
        )

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_fleet_contains_twelve_specialized_agents(self):
        expected_handles = [
            "@secops-dispatcher",
            "@rule-troubleshooter",
            "@yaral-optimizer",
            "@logjammer-agent",
            "@identity-governor",
            "@detection-decay-agent",
            "@detection-tuning-agent",
            "@feed-agent",
            "@parser-doctor",
            "@sql-analyst",
            "@gcp-telemetry-agent",
            "@tenant-posture-agent",
        ]
        for handle in expected_handles:
            self.assertIn(handle, self.fleet)
            agent = self.fleet[handle]
            self.assertIsInstance(agent, BaseSecOpsAdkAgent)

    def test_tenant_posture_agent_tool_bindings(self):
        agent = self.fleet["@tenant-posture-agent"]
        tools = agent.get_tools()
        tool_names = [getattr(t, "__name__", str(t)) for t in tools]
        self.assertIn("audit_tenant_posture", tool_names)
        self.assertIn("snapshot_tenant_baseline", tool_names)
        self.assertIn("detect_configuration_drift", tool_names)
        self.assertIn("query_settings_slice", tool_names)
        self.assertIn("list_historical_baselines", tool_names)
        self.assertEqual(agent.default_stream, "governance")
        self.assertEqual(agent.default_topic, "tenant-posture")

    def test_gcp_telemetry_agent_tool_bindings(self):
        telem = self.fleet["@gcp-telemetry-agent"]
        tools = telem.get_tools()
        tool_names = [getattr(t, "__name__", str(t)) for t in tools]
        self.assertIn("audit_chronicle_telemetry", tool_names)
        self.assertIn("query_metrics", tool_names)
        self.assertIn("search_audit_logs", tool_names)
        self.assertEqual(telem.default_stream, "telemetry")
        self.assertEqual(telem.default_topic, "logs-and-metrics")

    def test_identity_governor_tool_bindings(self):
        gov = self.fleet["@identity-governor"]
        tools = gov.get_tools()
        tool_names = [t.__name__ for t in tools]
        self.assertIn("audit_chronicle_iam_bindings", tool_names)
        self.assertIn("query_chronicle_custom_roles", tool_names)
        self.assertIn("query_inventory_identity_report", tool_names)
        self.assertIn("run_identity_drift_audit", tool_names)
        self.assertEqual(gov.default_stream, "identity")
        self.assertEqual(gov.default_topic, "iam-audit")

    def test_feed_agent_tool_bindings(self):
        feed_agent = self.fleet["@feed-agent"]
        tools = feed_agent.get_tools()
        tool_names = [getattr(t, "__name__", str(t)) for t in tools]
        self.assertIn("audit_feeds", tool_names)
        self.assertIn("get_feed_details", tool_names)
        self.assertIn("check_feed_latency", tool_names)
        self.assertIn("submit_feed_proposal", tool_names)
        self.assertEqual(feed_agent.default_stream, "ingestion")
        self.assertEqual(feed_agent.default_topic, "feed-health")

    def test_parser_doctor_tool_bindings(self):
        parser_doc = self.fleet["@parser-doctor"]
        tools = parser_doc.get_tools()
        tool_names = [getattr(t, "__name__", str(t)) for t in tools]
        self.assertIn("audit_parsers", tool_names)
        self.assertIn("get_parser_cbn", tool_names)
        self.assertIn("get_parser_extension", tool_names)
        self.assertIn("diagnose_unparsed_logs", tool_names)
        self.assertIn("run_parser_test", tool_names)
        self.assertIn("submit_parser_proposal", tool_names)
        self.assertEqual(parser_doc.default_stream, "ingestion")
        self.assertEqual(parser_doc.default_topic, "parser-drops")

    def test_yaral_optimizer_tool_bindings(self):
        optimizer: YaralOptimizerAgent = self.fleet["@yaral-optimizer"]
        tools = optimizer.get_tools()
        tool_names = [t.__name__ for t in tools]

        self.assertIn("verify_rule_text", tool_names)
        self.assertIn("get_rule", tool_names)
        self.assertIn("patch_rule", tool_names)
        self.assertEqual(optimizer.default_stream, "detections")
        self.assertEqual(optimizer.default_topic, "rule-proposals")

    def test_secops_dispatcher_tool_bindings(self):
        dispatcher = self.fleet["@secops-dispatcher"]
        tools = dispatcher.get_tools()
        tool_names = [t.__name__ for t in tools]
        self.assertIn("list_fleet_agents", tool_names)
        self.assertIn("delegate_task", tool_names)
        self.assertIn("list_open_proposals", tool_names)

    def test_agent_post_message_to_stream_and_topic(self):
        troubleshooter = self.fleet["@rule-troubleshooter"]
        msg = troubleshooter.post_message(
            content="Alert: Rule ru_0e378636 has encountered 36 timeouts in the last 2 hours.",
            stream="detections",
            topic="performance-alerts",
        )
        self.assertEqual(msg.stream, "detections")
        self.assertEqual(msg.topic, "performance-alerts")
        self.assertEqual(msg.sender_handle, "@rule-troubleshooter")
        self.assertIn("ru_0e378636", msg.content)

    def test_agent_submits_proposal(self):
        optimizer = self.fleet["@yaral-optimizer"]
        proposal = optimizer.submit_proposal(
            title="Partition ru_0e378636 by $target.user.userid",
            target_resource_id="ru_0e378636",
            action_type="PATCH_RULE",
            rationale="Eliminates cross-join memory spikes during peak traffic.",
            proposed_diff="--- a\n+++ b\n- match: $e over 5m\n+ match: $user over 5m",
            mutation_payload={
                "rule_text": "rule test_rule { condition: true }",
                "update_mask": "text",
            },
            preflight=PreflightProof(
                syntax_verified=True,
                replay_verified=True,
                replay_log_count=1000,
                replay_summary="0 timeouts detected",
            ),
        )

        self.assertTrue(proposal.id.startswith("prop-"))
        self.assertEqual(proposal.status, "OPEN")
        self.assertEqual(proposal.author, "@yaral-optimizer")

        # Check outbox has the notification message with hitl widget
        self.assertEqual(len(optimizer._outbox), 1)
        last_msg = optimizer._outbox[-1]
        self.assertEqual(last_msg.proposal_id, proposal.id)
        self.assertEqual(last_msg.widget["type"], "hitl_proposal_card")


if __name__ == "__main__":
    unittest.main()
