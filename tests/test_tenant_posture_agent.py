"""Unit and behavioral tests for TenantPostureAgent (@tenant-posture-agent)."""

from datetime import datetime, timezone
import os
from pathlib import Path
import tempfile
import unittest
from typing import Any, Dict, List, Optional

from agents.core.evidence_store import LocalFileEvidenceStore
from agents.core.proposal_manager import ProposalManager
from agents.generated.tenant_posture import TenantPostureAgent
from engine.facade import SecOpsEngine
from engine.registry import WorkflowRegistry


class _RecordingTenantSettingsAdapter:
    """Live-protocol compliant recording adapter for tenant posture and baseline testing."""

    def __init__(self):
        self.calls: List[str] = []
        self.retention_period_months: int = 12
        self.secops_ui_enabled: bool = True
        self.support_access_enabled: bool = False

    def get_tenant_instance(self) -> Dict[str, Any]:
        self.calls.append("get_tenant_instance")
        return {
            "name": "projects/test-project/locations/us/instances/test-instance",
            "displayName": "Test SecOps Instance",
            "customerCode": "PREVIEWAMERICASSDL",
            "state": "ACTIVE",
            "secopsUrls": ["https://previewamericassdl.chronicle.security.google.com"],
            "instanceConfig": {
                "secopsUiEnabled": self.secops_ui_enabled,
                "dataRbacEnabled": True,
                "triageAgentEnabled": True,
            },
        }

    def get_agent_settings(self) -> Dict[str, Any]:
        self.calls.append("get_agent_settings")
        return {
            "autoInvestigationEnabled": True,
            "alertFilter": "severity >= HIGH",
            "autoInvestigationDelay": "60s",
            "autoQuotaLimit": 100,
            "manualQuotaLimit": 50,
        }

    def get_risk_config(self) -> Dict[str, Any]:
        self.calls.append("get_risk_config")
        return {
            "defaultDetectionRiskScore": 75,
            "defaultAlertRiskScore": 60,
            "defaultWeightingFactor": 1.5,
            "defaultClosedAlertCoefficient": 0.5,
        }

    def get_managed_domain_settings(self) -> Dict[str, Any]:
        self.calls.append("get_managed_domain_settings")
        return {
            "domains": [
                {"domain": "corp.example.com", "addedTime": "2026-01-01T00:00:00Z"},
                {"domain": "internal.example.com", "addedTime": "2026-01-01T00:00:00Z"},
            ]
        }

    def list_log_processing_pipelines(self, page_size: int = 1000) -> Dict[str, Any]:
        self.calls.append("list_log_processing_pipelines")
        return {
            "logProcessingPipelines": [
                {"displayName": "Default Ingestion Pipeline", "streams": ["stream-1"], "processorsCount": 2},
            ]
        }

    def list_data_access_scopes(self, page_size: int = 1000) -> Dict[str, Any]:
        self.calls.append("list_data_access_scopes")
        return {
            "dataAccessScopes": [
                {"name": "projects/p/locations/l/instances/i/dataAccessScopes/scope-1", "displayName": "Global Scope", "description": "Global"},
            ]
        }

    def list_data_access_labels(self, page_size: int = 1000) -> Dict[str, Any]:
        self.calls.append("list_data_access_labels")
        return {
            "dataAccessLabels": [
                {"name": "projects/p/locations/l/instances/i/dataAccessLabels/label-1", "displayName": "Confidential", "description": "Confidential"},
            ]
        }

    def get_company_settings(self) -> Dict[str, Any]:
        self.calls.append("get_company_settings")
        return {
            "moduleSettingsProperties": [
                {"name": "settings/CompanyName", "displayName": "Company Name", "value": "SecOps Enterprise Corp"},
                {"name": "settings/Domain", "displayName": "Domain", "value": "secops.example.com"},
            ]
        }

    def get_data_retention_settings(self) -> Dict[str, Any]:
        self.calls.append("get_data_retention_settings")
        return {
            "moduleSettingsProperties": [
                {"name": "settings/DataRetentionPeriodInMonths", "displayName": "Data Retention", "value": str(self.retention_period_months)},
                {"name": "settings/AuditLogRetentionInMonths", "displayName": "Audit Retention", "value": "24"},
            ]
        }

    def get_email_settings_type(self) -> Dict[str, Any]:
        self.calls.append("get_email_settings_type")
        return {"use_custom": True}

    def get_email_settings(self) -> Dict[str, Any]:
        self.calls.append("get_email_settings")
        return {
            "moduleSettingsProperties": [
                {"name": "settings/SmtpServer", "displayName": "SMTP Server", "value": "smtp.example.com"},
                {"name": "settings/FromAddress", "displayName": "From Address", "value": "soar-alerts@example.com"},
            ]
        }

    def get_support_settings(self) -> Dict[str, Any]:
        self.calls.append("get_support_settings")
        return {
            "moduleSettingsProperties": [
                {"name": "settings/SupportAccessEnabled", "displayName": "Support Access Enabled", "value": "true" if self.support_access_enabled else "false"},
                {"name": "settings/DurationHours", "displayName": "Duration Hours", "value": "4"},
            ]
        }

    def get_alert_grouping_settings(self) -> Dict[str, Any]:
        self.calls.append("get_alert_grouping_settings")
        return {
            "moduleSettingsProperties": [
                {"name": "settings/GroupingEnabled", "displayName": "Grouping Enabled", "value": "true"},
                {"name": "settings/GroupingTimeWindowMinutes", "displayName": "Grouping Window", "value": "120"},
            ]
        }

    def get_case_title_settings(self) -> Dict[str, Any]:
        self.calls.append("get_case_title_settings")
        return {
            "moduleSettingsProperties": [
                {"name": "settings/CaseTitleTemplate", "displayName": "Case Title Template", "value": "[{severity}] - {alert_name} on {target_entity}"},
            ]
        }

    def list_soc_roles(self, page_size: int = 1000) -> Dict[str, Any]:
        self.calls.append("list_soc_roles")
        return {
            "socRoles": [
                {"name": "socRoles/role-1", "displayName": "Tier 1 Analyst"},
                {"name": "socRoles/role-2", "displayName": "Tier 2 Lead"},
            ]
        }

    def list_environments(self, page_size: int = 1000) -> Dict[str, Any]:
        self.calls.append("list_environments")
        return {
            "environments": [
                {"name": "environments/env-1", "displayName": "Production SOC", "system": False},
            ]
        }

    def list_remote_agents(self, page_size: int = 1000) -> Dict[str, Any]:
        self.calls.append("list_remote_agents")
        return {
            "remoteAgents": [
                {"name": "remoteAgents/agent-1", "displayName": "Corp Gateway Agent", "agentState": "CONNECTED"},
            ]
        }

    def list_soar_networks(self, page_size: int = 1000) -> Dict[str, Any]:
        self.calls.append("list_soar_networks")
        return {
            "soarNetworks": [
                {"name": "soarNetworks/net-1", "displayName": "Corp Network", "address": "10.0.0.0/8", "environments": ["Production SOC"]},
            ]
        }

    def list_soar_domains(self, page_size: int = 1000) -> Dict[str, Any]:
        self.calls.append("list_soar_domains")
        return {
            "soarDomains": [
                {"name": "soarDomains/dom-1", "displayName": "corp.example.com", "environments": ["Production SOC"]},
            ]
        }

    def list_soar_custom_lists(self, page_size: int = 1000) -> Dict[str, Any]:
        self.calls.append("list_soar_custom_lists")
        return {
            "customLists": [
                {"name": "customLists/list-1", "category": "Malicious IPs", "entityIdentifier": "198.51.100.1", "environments": ["Production SOC"]},
            ]
        }


class TenantPostureAgentTest(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root_path = Path(self.temp_dir.name)
        self.evidence_store = LocalFileEvidenceStore(base_dir=self.root_path / "evidence")
        self.proposal_manager = ProposalManager(root_dir=self.root_path)

        self.adapter = _RecordingTenantSettingsAdapter()
        self.engine = SecOpsEngine(
            adapter=self.adapter,
            custom_registry=WorkflowRegistry(),
        )

        self.agent = TenantPostureAgent(
            engine=self.engine,
            proposal_manager=self.proposal_manager,
            evidence_store=self.evidence_store,
        )

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_agent_attributes_and_tools(self):
        self.assertEqual(self.agent.handle, "@tenant-posture-agent")
        self.assertEqual(self.agent.subsystem, "configuration_governance")
        self.assertEqual(self.agent.default_stream, "governance")
        self.assertEqual(self.agent.default_topic, "tenant-posture")

        tools = self.agent.get_tools()
        tool_names = [getattr(t, "__name__", str(t)) for t in tools]
        self.assertIn("audit_tenant_posture", tool_names)
        self.assertIn("snapshot_tenant_baseline", tool_names)
        self.assertIn("detect_configuration_drift", tool_names)
        self.assertIn("query_settings_slice", tool_names)
        self.assertIn("list_historical_baselines", tool_names)

    def test_audit_tenant_posture_initial_baseline(self):
        res = self.agent.audit_tenant_posture(snapshot=True, tag="Initial-Gold")
        self.assertEqual(res["status"], "SUCCESS")
        self.assertEqual(res["tenant_id"], "PREVIEWAMERICASSDL")
        self.assertTrue(res["fingerprint"])
        self.assertTrue(res["snapshot_id"])

        drift = res["drift"]
        self.assertEqual(drift["status"], "INITIAL_BASELINE")
        self.assertFalse(drift["has_drift"])

        widget = res["widget"]
        self.assertEqual(widget["type"], "tenant_drift_card")
        self.assertEqual(widget["drift_status"], "INITIAL_BASELINE")
        self.assertEqual(widget["tag"], "Initial-Gold")

    def test_detect_configuration_drift_clean(self):
        # 1. Snapshot initial baseline
        self.agent.snapshot_tenant_baseline(tag="Baseline-v1")

        # 2. Run drift check with no changes
        res = self.agent.detect_configuration_drift()
        self.assertEqual(res["status"], "SUCCESS")
        drift = res["drift"]
        self.assertFalse(drift["has_drift"])
        self.assertEqual(drift["status"], "CLEAN")
        self.assertEqual(drift["drift_count"], 0)

    def test_detect_configuration_drift_critical(self):
        # 1. Save initial baseline
        self.agent.snapshot_tenant_baseline(tag="Baseline-Clean")

        # 2. Introduce CRITICAL configuration drift
        self.adapter.retention_period_months = 6  # Decreased retention: CRITICAL
        self.adapter.support_access_enabled = True  # Support access enabled: CRITICAL
        self.adapter.secops_ui_enabled = False  # UI disabled: CRITICAL

        # 3. Detect drift
        res = self.agent.audit_tenant_posture(snapshot=False)
        self.assertEqual(res["status"], "SUCCESS")
        drift = res["drift"]
        self.assertTrue(drift["has_drift"])
        self.assertEqual(drift["status"], "DRIFT_DETECTED")
        self.assertGreaterEqual(drift["critical_changes_count"], 3)
        self.assertIn("soar_settings", drift["subsystems_drifted"])
        self.assertIn("instance", drift["subsystems_drifted"])

        # 4. Verify widget
        widget = res["widget"]
        self.assertEqual(widget["type"], "tenant_drift_card")
        self.assertEqual(widget["drift_status"], "DRIFT_DETECTED")
        self.assertGreaterEqual(widget["critical_changes_count"], 3)

        # 5. Verify remediation todo was registered in Evidence Fabric
        todos = self.evidence_store.list_todos(assigned_to="@tenant-posture-agent")
        self.assertGreaterEqual(len(todos), 1)
        self.assertEqual(todos[0]["severity"], "CRITICAL")
        self.assertIn("Remediate Critical Tenant Drift", todos[0]["title"])

    def test_query_settings_slice(self):
        res = self.agent.query_settings_slice(section="instance")
        self.assertEqual(res["status"], "SUCCESS")
        self.assertEqual(res["section"], "instance")
        self.assertTrue(res["data"]["secops_ui_enabled"])

        # Test invalid section
        err_res = self.agent.query_settings_slice(section="invalid_sec")
        self.assertEqual(err_res["status"], "ERROR")

    def test_list_historical_baselines(self):
        self.agent.snapshot_tenant_baseline(tag="Baseline-A")
        self.agent.snapshot_tenant_baseline(tag="Baseline-B")

        baselines = self.agent.list_historical_baselines(limit=10)
        self.assertEqual(len(baselines), 2)
        tags = [b["tag"] for b in baselines]
        self.assertIn("Baseline-A", tags)
        self.assertIn("Baseline-B", tags)

    def test_anti_mock_invariants_in_generated_files(self):
        banned_terms = ["mock", "dummy", "fake", "sample_data", "sampleData", "test_data"]
        gen_path = Path("agents/generated/tenant_posture.py")
        content = gen_path.read_text()
        for term in banned_terms:
            self.assertNotIn(term, content.lower(), f"Banned term '{term}' found in production {gen_path}")


if __name__ == "__main__":
    unittest.main()
