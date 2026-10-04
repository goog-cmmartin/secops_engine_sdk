---
id: task.ingestion_specialist.audit_feed_health
title: Audit Feed Connectivity, Ingestion Latency, and Error States
type: task
persona: persona.ingestion_specialist
trigger:
- scheduled_daily
- on_demand
capabilities_used:
- feed.audit_health
- feed.search
- feed.get
related_concepts:
- concept.ingestion_pipeline_topology
related_features:
- feature.siem.feed_management
evaluation_rules:
  max_acceptable_latency_hours: 4.0
  max_unhealthy_feeds: 0
status: stable
description: Audit Feed Connectivity, Ingestion Latency, and Error States (task reference
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

# Audit Feed Connectivity, Ingestion Latency, and Error States

## 1. Intent & Context
Ensure that all push and pull feeds in Google SecOps are transmitting logs cleanly without authentication failures, transport errors, or ingestion latency drift.

## 2. Preconditions & Required Context
- Tenant must be initialized with authorized SecOps credentials.

## 3. Step-by-Step Execution Procedure

### Step 1: Run Proactive Feed Health Audit
Invoke SDK capability `feed.audit_health`:
- Evaluates configured feeds against Health Hub telemetry and Deep Dive metrics.
- Returns list of unhealthy feeds, severity classifications, and error messages.

### Step 2: Investigate Specific Unhealthy Feeds
For each feed reported in `UNHEALTHY` or `DEGRADED` state:
- Invoke `feed.get` to retrieve feed state, last initiation time, and failure details.

### Step 3: Evaluate Against Thresholds
- **Healthy:** 0 failing feeds, latency < 2.0 hours.
- **Warning:** Latency between 2.0 and 4.0 hours, or single non-critical feed degraded.
- **Critical:** Any primary feed (e.g. EDR, Cloud Audit) failing or latency > 4.0 hours.

## 4. Remediation & Escalation Runbook
- If feed failed due to expired credentials (e.g. AWS S3 IAM Role, Azure Client Secret), notify platform owner to rotate secrets.
- If feed is healthy but latency is elevated, check upstream forwarder queues or BindPlane collectors.
