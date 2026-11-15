"""Authoritative Behavioral Tests for SOAR Playbook Capabilities (Milestone 5.3).

Validates playbook category hierarchy, discovery search, multi-facet filtering,
and step DAG retrieval against live Google SecOps endpoints.
Invariants: Zero mocks, strict error visibility, live API provenance.
"""

from tests.test_helpers import get_live_adapter, get_live_engine
import os
import unittest
from typing import List

from adapters.google_secops import GoogleSecOpsAdapter
from engine import (
    PlaybookBatch,
    PlaybookCategory,
    PlaybookDetail,
    PlaybookSearchQuery,
    PlaybookSummary,
    PlaybookType,
    SecOpsEngine,
)


class TestPlaybookLiveCapabilities(unittest.TestCase):
    """Authoritative test suite for SOAR Playbook discovery and inspection."""

    @classmethod
    def setUpClass(cls):
        cls.engine = get_live_engine()
        cls.adapter = cls.engine.adapter
        all_pbs = cls.engine.search_playbooks(limit=50)
        cls.sample_playbooks = all_pbs.results

    def test_list_playbook_categories(self):
        """Validates that playbook category hierarchy is retrieved from live endpoint."""
        categories = self.engine.list_playbook_categories()
        self.assertIsInstance(categories, list)
        self.assertGreaterEqual(len(categories), 1)

        sample = categories[0]
        self.assertIsInstance(sample, PlaybookCategory)
        self.assertTrue(sample.id)
        self.assertTrue(sample.name)

        default_cat = next((c for c in categories if c.name == "Default"), None)
        if default_cat is not None:
            self.assertTrue(default_cat.is_default)

    def test_search_all_playbooks(self):
        """Validates listing/searching all playbooks returning live PlaybookSummary batches."""
        batch = self.engine.search_playbooks(limit=200)
        self.assertIsInstance(batch, PlaybookBatch)
        self.assertGreaterEqual(batch.total_count, 1)
        self.assertGreaterEqual(len(batch.results), 1)

        # Verify summary properties
        sample = batch.results[0]
        self.assertIsInstance(sample, PlaybookSummary)
        self.assertTrue(sample.id)
        self.assertTrue(sample.identifier)
        self.assertTrue(sample.name)
        self.assertIn(sample.playbook_type, [PlaybookType.REGULAR, PlaybookType.NESTED])
        self.assertIsInstance(sample.environments, list)

    def test_search_playbooks_keyword_filter(self):
        """Validates precision filtering by keyword against name and creator."""
        if not self.sample_playbooks:
            self.skipTest("No playbooks available in live tenant.")
        target = self.sample_playbooks[0]
        batch = self.engine.search_playbooks(query=target.name)
        self.assertGreaterEqual(batch.total_count, 1)
        self.assertTrue(any(p.identifier == target.identifier for p in batch.results))

    def test_search_playbooks_category_filter(self):
        """Validates filtering playbooks by category facet."""
        target = next((p for p in self.sample_playbooks if p.category_name), None)
        if not target:
            self.skipTest("No categorized playbooks available in live tenant.")
        batch_cat = self.engine.search_playbooks(category=target.category_name)
        self.assertGreaterEqual(batch_cat.total_count, 1)
        for pb in batch_cat.results:
            self.assertEqual(pb.category_name, target.category_name)

    def test_search_playbooks_type_filter(self):
        """Validates filtering playbooks by REGULAR vs NESTED type."""
        batch_reg = self.engine.search_playbooks(playbook_type=PlaybookType.REGULAR)
        for pb in batch_reg.results:
            self.assertEqual(pb.playbook_type, PlaybookType.REGULAR)

        batch_nested = self.engine.search_playbooks(playbook_type=PlaybookType.NESTED)
        for pb in batch_nested.results:
            self.assertEqual(pb.playbook_type, PlaybookType.NESTED)
        self.assertGreaterEqual(batch_reg.total_count + batch_nested.total_count, 1)

    def test_get_playbook_by_uuid(self):
        """Validates deep inspection of playbook definition, trigger, and step parameters."""
        if not self.sample_playbooks:
            self.skipTest("No playbooks available in live tenant.")
        target = self.sample_playbooks[0]
        pb = self.engine.get_playbook(target.identifier)

        self.assertIsInstance(pb, PlaybookDetail)
        self.assertEqual(pb.id, target.id)
        self.assertEqual(pb.identifier, target.identifier)
        self.assertEqual(pb.name, target.name)
        self.assertIsInstance(pb.steps, list)
        if pb.steps:
            step = pb.steps[0]
            self.assertTrue(bool(step.instance_name or step.name))
            self.assertIsInstance(step.parameters, list)

    def test_get_playbook_by_numeric_id(self):
        """Validates looking up a discovered playbook using its sequential integer ID."""
        if not self.sample_playbooks:
            self.skipTest("No playbooks available in live tenant.")
        target = self.sample_playbooks[0]
        pb = self.engine.get_playbook(target.id)
        self.assertEqual(pb.identifier, target.identifier)
        self.assertEqual(pb.name, target.name)

    def test_facade_capability_registration(self):
        """Validates that playbook capabilities are registered in the Workflow Registry."""
        caps = self.engine.list_capabilities(category="playbook")
        cap_ids = [c.capability_id for c in caps]
        self.assertIn("playbook.search", cap_ids)
        self.assertIn("playbook.get", cap_ids)
        self.assertIn("playbook.categories", cap_ids)

    def test_static_anti_mock_audit(self):
        """Validates strict compliance with no-mock invariant across playbook implementation."""
        banned_terms = ["mock", "fixture", "dummy", "fake", "sample_data", "test_data"]
        target_files = [
            "engine/workflows/playbook.py",
            "specs/playbook/playbook-search-001.yaml",
            "specs/playbook/playbook-get-001.yaml",
        ]
        base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
        for rel_path in target_files:
            full_path = os.path.join(base_dir, rel_path)
            self.assertTrue(os.path.exists(full_path), f"File missing: {rel_path}")
            with open(full_path, "r", encoding="utf-8") as f:
                content = f.read().lower()
                for term in banned_terms:
                    # Ignore comment occurrences about no-mock policy
                    lines = content.splitlines()
                    for idx, line in enumerate(lines, 1):
                        if term in line and "zero mock" not in line and "no-mock" not in line and "anti-mock" not in line and "isdebugmockdata" not in line:
                            self.fail(f"Banned term '{term}' found in {rel_path}:{idx}: {line}")


if __name__ == "__main__":
    unittest.main()
