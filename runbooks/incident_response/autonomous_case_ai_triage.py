#!/usr/bin/env python3
"""Autonomous Incident Response & AI Triage Runbook.

Orchestrates deep AI-driven case investigation by delegating to the SecOps Engine's
canonical `case.ai_investigate` capability:
1. Gemini AI Summary Retrieval & Extraction: Fetches and parses case narrative, reasons, and next steps.
2. IOC & Telemetry Parsing: Identifies IP addresses, user identities, and file hashes.
3. Autonomous Threat Hunting (UDM Search): Executes UDM queries across Chronicle event store.
4. Case Escalation & Audit Trail: Sets incident state, escalates alert priority, and posts audit comments.
"""

from __future__ import annotations

import argparse
import sys
from typing import Optional

from engine.domain import CaseAiInvestigationResult
from engine.facade import SecOpsEngine
from engine.workflows.case_ai_investigation import extract_indicators

# Canonical alias for backward compatibility
AutonomousTriageResult = CaseAiInvestigationResult


def _extract_indicators(text: str) -> tuple[list[str], list[str]]:
    """Legacy helper for backward compatibility; delegates to extract_indicators."""
    ips, users, _ = extract_indicators(text)
    return ips, users


def run_autonomous_case_ai_triage(
    case_id: str = "104655",
    hunt_lookback_days: int = 14,
    hunt_receive_limit: int = 50,
    summary_timeout_sec: float = 90.0,
    dry_run: bool = False,
    engine: Optional[SecOpsEngine] = None,
) -> CaseAiInvestigationResult:
    """Executes the Autonomous AI Case Triage Runbook via SecOpsEngine.ai_investigate_case.

    Args:
        case_id: Target SecOps case identifier.
        hunt_lookback_days: Days of historical event telemetry to query.
        hunt_receive_limit: Event cap per indicator hunt query.
        summary_timeout_sec: Maximum time to poll while Gemini AI generates the case summary.
        dry_run: If True, performs read-only actions and skips mutations (escalations/comments).
        engine: Optional SecOpsEngine instance.

    Returns:
        CaseAiInvestigationResult containing all telemetry, findings, and action statuses.
    """
    if engine is None:
        engine = SecOpsEngine()

    print(f"[*] Starting Autonomous IR Runbook for Case {case_id} (dry_run={dry_run})...\n")

    res = engine.ai_investigate_case(
        case_id=case_id,
        hunt_lookback_days=hunt_lookback_days,
        hunt_receive_limit=hunt_receive_limit,
        summary_timeout_sec=summary_timeout_sec,
        escalate_incident=True,
        escalate_alert_priority="PRIORITY_CRITICAL",
        post_comment=True,
        dry_run=dry_run,
    )

    print(f"[+] Case Summary state: {res.summary_state}")
    if res.summary_text:
        print(f"    Summary: {res.summary_text[:140]}...\n")

    print("[+] Extracted Indicators:")
    print(f"    - IP Addresses: {res.extracted_ips}")
    print(f"    - Target Users: {res.extracted_users}")
    print(f"    - File Hashes:  {res.extracted_hashes}\n")

    print(f"[+] UDM Threat Hunt Telemetry: {len(res.hunt_results)} indicator(s) queried.")
    for ioc, count in res.hunt_results.items():
        print(f"    - {ioc}: {count if count >= 0 else 'Error/No Access'} events found")
    print()

    print("[+] Escalation & Audit Summary:")
    print(f"    - Incident Marked: {res.incident_marked}")
    print(f"    - Alert Escalated: {res.alert_escalated}")
    print(f"    - Audit Comment Posted: {res.comment_posted}\n")

    print("[*] Autonomous Runbook Complete.")
    return res


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
    if res.summary_state not in ("SUCCESSFUL", "IN_PROGRESS", "PENDING_START"):
        sys.exit(1)


if __name__ == "__main__":
    main()
