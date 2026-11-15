#!/usr/bin/env python3
"""Launcher for the SecOps TUI proof-of-concept.

Run from anywhere; this script anchors ``sys.path`` to the project root so the
facade's root-relative imports (``from adapters.google_secops import ...``)
resolve correctly.

Usage:
    python run_tui.py                     # live engine (needs configured creds)
    python run_tui.py --query "..."       # seed the search box
    python run_tui.py --demo              # offline preview mode (loads tests/tui_demo_engine.py)
"""
from __future__ import annotations

import argparse
import os
import sys

# --- anchor project root (invariant #2 from clients/tui/__init__.py) ------
_ROOT = os.path.dirname(os.path.abspath(__file__))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)


def _build_demo_engine():
    """Loads the offline preview engine defined under tests/."""
    try:
        from tests.tui_demo_engine import _build_demo_engine as _load_demo_engine
    except ModuleNotFoundError as exc:
        raise RuntimeError(
            "--demo requires a source checkout containing tests/tui_demo_engine.py; "
            "installed wheels exclude test helpers per AGENTS.md."
        ) from exc
    return _load_demo_engine()


def main() -> int:
    parser = argparse.ArgumentParser(description="SecOps TUI proof-of-concept")
    parser.add_argument("--query", default="", help="seed the case search box")
    parser.add_argument("--demo", action="store_true", help="offline demo mode (no API calls)")
    parser.add_argument("--page-size", type=int, default=50)
    args = parser.parse_args()

    try:
        from clients.tui.app import SecOpsTUI
    except ModuleNotFoundError as exc:
        if "textual" in str(exc):
            print("Textual is not installed. Run: pip install -r clients/tui/requirements-tui.txt", file=sys.stderr)
            return 2
        raise

    if args.demo:
        engine = _build_demo_engine()
    else:
        from engine.facade import SecOpsEngine
        try:
            engine = SecOpsEngine()
        except Exception as exc:
            print(f"Failed to construct SecOpsEngine (creds/config?): {exc}", file=sys.stderr)
            print("Tip: use --demo to preview the UI without live credentials.", file=sys.stderr)
            return 3

    SecOpsTUI(engine=engine, initial_query=args.query, page_size=args.page_size).run()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
