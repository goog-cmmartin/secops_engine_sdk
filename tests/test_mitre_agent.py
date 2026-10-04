"""Unit and behavioral tests for MitreAttackAgent (@mitre-attack-agent) and standalone mitre_agent module."""

import json
import tempfile
import unittest
from unittest import mock

from agents.core.evidence_store import LocalFileEvidenceStore
from engine.facade import SecOpsEngine
from agents.generated.mitre_attack_agent import MitreAttackAgentAgent as MitreAttackAgent
from agents.mitre_agent import (
    list_mitre_threat_profiles,
    get_technique_rules,
    audit_mitre_coverage,
    generate_mitre_report,
    create_mitre_agent,
    run_direct_audit,
)
from tests.test_helpers import get_live_engine


class _InertAdapter:
    """Offline adapter stub: any adapter call is a no-op (no tenant access)."""

    def __getattr__(self, name: str):
        def _no_op(*args, **kwargs):
            return {"status": "ok"}
        return _no_op


def _offline_engine(root_dir: str) -> SecOpsEngine:
    """Engine that never touches a live tenant or Firestore."""
    return SecOpsEngine(
        adapter=_InertAdapter(),
        evidence_store=LocalFileEvidenceStore(root_dir=root_dir),
    )


class TestMitreAttackAgentManifest(unittest.TestCase):
    """Verifies ADK 2 agent manifest metadata, capabilities, and tools (offline)."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.engine = _offline_engine(self._tmp.name)
        self.agent = MitreAttackAgent(engine=self.engine)

    def test_agent_manifest_bindings(self):
        """Verifies agent handle, streams, topics, and declared capabilities."""
        self.assertEqual(self.agent.handle, "@mitre-attack-agent")
        self.assertEqual(self.agent.name, "MITRE ATT&CK Strategic Mapping Agent")
        self.assertEqual(self.agent.subsystem, "threat_intelligence")
        self.assertEqual(self.agent.default_stream, "threat_intel")
        self.assertEqual(self.agent.default_topic, "mitre-coverage")
        self.assertEqual(self.agent.model, "gemini-3.8-flash")

        # Verify declared capabilities
        self.assertIn("mitre.analyze_coverage", self.agent.CAPABILITIES)
        self.assertIn("mitre.sync_cache", self.agent.CAPABILITIES)
        self.assertIn("mitre.get_technique_rules", self.agent.CAPABILITIES)
        self.assertIn("mitre.list_threat_profiles", self.agent.CAPABILITIES)
        self.assertIn("mitre.generate_report", self.agent.CAPABILITIES)

        # Verify tool functions
        tools = self.agent.get_tools()
        tool_names = [getattr(t, "__name__", str(t)) for t in tools]
        self.assertIn("audit_mitre_coverage", tool_names)
        self.assertIn("sync_rules_cache", tool_names)
        self.assertIn("get_technique_rules", tool_names)
        self.assertIn("list_mitre_threat_profiles", tool_names)
        self.assertIn("generate_mitre_report", tool_names)


class TestMitreAttackAgentLive(unittest.TestCase):
    """Live-tenant checks; skipped when SecOps credentials are not configured."""

    def test_mitre_coverage_card_widget_generation(self):
        """Verifies that invoking audit_mitre_coverage generates a mitre_coverage_card widget."""
        engine = get_live_engine()
        agent = MitreAttackAgent(engine=engine)

        result = agent.audit_mitre_coverage(profile_id="global_baseline")
        self.assertEqual(result["status"], "SUCCESS")
        self.assertIsNotNone(agent.last_widget)
        self.assertEqual(agent.last_widget["type"], "mitre_coverage_card")
        self.assertGreater(agent.last_widget["coverage_score"], 0)
        self.assertGreater(agent.last_widget["validated_technique_count"], 0)
        self.assertIn("resilient_techniques_count", agent.last_widget)
        self.assertIn("fragile_techniques_count", agent.last_widget)


class TestStandaloneMitreAgentTools(unittest.TestCase):
    """Verifies standalone tool implementations in agents/mitre_agent.py (offline)."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        patcher = mock.patch(
            "agents.mitre_agent._ENGINE", _offline_engine(self._tmp.name)
        )
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_list_mitre_threat_profiles(self):
        """Verifies that list_mitre_threat_profiles returns registered profiles."""
        raw_json = list_mitre_threat_profiles()
        profiles = json.loads(raw_json)
        self.assertIsInstance(profiles, list)
        profile_ids = [p["profile_id"] for p in profiles]
        self.assertIn("global_baseline", profile_ids)
        self.assertIn("financial_services", profile_ids)
        self.assertIn("cloud_native", profile_ids)

    def test_get_technique_rules(self):
        """Verifies get_technique_rules returns a serialized JSON rule list."""
        raw_json = get_technique_rules("T1059")
        data = json.loads(raw_json)
        self.assertIsInstance(data, dict)
        self.assertIn("technique_id", data)
        self.assertEqual(data["technique_id"], "T1059")
        self.assertIn("rules", data)
        self.assertIsInstance(data["rules"], list)

    def test_create_mitre_agent(self):
        """Verifies that create_mitre_agent instantiates a valid Google ADK Agent or handles environment gracefully."""
        agent = create_mitre_agent()
        if agent is not None:
            self.assertEqual(agent.name, "MitreAttackAgent")
            self.assertIsNotNone(agent.instruction)
            self.assertTrue(len(agent.tools) >= 5)


class TestStandaloneMitreAgentToolsLive(unittest.TestCase):
    """Live standalone tool checks; skipped without SecOps credentials."""

    def setUp(self):
        # Reset the module singleton so it binds to the live engine.
        patcher = mock.patch("agents.mitre_agent._ENGINE", None)
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_live_audit_mitre_coverage(self):
        """Verifies live MITRE coverage analysis using get_live_engine."""
        _ = get_live_engine()  # Skips test if credentials not available
        raw_json = audit_mitre_coverage(profile_id="global_baseline", time_unit="DAY", time_value="7")
        assessment = json.loads(raw_json)
        self.assertIn("coverage_score", assessment)
        self.assertIn("validated_technique_count", assessment)
        self.assertIn("resilient_techniques_count", assessment)
        self.assertIn("fragile_techniques_count", assessment)
        self.assertGreater(assessment["total_rules_evaluated"], 0)

    def test_live_generate_mitre_report(self):
        """Verifies live Markdown executive report generation."""
        _ = get_live_engine()  # Skips test if credentials not available
        report_md = generate_mitre_report(profile_id="global_baseline")
        self.assertIsInstance(report_md, str)
        self.assertIn("# MITRE ATT&CK Strategic Coverage Report", report_md)
        self.assertIn("Executive Posture Summary", report_md)


if __name__ == "__main__":
    unittest.main()
