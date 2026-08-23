"""Textual TUI proof-of-concept for the Google SecOps Workflow SDK.

This package is a *thin rendering + interaction shell* over the existing
``engine.facade.SecOpsEngine``. It contains no workflow logic of its own and
must not import or duplicate anything from ``engine/`` beyond the public facade
and domain dataclasses.

Design invariants (do not violate):
  1. The SDK facade is latency-bound (live API, ~2-3s round trips). Every call
     into it MUST run on a worker thread via Textual's ``@work(thread=True)``.
     Calling the facade on the UI thread will freeze input and destroy the
     "responsive" property that justifies a TUI at all.
  2. Imports are project-root relative (``from engine.facade import ...``),
     mirroring how the facade itself imports ``adapters.*``. The launcher
     (``tui/app.py`` run as a module, or ``run_tui.py``) is responsible for
     ensuring the project root is on ``sys.path``.
  3. Bind only to confirmed domain shapes: ``CaseSearchResultItem`` for the
     list pane, ``CaseInvestigation`` for the detail pane.
"""

__all__ = ["SecOpsTUI"]
