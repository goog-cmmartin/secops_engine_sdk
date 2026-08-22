#!/usr/bin/env python3
"""Dogfood: non-closed SOAR case -> involved entities -> UDM Entity Graph lookups.

Flow:
  1. Find a non-closed case via engine.search_cases (filtering is_closed=False).
  2. Pull its involved entities via engine.investigate_case().
  3. Classify each entity via engine.detect_entity() (which type -> which graph field).
  4. Attempt an Entity Graph search (graph.entity.*) for each, report hit/miss.

Read-only. Uses the live engine from tests/test_helpers.py (skips cleanly if the
tenant is not configured).

Run:  python3 -u -m scripts.dogfood_entity_graph_from_case
Tuning (env):
  DOGFOOD_MAX_ENTITIES  max entities to probe against the graph (default 12)
  DOGFOOD_CASE_ID       force a specific case instead of auto-selecting
"""

import os
import re
import sys
from datetime import datetime, timedelta, timezone

# SOAR entity_type -> the entity category we'd expect detect_entity() to land in.
# Used only to surface disagreements; not authoritative.
_SOAR_TYPE_EXPECTED_CATEGORY = {
    "ADDRESS": "ASSET",
    "HOSTNAME": "ASSET",
    "FILEHASH": "FILE",
    "FILENAME": "FILE",
    "PROCESS": "PROCESS",
    "USERUNIQNAME": "USER",
    "USER": "USER",
    "PHONENUMBER": "OTHER",
    "DESTINATIONURL": "URL",
    "URL": "URL",
    "EMAILSUBJECT": "OTHER",
}

# Identifiers that cannot be meaningful graph indicators: empty, or no alphanumerics.
_HAS_ALNUM = re.compile(r"[A-Za-z0-9]")


def _iso(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def _is_probeable(ident: str) -> bool:
    if not ident:
        return False
    if not _HAS_ALNUM.search(ident):
        return False
    return True


def main() -> int:
    try:
        from tests.test_helpers import get_live_engine
    except Exception as e:  # pragma: no cover
        print(f"[SKIP] cannot import test helpers: {e}")
        return 0

    try:
        engine = get_live_engine()
    except Exception as e:
        print(f"[SKIP] live engine unavailable (tenant not configured?): {e}")
        return 0

    max_entities = int(os.environ.get("DOGFOOD_MAX_ENTITIES", "12"))
    forced_case = os.environ.get("DOGFOOD_CASE_ID", "").strip() or None

    now = datetime.now(timezone.utc)
    # Entity Graph is time-bounded; use a wide-but-bounded window.
    graph_start = _iso(now - timedelta(days=30))
    graph_end = _iso(now)

    # ---- 1. Find a non-closed case ------------------------------------------
    print("=" * 72)
    print("STEP 1  Selecting a non-closed case")
    print("=" * 72)

    if forced_case:
        chosen_id = forced_case
        print(f"  using forced case_id={chosen_id!r}")
    else:
        try:
            batch = engine.search_cases(query="", page_size=50)
        except Exception as e:
            print(f"[FAIL] search_cases raised: {e}")
            return 1

        open_cases = [c for c in batch.items if not c.is_closed]
        print(f"  retrieved={len(batch.items)}  non_closed={len(open_cases)}  "
              f"total_reported={batch.total_count}")
        if not open_cases:
            print("[SKIP] no non-closed cases in the returned page; nothing to dogfood.")
            return 0

        # Prefer a case that actually has alerts (more likely to carry entities).
        open_cases.sort(key=lambda c: c.alerts_count, reverse=True)
        chosen = open_cases[0]
        chosen_id = chosen.case_id
        print(f"  -> chosen case_id={chosen.case_id!r} title={chosen.title!r} "
              f"priority={getattr(chosen.priority,'value',chosen.priority)} "
              f"stage={chosen.stage!r} alerts={chosen.alerts_count}")

    # ---- 2. Extract involved entities ---------------------------------------
    print("\n" + "=" * 72)
    print(f"STEP 2  investigate_case({chosen_id}) -> involved entities")
    print("=" * 72)
    try:
        inv = engine.investigate_case(chosen_id)
    except Exception as e:
        print(f"[FAIL] investigate_case raised: {e}")
        return 1

    entities = inv.entities or []
    print(f"  case status={getattr(inv.status,'value',inv.status)} "
          f"alerts={inv.alert_count} entities={len(entities)}")
    if not entities:
        print("[SKIP] chosen case exposes no involved entities.")
        return 0

    # De-duplicate on identifier, preserve order; split probeable vs. junk.
    seen = set()
    uniq, junk = [], []
    for ent in entities:
        ident = (ent.identifier or "").strip()
        if not ident or ident in seen:
            continue
        seen.add(ident)
        (uniq if _is_probeable(ident) else junk).append(ent)

    print(f"  unique identifiers: {len(uniq) + len(junk)}  "
          f"(probeable={len(uniq)}, skipped_junk={len(junk)})")
    if len(uniq) > max_entities:
        print(f"  capping probes at DOGFOOD_MAX_ENTITIES={max_entities} "
              f"(of {len(uniq)} probeable)")
        uniq = uniq[:max_entities]

    # ---- 3 & 4. Classify + Entity Graph lookup per entity -------------------
    print("\n" + "=" * 72)
    print("STEP 3/4  Classify each entity and try UDM Entity Graph lookup")
    print(f"          window: {graph_start} .. {graph_end}")
    print("=" * 72)

    hits, misses, errors, mismatches = [], [], [], []
    for ent in uniq:
        ident = ent.identifier.strip()
        soar_type = (ent.entity_type or "?").upper()
        label = f"{ident!r} (soar_type={soar_type})"

        try:
            detected = engine.detect_entity(ident)
        except Exception as e:
            print(f"\n  - {label}\n      [DETECT-ERR] {e}")
            errors.append(ident)
            continue

        dtype = getattr(detected.entity_type, "value", detected.entity_type)
        dcat = getattr(detected.category, "value", detected.category)
        print(f"\n  - {label}")
        print(f"      detected_type={dtype} category={dcat}")
        print(f"      graph_query={detected.graph_query}")

        # Flag SOAR-vs-detector disagreement (the interesting classification signal).
        expected = _SOAR_TYPE_EXPECTED_CATEGORY.get(soar_type)
        if expected and expected != dcat:
            print(f"      [MISMATCH] SOAR says {soar_type} (~{expected}) "
                  f"but detector chose {dcat}")
            mismatches.append((ident, soar_type, dcat))

        try:
            session = engine.search_entity_graph(
                indicator_or_field=ident,
                start_time=graph_start,
                end_time=graph_end,
                receive_limit=5,
                batch_size=5,
            )
        except Exception as e:
            print(f"      [GRAPH-ERR] {type(e).__name__}: {e}")
            errors.append(ident)
            continue

        n = session.received_count
        lc = getattr(session.lifecycle, "value", session.lifecycle)
        comp = getattr(session.completeness, "value", session.completeness)
        print(f"      lifecycle={lc} completeness={comp} graph_entities_returned={n}")
        (hits if n > 0 else misses).append((ident, dtype, n))

    # ---- Summary ------------------------------------------------------------
    print("\n" + "=" * 72)
    print("SUMMARY")
    print("=" * 72)
    print(f"  case_id            : {chosen_id}")
    print(f"  probed entities    : {len(uniq)}")
    print(f"  graph HITS         : {len(hits)}")
    for ident, dtype, n in hits:
        print(f"      + {ident}  [{dtype}]  -> {n} graph entity record(s)")
    print(f"  graph MISSES       : {len(misses)}")
    for ident, dtype, _ in misses:
        print(f"      - {ident}  [{dtype}]")
    if errors:
        print(f"  errors             : {len(errors)} -> {errors}")
    if mismatches:
        print(f"  classify MISMATCH  : {len(mismatches)} "
              f"(detector ignored SOAR entity_type)")
        for ident, st, dc in mismatches:
            print(f"      ! {ident!r}  soar={st}  detected_category={dc}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
