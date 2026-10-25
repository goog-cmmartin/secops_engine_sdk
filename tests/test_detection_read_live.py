"""Live behavioural tests for detection-rule read primitives (read-only).

Skipped unless SECOPS_LIVE_TESTS=1 and a tenant is configured (see
tests/test_helpers.py). Every call here is a GET or a read-only POST
(dashboardQueries:execute, verifyRuleText, countAllCuratedRuleSetDetections),
all allowed by tests/live_guard.py without SECOPS_ALLOW_LIVE_WRITES.
"""

from __future__ import annotations

import unittest

from engine.domain import RuleHealthStatus
from tests.test_helpers import get_live_engine


class TestDetectionReadLive(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.engine = get_live_engine()

    def test_curated_rule_set_deployments(self):
        res = self.engine.list_curated_rule_set_deployments()
        self.assertGreater(len(res.deployments), 0)
        self.assertIsNone(res.next_page_token)
        self.assertTrue({d.precision for d in res.deployments} <= {"BROAD", "PRECISE"})
        self.assertTrue(all(d.rule_set_id and d.category_id for d in res.deployments))
        self.assertTrue(any(d.display_name for d in res.deployments))
        self.assertTrue(any(d.enabled for d in res.deployments))

    def test_rule_detection_series_hourly(self):
        res = self.engine.get_rule_detection_series(lookback_hours=24, bucket="hour")
        self.assertEqual(res.bucket, "hour")
        for s in res.series:
            starts = [b.bucket_start for b in s.buckets]
            self.assertEqual(starts, sorted(starts))
        self.assertEqual(res.total_detections, sum(s.total for s in res.series))

    def test_rule_case_environments(self):
        res = self.engine.get_rule_case_environments(lookback_days=30)
        for p in res.pairs:
            self.assertTrue(p.rule_id)
            self.assertGreater(p.case_count, 0)

    def test_list_all_pages(self):
        one = self.engine.list_rules(page_size=50)
        allp = self.engine.list_rules(page_size=50, all_pages=True)
        self.assertGreaterEqual(len(allp.rules), len(one.rules))
        self.assertIsNone(allp.next_page_token)
        deps = self.engine.list_rule_deployments(all_pages=True)
        self.assertGreaterEqual(len(deps.deployments), len(allp.rules) - 5)

    def test_audit_rule_health_truthful(self):
        rep = self.engine.audit_rule_health(error_lookback_days=7)
        self.assertGreater(rep.custom_rules_audited, 0)
        self.assertTrue(rep.detection_counts_available, rep.telemetry_errors)
        if rep.curated_available:
            curated = [f for f in rep.findings if f.rule_owner == "GOOGLE"]
            self.assertTrue(any(f.status != RuleHealthStatus.DISABLED for f in curated))
        if rep.total_detections_24h:
            self.assertGreater(rep.rules_firing_24h, 0)

    def test_audit_rule_decay_single_rule(self):
        rules = self.engine.list_rules(page_size=1).rules
        if not rules:
            self.skipTest("tenant has no custom rules")
        rep = self.engine.audit_rule_decay(rule_id=rules[0].rule_id, lookback_days=30, check_population=False)
        self.assertTrue(rep.telemetry_available, rep.telemetry_errors)
        if rep.assessments:
            self.assertTrue(rep.assessments[0].compile_checked, rep.check_errors)
            self.assertFalse(rep.assessments[0].rule_name.startswith("projects/"))


if __name__ == "__main__":
    unittest.main()
