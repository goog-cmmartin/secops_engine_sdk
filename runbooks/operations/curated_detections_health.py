#!/usr/bin/env python3
"""Google Chronicle SIEM Curated Detections Health Check & Operational Audit Runbook.

Performs a comprehensive audit and hygiene analysis of Google SecOps Curated Rule Sets:
1. Tenant Deployment Posture: Broad vs. Precise deployment coverage across categories and log sources.
2. Misconfiguration & Risk Detection: Identifies high-risk states such as BROAD set to Alerting ON.
3. Telemetry & Firing Volume: Surfaces top firing and noisy rule sets over a specified timeframe.
4. Content Lifecycle & Freshness: Identifies the newest threat intelligence and oldest rules.
5. Actionable Guidance: Generates remediation recommendations and CLI commands.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone
import json
import os
import sys
from typing import Any, Dict, List, Optional

from engine.domain import CuratedDetectionHealthReport
from engine.facade import SecOpsEngine
from engine.workflows.curated_detections_health import generate_curated_detections_health_report


def print_curated_detections_health_console(report: Any, json_output: bool = False) -> None:
    """Prints the Curated Detections health audit in rich human-readable format."""
    if json_output:
        raw_dict = report.to_dict() if hasattr(report, "to_dict") else report
        print(json.dumps(raw_dict, indent=2))
        return

    summary = report.get("summary", {})
    period = report.get("evaluation_period", {})
    quotas = report.get("tenant_quotas", {})
    findings = report.get("health_findings", [])
    top_firing = report.get("top_firing_rulesets", [])
    newest = report.get("newest_rules", [])
    oldest = report.get("oldest_rules", [])
    categories = report.get("category_coverage", [])

    print("\n" + "=" * 78)
    print(" GOOGLE SECOPS: CURATED DETECTIONS HEALTH CHECK & HYGIENE AUDIT")
    print("=" * 78)
    print(f" Evaluation Window : Last {period.get('days', 7)} Days ({period.get('start_time', '')[:10]} to {period.get('end_time', '')[:10]})")
    print(f" Report Generated   : {period.get('retrieved_at', '')}")
    print("-" * 78)

    print("\n--- TENANT CURATED DEPLOYMENT POSTURE ---")
    print(f" Total Categories   : {summary.get('total_categories', 0):<5d} | Curated Rule Sets : {summary.get('total_rulesets', 0):,}")
    print(f" Curated Rules Total: {summary.get('total_curated_rules', 0):<5d} | Active Deployments: {summary.get('total_rulesets_deployed', 0):,}")
    print(f" PRECISE Deployments: {summary.get('precise_enabled_count', 0)} Enabled ({summary.get('precise_alerting_count', 0)} Alerting)")
    print(f" BROAD Deployments  : {summary.get('broad_enabled_count', 0)} Enabled ({summary.get('broad_alerting_count', 0)} Alerting)")
    print(f" Detection Hits     : {summary.get('total_detections_period', 0):,} detections in window")
    print(f" Engine Quota Usage : {quotas.get('quota_usage', 0)} / {quotas.get('quota_limit', 0)} ({quotas.get('total_live_rule_count', 0)} Live Rules)")

    # Findings Section
    print(f"\n--- HEALTH FINDINGS & CONFIGURATION RISKS ({len(findings)}) ---")
    if findings:
        for idx, f in enumerate(findings, 1):
            sev = f.get("severity", "INFO")
            badge = f"[{sev}]"
            title = f.get("ruleset_title") or "Tenant Telemetry"
            cat = f.get("category") or "System"
            print(f"\n {idx:2d}. {badge:<8s} {f.get('code')}: {title} ({cat})")
            if f.get("ruleset_id"):
                print(f"     Ruleset ID : {f.get('ruleset_id')}")
            print(f"     Issue      : {f.get('message')}")
            print(f"     Action     : {f.get('recommendation')}")
    else:
        print(" [✓] No critical misconfigurations or deployment risks detected.")

    # Top Firing Telemetry
    print(f"\n--- TOP FIRING CURATED RULE SETS (Last {period.get('days', 7)} Days) ---")
    if top_firing:
        for idx, tf in enumerate(top_firing[:10], 1):
            name = tf.get("ruleset_name", tf.get("ruleset_id", "Unknown"))
            count = tf.get("count", 0)
            print(f"  [{idx:2d}] {name:<50s} : {count:>7,d} hits")
    else:
        print("  No detection hits recorded in this timeframe.")

    # Newest Content
    print("\n--- NEWEST CURATED THREAT INTELLIGENCE (Recently Published Rules) ---")
    if newest:
        for idx, nr in enumerate(newest[:5], 1):
            up = (nr.get("update_time") or "")[:10]
            print(f"  [{idx}] {nr.get('title'):<52s} | Updated: {up} | Sev: {nr.get('severity')}")
    else:
        print("  No rules metadata available.")

    # Category Coverage
    print("\n--- CATEGORY DEPLOYMENT MATRIX ---")
    print(f" {'Category Name':<32s} | {'Rule Sets':<9s} | {'Precise Enabled':<15s} | {'Broad Enabled':<13s}")
    print(" " + "-" * 76)
    for c in sorted(categories, key=lambda x: x["total_rulesets"], reverse=True):
        print(f" {c.get('category_name', ''):<32s} | {c.get('total_rulesets', 0):>9d} | {c.get('precise_enabled', 0):>15d} | {c.get('broad_enabled', 0):>13d}")

    print("\n" + "=" * 78 + "\n")


def main():
    """Main CLI entrypoint for Curated Detections Health Audit Runbook."""
    parser = argparse.ArgumentParser(
        description="Run Google SecOps Curated Detections Health Check & Operational Audit"
    )
    parser.add_argument("--days", type=int, default=7, help="Evaluation timeframe in days for detection hits (default: 7)")
    parser.add_argument("--json", action="store_true", help="Output raw JSON instead of text tables")
    parser.add_argument("--out", help="Optional output filepath to save the audit report (JSON)")

    args = parser.parse_args()

    print(f"[*] Running Curated Detections Health Check (Window: {args.days} days)...", file=sys.stderr)
    report = generate_curated_detections_health_report(days=args.days)

    if args.out:
        with open(args.out, "w", encoding="utf-8") as f:
            json.dump(report, f, indent=2)
        print(f"[+] Saved Curated Detections Health Report to: {args.out}", file=sys.stderr)

    print_curated_detections_health_console(report, json_output=args.json)


if __name__ == "__main__":
    main()
