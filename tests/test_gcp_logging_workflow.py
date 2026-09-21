"""Unit and contract tests for GCP Cloud Logging query workflow."""

import unittest

from engine.domain import GcpLogEntry, GcpLogQueryResult
from engine.facade import SecOpsEngine
from engine.registry import WorkflowRegistry
from engine.workflows.gcp_logging_query import (
    GcpLoggingQueryWorkflow,
    _normalize_log_entry,
)
from tests.test_helpers import get_live_engine


class _RecordingLoggingAdapter:
    """Inert adapter that captures parameters passed to query_cloud_logging without network calls."""

    def __init__(self, project_id: str = "test-project-alpha"):
        self.project_id = project_id
        self.last_query = {}

    def query_cloud_logging(
        self,
        filter_str: str,
        project_ids=None,
        page_size=50,
        page_token=None,
        order_by="timestamp desc",
    ):
        self.last_query = {
            "filter_str": filter_str,
            "project_ids": project_ids,
            "page_size": page_size,
            "page_token": page_token,
            "order_by": order_by,
        }
        return {
            "entries": [
                {
                    "logName": "projects/test-project-alpha/logs/cloudaudit.googleapis.com%2Factivity",
                    "resource": {"type": "audited_resource", "labels": {"project_id": "test-project-alpha"}},
                    "timestamp": "2026-09-19T12:00:00Z",
                    "severity": "NOTICE",
                    "insertId": "ins-98765",
                    "protoPayload": {"authenticationInfo": {"principalEmail": "secops-admin@example.com"}},
                }
            ],
            "nextPageToken": "token-next-page-123",
        }


class GcpLoggingWorkflowUnitTest(unittest.TestCase):
    def setUp(self):
        self.adapter = _RecordingLoggingAdapter()
        self.workflow = GcpLoggingQueryWorkflow(self.adapter)

    def test_normalize_log_entry(self):
        raw = {
            "logName": "projects/p/logs/audit",
            "resource": {"type": "gce_instance", "labels": {"zone": "us-central1-a"}},
            "timestamp": "2026-09-19T10:00:00Z",
            "severity": "ERROR",
            "insertId": "ins-1",
            "textPayload": "connection failed",
        }
        entry = _normalize_log_entry(raw)
        self.assertIsInstance(entry, GcpLogEntry)
        self.assertEqual(entry.log_name, "projects/p/logs/audit")
        self.assertEqual(entry.resource_type, "gce_instance")
        self.assertEqual(entry.severity, "ERROR")
        self.assertEqual(entry.text_payload, "connection failed")

    def test_execute_requires_filter(self):
        with self.assertRaises(ValueError):
            self.workflow.execute(filter_str="")

    def test_execute_records_parameters_and_normalizes(self):
        result = self.workflow.execute(
            filter_str='severity >= ERROR',
            page_size=25,
            page_token="tok-1",
        )
        self.assertIsInstance(result, GcpLogQueryResult)
        self.assertEqual(len(result.entries), 1)
        self.assertEqual(result.entries[0].insert_id, "ins-98765")
        self.assertEqual(result.next_page_token, "token-next-page-123")
        self.assertEqual(self.adapter.last_query["filter_str"], "severity >= ERROR")
        self.assertEqual(self.adapter.last_query["page_size"], 25)

    def test_query_secops_audit_logs_human_filter(self):
        self.workflow.query_secops_audit_logs(hours=12, human_only=True)
        query = self.adapter.last_query["filter_str"]
        self.assertIn("cloudaudit.googleapis.com", query)
        self.assertIn("!~ \"gserviceaccount.com\"", query)

    def test_facade_integration_and_capability_dispatch(self):
        engine = SecOpsEngine(adapter=self.adapter, custom_registry=WorkflowRegistry())
        cap = engine.registry.get("gcp_logging.search")
        self.assertIsNotNone(cap)
        self.assertEqual(cap.domain, "gcp_logging")
        self.assertEqual(cap.kind, "query")
        self.assertEqual(cap.cardinality, "bounded")

        # Execute via engine facade
        result = engine.query_cloud_logging(filter_str="severity >= WARNING")
        self.assertEqual(len(result.entries), 1)


class GcpLoggingLiveIntegrationTest(unittest.TestCase):
    def test_live_logging_query(self):
        """Optional live test against real tenant project, skips gracefully if unconfigured."""
        engine = get_live_engine()
        # Query for audit logs in the last 2 hours
        try:
            res = engine.query_cloud_logging(
                filter_str='logName =~ "cloudaudit.googleapis.com" OR severity >= ERROR',
                page_size=5,
            )
            self.assertIsInstance(res, GcpLogQueryResult)
        except Exception as e:
            # If tenant permissions don't include logging.viewer, skip
            if "PERMISSION_DENIED" in str(e) or "403" in str(e):
                raise unittest.SkipTest(f"Cloud Logging permissions not granted: {e}")
            raise


if __name__ == "__main__":
    unittest.main()
