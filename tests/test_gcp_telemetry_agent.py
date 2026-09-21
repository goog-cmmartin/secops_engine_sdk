"""Unit and behavioral tests for GcpTelemetryAgent (@gcp-telemetry-agent)."""

from datetime import datetime, timezone
import os
from pathlib import Path
import tempfile
import unittest
from typing import Any, Dict, List, Optional

from agents.core.evidence_store import LocalFileEvidenceStore
from agents.core.proposal_manager import ProposalManager
from agents.generated.gcp_telemetry import GcpTelemetryAgent
from engine.facade import SecOpsEngine
from engine.registry import WorkflowRegistry
from engine.domain import (
    GcpLogEntry,
    GcpLogQueryResult,
    GcpMonitoringQueryResult,
    MetricPoint,
    TimeSeriesData,
)


class _RecordingTelemetryAdapter:
    """Live-protocol compliant recording adapter for GCP telemetry testing."""

    def __init__(self):
        self.monitoring_calls: List[Dict[str, Any]] = []
        self.logging_calls: List[Dict[str, Any]] = []

    def query_cloud_monitoring_time_series(
        self,
        filter_str: str,
        start_time: str,
        end_time: str,
        project_id: Optional[str] = None,
        alignment_period: Optional[str] = "3600s",
        per_series_aligner: Optional[str] = "ALIGN_SUM",
        cross_series_reducer: Optional[str] = None,
        group_by_fields: Optional[List[str]] = None,
        page_size: Optional[int] = 50,
        page_token: Optional[str] = None,
    ) -> Dict[str, Any]:
        self.monitoring_calls.append({
            "filter_str": filter_str,
            "start_time": start_time,
            "end_time": end_time,
            "alignment_period": alignment_period,
            "per_series_aligner": per_series_aligner,
            "cross_series_reducer": cross_series_reducer,
            "group_by_fields": group_by_fields,
            "page_size": page_size,
        })
        return {
            "timeSeries": [
                {
                    "metric": {
                        "type": "chronicle.googleapis.com/collector/ingestion/total_ingested_log_count",
                        "labels": {"log_type": "WINEVTLOG", "customer_id": "test-cust"},
                    },
                    "resource": {
                        "type": "chronicle.googleapis.com/Collector",
                        "labels": {"project_id": "secops-test-prod"},
                    },
                    "metricKind": "DELTA",
                    "valueType": "INT64",
                    "points": [
                        {
                            "interval": {
                                "startTime": start_time,
                                "endTime": end_time,
                            },
                            "value": {"int64Value": "8450"},
                        }
                    ],
                }
            ],
            "nextPageToken": None,
        }

    def query_cloud_logging(
        self,
        filter_str: str,
        project_ids: Optional[List[str]] = None,
        page_size: Optional[int] = 50,
        page_token: Optional[str] = None,
        order_by: Optional[str] = "timestamp desc",
    ) -> Dict[str, Any]:
        self.logging_calls.append({
            "filter_str": filter_str,
            "project_ids": project_ids,
            "order_by": order_by,
            "page_size": page_size,
        })
        return {
            "entries": [
                {
                    "logName": "projects/secops-test-prod/logs/cloudaudit.googleapis.com%2Factivity",
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "severity": "WARNING",
                    "resource": {
                        "type": "chronicle.googleapis.com/Instance",
                        "labels": {"project_id": "secops-test-prod"},
                    },
                    "protoPayload": {
                        "authenticationInfo": {"principalEmail": "secops-admin@altostrat.com"},
                        "methodName": "google.cloud.chronicle.v1alpha.RuleService.UpdateRule",
                    },
                    "textPayload": "Rule update operation took longer than standard SLA",
                }
            ],
            "nextPageToken": None,
        }


class TestGcpTelemetryAgent(unittest.TestCase):
    """Verifies GCP Telemetry Agent manifest metadata, tool bindings, telemetry diagnostics, and CI invariants."""

    def setUp(self):
        self._tmpdir = tempfile.TemporaryDirectory()
        self.root_dir = Path(self._tmpdir.name)
        self.evidence_store = LocalFileEvidenceStore(root_dir=self.root_dir)
        self.proposal_manager = ProposalManager(root_dir=self.root_dir)

        self.adapter = _RecordingTelemetryAdapter()
        self.engine = SecOpsEngine(adapter=self.adapter)

        self.agent = GcpTelemetryAgent(
            engine=self.engine,
            proposal_manager=self.proposal_manager,
            evidence_store=self.evidence_store,
        )

    def tearDown(self):
        self._tmpdir.cleanup()

    def test_agent_manifest_bindings(self):
        """Verifies ADK 2 agent manifest metadata, streams, topics, and capability bindings."""
        self.assertEqual(self.agent.name, "GCP Telemetry Agent")
        self.assertEqual(self.agent.handle, "@gcp-telemetry-agent")
        self.assertEqual(self.agent.default_stream, "telemetry")
        self.assertEqual(self.agent.default_topic, "logs-and-metrics")
        self.assertIn("gcp_logging.search", self.agent.CAPABILITIES)
        self.assertIn("gcp_monitoring.time_series", self.agent.CAPABILITIES)

        # Verify custom tools bound
        tools = self.agent.get_tools()
        tool_names = [getattr(t, "__name__", str(t)) for t in tools]
        self.assertIn("audit_chronicle_telemetry", tool_names)
        self.assertIn("query_metrics", tool_names)
        self.assertIn("search_audit_logs", tool_names)

    def test_audit_chronicle_telemetry_flow(self):
        """Verifies cross-correlation of Cloud Monitoring metrics and Cloud Logging error events."""
        res = self.agent.audit_chronicle_telemetry(hours=12, log_type="WINEVTLOG")

        self.assertEqual(res["status"], "SUCCESS")
        summary = res["summary"]
        self.assertEqual(summary["hours"], 12)
        self.assertEqual(summary["log_type"], "WINEVTLOG")
        self.assertGreaterEqual(summary["ingestion_streams_count"], 1)
        self.assertGreaterEqual(summary["error_logs_count"], 1)

        # Verify telemetry health card widget
        widget = res.get("widget")
        self.assertIsNotNone(widget)
        self.assertEqual(widget["type"], "gcp_telemetry_card")
        self.assertEqual(widget["summary"]["hours"], 12)
        self.assertEqual(len(widget["recent_errors"]), 1)
        self.assertEqual(widget["recent_errors"][0]["severity"], "WARNING")

        # Verify executed tool calls logged for provenance
        calls = [c for c in self.agent.executed_tool_calls if c["tool"] == "audit_chronicle_telemetry"]
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0]["capability_id"], "gcp_monitoring.time_series")

    def test_query_metrics_tool(self):
        """Verifies direct invocation of query_metrics."""
        res = self.agent.query_metrics(
            filter_str='metric.type = "chronicle.googleapis.com/collector/ingestion/total_ingested_log_count"',
            hours=6,
        )
        self.assertEqual(res["status"], "SUCCESS")
        self.assertEqual(res["total_series"], 1)
        self.assertEqual(len(res["time_series"]), 1)
        self.assertEqual(res["time_series"][0]["points"][0]["value"], 8450)

    def test_search_audit_logs_tool(self):
        """Verifies direct invocation of search_audit_logs."""
        res = self.agent.search_audit_logs(hours=6, human_only=False)
        self.assertEqual(res["status"], "SUCCESS")
        self.assertEqual(res["total_entries"], 1)
        self.assertEqual(res["entries"][0]["severity"], "WARNING")
        self.assertEqual(res["entries"][0]["principal"], "secops-admin@altostrat.com")

    def test_no_mock_data_audit(self):
        """CI Invariant: Ensure zero banned mock/synthetic terms in agent production code."""
        repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        banned_terms = ["mock", "fixture", "dummy", "fake", "sample_data", "test_data"]

        prod_files = [
            os.path.join(repo_root, "agents", "generated", "gcp_telemetry.py"),
            os.path.join(repo_root, "agents", "manifests", "gcp_telemetry.yaml"),
        ]

        for path in prod_files:
            if not os.path.exists(path):
                continue
            with open(path, "r", encoding="utf-8") as f:
                content = f.read()
                lines = content.split("\n")
                for line_num, line in enumerate(lines, 1):
                    lower_line = line.lower()
                    for term in banned_terms:
                        if term in lower_line:
                            tokens = [t.strip("\"'()[]{},: ") for t in lower_line.split()]
                            self.assertNotIn(
                                term,
                                tokens,
                                f"Banned identifier '{term}' found in {path}:{line_num}",
                            )


if __name__ == "__main__":
    unittest.main()
