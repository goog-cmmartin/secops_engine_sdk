"""Tests for Google SecOps Protobuf Schema Catalog and GoogleSQL Grounding."""

import unittest
from engine.schema_catalog import SecOpsSchemaCatalog


class TestSecOpsSchemaCatalog(unittest.TestCase):
    """Verifies schema catalog integrity, table mappings, and dialect invariants."""

    def setUp(self):
        self.catalog = SecOpsSchemaCatalog()

    def test_list_tables(self):
        tables = self.catalog.list_tables()
        self.assertIn("events", tables)
        self.assertIn("detections", tables)
        self.assertIn("cases", tables)
        self.assertIn("case_history", tables)
        self.assertIn("rules", tables)

    def test_events_schema_structure(self):
        events_schema = self.catalog.get_table_schema("events")
        self.assertIsNotNone(events_schema)
        fields = events_schema["fields"]
        self.assertIn("metadata", fields)
        self.assertIn("principal", fields)
        self.assertIn("target", fields)
        self.assertIn("security_result", fields)
        self.assertEqual(fields["security_result"]["type"], "ARRAY<STRUCT>")

        # Subfields
        meta_sub = fields["metadata"]["subfields"]
        self.assertIn("event_timestamp", meta_sub)
        self.assertIn("sql_access", meta_sub["event_timestamp"])

    def test_cases_schema_structure(self):
        cases_schema = self.catalog.get_table_schema("cases")
        self.assertIsNotNone(cases_schema)
        fields = cases_schema["fields"]
        self.assertIn("response_platform_info", fields)
        self.assertIn("status", fields)
        self.assertIn("priority", fields)

    def test_grounding_prompt_generation(self):
        prompt = self.catalog.get_grounding_prompt()
        self.assertIn("GOOGLE SECOPS CHRONICLE GOOGLESQL PROTOBUF SCHEMA CATALOG", prompt)
        self.assertIn("STRICT CHRONICLE GOOGLESQL COMPILER INVARIANTS", prompt)
        self.assertIn("TIMESTAMP_SECONDS", prompt)
        self.assertIn("Table: `events`", prompt)
        self.assertIn("Table: `cases`", prompt)

    def test_vendored_protos_exist(self):
        protos_dir = self.catalog.protos_dir
        self.assertTrue(protos_dir.exists())
        self.assertTrue((protos_dir / "udm.proto").exists())
        self.assertTrue((protos_dir / "collections.proto").exists())
        self.assertTrue((protos_dir / "case.proto").exists())
        self.assertTrue((protos_dir / "case_history.proto").exists())
        self.assertTrue((protos_dir / "rule.proto").exists())


if __name__ == "__main__":
    unittest.main()
