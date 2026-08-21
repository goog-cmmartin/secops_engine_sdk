"""Acceptance and Live Behavioral Tests for Milestone 5.12:
Preview Features & Data RBAC (Scopes, Labels, SOAR Environments).

Ensures complete compliance with AGENTS.md:
1. Production data originates strictly from live SecOpsClient/GoogleSecOpsAdapter.
2. Zero mock, fixture, dummy, fake, or synthetic data in production paths.
3. Explicit error visibility on unexpected responses or schema breaks.
4. Complete provenance and typed domain model encapsulation.
"""

import os
import unittest
from datetime import datetime

from adapters.google_secops import GoogleSecOpsAdapter
from engine.domain import (
    DataAccessLabelBatch,
    DataAccessLabelDetail,
    DataAccessLabelSummary,
    DataAccessScopeBatch,
    DataAccessScopeDetail,
    DataAccessScopeSummary,
    EnvironmentScopeBatch,
    EnvironmentScopeSummary,
    PreviewFeatureBatch,
    PreviewFeatureSummary,
)
from engine.facade import SecOpsEngine


class TestPreviewFeaturesAndDataRBAC(unittest.TestCase):
    """Live acceptance test suite for Preview Features and Data Access RBAC."""

    @classmethod
    def setUpClass(cls):
        cls.adapter = GoogleSecOpsAdapter()
        cls.engine = SecOpsEngine(adapter=cls.adapter)

    def test_01_preview_features_discovery_and_get_live(self):
        """Discovers preview features and retrieves a specific feature by ID."""
        batch = self.engine.list_preview_features()
        self.assertIsInstance(batch, PreviewFeatureBatch)
        self.assertGreater(batch.total_count, 0)
        self.assertGreater(len(batch.features), 0)
        self.assertIsInstance(batch.retrieved_at, datetime)

        # Check enabled features filter
        enabled_batch = self.engine.list_preview_features(enabled_only=True)
        self.assertIsInstance(enabled_batch, PreviewFeatureBatch)
        self.assertEqual(enabled_batch.total_count, batch.enabled_count)
        for f in enabled_batch.features:
            self.assertTrue(f.enabled)

        # Retrieve a known feature (e.g. user_sql_search_enabled)
        target_feat = batch.features[0]
        feat = self.engine.get_preview_feature(target_feat.id)
        self.assertIsInstance(feat, PreviewFeatureSummary)
        self.assertEqual(feat.id, target_feat.id)
        self.assertTrue(feat.name.startswith("projects/"))
        self.assertIsNotNone(feat.display_name)
        self.assertIsNotNone(feat.stage)

    def test_02_data_access_scopes_search_and_get_live(self):
        """Searches data access scopes and deep inspects a specific scope."""
        batch = self.engine.search_data_access_scopes()
        self.assertIsInstance(batch, DataAccessScopeBatch)
        self.assertGreater(batch.total_count, 0)
        self.assertGreater(len(batch.scopes), 0)
        self.assertIsInstance(batch.global_scope_granted, bool)

        # Keyword query filter test
        first_scope = batch.scopes[0]
        filtered = self.engine.search_data_access_scopes(query=first_scope.id)
        self.assertGreater(len(filtered.scopes), 0)
        self.assertEqual(filtered.scopes[0].id, first_scope.id)

        # Deep inspection
        detail = self.engine.get_data_access_scope(first_scope.id)
        self.assertIsInstance(detail, DataAccessScopeDetail)
        self.assertEqual(detail.summary.id, first_scope.id)
        self.assertTrue(detail.summary.name.startswith("projects/"))
        self.assertIsInstance(detail.allowed_data_access_labels, list)
        self.assertIsInstance(detail.denied_data_access_labels, list)

    def test_03_data_access_labels_search_and_get_live(self):
        """Searches data access labels and deep inspects a specific label and its UDM query."""
        batch = self.engine.search_data_access_labels()
        self.assertIsInstance(batch, DataAccessLabelBatch)
        self.assertGreater(batch.total_count, 0)
        self.assertGreater(len(batch.labels), 0)

        # Find a label (e.g. pci)
        target_label = batch.labels[0]
        detail = self.engine.get_data_access_label(target_label.id)
        self.assertIsInstance(detail, DataAccessLabelDetail)
        self.assertEqual(detail.summary.id, target_label.id)
        self.assertTrue(detail.summary.name.startswith("projects/"))
        self.assertIsNotNone(detail.summary.udm_query)
        self.assertIsNotNone(detail.summary.author)

    def test_04_soar_environment_scopes_search_live(self):
        """Searches SOAR environments and inspects bound Data Access Scopes."""
        batch = self.engine.search_environment_scopes()
        self.assertIsInstance(batch, EnvironmentScopeBatch)
        self.assertGreater(batch.total_count, 0)
        self.assertGreater(len(batch.environments), 0)

        first_env = batch.environments[0]
        self.assertIsInstance(first_env, EnvironmentScopeSummary)
        self.assertTrue(first_env.name.startswith("projects/"))
        self.assertIsNotNone(first_env.display_name)
        self.assertIsInstance(first_env.data_access_scopes, list)

    def test_05_engine_capabilities_registered(self):
        """Verifies all 7 capabilities are correctly registered in the workflow registry."""
        capabilities = {c.capability_id: c for c in self.engine.list_capabilities()}

        expected_capabilities = [
            "preview_feature.list",
            "preview_feature.get",
            "data_rbac.scope.search",
            "data_rbac.scope.get",
            "data_rbac.label.search",
            "data_rbac.label.get",
            "data_rbac.environment.search",
        ]

        for cap_id in expected_capabilities:
            self.assertIn(cap_id, capabilities, f"Capability {cap_id} missing from registry")
            cap = capabilities[cap_id]
            self.assertIsNotNone(cap.handler)
            self.assertTrue(cap.evidence_path.startswith("evidence/"))

    def test_06_anti_mock_compliance(self):
        """Scans new source files for banned synthetic data markers per AGENTS.md."""
        banned_terms = [
            "mock",
            "fixture",
            "dummy",
            "fake",
            "sampledata",
            "placeholderdata",
            "testdata",
        ]

        target_files = [
            "specs/preview_features/preview-feature-list-001.yaml",
            "specs/preview_features/preview-feature-get-001.yaml",
            "specs/data_rbac/data-access-scope-search-001.yaml",
            "specs/data_rbac/data-access-scope-get-001.yaml",
            "specs/data_rbac/data-access-label-search-001.yaml",
            "specs/data_rbac/data-access-label-get-001.yaml",
            "specs/data_rbac/environment-scope-search-001.yaml",
            "engine/workflows/preview_feature.py",
            "engine/workflows/data_rbac.py",
        ]

        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        for rel_path in target_files:
            full_path = os.path.join(base_dir, rel_path)
            self.assertTrue(os.path.exists(full_path), f"File {rel_path} does not exist")
            with open(full_path, "r", encoding="utf-8") as f:
                content = f.read().lower()
                for term in banned_terms:
                    self.assertNotIn(
                        term,
                        content,
                        f"Banned mock identifier '{term}' found in production source {rel_path}",
                    )


if __name__ == "__main__":
    unittest.main()
