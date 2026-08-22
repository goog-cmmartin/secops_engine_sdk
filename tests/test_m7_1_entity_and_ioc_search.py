"""Acceptance Tests for Milestone 7.1: UDM Entity Graph Search and Enterprise IoC Intelligence.

Verifies live Google SecOps API interactions, entity graph streaming, enterprise IoC matching,
entity profile summarization, and unified cross-engine entity investigation.
"""

import unittest
from engine.domain import (
    EnterpriseIocBatch,
    EnterpriseIocMatch,
    EntityInvestigationReport,
    EntitySummaryResult,
    EntityType,
    LifecycleState,
    SearchSession,
)
from engine.entity_detector import EntityCategory, detect_entity
from tests.test_helpers import get_live_engine


class TestMilestone71EntityAndIocSearch(unittest.TestCase):
    """Live acceptance tests for Milestone 7.1 Entity and IoC Search."""

    @classmethod
    def setUpClass(cls):
        cls.engine = get_live_engine()

    def test_entity_detection_contract(self):
        """Verifies local entity detection logic via engine facade."""
        res = self.engine.detect_entity("10.0.0.1")
        self.assertEqual(res.entity_type, EntityType.IP)
        self.assertEqual(res.category, EntityCategory.ASSET)
        self.assertEqual(res.graph_query, 'graph.entity.ip = "10.0.0.1"')

        res_hash = self.engine.detect_entity("f01a9a2d1e31332ed36c1a4d2839f412")
        self.assertEqual(res_hash.entity_type, EntityType.MD5)
        self.assertEqual(res_hash.category, EntityCategory.FILE)

    def test_search_entity_graph_streaming(self):
        """Verifies querying UDM entity graph (graph.entity.*) with live streaming."""
        test_sha = "C9D5DC956841E000BFD8762E2F0B48B66C79B79500E894B4EFA7FB9BA17E4E9E"
        session = self.engine.search_entity_graph(
            indicator_or_field=test_sha,
            receive_limit=10,
        )
        self.assertIsInstance(session, SearchSession)
        self.assertEqual(session.lifecycle, LifecycleState.COMPLETED)
        self.assertIn("graph.entity.file.sha256", session.request.query)
        self.assertGreaterEqual(session.received_count, 1)

    def test_search_enterprise_iocs(self):
        """Verifies querying /legacy:legacySearchEnterpriseWideIoCs with Mandiant threat intel."""
        md5_val = "f01a9a2d1e31332ed36c1a4d2839f412"
        batch = self.engine.search_enterprise_iocs(
            value=md5_val,
            value_type="HASH_MD5",
            max_matches=100,
        )
        self.assertIsInstance(batch, EnterpriseIocBatch)
        self.assertEqual(batch.searched_value, md5_val)
        self.assertEqual(batch.value_type, "HASH_MD5")
        self.assertGreaterEqual(batch.total_count, 1)
        self.assertGreaterEqual(len(batch.matches), 1)

        first_match = batch.matches[0]
        self.assertIsInstance(first_match, EnterpriseIocMatch)
        self.assertIsInstance(first_match.sources, list)
        self.assertIsInstance(first_match.categories, list)

    def test_summarize_entity(self):
        """Verifies retrieving entity summary profile and timeline via :summarizeEntity."""
        # Query entity graph first to get a valid entity record/ID
        test_sha = "C9D5DC956841E000BFD8762E2F0B48B66C79B79500E894B4EFA7FB9BA17E4E9E"
        session = self.engine.search_entity_graph(
            indicator_or_field=test_sha,
            receive_limit=1,
        )
        self.assertGreaterEqual(session.received_count, 1)
        first_event = session.events[0]
        entity_obj = first_event.get("entity", {})
        entity_meta = entity_obj.get("metadata", {})
        entity_id = entity_meta.get("entityId") or entity_meta.get("id", "")

        if entity_id:
            summary = self.engine.summarize_entity(entity_id=entity_id)
            self.assertIsInstance(summary, EntitySummaryResult)
            self.assertEqual(summary.entity_id, entity_id)
            self.assertIsInstance(summary.timeline, list)
            self.assertIsInstance(summary.prevalence, dict)

    def test_investigate_entity_composite(self):
        """Verifies end-to-end composite investigation across Graph, Events, IoCs, and Cases."""
        test_sha = "C9D5DC956841E000BFD8762E2F0B48B66C79B79500E894B4EFA7FB9BA17E4E9E"
        report = self.engine.investigate_entity(
            indicator=test_sha,
            max_events=10,
            include_cases=True,
        )
        self.assertIsInstance(report, EntityInvestigationReport)
        self.assertEqual(report.indicator, test_sha)
        self.assertEqual(report.detected_type, EntityType.SHA256.value)
        self.assertGreaterEqual(report.entity_graph_events_count, 1)


if __name__ == "__main__":
    unittest.main()
