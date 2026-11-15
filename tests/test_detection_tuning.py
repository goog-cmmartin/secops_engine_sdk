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
        noisy = cls.engine.find_top_noisy_rules(lookback_days=30, limit=10)
        cls.noisy_rules = noisy.rules
        cls.target_rule = next((r for r in noisy.rules if r.is_curated), noisy.rules[0] if noisy.rules else None)

    def test_01_find_top_noisy_rules(self):
        """Verifies baseline aggregation of top firing detection rules."""
        batch = self.engine.find_top_noisy_rules(lookback_days=30, limit=5)

        self.assertIsInstance(batch, NoisyRulesBatch)
        self.assertIsInstance(batch.rules, list)
        if not batch.rules:
            self.skipTest("No firing detection rules in live tenant over 30-day lookback.")

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
        if not self.target_rule:
            self.skipTest("No firing detection rules available in live tenant.")
        report = self.engine.analyze_entity_cardinality(
            rule_id=self.target_rule.rule_id,
            dimensions=["ips", "users", "hosts"],
            lookback_days=30,
            limit_per_dimension=3,
        )

        self.assertIsInstance(report, EntityCardinalityReport)
        self.assertEqual(report.rule_id, self.target_rule.rule_id)
        self.assertGreater(len(report.dimensions), 0)

        dim = report.dimensions[0]
        self.assertIsInstance(dim, DimensionCardinality)
        self.assertIsInstance(dim.records, list)
        populated = [r for d in report.dimensions for r in d.records]
        for rec in populated:
            self.assertIsInstance(rec, EntityCardinalityRecord)
            self.assertTrue(len(rec.value) > 0)
            self.assertGreater(rec.count, 0)

    def test_03_cross_reference_rule_cases(self):
        """Verifies querying SOAR case history linked to the detection rule."""
        if not self.target_rule:
            self.skipTest("No firing detection rules available in live tenant.")
        batch = self.engine.cross_reference_rule_cases(
            rule_id=self.target_rule.rule_id,
            lookback_days=90,
            limit=5,
        )

        self.assertIsInstance(batch, RuleCaseHistoryBatch)
        self.assertEqual(batch.rule_id, self.target_rule.rule_id)
        self.assertIsInstance(batch.cases, list)

        if batch.cases:
            c = batch.cases[0]
            self.assertIsInstance(c, RuleCaseHistoryRecord)
            self.assertTrue(len(c.case_id) > 0)
            self.assertTrue(len(c.display_name) > 0)

    def test_04_test_findings_refinement(self):
        """Verifies live dry-run simulation of UDM findings refinement exclusion."""
        from engine.workflows.detection_tuning import translate_to_udm_refinement

        curated_rule = next((r for r in self.noisy_rules if r.is_curated), None)
        if not curated_rule:
            self.skipTest("No firing curated (ur_*) rule in live tenant to test findings refinement.")
        card = self.engine.analyze_entity_cardinality(
            rule_id=curated_rule.rule_id,
            dimensions=["ips", "hosts", "users"],
            lookback_days=30,
            limit_per_dimension=3,
        )
        sample_clause = None
        for dim in card.dimensions:
            if dim.records and dim.subfield_path:
                udm_field = dim.subfield_path.split("event.")[-1] if "event." in dim.subfield_path else dim.subfield_path
                sample_clause = translate_to_udm_refinement(udm_field, dim.records[0].value, is_regex=True)
                break
        if not sample_clause:
            sample_clause = translate_to_udm_refinement("principal.hostname", "nonexistent-tuning-probe", is_regex=True)

        res = self.engine.test_findings_refinement(
            curated_rule_ids=[curated_rule.rule_id],
            query=sample_clause,
            lookback_days=14,
        )

        self.assertIsInstance(res, FindingsRefinementTestResult)
        self.assertIn(curated_rule.rule_id, res.curated_rule_id)
        self.assertGreaterEqual(res.total_detections, 0)
        self.assertGreaterEqual(res.excluded_detections, 0)
        self.assertGreaterEqual(res.suppression_ratio, 0.0)

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
        if not self.target_rule:
            self.skipTest("No firing detection rules available in live tenant.")
        report = self.engine.tune_detection(
            rule_id=self.target_rule.rule_id,
            lookback_days=30,
        )

        self.assertIsInstance(report, DetectionTuningReport)
        self.assertEqual(report.rule_id, self.target_rule.rule_id)
        self.assertIn(report.rule_type, ["GOOGLE_MANAGED", "GOOGLE_CURATED", "CUSTOMER", "UNKNOWN"])
        self.assertEqual(report.is_curated, self.target_rule.is_curated)
        if report.is_curated and report.proposed_refinement_query and report.dry_run_impact is not None:
            self.assertGreaterEqual(report.dry_run_impact.total_detections, 0)

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
