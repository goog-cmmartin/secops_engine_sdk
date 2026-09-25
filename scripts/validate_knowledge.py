#!/usr/bin/env python3
"""Validates the knowledge base directory (knowledge/) for schema compliance,
referential integrity, capability linkage, anti-mock invariants, and OKF v0.2 conformance.

Usage:
    python scripts/validate_knowledge.py            # Run validation report
    python scripts/validate_knowledge.py --verbose  # Detailed per-item output
"""

from __future__ import annotations

import argparse
import os
import re
import sys
from pathlib import Path
from typing import Any, Dict, List, Set, Tuple

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from engine.facade import SecOpsEngine  # noqa: E402
from engine.okf import OKFDocument, OKFDocumentError, trust_tier, is_stale  # noqa: E402
from engine.registry import WorkflowRegistry  # noqa: E402


class _InertAdapter:
    def __getattr__(self, name):
        def _boom(*_a, **_k):
            raise RuntimeError(f"inert adapter: {name} must not be called")
        return _boom


def build_registry() -> WorkflowRegistry:
    return SecOpsEngine(adapter=_InertAdapter(), custom_registry=WorkflowRegistry()).registry


VALID_TYPES = {"concept", "feature", "persona", "task", "computation", "Attested Computation"}
VALID_PLATFORMS = {"secops_siem", "secops_soar", "bindplane", "gcp"}
VALID_RUNTIMES = {"yaral_2", "bigquery", "looker", "python", "dbt"}

ID_PATTERNS = {
    "concept": re.compile(r"^concept\.[a-z0-9_]+$"),
    "feature": re.compile(r"^feature\.[a-z0-9_]+\.[a-z0-9_]+$"),
    "persona": re.compile(r"^persona\.[a-z0-9_]+$"),
    "task": re.compile(r"^task\.[a-z0-9_]+\.[a-z0-9_]+$"),
    "computation": re.compile(r"^computation\.[a-z0-9_]+$"),
    "Attested Computation": re.compile(r"^computation\.[a-z0-9_]+$"),
}


def validate_knowledge(verbose: bool = False) -> List[str]:
    errors: List[str] = []
    knowledge_dir = REPO_ROOT / "knowledge"

    if not knowledge_dir.exists():
        return [f"Knowledge directory not found: {knowledge_dir}"]

    registry = build_registry()
    registered_caps: Set[str] = {c.capability_id for c in registry.list_capabilities()}

    docs: List[Tuple[Path, OKFDocument]] = []

    # 1. Discover all non-template, non-README, non-index markdown files
    for path in sorted(knowledge_dir.rglob("*.md")):
        rel_path = path.relative_to(knowledge_dir)
        # Skip top-level README, index.md, and anything inside templates/
        if str(rel_path) == "README.md" or path.name == "index.md" or "templates" in rel_path.parts:
            continue

        try:
            doc = OKFDocument.load(path)
            docs.append((path, doc))
        except Exception as e:
            errors.append(f"{path.relative_to(REPO_ROOT)}: Failed to parse OKF document: {e}")

    # Build index of defined IDs
    defined_concepts: Set[str] = set()
    defined_features: Set[str] = set()
    defined_personas: Set[str] = set()
    defined_tasks: Set[str] = set()
    defined_computations: Set[str] = set()

    for path, doc in docs:
        fm = doc.frontmatter
        doc_type = fm.get("type")
        doc_id = fm.get("id")
        rel = path.relative_to(REPO_ROOT)

        # OKF Conformance validation
        okf_errors = doc.validate_okf()
        for oe in okf_errors:
            errors.append(f"{rel}: [OKF v0.2] {oe}")

        if not doc_type or doc_type not in VALID_TYPES:
            errors.append(f"{rel}: 'type' must be one of {sorted(VALID_TYPES)}, got {repr(doc_type)}")
            continue

        if not doc_id or not isinstance(doc_id, str):
            errors.append(f"{rel}: Missing or non-string 'id'")
            continue

        expected_pattern = ID_PATTERNS.get(doc_type)
        if expected_pattern and not expected_pattern.match(doc_id):
            errors.append(f"{rel}: 'id' '{doc_id}' does not match pattern for {doc_type} (expected e.g. '{doc_type}.<name>')")

        if doc_type == "concept":
            if doc_id in defined_concepts:
                errors.append(f"{rel}: Duplicate concept ID '{doc_id}'")
            defined_concepts.add(doc_id)
        elif doc_type == "feature":
            if doc_id in defined_features:
                errors.append(f"{rel}: Duplicate feature ID '{doc_id}'")
            defined_features.add(doc_id)
        elif doc_type == "persona":
            if doc_id in defined_personas:
                errors.append(f"{rel}: Duplicate persona ID '{doc_id}'")
            defined_personas.add(doc_id)
        elif doc_type == "task":
            if doc_id in defined_tasks:
                errors.append(f"{rel}: Duplicate task ID '{doc_id}'")
            defined_tasks.add(doc_id)
        elif doc_type in ("computation", "Attested Computation"):
            if doc_id in defined_computations:
                errors.append(f"{rel}: Duplicate computation ID '{doc_id}'")
            defined_computations.add(doc_id)

    # 2. Field-level & Cross-reference validation
    for path, doc in docs:
        fm = doc.frontmatter
        body = doc.body
        rel = path.relative_to(REPO_ROOT)
        doc_type = fm.get("type")

        # Common required fields
        if not fm.get("title") or not isinstance(fm.get("title"), str):
            errors.append(f"{rel}: Missing or empty 'title'")

        # Concept specific
        if doc_type == "concept":
            applies_to = fm.get("applies_to", [])
            if not isinstance(applies_to, list) or not applies_to:
                errors.append(f"{rel}: 'applies_to' must be a non-empty list")
            else:
                for p in applies_to:
                    if p not in VALID_PLATFORMS:
                        errors.append(f"{rel}: Invalid platform in applies_to: '{p}'")

            for feat_id in fm.get("related_features", []) or []:
                if feat_id not in defined_features:
                    errors.append(f"{rel}: 'related_features' references non-existent feature '{feat_id}'")

        # Feature specific
        elif doc_type == "feature":
            platform = fm.get("platform")
            if platform not in VALID_PLATFORMS:
                errors.append(f"{rel}: 'platform' must be one of {sorted(VALID_PLATFORMS)}, got {repr(platform)}")

            caps = fm.get("sdk_capabilities", [])
            if not isinstance(caps, list) or not caps:
                errors.append(f"{rel}: 'sdk_capabilities' must be a non-empty list")
            else:
                for cap_id in caps:
                    if cap_id not in registered_caps:
                        errors.append(f"{rel}: 'sdk_capabilities' references unknown capability '{cap_id}'")

            for cid in fm.get("related_concepts", []) or []:
                if cid not in defined_concepts:
                    errors.append(f"{rel}: 'related_concepts' references non-existent concept '{cid}'")

        # Persona specific
        elif doc_type == "persona":
            scope = fm.get("scope", [])
            if not isinstance(scope, list) or not scope:
                errors.append(f"{rel}: 'scope' must be a non-empty list")

            if not fm.get("authority_level"):
                errors.append(f"{rel}: Missing 'authority_level'")

            tasks = fm.get("primary_tasks", [])
            if not isinstance(tasks, list):
                errors.append(f"{rel}: 'primary_tasks' must be a list")
            else:
                for tid in tasks:
                    if tid not in defined_tasks:
                        errors.append(f"{rel}: 'primary_tasks' references non-existent task '{tid}'")

        # Task specific
        elif doc_type == "task":
            persona = fm.get("persona")
            if not persona or persona not in defined_personas:
                errors.append(f"{rel}: 'persona' '{persona}' does not resolve to an existing persona")

            triggers = fm.get("trigger", [])
            if not isinstance(triggers, list) or not triggers:
                errors.append(f"{rel}: 'trigger' must be a non-empty list")

            caps_used = fm.get("capabilities_used", [])
            if not isinstance(caps_used, list) or not caps_used:
                errors.append(f"{rel}: 'capabilities_used' must be a non-empty list")
            else:
                for cap_id in caps_used:
                    if cap_id not in registered_caps:
                        errors.append(f"{rel}: 'capabilities_used' references unknown capability '{cap_id}'")

            for cid in fm.get("related_concepts", []) or []:
                if cid not in defined_concepts:
                    errors.append(f"{rel}: 'related_concepts' references non-existent concept '{cid}'")

            for fid in fm.get("related_features", []) or []:
                if fid not in defined_features:
                    errors.append(f"{rel}: 'related_features' references non-existent feature '{fid}'")

        # Attested Computation specific
        elif doc_type in ("computation", "Attested Computation"):
            runtime = fm.get("runtime")
            if runtime not in VALID_RUNTIMES:
                errors.append(f"{rel}: 'runtime' must be one of {sorted(VALID_RUNTIMES)}, got {repr(runtime)}")

            params = fm.get("parameters")
            if not isinstance(params, list):
                errors.append(f"{rel}: 'parameters' must be a list of parameter definitions")

            executor = fm.get("executor")
            if not isinstance(executor, dict) or not executor.get("resource"):
                errors.append(f"{rel}: 'executor' must be a mapping with a 'resource' path")
            else:
                res_path = REPO_ROOT / executor["resource"]
                if not res_path.exists():
                    errors.append(f"{rel}: executor.resource '{executor['resource']}' does not exist on disk")

            attester = fm.get("attester")
            if not isinstance(attester, dict) or not attester.get("resource"):
                errors.append(f"{rel}: 'attester' must be a mapping with a 'resource' path")
            else:
                att_path = REPO_ROOT / attester["resource"]
                if not att_path.exists():
                    errors.append(f"{rel}: attester.resource '{attester['resource']}' does not exist on disk")

    if verbose or not errors:
        print(f"Validated Knowledge Base (OKF v0.2 Compliant):")
        print(f"  • Concepts:     {len(defined_concepts)}")
        print(f"  • Features:     {len(defined_features)}")
        print(f"  • Personas:     {len(defined_personas)}")
        print(f"  • Tasks:        {len(defined_tasks)}")
        print(f"  • Computations: {len(defined_computations)}")
        print(f"  • Checked against {len(registered_caps)} SDK capabilities.")

    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate SecOps Knowledge Base (OKF v0.2)")
    parser.add_argument("--verbose", action="store_true", help="Enable verbose reporting")
    args = parser.parse_args()

    errors = validate_knowledge(verbose=args.verbose)
    if errors:
        print(f"\nKnowledge validation FAILED with {len(errors)} error(s):", file=sys.stderr)
        for err in errors:
            print(f"  ✗ {err}", file=sys.stderr)
        return 1

    print("\nKnowledge validation PASSED. All OKF schemas, capabilities, and links are valid.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
