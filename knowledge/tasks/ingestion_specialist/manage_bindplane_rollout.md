---
id: task.ingestion_specialist.manage_bindplane_rollout
title: Verify BindPlane Collector Pipeline and Downstream Ingestion Health
type: task
persona: persona.ingestion_specialist
trigger:
- on_demand
- scheduled_weekly
capabilities_used:
- feed.audit_health
- feed.search
related_concepts:
- concept.bindplane_telemetry_architecture
related_features:
- feature.bindplane.agent_fleet
evaluation_rules:
  max_canary_failure_rate_pct: 1.0
  max_latency_hours: 2.0
status: stable
description: Verify BindPlane Collector Pipeline and Downstream Ingestion Health (task
  reference in Google SecOps).
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

# Verify BindPlane Collector Pipeline and Downstream Ingestion Health

## 1. Intent & Context
Safely verify that telemetry collected by BindPlane OP OpenTelemetry agents successfully reaches Google SecOps feeds without pipeline drops or latency spikes during configuration updates.

## 2. Preconditions & Required Context
- Access to SecOps SIEM Ingestion APIs.

## 3. Step-by-Step Execution Procedure

### Step 1: Audit Downstream Feed Health
Invoke `feed.audit_health`:
- Inspect latency and error metrics across all Chronicle feeds receiving BindPlane telemetry.

### Step 2: Correlate Ingestion Velocity
Invoke `feed.search` to verify that feed state is `ACTIVE` and initiation timestamps are progressing normally.

### Step 3: Evaluate Against Thresholds
- **Healthy:** Latency < 2.0 hours, 0 feed transport errors.
- **Warning:** Ingestion latency between 2.0 and 4.0 hours during rollout window.
- **Critical:** Feed dropped to `FAILED` or latency > 4.0 hours, indicating collector pipeline stall.

## 4. Remediation & Escalation Runbook
- If latency spikes post-rollout, pause the rollout and review processor batch timeout settings.
