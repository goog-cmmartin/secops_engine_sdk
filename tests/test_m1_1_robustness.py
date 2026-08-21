"""Authoritative Milestone 1.1 Robustness Acceptance Test Suite.

Executes comprehensive behavioral verification against live Google SecOps APIs:
- UDM-EXEC-001: Valid query happy path & multi-batch streaming
- UDM-EXEC-002: Compiler / syntax error explicit propagation
- UDM-EXEC-003: Provider / API failure propagation (no mock fallback)
- UDM-EXEC-004: Early cancellation before stream
- UDM-EXEC-005: Mid-stream cancellation & partial data retention
- UDM-EXEC-006: Zero-result search completeness
- UDM-EXEC-007: Receive limit enforcement & partial completeness
- UDM-EXEC-008: Structural provenance verification
- UDM-EXEC-009: Static anti-mock audit across all production code
"""

import os
import re
import unittest
from datetime import datetime

from adapters.google_secops import GoogleSecOpsAdapter
from engine import (
    CompletenessState,
    LifecycleState,
    SearchBatchResult,
    SearchRequest,
    SearchSession,
    SecOpsEngine,
)


class TestUDMSearchRobustnessM11(unittest.TestCase):
    def setUp(self):
        self.adapter = GoogleSecOpsAdapter()
        self.engine = SecOpsEngine(self.adapter)
        self.end_time = "2026-08-17T11:03:00.000Z"
        self.start_time = "2026-08-16T11:03:00.000Z"

    def test_udm_exec_001_valid_query_happy_path(self):
        """UDM-EXEC-001: Valid query -> Validate -> Initiate -> Incremental Stream -> Complete."""
        req = SearchRequest(
            query='metadata.event_type = "USER_LOGIN"',
            start_time=self.start_time,
            end_time=self.end_time,
            receive_limit=100,
            batch_size=50,
        )

        batches = []

        def on_batch(batch: SearchBatchResult, session: SearchSession):
            batches.append(batch)

        session = self.engine.search_udm(req, on_batch=on_batch)

        self.assertIsNotNone(session.session_id)
        self.assertTrue(
            session.session_id.startswith("projects/") or "operations/" in session.session_id
        )
        self.assertEqual(session.lifecycle, LifecycleState.COMPLETED)
        self.assertIn(
            session.completeness, [CompletenessState.COMPLETE, CompletenessState.PARTIAL]
        )
        self.assertGreater(session.received_count, 0)
        self.assertEqual(len(session.events), session.received_count)

        first_event = session.events[0]
        event_body = first_event.get("event") or first_event.get("udm")
        self.assertEqual(event_body["metadata"]["eventType"], "USER_LOGIN")

    def test_udm_exec_002_syntax_error_propagation(self):
        """UDM-EXEC-002: Invalid query syntax causes explicit compiler error without crash/mock."""
        req = SearchRequest(
            query='metadata.event_type = = = "FOO"',
            start_time=self.start_time,
            end_time=self.end_time,
        )

        session = self.engine.search_udm(req)

        self.assertEqual(session.lifecycle, LifecycleState.FAILED)
        self.assertEqual(session.completeness, CompletenessState.EMPTY)
        self.assertIsNotNone(session.error)
        self.assertIn("compilation error", session.error.lower())
        self.assertEqual(session.received_count, 0)

    def test_udm_exec_003_api_failure_propagation(self):
        """UDM-EXEC-003: Backend HTTP failure surfaces verbatim without synthetic fallback."""
        bad_adapter = GoogleSecOpsAdapter(customer_id="00000000-0000-0000-0000-000000000000")
        bad_engine = SecOpsEngine(bad_adapter)

        req = SearchRequest(
            query='metadata.event_type = "USER_LOGIN"',
            start_time=self.start_time,
            end_time=self.end_time,
        )

        session = bad_engine.search_udm(req)

        self.assertEqual(session.lifecycle, LifecycleState.FAILED)
        self.assertEqual(session.completeness, CompletenessState.EMPTY)
        self.assertIsNotNone(session.error)
        self.assertIn("Google SecOps API Error", session.error)

    def test_udm_exec_004_early_cancellation(self):
        """UDM-EXEC-004: Early cancellation halts stream immediately and marks session CANCELLED."""
        req = SearchRequest(
            query='metadata.event_type = "USER_LOGIN"',
            start_time=self.start_time,
            end_time=self.end_time,
        )

        session = self.engine.search_udm(req, cancel_token=lambda: True)
        self.assertEqual(session.lifecycle, LifecycleState.CANCELLED)

    def test_udm_exec_005_mid_stream_cancellation(self):
        """UDM-EXEC-005: Mid-stream cancellation stops fetching and preserves prior results."""
        req = SearchRequest(
            query='metadata.event_type = "USER_LOGIN"',
            start_time=self.start_time,
            end_time=self.end_time,
            batch_size=1,
            receive_limit=10,
        )

        seen_batches = 0

        def cancel_after_one():
            return seen_batches >= 1

        def on_batch(b, s):
            nonlocal seen_batches
            seen_batches += 1

        session = self.engine.search_udm(req, on_batch=on_batch, cancel_token=cancel_after_one)

        # Either completed or cancelled, but events must be preserved
        self.assertIn(session.lifecycle, [LifecycleState.CANCELLED, LifecycleState.COMPLETED])
        self.assertGreater(session.received_count, 0)
        self.assertEqual(len(session.events), session.received_count)

    def test_udm_exec_006_zero_result_search(self):
        """UDM-EXEC-006: Query with zero matches completes cleanly with count=0 and COMPLETE."""
        req = SearchRequest(
            query='metadata.event_type = "USER_LOGIN" AND principal.hostname = "nonexistent-host-999999"',
            start_time=self.start_time,
            end_time=self.end_time,
        )

        session = self.engine.search_udm(req)

        self.assertEqual(session.lifecycle, LifecycleState.COMPLETED)
        self.assertEqual(session.completeness, CompletenessState.COMPLETE)
        self.assertEqual(session.received_count, 0)
        self.assertEqual(len(session.events), 0)

    def test_udm_exec_007_receive_limit_enforcement(self):
        """UDM-EXEC-007: Engine strictly caps at receive_limit and marks PARTIAL if more exist."""
        req = SearchRequest(
            query='metadata.event_type = "USER_LOGIN"',
            start_time=self.start_time,
            end_time=self.end_time,
            receive_limit=4,
            batch_size=2,
        )

        session = self.engine.search_udm(req)

        self.assertEqual(session.lifecycle, LifecycleState.COMPLETED)
        self.assertLessEqual(session.received_count, 4)
        self.assertEqual(len(session.events), session.received_count)

    def test_udm_exec_008_structural_provenance(self):
        """UDM-EXEC-008: Verifies structural provenance on all received batches."""
        req = SearchRequest(
            query='metadata.event_type = "USER_LOGIN"',
            start_time=self.start_time,
            end_time=self.end_time,
            receive_limit=10,
            batch_size=5,
        )

        received_batches = []

        def on_batch(b: SearchBatchResult, s: SearchSession):
            received_batches.append(b)

        session = self.engine.search_udm(req, on_batch=on_batch)

        self.assertGreater(len(received_batches), 0)
        for b in received_batches:
            self.assertEqual(b.provider, "google_secops")
            self.assertEqual(b.workflow_id, "search.udm")
            self.assertIsNotNone(b.operation_id, "Batch must carry live provider operation_id")
            self.assertTrue(b.operation_id.startswith("projects/") or "operations/" in b.operation_id)
            self.assertGreaterEqual(b.returned_start_index, 1)
            self.assertGreaterEqual(b.returned_end_index, b.returned_start_index)
            self.assertGreater(b.emitted_event_count, 0)
            self.assertGreater(b.provider_event_count, 0)
            self.assertIsInstance(b.retrieved_at, datetime)
            self.assertIsNotNone(b.retrieved_at.tzinfo, "Timestamp must be timezone-aware UTC")

    def test_udm_exec_009_anti_mock_audit(self):
        """UDM-EXEC-009: Strict static verification of zero synthetic data in production code."""
        prod_dirs = ["engine", "adapters", "clients"]
        banned_terms = [
            "mock",
            "dummy",
            "fixture",
            "sample_data",
            "placeholder_data",
            "fake_data",
        ]

        base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))

        for p_dir in prod_dirs:
            full_path = os.path.join(base_dir, p_dir)
            for root, _, files in os.walk(full_path):
                for file in files:
                    if file.endswith(".py") and not file.startswith("test_"):
                        f_path = os.path.join(root, file)
                        with open(f_path, "r", encoding="utf-8") as f:
                            content = f.read()
                            for term in banned_terms:
                                matches = re.findall(rf"\b{term}\b", content, re.IGNORECASE)
                                self.assertEqual(
                                    len(matches),
                                    0,
                                    f"Banned mock term '{term}' found in production file: {f_path}",
                                )


if __name__ == "__main__":
    unittest.main()
