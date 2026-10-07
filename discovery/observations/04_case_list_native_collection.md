# Discovery: native cases collection listing (`case.list`)

observed_at: 2026-10-07T05:40:00+00:00
method: read-only GET probes against the live tenant via `GoogleSecOpsAdapter._request`
        (scratch probe scripts, ~70 calls), then the shipped workflow
status: VERIFIED (behavioural test: `tests/test_case_list.py`)
scope: what the server accepted or rejected; nothing below is inferred

## Why
`case.search` (`legacySearches:legacyCaseSearchEverything`) has no open/closed
status filter and is bounded by a time window, so long-lived open cases never
show up in it. The native collection filters on exact status with no time window.
Example from this tenant: 2,774 open cases in environment "Demoverse" via the
native collection, versus 975 open within the last 30 days via legacy search.

## Endpoint
```
GET /v1alpha/projects/{project_id}/locations/{location}/instances/{customer_id}/cases
    ?pageSize=<1..1000>&filter=<expr>&orderBy=<expr>&pageToken=<token>
```
Response: `{"cases": [...], "nextPageToken": "...", "totalSize": <int>}`.
- `nextPageToken` is absent on the last page.
- **Zero matches return an empty body** (`{}`): no `cases`, no `totalSize` key.
- `totalSize` is the count for the whole filter, not for the page.

## Case item payload (all keys observed)
| Key | Example / type | Notes |
| :-- | :-- | :-- |
| `name` | `projects/.../instances/.../cases/20999` | case id = last segment |
| `displayName` | string | title |
| `createTime`, `updateTime` | `"1791328366962"` | epoch **millis as string** |
| `priority` | `PRIORITY_CRITICAL/HIGH/MEDIUM/LOW/INFO` | |
| `status` | `OPENED` / `CLOSED` | |
| `stage` | `Triage`, `Investigation`, ... | free text |
| `environment` | `Demoverse`, `Default Environment` | top-level string |
| `assignee` | `@Tier1` | role or user |
| `alertCount` | int | |
| `important`, `incident` | bool | |
| `description` | string | optional (absent on many items) |
| `type` | `EXTERNAL` | |
| `workflowStatus` | `PENDING_FOR_USER`, `COMPLETED` | |
| `source` | `Server`, `AlertMove` | |
| `lastModifyingUserId` | `Siemplify automation` | |
| `involvedSuspiciousEntity`, `overflowCase` | bool | |
| `moveEnvironment` | `{}` | |
| `dataAccessScopes` | list of strings | optional |

There is no `closeTime` field in list items (UNKNOWN whether the single-case GET
has one; not probed).

## Paging
- Max `pageSize` = **1000**. `pageSize=5000` -> HTTP 400 "The limit of '1000' for
  Top query has been exceeded". Omitting `pageSize` -> 50 per page.
- `pageToken` pagination: consecutive pages do not overlap. Full listing of
  `status="OPENED" AND environment="Demoverse"` at pageSize=1000 returned 3 pages,
  2,774 cases, 2,774 unique, equal to `totalSize`.
- A follow-up page may use a **different `pageSize`** than the first (verified:
  page 1 size 5 -> page 2 size 10 continued exactly after page 1).
- The token is bound to the filter: re-using it without the filter -> HTTP 400
  "You can only perform actions on the table if you are on Page 1".
- Garbage token -> HTTP 400 "Page token is not a valid base64".
- Token is returned with percent-escapes already in it (e.g. `%2F`); passing it
  back verbatim through `urlencode` works.
- Timing: listing all 2,774 Demoverse open cases took **9.8 s** (3 pages, ~3-3.5 s
  each at pageSize=1000). Small pages take 0.5-1 s.

## Filter grammar (OData-style; server type is `CaseQueryOptionsDto`)
| Expression | Result |
| :-- | :-- |
| `status="OPENED"` | OK (9,847) |
| `status="CLOSED"` | OK (534); OPENED + CLOSED = unfiltered total (10,381) |
| `status=OPENED` (unquoted) | 400 "Could not find a property named 'OPENED'" |
| `status="OPEN"` / `"CLOSE"` / `"UNKNOWN"` / `"STATUS_UNSPECIFIED"` | 400 "not a valid enumeration type constant" |
| `status!="CLOSED"` | OK (9,847) |
| `status='OPENED'` (single quotes) | OK |
| `... AND ...` / `... and ...` | OK (keyword is case-insensitive) |
| `priority="PRIORITY_CRITICAL"` (also HIGH/MEDIUM/LOW/INFO) | OK |
| `priority="CRITICAL"` | 400 enumeration constant |
| `a="x" OR a="y"` | OK |
| `status="OPENED" AND (priority="A" OR priority="B")` | OK (5,206 = 3,587 + 1,619). One earlier identical call returned 500, then 3 retries returned 200 (transient). |
| `status="OPENED" AND (environment="A" OR environment="B" OR environment="C")` | OK |
| DNF `s AND p1 OR s AND p2` | OK, same count as the parenthesised form |
| `priority in (...)` | 400 enumeration constant |
| `priority IN [...]` / `priority:(...)` | 500 parse error |
| `stage="Triage"` | OK |
| `assignee="@Tier1"` | OK |
| `important=true` / `false` | OK |
| `incident=true` / `false` | OK. One earlier call returned 500, 4 later calls returned 200 (transient). |
| `incident="true"` | 400 Edm.Boolean vs Edm.String |
| `createTime > 1791000000000` (unquoted int) | OK |
| `createTime > "1791000000000"` | 400 Edm.Int64 vs Edm.String |
| `contains(displayName,"IoC")` | OK |
| `displayName="Moved Alert"` | OK |
| `environment="De\"mo"` (escaped quote) | **500** -> no verified escape sequence |
| `environment="O'Brien"` (apostrophe in double quotes) | OK (0 matches, valid parse) |
| `bogus="x"` | 400 "Could not find a property named 'bogus'" |

## orderBy
- `createTime desc`, `createTime asc`, `updateTime desc`, `priority desc`, `createTime`
  (no direction) and `priority desc, createTime desc` are all accepted. Results
  come back in the requested order.
- Default order (no `orderBy`) on the probed page matched `createTime desc`.
  UNKNOWN whether that is guaranteed.
- Unknown field -> 400 "Could not find a property named ...".

## Transient errors
Three HTTP 500 "Internal error encountered" responses in ~110 calls: two during
probing and one during a full Demoverse listing. Each one was on a request that later succeeded
unchanged. A follow-up run of 6 full listings (18 pages) had 0 errors and took
10.2-12.5 s per listing. `_request` retries only 429/502/503/504, so
`GoogleSecOpsAdapter.list_cases` retries HTTP 500 up to 2 times (1 s, 2 s backoff)
on this idempotent GET. If it still fails, it raises `SecOpsApiError(500)`; the
error stays visible (Invariant #2), and nothing is substituted.

## SDK mapping (implemented)
- Adapter: `GoogleSecOpsAdapter.list_cases(filter, page_size, page_token, order_by)` -> raw page dict.
- Workflow: `engine/workflows/case_list.py::ListCasesWorkflow`
  - typed facets -> filter: values in a facet OR-ed inside parentheses, facets
    AND-ed, raw `filter` passthrough AND-ed in parentheses.
  - values containing `"` or `\` are rejected with `ValueError` (no verified escape).
  - status `OPEN`/`OPENED` -> `OPENED`, `CLOSE`/`CLOSED` -> `CLOSED`; priority bare
    names -> `PRIORITY_*`.
  - follows `nextPageToken` until `max_results`. Each request asks only for the
    remaining count, so no page is cut short and the returned token resumes exactly.
- Domain: `CaseListItem`, `CaseListBatch` (`engine/domain.py`).
- Capability `case.list`: kind `query`, cardinality `unbounded` (from the `list` verb),
  require-filter policy attached automatically.

## UNKNOWN
- Whether default ordering is guaranteed.
- Whether status values other than OPENED/CLOSED exist (OPENED + CLOSED add up to the full total here).
- Whether the full value sets of `stage`, `type`, `workflowStatus` and `source` are closed (only the values listed above were seen).
- Escape sequence for `"` inside a string literal.
- Token lifetime/expiry.
