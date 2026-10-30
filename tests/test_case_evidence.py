"""Acceptance and unit tests for Case Evidence Attachment and Silent Detection Correlation (`case.evidence.attach`, `case.evidence.detach`, `case.detection.correlate`)."""

import unittest
from engine.domain import (
    CaseEvidenceBatchResult,
    CaseEvidenceItem,
    CaseDetectionCorrelationResult,
)
from engine.facade import SecOpsEngine
from engine.taxonomy import derive_cardinality, derive_domain, derive_kind
from engine.workflows.case_evidence import (
    AttachCaseEvidenceWorkflow,
    DetachCaseEvidenceWorkflow,
    _normalize_evidence_type,
)
from tests.test_helpers import get_live_adapter, get_live_engine


class TestCaseEvidenceUnit(unittest.TestCase):
    def test_evidence_type_normalization(self):
        """Verifies evidence type normalization heuristics."""
        self.assertEqual(_normalize_evidence_type("detection"), "EVIDENCE_TYPE_DETECTION")
        self.assertEqual(_normalize_evidence_type("DETECTION"), "EVIDENCE_TYPE_DETECTION")
        self.assertEqual(_normalize_evidence_type("EVIDENCE_TYPE_DETECTION"), "EVIDENCE_TYPE_DETECTION")
        self.assertEqual(_normalize_evidence_type("event"), "EVIDENCE_TYPE_EVENT")
        self.assertEqual(_normalize_evidence_type("alert"), "EVIDENCE_TYPE_ALERT")
        self.assertEqual(_normalize_evidence_type("entity"), "EVIDENCE_TYPE_ENTITY")
        self.assertEqual(_normalize_evidence_type("threat_hunt"), "EVIDENCE_TYPE_THREAT_HUNT")

    def test_taxonomy_classification(self):
        """Verifies taxonomy classification for the new capabilities."""
        self.assertEqual(derive_kind("case.evidence.attach", composed=False), "primitive")
        self.assertEqual(derive_domain("case.evidence.attach", "case"), "case")
        self.assertIsNone(derive_cardinality("case.evidence.attach", "primitive"))

        self.assertEqual(derive_kind("case.evidence.detach", composed=False), "primitive")
        self.assertEqual(derive_domain("case.evidence.detach", "case"), "case")
        self.assertIsNone(derive_cardinality("case.evidence.detach", "primitive"))

        self.assertEqual(derive_kind("case.detection.correlate", composed=True), "workflow")
        self.assertEqual(derive_domain("case.detection.correlate", "case"), "case")
        self.assertIsNone(derive_cardinality("case.detection.correlate", "workflow"))

    def test_empty_evidence_raises(self):
        """Workflow should raise ValueError if evidence_items is empty."""
        class _Inert:
            pass
        wf_attach = AttachCaseEvidenceWorkflow(_Inert())
        with self.assertRaises(ValueError):
            wf_attach.execute(case_id="108339", evidence_items=[])

        wf_detach = DetachCaseEvidenceWorkflow(_Inert())
        with self.assertRaises(ValueError):
            wf_detach.execute(case_id="108339", evidence_items=[])


class TestCaseEvidenceLive(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.adapter = get_live_adapter()
        cls.engine = get_live_engine(adapter=cls.adapter)

    def test_live_attach_and_detach_evidence(self):
        """Validates roundtrip attach and detach of evidence on live SecOps case 108339."""
        case_id = "108339"
        # Test event ID verified against live tenant
        test_event_id = "AAAAADnuNlSqbJAaUjOTUTv2Tm4AAAAADgAAAAAAAAA="

        # 1. Attach
        attach_res = self.engine.attach_events_to_case(
            case_id=case_id,
            event_ids=[test_event_id],
        )
        self.assertIsInstance(attach_res, CaseEvidenceBatchResult)
        self.assertEqual(attach_res.case_id, case_id)
        self.assertGreaterEqual(attach_res.total_count, 1)
        self.assertEqual(attach_res.provenance["workflow"], "case.evidence.attach")

        # 2. Detach (cleanup)
        detach_res = self.engine.detach_case_evidence(
            case_id=case_id,
            evidence_items=[{"evidenceId": test_event_id, "evidenceType": "EVIDENCE_TYPE_EVENT"}],
        )
        self.assertIsInstance(detach_res, CaseEvidenceBatchResult)
        self.assertEqual(detach_res.case_id, case_id)
        self.assertEqual(detach_res.provenance["workflow"], "case.evidence.detach")

    def test_live_correlate_silent_detections(self):
        """Validates correlate_silent_detections workflow execution against live case."""
        case_id = "108339"
        res = self.engine.correlate_silent_detections(
            case_id=case_id,
            lookback_hours=24,
            attach_to_case=False,
            post_wall_comment=False,
            max_events=100,
        )
        self.assertIsInstance(res, CaseDetectionCorrelationResult)
        self.assertEqual(res.case_id, case_id)
        self.assertIsInstance(res.entities_searched, list)
        self.assertIsInstance(res.detections_found, list)
        self.assertIsInstance(res.events_found, list)
        self.assertEqual(res.provenance["workflow"], "case.detection.correlate")


if __name__ == "__main__":
    unittest.main()
