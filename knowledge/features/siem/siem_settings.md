---
id: feature.siem.siem_settings
title: SIEM Global Settings & Managed Domains
type: feature
platform: secops_siem
sdk_capabilities:
- siem.managed_domains.get
- pipeline.search
- pipeline.get
- siem.agent_settings.get
- siem.risk_config.get
- siem.tenant.get
mcp_tools:
- get_agent_settings
- get_entity_risk_config
- get_log_processing_pipeline
- get_managed_domain_settings
- get_tenant_instance
- search_log_processing_pipelines
status: stable
description: SIEM Global Settings & Managed Domains (feature reference in Google SecOps).
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

# SIEM Global Settings & Managed Domains

## 1. Feature Purpose & Scope
Provides programmatic operational access to SIEM Global Settings & Managed Domains within secops_siem.

## 2. Capabilities & SDK Workflows
### `siem.managed_domains.get`
- **Description:** Retrieves approved email domains for report deliveries and alerts.
- **Kind:** `query` | **Cardinality:** `single`
- **MCP Tool:** `get_managed_domain_settings`

### `pipeline.search`
- **Description:** Discovers and lists Data Processing Pipelines with parser transforms and Bindplane SaaS links.
- **Kind:** `query` | **Cardinality:** `unbounded`
- **MCP Tool:** `search_log_processing_pipelines`

### `pipeline.get`
- **Description:** Retrieves full transform statements and stream bindings for a Data Processing Pipeline.
- **Kind:** `query` | **Cardinality:** `single`
- **MCP Tool:** `get_log_processing_pipeline`

### `siem.agent_settings.get`
- **Description:** Retrieves tenant configuration for automated triage, investigation filters, delays, and quotas.
- **Kind:** `query` | **Cardinality:** `single`
- **MCP Tool:** `get_agent_settings`

### `siem.risk_config.get`
- **Description:** Retrieves UEBA entity risk scoring defaults, detection/alert scores, and weighting coefficients.
- **Kind:** `query` | **Cardinality:** `single`
- **MCP Tool:** `get_entity_risk_config`

### `siem.tenant.get`
- **Description:** Retrieves root tenant instance details, active URLs, feature flags, and workforce pool providers.
- **Kind:** `query` | **Cardinality:** `single`
- **MCP Tool:** `get_tenant_instance`

## 3. Operational Invariants & Constraints
- All queries returning unbounded collections require explicit filtering.
- Mutation capabilities must specify non-empty payloads and valid target IDs.

## 4. Telemetry & Observable Health Indicators
- Correlate changes against Native Dashboards and Health Hub.
