"""Tests for Google ADK 2 Natural Language to GoogleSQL Agent (@sql-analyst)."""

import os
import unittest
from engine.facade import SecOpsEngine
from agents.nl_to_sql_agent import SecOpsNL2SQLAgent
from tests.test_helpers import get_live_engine


class TestSecOpsNL2SQLAgent(unittest.TestCase):
    """Verifies SecOpsNL2SQLAgent tool execution, schema grounding, and compiler feedback loop."""

    def setUp(self):
        try:
            self.engine = get_live_engine()
        except unittest.SkipTest:
            self.engine = None
        self.agent = SecOpsNL2SQLAgent(engine=self.engine)

    def test_agent_attributes(self):
        self.assertEqual(self.agent.handle, "@sql-analyst")
        self.assertEqual(self.agent.subsystem, "analytics")
        self.assertEqual(self.agent.default_stream, "analytics")
        self.assertIn("validate_sql", self.agent._tools)
        self.assertIn("execute_sql", self.agent._tools)
        self.assertIn("get_table_schema", self.agent._tools)
        self.assertIn("explain_query", self.agent._tools)

    def test_get_table_schema(self):
        schema = self.agent.get_table_schema("events")
        self.assertIn("fields", schema)
        self.assertIn("metadata", schema["fields"])
        self.assertIn("security_result", schema["fields"])

        err_schema = self.agent.get_table_schema("nonexistent_table")
        self.assertIn("error", err_schema)

    def test_explain_query(self):
        sql = "SELECT metadata.event_type, COUNTIF('BLOCK' IN UNNEST(security_result[SAFE_OFFSET(0)].action)) FROM events GROUP BY 1"
        explanation = self.agent.explain_query(sql)
        self.assertIn("events", explanation)
        self.assertIn("UNNEST", explanation)
        self.assertIn("COUNTIF", explanation)
        self.assertIn("GROUP BY", explanation)

    def test_validate_sql_with_live_compiler(self):
        if not self.engine:
            self.skipTest("Live SecOpsEngine not configured")

        # Valid query
        valid_sql = "SELECT metadata.event_type, count(*) AS total FROM events GROUP BY 1 LIMIT 5"
        v_res = self.agent.validate_sql(valid_sql)
        self.assertTrue(v_res.get("valid"))
        self.assertIsNone(v_res.get("error_message"))

        # Invalid query syntax
        invalid_sql = "SELECT metadata.event_type, count(*) FROM events WHERE"
        inv_res = self.agent.validate_sql(invalid_sql)
        self.assertFalse(inv_res.get("valid"))
        self.assertIsNotNone(inv_res.get("error_message"))

    def test_execute_sql_with_live_secops(self):
        if not self.engine:
            self.skipTest("Live SecOpsEngine not configured")

        valid_sql = "SELECT metadata.event_type, count(*) AS total FROM events GROUP BY 1 LIMIT 3"
        e_res = self.agent.execute_sql(valid_sql, time_unit="DAY", time_value="7")
        self.assertTrue(e_res.get("success"))
        self.assertIn("columns", e_res)
        self.assertIn("rows", e_res)
        self.assertGreater(len(e_res["rows"]), 0)

        # Verify last_widget payload populated
        self.assertIsNotNone(self.agent.last_widget)
        self.assertEqual(self.agent.last_widget["type"], "data_table")
        self.assertEqual(self.agent.last_widget["columns"], e_res["columns"])


if __name__ == "__main__":
    unittest.main()
