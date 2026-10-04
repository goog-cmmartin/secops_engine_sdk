"""Unit and behavioral tests for Timestamp Integrity Workflow and Agent."""

from datetime import datetime, timezone
import json
import tempfile
import unittest
from pathlib import Path
from typing import Any, Dict, List, Optional
from unittest.mock import MagicMock

from engine.domain import (
    TimestampProgressionState,
    TimestampMetricRow,
    TimestampIntegrityReport,
)
from engine.workflows.timestamp_integrity import (
    TimestampIntegrityWorkflow,
    TIMESTAMP_INTEGRITY_QUERY,
)
from agents.core.evidence_store import LocalFileEvidenceStore
from agents.generated.timestamp_integrity import TimestampIntegrityAgent


class _StubDashboardResult:
    def __init__(self, rows: List[Dict[str, Any]]):
        self.rows = rows
        self.total_rows = len(rows)
        self.columns = [
            "$log_type",
            "$total",
            "$average_difference_minutes",
            "$cnt_lt_0_hours",
            "$cnt_0_1_hours",
            "$cnt_1_2_hours",
            "$cnt_gt_2_hours",
        ]


class _StubDashboardAdapter:
    def __init__(self, rows: Optional[List[Dict[str, Any]]] = None):
        self.last_query_text: Optional[str] = None
        self.last_time_unit: Optional[str] = None
        self.last_time_value: Optional[str] = None
        self.last_clear_cache: Optional[bool] = None
        self.rows = rows or []

    def execute_dashboard_query(
        self,
        query_text: str,
        time_unit: str = "DAY",
        time_value: str = "7",
        clear_cache: bool = True,
        dialect: str = "YL2",
    ) -> _StubDashboardResult:
        self.last_query_text = query_text
        self.last_time_unit = time_unit
        self.last_time_value = time_value
        self.last_clear_cache = clear_cache
        return _StubDashboardResult(self.rows)


class TestTimestampProgressionLogic(unittest.TestCase):
    """Verifies 4-state progression logic across healthy, delayed, and clock-skewed streams."""

    def test_state_transitions(self):
        # 1. Healthy stream without prior issue -> HEALTHY
        state_win = TimestampIntegrityWorkflow.classify_progression(
            is_anomaly=False,
            had_issue=False,
        )
        self.assertEqual(state_win, TimestampProgressionState.HEALTHY)

        # 2. Previously problematic stream becomes healthy -> RESOLVED
        state_nginx = TimestampIntegrityWorkflow.classify_progression(
            is_anomaly=False,
            had_issue=True,
        )
        self.assertEqual(state_nginx, TimestampProgressionState.RESOLVED)

        # 3. Stream remains an anomaly -> PREVIOUSLY KNOWN
        state_okta = TimestampIntegrityWorkflow.classify_progression(
            is_anomaly=True,
            had_issue=True,
        )
        self.assertEqual(state_okta, TimestampProgressionState.PREVIOUSLY_KNOWN)

        # 4. Stream newly surfaces as an anomaly -> NEW
        state_cs = TimestampIntegrityWorkflow.classify_progression(
            is_anomaly=True,
            had_issue=False,
        )
        self.assertEqual(state_cs, TimestampProgressionState.NEW)


class TestEvidenceFabricTimestampPersistence(unittest.TestCase):
    """Verifies dual-document persistence in Evidence Fabric."""

    def test_dual_document_lifecycle(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            store = LocalFileEvidenceStore(root_dir=Path(tmpdir))

            # Initial check: no baseline
            self.assertIsNone(store.get_latest_timestamp_integrity())
            self.assertEqual(len(store.list_timestamp_integrity_history()), 0)

            # First save
            row1 = TimestampMetricRow(
                log_type="WINEVTLOG",
                total=50000,
                average_difference_minutes=12.5,
                cnt_lt_0_hours=0,
                cnt_0_1_hours=48000,
                cnt_1_2_hours=2000,
                cnt_gt_2_hours=0,
                progression_state=TimestampProgressionState.HEALTHY,
            )
            report1 = TimestampIntegrityReport(
                timestamp=datetime.now(timezone.utc).isoformat(),
                days=7,
                total_log_types_audited=1,
                healthy_count=1,
                new_anomalies_count=0,
                previously_known_count=0,
                resolved_count=0,
                total_skewed_events=0,
                total_delayed_events=0,
                log_types=[row1],
                top_delayed_log_types=[],
                top_skewed_log_types=[],
                comparative_findings={"WINEVTLOG": "HEALTHY"},
                narrative="Baseline nominal.",
            )

            snap_id1 = store.save_timestamp_integrity_report(report1)
            self.assertTrue(snap_id1.startswith("snap_"))

            # Check latest document
            latest = store.get_latest_timestamp_integrity()
            self.assertIsNotNone(latest)
            self.assertEqual(latest["comparative_findings"]["WINEVTLOG"], "HEALTHY")
            self.assertEqual(latest["metrics"]["WINEVTLOG"]["total"], 50000)

            # Second save with anomaly
            row2 = TimestampMetricRow(
                log_type="WINEVTLOG",
                total=52000,
                average_difference_minutes=125.0,  # Delayed!
                cnt_lt_0_hours=5,                  # Clock skew!
                cnt_0_1_hours=10000,
                cnt_1_2_hours=20000,
                cnt_gt_2_hours=22000,
                progression_state=TimestampProgressionState.NEW,
            )
            report2 = TimestampIntegrityReport(
                timestamp=datetime.now(timezone.utc).isoformat(),
                days=7,
                total_log_types_audited=1,
                healthy_count=0,
                new_anomalies_count=1,
                previously_known_count=0,
                resolved_count=0,
                total_skewed_events=5,
                total_delayed_events=22000,
                log_types=[row2],
                top_delayed_log_types=[row2],
                top_skewed_log_types=[row2],
                comparative_findings={"WINEVTLOG": "NEW"},
                narrative="Degradation detected.",
            )
            snap_id2 = store.save_timestamp_integrity_report(report2)
            self.assertNotEqual(snap_id1, snap_id2)

            # Latest is updated
            latest2 = store.get_latest_timestamp_integrity()
            self.assertEqual(latest2["comparative_findings"]["WINEVTLOG"], "NEW")
            self.assertEqual(latest2["metrics"]["WINEVTLOG"]["cnt_lt_0_hours"], 5)

            # History contains both
            history = store.list_timestamp_integrity_history()
            self.assertEqual(len(history), 2)
            self.assertEqual(history[0]["snapshot_id"], snap_id2)
            self.assertEqual(history[1]["snapshot_id"], snap_id1)


class TestTimestampIntegrityWorkflowExecution(unittest.TestCase):
    """Verifies end-to-end execution of TimestampIntegrityWorkflow."""

    def test_workflow_execution_with_query_and_advisory(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            store = LocalFileEvidenceStore(root_dir=Path(tmpdir))

            rows = [
                {
                    "$log_type": "WINEVTLOG",
                    "$total": 100000,
                    "$average_difference_minutes": 14.2,
                    "$cnt_lt_0_hours": 0,
                    "$cnt_0_1_hours": 99000,
                    "$cnt_1_2_hours": 1000,
                    "$cnt_gt_2_hours": 0,
                },
                {
                    "$log_type": "SYSLOG",
                    "$total": 50000,
                    "$average_difference_minutes": 185.0,  # >2h delay bottleneck
                    "$cnt_lt_0_hours": 0,
                    "$cnt_0_1_hours": 5000,
                    "$cnt_1_2_hours": 10000,
                    "$cnt_gt_2_hours": 35000,
                },
                {
                    "$log_type": "PAN_FIREWALL",
                    "$total": 75000,
                    "$average_difference_minutes": 8.0,
                    "$cnt_lt_0_hours": 42,  # Clock skew / NTP drift
                    "$cnt_0_1_hours": 74500,
                    "$cnt_1_2_hours": 458,
                    "$cnt_gt_2_hours": 0,
                },
            ]

            adapter = _StubDashboardAdapter(rows=rows)
            workflow = TimestampIntegrityWorkflow(adapter=adapter, evidence_store=store)

            report = workflow.run(days=7, clear_cache=True)

            # Verify query and execution arguments
            self.assertEqual(adapter.last_time_unit, "DAY")
            self.assertEqual(adapter.last_time_value, "7")
            self.assertTrue(adapter.last_clear_cache)
            self.assertIn("metadata.ingested_timestamp.seconds - metadata.event_timestamp.seconds", adapter.last_query_text)

            # Verify metrics & progression
            self.assertEqual(report.total_log_types_audited, 3)
            self.assertEqual(report.healthy_count, 1)  # WINEVTLOG
            self.assertEqual(report.new_anomalies_count, 2)  # SYSLOG (delay) & PAN_FIREWALL (clock skew)
            self.assertEqual(report.total_skewed_events, 42)
            self.assertEqual(report.total_delayed_events, 35000)

            # Top skewed and top delayed lists
            self.assertEqual(len(report.top_skewed_log_types), 1)
            self.assertEqual(report.top_skewed_log_types[0].log_type, "PAN_FIREWALL")
            self.assertEqual(report.top_skewed_log_types[0].cnt_lt_0_hours, 42)

            self.assertEqual(len(report.top_delayed_log_types), 1)
            self.assertEqual(report.top_delayed_log_types[0].log_type, "SYSLOG")
            self.assertEqual(report.top_delayed_log_types[0].cnt_gt_2_hours, 35000)

            # Verify narrative contains operational advice for clock skew and delays
            self.assertIn("PAN_FIREWALL", report.narrative)
            self.assertIn("NTP", report.narrative)
            self.assertIn("SYSLOG", report.narrative)

            # Verify saved to evidence store
            latest = store.get_latest_timestamp_integrity()
            self.assertIsNotNone(latest)
            self.assertEqual(latest["comparative_findings"]["PAN_FIREWALL"], "NEW")
            self.assertEqual(latest["comparative_findings"]["SYSLOG"], "NEW")
            self.assertEqual(latest["comparative_findings"]["WINEVTLOG"], "HEALTHY")


class TestTimestampIntegrityAgent(unittest.IsolatedAsyncioTestCase):
    """Verifies ADK 2 Agent tool bindings and interactive chat dispatch."""

    async def test_agent_tools_and_chat(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            store = LocalFileEvidenceStore(root_dir=Path(tmpdir))

            rows = [
                {
                    "$log_type": "OKTA",
                    "$total": 25000,
                    "$average_difference_minutes": 2.1,
                    "$cnt_lt_0_hours": 0,
                    "$cnt_0_1_hours": 25000,
                    "$cnt_1_2_hours": 0,
                    "$cnt_gt_2_hours": 0,
                }
            ]
            from engine.facade import SecOpsEngine
            from agents.core.base_adk_agent import AgentMessage

            adapter = _StubDashboardAdapter(rows=rows)
            engine = SecOpsEngine(adapter=adapter, evidence_store=store)
            agent = TimestampIntegrityAgent(
                engine=engine,
                evidence_store=store,
            )

            # Check tools
            tools = agent.get_tools()
            tool_names = [getattr(t, "__name__", str(t)) for t in tools]
            self.assertIn("audit_timestamp_integrity", tool_names)
            self.assertIn("get_timestamp_integrity_report", tool_names)
            self.assertIn("list_timestamp_integrity_history", tool_names)

            # Direct tool call
            res = agent.audit_timestamp_integrity(days=7)
            self.assertEqual(res["status"], "SUCCESS")
            self.assertEqual(res["summary"]["healthy_count"], 1)
            self.assertIn("widget", res)
            self.assertEqual(res["widget"]["type"], "timestamp_integrity_card")
            self.assertIsNotNone(agent.last_widget)

            # Check baseline fetch
            baseline = agent.get_timestamp_integrity_report()
            self.assertEqual(baseline["status"], "SUCCESS")
            self.assertEqual(baseline["report"]["comparative_findings"]["OKTA"], "HEALTHY")

            # Check history list
            hist = agent.list_timestamp_integrity_history()
            self.assertEqual(hist["status"], "SUCCESS")
            self.assertEqual(hist["count"], 1)

            # Interactive chat verification
            with unittest.mock.patch.object(
                agent,
                "chat",
                return_value=AgentMessage(
                    id="msg_test",
                    stream="telemetry",
                    topic="timestamp-integrity",
                    sender_handle="@timestamp-integrity-agent",
                    content="Timestamp Integrity audit completed successfully.",
                    widget=agent.last_widget,
                ),
            ):
                chat_reply = await agent.chat("Audit telemetry timestamps for any clock skew or ingestion delays")
                self.assertIsNotNone(chat_reply)
                self.assertIsNotNone(chat_reply.widget)
                self.assertEqual(chat_reply.widget["type"], "timestamp_integrity_card")
                self.assertIn("Timestamp Integrity", chat_reply.content)


if __name__ == "__main__":
    unittest.main()
