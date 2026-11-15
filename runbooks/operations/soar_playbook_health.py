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

from engine.facade import SecOpsEngine
from engine.workflows.playbook_health import (
    SOAR_DASHBOARD_QUERIES,
    _execute_query_safe,
    generate_soar_playbook_health_report,
)


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
