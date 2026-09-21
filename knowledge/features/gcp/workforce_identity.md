---
id: feature.gcp.workforce_identity
title: "GCP Workforce Identity Pools & Data RBAC Context"
type: feature
platform: gcp
sdk_capabilities:
  - data_rbac.environment.search
  - data_rbac.scope.search
  - data_rbac.label.search
mcp_tools:
  - search_environment_scopes
  - search_data_rbac_scopes
  - search_data_rbac_labels
related_concepts:
  - concept.workforce_identity_federation
---

# GCP Workforce Identity Pools & Data RBAC Context

## 1. Feature Purpose & Scope
Provides operational visibility into federated access controls, identity pool groups, and row-level data access restrictions across Google SecOps and GCP.

## 2. Underlying APIs & SDK Primitives
- **Retrieve Effective RBAC Context:** `data_rbac.environment.search` (`GET v1alpha/{parent}:getDataAccessContext`)
- **Query Data Access Scopes:** `data_rbac.scope.search` (`GET v1alpha/{parent}/dataAccessScopes`)
- **Inspect Data Access Labels:** `data_rbac.label.search` (`GET v1alpha/{parent}/dataAccessLabels`)

## 3. Input Parameters & Constraints
- **Scope ID:** Targets specific compartment scopes assigned to workforce groups.
- **Cardinality:** Bounded collection lists.

## 4. Telemetry & Observable Health Indicators
- Monitor unauthorized 403 API spikes in GCP Cloud Logging for workforce pool principals.
- Track stale group mappings where federated groups have no corresponding active SecOps users.
