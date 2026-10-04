"""Unit and workflow tests for Rule Conflict & Overlap Agent and scoring engine."""

import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock

from agents.core.evidence_store import (
    LocalFileEvidenceStore,
    _compute_cosine_similarity,
    _is_same_rule_identity,
)
from agents.core.proposal_manager import ProposalManager
from agents.generated.rule_conflict_agent import RuleConflictAgentAgent
from engine.domain import (
    ConflictSeverityTier,
    RuleConflictPair,
    RuleConflictType,
)
from engine.workflows.rule_conflict import (
    AuditRuleConflictWorkflow,
    BatchAuditRuleConflictsWorkflow,
    FindSimilarRulesWorkflow,
    SyncRuleEmbeddingsWorkflow,
    calculate_conflict_overlap_score,
    extract_udm_fields,
    extract_yaral_sections,
    synthesize_rule_summary,
)


class TestRuleConflictFormulas(unittest.TestCase):
    """Verifies COS scoring, YARA-L parsing, and UDM extraction."""

    def test_calculate_conflict_overlap_score_weights(self):
        # 1. REDUNDANCY (+30), HIGH (+30), sim=1.0 (*40=40) => 100.0 (CRITICAL)
        score, sim_pts, type_pts, sev_pts, tier = calculate_conflict_overlap_score(
            similarity_score=1.0,
            conflict_type=RuleConflictType.REDUNDANCY,
            impact_severity="HIGH",
        )
        self.assertEqual(score, 100.0)
        self.assertEqual(tier, ConflictSeverityTier.CRITICAL)

        # 2. CONTRADICTION (+25), HIGH (+30), sim=0.8 (*40=32) => 87.0 (CRITICAL)
        score, sim_pts, type_pts, sev_pts, tier = calculate_conflict_overlap_score(
            similarity_score=0.8,
            conflict_type=RuleConflictType.CONTRADICTION,
            impact_severity="HIGH",
        )
        self.assertEqual(score, 87.0)
        self.assertEqual(tier, ConflictSeverityTier.CRITICAL)

        # 3. OVERLAP (+15), MEDIUM (+15), sim=0.7 (*40=28) => 58.0 (MODERATE)
        score, sim_pts, type_pts, sev_pts, tier = calculate_conflict_overlap_score(
            similarity_score=0.7,
            conflict_type=RuleConflictType.OVERLAP,
            impact_severity="MEDIUM",
        )
        self.assertEqual(score, 58.0)
        self.assertEqual(tier, ConflictSeverityTier.MODERATE)

        # 4. SCOPE GAPS (+5), LOW (+5), sim=0.5 (*40=20) => 30.0 (LOW / NO OVERLAP)
        score, sim_pts, type_pts, sev_pts, tier = calculate_conflict_overlap_score(
            similarity_score=0.5,
            conflict_type=RuleConflictType.SCOPE_GAPS,
            impact_severity="LOW",
        )
        self.assertEqual(score, 30.0)
        self.assertEqual(tier, ConflictSeverityTier.LOW)

    def test_synthesize_rule_summary(self):
        summary = synthesize_rule_summary({
            "rule_name": "Suspicious PowerShell Encoded Command",
            "description": "Detects suspicious powershell.exe execution with base64 encoded command arguments.",
            "severity": "HIGH",
            "raw": {"meta": {"mitre_attack": "T1059.001"}},
        })
        self.assertIn("Suspicious PowerShell Encoded Command", summary)
        self.assertIn("Detects suspicious powershell.exe", summary)
        self.assertIn("T1059.001", summary)
        self.assertIn("HIGH", summary)

    def test_extract_yaral_sections(self):
        yaral = """rule test_suspicious_login {
  meta:
    author = "SecOps Team"
    description = "Detects multiple failed logins followed by success"
    severity = "HIGH"
  events:
    $e.metadata.event_type = "USER_LOGIN"
    $e.target.user.userid = $user
    $e.security_result.action = "BLOCK"
  match:
    $user over 5m
  outcome:
    $risk_score = 75
  condition:
    #e > 3
}"""
        sections = extract_yaral_sections(yaral)
        self.assertIn("events", sections)
        self.assertIn("meta", sections)
        self.assertIn("match", sections)
        self.assertIn("outcome", sections)
        self.assertIn("condition", sections)
        self.assertIn("$e.metadata.event_type = \"USER_LOGIN\"", sections["events"])
        self.assertIn("$user over 5m", sections["match"])
        self.assertIn("#e > 3", sections["condition"])

    def test_extract_udm_fields(self):
        yaral = """
        $e1.metadata.event_type = "PROCESS_LAUNCH"
        $e1.principal.hostname = $host
        $e1.target.process.file.full_path = /powershell\\.exe/
        $e2.target.user.userid = $user
        """
        fields = extract_udm_fields(yaral)
        self.assertIn("metadata.event_type", fields)
        self.assertIn("principal.hostname", fields)
        self.assertIn("target.process.file.full_path", fields)
        self.assertIn("target.user.userid", fields)

    def test_is_same_rule_identity(self):
        # Prefix differences
        self.assertTrue(_is_same_rule_identity("ru_6cb5b1fe", "ur_6cb5b1fe"))
        self.assertTrue(_is_same_rule_identity("ur_abc-123", "ru_abc-123"))
        # Full resource path vs short ID
        self.assertTrue(_is_same_rule_identity("projects/p/locations/l/instances/i/rules/ru_test", "ru_test"))
        self.assertTrue(_is_same_rule_identity("projects/p/locations/l/instances/i/rules/ur_test", "ru_test"))
        # Truly different rules
        self.assertFalse(_is_same_rule_identity("ru_rule_alpha", "ru_rule_beta"))
        self.assertFalse(_is_same_rule_identity("ru_1111", "ru_2222"))


class TestEvidenceStoreRuleConflicts(unittest.TestCase):
    """Verifies vector storage, similarity search, and conflict audit persistence."""

    def setUp(self):
        self._tmpdir = tempfile.TemporaryDirectory()
        self.store = LocalFileEvidenceStore(root_dir=Path(self._tmpdir.name))

    def tearDown(self):
        self._tmpdir.cleanup()

    def test_cosine_similarity_math(self):
        # Identical vectors
        v1 = [1.0, 0.0, 0.0]
        v2 = [1.0, 0.0, 0.0]
        self.assertAlmostEqual(_compute_cosine_similarity(v1, v2), 1.0)

        # Orthogonal vectors
        v3 = [0.0, 1.0, 0.0]
        self.assertAlmostEqual(_compute_cosine_similarity(v1, v3), 0.0)

        # Opposite vectors
        v4 = [-1.0, 0.0, 0.0]
        self.assertAlmostEqual(_compute_cosine_similarity(v1, v4), -1.0)

        # Empty vectors
        self.assertEqual(_compute_cosine_similarity([], []), 0.0)

    def test_rule_embeddings_and_similarity_search(self):
        # Seed 3 rules
        embeddings = [
            {
                "rule_id": "ru_login_bruteforce",
                "rule_name": "Login Brute Force Attack",
                "summary": "Detects multiple failed logins from single IP",
                "embedding": [0.9, 0.1, 0.0],
                "is_live": True,
            },
            {
                "rule_id": "ru_auth_spray",
                "rule_name": "Password Spraying Campaign",
                "summary": "Detects failed authentication across multiple accounts",
                "embedding": [0.85, 0.15, 0.0],
                "is_live": True,
            },
            {
                "rule_id": "ru_cloud_crypto",
                "rule_name": "Cloud Cryptomining Binary Execution",
                "summary": "Detects xmrig mining binaries in container pods",
                "embedding": [0.0, 0.0, 0.95],
                "is_live": True,
            },
        ]
        self.store.batch_save_rule_embeddings(embeddings)

        # Query similar rules to ru_login_bruteforce
        results = self.store.find_similar_rules("ru_login_bruteforce", limit=5)
        self.assertEqual(len(results), 2)
        # Top result should be Password Spraying Campaign (high cosine similarity)
        self.assertEqual(results[0]["rule_id"], "ru_auth_spray")
        self.assertGreater(results[0]["similarity_score"], 0.95)
        # Ensure self was excluded
        self.assertNotIn("ru_login_bruteforce", [r["rule_id"] for r in results])

    def test_save_and_retrieve_rule_conflict(self):
        record = {
            "rule_id": "ru_target",
            "rule_name": "Target Rule",
            "highest_cos": 88.5,
            "severity_tier": "CRITICAL",
            "is_live": True,
            "is_silent": False,
            "conflicts": [
                {
                    "similar_rule_id": "ru_sibling",
                    "similar_rule_name": "Sibling Rule",
                    "similarity_score": 0.92,
                    "conflict_type": "REDUNDANCY",
                    "impact_severity": "HIGH",
                    "cos_score": 88.5,
                }
            ],
        }
        self.store.save_rule_conflict("ru_target", record)

        fetched = self.store.get_rule_conflict("ru_target")
        self.assertIsNotNone(fetched)
        self.assertEqual(fetched["highest_cos"], 88.5)

        # List with min_cos filter
        crit_list = self.store.list_rule_conflicts(min_cos=80.0)
        self.assertEqual(len(crit_list), 1)

        low_list = self.store.list_rule_conflicts(min_cos=95.0)
        self.assertEqual(len(low_list), 0)


class TestRuleConflictAgent(unittest.TestCase):
    """Verifies agent bindings, custom tools, and multi-agent synergy."""

    def setUp(self):
        self._tmpdir = tempfile.TemporaryDirectory()
        self.root_dir = Path(self._tmpdir.name)
        self.evidence_store = LocalFileEvidenceStore(root_dir=self.root_dir)
        self.proposal_manager = ProposalManager(root_dir=self.root_dir)

        from engine.facade import SecOpsEngine
        self.mock_adapter = MagicMock()
        self.engine = SecOpsEngine(adapter=self.mock_adapter, evidence_store=self.evidence_store)
        self.agent = RuleConflictAgentAgent(
            engine=self.engine,
            proposal_manager=self.proposal_manager,
            evidence_store=self.evidence_store,
        )

    def tearDown(self):
        self._tmpdir.cleanup()

    def test_agent_manifest_bindings(self):
        self.assertEqual(self.agent.handle, "@rule-conflict-agent")
        self.assertEqual(self.agent.default_stream, "detections")
        self.assertEqual(self.agent.default_topic, "rule-conflicts")
        self.assertIn("rule.conflict.audit", self.agent.CAPABILITIES)
        self.assertIn("rule.conflict.batch_audit", self.agent.CAPABILITIES)

        # Verify custom tools bound
        tools = self.agent.get_tools()
        tool_names = [getattr(t, "__name__", str(t)) for t in tools]
        self.assertIn("audit_rule_conflicts", tool_names)
        self.assertIn("batch_audit_rule_conflicts", tool_names)
        self.assertIn("find_similar_rules", tool_names)
        self.assertIn("sync_rule_embeddings", tool_names)
        self.assertIn("get_stored_rule_conflict", tool_names)
        self.assertIn("list_stored_rule_conflicts", tool_names)

    def test_agent_audit_rule_conflicts_tool(self):
        mock_result = MagicMock()
        mock_result.rule_id = "ru_test_abc"
        mock_result.rule_name = "Test Audit Rule"
        mock_result.highest_cos = 78.0
        mock_result.severity_tier = "CRITICAL"
        mock_result.is_live = True
        mock_result.is_silent = False
        mock_result.strategic_recommendation = "Consolidate into single parameterized rule."
        mock_conflict = RuleConflictPair(
            target_rule_id="ru_test_abc",
            target_rule_name="Test Audit Rule",
            similar_rule_id="ru_sibling_xyz",
            similar_rule_name="Sibling Rule",
            similarity_score=0.91,
            conflict_type=RuleConflictType.OVERLAP,
            impact_severity="HIGH",
            cos_score=78.0,
            events_overlap=True,
            match_overlap=True,
            condition_overlap=False,
            explanation="Significant overlap in events block.",
            consolidation_strategy="Merge match windows.",
        )
        mock_result.conflicts = [mock_conflict]

        self.engine.audit_rule_conflicts = MagicMock(return_value=mock_result)

        out = self.agent.audit_rule_conflicts("ru_test_abc", limit=5)
        self.assertEqual(out["status"], "SUCCESS")
        self.assertEqual(out["highest_cos"], 78.0)
        self.assertEqual(out["widget"]["type"], "rule_conflict_card")
        self.assertEqual(len(out["widget"]["conflicts"]), 1)
        self.assertEqual(len(self.agent.executed_tool_calls), 1)

    def test_multi_agent_silent_rule_synergy(self):
        # Save a silent rule state in evidence fabric (from Detection Decay Agent)
        self.evidence_store.save_rule_state("ru_silent_orphan", {
            "rule_id": "ru_silent_orphan",
            "rule_name": "Silent Orphaned Rule",
            "dps_score": 90,
            "decay_flags": ["SILENT"],
            "detection_count_90d": 0,
            "decay_meta": {
                "is_silent": True,
                "detection_count_90d": 0,
            },
            "is_live": True,
        })

        # Seed sibling embedding
        self.evidence_store.batch_save_rule_embeddings([
            {
                "rule_id": "ru_silent_orphan",
                "rule_name": "Silent Orphaned Rule",
                "summary": "Powershell download cradle detection",
                "embedding": [0.95, 0.05],
                "is_live": True,
            },
            {
                "rule_id": "ru_active_sibling",
                "rule_name": "Active Powershell Download",
                "summary": "Powershell web client download cradle",
                "embedding": [0.93, 0.07],
                "is_live": True,
            },
        ])

        # Instantiate Audit workflow with mock adapter and evidence store
        mock_adapter = MagicMock()
        mock_rule = MagicMock()
        mock_rule.name = "projects/p/locations/l/instances/i/rules/ru_silent_orphan"
        mock_rule.rule_name = "Silent Orphaned Rule"
        mock_rule.rule_text = "rule silent_orphan { events: $e.metadata.event_type = \"PROCESS_LAUNCH\" condition: $e }"

        mock_sibling = MagicMock()
        mock_sibling.name = "projects/p/locations/l/instances/i/rules/ru_active_sibling"
        mock_sibling.rule_name = "Active Powershell Download"
        mock_sibling.rule_text = "rule active_sibling { events: $e.metadata.event_type = \"PROCESS_LAUNCH\" condition: $e }"

        def _get_rule_side_effect(rid: str):
            if "silent" in rid:
                return mock_rule
            return mock_sibling

        mock_adapter.get_rule.side_effect = _get_rule_side_effect
        mock_adapter.list_rule_deployments.return_value = MagicMock(deployments=[])

        wf = AuditRuleConflictWorkflow(adapter=mock_adapter, store=self.evidence_store)
        report = wf.execute(rule_id="ru_silent_orphan", limit=5)

        self.assertTrue(report.is_silent)
        self.assertIn("RETIRE / ARCHIVE", report.strategic_recommendation.upper())
        self.assertIn("0 detections", report.strategic_recommendation)


if __name__ == "__main__":
    unittest.main()
