"""Regression tests for SDK write-path fixes L1, G1, G2, G3, G3a, G3b.

Response shapes are taken from the live tenant probe (docs/SDK_AGENT_REVIEW.md) and the
official Chronicle REST reference (RuleDeployment, testFindingsRefinement).
"""
import io
import json
import unittest
import urllib.error
from types import SimpleNamespace
from unittest import mock

from adapters.google_secops import GoogleSecOpsAdapter, SecOpsApiError, _extract_error_message
from agents.core.approval_policy import ApprovalPolicyError, check_approval
from engine.parsing import parse_id_list, parse_strict_bool
from engine.workflows.detection_rules import _map_rule_deployment
from engine.workflows.detection_tuning import TestFindingsRefinementWorkflow
from engine.workflows.rule_health import AuditRuleHealthWorkflow

DEP = "projects/p/locations/us/instances/i/rules/ru_1/deployment"


def _adapter():
    ad = GoogleSecOpsAdapter.__new__(GoogleSecOpsAdapter)
    ad.project_id, ad.project_number, ad.location, ad.customer_id = "proj", "123", "us", "inst"
    ad.api_base = "https://example.invalid"
    ad.calls = []

    def fake_request(method, path, params=None, body=None, timeout=None):
        ad.calls.append({"method": method, "path": path, "params": params, "body": body})
        return {}

    ad._request = fake_request
    return ad


class RuleDeploymentMappingTests(unittest.TestCase):
    """L1: the API omits false booleans and always returns runFrequency."""

    def test_disabled_rule_with_run_frequency_is_not_enabled(self):
        dep = _map_rule_deployment({"name": DEP, "runFrequency": "LIVE", "executionState": "DEFAULT"})
        self.assertFalse(dep.enabled)
        self.assertFalse(dep.alerting)
        self.assertEqual(dep.run_frequency, "LIVE")

    def test_hourly_and_daily_disabled_rules_are_not_enabled(self):
        for freq in ("HOURLY", "DAILY", "LIVE_CUSTOMIZABLE"):
            self.assertFalse(_map_rule_deployment({"name": DEP, "runFrequency": freq}).enabled, freq)

    def test_enabled_and_alerting_read_from_explicit_fields(self):
        dep = _map_rule_deployment({"name": DEP, "enabled": True, "alerting": True, "runFrequency": "LIVE"})
        self.assertTrue(dep.enabled)
        self.assertTrue(dep.alerting)
        self.assertEqual(dep.rule_id, "ru_1")

    def test_enabled_without_alerting(self):
        dep = _map_rule_deployment({"name": DEP, "enabled": True, "runFrequency": "DAILY"})
        self.assertTrue(dep.enabled)
        self.assertFalse(dep.alerting)


class RuleHealthDeploymentTests(unittest.TestCase):
    """rule_health must read enabled/alerting from RuleDeployment, not the Rule resource."""

    def _rule(self):
        return SimpleNamespace(name="projects/p/rules/ru_1", display_name="R1", run_frequency="LIVE",
                               severity="LOW", raw={})

    def _eval(self, deployment):
        wf = AuditRuleHealthWorkflow.__new__(AuditRuleHealthWorkflow)
        return wf._evaluate_rule(rule=self._rule(), errors_by_rule={}, telemetry={},
                                 latency_threshold_min=30.0, deployment=deployment)

    def test_disabled_deployment_reports_disabled(self):
        f = self._eval(_map_rule_deployment({"name": DEP, "runFrequency": "LIVE"}))
        self.assertFalse(f.enabled)
        self.assertEqual(f.status.name, "DISABLED")

    def test_enabled_not_alerting_reports_misconfigured(self):
        f = self._eval(_map_rule_deployment({"name": DEP, "enabled": True, "runFrequency": "LIVE"}))
        self.assertEqual(f.status.name, "MISCONFIGURED_ALERTING")

    def test_missing_deployment_does_not_raise_false_disabled(self):
        f = self._eval(None)
        self.assertTrue(f.enabled)
        self.assertEqual(f.status.name, "HEALTHY")

    def test_collect_deployments_paginates(self):
        pages = {
            None: {"ruleDeployments": [{"name": DEP, "enabled": True}], "nextPageToken": "t2"},
            "t2": {"ruleDeployments": [{"name": DEP.replace("ru_1", "ru_2")}]},
        }
        adapter = SimpleNamespace(list_rule_deployments=lambda page_size, page_token=None: pages[page_token])
        wf = AuditRuleHealthWorkflow(adapter)
        deps = wf._collect_deployments()
        self.assertTrue(deps["ru_1"].enabled)
        self.assertFalse(deps["ru_2"].enabled)


class ParsingHelperTests(unittest.TestCase):
    def test_strict_bool(self):
        for v, want in ((True, True), (False, False), (None, None), ("false", False), ("TRUE", True),
                        (" 0 ", False), ("1", True), (0, False), (1, True)):
            self.assertIs(parse_strict_bool(v), want, v)
        for bad in ("no", "yes", "", "off", 2, 1.0, [], {}):
            with self.assertRaises(ValueError, msg=repr(bad)):
                parse_strict_bool(bad)

    def test_id_list(self):
        self.assertEqual(parse_id_list("ur_1"), ["ur_1"])
        self.assertEqual(parse_id_list("ur_1, ur_2,,ur_1"), ["ur_1", "ur_2"])
        self.assertEqual(parse_id_list(("ur_1",)), ["ur_1"])
        self.assertEqual(parse_id_list(None), [])
        with self.assertRaises(ValueError):
            parse_id_list(5)
        with self.assertRaises(ValueError):
            parse_id_list(["ur_1", 5])


class AdapterWritePathTests(unittest.TestCase):
    """G1 at the adapter boundary (defence in depth)."""

    def test_create_refinement_with_string_rule_id_is_not_split(self):
        ad = _adapter()
        ad.create_findings_refinement(display_name="x", query="principal.hostname = \"a\"", curated_rule_ids="ur_1")
        rules = ad.calls[0]["body"]["detectionExclusionApplication"]["curatedRules"]
        self.assertEqual(rules, ["projects/123/locations/us/instances/inst/curatedRules/ur_1"])

    def test_test_refinement_with_string_rule_id_is_not_split(self):
        ad = _adapter()
        ad.test_findings_refinement(curated_rule_ids="ur_1", query="q", start_time="s", end_time="e")
        rules = ad.calls[0]["body"]["detectionExclusionApplication"]["curatedRules"]
        self.assertEqual(len(rules), 1)
        self.assertTrue(rules[0].endswith("/curatedRules/ur_1"))

    def test_full_resource_names_pass_through(self):
        ad = _adapter()
        full = "projects/9/locations/us/instances/x/curatedRules/ur_9"
        ad.create_findings_refinement(display_name="x", query="q", curated_rule_ids=[full])
        self.assertEqual(ad.calls[0]["body"]["detectionExclusionApplication"]["curatedRules"], [full])

    def test_test_refinement_accepts_single_object_response(self):
        # API reference documents {"activity": {...}}; the live tenant returned an array.
        ad = _adapter()
        ad._request = lambda *a, **k: {"activity": {"detectionExclusionActivity": {}}}
        self.assertEqual(len(ad.test_findings_refinement(["ur_1"], "q", "s", "e")), 1)


class FacadeCoercionTests(unittest.TestCase):
    """G1/G2 at the facade: LLM tool calls and GENERIC_CAPABILITY enter here."""

    def setUp(self):
        from engine.facade import SecOpsEngine
        self.engine = SecOpsEngine.__new__(SecOpsEngine)
        self.update_wf = mock.Mock()
        self.create_wf = mock.Mock()
        self.test_wf = mock.Mock()
        self.engine.__dict__["_update_rule_deployment_wf"] = self.update_wf
        self.engine.__dict__["_manage_findings_refinements_wf"] = self.create_wf
        self.engine.__dict__["_test_findings_refinement_wf"] = self.test_wf

    def test_update_rule_deployment_string_false_becomes_bool(self):
        self.engine.update_rule_deployment("ru_1", enabled="false", alerting="true")
        kw = self.update_wf.execute.call_args.kwargs
        self.assertIs(kw["enabled"], False)
        self.assertIs(kw["alerting"], True)

    def test_update_rule_deployment_rejects_ambiguous(self):
        with self.assertRaises(ValueError):
            self.engine.update_rule_deployment("ru_1", enabled="off")
        self.update_wf.execute.assert_not_called()

    def test_create_refinement_string_rule_id_becomes_list(self):
        self.engine.create_findings_refinement(display_name="x", query="q", curated_rule_ids="ur_1")
        self.assertEqual(self.create_wf.create_refinement.call_args.kwargs["curated_rule_ids"], ["ur_1"])

    def test_create_refinement_empty_ids_stays_none(self):
        self.engine.create_findings_refinement(display_name="x", query="q", curated_rule_ids="")
        self.assertIsNone(self.create_wf.create_refinement.call_args.kwargs["curated_rule_ids"])

    def test_test_refinement_string_rule_id_becomes_list(self):
        self.engine.test_findings_refinement(curated_rule_ids="ur_1", query="q")
        self.assertEqual(self.test_wf.execute.call_args.kwargs["curated_rule_ids"], ["ur_1"])


class ErrorBodyTests(unittest.TestCase):
    """G3b: :testFindingsRefinement returns errors as a JSON array."""

    ARRAY_BODY = json.dumps([{"error": {"code": 400, "status": "INVALID_ARGUMENT",
                                        "message": "one or more conditions are invalid: 1:21 no viable alternative"}}])

    def test_array_body(self):
        self.assertEqual(_extract_error_message(self.ARRAY_BODY),
                         "one or more conditions are invalid: 1:21 no viable alternative")

    def test_object_body(self):
        self.assertEqual(_extract_error_message('{"error": {"message": "nope"}}'), "nope")

    def test_non_json_and_odd_shapes_fall_back_to_raw(self):
        for raw in ("<html>502</html>", "[]", '{"foo": 1}', '["x"]'):
            self.assertEqual(_extract_error_message(raw), raw)

    def test_request_raises_typed_error_with_clean_message(self):
        ad = GoogleSecOpsAdapter.__new__(GoogleSecOpsAdapter)
        ad.api_base = "https://example.invalid"
        ad._get_auth_token = lambda: "t"
        err = urllib.error.HTTPError("u", 400, "Bad", {}, io.BytesIO(self.ARRAY_BODY.encode()))
        with mock.patch("urllib.request.urlopen", side_effect=err):
            with self.assertRaises(SecOpsApiError) as ctx:
                ad._request("POST", "/x", body={})
        self.assertEqual(ctx.exception.status, 400)
        self.assertIsInstance(ctx.exception, RuntimeError)
        self.assertEqual(str(ctx.exception),
                         "Google SecOps API Error [400]: one or more conditions are invalid: 1:21 no viable alternative")


class RefinementTestCacheTests(unittest.TestCase):
    """G3a: very low quota on :testFindingsRefinement."""

    RESP = [{"activity": {"detectionExclusionActivity": {"detectionExclusionDetectorActivities": [
        {"curatedRule": "ur_1", "totalDetectionCount": "10", "excludedDetectionCount": "4"}]}}}]

    def test_success_is_cached_per_query_and_rules(self):
        adapter = mock.Mock()
        adapter.test_findings_refinement.return_value = self.RESP
        wf = TestFindingsRefinementWorkflow(adapter)
        args = dict(start_time="s", end_time="e")
        r1 = wf.execute(curated_rule_ids=["ur_1"], query="q ", **args)
        r2 = wf.execute(curated_rule_ids=["projects/x/curatedRules/ur_1"], query="q", **args)
        self.assertEqual(adapter.test_findings_refinement.call_count, 1)
        self.assertIs(r1, r2)
        self.assertAlmostEqual(r1.suppression_ratio, 0.4)
        wf.execute(curated_rule_ids=["ur_1"], query="other", **args)
        self.assertEqual(adapter.test_findings_refinement.call_count, 2)

    def test_errors_are_not_cached(self):
        adapter = mock.Mock()
        adapter.test_findings_refinement.side_effect = [SecOpsApiError(429, "quota"), self.RESP]
        wf = TestFindingsRefinementWorkflow(adapter)
        with self.assertRaises(SecOpsApiError):
            wf.execute(curated_rule_ids=["ur_1"], query="q", start_time="s", end_time="e")
        wf.execute(curated_rule_ids=["ur_1"], query="q", start_time="s", end_time="e")
        self.assertEqual(adapter.test_findings_refinement.call_count, 2)


class TuningPreflightTests(unittest.TestCase):
    """G3: refinement proposals are preflighted with testFindingsRefinement, not verify_rule."""

    def _agent(self, engine):
        from agents.generated.detection_tuning_agent import DetectionTuningAgentAgent
        agent = DetectionTuningAgentAgent.__new__(DetectionTuningAgentAgent)
        agent.engine = engine
        agent.evidence_store = None
        agent.captured = {}

        def submit_proposal(**kw):
            agent.captured = kw
            return SimpleNamespace(id="p-1")

        agent.submit_proposal = submit_proposal
        return agent

    def _submit(self, agent):
        return agent.submit_tuning_proposal(
            title="t", rule_id="ur_1", rationale="r", proposed_diff="d",
            tuned_rule_text="// header\nprincipal.hostname = \"build-1\"",
            unsuppressed_trigger_count=10, projected_suppressed_count=4,
            noise_reduction_pct=40.0, preserved_real_alerts=6,
        )

    def test_valid_query_is_verified_with_refinement_test(self):
        engine = mock.Mock()
        engine.test_findings_refinement.return_value = SimpleNamespace(
            total_detections=10, excluded_detections=4, suppression_ratio=0.4)
        agent = self._agent(engine)
        res = self._submit(agent)
        engine.verify_rule.assert_not_called()
        engine.test_findings_refinement.assert_called_once_with(
            curated_rule_ids=["ur_1"], query='principal.hostname = "build-1"')
        self.assertTrue(res["syntax_verified"])
        pf = agent.captured["preflight"]
        self.assertEqual(pf.details["preflight_status"], "VERIFIED")
        self.assertEqual(agent.captured["mutation_payload"]["refinement_query"], 'principal.hostname = "build-1"')

    def test_400_marks_invalid(self):
        engine = mock.Mock()
        engine.test_findings_refinement.side_effect = SecOpsApiError(400, "no viable alternative")
        agent = self._agent(engine)
        self.assertFalse(self._submit(agent)["syntax_verified"])
        pf = agent.captured["preflight"]
        self.assertEqual(pf.details["preflight_status"], "INVALID")
        self.assertIn("no viable alternative", pf.compiler_diagnostics[0])

    def test_429_marks_unverified_not_invalid(self):
        engine = mock.Mock()
        engine.test_findings_refinement.side_effect = SecOpsApiError(429, "quota")
        agent = self._agent(engine)
        self.assertFalse(self._submit(agent)["syntax_verified"])
        pf = agent.captured["preflight"]
        self.assertEqual(pf.details["preflight_status"], "UNVERIFIED")
        self.assertIn("429", pf.compiler_diagnostics[0])


class RefinementApprovalGateTests(unittest.TestCase):
    def test_unverified_refinement_needs_override(self):
        with self.assertRaises(ApprovalPolicyError) as ctx:
            check_approval(author="@detection-tuning-agent", approver="alice@corp",
                              action_type="CREATE_FINDINGS_REFINEMENT", risk_level="MEDIUM",
                              stored_tier=None, syntax_verified=False)
        self.assertEqual(ctx.exception.code, ApprovalPolicyError.PREFLIGHT_FAILED)

    def test_verified_refinement_passes(self):
        check_approval(author="@detection-tuning-agent", approver="alice@corp",
                          action_type="CREATE_FINDINGS_REFINEMENT", risk_level="MEDIUM",
                          stored_tier=None, syntax_verified=True)


if __name__ == "__main__":
    unittest.main()
