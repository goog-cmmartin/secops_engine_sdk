"""Acceptance and Behavioral Tests for Detection Tuning & Findings Refinements.

Verifies:
1. Top noisy detection rules aggregation and classification (`find_top_noisy_rules`).
2. Multi-dimensional entity cardinality profiling (`analyze_entity_cardinality`).
3. Historical SOAR case cross-referencing (`cross_reference_rule_cases`).
4. UDM Findings Refinement dry-run simulation (`test_findings_refinement`).
5. UDM Findings Refinement listing (`list_findings_refinements`).
6. High-level composite tuning diagnosis (`tune_detection`).
7. Strict anti-mock audit compliance.
"""

import os
import unittest
from datetime import datetime

from engine import (
    DetectionTuningReport,
    DimensionCardinality,
    EntityCardinalityRecord,
    EntityCardinalityReport,
    FindingsRefinementBatch,
    FindingsRefinementSummary,
    FindingsRefinementTestResult,
    NoisyRuleRecord,
    NoisyRulesBatch,
    RuleCaseHistoryBatch,
    RuleCaseHistoryRecord,
    SecOpsEngine,
)
from tests.test_helpers import get_live_engine


class TestDetectionTuningLive(unittest.TestCase):
    """Live acceptance tests for Detection Tuning and Findings Refinements workflows."""

    @classmethod
    def setUpClass(cls):
        cls.engine = get_live_engine()

    def test_01_find_top_noisy_rules(self):
        """Verifies baseline aggregation of top firing detection rules."""
        batch = self.engine.find_top_noisy_rules(lookback_days=7, limit=5)

        self.assertIsInstance(batch, NoisyRulesBatch)
        self.assertIsInstance(batch.rules, list)
        self.assertGreater(len(batch.rules), 0)

        rule = batch.rules[0]
        self.assertIsInstance(rule, NoisyRuleRecord)
        self.assertTrue(len(rule.rule_id) > 0)
        self.assertTrue(len(rule.rule_name) > 0)
        self.assertIn(rule.rule_type, ["GOOGLE_MANAGED", "GOOGLE_CURATED", "CUSTOMER", "UNKNOWN"])
        self.assertIsInstance(rule.detection_count, int)
        self.assertGreater(rule.detection_count, 0)
        self.assertIsInstance(rule.is_curated, bool)

    def test_02_analyze_entity_cardinality(self):
        """Verifies multi-dimensional entity subfield profiling for top noisy rule."""
        report = self.engine.analyze_entity_cardinality(
            rule_id="ur_5f1035ac-b376-4d6b-ad72-5f6da5d51d02",
            dimensions=["ips"],
            lookback_days=7,
            limit_per_dimension=3,
        )

        self.assertIsInstance(report, EntityCardinalityReport)
        self.assertEqual(report.rule_id, "ur_5f1035ac-b376-4d6b-ad72-5f6da5d51d02")
        self.assertGreater(len(report.dimensions), 0)

        dim = report.dimensions[0]
        self.assertIsInstance(dim, DimensionCardinality)
        self.assertIn("ip", dim.dimension.lower())
        self.assertIn("principal.ip", dim.subfield_path)
        self.assertGreater(len(dim.records), 0)

        rec = dim.records[0]
        self.assertIsInstance(rec, EntityCardinalityRecord)
        self.assertTrue(len(rec.value) > 0)
        self.assertGreater(rec.count, 0)

    def test_03_cross_reference_rule_cases(self):
        """Verifies querying SOAR case history linked to the detection rule."""
        batch = self.engine.cross_reference_rule_cases(
            rule_id="ur_5f1035ac-b376-4d6b-ad72-5f6da5d51d02",
            lookback_days=90,
            limit=5,
        )

        self.assertIsInstance(batch, RuleCaseHistoryBatch)
        self.assertEqual(batch.rule_id, "ur_5f1035ac-b376-4d6b-ad72-5f6da5d51d02")
        self.assertIsInstance(batch.cases, list)

        if batch.cases:
            c = batch.cases[0]
            self.assertIsInstance(c, RuleCaseHistoryRecord)
            self.assertTrue(len(c.case_id) > 0)
            self.assertTrue(len(c.display_name) > 0)

    def test_04_test_findings_refinement(self):
        """Verifies live dry-run simulation of UDM findings refinement exclusion."""
        res = self.engine.test_findings_refinement(
            curated_rule_ids=["ur_5f1035ac-b376-4d6b-ad72-5f6da5d51d02"],
            query="(principal.ip = /213.209.159.175/)",
            lookback_days=7,
        )

        self.assertIsInstance(res, FindingsRefinementTestResult)
        self.assertIn("ur_5f1035ac-b376-4d6b-ad72-5f6da5d51d02", res.curated_rule_id)
        self.assertGreater(res.total_detections, 0)
        self.assertGreater(res.excluded_detections, 0)
        self.assertGreater(res.suppression_ratio, 0.0)

    def test_05_list_findings_refinements(self):
        """Verifies listing active findings refinements across tenant."""
        batch = self.engine.list_findings_refinements(page_size=10)

        self.assertIsInstance(batch, FindingsRefinementBatch)
        self.assertIsInstance(batch.refinements, list)

        if batch.refinements:
            r = batch.refinements[0]
            self.assertIsInstance(r, FindingsRefinementSummary)
            self.assertTrue(len(r.id) > 0)
            self.assertTrue(len(r.query) > 0)

    def test_06_diagnose_and_tune_composite(self):
        """Verifies composite autonomous detection tuning workflow."""
        report = self.engine.tune_detection(
            rule_id="ur_5f1035ac-b376-4d6b-ad72-5f6da5d51d02",
            lookback_days=7,
        )

        self.assertIsInstance(report, DetectionTuningReport)
        self.assertEqual(report.rule_id, "ur_5f1035ac-b376-4d6b-ad72-5f6da5d51d02")
        self.assertEqual(report.rule_type, "GOOGLE_MANAGED")
        self.assertTrue(report.is_curated)
        self.assertIsNotNone(report.proposed_refinement_query)
        self.assertIsNotNone(report.dry_run_impact)
        self.assertGreater(report.dry_run_impact.total_detections, 0)

    def test_07_no_mock_data_audit(self):
        """CI Invariant: Ensure zero banned mock/synthetic terms in production files."""
        repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        banned_terms = ["mock", "fixture", "dummy", "fake", "sample_data", "test_data"]

        prod_files = [
            os.path.join(repo_root, "engine", "workflows", "detection_tuning.py"),
            os.path.join(repo_root, "engine", "domain.py"),
            os.path.join(repo_root, "adapters", "google_secops.py"),
            os.path.join(repo_root, "engine", "facade.py"),
        ]

        for path in prod_files:
            with open(path, "r", encoding="utf-8") as f:
                content = f.read()
                lines = content.split("\n")
                for line_num, line in enumerate(lines, 1):
                    lower_line = line.lower()
                    for term in banned_terms:
                        if term in lower_line:
                            tokens = [t.strip("\"'()[]{},: ") for t in lower_line.split()]
                            for tok in tokens:
                                if tok == term:
                                    self.fail(
                                        f"Banned term '{term}' found in production file "
                                        f"'{os.path.relpath(path, repo_root)}' line {line_num}: {line}"
                                    )


if __name__ == "__main__":
    unittest.main()
