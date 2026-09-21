---
id: concept.udm_search_lifecycle
title: "UDM Search Execution Lifecycle & Query Optimization"
type: concept
applies_to:
  - secops_siem
related_features:
  - feature.siem.native_dashboards
tags:
  - search
  - udm
  - performance
---

# UDM Search Execution Lifecycle & Query Optimization

## 1. Overview & Mental Model
Unified Data Model (UDM) search executes against Google SecOps' distributed columnar event store. When an analyst or agent submits a search query, the engine parses the expression, determines whether filters target indexed fields (e.g., `principal.ip`, `target.user.userid`) or unindexed attributes, and plans execution across time partition buckets.

## 2. Architecture & Performance Topology
UDM search performance is driven by three primary factors:
1. **Time Range Partitioning:** Queries constrained to narrower windows (e.g., 24 hours vs 30 days) execute orders of magnitude faster.
2. **Indexed Filter Selectivity:** Filtering on indexed fields allows partition pruning before scanning unindexed fields.
3. **Ingestion Latency Alignment:** Searches expecting real-time event matches can produce false negatives if upstream ingestion latency exceeds the query lookback window.

## 3. Operational Guarantees & Constraints
- **Timeout Limits:** Interactive searches have a hard execution cutoff (typically 300 seconds).
- **Page Size Limits:** Results page size is bounded (standard page size 100 to 1,000 items).
- **Quota Throttling:** Rapid sequential or parallel unbounded queries trigger tenant API concurrency limits.

## 4. Cross-System Dependencies
- **SecOps Dashboards:** Health Hub monitors query execution latency (p50, p95) and error spikes.
- **Log Feeds:** Feed ingestion delays directly impact search result freshness.
