"""Taxonomy tests: lock in `kind`/`domain` (Step 2) and result-set
`cardinality` + require-filter policy (Step 4) derivation and invariants.

These are unit tests on the pure derivation functions plus structural
assertions over the live registry. They guarantee that the classification
model stays coherent as capabilities are added or hand-tuned.
"""

import unittest
from collections import Counter

from engine.registry import WorkflowCapability, WorkflowRegistry
from engine.taxonomy import (
    REQUIRE_FILTER_POLICY_KEY,
    VALID_CARDINALITIES,
    VALID_KINDS,
    derive_cardinality,
    derive_domain,
    derive_kind,
)


def _build_registry():
    """Construct the full engine registry against an inert adapter (offline)."""
    from engine.facade import SecOpsEngine

    class _InertAdapter:
        def __getattr__(self, name):
            def _boom(*_a, **_k):
                raise RuntimeError(f"inert adapter: {name} must not be called")
            return _boom

    engine = SecOpsEngine(adapter=_InertAdapter(), custom_registry=WorkflowRegistry())
    return engine.registry


class DeriveKindTest(unittest.TestCase):
    def test_composed_is_workflow(self):
        self.assertEqual(derive_kind("case.investigate", composed=True), "workflow")
        # composed wins even over a read verb suffix.
        self.assertEqual(derive_kind("dashboard.get", composed=True), "workflow")

    def test_read_verbs_are_queries(self):
        for cid in ("feed.get", "case.search", "case_config.stage.list",
                    "curated_detections.metrics", "marketplace_integration.diff",
                    "dashboard.execute_query", "dashboard.validate_query"):
            self.assertEqual(derive_kind(cid, composed=False), "query", cid)

    def test_write_verbs_are_primitives(self):
        for cid in ("case.comment", "rule.create", "alert.update", "feed.enable"):
            self.assertEqual(derive_kind(cid, composed=False), "primitive", cid)

    def test_all_derived_kinds_are_valid(self):
        for cid in ("case.comment", "case.search", "case.investigate"):
            self.assertIn(
                derive_kind(cid, composed=cid.endswith("investigate")), VALID_KINDS
            )


class DeriveDomainTest(unittest.TestCase):
    def test_category_is_preferred(self):
        self.assertEqual(derive_domain("case_config.view.get", "case_config"), "case_config")

    def test_falls_back_to_leading_segment(self):
        self.assertEqual(derive_domain("case_config.view.get", None), "case_config")
        self.assertEqual(derive_domain("search.udm", ""), "search")

    def test_degenerate_id(self):
        self.assertEqual(derive_domain("solo", None), "solo")


class DeriveCardinalityTest(unittest.TestCase):
    def test_nonquery_has_no_cardinality(self):
        self.assertIsNone(derive_cardinality("x.run", kind="primitive"))
        self.assertIsNone(derive_cardinality("x.investigate", kind="workflow"))

    def test_single_result_verbs(self):
        for cid in ("feed.get", "curated_detections.get_rule",
                    "marketplace_integration.diff", "curated_detections.metrics"):
            self.assertEqual(derive_cardinality(cid, "query"), "single", cid)

    def test_bounded_caller_supplied_verbs(self):
        for cid in ("dashboard.execute_query", "dashboard.validate_query"):
            self.assertEqual(derive_cardinality(cid, "query"), "bounded", cid)

    def test_collection_verbs_are_unbounded(self):
        for cid in ("case.search", "case_config.stage.list",
                    "integration.instances", "job.logs",
                    "content_pack.categories", "feed_schema.list_sources"):
            self.assertEqual(derive_cardinality(cid, "query"), "unbounded", cid)

    def test_unknown_query_verb_fails_safe_to_unbounded(self):
        self.assertEqual(derive_cardinality("x.frobnicate", "query"), "unbounded")

    def test_all_derived_cardinalities_are_valid(self):
        for cid, kind in (("a.get","query"),("b.search","query"),
                          ("c.execute_query","query"),("d.run","primitive")):
            card = derive_cardinality(cid, kind)
            if card is not None:
                self.assertIn(card, VALID_CARDINALITIES, cid)


class CapabilityConstructionTest(unittest.TestCase):
    def test_explicit_kind_overrides_derivation(self):
        cap = WorkflowCapability(
            capability_id="x.get", name="x", description="d",
            category="x", handler=lambda: None, kind="primitive",
        )
        self.assertEqual(cap.kind, "primitive")  # explicit beats derived 'query'

    def test_invalid_explicit_kind_rejected(self):
        with self.assertRaises(ValueError):
            WorkflowCapability(
                capability_id="x.get", name="x", description="d",
                category="x", handler=lambda: None, kind="mutation",
            )

    def test_query_with_side_effects_rejected(self):
        with self.assertRaises(ValueError):
            WorkflowCapability(
                capability_id="x.get", name="x", description="d",
                category="x", handler=lambda: None,
                kind="query", side_effects=["writes_case"],
            )

    def test_domain_autofilled_from_category(self):
        cap = WorkflowCapability(
            capability_id="x.y", name="x", description="d",
            category="mydomain", handler=lambda: None,
        )
        self.assertEqual(cap.domain, "mydomain")

    def test_unbounded_query_autoattaches_require_filter_policy(self):
        cap = WorkflowCapability(
            capability_id="x.search", name="x", description="d",
            category="x", handler=lambda: None,
        )
        self.assertEqual(cap.cardinality, "unbounded")
        self.assertTrue(cap.agent.get(REQUIRE_FILTER_POLICY_KEY))

    def test_single_query_has_no_filter_policy(self):
        cap = WorkflowCapability(
            capability_id="x.get", name="x", description="d",
            category="x", handler=lambda: None,
        )
        self.assertEqual(cap.cardinality, "single")
        self.assertNotIn(REQUIRE_FILTER_POLICY_KEY, cap.agent)

    def test_explicit_bounded_cardinality_overrides_and_skips_policy(self):
        # A verified finite enumeration: caller tags it bounded, so no filter
        # is forced despite the collection-shaped ".list" verb.
        cap = WorkflowCapability(
            capability_id="x.list", name="x", description="d",
            category="x", handler=lambda: None, cardinality="bounded",
        )
        self.assertEqual(cap.cardinality, "bounded")
        self.assertNotIn(REQUIRE_FILTER_POLICY_KEY, cap.agent)

    def test_operator_can_preserve_explicit_no_filter_decision(self):
        # An explicit False must be respected (human-justified escape hatch),
        # not silently overwritten by the auto-attach default.
        cap = WorkflowCapability(
            capability_id="x.search", name="x", description="d",
            category="x", handler=lambda: None,
            agent={REQUIRE_FILTER_POLICY_KEY: False},
        )
        self.assertEqual(cap.cardinality, "unbounded")
        self.assertIs(cap.agent[REQUIRE_FILTER_POLICY_KEY], False)

    def test_invalid_cardinality_rejected(self):
        with self.assertRaises(ValueError):
            WorkflowCapability(
                capability_id="x.get", name="x", description="d",
                category="x", handler=lambda: None, cardinality="infinite",
            )

    def test_nonquery_with_cardinality_rejected(self):
        with self.assertRaises(ValueError):
            WorkflowCapability(
                capability_id="x.run", name="x", description="d",
                category="x", handler=lambda: None,
                kind="primitive", cardinality="single",
            )


class LiveRegistryTaxonomyTest(unittest.TestCase):
    def setUp(self):
        self.caps = _build_registry().list_capabilities()

    def test_every_capability_has_valid_kind_and_domain(self):
        for c in self.caps:
            self.assertIn(c.kind, VALID_KINDS, c.capability_id)
            self.assertTrue(c.domain, f"{c.capability_id}: empty domain")

    def test_workflows_are_exactly_the_composed_capabilities(self):
        workflows = {c.capability_id for c in self.caps if c.kind == "workflow"}
        composed = {c.capability_id for c in self.caps if c.composed}
        self.assertEqual(workflows, composed)

    def test_queries_are_side_effect_free(self):
        for c in self.caps:
            if c.kind == "query":
                self.assertEqual(list(c.side_effects), [], c.capability_id)

    def test_kind_distribution_is_sane(self):
        """Guard against a derivation bug collapsing everything into one kind."""
        dist = Counter(c.kind for c in self.caps)
        self.assertGreater(dist["query"], 0)
        self.assertGreater(dist["workflow"], 0)
        # Total must still be the full corpus.
        self.assertEqual(sum(dist.values()), len(self.caps))

    def test_only_queries_carry_cardinality(self):
        for c in self.caps:
            if c.kind == "query":
                self.assertIn(c.cardinality, VALID_CARDINALITIES, c.capability_id)
            else:
                self.assertIsNone(c.cardinality, c.capability_id)

    def test_every_unbounded_capability_requires_a_filter(self):
        # This is the live, non-vacuous form of the Step 4 contract invariant.
        offenders = [
            c.capability_id for c in self.caps
            if c.cardinality == "unbounded"
            and not c.agent.get(REQUIRE_FILTER_POLICY_KEY)
        ]
        self.assertEqual(offenders, [], f"unbounded without filter: {offenders}")

    def test_unbounded_population_is_nonempty(self):
        # Guard against a derivation regression making the Step 4 check vacuous.
        unbounded = [c for c in self.caps if c.cardinality == "unbounded"]
        self.assertGreater(len(unbounded), 0)



if __name__ == "__main__":
    unittest.main()
