#!/usr/bin/env python3
"""Read-only live probe against the configured Google SecOps tenant.

Only GET requests and side-effect-free validation POSTs (verifyRuleText,
testFindingsRefinement) are permitted; any other call raises before it hits the
network. Every call is appended to .state/live_probe_log.jsonl.

Usage: python scripts/live_probe.py [--json]
"""
from __future__ import annotations

import json
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from adapters.google_secops import GoogleSecOpsAdapter  # noqa: E402

LOG_PATH = ROOT / ".state" / "live_probe_log.jsonl"
READ_ONLY_POST_SUFFIXES = (":verifyRuleText", ":testFindingsRefinement")


class ReadOnlyAdapter(GoogleSecOpsAdapter):
    """Adapter that refuses mutating calls and logs every request."""

    def _request(self, method, path, params=None, body=None, timeout=None):
        base_path = path.split("?", 1)[0]
        allowed = method == "GET" or (
            method == "POST" and base_path.endswith(READ_ONLY_POST_SUFFIXES)
        )
        if not allowed:
            raise PermissionError(f"live_probe is read-only; blocked {method} {base_path}")
        started = time.time()
        entry: Dict[str, Any] = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "method": method,
            "path": base_path,
            "params": params,
        }
        try:
            res = super()._request(method, path, params=params, body=body, timeout=timeout)
            entry["ok"] = True
            return res
        except Exception as exc:  # noqa: BLE001
            entry["ok"] = False
            entry["error"] = str(exc)[:500]
            raise
        finally:
            entry["ms"] = int((time.time() - started) * 1000)
            LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
            with LOG_PATH.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps(entry, default=str) + "\n")


def _keys(obj: Any) -> List[str]:
    return sorted(obj.keys()) if isinstance(obj, dict) else []


def main() -> int:
    a = ReadOnlyAdapter()
    inst = f"locations/{a.location}/instances/{a.customer_id}"
    results: Dict[str, Any] = {}
    ctx: Dict[str, Any] = {}

    def probe(name: str, fn: Callable[[], Any], summarise: Callable[[Any], Any]) -> None:
        try:
            res = fn()
            results[name] = {"ok": True, "summary": summarise(res)}
        except Exception as exc:  # noqa: BLE001
            results[name] = {"ok": False, "error": str(exc)[:400]}

    # --- Rules ---------------------------------------------------------------
    def rules_summary(r):
        rules = r.get("rules", [])
        if rules:
            ctx["rule_name"] = rules[0].get("name")
            ctx["rule_id"] = rules[0].get("name", "").split("/")[-1]
        return {"count_page": len(rules), "next_page": bool(r.get("nextPageToken")),
                "rule_keys": _keys(rules[0]) if rules else [],
                "sample_ids": [x.get("name", "").split("/")[-1] for x in rules[:5]]}

    probe("rules.list", lambda: a.list_rules(page_size=25, view="BASIC"), rules_summary)
    probe("rules.list[path=project_number]",
          lambda: a._request("GET", f"/v1alpha/projects/{a.project_number}/{inst}/rules", params={"pageSize": 1}),
          lambda r: {"count_page": len(r.get("rules", []))})
    if ctx.get("rule_id"):
        probe("rules.get[id]", lambda: a.get_rule(ctx["rule_id"]),
              lambda r: {"keys": _keys(r), "revision": r.get("revisionId"), "type": r.get("type")})
        probe("rules.get[full_name]", lambda: a.get_rule(ctx["rule_name"]),
              lambda r: {"name_match": r.get("name") == ctx["rule_name"]})
        probe("rules.get[bogus_id]", lambda: a.get_rule("ru_00000000-0000-0000-0000-000000000000"),
              lambda r: {"unexpected_ok": True})
        probe("rules.get[non_ru_string]", lambda: a.get_rule("not-a-rule-id"),
              lambda r: {"unexpected_ok": True, "keys": _keys(r)})
        probe("rules.deployment.get", lambda: a.get_rule_deployment(ctx["rule_id"]),
              lambda r: {"keys": _keys(r), "enabled_type": type(r.get("enabled")).__name__})

    probe("rules.deployments.list", lambda: a.list_rule_deployments(page_size=1000),
          lambda r: {"count": len(r.get("ruleDeployments", [])),
                     "enabled": sum(1 for d in r.get("ruleDeployments", []) if d.get("enabled")),
                     "alerting": sum(1 for d in r.get("ruleDeployments", []) if d.get("alerting")),
                     "keys": _keys((r.get("ruleDeployments") or [{}])[0])})

    probe("rules.verifyRuleText[valid]", lambda: a.verify_rule_text(
        'rule zz_sdk_probe { meta: author = "probe" events: $e.metadata.event_type = "USER_LOGIN" condition: $e }'),
        lambda r: r)
    probe("rules.verifyRuleText[invalid]", lambda: a.verify_rule_text("rule broken { events: condition: }"),
          lambda r: r)

    # --- Exclusions / curated --------------------------------------------------
    def refinements_summary(r):
        items = r.get("findingsRefinements", [])
        if items:
            ctx["refinement_id"] = items[0].get("name", "").split("/")[-1]
        return {"count_page": len(items), "keys": _keys(items[0]) if items else [],
                "types": sorted({i.get("type") for i in items if i.get("type")})}

    probe("findingsRefinements.list", lambda: a.list_findings_refinements(page_size=100), refinements_summary)
    if ctx.get("refinement_id"):
        probe("findingsRefinements.get", lambda: a.get_findings_refinement(ctx["refinement_id"]),
              lambda r: {"keys": _keys(r), "has_etag": "etag" in r if isinstance(r, dict) else None})

    def curated_summary(r):
        items = r.get("curatedRules", [])
        if items:
            ctx["curated_rule"] = items[0].get("name")
        return {"count": len(items), "keys": _keys(items[0]) if items else []}

    probe("curatedRules.list", lambda: a.list_curated_rules(page_size=1000), curated_summary)
    probe("curatedRuleSets.list", lambda: a.list_curated_rulesets(),
          lambda r: {"top_keys": _keys(r), "count": len(r.get("curatedRuleSets", []))})
    if ctx.get("curated_rule"):
        now = datetime.now(timezone.utc)
        probe("testFindingsRefinement[dry_run]", lambda: a.test_findings_refinement(
            [ctx["curated_rule"]], 'principal.hostname = "zz-sdk-probe-nonexistent"',
            (now - timedelta(days=1)).strftime("%Y-%m-%dT%H:%M:%SZ"), now.strftime("%Y-%m-%dT%H:%M:%SZ"),
            timeout=60.0), lambda r: {"type": type(r).__name__, "len": len(r)})

    # --- Search / validation -------------------------------------------------
    probe("validateQuery[valid]", lambda: a.validate_query('metadata.event_type = "USER_LOGIN"'),
          lambda r: getattr(r, "__dict__", str(r)))
    probe("validateQuery[invalid]", lambda: a.validate_query('metadata.event_type = = '),
          lambda r: getattr(r, "__dict__", str(r)))

    # --- Data inventory ------------------------------------------------------
    probe("dataTables.list", lambda: a.list_data_tables(page_size=100),
          lambda r: {"count_page": len(r.get("dataTables", [])),
                     "names": [d.get("name", "").split("/")[-1] for d in r.get("dataTables", [])[:10]]})
    probe("referenceLists.list",
          lambda: a._request("GET", f"/v1alpha/projects/{a.project_id}/{inst}/referenceLists", params={"pageSize": 100}),
          lambda r: {"count_page": len(r.get("referenceLists", []))})
    probe("feeds.list", lambda: a.list_feeds(),
          lambda r: {"count": len(r.get("feeds", [])),
                     "states": sorted({f.get("state") for f in r.get("feeds", []) if f.get("state")})})
    probe("logTypes.list", lambda: a.list_log_types(),
          lambda r: {"count_page": len(r.get("logTypes", [])) if isinstance(r, dict) else None})
    probe("parsers.list", lambda: a.list_parsers(),
          lambda r: {"count_page": len(r.get("parsers", [])) if isinstance(r, dict) else None})
    probe("retrohunts.list",
          lambda: a._request("GET", f"/v1alpha/projects/{a.project_id}/{inst}/rules/-/retrohunts", params={"pageSize": 5}),
          lambda r: {"count_page": len(r.get("retrohunts", []))})

    if "--json" in sys.argv:
        print(json.dumps(results, indent=2, default=str))
    else:
        for name, res in results.items():
            status = "OK  " if res["ok"] else "FAIL"
            detail = res.get("summary") if res["ok"] else res.get("error")
            print(f"[{status}] {name}: {json.dumps(detail, default=str)[:600]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
