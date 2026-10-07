"""Behavioural live tests for `case.list` (native cases collection).

Verifies against the live tenant:
1. Exact open-status filter returns only OPENED cases and a server total.
2. Open + closed totals partition the unfiltered total.
3. Environment filter (single and multiple values).
4. Priority multi-value OR filter.
5. Token pagination across pages without overlap, honouring max_results.
6. Ordering by createTime desc.
7. Invalid filter / orderBy errors propagate.
8. Capability registration and taxonomy (query / unbounded / require-filter).

Skips unless SECOPS_LIVE_TESTS=1 and a tenant is configured (tests/test_helpers.py).
"""

import unittest

from adapters.google_secops import SecOpsApiError
from engine import CaseListBatch, CaseListItem, CasePriority, CaseStatus
from engine.taxonomy import REQUIRE_FILTER_POLICY_KEY
from tests.test_helpers import get_live_adapter, get_live_engine


class TestCaseListLive(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.adapter = get_live_adapter()
        cls.engine = get_live_engine(adapter=cls.adapter)
        probe = cls.engine.list_cases(status="OPENED", max_results=1, page_size=1)
        if not probe.cases:
            raise unittest.SkipTest("Tenant has no open cases; case.list behaviour cannot be exercised.")
        cls.sample_env = probe.cases[0].environment

    def test_case_list_001_open_status_exact(self):
        batch = self.engine.list_cases(status="OPENED", max_results=50, page_size=50)
        self.assertIsInstance(batch, CaseListBatch)
        self.assertGreater(batch.total_count, 0)
        self.assertGreaterEqual(len(batch.cases), 1)
        self.assertLessEqual(len(batch.cases), 50)
        for c in batch.cases:
            self.assertIsInstance(c, CaseListItem)
            self.assertEqual(c.raw_status, "OPENED")
            self.assertEqual(c.status, CaseStatus.OPEN)
            self.assertTrue(c.case_id)
            self.assertIsNotNone(c.create_time)
            self.assertIsInstance(c.priority, CasePriority)
        self.assertEqual(batch.provenance["filter"], 'status="OPENED"')
        self.assertIn("endpoint", batch.provenance)

    def test_case_list_002_status_partition(self):
        everything = self.engine.list_cases(max_results=1, page_size=1)
        opened = self.engine.list_cases(status="OPEN", max_results=1, page_size=1)
        closed = self.engine.list_cases(status=CaseStatus.CLOSED, max_results=1, page_size=1)
        # Allow small drift: cases may be created/closed between the three calls.
        self.assertLessEqual(abs(everything.total_count - (opened.total_count + closed.total_count)), 25)

    def test_case_list_003_environment_filter(self):
        batch = self.engine.list_cases(status="OPENED", environments=self.sample_env, max_results=100)
        self.assertGreater(batch.total_count, 0)
        self.assertTrue(all(c.environment == self.sample_env for c in batch.cases))
        multi = self.engine.list_cases(
            status="OPENED", environments=[self.sample_env, "NoSuchEnvironment_case_list_test"], max_results=1, page_size=1
        )
        self.assertEqual(multi.total_count, batch.total_count)

    def test_case_list_004_priority_or(self):
        crit = self.engine.list_cases(status="OPENED", priorities="CRITICAL", max_results=1, page_size=1)
        high = self.engine.list_cases(status="OPENED", priorities=CasePriority.HIGH, max_results=1, page_size=1)
        both = self.engine.list_cases(status="OPENED", priorities=["CRITICAL", "HIGH"], max_results=200, page_size=200)
        self.assertLessEqual(abs(both.total_count - (crit.total_count + high.total_count)), 10)
        self.assertTrue(all(c.raw_priority in ("PRIORITY_CRITICAL", "PRIORITY_HIGH") for c in both.cases))

    def test_case_list_005_pagination(self):
        batch = self.engine.list_cases(status="OPENED", max_results=25, page_size=10)
        if batch.total_count < 25:
            self.skipTest("Fewer than 25 open cases; multi-page listing not exercisable.")
        self.assertEqual(len(batch.cases), 25)
        self.assertEqual(batch.provenance["pages_fetched"], 3)
        self.assertEqual(batch.provenance["page_item_counts"], [10, 10, 5])
        ids = [c.case_id for c in batch.cases]
        self.assertEqual(len(ids), len(set(ids)))
        self.assertTrue(batch.truncated)
        single = self.engine.list_cases(status="OPENED", max_results=25, page_size=25)
        self.assertEqual(ids, [c.case_id for c in single.cases])

    def test_case_list_006_order_create_desc(self):
        batch = self.engine.list_cases(status="OPENED", order_by="createTime desc", max_results=20, page_size=20)
        times = [c.create_time for c in batch.cases]
        self.assertEqual(times, sorted(times, reverse=True))

    def test_case_list_007_errors_propagate(self):
        with self.assertRaises(SecOpsApiError):
            self.engine.list_cases(filter='bogusField="x"', max_results=1, page_size=1)
        with self.assertRaises(SecOpsApiError):
            self.engine.list_cases(status="OPENED", order_by="bogusField desc", max_results=1, page_size=1)
        with self.assertRaises(ValueError):
            self.engine.list_cases(status="UNKNOWN", max_results=1)

    def test_case_list_008_registration_and_taxonomy(self):
        cap = self.engine.registry.get("case.list")
        self.assertIsNotNone(cap)
        self.assertEqual(cap.mcp_tool_name, "list_cases")
        self.assertEqual(cap.category, "case")
        self.assertEqual(cap.kind, "query")
        self.assertEqual(cap.cardinality, "unbounded")
        self.assertTrue(cap.agent.get(REQUIRE_FILTER_POLICY_KEY))
        self.assertTrue(cap.evidence_path.endswith("04_case_list_native_collection.md"))


if __name__ == "__main__":
    unittest.main()
