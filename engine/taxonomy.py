"""Capability taxonomy: the `kind` and `domain` classification model (Step 2).

This module centralizes the rules that assign every registered capability a
`kind` and a `domain`. Both are derivable from data the registry already
carries (`capability_id`, `category`, `composed`), so the 104 existing
registrations need ZERO per-call edits: derivation happens in
`WorkflowCapability.__post_init__`. Explicit values always win over derivation,
which is how Step 3+ will hand-tune the handful of ambiguous cases.

Taxonomy axes
-------------
kind:
  * ``query``     -- read-only. MUST be side-effect free. (`.get/.search/.list`)
  * ``primitive`` -- a single atomic operation that may mutate state.
  * ``workflow``  -- a composed, multi-step capability (``composed=True``).

domain:
  * The coarse functional area (search, case, case_config, soar_settings, ...).
    Today this equals ``category``; making it a first-class field lets the
    contract suite and CLI/MCP layers filter on it without reaching into the
    legacy ``category`` name.
"""

from __future__ import annotations

from typing import Optional

# The only legal kinds. Kept in sync with the contract suite's KINDS set.
VALID_KINDS = frozenset({"primitive", "query", "workflow"})

# Verb suffixes (the final dotted segment of a capability_id) that denote a
# read-only operation. Anything ending in one of these is a `query` unless it
# is composed (then it is a `workflow`) or explicitly overridden.
READ_VERB_SUFFIXES = frozenset({
    "get",
    "search",
    "list",
    "list_log_types",
    "list_sources",
    "instances",
    "logs",
    "metrics",
    "diff",
    "affected_items",
    "categories",
    "remote_agents",
    "get_rule",
    "get_ruleset",
    "search_rulesets",
    "execute_query",
    "validate_query",
})


def _terminal_segment(capability_id: str) -> str:
    """Return the final dotted segment of a capability id (its 'verb')."""
    return capability_id.rsplit(".", 1)[-1] if capability_id else ""


def derive_kind(capability_id: str, composed: bool) -> str:
    """Classify a capability into exactly one VALID_KINDS member.

    Rules, in priority order:
      1. composed capabilities are ``workflow``;
      2. capabilities whose terminal verb is a known read verb are ``query``;
      3. everything else is a ``primitive`` (a single mutating operation).
    """
    if composed:
        return "workflow"
    if _terminal_segment(capability_id) in READ_VERB_SUFFIXES:
        return "query"
    return "primitive"


def derive_domain(capability_id: str, category: Optional[str]) -> str:
    """Determine a capability's domain.

    Prefers the explicit legacy ``category``; otherwise falls back to the
    leading dotted segment of the id (e.g. ``case_config.view.get`` -> the
    ``case_config`` domain).
    """
    if category:
        return category
    if capability_id and "." in capability_id:
        return capability_id.split(".", 1)[0]
    return capability_id or ""
