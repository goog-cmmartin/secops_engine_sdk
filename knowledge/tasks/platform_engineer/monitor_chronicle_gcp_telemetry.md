---
id: task.platform_engineer.monitor_chronicle_gcp_telemetry
title: "Monitor Chronicle GCP Logging and Metrics Telemetry"
type: task
persona: persona.platform_engineer
trigger:
  - scheduled_daily
  - on_demand
capabilities_used:
  - gcp_logging.search
  - gcp_monitoring.time_series
related_concepts:
  - concept.ingestion_pipeline_topology
related_features:
  - feature.gcp.cloud_logging
  - feature.gcp.cloud_monitoring
evaluation_rules:
  warning_ingestion_drop_pct: 20.0
  critical_api_error_pct: 5.0
---

# Monitor Chronicle GCP Logging and Metrics Telemetry

## 1. Intent & Context
Continuously evaluate Google Cloud Logging and Google Cloud Monitoring time series to detect Chronicle ingestion anomalies, normalizer stalls, API consumption spikes, forwarder errors, and administrative audit events across the Google Cloud project.

## 2. Preconditions & Required Context
- Google Cloud project ID for the Chronicle tenant.
- Service account or ADC with `roles/logging.viewer` and `roles/monitoring.viewer`.

## 3. Step-by-Step Execution Procedure

### Step 1: Query Chronicle Health Metrics
Invoke `gcp_monitoring.time_series` to retrieve recent telemetry:
- Ingestion metrics: `chronicle.googleapis.com/collector/ingestion/total_ingested_log_count`
- Normalizer metrics: `chronicle.googleapis.com/normalizer/throughput/total_record_count`
- API metrics: `serviceruntime.googleapis.com/api/request_count` for service `chronicle.googleapis.com`

### Step 2: Query Cloud Logging for Error Events
Invoke `gcp_logging.search` to inspect error logs over the same time window:
- Filter: `severity >= ERROR AND (resource.type = "chronicle.googleapis.com/..." OR logName : "cloudaudit.googleapis.com")`
- Extract error messages, failure codes, and impacted forwarder agents or users.

### Step 3: Correlate and Evaluate Findings
- Check whether ingestion drops align with forwarder error logs or network disconnections.
- Verify whether API request surges triggered HTTP 429 quota exhaustion.

## 4. Remediation & Escalation Runbook
- If forwarder error logs indicate TLS handshake failure, instruct the infrastructure team to renew certificates.
- If normalizer drops are detected, engage `@parser-doctor` to review CBN parser syntax.
- If API quotas are exceeded, alert the platform administrator to request a quota increase.
