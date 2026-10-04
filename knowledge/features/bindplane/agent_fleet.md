---
id: feature.bindplane.agent_fleet
title: BindPlane OP Collector Fleets & Pipeline Ingestion
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
status: stable
description: BindPlane OP Collector Fleets & Pipeline Ingestion (feature reference
  in Google SecOps).
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
