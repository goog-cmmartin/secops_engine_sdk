---
id: task.platform_engineer.check_udm_search_performance
title: Check UDM Search Performance and Error Rates
type: task
persona: persona.platform_engineer
trigger:
- scheduled_weekly
- on_demand
capabilities_used:
- dashboard.execute_query
- search.udm.stats
related_concepts:
- concept.udm_search_lifecycle
related_features:
- feature.siem.native_dashboards
evaluation_rules:
  warning_latency_p95_ms: 15000
  critical_failure_rate_pct: 5.0
status: stable
description: Check UDM Search Performance and Error Rates (task reference in Google
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

# Check UDM Search Performance and Error Rates

## 1. Intent & Context
Assess the operational responsiveness and reliability of interactive UDM search across the tenant. Detect whether query latency has degraded, timeouts are spiking, or users are issuing unindexed scans that impact tenant performance.

## 2. Preconditions & Required Context
- Tenant must be onboarded with SecOps API credentials (ADC or Service Account).
- Health Hub or Native Dashboard query capability must be accessible.

## 3. Step-by-Step Execution Procedure

### Step 1: Query Search Performance Metrics
Invoke `dashboard.execute_query` targeting the Health Hub dashboard:
- Query: Retrieve search count, median latency (`p50`), 95th percentile latency (`p95`), and total failed queries over the last 7 days.

### Step 2: Correlate with Ingestion Stats
Invoke `search.udm.stats` to check if event volume shifts coincide with query performance degradation.

### Step 3: Evaluate Health Against Thresholds
- **Healthy:** Failure rate < 1.0% and p95 latency < 15,000 ms.
- **Warning:** p95 latency >= 15,000 ms or failure rate between 1.0% and 5.0%.
- **Critical:** Failure rate >= 5.0% or continuous query timeouts.

## 4. Remediation & Escalation Runbook
- If high failure rate is caused by unindexed scans, identify the originating user accounts or automation scripts and provide query optimization guidance.
- If high failure rate is due to backend quota limits, file an operational escalation to adjust Google SecOps API quota allocations.
