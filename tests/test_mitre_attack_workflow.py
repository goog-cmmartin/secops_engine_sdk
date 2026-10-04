"""Comprehensive Unit & Behavioral Test Suite for MITRE ATT&CK Strategic Mapping Agent."""

import json
from pathlib import Path
import shutil
import tempfile
import unittest

from engine.domain import MitreCoverageAssessment, Provenance
from engine.mitre_catalog import MitreCatalog
from agents.core.evidence_store import LocalFileEvidenceStore
from engine.workflows.mitre_attack import (
    SyncMitreRulesWorkflow,
    AnalyzeMitreCoverageWorkflow,
    GenerateMitreReportWorkflow,
)
from tests.test_helpers import get_live_engine


class MitreCatalogTest(unittest.TestCase):
    """Verifies MitreCatalog loading, normalization, and regex extraction."""

    def setUp(self):
        self.catalog = MitreCatalog.get_instance()

    def test_matrix_loaded_and_active(self):
        self.assertEqual(self.catalog.version, "18.1")
        self.assertGreaterEqual(self.catalog.total_techniques, 690)
        self.assertEqual(self.catalog.total_tactics, 14)
        self.assertIn("T1059", self.catalog.techniques)
        self.assertIn("T1059.001", self.catalog.techniques)

    def test_normalization(self):
        self.assertEqual(self.catalog.normalize_technique_id("t1059.001"), "T1059.001")
        self.assertEqual(self.catalog.normalize_technique_id("T1059_001"), "T1059.001")
        self.assertEqual(self.catalog.normalize_technique_id("  T1078  "), "T1078")

    def test_technique_lookup(self):
        tech = self.catalog.get_technique("T1059.001")
        self.assertIsNotNone(tech)
        self.assertEqual(tech.get("name"), "PowerShell")
        self.assertIn("execution", tech.get("tactics", []))

    def test_threat_profiles_loading(self):
        profiles = self.catalog.list_threat_profiles()
        self.assertGreaterEqual(len(profiles), 5)
        profile_ids = [p["profile_id"] for p in profiles]
        self.assertIn("global_baseline", profile_ids)
        self.assertIn("financial_services", profile_ids)
        self.assertIn("cloud_native", profile_ids)
        self.assertIn("ransomware_defense", profile_ids)
        self.assertIn("eu_public_finance", profile_ids)

        fin = self.catalog.get_threat_profile("financial_services")
        self.assertEqual(fin["relevant_techniques"], 120)
        self.assertIn("T1078", fin["high_risk_techniques"])

    def test_technique_extraction_regex(self):
        sample_rule_text = """
        rule suspicious_powershell_execution {
            meta:
                author = "SOC Team"
                mitre_technique = "T1059.001"
                tactic = "Execution"
                tag = "attack.t1078, attack.t1055"
            events:
                $e.metadata.event_type = "PROCESS_LAUNCH"
            condition:
                $e
        }
        """
        extracted = self.catalog.extract_techniques(sample_rule_text)
        self.assertIn("T1059.001", extracted)
        self.assertIn("T1078", extracted)
        self.assertIn("T1055", extracted)

    def test_log_source_categorization(self):
        cat_crowdstrike = self.catalog.categorize_log_type("CROWDSTRIKE_EDR")
        self.assertEqual(cat_crowdstrike, "EDR")

        cat_okta = self.catalog.categorize_log_type("OKTA")
        self.assertEqual(cat_okta, "IDENTITY")

        cat_gcp = self.catalog.categorize_log_type("GCP_CLOUDAUDIT")
        self.assertEqual(cat_gcp, "CLOUD")

        cat_zeek = self.catalog.categorize_log_type("ZEEK_DNS")
        self.assertEqual(cat_zeek, "NETWORK")

    def test_tactical_visibility_mapping(self):
        vis = self.catalog.get_tactical_visibility(["EDR", "CLOUD", "IDENTITY"])
        self.assertIn("execution", vis)
        self.assertIn("privilege-escalation", vis)
        self.assertIn("credential-access", vis)


class MitreCoverageAssessmentDomainTest(unittest.TestCase):
    """Verifies domain serialization of MitreCoverageAssessment."""

    def test_round_trip_serialization(self):
        assessment = MitreCoverageAssessment(
            profile_id="financial_services",
            profile_name="Financial Services Profile",
            coverage_score=78.5,
            total_baseline_techniques=120,
            validated_technique_count=65,
            total_rules_evaluated=45,
            enabled_rules_count=40,
            visibility_tactics_count=12,
            detection_tactics_count=10,
            visibility_gaps=["exfiltration"],
            detection_gaps=["lateral-movement"],
            blind_tactics=["command-and-control"],
            critical_techniques=["T1078.004"],
            resilient_techniques=["T1059.001", "T1078"],
            fragile_techniques=["T1055"],
            categorized_logs={"EDR": 3, "CLOUD": 5},
            score_breakdown={"raw_score": 75.0, "resilience_bonus": 3.5},
            provenance=Provenance(source="ChronicleDashboardQuery", details={"raw_query_id": "825b61da"}),
        )
        as_dict = assessment.to_dict()
        self.assertEqual(as_dict["profile_id"], "financial_services")
        self.assertEqual(as_dict["coverage_score"], 78.5)
        self.assertIn("exfiltration", as_dict["visibility_gaps"])
        self.assertIn("T1078.004", as_dict["critical_techniques"])

        restored = MitreCoverageAssessment.from_dict(as_dict)
        self.assertEqual(restored.profile_id, "financial_services")
        self.assertEqual(restored.coverage_score, 78.5)
        self.assertEqual(restored.provenance.source, "ChronicleDashboardQuery")
        self.assertEqual(restored.provenance.details.get("raw_query_id"), "825b61da")


class LocalEvidenceStoreMitreTest(unittest.TestCase):
    """Verifies rule caching and assessment persistence in LocalFileEvidenceStore."""

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.store = LocalFileEvidenceStore(root_dir=Path(self.temp_dir))

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_rule_batch_persistence_and_query(self):
        test_rules = [
            {
                "rule_id": "ru_123",
                "display_name": "PowerShell Script Block Logging",
                "enabled": True,
                "is_curated": False,
                "mitre_techniques": ["T1059.001"],
                "mitre_tactics": ["execution"],
            },
            {
                "rule_id": "ru_456",
                "display_name": "Valid Accounts Cloud Console",
                "enabled": True,
                "is_curated": True,
                "mitre_techniques": ["T1078.004"],
                "mitre_tactics": ["defense-evasion", "persistence"],
            },
        ]
        saved_count = self.store.batch_save_rule_states(test_rules)
        self.assertEqual(saved_count, 2)

        retrieved = self.store.list_rule_states(limit=10)
        self.assertEqual(len(retrieved), 2)
        r123 = self.store.get_rule_state("ru_123")
        self.assertIsNotNone(r123)
        self.assertEqual(r123["display_name"], "PowerShell Script Block Logging")
        self.assertIn("T1059.001", r123["mitre_techniques"])

    def test_assessment_persistence_and_retrieval(self):
        doc = {
            "profile_id": "global_baseline",
            "coverage_score": 64.2,
            "created_at": "2026-09-25T16:00:00Z",
        }
        assessment_id = self.store.save_mitre_assessment(doc)
        self.assertTrue(assessment_id.startswith("mitre_assess_"))

        latest = self.store.get_latest_mitre_assessment()
        self.assertIsNotNone(latest)
        self.assertEqual(latest["profile_id"], "global_baseline")
        self.assertEqual(latest["coverage_score"], 64.2)

        assessments = self.store.list_mitre_assessments()
        self.assertEqual(len(assessments), 1)


class LiveMitreWorkflowTest(unittest.TestCase):
    """End-to-end behavioral test running against live Google SecOps tenant."""

    def setUp(self):
        self.engine = get_live_engine()

    def test_list_threat_profiles(self):
        profiles = self.engine.list_mitre_threat_profiles()
        self.assertGreaterEqual(len(profiles), 5)

    def test_live_tenant_mitre_coverage_audit(self):
        """Audits live tenant telemetry & cached detection rules."""
        assessment = self.engine.analyze_mitre_coverage(
            profile_id="global_baseline",
            sync_cache_if_empty=False,  # Use existing cache or empty gracefully
            time_unit="DAY",
            time_value="7",
        )
        self.assertIsInstance(assessment, MitreCoverageAssessment)
        self.assertGreaterEqual(assessment.coverage_score, 0.0)
        self.assertLessEqual(assessment.coverage_score, 100.0)
        self.assertGreater(len(assessment.categorized_logs), 0)
        self.assertIsNotNone(assessment.provenance)
        self.assertEqual(assessment.provenance.details.get("raw_query_id"), "825b61da-751f-45c6-b08e-ba7eea249c16")

    def test_generate_mitre_report(self):
        report = self.engine.generate_mitre_report(profile_id="global_baseline")
        self.assertIn("markdown", report)
        self.assertIn("MITRE ATT&CK Strategic Coverage Report", report["markdown"])
        self.assertIn("Executive Posture Summary", report["markdown"])


if __name__ == "__main__":
    unittest.main()
