"""Unit tests verifying Phase 0 write-path guards and tenant mutation boundaries."""

from pathlib import Path
import os
import tempfile
import unittest
from unittest.mock import patch

from adapters.google_secops import GoogleSecOpsAdapter
from agents.core.approval_policy import ApprovalPolicyError, check_approval, required_tier
from agents.core.proposal_manager import ChangeProposal, PreflightProof, ProposalManager
from agents.generated import create_agent_fleet
from agents.generated.identity_governor import IdentityGovernorAgent
from agents.generated.logjammer_agent import LogjammerAgentAgent
from agents.generated.yaral_optimizer import YaralOptimizerAgent
from engine.config import SecOpsConfigurationError, resolve_inventory_base_url
from engine.domain import AuthorityTier
from engine.facade import SecOpsEngine
from engine.registry import WorkflowCapability, WorkflowRegistry
from engine.taxonomy import has_tenant_side_effects


class _InertAdapter:
    project_id = "proj-alpha"
    project_number = "12345"
    customer_id = "cust-111"
    location = "us"

    def __getattr__(self, name: str):
        def _blocked(*_a, **_kw):
            raise AssertionError(f"Unexpected live adapter call: {name}")
        return _blocked


class Phase0CapabilityAndAgentGuardsTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.engine = SecOpsEngine(adapter=_InertAdapter(), custom_registry=WorkflowRegistry())
        self.prop_mgr = ProposalManager(root_dir=Path(self._tmp.name) / "ledger")
        self.fleet = create_agent_fleet(engine=self.engine, proposal_manager=self.prop_mgr)

    def test_every_primitive_declares_side_effects(self):
        missing = [
            c.capability_id
            for c in self.engine.registry.list_capabilities()
            if c.kind == "primitive" and not c.side_effects
        ]
        self.assertEqual(missing, [], f"Primitives missing side_effects: {missing}")

    def test_bind_capability_rejects_tenant_mutating_capabilities(self):
        from engine.agent_tools import is_read_only_capability
        from engine.taxonomy import is_tenant_read_only_capability

        agent = self.fleet["@raw-log-agent"]
        for cap_id in (
            "rule.patch",
            "case.detection.correlate",
            "case.triage",
            "case.orchestrate_triage",
            "case.ai_investigate",
            "case.get_summary",
            "case_alert.get_recommendation",
        ):
            cap = self.engine.registry.get(cap_id)
            self.assertIsNotNone(cap, cap_id)
            self.assertFalse(is_read_only_capability(cap, self.engine.registry), cap_id)
            with self.assertRaisesRegex(ValueError, "cannot bind tenant-mutating capability"):
                agent.bind_capability(cap)

        # Verify bind_capability and is_read_only_capability agree across the entire registry
        disagreements = [
            c.capability_id
            for c in self.engine.registry.list_capabilities()
            if is_tenant_read_only_capability(c, self.engine.registry)
            != is_read_only_capability(c, self.engine.registry)
        ]
        self.assertEqual(disagreements, [])

    def test_bind_capability_enforces_unbounded_query_filter_before_defaults(self):
        agent = self.fleet["@raw-log-agent"]
        calls = []
        unbounded_cap = WorkflowCapability(
            capability_id="phase0_audit.search",
            name="Search Phase0 Audit",
            description="Unbounded search capability for policy testing.",
            category="search",
            handler=lambda query="", state="ALL", limit=50: (
                calls.append((query, state, limit)) or {"query": query, "state": state, "limit": limit}
            ),
            mcp_tool_name="search_phase0_audit",
        )
        agent.bind_capability(unbounded_cap)
        tool_fn = agent._tools["search_phase0_audit"]

        with self.assertRaisesRegex(ValueError, "require_filter_for_unbounded_query"):
            tool_fn()
        with self.assertRaisesRegex(ValueError, "require_filter_for_unbounded_query"):
            tool_fn(limit=10)
        with self.assertRaisesRegex(ValueError, "require_filter_for_unbounded_query"):
            tool_fn(query="   ", state="ALL")
        self.assertEqual(calls, [])

        res = tool_fn(query="principal.ip != ''", limit=25)
        self.assertEqual(res["query"], "principal.ip != ''")
        self.assertEqual(len(calls), 1)

    def test_no_agent_in_fleet_binds_tenant_mutating_capability(self):
        for handle, agent in self.fleet.items():
            for cid, cap in agent._capabilities.items():
                self.assertFalse(
                    has_tenant_side_effects(cap),
                    f"Agent {handle} bound tenant-mutating capability {cid}",
                )
            tool_names = [t.__name__ for t in agent.get_tools()]
            for forbidden in ("patch_rule", "update_rule_deployment", "create_findings_refinement"):
                self.assertNotIn(forbidden, tool_names, f"{handle} still exposes {forbidden}")

    def test_logjammer_replay_tools_removed_from_model_tool_list(self):
        lj: LogjammerAgentAgent = self.fleet["@logjammer-agent"]
        tool_names = [t.__name__ for t in lj.get_tools()]
        self.assertNotIn("replay_to_secops", tool_names)
        self.assertNotIn("verify_proposal_with_replay", tool_names)
        self.assertIn("generate_scenario_logs", tool_names)

    def test_identity_governor_tools_do_not_accept_inventory_base_url(self):
        import inspect

        ig: IdentityGovernorAgent = self.fleet["@identity-governor"]
        for name in ("query_inventory_identity_report", "run_identity_drift_audit", "fetch_inventory_identity_report"):
            if name in ig._tools:
                sig = inspect.signature(ig._tools[name])
                self.assertNotIn("inventory_base_url", sig.parameters, f"{name} still exposes inventory_base_url")

        with self.assertRaises(SecOpsConfigurationError):
            resolve_inventory_base_url("file:///etc/passwd")
        with self.assertRaises(SecOpsConfigurationError):
            resolve_inventory_base_url("http://user:pass@localhost:8000")

    def test_yaral_optimizer_derives_diff_from_live_baseline_and_ignores_spoofed_diff(self):
        class _RuleEngine:
            registry = self.engine.registry

            def verify_rule(self, rule_text: str):
                class _Res:
                    success = True
                    diagnostics = []
                return _Res()

            def get_rule(self, rule_id: str, view: str = "FULL"):
                class _Rule:
                    rule_text = "rule demo {\n  condition:\n    $e1 and $e2\n}\n"
                return _Rule()

        opt = YaralOptimizerAgent(engine=_RuleEngine(), proposal_manager=self.prop_mgr)
        res = opt.submit_rule_proposal(
            title="Tighten demo rule",
            target_resource_id="ru_demo",
            rationale="Remove redundant join",
            proposed_diff="--- SPOOFED DIFF THAT MUST BE IGNORED ---",
            optimized_rule_text="rule demo {\n  condition:\n    $e1\n}\n",
        )
        prop = self.prop_mgr.get_proposal(res["proposal_id"])
        self.assertNotIn("SPOOFED DIFF", prop.proposed_diff)
        self.assertIn("-$e1 and $e2" if "-$e1" in prop.proposed_diff else "-    $e1 and $e2", prop.proposed_diff)


class Phase0ApprovalAndAdapterValidationTest(unittest.TestCase):
    def test_code_and_refinement_changes_always_require_human_tier3(self):
        for action in ("PATCH_RULE", "UPDATE_RULE_TEXT", "PATCH_PARSER_CBN", "CREATE_FINDINGS_REFINEMENT", "DELETE_RULE"):
            for risk in ("LOW", "MEDIUM", "HIGH"):
                self.assertEqual(
                    required_tier(action, risk),
                    AuthorityTier.TIER_3_HUMAN_APPROVAL.value,
                    f"{action} ({risk}) must require TIER_3_HUMAN_APPROVAL",
                )
            with self.assertRaises(ApprovalPolicyError) as ctx:
                check_approval(
                    author="@yaral-optimizer",
                    approver="@peer-agent",
                    action_type=action,
                    risk_level="LOW",
                    stored_tier=None,
                    syntax_verified=True,
                )
            self.assertEqual(ctx.exception.code, ApprovalPolicyError.HUMAN_REQUIRED)

    def test_adapter_validates_resource_names_against_configured_instance_and_collection(self):
        ad = GoogleSecOpsAdapter.__new__(GoogleSecOpsAdapter)
        ad.project_id = "proj-alpha"
        ad.project_number = "12345"
        ad.location = "us"
        ad.customer_id = "cust-111"
        ad.calls = []
        ad._request = lambda method, path, params=None, body=None, timeout=None: (
            ad.calls.append((method, path)) or {"ok": True}
        )

        # Valid short ID and matching full resource paths (project_id or project_number) succeed
        ad.delete_rule("ru_abc")
        ad.delete_rule("projects/proj-alpha/locations/us/instances/cust-111/rules/ru_abc")
        ad.delete_rule("projects/12345/locations/us/instances/cust-111/rules/ru_abc")
        self.assertEqual(len(ad.calls), 3)

        # Cross-project, cross-instance, wrong collection, wildcard '-', and traversal are rejected
        bad_inputs = [
            "projects/other-proj/locations/us/instances/cust-111/rules/ru_abc",
            "projects/proj-alpha/locations/eu/instances/cust-111/rules/ru_abc",
            "projects/proj-alpha/locations/us/instances/other-cust/rules/ru_abc",
            "projects/proj-alpha/locations/us/instances/cust-111/dataTables/dt_1",
            "projects/proj-alpha/locations/us/instances/cust-111/rules/-",
            "-",
            "../dataTables/dt_1",
            "ru_abc?force=true",
        ]
        for bad in bad_inputs:
            with self.assertRaises(ValueError, msg=f"Expected ValueError for {bad!r}"):
                ad.delete_rule(bad)


class Phase0WebServerSecurityTest(unittest.TestCase):
    def test_web_server_source_guards_cors_auth_and_tuning_deploy(self):
        repo_root = Path(__file__).resolve().parent.parent
        server_src = (repo_root / "clients" / "web" / "server.py").read_text(encoding="utf-8")
        index_src = (repo_root / "clients" / "web" / "static" / "index.html").read_text(encoding="utf-8")
        app_js = (repo_root / "clients" / "web" / "static" / "app.js").read_text(encoding="utf-8")

        self.assertNotIn("CORSMiddleware", server_src)
        self.assertNotIn('allow_origins=["*"]', server_src)
        self.assertNotIn("/api/tuning/deploy", server_src)
        self.assertNotIn("/api/tuning/deploy", app_js)
        self.assertIn("validate_web_bind_host", server_src)
        self.assertIn("x-secops-token", server_src.lower())
        self.assertIn('meta[name="secops-api-token"]', index_src)
        self.assertIn("X-SecOps-Token", index_src)

    def test_cors_removed_token_required_and_tuning_deploy_deleted(self):
        try:
            from fastapi.testclient import TestClient
        except ImportError:
            self.skipTest("fastapi not installed in active environment")
        import clients.web.server as srv

        with patch.dict(os.environ, {"SECOPS_WEB_API_TOKEN": "test-secret-token", "SECOPS_OPERATOR_ID": "operator@corp"}, clear=False):
            client = TestClient(srv.app)

            unauth = client.get("/api/health", headers={"Origin": "https://evil.example"})
            self.assertEqual(unauth.status_code, 401)
            self.assertNotIn("access-control-allow-origin", {k.lower() for k in unauth.headers.keys()})

            auth = client.get("/api/health", headers={"X-SecOps-Token": "test-secret-token", "Origin": "https://evil.example"})
            self.assertEqual(auth.status_code, 200)
            self.assertNotIn("access-control-allow-origin", {k.lower() for k in auth.headers.keys()})

            dep = client.post("/api/tuning/deploy/ru_123", headers={"X-SecOps-Token": "test-secret-token"}, json={"rule_name": "x"})
            self.assertIn(dep.status_code, (404, 405))

        with patch.dict(os.environ, {"SECOPS_WEB_API_TOKEN": ""}, clear=False):
            with self.assertRaises(RuntimeError):
                srv.validate_web_bind_host("0.0.0.0")

        # "testclient" must not be in production LOOPBACK_HOSTS
        self.assertNotIn("testclient", srv.LOOPBACK_HOSTS)

        # Loopback socket + loopback Host header injects token; DNS-rebinding Host header does not
        with patch.dict(os.environ, {"SECOPS_WEB_API_TOKEN": "loopback-secret"}, clear=False):
            local_client = TestClient(srv.app, base_url="http://127.0.0.1:8000", client=("127.0.0.1", 50000))
            ok_root = local_client.get("/")
            self.assertIn('<meta name="secops-api-token" content="loopback-secret">', ok_root.text)

            rebind_client = TestClient(srv.app, base_url="http://evil.rebind.example:8000", client=("127.0.0.1", 50000))
            rebind_root = rebind_client.get("/")
            self.assertNotIn('<meta name="secops-api-token"', rebind_root.text)
            self.assertNotIn("loopback-secret", rebind_root.text)
            self.assertNotIn(srv.SESSION_COOKIE_NAME, rebind_root.cookies)

        # x-goog-authenticated-user-email is ignored unless SECOPS_TRUST_IAP_HEADERS=1
        with patch.dict(
            os.environ,
            {
                "SECOPS_WEB_API_TOKEN": "test-secret-token",
                "SECOPS_OPERATOR_ID": "real-local-operator",
                "SECOPS_TRUST_IAP_HEADERS": "",
            },
            clear=False,
        ):
            spoof_req = TestClient(srv.app, headers={
                "X-SecOps-Token": "test-secret-token",
                "x-goog-authenticated-user-email": "accounts.google.com:spoofed@corp",
            })
            prop_id = srv.proposal_manager.create_proposal(ChangeProposal(
                id="",
                title="Verify IAP header trust boundary",
                author="@parser-doctor",
                subsystem="parsers",
                target_resource_id="WINEVTLOG",
                action_type="PATCH_PARSER_CBN",
                mutation_payload={"log_type": "WINEVTLOG", "cbn_snippet": "filter {}"},
                preflight=PreflightProof(syntax_verified=True),
            ))
            try:
                resp = spoof_req.post(f"/api/proposals/{prop_id}/approve", json={})
                self.assertEqual(resp.status_code, 200)
                merged = srv.proposal_manager.get_proposal(prop_id)
                self.assertEqual(merged.merged_by, "real-local-operator")
            finally:
                for d in (srv.proposal_manager.open_dir, srv.proposal_manager.merged_dir):
                    (d / f"{prop_id}.md").unlink(missing_ok=True)

    def test_proposal_lock_recovers_after_stale_lockfile(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        pm = ProposalManager(root_dir=Path(tmp.name) / "ledger")
        prop_id = pm.create_proposal(ChangeProposal(
            id="",
            title="Crash-safe lock verification",
            author="@yaral-optimizer",
            subsystem="detection_rules",
            target_resource_id="ru_12345678",
            action_type="PATCH_PARSER_CBN",
            mutation_payload={"log_type": "WINEVTLOG", "cbn_snippet": "filter {}"},
            preflight=PreflightProof(syntax_verified=True),
        ))
        # Simulate a stale .lock file left behind on disk after SIGKILL
        stale_lock = pm.open_dir / f".{prop_id}.lock"
        stale_lock.write_text("999999\n", encoding="ascii")
        with pm._claim_proposal_lock(prop_id):
            with self.assertRaisesRegex(ValueError, "currently locked"):
                with pm._claim_proposal_lock(prop_id):
                    pass
        self.assertFalse(stale_lock.exists())


if __name__ == "__main__":
    unittest.main()
