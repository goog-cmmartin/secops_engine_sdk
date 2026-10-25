# Discovery: detection-rule reads (curated deployments, detection series, rule/environment join, pagination)

observed_at: 2026-10-10T13:37:00Z – 14:40:00Z
tenant: gus-sdl / instance 8cbac5ae (project number 288909297183, location us)
method: read-only GET / read-only POST (`dashboardQueries:execute`, `:verifyRuleText`,
        `:countAllCuratedRuleSetDetections`) through `GoogleSecOpsAdapter`, first with scratch probes,
        then through the shipped workflows with `tests/live_guard` installed (tenant writes blocked).
        No create/patch/delete/update/sync call was made.
input: probe report `gunsmith_sdk_probe.md` (2026-10-10 ~13:10–13:24Z, same tenant)
behavioural tests: `tests/test_detection_read_fixes.py` (no network),
                   `tests/test_detection_read_live.py` (SECOPS_LIVE_TESTS=1)

## 1. Bulk curated rule set deployments — VERIFIED

`GET /v1alpha/projects/{n}/locations/{loc}/instances/{id}/curatedRuleSetCategories/-/curatedRuleSets/-/curatedRuleSetDeployments`

| Param | Observed |
| :-- | :-- |
| `pageSize=1000` | 460 items, no `nextPageToken`, 1.2–2.9 s |
| `pageSize=100` | 100 items + `nextPageToken` (pagination works) |

Item keys: `name, precision, enabled, alerting` only. No display name.
`name` = `.../curatedRuleSetCategories/{category}/curatedRuleSets/{rule_set}/curatedRuleSetDeployments/{broad|precise}`.
Proto3 omits false booleans: a disabled deployment has neither `enabled` nor `alerting`.
Counts: 230 BROAD + 230 PRECISE; enabled+alerting 180, enabled non-alerting 189, disabled 91.
Joined with `curatedRuleSets` (1 page, 230 sets) for display names: 460/460 named.
Engine: `ListCuratedRuleSetDeploymentsWorkflow` / `engine.list_curated_rule_set_deployments()` (4.1 s with the name join).

## 2. Direct Curated Rule Set GET — VERIFIED

`GET .../curatedRuleSetCategories/-/curatedRuleSets/{rule_set_id}` works with the `-` category wildcard
(0.8–0.9 s). Keys: `authors, createTime, description, displayName, logSources, name, quota, tactics,
techniques, updateTime`. `get_curated_ruleset` now uses it for IDs/resource names instead of listing
the catalog; a 400/404 falls back to title resolution.

## 3. `curatedRules` has no filter — VERIFIED (limitation)

`GET .../curatedRules?filter=...` → `400 Invalid JSON payload received. Unknown name "filter"` (tried
`curated_rule_set="..."` and `curatedRuleSet="..."`). `pageSize=100` took 19.1 s and returned a
`nextPageToken`. Member-rule lookup for one rule set therefore still needs the full catalog;
`get_curated_ruleset(..., include_rules=False)` skips it.

## 4. Bucketed per-rule detection counts — VERIFIED

```
$rule_id = detection.detection.rule_id
$rule_name = detection.detection.rule_name
$bucket = timestamp.get_timestamp(detection.detection_time.seconds, "%Y-%m-%dT%H")   # or "%Y-%m-%d"
match: $rule_id, $rule_name, $bucket
outcome: $count = count_distinct(detection.id)
order: $bucket desc
limit: 10000
```
Relative window `{"timeUnit": "HOUR", "startTimeVal": "24"}` is accepted.
Columns: `rule_id, rule_name, bucket, count`; bucket strings `2026-10-09T13` / `2026-10-03` (UTC).

| Window | Rows | Rules | Detections | Time |
| :-- | --: | --: | --: | --: |
| 24 h, hour | 250–257 | 173 (9 `ru_`) | 1,209–1,232 | 4.0–9.1 s |
| 168 h, day | ~1,594 | 272 | 5,131 | 2.9–7.0 s |

Empty buckets produce no row. Engine: `QueryRuleDetectionSeriesWorkflow` /
`engine.get_rule_detection_series(lookback_hours, bucket, rule_ids)`.

## 5. Rule → SOAR environment join — VERIFIED

```
$rule_id = case.alerts.metadata.detection.rule_id
$rule_name = case.alerts.metadata.detection.rule_name
$env = case.environment
match: $rule_id, $rule_name, $env
outcome: $cases = count_distinct(case.name)
order: $cases desc
limit: 5000
```
30 days: 128–132 pairs (Demoverse 119–120, S1 5, Default Environment 3–4, MDE 1), 2.1–14.4 s
(the faster value is a dashboard cache hit). No regex filter is used (`rule_id = /^ru_/` took 112 s).
Engine: `QueryRuleCaseEnvironmentsWorkflow` / `engine.get_rule_case_environments(lookback_days)`.

Whether `case.environment` is the environment at case creation or after a move: UNKNOWN.

## 6. SOAR numeric case ID in the case dashboard schema — VERIFIED

`case` fields (from the compiler error listing valid fields): `name, display_name, stage, priority, status,
response_platform_info, environment, assignee, important, incident, create_time, update_time,
closure_details, tags, tasks, wall_activities, alerts, overflow_case, type, source, description, score,
creator_user, last_modifying_user, custom_fields`. `case.alerts` has `metadata, entities`.
`case.response_platform_info` has `response_platform_type, response_platform_id`.
`response_platform_id` holds the SOAR case number (e.g. `19950`, `20036`) with
`response_platform_type = RESPONSE_PLATFORM_TYPE_SIEMPLIFY`; `case.name` is a UUID.
`case.id`, `case.case_id`, `case.soar_case_id`, `case.external_id`, `case.ticket_id`, `case.legacy_id`,
`case.soar_id` do not exist. `cross_reference_rule_cases` now returns `environment` and `soar_case_id`
(11.9 s for 3 cases over 30 d with an environment filter).

## 7. Pagination of existing lists — VERIFIED

| List | Default page | Items (all pages) | Pages | Time |
| :-- | --: | --: | --: | --: |
| `rules` (pageSize 100) | 100 | 202 | 3 | 4.5 s |
| `rules/-/deployments` (1000) | 1000 | 202 | 1 | 0.8 s |
| `ruleExecutionErrors` (1000) | 100 | 2,713 | 3 | 2.8 s |
| `ruleExecutionErrors`, client-side `timeRange.endTime >= now-7d` | — | 2 | 3 | 2.6 s |
| `curatedRuleSets` (1000) | 1000 | 230 | 1 | 2.3 s |
| `findingsRefinements` | 100 | 0 | 1 | 0.8 s |

`ruleExecutionErrors` has no time filter; `timeRange.endTime` has nanosecond precision.
Deployment `runFrequency` is present on all 202 deployments (LIVE 143, HOURLY 57, HOURLY_CUSTOMIZABLE 2).
Rule severity after upper-casing: LOW 71, MEDIUM 62, HIGH 48, CRITICAL 13, INFO 6, none 2 (→ `UNKNOWN`).
`rules:listRevisions` returns the revision only in `name` (`...@v_1789547880_848831000`); the
`v_<seconds>_<nanos>` suffix maps to `2026-09-16T08:38:00.848831Z`.

## 8. `verifyRuleText` quota — OBSERVED

Compiling all 200 active rules with 8 concurrent workers: 192 compiled, 8 returned
`429 You have reached the maximum allowed quota for this operation` after the adapter's 5 retries.
The decay audit records these in `check_errors` / `compile_check_error` and does not flag them
`BROKEN_COMPILATION`. The default concurrency is now 4. The exact per-minute quota is UNKNOWN.

## 9. UDM field population query — fixed and re-verified

The population query used `$e.`-prefixed fields with an `events:` section after `match:`; the
dashboard compiler rejects it (`parser error: mismatched input 'events' expecting <EOF>`) for every
field. Before this change the check never ran (rule text was read from the wrong key), so the error
was invisible. Corrected statement form (VERIFIED live, 6–16 s per field over 30 d):

```
$field_val = $e.principal.hostname
$e.principal.hostname != ""            # arrays: $e.principal.ip = /.+/
$e.metadata.product_name = "..."        # optional vendor scope
match:
    $field_val
outcome:
    $count = count_distinct($e.metadata.id)
limit:
    10
```
One rule (`ru_d4ba83dc…`, 10 fields): 85 s; 7 fields populated, 0 unpopulated, 3 recorded as check
errors because the `!= ""` predicate does not type-check for non-string fields
(`metadata.event_timestamp.seconds` int, `metadata.event_type` enum, `metadata.id` bytes).
Population checks for non-string fields are therefore UNKNOWN (reported, never UNPOPULATED).
Tenant-wide population checks cost roughly (distinct fields × ~10 s) / workers; not run tenant-wide.

## 10. Post-fix audit results (same tenant, 2026-10-10 ~14:36Z)

`audit_rule_health()` 42.7 s: 432 findings (202 custom + 230 curated rule sets).
Custom: DISABLED 121, HEALTHY 43, EXECUTION_ERROR 36 (lifetime errors), HIGH_LATENCY 2.
With `error_lookback_days=7`: EXECUTION_ERROR 1, MISCONFIGURED_ALERTING 4, HEALTHY 73.
Curated: HEALTHY 185, DISABLED 45 (rule sets with every precision disabled).
`total_detections_24h=1213` across 173 firing rules; all four telemetry sources available.

`audit_rule_decay(lookback_days=30, check_population=False)` 61.2 s: 200 audited (2 archived skipped),
81 live, SILENT 71 (all live), STALE 48, BROKEN 0, compile-checked 192 (8 quota errors recorded),
no resource-path names.
