---
id: feature.soar.soar_settings
title: "SOAR Global Settings & Environments"
type: feature
platform: secops_soar
sdk_capabilities:
  - soar.user.search
  - soar.user.get
  - soar.soc_role.list
  - soar.company.get
  - soar.data_retention.get
  - soar.environment.search
  - soar.environment.get
  - soar.environment_group.search
  - soar.remote_agent.search
  - soar.remote_agent.get
  - soar.email_settings.get
  - soar.support_settings.get
  - soar.network.search
  - soar.network.get
  - soar.domain.search
  - soar.domain.get
  - soar.custom_list.search
  - soar.custom_list.get
  - soar.email_template.search
  - soar.email_template.get
  - soar.entities_blocklist.search
  - soar.entities_blocklist.get
  - soar.sla_definition.search
  - soar.sla_definition.get
  - soar.request_template.search
  - soar.request_template.get
  - soar.ingestion_connector.search
  - soar.ingestion_connector.get
  - soar.webhook.search
  - soar.webhook.get
mcp_tools:
  - get_company_settings
  - get_data_retention_settings
  - get_email_settings
  - get_email_template
  - get_entities_blocklist
  - get_environment
  - get_remote_agent
  - get_request_template
  - get_sla_definition
  - get_soar_custom_list
  - get_soar_domain
  - get_soar_ingestion_connector
  - get_soar_network
  - get_soar_user
  - get_soar_webhook
  - get_support_settings
  - list_soc_roles
  - search_email_templates
  - search_entities_blocklists
  - search_environment_groups
  - search_environments
  - search_remote_agents
  - search_request_templates
  - search_sla_definitions
  - search_soar_custom_lists
  - search_soar_domains
  - search_soar_ingestion_connectors
  - search_soar_networks
  - search_soar_users
  - search_soar_webhooks
---

# SOAR Global Settings & Environments

## 1. Feature Purpose & Scope
Provides programmatic operational access to SOAR Global Settings & Environments within secops_soar.

## 2. Capabilities & SDK Workflows
### `soar.user.search`
- **Description:** Discovers and filters SOAR users and external identity profiles.
- **Kind:** `query` | **Cardinality:** `unbounded`
- **MCP Tool:** `search_soar_users`

### `soar.user.get`
- **Description:** Retrieves deep profile details of a single SOAR user including roles, permission groups, and environment access.
- **Kind:** `query` | **Cardinality:** `single`
- **MCP Tool:** `get_soar_user`

### `soar.soc_role.list`
- **Description:** Lists configured SOC roles and workflow assignment access hierarchy.
- **Kind:** `query` | **Cardinality:** `unbounded`
- **MCP Tool:** `list_soc_roles`

### `soar.company.get`
- **Description:** Retrieves tenant branding, report customizations, and system email settings.
- **Kind:** `query` | **Cardinality:** `single`
- **MCP Tool:** `get_company_settings`

### `soar.data_retention.get`
- **Description:** Retrieves SOAR data retention configuration and per-environment policy settings.
- **Kind:** `query` | **Cardinality:** `single`
- **MCP Tool:** `get_data_retention_settings`

### `soar.environment.search`
- **Description:** Discovers and filters multi-tenancy environment boundaries within the SOAR tenant.
- **Kind:** `query` | **Cardinality:** `unbounded`
- **MCP Tool:** `search_environments`

### `soar.environment.get`
- **Description:** Retrieves deep configuration details of a single multi-tenancy environment.
- **Kind:** `query` | **Cardinality:** `single`
- **MCP Tool:** `get_environment`

### `soar.environment_group.search`
- **Description:** Discovers and lists logical groupings of multi-tenancy environments.
- **Kind:** `query` | **Cardinality:** `unbounded`
- **MCP Tool:** `search_environment_groups`

### `soar.remote_agent.search`
- **Description:** Discovers and filters remote execution agents, bindings, and active health states.
- **Kind:** `query` | **Cardinality:** `unbounded`
- **MCP Tool:** `search_remote_agents`

### `soar.remote_agent.get`
- **Description:** Retrieves deep configuration of a remote agent including certificates and installer links.
- **Kind:** `query` | **Cardinality:** `single`
- **MCP Tool:** `get_remote_agent`

### `soar.email_settings.get`
- **Description:** Retrieves composite email transport configuration combining custom SMTP and Google defaults.
- **Kind:** `query` | **Cardinality:** `single`
- **MCP Tool:** `get_email_settings`

### `soar.support_settings.get`
- **Description:** Retrieves Google Support access delegation parameters including roles, environments, and expiry.
- **Kind:** `query` | **Cardinality:** `single`
- **MCP Tool:** `get_support_settings`

### `soar.network.search`
- **Description:** Discovers and filters customer-defined CIDR network address ranges and environment mappings.
- **Kind:** `query` | **Cardinality:** `unbounded`
- **MCP Tool:** `search_soar_networks`

### `soar.network.get`
- **Description:** Retrieves complete configuration for a single customer-defined CIDR network.
- **Kind:** `query` | **Cardinality:** `single`
- **MCP Tool:** `get_soar_network`

### `soar.domain.search`
- **Description:** Discovers and filters customer-approved domain names and environment mappings.
- **Kind:** `query` | **Cardinality:** `unbounded`
- **MCP Tool:** `search_soar_domains`

### `soar.domain.get`
- **Description:** Retrieves complete configuration for a single approved customer domain.
- **Kind:** `query` | **Cardinality:** `single`
- **MCP Tool:** `get_soar_domain`

### `soar.custom_list.search`
- **Description:** Discovers and filters SOAR custom key-value style retention lists by query, category, and environment.
- **Kind:** `query` | **Cardinality:** `unbounded`
- **MCP Tool:** `search_soar_custom_lists`

### `soar.custom_list.get`
- **Description:** Retrieves complete configuration for a single SOAR custom list record.
- **Kind:** `query` | **Cardinality:** `single`
- **MCP Tool:** `get_soar_custom_list`

### `soar.email_template.search`
- **Description:** Discovers and filters plain text and HTML email templates used in SOAR playbooks.
- **Kind:** `query` | **Cardinality:** `unbounded`
- **MCP Tool:** `search_email_templates`

### `soar.email_template.get`
- **Description:** Retrieves complete email template definition including markup and body content.
- **Kind:** `query` | **Cardinality:** `single`
- **MCP Tool:** `get_email_template`

### `soar.entities_blocklist.search`
- **Description:** Discovers and filters entity extraction noise-reduction blocklists.
- **Kind:** `query` | **Cardinality:** `unbounded`
- **MCP Tool:** `search_entities_blocklists`

### `soar.entities_blocklist.get`
- **Description:** Retrieves complete configuration for a single entity blocklist entry.
- **Kind:** `query` | **Cardinality:** `single`
- **MCP Tool:** `get_entities_blocklist`

### `soar.sla_definition.search`
- **Description:** Discovers and filters Service Level Agreement definitions across stages and priorities.
- **Kind:** `query` | **Cardinality:** `unbounded`
- **MCP Tool:** `search_sla_definitions`

### `soar.sla_definition.get`
- **Description:** Retrieves complete SLA parameters for a single SLA rule.
- **Kind:** `query` | **Cardinality:** `single`
- **MCP Tool:** `get_sla_definition`

### `soar.request_template.search`
- **Description:** Discovers and filters SOAR manual case request form templates.
- **Kind:** `query` | **Cardinality:** `unbounded`
- **MCP Tool:** `search_request_templates`

### `soar.request_template.get`
- **Description:** Retrieves complete form field definitions and options for a single request template.
- **Kind:** `query` | **Cardinality:** `single`
- **MCP Tool:** `get_request_template`

### `soar.ingestion_connector.search`
- **Description:** Discovers and filters configured SOAR ingestion connector instances across integrations.
- **Kind:** `query` | **Cardinality:** `unbounded`
- **MCP Tool:** `search_soar_ingestion_connectors`

### `soar.ingestion_connector.get`
- **Description:** Retrieves complete configuration for a single SOAR ingestion connector instance.
- **Kind:** `query` | **Cardinality:** `single`
- **MCP Tool:** `get_soar_ingestion_connector`

### `soar.webhook.search`
- **Description:** Discovers and filters configured SOAR event ingestion webhooks.
- **Kind:** `query` | **Cardinality:** `unbounded`
- **MCP Tool:** `search_soar_webhooks`

### `soar.webhook.get`
- **Description:** Retrieves complete configuration and schema mapping for a single SOAR event ingestion webhook.
- **Kind:** `query` | **Cardinality:** `single`
- **MCP Tool:** `get_soar_webhook`

## 3. Operational Invariants & Constraints
- All queries returning unbounded collections require explicit filtering.
- Mutation capabilities must specify non-empty payloads and valid target IDs.

## 4. Telemetry & Observable Health Indicators
- Correlate changes against Native Dashboards and Health Hub.
