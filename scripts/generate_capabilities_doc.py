#!/usr/bin/env python3
"""Generate docs/CAPABILITIES.md from the live engine registry.

This is the single source of truth for the capability reference. It builds
the real registry against an inert (offline) adapter -- no credentials, no
network -- so it is safe to run in CI and locally.

Usage:
    python scripts/generate_capabilities_doc.py            # write docs/CAPABILITIES.md
    python scripts/generate_capabilities_doc.py --check    # exit 1 if out of date

The --check mode lets CI enforce that the committed doc matches the registry.
"""
from __future__ import annotations

import argparse
import sys
from collections import Counter, defaultdict
from datetime import date
from pathlib import Path

# Ensure repo root is importable when invoked from anywhere.
REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from engine.facade import SecOpsEngine  # noqa: E402
from engine.registry import WorkflowRegistry  # noqa: E402

OUTPUT_PATH = REPO_ROOT / "docs" / "CAPABILITIES.md"

_KIND_ORDER = {"workflow": 0, "primitive": 1, "query": 2}


class _InertAdapter:
    """Adapter whose every method raises; capabilities register without I/O."""

    def __getattr__(self, name):
        def _boom(*_a, **_k):
            raise RuntimeError(f"inert adapter: {name} must not be called")

        return _boom


def build_registry() -> WorkflowRegistry:
    engine = SecOpsEngine(adapter=_InertAdapter(), custom_registry=WorkflowRegistry())
    return engine.registry


def _fmt_card(card: str | None) -> str:
    return f"`{card}`" if card else "—"


def render(caps) -> str:
    caps = list(caps)
    kinds = Counter(c.kind for c in caps)
    cards = Counter(str(c.cardinality) for c in caps if c.cardinality)
    by_domain: dict[str, list] = defaultdict(list)
    for c in caps:
        by_domain[c.domain].append(c)

    L: list[str] = []
    a = L.append

    a("<!-- GENERATED FILE — do not edit by hand. -->")
    a("<!-- Regenerate with: python scripts/generate_capabilities_doc.py -->")
    a("")
    a("# Capability Reference")
    a("")
    a(f"_Generated {date.today().isoformat()} from `engine/registry.py` "
      f"via `scripts/generate_capabilities_doc.py`._")
    a("")
    a(f"**{len(caps)} registered capabilities.** Every capability is exposed to the "
      "Python SDK (`engine.facade`), the CLI, and as an MCP tool.")
    a("")

    # --- Legend -----------------------------------------------------------
    a("## Classification legend")
    a("")
    a("- **kind** — `workflow` (composed, multi-step), `primitive` (single mutating "
      "action), `query` (read-only).")
    a("- **cardinality** — `single` (one entity), `bounded` (finite/enum set), "
      "`unbounded` (open collection; agent must supply a filter — see AGENTS.md "
      "Invariant #9).")
    a("")

    # --- Totals -----------------------------------------------------------
    a("## Totals")
    a("")
    a("| kind | count |")
    a("| :--- | ----: |")
    for k in sorted(kinds, key=lambda x: _KIND_ORDER.get(x, 9)):
        a(f"| {k} | {kinds[k]} |")
    a(f"| **total** | **{len(caps)}** |")
    a("")
    a("| cardinality | count |")
    a("| :--- | ----: |")
    for c in ("single", "bounded", "unbounded"):
        if cards.get(c):
            a(f"| {c} | {cards[c]} |")
    a(f"| (n/a — workflows/primitive) | {len(caps) - sum(cards.values())} |")
    a("")

    # --- Workflows spotlight ---------------------------------------------
    workflows = sorted((c for c in caps if c.kind == "workflow"),
                       key=lambda x: x.capability_id)
    a("## Workflows")
    a("")
    a("Composed, provenance-tracked operations — the orchestrated behaviors of the "
      "engine.")
    a("")
    a("| capability_id | domain | description |")
    a("| :--- | :--- | :--- |")
    for c in workflows:
        desc = c.description.replace("|", "\\|")
        a(f"| `{c.capability_id}` | {c.domain} | {desc} |")
    a("")

    # --- Full table by domain --------------------------------------------
    a("## All capabilities by domain")
    a("")
    for dom in sorted(by_domain):
        group = by_domain[dom]
        kc = Counter(c.kind for c in group)
        summary = ", ".join(f"{k}={kc[k]}" for k in sorted(kc, key=lambda x: _KIND_ORDER.get(x, 9)))
        a(f"### {dom}  ({len(group)}: {summary})")
        a("")
        a("| capability_id | kind | cardinality | mcp_tool | description |")
        a("| :--- | :--- | :--- | :--- | :--- |")
        for c in sorted(group, key=lambda x: (_KIND_ORDER.get(x.kind, 9), x.capability_id)):
            desc = c.description.replace("|", "\\|")
            tool = f"`{c.mcp_tool_name}`" if c.mcp_tool_name else "—"
            a(f"| `{c.capability_id}` | {c.kind} | {_fmt_card(c.cardinality)} | {tool} | {desc} |")
        a("")

    return "\n".join(L).rstrip() + "\n"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--check", action="store_true",
                    help="Exit non-zero if docs/CAPABILITIES.md is stale.")
    args = ap.parse_args()

    content = render(build_registry().list_capabilities())

    if args.check:
        current = OUTPUT_PATH.read_text() if OUTPUT_PATH.exists() else ""
        if current != content:
            print("docs/CAPABILITIES.md is STALE. Run: "
                  "python scripts/generate_capabilities_doc.py", file=sys.stderr)
            return 1
        print("docs/CAPABILITIES.md is up to date.")
        return 0

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(content)
    print(f"Wrote {OUTPUT_PATH.relative_to(REPO_ROOT)} "
          f"({len(content.splitlines())} lines).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
