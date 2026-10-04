---
id: feature.siem.data_tables
title: SIEM Data Tables & Lookup Lists
type: feature
platform: secops_siem
sdk_capabilities:
- data_table.list
- data_table.get
- data_table.create
- data_table.patch
- data_table.delete
- data_table.list_rows
- data_table.add_rows
- data_table.delete_row
- data_table.audit_health
mcp_tools:
- add_data_table_rows
- audit_data_tables
- create_data_table
- delete_data_table
- delete_data_table_row
- get_data_table
- list_data_table_rows
- list_data_tables
- patch_data_table
status: stable
description: SIEM Data Tables & Lookup Lists (feature reference in Google SecOps).
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

# SIEM Data Tables & Lookup Lists

## 1. Feature Purpose & Scope
Provides programmatic operational access to SIEM Data Tables & Lookup Lists within secops_siem.

## 2. Capabilities & SDK Workflows
### `data_table.list`
- **Description:** Lists all structured Data Tables defined in Chronicle SIEM.
- **Kind:** `query` | **Cardinality:** `unbounded`
- **MCP Tool:** `list_data_tables`

### `data_table.get`
- **Description:** Retrieves schema, columns, TTL, and metadata for a Chronicle SIEM Data Table.
- **Kind:** `query` | **Cardinality:** `single`
- **MCP Tool:** `get_data_table`

### `data_table.create`
- **Description:** Creates a new structured Data Table with typed column definitions in Chronicle SIEM.
- **Kind:** `primitive` | **Cardinality:** `none`
- **MCP Tool:** `create_data_table`

### `data_table.patch`
- **Description:** Updates description, TTL, or scope info of an existing Chronicle SIEM Data Table.
- **Kind:** `primitive` | **Cardinality:** `none`
- **MCP Tool:** `patch_data_table`

### `data_table.delete`
- **Description:** Deletes a structured Data Table from Chronicle SIEM.
- **Kind:** `primitive` | **Cardinality:** `none`
- **MCP Tool:** `delete_data_table`

### `data_table.list_rows`
- **Description:** Queries and filters rows contained within a Chronicle SIEM Data Table.
- **Kind:** `query` | **Cardinality:** `unbounded`
- **MCP Tool:** `list_data_table_rows`

### `data_table.add_rows`
- **Description:** Creates or appends rows in bulk to a Chronicle SIEM Data Table.
- **Kind:** `primitive` | **Cardinality:** `none`
- **MCP Tool:** `add_data_table_rows`

### `data_table.delete_row`
- **Description:** Deletes a single row from a Chronicle SIEM Data Table by row ID.
- **Kind:** `primitive` | **Cardinality:** `none`
- **MCP Tool:** `delete_data_table_row`

### `data_table.audit_health`
- **Description:** Audits Data Tables across the tenant for lifecycle recency, schema integrity, and detection false-negative risks.
- **Kind:** `workflow` | **Cardinality:** `none`
- **MCP Tool:** `audit_data_tables`

## 3. Operational Invariants & Constraints
- All queries returning unbounded collections require explicit filtering.
- Mutation capabilities must specify non-empty payloads and valid target IDs.

## 4. Telemetry & Observable Health Indicators
- Correlate changes against Native Dashboards and Health Hub.
