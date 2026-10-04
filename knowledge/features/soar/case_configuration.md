---
id: feature.soar.case_configuration
title: SOAR Case Configuration & Tags
type: feature
platform: secops_soar
sdk_capabilities:
- case_config.tag.search
- case_config.stage.list
- case_config.close_definition.list
- case_config.close_parameter.list
- case_config.title_settings.get
- case_config.view.search
- case_config.view.get
- case_config.custom_field.search
- case_config.custom_field.get
- case_config.calculated_field.search
- case_config.calculated_field.get
- case_config.alert_grouping.rule.search
- case_config.alert_grouping.rule.get
- case_config.alert_grouping.settings.get
mcp_tools:
- get_alert_grouping_rule
- get_alert_grouping_settings
- get_calculated_field
- get_case_title_settings
- get_case_view
- get_custom_field
- list_case_close_definitions
- list_case_close_dynamic_parameters
- list_case_stage_definitions
- search_alert_grouping_rules
- search_calculated_fields
- search_case_tag_definitions
- search_case_views
- search_custom_fields
status: stable
description: SOAR Case Configuration & Tags (feature reference in Google SecOps).
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

# SOAR Case Configuration & Tags

## 1. Feature Purpose & Scope
Provides programmatic operational access to SOAR Case Configuration & Tags within secops_soar.

## 2. Capabilities & SDK Workflows
### `case_config.tag.search`
- **Description:** Discovers and filters case tag classification rules and criteria.
- **Kind:** `query` | **Cardinality:** `unbounded`
- **MCP Tool:** `search_case_tag_definitions`

### `case_config.stage.list`
- **Description:** Lists ordered SOC case lifecycle pipeline stages.
- **Kind:** `query` | **Cardinality:** `unbounded`
- **MCP Tool:** `list_case_stage_definitions`

### `case_config.close_definition.list`
- **Description:** Catalogs predefined close reasons and root causes for closing cases.
- **Kind:** `query` | **Cardinality:** `unbounded`
- **MCP Tool:** `list_case_close_definitions`

### `case_config.close_parameter.list`
- **Description:** Discovers dynamic form fields and custom field schemas required when closing cases.
- **Kind:** `query` | **Cardinality:** `unbounded`
- **MCP Tool:** `list_case_close_dynamic_parameters`

### `case_config.title_settings.get`
- **Description:** Retrieves priority rules for automated SOAR case naming.
- **Kind:** `query` | **Cardinality:** `single`
- **MCP Tool:** `get_case_title_settings`

### `case_config.view.search`
- **Description:** Discovers and filters layout view templates for Cases, Alerts, and Detections.
- **Kind:** `query` | **Cardinality:** `unbounded`
- **MCP Tool:** `search_case_views`

### `case_config.view.get`
- **Description:** Retrieves deep inspection of a specific view layout template and widget hierarchy.
- **Kind:** `query` | **Cardinality:** `single`
- **MCP Tool:** `get_case_view`

### `case_config.custom_field.search`
- **Description:** Lists and filters custom typed fields across Case and Alert scopes.
- **Kind:** `query` | **Cardinality:** `unbounded`
- **MCP Tool:** `search_custom_fields`

### `case_config.custom_field.get`
- **Description:** Retrieves deep inspection of a single custom field definition and ordered option values.
- **Kind:** `query` | **Cardinality:** `single`
- **MCP Tool:** `get_custom_field`

### `case_config.calculated_field.search`
- **Description:** Lists and filters calculated field formula definitions.
- **Kind:** `query` | **Cardinality:** `unbounded`
- **MCP Tool:** `search_calculated_fields`

### `case_config.calculated_field.get`
- **Description:** Retrieves deep inspection of a single calculated field definition.
- **Kind:** `query` | **Cardinality:** `single`
- **MCP Tool:** `get_calculated_field`

### `case_config.alert_grouping.rule.search`
- **Description:** Discovers and filters SOAR alert grouping rules determining case clustering.
- **Kind:** `query` | **Cardinality:** `unbounded`
- **MCP Tool:** `search_alert_grouping_rules`

### `case_config.alert_grouping.rule.get`
- **Description:** Retrieves deep inspection of a single alert grouping rule including entity types and category details.
- **Kind:** `query` | **Cardinality:** `single`
- **MCP Tool:** `get_alert_grouping_rule`

### `case_config.alert_grouping.settings.get`
- **Description:** Retrieves global SOAR alert grouping configuration parameters including timeframes and algorithms.
- **Kind:** `query` | **Cardinality:** `single`
- **MCP Tool:** `get_alert_grouping_settings`

## 3. Operational Invariants & Constraints
- All queries returning unbounded collections require explicit filtering.
- Mutation capabilities must specify non-empty payloads and valid target IDs.

## 4. Telemetry & Observable Health Indicators
- Correlate changes against Native Dashboards and Health Hub.
