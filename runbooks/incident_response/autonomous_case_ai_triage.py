#!/usr/bin/env python3
"""Autonomous Incident Response & AI Triage Runbook.

Orchestrates a 4-stage autonomous loop directly through the Google SecOps SDK:
1. Gemini AI Summary Retrieval & Extraction: Fetches and parses case narrative, reasons, and next steps.
2. IOC & Telemetry Parsing: Identifies IP addresses and email identities.
3. Autonomous Threat Hunting (UDM Search): Executes UDM queries across Chronicle event store.
4. Case Escalation & Audit Trail: Sets incident state, escalates alert priority, and posts audit comments.
"""

from __future__ import annotations

import argparse
import re
import sys
import urllib.parse
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional

from engine.facade import SecOpsEngine
from engine.domain import SearchRequest, CaseSummary


def _extract_indicators(text: str) -> tuple[List[str], List[str]]:
    """Extracts IPv4/IPv6 addresses and user identities from plain text and entity annotations."""
    decoded_text = urllib.parse.unquote(text)

    entity_addresses = re.findall(r"\[\[\[([^|]+)\|ADDRESS\|\d+\]\]\]", decoded_text)
    entity_users = re.findall(r"\[\[\[([^|]+)\|USERUNIQNAME\|\d+\]\]\]", decoded_text)

    ipv4_matches = re.findall(r"\b(?:[0-9]{1,3}\.){3}[0-9]{1,3}\b", decoded_text)
    ipv6_matches = re.findall(r"\b(?:[a-fA-F0-9]{1,4}:){3,7}[a-fA-F0-9]{1,4}\b", decoded_text)
    user_matches = re.findall(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b", decoded_text)

    all_ips = sorted(list(set(ipv4_matches + ipv6_matches + entity_addresses)))
    valid_ips = [ip for ip in all_ips if not ip.startswith("0.0.0") and not ip.startswith("255.255")]

    all_users = sorted(list(set(user_matches + entity_users)))

    return valid_ips, all_users


@dataclass
class AutonomousTriageResult:
    case_id: str
    summary_state: str
    summary_text: Optional[str] = None
    extracted_ips: List[str] = field(default_factory=list)
    extracted_users: List[str] = field(default_factory=list)
    hunt_results: Dict[str, int] = field(default_factory=dict)
    primary_alert_id: Optional[str] = None
    incident_marked: bool = False
    alert_escalated: bool = False
    comment_posted: bool = False
    audit_comment: Optional[str] = None
    dry_run: bool = False


def run_autonomous_case_ai_triage(
    case_id: str = "104655",
    hunt_lookback_days: int = 14,
    hunt_receive_limit: int = 50,
    summary_timeout_sec: float = 90.0,
    dry_run: bool = False,
    engine: Optional[SecOpsEngine] = None,
) -> AutonomousTriageResult:
    """Executes the Autonomous AI Case Triage Runbook.

    Args:
        case_id: Target SecOps case identifier.
        hunt_lookback_days: Days of historical event telemetry to query.
        hunt_receive_limit: Event cap per indicator hunt query.
        summary_timeout_sec: Maximum time to poll while Gemini AI generates the case summary.
        dry_run: If True, performs read-only actions and skips mutations (escalations/comments).
        engine: Optional SecOpsEngine instance.

    Returns:
        AutonomousTriageResult containing all telemetry, findings, and action statuses.
    """
    if engine is None:
        engine = SecOpsEngine()

    print(f"[*] Starting Autonomous IR Runbook for Case {case_id} (dry_run={dry_run})...\n")

    # =========================================================================
    # Step 1: Retrieve and Poll Case AI Summary
    # =========================================================================
    print(f"[1/4] Fetching Gemini AI Case Summary (polling timeout: {summary_timeout_sec}s)...")
    summary: CaseSummary = engine.get_case_summary(case_id=case_id, timeout_sec=summary_timeout_sec)

    if summary.state != "SUCCESSFUL":
        print(f"[-] Summary state: {summary.state}. Halting runbook.")
        return AutonomousTriageResult(
            case_id=case_id,
            summary_state=summary.state,
            summary_text=summary.summary,
            dry_run=dry_run,
        )

    print(f"[+] Case Summary retrieved successfully (State: {summary.state})")
    if summary.summary:
        print(f"    Summary: {summary.summary[:140]}...\n")

    # =========================================================================
    # Step 2: Extract IOCs from Case Alerts & Summary
    # =========================================================================
    print("[2/4] Parsing Indicators and Telemetry Boundaries...")
    alerts = engine.adapter.list_case_alerts(case_id=case_id)
    primary_alert_id = None
    if alerts:
        primary_alert_id = alerts[0].get("name", "").split("/")[-1]
        print(f"[+] Found {len(alerts)} alert(s). Primary Alert ID: {primary_alert_id}")

    combined_text = " ".join(summary.reasons + summary.next_steps + [summary.summary or ""])
    all_ips, sorted_users = _extract_indicators(combined_text)

    print(f"[+] Extracted Indicators:")
    print(f"    - IP Addresses: {all_ips}")
    print(f"    - Target Users: {sorted_users}\n")

    # =========================================================================
    # Step 3: Threat Hunting via UDM Search
    # =========================================================================
    print(f"[3/4] Scoping Activity via UDM Threat Hunt (last {hunt_lookback_days} days)...")
    now = datetime.now(timezone.utc)
    start_time = (now - timedelta(days=hunt_lookback_days)).strftime("%Y-%m-%dT%H:%M:%SZ")
    end_time = now.strftime("%Y-%m-%dT%H:%M:%SZ")

    hunt_results: Dict[str, int] = {}

    for ip in all_ips:
        query = f'principal.ip = "{ip}" or target.ip = "{ip}"'
        req = SearchRequest(
            query=query,
            start_time=start_time,
            end_time=end_time,
            receive_limit=hunt_receive_limit,
        )
        try:
            session = engine.search_udm(req)
            hunt_results[ip] = session.received_count
            print(f"    [UDM] Hunt for IP {ip}: {session.received_count} events found.")
        except Exception as e:
            print(f"    [!] Hunt error for IP {ip}: {e}")
            hunt_results[ip] = -1

    for user in sorted_users:
        query = f'principal.user.userid = "{user}" or target.user.userid = "{user}"'
        req = SearchRequest(
            query=query,
            start_time=start_time,
            end_time=end_time,
            receive_limit=hunt_receive_limit,
        )
        try:
            session = engine.search_udm(req)
            hunt_results[user] = session.received_count
            print(f"    [UDM] Hunt for User {user}: {session.received_count} events found.")
        except Exception as e:
            print(f"    [!] Hunt error for User {user}: {e}")
            hunt_results[user] = -1

    print()

    # =========================================================================
    # Step 4: Case Lifecycle Escalation & Audit Comment
    # =========================================================================
    print(f"[4/4] Escalating Case Lifecycle and Logging Audit Record (dry_run={dry_run})...")

    incident_marked = False
    alert_escalated = False
    comment_posted = False

    # 4a. Mark Case as Incident
    if not dry_run:
        inc_update = engine.set_case_incident(case_id=case_id, incident=True)
        incident_marked = inc_update.incident
        print(f"[+] Case {case_id} incident flag set to: {inc_update.incident} (Stage: {inc_update.stage})")
    else:
        print(f"[*] [DRY-RUN] Would set case {case_id} incident flag to True.")

    # 4b. Elevate Primary Alert Priority
    if primary_alert_id:
        if not dry_run:
            prio_update = engine.set_case_alert_priority(
                case_id=case_id,
                alert_id=primary_alert_id,
                priority="PRIORITY_CRITICAL",
            )
            alert_escalated = True
            print(f"[+] Alert {primary_alert_id} priority set to: {prio_update.priority}")
        else:
            print(f"[*] [DRY-RUN] Would set alert {primary_alert_id} priority to PRIORITY_CRITICAL.")

    # 4c. Construct Audit Comment
    hunt_summary_lines = "\n".join(
        [f"- `{ioc}`: {count if count >= 0 else 'Error/No Access'} events found" for ioc, count in hunt_results.items()]
    )
    reasons_text = "\n".join([f"- {r}" for r in summary.reasons])
    next_steps_text = "\n".join([f"- {s}" for s in summary.next_steps])

    audit_comment = f"""### [ASOC Autonomous Incident Response Report]
**Threat Context**: {summary.summary}

**Underlying Evidence & MITRE ATT&CK**:
{reasons_text}

**Automated Threat Hunt Telemetry**:
{hunt_summary_lines}

**Actions Taken**:
- Elevated Case to Active Incident (`incident=True`).
- Escalated Primary Alert `{primary_alert_id}` to `PRIORITY_CRITICAL`.

**Pending Manual Operator Actions**:
{next_steps_text}
"""

    if not dry_run:
        comment_res = engine.add_case_comment(case_id=case_id, comment=audit_comment)
        comment_posted = True
        print(f"[+] Investigation comment posted successfully (Resource: {comment_res.name})\n")
    else:
        print(f"[*] [DRY-RUN] Would post investigation comment to case {case_id}.\n")

    print("[*] Autonomous Runbook Complete.")

    return AutonomousTriageResult(
        case_id=case_id,
        summary_state=summary.state,
        summary_text=summary.summary,
        extracted_ips=all_ips,
        extracted_users=sorted_users,
        hunt_results=hunt_results,
        primary_alert_id=primary_alert_id,
        incident_marked=incident_marked,
        alert_escalated=alert_escalated,
        comment_posted=comment_posted,
        audit_comment=audit_comment,
        dry_run=dry_run,
    )


def main():
    parser = argparse.ArgumentParser(description="Autonomous Incident Response & AI Triage Runbook")
    parser.add_argument("--case-id", "-c", default="104655", help="Target SecOps case ID (default: 104655)")
    parser.add_argument("--lookback-days", type=int, default=14, help="Threat hunt telemetry lookback days (default: 14)")
    parser.add_argument("--limit", type=int, default=50, help="Per-query threat hunt event cap (default: 50)")
    parser.add_argument("--timeout", type=float, default=90.0, help="Summary polling timeout in seconds (default: 90)")
    parser.add_argument("--dry-run", action="store_true", help="Execute in read-only preview mode")
    args = parser.parse_args()

    res = run_autonomous_case_ai_triage(
        case_id=args.case_id,
        hunt_lookback_days=args.lookback_days,
        hunt_receive_limit=args.limit,
        summary_timeout_sec=args.timeout,
        dry_run=args.dry_run,
    )
    if res.summary_state != "SUCCESSFUL":
        sys.exit(1)


if __name__ == "__main__":
    main()
