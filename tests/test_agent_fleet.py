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

    def test_fleet_contains_twenty_specialized_agents(self):
        self.assertGreaterEqual(len(self.fleet), 20)
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
            "@playbook-decay-agent",
            "@timestamp-integrity-agent",
            "@rule-conflict-agent",
            "@log-cost-agent",
            "@raw-log-agent",
            "@namespace-label-agent",
            "@tenant-cartographer",
            "@soc-briefing-agent",
        ]
        for handle in expected_handles:
            self.assertIn(handle, self.fleet)
            agent = self.fleet[handle]
            self.assertIsInstance(agent, BaseSecOpsAdkAgent)

    def test_soc_briefing_agent_tool_bindings(self):
        agent = self.fleet["@soc-briefing-agent"]
        tools = agent.get_tools()
        tool_names = [getattr(t, "__name__", str(t)) for t in tools]
        self.assertIn("generate_shift_briefing", tool_names)
        self.assertIn("generate_posture_snapshot", tool_names)
        self.assertIn("get_composite_entity_dossier", tool_names)
        self.assertEqual(agent.default_stream, "briefings")
        self.assertEqual(agent.default_topic, "shift-briefings")


    def test_namespace_label_agent_tool_bindings(self):
        agent = self.fleet["@namespace-label-agent"]
        tools = agent.get_tools()
        tool_names = [getattr(t, "__name__", str(t)) for t in tools]
        self.assertIn("analyze_ingestion_labels", tool_names)
        self.assertIn("analyze_namespaces", tool_names)
        self.assertIn("audit_data_rbac_alignment", tool_names)
        self.assertIn("analyze_labels_and_namespaces", tool_names)
        self.assertEqual(agent.default_stream, "ingestion")
        self.assertEqual(agent.default_topic, "namespace-labels")

    def test_raw_log_agent_tool_bindings(self):
        agent = self.fleet["@raw-log-agent"]
        tools = agent.get_tools()
        tool_names = [getattr(t, "__name__", str(t)) for t in tools]
        self.assertIn("search_raw_logs", tool_names)
        self.assertIn("validate_raw_log_query", tool_names)
        self.assertIn("query_product_source_stats", tool_names)
        self.assertIn("investigate_event", tool_names)
        self.assertIn("diagnose_unparsed_logs", tool_names)
        self.assertIn("list_log_types", tool_names)
        self.assertEqual(agent.default_stream, "ingestion")
        self.assertEqual(agent.default_topic, "raw-logs")

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

    def test_playbook_decay_agent_tool_bindings(self):
        agent = self.fleet["@playbook-decay-agent"]
        tools = agent.get_tools()
        tool_names = [getattr(t, "__name__", str(t)) for t in tools]
        self.assertIn("audit_playbook_decay", tool_names)
        self.assertIn("get_playbook_decay_report", tool_names)
        self.assertIn("list_playbook_reports", tool_names)
        self.assertEqual(agent.default_stream, "soar")
        self.assertEqual(agent.default_topic, "playbook-health")

    def test_timestamp_integrity_agent_tool_bindings(self):
        agent = self.fleet["@timestamp-integrity-agent"]
        tools = agent.get_tools()
        tool_names = [getattr(t, "__name__", str(t)) for t in tools]
        self.assertIn("audit_timestamp_integrity", tool_names)
        self.assertIn("get_timestamp_integrity_report", tool_names)
        self.assertIn("list_timestamp_integrity_history", tool_names)
        self.assertEqual(agent.default_stream, "ingestion")
        self.assertEqual(agent.default_topic, "timestamp-integrity")

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

    def test_afc_fallback_handles_active_chat_session(self):
        """Verifies that the AFC empty text recovery correctly inspects active_chat_session."""
        agent = self.fleet["@yaral-optimizer"]
        import inspect
        source = inspect.getsource(agent.chat)
        # Ensure 'chat' is not used as a bare reference in AFC recovery block
        self.assertNotIn("hasattr(chat,", source)
        self.assertIn("active_chat_session", source)


if __name__ == "__main__":
    unittest.main()
