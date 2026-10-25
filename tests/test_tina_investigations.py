"""Tests for Google SecOps Gemini Triage & Investigation Agent (TINA) Investigations."""

import json
import os
import unittest

from engine.domain import (
    TinaConfidence,
    TinaInvestigation,
    TinaInvestigationBatch,
    TinaInvestigationStep,
    TinaNextStep,
    TinaVerdict,
)
from engine.facade import SecOpsEngine
from engine.workflows.tina_investigation import (
    parse_tina_investigation,
    parse_tina_next_step,
    parse_tina_step,
)
from tests.test_helpers import get_live_engine


class TestTinaInvestigationContracts(unittest.TestCase):
    """Verifies registry capabilities, taxonomy axes, and contract rules."""

    def setUp(self):
        self.engine = SecOpsEngine()
        self.reg = self.engine.registry

    def test_capabilities_registered(self):
        cap_list = self.reg.get("investigation.tina.list")
        self.assertIsNotNone(cap_list, "Missing investigation.tina.list capability")
        self.assertEqual(cap_list.category, "investigation")
        self.assertEqual(cap_list.kind, "query")
        self.assertEqual(cap_list.cardinality, "unbounded")
        self.assertTrue(cap_list.agent.get("require_filter_for_unbounded_query"))

        cap_get = self.reg.get("investigation.tina.get")
        self.assertIsNotNone(cap_get, "Missing investigation.tina.get capability")
        self.assertEqual(cap_get.category, "investigation")
        self.assertEqual(cap_get.kind, "query")
        self.assertEqual(cap_get.cardinality, "single")

        cap_latest = self.reg.get("alert.tina.latest")
        self.assertIsNotNone(cap_latest, "Missing alert.tina.latest capability")
        self.assertEqual(cap_latest.category, "investigation")
        self.assertEqual(cap_latest.kind, "query")
        self.assertEqual(cap_latest.cardinality, "single")


class TestTinaInvestigationParsing(unittest.TestCase):
    """Verifies domain parsing against live captured raw evidence payloads."""

    def test_parse_live_evidence_list_and_get(self):
        evidence_dir = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            "evidence",
            "investigation",
        )
        list_evidence_file = os.path.join(evidence_dir, "tina_list", "raw.json")
        get_evidence_file = os.path.join(evidence_dir, "tina_get", "raw.json")

        self.assertTrue(os.path.exists(list_evidence_file), f"Missing {list_evidence_file}")
        with open(list_evidence_file, "r", encoding="utf-8") as f:
            list_data = json.load(f)

        raw_invs = list_data.get("investigations", [])
        self.assertGreater(len(raw_invs), 0, "No investigations found in list evidence")

        batch = [parse_tina_investigation(raw) for raw in raw_invs]
        for inv in batch:
            self.assertIsInstance(inv, TinaInvestigation)
            self.assertTrue(inv.id)
            self.assertTrue(inv.name.startswith("projects/"))
            self.assertIn("investigations/", inv.name)

        self.assertTrue(os.path.exists(get_evidence_file), f"Missing {get_evidence_file}")
        with open(get_evidence_file, "r", encoding="utf-8") as f:
            get_data = json.load(f)

        detail = parse_tina_investigation(get_data)
        self.assertIsInstance(detail, TinaInvestigation)
        self.assertTrue(detail.id)
        self.assertIsNotNone(detail.verdict)
        self.assertIsNotNone(detail.confidence)
        self.assertGreater(len(detail.investigation_steps), 0)

        step = detail.investigation_steps[0]
        self.assertIsInstance(step, TinaInvestigationStep)
        self.assertTrue(step.name)
        if step.source_metadata:
            self.assertIsNotNone(step.source_metadata.source_type)

        if detail.next_steps:
            ns = detail.next_steps[0]
            self.assertIsInstance(ns, TinaNextStep)
            self.assertTrue(ns.title)
            self.assertIn(ns.step_type, ("SEARCHABLE", "MANUAL"))


class TestLiveTinaWorkflow(unittest.TestCase):
    """Live smoke test against real SecOps tenant (skipped if unconfigured)."""

    def setUp(self):
        self.engine = get_live_engine()

    def test_live_list_tina_investigations(self):
        batch = self.engine.list_tina_investigations(page_size=3)
        self.assertIsInstance(batch, TinaInvestigationBatch)
        if len(batch.investigations) > 0:
            first_inv = batch.investigations[0]
            self.assertIsInstance(first_inv, TinaInvestigation)
            self.assertTrue(first_inv.id)

            fetched = self.engine.get_tina_investigation(first_inv.id)
            self.assertEqual(fetched.id, first_inv.id)
            self.assertGreater(len(fetched.investigation_steps), 0)


if __name__ == "__main__":
    unittest.main()
