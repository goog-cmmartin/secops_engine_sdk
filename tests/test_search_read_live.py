"""Live behavioural tests for the search read fixes (read-only, small windows).

Skipped unless SECOPS_LIVE_TESTS=1 and a tenant is configured (see
tests/test_helpers.py). Calls: dashboardQueries:execute, validateQuery,
legacyFetchUdmSearchView + streamSearch, findUdmFieldValues,
translateUdmQuery, legacySearchEnterpriseWideIoCs - all read-only and allowed
by tests/live_guard.py without SECOPS_ALLOW_LIVE_WRITES.
"""

from __future__ import annotations

import unittest
from datetime import datetime, timedelta, timezone

from engine.domain import CompletenessState, LifecycleState
from engine.workflows.udm_aggregate import UdmFilterError
from tests.test_helpers import get_live_engine


class TestSearchReadLive(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.engine = get_live_engine()

    def test_aggregate_log_type_by_hour(self):
        res = self.engine.aggregate_udm(group_by=["metadata.log_type"], time_bucket="hour", lookback_hours=24, limit=1000)
        self.assertGreater(len(res.rows), 0)
        self.assertFalse(res.truncated)
        for r in res.rows:
            self.assertIsNotNone(r.bucket)
            self.assertEqual((r.bucket.minute, r.bucket.second), (0, 0))
            self.assertGreater(r.count, 0)
        keys = [(r.dims["metadata.log_type"], r.bucket) for r in res.rows]
        self.assertEqual(len(keys), len(set(keys)))

    def test_aggregate_truncation_and_two_dims(self):
        res = self.engine.aggregate_udm(group_by=["metadata.log_type"], lookback_hours=24, limit=2)
        self.assertEqual(len(res.rows), 2)
        self.assertTrue(res.truncated)
        res = self.engine.aggregate_udm(
            filter='metadata.log_type = "WINEVTLOG" OR metadata.log_type = "BRO_JSON"',
            group_by=["metadata.log_type", "metadata.event_type"], lookback_hours=6, limit=50)
        self.assertTrue({r.dims["metadata.log_type"] for r in res.rows} <= {"WINEVTLOG", "BRO_JSON"})

    def test_aggregate_repeated_and_day_bucket(self):
        res = self.engine.aggregate_udm(group_by=["principal.ip"], lookback_hours=1, limit=5)
        self.assertGreater(len(res.rows), 0)
        res = self.engine.aggregate_udm(group_by=[], time_bucket="day", lookback_hours=48, limit=5)
        for r in res.rows:
            self.assertEqual((r.bucket.hour, r.bucket.minute), (0, 0))  # UTC midnight

    def test_aggregate_rejects_injection(self):
        for bad in ('metadata.log_type = "X" |> LIMIT 1', "metadata.log_type = 'X' OR 1=1", 'raw = "x"'):
            with self.assertRaises(UdmFilterError):
                self.engine.aggregate_udm(filter=bad, lookback_hours=1, limit=1)

    def test_search_udm_totals_and_no_duplicates(self):
        s = self.engine.search_udm(
            query='metadata.event_type = "NETWORK_CONNECTION"', lookback_hours=1, limit=100,
            materialize_budget=100, include_detections=False, include_prevalence=False)
        self.assertEqual(s.lifecycle, LifecycleState.COMPLETED, s.error)
        ids = [e.get_field("metadata.id") for e in s.events]
        self.assertEqual(len(ids), len(set(ids)))
        self.assertIsNotNone(s.search_stats)
        self.assertIsNotNone(s.total_matched)
        if s.capped:
            self.assertTrue(s.aggregates_sampled)
            self.assertTrue(s.more_data_available)
            self.assertEqual(s.completeness, CompletenessState.PARTIAL)
            self.assertEqual(sum(b.count for b in s.timeline), s.total_matched)
        self.assertGreater(len(s.field_aggregations), 0)

    def test_validators(self):
        ok = self.engine.adapter.validate_query('metadata.event_type = "NETWORK_CONNECTION"')
        self.assertTrue(ok.valid)
        bad = self.engine.adapter.validate_query('metadata.event_type = = "X')
        self.assertFalse(bad.valid)
        self.assertEqual(bad.error_position["start_line"], 1)
        raw = self.engine.validate_raw_log_query('raw = "sshd"')
        self.assertTrue(raw.is_valid)
        self.assertEqual(raw.query_type, "QUERY_TYPE_RAW_LOG_QUERY")

    def test_field_values_and_translate(self):
        fv = self.engine.find_udm_field_values("NETWORK", page_size=5)
        self.assertLessEqual(len(fv.matches), 5)
        tr = self.engine.translate_udm_query("network connections from host server01 in the last hour")
        self.assertIn("server01", tr.query)
        self.assertIsNotNone(tr.time_range)

    def test_ioc_ip_search_accepts_ip(self):
        end = datetime.now(timezone.utc)
        res = self.engine.search_enterprise_iocs(
            "172.16.6.110", max_matches=5,
            start_time=(end - timedelta(days=7)).strftime("%Y-%m-%dT%H:%M:%SZ"),
            end_time=end.strftime("%Y-%m-%dT%H:%M:%SZ"))
        self.assertIsNotNone(res)  # previously HTTP 400 (IP_ADDRESS enum)


if __name__ == "__main__":
    unittest.main()
