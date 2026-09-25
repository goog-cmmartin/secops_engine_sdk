# Features

System capabilities, API contracts, Looker/Native dashboards, and SDK workflow primitives across Google SecOps, GCP, and BindPlane OP.

## Google SecOps SIEM

- [Curated Detections](siem/curated_detections.md): Google-managed detection sets, rule deployment, and precision exceptions.
- [Data RBAC](siem/data_rbac.md): Scoped access controls, log-type restrictions, and namespace isolation.
- [Data Tables](siem/data_tables.md): Chronicle reference tables, lookups, threat lists, and enrichment feeds.
- [Feed Management](siem/feed_management.md): Ingestion feed configurations, source authentications, and schedule intervals.
- [Native Dashboards](siem/native_dashboards.md): Built-in and Looker-driven telemetry tiles, ingestion health, and audit boards.
- [Parser Lifecycle](siem/parser_lifecycle.md): Custom and default parsers, CBN snippets, schema validation, and error triage.
- [Rules Engine](siem/rules_engine.md): YARA-L 2 rule management, versioning, alert dispatch, and live validation.
- [SIEM Settings](siem/siem_settings.md): Enterprise tenant configuration, retention periods, and system preferences.

## Google SecOps SOAR

- [Case Configuration](soar/case_configuration.md): Case stages, custom fields, taxonomies, and priority mappings.
- [Case Management](soar/case_management.md): Incident triage, analyst assignments, comments, and timeline histories.
- [Integrations](soar/integrations.md): Third-party connectors, API keys, action runners, and proxy connections.
- [Playbooks](soar/playbooks.md): Automated response trees, condition branches, playbook blocks, and run histories.
- [SOAR Settings](soar/soar_settings.md): SLA timers, environment partitions, notification rules, and webhook receivers.

## BindPlane OP

- [Agent Fleet](bindplane/agent_fleet.md): BindPlane agent deployments, configuration rollouts, and health monitoring.

## Google Cloud Platform (GCP)

- [Cloud Logging](gcp/cloud_logging.md): GCP log routers, sinks, log buckets, and export feeds into Chronicle.
- [Cloud Monitoring](gcp/cloud_monitoring.md): Alert policies, log-based metrics, and telemetry dashboards.
- [Workforce Identity](gcp/workforce_identity.md): SAML / OIDC pools, attribute mappings, and SecOps role synchronization.
