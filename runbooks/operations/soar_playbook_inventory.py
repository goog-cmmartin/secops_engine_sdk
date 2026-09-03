#!/usr/bin/env python3
"""Google SecOps SOAR Playbook & Reusable Block Inventory Audit Runbook.

Performs a full audit and health assessment across all SOAR Playbooks and Blocks:
1. Classification: Standard Playbooks (REGULAR) vs Reusable Modular Blocks (NESTED)
2. Deployment & Execution Status: Enabled vs Disabled status
3. Execution Priority: Priority distribution (1=High/Critical, 2=Medium, 3=Low)
4. SOC Topography & Environments: Multi-tenant environment mappings
5. Category & Ownership: Category folders, creator attribution, and modification timestamps
"""

from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
import json
import sys
from typing import Any, Dict, List, Optional

from engine.domain import PlaybookSearchQuery, PlaybookType
from engine.facade import SecOpsEngine


def generate_playbook_inventory_report(
    engine: Optional[SecOpsEngine] = None,
    query: Optional[str] = None,
    category: Optional[str] = None,
    playbook_type: Optional[PlaybookType] = None,
    environment: Optional[str] = None,
    is_enabled: Optional[bool] = None,
    limit: int = 500,
) -> Dict[str, Any]:
    """Generates a complete inventory and configuration audit for SOAR Playbooks and Blocks.

    Args:
        engine: Optional SecOpsEngine instance.
        query: Optional search keyword filter.
        category: Optional category folder filter.
        playbook_type: Optional filter for REGULAR or NESTED playbooks.
        environment: Optional SOC environment filter.
        is_enabled: Optional enabled/disabled filter.
        limit: Maximum playbooks to inspect (default: 500).

    Returns:
        Structured dictionary containing executive metrics, environment distribution,
        standard playbooks, and reusable blocks.
    """
    if engine is None:
        engine = SecOpsEngine()

    batch = engine.search_playbooks(
        query=query,
        category=category,
        playbook_type=playbook_type,
        environment=environment,
        is_enabled=is_enabled,
        limit=limit,
    )

    playbooks_list: List[Dict[str, Any]] = []
    blocks_list: List[Dict[str, Any]] = []

    priority_counter: Counter[str] = Counter()
    status_counter: Counter[str] = Counter()
    env_counter: Counter[str] = Counter()
    category_counter: Counter[str] = Counter()

    for item in batch.results:
        pt_val = item.playbook_type.value if item.playbook_type else "UNKNOWN"
        is_nested = (pt_val == "NESTED")
        status_label = "ENABLED" if item.is_enabled else "DISABLED"

        status_counter[status_label] += 1
        priority_counter[f"Priority {item.priority}"] += 1
        category_counter[item.category_name or "Uncategorized"] += 1

        for env in (item.environments or ["*"]):
            env_counter[env] += 1

        created_str = item.creation_time.isoformat() if item.creation_time else None
        modified_str = item.modification_time.isoformat() if item.modification_time else None

        record: Dict[str, Any] = {
            "id": item.id,
            "identifier": item.identifier,
            "name": item.name,
            "type": pt_val,
            "is_enabled": item.is_enabled,
            "priority": item.priority,
            "category": item.category_name or "Uncategorized",
            "creator": item.creator_full_name or item.creator or "Unknown",
            "environments": item.environments or ["*"],
            "has_restricted_environments": item.has_restricted_environments,
            "is_debug_mode": item.is_debug_mode,
            "created_at": created_str,
            "modified_at": modified_str,
        }

        if is_nested:
            blocks_list.append(record)
        else:
            playbooks_list.append(record)

    total_count = len(playbooks_list) + len(blocks_list)

    return {
        "report_type": "soar_playbook_and_block_inventory",
        "retrieved_at": datetime.now(timezone.utc).isoformat(),
        "summary": {
            "total_workflows": total_count,
            "standard_playbooks": len(playbooks_list),
            "reusable_blocks": len(blocks_list),
            "enabled_count": status_counter["ENABLED"],
            "disabled_count": status_counter["DISABLED"],
            "priority_breakdown": dict(priority_counter),
            "environment_distribution": dict(env_counter),
            "category_distribution": dict(category_counter),
        },
        "standard_playbooks": playbooks_list,
        "reusable_blocks": blocks_list,
    }


def print_playbook_inventory_console(report: Dict[str, Any]) -> None:
    """Prints a formatted, human-readable summary of the playbook inventory report."""
    summary = report.get("summary", {})
    playbooks = report.get("standard_playbooks", [])
    blocks = report.get("reusable_blocks", [])

    print("\n" + "=" * 110)
    print(f"GOOGLE SECOPS SOAR PLAYBOOK & REUSABLE BLOCK AUDIT ({summary.get('total_workflows', 0)} Total Workflows)")
    print("=" * 110)
    print(f"  • Standard Playbooks (REGULAR) : {summary.get('standard_playbooks', 0)}")
    print(f"  • Reusable Blocks (NESTED)     : {summary.get('reusable_blocks', 0)}")
    print(f"  • Enabled Workflows            : {summary.get('enabled_count', 0)}")
    print(f"  • Disabled Workflows           : {summary.get('disabled_count', 0)}")
    print(f"  • Priorities                   : {summary.get('priority_breakdown', {})}")
    print(f"  • Mapped Environments          : {list(summary.get('environment_distribution', {}).keys())}")
    print("-" * 110)

    if playbooks:
        print(f"\n[+] STANDARD PLAYBOOKS ({len(playbooks)} workflows):")
        print(f"  {'STATUS':11s} {'PRI':4s} {'ID':7s} {'NAME':45s} {'CATEGORY':20s} {'ENVIRONMENTS'}")
        print("  " + "-" * 105)
        for p in playbooks:
            status_badge = "[ENABLED]" if p["is_enabled"] else "[DISABLED]"
            envs_str = ", ".join(p["environments"])
            print(f"  {status_badge:11s} P{p['priority']:<3d} {p['id']:7s} {p['name'][:43]:45s} {p['category'][:18]:20s} {envs_str}")

    if blocks:
        print(f"\n[+] REUSABLE MODULAR BLOCKS ({len(blocks)} blocks):")
        print(f"  {'STATUS':11s} {'PRI':4s} {'ID':7s} {'NAME':45s} {'CATEGORY':20s} {'ENVIRONMENTS'}")
        print("  " + "-" * 105)
        for b in blocks:
            status_badge = "[ENABLED]" if b["is_enabled"] else "[DISABLED]"
            envs_str = ", ".join(b["environments"])
            print(f"  {status_badge:11s} P{b['priority']:<3d} {b['id']:7s} {b['name'][:43]:45s} {b['category'][:18]:20s} {envs_str}")

    print("\n" + "=" * 110)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Google SecOps SOAR Playbook & Reusable Block Inventory Audit Runbook"
    )
    parser.add_argument(
        "--out",
        "-o",
        help="Optional path to output JSON report file.",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Print raw JSON output instead of formatted console report.",
    )
    parser.add_argument(
        "--type",
        "-t",
        choices=["REGULAR", "NESTED"],
        help="Filter by playbook type: REGULAR (Standard Playbooks) or NESTED (Modular Blocks).",
    )
    parser.add_argument(
        "--category",
        "-c",
        help="Filter by category folder name.",
    )
    parser.add_argument(
        "--environment",
        "-e",
        help="Filter by SOC environment name.",
    )
    parser.add_argument(
        "--enabled",
        action="store_true",
        help="Filter for enabled playbooks only.",
    )
    parser.add_argument(
        "--disabled",
        action="store_true",
        help="Filter for disabled playbooks only.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=500,
        help="Maximum workflows to retrieve (default: 500).",
    )

    args = parser.parse_args()
    engine = SecOpsEngine()

    pt = PlaybookType(args.type) if args.type else None
    is_enabled = None
    if args.enabled:
        is_enabled = True
    elif args.disabled:
        is_enabled = False

    print("\n[+] Collecting Google SecOps SOAR Playbooks, Blocks, Priorities, and Environment Mappings...")
    report = generate_playbook_inventory_report(
        engine=engine,
        category=args.category,
        playbook_type=pt,
        environment=args.environment,
        is_enabled=is_enabled,
        limit=args.limit,
    )

    if args.json:
        print(json.dumps(report, indent=2, default=str))
    else:
        print_playbook_inventory_console(report)

    if args.out:
        with open(args.out, "w", encoding="utf-8") as f:
            json.dump(report, f, indent=2, default=str)
        print(f"\n[+] Playbook inventory report written to: {args.out}")


if __name__ == "__main__":
    main()
