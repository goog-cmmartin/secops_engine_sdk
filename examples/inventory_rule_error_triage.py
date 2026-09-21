"""SecOps Inventory to ADK Workflow: Detection Rule Execution Error Triage.

Connects the SecOps Inventory service (capturing audit history and drift)
to the SecOps Engine SDK and ADK Rule Agent workflow tools.
"""

from __future__ import annotations

import json
import os
import sys
from typing import Any, Dict, List
import requests

# Ensure project root is on PYTHONPATH
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from agents.rule_agent import (
    get_rule_execution_errors,
    get_rule_source,
    validate_yara_l_rule,
)


def run_inventory_rule_triage(
    inventory_base_url: str = "http://localhost:8000",
    tenant_id: str = "37679061640",
    top_n: int = 5,
) -> None:
    print("==========================================================================")
    print("  SecOps Inventory -> ADK Workflow: Rule Execution Error Triage")
    print("==========================================================================\n")

    # Step 1: Discover Rule Execution Errors recorded by the Inventory Service
    print(f"[*] Querying Inventory Service at {inventory_base_url} for tenant {tenant_id}...")
    endpoint = f"{inventory_base_url}/api/tenants/{tenant_id}/audits/SIEM%20Rule%20Execution%20Errors/view"
    try:
        resp = requests.get(endpoint, timeout=15)
        resp.raise_for_status()
        audit_data = resp.json()
    except Exception as exc:
        print(f"[!] Error fetching audit from Inventory Service: {exc}")
        return

    errors = audit_data.get("results", {}).get("ruleExecutionErrors", [])
    total_recorded = audit_data.get("item_count", len(errors))
    print(f"[+] Total execution errors on record: {total_recorded:,} (parsed batch: {len(errors)})\n")

    # Group by affected rule resource
    rule_counts: Dict[str, int] = {}
    for e in errors:
        r = e.get("rule") or e.get("curatedRule")
        if r:
            rule_counts[r] = rule_counts.get(r, 0) + 1

    top_rules = sorted(rule_counts.items(), key=lambda x: x[1], reverse=True)[:top_n]

    print(f"=== Handing Top {len(top_rules)} Failing Rules to ADK Agent Workflow ===")
    for idx, (r_name, count) in enumerate(top_rules, 1):
        clean_id = r_name.split("/")[-1].split("@")[0]
        print(f"\n[{idx}] Target Rule: {clean_id} (Recorded Errors in Inventory: {count})")

        # ADK Tool 1: Inspect Live Runtime Execution Errors
        err_raw = get_rule_execution_errors(clean_id)
        err_json = json.loads(err_raw)
        live_count = err_json.get("count", 0)
        print(f"    - Recent Live Errors: {live_count}")
        msg = ""
        if err_json.get("errors"):
            first_err = err_json["errors"][0]
            code = first_err.get("error_code")
            msg = first_err.get("error_message", "")
            print(f"    - Error Code: {code}")
            print(f"    - Error Detail: {msg}")

        # ADK Tool 2: Inspect Rule Source & Deployment Metadata
        try:
            source_raw = get_rule_source(clean_id)
            source_json = json.loads(source_raw)
            disp_name = source_json.get("display_name")
            author = source_json.get("author")
            severity = source_json.get("severity")
            comp_state = source_json.get("compilation_state")
            rule_code = source_json.get("rule_text", "")
            print(f"    - Display Name: {disp_name}")
            print(f"    - Author:       {author}")
            print(f"    - Severity:     {severity}")
            print(f"    - Compilation:  {comp_state}")

            # ADK Tool 3: Compiler Validation
            val_raw = validate_yara_l_rule(rule_code)
            val_json = json.loads(val_raw)
            is_valid = val_json.get("success")
            print(f"    - Compiler Valid: {is_valid}")
            if not is_valid:
                print(f"    - Diagnostics: {val_json.get('diagnostics')}")
            else:
                # Provide Autonomous Remediation Assessment
                if "Rule is limited because of high resource usage" in msg:
                    print("    - [ADK Diagnostic]: Syntax is valid, but the rule exceeds Chronicle streaming compute quotas.")
                    print("    - [Actionable Fix]: Add high-cardinality index filters (e.g. metadata.log_type, principal.hostname),")
                    print("                        narrow the sliding window (e.g. reduction from multi-hour to minutes),")
                    print("                        or refine join keys on entity graphs.")
        except Exception as exc:
            print(f"    - Could not retrieve rule details: {exc}")

    print("\n==========================================================================")
    print("  Triage Complete: Live Telemetry Correlated with Historical Audit State")
    print("==========================================================================")


if __name__ == "__main__":
    run_inventory_rule_triage()
