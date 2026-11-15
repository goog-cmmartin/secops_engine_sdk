#!/usr/bin/env python3
"""Google SecOps Complete Instance Settings & Configuration Audit Runbook.

Collects and audits tenant configuration across:
1. Root Instance & Security Command Center endpoints
2. Gemini AI & UEBA risk scoring parameters
3. Governance, pipelines, and RBAC data access scopes/labels
4. SOAR global configuration (company, retention, email, support, alert grouping, title rules)
5. SOC topography (roles, environments, remote agents, networks, domains, custom lists)
"""

from __future__ import annotations

import argparse
import json
import sys
from typing import Any, Dict, Optional

from engine.facade import SecOpsEngine
from engine.workflows.tenant_settings_audit import generate_tenant_settings_report


def main():
    parser = argparse.ArgumentParser(description="Google SecOps Tenant Settings & Configuration Audit Runbook")
    parser.add_argument("--out", "-o", help="Optional filepath to save JSON audit report")
    parser.add_argument("--indent", type=int, default=2, help="JSON indentation level (default: 2)")
    args = parser.parse_args()

    data = generate_tenant_settings_report()
    rendered = json.dumps(data, indent=args.indent)

    if args.out:
        with open(args.out, "w", encoding="utf-8") as f:
            f.write(rendered)
        print(f"[+] Audit report written to {args.out}")
    else:
        print(rendered)


if __name__ == "__main__":
    main()
