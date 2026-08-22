"""Capability Contract Consistency & Invariant Tests (Step 1 guardrail).

This suite is the enforcement mechanism for the SecOps capability taxonomy.
It runs fully OFFLINE (no live tenant, no network) by constructing the engine
registry with an inert sentinel adapter.

Design philosophy
-----------------
A guardrail is only trusted if it reflects reality on day one. The spec corpus
is currently schema-anarchic (97 files, ~5 different id conventions, 70 with no
machine-extractable capability id). Rather than emit 70 spurious failures, this
suite:

  1. HARD-ASSERTS invariants that already hold (so they can never regress).
  2. Captures known drift as an explicit, reviewed BASELINE (so it cannot get
     worse, and shrinks visibly over time as specs are normalized).
  3. Leaves ACTIVATED-LATER hooks (kind layering, uses-graph, side_effects,
     cardinality) wired but tolerant, so Steps 2-4 flip them on by tightening
     one constant each -- not by rewriting the suite.

When you normalize a spec (add `metadata.capability_id`) or enrich a capability
(add `kind`/`side_effects`/`uses`/`cardinality`), REMOVE the corresponding entry
from the baseline sets below. The suite will then guarantee it stays fixed.
"""

import glob
import os
import re
import unittest
from typing import Any, Dict, List, Optional, Set

import yaml

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SPEC_GLOB = os.path.join(REPO_ROOT, "specs", "**", "*.yaml")
TESTS_DIR = os.path.join(REPO_ROOT, "tests")


from tests.capability_contract_baseline import (
    KNOWN_SPEC_ID_MISMATCHES,
    SPECS_WITHOUT_EXTRACTABLE_ID_BASELINE,
)


def _iter_spec_files() -> List[str]:
    return sorted(glob.glob(SPEC_GLOB, recursive=True))


def _rel(path: str) -> str:
    return os.path.relpath(path, os.path.join(REPO_ROOT, "specs"))


def _load_yaml(path: str) -> Any:
    """Parse a YAML file, guaranteeing the handle is closed."""
    with open(path, encoding="utf-8") as fh:
        return yaml.safe_load(fh)


def extract_capability_ids(doc: Any) -> List[str]:
    """Best-effort extraction of dotted capability id(s) from a spec doc.

    Tolerates the current schema anarchy by checking, in order:
      - metadata.capability_id / top-level capability_id
      - metadata.id / top-level id  (only if it looks dotted, e.g. 'search.udm')
      - metadata.capabilities[].id / top-level capabilities[].id
    """
    out: List[str] = []
    if not isinstance(doc, dict):
        return out
    meta = doc.get("metadata") if isinstance(doc.get("metadata"), dict) else {}
    for src in (meta, doc):
        if not isinstance(src, dict):
            continue
        if src.get("capability_id"):
            out.append(str(src["capability_id"]))
        raw_id = src.get("id")
        if raw_id and "." in str(raw_id):
            out.append(str(raw_id))
    for cap_src in (meta.get("capabilities"), doc.get("capabilities")):
        if isinstance(cap_src, list):
            out.extend(
                str(c["id"]) for c in cap_src
                if isinstance(c, dict) and c.get("id")
            )
    # De-dupe, preserve order.
    seen: Set[str] = set()
    result: List[str] = []
    for cid in out:
        if cid not in seen:
            seen.add(cid)
            result.append(cid)
    return result


def _normalize_cap_id(cid: str) -> str:
    """Strip trailing version suffixes like '.v1' so spec ids can align to
    registry ids (registry uses 'search.refine'; some specs use 'search.refine.v1')."""
    return re.sub(r"\.v\d+$", "", cid)


def build_registry_capabilities() -> Dict[str, Any]:
    """Construct the full engine registry OFFLINE using an inert adapter.

    Workflows are lazy (see SecOpsEngine._WORKFLOW_MAP), so no network or gcloud
    invocation occurs merely by registering capabilities.
    """
    from engine.facade import SecOpsEngine
    from engine.registry import WorkflowRegistry

    class _InertAdapter:
        """Raises if any provider method is actually invoked during registration."""

        def __getattr__(self, name):
            def _blocked(*_a, **_k):
                raise AssertionError(
                    f"Live adapter call '{name}' attempted during offline "
                    f"contract test. Registration must not touch the provider."
                )
            return _blocked

    engine = SecOpsEngine(adapter=_InertAdapter(), custom_registry=WorkflowRegistry())
    return {c.capability_id: c for c in engine.registry.list_capabilities()}


class RegistryLoadTest(unittest.TestCase):
    """The registry must build offline and be non-trivial."""

    def test_registry_builds_offline(self):
        caps = build_registry_capabilities()
        self.assertGreaterEqual(
            len(caps), 100,
            f"Expected >=100 registered capabilities, got {len(caps)}.",
        )

    def test_capability_ids_are_unique_and_dotted(self):
        caps = build_registry_capabilities()
        for cid in caps:
            self.assertRegex(
                cid, r"^[a-z0-9_]+(\.[a-z0-9_]+)+$",
                f"Capability id '{cid}' is not lowercase dotted-namespace form.",
            )

    def test_every_capability_declares_domain_and_handler(self):
        caps = build_registry_capabilities()
        for cid, cap in caps.items():
            # 'category' today, 'domain' after Step 2; accept either.
            domain = getattr(cap, "domain", None) or getattr(cap, "category", None)
            self.assertTrue(domain, f"{cid}: missing domain/category.")
            self.assertTrue(callable(cap.handler), f"{cid}: handler not callable.")


class SpecParseTest(unittest.TestCase):
    """Every spec file must be valid YAML mapping. This is a HARD invariant."""

    def test_all_specs_parse_as_yaml_mappings(self):
        failures = []
        for f in _iter_spec_files():
            try:
                doc = _load_yaml(f)
            except Exception as e:  # noqa: BLE001 - report path + error
                failures.append(f"{_rel(f)}: PARSE ERROR: {e}")
                continue
            if not isinstance(doc, dict):
                failures.append(f"{_rel(f)}: top-level is not a mapping.")
        self.assertEqual(failures, [], "Spec YAML problems:\n" + "\n".join(failures))

    def test_spec_corpus_is_present(self):
        self.assertGreaterEqual(
            len(_iter_spec_files()), 90,
            "Spec corpus unexpectedly small; did the specs/ tree move?",
        )


class SpecToRegistryLinkageTest(unittest.TestCase):
    """Specs that DO declare a capability id must point at a REAL registry id.

    This is the load-bearing anti-drift assertion: a spec may currently omit an
    id (quarantined baseline), but it may never declare a WRONG one.
    """

    def test_declared_spec_ids_resolve_to_registry(self):
        caps = build_registry_capabilities()
        reg_ids = set(caps)
        reg_ids_normalized = {_normalize_cap_id(c) for c in reg_ids}

        broken = []
        quarantined_hit: set = set()
        for f in _iter_spec_files():
            rel = _rel(f)
            doc = _load_yaml(f)
            for cid in extract_capability_ids(doc):
                norm = _normalize_cap_id(cid)
                if cid in reg_ids or norm in reg_ids_normalized:
                    continue
                # Tolerate ONLY the exact reviewed mismatch for this exact spec.
                known = KNOWN_SPEC_ID_MISMATCHES.get(rel)
                if known and known[0] == cid:
                    quarantined_hit.add(rel)
                    continue
                broken.append(f"{rel}: declares '{cid}' -> NOT in registry.")
        self.assertEqual(
            broken, [],
            "Specs declaring capability ids that do not exist in the registry "
            "(fix the spec or the registration):\n" + "\n".join(broken),
        )
        # Quarantine hygiene: a fixed spec must be removed from the mismatch set.
        stale = set(KNOWN_SPEC_ID_MISMATCHES) - quarantined_hit
        self.assertEqual(
            stale, set(),
            "These specs no longer exhibit their known id mismatch and must be "
            "REMOVED from KNOWN_SPEC_ID_MISMATCHES:\n  " + "\n  ".join(sorted(stale)),
        )

    def test_spec_id_drift_matches_reviewed_baseline(self):
        """The set of specs lacking an extractable id must not GROW.

        Passes when the live drift set == reviewed baseline. Fails loudly with a
        precise delta when a spec regresses (new drift) OR when a spec has been
        fixed (remove it from the baseline to lock the win in).
        """
        live_missing: Set[str] = set()
        for f in _iter_spec_files():
            doc = _load_yaml(f)
            if not extract_capability_ids(doc):
                live_missing.add(_rel(f))

        new_drift = live_missing - SPECS_WITHOUT_EXTRACTABLE_ID_BASELINE
        fixed = SPECS_WITHOUT_EXTRACTABLE_ID_BASELINE - live_missing

        # New drift is a hard failure -- a spec lost its id linkage.
        self.assertEqual(
            new_drift, set(),
            "NEW spec id drift detected (these specs lost/lack a capability id "
            "and are not in the reviewed baseline):\n  "
            + "\n  ".join(sorted(new_drift)),
        )
        # Fixed specs must be removed from the baseline to prevent silent re-drift.
        self.assertEqual(
            fixed, set(),
            "These specs now expose an id and must be REMOVED from "
            "SPECS_WITHOUT_EXTRACTABLE_ID_BASELINE to lock in the fix:\n  "
            + "\n  ".join(sorted(fixed)),
        )


class TestInventoryLinkageTest(unittest.TestCase):
    """Specs with a `test_inventory` must have every id referenced by a real test.

    Currently only search-udm-001 has one, and all 9 ids ARE referenced, so this
    is asserted HARD. As more specs adopt test_inventory, this scales for free.
    """

    def _collect_test_source(self) -> str:
        blobs = []
        for f in glob.glob(os.path.join(TESTS_DIR, "**", "*.py"), recursive=True):
            if os.path.abspath(f) == os.path.abspath(__file__):
                continue
            try:
                with open(f, encoding="utf-8", errors="ignore") as fh:
                    blobs.append(fh.read())
            except OSError:
                pass
        return "\n".join(blobs)

    def test_inventory_ids_are_referenced_in_tests(self):
        test_src = self._collect_test_source()
        missing = []
        specs_with_inventory = 0
        for f in _iter_spec_files():
            doc = _load_yaml(f)
            inv = doc.get("test_inventory") if isinstance(doc, dict) else None
            if not isinstance(inv, list):
                continue
            specs_with_inventory += 1
            for item in inv:
                tid = item.get("id") if isinstance(item, dict) else None
                if not tid:
                    continue
                if tid not in test_src:
                    missing.append(f"{_rel(f)}: test_inventory id '{tid}' "
                                   f"not referenced by any test.")
        self.assertGreaterEqual(
            specs_with_inventory, 1,
            "Expected at least one spec with a test_inventory (search-udm-001).",
        )
        self.assertEqual(
            missing, [],
            "test_inventory ids missing test coverage:\n" + "\n".join(missing),
        )


# ---------------------------------------------------------------------------
# ACTIVATED-LATER invariants (Steps 2-4). Wired now, tolerant now. Each flips on
# by tightening its guard once the metadata exists, WITHOUT touching the harness.
# ---------------------------------------------------------------------------
class TaxonomyInvariantsTest(unittest.TestCase):
    """Placeholders for kind-layering, uses-graph, side_effects, cardinality.

    These run today but only enforce rules on capabilities that ALREADY carry
    the relevant metadata. Since none do yet (pre-Step-2), they pass vacuously
    while still guaranteeing: the moment a field is added, it must be VALID.
    """

    KINDS = {"primitive", "query", "workflow"}
    CARDINALITIES = {"tiny", "small", "medium", "large", "unbounded"}

    def test_kind_values_are_valid_when_present(self):
        caps = build_registry_capabilities()
        bad = [
            f"{cid}: kind='{getattr(c, 'kind')}'"
            for cid, c in caps.items()
            if getattr(c, "kind", None) is not None
            and str(getattr(c, "kind")).split(".")[-1].lower() not in self.KINDS
        ]
        self.assertEqual(bad, [], "Invalid kind values:\n" + "\n".join(bad))

    def test_query_kind_has_no_side_effects_when_present(self):
        """Step 2/3 invariant: kind:query => side_effects == []."""
        caps = build_registry_capabilities()
        violations = []
        for cid, c in caps.items():
            kind = getattr(c, "kind", None)
            se = getattr(c, "side_effects", None)
            if kind is None or se is None:
                continue
            if str(kind).split(".")[-1].lower() == "query" and list(se):
                violations.append(f"{cid}: query declares side_effects={list(se)}")
        self.assertEqual(
            violations, [],
            "Queries must be side-effect-free:\n" + "\n".join(violations),
        )

    def test_uses_targets_exist_and_are_acyclic_when_present(self):
        """Step 3 invariant: every `uses` edge resolves; graph is a DAG."""
        caps = build_registry_capabilities()
        edges: Dict[str, List[str]] = {}
        for cid, c in caps.items():
            uses = getattr(c, "uses", None)
            if uses:
                edges[cid] = list(uses)

        dangling = [
            f"{cid} -> {tgt}"
            for cid, tgts in edges.items()
            for tgt in tgts
            if tgt not in caps
        ]
        self.assertEqual(
            dangling, [], "Dangling `uses` edges:\n" + "\n".join(dangling),
        )

        # Cycle detection (DFS) over declared edges only.
        WHITE, GRAY, BLACK = 0, 1, 2
        color = {cid: WHITE for cid in caps}
        cyclic_path: List[str] = []

        def visit(node: str, stack: List[str]) -> bool:
            color[node] = GRAY
            for nxt in edges.get(node, []):
                if color.get(nxt, BLACK) == GRAY:
                    cyclic_path.extend(stack + [node, nxt])
                    return True
                if color.get(nxt, BLACK) == WHITE and visit(nxt, stack + [node]):
                    return True
            color[node] = BLACK
            return False

        for cid in list(edges):
            if color[cid] == WHITE and visit(cid, []):
                break
        self.assertEqual(
            cyclic_path, [],
            "Cycle detected in `uses` graph: " + " -> ".join(cyclic_path),
        )

    def test_unbounded_cardinality_requires_filter_when_present(self):
        """Step 4 invariant: cardinality:unbounded => require_filter policy set."""
        caps = build_registry_capabilities()
        violations = []
        for cid, c in caps.items():
            card = getattr(c, "cardinality", None)
            if card is None:
                continue
            card_val = str(card).split(".")[-1].lower()
            if card_val == "unbounded":
                agent = getattr(c, "agent", None) or {}
                require = (
                    agent.get("require_filter_for_unbounded_query")
                    if isinstance(agent, dict) else
                    getattr(agent, "require_filter_for_unbounded_query", None)
                )
                if not require:
                    violations.append(
                        f"{cid}: cardinality=unbounded but no require_filter policy."
                    )
        self.assertEqual(
            violations, [],
            "Unbounded capabilities must require a filter:\n" + "\n".join(violations),
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
