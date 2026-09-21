---
id: feature.soar.integrations
title: "SOAR Connectors & Third-Party Integrations"
type: feature
platform: secops_soar
sdk_capabilities:
  - integration.search
  - integration.get
  - integration.instances
  - integration.remote_agents
mcp_tools:
  - get_integration
  - list_integration_instances
  - list_remote_agents
  - search_integrations
---

# SOAR Connectors & Third-Party Integrations

## 1. Feature Purpose & Scope
Provides programmatic operational access to SOAR Connectors & Third-Party Integrations within secops_soar.

## 2. Capabilities & SDK Workflows
### `integration.search`
- **Description:** Searches, lists, and filters SOAR integrations across environments, status, and certification.
- **Kind:** `query` | **Cardinality:** `unbounded`
- **MCP Tool:** `search_integrations`

### `integration.get`
- **Description:** Retrieves complete integration details, instances, remote agents, and documentation.
- **Kind:** `query` | **Cardinality:** `single`
- **MCP Tool:** `get_integration`

### `integration.instances`
- **Description:** Lists configured integration instances across environments or specific integrations.
- **Kind:** `query` | **Cardinality:** `unbounded`
- **MCP Tool:** `list_integration_instances`

### `integration.remote_agents`
- **Description:** Lists remote proxy execution agents and their supported environments.
- **Kind:** `query` | **Cardinality:** `unbounded`
- **MCP Tool:** `list_remote_agents`

## 3. Operational Invariants & Constraints
- All queries returning unbounded collections require explicit filtering.
- Mutation capabilities must specify non-empty payloads and valid target IDs.

## 4. Telemetry & Observable Health Indicators
- Correlate changes against Native Dashboards and Health Hub.
