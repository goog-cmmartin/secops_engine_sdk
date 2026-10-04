---
id: feature.gcp.cloud_logging
title: Google Cloud Logging Audit & SecOps Diagnostic Trails
type: feature
platform: gcp
sdk_capabilities:
- gcp_logging.search
mcp_tools:
- query_gcp_cloud_logging
related_concepts:
- concept.ingestion_pipeline_topology
status: stable
description: Google Cloud Logging Audit & SecOps Diagnostic Trails (feature reference
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

# Google Cloud Logging Audit & SecOps Diagnostic Trails

## 1. Feature Purpose & Scope
Provides unified querying and search across Google Cloud Logging (`logging.googleapis.com/v2/entries:list`) for Chronicle SIEM & SOAR audit trails, forwarder error logs, API error diagnostics, and administrative operations.

## 2. Underlying APIs & SDK Primitives
- **Query Cloud Logging Entries:** `gcp_logging.search` (`POST v2/entries:list`)
  - Target projects: Chronicle tenant Google Cloud project.
  - Filters: Supports Cloud Logging Advanced Filter syntax (e.g. `severity >= ERROR`, `resource.type = "chronicle.googleapis.com/..."`, `logName : "cloudaudit.googleapis.com"`).
  - Normalization: Extends `UniversalBatchMixin` returning normalized `GcpLogEntry` objects.

## 3. Input Parameters & Constraints
- **Filter Expression:** String filter defining resource types, timestamps, severity, and text/proto payloads.
- **Order:** Defaults to descending timestamp order (`timestamp desc`).
- **Cardinality:** Bounded collection query with explicit page sizes.

## 4. Telemetry & Observable Health Indicators
- Detect high-severity errors from Chronicle forwarder agents (`chronicle.googleapis.com/agent`).
- Monitor API authorization failures and permission denied errors (`Code 7 / 403`).
- Track administrative changes and role updates in Cloud Audit activity logs.
