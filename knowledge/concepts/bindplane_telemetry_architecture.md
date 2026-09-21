---
id: concept.bindplane_telemetry_architecture
title: "BindPlane OP OpenTelemetry Collection Architecture"
type: concept
applies_to:
  - bindplane
  - secops_siem
related_features:
  - feature.bindplane.agent_fleet
  - feature.siem.feed_management
tags:
  - bindplane
  - opentelemetry
  - collectors
---

# BindPlane OP OpenTelemetry Collection Architecture

## 1. Overview & Mental Model
BindPlane OP manages fleets of OpenTelemetry (OTel) collectors across multi-cloud and on-premises environments. It decouples telemetry generation from destination ingestion by providing a central control plane for agent configuration, filtering processors, and rollout management.

## 2. Ingestion Pipeline Funnel
A BindPlane telemetry pipeline consists of three core components:
1. **Sources:** Inputs capturing system logs (e.g., Windows Event Logs, Syslog, Fluent, Kafka).
2. **Processors:** Pipeline stages performing local filtering, masking sensitive fields, sampling, and batching.
3. **Destinations:** Ingestion endpoints routing data to Chronicle HTTP feeds, Google Cloud Pub/Sub, or Google Cloud Storage.

## 3. Rollout Safety & Canary Stages
- **Progressive Rollout:** When deploying configuration updates to thousands of agents, rollouts proceed in stages (e.g. 5% canary &rarr; 25% &rarr; 100%).
- **Error Backoff:** If canary agents experience elevated crash loops or network buffer exhaustion, rollouts automatically pause to prevent fleet-wide log loss.
