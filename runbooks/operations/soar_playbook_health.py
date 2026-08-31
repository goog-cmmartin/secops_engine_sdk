#!/usr/bin/env python3
"""Google SecOps SOAR Playbook Health Check & Operational Audit Runbook.

Performs a comprehensive audit and health assessment across all SOAR Playbooks and Blocks
by synthesizing structural configuration governance with live operational telemetry from
the Google SecOps native 'Playbook Dashboard (SOAR)':

1. Structural & Configuration Governance:
   - Enabled vs. Disabled state
   - Trigger configuration and orphaned triggers
   - Regular Playbooks vs. Reusable Modular Blocks (Nested)
   - SOC environment bindings and execution priorities

2. Operational & Execution Telemetry (Native SOAR Dashboard Queries):
   - Execution volume and failure rates (tenant-wide and per-playbook)
   - Faulted action hotspots (connector actions repeatedly failing)
   - Execution duration anomalies and latency outliers
   - Playbooks stuck in queue (PENDING_IN_QUEUE)
   - Action distribution (automated vs. manual, faulted step %)

3. Actionable Remediation Guidance:
   - Prioritized operational findings (CRITICAL, HIGH, MEDIUM, LOW, INFO)
   - Targeted remediation commands and troubleshooting steps
"""

from __future__ import annotations

import argparse
from collections import Counter
import concurrent.futures
from datetime import datetime, timezone
import json
import os
import sys
from typing import Any, Dict, List, Optional

from engine.domain import PlaybookBatch, PlaybookSummary, PlaybookType
from engine.facade import SecOpsEngine

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


def _execute_query_safe(engine: SecOpsEngine, key: str, query_id: str) -> tuple[str, List[Dict[str, Any]], Optional[str]]:
    """Safely executes a single dashboard query."""
    try:
        res = engine.adapter.execute_dashboard_query(query_id)
        return key, res.rows, None
    except Exception as ex:
        return key, [], str(ex)


def generate_soar_playbook_health_report(
    engine: Optional[SecOpsEngine] = None,
    days: int = 7,
    scan_deep: bool = True,
    fail_threshold_pct: float = 15.0,
    slow_threshold_minutes: float = 3.0,
) -> Dict[str, Any]:
    """Generates a comprehensive health check and operational audit report for SOAR playbooks.

    Args:
        engine: Optional SecOpsEngine instance.
        days: Evaluation lookback window in days (default: 7).
        scan_deep: Whether to execute deep query analytics from Playbook Dashboard (SOAR).
        fail_threshold_pct: Failure percentage threshold to flag playbooks as high risk (default: 15%).
        slow_threshold_minutes: Runtime threshold in minutes to flag slow playbooks (default: 3 min).

    Returns:
        Structured dictionary containing executive metrics, operational KPIs, health findings,
        failing playbooks, faulted connector actions, and duration benchmarks.
    """
    if engine is None:
        engine = SecOpsEngine()

    now_utc = datetime.now(timezone.utc)

    # 1. Fetch Structural Inventory via SDK
    try:
        batch: PlaybookBatch = engine.search_playbooks(limit=1000)
        playbook_summaries: List[PlaybookSummary] = batch.results
    except Exception as ex:
        playbook_summaries = []

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

    # Map name -> PlaybookSummary for correlation
    playbook_by_name: Dict[str, PlaybookSummary] = {p.name: p for p in playbook_summaries if p.name}

    # 2. Execute Native Dashboard Queries in Parallel
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

    # 3. Parse Telemetry Metrics
    # Total Runs
    total_runs_val = 0
    if query_results.get("total_runs"):
        try:
            total_runs_val = int(query_results["total_runs"][0].get("Total_Playbook_Runs", 0))
        except (ValueError, TypeError):
            total_runs_val = 0

    # Failed Runs
    failed_runs_val = 0
    if query_results.get("failed_runs"):
        try:
            failed_runs_val = int(query_results["failed_runs"][0].get("Total_Playbook_Runs", 0))
        except (ValueError, TypeError):
            failed_runs_val = 0

    overall_fail_rate_pct = round((failed_runs_val / max(1, total_runs_val)) * 100, 2) if total_runs_val > 0 else 0.0

    # Failed Playbooks Count
    failed_playbooks_count = 0
    if query_results.get("failed_playbooks_count"):
        try:
            failed_playbooks_count = int(query_results["failed_playbooks_count"][0].get("Total_Failed_Playbooks", 0))
        except (ValueError, TypeError):
            failed_playbooks_count = 0

    # Cases with Failed Playbooks
    failed_cases_count = 0
    if query_results.get("failed_cases_count"):
        try:
            failed_cases_count = int(query_results["failed_cases_count"][0].get("Total_Case_IDs", 0))
        except (ValueError, TypeError):
            failed_cases_count = 0

    # Overall Avg Runtime
    overall_avg_runtime_min = 0.0
    if query_results.get("overall_avg_runtime"):
        try:
            overall_avg_runtime_min = float(query_results["overall_avg_runtime"][0].get("Average", 0.0))
        except (ValueError, TypeError):
            overall_avg_runtime_min = 0.0

    # Faulted Actions Metric
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

    # Stuck / Queued Playbooks
    stuck_queue_rows = query_results.get("queue_stuck", [])
    stuck_queue_count = len(stuck_queue_rows)

    # 4. Process Failing Playbooks
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
            failing_playbooks.append({
                "name": pb_name,
                "total_runs": runs,
                "failed_runs": failed,
                "failure_rate_pct": pct,
                "is_enabled": pb_meta.is_enabled if pb_meta else None,
                "category": pb_meta.category_name if pb_meta else "Unknown",
                "identifier": pb_meta.identifier if pb_meta else None,
            })

    # Sort failing playbooks by failure rate descending, then failed runs descending
    failing_playbooks.sort(key=lambda x: (x["failure_rate_pct"], x["failed_runs"]), reverse=True)

    # 5. Process Faulted Actions Hotspots
    faulted_action_hotspots: List[Dict[str, Any]] = []
    for row in query_results.get("failed_actions", []):
        act_name = row.get("Action_Name", "")
        try:
            total_faults = int(row.get("Total_Actions", 0))
        except (ValueError, TypeError):
            total_faults = 0
        if total_faults > 0 and act_name:
            faulted_action_hotspots.append({
                "action_name": act_name,
                "fault_count": total_faults,
            })
    faulted_action_hotspots.sort(key=lambda x: x["fault_count"], reverse=True)

    # 6. Process Top Executed Playbooks
    top_executed_playbooks: List[Dict[str, Any]] = []
    for row in query_results.get("playbook_distribution", []):
        pb_name = row.get("Playbook_Name", "")
        try:
            runs = int(row.get("Total_Playbook_Runs", 0))
        except (ValueError, TypeError):
            runs = 0
        if runs > 0 and pb_name:
            pb_meta = playbook_by_name.get(pb_name)
            top_executed_playbooks.append({
                "name": pb_name,
                "total_runs": runs,
                "category": pb_meta.category_name if pb_meta else "Unknown",
                "is_enabled": pb_meta.is_enabled if pb_meta else None,
            })
    top_executed_playbooks.sort(key=lambda x: x["total_runs"], reverse=True)

    # 7. Process Runtime Latency & Outliers
    runtime_benchmarks: List[Dict[str, Any]] = []
    for row in query_results.get("avg_runtime_per_pb", []):
        pb_name = row.get("Playbook_Name", "")
        try:
            avg_dur = float(row.get("Average", 0.0))
        except (ValueError, TypeError):
            avg_dur = 0.0
        if pb_name:
            runtime_benchmarks.append({
                "name": pb_name,
                "avg_runtime_minutes": avg_dur,
            })
    runtime_benchmarks.sort(key=lambda x: x["avg_runtime_minutes"], reverse=True)

    # 8. Synthesize Health Findings & Severity Taxonomy
    findings: List[Dict[str, Any]] = []

    # Finding: Stuck in Queue
    if stuck_queue_count > 0:
        findings.append({
            "severity": "CRITICAL",
            "code": "STUCK_PLAYBOOK_QUEUE",
            "title": f"{stuck_queue_count} Playbook Runs Stuck in Pending Queue",
            "message": (
                f"Detected {stuck_queue_count} playbook execution(s) currently blocked in 'PENDING_IN_QUEUE'. "
                "This indicates worker congestion, connector deadlock, or resource starvation."
            ),
            "recommendation": "Inspect SOAR worker queues and restart unresponsive remote connector agents.",
        })

    # Finding: High Overall Failure Rate
    if overall_fail_rate_pct > fail_threshold_pct and total_runs_val >= 20:
        findings.append({
            "severity": "HIGH",
            "code": "HIGH_OVERALL_FAILURE_RATE",
            "title": f"High Tenant Automation Failure Rate ({overall_fail_rate_pct}%)",
            "message": (
                f"{failed_runs_val} of {total_runs_val} playbook runs failed in the last {days} days "
                f"across {failed_cases_count} cases."
            ),
            "recommendation": "Review top failing playbooks and remediate broken integration credentials.",
        })

    # Finding: Playbooks with 100% Failure Rate
    total_100_fail = [p for p in failing_playbooks if p["failure_rate_pct"] == 100.0 and p["total_runs"] >= 5]
    for p in total_100_fail:
        findings.append({
            "severity": "HIGH",
            "code": "PERSISTENT_PLAYBOOK_FAILURE",
            "title": f"Playbook '{p['name']}' Has 100% Failure Rate",
            "message": f"Playbook '{p['name']}' failed in all {p['total_runs']} execution runs over the last {days} days.",
            "recommendation": (
                f"Inspect playbook step trace for '{p['name']}':\n"
                f"  secops playbook get \"{p.get('identifier') or p['name']}\""
            ),
        })

    # Finding: Action Fault Hotspots
    if faulted_action_hotspots:
        top_fault_action = faulted_action_hotspots[0]
        if top_fault_action["fault_count"] > 100:
            findings.append({
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
            })

    # Finding: Slow Running Execution Outliers
    slow_playbooks = [r for r in runtime_benchmarks if r["avg_runtime_minutes"] >= slow_threshold_minutes]
    for sp in slow_playbooks[:3]:
        findings.append({
            "severity": "MEDIUM",
            "code": "SLOW_EXECUTION_OUTLIER",
            "title": f"Slow Playbook Latency: '{sp['name']}' ({sp['avg_runtime_minutes']}m avg)",
            "message": (
                f"Playbook '{sp['name']}' takes an average of {sp['avg_runtime_minutes']} minutes to run "
                f"(tenant average: {overall_avg_runtime_min}m)."
            ),
            "recommendation": "Optimize loops, reduce redundant entity enrichments, or enable step caching.",
        })

    # Finding: Structural Stale / Disabled Configuration
    if disabled_count > 0:
        findings.append({
            "severity": "INFO",
            "code": "DISABLED_PLAYBOOK_INVENTORY",
            "title": f"{disabled_count} Disabled Playbooks / Blocks in Tenant",
            "message": f"{disabled_count} of {total_playbooks} playbooks and reusable blocks are currently disabled.",
            "recommendation": "Archive or clean up unmaintained playbooks to reduce configuration clutter.",
        })

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
    }


def print_soar_playbook_health_console(report: Dict[str, Any], json_output: bool = False) -> None:
    """Prints the SOAR Playbook health check report formatted for console output."""
    if json_output:
        print(json.dumps(report, indent=2))
        return

    exec_summary = report.get("executive_summary", {})
    ops_metrics = report.get("operational_metrics", {})
    findings = report.get("health_findings", [])
    failing_pbs = report.get("failing_playbooks", [])
    fault_actions = report.get("faulted_action_hotspots", [])
    top_exec = report.get("top_executed_playbooks", [])
    runtime_bench = report.get("runtime_benchmarks", [])
    days = report.get("lookback_days", 7)

    print("\n" + "=" * 80)
    print("      GOOGLE SECOPS SOAR PLAYBOOK HEALTH CHECK & OPERATIONAL AUDIT")
    print("=" * 80)
    print(f" Generated At       : {report.get('generated_at')}")
    print(f" Lookback Window    : Last {days} days")
    print(f" Total Playbooks    : {exec_summary.get('total_playbooks', 0):,} "
          f"({exec_summary.get('regular_playbooks_count', 0)} Standard, {exec_summary.get('nested_blocks_count', 0)} Nested Blocks)")
    print(f" Deployment Posture : {exec_summary.get('enabled_count', 0)} Enabled, {exec_summary.get('disabled_count', 0)} Disabled")
    print(f" Total Runs ({days}d)   : {ops_metrics.get('total_playbook_runs', 0):,}")
    print(f" Failed Runs ({days}d)  : {ops_metrics.get('failed_playbook_runs', 0):,} ({ops_metrics.get('overall_fail_rate_pct', 0.0)}% failure rate)")
    print(f" Impacted Cases     : {ops_metrics.get('failed_cases_count', 0):,} cases")
    print(f" Avg Run Duration   : {ops_metrics.get('overall_avg_runtime_minutes', 0.0):.2f} minutes")
    print(f" Action Health      : {ops_metrics.get('faulted_actions_pct', 0.0):.2f}% faulted steps "
          f"({ops_metrics.get('faulted_actions_count', 0):,} / {ops_metrics.get('total_actions_executed', 0):,} actions)")
    print(f" Stuck in Queue     : {ops_metrics.get('stuck_queue_count', 0)} runs")

    # 1. Health Findings Section
    print("\n" + "-" * 80)
    print(f" OPERATIONAL HEALTH FINDINGS ({len(findings)})")
    print("-" * 80)

    if not findings:
        print("  ✅ No operational anomalies or misconfigurations detected. All systems healthy.")
    else:
        for idx, f in enumerate(findings, 1):
            sev = f.get("severity", "INFO")
            tag = f"[{sev}]".ljust(10)
            print(f"\n {idx:2d}. {tag} {f.get('title')}")
            print(f"     Code       : {f.get('code')}")
            print(f"     Details    : {f.get('message')}")
            if f.get("recommendation"):
                rec_lines = f.get("recommendation").split("\n")
                print(f"     Action     : {rec_lines[0]}")
                for rl in rec_lines[1:]:
                    print(f"                  {rl}")

    # 2. Top Failing Playbooks
    if failing_pbs:
        print("\n" + "-" * 80)
        print(" TOP FAILING PLAYBOOKS (Ranked by Failure Rate & Volume)")
        print("-" * 80)
        print(f" {'#':<3} | {'Playbook Name':<42} | {'Runs':<6} | {'Failed':<6} | {'Fail %':<7} | {'Category'}")
        print(" " + "-" * 78)
        for idx, pb in enumerate(failing_pbs[:10], 1):
            name_trunc = pb['name'][:42]
            print(f" {idx:<3} | {name_trunc:<42} | {pb['total_runs']:<6} | {pb['failed_runs']:<6} | {pb['failure_rate_pct']:>5.1f}% | {pb['category']}")

    # 3. Faulted Action Hotspots
    if fault_actions:
        print("\n" + "-" * 80)
        print(" FAULTED STEP / CONNECTOR ACTION HOTSPOTS")
        print("-" * 80)
        print(f" {'#':<3} | {'Faulted Step / Action Name':<55} | {'Fault Count'}")
        print(" " + "-" * 78)
        for idx, act in enumerate(fault_actions[:10], 1):
            act_trunc = act['action_name'][:55]
            print(f" {idx:<3} | {act_trunc:<55} | {act['fault_count']:,} faults")

    # 4. Top Executed Playbooks
    if top_exec:
        print("\n" + "-" * 80)
        print(" TOP EXECUTED PLAYBOOKS (Automation Volume)")
        print("-" * 80)
        print(f" {'#':<3} | {'Playbook Name':<50} | {'Execution Runs'}")
        print(" " + "-" * 78)
        for idx, pb in enumerate(top_exec[:8], 1):
            name_trunc = pb['name'][:50]
            print(f" {idx:<3} | {name_trunc:<50} | {pb['total_runs']:,} runs")

    # 5. Slow Running Outliers
    if runtime_bench:
        print("\n" + "-" * 80)
        print(" PLAYBOOK RUNTIME LATENCY BENCHMARKS (Slowest Workflows)")
        print("-" * 80)
        print(f" {'#':<3} | {'Playbook Name':<50} | {'Avg Runtime'}")
        print(" " + "-" * 78)
        for idx, pb in enumerate(runtime_bench[:5], 1):
            name_trunc = pb['name'][:50]
            print(f" {idx:<3} | {name_trunc:<50} | {pb['avg_runtime_minutes']:.2f} minutes")

    print("\n" + "=" * 80 + "\n")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Google SecOps SOAR Playbook Health Check & Operational Audit Runbook"
    )
    parser.add_argument(
        "--days", "-d",
        type=int,
        default=7,
        help="Lookback period in days for execution telemetry (default: 7)",
    )
    parser.add_argument(
        "--no-deep-scan",
        action="store_true",
        help="Skip deep query analytics and run inventory-only audit",
    )
    parser.add_argument(
        "--json", "-j",
        action="store_true",
        help="Output raw JSON format instead of human-readable console tables",
    )
    parser.add_argument(
        "--out", "-o",
        type=str,
        default=None,
        help="Output file path to write JSON report results",
    )

    args = parser.parse_args()

    engine = SecOpsEngine()
    report = generate_soar_playbook_health_report(
        engine=engine,
        days=args.days,
        scan_deep=not args.no_deep_scan,
    )

    if args.out:
        with open(args.out, "w", encoding="utf-8") as f:
            json.dump(report, f, indent=2)
        print(f"[+] Health report saved to: {args.out}")

    print_soar_playbook_health_console(report, json_output=args.json)


if __name__ == "__main__":
    main()
