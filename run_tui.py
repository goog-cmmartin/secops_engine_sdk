#!/usr/bin/env python3
"""Launcher for the SecOps TUI proof-of-concept.

Run from anywhere; this script anchors ``sys.path`` to the project root so the
facade's root-relative imports (``from adapters.google_secops import ...``)
resolve correctly.

Usage:
    python run_tui.py                     # live engine (needs configured creds)
    python run_tui.py --query "..."       # seed the search box
    python run_tui.py --demo              # offline: fake data, no API calls
"""
from __future__ import annotations

import argparse
import os
import sys

# --- anchor project root (invariant #2 from clients/tui/__init__.py) ------
_ROOT = os.path.dirname(os.path.abspath(__file__))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)


def _build_demo_engine():
    """A minimal stand-in exposing only the two methods the POC calls.

    Lets us validate layout / threading / rendering with zero live dependency.
    """
    from datetime import datetime, timedelta
    from engine.domain import (
        CaseSearchBatch,
        CaseSearchResultItem,
        CaseInvestigation,
        CaseAlertSummary,
        InvolvedEntitySummary,
        CasePriority,
        CaseStatus,
    )

    now = datetime.now()
    demo_items = [
        CaseSearchResultItem(
            case_id=str(1000 + i),
            title=title,
            create_time=now - timedelta(hours=i * 3),
            priority=pri,
            stage=stage,
            tags=[],
            products=["Chronicle"],
            user_assigned=assignee,
            is_important=(i % 3 == 0),
            is_incident=(i % 4 == 0),
            is_closed=False,
            alerts_count=alerts,
            environment="Default",
            ticket_ids=[],
            ports=[],
            raw={},
        )
        for i, (title, pri, stage, assignee, alerts) in enumerate([
            ("Suspected credential phishing burst", CasePriority.CRITICAL, "Triage", "amartin", 4),
            ("Impossible travel — VPN + on-prem", CasePriority.HIGH, "Investigation", "bchen", 2),
            ("Malware beacon to known C2", CasePriority.HIGH, "Triage", None, 6),
            ("Excessive failed logins (svc acct)", CasePriority.MEDIUM, "Assessment", "amartin", 1),
            ("DLP: bulk export to personal drive", CasePriority.MEDIUM, "Investigation", None, 3),
            ("Port scan from internal host", CasePriority.LOW, "Triage", "dpatel", 1),
        ])
    ]

    class _DemoEngine:
        def search_cases(self, query="", page_size=50, **_):
            items = demo_items
            if query:
                q = query.lower()
                items = [it for it in demo_items if q in it.title.lower()]
            return CaseSearchBatch(
                results=items,
                total_count=len(items),
                page_size=page_size,
                page_number=0,
                provenance={"demo": True},
            )

        def investigate_case(self, case_id):
            src = next((it for it in demo_items if it.case_id == str(case_id)), demo_items[0])
            return CaseInvestigation(
                case_id=src.case_id,
                name=f"cases/{src.case_id}",
                display_name=src.title,
                status=CaseStatus.OPEN,
                priority=src.priority,
                stage=src.stage,
                create_time=src.create_time,
                update_time=now,
                assignee=src.user_assigned,
                alert_count=src.alerts_count,
                alerts=[
                    CaseAlertSummary(
                        name=f"cases/{src.case_id}/alerts/{j}",
                        identifier=f"alert-{j}",
                        display_name=f"{src.title} — alert {j+1}",
                        priority=src.priority.name,
                        status="OPEN",
                        product="Chronicle",
                        vendor="Google",
                        event_count=(j + 1) * 5,
                        start_time=src.create_time,
                        end_time=now,
                        rule_name="demo_rule",
                        attached_playbook_name="Auto-Triage" if j == 0 else None,
                        playbook_status="Completed" if j == 0 else None,
                        playbook_run_count=1 if j == 0 else 0,
                        alert_group_identifier=None,
                        raw={},
                    )
                    for j in range(min(src.alerts_count, 3))
                ],
                entities=[
                    InvolvedEntitySummary(
                        identifier="jdoe@corp.example",
                        display_name="jdoe@corp.example",
                        entity_type="USER",
                        role="source",
                        is_suspicious=True,
                        raw={},
                    ),
                    InvolvedEntitySummary(
                        identifier="10.0.4.17",
                        display_name="10.0.4.17",
                        entity_type="IP",
                        role="target",
                        is_suspicious=False,
                        raw={},
                    ),
                ],
                comments=[],
                provenance={"demo": True},
                raw_case={},
            )

    return _DemoEngine()


def main() -> int:
    parser = argparse.ArgumentParser(description="SecOps TUI proof-of-concept")
    parser.add_argument("--query", default="", help="seed the case search box")
    parser.add_argument("--demo", action="store_true", help="offline demo mode (no API calls)")
    parser.add_argument("--page-size", type=int, default=50)
    args = parser.parse_args()

    try:
        from clients.tui.app import SecOpsTUI
    except ModuleNotFoundError as exc:
        if "textual" in str(exc):
            print("Textual is not installed. Run: pip install -r clients/tui/requirements-tui.txt", file=sys.stderr)
            return 2
        raise

    if args.demo:
        engine = _build_demo_engine()
    else:
        from engine.facade import SecOpsEngine
        try:
            engine = SecOpsEngine()
        except Exception as exc:
            print(f"Failed to construct SecOpsEngine (creds/config?): {exc}", file=sys.stderr)
            print("Tip: use --demo to preview the UI without live credentials.", file=sys.stderr)
            return 3

    SecOpsTUI(engine=engine, initial_query=args.query, page_size=args.page_size).run()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
