"""Google ADK Autonomous Feed Health Agent.

Connects the SecOps Engine SDK workflows to a Google ADK Agent
for proactive feed decay detection, telemetry correlation, and triage.
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
from engine.domain import FeedHealthReport, FeedHealthStatus

# ----------------------------------------------------------------------
# 1. SDK Tools Exposed to ADK
# ----------------------------------------------------------------------

# Global engine instance for ADK tool execution
_ENGINE: Optional[SecOpsEngine] = None


def get_engine() -> SecOpsEngine:
    global _ENGINE
    if _ENGINE is None:
        _ENGINE = SecOpsEngine()
    return _ENGINE


def audit_feeds(lookback_days: int = 7) -> str:
    """Audits all configured SecOps ingestion feeds against Health Hub telemetry and decay indicators.
    
    Args:
        lookback_days: Number of days of Health Hub telemetry to evaluate.
        
    Returns:
        JSON string containing the FeedHealthReport with status counts and detailed findings.
    """
    engine = get_engine()
    report = engine.audit_feed_health(lookback_days=lookback_days)
    
    findings_data = [
        {
            "feed_id": f.feed_id,
            "feed_name": f.feed_name,
            "source_type": f.source_type,
            "log_type": f.log_type,
            "status": f.status.value,
            "state": f.state,
            "collector_name": f.collector_name,
            "latency_p95": f.latency_p95,
            "last_event_time": f.last_event_time,
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
            "total_feeds_audited": report.total_feeds_audited,
            "healthy_count": report.healthy_count,
            "irregular_count": report.irregular_count,
            "failed_count": report.failed_count,
            "high_latency_count": report.high_latency_count,
            "quota_rejections_detected": report.quota_rejections_detected,
            "generated_at": report.generated_at.isoformat(),
        },
        "findings": findings_data,
    }
    return json.dumps(result, indent=2)


def get_feed_details(feed_id_or_title: str) -> str:
    """Retrieves full configuration details and source parameters for a specific ingestion feed.
    
    Args:
        feed_id_or_title: Feed UUID or exact display name.
        
    Returns:
        JSON string with source configuration, endpoint parameters, and ingestion settings.
    """
    engine = get_engine()
    detail = engine.get_feed(feed_id_or_title)
    return json.dumps(
        {
            "id": detail.summary.id,
            "display_name": detail.summary.display_name,
            "state": detail.summary.state,
            "feed_source_type": detail.summary.feed_source_type,
            "log_type": detail.summary.log_type,
            "details": detail.details,
        },
        indent=2,
    )


# ----------------------------------------------------------------------
# 2. ADK Agent Factory
# ----------------------------------------------------------------------

SYSTEM_INSTRUCTION = """You are the SecOps Feed Health Agent, an autonomous security operations agent.
Your mission is to continuously audit, evaluate, and safeguard data ingestion pipelines into Google SecOps.

Guidelines:
1. Call `audit_feeds()` to discover all configured feeds and their real-time Health Hub telemetry.
2. If any feed is in a FAILED, IRREGULAR, or HIGH_LATENCY state, call `get_feed_details()` to inspect source parameters (e.g. S3 buckets, PubSub subscriptions, IAM roles).
3. Distinguish between Push feeds (e.g. PubSub, HTTPS push) and Pull feeds (e.g. S3, API). Note that Push feeds can fail silently without initiation errors.
4. Provide structured findings with severity, root-cause assessment, and actionable remediation steps.
"""


def create_feed_agent():
    """Creates a configured Google ADK Agent instance."""
    try:
        from google.adk import Agent
        from google.adk.tools import FunctionTool

        tools = [
            FunctionTool(audit_feeds),
            FunctionTool(get_feed_details),
        ]

        agent = Agent(
            name="secops_feed_health_agent",
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
    print("================================================================")
    print("  Google SecOps Autonomous Feed Health Agent (Direct Audit Mode)")
    print("================================================================\n")
    
    report_json = audit_feeds()
    report = json.loads(report_json)
    summary = report["summary"]
    findings = report["findings"]
    
    print(f"Audit Timestamp: {summary['generated_at']}")
    print(f"Total Feeds Audited: {summary['total_feeds_audited']}")
    print(f"  • Healthy:          {summary['healthy_count']}")
    print(f"  • Irregular:        {summary['irregular_count']}")
    print(f"  • High Latency:     {summary['high_latency_count']}")
    print(f"  • Failed/Silent:    {summary['failed_count']}")
    print(f"  • Quota Drops:      {summary.get('quota_rejections_detected', 0)}\n")
    
    print("Feed Findings:")
    for f in findings:
        status_tag = f"[{f['status']}]".ljust(15)
        print(f"  {status_tag} {f['feed_name']} ({f['log_type']})")
        coll_str = f" | Collector: {f['collector_name']}" if f.get('collector_name') else ""
        print(f"                  Type: {f['source_type']} | State: {f['state']}{coll_str}")
        if f.get('quota_rejected_volume_mb', 0) > 0:
            print(f"                  Quota Alert: {f['quota_rejected_volume_mb']:.2f} MB rejected (Limit: {f.get('quota_limit_mb_per_sec', 0):.1f} MB/s)")
        if f.get('volume_funnel') and f['volume_funnel'].get('total_logs', 0) > 0:
            fn = f['volume_funnel']
            print(f"                  Funnel: Ingested={fn.get('total_logs', 0):,} | Parsed={fn.get('normalized_events', 0):,} | Parsing Errors={fn.get('parsing_error_events', 0):,}")
        if f['latency_p95']:
            print(f"                  P95 Latency: {f['latency_p95']}")
        if f['last_event_time']:
            print(f"                  Last Initiation: {f['last_event_time']}")
        print(f"                  Details: {f['anomaly_description']}")
        if f['remediation_steps']:
            print(f"                  Remediation: {', '.join(f['remediation_steps'])}")
        print()


if __name__ == "__main__":
    run_direct_audit()
