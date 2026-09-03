"""Unit tests for AuditDataTableHealthWorkflow and Data Table Health models."""

import unittest
from datetime import datetime, timezone
from typing import Any, Dict, List
from unittest.mock import MagicMock

from engine.domain import (
    DataTable,
    DataTableColumnInfo,
    DataTableHealthFinding,
    DataTableHealthReport,
    DataTableHealthStatus,
    DataTableListResult,
    RuleSummary,
    RuleListResult,
)
from engine.facade import SecOpsEngine
from engine.workflows.data_table_health import AuditDataTableHealthWorkflow


class TestDataTableHealthWorkflow(unittest.TestCase):
    """Test suite for AuditDataTableHealthWorkflow."""

    def setUp(self):
        self.mock_adapter = MagicMock()
        self.workflow = AuditDataTableHealthWorkflow(adapter=self.mock_adapter)

    def test_capability_registration(self):
        """Verifies data_table.audit_health capability is properly registered."""
        engine = SecOpsEngine()
        cap = engine.registry.get("data_table.audit_health")
        self.assertIsNotNone(cap)
        self.assertEqual(cap.category, "data_table")
        self.assertEqual(cap.domain, "data_table")
        self.assertEqual(cap.kind, "workflow")
        self.assertTrue(cap.composed)
        self.assertIn("data_table.list", cap.uses)
        self.assertIn("rule.list", cap.uses)

    def test_healthy_table_evaluation(self):
        """Verifies evaluation of healthy populated Data Table."""
        self.mock_adapter.list_data_tables.return_value = {
            "dataTables": [
                {
                    "name": "projects/123/locations/us/instances/abc/dataTables/monitored_ips",
                    "displayName": "monitored_ips",
                    "approximateRowCount": "1500",
                    "columnInfo": [
                        {"columnIndex": 0, "originalColumn": "ip_address", "columnType": "STRING", "keyColumn": True},
                        {"columnIndex": 1, "originalColumn": "threat_label", "columnType": "STRING", "keyColumn": False},
                    ],
                    "rules": ["rule_1"],
                    "ruleAssociationsCount": 1,
                    "createTime": "2026-01-01T00:00:00Z",
                    "updateTime": "2026-01-10T00:00:00Z",
                }
            ]
        }
        self.mock_adapter.list_rules.return_value = {"rules": []}

        report = self.workflow.execute(lookback_days=14, stale_days=1000, correlate_rules=False)

        self.assertEqual(report.total_tables_audited, 1)
        self.assertEqual(report.healthy_count, 1)
        self.assertEqual(report.empty_referenced_count, 0)
        finding = report.findings[0]
        self.assertEqual(finding.status, DataTableHealthStatus.HEALTHY)
        self.assertEqual(finding.approximate_row_count, 1500)
        self.assertEqual(finding.key_columns, ["ip_address"])

    def test_empty_referenced_table_detection(self):
        """Verifies detection of critical risk: 0 rows in table referenced by active rules."""
        self.mock_adapter.list_data_tables.return_value = {
            "dataTables": [
                {
                    "name": "projects/123/locations/us/instances/abc/dataTables/critical_watchlist",
                    "displayName": "critical_watchlist",
                    "approximateRowCount": "0",
                    "columnInfo": [
                        {"columnIndex": 0, "originalColumn": "username", "columnType": "STRING", "keyColumn": True},
                    ],
                    "rules": ["Executive Login Anomaly"],
                    "ruleAssociationsCount": 1,
                    "createTime": "2026-01-01T00:00:00Z",
                    "updateTime": "2026-01-01T00:00:00Z",
                }
            ]
        }
        self.mock_adapter.list_rules.return_value = {"rules": []}

        report = self.workflow.execute(lookback_days=14, stale_days=1000, correlate_rules=False)

        self.assertEqual(report.total_tables_audited, 1)
        self.assertEqual(report.empty_referenced_count, 1)
        finding = report.findings[0]
        self.assertEqual(finding.status, DataTableHealthStatus.EMPTY_REFERENCED)
        self.assertIn("CRITICAL DETECTION RISK", finding.details)
        self.assertIn("Executive Login Anomaly", finding.associated_rules)

    def test_orphan_table_detection(self):
        """Verifies detection of orphan table with 0 rows, 0 rules, and stale inactivity."""
        self.mock_adapter.list_data_tables.return_value = {
            "dataTables": [
                {
                    "name": "projects/123/locations/us/instances/abc/dataTables/abandoned_temp",
                    "displayName": "abandoned_temp",
                    "approximateRowCount": "0",
                    "columnInfo": [
                        {"columnIndex": 0, "originalColumn": "temp_id", "columnType": "STRING", "keyColumn": True},
                    ],
                    "rules": [],
                    "ruleAssociationsCount": 0,
                    "createTime": "2024-01-01T00:00:00Z",
                    "updateTime": "2024-01-01T00:00:00Z",
                }
            ]
        }
        self.mock_adapter.list_rules.return_value = {"rules": []}

        report = self.workflow.execute(lookback_days=14, stale_days=180, correlate_rules=False)

        self.assertEqual(report.total_tables_audited, 1)
        self.assertEqual(report.orphan_count, 1)
        self.assertEqual(report.findings[0].status, DataTableHealthStatus.ORPHAN)

    def test_recently_created_table(self):
        """Verifies detection of recently created Data Table."""
        now_str = datetime.now(timezone.utc).isoformat()
        self.mock_adapter.list_data_tables.return_value = {
            "dataTables": [
                {
                    "name": "projects/123/locations/us/instances/abc/dataTables/new_ioc_feed",
                    "displayName": "new_ioc_feed",
                    "approximateRowCount": "50",
                    "columnInfo": [
                        {"columnIndex": 0, "originalColumn": "ioc_val", "columnType": "STRING", "keyColumn": True},
                    ],
                    "rules": [],
                    "ruleAssociationsCount": 0,
                    "createTime": now_str,
                    "updateTime": now_str,
                }
            ]
        }
        self.mock_adapter.list_rules.return_value = {"rules": []}

        report = self.workflow.execute(lookback_days=14, correlate_rules=False)

        self.assertEqual(report.total_tables_audited, 1)
        self.assertEqual(report.recently_created_count, 1)
        self.assertEqual(report.findings[0].status, DataTableHealthStatus.RECENTLY_CREATED)

    def test_schema_missing_key_column(self):
        """Verifies detection of schema issues when no key column is configured."""
        self.mock_adapter.list_data_tables.return_value = {
            "dataTables": [
                {
                    "name": "projects/123/locations/us/instances/abc/dataTables/unindexed_table",
                    "displayName": "unindexed_table",
                    "approximateRowCount": "200",
                    "columnInfo": [
                        {"columnIndex": 0, "originalColumn": "col1", "columnType": "STRING", "keyColumn": False},
                        {"columnIndex": 1, "originalColumn": "col2", "columnType": "STRING", "keyColumn": False},
                    ],
                    "rules": [],
                    "ruleAssociationsCount": 0,
                    "createTime": "2026-01-01T00:00:00Z",
                    "updateTime": "2026-01-01T00:00:00Z",
                }
            ]
        }
        self.mock_adapter.list_rules.return_value = {"rules": []}

        report = self.workflow.execute(lookback_days=14, stale_days=1000, correlate_rules=False)

        self.assertEqual(report.total_tables_audited, 1)
        self.assertEqual(report.schema_issue_count, 1)
        self.assertEqual(report.findings[0].status, DataTableHealthStatus.SCHEMA_ISSUE)
        self.assertIn("no key column designated", report.findings[0].details)

    def test_rule_lineage_correlation(self):
        """Verifies correlation of Data Table references from YARA-L rule bodies."""
        self.mock_adapter.list_data_tables.return_value = {
            "dataTables": [
                {
                    "name": "projects/123/locations/us/instances/abc/dataTables/bad_domains",
                    "displayName": "bad_domains",
                    "approximateRowCount": "100",
                    "columnInfo": [
                        {"columnIndex": 0, "originalColumn": "domain", "columnType": "STRING", "keyColumn": True},
                    ],
                    "rules": [],
                    "ruleAssociationsCount": 0,
                    "createTime": "2026-01-01T00:00:00Z",
                    "updateTime": "2026-01-01T00:00:00Z",
                }
            ]
        }
        self.mock_adapter.list_rules.return_value = {
            "rules": [
                {
                    "name": "projects/123/locations/us/instances/abc/rules/r_123",
                    "displayName": "DNS Bad Domain Query",
                    "ruleText": "rule dns_bad_domain {\n events:\n  $e.target.hostname in %bad_domains%\n condition:\n  $e\n}",
                }
            ]
        }

        report = self.workflow.execute(lookback_days=14, stale_days=1000, correlate_rules=True)

        self.assertEqual(report.total_tables_audited, 1)
        finding = report.findings[0]
        self.assertEqual(finding.rule_associations_count, 1)
        self.assertIn("DNS Bad Domain Query", finding.associated_rules)


if __name__ == "__main__":
    unittest.main()
