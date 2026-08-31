# Google SecOps SDK Runbooks & Autonomous Procedures

This directory contains executable, multi-step incident response, threat hunting, governance, and configuration audit runbooks built directly on top of the [`SecOpsEngine`](../engine/facade.py) Python SDK.

---

## 1. Directory Structure

```
runbooks/
├── README.md                           # Runbook catalog & execution guide
├── incident_response/
│   └── autonomous_case_ai_triage.py    # 4-stage AI summary, IOC extraction, UDM hunt, and escalation loop
├── operations/
│   └── tenant_settings_audit.py        # Complete instance settings & configuration audit report
├── threat_hunting/                     # Proactive and retrospective threat hunting runbooks
└── remediation/                        # Identity containment and IOC perimeter blocking runbooks
```

---

## 2. Available Runbooks

### `incident_response.autonomous_case_ai_triage`
Executes an end-to-end autonomous incident response and triage loop for a target SOAR case:
1. **Gemini AI Summary**: Fetches and parses case narrative, MITRE ATT&CK techniques, and next steps via `engine.get_case_summary()`.
2. **Indicator Extraction**: Parses IPv4/IPv6 indicators and email identities from case evidence and alerts.
3. **UDM Threat Hunting**: Scopes historical event telemetry across the Chronicle event store for each indicator via `engine.search_udm()`.
4. **Lifecycle Escalation & Audit Trail**: Toggles the case into active incident state (`incident=True`), escalates alert priority, and writes an audit report to the case timeline via `engine.add_case_comment()`.

#### Execution:
```bash
# Preview actions without writing changes (read-only):
python3 -m runbooks.incident_response.autonomous_case_ai_triage --case-id 104655 --dry-run

# Execute full autonomous loop:
python3 -m runbooks.incident_response.autonomous_case_ai_triage --case-id 104655

# Or via SecOps CLI:
secops runbook run case-ai-triage --case-id 104655
```

---

### `operations.tenant_settings_audit`
Generates a comprehensive JSON audit report of all tenant settings, SOC topography, and configurations:
1. **Root Instance**: Instance ID, customer code, UI state, RBAC, Gemini Triage status, and URLs.
2. **Gemini AI & UEBA Risk**: Auto-investigation flags, delay, quotas, and baseline risk scoring weights.
3. **Governance & RBAC**: Managed domains, log processing pipelines, and data access scopes/labels.
4. **SOAR Global Settings**: Company properties, retention periods, custom email, support access, alert grouping rules, and case title templates.
5. **Topography**: SOC roles, environments, remote execution agents, CIDR networks, domains, and custom blocklists/whitelists.

#### Execution:
```bash
# Print formatted JSON to stdout:
python3 -m runbooks.operations.tenant_settings_audit

# Save audit report to file:
python3 -m runbooks.operations.tenant_settings_audit --out tenant_audit.json

# Or via SecOps CLI:
secops runbook run tenant-settings-audit [--out tenant_audit.json]
```

---

### `operations.data_table_inventory`
Audits all Google Chronicle SIEM Data Tables, schemas, and metadata across the tenant:
1. **Identity & Lifecycle**: Table ID, Resource Name, Display Name, Description, Creation & Last Updated timestamps, Row TTL.
2. **Schema & Types**: Detailed column definitions, data types (`STRING`, `REGEX`, `CIDR`, `NUMBER`, `TIMESTAMP`), and key column markers.
3. **Governance & Scope**: RBAC access scope metadata (`scope_info`) and data access labels.
4. **Detection Association**: Approximate row count and linked YARA-L detection rules.

#### Execution:
```bash
# Formatted console report:
python3 -m runbooks.operations.data_table_inventory

# Export structured JSON to file:
python3 -m runbooks.operations.data_table_inventory --out data_tables_inventory.json

# Or via SecOps CLI:
secops runbook run data-table-inventory [--out data_tables_inventory.json]
```

---

### `operations.yara_l_rules_audit`
Performs a comprehensive audit and health assessment across all custom YARA-L detection rules:
1. **Rule Classification & Metadata**: Display name, Rule ID, author, severity, and rule type (`SINGLE_EVENT` vs `MULTI_EVENT`).
2. **Lifecycle & Timestamps**: Creation timestamp, last modified revision timestamp, and compilation state.
3. **Deployment & Alerting**: Enabled state, alerting state, execution frequency (`LIVE`, `HOURLY`, `DAILY`), and execution state.
4. **Error Cross-Correlation**: Queries runtime execution errors and cross-correlates them directly to failing detection rules.
5. **Executive Summary**: Aggregated metrics of healthy vs failing rules and total runtime error events.

#### Execution:
```bash
# Formatted console health report:
python3 -m runbooks.operations.yara_l_rules_audit

# Export structured JSON to file:
python3 -m runbooks.operations.yara_l_rules_audit --out yara_l_rules_audit.json

# Or via SecOps CLI:
secops runbook run yara-l-rules-audit [--out yara_l_rules_audit.json]
secops rule audit [--out yara_l_rules_audit.json]
```

---

### `operations.soar_playbook_inventory`
Audits all Google SecOps SOAR Playbooks and Reusable Modular Blocks across the tenant:
1. **Workflow Classification**: Standard Playbooks (`REGULAR`) vs Reusable Sub-playbooks/Blocks (`NESTED`).
2. **Operational Status**: Enabled vs Disabled status, debug mode state.
3. **Execution Priority**: Priority levels (1 = High/Critical, 2 = Medium/Default, 3 = Low).
4. **Environment Mappings**: SOC environments (`Default Environment`, `Cymbal`, `SDL`, `*`).
5. **Ownership & Categorization**: Category folder assignment, creator attribution, and creation/modification timestamps.

#### Execution:
```bash
# Formatted console inventory report:
python3 -m runbooks.operations.soar_playbook_inventory

# Export structured JSON to file:
python3 -m runbooks.operations.soar_playbook_inventory --out soar_playbooks_audit.json

# Or via SecOps CLI:
secops runbook run soar-playbook-inventory [--out soar_playbooks_audit.json]
secops playbook audit [--type REGULAR|NESTED] [--environment <ENV>] [--out soar_playbooks_audit.json]
```

---

### `operations.curated_detections_health`
Performs a comprehensive health check, deployment posture review, and hygiene audit across Google SecOps Curated Rule Sets:
1. **Deployment Posture**: Evaluates `PRECISE` vs `BROAD` deployment coverage and Alerting status across categories.
2. **Misconfiguration Risks**: Flags high-risk states such as `BROAD` set to `Alerting ON` ([HIGH]) and `BROAD` enabled while `PRECISE` is disabled ([MEDIUM]).
3. **Firing Volume**: Identifies top firing and noisy rule sets over a specified evaluation window (default: 7 days).
4. **Content Freshness**: Lists newest threat intelligence releases and oldest legacy rules.
5. **Remediation CLI**: Provides exact commands to remediate misconfigured rule sets.

#### Execution:
```bash
# Formatted console health check report:
python3 -m runbooks.operations.curated_detections_health --days 7

# Export structured JSON to file:
python3 -m runbooks.operations.curated_detections_health --days 14 --out curated_audit.json

# Or via SecOps CLI:
secops runbook run curated-detections-health [--days <N>] [--out curated_audit.json]
secops curated audit [--days <N>] [--out curated_audit.json]
```

---

### `operations.soar_playbook_health`
Performs a comprehensive health check, execution telemetry review, and operational triage across Google SecOps SOAR Playbooks and Reusable Modular Blocks:
1. **Structural & Operational Fusion**: Synthesizes structural playbook configurations with live operational metrics from the native **"Playbook Dashboard (SOAR)"**.
2. **Prioritized Health Findings**: Isolates critical stuck queues (`PENDING_IN_QUEUE`), playbooks with persistent 100% failure rates, and faulted connector action hotspots.
3. **Execution Metrics**: Aggregates tenant-wide playbook execution volume, failure counts, faulted actions, and mean execution runtimes over a lookback window (default: 7 days).
4. **Latency & Bottleneck Detection**: Identifies slow-running workflows exceeding execution time thresholds (> 3 minutes).
5. **Remediation CLI**: Generates direct inspection commands for failing workflows and faulted connector instances.

#### Execution:
```bash
# Formatted console health check report:
python3 -m runbooks.operations.soar_playbook_health --days 7

# Export structured JSON to file:
python3 -m runbooks.operations.soar_playbook_health --days 7 --out soar_health.json

# Or via SecOps CLI:
secops runbook run soar-playbook-health [--lookback-days 7] [--out soar_health.json]
secops playbook audit-health [--days 7] [--out soar_health.json]
```

---

## 3. Authoring Guidelines for New Runbooks

1. **Strict Live Data Origin**: Use `SecOpsEngine` methods exclusively. Zero mock data is permitted in production runbooks.
2. **Support `--dry-run`**: Every runbook modifying case states, IOC reference lists, or firewall rules must provide a non-destructive preview mode.
3. **Structured Returns**: Return typed dataclasses (e.g. `AutonomousTriageResult`) or structured dictionaries for programmatic consumption.
4. **Audit Logging**: Write comprehensive Markdown audit notes back to the target SOAR case timeline or investigation log.
