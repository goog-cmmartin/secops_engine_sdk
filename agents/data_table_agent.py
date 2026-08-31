"""Google ADK Autonomous SIEM Data Table Governance & Lineage Agent.

Connects the SecOps Engine SDK workflows to a Google ADK Agent
for proactive Data Table monitoring, recency/drift tracking, silent false-negative detection risk triage
(active rules referencing empty tables), schema hygiene, and cross-resource lineage.
"""

from __future__ import annotations

import json
import os
import sys
from typing import Any, Dict, List, Optional

# Ensure project root is in PYTHONPATH
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from engine.facade import SecOpsEngine
from engine.domain import DataTableHealthReport, DataTableHealthStatus

# ----------------------------------------------------------------------
# 1. SDK Tools Exposed to ADK
# ----------------------------------------------------------------------

_ENGINE: Optional[SecOpsEngine] = None


def get_engine() -> SecOpsEngine:
    global _ENGINE
    if _ENGINE is None:
        _ENGINE = SecOpsEngine()
    return _ENGINE


def audit_data_tables(
    lookback_days: int = 14,
    stale_days: int = 180,
    correlate_rules: bool = True,
    max_tables: int = 200,
) -> str:
    """Audits all Data Tables across the Google SecOps tenant.

    Args:
        lookback_days: Days threshold to classify recently created or modified tables.
        stale_days: Days of inactivity to classify stale unreferenced tables.
        correlate_rules: Whether to scan custom detection rules for %table% references.
        max_tables: Maximum number of data tables to audit.

    Returns:
        JSON string containing the DataTableHealthReport with summary counts and detailed findings.
    """
    engine = get_engine()
    report = engine.audit_data_table_health(
        lookback_days=lookback_days,
        stale_days=stale_days,
        correlate_rules=correlate_rules,
        max_tables=max_tables,
    )

    findings_data = [
        {
            "table_id": f.table_id,
            "display_name": f.display_name,
            "description": f.description,
            "approximate_row_count": f.approximate_row_count,
            "column_count": f.column_count,
            "key_columns": f.key_columns,
            "row_time_to_live": f.row_time_to_live,
            "create_time": f.create_time.isoformat() if f.create_time else None,
            "update_time": f.update_time.isoformat() if f.update_time else None,
            "associated_rules": f.associated_rules,
            "rule_associations_count": f.rule_associations_count,
            "status": f.status.value,
            "details": f.details,
            "remediation_steps": f.remediation_steps,
        }
        for f in report.findings
    ]

    result = {
        "summary": {
            "total_tables_audited": report.total_tables_audited,
            "healthy_count": report.healthy_count,
            "empty_referenced_count": report.empty_referenced_count,
            "orphan_count": report.orphan_count,
            "recently_created_count": report.recently_created_count,
            "recently_modified_count": report.recently_modified_count,
            "stale_count": report.stale_count,
            "schema_issue_count": report.schema_issue_count,
            "generated_at": report.generated_at.isoformat(),
        },
        "findings": findings_data,
    }
    return json.dumps(result, indent=2)


def get_table_schema(table_name_or_id: str) -> str:
    """Retrieves detailed column schema and configuration for a single Data Table.

    Args:
        table_name_or_id: The resource name or table ID.

    Returns:
        JSON string containing column types, key column flags, and row count.
    """
    engine = get_engine()
    table = engine.get_data_table(table_name_or_id=table_name_or_id)
    return json.dumps(
        {
            "id": table.id,
            "name": table.name,
            "display_name": table.display_name,
            "description": table.description,
            "approximate_row_count": table.approximate_row_count,
            "row_time_to_live": table.row_time_to_live,
            "columns": [
                {
                    "column_index": c.column_index,
                    "original_column": c.original_column,
                    "column_type": c.column_type,
                    "key_column": c.key_column,
                    "repeated_values": c.repeated_values,
                    "mapped_column_path": c.mapped_column_path,
                }
                for c in table.column_info
            ],
            "rules": table.rules,
            "rule_associations_count": table.rule_associations_count,
        },
        indent=2,
    )


def list_table_rows_sample(table_name_or_id: str, page_size: int = 10) -> str:
    """Retrieves a sample preview of rows from a Data Table.

    Args:
        table_name_or_id: The resource name or table ID.
        page_size: Maximum number of rows to retrieve (default: 10).

    Returns:
        JSON string containing sample rows.
    """
    engine = get_engine()
    res = engine.list_data_table_rows(table_name_or_id=table_name_or_id, page_size=page_size)
    return json.dumps(
        {
            "total_sample_rows": len(res.rows),
            "next_page_token": res.next_page_token,
            "rows": [
                {
                    "id": r.id,
                    "values": r.values,
                    "create_time": r.create_time.isoformat() if r.create_time else None,
                    "update_time": r.update_time.isoformat() if r.update_time else None,
                }
                for r in res.rows
            ],
        },
        indent=2,
    )


def trace_table_lineage(table_name_or_id: str) -> str:
    """Traces which YARA-L detection rules and threat hunting workflows reference this Data Table.

    Args:
        table_name_or_id: The resource name or table ID.

    Returns:
        JSON string with referencing rules and association metrics.
    """
    engine = get_engine()
    table = engine.get_data_table(table_name_or_id=table_name_or_id)
    report = engine.audit_data_table_health(correlate_rules=True)

    matching_finding = next((f for f in report.findings if f.table_id == table.id or f.display_name == table.display_name), None)

    return json.dumps(
        {
            "table_id": table.id,
            "display_name": table.display_name,
            "approximate_row_count": table.approximate_row_count,
            "direct_rules": table.rules,
            "lineage_rules": matching_finding.associated_rules if matching_finding else table.rules,
            "rule_associations_count": matching_finding.rule_associations_count if matching_finding else table.rule_associations_count,
            "status": matching_finding.status.value if matching_finding else "UNKNOWN",
        },
        indent=2,
    )


# ----------------------------------------------------------------------
# 2. ADK Agent Factory
# ----------------------------------------------------------------------

SYSTEM_INSTRUCTION = """You are the SecOps Data Table Governance & Lineage Agent, an autonomous security operations agent.
Your mission is to continuously monitor, audit, and govern structured Data Tables across Google SecOps.

Guidelines:
1. Call `audit_data_tables()` to evaluate all Data Tables for recency, orphan status, schema issues, and critical empty-referenced detection risks.
2. If any table has EMPTY_REFERENCED status, immediately prioritize it as a CRITICAL RISK: active detection rules are querying an empty table, causing silent false negatives. Call `trace_table_lineage()` to isolate the impacted rules.
3. Call `get_table_schema()` to verify column typing, key indexing, and schema mappings.
4. Call `list_table_rows_sample()` to verify row data freshness and format consistency.
5. Provide structured, actionable remediation steps (e.g. data population, rule updates, or table archiving).
"""


def create_data_table_agent():
    """Creates a configured Google ADK Agent instance."""
    try:
        from google.adk import Agent
        from google.adk.tools import FunctionTool

        tools = [
            FunctionTool(audit_data_tables),
            FunctionTool(get_table_schema),
            FunctionTool(list_table_rows_sample),
            FunctionTool(trace_table_lineage),
        ]

        agent = Agent(
            name="secops_data_table_governance_agent",
            model="gemini-2.5-pro",
            instructions=SYSTEM_INSTRUCTION,
            tools=tools,
        )
        return agent
    except ImportError as e:
        print(f"[ADK Warning] Google ADK package import issue: {e}", file=sys.stderr)
        return None


# ----------------------------------------------------------------------
# 3. Direct Runner & Execution CLI
# ----------------------------------------------------------------------

def run_direct_audit():
    """Executes a direct audit pass using the underlying SDK workflows."""
    print("=======================================================================")
    print("  Google SecOps Autonomous Data Table Governance Agent (Direct Audit)")
    print("=======================================================================\n")

    report_json = audit_data_tables(lookback_days=14, stale_days=180, correlate_rules=True)
    report = json.loads(report_json)
    summary = report["summary"]
    findings = report["findings"]

    print(f"Audit Timestamp: {summary['generated_at']}")
    print(f"Total Data Tables Audited: {summary['total_tables_audited']}")
    print(f"  • Healthy:            {summary['healthy_count']}")
    print(f"  • Empty Referenced:   {summary['empty_referenced_count']}  <-- CRITICAL DETECTION RISKS")
    print(f"  • Orphan Tables:      {summary['orphan_count']}")
    print(f"  • Recently Created:   {summary['recently_created_count']}")
    print(f"  • Recently Modified:  {summary['recently_modified_count']}")
    print(f"  • Schema Issues:      {summary['schema_issue_count']}")
    print(f"  • Stale (>180d):      {summary['stale_count']}\n")

    # Group findings for clean output
    actionable = [f for f in findings if f["status"] not in ("HEALTHY", "UNKNOWN")]
    healthy = [f for f in findings if f["status"] == "HEALTHY"]

    if actionable:
        print("Actionable Data Table Findings:")
        for f in actionable:
            status_tag = f"[{f['status']}]".ljust(22)
            rows_str = f"Rows: {f['approximate_row_count'] if f.get('approximate_row_count') is not None else 'N/A'}"
            rules_str = f"Associated Rules: {f['rule_associations_count']}"
            keys_str = f"Keys: {', '.join(f['key_columns']) if f.get('key_columns') else 'None'}"
            print(f"  {status_tag} {f['display_name']} ({f['table_id']})")
            print(f"                         {rows_str} | {rules_str} | {keys_str}")
            if f.get("create_time"):
                print(f"                         Created: {f['create_time']}")
            if f.get("update_time"):
                print(f"                         Updated: {f['update_time']}")
            print(f"                         Details: {f['details']}")
            if f.get("associated_rules"):
                print(f"                         Referencing Rules: {', '.join(f['associated_rules'][:5])}")
            if f["remediation_steps"]:
                print(f"                         Remediation: {', '.join(f['remediation_steps'])}")
            print()

    print(f"Healthy Data Tables: {len(healthy)} tables populated and functioning normally.")


if __name__ == "__main__":
    run_direct_audit()
