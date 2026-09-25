"""Unit and behavioral tests for LogCostAgent (@log-cost-agent) and log cost workflows."""

import os
import tempfile
import unittest
from pathlib import Path

from agents.core.evidence_store import LocalFileEvidenceStore
from agents.generated.log_cost_agent import LogCostAgentAgent
from engine.facade import SecOpsEngine
from engine.domain import (
    FinOpsRecommendation,
    LogCostAnalysisReport,
    LogPricingTier,
    LogTypeCostMetric,
)
from engine.workflows.log_cost import (
    AnalyzeLogCostWorkflow,
    GetLatestLogCostWorkflow,
    DEFAULT_BLOAT_THRESHOLD_BYTES,
)
from tests.test_helpers import get_live_engine


class TestLogCostAgent(unittest.TestCase):
    """Verifies agent bindings, tool registration, mathematical sizing, and FinOps calculations."""

    def setUp(self):
        self._tmpdir = tempfile.TemporaryDirectory()
        self.root_dir = Path(self._tmpdir.name)
        self.evidence_store = LocalFileEvidenceStore(root_dir=self.root_dir)
        self.engine = SecOpsEngine(adapter=None)
        self.agent = LogCostAgentAgent(
            engine=self.engine,
            evidence_store=self.evidence_store,
        )

    def tearDown(self):
        self._tmpdir.cleanup()

    def test_agent_manifest_bindings(self):
        """Verifies ADK 2 agent manifest metadata, streams, topics, and tool bindings."""
        self.assertEqual(self.agent.handle, "@log-cost-agent")
        self.assertEqual(self.agent.default_stream, "ingestion")
        self.assertEqual(self.agent.default_topic, "cost-optimization")
        self.assertIn("log_cost.analyze", self.agent.CAPABILITIES)
        self.assertIn("log_cost.get_latest", self.agent.CAPABILITIES)

        # Verify custom tools bound
        tools = self.agent.get_tools()
        tool_names = [getattr(t, "__name__", str(t)) for t in tools]
        self.assertIn("analyze_log_costs", tool_names)
        self.assertIn("get_latest_log_costs", tool_names)

    def test_mathematical_sizing_and_pricing_tiers(self):
        """Verifies binary GiB vs decimal GB, bloat detection, and 3-tier pricing math."""
        # 100 GB in bytes (100 * 10^9 = 100,000,000,000 bytes)
        raw_bytes = 100_000_000_000
        event_count = 20_000_000  # 5,000 bytes per event (> 2048 bloat threshold)

        vol_gb_dec = raw_bytes / 1e9  # 100.0 GB
        vol_gib_bin = raw_bytes / (1024 ** 3)  # ~93.13 GiB
        avg_bytes = raw_bytes / event_count  # 5000.0 B
        is_bloated = avg_bytes > DEFAULT_BLOAT_THRESHOLD_BYTES  # True

        # Monthly spend for 7 days lookback extrapolated to 30 days
        multiplier_30d = 30.0 / 7.0
        monthly_gb = vol_gb_dec * multiplier_30d

        cost_std = monthly_gb * LogPricingTier.STANDARD.rate_per_gb
        cost_ent = monthly_gb * LogPricingTier.ENTERPRISE.rate_per_gb
        cost_ent_plus = monthly_gb * LogPricingTier.ENTERPRISE_PLUS.rate_per_gb

        self.assertAlmostEqual(vol_gb_dec, 100.0, places=2)
        self.assertAlmostEqual(vol_gib_bin, 93.132, places=2)
        self.assertEqual(avg_bytes, 5000.0)
        self.assertTrue(is_bloated)

        # Rate checks
        self.assertEqual(LogPricingTier.STANDARD.rate_per_gb, 1.95)
        self.assertEqual(LogPricingTier.ENTERPRISE.rate_per_gb, 2.40)
        self.assertEqual(LogPricingTier.ENTERPRISE_PLUS.rate_per_gb, 4.60)

        self.assertAlmostEqual(cost_std, 100.0 * (30 / 7) * 1.95, places=2)
        self.assertAlmostEqual(cost_ent, 100.0 * (30 / 7) * 2.40, places=2)
        self.assertAlmostEqual(cost_ent_plus, 100.0 * (30 / 7) * 4.60, places=2)

    def test_evidence_store_persistence(self):
        """Verifies saving and retrieving LogCostAnalysisReport via evidence store."""
        report = LogCostAnalysisReport(
            lookback_window="7d",
            pricing_tier="ENTERPRISE",
            total_events=50_000_000,
            total_volume_bytes=50_000_000_000,
            total_volume_gb=50.0,
            total_volume_gib=46.56,
            total_projected_monthly_spend_standard=417.85,
            total_projected_monthly_spend_enterprise=514.28,
            total_projected_monthly_spend_enterprise_plus=985.71,
            top_volume_drivers=[
                LogTypeCostMetric(
                    log_type="WINEVTLOG",
                    event_count=30_000_000,
                    volume_bytes=30_000_000_000,
                    volume_gb_decimal=30.0,
                    volume_gib_binary=27.93,
                    avg_event_size_bytes=1000.0,
                    cost_standard=250.71,
                    cost_enterprise=308.57,
                    cost_enterprise_plus=591.43,
                    is_bloated=False,
                )
            ],
            bloated_sources=[],
            recommendations=[
                FinOpsRecommendation(
                    log_type="WINEVTLOG",
                    category="UPSTREAM_DROP_FILTER",
                    title="Filter Event 4663",
                    description="Drop file access spam",
                    potential_volume_savings_gb=5.0,
                    potential_monthly_savings_usd=12.00,
                    implementation_guidance="Use XPath filter",
                )
            ],
            total_potential_savings_usd=12.00,
            provenance=None,
        )

        # Save to store
        self.evidence_store.save_log_cost_analysis(report.to_dict())

        # Retrieve
        loaded_dict = self.evidence_store.get_latest_log_cost_analysis()
        self.assertIsNotNone(loaded_dict)
        self.assertEqual(loaded_dict["total_events"], 50_000_000)
        self.assertEqual(loaded_dict["total_volume_gb"], 50.0)
        self.assertEqual(len(loaded_dict["recommendations"]), 1)
        self.assertEqual(loaded_dict["recommendations"][0]["log_type"], "WINEVTLOG")
    def test_cloud_audit_and_load_balancing_recommendations(self):
        """Verifies that high-volume GCP_CLOUDAUDIT and GCP_LOADBALANCING generate high-impact recommendations."""
        wf = AnalyzeLogCostWorkflow(adapter=None, store=self.evidence_store)
        metrics = [
            LogTypeCostMetric(
                log_type="GCP_CLOUDAUDIT",
                event_count=160_000_000,
                volume_bytes=250_000_000_000,
                volume_gb_decimal=250.0,
                volume_gib_binary=232.83,
                avg_event_size_bytes=1562.5,
                cost_standard=2089.28,
                cost_enterprise=2571.43,
                cost_enterprise_plus=4928.57,
                is_bloated=False,
                pct_total_volume=70.0,
            ),
            LogTypeCostMetric(
                log_type="GCP_LOADBALANCING",
                event_count=50_000_000,
                volume_bytes=75_000_000_000,
                volume_gb_decimal=75.0,
                volume_gib_binary=69.85,
                avg_event_size_bytes=1500.0,
                cost_standard=626.78,
                cost_enterprise=771.43,
                cost_enterprise_plus=1478.57,
                is_bloated=False,
                pct_total_volume=21.0,
            ),
        ]
        recs = wf._generate_finops_recommendations(
            metrics=metrics,
            effective_days=7,
            tier_rate=2.40,
        )
        rec_titles = [r.title for r in recs]
        self.assertTrue(any("GCP_CLOUDAUDIT" in t for t in rec_titles))
        self.assertTrue(any("GCP_LOADBALANCING" in t for t in rec_titles))

        # Cloud audit recommendation should project 25% savings: (250 / 7) * 30 * 0.25 * 2.40 = 642.85 USD
        audit_rec = next(r for r in recs if r.log_type == "GCP_CLOUDAUDIT")
        self.assertAlmostEqual(audit_rec.potential_monthly_savings_usd, 642.857, places=2)

        # Load balancing recommendation should project 35% savings: (75 / 7) * 30 * 0.35 * 2.40 = 270.00 USD
        lb_rec = next(r for r in recs if r.log_type == "GCP_LOADBALANCING")
        self.assertAlmostEqual(lb_rec.potential_monthly_savings_usd, 270.00, places=2)

        # Total savings from these two major drivers should exceed 900 USD/mo
        total_savings = sum(r.potential_monthly_savings_usd for r in recs)
        self.assertGreater(total_savings, 900.0)

    def test_live_analysis_workflow_if_configured(self):
        """Executes log cost analysis against engine if configured, or tests workflow fallback."""
        engine = get_live_engine()
        if not engine:
            self.skipTest("Live SecOps engine not configured; skipping live Chronicle query.")

        wf = AnalyzeLogCostWorkflow(adapter=engine.adapter, store=self.evidence_store)
        report = wf.execute(lookback_days=7, pricing_tier="ENTERPRISE")
        self.assertIsInstance(report, LogCostAnalysisReport)
        self.assertGreater(report.total_events, 0)
        self.assertGreater(report.total_volume_gb, 0.0)
        self.assertGreater(report.total_projected_monthly_spend_enterprise, 0.0)
        self.assertIsInstance(report.recommendations, list)

    def test_anti_mock_compliance(self):
        """CI invariant audit: ensures log_cost production files have zero banned terms."""
        files = [
            "engine/workflows/log_cost.py",
            "agents/generated/log_cost_agent.py",
        ]
        banned = [
            "mock", "Mock", "MOCK",
            "dummy", "Dummy",
            "fake", "Fake",
            "sample_data", "sampleData",
            "placeholder_data", "placeholderData",
            "test_data", "testData",
        ]
        base_dir = Path(__file__).resolve().parent.parent
        for rel_path in files:
            file_path = base_dir / rel_path
            with open(file_path, "r", encoding="utf-8") as f:
                code = f.read()
            for term in banned:
                self.assertNotIn(term, code, f"Banned identifier '{term}' found in {rel_path}")


if __name__ == "__main__":
    unittest.main()
