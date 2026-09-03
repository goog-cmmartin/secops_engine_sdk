"""Google ADK Autonomous SIEM Rule & Detection Health Agent.

Connects the SecOps Engine SDK workflows to a Google ADK Agent
for proactive detection health monitoring, YARA-L compiler diagnostics,
runtime execution error triage, detection decay analysis, and latency observability.
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
from engine.domain import RuleHealthReport, RuleHealthStatus

# ----------------------------------------------------------------------
# 1. SDK Tools Exposed to ADK
# ----------------------------------------------------------------------

_ENGINE: Optional[SecOpsEngine] = None


def get_engine() -> SecOpsEngine:
    global _ENGINE
    if _ENGINE is None:
        _ENGINE = SecOpsEngine()
    return _ENGINE


def audit_rules(
    include_curated: bool = True,
    latency_threshold_min: float = 30.0,
) -> str:
    """Audits all SIEM detection rules against execution errors, latency observability, and detection decay.

    Args:
        include_curated: Whether to include Google curated rulesets in the audit.
        latency_threshold_min: Latency threshold in minutes to flag slow detection rules.

    Returns:
        JSON string containing the RuleHealthReport with status counts and detailed findings.
    """
    engine = get_engine()
    report = engine.audit_rule_health(
        include_curated=include_curated,
        latency_threshold_min=latency_threshold_min,
    )

    findings_data = [
        {
            "rule_id": f.rule_id,
            "display_name": f.display_name,
            "rule_owner": f.rule_owner,
            "severity": f.severity,
            "status": f.status.value,
            "enabled": f.enabled,
            "alerting": f.alerting,
            "run_frequency": f.run_frequency,
            "detection_count_recent": f.detection_count_recent,
            "execution_error_count": f.execution_error_count,
            "last_error_message": f.last_error_message,
            "ingestion_to_detection_latency_min": f.ingestion_to_detection_latency_min,
            "event_to_detection_latency_min": f.event_to_detection_latency_min,
            "mitre_tactics": f.mitre_tactics,
            "mitre_techniques": f.mitre_techniques,
            "details": f.details,
            "remediation_steps": f.remediation_steps,
        }
        for f in report.findings
    ]

    result = {
        "summary": {
            "total_rules_audited": report.total_rules_audited,
            "healthy_count": report.healthy_count,
            "failing_count": report.failing_count,
            "decay_count": report.decay_count,
            "latency_alert_count": report.latency_alert_count,
            "misconfigured_count": report.misconfigured_count,
            "disabled_count": report.disabled_count,
            "total_detections_24h": report.total_detections_24h,
            "average_risk_score": report.average_risk_score,
            "top_mitre_tactics": report.top_mitre_tactics,
            "top_threat_categories": report.top_threat_categories,
            "generated_at": report.generated_at.isoformat(),
        },
        "findings": findings_data,
    }
    return json.dumps(result, indent=2)


def get_rule_source(rule_id_or_name: str) -> str:
    """Retrieves full YARA-L rule text, author metadata, and compilation diagnostics.

    Args:
        rule_id_or_name: The rule resource name or unique UUID.

    Returns:
        JSON string containing rule logic, author, revision, and compilation status.
    """
    engine = get_engine()
    detail = engine.get_rule(rule_id_or_name=rule_id_or_name)
    return json.dumps(
        {
            "name": detail.name,
            "rule_id": detail.rule_id,
            "display_name": detail.display_name,
            "author": detail.author,
            "severity": detail.severity,
            "compilation_state": detail.compilation_state,
            "rule_text": detail.rule_text,
            "revision_create_time": detail.revision_create_time,
        },
        indent=2,
    )


def validate_yara_l_rule(rule_text: str) -> str:
    """Compiles and validates YARA-L rule syntax against the Chronicle compiler.

    Args:
        rule_text: The complete YARA-L 2.0 rule string.

    Returns:
        JSON string with compiler success status and detailed compilation diagnostics.
    """
    engine = get_engine()
    res = engine.verify_rule(rule_text=rule_text)
    return json.dumps(
        {
            "success": res.success,
            "diagnostics": [
                {
                    "message": d.message,
                    "position": {
                        "start_line": d.position.start_line,
                        "start_column": d.position.start_column,
                        "end_line": d.position.end_line,
                        "end_column": d.position.end_column,
                    } if d.position else None,
                }
                for d in res.diagnostics
            ],
        },
        indent=2,
    )


def get_rule_execution_errors(rule_id_or_name: Optional[str] = None) -> str:
    """Lists runtime and execution errors across detection rules.

    Args:
        rule_id_or_name: Optional filter for a specific rule resource name.

    Returns:
        JSON string containing error codes, timestamps, and error messages.
    """
    engine = get_engine()
    res = engine.list_rule_errors(rule_id_or_name=rule_id_or_name)
    return json.dumps(
        {
            "count": len(res.errors),
            "errors": [
                {
                    "rule": e.rule_resource_name,
                    "curated_rule": e.curated_rule,
                    "error_code": e.error_code,
                    "error_message": e.error_message,
                    "start_time": e.start_time,
                    "end_time": e.end_time,
                }
                for e in res.errors
            ],
        },
        indent=2,
    )


# ----------------------------------------------------------------------
# 2. ADK Agent Factory
# ----------------------------------------------------------------------

SYSTEM_INSTRUCTION = """You are the SecOps Rule & Detection Health Agent, an autonomous security operations agent.
Your mission is to continuously monitor, diagnose, and safeguard Chronicle detection rules and curated rulesets.

Guidelines:
1. Call `audit_rules()` to audit all active/inactive detection rules, execution errors, latency numbers, and detection decay.
2. For any rule with EXECUTION_ERROR or COMPILATION_ERROR, call `get_rule_execution_errors()` and `get_rule_source()` to inspect YARA-L syntax and error messages.
3. For proposed rule repairs or optimizations, call `validate_yara_l_rule()` to verify that the fixed YARA-L compiles cleanly.
4. For rules flagged with HIGH_LATENCY, evaluate the match window duration and event conditions to recommend index and window optimizations.
5. Provide structured, actionable remediation guidance (e.g. syntax fixes, sliding window adjustments, log source coverage checks).
"""


def create_rule_agent():
    """Creates a configured Google ADK Agent instance."""
    try:
        from google.adk import Agent
        from google.adk.tools import FunctionTool

        tools = [
            FunctionTool(audit_rules),
            FunctionTool(get_rule_source),
            FunctionTool(validate_yara_l_rule),
            FunctionTool(get_rule_execution_errors),
        ]

        agent = Agent(
            name="secops_rule_health_agent",
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
    print("==================================================================")
    print("  Google SecOps Autonomous Rule Health Agent (Direct Audit Mode)")
    print("==================================================================\n")

    report_json = audit_rules()
    report = json.loads(report_json)
    summary = report["summary"]
    findings = report["findings"]

    print(f"Audit Timestamp: {summary['generated_at']}")
    print(f"Total Rules Audited: {summary['total_rules_audited']}")
    print(f"  • Healthy:            {summary['healthy_count']}")
    print(f"  • Failing/Errors:     {summary['failing_count']}")
    print(f"  • Silent Decay:       {summary['decay_count']}")
    print(f"  • High Latency Alert: {summary['latency_alert_count']}")
    print(f"  • Misconfigured:      {summary['misconfigured_count']}")
    print(f"  • Disabled:           {summary['disabled_count']}")
    print(f"  • Total Detections:   {summary.get('total_detections_24h', 0):,}")
    print(f"  • Average Risk Score: {summary.get('average_risk_score', 0.0):.1f}\n")

    # Group findings for clean output
    actionable = [f for f in findings if f["status"] != "HEALTHY"]
    healthy = [f for f in findings if f["status"] == "HEALTHY"]

    if actionable:
        print("Actionable Rule Findings:")
        for f in actionable:
            status_tag = f"[{f['status']}]".ljust(22)
            owner_tag = f"[{f['rule_owner']}]"
            freq_str = f"Freq: {f['run_frequency']}" if f.get("run_frequency") else "Freq: Live"
            print(f"  {status_tag} {owner_tag} Rule: {f['display_name']} ({f['rule_id']})")
            print(f"                         Severity: {f['severity']} | {freq_str} | Enabled: {f['enabled']} | Alerting: {f['alerting']}")
            if f.get("detection_count_recent", 0) > 0:
                print(f"                         Recent Detections: {f['detection_count_recent']:,}")
            if f.get("ingestion_to_detection_latency_min") is not None:
                print(f"                         Ingestion-to-Detection Latency: {f['ingestion_to_detection_latency_min']:.1f} min")
            if f.get("execution_error_count", 0) > 0:
                print(f"                         Execution Errors: {f['execution_error_count']} (Last: {f.get('last_error_message')})")
            print(f"                         Details: {f['details']}")
            if f["remediation_steps"]:
                print(f"                         Remediation: {', '.join(f['remediation_steps'])}")
            print()

    print(f"Healthy Detection Rules: {len(healthy)} rules operating normally without errors, latency lag, or silent decay.")


if __name__ == "__main__":
    run_direct_audit()
