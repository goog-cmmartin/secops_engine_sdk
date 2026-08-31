# Prompt: Google SecOps SOAR Playbook Health Check, Telemetry & Operational Audit

## Role & Purpose
Act as a Principal SOAR Automation Engineer and SOC Operations Lead. Perform a comprehensive health check, execution telemetry review, and operational audit across all SOAR Playbooks, modular blocks, and remote connector integrations in the Google SecOps deployment.

The objective is to:
1. Synthesize structural playbook inventory governance (enabled states, trigger configs, modular blocks, environment scopes) with real-time telemetry from the native **"Playbook Dashboard (SOAR)"**.
2. Identify critical automation failures, persistent 100% failure rates, and playbooks stuck in `PENDING_IN_QUEUE`.
3. Isolate faulted step hotspots (e.g. failing integration actions, expired API keys, connector timeouts).
4. Benchmark playbook latency and execution durations to detect slow running or hanging workflows.
5. Provide actionable remediation steps and CLI commands.

---

## Prompt Template

```text
Please generate a comprehensive SOAR Playbook Health Check and Operational Audit report across our Google SecOps tenant.

Evaluate and report across the following operational dimensions:

1. Executive Inventory & Deployment Posture:
   - Total playbooks, standard playbooks (REGULAR), and reusable modular blocks (NESTED).
   - Deployment breakdown: Enabled vs. Disabled playbooks.
   - Category folder taxonomy and multi-tenant environment coverage.

2. Real-time Telemetry & Execution KPIs (Native Playbook Dashboard):
   - Total playbook execution runs over the evaluation window (e.g. last 7 or 14 days).
   - Total failed playbook runs and tenant-wide failure rate percentage.
   - Total security cases affected by failed playbook automation.
   - Tenant-wide average execution runtime in minutes.
   - Total action/step execution count, faulted action count, and % faulted action rate.
   - Count of playbooks currently stuck in queue (PENDING_IN_QUEUE).

3. Prioritized Operational Health Findings:
   - [CRITICAL] Stuck queue runs indicating worker congestion or agent deadlock.
   - [HIGH] Playbooks with persistent 100% failure rates or high failure percentages (> 15%).
   - [HIGH] Faulted action hotspots (repeatedly failing connector actions).
   - [MEDIUM] Slow running latency outliers (> 3-5 minutes average runtime).
   - [INFO] Disabled or orphaned playbook inventory.
   - Include exact playbook names, error details, and remediation recommendations for every finding.

4. Top Failing & High Volume Ranking Tables:
   - Top failing playbooks ranked by failure percentage and failed run count.
   - Top executed playbooks driving the majority of SOC automation volume.
   - Top faulted connector actions / steps causing automation breakage.
   - Slowest playbooks by average runtime.

Please format the output in executive Markdown tables with clear status badges and targeted remediation recommendations.
```

---

## Programmatic Execution

### Using SecOps Python SDK:
```python
from engine.facade import SecOpsEngine
from runbooks.operations.soar_playbook_health import (
    generate_soar_playbook_health_report,
    print_soar_playbook_health_console,
)

engine = SecOpsEngine()

# Run 7-day SOAR Playbook health check
report = engine.audit_soar_playbook_health(days=7)

# Print human-readable report or export JSON
print_soar_playbook_health_console(report)
```

### Using SecOps CLI:
```bash
# Run SOAR Playbook Health Check via CLI
secops playbook audit-health --days 7

# Run via autonomous runbook runner and export to JSON
secops runbook run soar-playbook-health --lookback-days 7 --out soar_health.json

# Deep inspect a specific failing playbook
secops playbook get "<PLAYBOOK_IDENTIFIER_OR_UUID>"
```
