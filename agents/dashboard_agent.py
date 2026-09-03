"""Google ADK Autonomous SIEM Dashboard Health & Governance Agent.

Connects the SecOps Engine SDK workflows to a Google ADK Agent
for proactive dashboard monitoring, recency/drift tracking, broken widget query triage,
and unused/stale dashboard governance.
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
from engine.domain import DashboardHealthReport, DashboardHealthStatus

# ----------------------------------------------------------------------
# 1. SDK Tools Exposed to ADK
# ----------------------------------------------------------------------

_ENGINE: Optional[SecOpsEngine] = None


def get_engine() -> SecOpsEngine:
    global _ENGINE
    if _ENGINE is None:
        _ENGINE = SecOpsEngine()
    return _ENGINE


def audit_dashboards(
    lookback_days: int = 14,
    stale_days: int = 180,
    validate_queries: bool = True,
    max_deep_dashboards: int = 50,
) -> str:
    """Audits all native dashboards across the Google SecOps tenant.

    Args:
        lookback_days: Days threshold to classify recently created or modified dashboards.
        stale_days: Days of inactivity to classify stale or abandoned custom dashboards.
        validate_queries: Whether to run deep syntax validation against chart queries.
        max_deep_dashboards: Maximum number of dashboards to deeply validate.

    Returns:
        JSON string containing the DashboardHealthReport with summary counts and detailed findings.
    """
    engine = get_engine()
    report = engine.audit_dashboard_health(
        lookback_days=lookback_days,
        stale_days=stale_days,
        validate_queries=validate_queries,
        max_deep_dashboards=max_deep_dashboards,
    )

    findings_data = [
        {
            "dashboard_id": f.dashboard_id,
            "display_name": f.display_name,
            "dashboard_type": f.dashboard_type,
            "create_user_id": f.create_user_id,
            "update_user_id": f.update_user_id,
            "create_time": f.create_time.isoformat() if f.create_time else None,
            "update_time": f.update_time.isoformat() if f.update_time else None,
            "charts_count": f.charts_count,
            "broken_queries_count": f.broken_queries_count,
            "status": f.status.value,
            "details": f.details,
            "remediation_steps": f.remediation_steps,
            "broken_query_details": f.broken_query_details,
        }
        for f in report.findings
    ]

    result = {
        "summary": {
            "total_dashboards_audited": report.total_dashboards_audited,
            "healthy_count": report.healthy_count,
            "recently_created_count": report.recently_created_count,
            "recently_modified_count": report.recently_modified_count,
            "broken_query_count": report.broken_query_count,
            "empty_dashboard_count": report.empty_dashboard_count,
            "stale_count": report.stale_count,
            "custom_count": report.custom_count,
            "curated_count": report.curated_count,
            "generated_at": report.generated_at.isoformat(),
        },
        "findings": findings_data,
    }
    return json.dumps(result, indent=2)


def get_dashboard_details(dashboard_id_or_title: str) -> str:
    """Retrieves full composite dashboard structure including charts, queries, and layout.

    Args:
        dashboard_id_or_title: The unique UUID or display name of the dashboard.

    Returns:
        JSON string containing deep composite dashboard structure.
    """
    engine = get_engine()
    detail = engine.get_dashboard(identifier_or_title=dashboard_id_or_title, include_queries=True)
    return json.dumps(
        {
            "id": detail.summary.id,
            "name": detail.summary.name,
            "display_name": detail.summary.display_name,
            "description": detail.summary.description,
            "type": detail.summary.type,
            "create_time": detail.summary.create_time,
            "update_time": detail.summary.update_time,
            "charts": [
                {
                    "id": c.id,
                    "display_name": c.display_name,
                    "query_name": c.query_name,
                    "query_text": c.query.query_text if c.query else None,
                    "dialect": c.query.dialect if c.query else None,
                }
                for c in detail.charts
            ],
            "filters": detail.filters,
        },
        indent=2,
    )


def validate_dashboard_query(query_text: str, dialect: str = "DIALECT_STATS") -> str:
    """Validates statistical query syntax against the live Chronicle compiler.

    Args:
        query_text: Raw statistical query string (e.g. UDM stats SQL).
        dialect: Query dialect (default: "DIALECT_STATS").

    Returns:
        JSON string containing compilation success status and diagnostics.
    """
    engine = get_engine()
    res = engine.validate_dashboard_query(raw_query=query_text, dialect=dialect)
    return json.dumps(
        {
            "valid": res.valid,
            "dialect": res.dialect,
            "raw_query_type": res.raw_query_type,
            "error_message": res.error_message,
        },
        indent=2,
    )


def execute_chart_query(query_name_or_id: str) -> str:
    """Executes a dashboard widget query against live telemetry and returns tabular records.

    Args:
        query_name_or_id: The query resource name or UUID.

    Returns:
        JSON string with row-oriented query execution output.
    """
    engine = get_engine()
    res = engine.execute_dashboard_query(query_name_or_id=query_name_or_id)
    return json.dumps(
        {
            "query_name": res.query_name,
            "total_rows": res.total_rows,
            "columns": res.columns,
            "rows": res.rows[:20],  # sample preview
        },
        indent=2,
    )


# ----------------------------------------------------------------------
# 2. ADK Agent Factory
# ----------------------------------------------------------------------

SYSTEM_INSTRUCTION = """You are the SecOps Dashboard Health & Governance Agent, an autonomous security operations agent.
Your mission is to continuously monitor, validate, and govern native dashboards across Google SecOps.

Guidelines:
1. Call `audit_dashboards()` to evaluate all custom and curated dashboards for recent modifications, broken widget queries, empty placeholders, and staleness.
2. For any dashboard with BROKEN_QUERY or ORPHAN_CHART, call `get_dashboard_details()` to inspect chart queries and layout.
3. For failing or proposed widget queries, call `validate_dashboard_query()` to verify statistical SQL syntax and compiler diagnostics.
4. For active widgets, call `execute_chart_query()` to inspect live telemetry rows and data freshness.
5. Provide structured, actionable remediation guidance (e.g. query repairs, widget additions, or archiving recommendations).
"""


def create_dashboard_agent():
    """Creates a configured Google ADK Agent instance."""
    try:
        from google.adk import Agent
        from google.adk.tools import FunctionTool

        tools = [
            FunctionTool(audit_dashboards),
            FunctionTool(get_dashboard_details),
            FunctionTool(validate_dashboard_query),
            FunctionTool(execute_chart_query),
        ]

        agent = Agent(
            name="secops_dashboard_health_agent",
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
    print("  Google SecOps Autonomous Dashboard Health Agent (Direct Audit Mode)")
    print("=======================================================================\n")

    report_json = audit_dashboards(lookback_days=14, stale_days=180, validate_queries=True, max_deep_dashboards=30)
    report = json.loads(report_json)
    summary = report["summary"]
    findings = report["findings"]

    print(f"Audit Timestamp: {summary['generated_at']}")
    print(f"Total Dashboards Audited: {summary['total_dashboards_audited']}")
    print(f"  • Custom Dashboards:  {summary['custom_count']}")
    print(f"  • Curated/Default:    {summary['curated_count']}")
    print(f"  • Healthy:            {summary['healthy_count']}")
    print(f"  • Recently Created:   {summary['recently_created_count']}")
    print(f"  • Recently Modified:  {summary['recently_modified_count']}")
    print(f"  • Broken Queries:     {summary['broken_query_count']}")
    print(f"  • Empty Dashboards:   {summary['empty_dashboard_count']}")
    print(f"  • Stale (>180d):      {summary['stale_count']}\n")

    # Group findings for clean output
    actionable = [f for f in findings if f["status"] not in ("HEALTHY", "UNKNOWN")]
    healthy = [f for f in findings if f["status"] == "HEALTHY"]

    if actionable:
        print("Actionable & Recent Dashboard Findings:")
        for f in actionable:
            status_tag = f"[{f['status']}]".ljust(22)
            type_tag = f"[{f['dashboard_type']}]"
            author_str = f"Owner: {f['create_user_id']}" if f.get("create_user_id") else "Owner: N/A"
            charts_str = f"Charts: {f['charts_count']}"
            print(f"  {status_tag} {type_tag} {f['display_name']} ({f['dashboard_id']})")
            print(f"                         {author_str} | {charts_str}")
            if f.get("create_time"):
                print(f"                         Created: {f['create_time']}")
            if f.get("update_time"):
                print(f"                         Updated: {f['update_time']}")
            print(f"                         Details: {f['details']}")
            if f.get("broken_query_details"):
                for bq in f["broken_query_details"]:
                    print(f"                         Broken Widget: '{bq.get('chart_display_name')}'")
                    if bq.get("error_message"):
                        print(f"                           -> Error: {bq.get('error_message')}")
            if f["remediation_steps"]:
                print(f"                         Remediation: {', '.join(f['remediation_steps'])}")
            print()

    print(f"Healthy Dashboards: {len(healthy)} dashboards operating normally.")


if __name__ == "__main__":
    run_direct_audit()
