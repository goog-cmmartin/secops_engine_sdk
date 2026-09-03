"""Tests for Chronicle SIEM Data Tables engine workflows and capabilities."""

import unittest
from engine.facade import SecOpsEngine
from engine.domain import DataTable, DataTableListResult, DataTableRowListResult
from tests.test_helpers import get_live_engine


class TestDataTablesWorkflows(unittest.TestCase):
    """Test suite for Chronicle SIEM Data Tables workflows."""

    @classmethod
    def setUpClass(cls):
        cls.engine = get_live_engine()

    def test_list_data_tables(self):
        """Validates listing Chronicle SIEM Data Tables."""
        res = self.engine.list_data_tables(page_size=20)
        self.assertIsInstance(res, DataTableListResult)
        self.assertIsInstance(res.data_tables, list)
        if res.data_tables:
            first_table = res.data_tables[0]
            self.assertIsInstance(first_table, DataTable)
            self.assertTrue(bool(first_table.table_id))
            self.assertTrue(bool(first_table.display_name))
            self.assertIsInstance(first_table.column_info, list)

    def test_get_data_table_and_rows(self):
        """Validates retrieving a specific Data Table and its rows."""
        res = self.engine.list_data_tables(page_size=10)
        if not res.data_tables:
            self.skipTest("No data tables available in tenant to test get_data_table.")

        target_table_id = res.data_tables[0].table_id
        dt = self.engine.get_data_table(target_table_id)
        self.assertIsInstance(dt, DataTable)
        self.assertEqual(dt.table_id, target_table_id)
        self.assertTrue(bool(dt.display_name))

        rows_res = self.engine.list_data_table_rows(target_table_id, page_size=10)
        self.assertIsInstance(rows_res, DataTableRowListResult)
        self.assertIsInstance(rows_res.rows, list)
        if rows_res.rows:
            first_row = rows_res.rows[0]
            self.assertTrue(bool(first_row.row_id))
            self.assertIsInstance(first_row.values, list)

    def test_data_table_capability_registration(self):
        """Validates that all data table capabilities are registered on the engine."""
        capabilities = {c.capability_id: c for c in self.engine.list_capabilities(category="data_table")}
        expected_ids = [
            "data_table.list",
            "data_table.get",
            "data_table.create",
            "data_table.patch",
            "data_table.delete",
            "data_table.list_rows",
            "data_table.add_rows",
            "data_table.delete_row",
        ]
        for cap_id in expected_ids:
            self.assertIn(cap_id, capabilities)
            self.assertEqual(capabilities[cap_id].category, "data_table")
