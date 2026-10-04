"""Unit and integration tests for Unified Detection Repository Audit (rule.audit)."""

import tempfile
import unittest
from pathlib import Path

from agents.core.evidence_store import LocalFileEvidenceStore
from engine.domain import (
    RuleAuditFinding,
    RuleAuditReport,
    RuleHealthStatus,
    RuleSourceType,
)
from engine.facade import SecOpsEngine
from engine.registry import WorkflowRegistry
from engine.workflows.rule_audit import AuditRulesWorkflow
from engine.workflows.rule_conflict import synthesize_rule_summary


class TestRuleAuditModels(unittest.TestCase):
    """Verifies domain models, serialization, and aggregation for rule audits."""

    def test_rule_audit_finding_serialization(self):
        finding = RuleAuditFinding(
            rule_id="ru_1001",
            display_name="Suspicious PowerShell Encoded Command",
            rule_source=RuleSourceType.CUSTOMER.value,
            status=RuleHealthStatus.HEALTHY,
            enabled=True,
            alerting=True,
            dps_score=15.0,
            detection_count_90d=142,
            has_embedding=True,
            highest_conflict_cos=35.0,
            shadowed_by_curated_id="ur_powershell_base64",
            shadowed_by_curated_name="Google Curated PowerShell Encoded Execution",
            remediation_steps=["Review overlap with Google Curated rule."],
        )
        d = finding.to_dict()
        self.assertEqual(d["rule_id"], "ru_1001")
        self.assertEqual(d["display_name"], "Suspicious PowerShell Encoded Command")
        self.assertEqual(d["rule_source"], "CUSTOMER")
        self.assertEqual(d["status"], "HEALTHY")
        self.assertEqual(d["detection_count_90d"], 142)
        self.assertEqual(d["shadowed_by_curated_id"], "ur_powershell_base64")
        self.assertEqual(len(d["remediation_steps"]), 1)

    def test_rule_audit_report_counters_and_serialization(self):
        report = RuleAuditReport(
            total_rules_scanned=2,
            customer_rules_count=1,
            curated_rules_count=1,
            embeddings_synced_count=2,
            healthy_count=1,
            silent_decay_count=1,
            failing_count=0,
            misconfigured_count=0,
            disabled_count=0,
            conflict_count=1,
            shadowed_by_curated_count=1,
            total_detections_90d=500,
            findings=[
                RuleAuditFinding(
                    rule_id="ru_custom",
                    display_name="Custom Rule",
                    rule_source=RuleSourceType.CUSTOMER.value,
                    status=RuleHealthStatus.SILENT_DECAY,
                    enabled=True,
                    alerting=True,
                    dps_score=80.0,
                    detection_count_90d=0,
                    has_embedding=True,
                    highest_conflict_cos=82.0,
                    shadowed_by_curated_id="ur_curated",
                    shadowed_by_curated_name="Google Curated Equivalent",
                ),
                RuleAuditFinding(
                    rule_id="ur_curated",
                    display_name="Google Curated Equivalent",
                    rule_source=RuleSourceType.GOOGLE_CURATED.value,
                    status=RuleHealthStatus.HEALTHY,
                    enabled=True,
                    alerting=True,
                    dps_score=10.0,
                    detection_count_90d=500,
                    has_embedding=True,
                ),
            ],
        )
        d = report.to_dict()
        self.assertEqual(d["total_rules_scanned"], 2)
        self.assertEqual(d["customer_rules_count"], 1)
        self.assertEqual(d["curated_rules_count"], 1)
        self.assertEqual(d["shadowed_by_curated_count"], 1)
        self.assertEqual(len(d["findings"]), 2)
        self.assertEqual(d["findings"][0]["status"], "SILENT_DECAY")
        self.assertEqual(d["findings"][1]["status"], "HEALTHY")

    def test_curated_rule_summary_synthesis(self):
        curated_dict = {
            "ruleId": "ur_credential_dumping_lsass",
            "displayName": "Access to LSASS Process Memory",
            "description": "Detects attempts to access or dump memory of Local Security Authority Server Service.",
            "severity": {"severity": "HIGH"},
            "techniques": [{"id": "T1003.001", "name": "LSASS Memory"}],
        }
        summary = synthesize_rule_summary(curated_dict)
        self.assertIn("Access to LSASS Process Memory", summary)
        self.assertIn("T1003.001", summary)
        self.assertIn("HIGH", summary)


class TestRuleAuditEvidencePersistence(unittest.TestCase):
    """Verifies Evidence Fabric persistence for unified rule audit reports."""

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.store = LocalFileEvidenceStore(base_dir=Path(self.temp_dir.name))

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_save_and_retrieve_rule_audit(self):
        audit_payload = {
            "total_rules_scanned": 150,
            "customer_rules_count": 50,
            "curated_rules_count": 100,
            "embeddings_synced_count": 150,
            "healthy_count": 120,
            "silent_decay_count": 20,
            "failing_count": 2,
            "misconfigured_count": 8,
            "disabled_count": 10,
            "conflict_count": 5,
            "shadowed_by_curated_count": 3,
            "total_detections_90d": 125000,
            "findings": [
                {
                    "rule_id": "ru_test_01",
                    "rule_name": "Test Rule",
                    "rule_source": "CUSTOMER",
                    "status": "SILENT_DECAY",
                    "dps_score": 75.0,
                    "highest_conflict_cos": 88.0,
                    "shadowed_by_curated_id": "ur_test_curated",
                }
            ],
        }

        saved_id = self.store.save_rule_audit(audit_payload)
        self.assertTrue(saved_id.startswith("rule_audit_"))

        latest = self.store.get_latest_rule_audit()
        self.assertIsNotNone(latest)
        self.assertEqual(latest["total_rules_scanned"], 150)
        self.assertEqual(latest["shadowed_by_curated_count"], 3)
        self.assertEqual(len(latest["findings"]), 1)
        self.assertEqual(latest["findings"][0]["rule_id"], "ru_test_01")


class TestRuleAuditCapabilityContract(unittest.TestCase):
    """Verifies registry contracts, composition, and facade exposure for rule.audit."""

    def test_rule_audit_capability_registered(self):
        engine = SecOpsEngine()
        cap = engine.registry.get("rule.audit")
        self.assertIsNotNone(cap)
        self.assertEqual(cap.category, "rule")
        self.assertTrue(cap.composed)
        self.assertEqual(cap.mcp_tool_name, "audit_rules")
        self.assertIn("rule.list", cap.uses)
        self.assertIn("rule.deployment.list", cap.uses)
        self.assertIn("rule.embeddings.sync", cap.uses)
        self.assertIn("rule.decay.audit", cap.uses)

    def test_facade_method_exists(self):
        engine = SecOpsEngine()
        self.assertTrue(hasattr(engine, "audit_rules"))
        self.assertTrue(callable(engine.audit_rules))
