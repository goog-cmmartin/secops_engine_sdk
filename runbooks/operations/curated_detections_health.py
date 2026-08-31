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

from engine.facade import SecOpsEngine


def generate_curated_detections_health_report(
    engine: Optional[SecOpsEngine] = None,
    days: int = 7,
    scan_deployments: bool = True,
) -> Dict[str, Any]:
    """Generates a complete health, deployment, and hygiene audit for Curated Detections.

    Args:
        engine: Optional SecOpsEngine instance.
        days: Evaluation window for detection telemetry (default: 7 days).
        scan_deployments: Whether to query deployment states for rule sets.

    Returns:
        Structured dictionary containing summary statistics, findings, and ranking tables.
    """
    if engine is None:
        engine = SecOpsEngine()

    adapter = engine.adapter
    days = max(1, days)
    now = datetime.now(timezone.utc)
    start_iso = (now - timedelta(days=days)).strftime("%Y-%m-%dT%H:%M:%S.000Z")
    end_iso = now.strftime("%Y-%m-%dT%H:%M:%S.000Z")

    # 1. Fetch Categories and Rule Sets
    cat_res = adapter.list_curated_ruleset_categories()
    raw_cats = cat_res.get("curatedRuleSetCategories", []) if isinstance(cat_res, dict) else []
    cat_map: Dict[str, str] = {c.get("name", "").split("/")[-1]: c.get("displayName", "") for c in raw_cats if c.get("name")}

    rs_res = adapter.list_curated_rulesets(page_size=1000)
    raw_rulesets = rs_res.get("curatedRuleSets", []) if isinstance(rs_res, dict) else []

    # 2. Fetch Detection Metrics & Tenant Quotas
    metrics = engine.get_curated_detection_metrics(start_time=start_iso, end_time=end_iso)
    tenant_metrics = metrics.tenant_metrics
    top_firing = metrics.top_firing_rulesets or []
    firing_map: Dict[str, int] = {f.get("resource_name", ""): int(f.get("count", 0)) for f in top_firing if f.get("resource_name")}

    # 3. Fetch Curated Individual Rules (for content freshness)
    rules_res = adapter.list_curated_rules(page_size=1000)
    raw_rules = rules_res.get("curatedRules", []) if isinstance(rules_res, dict) else []

    # 4. Analyze Rule Sets and Deployments
    ruleset_audits: List[Dict[str, Any]] = []
    health_findings: List[Dict[str, Any]] = []

    total_broad_enabled = 0
    total_broad_alerting = 0
    total_precise_enabled = 0
    total_precise_alerting = 0
    total_rulesets_with_active_deployments = 0

    category_stats: Dict[str, Dict[str, Any]] = {}
    log_source_stats: Dict[str, Dict[str, Any]] = {}

    for cat_id, cat_title in cat_map.items():
        category_stats[cat_title] = {
            "category_name": cat_title,
            "total_rulesets": 0,
            "broad_enabled": 0,
            "precise_enabled": 0,
            "precise_alerting": 0,
        }

    # Count member rules per ruleset
    rules_per_ruleset: Dict[str, int] = {}
    for r in raw_rules:
        parent_rs = r.get("curatedRuleSet", "")
        if parent_rs:
            rules_per_ruleset[parent_rs] = rules_per_ruleset.get(parent_rs, 0) + 1

    # Pre-fetch deployments concurrently if scan_deployments is True
    deployments_cache: Dict[str, List[Dict[str, Any]]] = {}
    if scan_deployments:
        import concurrent.futures

        def _fetch_dep(rs_n: str):
            try:
                dres = adapter.get_curated_ruleset_deployments(rs_n)
                return rs_n, dres.get("curatedRuleSetDeployments", []) if isinstance(dres, dict) else []
            except Exception:
                return rs_n, []

        with concurrent.futures.ThreadPoolExecutor(max_workers=15) as executor:
            fut_to_rs = {executor.submit(_fetch_dep, rs.get("name", "")): rs.get("name", "") for rs in raw_rulesets if rs.get("name")}
            for fut in concurrent.futures.as_completed(fut_to_rs):
                rs_k, rdeps = fut.result()
                deployments_cache[rs_k] = rdeps

    for rs in raw_rulesets:
        rs_name = rs.get("name", "")
        rs_id = rs_name.split("/")[-1] if rs_name else ""
        rs_title = rs.get("displayName", "") or rs_id
        
        # Extract category from resource name
        cat_id = ""
        if "/curatedRuleSetCategories/" in rs_name:
            cat_id = rs_name.split("/curatedRuleSetCategories/")[1].split("/")[0]
        cat_display = cat_map.get(cat_id, "General Threats")
        log_types = rs.get("logSources", []) or []
        member_rule_count = rules_per_ruleset.get(rs_name, 0)
        hits_count = firing_map.get(rs_name, 0)

        if cat_display in category_stats:
            category_stats[cat_display]["total_rulesets"] += 1

        for lt in log_types:
            if lt not in log_source_stats:
                log_source_stats[lt] = {"log_source": lt, "total_rulesets": 0, "active_rulesets": 0}
            log_source_stats[lt]["total_rulesets"] += 1

        # Process Deployments
        deployments: List[Dict[str, Any]] = []
        has_active = False
        broad_enabled = False
        broad_alerting = False
        precise_enabled = False
        precise_alerting = False

        if scan_deployments:
            raw_deps = deployments_cache.get(rs_name, [])
            for d in raw_deps:
                d_name = d.get("name", "")
                precision_str = d_name.split("/")[-1].upper() if d_name else "UNKNOWN"
                is_enabled = bool(d.get("enabled", False))
                is_alerting = bool(d.get("alerting", False))
                deployments.append({
                    "precision": precision_str,
                    "enabled": is_enabled,
                    "alerting": is_alerting,
                    "resource_name": d_name,
                })

                if precision_str == "BROAD":
                    broad_enabled = is_enabled
                    broad_alerting = is_alerting
                    if is_enabled:
                        total_broad_enabled += 1
                    if is_alerting:
                        total_broad_alerting += 1
                elif precision_str == "PRECISE":
                    precise_enabled = is_enabled
                    precise_alerting = is_alerting
                    if is_enabled:
                        total_precise_enabled += 1
                    if is_alerting:
                        total_precise_alerting += 1

                if is_enabled:
                    has_active = True

        if has_active:
            total_rulesets_with_active_deployments += 1
            if cat_display in category_stats:
                if broad_enabled:
                    category_stats[cat_display]["broad_enabled"] += 1
                if precise_enabled:
                    category_stats[cat_display]["precise_enabled"] += 1
                if precise_alerting:
                    category_stats[cat_display]["precise_alerting"] += 1
            for lt in log_types:
                if lt in log_source_stats:
                    log_source_stats[lt]["active_rulesets"] += 1

        # --- Health Findings & Misconfiguration Evaluation ---
        # 1. Critical Misconfiguration: BROAD set to Alerting ON
        if broad_enabled and broad_alerting:
            health_findings.append({
                "severity": "HIGH",
                "code": "BROAD_ALERTING_ENABLED",
                "ruleset_id": rs_id,
                "ruleset_title": rs_title,
                "category": cat_display,
                "message": f"Rule set '{rs_title}' has BROAD precision deployment configured with Alerting ON.",
                "recommendation": (
                    f"Set BROAD deployment to Alerting OFF (Silent Detection) to avoid alert fatigue:\n"
                    f"  secops curated set-deployment {rs_id} --precision BROAD --no-alerting"
                ),
            })

        # 2. Inconsistent Deployment: BROAD enabled while PRECISE disabled
        if broad_enabled and not precise_enabled:
            health_findings.append({
                "severity": "MEDIUM",
                "code": "BROAD_ENABLED_PRECISE_DISABLED",
                "ruleset_id": rs_id,
                "ruleset_title": rs_title,
                "category": cat_display,
                "message": f"Rule set '{rs_title}' has BROAD mode enabled but PRECISE mode is disabled.",
                "recommendation": (
                    f"Enable PRECISE deployment with Alerting ON for high-confidence detections:\n"
                    f"  secops curated set-deployment {rs_id} --precision PRECISE --enabled --alerting"
                ),
            })

        # 3. High Volume Noise Warning
        if hits_count > 500 and (broad_alerting or precise_alerting):
            health_findings.append({
                "severity": "LOW",
                "code": "HIGH_FIRING_VOLUME",
                "ruleset_id": rs_id,
                "ruleset_title": rs_title,
                "category": cat_display,
                "message": f"Rule set '{rs_title}' generated {hits_count:,} detections in the last {days} days.",
                "recommendation": "Review detection tuning exclusions or verify alert thresholds.",
            })

        # 4. Dormant / Empty Rule Set Enabled
        if has_active and member_rule_count == 0:
            health_findings.append({
                "severity": "INFO",
                "code": "EMPTY_ENABLED_RULESET",
                "ruleset_id": rs_id,
                "ruleset_title": rs_title,
                "category": cat_display,
                "message": f"Rule set '{rs_title}' is enabled but currently has 0 active member rules.",
                "recommendation": "Check if updated content is pending publication from Google Cloud Threat Intelligence.",
            })

        ruleset_audits.append({
            "ruleset_id": rs_id,
            "title": rs_title,
            "category": cat_display,
            "log_sources": log_types,
            "member_rules_count": member_rule_count,
            "detections_count": hits_count,
            "broad_enabled": broad_enabled,
            "broad_alerting": broad_alerting,
            "precise_enabled": precise_enabled,
            "precise_alerting": precise_alerting,
            "deployments": deployments,
        })

    # 5. Content Freshness: Rank Rules by updateTime
    valid_rules: List[Dict[str, Any]] = []
    for r in raw_rules:
        r_name = r.get("name", "")
        r_id = r_name.split("/")[-1] if r_name else ""
        up_time = r.get("updateTime", "")
        techs = [t.get("id", "") for t in r.get("techniques", []) if isinstance(t, dict)]
        valid_rules.append({
            "rule_id": r_id,
            "title": r.get("displayName", "") or r_id,
            "severity": (r.get("severity", {}) or {}).get("displayName", "MEDIUM"),
            "precision": r.get("precision", "PRECISE"),
            "rule_type": r.get("type", "SINGLE_EVENT"),
            "update_time": up_time,
            "techniques": techs,
            "parent_ruleset_name": r.get("curatedRuleSet", ""),
        })

    # Sort rules with valid update_time
    sorted_by_newest = sorted([r for r in valid_rules if r["update_time"]], key=lambda x: x["update_time"], reverse=True)
    sorted_by_oldest = sorted([r for r in valid_rules if r["update_time"]], key=lambda x: x["update_time"])

    newest_rules = sorted_by_newest[:10]
    oldest_rules = sorted_by_oldest[:10]

    # Calculate overall health summary
    total_detections_period = sum(f.get("count", 0) for f in top_firing)
    healthy_count = len(raw_rulesets) - len(health_findings)

    return {
        "evaluation_period": {
            "days": days,
            "start_time": start_iso,
            "end_time": end_iso,
            "retrieved_at": now.isoformat(),
        },
        "summary": {
            "total_categories": len(raw_cats),
            "total_rulesets": len(raw_rulesets),
            "total_curated_rules": len(raw_rules),
            "total_rulesets_deployed": total_rulesets_with_active_deployments,
            "broad_enabled_count": total_broad_enabled,
            "broad_alerting_count": total_broad_alerting,
            "precise_enabled_count": total_precise_enabled,
            "precise_alerting_count": total_precise_alerting,
            "total_detections_period": total_detections_period,
            "total_findings_count": len(health_findings),
            "healthy_rulesets_count": max(0, healthy_count),
        },
        "tenant_quotas": {
            "quota_usage": tenant_metrics.quota_usage,
            "quota_limit": tenant_metrics.quota_limit,
            "total_live_rule_count": tenant_metrics.total_live_rule_count,
            "max_live_rule_count": tenant_metrics.max_live_rule_count,
            "total_active_count": tenant_metrics.total_active_count,
        },
        "health_findings": health_findings,
        "top_firing_rulesets": top_firing[:15],
        "newest_rules": newest_rules,
        "oldest_rules": oldest_rules,
        "category_coverage": list(category_stats.values()),
        "log_source_coverage": sorted(list(log_source_stats.values()), key=lambda x: x["total_rulesets"], reverse=True),
        "ruleset_audits": ruleset_audits,
    }


def print_curated_detections_health_console(report: Dict[str, Any], json_output: bool = False) -> None:
    """Prints the Curated Detections health audit in rich human-readable format."""
    if json_output:
        print(json.dumps(report, indent=2))
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
            print(f"\n {idx:2d}. {badge:<8s} {f.get('code')}: {f.get('ruleset_title')} ({f.get('category')})")
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
