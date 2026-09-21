---
id: feature.bindplane.agent_fleet
title: "BindPlane OP Collector Fleets & Pipeline Ingestion"
type: feature
platform: bindplane
sdk_capabilities:
  - feed.search
  - feed.get
  - feed.audit_health
mcp_tools:
  - search_feeds
  - get_feed
  - audit_feed_health
related_concepts:
  - concept.bindplane_telemetry_architecture
---

# BindPlane OP Collector Fleets & Pipeline Ingestion

## 1. Feature Purpose & Scope
Provides operational visibility into BindPlane agent fleets and connects agent health directly to downstream Chronicle SIEM feed ingestion health.

## 2. Underlying APIs & SDK Primitives
- **Feed Ingestion Health:** `feed.audit_health` correlates feed status with upstream collector transmission.
- **Feed Configuration:** `feed.search` and `feed.get` identify collector-driven Chronicle endpoints.

## 3. Input Parameters & Constraints
- **Agent Health State:** Track active, disconnected, and error states.
- **Canary Thresholds:** Maximum acceptable failure rate during progressive rollouts (< 1.0%).

## 4. Telemetry & Observable Health Indicators
- Ingestion latency spikes correlating with agent buffer backlog.
- Collector heartbeat disconnects.
