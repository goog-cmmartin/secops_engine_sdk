#!/usr/bin/env python3
"""Google Chronicle SIEM Data Table Schema & Inventory Audit Runbook.

Collects and audits all Data Tables across the tenant:
1. Table identity: Table ID, Resource Name, Display Name, Description
2. Lifecycle: Creation time, Last updated time, Row TTL
3. Schema: Column names, Column types, Key column designations
4. Scope & Ownership: RBAC scope metadata and data access labels
5. Telemetry & Rules: Approximate row counts and associated YARA-L detection rules
"""

from __future__ import annotations

import argparse
import json
import sys
from typing import Any, Dict, List, Optional

from engine.facade import SecOpsEngine


def generate_data_table_inventory_report(
    engine: Optional[SecOpsEngine] = None,
    page_size: int = 100,
) -> Dict[str, Any]:
    """Generates a complete schema, metadata, and lifecycle audit for all Data Tables.

    Args:
        engine: Optional SecOpsEngine instance.
        page_size: Maximum tables to retrieve per page.

    Returns:
        Structured dictionary containing total count and full table inventory.
    """
    if engine is None:
        engine = SecOpsEngine()

    result = engine.list_data_tables(page_size=page_size)
    tables = result.data_tables

    inventory_items: List[Dict[str, Any]] = []

    for dt in tables:
        columns: List[Dict[str, Any]] = []
        for col in dt.column_info:
            columns.append({
                "column_index": col.column_index,
                "column_name": col.column_name,
                "data_type": col.data_type,
                "is_key_column": col.is_key_column,
                "repeated_values": col.repeated_values,
                "mapped_column_path": col.mapped_column_path,
            })

        item: Dict[str, Any] = {
            "table_id": dt.table_id,
            "display_name": dt.display_name,
            "description": dt.description or None,
            "resource_name": dt.name,
            "row_time_to_live": dt.row_time_to_live or None,
            "scope_info": dt.scope_info or None,
            "data_table_uuid": dt.data_table_uuid or None,
            "approximate_row_count": dt.approximate_row_count,
            "rule_associations_count": dt.rule_associations_count or len(dt.rules),
            "rules": dt.rules,
            "create_time": dt.create_time.isoformat() if dt.create_time else None,
            "update_time": dt.update_time.isoformat() if dt.update_time else None,
            "column_count": len(columns),
            "columns": columns,
        }
        inventory_items.append(item)

    return {
        "report_type": "chronicle_siem_data_table_inventory",
        "total_tables": len(inventory_items),
        "data_tables": inventory_items,
    }


def print_data_table_inventory_console(report: Dict[str, Any]) -> None:
    """Prints a human-readable summary of the data table inventory report."""
    total = report.get("total_tables", 0)
    tables = report.get("data_tables", [])

    print("\n" + "=" * 95)
    print(f"GOOGLE CHRONICLE SIEM DATA TABLE INVENTORY ({total} Tables)")
    print("=" * 95)

    if not tables:
        print("  No Data Tables found in tenant.")
        return

    for idx, dt in enumerate(tables, 1):
        print(f"\n[{idx}] {dt['display_name']} (ID: {dt['table_id']})")
        print(f"    Description : {dt['description'] or 'N/A'}")
        print(f"    Resource    : {dt['resource_name']}")
        print(f"    Created At  : {dt['create_time'] or 'N/A'}")
        print(f"    Last Updated: {dt['update_time'] or 'N/A'}")
        print(f"    TTL         : {dt['row_time_to_live'] or 'None'}")
        print(f"    Scope/Owner : {dt['scope_info'] or 'Global / Default'}")
        if dt.get("rule_associations_count"):
            print(f"    Rules ({dt['rule_associations_count']}): {', '.join(dt.get('rules', [])[:3])}")

        print(f"    Columns ({dt['column_count']}):")
        for col in dt.get("columns", []):
            key_flag = " [KEY]" if col.get("is_key_column") else ""
            rep_flag = " [REPEATED]" if col.get("repeated_values") else ""
            print(f"      - {col['column_name']:28s} {col['data_type']:15s}{key_flag}{rep_flag}")

    print("\n" + "=" * 95)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Google Chronicle SIEM Data Table Schema & Inventory Audit Runbook"
    )
    parser.add_argument(
        "--out",
        "-o",
        help="Optional path to output JSON report file.",
    )
    parser.add_argument(
        "--page-size",
        type=int,
        default=100,
        help="Maximum tables to retrieve (default: 100).",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Print raw JSON to stdout instead of formatted table view.",
    )
    args = parser.parse_args()

    engine = SecOpsEngine()
    print("[*] Generating Chronicle SIEM Data Table Inventory Audit Report...", file=sys.stderr)
    report = generate_data_table_inventory_report(engine=engine, page_size=args.page_size)

    if args.out:
        with open(args.out, "w", encoding="utf-8") as f:
            json.dump(report, f, indent=2)
        print(f"[+] Report saved to {args.out}", file=sys.stderr)

    if args.json:
        print(json.dumps(report, indent=2))
    elif not args.out:
        print_data_table_inventory_console(report)


if __name__ == "__main__":
    main()
