---
id: feature.gcp.cloud_monitoring
title: "Google Cloud Monitoring Time Series & Chronicle Telemetry"
type: feature
platform: gcp
sdk_capabilities:
  - gcp_monitoring.time_series
mcp_tools:
  - query_gcp_cloud_metrics
related_concepts:
  - concept.ingestion_pipeline_topology
---

# Google Cloud Monitoring Time Series & Chronicle Telemetry

## 1. Feature Purpose & Scope
Provides operational metrics and time series query capabilities across Google Cloud Monitoring (`monitoring.googleapis.com/v3/projects/{project_id}/timeSeries`) to track Chronicle SIEM ingestion volume, normalizer throughput, API request consumption, and forwarder agent performance.

## 2. Underlying APIs & SDK Primitives
- **Query Time Series:** `gcp_monitoring.time_series` (`GET v3/projects/{project_id}/timeSeries`)
  - Supported metric domains:
    - Collector ingestion: `chronicle.googleapis.com/collector/ingestion/total_ingested_log_count`, `total_ingested_log_size`
    - Normalizer throughput: `chronicle.googleapis.com/normalizer/throughput/total_record_count`, `total_event_count`
    - Service API usage: `serviceruntime.googleapis.com/api/request_count` filtered by `resource.label.service = "chronicle.googleapis.com"`
    - Agent health: `chronicle.googleapis.com/agent/cpu_seconds`, `chronicle.googleapis.com/agent/exporter_queue_size`

## 3. Input Parameters & Constraints
- **Filter Expression:** Metric type filter (e.g. `metric.type = starts_with("chronicle.googleapis.com/")`).
- **Interval:** RFC3339 start and end timestamps or dynamic lookback window (`hours`).
- **Aggregation:** Alignment period (e.g. `3600s`), per-series aligner (`ALIGN_SUM`, `ALIGN_RATE`), and cross-series reducers.
- **Cardinality:** Bounded time series query.

## 4. Telemetry & Observable Health Indicators
- Sudden drops in ingestion count or volume indicating forwarder disconnections.
- Normalizer event count anomalies diverging from raw ingested record counts.
- High error rates on API request counts indicating quota limits or authentication timeouts.
