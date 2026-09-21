"""SecOps Identity & Access Governance: Active vs Dormant Usage Verification.

Extracts privileged users and service accounts discovered by the SecOps
Inventory Access Governance report, then queries Chronicle UDM Search and
Raw Log Search via the SecOps Engine SDK to verify real-world activity.
"""

from __future__ import annotations

import json
import os
import re
import sys
from typing import Any, Dict, List, Tuple
import requests

# Ensure project root is on PYTHONPATH
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from engine.facade import SecOpsEngine


def run_identity_usage_audit(
    inventory_base_url: str = "http://localhost:8000",
    tenant_id: str = "37679061640",
    udm_window_days: int = 7,
    raw_log_lookback_hours: int = 48,
) -> None:
    print("=========================================================================================================")
    print("  SecOps Identity Governance: Active vs Dormant Account Audit (Inventory -> SDK)")
    print("=========================================================================================================\n")

    engine = SecOpsEngine()

    # Step 1: Pull identities from Inventory Service
    print(f"[*] Fetching Identity & Access Governance report from {inventory_base_url}...")
    accounts: List[Tuple[str, str, str]] = []

    try:
        resp = requests.get(f"{inventory_base_url}/api/reports/299", timeout=15)
        resp.raise_for_status()
        report_content = resp.json().get("report_content", "")
        # Parse emails and roles from markdown report
        for line in report_content.splitlines():
            # Matches: * **`email@domain`** — Role
            m = re.search(r"\*\s+\*\*`([^`]+@[^`]+)`\*\*\s+[—–-]\s+(.+)", line)
            if m:
                email = m.group(1).strip()
                role_desc = m.group(2).strip()
                acct_type = "Service Account" if "gserviceaccount.com" in email else "User"
                accounts.append((email, role_desc, acct_type))
            elif "serviceaccount.com" in line and "`" in line:
                for token in re.findall(r"`([^`]+@gserviceaccount\.com)`", line):
                    accounts.append((token, "Service Account", "Service Account"))
    except Exception as exc:
        print(f"[!] Warning: Could not reach inventory report 299 ({exc}). Using canonical governance baseline.")
        accounts = [
            ("admin@1823127835827.altostrat.com", "Chronicle Admin", "User"),
            ("jose.marin@1823127835827.altostrat.com", "Chronicle & SOAR Admin", "User"),
            ("slichtenstein@1823127835827.altostrat.com", "Chronicle Admin", "User"),
            ("sa-secops-inventory@webapps-397711.iam.gserviceaccount.com", "Chronicle Admin", "Service Account"),
            ("sa-chronicle-api@sdl-preview-americas.iam.gserviceaccount.com", "Chronicle & SOAR Admin", "Service Account"),
            ("sa-bp-to-secops-wif@sdl-preview-americas.iam.gserviceaccount.com", "Chronicle Admin", "Service Account"),
            ("demoverse-be@secops-demoverse-main.iam.gserviceaccount.com", "Chronicle & SOAR Admin", "Service Account"),
            ("sdl-preview-americas@sdl-preview-americas.iam.gserviceaccount.com", "Chronicle Admin", "Service Account"),
            ("wiz-to-secops@sdl-preview-americas.iam.gserviceaccount.com", "Chronicle Admin", "Service Account"),
            ("lieva@1823127835827.altostrat.com", "Chronicle Viewer", "User"),
            ("sa-sdl-tag-agentic-ai@webapps-397711.iam.gserviceaccount.com", "Chronicle Editor", "Service Account"),
            ("sa-sdl-et-replay@webapps-397711.iam.gserviceaccount.com", "Chronicle Viewer", "Service Account"),
        ]

    # De-duplicate preserving order
    seen = set()
    deduped_accounts = []
    for email, role, atype in accounts:
        if email not in seen:
            seen.add(email)
            deduped_accounts.append((email, role, atype))

    print(f"[+] Loaded {len(deduped_accounts)} privileged and service account identities for verification.\n")

    # Time bounds
    from datetime import datetime, timezone, timedelta
    now = datetime.now(timezone.utc)
    start_dt = now - timedelta(days=udm_window_days)
    start_time_iso = start_dt.strftime("%Y-%m-%dT%H:%M:%SZ")
    end_time_iso = now.strftime("%Y-%m-%dT%H:%M:%SZ")

    audit_records = []

    print(f"[*] Scanning Chronicle UDM ({udm_window_days}d window) & Raw Logs ({raw_log_lookback_hours}h window)...")
    for email, role, atype in deduped_accounts:
        # 1. Primary Check: Chronicle UDM Search
        udm_query = f"principal.user.userid = \"{email}\" or target.user.userid = \"{email}\""
        session = engine.search_udm(
            query=udm_query,
            start_time=start_time_iso,
            end_time=end_time_iso,
            limit=5,
        )
        udm_count = len(session.events)
        latest_ts = "None"
        products: List[str] = []

        if udm_count > 0:
            latest_ts = session.events[0].metadata.event_timestamp or "Recent"
            prods = {e.metadata.product_name for e in session.events if e.metadata.product_name}
            products = list(prods)[:2]

        # 2. Secondary Check: Raw Log Search (unparsed / GCP Audit log stream)
        raw_count = 0
        raw_log_type = ""
        if udm_count == 0:
            prefix = email.split("@")[0]
            try:
                raw_res = engine.search_raw_logs(
                    query=f"raw = /{prefix}/",
                    lookback_hours=raw_log_lookback_hours,
                    page_size=3,
                )
                raw_count = len(raw_res.matches)
                if raw_count > 0:
                    raw_log_type = raw_res.matches[0].log_type or "Raw Match"
                    latest_ts = f"Raw Log ({raw_log_type})"
            except Exception:
                raw_count = 0

        # Classification
        if udm_count > 0:
            status = "ACTIVE (UDM)"
        elif raw_count > 0:
            status = "ACTIVE (Raw Logs)"
        else:
            status = "DORMANT"

        audit_records.append({
            "identity": email,
            "role": role,
            "type": atype,
            "status": status,
            "udm_count": udm_count,
            "raw_count": raw_count,
            "latest_activity": latest_ts,
            "products": products,
        })

    # Summary Display
    hdr = "%-42s | %-16s | %-26s | %-18s | %-22s"
    print("\n" + (hdr % ("Identity", "Type", "Assigned Role", "Status", "Latest Activity")))
    print("-" * 132)

    for r in audit_records:
        ident = r["identity"] if len(r["identity"]) <= 42 else r["identity"][:39] + "..."
        print(hdr % (ident, r["type"], r["role"][:26], r["status"], str(r["latest_activity"])[:22]))

    print("\n" + "=" * 132)
    print("  Governance Risk Assessment & Remediation")
    print("=" * 132)

    active_count = sum(1 for r in audit_records if "ACTIVE" in r["status"])
    dormant_count = sum(1 for r in audit_records if r["status"] == "DORMANT")
    dormant_admins = [r for r in audit_records if r["status"] == "DORMANT" and "Admin" in r["role"]]

    print(f"Total Accounts Verified: {len(audit_records)}")
    print(f"  • Actively Generating Telemetry: {active_count}")
    print(f"  • Dormant / Inactive Accounts:   {dormant_count}")

    if dormant_admins:
        print(f"\n[!] HIGH-RISK FINDING: {len(dormant_admins)} Dormant Administrative Identity(ies) Detected:")
        for da in dormant_admins:
            print(f"    - {da['identity']} ({da['role']})")
            print(f"      Risk: Retains elevated tenant administration permissions with zero activity in {udm_window_days} days.")
            print(f"      Remediation: Audit necessity, apply least-privilege role scoping, or revoke inactive credentials.\n")
    else:
        print("\n[+] All administrative accounts exhibit active, verifiable operational telemetry.")


if __name__ == "__main__":
    run_identity_usage_audit()
