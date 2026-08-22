"""Dogfood: analyst opening a case -> is it still open? -> what are the recent comments?

Uses ONLY the documented public surface (facade + returned domain objects).
Tests whether the SDK's descriptions guide an analyst through first-touch triage.
"""

from datetime import datetime, timedelta, timezone

from engine.domain import CaseStatus
from tests.test_helpers import get_live_engine


def main() -> None:
    engine = get_live_engine()

    # Pick a real, recent case to triage (reuse the 'latest case' discovery).
    lookback = datetime.now(timezone.utc) - timedelta(days=30)
    batch = engine.search_cases(query="", start_time=lookback, page_size=50)
    if not batch:
        print("No recent cases to triage. Exiting cleanly.")
        return
    dated = [c for c in batch if c.create_time is not None]
    target = max(dated, key=lambda c: c.create_time) if dated else batch[0]

    # First-touch triage: one call returns status AND comments.
    case = engine.investigate_case(target.case_id)

    # --- Analyst check 1: is it closed? ---------------------------------
    is_closed = case.status == CaseStatus.CLOSED
    print(f"[1] Case {case.case_id!r} '{case.title}'")
    print(f"    status={case.status.value}  ->  {'CLOSED (skip)' if is_closed else 'WORKABLE'}")
    if is_closed:
        print("    Case is closed; an analyst would stop here.")
        return

    # --- Analyst check 2: recent comments -------------------------------
    live = [c for c in case.comments if not c.is_deleted]
    print(f"[2] comments: {len(case.comments)} total, {len(live)} not-deleted")
    if not live:
        print("    No comments yet on this case.")
        return

    # No documented ordering -> sort by create_time ourselves for 'recent'.
    ordered = sorted(
        live,
        key=lambda c: c.create_time or datetime.min.replace(tzinfo=timezone.utc),
        reverse=True,
    )
    for c in ordered[:5]:
        who = c.author_name or c.author or "unknown"
        when = c.create_time.isoformat() if c.create_time else "no-timestamp"
        snippet = (c.comment or "").replace("\n", " ")[:80]
        print(f"      - {when}  {who}: {snippet}")

    print("\nDONE: status + recent-comments triage completed via public API.")


if __name__ == "__main__":
    main()
