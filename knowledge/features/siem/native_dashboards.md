---
id: feature.siem.native_dashboards
title: SIEM Native Dashboards & Health Hub Telemetry
type: feature
platform: secops_siem
sdk_capabilities:
- dashboard.get
- dashboard.execute_query
- search.udm.stats
mcp_tools:
- get_dashboard
- execute_dashboard_query
- search_udm_stats
related_concepts:
- concept.udm_search_lifecycle
status: stable
description: SIEM Native Dashboards & Health Hub Telemetry (feature reference in Google
  SecOps).
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

# SIEM Native Dashboards & Health Hub Telemetry

## 1. Feature Purpose & Scope
Google SecOps provides Looker-backed native dashboards that expose tenant operational metrics, including ingestion velocity, parser health, and search execution performance. AI agents invoke dashboard queries to retrieve aggregated telemetry without executing expensive ad-hoc raw log scans.

## 2. Underlying APIs & SDK Primitives
- **Fetch Dashboard Specification:** `dashboard.get` (`GET v1alpha/{parent}/dashboards/{dashboard_id}`)
- **Execute Dashboard Tile Query:** `dashboard.execute_query` (`POST v1alpha/{parent}/dashboards:executeQuery`)
- **UDM Aggregate Stats:** `search.udm.stats` (`POST v1alpha/{parent}:searchUdmStats`)

## 3. Input Parameters & Constraints
- **Dashboard ID:** Prebuilt system dashboards use reserved IDs (e.g., `health_hub`).
- **Execution Filter:** Requires a valid Looker filter string or time range window (e.g., `last 7 days`).
- **Cardinality:** Bounded aggregate result sets returning structured row lists.

## 4. Telemetry & Observable Metrics
- `p50_query_latency_ms`: Median execution duration for interactive UDM searches.
- `p95_query_latency_ms`: 95th percentile latency identifying query tail degradation.
- `failed_query_count`: Count of searches failing due to timeout, syntax errors, or quota exhaustion.
