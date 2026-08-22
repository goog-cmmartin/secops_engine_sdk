# Discovery: case free-text search vs involved entities
observed_at: 2026-08-22T10:06:24.310548+00:00
method: read-only search_cases + case.investigate against live tenant

## Step 1 — baseline case search (empty query, 30d)
total_count: 1185, returned: 5
  - case_id=<CASE:19171> title='Moved Alert' alerts=1
  - case_id=<CASE:19170> title='Moved Alert' alerts=1
  - case_id=<CASE:19169> title='Moved Alert' alerts=1
  - case_id=<CASE:19168> title='Moved Alert' alerts=1
  - case_id=<CASE:19167> title='Doplik Loading Chrome Extension' alerts=1

## Step 2 — pull a ground-truth involved entity via case.investigate
  source case <CASE:19171> has 12 entities
  chosen probe entity: <ENTITY> (type=FILENAME)

## Step 3 — search cases by that entity value (decisive)
query_text=<ENTITY> -> total_count=0, returned=0
source case <CASE:19171> present in results: False

## VERDICT
PATH B confirmed: free-text search did NOT return the entity's own case.
=> title-only. Entity recurrence must route via involvedEntities fan-out.
