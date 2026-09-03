<!-- GENERATED FILE — do not edit by hand. -->
<!-- Regenerate with: python scripts/generate_capabilities_doc.py -->

# Capability Reference

_Generated 2026-09-01 from `engine/registry.py` via `scripts/generate_capabilities_doc.py`._

**153 registered capabilities.** Every capability is exposed to the Python SDK (`engine.facade`) and the CLI. Each also carries a reserved MCP tool name (see the `mcp_tool (proposed)` column) for a planned MCP binding; no MCP server ships today.

## Classification legend

- **kind** — `workflow` (composed, multi-step), `primitive` (single mutating action), `query` (read-only).
- **cardinality** — `single` (one entity), `bounded` (finite/enum set), `unbounded` (open collection; agent must supply a filter — see AGENTS.md Invariant #9).

## Totals

| kind | count |
| :--- | ----: |
| workflow | 21 |
| primitive | 21 |
| query | 111 |
| **total** | **153** |

| cardinality | count |
| :--- | ----: |
| single | 48 |
| bounded | 4 |
| unbounded | 59 |
| (n/a — workflows/primitive) | 42 |

## Workflows

Composed, provenance-tracked operations — the orchestrated behaviors of the engine.

| capability_id | domain | description |
| :--- | :--- | :--- |
| `alert.investigate` | alert | Retrieves security alert details with root-cause entities and raw log attachments. |
| `case.get_summary` | case | Requests Gemini AI case summary and polls until generation is complete or timeout. |
| `case.investigate` | case | Aggregates case metadata, security alerts, involved entities, and analyst comments. |
| `case.orchestrate_triage` | case | Batched retrieval, parallel investigation, and automated initial triage assessment for SOAR cases. |
| `case.timeline` | case | Synthesizes a chronologically ordered event timeline across Case Creation, Alert Detections, Playbook Milestones, Analyst Comments, and Case Updates. |
| `case.triage` | case | End-to-end single case triage: deep investigation, Gemini AI summary, title and entity precedent correlation, novelty assessment, and stage transitions. |
| `case_alert.get_recommendation` | case | End-to-end workflow to trigger Gemini AI recommendation generation and poll until completion or failure. |
| `curated_detections.audit_health` | curated_detections | Performs a comprehensive deployment posture audit, detects misconfigurations like broad alerting, identifies top firing rules, and ranks newest/oldest content. |
| `dashboard.audit_health` | dashboard | Audits native dashboards for recent creations, modifications, broken widget queries, empty placeholders, and staleness. |
| `dashboard.get` | dashboard | Retrieves complete composite dashboard graph with layout, batch-resolved charts, and queries. |
| `dashboard.health_check` | dashboard | Executes comprehensive health check for a named dashboard by resolving configuration, executing all widget queries, and generating operational ingestion health summary. |
| `data_table.audit_health` | data_table | Audits Data Tables across the tenant for lifecycle recency, schema integrity, and detection false-negative risks. |
| `entity.investigate` | entity | Correlates an indicator across UDM Entity Graph, UDM Events, Enterprise IoC Intelligence, and SOAR Cases. |
| `entity.search_udm` | entity | Executes streaming searches across the native UDM entity graph (graph.entity.*). |
| `event.investigate` | event | Retrieves canonical UDM fields and raw log payload with complete provenance. |
| `feed.audit_health` | feed | Audits and correlates ingestion feed states, Health Hub telemetry, and transport latency. |
| `parser.audit_health` | parser | Audits and correlates SIEM parser states, CBN version drift, extension conflicts, and Health Hub telemetry. |
| `rule.audit_health` | rule | Audits and correlates Chronicle YARA-L rules, execution errors, latency observability, and detection decay. |
| `search.from_entity` | search | Translates high-level entity artifacts into canonical UDM query expressions. |
| `search.refine` | search | Refines existing queries by applying structured inclusion/exclusion filters on UDM paths. |
| `search.udm` | search | Validates, initiates, incrementally streams, and manages lifecycle of UDM search queries. |

## All capabilities by domain

### alert  (1: workflow=1)

| capability_id | kind | cardinality | mcp_tool (proposed) | description |
| :--- | :--- | :--- | :--- | :--- |
| `alert.investigate` | workflow | — | `investigate_alert` | Retrieves security alert details with root-cause entities and raw log attachments. |

### case  (19: workflow=6, primitive=10, query=3)

| capability_id | kind | cardinality | mcp_tool (proposed) | description |
| :--- | :--- | :--- | :--- | :--- |
| `case.get_summary` | workflow | — | `get_case_summary` | Requests Gemini AI case summary and polls until generation is complete or timeout. |
| `case.investigate` | workflow | — | `investigate_case` | Aggregates case metadata, security alerts, involved entities, and analyst comments. |
| `case.orchestrate_triage` | workflow | — | `orchestrate_case_triage` | Batched retrieval, parallel investigation, and automated initial triage assessment for SOAR cases. |
| `case.timeline` | workflow | — | `get_case_timeline` | Synthesizes a chronologically ordered event timeline across Case Creation, Alert Detections, Playbook Milestones, Analyst Comments, and Case Updates. |
| `case.triage` | workflow | — | `triage_case` | End-to-end single case triage: deep investigation, Gemini AI summary, title and entity precedent correlation, novelty assessment, and stage transitions. |
| `case_alert.get_recommendation` | workflow | — | `get_case_alert_recommendation` | End-to-end workflow to trigger Gemini AI recommendation generation and poll until completion or failure. |
| `case.assign` | primitive | — | `assign_case` | Assigns a SOAR case to a SOC role (@Role) or user GUID. |
| `case.comment` | primitive | — | `add_case_comment` | Adds structured analyst investigation comments to a SOAR case. |
| `case.get_or_create_summary` | primitive | — | `get_or_create_case_summary` | Gets or initiates generation of a Gemini AI-driven overview, reasons, and next steps for a SOAR case. |
| `case.set_incident` | primitive | — | `set_case_incident` | Marks or unmarks a SOAR case as an incident. |
| `case.set_stage` | primitive | — | `set_case_stage` | Updates the lifecycle stage of a SOAR case. |
| `case.update` | primitive | — | `update_case` | Mutates case attributes such as assignee, stage, incident flag, or priority. |
| `case_alert.create_recommendation` | primitive | — | `create_case_alert_recommendation` | Initiates asynchronous generation of a Gemini AI recommendation for a case alert. |
| `case_alert.fetch_recommendation` | primitive | — | `fetch_case_alert_recommendation` | Fetches a previously generated Gemini AI recommendation for a case alert by recommendation ID. |
| `case_alert.set_priority` | primitive | — | `set_case_alert_priority` | Updates the priority level of a specific case alert. |
| `case_alert.update` | primitive | — | `update_case_alert` | Mutates case alert attributes such as priority or status. |
| `case.get_wall` | query | `unbounded` | `get_case_wall` | Retrieves the complete SOAR case activity stream including status changes, tag updates, and playbook execution steps. |
| `case.list_comments` | query | `unbounded` | `list_case_comments` | Lists all analyst comments and AI assessment notes for a SOAR case. |
| `case.search` | query | `unbounded` | `search_cases` | Searches, lists, and filters SOAR cases across time ranges, status, priority, and stages. |

### case_config  (14: query=14)

| capability_id | kind | cardinality | mcp_tool (proposed) | description |
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

| capability_id | kind | cardinality | mcp_tool (proposed) | description |
| :--- | :--- | :--- | :--- | :--- |
| `content_pack.categories` | query | `unbounded` | `list_content_pack_categories` | Discovers and aggregates the taxonomy of Content Hub categories with pack counts. |
| `content_pack.get` | query | `single` | `get_content_pack` | Retrieves complete Content Pack details and bundled playbooks, integrations, dashboards, rulesets, and queries. |
| `content_pack.search` | query | `unbounded` | `search_content_packs` | Searches, lists, and filters Content Hub Marketplace Content Packs across categories and pack types. |

### curated_detections  (6: workflow=1, primitive=1, query=4)

| capability_id | kind | cardinality | mcp_tool (proposed) | description |
| :--- | :--- | :--- | :--- | :--- |
| `curated_detections.audit_health` | workflow | — | `audit_curated_detections_health` | Performs a comprehensive deployment posture audit, detects misconfigurations like broad alerting, identifies top firing rules, and ranks newest/oldest content. |
| `curated_detections.set_deployment` | primitive | — | `set_curated_ruleset_deployment` | Updates enabled and alerting states for a Curated Rule Set precision deployment. |
| `curated_detections.get_rule` | query | `single` | `get_curated_rule` | Retrieves an individual Curated Rule, its MITRE techniques, false positives, and raw YARA-L logic. |
| `curated_detections.get_ruleset` | query | `single` | `get_curated_ruleset` | Deep-inspects a Curated Rule Set, its broad/precise deployments, member rules, and detection telemetry. |
| `curated_detections.metrics` | query | `single` | `get_curated_detection_metrics` | Aggregates detection firing counts and retrieves tenant-wide rule quotas and telemetry. |
| `curated_detections.search_rulesets` | query | `unbounded` | `search_curated_rulesets` | Discovers and searches Google SecOps Curated Rule Sets with MITRE ATT&CK mappings and log sources. |

### dashboard  (6: workflow=3, query=3)

| capability_id | kind | cardinality | mcp_tool (proposed) | description |
| :--- | :--- | :--- | :--- | :--- |
| `dashboard.audit_health` | workflow | — | `audit_dashboard_health` | Audits native dashboards for recent creations, modifications, broken widget queries, empty placeholders, and staleness. |
| `dashboard.get` | workflow | — | `get_dashboard` | Retrieves complete composite dashboard graph with layout, batch-resolved charts, and queries. |
| `dashboard.health_check` | workflow | — | `run_dashboard_health_check` | Executes comprehensive health check for a named dashboard by resolving configuration, executing all widget queries, and generating operational ingestion health summary. |
| `dashboard.execute_query` | query | `bounded` | `execute_dashboard_query` | Executes a dashboard widget query against live telemetry and transforms columnar results into tabular records. |
| `dashboard.search` | query | `unbounded` | `search_dashboards` | Searches, lists, and filters native dashboards configured in Google SecOps. |
| `dashboard.validate_query` | query | `bounded` | `validate_dashboard_query` | Validates statistical / dashboard widget query syntax against the live Google SecOps query compiler. |

### data_rbac  (5: query=5)

| capability_id | kind | cardinality | mcp_tool (proposed) | description |
| :--- | :--- | :--- | :--- | :--- |
| `data_rbac.environment.search` | query | `unbounded` | `search_environment_scopes` | Discovers SOAR multi-tenant environments and inspects their bound Data Access Scopes. |
| `data_rbac.label.get` | query | `single` | `get_data_access_label` | Retrieves full configuration of a Data Access Label including UDM filter expression. |
| `data_rbac.label.search` | query | `unbounded` | `search_data_access_labels` | Discovers Data Access Labels and their associated UDM filter query definitions. |
| `data_rbac.scope.get` | query | `single` | `get_data_access_scope` | Retrieves deep configuration of a Data Access Scope including label attachments. |
| `data_rbac.scope.search` | query | `unbounded` | `search_data_access_scopes` | Discovers and filters Data Access RBAC Scopes and allow/deny label counts. |

### data_table  (9: workflow=1, primitive=5, query=3)

| capability_id | kind | cardinality | mcp_tool (proposed) | description |
| :--- | :--- | :--- | :--- | :--- |
| `data_table.audit_health` | workflow | — | `audit_data_tables` | Audits Data Tables across the tenant for lifecycle recency, schema integrity, and detection false-negative risks. |
| `data_table.add_rows` | primitive | — | `add_data_table_rows` | Creates or appends rows in bulk to a Chronicle SIEM Data Table. |
| `data_table.create` | primitive | — | `create_data_table` | Creates a new structured Data Table with typed column definitions in Chronicle SIEM. |
| `data_table.delete` | primitive | — | `delete_data_table` | Deletes a structured Data Table from Chronicle SIEM. |
| `data_table.delete_row` | primitive | — | `delete_data_table_row` | Deletes a single row from a Chronicle SIEM Data Table by row ID. |
| `data_table.patch` | primitive | — | `patch_data_table` | Updates description, TTL, or scope info of an existing Chronicle SIEM Data Table. |
| `data_table.get` | query | `single` | `get_data_table` | Retrieves schema, columns, TTL, and metadata for a Chronicle SIEM Data Table. |
| `data_table.list` | query | `unbounded` | `list_data_tables` | Lists all structured Data Tables defined in Chronicle SIEM. |
| `data_table.list_rows` | query | `unbounded` | `list_data_table_rows` | Queries and filters rows contained within a Chronicle SIEM Data Table. |

### enrichment  (3: query=3)

| capability_id | kind | cardinality | mcp_tool (proposed) | description |
| :--- | :--- | :--- | :--- | :--- |
| `enrichment.combination.list` | query | `unbounded` | `list_enrichment_combinations` | Discovers available enrichment types, target log types, and enrichment sources. |
| `enrichment.control.get` | query | `single` | `get_enrichment_control` | Retrieves full configuration and timing rules for a deployed enrichment control. |
| `enrichment.control.search` | query | `unbounded` | `search_enrichment_controls` | Discovers and filters deployed enrichment controls that restrict entity enrichments. |

### entity  (3: workflow=2, query=1)

| capability_id | kind | cardinality | mcp_tool (proposed) | description |
| :--- | :--- | :--- | :--- | :--- |
| `entity.investigate` | workflow | — | `investigate_entity` | Correlates an indicator across UDM Entity Graph, UDM Events, Enterprise IoC Intelligence, and SOAR Cases. |
| `entity.search_udm` | workflow | — | `search_entity_udm` | Executes streaming searches across the native UDM entity graph (graph.entity.*). |
| `entity.summarize` | query | `single` | `summarize_entity` | Retrieves entity timeline intervals, prevalence metrics, and metadata. |

### event  (1: workflow=1)

| capability_id | kind | cardinality | mcp_tool (proposed) | description |
| :--- | :--- | :--- | :--- | :--- |
| `event.investigate` | workflow | — | `investigate_event` | Retrieves canonical UDM fields and raw log payload with complete provenance. |

### feed  (5: workflow=1, query=4)

| capability_id | kind | cardinality | mcp_tool (proposed) | description |
| :--- | :--- | :--- | :--- | :--- |
| `feed.audit_health` | workflow | — | `audit_feed_health` | Audits and correlates ingestion feed states, Health Hub telemetry, and transport latency. |
| `feed.get` | query | `single` | `get_feed` | Retrieves full configuration details and source parameters for an ingestion feed. |
| `feed.search` | query | `unbounded` | `search_feeds` | Searches, lists, and filters push/pull ingestion feeds across source types and log types. |
| `feed_schema.list_log_types` | query | `unbounded` | `list_feed_log_type_schemas` | Lists log types supported by a specific feed source with lean payload handling. |
| `feed_schema.list_sources` | query | `unbounded` | `list_feed_source_type_schemas` | Lists all supported feed source types and collection mechanisms. |

### integration  (4: query=4)

| capability_id | kind | cardinality | mcp_tool (proposed) | description |
| :--- | :--- | :--- | :--- | :--- |
| `integration.get` | query | `single` | `get_integration` | Retrieves complete integration details, instances, remote agents, and documentation. |
| `integration.instances` | query | `unbounded` | `list_integration_instances` | Lists configured integration instances across environments or specific integrations. |
| `integration.remote_agents` | query | `unbounded` | `list_remote_agents` | Lists remote proxy execution agents and their supported environments. |
| `integration.search` | query | `unbounded` | `search_integrations` | Searches, lists, and filters SOAR integrations across environments, status, and certification. |

### ioc  (1: query=1)

| capability_id | kind | cardinality | mcp_tool (proposed) | description |
| :--- | :--- | :--- | :--- | :--- |
| `ioc.search_enterprise` | query | `bounded` | `search_enterprise_iocs` | Searches enterprise IoC matches and Mandiant breach intelligence for indicators. |

### job  (4: query=4)

| capability_id | kind | cardinality | mcp_tool (proposed) | description |
| :--- | :--- | :--- | :--- | :--- |
| `job.get` | query | `single` | `get_job` | Retrieves complete job details, deployed runtime instances, and recent execution logs. |
| `job.instances` | query | `unbounded` | `list_job_instances` | Lists runtime job instances deployed across environments or specific jobs. |
| `job.logs` | query | `unbounded` | `get_job_instance_logs` | Retrieves execution run records and output logs for a job instance. |
| `job.search` | query | `unbounded` | `search_jobs` | Searches, lists, and filters SOAR scheduled jobs across integrations and execution schedules. |

### marketplace_integration  (4: query=4)

| capability_id | kind | cardinality | mcp_tool (proposed) | description |
| :--- | :--- | :--- | :--- | :--- |
| `marketplace_integration.affected_items` | query | `unbounded` | `get_marketplace_integration_affected_items` | Resolves affected environment instances and active playbooks before integration modifications. |
| `marketplace_integration.diff` | query | `single` | `get_marketplace_integration_diff` | Compares commercial upgrade differences and overrides between installed and target versions. |
| `marketplace_integration.get` | query | `single` | `get_marketplace_integration` | Retrieves complete integration composite, actions, connectors, jobs, managers, and release notes. |
| `marketplace_integration.search` | query | `unbounded` | `search_marketplace_integrations` | Discovers, searches, and filters Marketplace Response Integrations across categories and update states. |

### parser  (7: workflow=1, query=6)

| capability_id | kind | cardinality | mcp_tool (proposed) | description |
| :--- | :--- | :--- | :--- | :--- |
| `parser.audit_health` | workflow | — | `audit_parser_health` | Audits and correlates SIEM parser states, CBN version drift, extension conflicts, and Health Hub telemetry. |
| `parser.extensions.get` | query | `single` | `get_parser_extension` | Retrieves full parser extension configuration, decoded snippet, and test log. |
| `parser.extensions.search` | query | `unbounded` | `search_parser_extensions` | Discovers parser extensions and dynamic parsing configurations across log types. |
| `parser.get` | query | `single` | `get_parser` | Retrieves complete parser metadata and decoded Logstash CBN filter code. |
| `parser.log_type_setting.get` | query | `single` | `get_log_type_setting` | Retrieves autonomous parsing settings and extraction type for a specific log type. |
| `parser.log_types.list` | query | `unbounded` | `list_log_types` | Discovers and filters supported ingestion log types cataloged in Google SecOps. |
| `parser.search` | query | `unbounded` | `search_parsers` | Discovers and filters parsers across log types with creator and state filters. |

### playbook  (5: primitive=1, query=4)

| capability_id | kind | cardinality | mcp_tool (proposed) | description |
| :--- | :--- | :--- | :--- | :--- |
| `playbook.audit_health` | primitive | — | `audit_soar_playbook_health` | Audits SOAR playbooks and modular blocks for configuration hygiene, failure spikes, faulted actions, and queue latency using native Playbook Dashboard analytics. |
| `playbook.categories` | query | `unbounded` | `list_playbook_categories` | Lists all SOAR Playbook folder categories. |
| `playbook.get` | query | `single` | `get_playbook` | Retrieves complete playbook definition, trigger conditions, and step execution DAG. |
| `playbook.instances` | query | `unbounded` | `get_alert_playbook_instances` | Retrieves authoritative per-alert playbook run instances and the executed step DAG. |
| `playbook.search` | query | `unbounded` | `search_playbooks` | Searches, lists, and filters SOAR playbooks across categories, triggers, and environments. |

### preview_feature  (2: query=2)

| capability_id | kind | cardinality | mcp_tool (proposed) | description |
| :--- | :--- | :--- | :--- | :--- |
| `preview_feature.get` | query | `single` | `get_preview_feature` | Retrieves specific preview feature configuration, documentation, and retirement dates. |
| `preview_feature.list` | query | `unbounded` | `list_preview_features` | Discovers customer preview feature flags, enablement states, retirement schedules, and docs. |

### rule  (11: workflow=1, primitive=4, query=6)

| capability_id | kind | cardinality | mcp_tool (proposed) | description |
| :--- | :--- | :--- | :--- | :--- |
| `rule.audit_health` | workflow | — | `audit_rule_health` | Audits and correlates Chronicle YARA-L rules, execution errors, latency observability, and detection decay. |
| `rule.create` | primitive | — | `create_rule` | Creates a new YARA-L detection rule in Chronicle SIEM. |
| `rule.delete` | primitive | — | `delete_rule` | Deletes a custom detection rule from Chronicle SIEM. |
| `rule.deployment.update` | primitive | — | `update_rule_deployment` | Updates deployment properties (enabled, alerting, frequency) of a rule. |
| `rule.patch` | primitive | — | `patch_rule` | Updates the YARA-L logic of an existing detection rule. |
| `rule.deployment.get` | query | `single` | `get_rule_deployment` | Retrieves deployment, frequency, and alerting status of a rule. |
| `rule.errors` | query | `unbounded` | `list_rule_errors` | Lists runtime and execution errors across detection rules. |
| `rule.get` | query | `single` | `get_rule` | Retrieves full details and YARA-L logic of a detection rule. |
| `rule.list` | query | `unbounded` | `list_rules` | Lists custom YARA-L detection rules in Chronicle SIEM. |
| `rule.revisions` | query | `unbounded` | `list_rule_revisions` | Lists historical revisions and version history of a detection rule. |
| `rule.verify` | query | `bounded` | `verify_rule_text` | Validates YARA-L 2.0 rule syntax against the Chronicle compiler. |

### search  (4: workflow=3, query=1)

| capability_id | kind | cardinality | mcp_tool (proposed) | description |
| :--- | :--- | :--- | :--- | :--- |
| `search.from_entity` | workflow | — | `search_from_entity` | Translates high-level entity artifacts into canonical UDM query expressions. |
| `search.refine` | workflow | — | `refine_search` | Refines existing queries by applying structured inclusion/exclusion filters on UDM paths. |
| `search.udm` | workflow | — | `search_udm` | Validates, initiates, incrementally streams, and manages lifecycle of UDM search queries. |
| `search.udm.stats` | query | `unbounded` | `search_udm_stats` | Validates, initiates, streams, and aggregates UDM statistics, match/outcome metrics, and multi-field grouping operations via LRO. |

### siem_settings  (6: query=6)

| capability_id | kind | cardinality | mcp_tool (proposed) | description |
| :--- | :--- | :--- | :--- | :--- |
| `pipeline.get` | query | `single` | `get_log_processing_pipeline` | Retrieves full transform statements and stream bindings for a Data Processing Pipeline. |
| `pipeline.search` | query | `unbounded` | `search_log_processing_pipelines` | Discovers and lists Data Processing Pipelines with parser transforms and Bindplane SaaS links. |
| `siem.agent_settings.get` | query | `single` | `get_agent_settings` | Retrieves tenant configuration for automated triage, investigation filters, delays, and quotas. |
| `siem.managed_domains.get` | query | `single` | `get_managed_domain_settings` | Retrieves approved email domains for report deliveries and alerts. |
| `siem.risk_config.get` | query | `single` | `get_entity_risk_config` | Retrieves UEBA entity risk scoring defaults, detection/alert scores, and weighting coefficients. |
| `siem.tenant.get` | query | `single` | `get_tenant_instance` | Retrieves root tenant instance details, active URLs, feature flags, and workforce pool providers. |

### soar_settings  (30: query=30)

| capability_id | kind | cardinality | mcp_tool (proposed) | description |
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
