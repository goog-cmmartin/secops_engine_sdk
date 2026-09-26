"""Google ADK 2 Agent Prompt & Skill Evaluation Contract Tests.

Validates that:
1. All 12 agent manifests enforce ADK 2 prompt directives (ambiguity, conciseness).
2. The dynamic SkillCatalog parses operational runbooks from knowledge/.
3. The evaluation benchmark suite in tests/evals/test_adk_prompts.json passes with 100% score.
"""

from __future__ import annotations

import unittest
from pathlib import Path
import yaml

from agents.core.base_adk_agent import SkillCatalog
from scripts.eval_adk_prompts import run_evaluations


class TestAdkPromptAndSkillEvals(unittest.TestCase):
    def setUp(self):
        self.workspace_root = Path(__file__).resolve().parent.parent
        self.manifest_dir = self.workspace_root / "agents" / "manifests"
        self.eval_file = self.workspace_root / "tests" / "evals" / "test_adk_prompts.json"

    def test_all_manifests_contain_adk_guardrails(self):
        """Every fleet manifest must contain ambiguity guardrails and conciseness constraints."""
        manifest_files = list(self.manifest_dir.glob("*.yaml"))
        self.assertEqual(len(manifest_files), 22, "Expected exactly 22 agent manifests")

        for m_path in manifest_files:
            with open(m_path, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f)
            instruction = data.get("system_instruction", "")
            self.assertIn(
                "Ambiguity & Clarification Guardrails",
                instruction,
                f"Manifest {m_path.name} missing Ambiguity & Clarification Guardrails",
            )
            self.assertIn(
                "Output Formatting & Conciseness Constraints",
                instruction,
                f"Manifest {m_path.name} missing Output Formatting & Conciseness Constraints",
            )

    def test_skill_catalog_loads_from_knowledge(self):
        """SkillCatalog must parse operational runbooks and concepts from knowledge/."""
        sc = SkillCatalog.get_instance()
        self.assertGreaterEqual(len(sc.skills), 25, "Expected at least 25 skills in catalog")
        
        # Verify both tasks and features are loaded
        tasks = [s for s in sc.skills.values() if s.skill_type == "task"]
        features = [s for s in sc.skills.values() if s.skill_type == "feature"]
        self.assertGreaterEqual(len(tasks), 5, "Expected at least 5 operational tasks in catalog")
        self.assertGreaterEqual(len(features), 10, "Expected at least 10 features in catalog")

    def test_benchmark_evaluations_pass(self):
        """Runs the ADK 2 prompt and skill evaluation harness and asserts 100% pass."""
        exit_code = run_evaluations(self.eval_file, self.manifest_dir)
        self.assertEqual(exit_code, 0, "ADK evaluation benchmark failed")


if __name__ == "__main__":
    unittest.main()
