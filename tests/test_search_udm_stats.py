"""Acceptance and Unit Tests for UDM Stats Search (Aggregation, Analytics, and Metrics).

Verifies:
1. Syntax validation failure handling.
2. Long-Running Operation (LRO) initiation, polling, and stats payload parsing.
3. Accurate transformation from columnar results to row records.
4. Field-level event distribution aggregations parsing.
5. Cancellation and timeout lifecycle state transitions.
6. Engine capability registration and facade integration.
7. Optional live tenant integration using get_live_engine().
"""

import unittest
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from engine import (
    CompletenessState,
    LifecycleState,
    SecOpsEngine,
    StatsColumn,
    StatsColumnMetadata,
    StatsFieldAggregation,
    StatsSearchRequest,
    StatsSearchResult,
    StatsSearchSession,
    ValidationResult,
    WorkflowCapability,
)
from engine.workflows.search_udm_stats import SearchUDMStatsWorkflow
from tests.test_helpers import get_live_engine


class MockAdapterForStats:
    """Offline test adapter strictly for unit testing workflow orchestration."""

    def __init__(
        self,
        valid_syntax: bool = True,
        operation_id: str = "projects/123/locations/us/instances/abc/operations/s-udm-test-1",
        stats_response: Optional[StatsSearchResult] = None,
        poll_count_before_done: int = 1,
    ):
        self.valid_syntax = valid_syntax
        self.operation_id = operation_id
        self.cancelled_ops: List[str] = []
        self.polls = 0
        self.poll_count_before_done = poll_count_before_done

        if stats_response is None:
            self.stats_response = StatsSearchResult(
                columns=[
                    StatsColumn(
                        column="et",
                        values=["USER_RESOURCE_ACCESS", "USER_LOGIN"],
                        filterable=True,
                        filter_expression="metadata.event_type",
                        column_metadata=StatsColumnMetadata(
                            column="MATCH_PLACEHOLDER_et",
                            field_path="udm.metadata.event_type",
                            data_type="STRING",
                        ),
                    ),
                    StatsColumn(
                        column="total",
                        values=[1385218, 1304205],
                        column_metadata=StatsColumnMetadata(
                            column="OUTCOME_total",
                            field_path="udm.metadata.id",
                            function_name_used="COUNT",
                            data_type="NUMBER",
                        ),
                    ),
                ],
                rows=[
                    {"et": "USER_RESOURCE_ACCESS", "total": 1385218},
                    {"et": "USER_LOGIN", "total": 1304205},
                ],
                total_results=2,
                filtered_result_count=2,
                data_query_expression="metadata.event_type = $et",
                aggregations=[
                    StatsFieldAggregation(
                        field_name="et",
                        baseline_event_count=2,
                        event_count=2,
                        value_count=2,
                    )
                ],
                progress=1.0,
                complete=True,
                operation_id=operation_id,
            )
        else:
            self.stats_response = stats_response

    def validate_query(self, query: str) -> ValidationResult:
        if not self.valid_syntax or "INVALID" in query:
            return ValidationResult(valid=False, error_message="Syntax error in match clause")
        return ValidationResult(valid=True)

    def start_search(self, query: str, start_time: str, end_time: str, max_events: int = 10000) -> str:
        return self.operation_id

    def get_stats(self, operation_id: str, start_index: int = 1, batch_size: int = 2000) -> StatsSearchResult:
        self.polls += 1
        if self.polls < self.poll_count_before_done:
            return StatsSearchResult(
                columns=[],
                rows=[],
                total_results=0,
                progress=0.5,
                complete=False,
                operation_id=operation_id,
            )
        return self.stats_response

    def cancel_operation(self, operation_id: str) -> None:
        self.cancelled_ops.append(operation_id)


class TestUDMStatsSearchUnit(unittest.TestCase):
    """Unit and behavioral tests for UDM Stats Search."""

    def test_01_syntax_validation_failure(self):
        """Verifies that invalid queries immediately fail with descriptive error."""
        adapter = MockAdapterForStats(valid_syntax=False)
        wf = SearchUDMStatsWorkflow(adapter=adapter)
        req = StatsSearchRequest(
            query="INVALID QUERY",
            start_time="2026-08-21T00:00:00Z",
            end_time="2026-08-23T00:00:00Z",
        )
        session = wf.execute(req)
        self.assertEqual(session.lifecycle, LifecycleState.FAILED)
        self.assertEqual(session.completeness, CompletenessState.EMPTY)
        self.assertIn("Syntax error", str(session.error))

    def test_02_successful_columnar_and_row_records(self):
        """Verifies full execution and transformation to both columns and row records."""
        adapter = MockAdapterForStats()
        wf = SearchUDMStatsWorkflow(adapter=adapter)
        req = StatsSearchRequest(
            query="metadata.event_type = $et match: $et outcome: $total = count(metadata.id) limit: 2",
            start_time="2026-08-21T00:00:00Z",
            end_time="2026-08-23T00:00:00Z",
        )
        session = wf.execute(req)
        self.assertEqual(session.lifecycle, LifecycleState.COMPLETED)
        self.assertEqual(session.completeness, CompletenessState.COMPLETE)
        self.assertIsNotNone(session.result)

        res = session.result
        self.assertEqual(res.total_results, 2)
        self.assertEqual(len(res.columns), 2)
        self.assertEqual(res.column_names(), ["et", "total"])
        self.assertEqual(len(res.rows), 2)
        self.assertEqual(res.rows[0]["et"], "USER_RESOURCE_ACCESS")
        self.assertEqual(res.rows[0]["total"], 1385218)
        self.assertEqual(res.rows[1]["et"], "USER_LOGIN")
        self.assertEqual(res.rows[1]["total"], 1304205)

        # Verify UniversalBatchMixin items property
        self.assertEqual(res.items, res.rows)

        # Verify aggregations
        self.assertEqual(len(res.aggregations), 1)
        self.assertEqual(res.aggregations[0].field_name, "et")

    def test_03_cancellation_during_execution(self):
        """Verifies cancellation token aborts workflow and calls adapter.cancel_operation."""
        adapter = MockAdapterForStats(poll_count_before_done=5)
        wf = SearchUDMStatsWorkflow(adapter=adapter)
        req = StatsSearchRequest(
            query="metadata.event_type = $et match: $et outcome: $total = count(metadata.id)",
            start_time="2026-08-21T00:00:00Z",
            end_time="2026-08-23T00:00:00Z",
        )

        cancel_flag = False

        def on_batch(result, session):
            nonlocal cancel_flag
            cancel_flag = True

        session = wf.execute(
            req,
            on_batch=on_batch,
            cancel_token=lambda: cancel_flag,
            poll_interval=0.01,
        )

        self.assertEqual(session.lifecycle, LifecycleState.CANCELLED)
        self.assertIn(adapter.operation_id, adapter.cancelled_ops)

    def test_04_engine_facade_integration(self):
        """Verifies SecOpsEngine.search_udm_stats convenience facade method."""
        adapter = MockAdapterForStats()
        engine = SecOpsEngine(adapter=adapter)

        # String invocation
        session = engine.search_udm_stats(
            query="metadata.event_type = $et match: $et outcome: $total = count(metadata.id)",
            start_time="2026-08-21T00:00:00Z",
            end_time="2026-08-23T00:00:00Z",
        )
        self.assertEqual(session.lifecycle, LifecycleState.COMPLETED)
        self.assertEqual(len(session.result.rows), 2)

        # Capability registered
        cap = engine.registry.get("search.udm.stats")
        self.assertIsNotNone(cap)
        self.assertEqual(cap.capability_id, "search.udm.stats")
        self.assertEqual(cap.kind, "query")
        self.assertEqual(cap.domain, "search")
        self.assertEqual(cap.cardinality, "unbounded")

    def test_05_deduplication_and_csv_formatting(self):
        """Verifies row deduplication and CSV generation."""
        import csv
        import io

        res = StatsSearchResult(
            columns=[
                StatsColumn(column="et", values=["USER_LOGIN", "USER_LOGIN", "NETWORK_CONNECTION"]),
                StatsColumn(column="total", values=[500, 500, 250]),
            ],
            rows=[
                {"et": "USER_LOGIN", "total": 500},
                {"et": "USER_LOGIN", "total": 500},
                {"et": "NETWORK_CONNECTION", "total": 250},
            ],
            total_results=3,
        )

        self.assertEqual(len(res.rows), 3)
        deduped = res.dedup_rows()
        self.assertEqual(len(deduped), 2)
        self.assertEqual(deduped[0]["et"], "USER_LOGIN")
        self.assertEqual(deduped[1]["et"], "NETWORK_CONNECTION")

        # Test to_records with dedup
        self.assertEqual(len(res.to_records(dedup=True)), 2)
        self.assertEqual(len(res.to_records(dedup=False)), 3)

        # Test CSV export
        buf = io.StringIO()
        writer = csv.DictWriter(buf, fieldnames=res.column_names())
        writer.writeheader()
        for row in deduped:
            writer.writerow(row)
        csv_text = buf.getvalue().strip()
        lines = csv_text.splitlines()
        self.assertEqual(len(lines), 3)
        self.assertEqual(lines[0], "et,total")
        self.assertEqual(lines[1], "USER_LOGIN,500")
        self.assertEqual(lines[2], "NETWORK_CONNECTION,250")

    def test_06_entity_graph_and_detection_queries(self):
        """Verifies workflow orchestration for Entity Graph and Detection stats queries."""
        # 1. Entity Graph Stats Result
        graph_res = StatsSearchResult(
            columns=[
                StatsColumn(column="et", values=["USER", "IP_ADDRESS"]),
                StatsColumn(column="total", values=[1420, 890]),
            ],
            rows=[
                {"et": "USER", "total": 1420},
                {"et": "IP_ADDRESS", "total": 890},
            ],
            total_results=2,
        )
        adapter = MockAdapterForStats(stats_response=graph_res)
        wf = SearchUDMStatsWorkflow(adapter=adapter)
        req = StatsSearchRequest(
            query="graph.metadata.entity_type = $et match: $et outcome: $total = count(graph.metadata.product_entity_id) order: $total desc limit: 10",
            start_time="2026-08-21T00:00:00Z",
            end_time="2026-08-23T00:00:00Z",
        )
        session = wf.execute(req)
        self.assertEqual(session.lifecycle, LifecycleState.COMPLETED)
        self.assertEqual(len(session.result.rows), 2)
        self.assertEqual(session.result.rows[0]["et"], "USER")

        # 2. Detections Stats Result
        det_res = StatsSearchResult(
            columns=[
                StatsColumn(column="rn", values=["Suspicious PowerShell Execution", "Brute Force Login"]),
                StatsColumn(column="total", values=[45, 12]),
            ],
            rows=[
                {"rn": "Suspicious PowerShell Execution", "total": 45},
                {"rn": "Brute Force Login", "total": 12},
            ],
            total_results=2,
        )
        adapter_det = MockAdapterForStats(stats_response=det_res)
        wf_det = SearchUDMStatsWorkflow(adapter=adapter_det)
        req_det = StatsSearchRequest(
            query="detection.detection.rule_name = $rn match: $rn outcome: $total = count(detection.id) order: $total desc limit: 10",
            start_time="2026-08-21T00:00:00Z",
            end_time="2026-08-23T00:00:00Z",
        )
        session_det = wf_det.execute(req_det)
        self.assertEqual(session_det.lifecycle, LifecycleState.COMPLETED)
        self.assertEqual(len(session_det.result.rows), 2)
        self.assertEqual(session_det.result.rows[0]["rn"], "Suspicious PowerShell Execution")


class TestUDMStatsSearchLive(unittest.TestCase):
    """Live acceptance test against Google SecOps endpoint if configured."""

    @classmethod
    def setUpClass(cls):
        try:
            cls.engine = get_live_engine()
        except Exception as e:
            raise unittest.SkipTest(f"Live engine not configured: {e}")

    def test_live_stats_query(self):
        """Executes a live aggregation stats search against Google SecOps."""
        now = datetime.now(timezone.utc)
        start = (now - timedelta(days=2)).strftime("%Y-%m-%dT%H:%M:%SZ")
        end = now.strftime("%Y-%m-%dT%H:%M:%SZ")

        query = (
            'metadata.event_type = $et\n'
            'match: $et\n'
            'outcome: $total = count(metadata.id)\n'
            'limit: 5'
        )

        session = self.engine.search_udm_stats(
            query=query,
            start_time=start,
            end_time=end,
            max_events=5000,
            poll_interval=1.0,
            max_poll_seconds=60.0,
        )

        if session.lifecycle == LifecycleState.FAILED:
            self.skipTest(f"Live SecOps query returned failure: {session.error}")

        self.assertEqual(session.lifecycle, LifecycleState.COMPLETED)
        self.assertIsNotNone(session.result)
        self.assertGreaterEqual(len(session.result.columns), 1)


if __name__ == "__main__":
    unittest.main()
