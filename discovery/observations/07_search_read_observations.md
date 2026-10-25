# Discovery: UDM search reads (aggregate grid, totals/aggregates, chunk dedupe, validators, assist endpoints)

observed_at: 2026-10-10T16:30:00Z – 17:18:00Z
tenant: gus-sdl / instance 8cbac5ae (project number 288909297183, location us)
method: read-only GET / read-only POST (`dashboardQueries:execute`, `legacy:legacyFetchUdmSearchView`
        + `operations/{op}:streamSearch`, `:translateUdmQuery`, `:searchRawLogs`) through
        `GoogleSecOpsAdapter`, first with scratch probes, then through the shipped facade.
        No create/patch/delete/update call was made. No HTTP 429 was seen.
inputs: survey `search_sdk_probe.md` and review `udm_search_review.md` (same tenant, 2026-10-10 ~15:40Z)
behavioural tests: `tests/test_search_read_fixes.py` (no network),
                   `tests/test_search_read_live.py` (SECOPS_LIVE_TESTS=1)

## 1. `aggregate_udm` over dashboard SQL — VERIFIED

`POST .../dashboardQueries:execute` with `query.dialect = "SQL"` and `input.timeWindow`.
Generated query (GoogleSQL pipe syntax), e.g. log type x hour:

```
FROM events
|> AGGREGATE COUNT(1) AS agg_count GROUP BY metadata.log_type AS d0,
   TIMESTAMP_TRUNC(TIMESTAMP_SECONDS(metadata.event_timestamp.seconds), HOUR, 'UTC') AS bucket
|> ORDER BY bucket DESC, agg_count DESC
|> LIMIT 501
```

| Run (facade) | Time | Result |
| :-- | :-- | :-- |
| log_type x hour, 24 h, limit 500 | 6.1 s | 260 rows, truncated=False (25 hour buckets because the window is not hour-aligned; probe saw 224–244 earlier in the day) |
| log_type, 24 h, limit 3 | 2.8 s | 3 rows, truncated=True (limit+1 detection) |
| principal.hostname x metadata.event_type, filter `metadata.log_type = "WINEVTLOG" AND principal.hostname != ""`, 24 h, limit 50 | 7.0 s | 50 rows, truncated=True |
| total x day, 48 h | 3.4 s | buckets at 00:00Z |
| count_distinct(principal.hostname) by log_type, 24 h | 4.3 s | WINEVTLOG 123, SENTINELONE_CF 92, ... |

Facts established:
- `TIMESTAMP_TRUNC(..., DAY)` without a time zone buckets at **07:00Z** (tenant zone). With `'UTC'` buckets are at 00:00Z. The builder always passes `'UTC'`.
- `GROUP BY principal.ip` fails: `Grouping by expressions of type ARRAY is not allowed` (400). `LEFT JOIN UNNEST(principal.ip) AS _u0` works and puts events with an empty array in the NULL row; counts are per (event, value).
- `security_result.action` is repeated inside repeated `security_result`: `CAST(sr.action AS STRING)` fails (`Invalid cast from ARRAY<...Action>`); double `LEFT JOIN UNNEST(security_result) / UNNEST(_p.action)` works.
- Enum fields compare to string literals (`metadata.event_type = 'NETWORK_CONNECTION'`); an unknown name fails with `Could not cast literal "NOT_AN_ENUM" to type backstory.Metadata.EventType` (400). Enum values come back as names.
- Repeated filter: `'172.16.1.12' IN UNNEST(principal.ip)` works.
- Backslash literal: `principal.user.userid = 'NT AUTHORITY\\SYSTEM'` matches 80 496 events (escaping correct).
- Every allow-listed field was checked as GROUP BY and as `=` / `!=` filter over a fixed 1 h window 3 h in the past: the `=` count equals the grouped row count for the same value for all 14 fields. With `clear_cache=True`, `=` + `!=` equals the unfiltered total exactly (event_type: 958 518 + 1 418 979 = 2 377 497; principal.ip: 674 276 + 1 703 221 = 2 377 497). Without `clear_cache` the unfiltered total can come from the backend cache and lag late-arriving events (observed: 25 events).
- Allow-list (all VERIFIED): metadata.log_type, metadata.event_type (enum), metadata.product_name, metadata.vendor_name, metadata.product_event_type, principal.hostname, principal.ip (repeated), principal.user.userid, target.hostname, target.ip (repeated), target.user.userid, security_result.action (nested repeated enum), network.application_protocol (enum), network.ip_protocol (enum). String fields hold both `""` and NULL.
- Filter grammar and injection safety: see `engine/workflows/udm_aggregate.py`. Live attempts with `|>`, `'...'`, `;`, `--`, a `\'` escape, `raw =`, `/regex/` and an enum breakout were all rejected locally (`UdmFilterError`) before any request.

Fallback (not implemented): the search view with `userSql` returns the same grid as `stats.results` (3.5–6 s, LRO + index paging; `eventIndexStart` must be ≥ 1).

## 2. UDM search view: streamed chunks, totals and aggregates — VERIFIED

`legacyFetchUdmSearchView` (lean body: no `detectionOptions`, no `prevalence`, `generateAiOverview=false`) then
`GET operations/{op}:streamSearch?eventIndexStart=1&eventIndexEnd=100&pageRequest=false&paginationEnabled=true`.

- One stream call returned 3 chunks with 1, 100 and 100 events; the last has `done: true`. They are cumulative snapshots (a 1..100 range cannot hold 201 unique events). The old adapter concatenated them. Now only the final (`done`, else last non-empty) chunk is used, deduped by `metadata.id`: 100 received, 100 unique, `duplicates_dropped=101`.
- Final chunk keys: `baselineEventsCount=30000, filteredEventsCount=30000, availableResultCount=30000, tooManyEvents=true, timeline{sizeOfBucketMs:60000, buckets[61]}, activityTimeline{sizeOfBucketMs:3600000, buckets[2]}, fieldAggregations.fields[...]{fieldName, eventCount, valueCount, tooManyValues, topValues|allValues, bottomValues}, groupedFieldAggregations, detections, aiOverview`.
- Timeline buckets carry no timestamps and omit counts when empty. Placement: aligned to multiples of the bucket size since the epoch, starting at the bucket that contains the window start. Evidence: 61 one-minute buckets for a 1 h window starting at 16:06:xx; 2 hourly activity buckets (16:00, 17:00); 96 fifteen-minute buckets for a 24 h window starting at 17:15. A narrow search (2 events, 24 h) placed both events in exactly the non-zero timeline buckets.
- With `tooManyEvents`, the timeline sums to exactly 30 000 and field aggregations cover the first 30 000 matches: `aggregates_sampled=True`.
- Page 96–105 of a 100-event materialization returned 5 events, `done: true`, `complete: true`: paging stops at `maxReturnedEvents`, not at `availableResultCount`. `more_data_available` now also reflects server totals (capped or received < total_matched) so a capped search is `PARTIAL`.
- Default body (detections + prevalence) 1 h, limit 50: 50 unique events, 235 field aggregations, 5.1 s. Lean body: 5.2 s. `generateAiOverview` now defaults to False for `search_udm` (the SDK never parsed it).

## 3. Stats search duplication — VERIFIED fixed

`search_udm_stats` log_type x hour 24 h, `case_insensitive=False`, lean: 9.5 s, 261 rows, 261 unique, `total_results=261` (was 490 rows for 245 results). Values keep their case (`BRO_JSON`, not `bro_json`) now that `caseInsensitive` is honoured.

## 4. `:validateQuery` — VERIFIED

Compile errors are **HTTP 200** with `errorType`, `errorText`, `errorPosition{startLine,startColumn,endLine,endColumn}`:
- UDM `metadata.event_type = = "X` → `INVALID_QUERY_TYPE`, line 1, columns 25–26.
- Stats query with trailing `(` → line 3, columns 34–35.
- `DIALECT_DASHBOARD_SQL` with `metadata.log_typo` → errorText with "Did you mean log_type?" (no errorPosition).
So any HTTP error (network, auth, 429, 5xx) is a transport failure; validators now raise instead of returning `valid=False`. `BACKEND_ERROR_TYPE` raises `QueryValidationUnavailableError`.
Dialect enum (API reference): DIALECT_LEGACY, DIALECT_UDM_SEARCH, DIALECT_STATS, DIALECT_SQL, DIALECT_RULE_SQL, DIALECT_DASHBOARD_SQL.

## 5. Raw log validation dialect — VERIFIED (no change needed)

`raw = "sshd"` under DIALECT_UDM_SEARCH → `QUERY_TYPE_RAW_LOG_QUERY`. A bare `sshd` / `"sshd"` is rejected by validateQuery **and** by `:searchRawLogs` itself (`400 Request contains an invalid argument`); `raw = "sshd"` searches fine (14.6 s, 30 min). DIALECT_LEGACY rejects both forms. The survey's "wrong dialect" finding was a query-form issue.

## 6. IoC / summarizeEntity IP value type — VERIFIED

`FieldAndValue.ValueType` (API reference) has `ASSET_IP_ADDRESS` and `RESOLVED_IP_ADDRESS`, no `IP_ADDRESS`.
- `legacySearchEnterpriseWideIoCs` with `ASSET_IP_ADDRESS` for 172.16.6.110: 200 (`{}` over 30 days, 1 match over all time). `IP_ADDRESS` → 400 (survey).
- `summarizeEntity` with `fieldAndValue.valueType=ASSET_IP_ADDRESS`: 1 ASSET entity with `ip: [172.16.6.110]`.
- `RESOLVED_IP_ADDRESS` is also accepted and returned different matches; its exact semantics are UNKNOWN. The SDK maps IPs to `ASSET_IP_ADDRESS`.
- IoC default start: the code always sent the epoch while the comment said 30 days. Kept the epoch (all-time returned matches; 30 days did not) and added `lookback_days`.

## 7. `:findUdmFieldValues` and `:translateUdmQuery` — VERIFIED

- `GET :findUdmFieldValues?query=NETWORK_CONN&pageSize=5` → 1.3 s, `valueMatches[{fieldPath, value, ingestionTime, matchStart?, matchEnd}]`, `fieldMatchRegex`, `nextPageToken`, `hasMoreMatches`. Matches any UDM field (labels, product_event_type, ...).
- `POST :translateUdmQuery {text}` → 3.4–4.2 s, `{query, timeRange?}`. "failed logins for user alice in the last 24 hours" → `metadata.event_type = "USER_LOGIN" AND security_result.action = "FAIL" AND target.user.userid = "alice"` with a 24 h range. Nonsense text still yields a query (`principal.hostname = "asdf" OR ...`) and no time range.
- Gemini quota / per-user limits for translateUdmQuery: UNKNOWN (not in the API reference, no quota header or error observed).

## 8. Retry visibility

`_request` still retries 429/502/503/504 and network errors up to 5 attempts with the same backoff. Each retry is now logged at WARNING and recorded (`adapter.retry_log`, `retry_marker()` / `retries_since()`); `SearchSession.api_retries` and `UdmAggregateResult.api_retries` carry the retries for that call. None occurred during these probes.

## UNKNOWN

- Maximum rows / maximum window accepted by `dashboardQueries:execute` (2000 rows + 168 h are SDK bounds, not server limits).
- Per-tenant QPS limits for search and dashboard endpoints.
- `RESOLVED_IP_ADDRESS` vs `ASSET_IP_ADDRESS` semantics for enterprise IoC search.
- translateUdmQuery quota/cost.
