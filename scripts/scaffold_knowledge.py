#!/usr/bin/env python3
"""Scaffolds knowledge base feature files directly from the SDK WorkflowRegistry.

Groups capabilities by platform and domain, generating clean starter skeletons
with exact capability IDs, MCP tool names, and taxonomy metadata.

Usage:
    python scripts/scaffold_knowledge.py --list      # Preview files to generate
    python scripts/scaffold_knowledge.py             # Scaffold missing feature files
    python scripts/scaffold_knowledge.py --force     # Overwrite existing skeleton files
"""

from __future__ import annotations

import argparse
import sys
from collections import defaultdict
from pathlib import Path
from typing import Dict, List

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from engine.facade import SecOpsEngine  # noqa: E402
from engine.registry import WorkflowCapability, WorkflowRegistry  # noqa: E402
from scripts.validate_knowledge import _InertAdapter  # noqa: E402

# Domain to platform and feature name mapping
DOMAIN_FEATURE_MAP: Dict[str, Dict[str, str]] = {
    "feed": {
        "platform": "secops_siem",
        "file": "features/siem/feed_management.md",
        "title": "Log Feeds & Ingestion Endpoints",
        "id": "feature.siem.feed_management",
    },
    "parser": {
        "platform": "secops_siem",
        "file": "features/siem/parser_lifecycle.md",
        "title": "Log Parsers & CBN Normalization",
        "id": "feature.siem.parser_lifecycle",
    },
    "rule": {
        "platform": "secops_siem",
        "file": "features/siem/rules_engine.md",
        "title": "YARA-L Detection Rules Engine",
        "id": "feature.siem.rules_engine",
    },
    "curated_detections": {
        "platform": "secops_siem",
        "file": "features/siem/curated_detections.md",
        "title": "Google Curated Detections & Rule Tuning",
        "id": "feature.siem.curated_detections",
    },
    "data_table": {
        "platform": "secops_siem",
        "file": "features/siem/data_tables.md",
        "title": "SIEM Data Tables & Lookup Lists",
        "id": "feature.siem.data_tables",
    },
    "data_rbac": {
        "platform": "secops_siem",
        "file": "features/siem/data_rbac.md",
        "title": "SIEM Data RBAC & Scope Permissions",
        "id": "feature.siem.data_rbac",
    },
    "siem_settings": {
        "platform": "secops_siem",
        "file": "features/siem/siem_settings.md",
        "title": "SIEM Global Settings & Managed Domains",
        "id": "feature.siem.siem_settings",
    },
    "case": {
        "platform": "secops_soar",
        "file": "features/soar/case_management.md",
        "title": "SOAR Case Management & Triage",
        "id": "feature.soar.case_management",
    },
    "case_config": {
        "platform": "secops_soar",
        "file": "features/soar/case_configuration.md",
        "title": "SOAR Case Configuration & Tags",
        "id": "feature.soar.case_configuration",
    },
    "playbook": {
        "platform": "secops_soar",
        "file": "features/soar/playbooks.md",
        "title": "SOAR Playbooks & Automation Runs",
        "id": "feature.soar.playbooks",
    },
    "integration": {
        "platform": "secops_soar",
        "file": "features/soar/integrations.md",
        "title": "SOAR Connectors & Third-Party Integrations",
        "id": "feature.soar.integrations",
    },
    "soar_settings": {
        "platform": "secops_soar",
        "file": "features/soar/soar_settings.md",
        "title": "SOAR Global Settings & Environments",
        "id": "feature.soar.soar_settings",
    },
}


def scaffold_feature(
    meta: Dict[str, str],
    caps: List[WorkflowCapability],
    force: bool = False,
) -> bool:
    target_path = REPO_ROOT / "knowledge" / meta["file"]
    if target_path.exists() and not force:
        return False

    cap_ids = [c.capability_id for c in caps]
    mcp_tools = [c.mcp_tool_name for c in caps if getattr(c, "mcp_tool_name", None)]

    lines = [
        "---",
        f"id: {meta['id']}",
        f"title: \"{meta['title']}\"",
        "type: feature",
        f"platform: {meta['platform']}",
        "sdk_capabilities:",
    ]
    for cid in cap_ids:
        lines.append(f"  - {cid}")

    if mcp_tools:
        lines.append("mcp_tools:")
        for mcp in sorted(set(mcp_tools)):
            lines.append(f"  - {mcp}")

    lines.extend([
        "---",
        "",
        f"# {meta['title']}",
        "",
        "## 1. Feature Purpose & Scope",
        f"Provides programmatic operational access to {meta['title']} within {meta['platform']}.",
        "",
        "## 2. Capabilities & SDK Workflows",
    ])

    for c in caps:
        lines.extend([
            f"### `{c.capability_id}`",
            f"- **Description:** {c.description}",
            f"- **Kind:** `{c.kind}` | **Cardinality:** `{c.cardinality or 'none'}`",
            f"- **MCP Tool:** `{c.mcp_tool_name or 'none'}`",
            "",
        ])

    lines.extend([
        "## 3. Operational Invariants & Constraints",
        "- All queries returning unbounded collections require explicit filtering.",
        "- Mutation capabilities must specify non-empty payloads and valid target IDs.",
        "",
        "## 4. Telemetry & Observable Health Indicators",
        "- Correlate changes against Native Dashboards and Health Hub.",
        "",
    ])

    target_path.parent.mkdir(parents=True, exist_ok=True)
    target_path.write_text("\n".join(lines), encoding="utf-8")
    return True


def main() -> int:
    parser = argparse.ArgumentParser(description="Scaffold knowledge features from SDK registry")
    parser.add_argument("--list", action="store_true", help="List scaffoldable feature files")
    parser.add_argument("--force", action="store_true", help="Overwrite existing files")
    args = parser.parse_args()

    engine = SecOpsEngine(adapter=_InertAdapter(), custom_registry=WorkflowRegistry())
    reg = engine.registry

    by_domain: Dict[str, List[WorkflowCapability]] = defaultdict(list)
    for c in reg.list_capabilities():
        by_domain[c.domain].append(c)

    if args.list:
        print("Available Feature Domains to Scaffold:")
        for d, meta in sorted(DOMAIN_FEATURE_MAP.items()):
            caps = by_domain.get(d, [])
            path = REPO_ROOT / "knowledge" / meta["file"]
            status = "EXISTS" if path.exists() else "MISSING"
            print(f"  [{status:7}] {meta['id']:<35} -> {meta['file']} ({len(caps)} caps)")
        return 0

    scaffolded_count = 0
    for d, meta in DOMAIN_FEATURE_MAP.items():
        caps = by_domain.get(d, [])
        if not caps:
            continue
        created = scaffold_feature(meta, caps, force=args.force)
        if created:
            print(f"  ✓ Scaffolded: {meta['file']} ({len(caps)} capabilities)")
            scaffolded_count += 1
        else:
            print(f"  - Skipped (already exists): {meta['file']}")

    print(f"\nDone. Scaffolded {scaffolded_count} feature files.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
