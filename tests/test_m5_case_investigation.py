"""Authoritative Acceptance Tests for Milestone 5: Case Investigation Workspace & Mutation.

Verifies:
1. Composite Case Loading (Metadata, Alerts, Entities, Comments in parallel).
2. Entity Resolution and Deduplication across alerts.
3. Case Comment Mutation (Posting comment, immediate retrieval, strict verification).
4. Strict Error Visibility (CaseNotFoundError / invalid case handling without synthetic fallbacks).
5. Validation Rules (empty comments rejected before transmission).
6. Anti-Mock Compliance.
"""

import ast
import os
import unittest
from datetime import datetime, timezone

from adapters.google_secops import GoogleSecOpsAdapter
from engine import CasePriority, CaseStatus, SecOpsEngine


class TestMilestone5CaseInvestigation(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.adapter = GoogleSecOpsAdapter()
        cls.engine = SecOpsEngine(adapter=cls.adapter)
        cls.known_case_id = "104185"

    def test_case_inv_001_composite_case_loading(self):
        """Validates parallel composite loading of live Case 104185."""
        inv = self.engine.investigate_case(self.known_case_id)

        self.assertEqual(inv.case_id, self.known_case_id)
        self.assertTrue(len(inv.display_name) > 0)
        self.assertIn(inv.status, [CaseStatus.OPEN, CaseStatus.CLOSED])
        self.assertIn(inv.priority, [CasePriority.HIGH, CasePriority.CRITICAL, CasePriority.MEDIUM, CasePriority.LOW])
        self.assertIsNotNone(inv.create_time)

        # Assert alerts loaded
        self.assertGreaterEqual(len(inv.alerts), 1)
        alert = inv.alerts[0]
        self.assertTrue(alert.name.startswith("projects/"))
        self.assertEqual(alert.priority, "HIGH")

        # Assert entities loaded
        self.assertGreaterEqual(len(inv.entities), 1)
        entity_ids = [e.identifier for e in inv.entities]
        self.assertTrue(any("A605570555620CEA6D6BE211520525FC95A30961661780DA4CC4BAFE9864F394" in eid for eid in entity_ids))

        # Assert provenance
        self.assertIn("retrieved_at", inv.provenance)
        self.assertEqual(inv.provenance["case_id"], self.known_case_id)

    def test_case_inv_002_entity_deduplication(self):
        """Validates that involved entities are properly typed and deduplicated."""
        inv = self.engine.investigate_case(self.known_case_id)
        keys = set()
        for e in inv.entities:
            key = (e.identifier, e.entity_type)
            self.assertNotIn(key, keys, f"Duplicate entity encountered: {key}")
            keys.add(key)
            self.assertTrue(len(e.identifier) > 0)

    def test_case_inv_003_case_comment_mutation_and_retrieval(self):
        """Validates posting a real comment and verifying its appearance in the case workspace."""
        timestamp_str = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
        test_comment = f"Automated M5 verification test at {timestamp_str}"

        # 1. Post comment mutation
        created_comment = self.engine.add_case_comment(
            case_id=self.known_case_id,
            comment=test_comment,
        )

        self.assertIsNotNone(created_comment)
        self.assertEqual(created_comment.comment, test_comment)
        self.assertTrue(created_comment.name.startswith("projects/"))
        self.assertFalse(created_comment.is_deleted)

        # 2. Re-investigate case and verify comment is present in workspace
        inv = self.engine.investigate_case(self.known_case_id)
        comment_texts = [c.comment for c in inv.comments]
        self.assertIn(test_comment, comment_texts)

    def test_case_inv_004_invalid_case_strict_error_visibility(self):
        """Validates that non-existent case IDs raise explicit errors without silent fallbacks."""
        invalid_case_id = "999999999999"
        with self.assertRaises(Exception) as ctx:
            self.engine.investigate_case(invalid_case_id)
        self.assertTrue(len(str(ctx.exception)) > 0)

    def test_case_inv_005_empty_comment_validation(self):
        """Validates that empty or whitespace comments are rejected before API dispatch."""
        with self.assertRaises(ValueError):
            self.engine.add_case_comment(self.known_case_id, "")

        with self.assertRaises(ValueError):
            self.engine.add_case_comment(self.known_case_id, "   \n\t  ")

    def test_case_inv_006_anti_mock_audit(self):
        """Scans Milestone 5 implementation files to ensure zero mock identifiers."""
        m5_files = [
            os.path.abspath(os.path.join(os.path.dirname(__file__), "../engine/workflows/case_investigation.py")),
            os.path.abspath(os.path.join(os.path.dirname(__file__), "../engine/workflows/alert_investigation.py")),
            os.path.abspath(os.path.join(os.path.dirname(__file__), "../adapters/google_secops.py")),
            os.path.abspath(os.path.join(os.path.dirname(__file__), "../engine/facade.py")),
        ]
        banned_terms = ["mock", "fixture", "dummy", "fake", "placeholderdata", "sampledata"]

        for file_path in m5_files:
            self.assertTrue(os.path.exists(file_path), f"File {file_path} not found.")
            with open(file_path, "r", encoding="utf-8") as f:
                content = f.read().lower()
                for term in banned_terms:
                    self.assertNotIn(
                        term,
                        content,
                        f"Banned mock term '{term}' found in production file: {file_path}",
                    )


if __name__ == "__main__":
    unittest.main()
