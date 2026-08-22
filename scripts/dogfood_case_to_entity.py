"""Dogfooding walkthrough: latest SOAR case -> its entities -> case search by entity.

Goal: verify the SDK's *own guidance* (docstrings + public surface) is sufficient
for a user with no internal knowledge to:
  1. get the latest case from SOAR,
  2. extract the entities involved in it,
  3. search SOAR for other cases involving those entities.

This script intentionally uses ONLY the documented public API exported from
`engine` and the `SecOpsEngine` facade methods. If something here required
reading adapter/internal source, that's a documentation gap worth noting.
"""

from datetime import datetime, timedelta, timezone

from tests.test_helpers import get_live_engine


def main() -> None:
    engine = get_live_engine()

    # --- Step 1: get the latest case -------------------------------------
    # Discoverability check: there is no `get_latest_case()`; a user must know
    # to search with an empty query and sort by create_time client-side.
    lookback_start = datetime.now(timezone.utc) - timedelta(days=30)
    batch = engine.search_cases(query="", start_time=lookback_start, page_size=50)
    print(f"[1] search_cases(empty) -> total_count={batch.total_count}, page={len(batch)}")

    if not batch:
        print("    No cases in the last 30 days; nothing to dogfood. Exiting cleanly.")
        return

    dated = [c for c in batch if c.create_time is not None]
    latest = max(dated, key=lambda c: c.create_time) if dated else batch[0]
    print(f"    latest case -> id={latest.case_id!r} title={latest.title!r} "
          f"created={latest.create_time} priority={latest.priority}")

    # --- Step 2: investigate the case to get involved entities -----------
    inv = engine.investigate_case(latest.case_id)
    print(f"[2] investigate_case({latest.case_id}) -> "
          f"alerts={inv.alert_count} entities={len(inv.involved_entities)}")

    if not inv.involved_entities:
        print("    Case has no involved entities; cannot pivot. Exiting cleanly.")
        return

    for e in inv.involved_entities:
        flag = " (suspicious)" if e.is_suspicious else ""
        print(f"      - {e.entity_type or '?'}: {e.identifier!r}{flag}")

    # --- Step 3: for each entity, search cases by entity -----------------
    # Uses the documented canonical helper for entity-driven case lookups.
    print("[3] pivoting each entity through search_cases_by_entity(...)")
    for e in inv.involved_entities:
        hits = engine.search_cases_by_entity(e.identifier, start_time=lookback_start)
        others = [c.case_id for c in hits if c.case_id != latest.case_id]
        print(f"      Entity:{e.identifier!r} -> {hits.total_count} case(s); "
              f"other than source: {others[:5]}{'...' if len(others) > 5 else ''}")

    print("\nDONE: full case -> entity -> case-search loop completed via public API.")


if __name__ == "__main__":
    main()
