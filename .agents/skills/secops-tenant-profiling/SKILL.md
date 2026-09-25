---
name: secops-tenant-profiling
description: >-
  Systematic tenant telemetry cartography, entity graph lineage profiling, and UDM identity
  density matrix generation using native Google SecOps GoogleSQL pipe syntax. Use this skill
  when baselining a tenant, validating detection rule field feasibility, ranking log sources
  by semantic entity value, or scoping Deacon monitoring cadences.
type: concept
id: concept.tenant_telemetry_profiling
status: stable
generated:
  by: agent/gemini-3.8-flash
  at: '2026-09-24T19:50:00Z'
verified:
  - by: process:secops-engine-live-verifier
    at: '2026-09-24T19:53:00Z'
stale_after: '2027-09-24T19:50:00Z'
tags:
  - secops
  - cartography
  - googlesql
  - pipe-syntax
  - entity-graph
  - identity-density
  - telemetry-profiling
  - udm
---

# SecOps Tenant Telemetry Cartography & Profiling Guide

Tenant Cartography is the discipline of mapping a Google SecOps tenant's live data topography without generating issue queue churn. It answers foundational operational questions:
1. **Entity Provenance**: Where does Chronicle's Entity Graph get its identity bindings?
2. **Identity Density**: Which log sources actually populate distinct user IDs, email addresses, Windows SIDs, or cloud object IDs?
3. **Asset & Network Fidelity**: Which log sources provide authoritative IP-to-hostname bindings?
4. **Semantic vs. Volume Pareto**: Which log types account for 80% of volume vs. 80% of entity richness?

All queries in this skill use **native Google SecOps GoogleSQL pipe syntax** (`execute_dashboard_query` with `dialect="SQL"`).

---

## 1. Core Principles of Autonomous Cartography

1. **Context Over Alerting:**
   - Cartography queries are strictly non-disruptive. They do **not** open issues in the operational work queue (`BaseWorkQueue`).
   - Instead, they produce **Attested Tenant Computations** (`knowledge/computations/`) that ground autonomous agents (e.g. `@yaral-optimizer`, `@detection-tuning-agent`, `@secops-dispatcher`).

2. **Pre-flight Rule Feasibility:**
   - Autonomous detection agents must never draft or tune a YARAL rule referencing `$e.principal.user.userid` without verifying that the targeted `metadata.log_type` has a non-zero `principal_user_id` density in the current tenant.

3. **Quota & Performance Efficiency:**
   - Historical multi-day aggregations across `events` and `graph` are executed on a low-cadence schedule (e.g. weekly or on-demand by `@tenant-cartographer`) and cached as structured context.

---

## 2. Query Catalog: Native GoogleSQL Pipe Syntax

### 2.1 Identity Fidelity Density Matrix (`events` table)
Measures the population density of distinct user identity keys across all active log types. Use this to determine which log sources can be reliably joined on user identifiers.

```sql
FROM events
|> WHERE TIMESTAMP_SECONDS(metadata.event_timestamp.seconds) >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 7 DAY)
|> AGGREGATE
     COUNT(DISTINCT NULLIF(principal.user.userid, '')) AS principal_user_id,
     COUNT(DISTINCT NULLIF(ARRAY_TO_STRING(principal.user.email_addresses, ','), '')) AS principal_user_email_address,
     COUNT(DISTINCT NULLIF(principal.user.windows_sid, '')) AS principal_user_windows_sid,
     COUNT(DISTINCT NULLIF(principal.user.product_object_id, '')) AS principal_user_product_object_id,
     COUNT(DISTINCT NULLIF(target.user.userid, '')) AS target_user_id,
     COUNT(DISTINCT NULLIF(ARRAY_TO_STRING(target.user.email_addresses, ','), '')) AS target_user_email_address,
     COUNT(DISTINCT NULLIF(target.user.windows_sid, '')) AS target_user_windows_sid,
     COUNT(DISTINCT NULLIF(target.user.product_object_id, '')) AS target_user_product_object_id
   GROUP BY UPPER(metadata.log_type) AS log_type
|> ORDER BY principal_user_id DESC;
```

#### Interpretation Heuristics:
- **High Principal User ID (`GCP_CLOUDAUDIT`, `WORKSPACE_ACTIVITY`)**: Authoritative for cloud identity and administrator actions.
- **High Target User ID (`CS_EDR`, `WINEVTLOG`)**: Authoritative for endpoint execution and lateral movement targets.
- **Windows SID Dominance (`WINEVTLOG`, `ACTIVE_DIRECTORY`)**: On-premise Active Directory environments. Must use Windows SID for cross-event correlation.

---

### 2.2 Entity Graph Lineage & Longevity (`graph` table)
Aggregates entities by source, vendor, product, and log type. Use this to map where Chronicle's entity resolution graph is populated from and to detect stale or decommissioned identity feeds.

```sql
FROM graph
LEFT JOIN UNNEST(metadata.event_metadata.base_labels.log_types) AS log_type
|> AGGREGATE
     COUNT(metadata.product_entity_id) AS total,
     DATE(TIMESTAMP_SECONDS(MIN(metadata.collected_timestamp.seconds))) AS first_seen,
     DATE(TIMESTAMP_SECONDS(MAX(metadata.collected_timestamp.seconds))) AS last_seen
   GROUP BY
     UPPER(COALESCE(log_type, 'UNKNOWN')) AS log_type,
     metadata.source_type AS entity_source,
     metadata.vendor_name,
     metadata.product_name
|> ORDER BY total DESC;
```

#### Interpretation Heuristics:
- **`DERIVED_CONTEXT` vs `ENTITY_CONTEXT`**: `ENTITY_CONTEXT` stems from explicit context feeds (Okta, Workday, Azure AD, GTI). `DERIVED_CONTEXT` represents entities synthesized dynamically from event stream UDM fields.
- **Stale Entities**: If `last_seen` is older than 14 days for a primary identity provider, flag for feed ingestion health review.

---

### 2.3 Asset & Network Fidelity Density (`events` table)
Identifies which telemetry sources provide reliable IP, hostname, and MAC address bindings for network and asset tracking.

```sql
FROM events
|> WHERE TIMESTAMP_SECONDS(metadata.event_timestamp.seconds) >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 7 DAY)
|> AGGREGATE
     COUNT(DISTINCT NULLIF(principal.asset.hostname, '')) AS principal_hostnames,
     COUNT(DISTINCT NULLIF(ARRAY_TO_STRING(principal.ip, ','), '')) AS principal_ips,
     COUNT(DISTINCT NULLIF(principal.asset.asset_id, '')) AS principal_asset_ids,
     COUNT(DISTINCT NULLIF(target.asset.hostname, '')) AS target_hostnames,
     COUNT(DISTINCT NULLIF(ARRAY_TO_STRING(target.ip, ','), '')) AS target_ips,
     COUNT(DISTINCT NULLIF(target.asset.asset_id, '')) AS target_asset_ids
   GROUP BY UPPER(metadata.log_type) AS log_type
|> ORDER BY principal_hostnames DESC;
```

---

### 2.4 Telemetry Volume & Semantic Pareto Analysis
Ranks log types by total raw event volume to establish FinOps and ingestion baselines.

```sql
FROM events
|> WHERE TIMESTAMP_SECONDS(metadata.event_timestamp.seconds) >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 7 DAY)
|> AGGREGATE
     COUNT(1) AS event_count,
     DATE(TIMESTAMP_SECONDS(MIN(metadata.event_timestamp.seconds))) AS earliest_event,
     DATE(TIMESTAMP_SECONDS(MAX(metadata.event_timestamp.seconds))) AS latest_event
   GROUP BY UPPER(metadata.log_type) AS log_type
|> ORDER BY event_count DESC;
```

---

## 3. How Autonomous Agents Consume Tenant Cartography

| Consumer Agent | Cartography Requirement | Operational Decision |
| :--- | :--- | :--- |
| **`@yaral-optimizer`** | Identity Density Matrix | Verifies field availability before drafting multi-event joins (e.g. ensures `$e.principal.user.userid` is actually parsed). |
| **`@detection-tuning-agent`** | Ingestion Volume Pareto | Targets tuning and noise-exclusion filters at the top 3 high-volume log sources first. |
| **`@feed-health-agent` (Deacon)** | Graph Lineage & Longevity | Calibrates sensing patrols: high-frequency patrols for top entity sources; daily checks for low-volume devices. |
| **`@secops-dispatcher` (Mayor)** | Complete Telemetry Profile | Orients triage recommendations based on known organizational technology stacks (e.g. AWS vs GCP vs Windows). |

---

## 4. Attested Computation Output Template

When `@tenant-cartographer` completes a survey, it records an OKF Attested Computation under `knowledge/computations/tenant_telemetry_profile.md` using the canonical schema:

```markdown
---
id: computation.tenant_telemetry_profile
type: computation
title: Live Tenant Telemetry & Identity Cartography Profile
status: attested
attestation:
  attested_by: agent/@tenant-cartographer
  attested_at: '2026-09-24T19:50:00Z'
  verification_method: live_secops_googlesql_pipe_queries
  durability_hash: 7b8f9e...
---

# Tenant Telemetry & Identity Cartography Profile

## 1. Primary Identity Providers (Graph Lineage)
...

## 2. UDM Identity Density Matrix (7-Day Observation)
...

## 3. Volume vs. Semantic Density Pareto
...
```
