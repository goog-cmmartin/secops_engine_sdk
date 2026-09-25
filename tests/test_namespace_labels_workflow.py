"""Unit and behavioral tests for Ingestion Labels, UDM Namespaces, and Data RBAC hygiene workflows."""

import unittest
from datetime import datetime, timezone

from engine.domain import (
    DataRbacLabelReference,
    IngestionLabelMetric,
    NamespaceLabelAnalysisReport,
    NamespaceLabelHygieneFinding,
    NamespaceMetric,
    Provenance,
    UntaggedTelemetrySummary,
)
from engine.workflows.namespace_labels import (
    AnalyzeIngestionLabelsWorkflow,
    AnalyzeNamespaceLabelsCompositeWorkflow,
    AnalyzeNamespacesWorkflow,
    AuditDataRbacAlignmentWorkflow,
    INGESTION_LABELS_QUERY,
    NAMESPACES_QUERY,
    UNTAGGED_NAMESPACES_QUERY,
    UNLABELLED_INGESTION_QUERY,
)
from tests.test_helpers import get_live_engine


class TestNamespaceLabelDomainModels(unittest.TestCase):
    """Verifies domain model instantiation, serialization, and helper properties."""

    def test_ingestion_label_metric_model(self):
        metric = IngestionLabelMetric(
            label_key="sourceUsecase",
            log_types=["WINEVTLOG", "WINDOWS_SYSMON"],
            event_count=154200,
            is_auto_generated=False,
        )
        data = metric.to_dict()
        self.assertEqual(data["label_key"], "sourceUsecase")
        self.assertEqual(len(data["log_types"]), 2)
        self.assertEqual(data["event_count"], 154200)
        self.assertFalse(data["is_auto_generated"])

    def test_namespace_metric_model(self):
        metric = NamespaceMetric(
            namespace="SDL",
            log_types=["PAN_FIREWALL", "CISCO_ASA"],
            event_count=17900000,
            is_network_rfc1918_relevant=True,
        )
        data = metric.to_dict()
        self.assertEqual(data["namespace"], "SDL")
        self.assertEqual(data["event_count"], 17900000)
        self.assertTrue(data["is_network_rfc1918_relevant"])

    def test_untagged_telemetry_summary_model(self):
        summary = UntaggedTelemetrySummary(
            log_type="GCP_CLOUDAUDIT",
            unlabelled_event_count=30000000,
            untagged_namespace_event_count=56700000,
        )
        data = summary.to_dict()
        self.assertEqual(data["log_type"], "GCP_CLOUDAUDIT")
        self.assertEqual(data["unlabelled_event_count"], 30000000)
        self.assertEqual(data["untagged_namespace_event_count"], 56700000)

    def test_data_rbac_label_reference_model(self):
        ref = DataRbacLabelReference(
            label_id="lbl-123",
            display_name="PCI Scope",
            udm_query='metadata.ingestion_labels["env"] = "pci"',
            extracted_label_keys=["env"],
            extracted_namespaces=[],
            is_telemetry_backed=True,
            status="ACTIVE_MATCH",
        )
        data = ref.to_dict()
        self.assertEqual(data["label_id"], "lbl-123")
        self.assertEqual(data["display_name"], "PCI Scope")
        self.assertEqual(data["extracted_label_keys"], ["env"])
        self.assertEqual(data["status"], "ACTIVE_MATCH")

    def test_analysis_report_serialization(self):
        report = NamespaceLabelAnalysisReport(
            lookback_window="7d",
            total_labelled_events=120000,
            total_namespaced_events=20000000,
            total_untagged_events=56000000,
            active_ingestion_labels=[
                IngestionLabelMetric(
                    label_key="workspace_ou",
                    log_types=["WORKSPACE_ALERTS"],
                    event_count=120000,
                    is_auto_generated=False,
                )
            ],
            active_namespaces=[
                NamespaceMetric(
                    namespace="ATD",
                    log_types=["PAN_FIREWALL"],
                    event_count=1600000,
                    is_network_rfc1918_relevant=True,
                )
            ],
            untagged_telemetry=[
                UntaggedTelemetrySummary(
                    log_type="GCP_CLOUDAUDIT",
                    unlabelled_event_count=30000000,
                    untagged_namespace_event_count=56000000,
                )
            ],
            data_rbac_references=[],
            findings=[
                NamespaceLabelHygieneFinding(
                    finding_id="f-001",
                    severity="HIGH",
                    category="DATA_RBAC_UNBACKED",
                    title="Data Access Label References Absent Ingestion Label",
                    description="Label 'pci' is not present in telemetry.",
                    affected_log_types=["PCI_DSS"],
                    remediation_guidance="Tag incoming forwarder feeds with label 'pci'.",
                )
            ],
            provenance=Provenance(source="test", details={}),
            generated_at=datetime.now(timezone.utc),
        )
        data = report.to_dict()
        self.assertEqual(data["lookback_window"], "7d")
        self.assertEqual(data["total_labelled_events"], 120000)
        self.assertEqual(len(data["active_ingestion_labels"]), 1)
        self.assertEqual(len(data["active_namespaces"]), 1)
        self.assertEqual(len(data["findings"]), 1)
        self.assertEqual(data["findings"][0]["severity"], "HIGH")


class TestNamespaceLabelQueries(unittest.TestCase):
    """Verifies the Chronicle GoogleSQL queries used by the workflow."""

    def test_sql_syntax_conventions(self):
        self.assertIn("metadata.ingestion_labels", INGESTION_LABELS_QUERY)
        self.assertIn("ARRAY_AGG(DISTINCT metadata.log_type)", INGESTION_LABELS_QUERY)
        self.assertIn("metadata.base_labels.namespaces", NAMESPACES_QUERY)
        self.assertIn("ARRAY_AGG(DISTINCT metadata.log_type)", NAMESPACES_QUERY)
        self.assertIn("events", UNTAGGED_NAMESPACES_QUERY)
        self.assertIn("events", UNLABELLED_INGESTION_QUERY)


class TestNamespaceLabelsLiveBehavioral(unittest.TestCase):
    """Behavioral live tests run against live Google SecOps tenant when configured."""

    def setUp(self):
        self.engine = get_live_engine()

    def test_live_analyze_ingestion_labels(self):
        labels = self.engine.analyze_ingestion_labels(lookback_days=7)
        self.assertIsInstance(labels, list)

    def test_live_analyze_namespaces(self):
        namespaces = self.engine.analyze_namespaces(lookback_days=7)
        self.assertIsInstance(namespaces, list)

    def test_live_audit_data_rbac_alignment(self):
        rbac_refs = self.engine.audit_data_rbac_alignment()
        self.assertIsInstance(rbac_refs, list)

    def test_live_analyze_labels_and_namespaces_composite(self):
        report = self.engine.analyze_labels_and_namespaces(lookback_days=7)
        self.assertIsInstance(report, NamespaceLabelAnalysisReport)
        self.assertEqual(report.lookback_window, "7d")
        self.assertIsInstance(report.active_ingestion_labels, list)
        self.assertIsInstance(report.active_namespaces, list)
        self.assertIsInstance(report.findings, list)


if __name__ == "__main__":
    unittest.main()
