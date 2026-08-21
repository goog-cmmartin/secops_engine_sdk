"""Acceptance tests for Milestone 5.7: Curated Detections Engine.

Verifies:
1. Curated Rule Sets and Categories discovery from live Google SecOps.
2. Multi-facet search by MITRE ATT&CK tactics, techniques, and log sources.
3. Curated Rule Set deep inspection, including broad/precise deployments and detection telemetry.
4. Curated Rule detail retrieval with raw executable YARA-L logic extraction from Content Hub.
5. Curated detection firing counts aggregation and tenant rule engine quotas.
6. Engine capability registry registration for curated_detections.*.
7. Anti-mock compliance audit ensuring zero synthetic fixtures in production code.

Invariants: Strict live API provenance, no synthetic fallbacks, explicit errors.
"""

from tests.test_helpers import get_live_adapter, get_live_engine
from datetime import datetime, timedelta, timezone
import os
import unittest

from adapters.google_secops import GoogleSecOpsAdapter
from engine.domain import (
    CuratedDetectionMetrics,
    CuratedPrecision,
    CuratedRuleDetail,
    CuratedRuleSetBatch,
    CuratedRuleSetDetail,
    CuratedRuleSetSummary,
    CuratedRuleSummary,
    TenantRuleMetrics,
)
from engine.facade import SecOpsEngine
from engine.registry import registry


class TestCuratedDetectionsLive(unittest.TestCase):
    """Authoritative behavioral test suite for Curated Detections against live SecOps."""

    @classmethod
    def setUpClass(cls):
        cls.adapter = get_live_adapter()
        cls.engine = get_live_engine(adapter=cls.adapter)

    def test_01_list_curated_categories_and_rulesets_live(self):
        """Verify discovery of categories and curated rule sets."""
        # Adapter direct probe
        cats_res = self.adapter.list_curated_ruleset_categories()
        cats = cats_res.get("curatedRuleSetCategories", [])
        self.assertIsInstance(cats, list)
        self.assertGreater(len(cats), 0, "Expected at least 1 curated category in tenant")

        # Search via engine
        batch = self.engine.search_curated_rulesets(limit=10)
        self.assertIsInstance(batch, CuratedRuleSetBatch)
        self.assertGreater(batch.total_count, 0, "Expected positive count of curated rule sets")
        self.assertGreater(len(batch.results), 0)

        first_rs = batch.results[0]
        self.assertIsInstance(first_rs, CuratedRuleSetSummary)
        self.assertTrue(first_rs.id, "Expected non-empty rule set ID")
        self.assertTrue(first_rs.title, "Expected non-empty title")
        self.assertTrue(first_rs.resource_name.startswith("projects/"))

    def test_02_search_curated_rulesets_by_mitre_and_log_source(self):
        """Verify multi-facet filtering by MITRE tactic/technique and log sources."""
        # 1. Filter by MITRE tactic (e.g. TA0005 Stealth / TA0001 Initial Access)
        batch_tactic = self.engine.search_curated_rulesets(mitre_tactic="TA0005", limit=20)
        self.assertIsInstance(batch_tactic, CuratedRuleSetBatch)
        if batch_tactic.results:
            for rs in batch_tactic.results:
                tactic_ids = [t.id for t in rs.tactics]
                self.assertIn("TA0005", tactic_ids, f"Rule set {rs.title} missing TA0005 tactic")

        # 2. Filter by Log Source (e.g. 'Azure Activity' or 'Office 365')
        batch_logs = self.engine.search_curated_rulesets(log_source="Azure Activity", limit=20)
        self.assertIsInstance(batch_logs, CuratedRuleSetBatch)
        if batch_logs.results:
            for rs in batch_logs.results:
                log_matched = any("azure activity" in ls.lower() for ls in rs.log_sources)
                self.assertTrue(log_matched, f"Rule set {rs.title} missing expected log source")

    def test_03_get_curated_ruleset_deployments(self):
        """Verify deep inspection of a curated rule set with broad/precise deployments."""
        batch = self.engine.search_curated_rulesets(query="Azure - Network", limit=5)
        self.assertGreater(len(batch.results), 0, "Expected 'Azure - Network' rule set to exist")
        target_rs = batch.results[0]

        detail = self.engine.get_curated_ruleset(target_rs.id)
        self.assertIsInstance(detail, CuratedRuleSetDetail)
        self.assertEqual(detail.rule_set.id, target_rs.id)
        self.assertTrue(detail.rule_set.title)

        # Verify deployments (broad vs precise)
        self.assertIsInstance(detail.deployments, list)
        self.assertGreater(len(detail.deployments), 0, "Expected deployments for curated rule set")
        precisions = [d.precision for d in detail.deployments]
        self.assertTrue(any(p in ["BROAD", "PRECISE"] for p in precisions))

    def test_04_get_curated_rule_and_yaral_logic(self):
        """Verify retrieving an individual curated rule and extracting executable YARA-L logic."""
        rule_id = "ur_025628f0-af2d-4a52-b899-4de31928edfc"
        detail = self.engine.get_curated_rule(rule_id)

        self.assertIsInstance(detail, CuratedRuleDetail)
        self.assertEqual(detail.rule.id, rule_id)
        self.assertEqual(detail.rule.title, "Azure Network Device Modified")
        self.assertIsInstance(detail.rule_text, str)
        self.assertGreater(len(detail.rule_text), 50, "Expected non-empty YARA-L rule text")
        self.assertIn("rule ttp_azure_network_device_modified", detail.rule_text)
        self.assertIn("events:", detail.rule_text)
        self.assertIn("condition:", detail.rule_text)

    def test_05_curated_detection_counts_and_tenant_metrics(self):
        """Verify querying :countAllCuratedRuleSetDetections and legacy rule engine quotas."""
        now = datetime.now(timezone.utc)
        start_iso = (now - timedelta(days=7)).strftime("%Y-%m-%dT%H:%M:%S.000Z")
        end_iso = now.strftime("%Y-%m-%dT%H:%M:%S.000Z")

        metrics = self.engine.get_curated_detection_metrics(start_time=start_iso, end_time=end_iso)
        self.assertIsInstance(metrics, CuratedDetectionMetrics)

        # Tenant quotas
        tm = metrics.tenant_metrics
        self.assertIsInstance(tm, TenantRuleMetrics)
        self.assertGreaterEqual(tm.total_active_count, 0)
        self.assertGreater(tm.quota_limit, 0, "Expected positive quota limit")

        # Top firing curated rule sets
        self.assertIsInstance(metrics.top_firing_rulesets, list)
        if metrics.top_firing_rulesets:
            first_hit = metrics.top_firing_rulesets[0]
            self.assertIn("ruleset_id", first_hit)
            self.assertIn("ruleset_name", first_hit)
            self.assertIn("count", first_hit)
            self.assertGreaterEqual(first_hit["count"], 0)

    def test_06_capabilities_registered(self):
        """Verify engine capability registry exposes curated_detections.*."""
        caps = registry.list_capabilities(category="curated_detections")
        cap_ids = {c.capability_id for c in caps}

        expected = {
            "curated_detections.search_rulesets",
            "curated_detections.get_ruleset",
            "curated_detections.get_rule",
            "curated_detections.metrics",
        }
        self.assertTrue(expected.issubset(cap_ids), f"Missing capabilities: {expected - cap_ids}")

    def test_07_static_anti_mock_audit(self):
        """Audit curated detections implementation for banned mock/synthetic patterns."""
        banned_terms = [
            "mock",
            "Mock",
            "MOCK",
            "fixture",
            "dummy",
            "fake",
            "sample_data",
            "sampleData",
            "placeholder_data",
            "placeholderData",
            "test_data",
        ]

        target_files = [
            os.path.join(os.path.dirname(__file__), "..", "engine", "workflows", "curated_detections.py"),
            os.path.join(os.path.dirname(__file__), "..", "engine", "domain.py"),
            os.path.join(os.path.dirname(__file__), "..", "engine", "facade.py"),
        ]

        for filepath in target_files:
            if not os.path.exists(filepath):
                continue
            with open(filepath, "r", encoding="utf-8") as f:
                content = f.read()
                for term in banned_terms:
                    self.assertNotIn(
                        term,
                        content,
                        f"Banned identifier '{term}' found in production source: {filepath}",
                    )


if __name__ == "__main__":
    unittest.main()
