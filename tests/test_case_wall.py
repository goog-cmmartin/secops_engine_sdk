"""Acceptance and unit tests for Case Comments and Case Activity Wall (`case.list_comments` and `case.get_wall`)."""

import ast
import os
import unittest
from datetime import datetime, timezone

from engine.domain import (
    CaseCommentRecord,
    CaseWallRecord,
    CaseWallResult,
)
from engine.facade import SecOpsEngine
from engine.taxonomy import derive_cardinality, derive_domain, derive_kind
from engine.workflows.case_wall import (
    GetCaseWallWorkflow,
    ListCaseCommentsWorkflow,
    _parse_wall_description,
)
from tests.test_helpers import get_live_adapter, get_live_engine


class TestCaseWallWorkflow(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.adapter = get_live_adapter()
        cls.engine = get_live_engine(adapter=cls.adapter)

    def test_case_comments_001_live(self):
        """Validates listing comments from live SecOps case."""
        comments = self.engine.list_case_comments("104185")
        self.assertIsInstance(comments, list)
        if comments:
            first = comments[0]
            self.assertIsInstance(first, CaseCommentRecord)
            self.assertTrue(len(first.name) > 0)
            self.assertIsInstance(first.comment, str)
            if first.create_time:
                self.assertIsInstance(first.create_time, datetime)

    def test_case_wall_001_live(self):
        """Validates retrieving case activity wall records from live SecOps case."""
        wall_res = self.engine.get_case_wall("104185", limit=10)
        self.assertIsInstance(wall_res, CaseWallResult)
        self.assertEqual(wall_res.case_id, "104185")
        self.assertGreaterEqual(wall_res.total_size, 0)
        self.assertIn("workflow", wall_res.provenance)
        self.assertEqual(wall_res.provenance["workflow"], "case.get_wall")

        if wall_res.records:
            first = wall_res.records[0]
            self.assertIsInstance(first, CaseWallRecord)
            self.assertEqual(first.case_id, "104185")
            self.assertTrue(len(first.activity_type) > 0)
            self.assertTrue(len(first.description) > 0)
            if first.create_time:
                self.assertIsInstance(first.create_time, datetime)

    def test_case_wall_002_parsing_heuristics(self):
        """Validates human-readable description parsing across various wall activity types."""
        # 1. CASE_ACTION execution
        details_action = {
            "Integration": "GoogleThreatIntelligence",
            "ActionDisplayName": "Enrich IP",
            "ExecutingUser": "System",
            "Status": 0,
        }
        desc_action = _parse_wall_description("CASE_ACTION", "ACTION", details_action)
        self.assertIn("GoogleThreatIntelligence", desc_action)
        self.assertIn("Enrich IP", desc_action)
        self.assertIn("by System", desc_action)

        # 2. Stage transition
        details_stage = {"stage": "Incident", "activityDescription": "Case stage set to Incident"}
        desc_stage = _parse_wall_description("CASE_STATUS_CHANGE", "CASE_STAGE_CHANGED", details_stage)
        self.assertEqual(desc_stage, "Case stage set to Incident")

        # 3. Comment activity
        details_comment = {"comment": "Analyst escalated case for containment"}
        desc_comment = _parse_wall_description("CASE_COMMENT", "COMMENT", details_comment)
        self.assertEqual(desc_comment, "Analyst escalated case for containment")

    def test_case_wall_003_anti_mock_compliance(self):
        """Scans case_wall.py for banned mock/dummy/fake identifiers."""
        target_path = os.path.abspath(
            os.path.join(os.path.dirname(__file__), "..", "engine", "workflows", "case_wall.py")
        )
        self.assertTrue(os.path.exists(target_path), f"File {target_path} missing")

        with open(target_path, "r", encoding="utf-8") as f:
            code = f.read()

        banned_tokens = [
            "mock", "Mock", "MOCK",
            "fixture", "Fixture",
            "dummy", "Dummy",
            "fake", "Fake",
            "sampleData", "sample_data",
            "placeholderData", "placeholder_data",
            "testData", "test_data",
        ]
        for token in banned_tokens:
            self.assertNotIn(
                token,
                code,
                f"Banned mock identifier '{token}' found in engine/workflows/case_wall.py",
            )

    def test_case_wall_004_capability_contract(self):
        """Verifies capability registration and taxonomy for case.list_comments and case.get_wall."""
        engine = SecOpsEngine()
        cap_comments = engine.registry.get("case.list_comments")
        self.assertIsNotNone(cap_comments)
        self.assertEqual(cap_comments.category, "case")
        self.assertEqual(cap_comments.mcp_tool_name, "list_case_comments")
        self.assertFalse(cap_comments.composed)

        cap_wall = engine.registry.get("case.get_wall")
        self.assertIsNotNone(cap_wall)
        self.assertEqual(cap_wall.category, "case")
        self.assertEqual(cap_wall.mcp_tool_name, "get_case_wall")
        self.assertFalse(cap_wall.composed)

        # Verify taxonomy derivation
        self.assertEqual(cap_comments.kind, "query")
        self.assertEqual(cap_comments.domain, "case")
        self.assertEqual(cap_comments.cardinality, "unbounded")

        self.assertEqual(cap_wall.kind, "query")
        self.assertEqual(cap_wall.domain, "case")
        self.assertIn(cap_wall.cardinality, ("bounded", "single", "unbounded"))


if __name__ == "__main__":
    unittest.main()
