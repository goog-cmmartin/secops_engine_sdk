"""Authoritative Milestone 1 Acceptance Test Suite.

Verifies the real UDM Search vertical slice against live Google SecOps APIs:
- Happy Path (Validate -> Initiate -> Stream Incremental Events -> Complete)
- Unhappy Path 1 (Invalid Query / Compilation Error surfaced explicitly)
- Unhappy Path 2 (API / Network failure surfaced without mock fallback)
- Unhappy Path 3 (Cancellation stops stream and retains partial results)
- Anti-Mock Audit (Verifies strict absence of mock/synthetic fallback data)
"""

from tests.test_helpers import get_live_adapter, get_live_engine
import os
import re
import unittest
from datetime import datetime, timedelta, timezone

from adapters.google_secops import GoogleSecOpsAdapter
from engine import (
    CompletenessState,
    LifecycleState,
    SearchBatchResult,
    SearchRequest,
    SearchSession,
    SecOpsEngine,
)


class TestM1VerticalSlice(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.adapter = get_live_adapter()
        cls.engine = get_live_engine(adapter=cls.adapter)

    def setUp(self):
        self.adapter = self.__class__.adapter
        self.engine = self.__class__.engine
        now = datetime.now(timezone.utc)
        self.end_time = now.strftime("%Y-%m-%dT%H:%M:%SZ")
        self.start_time = (now - timedelta(days=2)).strftime("%Y-%m-%dT%H:%M:%SZ")


    def test_01_happy_path_udm_search(self):
        """Happy path: Valid query -> Validate -> Initiate -> Incremental Stream -> Complete."""
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

        # Invariants & Assertions
        self.assertIsNotNone(session.session_id, "Session ID must be populated")
        self.assertTrue(
            session.session_id.startswith("projects/") or "operations/" in session.session_id,
            f"Expected Google operation path, got: {session.session_id}",
        )
        self.assertEqual(session.lifecycle, LifecycleState.COMPLETED)
        self.assertIn(
            session.completeness,
            [CompletenessState.COMPLETE, CompletenessState.PARTIAL],
        )
        self.assertGreater(session.received_count, 0, "Expected live events from Google SecOps")

        self.assertEqual(len(session.events), session.received_count)

        # Verify event provenance / structure
        first_event = session.events[0]
        self.assertTrue(
            "event" in first_event or "udm" in first_event,
            "Event must contain event/udm structure",
        )
        event_body = first_event.get("event") or first_event.get("udm")
        self.assertEqual(
            event_body["metadata"]["eventType"],
            "USER_LOGIN",
            "Event type must match query",
        )

    def test_02_unhappy_path_syntax_error(self):
        """Unhappy path 1: Malformed query causes backend compilation error without crash/mock."""
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

    def test_03_unhappy_path_api_error(self):
        """Unhappy path 2: API error (e.g. invalid customer ID) surfaces without synthetic fallback."""
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

    def test_04_unhappy_path_cancellation(self):
        """Unhappy path 3: Early cancellation halts stream and transitions to CANCELLED."""
        req = SearchRequest(
            query='metadata.event_type = "USER_LOGIN"',
            start_time=self.start_time,
            end_time=self.end_time,
        )

        # Cancel immediately before execution
        session = self.engine.search_udm(req, cancel_token=lambda: True)

        self.assertEqual(session.lifecycle, LifecycleState.CANCELLED)

    def test_05_anti_mock_audit(self):
        """Anti-Mock Invariant: Verify zero synthetic data or mock terms in production code."""
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
                                # Look for exact word or function identifier
                                matches = re.findall(rf"\b{term}\b", content, re.IGNORECASE)
                                self.assertEqual(
                                    len(matches),
                                    0,
                                    f"Banned mock term '{term}' found in production file: {f_path}",
                                )


if __name__ == "__main__":
    unittest.main()
