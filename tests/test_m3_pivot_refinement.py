"""Milestone 3 Acceptance & Behavioral Verification Suite.

Validates UDM Search Refinement and Canonical Entity Pivot Workflows against live Google SecOps endpoints.
Zero mocks. Complete error visibility. Provenance tracking.
"""

from tests.test_helpers import get_live_adapter, get_live_engine
import os
import re
import unittest
from datetime import datetime, timezone

from engine import (
    EntityType,
    FieldFilter,
    FilterOperator,
    SearchRequest,
    SearchSession,
    SecOpsEngine,
)


class TestSearchPivotRefinementLive(unittest.TestCase):
    """Behavioral tests for Milestone 3: Search Refinement & Entity Pivoting."""

    @classmethod
    def setUpClass(cls):
        cls.engine = get_live_engine()
        # Fetch 1 real event to serve as live reference for investigation and pivot tests
        req = SearchRequest(
            query='metadata.event_type = "USER_LOGIN"',
            start_time="2026-08-16T11:03:00Z",
            end_time="2026-08-17T11:03:00Z",
            receive_limit=1,
            batch_size=1,
        )
        batches = []
        session = cls.engine.search_udm(req, on_batch=lambda b, s: batches.append(b))
        if not batches or not batches[0].events:
            raise unittest.SkipTest("No live events returned for test setup query")

        cls.live_event_wrapper = batches[0].events[0]
        cls.investigation = cls.engine.investigate_event(cls.live_event_wrapper)
        cls.live_hostname = cls.investigation.get_field("principal.hostname")
        cls.live_vendor = cls.investigation.get_field("metadata.vendorName")

    def test_pivot_ref_001_event_investigation_pivot_filter(self):
        """[PIVOT-REF-001] Event Investigation generates FieldFilter and executes refined search."""
        f_filter = self.investigation.build_pivot_filter("principal.hostname", FilterOperator.EQUALS)
        self.assertEqual(f_filter.field_path, "principal.hostname")
        self.assertEqual(f_filter.value, self.live_hostname)

        # Execute refined search
        session = self.engine.refine_search(
            base='metadata.event_type = "USER_LOGIN"',
            filters=[f_filter],
            start_time="2026-08-16T11:03:00Z",
            end_time="2026-08-17T11:03:00Z",
            receive_limit=5,
            batch_size=5,
        )

        self.assertGreater(session.received_count, 0)
        for ev_wrapper in session.events:
            h = ev_wrapper.get("event", {}).get("principal", {}).get("hostname")
            self.assertEqual(h.lower(), self.live_hostname.lower())

    def test_pivot_ref_002_multi_field_additive_refinement(self):
        """[PIVOT-REF-002] Refine query with multiple additive inclusive filters."""
        f1 = FieldFilter(field_path="metadata.eventType", operator=FilterOperator.EQUALS, value="USER_LOGIN")
        f2 = FieldFilter(field_path="metadata.vendorName", operator=FilterOperator.EQUALS, value=self.live_vendor)

        session = self.engine.refine_search(
            base="",  # Standalone filters
            filters=[f1, f2],
            start_time="2026-08-16T11:03:00Z",
            end_time="2026-08-17T11:03:00Z",
            receive_limit=5,
            batch_size=5,
        )

        self.assertGreater(session.received_count, 0)
        for ev_wrapper in session.events:
            ev = ev_wrapper.get("event", {})
            self.assertEqual(ev.get("metadata", {}).get("eventType"), "USER_LOGIN")
            self.assertEqual(ev.get("metadata", {}).get("vendorName"), self.live_vendor)

    def test_pivot_ref_003_exclusive_filter_refinement(self):
        """[PIVOT-REF-003] Refine query with exclusion filter (NOT EQUALS)."""
        f_exc = FieldFilter(
            field_path="principal.hostname",
            operator=FilterOperator.NOT_EQUALS,
            value=self.live_hostname,
        )

        session = self.engine.refine_search(
            base='metadata.event_type = "USER_LOGIN"',
            filters=[f_exc],
            start_time="2026-08-16T11:03:00Z",
            end_time="2026-08-17T11:03:00Z",
            receive_limit=5,
            batch_size=5,
        )

        # None of the returned events should match excluded hostname
        for ev_wrapper in session.events:
            h = ev_wrapper.get("event", {}).get("principal", {}).get("hostname")
            self.assertNotEqual(h, self.live_hostname)

    def test_pivot_ref_004_session_chaining_refinement(self):
        """[PIVOT-REF-004] Refinement from SearchSession inherits time window and query."""
        initial_req = SearchRequest(
            query='metadata.event_type = "USER_LOGIN"',
            start_time="2026-08-16T11:03:00Z",
            end_time="2026-08-17T11:03:00Z",
            receive_limit=2,
            batch_size=2,
        )
        base_session = self.engine.search_udm(initial_req)

        f_filter = FieldFilter("metadata.vendorName", FilterOperator.EQUALS, self.live_vendor)
        chained_session = self.engine.refine_search(
            base=base_session,
            filters=[f_filter],
            receive_limit=5,
            batch_size=5,
        )

        self.assertIn("metadata.vendor_name", chained_session.request.query)
        self.assertEqual(chained_session.request.start_time, base_session.request.start_time)
        self.assertEqual(chained_session.request.end_time, base_session.request.end_time)


    def test_pivot_ref_005_canonical_entity_search_hostname(self):
        """[PIVOT-REF-005] Canonical Entity Search for Hostname."""
        session = self.engine.search_from_entity(
            entity_type=EntityType.HOSTNAME,
            entity_value=self.live_hostname,
            start_time="2026-08-16T11:03:00Z",
            end_time="2026-08-17T11:03:00Z",
            receive_limit=5,
            batch_size=5,
        )

        self.assertIn("principal.hostname", session.request.query)
        self.assertIn("target.hostname", session.request.query)
        self.assertGreater(session.received_count, 0)

    def test_pivot_ref_006_canonical_entity_search_ip(self):
        """[PIVOT-REF-006] Canonical Entity Search for IP."""
        session = self.engine.search_from_entity(
            entity_type=EntityType.IP,
            entity_value="10.128.0.22",
            start_time="2026-08-16T11:03:00Z",
            end_time="2026-08-17T11:03:00Z",
            receive_limit=5,
            batch_size=5,
        )

        self.assertIn("principal.ip", session.request.query)
        self.assertIn("target.ip", session.request.query)
        self.assertGreater(session.received_count, 0)

    def test_pivot_ref_007_missing_field_pivot_error(self):
        """[PIVOT-REF-007] Key error raised when pivoting on non-existent field."""
        with self.assertRaises(KeyError):
            self.investigation.build_pivot_filter("non.existent.path.value")

    def test_pivot_ref_008_static_anti_mock_audit(self):
        """[PIVOT-REF-008] Anti-mock static audit across production source directories."""
        banned_patterns = [
            r"\bmock\b",
            r"\bMock\b",
            r"\bMOCK\b",
            r"\bfixture\b",
            r"\bFixture\b",
            r"\bdummy\b",
            r"\bDummy\b",
            r"\bfake\b",
            r"\bFake\b",
            r"\bsampleData\b",
            r"\bsample_data\b",
            r"\bplaceholderData\b",
            r"\bplaceholder_data\b",
        ]
        combined_regex = re.compile("|".join(banned_patterns))

        src_dirs = [
            "secops-lean/engine",
            "secops-lean/adapters",
            "secops-lean/clients",
        ]

        violations = []
        for src_dir in src_dirs:
            abs_dir = os.path.abspath(
                os.path.join(os.path.dirname(__file__), "..", "..", src_dir)
            )
            if not os.path.exists(abs_dir):
                abs_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", src_dir.split("/")[-1]))

            for root, _, files in os.walk(abs_dir):
                for f in files:
                    if f.endswith(".py"):
                        fpath = os.path.join(root, f)
                        with open(fpath, "r", encoding="utf-8") as fp:
                            for lnum, line in enumerate(fp, 1):
                                if combined_regex.search(line):
                                    violations.append(f"{fpath}:{lnum}: {line.strip()}")

        self.assertEqual(
            violations,
            [],
            f"Anti-mock violations found in production code:\n" + "\n".join(violations),
        )


if __name__ == "__main__":
    unittest.main()
