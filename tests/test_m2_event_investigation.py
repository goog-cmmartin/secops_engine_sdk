"""Milestone 2 Acceptance & Behavioral Verification Suite.

Validates the Event Investigation & Raw Log Workflow against live Google SecOps endpoints.
Zero mocks. Complete error visibility. Provenance tracking.
"""

from tests.test_helpers import get_live_adapter, get_live_engine
import os
import re
import unittest
from datetime import datetime, timezone

from engine import (
    EventInvestigation,
    EventReference,
    InvestigationProvenance,
    RawLogPayload,
    SearchRequest,
    SecOpsEngine,
)


class TestEventInvestigationLive(unittest.TestCase):
    """Behavioral tests for Milestone 2: Event Details & Raw Log."""

    @classmethod
    def setUpClass(cls):
        cls.engine = get_live_engine()
        # Fetch 1 real event to serve as live reference for investigation tests
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
        cls.live_event = cls.live_event_wrapper.get("event", {})
        cls.live_event_id = cls.live_event.get("metadata", {}).get("id")
        cls.live_log_token = cls.live_event_wrapper.get("eventLogToken")

    def test_ev_inv_001_investigate_from_search_result(self):
        """[EV-INV-001] Investigate event directly from SearchBatchResult (in-memory UDM + lazy raw log)."""
        investigation = self.engine.investigate_event(
            event_ref=self.live_event_wrapper,
            eager_load_raw_log=False,
        )

        self.assertIsInstance(investigation, EventInvestigation)
        self.assertEqual(investigation.event_id, self.live_event_id)
        self.assertEqual(investigation.event.get("metadata", {}).get("eventType"), "USER_LOGIN")
        self.assertIsNone(investigation.raw_log)  # Lazy loaded

        # Now trigger lazy load
        raw_log = investigation.load_raw_log()
        self.assertIsInstance(raw_log, RawLogPayload)
        self.assertTrue(len(raw_log.raw_text) > 0)
        self.assertIsNotNone(raw_log.log_type)
        self.assertIsNotNone(investigation.raw_log)

    def test_ev_inv_002_standalone_investigate_by_id(self):
        """[EV-INV-002] Standalone investigation by Event ID only (fetches via :fetchEnrichedEvent)."""
        investigation = self.engine.investigate_event(
            event_ref=self.live_event_id,
            eager_load_raw_log=False,
        )

        self.assertIsInstance(investigation, EventInvestigation)
        self.assertEqual(investigation.event_id, self.live_event_id)
        self.assertIn("metadata", investigation.event)
        self.assertEqual(investigation.event["metadata"].get("id"), self.live_event_id)

    def test_ev_inv_003_eager_raw_log_retrieval(self):
        """[EV-INV-003] Eager raw log retrieval during initialization."""
        ref = EventReference(
            event_id=self.live_event_id,
            log_token=self.live_log_token,
            structured_event=self.live_event,
        )
        investigation = self.engine.investigate_event(
            event_ref=ref,
            eager_load_raw_log=True,
        )

        self.assertIsNotNone(investigation.raw_log)
        self.assertIsInstance(investigation.raw_log, RawLogPayload)
        self.assertGreater(investigation.raw_log.raw_bytes_size, 0)
        self.assertTrue(len(investigation.raw_log.raw_text) > 0)

    def test_ev_inv_004_raw_log_decoding_integrity(self):
        """[EV-INV-004] Verifies Base64 decoding produces valid unparsed log text."""
        raw_log = self.engine.adapter.get_raw_log(
            event_id=self.live_event_id,
            log_token=self.live_log_token,
        )

        self.assertIsInstance(raw_log.raw_text, str)
        self.assertGreater(len(raw_log.raw_text), 0)
        self.assertIsNotNone(raw_log.source_product)
        self.assertIsNotNone(raw_log.log_type)

    def test_ev_inv_005_dot_notation_and_field_flattening(self):
        """[EV-INV-005] Verifies dot-notation navigation and dictionary flattening."""
        investigation = self.engine.investigate_event(self.live_event_wrapper)

        # Dot-notation lookup
        event_type = investigation.get_field("metadata.eventType")
        self.assertEqual(event_type, "USER_LOGIN")

        expected_vendor = self.live_event.get("metadata", {}).get("vendorName")
        vendor = investigation.get_field("metadata.vendorName")
        self.assertEqual(vendor, expected_vendor)

        # Non-existent field returns default
        missing = investigation.get_field("metadata.nonExistentField", default="MISSING")
        self.assertEqual(missing, "MISSING")

        # Field flattening
        flat_dict = investigation.flatten_fields()
        self.assertIn("metadata.eventType", flat_dict)
        self.assertIn("metadata.vendorName", flat_dict)
        self.assertEqual(flat_dict["metadata.eventType"], "USER_LOGIN")

    def test_ev_inv_006_error_visibility_on_invalid_id(self):
        """[EV-INV-006] API errors propagate explicitly without fake fallback."""
        fake_id = "AAAAA_INVALID_EVENT_ID_XYZ12345="
        with self.assertRaises(Exception) as ctx:
            self.engine.investigate_event(event_ref=fake_id)

        # Ensure explicit API error message is preserved
        self.assertTrue(
            "Google SecOps API Error" in str(ctx.exception)
            or "Request contains an invalid argument" in str(ctx.exception)
            or "400" in str(ctx.exception)
            or "404" in str(ctx.exception)
        )

    def test_ev_inv_007_provenance_and_aware_utc(self):
        """[EV-INV-007] Verifies structural provenance and timezone-aware UTC timestamps."""
        investigation = self.engine.investigate_event(self.live_event_wrapper)

        self.assertIsInstance(investigation.provenance, InvestigationProvenance)
        self.assertEqual(investigation.provenance.provider, "google_secops")
        self.assertEqual(investigation.provenance.workflow_id, "event.investigate")
        self.assertEqual(investigation.provenance.event_id, self.live_event_id)

        # Verify aware UTC timestamp
        retrieved_at = investigation.provenance.retrieved_at
        self.assertIsNotNone(retrieved_at.tzinfo)
        self.assertEqual(retrieved_at.tzinfo, timezone.utc)

    def test_ev_inv_008_static_anti_mock_audit(self):
        """[EV-INV-008] Anti-mock static audit: zero mock data in production source directories."""
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
