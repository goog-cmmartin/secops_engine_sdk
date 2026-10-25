# Discovery: ingestion health (feed states, Health Hub telemetry, timestamp-integrity persistence)

observed_at: 2026-10-09T22:50:00+00:00 (first probe 05:57Z, re-probed 22:15-22:52Z)
method: read-only GET/POST(query) probes against the live tenant via `GoogleSecOpsAdapter`
        (scratch scripts), then the shipped workflows. No writes were made.
status: see per-section statuses below (AGENTS.md section 2 taxonomy)
behavioural tests: `tests/test_ingestion_health_fixes.py` (no network)

## 1. Feed state enum

Source: public REST reference, `projects.locations.instances.feeds` (v1alpha),
type `Feed.State`. It documents only the names; there are no per-value descriptions.

| State | Documented | Seen on tenant | Classification (`FeedHealthStatus`) | Status |
| :-- | :-- | :-- | :-- | :-- |
| `STATE_UNSPECIFIED` | yes | no | `UNKNOWN` | VERIFIED (doc), UNKNOWN (live) |
| `ACTIVE` | yes | 2 feeds (push: Pub/Sub, webhook) | operational, then telemetry checks | VERIFIED |
| `INACTIVE` | yes | 5 feeds | `INACTIVE` (new) | VERIFIED |
| `RUNNING` | yes | no | operational, then telemetry checks | UNKNOWN (live) |
| `SUCCEEDED` | yes | 1 feed (GCS v2 pull; `lastFeedInitiationTime` set) | operational, then telemetry checks | VERIFIED |
| `FAILED` | yes | no | `FAILED` (+ `failureMsg` / `failureDetails.errorCause` / `errorAction`) | VERIFIED (doc), UNKNOWN (live) |
| `ERROR`, `DISABLED` | **no** | no | kept as defensive aliases of `FAILED` / `INACTIVE` | UNKNOWN |
| anything else | no | no | `UNKNOWN` | n/a |

How we know INACTIVE means "disabled": Health Hub chart "Health Status by Data Source"
returns 2 of the 5 INACTIVE feeds (`914088f1…`, `d6f6d9fd…`) with `status=Critical`,
`latest_error_code=Disabled_feed`, `latest_issue_desc="Feed Config Info: Feed is disabled."`.
The other 3 INACTIVE feeds have no row in that chart (it uses a 24h window).
**Choice:** INACTIVE is its own status. It is neither HEALTHY (no collection happens)
nor FAILED (disabling is an operator decision, not a fault), and `FeedHealthReport.inactive_count`
counts it. Before this change, all 5 INACTIVE feeds came back HEALTHY ("Feed is operating normally").
`RUNNING` and `SUCCEEDED` are treated as operational because the doc lists them next to
ACTIVE as run states and the SUCCEEDED feed on this tenant is healthy in Health Hub.
How RUNNING behaves under load is UNKNOWN.

Raw feed keys on this tenant: `details, displayName, name, referenceId, state, uid`
(+ `lastFeedInitiationTime` on the pull feed). `details.logType` is a full resource
name (`projects/.../logTypes/CS_EDR`); `_normalize_feed_summary` strips it to the short name.

## 2. Health Hub availability and why audit_feed_health telemetry was empty

- Health Hub `1b0cb92f-c162-424a-9d31-05b35180c8a5`: **exists** (`type=CURATED`,
  13 charts). Data Health Deep Dive `5cf5988b-951f-4e54-830d-330ef5ad438a`: **exists**
  (`CURATED`, 26 charts incl. markdown tiles). Every chart query executed without error. Status: VERIFIED.
- **Root cause of "all HEALTHY, 0 latency":** the old code queried the wrong charts and read the wrong columns:
  - `Failed Sources` and `Irregular Data Sources` are KPI tiles that return a single row,
    `{"total_count": 2}`. They have no feed/log-type key, so every row was dropped.
  - `Latency Status By Source` has rows keyed by `feed_id`, or by `collector_id` for
    forwarder/API sources. The latency value is in `event_ingestion_latency_p95` (e.g.
    `"18 min 8 sec"`, `"5 hr 10 min"`, `"No data recorded"`), but the code looked for
    `latency` / `event_ingestion_latency`, which this chart does not have. So latency was always None.
  - Per-feed status lives in `Health Status by Data Source` (columns `feed_id`, `status`
    Healthy/Warning/Critical, `original_status`, `latest_error_code`, `latest_issue_desc`,
    `last_ingestion_time`, …). The old code never queried it.
  - All of this was hidden because every failure path was `except Exception: continue/pass`.
- Fix: the feed audit queries `Health Status by Data Source` and `Latency Status By Source`
  only, keyed by `feed_id`. Rows with only a `collector_id` are not feeds and are skipped.
  `Critical` raises a FAILED signal and `Warning` raises an IRREGULAR signal. The 2 Critical
  rows match the `Failed Sources` KPI value of 2 (status: OBSERVED_NOT_MAPPED, because the
  dashboard's own definition of "failed" is not documented).
- Deep Dive `Ingestion - Events by Status` returns 1 row (`log_type=UDM`) whose saved
  query has a fixed time window (`2025-11-27T00:00Z`–`11:59Z`), so volume funnels are
  empty for feed log types. This is a property of the curated query, not an SDK bug. Status: OBSERVED_NOT_MAPPED.
- How errors are reported now: `FeedHealthReport` / `ParserHealthReport` carry
  `health_hub_available`, `deep_dive_available`, `telemetry_errors: list[str]`
  (dashboard unavailable / expected chart missing / chart query failed / unexpected row
  schema), and a `telemetry_available` property. `FeedHealthFinding` adds
  `health_hub_status` and `telemetry_observed`. A HEALTHY finding now says whether
  Health Hub corroborated it ("Health Hub status: Healthy") or whether the result rests on state
  alone. Failures are logged at WARNING and never abort the audit.

Post-fix live result (`audit_feed_health`): 3 HEALTHY (2 with Health Hub latency 26.91 s /
18 min 8 s; webhook feed has no Health Hub row and is labelled state-only), 5 INACTIVE,
`telemetry_errors=[]`.

## 3. Timestamp integrity persistence

- `SecOpsEngine()` wires **no** evidence store by default (`evidence_store=None`), and
  neither does the CLI (`SecOpsEngine()`) or `clients/web/server.py::_build_engine`.
  So `audit_timestamp_integrity` through the facade has never persisted in those
  entry points. It persists only when a caller passes `evidence_store=`. Status: VERIFIED (code).
- New: `execute(..., persist=True)` / `audit_timestamp_integrity(..., persist=True)` /
  CLI `--no-persist`. The default (True) keeps the existing behaviour. With `persist=False`, no
  `save_timestamp_integrity_report` call is made. The baseline is still read.
  The report records `persist_requested`, `persisted`, `persisted_snapshot_id`,
  `persistence_error` (also "No evidence store configured" when persist was requested
  without a store), `baseline_available`, `baseline_error`. These appear in
  `to_dict()["run_metadata"]` and are not part of the stored document.
- `get_latest_timestamp_integrity`: facade returns None without a store (no I/O).
  The Firestore implementation is a single document `get` (read-only). The
  `LocalFileEvidenceStore` implementation reads a JSON file, but its constructor and
  `_col_path` call `os.makedirs`, which creates directories as a side effect (no data is written).
- Stored baseline on this tenant: **none**. The facade returned None. There is no
  `.state/evidence_fabric/timestamp_integrity/` in the SDK or secops-town checkouts. The
  Firestore REST read of `timestamp_integrity/latest` returned 404 "The database (default)
  does not exist for project gus-sdl".
- Live `persist=False` run (7d, 24 s): 40 log types, 23 healthy, 17 NEW anomalies,
  467 skewed events (WINEVTLOG 343, INFOBLOX_DHCP 96, NIX_SYSTEM 28), 956,895 events
  delayed >2h. Top average delay: SENTINEL_EDR 2954.6 min, FIREEYE_HX 2904.2,
  MICROSOFT_DEFENDER_ENDPOINT 2902.6, WINDOWS_DEFENDER_ATP 2898.5, LIMACHARLIE_EDR 1370.4,
  WINDOWS_DHCP 438.8, CS_EDR 323.0 (2,301/2,552 events >2h).

## 4. Pareto earliest/latest_event were null

Root cause (VERIFIED): GoogleSQL `DATE(...)` columns come back from
`dashboardQueries:execute` as `{"metadata": {}, "dateVal": {"year": 2026, "month": 10, "day": 7}}`.
`_parse_dashboard_result._extract_dashboard_val` had no `dateVal` branch and returned
None. It now decodes them to ISO `YYYY-MM-DD`. Post-fix: `BRO_JSON 20,980,420 events, 2026-10-08 → 2026-10-09`.
The same fix applies to `get_entity_graph_lineage` `first_seen`/`last_seen` (also `DATE`).

## 5. Cloud Monitoring (gcp_monitoring.time_series)

`metricDescriptors` with prefix `chronicle.googleapis.com/` lists 42 descriptors on project
`gus-sdl`, including `ingestion/log/bytes_count`, `ingestion/log/record_count` (labels `namespace`,
`ingestion_source`), `ingestion/log/quota_rejected_bytes_count`, `ingestion/quota_limit`,
`normalizer/log/record_count` (`state`, `drop_reason`, …), `normalizer/event/record_count`,
`outofband/log/{bytes,record}_count` and `https_push/*` / `azure_event_hub/*` (`feed_name`),
`*/is_unhealthy` gauges, `forwarder/*`, `agent/*`, `log_processing_pipeline/*`.
- `ingestion/log/bytes_count`, `ingestion/log/record_count`, `normalizer/log/record_count`
  return data (resource type `chronicle.googleapis.com/Collector`; resource labels
  `log_type`, `collector_id`, `project_id`, `location`). Raw granularity is **1-minute** DELTA points.
  With `alignmentPeriod=3600s` + `ALIGN_SUM` you get hourly points (24 per 24h).
  Calls take 0.2–2.4 s. `quota_rejected_bytes_count` returned 0 series (no rejections in 24h).
- `log_type` is a **resource** label. Group by `resource.label.log_type` (28 series per
  24h page). `metric.label.log_type` does not exist and collapses everything into 1 series.
- Fixed in this branch: `get_chronicle_ingestion_metrics` used to build
  `metric.type = starts_with("chronicle.googleapis.com/")`, which the API rejects with
  `400 The provided filter matches more than one metric`, and it filtered on
  `metric.label.log_type`. The legacy workflow method `query_chronicle_ingestion_metrics`
  is unchanged because `tests/test_gcp_monitoring_workflow.py` pins its filter. The facade now calls
  `GcpMonitoringQueryWorkflow.query_chronicle_ingestion_series`.

### Verified call (2026-10-09T23:02Z, project `gus-sdl`). Status: VERIFIED
```
GET https://monitoring.googleapis.com/v3/projects/gus-sdl/timeSeries
  filter = metric.type = "chronicle.googleapis.com/ingestion/log/record_count"
           AND resource.type = "chronicle.googleapis.com/Collector"
           [AND resource.label.log_type = "X" | one_of("X", "Y")]
  interval.startTime / interval.endTime = now-24h / now
  aggregation.alignmentPeriod = 3600s, perSeriesAligner = ALIGN_SUM,
  aggregation.crossSeriesReducer = REDUCE_SUM, groupByFields = resource.label.log_type
  pageSize = 1000 (follow nextPageToken)
```
- 1 page, 1.5 s, 41 log types. Up to 24 hourly points per log type. Log types with gaps return fewer
  (SENTINELONE_CF: 10). Points arrive newest-first; the SDK sorts them ascending.
- Top 5 by 24h records: BRO_JSON 23,777,834; WINEVTLOG 1,675,240; SENTINELONE_CF 1,265,002;
  SQUID_WEBPROXY 612,256; NIX_SYSTEM 152,016.
- `ingestion/log/bytes_count` (0.8 s) and `normalizer/log/record_count` (0.5 s) work the same way.
  Ungrouped (`REDUCE_SUM`, no groupBy) returns 1 series: 27,604,999 records in 24h (0.36 s).
- With `pageSize=100` the same grouped query returned a `nextPageToken` after 28 series,
  so pagination must be followed.

## 6. Status incidents (gcp_status.incidents.query)

`query_cloud_status_incidents(service_name="Google SecOps", lookback_days=30)`: 0.04 s,
18 incidents. Each item has `id, number, begin, end, created, modified, external_desc,
status_impact, severity, service_key, service_name, affected_products,
currently_affected_locations, previously_affected_locations, updates[], most_recent_update,
uri, is_active, public_url`. Latest: 2026-10-06 "delayed UDM Search and detections in the US
region" (SERVICE_DISRUPTION, resolved).

## 7. Timing (audit_feed_health / audit_parser_health)

All wall time is HTTP. Client-side processing is under 0.2 s.

| Run | Total | feeds/parsers list | dashboard GET + batchGet | dashboardQueries:execute |
| :-- | --: | --: | --: | --: |
| feed, before (8 queries) | 24.9 s | 3.0 s | 7.9 s | 13.9 s |
| feed, after (7 queries) | 43.1 s | 2.2 s | 9.2 s | 31.7 s (funnel query 14.2 s, status 7.9 s) |
| parser, before (9 queries) | 27.8 s | 2.9 s | 8.8 s | 16.0 s |
| parser, after (7 queries) | 27.7 s | 3.2 s | 9.3 s | 15.1 s |

The reported 68.7 s run and the 43 s run come from backend variance: the same named query
took between 2.8 s and 14.2 s across runs. The change drops the scalar KPI queries
(feed −2 / +1 per-feed status chart; parser −2). The remaining cost is sequential:
2 dashboard GETs, 2 batchGets, and 7 query executions. The large wins would be running
chart queries concurrently and caching the dashboard definitions (chart→query ids are
static for CURATED dashboards). Neither is done here. Both need a thread-safety review of `_request`.
