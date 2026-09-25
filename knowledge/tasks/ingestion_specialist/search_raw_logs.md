---
id: task.ingestion_specialist.search_raw_logs
title: Search Raw Logs and Diagnose Unparsed Telemetry
type: task
persona: persona.ingestion_specialist
trigger:
- on_demand
- unparsed_log_spike
capabilities_used:
- log.raw_logs.search
- log.query.validate_query
- log.product_sources.stats
- event.investigate
- parser.diagnose_unparsed
related_concepts:
- concept.ingestion_pipeline_topology
- concept.udm_search_lifecycle
related_features:
- feature.siem.parser_lifecycle
- feature.siem.feed_management
evaluation_rules:
  max_acceptable_unparsed_ratio: 0.05
  syntax_validation_required: true
status: stable
description: Search unparsed and unnormalized Chronicle raw logs, validate query syntax, discover product sources, and isolate parser drop root causes.
generated:
  by: raw-log-agent/gemini-3.8-flash
  at: '2026-09-22T20:00:00Z'
verified:
- by: human:secops-architect
  at: '2026-09-22T20:05:00Z'
stale_after: '2027-01-01T00:00:00Z'
sources:
- id: chronicle-raw-log-docs
  resource: https://cloud.google.com/chronicle/docs/investigation/raw-log-search
  title: Google SecOps Raw Log Search Documentation
---

# Search Raw Logs and Diagnose Unparsed Telemetry

## 1. Intent & Context
Enable ingestion specialists and SOC operators to search unparsed, unnormalized, or raw log telemetry across Google SecOps Chronicle instances, validate query syntax against the Chronicle query compiler, discover product source telemetry, and inspect verbatim raw log records.

## 2. Preconditions & Required Context
- Google SecOps instance initialized with active ingestion feeds or Cloud Logging forwarders.
- Authorized credentials with `chronicle.logs.get` or `chronicle.legacyFindRawLogs` permissions.

## 3. Step-by-Step Execution Procedure

### Step 1: Discover Active Ingestion Sources and Volumes
Invoke SDK capability `log.product_sources.stats`:
- Queries product log source statistics across the specified lookback window.
- Identifies active log types (e.g., `GCP_CLOUDAUDIT`, `WINEVTLOG`, `CS_EDR`) and total byte volumes to choose appropriate search filters.

### Step 2: Validate Raw Log Query Syntax
Invoke SDK capability `log.query.validate_query`:
- Evaluates the query expression against the Chronicle query compiler dialect (`DIALECT_UDM_SEARCH`).
- Validates field predicates, regular expressions (e.g. `raw = /.*auth fail.*/`), and parse flags (`parsed = false`).
- If validation fails, halt execution, parse diagnostic errors, and refine query syntax before submitting heavy search workloads.

### Step 3: Execute Filtered Raw Log Search
Invoke SDK capability `log.raw_logs.search`:
- Submits the validated query with bounded time parameters (`lookback_hours` or explicit RFC 3339 timestamps).
- Honors Invariant #9 (Bounded Autonomy Guardrails) requiring query filters for unbounded search operations.
- Collects matched raw log snippets, log types, and ingestion timestamps.

### Step 4: Investigate Specific Events or Unparsed Drops
For problematic records or parsing anomalies:
- Invoke `event.investigate` to retrieve enriched UDM fields alongside the verbatim raw payload.
- Invoke `parser.diagnose_unparsed` to diagnose specific parsing drop reasons, syntax discrepancies, or missing schema fields.

## 4. Remediation & Parser Normalization Runbook
- **Malformed Upstream Payload:** If the raw log contains truncated JSON or corrupt timestamps, notify the data source administrator or configure upstream transformation in BindPlane / Logstash.
- **Missing Parser Extraction:** If raw logs arrive successfully but fail normalization (`parsed = false`), author a CBN parser extension or submit an optimization proposal via `@parser-doctor`.
