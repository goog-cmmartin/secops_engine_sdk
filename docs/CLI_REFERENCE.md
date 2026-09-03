# Google SecOps CLI (`secops`) Reference Guide

The `secops` CLI provides an enterprise command-line interface for the Google SecOps SDK. It exposes live Chronicle SIEM telemetry hunting, SOAR case lifecycle management, Data Tables, ingestion pipelines, RBAC governance, SOC topography, and autonomous runbooks.

---

## 1. Installation & Environment Configuration

### Prerequisites
The CLI communicates natively with Google SecOps REST and gRPC endpoints using Google Cloud OAuth2 credentials.

```bash
# Set your Google Cloud application default credentials
export GOOGLE_APPLICATION_CREDENTIALS="/path/to/sa-key.json"

# Optional environment overrides (defaults loaded from config or credentials)
export GCP_PROJECT_ID="your-project-id"
export SECOPS_CUSTOMER_ID="your-customer-uuid"
export SECOPS_REGION="us"
```

### Global Options
All commands support:
- `-h`, `--help`: Display usage and argument syntax for any command or subcommand.

---

## 2. Command Index

| Category | Commands |
|:---|:---|
| **SIEM Search & Hunting** | `search`, `stats-search`, `investigate`, `entity-search`, `entity`, `ioc`, `refine` |
| **SOAR Case & Alert Management** | `case`, `alert`, `playbook`, `integration`, `job`, `case-config` |
| **Chronicle SIEM Data Tables** | `data-table` (`list`, `get`, `create`, `delete`, `rows`, `add-row`, `delete-row`) |
| **Custom YARA-L Detection Rules** | `rule` (`list`, `get`, `verify`, `create`, `patch`, `delete`, `revisions`, `deployment`, `set-deployment`, `errors`) |
| **Content & Detection Management** | `pack`, `curated`, `marketplace`, `dashboard` |
| **Ingestion, Feeds & Parsers** | `feed`, `pipeline`, `feed-schema`, `parser`, `preview` |
| **Governance, RBAC & Labels** | `domain`, `rbac`, `enrichment`, `siem` |
| **SOAR Admin & Topography** | `soar-users`, `soar-roles`, `soar-company-settings`, `soar-data-retention`, `soar-environments`, `soar-remote-agents`, `soar-networks`, `soar-domains`, `soar-custom-lists`, `soar-webhooks`, etc. |
| **Autonomous Runbooks** | `runbook list`, `runbook run <NAME>` |

---

## 3. SIEM Search & Threat Hunting

### `secops search`
Executes raw UDM filter queries across Chronicle SIEM historical event store.

```bash
secops search "<UDM_FILTER_QUERY>" [--start <ISO8601>] [--end <ISO8601>] [--limit <N>] [--format <table|json|csv>]
```

**Examples:**
```bash
# Search for network connections to a suspicious external IP
secops search 'principal.ip = "10.0.0.5" AND target.ip = "198.51.100.2"' --limit 50

# Search user logon events with explicit time window
secops search 'metadata.event_type = "USER_LOGIN" AND target.user.userid = "alice"' \
  --start "2026-08-20T00:00:00Z" --end "2026-08-28T00:00:00Z"
```

---

### `secops stats-search` / `secops search-stats`
Executes UDM Statistical / Aggregation queries (`sum`, `count`, `avg`, `values`) for threat hunting and volumetric baseline analytics.

```bash
secops stats-search "<UDM_STATS_QUERY>" [--start <ISO8601>] [--end <ISO8601>] [--limit <N>]
```

**Example:**
```bash
secops stats-search 'principal.ip != "" | stats count() by principal.ip, metadata.event_type'
```

---

### `secops investigate`
Performs deep-dive single-event forensics with entity resolution and verbatim raw log payload retrieval.

```bash
secops investigate <EVENT_ID> [--raw-log]
```

---

### `secops entity-search` & `secops entity`
Searches and summarises canonical entity graph records (assets, IP addresses, users, domains).

```bash
# Search entity graph by entity type
secops entity-search <VALUE> --type <IP_ADDRESS|HOSTNAME|USER_ID|DOMAIN_NAME> [--start <ISO8601>] [--end <ISO8601>]

# Get comprehensive entity summary & risk posture
secops entity summary <VALUE> --type <IP_ADDRESS|HOSTNAME|USER_ID>
```

---

### `secops ioc`
Searches enterprise-wide IOC matches across global threat intelligence indicators.

```bash
secops ioc search <VALUE> [--type <HASH_SHA256|IP_ADDRESS|DOMAIN_NAME>] [--limit <N>]
```

---

## 4. Chronicle SIEM Data Tables

Manage structured, YARA-L-queryable reference tables and row datasets.

### List Data Tables
```bash
secops data-table list [--limit <N>] [--json]
```

### Inspect Data Table Schema & Metadata
```bash
secops data-table get <TABLE_ID_OR_NAME> [--json]
```

### Create a Data Table
```bash
secops data-table create <TABLE_ID> \
  --columns "col_name:DATA_TYPE[:key],col2:DATA_TYPE" \
  [--display-name <NAME>] \
  [--description <DESC>] \
  [--ttl <168h>]
```
*Supported column types:* `STRING`, `REGEX`, `CIDR`, `NUMBER`.

### Query Rows from a Data Table
```bash
secops data-table rows <TABLE_ID> [--filter "<FILTER_EXPR>"] [--limit <N>] [--json]
```

### Add a Row
```bash
secops data-table add-row <TABLE_ID> --values "value1,value2,value3"
```

### Delete a Row
```bash
secops data-table delete-row <TABLE_ID> <ROW_ID>
```

### Delete a Data Table
```bash
secops data-table delete <TABLE_ID>
```

---

## 5. SOAR Case & Alert Management

### `secops case`
Inspect and interact with SOAR cases, timeline comments, and investigations.

```bash
# List cases
secops case list [--status <OPEN|CLOSED>] [--limit <N>]

# Get full case details
secops case get <CASE_ID>

# Add investigation note to case timeline
secops case comment <CASE_ID> --comment "Autonomous investigation completed."

# Close case
secops case close <CASE_ID> --reason "Resolved" --root-cause "True Positive"
```

---

### `secops alert`
Inspect and triage SOAR alerts and attached telemetry.

```bash
# List alerts
secops alert list [--case-id <CASE_ID>] [--limit <N>]

# Get alert details
secops alert get <ALERT_ID>

# Update alert priority / status
secops alert update <ALERT_ID> --priority <CRITICAL|HIGH|MEDIUM|LOW>
```

---

### `secops playbook` & `secops integration`
Manage and audit automated SOAR playbooks, reusable modular blocks, integration connectors, and background jobs.

```bash
# List all playbooks and modular blocks
secops playbook list [--type <REGULAR|NESTED>] [--limit <N>]

# Search playbooks with keyword filter
secops playbook search <QUERY> [--category <CAT>] [--type <REGULAR|NESTED>]

# Deep-dive inspect playbook trigger, priority, and step execution DAG
secops playbook get <PLAYBOOK_ID_OR_UUID>

# List playbook folder categories
secops playbook categories

# Comprehensive audit of all playbooks, blocks, priorities, and environment mappings
secops playbook audit [--type <REGULAR|NESTED>] [--environment <ENV>] [--out <FILE>] [--json]

# Comprehensive SOAR Playbook Health Check with Playbook Dashboard (SOAR) telemetry
secops playbook audit-health [--days <N>] [--out <FILE>] [--json]

# List integrations
secops integration list

# Inspect background jobs
secops job list
```

---

## 6. Custom YARA-L Detection Rules

### `secops rule`
Full lifecycle management and compiler verification for custom YARA-L 2.0 detection rules.

```bash
# List custom detection rules
secops rule list [--filter <FILTER>] [--view <BASIC|FULL>] [--limit <N>] [--json]

# Get rule details, metadata, and full YARA-L 2.0 code
secops rule get <RULE_ID> [--view <BASIC|FULL>] [--json]

# Verify and validate YARA-L 2.0 syntax against the Chronicle compiler
secops rule verify <FILE_PATH | RULE_TEXT> [--json]

# Create a new custom detection rule
secops rule create <FILE_PATH | RULE_TEXT> [--json]

# Update / patch the YARA-L logic of an existing detection rule
secops rule patch <RULE_ID> <FILE_PATH | RULE_TEXT> [--json]

# Delete a custom detection rule
secops rule delete <RULE_ID>

# List historical revisions and version history
secops rule revisions <RULE_ID> [--limit <N>] [--json]

# Get deployment, run frequency, and alerting status
secops rule deployment <RULE_ID> [--json]

# Update deployment configuration (enable/disable, alerting, schedule)
secops rule set-deployment <RULE_ID> [--enabled | --disabled] [--alerting | --no-alerting] [--frequency <LIVE|HOURLY|DAILY>]

# List rule execution and runtime errors
secops rule errors [--rule <RULE_ID>] [--limit <N>] [--json]

# Audit all rules, deployment status, and cross-correlate errors
secops rule audit [--filter <FILTER>] [--limit <N>] [--out <FILE>] [--json]
```

**Examples:**
```bash
# Run comprehensive YARA-L detection rules health and error audit
secops rule audit

# Verify YARA-L rule syntax before deploying
secops rule verify ./my_rule.yaral

# View full rule details and source code
secops rule get ru_6cb096c8-2270-4d03-860b-3c3db443a7e4

# Enable alerting on a rule
secops rule set-deployment ru_6cb096c8-2270-4d03-860b-3c3db443a7e4 --alerting
```

---

## 7. Curated Detections & Content Hub

### `secops curated`
Discover Google Cloud Threat Intelligence (GCTI) and Mandiant Curated Rule Sets, inspect individual YARA-L logic, manage Broad/Precise deployment profiles, and monitor detection telemetry.

```bash
# Search Curated Rule Sets by keyword, category, MITRE tactic/technique, or log source
secops curated rulesets [QUERY] [--category <CAT>] [--tactic <TA>] [--technique <T>] [--log-source <LOG>] [--limit <N>]

# Deep-inspect a Curated Rule Set (Broad & Precise deployment states, 7-day hits, member rules)
secops curated get <RULESET_UUID_OR_TITLE>

# Inspect a specific Curated Rule and view its executable YARA-L logic
secops curated rule <RULE_ID>

# Query tenant rule engine quotas and top firing Curated Rule Sets
secops curated metrics [--days <N>]

# Enable/disable a Curated Rule Set deployment profile and toggle alerting
secops curated set-deployment <RULESET_ID_OR_TITLE> [--precision <PRECISE|BROAD>] [--enabled | --disabled] [--alerting | --no-alerting] [--no-sync-rules]

# Run full health check, deployment posture review, and misconfiguration hygiene audit
secops curated audit [--days <N>] [--out <FILE>] [--json]
```

**Examples:**
```bash
# Search for Cloud Threat rulesets covering Azure
secops curated rulesets "Azure" --category "Cloud Threats"

# Deep-inspect "Azure - Network" curated ruleset
secops curated get "Azure - Network"

# Enable PRECISE mode with Alerting ON
secops curated set-deployment "Azure - Network" --precision PRECISE --enabled --alerting

# Enable BROAD mode with Silent Detection (Alerting OFF)
secops curated set-deployment "Azure - Network" --precision BROAD --enabled --no-alerting

# Run curated detections operational health check over 14 days
secops curated audit --days 14 --out curated_audit.json

# View top firing curated rulesets over the last 14 days
secops curated metrics --days 14
```

---

## 8. Ingestion, Feeds & Parsers

### `secops feed`
Manage log ingestion feeds.

```bash
# List ingestion feeds
secops feed list [--limit <N>]

# Get feed details
secops feed get <FEED_ID>

# Enable / disable feed
secops feed enable <FEED_ID>
secops feed disable <FEED_ID>
```

---

### `secops parser` & `secops preview`
Inspect, validate, and preview CBN log parsers against raw logs.

```bash
# List parsers
secops parser list [--log-type <LOG_TYPE>]

# Run parser preview on sample log
secops preview run --log-type <LOG_TYPE> --log-data "<RAW_LOG_STRING>"
```

---

## 9. Platform Administration & SOC Topography

Inspect governance, RBAC scopes, environments, and network boundaries:

```bash
# View RBAC scopes and data access labels
secops rbac list-scopes

# View managed environments & remote execution agents
secops soar-environments
secops soar-remote-agents

# View CIDR networks and managed domains
secops soar-networks
secops soar-domains

# View company settings & data retention periods
secops soar-company-settings
secops soar-data-retention
```

---

## 10. Autonomous Runbooks

Execute multi-step autonomous incident response, threat hunting, and operational audit procedures.

### List Available Runbooks
```bash
secops runbook list
```

### Execute a Runbook
```bash
# Autonomous Case AI Triage (Incident Response)
secops runbook run case-ai-triage --case-id 104655 [--dry-run]

# Tenant Settings & Governance Audit (Operations)
secops runbook run tenant-settings-audit [--out tenant_audit.json]

# Chronicle SIEM Data Table Schema & Inventory Audit (Operations)
secops runbook run data-table-inventory [--out dt_inventory.json]

# Chronicle SIEM YARA-L Rules Health & Error Audit (Operations & Detection)
secops runbook run yara-l-rules-audit [--out yara_rules_audit.json]

# Google SecOps SOAR Playbooks & Reusable Blocks Inventory Audit (Operations & Automation)
secops runbook run soar-playbook-inventory [--out soar_playbooks_audit.json]

# Curated Rule Sets Deployment & Hygiene Health Check (Operations & Detection)
secops runbook run curated-detections-health [--lookback-days 7] [--out curated_audit.json]

# Google SecOps SOAR Playbook Health & Telemetry Audit (Operations & SOAR Telemetry)
secops runbook run soar-playbook-health [--lookback-days 7] [--out soar_health.json]
```
