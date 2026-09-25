---
id: feature.siem.data_rbac
title: SIEM Data RBAC & Scope Permissions
type: feature
platform: secops_siem
sdk_capabilities:
- data_rbac.scope.search
- data_rbac.scope.get
- data_rbac.label.search
- data_rbac.label.get
- data_rbac.environment.search
mcp_tools:
- get_data_access_label
- get_data_access_scope
- search_data_access_labels
- search_data_access_scopes
- search_environment_scopes
status: stable
description: SIEM Data RBAC & Scope Permissions (feature reference in Google SecOps).
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

# SIEM Data RBAC & Scope Permissions

## 1. Feature Purpose & Scope
Provides programmatic operational access to SIEM Data RBAC & Scope Permissions within secops_siem.

## 2. Capabilities & SDK Workflows
### `data_rbac.scope.search`
- **Description:** Discovers and filters Data Access RBAC Scopes and allow/deny label counts.
- **Kind:** `query` | **Cardinality:** `unbounded`
- **MCP Tool:** `search_data_access_scopes`

### `data_rbac.scope.get`
- **Description:** Retrieves deep configuration of a Data Access Scope including label attachments.
- **Kind:** `query` | **Cardinality:** `single`
- **MCP Tool:** `get_data_access_scope`

### `data_rbac.label.search`
- **Description:** Discovers Data Access Labels and their associated UDM filter query definitions.
- **Kind:** `query` | **Cardinality:** `unbounded`
- **MCP Tool:** `search_data_access_labels`

### `data_rbac.label.get`
- **Description:** Retrieves full configuration of a Data Access Label including UDM filter expression.
- **Kind:** `query` | **Cardinality:** `single`
- **MCP Tool:** `get_data_access_label`

### `data_rbac.environment.search`
- **Description:** Discovers SOAR multi-tenant environments and inspects their bound Data Access Scopes.
- **Kind:** `query` | **Cardinality:** `unbounded`
- **MCP Tool:** `search_environment_scopes`

## 3. Operational Invariants & Constraints
- All queries returning unbounded collections require explicit filtering.
- Mutation capabilities must specify non-empty payloads and valid target IDs.

## 4. Telemetry & Observable Health Indicators
- Correlate changes against Native Dashboards and Health Hub.
