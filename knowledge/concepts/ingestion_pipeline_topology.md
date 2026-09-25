---
id: concept.ingestion_pipeline_topology
title: Log Ingestion Pipeline Topology & Latency Dynamics
type: concept
applies_to:
- secops_siem
- bindplane
- gcp
related_features:
- feature.siem.feed_management
- feature.siem.parser_lifecycle
tags:
- ingestion
- latency
- pipelines
status: stable
description: 'Understanding the pipeline topology is essential for isolating latency:
  1. **Source Generation:** System emits log (`metadata.event_timestamp`). 2. **Collect...'
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

# Log Ingestion Pipeline Topology & Latency Dynamics

## 1. Overview & Mental Model
Telemetry enters Google SecOps through multiple ingestion paths: BindPlane OP OpenTelemetry agents, GCP Cloud Logging Pub/Sub exports, direct API ingestion, and native pull feeds (e.g., S3, Azure Blob, Office 365). 

Understanding the pipeline topology is essential for isolating latency:
1. **Source Generation:** System emits log (`metadata.event_timestamp`).
2. **Collection & Transport:** Agent or collector buffers and transports to intermediate queues (e.g., GCP Pub/Sub, BindPlane OP).
3. **Chronicle Feed Receipt:** Chronicle pull/push feed ingests payload.
4. **Ingestion Pipeline & Normalization:** Chronicle extracts fields via Parser and maps to UDM (`metadata.ingested_timestamp`).

## 2. Ingestion Latency vs Event Latency
- **Event Latency ($T_{ingested} - T_{event}$):** Represents delay between event occurrence and indexing in Chronicle. Delays exceeding 2 hours degrade detection timeliness.
- **Transport Latency:** Delay between collector batch flushes.
- **Processing Queue Latency:** Backlog inside Chronicle ingestion queues during volume spikes.

## 3. Operational Guarantees & Constraints
- **Late-Arriving Data Buffer:** YARA-L rules rely on execution schedules that accommodate late data. Setting late-arriving buffers to 0 seconds risks missing delayed telemetry.
- **Feed Error Quotas:** Feeds encountering continuous authentication or schema failures enter degraded or failed states.
