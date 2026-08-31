"""Google ADK Autonomous SIEM Parser Health Agent.

Connects the SecOps Engine SDK workflows to a Google ADK Agent
for proactive normalizer hygiene, CBN code analysis, version drift detection,
and parser extension conflict triage.
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
from engine.domain import ParserHealthReport, ParserHealthStatus

# ----------------------------------------------------------------------
# 1. SDK Tools Exposed to ADK
# ----------------------------------------------------------------------

_ENGINE: Optional[SecOpsEngine] = None


def get_engine() -> SecOpsEngine:
    global _ENGINE
    if _ENGINE is None:
        _ENGINE = SecOpsEngine()
    return _ENGINE


def audit_parsers(lookback_days: int = 7) -> str:
    """Audits all SIEM parsers and extensions against Health Hub telemetry and version drift.
    
    Args:
        lookback_days: Number of days of Health Hub telemetry to evaluate.
        
    Returns:
        JSON string containing the ParserHealthReport with status counts and detailed findings.
    """
    engine = get_engine()
    report = engine.audit_parser_health(lookback_days=lookback_days)

    findings_data = [
        {
            "log_type": f.log_type,
            "parser_id": f.parser_id,
            "status": f.status.value,
            "state": f.state,
            "creator_source": f.creator_source,
            "collector_name": f.collector_name,
            "version": f.version,
            "latest_version": f.latest_version,
            "rollback_available": f.rollback_available,
            "has_extension": f.has_extension,
            "extension_id": f.extension_id,
            "extension_state": f.extension_state,
            "dynamic_parsing_enabled": f.dynamic_parsing_enabled,
            "opted_fields_count": f.opted_fields_count,
            "drop_reason_code": f.drop_reason_code,
            "zscore_anomaly_detail": f.zscore_anomaly_detail,
            "anomalous_since": f.anomalous_since,
            "last_normalization_time": f.last_normalization_time,
            "event_latency": f.event_latency,
            "volume_funnel": f.volume_funnel,
            "quota_rejected_volume_mb": f.quota_rejected_volume_mb,
            "quota_limit_mb_per_sec": f.quota_limit_mb_per_sec,
            "anomaly_description": f.anomaly_description,
            "remediation_steps": f.remediation_steps,
        }
        for f in report.findings
    ]

    result = {
        "summary": {
            "total_parsers_audited": report.total_parsers_audited,
            "healthy_count": report.healthy_count,
            "irregular_count": report.irregular_count,
            "failed_count": report.failed_count,
            "version_drift_count": report.version_drift_count,
            "extension_conflict_count": report.extension_conflict_count,
            "quota_rejections_detected": report.quota_rejections_detected,
            "generated_at": report.generated_at.isoformat(),
        },
        "findings": findings_data,
    }
    return json.dumps(result, indent=2)


def get_parser_cbn(log_type: str, parser_id: Optional[str] = None) -> str:
    """Retrieves full parser metadata and decodes CBN Logstash filter code for syntax review.
    
    Args:
        log_type: The log type identifier (e.g. 'CS_EDR', 'A10_LOAD_BALANCER').
        parser_id: Optional specific parser ID. If omitted, fetches active parser.
        
    Returns:
        JSON string with decoded CBN code, version info, and validation report.
    """
    engine = get_engine()
    detail = engine.get_parser(log_type=log_type, parser_id=parser_id)
    return json.dumps(
        {
            "id": detail.summary.id,
            "log_type": detail.summary.log_type,
            "state": detail.summary.state,
            "creator": detail.summary.creator_source,
            "version": detail.summary.version,
            "latest_version": detail.summary.latest_version,
            "cbn_code": detail.cbn_code,
            "validation_report": detail.validation_report,
        },
        indent=2,
    )


def get_parser_extension_details(log_type: str, extension_id: str) -> str:
    """Retrieves parser extension snippet, dynamic parsing fields, and sample log.
    
    Args:
        log_type: The log type identifier.
        extension_id: The extension UUID.
        
    Returns:
        JSON string with decoded extension snippet, dynamic parsing fields, and test log.
    """
    engine = get_engine()
    detail = engine.get_parser_extension(log_type=log_type, extension_id=extension_id)
    return json.dumps(
        {
            "id": detail.summary.id,
            "log_type": detail.summary.log_type,
            "state": detail.summary.state,
            "has_dynamic_parsing": detail.summary.has_dynamic_parsing,
            "opted_fields": detail.opted_fields,
            "cbn_snippet": detail.cbn_snippet,
            "sample_log": detail.sample_log,
            "validation_report": detail.validation_report,
        },
        indent=2,
    )


# ----------------------------------------------------------------------
# 2. ADK Agent Factory
# ----------------------------------------------------------------------

SYSTEM_INSTRUCTION = """You are the SecOps Parser Health Agent, an autonomous security operations agent.
Your mission is to continuously audit, evaluate, and safeguard data normalizers and CBN parsers in Google SecOps.

Guidelines:
1. Call `audit_parsers()` to discover all active/inactive parsers, extensions, and real-time Health Hub normalizer drop reasons.
2. For any FAILED or IRREGULAR log type, call `get_parser_cbn()` to inspect the Logstash CBN code and validation report.
3. For any EXTENSION_CONFLICT or when analyzing customized field extractions, call `get_parser_extension_details()` to inspect dynamic fields and CBN snippets.
4. Flag VERSION_DRIFT when a tenant is running an older Google default parser version while an updated release is available.
5. Provide structured, actionable remediation guidance (e.g. syntax fixes, parser upgrades, field mapping adjustments).
"""


def create_parser_agent():
    """Creates a configured Google ADK Agent instance."""
    try:
        from google.adk import Agent
        from google.adk.tools import FunctionTool

        tools = [
            FunctionTool(audit_parsers),
            FunctionTool(get_parser_cbn),
            FunctionTool(get_parser_extension_details),
        ]

        agent = Agent(
            name="secops_parser_health_agent",
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
    print("  Google SecOps Autonomous Parser Health Agent (Direct Audit Mode)")
    print("==================================================================\n")

    report_json = audit_parsers()
    report = json.loads(report_json)
    summary = report["summary"]
    findings = report["findings"]

    print(f"Audit Timestamp: {summary['generated_at']}")
    print(f"Total Log Types Audited: {summary['total_parsers_audited']}")
    print(f"  • Healthy:            {summary['healthy_count']}")
    print(f"  • Irregular:          {summary['irregular_count']}")
    print(f"  • Failed/Critical:    {summary['failed_count']}")
    print(f"  • Version Drift:      {summary['version_drift_count']}")
    print(f"  • Extension Conflict: {summary['extension_conflict_count']}")
    print(f"  • Quota Drops:        {summary.get('quota_rejections_detected', 0)}\n")

    # Group findings for clean output
    actionable = [f for f in findings if f["status"] != "HEALTHY"]
    healthy = [f for f in findings if f["status"] == "HEALTHY"]

    if actionable:
        print("Actionable Parser Findings:")
        for f in actionable:
            status_tag = f"[{f['status']}]".ljust(22)
            ext_tag = f" (Extension: {f['extension_state']})" if f["has_extension"] else ""
            coll_str = f" | Collector: {f['collector_name']}" if f.get("collector_name") else ""
            print(f"  {status_tag} Log Type: {f['log_type']}{ext_tag}")
            ver_str = f"v{f['version']}" if f["version"] else "N/A"
            if f.get("latest_version") and f.get("version"):
                if f["version"] == f["latest_version"]:
                    ver_str += f" (Latest: v{f['latest_version']} - Up to date)"
                else:
                    ver_str += f" (Latest: v{f['latest_version']} - Upgrade Available!)"
            if f.get("rollback_available"):
                ver_str += " [Rollback Available]"

            print(f"                         Creator: {f['creator_source']} | State: {f['state']} | Version: {ver_str}{coll_str}")
            if f.get("quota_rejected_volume_mb", 0) > 0:
                print(f"                         Quota Alert: {f['quota_rejected_volume_mb']:.2f} MB dropped (Limit: {f.get('quota_limit_mb_per_sec', 0):.1f} MB/s)")
            if f.get("volume_funnel") and f["volume_funnel"].get("total_logs", 0) > 0:
                fn = f["volume_funnel"]
                print(f"                         Funnel: Ingested={fn.get('total_logs', 0):,} | Parsed={fn.get('normalized_events', 0):,} | Parsing Errors={fn.get('parsing_error_events', 0):,}")
            if f.get("zscore_anomaly_detail"):
                print(f"                         Statistical Z-Score: {f['zscore_anomaly_detail']}")
            if f["drop_reason_code"]:
                print(f"                         Drop Reason: {f['drop_reason_code']}")
            if f["anomalous_since"]:
                print(f"                         Anomalous Since: {f['anomalous_since']}")
            if f["event_latency"]:
                print(f"                         Ingestion Latency: {f['event_latency']}")
            print(f"                         Details: {f['anomaly_description']}")
            if f["remediation_steps"]:
                print(f"                         Remediation: {', '.join(f['remediation_steps'])}")
            print()

    print(f"Healthy Normalizers: {len(healthy)} log types operating normally without drop reasons or version drift.")


if __name__ == "__main__":
    run_direct_audit()
