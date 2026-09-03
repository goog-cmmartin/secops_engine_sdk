"""Google ADK Autonomous SOAR Playbook Health & Telemetry Agent.

Connects the SecOps Engine SDK workflows and Google SecOps native
'Playbook Dashboard (SOAR)' analytics to an autonomous ADK Agent
for continuous playbook health monitoring, fault triage, action hot spot
diagnosis, and automation optimization.
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
from engine.domain import PlaybookSearchQuery, PlaybookType

# ----------------------------------------------------------------------
# 1. SDK Tools Exposed to ADK
# ----------------------------------------------------------------------

_ENGINE: Optional[SecOpsEngine] = None


def get_engine() -> SecOpsEngine:
    global _ENGINE
    if _ENGINE is None:
        _ENGINE = SecOpsEngine()
    return _ENGINE


def audit_soar_playbooks(
    days: int = 7,
    fail_threshold_pct: float = 15.0,
    slow_threshold_minutes: float = 3.0,
    scan_deep: bool = True,
) -> str:
    """Performs a comprehensive health check and operational audit across all SOAR Playbooks.

    Combines structural inventory governance with live execution analytics from the
    native 'Playbook Dashboard (SOAR)'.

    Args:
        days: Lookback evaluation period in days (default: 7).
        fail_threshold_pct: Failure rate % threshold to flag playbooks as high risk (default: 15%).
        slow_threshold_minutes: Execution duration threshold in minutes for slow playbooks (default: 3 min).
        scan_deep: Whether to run deep telemetry queries from the native SOAR dashboard.

    Returns:
        JSON string containing executive summary, operational metrics, prioritized findings,
        failing playbooks, faulted action hotspots, and duration benchmarks.
    """
    engine = get_engine()
    report = engine.audit_soar_playbook_health(
        days=days,
        scan_deep=scan_deep,
        fail_threshold_pct=fail_threshold_pct,
        slow_threshold_minutes=slow_threshold_minutes,
    )
    return json.dumps(report, indent=2)


def get_playbook_definition(identifier_or_id: str) -> str:
    """Retrieves full playbook definition, trigger conditions, and step execution graph/DAG.

    Args:
        identifier_or_id: Playbook UUID identifier or numeric ID.

    Returns:
        JSON string containing full playbook details and step configurations.
    """
    engine = get_engine()
    detail = engine.get_playbook(identifier_or_id)
    data = {
        "id": detail.id,
        "identifier": detail.identifier,
        "name": detail.name,
        "is_enabled": detail.is_enabled,
        "priority": detail.priority,
        "category_name": detail.category_name,
        "environments": detail.environments,
        "steps_count": len(detail.steps),
        "steps": [
            {
                "id": s.id,
                "name": s.name,
                "action_name": s.action_name,
                "integration": s.integration,
                "instance_name": s.instance_name,
                "is_automatic": s.is_automatic,
            }
            for s in detail.steps
        ],
    }
    return json.dumps(data, indent=2)


def search_playbooks_inventory(
    query: Optional[str] = None,
    category: Optional[str] = None,
    is_enabled: Optional[bool] = None,
    environment: Optional[str] = None,
) -> str:
    """Searches and filters the SOAR Playbook inventory.

    Args:
        query: Optional text keyword search against name, creator, or ID.
        category: Optional category folder name.
        is_enabled: Optional filter for enabled (True) or disabled (False) playbooks.
        environment: Optional SOC environment filter.

    Returns:
        JSON string list of matching playbook summaries.
    """
    engine = get_engine()
    batch = engine.search_playbooks(
        query=query,
        category=category,
        is_enabled=is_enabled,
        environment=environment,
        limit=100,
    )
    results = [
        {
            "id": p.id,
            "identifier": p.identifier,
            "name": p.name,
            "type": p.playbook_type.value if p.playbook_type else "UNKNOWN",
            "is_enabled": p.is_enabled,
            "priority": p.priority,
            "category": p.category_name,
            "creator": p.creator_full_name or p.creator,
            "environments": p.environments,
        }
        for p in batch.results
    ]
    return json.dumps(results, indent=2)


# ----------------------------------------------------------------------
# 2. Agent Definition & System Instructions
# ----------------------------------------------------------------------

SYSTEM_INSTRUCTION = """You are the Google SecOps Autonomous SOAR Playbook Health & Telemetry Agent.
Your primary role is to audit, triage, and optimize SOAR playbooks, reusable modular blocks,
and connector execution performance across the Google SecOps deployment.

You operate across two primary layers:
1. Structural Configuration Governance (Enabled states, triggers, blocks, environment scopes)
2. Operational Telemetry (Live run volumes, failure spikes, faulted connector steps, queue bottlenecks)

When auditing or answering requests:
1. Call `audit_soar_playbooks` to retrieve the current health baseline and live operational telemetry.
2. If specific playbooks exhibit 100% or high failure rates, inspect their definition using `get_playbook_definition`.
3. Highlight critical issues first (e.g. `STUCK_PLAYBOOK_QUEUE`, persistent failure playbooks, faulted integration hotspots).
4. Provide concrete root causes (e.g. unconfigured credentials, network timeouts, invalid condition expressions) and CLI remediation commands.
"""


def create_soar_playbook_agent() -> Any:
    """Factory creating the Google ADK Agent for SOAR Playbook Health & Telemetry."""
    try:
        from google.adk.agents import Agent
        from google.adk.tools import FunctionTool

        tools = [
            FunctionTool(audit_soar_playbooks),
            FunctionTool(get_playbook_definition),
            FunctionTool(search_playbooks_inventory),
        ]

        agent = Agent(
            name="secops_soar_playbook_health_agent",
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

def run_direct_audit(days: int = 7) -> None:
    """Executes a direct health audit pass and prints formatted console output."""
    from runbooks.operations.soar_playbook_health import print_soar_playbook_health_console

    engine = get_engine()
    report = engine.audit_soar_playbook_health(days=days, scan_deep=True)
    print_soar_playbook_health_console(report)


if __name__ == "__main__":
    run_direct_audit()
