#!/usr/bin/env python3
"""Google Chronicle SIEM YARA-L Detection Rules Health, Deployment & Error Audit Runbook.

Performs a full audit and health assessment across all custom YARA-L detection rules:
1. Rule Identity & Logic: Rule ID, Display Name, Author, Severity, Rule Type (Single/Multi-Event), Compilation State
2. Lifecycle & Versioning: Creation timestamp, Last revision timestamp, Revision ID
3. Deployment & Alerting: Enabled state, Alerting state, Run frequency, Execution state
4. Error Cross-Correlation: Cross-references runtime execution errors (ruleExecutionErrors)
5. Executive Summary & Health Metrics: Aggregated counts of healthy, alerting, disabled, and failing rules
"""

from __future__ import annotations

import argparse
import json
import sys
from typing import Any, Dict, List, Optional

from engine.facade import SecOpsEngine


def generate_yara_l_rules_audit_report(
    engine: Optional[SecOpsEngine] = None,
    page_size: int = 100,
    filter_expr: Optional[str] = None,
) -> Dict[str, Any]:
    """Generates a complete detection rules inventory, deployment, and error audit.

    Args:
        engine: Optional SecOpsEngine instance.
        page_size: Maximum rules and errors to retrieve per query.
        filter_expr: Optional filter expression for listing rules.

    Returns:
        Structured dictionary containing summary statistics and detailed rule audit items.
    """
    if engine is None:
        engine = SecOpsEngine()

    # 1. Fetch rules and runtime execution errors
    rules_res = engine.list_rules(page_size=page_size, filter_expr=filter_expr, view="FULL")
    errors_res = engine.list_rule_errors(page_size=page_size)

    # 2. Index runtime errors by rule ID
    errors_by_rule: Dict[str, List[Dict[str, Any]]] = {}
    for err in errors_res.errors:
        err_item = {
            "error_code": err.error_code,
            "error_message": err.error_message,
            "start_time": err.start_time,
            "end_time": err.end_time,
        }
        errors_by_rule.setdefault(err.rule_id, []).append(err_item)

    # 3. Cross-correlate each rule with its deployment configuration and runtime errors
    audit_rules: List[Dict[str, Any]] = []
    total_enabled = 0
    total_alerting = 0
    total_errors = 0
    total_disabled = 0

    for rule in rules_res.rules:
        # Query deployment settings for the rule
        try:
            dep = engine.get_rule_deployment(rule.rule_id)
            is_enabled = dep.enabled
            is_alerting = dep.alerting
            run_frequency = dep.run_frequency
            execution_state = dep.execution_state
            last_alert_status_change_time = dep.last_alert_status_change_time
        except Exception:
            is_enabled = False
            is_alerting = False
            run_frequency = rule.run_frequency or "UNKNOWN"
            execution_state = "UNKNOWN"
            last_alert_status_change_time = None

        rule_errors = errors_by_rule.get(rule.rule_id, [])
        has_runtime_errors = len(rule_errors) > 0
        compilation_state = getattr(rule, "compilation_state", None) or rule.raw.get("compilationState", "SUCCEEDED")
        has_compilation_errors = (compilation_state or "").upper() != "SUCCEEDED"
        revision_create_time = getattr(rule, "revision_create_time", None) or rule.raw.get("revisionCreateTime", rule.create_time)
        metadata = getattr(rule, "metadata", None) or rule.raw.get("metadata", {})

        if is_enabled:
            total_enabled += 1
        else:
            total_disabled += 1

        if is_alerting:
            total_alerting += 1

        if has_runtime_errors or has_compilation_errors:
            total_errors += 1

        health_status = "ERROR" if (has_runtime_errors or has_compilation_errors) else "HEALTHY"

        rule_item: Dict[str, Any] = {
            "rule_id": rule.rule_id,
            "display_name": rule.display_name,
            "resource_name": rule.name,
            "revision_id": rule.revision_id,
            "author": rule.author or "Unknown",
            "severity": rule.severity,
            "rule_type": rule.rule_type,
            "compilation_state": compilation_state,
            "create_time": rule.create_time,
            "revision_create_time": revision_create_time,
            "run_frequency": run_frequency,
            "enabled": is_enabled,
            "alerting": is_alerting,
            "execution_state": execution_state,
            "last_alert_status_change_time": last_alert_status_change_time,
            "health_status": health_status,
            "has_runtime_errors": has_runtime_errors,
            "runtime_errors_count": len(rule_errors),
            "runtime_errors": rule_errors,
            "metadata": metadata,
        }
        audit_rules.append(rule_item)

    return {
        "report_type": "chronicle_siem_yara_l_rules_audit",
        "summary": {
            "total_rules": len(audit_rules),
            "enabled_rules": total_enabled,
            "alerting_rules": total_alerting,
            "disabled_rules": total_disabled,
            "rules_with_errors": total_errors,
            "healthy_rules": len(audit_rules) - total_errors,
            "total_runtime_error_events": len(errors_res.errors),
        },
        "rules": audit_rules,
    }


def print_yara_l_rules_audit_console(report: Dict[str, Any]) -> None:
    """Prints a structured, formatted health report to stdout."""
    summary = report.get("summary", {})
    rules = report.get("rules", [])

    print("\n" + "=" * 110)
    print("GOOGLE CHRONICLE SIEM YARA-L DETECTION RULES AUDIT & HEALTH REPORT")
    print("=" * 110)
    print(f"  Total Rules       : {summary.get('total_rules', 0)}")
    print(f"  Enabled / Active  : {summary.get('enabled_rules', 0)}")
    print(f"  Alerting Enabled  : {summary.get('alerting_rules', 0)}")
    print(f"  Disabled          : {summary.get('disabled_rules', 0)}")
    print(f"  Rules in Error    : {summary.get('rules_with_errors', 0)}")
    print(f"  Healthy Rules     : {summary.get('healthy_rules', 0)}")
    print("-" * 110)

    if not rules:
        print("  No custom YARA-L rules found in tenant.")
        return

    for idx, r in enumerate(rules, 1):
        status_tag = "[HEALTHY]" if r["health_status"] == "HEALTHY" else "[ERROR]"
        enabled_tag = "[ENABLED]" if r["enabled"] else "[DISABLED]"
        alert_tag = "[ALERTING]" if r["alerting"] else "[NO ALERT]"

        print(f"\n[{idx:02d}] {r['display_name']} (ID: {r['rule_id']}) {status_tag}")
        print(f"     Author       : {r['author']:25s} | Severity : {r['severity']:10s} | Type: {r['rule_type']}")
        print(f"     Created At   : {r['create_time'] or 'N/A'}")
        print(f"     Last Modified: {r['revision_create_time'] or 'N/A'}")
        print(f"     Deployment   : {enabled_tag} {alert_tag} | Frequency: {r['run_frequency']}")
        print(f"     Compilation  : {r['compilation_state']}")

        if r.get("runtime_errors"):
            print(f"     ⚠️ Runtime Execution Errors ({r['runtime_errors_count']} events recorded):")
            for err in r["runtime_errors"][:3]:
                print(f"        - [{err.get('start_time', 'N/A')}] Code {err.get('error_code')}: {err.get('error_message')}")

    print("\n" + "=" * 110)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Google Chronicle SIEM YARA-L Detection Rules Health, Deployment & Error Audit Runbook"
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
        "--filter",
        "-f",
        help="Optional filter expression for listing detection rules.",
    )
    parser.add_argument(
        "--page-size",
        type=int,
        default=100,
        help="Maximum rules to inspect (default: 100).",
    )

    args = parser.parse_args()
    engine = SecOpsEngine()

    print("\n[+] Collecting Chronicle SIEM YARA-L detection rules, deployments, and execution errors...")
    report = generate_yara_l_rules_audit_report(
        engine=engine,
        page_size=args.page_size,
        filter_expr=args.filter,
    )

    if args.json:
        print(json.dumps(report, indent=2, default=str))
    else:
        print_yara_l_rules_audit_console(report)

    if args.out:
        with open(args.out, "w", encoding="utf-8") as f:
            json.dump(report, f, indent=2, default=str)
        print(f"\n[+] Audit report written to: {args.out}")


if __name__ == "__main__":
    main()
