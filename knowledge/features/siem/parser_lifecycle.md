---
id: feature.siem.parser_lifecycle
title: Log Parsers & CBN Normalization
type: feature
platform: secops_siem
sdk_capabilities:
- parser.log_types.list
- parser.search
- parser.get
- parser.run
- parser.diagnose_unparsed
- parser.extensions.search
- parser.extensions.get
- parser.log_type_setting.get
- parser.audit_health
mcp_tools:
- audit_parser_health
- diagnose_unparsed_logs
- get_log_type_setting
- get_parser
- get_parser_extension
- list_log_types
- run_parser
- search_parser_extensions
- search_parsers
status: stable
description: Log Parsers & CBN Normalization (feature reference in Google SecOps).
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

# Log Parsers & CBN Normalization

## 1. Feature Purpose & Scope
Provides programmatic operational access to Log Parsers & CBN Normalization within secops_siem.

## 2. Capabilities & SDK Workflows
### `parser.log_types.list`
- **Description:** Discovers and filters supported ingestion log types cataloged in Google SecOps.
- **Kind:** `query` | **Cardinality:** `unbounded`
- **MCP Tool:** `list_log_types`

### `parser.search`
- **Description:** Discovers and filters parsers across log types with creator and state filters.
- **Kind:** `query` | **Cardinality:** `unbounded`
- **MCP Tool:** `search_parsers`

### `parser.get`
- **Description:** Retrieves complete parser metadata and decoded Logstash CBN filter code.
- **Kind:** `query` | **Cardinality:** `single`
- **MCP Tool:** `get_parser`

### `parser.run`
- **Description:** Executes a Logstash CBN parser configuration against a raw log string.
- **Kind:** `primitive` | **Cardinality:** `none`
- **MCP Tool:** `run_parser`

### `parser.diagnose_unparsed`
- **Description:** Finds unparsed raw logs for a log type and runs them against the active parser to diagnose errors.
- **Kind:** `workflow` | **Cardinality:** `none`
- **MCP Tool:** `diagnose_unparsed_logs`

### `parser.extensions.search`
- **Description:** Discovers parser extensions and dynamic parsing configurations across log types.
- **Kind:** `query` | **Cardinality:** `unbounded`
- **MCP Tool:** `search_parser_extensions`

### `parser.extensions.get`
- **Description:** Retrieves full parser extension configuration, decoded snippet, and test log.
- **Kind:** `query` | **Cardinality:** `single`
- **MCP Tool:** `get_parser_extension`

### `parser.log_type_setting.get`
- **Description:** Retrieves autonomous parsing settings and extraction type for a specific log type.
- **Kind:** `query` | **Cardinality:** `single`
- **MCP Tool:** `get_log_type_setting`

### `parser.audit_health`
- **Description:** Audits and correlates SIEM parser states, CBN version drift, extension conflicts, and Health Hub telemetry.
- **Kind:** `workflow` | **Cardinality:** `none`
- **MCP Tool:** `audit_parser_health`

## 3. Operational Invariants & Constraints
- All queries returning unbounded collections require explicit filtering.
- Mutation capabilities must specify non-empty payloads and valid target IDs.

## 4. Telemetry & Observable Health Indicators
- Correlate changes against Native Dashboards and Health Hub.
