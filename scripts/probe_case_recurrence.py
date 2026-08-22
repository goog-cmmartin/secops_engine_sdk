#!/usr/bin/env python3
"""Discovery probe: does SOAR free-text case search match INVOLVED ENTITIES,
or only case titles?

Read-only. Resolves Path A (free-text indexes entities) vs Path B (title-only)
for the `case.recurrence` capability design.

Writes a REDACTED observation to discovery/observations/ — real entity/case/tenant
values are replaced with stable placeholders before anything is persisted.

Usage:
    PYTHONPATH=. python3 scripts/probe_case_recurrence.py
"""

import re
import sys
from datetime import datetime, timedelta, timezone

from adapters.google_secops import GoogleSecOpsAdapter
from engine.facade import SecOpsEngine


def redact(text: str, mapping: dict) -> str:
    """Replace every known-sensitive literal with its placeholder."""
    out = text
    for real, placeholder in mapping.items():
        if real:
            out = out.replace(str(real), placeholder)
    # Belt-and-suspenders: scrub any UUID and any raw IPv4 that slipped through.
    out = re.sub(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}",
                 "<UUID>", out, flags=re.I)
    return out


def main() -> int:
    adapter = GoogleSecOpsAdapter()
    engine = SecOpsEngine(adapter=adapter)

    redaction = {
        adapter.customer_id: "<CUSTOMER_ID>",
        adapter.project_id: "<PROJECT_ID>",
        adapter.project_number: "<PROJECT_NUMBER>",
    }
    lines = []
    def log(msg: str = ""):
        print(msg)
        lines.append(msg)

    end = datetime.now(timezone.utc)
    start = end - timedelta(days=30)

    log("# Discovery: case free-text search vs involved entities")
    log(f"observed_at: {end.isoformat()}")
    log("method: read-only search_cases + case.investigate against live tenant")
    log("")

    # --- Step 1: baseline connectivity + grab real cases -------------------
    log("## Step 1 — baseline case search (empty query, 30d)")
    batch = engine.search_cases(query="", page_size=5)
    log(f"total_count: {batch.total_count}, returned: {len(batch.items)}")
    if not batch.items:
        log("NO CASES in window — cannot resolve A/B. Widen window or seed a case.")
        _persist(lines, redaction)
        return 2
    for it in batch.items:
        log(f"  - case_id=<CASE:{it.case_id}> title={it.title!r} alerts={it.alerts_count}")

    # --- Step 2: find a case with a real involved entity ------------------
    log("")
    log("## Step 2 — pull a ground-truth involved entity via case.investigate")
    probe_entity = None
    source_case_id = None
    for it in batch.items:
        if it.alerts_count == 0:
            continue
        try:
            inv = engine.investigate_case(it.case_id)
        except Exception as e:  # noqa: BLE001 - surface, keep probing
            log(f"  investigate(case=<CASE:{it.case_id}>) error: {redact(str(e), redaction)}")
            continue
        ents = inv.involved_entities
        if ents:
            probe_entity = ents[0].identifier
            source_case_id = it.case_id
            redaction[probe_entity] = "<ENTITY>"
            log(f"  source case <CASE:{source_case_id}> has {len(ents)} entities")
            log(f"  chosen probe entity: <ENTITY> (type={ents[0].entity_type})")
            break
        else:
            log(f"  case <CASE:{it.case_id}> — no involved entities")

    if not probe_entity:
        log("NO involved entity found on any sampled case — inconclusive (try more cases).")
        _persist(lines, redaction)
        return 2

    # --- Step 3: THE decisive test ---------------------------------------
    log("")
    log("## Step 3 — search cases by that entity value (decisive)")
    ent_batch = engine.search_cases(query=probe_entity, page_size=25)
    hit_ids = {i.case_id for i in ent_batch.items}
    matched_source = source_case_id in hit_ids
    log(f"query_text=<ENTITY> -> total_count={ent_batch.total_count}, returned={len(ent_batch.items)}")
    log(f"source case <CASE:{source_case_id}> present in results: {matched_source}")

    log("")
    log("## VERDICT")
    if matched_source:
        log("PATH A confirmed: free-text case search MATCHES involved entities.")
        log("=> case.recurrence = thin fan-out over case.search (one search per signal).")
    else:
        log("PATH B confirmed: free-text search did NOT return the entity's own case.")
        log("=> title-only. Entity recurrence must route via involvedEntities fan-out.")

    _persist(lines, redaction)
    return 0


def _persist(lines, redaction):
    body = redact("\n".join(lines) + "\n", redaction)
    path = "discovery/observations/02_case_recurrence_discovery.md"
    with open(path, "w", encoding="utf-8") as f:
        f.write(body)
    print(f"\n[written, redacted] {path}")


if __name__ == "__main__":
    sys.exit(main())
