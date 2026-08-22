# Discovery: analyst first-touch case triage (is-it-closed? + recent comments)

observed_at: 2026-08-21T00:00:00+00:00
method: read-only search_cases + case.investigate against live tenant, public surface only
scope: strictly what the SDK can CURRENTLY express — no aspirational fields

## Question
When an analyst opens a case, the first two moves are:
  (1) confirm it is not Closed, and
  (2) read the most recent comments.
Can the documented SDK surface express both, and do its descriptions guide you there?

## Step 1 — capability surface (facade)
`investigate_case(case_id) -> CaseInvestigation` is the single entry point that
returns BOTH triage signals: a `status` field and a `comments` list.
Facade docstring is a one-liner ("Executes the Case Investigation Workspace
workflow"); it does not state that this is where status+comments live, nor how
comments are ordered. Capability present; description under-specifies it.

## Step 2 — model facts (engine/domain.py, verified in source)
  - CaseStatus enum        = {OPEN, CLOSED, UNKNOWN}
  - CaseInvestigation.status: CaseStatus              (detail view)
  - CaseInvestigation.comments: List[CaseCommentRecord]
  - CaseSearchResultItem.is_closed: bool             (queue/list view)
  - CaseCommentRecord: {name, comment, author, author_name,
                        create_time, is_deleted, raw}

## Step 3 — live exercise (read-only)
  - Newest recent case <CASE:a> came back status=CLOSED -> workflow correctly
    short-circuits ("analyst stops here"). Check (1) works on the detail view.
  - Recent search page (30d, page_size=50): 15 closed / 35 open via
    CaseSearchResultItem.is_closed. Check (1) also works on the queue view.
  - Newest OPEN case <CASE:b> investigated: status=OPEN; the two
    representations AGREE on closed-state (is_closed == (status==CLOSED)).
  - <CASE:b> had 0 comments -> cleanly handled valid result, not a failure.
    Comment path exercised on a case with comments elsewhere in-session.

## VERDICT
FEASIBLE end-to-end via the documented surface. Both triage checks are
expressible today. Three description/consistency caveats, none functional bugs:

  F1 (consistency) — "is it closed?" is modeled two different ways depending on
     which object you hold: `CaseSearchResultItem.is_closed` (bool, queue view)
     vs `CaseInvestigation.status` (CaseStatus enum, detail view). Neither
     description cross-references the other; crossing queue->detail forces a
     relearn. Highest-value finding.

  F2 (ordering) — `CaseInvestigation.comments` has NO documented ordering, so
     "recent comments" requires the caller to sort by `create_time`. Same
     pattern as the latest-case ordering gap (obs 02 family).

  F3 (discoverability) — one-line facade docstrings do not reveal that
     `investigate_case` is the single call yielding both status and comments;
     you must read the return type to find out.

## Suggested (non-binding) follow-ups
  - CAPABILITIES.md `case.investigate` row: add caveat "comments unordered;
    sort by create_time" and note the is_closed/status split.
  - Consider a derived `CaseSearchResultItem.status` or
    `CaseInvestigation.is_closed` alias to unify F1 (code change — out of scope
    for this doc-only task; recorded for later).
