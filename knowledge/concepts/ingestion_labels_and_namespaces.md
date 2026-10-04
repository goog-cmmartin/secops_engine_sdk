---
id: concept.ingestion_labels_and_namespaces
title: Ingestion Labels, UDM Namespaces & Data RBAC Hygiene
type: concept
applies_to:
- secops_siem
related_features:
- feature.siem.data_rbac
- feature.siem.feed_management
- feature.siem.parser_lifecycle
tags:
- ingestion
- namespaces
- labels
- rbac
- data-hygiene
- rfc1918
status: stable
description: Mental model, operational best practices, RFC 1918 overlapping IP mitigation, and Data RBAC alignment for Ingestion Labels and UDM Namespaces in Google SecOps.
generated:
  by: namespace-label-agent/gemini-3.8-flash
  at: '2026-09-24T14:50:00Z'
verified:
- by: human:secops-architect
  at: '2026-09-24T14:55:00Z'
stale_after: '2027-01-01T00:00:00Z'
sources:
- id: google-secops-docs
  resource: https://cloud.google.com/chronicle/docs/unified-data-model/udm-overview
  title: Google SecOps Unified Data Model Overview
- id: google-secops-rbac-docs
  resource: https://cloud.google.com/chronicle/docs/administration/data-access-control
  title: Google SecOps Data Access Control (Data RBAC)
---

# Ingestion Labels, UDM Namespaces & Data RBAC Hygiene

## 1. Overview & Mental Model

In Google SecOps, log hygiene and data quality depend fundamentally on how incoming telemetry is partitioned, tagged, and scoped at ingestion time. Two primary primitives govern telemetry tagging in the Unified Data Model (UDM): **Ingestion Labels** (`metadata.ingestion_labels`) and **UDM Namespaces** (`metadata.base_labels.namespaces`).

```
                    ┌───────────────────────────────┐
                    │      Incoming Telemetry       │
                    └───────────────┬───────────────┘
                                    │
               ┌────────────────────┴────────────────────┐
               ▼                                         ▼
   ┌───────────────────────┐                 ┌───────────────────────┐
   │   Ingestion Labels    │                 │    UDM Namespaces     │
   │  Arbitrary Key-Value  │                 │  Disambiguates IP     │
   │  (e.g., env, team,    │                 │  Collisions (RFC1918) │
   │   gcp_organization)   │                 │  (Default = untagged) │
   └───────────┬───────────┘                 └───────────┬───────────┘
               │                                         │
               └────────────────────┬────────────────────┘
                                    ▼
                    ┌───────────────────────────────┐
                    │       Google SecOps UDM       │
                    └───────────────┬───────────────┘
                                    │
                                    ▼
                    ┌───────────────────────────────┐
                    │       Data Access RBAC        │
                    │   Scopes & Access Labels      │
                    │ (Isolates access per tenant)  │
                    └───────────────────────────────┘
```

### 1.1 Ingestion Labels (`metadata.ingestion_labels`)
- **Arbitrary & Decentralized:** Ingestion Labels are arbitrary key-value pairs (`label.key` and `label.value`). They are not defined centrally in a fixed schema.
- **Consistency Best Practice:** While arbitrary, best practice dictates that when used, Ingestion Labels must be applied consistently across feeds, forwarders, and log types. Inconsistent casing or naming conventions (e.g., `sourceUsecase` vs `use_case_name` or `env` vs `environment`) fracture UDM search queries and break downstream automation.
- **Provider-Injected Labels:** In certain cases, ingestion labels are injected automatically by Google Cloud or ingestion pipelines. For instance, `gcp_organization_id` is automatically attached to `GCP_CLOUDAUDIT` telemetry.

### 1.2 UDM Namespaces (`metadata.base_labels.namespaces`)
- **Optional Primitive:** Namespaces are a best practice but optional.
- **Untagged Default Namespace:** By default, all telemetry ingested without an explicit namespace assignment resides in the **untagged default namespace**. This default namespace is not displayed in the Google SecOps UI.
- **RFC 1918 Collision Disambiguation:** Namespaces exist specifically to resolve overlapping private IP address ranges (RFC 1918 private subnets: `10.0.0.0/8`, `172.16.0.0/12`, `192.168.0.0/16`). In modern enterprise architectures, multiple branch offices, physical datacenters, or acquired cloud VPCs frequently re-use the exact same private subnet addresses (e.g. `10.0.1.5` at Office A and `10.0.1.5` at Datacenter B). Without namespaces, Google SecOps treats them as the same asset, causing asset graph corruption, false-positive entity linkage, and invalid timeline correlations.

### 1.3 Critical Dependency: Data RBAC Alignment
- **Data Access Isolation:** Google SecOps Data RBAC enforces granular access isolation via **Data Access Scopes** and **Data Access Labels**.
- **UDM Predicate Matching:** Data Access Labels evaluate explicit UDM filter predicates against indexed events—specifically targeting `metadata.ingestion_labels[...]` and `metadata.base_labels.namespaces`.
- **Integrity Requirement:** For Data RBAC to work reliably, data labelling and namespaces must be applied accurately and consistently at ingestion. If an ingestion feed drops a label or assigns an incorrect namespace, events either fail to match the designated Data Access Scope or leak across tenant administrative boundaries.

---

## 2. Operational GoogleSQL Auditing Recipes

To audit data quality and hygiene across active telemetry, administrators and automated agents execute native GoogleSQL queries against the Chronicle `events` table:

### 2.1 Checking Active Ingestion Labels
```sql
SELECT
  label.key AS ingestion_label_key,
  ARRAY_AGG(DISTINCT metadata.log_type) AS log_types,
  COUNT(1) AS event_count
FROM events,
UNNEST(metadata.ingestion_labels) AS label
WHERE
  NULLIF(label.key, '') IS NOT NULL
GROUP BY 1
ORDER BY event_count DESC;
```

### 2.2 Checking Active UDM Namespaces
```sql
SELECT
  namespace,
  ARRAY_AGG(DISTINCT metadata.log_type) AS log_types,
  COUNT(1) AS event_count
FROM events,
UNNEST(metadata.base_labels.namespaces) AS namespace
WHERE
  NULLIF(namespace, '') IS NOT NULL
GROUP BY 1
ORDER BY event_count DESC;
```

### 2.3 Identifying Untagged Telemetry Volume
```sql
-- Unlabelled ingestion events
SELECT
  metadata.log_type,
  COUNT(1) AS event_count
FROM events
WHERE ARRAY_LENGTH(metadata.ingestion_labels) = 0 OR metadata.ingestion_labels IS NULL
GROUP BY 1
ORDER BY event_count DESC;

-- Events residing in default untagged namespace
SELECT
  metadata.log_type,
  COUNT(1) AS event_count
FROM events
WHERE ARRAY_LENGTH(metadata.base_labels.namespaces) = 0 OR metadata.base_labels.namespaces IS NULL
GROUP BY 1
ORDER BY event_count DESC;
```

---

## 3. Hygiene Violations & Anti-Patterns

| Anti-Pattern | Severity | Operational Impact | Recommended Remediation |
| :--- | :--- | :--- | :--- |
| **Unbacked Data RBAC Labels** | `HIGH` | Data Access Label references an Ingestion Label or Namespace not present in any live telemetry, causing access rules to never match. | Audit forwarder configuration or correct Data Access Label UDM query predicate. |
| **Untagged RFC 1918 Network Telemetry** | `HIGH` | Network logs (`PAN_FIREWALL`, `GCP_FIREWALL`, `GCP_DNS`, `GCP_VPC_FLOW`, DHCP) ingested without a namespace cause asset timeline collisions across private IP subnets. | Assign discrete namespaces per VPC, branch site, or collector cluster in feed configuration. |
| **Inconsistent Label Casing / Naming** | `MEDIUM` | Mixed casing or naming conventions (e.g., `sourceUsecase` vs `use_case_name`) causes fragmented searches and broken detection queries. | Standardize forwarder feed labels to lowercase snake_case. |
| **Missing Labels on Compliance Logs** | `LOW` | Audit and authentication logs lack environment or tenant tags needed for regulatory scoping (PCI, HIPAA, SOC 2). | Configure collector transforms or forwarder metadata tags. |

---

## 4. Remediation & Operational Protocol

1. **Regular Autonomous Auditing:** Schedule periodic hygiene evaluations via `@namespace-label-agent` (`ingestion.labels_and_namespaces.analyze`) to identify untagged volume spikes and RFC 1918 risks.
2. **Pre-Deployment Data RBAC Verification:** Whenever a new Data Access Label is configured, execute `ingestion.rbac_alignment.audit` to confirm that all referenced ingestion labels and namespaces actually exist in indexed telemetry.
3. **Feed Configuration Standardization:** When standing up new Chronicle forwarders or BindPlane pipelines, explicitly enforce:
   - Mandatory namespace assignment for any pipeline ingesting private RFC 1918 address telemetry.
   - Consistent lowercase snake_case ingestion labels for business units, environments, and compliance tags.
