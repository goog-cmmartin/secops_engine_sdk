"""Unit and behavioral tests for Tenant Telemetry Cartography and Profiling workflows."""

import unittest
from engine.domain import (
    EntityGraphSource,
    IdentityFidelityMetric,
    LogSourceVolumeMetric,
    TenantTelemetryProfile,
)
from engine.workflows.tenant_profiling import TenantProfilingWorkflow
from tests.test_helpers import get_live_engine


class TestTenantProfilingDomainModels(unittest.TestCase):
    """Verifies domain model instantiation, serialization, and round-trip conversion."""

    def test_identity_fidelity_metric_model(self):
        metric = IdentityFidelityMetric(
            log_type="GCP_CLOUDAUDIT",
            principal_user_id=2476,
            principal_user_email_address=310,
            principal_user_windows_sid=1,
            principal_user_product_object_id=58,
            target_user_id=49,
            target_user_email_address=46,
            target_user_windows_sid=0,
            target_user_product_object_id=7,
        )
        data = metric.to_dict()
        self.assertEqual(data["log_type"], "GCP_CLOUDAUDIT")
        self.assertEqual(data["principal_user_id"], 2476)
        self.assertEqual(data["target_user_id"], 49)

        roundtrip = IdentityFidelityMetric.from_dict(data)
        self.assertEqual(roundtrip.log_type, "GCP_CLOUDAUDIT")
        self.assertEqual(roundtrip.principal_user_id, 2476)
        self.assertEqual(roundtrip.target_user_id, 49)

    def test_entity_graph_source_model(self):
        source = EntityGraphSource(
            log_type="GCP_THREATINTEL",
            entity_source="ENTITY_CONTEXT",
            vendor_name="Google",
            product_name="Google Threat Intelligence",
            total_entities=172558241,
            first_seen="2026-09-01",
            last_seen="2026-09-24",
        )
        data = source.to_dict()
        self.assertEqual(data["log_type"], "GCP_THREATINTEL")
        self.assertEqual(data["total_entities"], 172558241)

        roundtrip = EntityGraphSource.from_dict(data)
        self.assertEqual(roundtrip.total_entities, 172558241)
        self.assertEqual(roundtrip.vendor_name, "Google")

    def test_log_source_volume_metric_model(self):
        metric = LogSourceVolumeMetric(
            log_type="GCP_IDS",
            event_count=370594,
            earliest_event="2026-09-17",
            latest_event="2026-09-24",
        )
        data = metric.to_dict()
        self.assertEqual(data["log_type"], "GCP_IDS")
        self.assertEqual(data["event_count"], 370594)

        roundtrip = LogSourceVolumeMetric.from_dict(data)
        self.assertEqual(roundtrip.event_count, 370594)

    def test_tenant_telemetry_profile_model_and_markdown_export(self):
        profile = TenantTelemetryProfile(
            observation_window_days=7,
            identity_metrics=[
                IdentityFidelityMetric(
                    log_type="GCP_CLOUDAUDIT",
                    principal_user_id=2476,
                    principal_user_email_address=310,
                )
            ],
            graph_sources=[
                EntityGraphSource(
                    log_type="GCP_THREATINTEL",
                    entity_source="ENTITY_CONTEXT",
                    vendor_name="Google",
                    product_name="Google Threat Intelligence",
                    total_entities=172558241,
                )
            ],
            volume_metrics=[
                LogSourceVolumeMetric(
                    log_type="GCP_IDS",
                    event_count=370594,
                )
            ],
            total_events_observed=370594,
            total_graph_entities_observed=172558241,
            summary="Tenant profile benchmark test.",
        )
        data = profile.to_dict()
        self.assertEqual(data["total_events_observed"], 370594)
        self.assertEqual(data["total_graph_entities_observed"], 172558241)
        self.assertEqual(len(data["identity_metrics"]), 1)

        # Markdown Export verification
        wf = TenantProfilingWorkflow(adapter=None)
        md = wf.export_attested_computation_markdown(profile)
        self.assertIn("id: computation.tenant_telemetry_profile", md)
        self.assertIn("GCP_CLOUDAUDIT", md)
        self.assertIn("GCP_THREATINTEL", md)
        self.assertIn("GCP_IDS", md)
        self.assertIn("durability_hash", md)


class TestTenantProfilingLiveQueries(unittest.TestCase):
    """Verifies execution of GoogleSQL pipe syntax queries against live SecOps tenant."""

    def setUp(self):
        self.engine = get_live_engine()

    def test_live_identity_fidelity_survey(self):
        metrics = self.engine.get_identity_fidelity(days=7, limit=5)
        self.assertIsInstance(metrics, list)
        if metrics:
            first = metrics[0]
            self.assertIsInstance(first, IdentityFidelityMetric)
            self.assertTrue(first.log_type)
            self.assertGreaterEqual(first.principal_user_id, 0)

    def test_live_entity_graph_lineage_survey(self):
        sources = self.engine.get_entity_graph_lineage(days=7, limit=5)
        self.assertIsInstance(sources, list)
        if sources:
            first = sources[0]
            self.assertIsInstance(first, EntityGraphSource)
            self.assertTrue(first.log_type)
            self.assertGreaterEqual(first.total_entities, 0)

    def test_live_volume_pareto_survey(self):
        volumes = self.engine.get_log_source_volume_pareto(days=7, limit=5)
        self.assertIsInstance(volumes, list)
        if volumes:
            first = volumes[0]
            self.assertIsInstance(first, LogSourceVolumeMetric)
            self.assertTrue(first.log_type)
            self.assertGreater(first.event_count, 0)


if __name__ == "__main__":
    unittest.main()
