---
id: feature.soar.playbooks
title: SOAR Playbooks & Automation Runs
type: feature
platform: secops_soar
sdk_capabilities:
- playbook.search
- playbook.get
- playbook.categories
- playbook.instances
- playbook.audit_health
- playbook.decay_audit
mcp_tools:
- audit_playbook_decay
- audit_soar_playbook_health
- get_alert_playbook_instances
- get_playbook
- list_playbook_categories
- search_playbooks
status: stable
description: SOAR Playbooks & Automation Runs (feature reference in Google SecOps).
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

# SOAR Playbooks & Automation Runs

## 1. Feature Purpose & Scope
Provides programmatic operational access to SOAR Playbooks & Automation Runs within secops_soar.

## 2. Capabilities & SDK Workflows
### `playbook.search`
- **Description:** Searches, lists, and filters SOAR playbooks across categories, triggers, and environments.
- **Kind:** `query` | **Cardinality:** `unbounded`
- **MCP Tool:** `search_playbooks`

### `playbook.get`
- **Description:** Retrieves complete playbook definition, trigger conditions, and step execution DAG.
- **Kind:** `query` | **Cardinality:** `single`
- **MCP Tool:** `get_playbook`

### `playbook.categories`
- **Description:** Lists all SOAR Playbook folder categories.
- **Kind:** `query` | **Cardinality:** `unbounded`
- **MCP Tool:** `list_playbook_categories`

### `playbook.instances`
- **Description:** Retrieves authoritative per-alert playbook run instances and the executed step DAG.
- **Kind:** `query` | **Cardinality:** `unbounded`
- **MCP Tool:** `get_alert_playbook_instances`

### `playbook.audit_health`
- **Description:** Audits SOAR playbooks and modular blocks for configuration hygiene, failure spikes, faulted actions, and queue latency using native Playbook Dashboard analytics.
- **Kind:** `workflow` | **Cardinality:** `none`
- **MCP Tool:** `audit_soar_playbook_health`

## 3. Operational Invariants & Constraints
- All queries returning unbounded collections require explicit filtering.
- Mutation capabilities must specify non-empty payloads and valid target IDs.

## 4. Telemetry & Observable Health Indicators
- Correlate changes against Native Dashboards and Health Hub.
