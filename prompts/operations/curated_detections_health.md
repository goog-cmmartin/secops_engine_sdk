# Prompt: Google SecOps Curated Detections Health Check, Deployment & Hygiene Audit

## Role & Purpose
Act as a Principal Threat Detection Architect and SOC Operations Lead. Perform a comprehensive health check, deployment posture review, and hygiene audit of all Google Cloud Threat Intelligence (GCTI) and Mandiant Curated Rule Sets and Content Hub detections across the Google SecOps tenant.

The objective is to:
1. Audit tenant-wide Curated Rule Set deployment states across `PRECISE` (high-fidelity alerting) and `BROAD` (silent telemetry) profiles.
2. Identify critical deployment misconfigurations (e.g., `BROAD` precision set to `Alerting ON` causing alert queue fatigue).
3. Evaluate detection telemetry and identify high-volume / noisy rule sets over a specified evaluation timeframe.
4. Discover the newest threat intelligence releases and oldest legacy rules.
5. Provide actionable remediation steps and CLI commands.

---

## Prompt Template

```text
Please generate a comprehensive health check, deployment posture review, and hygiene audit report for all Google SecOps Curated Rule Sets across our tenant.

Retrieve and evaluate the following dimensions:

1. Tenant Deployment Posture & Quota Utilization:
   - Total categories, curated rule sets, and individual member rules.
   - Count of active deployments across PRECISE and BROAD modes.
   - Count of rule sets with Alerting Enabled vs Silent Detection.
   - Total detection telemetry volume over the evaluation window (e.g., last 7 or 14 days).
   - Rule engine quota usage vs tenant capacity limit.

2. Health Findings & Misconfiguration Risks:
   - Identify any rule sets with BROAD precision set to Alerting ON ([HIGH] Severity).
   - Identify any rule sets with BROAD enabled while PRECISE is disabled ([MEDIUM] Severity).
   - Identify any high-firing noisy rule sets generating excessive telemetry ([LOW] Severity).
   - Identify empty or dormant rule sets enabled with 0 member rules ([INFO] Severity).
   - For each finding, provide the Category, Ruleset ID, Issue description, and exact CLI remediation command.

3. Telemetry & High Volume Telemetry:
   - List the top 10 firing Curated Rule Sets ranked by detection count in the evaluation window.

4. Content Lifecycle & Freshness:
   - List the newest threat intelligence rules (recently updated/published by Google Threat Intelligence).
   - List the oldest legacy curated rules to assess coverage age.

5. Category & Log Source Coverage Matrix:
   - Present a breakdown table showing total rule sets, Precise enabled, and Broad enabled across categories (e.g., Cloud Threats, Windows Threats, Linux Threats, Network Threats).

Please format the output in executive Markdown tables with clear status badges and remediation recommendations.
```

---

## Programmatic Execution

### Using SecOps Python SDK:
```python
from engine.facade import SecOpsEngine
from runbooks.operations.curated_detections_health import (
    generate_curated_detections_health_report,
    print_curated_detections_health_console,
)

engine = SecOpsEngine()

# Run 7-day curated detections health check
report = engine.audit_curated_detections_health(days=7)

# Print human-readable report or export JSON
print_curated_detections_health_console(report)
```

### Using SecOps CLI:
```bash
# Run Curated Detections health audit via CLI
secops curated audit --days 7

# Run via autonomous runbook runner and export to JSON
secops runbook run curated-detections-health --days 14 --out curated_audit.json

# Fix high-risk misconfiguration: set BROAD profile to Alerting OFF
secops curated set-deployment <RULESET_ID> --precision BROAD --no-alerting
```
