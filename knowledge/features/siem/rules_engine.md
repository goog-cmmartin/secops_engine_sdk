---
id: feature.siem.rules_engine
title: YARA-L Detection Rules Engine
type: feature
platform: secops_siem
sdk_capabilities:
- rule.list
- rule.get
- rule.verify
- rule.create
- rule.patch
- rule.delete
- rule.revisions
- rule.deployment.get
- rule.deployment.update
- rule.errors
- rule.audit_health
mcp_tools:
- audit_rule_health
- create_rule
- delete_rule
- get_rule
- get_rule_deployment
- list_rule_errors
- list_rule_revisions
- list_rules
- patch_rule
- update_rule_deployment
- verify_rule_text
status: stable
description: YARA-L Detection Rules Engine (feature reference in Google SecOps).
generated:
  by: process:secops-sdk-v1
  at: '2026-09-20T00:00:00Z'
verified:
- by: human:secops-architect
  at: '2026-09-21T12:00:00Z'
stale_after: '2027-01-01T00:00:00Z'
sources:
- id: google-secops-docs
  resource: https://cloud.google.com/chronicle/docs
  title: Google SecOps Official Documentation
---

# YARA-L Detection Rules Engine

## 1. Feature Purpose & Scope
Provides programmatic operational access to YARA-L Detection Rules Engine within secops_siem.

## 2. Capabilities & SDK Workflows
### `rule.list`
- **Description:** Lists custom YARA-L detection rules in Chronicle SIEM.
- **Kind:** `query` | **Cardinality:** `unbounded`
- **MCP Tool:** `list_rules`

### `rule.get`
- **Description:** Retrieves full details and YARA-L logic of a detection rule.
- **Kind:** `query` | **Cardinality:** `single`
- **MCP Tool:** `get_rule`

### `rule.verify`
- **Description:** Validates YARA-L 2.0 rule syntax against the Chronicle compiler.
- **Kind:** `query` | **Cardinality:** `bounded`
- **MCP Tool:** `verify_rule_text`

### `rule.create`
- **Description:** Creates a new YARA-L detection rule in Chronicle SIEM.
- **Kind:** `primitive` | **Cardinality:** `none`
- **MCP Tool:** `create_rule`

### `rule.patch`
- **Description:** Updates the YARA-L logic of an existing detection rule.
- **Kind:** `primitive` | **Cardinality:** `none`
- **MCP Tool:** `patch_rule`

### `rule.delete`
- **Description:** Deletes a custom detection rule from Chronicle SIEM.
- **Kind:** `primitive` | **Cardinality:** `none`
- **MCP Tool:** `delete_rule`

### `rule.revisions`
- **Description:** Lists historical revisions and version history of a detection rule.
- **Kind:** `query` | **Cardinality:** `unbounded`
- **MCP Tool:** `list_rule_revisions`

### `rule.deployment.get`
- **Description:** Retrieves deployment, frequency, and alerting status of a rule.
- **Kind:** `query` | **Cardinality:** `single`
- **MCP Tool:** `get_rule_deployment`

### `rule.deployment.update`
- **Description:** Updates deployment properties (enabled, alerting, frequency) of a rule.
- **Kind:** `primitive` | **Cardinality:** `none`
- **MCP Tool:** `update_rule_deployment`

### `rule.errors`
- **Description:** Lists runtime and execution errors across detection rules.
- **Kind:** `query` | **Cardinality:** `unbounded`
- **MCP Tool:** `list_rule_errors`

### `rule.audit_health`
- **Description:** Audits and correlates Chronicle YARA-L rules, execution errors, latency observability, and detection decay.
- **Kind:** `workflow` | **Cardinality:** `none`
- **MCP Tool:** `audit_rule_health`

## 3. Operational Invariants & Constraints
- All queries returning unbounded collections require explicit filtering.
- Mutation capabilities must specify non-empty payloads and valid target IDs.

## 4. Telemetry & Observable Health Indicators
- Correlate changes against Native Dashboards and Health Hub.
