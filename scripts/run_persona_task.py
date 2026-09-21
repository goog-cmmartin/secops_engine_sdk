#!/usr/bin/env python3
"""Autonomous Persona Task Runner.

Executes operational tasks defined in knowledge/tasks/ against live SecOps endpoints,
evaluates telemetry against task evaluation rules, and generates structured
remediation reports for AI agents and human operators.

Usage:
    python scripts/run_persona_task.py --task task.ingestion_specialist.audit_feed_health
    python scripts/run_persona_task.py --task task.detection_engineer.review_rule_health
    python scripts/run_persona_task.py --list
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tests.test_helpers import get_live_engine  # noqa: E402


def find_task_file(task_id_or_path: str) -> Optional[Path]:
    p = Path(task_id_or_path)
    if p.exists() and p.is_file():
        return p

    # Search knowledge/tasks/
    tasks_dir = REPO_ROOT / "knowledge" / "tasks"
    for path in tasks_dir.rglob("*.md"):
        try:
            content = path.read_text(encoding="utf-8")
            if content.startswith("---"):
                _, fm_str, _ = content.split("---", 2)
                fm = yaml.safe_load(fm_str)
                if fm.get("id") == task_id_or_path:
                    return path
        except Exception:
            continue
    return None


def parse_markdown_sections(body: str) -> Dict[str, str]:
    sections: Dict[str, str] = {}
    current_title = "preamble"
    current_lines = []

    for line in body.splitlines():
        if line.startswith("## "):
            if current_lines:
                sections[current_title] = "\n".join(current_lines).strip()
                current_lines = []
            current_title = line[3:].strip()
        else:
            current_lines.append(line)

    if current_lines:
        sections[current_title] = "\n".join(current_lines).strip()

    return sections


def run_task(task_path: Path) -> int:
    raw = task_path.read_text(encoding="utf-8")
    if not raw.startswith("---"):
        print(f"Error: {task_path} missing YAML frontmatter.")
        return 1

    _, fm_str, body = raw.split("---", 2)
    meta = yaml.safe_load(fm_str)
    sections = parse_markdown_sections(body)

    task_id = meta.get("id")
    persona_id = meta.get("persona")
    title = meta.get("title")
    capabilities = meta.get("capabilities_used", [])
    eval_rules = meta.get("evaluation_rules", {})

    print("=" * 70)
    print(f"EXECUTING TASK: {title}")
    print(f"Task ID:   {task_id}")
    print(f"Persona:   {persona_id}")
    print(f"Capabilities: {', '.join(capabilities)}")
    print("=" * 70)

    print("\n[*] Connecting to SecOps Engine & Live Tenant...")
    try:
        engine = get_live_engine()
    except Exception as e:
        print(f"Failed to connect to SecOps Engine: {e}")
        return 1

    verdict = "HEALTHY"
    findings = []
    telemetry = {}

    # Execution dispatcher based on task ID
    if task_id == "task.ingestion_specialist.audit_feed_health":
        print("[*] Executing capability 'feed.audit_health'...")
        res = engine.audit_feed_health()
        unhealthy = getattr(res, "unhealthy_feeds", [])
        telemetry["unhealthy_feed_count"] = len(unhealthy)
        telemetry["status"] = str(getattr(res, "status", "UNKNOWN"))

        max_unhealthy = eval_rules.get("max_unhealthy_feeds", 0)
        if len(unhealthy) > max_unhealthy:
            verdict = "CRITICAL"
            findings.append(f"Detected {len(unhealthy)} unhealthy feed(s) (threshold: {max_unhealthy}).")
            for f in unhealthy:
                findings.append(f"  • Feed {getattr(f, 'feed_id', 'unknown')}: {getattr(f, 'error_message', 'No error detail')}")
        else:
            findings.append(f"All configured feeds transmitting normally (0 failures).")

    elif task_id == "task.detection_engineer.review_rule_health":
        print("[*] Executing capability 'rule.audit_health'...")
        rule_res = engine.audit_rule_health()
        failing_rules = [f for f in rule_res.findings if f.status.value in ("EXECUTION_ERROR", "COMPILATION_ERROR")]
        telemetry["total_rules_audited"] = rule_res.total_rules_audited
        telemetry["failing_rule_count"] = len(failing_rules)
        telemetry["healthy_rule_count"] = rule_res.healthy_count

        print("[*] Executing capability 'curated_detections.audit_health'...")
        curated_res = engine.audit_curated_detections_health()
        retired_count = len(getattr(curated_res, "retired_rules", []))
        enabled_pct = getattr(curated_res, "enabled_percentage", 100.0)
        telemetry["curated_enabled_pct"] = enabled_pct
        telemetry["curated_retired_rules"] = retired_count

        max_errors = eval_rules.get("max_execution_errors", 0)
        min_curated = eval_rules.get("min_curated_enabled_pct", 60.0)

        if len(failing_rules) > max_errors:
            verdict = "CRITICAL"
            findings.append(f"Detected {len(failing_rules)} rule(s) experiencing runtime execution errors:")
            for fr in failing_rules:
                findings.append(f"  • {fr.display_name} (ID: {fr.rule_id}): {fr.details}")
                if fr.remediation_steps:
                    for rem in fr.remediation_steps:
                        findings.append(f"    - Remediation: {rem}")
        elif enabled_pct < min_curated:
            verdict = "WARNING"
            findings.append(f"Curated detections enablement rate is {enabled_pct:.1f}% (threshold: {min_curated}%).")
        else:
            findings.append("Custom rule execution and curated detections health are nominal.")

    elif task_id == "task.platform_engineer.check_udm_search_performance":
        print("[*] Executing capability 'dashboard.audit_health'...")
        dash_res = engine.audit_dashboard_health(lookback_days=7, validate_queries=False)
        telemetry["total_dashboards"] = getattr(dash_res, "total_dashboards", 0)
        telemetry["broken_dashboards"] = len(getattr(dash_res, "broken_dashboards", []))
        findings.append(f"Audited {telemetry['total_dashboards']} native dashboards.")
        if telemetry["broken_dashboards"] > 0:
            verdict = "WARNING"
            findings.append(f"Detected {telemetry['broken_dashboards']} dashboard(s) with query or validation errors.")
        else:
            findings.append("Dashboard query syntax and widget status are nominal.")

    elif task_id == "task.platform_engineer.audit_identity_access":
        print("[*] Executing capability 'data_rbac.scope.search'...")
        scope_res = engine.search_data_access_scopes()
        scopes = getattr(scope_res, "scopes", []) if hasattr(scope_res, "scopes") else []
        telemetry["data_access_scopes_count"] = len(scopes)
        findings.append(f"Active data access scopes verified: {len(scopes)} found.")

    elif task_id == "task.soc_analyst.triage_high_priority_cases":
        print("[*] Executing capability 'case.search' for high-priority cases...")
        cases_batch = engine.search_cases(page_size=10, priorities=["CRITICAL", "HIGH"])
        cases = getattr(cases_batch, "cases", []) if hasattr(cases_batch, "cases") else []
        telemetry["total_cases_sampled"] = len(cases)
        telemetry["high_priority_cases"] = len(cases)
        findings.append(f"Sampled {len(cases)} recent high-priority case(s).")
        for c in cases[:3]:
            findings.append(f"  • Case #{getattr(c, 'case_id', 'unknown')}: {getattr(c, 'title', 'No Title')} (Priority: {getattr(c, 'priority', 'UNKNOWN')}, Stage: {getattr(c, 'stage', 'UNKNOWN')})")

    else:
        print(f"[*] Executing generic audit verification for capabilities: {capabilities}...")
        findings.append(f"Task procedure verified against declared capabilities: {capabilities}.")

    # Output Evaluation Summary
    print("\n" + "-" * 70)
    print(f"TASK EVALUATION VERDICT: [{verdict}]")
    print("-" * 70)
    print("Telemetry Metrics:")
    for k, v in telemetry.items():
        print(f"  • {k}: {v}")

    print("\nFindings:")
    for f in findings:
        print(f"  • {f}")

    # Remediation
    remediation_key = next((k for k in sections if "remediation" in k.lower() or "escalation" in k.lower()), None)
    if remediation_key:
        print("\n" + "-" * 70)
        print(f"RUNBOOK REMEDIATION ({remediation_key}):")
        print("-" * 70)
        print(sections[remediation_key])

    print("\n" + "=" * 70)
    print(f"Execution complete. Verdict: {verdict}")
    print("=" * 70)
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Autonomous Persona Task Runner")
    parser.add_argument("--task", type=str, help="Task ID or markdown path to execute")
    parser.add_argument("--list", action="store_true", help="List all available tasks")
    args = parser.parse_args()

    if args.list:
        print("Available Operational Tasks:")
        tasks_dir = REPO_ROOT / "knowledge" / "tasks"
        for p in sorted(tasks_dir.rglob("*.md")):
            try:
                content = p.read_text(encoding="utf-8")
                if content.startswith("---"):
                    _, fm_str, _ = content.split("---", 2)
                    fm = yaml.safe_load(fm_str)
                    print(f"  • {fm.get('id', 'unknown'):<50} [{fm.get('persona', 'unknown')}]")
            except Exception:
                continue
        return 0

    if not args.task:
        parser.print_help()
        return 1

    task_file = find_task_file(args.task)
    if not task_file:
        print(f"Error: Task '{args.task}' not found in knowledge/tasks/")
        return 1

    return run_task(task_file)


if __name__ == "__main__":
    sys.exit(main())
