#!/usr/bin/env python3
"""
ADK 2 Prompt & Skill Evaluation Harness.

Validates the SecOps multi-agent fleet against Google ADK 2 best practices:
1. Ambiguity & Clarification Guardrails (forbids parameter guessing, mandates clarification)
2. A2A Dispatcher Routing Precision
3. Dynamic Modular Skill Injection (grounded in knowledge/ runbooks)
4. Output Conciseness & Unified Diff Formatting Constraints
"""

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any, Dict, List

import yaml

# Add workspace root to sys.path
WORKSPACE_ROOT = Path(__file__).resolve().parent.parent
if str(WORKSPACE_ROOT) not in sys.path:
    sys.path.insert(0, str(WORKSPACE_ROOT))

from agents.core.base_adk_agent import SkillCatalog


def load_manifests(manifest_dir: Path) -> Dict[str, Dict[str, Any]]:
    manifests: Dict[str, Dict[str, Any]] = {}
    for path in manifest_dir.glob("*.yaml"):
        with open(path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
            handle = data.get("handle")
            if handle:
                manifests[handle] = data
    return manifests


def run_evaluations(eval_file: Path, manifest_dir: Path) -> int:
    with open(eval_file, "r", encoding="utf-8") as f:
        evals = json.load(f)

    manifests = load_manifests(manifest_dir)
    skill_catalog = SkillCatalog.get_instance()

    print("=" * 72)
    print(" Google ADK 2 Agent Prompt & Skill Evaluation Benchmark")
    print("=" * 72)
    print(f"Loaded {len(evals)} evaluation cases from {eval_file.name}")
    print(f"Loaded {len(manifests)} agent manifests from {manifest_dir.name}")
    print(f"Loaded {len(skill_catalog.skills)} modular skills from knowledge/\n")

    passed = 0
    failed = 0

    for item in evals:
        eval_id = item["eval_id"]
        category = item["category"]
        handle = item["agent_handle"]
        prompt = item["input_prompt"]
        assertions = item.get("assertions", {})

        manifest = manifests.get(handle)
        if not manifest:
            print(f"[[91mFAIL[0m] {eval_id} ({category}) - Unknown agent handle {handle}")
            failed += 1
            continue

        instruction = manifest.get("system_instruction", "")
        caps = manifest.get("capabilities", [])

        case_passed = True
        err_msg = ""

        # Category 1: Ambiguity Guardrails
        if category == "ambiguity_guardrails":
            directive = assertions.get("prompt_contains_directive")
            if directive and directive.lower() not in instruction.lower():
                case_passed = False
                err_msg = f"Missing required ambiguity directive in prompt: '{directive}'"

        # Category 2: Routing Precision
        elif category == "routing_precision":
            target = assertions.get("target_agent")
            routing_text = assertions.get("prompt_contains_routing")
            if routing_text and routing_text.lower() not in instruction.lower():
                case_passed = False
                err_msg = f"Dispatcher instruction does not contain expected routing: '{routing_text}'"
            elif target and target not in instruction:
                case_passed = False
                err_msg = f"Dispatcher instruction does not mention target agent {target}"

        # Category 3: Skill Matching
        elif category == "skill_matching":
            expected_skill = assertions.get("expected_skill_id")
            matched = skill_catalog.match_skill(prompt, caps)
            if not matched:
                case_passed = False
                err_msg = f"No skill matched prompt: '{prompt}' (expected {expected_skill})"
            elif matched.id != expected_skill:
                case_passed = False
                err_msg = f"Matched skill '{matched.id}' != expected '{expected_skill}'"

        # Category 4: Formatting Constraints
        elif category == "formatting_constraints":
            directive = assertions.get("prompt_contains_directive")
            if directive and directive.lower() not in instruction.lower():
                case_passed = False
                err_msg = f"Missing required formatting directive in prompt: '{directive}'"

        else:
            case_passed = False
            err_msg = f"Unknown category '{category}'"

        if case_passed:
            print(f"[[92mPASS[0m] {eval_id} [{category}] {handle}: {item.get('expected_behavior', '')[:60]}...")
            passed += 1
        else:
            print(f"[[91mFAIL[0m] {eval_id} [{category}] {handle}: {err_msg}")
            failed += 1

    print("\n" + "-" * 72)
    score_pct = (passed / len(evals)) * 100 if evals else 0
    print(f"Results: {passed} PASSED, {failed} FAILED across {len(evals)} benchmark evaluations.")
    print(f"Google ADK 2 Quality Score: {score_pct:.1f}%")
    print("-" * 72)

    return 0 if failed == 0 else 1


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Evaluate ADK 2 agent prompts and skills")
    parser.add_argument(
        "--eval-file",
        type=Path,
        default=WORKSPACE_ROOT / "tests" / "evals" / "test_adk_prompts.json",
        help="Path to test_adk_prompts.json",
    )
    parser.add_argument(
        "--manifest-dir",
        type=Path,
        default=WORKSPACE_ROOT / "agents" / "manifests",
        help="Path to agents/manifests/",
    )
    args = parser.parse_args()
    sys.exit(run_evaluations(args.eval_file, args.manifest_dir))
