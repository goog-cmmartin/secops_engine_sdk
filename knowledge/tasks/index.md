# Tasks & Runbooks

Step-by-step executable runbooks, quantitative evaluation thresholds, and remediation procedures for autonomous agents and human operators.

## Detection Engineering Runbooks

- [Review Rule Health](detection_engineer/review_rule_health.md): Audit YARA-L 2 rule execution latency, memory footprint, and false positive rates.

## Ingestion Engineering Runbooks

- [Audit Feed Health](ingestion_specialist/audit_feed_health.md): Ingestion pipeline latency, timestamp skew anomalies, and parser CBN error triage.
- [Manage BindPlane Rollout](ingestion_specialist/manage_bindplane_rollout.md): Staged configuration deployment, agent fleet health checks, and rollback safety.

## Platform Engineering Runbooks

- [Audit Identity & Access](platform_engineer/audit_identity_access.md): Workforce identity federation, IAM role bindings, and privilege drift.
- [Audit Tenant Configuration Posture](platform_engineer/audit_tenant_configuration_posture.md): Chronicle settings, data RBAC scope policies, and retention compliance.
- [Check UDM Search Performance](platform_engineer/check_udm_search_performance.md): Query partition pruning, scan quotas, and index latency benchmarks.
- [Monitor Chronicle GCP Telemetry](platform_engineer/monitor_chronicle_gcp_telemetry.md): Cloud Logging sinks, Pub/Sub export queues, and forwarding errors.

## SOC Analyst Runbooks

- [Audit SOAR Playbook Decay](soc_analyst/audit_soar_playbook_decay.md): Deprecated action blocks, broken integration connectors, and failed execution runs.
- [Triage High Priority Cases](soc_analyst/triage_high_priority_cases.md): SLA triage, alert grouping, threat enrichment, and incident assignment.
