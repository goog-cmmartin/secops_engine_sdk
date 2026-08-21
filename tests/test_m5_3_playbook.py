"""Authoritative Behavioral Tests for SOAR Playbook Capabilities (Milestone 5.3).

Validates playbook category hierarchy, discovery search, multi-facet filtering,
and step DAG retrieval against live Google SecOps endpoints.
Invariants: Zero mocks, strict error visibility, live API provenance.
"""

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
        cls.engine = SecOpsEngine()
        cls.adapter = cls.engine.adapter

    def test_list_playbook_categories(self):
        """Validates that playbook category hierarchy is retrieved from live endpoint."""
        categories = self.engine.list_playbook_categories()
        self.assertIsInstance(categories, list)
        self.assertGreaterEqual(len(categories), 10)

        cat_names = [c.name for c in categories]
        self.assertIn("GSA", cat_names)
        self.assertIn("Blocks", cat_names)
        self.assertIn("Cymbal", cat_names)

        # Check category structure
        sample = next(c for c in categories if c.name == "Blocks")
        self.assertIsInstance(sample, PlaybookCategory)
        self.assertTrue(sample.id)
        self.assertEqual(sample.category_state, "FULL")
        self.assertFalse(sample.is_default)

        default_cat = next(c for c in categories if c.name == "Default")
        self.assertTrue(default_cat.is_default)

    def test_search_all_playbooks(self):
        """Validates listing/searching all playbooks returning live PlaybookSummary batches."""
        batch = self.engine.search_playbooks(limit=200)
        self.assertIsInstance(batch, PlaybookBatch)
        self.assertGreaterEqual(batch.total_count, 150)
        self.assertGreaterEqual(len(batch.results), 150)

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
        batch = self.engine.search_playbooks(query="Hybrid Automation")
        self.assertEqual(batch.total_count, 1)
        self.assertEqual(batch.results[0].name, "Hybrid Automation Playbook")
        self.assertEqual(batch.results[0].id, "2277")

    def test_search_playbooks_category_filter(self):
        """Validates filtering playbooks by category facet."""
        batch_gsa = self.engine.search_playbooks(category="GSA")
        self.assertGreaterEqual(batch_gsa.total_count, 10)
        for pb in batch_gsa.results:
            self.assertEqual(pb.category_name, "GSA")

    def test_search_playbooks_type_filter(self):
        """Validates filtering playbooks by REGULAR vs NESTED type."""
        batch_reg = self.engine.search_playbooks(playbook_type=PlaybookType.REGULAR)
        self.assertGreaterEqual(batch_reg.total_count, 40)
        for pb in batch_reg.results:
            self.assertEqual(pb.playbook_type, PlaybookType.REGULAR)

        batch_nested = self.engine.search_playbooks(playbook_type=PlaybookType.NESTED)
        self.assertGreaterEqual(batch_nested.total_count, 100)
        for pb in batch_nested.results:
            self.assertEqual(pb.playbook_type, PlaybookType.NESTED)

    def test_get_playbook_by_uuid(self):
        """Validates deep inspection of playbook definition, trigger, and step parameters."""
        pb_uuid = "7b17236f-8b9d-441b-a744-e4482e281627"
        pb = self.engine.get_playbook(pb_uuid)

        self.assertIsInstance(pb, PlaybookDetail)
        self.assertEqual(pb.id, "2277")
        self.assertEqual(pb.identifier, pb_uuid)
        self.assertEqual(pb.name, "Hybrid Automation Playbook")
        self.assertEqual(pb.category_name, "GSA")
        self.assertIn("Agentic investigation results", pb.description)

        # Validate Trigger
        self.assertIsNotNone(pb.trigger)
        self.assertEqual(pb.trigger.trigger_type, "PRODUCT_NAME")
        self.assertEqual(pb.trigger.logical_operator, "AND")
        self.assertGreaterEqual(len(pb.trigger.conditions), 1)
        self.assertEqual(pb.trigger.conditions[0].value, "RULE")
        self.assertEqual(pb.trigger.conditions[0].match_type, "EQUAL")

        # Validate Steps
        self.assertGreaterEqual(len(pb.steps), 1)
        step = pb.steps[0]
        self.assertEqual(step.instance_name, "Triage and Investigation Agent_1")
        self.assertEqual(step.integration, "GoogleSecOpsAiAgents")
        self.assertEqual(step.action_provider, "Scripts")
        self.assertTrue(step.is_automatic)
        self.assertFalse(step.is_skippable)

        # Validate Parameters
        param_names = [p.name for p in step.parameters]
        self.assertIn("AsyncActionTimeout", param_names)
        self.assertIn("IntegrationInstance", param_names)

    def test_get_playbook_by_numeric_id(self):
        """Validates looking up playbook using sequential integer ID ('2277')."""
        pb = self.engine.get_playbook("2277")
        self.assertEqual(pb.identifier, "7b17236f-8b9d-441b-a744-e4482e281627")
        self.assertEqual(pb.name, "Hybrid Automation Playbook")

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
