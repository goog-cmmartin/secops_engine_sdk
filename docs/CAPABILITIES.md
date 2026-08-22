<!-- GENERATED FILE — do not edit by hand. -->
<!-- Regenerate with: python scripts/generate_capabilities_doc.py -->

# Capability Reference

_Generated 2026-08-22 from `engine/registry.py` via `scripts/generate_capabilities_doc.py`._

**104 registered capabilities.** Every capability is exposed to the Python SDK (`engine.facade`), the CLI, and as an MCP tool.

## Classification legend

- **kind** — `workflow` (composed, multi-step), `primitive` (single mutating action), `query` (read-only).
- **cardinality** — `single` (one entity), `bounded` (finite/enum set), `unbounded` (open collection; agent must supply a filter — see AGENTS.md Invariant #9).

## Totals

| kind | count |
| :--- | ----: |
| workflow | 7 |
| primitive | 1 |
| query | 96 |
| **total** | **104** |

| cardinality | count |
| :--- | ----: |
| single | 44 |
| bounded | 2 |
| unbounded | 50 |
| (n/a — workflows/primitive) | 8 |

## Workflows

Composed, provenance-tracked operations — the orchestrated behaviors of the engine.

| capability_id | domain | description |
| :--- | :--- | :--- |
| `alert.investigate` | alert | Retrieves security alert details with root-cause entities and raw log attachments. |
| `case.investigate` | case | Aggregates case metadata, security alerts, involved entities, and analyst comments. |
| `dashboard.get` | dashboard | Retrieves complete composite dashboard graph with layout, batch-resolved charts, and queries. |
| `event.investigate` | event | Retrieves canonical UDM fields and raw log payload with complete provenance. |
| `search.from_entity` | search | Translates high-level entity artifacts into canonical UDM query expressions. |
| `search.refine` | search | Refines existing queries by applying structured inclusion/exclusion filters on UDM paths. |
| `search.udm` | search | Validates, initiates, incrementally streams, and manages lifecycle of UDM search queries. |

## All capabilities by domain

### alert  (1: workflow=1)

| capability_id | kind | cardinality | mcp_tool | description |
| :--- | :--- | :--- | :--- | :--- |
| `alert.investigate` | workflow | — | `investigate_alert` | Retrieves security alert details with root-cause entities and raw log attachments. |

### case  (3: workflow=1, primitive=1, query=1)

| capability_id | kind | cardinality | mcp_tool | description |
| :--- | :--- | :--- | :--- | :--- |
| `case.investigate` | workflow | — | `investigate_case` | Aggregates case metadata, security alerts, involved entities, and analyst comments. |
| `case.comment` | primitive | — | `add_case_comment` | Adds structured analyst investigation comments to a SOAR case. |
| `case.search` | query | `unbounded` | `search_cases` | Searches, lists, and filters SOAR cases across time ranges, status, priority, and stages. |

### case_config  (14: query=14)

| capability_id | kind | cardinality | mcp_tool | description |
| :--- | :--- | :--- | :--- | :--- |
| `case_config.alert_grouping.rule.get` | query | `single` | `get_alert_grouping_rule` | Retrieves deep inspection of a single alert grouping rule including entity types and category details. |
| `case_config.alert_grouping.rule.search` | query | `unbounded` | `search_alert_grouping_rules` | Discovers and filters SOAR alert grouping rules determining case clustering. |
| `case_config.alert_grouping.settings.get` | query | `single` | `get_alert_grouping_settings` | Retrieves global SOAR alert grouping configuration parameters including timeframes and algorithms. |
| `case_config.calculated_field.get` | query | `single` | `get_calculated_field` | Retrieves deep inspection of a single calculated field definition. |
| `case_config.calculated_field.search` | query | `unbounded` | `search_calculated_fields` | Lists and filters calculated field formula definitions. |
| `case_config.close_definition.list` | query | `unbounded` | `list_case_close_definitions` | Catalogs predefined close reasons and root causes for closing cases. |
| `case_config.close_parameter.list` | query | `unbounded` | `list_case_close_dynamic_parameters` | Discovers dynamic form fields and custom field schemas required when closing cases. |
| `case_config.custom_field.get` | query | `single` | `get_custom_field` | Retrieves deep inspection of a single custom field definition and ordered option values. |
| `case_config.custom_field.search` | query | `unbounded` | `search_custom_fields` | Lists and filters custom typed fields across Case and Alert scopes. |
| `case_config.stage.list` | query | `unbounded` | `list_case_stage_definitions` | Lists ordered SOC case lifecycle pipeline stages. |
| `case_config.tag.search` | query | `unbounded` | `search_case_tag_definitions` | Discovers and filters case tag classification rules and criteria. |
| `case_config.title_settings.get` | query | `single` | `get_case_title_settings` | Retrieves priority rules for automated SOAR case naming. |
| `case_config.view.get` | query | `single` | `get_case_view` | Retrieves deep inspection of a specific view layout template and widget hierarchy. |
| `case_config.view.search` | query | `unbounded` | `search_case_views` | Discovers and filters layout view templates for Cases, Alerts, and Detections. |

### content_pack  (3: query=3)

| capability_id | kind | cardinality | mcp_tool | description |
| :--- | :--- | :--- | :--- | :--- |
| `content_pack.categories` | query | `unbounded` | `list_content_pack_categories` | Discovers and aggregates the taxonomy of Content Hub categories with pack counts. |
| `content_pack.get` | query | `single` | `get_content_pack` | Retrieves complete Content Pack details and bundled playbooks, integrations, dashboards, rulesets, and queries. |
| `content_pack.search` | query | `unbounded` | `search_content_packs` | Searches, lists, and filters Content Hub Marketplace Content Packs across categories and pack types. |

### curated_detections  (4: query=4)

| capability_id | kind | cardinality | mcp_tool | description |
| :--- | :--- | :--- | :--- | :--- |
| `curated_detections.get_rule` | query | `single` | `get_curated_rule` | Retrieves an individual Curated Rule, its MITRE techniques, false positives, and raw YARA-L logic. |
| `curated_detections.get_ruleset` | query | `single` | `get_curated_ruleset` | Deep-inspects a Curated Rule Set, its broad/precise deployments, member rules, and detection telemetry. |
| `curated_detections.metrics` | query | `single` | `get_curated_detection_metrics` | Aggregates detection firing counts and retrieves tenant-wide rule quotas and telemetry. |
| `curated_detections.search_rulesets` | query | `unbounded` | `search_curated_rulesets` | Discovers and searches Google SecOps Curated Rule Sets with MITRE ATT&CK mappings and log sources. |

### dashboard  (4: workflow=1, query=3)

| capability_id | kind | cardinality | mcp_tool | description |
| :--- | :--- | :--- | :--- | :--- |
| `dashboard.get` | workflow | — | `get_dashboard` | Retrieves complete composite dashboard graph with layout, batch-resolved charts, and queries. |
| `dashboard.execute_query` | query | `bounded` | `execute_dashboard_query` | Executes a dashboard widget query against live telemetry and transforms columnar results into tabular records. |
| `dashboard.search` | query | `unbounded` | `search_dashboards` | Searches, lists, and filters native dashboards configured in Google SecOps. |
| `dashboard.validate_query` | query | `bounded` | `validate_dashboard_query` | Validates statistical / dashboard widget query syntax against the live Google SecOps query compiler. |

### data_rbac  (5: query=5)

| capability_id | kind | cardinality | mcp_tool | description |
| :--- | :--- | :--- | :--- | :--- |
| `data_rbac.environment.search` | query | `unbounded` | `search_environment_scopes` | Discovers SOAR multi-tenant environments and inspects their bound Data Access Scopes. |
| `data_rbac.label.get` | query | `single` | `get_data_access_label` | Retrieves full configuration of a Data Access Label including UDM filter expression. |
| `data_rbac.label.search` | query | `unbounded` | `search_data_access_labels` | Discovers Data Access Labels and their associated UDM filter query definitions. |
| `data_rbac.scope.get` | query | `single` | `get_data_access_scope` | Retrieves deep configuration of a Data Access Scope including label attachments. |
| `data_rbac.scope.search` | query | `unbounded` | `search_data_access_scopes` | Discovers and filters Data Access RBAC Scopes and allow/deny label counts. |

### enrichment  (3: query=3)

| capability_id | kind | cardinality | mcp_tool | description |
| :--- | :--- | :--- | :--- | :--- |
| `enrichment.combination.list` | query | `unbounded` | `list_enrichment_combinations` | Discovers available enrichment types, target log types, and enrichment sources. |
| `enrichment.control.get` | query | `single` | `get_enrichment_control` | Retrieves full configuration and timing rules for a deployed enrichment control. |
| `enrichment.control.search` | query | `unbounded` | `search_enrichment_controls` | Discovers and filters deployed enrichment controls that restrict entity enrichments. |

### event  (1: workflow=1)

| capability_id | kind | cardinality | mcp_tool | description |
| :--- | :--- | :--- | :--- | :--- |
| `event.investigate` | workflow | — | `investigate_event` | Retrieves canonical UDM fields and raw log payload with complete provenance. |

### feed  (4: query=4)

| capability_id | kind | cardinality | mcp_tool | description |
| :--- | :--- | :--- | :--- | :--- |
| `feed.get` | query | `single` | `get_feed` | Retrieves full configuration details and source parameters for an ingestion feed. |
| `feed.search` | query | `unbounded` | `search_feeds` | Searches, lists, and filters push/pull ingestion feeds across source types and log types. |
| `feed_schema.list_log_types` | query | `unbounded` | `list_feed_log_type_schemas` | Lists log types supported by a specific feed source with lean payload handling. |
| `feed_schema.list_sources` | query | `unbounded` | `list_feed_source_type_schemas` | Lists all supported feed source types and collection mechanisms. |

### integration  (4: query=4)

| capability_id | kind | cardinality | mcp_tool | description |
| :--- | :--- | :--- | :--- | :--- |
| `integration.get` | query | `single` | `get_integration` | Retrieves complete integration details, instances, remote agents, and documentation. |
| `integration.instances` | query | `unbounded` | `list_integration_instances` | Lists configured integration instances across environments or specific integrations. |
| `integration.remote_agents` | query | `unbounded` | `list_remote_agents` | Lists remote proxy execution agents and their supported environments. |
| `integration.search` | query | `unbounded` | `search_integrations` | Searches, lists, and filters SOAR integrations across environments, status, and certification. |

### job  (4: query=4)

| capability_id | kind | cardinality | mcp_tool | description |
| :--- | :--- | :--- | :--- | :--- |
| `job.get` | query | `single` | `get_job` | Retrieves complete job details, deployed runtime instances, and recent execution logs. |
| `job.instances` | query | `unbounded` | `list_job_instances` | Lists runtime job instances deployed across environments or specific jobs. |
| `job.logs` | query | `unbounded` | `get_job_instance_logs` | Retrieves execution run records and output logs for a job instance. |
| `job.search` | query | `unbounded` | `search_jobs` | Searches, lists, and filters SOAR scheduled jobs across integrations and execution schedules. |

### marketplace_integration  (4: query=4)

| capability_id | kind | cardinality | mcp_tool | description |
| :--- | :--- | :--- | :--- | :--- |
| `marketplace_integration.affected_items` | query | `unbounded` | `get_marketplace_integration_affected_items` | Resolves affected environment instances and active playbooks before integration modifications. |
| `marketplace_integration.diff` | query | `single` | `get_marketplace_integration_diff` | Compares commercial upgrade differences and overrides between installed and target versions. |
| `marketplace_integration.get` | query | `single` | `get_marketplace_integration` | Retrieves complete integration composite, actions, connectors, jobs, managers, and release notes. |
| `marketplace_integration.search` | query | `unbounded` | `search_marketplace_integrations` | Discovers, searches, and filters Marketplace Response Integrations across categories and update states. |

### parser  (6: query=6)

| capability_id | kind | cardinality | mcp_tool | description |
| :--- | :--- | :--- | :--- | :--- |
| `parser.extensions.get` | query | `single` | `get_parser_extension` | Retrieves full parser extension configuration, decoded snippet, and test log. |
| `parser.extensions.search` | query | `unbounded` | `search_parser_extensions` | Discovers parser extensions and dynamic parsing configurations across log types. |
| `parser.get` | query | `single` | `get_parser` | Retrieves complete parser metadata and decoded Logstash CBN filter code. |
| `parser.log_type_setting.get` | query | `single` | `get_log_type_setting` | Retrieves autonomous parsing settings and extraction type for a specific log type. |
| `parser.log_types.list` | query | `unbounded` | `list_log_types` | Discovers and filters supported ingestion log types cataloged in Google SecOps. |
| `parser.search` | query | `unbounded` | `search_parsers` | Discovers and filters parsers across log types with creator and state filters. |

### playbook  (3: query=3)

| capability_id | kind | cardinality | mcp_tool | description |
| :--- | :--- | :--- | :--- | :--- |
| `playbook.categories` | query | `unbounded` | `list_playbook_categories` | Lists all SOAR Playbook folder categories. |
| `playbook.get` | query | `single` | `get_playbook` | Retrieves complete playbook definition, trigger conditions, and step execution DAG. |
| `playbook.search` | query | `unbounded` | `search_playbooks` | Searches, lists, and filters SOAR playbooks across categories, triggers, and environments. |

### preview_feature  (2: query=2)

| capability_id | kind | cardinality | mcp_tool | description |
| :--- | :--- | :--- | :--- | :--- |
| `preview_feature.get` | query | `single` | `get_preview_feature` | Retrieves specific preview feature configuration, documentation, and retirement dates. |
| `preview_feature.list` | query | `unbounded` | `list_preview_features` | Discovers customer preview feature flags, enablement states, retirement schedules, and docs. |

### search  (3: workflow=3)

| capability_id | kind | cardinality | mcp_tool | description |
| :--- | :--- | :--- | :--- | :--- |
| `search.from_entity` | workflow | — | `search_from_entity` | Translates high-level entity artifacts into canonical UDM query expressions. |
| `search.refine` | workflow | — | `refine_search` | Refines existing queries by applying structured inclusion/exclusion filters on UDM paths. |
| `search.udm` | workflow | — | `search_udm` | Validates, initiates, incrementally streams, and manages lifecycle of UDM search queries. |

### siem_settings  (6: query=6)

| capability_id | kind | cardinality | mcp_tool | description |
| :--- | :--- | :--- | :--- | :--- |
| `pipeline.get` | query | `single` | `get_log_processing_pipeline` | Retrieves full transform statements and stream bindings for a Data Processing Pipeline. |
| `pipeline.search` | query | `unbounded` | `search_log_processing_pipelines` | Discovers and lists Data Processing Pipelines with parser transforms and Bindplane SaaS links. |
| `siem.agent_settings.get` | query | `single` | `get_agent_settings` | Retrieves tenant configuration for automated triage, investigation filters, delays, and quotas. |
| `siem.managed_domains.get` | query | `single` | `get_managed_domain_settings` | Retrieves approved email domains for report deliveries and alerts. |
| `siem.risk_config.get` | query | `single` | `get_entity_risk_config` | Retrieves UEBA entity risk scoring defaults, detection/alert scores, and weighting coefficients. |
| `siem.tenant.get` | query | `single` | `get_tenant_instance` | Retrieves root tenant instance details, active URLs, feature flags, and workforce pool providers. |

### soar_settings  (30: query=30)

| capability_id | kind | cardinality | mcp_tool | description |
| :--- | :--- | :--- | :--- | :--- |
| `soar.company.get` | query | `single` | `get_company_settings` | Retrieves tenant branding, report customizations, and system email settings. |
| `soar.custom_list.get` | query | `single` | `get_soar_custom_list` | Retrieves complete configuration for a single SOAR custom list record. |
| `soar.custom_list.search` | query | `unbounded` | `search_soar_custom_lists` | Discovers and filters SOAR custom key-value style retention lists by query, category, and environment. |
| `soar.data_retention.get` | query | `single` | `get_data_retention_settings` | Retrieves SOAR data retention configuration and per-environment policy settings. |
| `soar.domain.get` | query | `single` | `get_soar_domain` | Retrieves complete configuration for a single approved customer domain. |
| `soar.domain.search` | query | `unbounded` | `search_soar_domains` | Discovers and filters customer-approved domain names and environment mappings. |
| `soar.email_settings.get` | query | `single` | `get_email_settings` | Retrieves composite email transport configuration combining custom SMTP and Google defaults. |
| `soar.email_template.get` | query | `single` | `get_email_template` | Retrieves complete email template definition including markup and body content. |
| `soar.email_template.search` | query | `unbounded` | `search_email_templates` | Discovers and filters plain text and HTML email templates used in SOAR playbooks. |
| `soar.entities_blocklist.get` | query | `single` | `get_entities_blocklist` | Retrieves complete configuration for a single entity blocklist entry. |
| `soar.entities_blocklist.search` | query | `unbounded` | `search_entities_blocklists` | Discovers and filters entity extraction noise-reduction blocklists. |
| `soar.environment.get` | query | `single` | `get_environment` | Retrieves deep configuration details of a single multi-tenancy environment. |
| `soar.environment.search` | query | `unbounded` | `search_environments` | Discovers and filters multi-tenancy environment boundaries within the SOAR tenant. |
| `soar.environment_group.search` | query | `unbounded` | `search_environment_groups` | Discovers and lists logical groupings of multi-tenancy environments. |
| `soar.ingestion_connector.get` | query | `single` | `get_soar_ingestion_connector` | Retrieves complete configuration for a single SOAR ingestion connector instance. |
| `soar.ingestion_connector.search` | query | `unbounded` | `search_soar_ingestion_connectors` | Discovers and filters configured SOAR ingestion connector instances across integrations. |
| `soar.network.get` | query | `single` | `get_soar_network` | Retrieves complete configuration for a single customer-defined CIDR network. |
| `soar.network.search` | query | `unbounded` | `search_soar_networks` | Discovers and filters customer-defined CIDR network address ranges and environment mappings. |
| `soar.remote_agent.get` | query | `single` | `get_remote_agent` | Retrieves deep configuration of a remote agent including certificates and installer links. |
| `soar.remote_agent.search` | query | `unbounded` | `search_remote_agents` | Discovers and filters remote execution agents, bindings, and active health states. |
| `soar.request_template.get` | query | `single` | `get_request_template` | Retrieves complete form field definitions and options for a single request template. |
| `soar.request_template.search` | query | `unbounded` | `search_request_templates` | Discovers and filters SOAR manual case request form templates. |
| `soar.sla_definition.get` | query | `single` | `get_sla_definition` | Retrieves complete SLA parameters for a single SLA rule. |
| `soar.sla_definition.search` | query | `unbounded` | `search_sla_definitions` | Discovers and filters Service Level Agreement definitions across stages and priorities. |
| `soar.soc_role.list` | query | `unbounded` | `list_soc_roles` | Lists configured SOC roles and workflow assignment access hierarchy. |
| `soar.support_settings.get` | query | `single` | `get_support_settings` | Retrieves Google Support access delegation parameters including roles, environments, and expiry. |
| `soar.user.get` | query | `single` | `get_soar_user` | Retrieves deep profile details of a single SOAR user including roles, permission groups, and environment access. |
| `soar.user.search` | query | `unbounded` | `search_soar_users` | Discovers and filters SOAR users and external identity profiles. |
| `soar.webhook.get` | query | `single` | `get_soar_webhook` | Retrieves complete configuration and schema mapping for a single SOAR event ingestion webhook. |
| `soar.webhook.search` | query | `unbounded` | `search_soar_webhooks` | Discovers and filters configured SOAR event ingestion webhooks. |
