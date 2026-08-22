"""Live smoke test for the SOAR Search workflow.

Exercises three stages against the configured tenant:
  1. Retrieve the latest case (newest by create_time).
  2. Search historical cases over a wider window with paging.
  3. Pivot: extract an entity from the latest case's alerts and run
     an entity search (UDM) over recent history.

Run: PYTHONPATH=. python3 scripts/probe_soar_search.py
"""

from datetime import datetime, timedelta, timezone

from engine.facade import SecOpsEngine
from engine.domain import EntityType


def _fmt(dt):
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ") if dt else "n/a"


def main() -> None:
    eng = SecOpsEngine()
    now = datetime.now(timezone.utc)

    # --- Stage 1: latest case -------------------------------------------
    print("=" * 68)
    print("STAGE 1  Latest case (trailing 30d, newest first)")
    print("=" * 68)
    recent = eng.search_cases(query="", page_size=50)
    print(f"total_count={recent.total_count}  returned={len(recent.items)}")
    if not recent.items:
        print("No cases in window; aborting downstream stages.")
        return

    latest = max(
        recent.items,
        key=lambda c: c.create_time or datetime.min.replace(tzinfo=timezone.utc),
    )
    print(f"latest case_id={latest.case_id}")
    print(f"  title      = {latest.title!r}")
    print(f"  created    = {_fmt(latest.create_time)}")
    print(f"  priority   = {latest.priority}  stage={latest.stage}")
    print(f"  alerts     = {latest.alerts_count}  env={latest.environment!r}")
    print(f"  tags       = {latest.tags}")

    # --- Stage 2: historical search -------------------------------------
    print()
    print("=" * 68)
    print("STAGE 2  Historical search (trailing 90d, page 0 + page 1)")
    print("=" * 68)
    start = now - timedelta(days=90)
    p0 = eng.search_cases(query="", start_time=start, end_time=now,
                          page_size=25, page_number=0)
    print(f"total_count={p0.total_count}  page0_returned={len(p0.items)}")
    if p0.total_count > 25:
        p1 = eng.search_cases(query="", start_time=start, end_time=now,
                              page_size=25, page_number=1)
        print(f"page1_returned={len(p1.items)}")
        overlap = {c.case_id for c in p0.items} & {c.case_id for c in p1.items}
        print(f"page0/page1 id overlap = {len(overlap)} (expect 0)")
    else:
        print("(<=25 total; no second page to fetch)")

    # --- Stage 3: entity pivot ------------------------------------------
    print()
    print("=" * 68)
    print("STAGE 3  Entity pivot from latest case")
    print("=" * 68)
    adapter = eng.adapter
    alerts = adapter.list_case_alerts(latest.case_id)
    print(f"alerts on latest case: {len(alerts)}")

    entity_value = None
    entity_type = None
    for al in alerts:
        name = al.get("name")
        if not name:
            continue
        ents = adapter.list_alert_entities(name)
        print(f"  alert {name.split('/')[-1]}: {len(ents)} involved entities")
        for e in ents:
            ident = e.get("entityIdentifier") or e.get("identifier")
            etype = (e.get("entityType") or e.get("type") or "").upper()
            if ident and etype:
                entity_value, entity_type = ident, etype
                break
        if entity_value:
            break

    if not entity_value:
        print("No usable entity found on latest case's alerts; skipping pivot.")
        return

    # Map SOAR entity type string -> engine EntityType (best effort).
    type_map = {
        "ADDRESS": EntityType.IP,
        "DESTINATIONIPADDRESS": EntityType.IP,
        "HOSTNAME": EntityType.HOSTNAME,
        "USERUNIQNAME": EntityType.USER,
        "USERNAME": EntityType.USER,
        "FILEHASH": EntityType.SHA256,
    }
    mapped = type_map.get(entity_type)
    print(f"selected entity: type={entity_type} value={entity_value!r} "
          f"-> mapped={mapped}")
    if mapped is None:
        print(f"No EntityType mapping for {entity_type!r}; skipping UDM pivot.")
        return

    p_start = _fmt(now - timedelta(days=7))
    p_end = _fmt(now)
    print(f"running entity search over {p_start} .. {p_end}")
    session = eng.search_from_entity(
        entity_type=mapped,
        entity_value=entity_value,
        start_time=p_start,
        end_time=p_end,
        receive_limit=50,
        batch_size=50,
    )
    print(f"session lifecycle  = {session.lifecycle}")
    print(f"session completeness= {session.completeness}")
    print(f"events received     = {session.received_count}")

    print()
    print("SOAR Search workflow smoke test complete.")


if __name__ == "__main__":
    main()
