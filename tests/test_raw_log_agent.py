"""Unit and behavioral tests for RawLogAgent (@raw-log-agent)."""

import unittest
from engine.facade import SecOpsEngine
from engine.registry import WorkflowRegistry, WorkflowCapability
from engine.domain import RawLogSearchResult, RawLogSnippet
from agents.generated.raw_log_agent import RawLogAgentAgent
from tests.test_helpers import get_live_engine


class TestRawLogAgent(unittest.TestCase):
    """Verifies agent manifest metadata, capability bindings, tool registration, and widget generation."""

    def setUp(self):
        self.engine = SecOpsEngine(adapter=None)
        self.agent = RawLogAgentAgent(engine=self.engine)

    def test_agent_manifest_bindings(self):
        """Verifies ADK 2 agent manifest metadata, streams, topics, and tool bindings."""
        self.assertEqual(self.agent.handle, "@raw-log-agent")
        self.assertEqual(self.agent.name, "Raw Log Search Agent")
        self.assertEqual(self.agent.subsystem, "ingestion")
        self.assertEqual(self.agent.default_stream, "ingestion")
        self.assertEqual(self.agent.default_topic, "raw-logs")
        self.assertEqual(self.agent.model, "gemini-3.8-flash")

        # Verify declared capabilities
        self.assertIn("log.raw_logs.search", self.agent.CAPABILITIES)
        self.assertIn("log.query.validate_query", self.agent.CAPABILITIES)
        self.assertIn("log.product_sources.stats", self.agent.CAPABILITIES)
        self.assertIn("event.investigate", self.agent.CAPABILITIES)
        self.assertIn("parser.diagnose_unparsed", self.agent.CAPABILITIES)
        self.assertIn("parser.log_types.list", self.agent.CAPABILITIES)

        # Verify bound tool functions
        tools = self.agent.get_tools()
        tool_names = [getattr(t, "__name__", str(t)) for t in tools]
        self.assertIn("search_raw_logs", tool_names)
        self.assertIn("validate_raw_log_query", tool_names)
        self.assertIn("query_product_source_stats", tool_names)
        self.assertIn("investigate_event", tool_names)
        self.assertIn("diagnose_unparsed_logs", tool_names)
        self.assertIn("list_log_types", tool_names)

    def test_raw_log_search_card_widget_generation(self):
        """Verifies that invoking search_raw_logs generates a raw_log_search_card widget."""
        sample_result = RawLogSearchResult(
            total_matches=2,
            progress=100,
            has_more=False,
            matches=[
                RawLogSnippet(
                    id="sample-event-1",
                    log_type="GCP_CLOUDAUDIT",
                    ingestion_time="2026-09-22T12:00:00Z",
                    snippet='{"protoPayload": {"methodName": "storage.objects.get"}}',
                ),
                RawLogSnippet(
                    id="sample-event-2",
                    log_type="WINEVTLOG",
                    ingestion_time="2026-09-22T12:01:00Z",
                    snippet='<Event xmlns="http://schemas.microsoft.com/win/2004/08/events/event">...</Event>',
                ),
            ],
        )

        isolated_cap = WorkflowCapability(
            capability_id="log.raw_logs.search",
            name="Search Raw Logs",
            description="Searches raw unparsed logs.",
            category="log",
            handler=lambda query, lookback_hours=24, log_types=None: sample_result,
            mcp_tool_name="search_raw_logs",
        )

        custom_agent = RawLogAgentAgent(engine=None)
        custom_agent.bind_capability(isolated_cap)

        tools = {getattr(t, "__name__", str(t)): t for t in custom_agent.get_tools()}
        self.assertIn("search_raw_logs", tools)

        res = tools["search_raw_logs"](query="raw = /.*/ parsed = false", lookback_hours=12)
        self.assertIsInstance(res, dict)
        self.assertEqual(res["total_matches"], 2)

        # Verify widget constructed on agent
        widget = custom_agent.last_widget
        self.assertIsNotNone(widget)
        self.assertEqual(widget["type"], "raw_log_search_card")
        self.assertEqual(widget["total_matches"], 2)
        self.assertEqual(widget["progress"], 100)
        self.assertEqual(widget["query"], "raw = /.*/ parsed = false")
        self.assertEqual(widget["lookback_hours"], 12)
        self.assertEqual(len(widget["matches"]), 2)
        self.assertEqual(widget["matches"][0]["log_type"], "GCP_CLOUDAUDIT")


class TestRawLogAgentLive(unittest.TestCase):
    """Live verification against live Google SecOps endpoint if credentials configured."""

    def setUp(self):
        self.engine = get_live_engine()

    def test_live_agent_validate_and_search(self):
        agent = RawLogAgentAgent(engine=self.engine)
        tools = {getattr(t, "__name__", str(t)): t for t in agent.get_tools()}

        # 1. Validate query syntax
        val_res = tools["validate_raw_log_query"](query="raw = /.*/ parsed = false")
        self.assertIn("is_valid", val_res)
        self.assertTrue(val_res["is_valid"])

        # 2. Search unparsed logs in recent 1 hour
        search_res = tools["search_raw_logs"](
            query="raw = /.*/ parsed = false",
            lookback_hours=1,
            page_size=10,
        )
        self.assertIn("total_matches", search_res)
        self.assertIn("matches", search_res)
        self.assertIsNotNone(agent.last_widget)
        self.assertEqual(agent.last_widget["type"], "raw_log_search_card")


if __name__ == "__main__":
    unittest.main()
