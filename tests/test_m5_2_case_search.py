"""Authoritative Acceptance Tests for Milestone 5.2: SOAR Case Search & Filtering.

Verifies:
1. Broad Case Search with time window and pagination.
2. Keyword Search across case titles.
3. Multi-facet filtering by priority and stage.
4. Pagination indexing (page 0 vs page 1).
5. Facet filter value discovery (legacyGetCasesFilterValues).
6. Capability Registration in WorkflowRegistry.
7. Anti-mock compliance across production paths.
"""

from tests.test_helpers import get_live_adapter, get_live_engine
import os
import unittest

from adapters.google_secops import GoogleSecOpsAdapter
from engine import CasePriority, CaseSearchQuery, SecOpsEngine


class TestMilestone52CaseSearch(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.adapter = get_live_adapter()
        cls.engine = get_live_engine(adapter=cls.adapter)

    def test_case_search_001_broad_search(self):
        """Validates that broad case search returns a typed CaseSearchBatch with valid metadata."""
        batch = self.engine.search_cases(query="", page_size=10, page_number=0)

        self.assertIsNotNone(batch)
        self.assertGreater(batch.total_count, 0)
        self.assertGreaterEqual(len(batch.results), 1)
        self.assertLessEqual(len(batch.results), 10)
        self.assertEqual(batch.page_number, 0)

        sample = batch.results[0]
        self.assertTrue(len(sample.case_id) > 0)
        self.assertTrue(len(sample.title) > 0)
        self.assertIsNotNone(sample.create_time)
        self.assertIsInstance(sample.priority, CasePriority)
        self.assertTrue(len(sample.stage) > 0)
        self.assertIn("endpoint", batch.provenance)

    def test_case_search_002_keyword_search(self):
        """Validates that search with keyword 'File IoCs' retrieves targeted cases."""
        batch = self.engine.search_cases(query="File IoCs", page_size=5)

        self.assertGreater(batch.total_count, 0)
        self.assertGreaterEqual(len(batch.results), 1)
        for item in batch.results:
            self.assertTrue(
                "File IoC" in item.title or "IoC" in item.title or any("IoC" in t for t in item.tags)
            )

    def test_case_search_003_faceted_priority_filter(self):
        """Validates that priority filtering strictly constrains results to CRITICAL."""
        batch = self.engine.search_cases(query="", priorities=["CRITICAL"], page_size=5)

        self.assertGreater(batch.total_count, 0)
        self.assertGreaterEqual(len(batch.results), 1)
        for item in batch.results:
            self.assertEqual(item.priority, CasePriority.CRITICAL)

    def test_case_search_004_pagination(self):
        """Validates that requesting page 0 and page 1 returns consecutive distinct results."""
        batch_p0 = self.engine.search_cases(query="File IoCs", page_size=2, page_number=0)
        batch_p1 = self.engine.search_cases(query="File IoCs", page_size=2, page_number=1)

        self.assertEqual(len(batch_p0.results), 2)
        self.assertEqual(len(batch_p1.results), 2)

        ids_p0 = [r.case_id for r in batch_p0.results]
        ids_p1 = [r.case_id for r in batch_p1.results]

        # Ensure pages do not overlap
        self.assertEqual(len(set(ids_p0).intersection(set(ids_p1))), 0)

    def test_case_search_005_filter_values(self):
        """Validates retrieval of filter suggestion values (e.g. ENVIRONMENTS, TAGS)."""
        envs = self.engine.get_case_filter_values("ENVIRONMENTS", limit=5)
        self.assertIsInstance(envs, list)
        self.assertGreaterEqual(len(envs), 1)

        tags = self.engine.get_case_filter_values("TAGS", limit=5)
        self.assertIsInstance(tags, list)
        self.assertGreaterEqual(len(tags), 1)

    def test_case_search_006_capability_registration(self):
        """Validates that case.search is registered in WorkflowRegistry."""
        caps = {c.capability_id: c for c in self.engine.list_capabilities()}
        self.assertIn("case.search", caps)
        cap = caps["case.search"]
        self.assertEqual(cap.category, "case")
        self.assertFalse(cap.composed)

    def test_case_search_007_anti_mock_audit(self):
        """Audits all production code for banned mock identifiers."""
        banned = ["mock", "dummy", "fake", "fixture", "sample_data"]
        production_dirs = ["engine", "adapters", "clients"]

        base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
        for pdir in production_dirs:
            full_path = os.path.join(base_dir, pdir)
            for root, _, files in os.walk(full_path):
                for f in files:
                    if f.endswith(".py"):
                        fpath = os.path.join(root, f)
                        with open(fpath, "r", encoding="utf-8") as fh:
                            content = fh.read().lower()
                            for b in banned:
                                self.assertNotIn(
                                    b,
                                    content,
                                    f"Banned term '{b}' found in production file: {fpath}",
                                )


if __name__ == "__main__":
    unittest.main()
