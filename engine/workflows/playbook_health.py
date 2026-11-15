"""SOAR Playbook Health Check and Governance Workflow.

Audits SOAR playbooks and modular blocks across Google SecOps by fusing
structural configuration governance with live operational telemetry from the
native 'Playbook Dashboard (SOAR)'.
"""

from __future__ import annotations

from collections import Counter
import concurrent.futures
from datetime import datetime, timezone
import logging
from typing import TYPE_CHECKING, Any, Dict, List, Optional

from engine.domain import PlaybookBatch, PlaybookSummary, PlaybookType

if TYPE_CHECKING:
    from engine.facade import SecOpsEngine

logger = logging.getLogger(__name__)

# Native Dashboard Queries from "Playbook Dashboard (SOAR)" (ff9a7d04-c97d-455f-9d7c-ed4879a610a7)
SOAR_DASHBOARD_QUERIES = {
    "total_runs": "bd762dba-6fb1-4c20-8699-d3af118ab9fc",
    "failed_runs": "79a1bca7-3aa5-4a80-9509-5179c77c14f2",
    "failed_playbooks_count": "453100a2-0dc9-474e-8790-7a98e9d0f0d1",
    "failed_cases_count": "783febf0-9df0-4d67-9049-57967dc1668c",
    "fail_rate_per_playbook": "ba0bb376-796c-4c94-8c04-c0505af09e9e",
    "failed_actions": "fb69437b-f7fc-4a26-9846-fede3ae2b8c3",
    "failed_summary": "8ececf5f-72f9-4129-93ef-604e9861c4f0",
    "avg_runtime_per_pb": "8a3d9198-70dd-4081-a77f-87564d1aebad",
    "overall_avg_runtime": "456a22f7-ab96-4c90-99c5-14ae0260b536",
    "queue_stuck": "4943914f-4d80-44b7-8cb4-568c923e4a15",
    "playbook_distribution": "def15d90-9f83-4b5f-bf6c-e500e92928cb",
    "actions_faulted_pct": "7013d2f1-c42c-47a8-8daa-c73cc2d50317",
    "manual_actions_pct": "d991d989-3e97-43ee-8321-2909c22aa749",
}


def _execute_query_safe(
    engine: "SecOpsEngine", key: str, query_id: str
) -> tuple[str, List[Dict[str, Any]], Optional[str]]:
    """Executes a single dashboard query and captures any error explicitly."""
    try:
        res = engine.adapter.execute_dashboard_query(query_id)
        return key, res.rows, None
    except Exception as ex:
        return key, [], str(ex)


def generate_soar_playbook_health_report(
    engine: Optional["SecOpsEngine"] = None,
    days: int = 7,
    scan_deep: bool = True,
    fail_threshold_pct: float = 15.0,
    slow_threshold_minutes: float = 3.0,
) -> Dict[str, Any]:
    """Generates a comprehensive health check and operational audit report for SOAR playbooks."""
    if engine is None:
        from engine.facade import SecOpsEngine

        engine = SecOpsEngine()

    now_utc = datetime.now(timezone.utc)

    batch: PlaybookBatch = engine.search_playbooks(limit=1000)
    playbook_summaries: List[PlaybookSummary] = batch.results

    total_playbooks = len(playbook_summaries)
    enabled_count = sum(1 for p in playbook_summaries if p.is_enabled)
    disabled_count = total_playbooks - enabled_count

    regular_playbooks = [p for p in playbook_summaries if p.playbook_type == PlaybookType.REGULAR]
    nested_blocks = [p for p in playbook_summaries if p.playbook_type == PlaybookType.NESTED]

    category_counter: Counter[str] = Counter()
    env_counter: Counter[str] = Counter()
    priority_counter: Counter[str] = Counter()

    for p in playbook_summaries:
        category_counter[p.category_name or "Uncategorized"] += 1
        priority_counter[f"Priority {p.priority}"] += 1
        for env in (p.environments or ["*"]):
            env_counter[env] += 1

    playbook_by_name: Dict[str, PlaybookSummary] = {p.name: p for p in playbook_summaries if p.name}

    query_results: Dict[str, List[Dict[str, Any]]] = {}
    query_errors: Dict[str, str] = {}

    if scan_deep:
        with concurrent.futures.ThreadPoolExecutor(max_workers=12) as executor:
            future_to_key = {
                executor.submit(_execute_query_safe, engine, k, qid): k
                for k, qid in SOAR_DASHBOARD_QUERIES.items()
            }
            for future in concurrent.futures.as_completed(future_to_key):
                key, rows, err = future.result()
                if err:
                    query_errors[key] = err
                    query_results[key] = []
                else:
                    query_results[key] = rows

    total_runs_val = 0
    if query_results.get("total_runs"):
        try:
            total_runs_val = int(query_results["total_runs"][0].get("Total_Playbook_Runs", 0))
        except (ValueError, TypeError):
            total_runs_val = 0

    failed_runs_val = 0
    if query_results.get("failed_runs"):
        try:
            failed_runs_val = int(query_results["failed_runs"][0].get("Total_Playbook_Runs", 0))
        except (ValueError, TypeError):
            failed_runs_val = 0

    overall_fail_rate_pct = (
        round((failed_runs_val / max(1, total_runs_val)) * 100, 2) if total_runs_val > 0 else 0.0
    )

    failed_playbooks_count = 0
    if query_results.get("failed_playbooks_count"):
        try:
            failed_playbooks_count = int(
                query_results["failed_playbooks_count"][0].get("Total_Failed_Playbooks", 0)
            )
        except (ValueError, TypeError):
            failed_playbooks_count = 0

    failed_cases_count = 0
    if query_results.get("failed_cases_count"):
        try:
            failed_cases_count = int(query_results["failed_cases_count"][0].get("Total_Case_IDs", 0))
        except (ValueError, TypeError):
            failed_cases_count = 0

    overall_avg_runtime_min = 0.0
    if query_results.get("overall_avg_runtime"):
        try:
            overall_avg_runtime_min = float(query_results["overall_avg_runtime"][0].get("Average", 0.0))
        except (ValueError, TypeError):
            overall_avg_runtime_min = 0.0

    total_actions_val = 0
    faulted_actions_val = 0
    faulted_actions_pct = 0.0
    if query_results.get("actions_faulted_pct"):
        try:
            row = query_results["actions_faulted_pct"][0]
            total_actions_val = int(row.get("Total_Actions", 0))
            faulted_actions_val = int(row.get("Faulted_Actions", 0))
            faulted_actions_pct = float(row.get("Percentage", 0.0))
        except (ValueError, TypeError):
            pass

    stuck_queue_rows = query_results.get("queue_stuck", [])
    stuck_queue_count = len(stuck_queue_rows)

    failing_playbooks: List[Dict[str, Any]] = []
    for row in query_results.get("fail_rate_per_playbook", []):
        pb_name = row.get("Playbook_Name", "")
        try:
            runs = int(row.get("Total_Playbook_Runs", 0))
            failed = int(row.get("Playbook_Failed", 0))
            pct = float(row.get("Percentage", 0.0))
        except (ValueError, TypeError):
            runs, failed, pct = 0, 0, 0.0

        if failed > 0:
            pb_meta = playbook_by_name.get(pb_name)
            failing_playbooks.append(
                {
                    "name": pb_name,
                    "total_runs": runs,
                    "failed_runs": failed,
                    "failure_rate_pct": pct,
                    "is_enabled": pb_meta.is_enabled if pb_meta else None,
                    "category": pb_meta.category_name if pb_meta else "Unknown",
                    "identifier": pb_meta.identifier if pb_meta else None,
                }
            )

    failing_playbooks.sort(key=lambda x: (x["failure_rate_pct"], x["failed_runs"]), reverse=True)

    faulted_action_hotspots: List[Dict[str, Any]] = []
    for row in query_results.get("failed_actions", []):
        act_name = row.get("Action_Name", "")
        try:
            total_faults = int(row.get("Total_Actions", 0))
        except (ValueError, TypeError):
            total_faults = 0
        if total_faults > 0 and act_name:
            faulted_action_hotspots.append({"action_name": act_name, "fault_count": total_faults})
    faulted_action_hotspots.sort(key=lambda x: x["fault_count"], reverse=True)

    top_executed_playbooks: List[Dict[str, Any]] = []
    for row in query_results.get("playbook_distribution", []):
        pb_name = row.get("Playbook_Name", "")
        try:
            runs = int(row.get("Total_Playbook_Runs", 0))
        except (ValueError, TypeError):
            runs = 0
        if runs > 0 and pb_name:
            pb_meta = playbook_by_name.get(pb_name)
            top_executed_playbooks.append(
                {
                    "name": pb_name,
                    "total_runs": runs,
                    "category": pb_meta.category_name if pb_meta else "Unknown",
                    "is_enabled": pb_meta.is_enabled if pb_meta else None,
                }
            )
    top_executed_playbooks.sort(key=lambda x: x["total_runs"], reverse=True)

    runtime_benchmarks: List[Dict[str, Any]] = []
    for row in query_results.get("avg_runtime_per_pb", []):
        pb_name = row.get("Playbook_Name", "")
        try:
            avg_dur = float(row.get("Average", 0.0))
        except (ValueError, TypeError):
            avg_dur = 0.0
        if pb_name:
            runtime_benchmarks.append({"name": pb_name, "avg_runtime_minutes": avg_dur})
    runtime_benchmarks.sort(key=lambda x: x["avg_runtime_minutes"], reverse=True)

    findings: List[Dict[str, Any]] = []

    if stuck_queue_count > 0:
        findings.append(
            {
                "severity": "CRITICAL",
                "code": "STUCK_PLAYBOOK_QUEUE",
                "title": f"{stuck_queue_count} Playbook Runs Stuck in Pending Queue",
                "message": (
                    f"Detected {stuck_queue_count} playbook execution(s) currently blocked in 'PENDING_IN_QUEUE'. "
                    "This indicates worker congestion, connector deadlock, or resource starvation."
                ),
                "recommendation": "Inspect SOAR worker queues and restart unresponsive remote connector agents.",
            }
        )

    if overall_fail_rate_pct > fail_threshold_pct and total_runs_val >= 20:
        findings.append(
            {
                "severity": "HIGH",
                "code": "HIGH_OVERALL_FAILURE_RATE",
                "title": f"High Tenant Automation Failure Rate ({overall_fail_rate_pct}%)",
                "message": (
                    f"{failed_runs_val} of {total_runs_val} playbook runs failed in the last {days} days "
                    f"across {failed_cases_count} cases."
                ),
                "recommendation": "Review top failing playbooks and remediate broken integration credentials.",
            }
        )

    total_100_fail = [
        p for p in failing_playbooks if p["failure_rate_pct"] == 100.0 and p["total_runs"] >= 5
    ]
    for p in total_100_fail:
        findings.append(
            {
                "severity": "HIGH",
                "code": "PERSISTENT_PLAYBOOK_FAILURE",
                "title": f"Playbook '{p['name']}' Has 100% Failure Rate",
                "message": f"Playbook '{p['name']}' failed in all {p['total_runs']} execution runs over the last {days} days.",
                "recommendation": (
                    f"Inspect playbook step trace for '{p['name']}':\n"
                    f"  secops playbook get \"{p.get('identifier') or p['name']}\""
                ),
            }
        )

    if faulted_action_hotspots:
        top_fault_action = faulted_action_hotspots[0]
        if top_fault_action["fault_count"] > 100:
            findings.append(
                {
                    "severity": "HIGH",
                    "code": "FAULTED_ACTION_HOTSPOT",
                    "title": f"Fault Hotspot: Action '{top_fault_action['action_name']}'",
                    "message": (
                        f"Action '{top_fault_action['action_name']}' failed {top_fault_action['fault_count']:,} times. "
                        f"Overall action fault rate is {faulted_actions_pct}% ({faulted_actions_val:,} faulted steps)."
                    ),
                    "recommendation": (
                        f"Inspect integration instance settings and parameters for action '{top_fault_action['action_name']}'."
                    ),
                }
            )

    slow_playbooks = [
        r for r in runtime_benchmarks if r["avg_runtime_minutes"] >= slow_threshold_minutes
    ]
    for sp in slow_playbooks[:3]:
        findings.append(
            {
                "severity": "MEDIUM",
                "code": "SLOW_EXECUTION_OUTLIER",
                "title": f"Slow Playbook Latency: '{sp['name']}' ({sp['avg_runtime_minutes']}m avg)",
                "message": (
                    f"Playbook '{sp['name']}' takes an average of {sp['avg_runtime_minutes']} minutes to run "
                    f"(tenant average: {overall_avg_runtime_min}m)."
                ),
                "recommendation": "Optimize loops, reduce redundant entity enrichments, or enable step caching.",
            }
        )

    if disabled_count > 0:
        findings.append(
            {
                "severity": "INFO",
                "code": "DISABLED_PLAYBOOK_INVENTORY",
                "title": f"{disabled_count} Disabled Playbooks / Blocks in Tenant",
                "message": f"{disabled_count} of {total_playbooks} playbooks and reusable blocks are currently disabled.",
                "recommendation": "Archive or clean up unmaintained playbooks to reduce configuration clutter.",
            }
        )

    if query_errors:
        findings.append(
            {
                "severity": "MEDIUM",
                "code": "TELEMETRY_QUERY_ERRORS",
                "title": f"{len(query_errors)} SOAR Dashboard Telemetry Queries Failed",
                "message": f"Failed to execute {len(query_errors)} of {len(SOAR_DASHBOARD_QUERIES)} native SOAR dashboard queries.",
                "recommendation": "Verify dashboard query permissions and native Playbook Dashboard availability.",
            }
        )

    summary_dict = {
        "total_playbooks": total_playbooks,
        "regular_playbooks_count": len(regular_playbooks),
        "nested_blocks_count": len(nested_blocks),
        "enabled_count": enabled_count,
        "disabled_count": disabled_count,
        "categories_count": len(category_counter),
        "environments_count": len(env_counter),
    }

    metrics_dict = {
        "total_playbook_runs": total_runs_val,
        "failed_playbook_runs": failed_runs_val,
        "overall_fail_rate_pct": overall_fail_rate_pct,
        "failure_rate_pct": overall_fail_rate_pct,
        "failed_playbooks_count": failed_playbooks_count,
        "failed_cases_count": failed_cases_count,
        "overall_avg_runtime_minutes": overall_avg_runtime_min,
        "total_actions_executed": total_actions_val,
        "faulted_actions_count": faulted_actions_val,
        "faulted_actions_pct": faulted_actions_pct,
        "stuck_queue_count": stuck_queue_count,
    }

    return {
        "report_type": "soar_playbook_health_and_telemetry_audit",
        "generated_at": now_utc.isoformat(),
        "lookback_days": days,
        "summary": summary_dict,
        "executive_summary": summary_dict,
        "operational_telemetry": metrics_dict,
        "operational_metrics": metrics_dict,
        "health_findings": findings,
        "failing_playbooks": failing_playbooks,
        "top_failing_playbooks": failing_playbooks,
        "faulted_action_hotspots": faulted_action_hotspots,
        "top_faulted_actions": faulted_action_hotspots,
        "top_executed_playbooks": top_executed_playbooks,
        "runtime_benchmarks": runtime_benchmarks,
        "slowest_playbooks": runtime_benchmarks,
        "categories_distribution": dict(category_counter.most_common()),
        "environments_distribution": dict(env_counter.most_common()),
        "query_errors": query_errors,
    }


class AuditPlaybookHealthWorkflow:
    """Orchestrates comprehensive health and operational auditing across SOAR playbooks."""

    def __init__(self, engine: "SecOpsEngine"):
        self.engine = engine

    def execute(
        self,
        days: int = 7,
        scan_deep: bool = True,
        fail_threshold_pct: float = 15.0,
        slow_threshold_minutes: float = 3.0,
    ) -> Dict[str, Any]:
        """Audits SOAR playbooks for configuration anomalies, failure spikes, faulted actions, and queue latency."""
        return generate_soar_playbook_health_report(
            engine=self.engine,
            days=days,
            scan_deep=scan_deep,
            fail_threshold_pct=fail_threshold_pct,
            slow_threshold_minutes=slow_threshold_minutes,
        )
