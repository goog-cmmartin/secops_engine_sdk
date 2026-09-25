---
id: feature.siem.feed_management
title: Log Feeds & Ingestion Endpoints
type: feature
platform: secops_siem
sdk_capabilities:
- feed.search
- feed.get
- feed.audit_health
- feed_schema.list_sources
- feed_schema.list_log_types
mcp_tools:
- audit_feed_health
- get_feed
- list_feed_log_type_schemas
- list_feed_source_type_schemas
- search_feeds
status: stable
description: Log Feeds & Ingestion Endpoints (feature reference in Google SecOps).
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

# Log Feeds & Ingestion Endpoints

## 1. Feature Purpose & Scope
Provides programmatic operational access to Log Feeds & Ingestion Endpoints within secops_siem.

## 2. Capabilities & SDK Workflows
### `feed.search`
- **Description:** Searches, lists, and filters push/pull ingestion feeds across source types and log types.
- **Kind:** `query` | **Cardinality:** `unbounded`
- **MCP Tool:** `search_feeds`

### `feed.get`
- **Description:** Retrieves full configuration details and source parameters for an ingestion feed.
- **Kind:** `query` | **Cardinality:** `single`
- **MCP Tool:** `get_feed`

### `feed.audit_health`
- **Description:** Audits and correlates ingestion feed states, Health Hub telemetry, and transport latency.
- **Kind:** `workflow` | **Cardinality:** `none`
- **MCP Tool:** `audit_feed_health`

### `feed_schema.list_sources`
- **Description:** Lists all supported feed source types and collection mechanisms.
- **Kind:** `query` | **Cardinality:** `unbounded`
- **MCP Tool:** `list_feed_source_type_schemas`

### `feed_schema.list_log_types`
- **Description:** Lists log types supported by a specific feed source with lean payload handling.
- **Kind:** `query` | **Cardinality:** `unbounded`
- **MCP Tool:** `list_feed_log_type_schemas`

## 3. Operational Invariants & Constraints
- All queries returning unbounded collections require explicit filtering.
- Mutation capabilities must specify non-empty payloads and valid target IDs.

## 4. Telemetry & Observable Health Indicators
- Correlate changes against Native Dashboards and Health Hub.
