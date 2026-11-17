"""Tests for marketplace integration install, integration instance create/update, and playbook attach.

Verifies:
1. Registration and taxonomy invariants for the four mutating capabilities.
2. Behavioral unit tests for the workflows against an offline stub adapter.
3. Parameter values never appear on write results.
4. Live read-only verification of the instance parameter shape the update workflow depends on.

The live class performs reads only. Installing integrations, creating instances and attaching
playbooks change shared tenant state, so they are not exercised live by this suite.
"""

import unittest
from typing import Any, Dict, List, Optional
from unittest import SkipTest

from engine.domain import (
    IntegrationInstanceWriteResult,
    MarketplaceIntegrationInstallResult,
    PlaybookAttachResult,
)
from engine.facade import SecOpsEngine
from engine.taxonomy import is_tenant_read_only_capability
from engine.workflows.integration import (
    CreateIntegrationInstanceWorkflow,
    UpdateIntegrationInstanceParametersWorkflow,
)
from engine.workflows.marketplace_integrations import InstallMarketplaceIntegrationWorkflow
from engine.workflows.playbook import AttachPlaybookToAlertWorkflow
from tests.test_helpers import get_live_adapter

SECRET = "s3cr3t-value-that-must-not-leak"


def _instance_response(parameters: List[Dict[str, Any]], configured: bool = True) -> Dict[str, Any]:
    return {
        "name": "projects/p/locations/us/instances/i/integrations/ExampleProduct/integrationInstances/inst-1",
        "identifier": "inst-1",
        "integrationIdentifier": "ExampleProduct",
        "displayName": "Example instance",
        "environment": "Example Env",
        "configured": configured,
        "systemDefault": False,
        "parameters": parameters,
    }


def _params() -> List[Dict[str, Any]]:
    return [
        {"id": "1", "displayName": "API Root", "propertyName": "ApiRoot", "type": "STRING", "mandatory": False, "value": "https://api.example.com"},
        {"id": "2", "displayName": "API Key", "propertyName": "ApiKey", "type": "PASSWORD", "mandatory": True, "value": ""},
        {"id": "3", "displayName": "Verify SSL", "propertyName": "VerifySSL", "type": "BOOLEAN", "mandatory": False, "value": "true"},
    ]


class _StubAdapter:
    """Offline test adapter recording the write calls made by the workflows."""

    def __init__(
        self,
        install_response: Optional[Dict[str, Any]] = None,
        attach_response: Optional[Dict[str, Any]] = None,
    ):
        self.install_response = {"identifier": "ExampleProduct", "version": "7"} if install_response is None else install_response
        self.attach_response = {"payload": True} if attach_response is None else attach_response
        self.current_parameters = _params()
        self.install_calls: List[Dict[str, Any]] = []
        self.create_calls: List[tuple] = []
        self.update_calls: List[tuple] = []
        self.attach_calls: List[tuple] = []

    def install_marketplace_integration(self, identifier, version=None, staging=False, override_mapping=False):
        self.install_calls.append({"identifier": identifier, "version": version, "staging": staging, "override_mapping": override_mapping})
        return self.install_response

    def create_integration_instance(self, integration_id, environment, display_name, description=None):
        self.create_calls.append((integration_id, environment, display_name, description))
        return _instance_response(self.current_parameters, configured=False)

    def get_integration_instance(self, integration_id, instance_id):
        return _instance_response(self.current_parameters)

    def update_integration_instance_parameters(self, integration_id, instance_id, parameters):
        self.update_calls.append((integration_id, instance_id, parameters))
        return _instance_response(parameters)

    def attach_playbook_to_alert(self, case_id, alert_group_identifier, alert_identifier, playbook_name, playbook_identifier=None, run_automatic=True):
        self.attach_calls.append((case_id, alert_group_identifier, alert_identifier, playbook_name, playbook_identifier, run_automatic))
        return self.attach_response


class TestInstallMarketplaceIntegrationOffline(unittest.TestCase):
    def test_install_returns_typed_result(self):
        adapter = _StubAdapter()
        res = InstallMarketplaceIntegrationWorkflow(adapter).execute("ExampleProduct")
        self.assertIsInstance(res, MarketplaceIntegrationInstallResult)
        self.assertEqual((res.identifier, res.version, res.staging), ("ExampleProduct", "7", False))
        self.assertEqual(adapter.install_calls, [{"identifier": "ExampleProduct", "version": None, "staging": False, "override_mapping": False}])

    def test_install_accepts_resource_name_and_options(self):
        adapter = _StubAdapter()
        InstallMarketplaceIntegrationWorkflow(adapter).execute("projects/p/marketplaceIntegrations/ExampleProduct", version="6", staging=True, override_mapping=True)
        self.assertEqual(adapter.install_calls[0], {"identifier": "ExampleProduct", "version": "6", "staging": True, "override_mapping": True})

    def test_install_rejects_empty_identifier_before_any_call(self):
        adapter = _StubAdapter()
        with self.assertRaises(ValueError):
            InstallMarketplaceIntegrationWorkflow(adapter).execute("  ")
        self.assertEqual(adapter.install_calls, [])

    def test_install_response_without_identifier_is_an_explicit_failure(self):
        adapter = _StubAdapter(install_response={})
        with self.assertRaises(RuntimeError):
            InstallMarketplaceIntegrationWorkflow(adapter).execute("ExampleProduct")


class TestIntegrationInstanceWriteOffline(unittest.TestCase):
    def test_create_reports_unset_mandatory_parameters(self):
        adapter = _StubAdapter()
        res = CreateIntegrationInstanceWorkflow(adapter).execute("ExampleProduct", "Example Env", "Example instance", description="d")
        self.assertIsInstance(res, IntegrationInstanceWriteResult)
        self.assertEqual(adapter.create_calls, [("ExampleProduct", "Example Env", "Example instance", "d")])
        self.assertEqual(res.instance.identifier, "inst-1")
        self.assertEqual(res.instance.integration_identifier, "ExampleProduct")
        self.assertEqual(res.instance.environment, "Example Env")
        self.assertFalse(res.instance.is_configured)
        self.assertEqual(res.unset_mandatory_parameters, ["API Key"])
        self.assertEqual([p.display_name for p in res.parameters], ["API Root", "API Key", "Verify SSL"])

    def test_create_validates_inputs_before_any_call(self):
        adapter = _StubAdapter()
        wf = CreateIntegrationInstanceWorkflow(adapter)
        for args in (("", "Env", "Name"), ("ExampleProduct", " ", "Name"), ("ExampleProduct", "Env", "")):
            with self.assertRaises(ValueError):
                wf.execute(*args)
        self.assertEqual(adapter.create_calls, [])

    def test_update_merges_by_display_name_or_property_name(self):
        adapter = _StubAdapter()
        res = UpdateIntegrationInstanceParametersWorkflow(adapter).execute(
            "ExampleProduct", "inst-1", {"api key": SECRET, "VerifySSL": False}
        )
        self.assertEqual(len(adapter.update_calls), 1)
        _, _, sent = adapter.update_calls[0]
        self.assertEqual({p["displayName"]: p["value"] for p in sent}, {"API Root": "https://api.example.com", "API Key": SECRET, "Verify SSL": "false"})
        self.assertEqual(len(sent), 3, "the full parameter list is written back, not only the changed entries")
        self.assertEqual(res.updated_parameters, ["API Key", "Verify SSL"])
        self.assertEqual(res.unset_mandatory_parameters, [])

    def test_update_does_not_mutate_the_parameters_it_read(self):
        adapter = _StubAdapter()
        UpdateIntegrationInstanceParametersWorkflow(adapter).execute("ExampleProduct", "inst-1", {"API Key": SECRET})
        self.assertEqual(adapter.current_parameters[1]["value"], "")

    def test_update_unknown_parameter_fails_before_any_write(self):
        adapter = _StubAdapter()
        with self.assertRaises(ValueError) as ctx:
            UpdateIntegrationInstanceParametersWorkflow(adapter).execute("ExampleProduct", "inst-1", {"API Key": SECRET, "No Such Field": "x"})
        self.assertIn("No Such Field", str(ctx.exception))
        self.assertIn("API Root", str(ctx.exception))
        self.assertNotIn(SECRET, str(ctx.exception))
        self.assertEqual(adapter.update_calls, [])

    def test_update_requires_values(self):
        adapter = _StubAdapter()
        with self.assertRaises(ValueError):
            UpdateIntegrationInstanceParametersWorkflow(adapter).execute("ExampleProduct", "inst-1", {})
        self.assertEqual(adapter.update_calls, [])

    def test_write_results_never_carry_parameter_values(self):
        adapter = _StubAdapter()
        res = UpdateIntegrationInstanceParametersWorkflow(adapter).execute("ExampleProduct", "inst-1", {"API Key": SECRET})
        self.assertNotIn(SECRET, repr(res))
        self.assertNotIn("parameters", res.instance.raw)
        api_key = next(p for p in res.parameters if p.display_name == "API Key")
        self.assertTrue(api_key.has_value)
        self.assertFalse(hasattr(api_key, "value"))


class TestAttachPlaybookOffline(unittest.TestCase):
    def test_attach_returns_typed_result(self):
        adapter = _StubAdapter()
        res = AttachPlaybookToAlertWorkflow(adapter).execute(123, "group-1", "alert-1", "Example Playbook", playbook_identifier="uuid-1")
        self.assertIsInstance(res, PlaybookAttachResult)
        self.assertEqual(adapter.attach_calls, [("123", "group-1", "alert-1", "Example Playbook", "uuid-1", True)])
        self.assertEqual((res.case_id, res.playbook_name, res.run_automatic), ("123", "Example Playbook", True))

    def test_attach_unacknowledged_response_is_an_explicit_failure(self):
        for response in ({}, {"payload": False}, {"payload": "true"}):
            adapter = _StubAdapter(attach_response=response)
            with self.assertRaises(RuntimeError):
                AttachPlaybookToAlertWorkflow(adapter).execute("123", "group-1", "alert-1", "Example Playbook")

    def test_attach_validates_inputs_before_any_call(self):
        adapter = _StubAdapter()
        wf = AttachPlaybookToAlertWorkflow(adapter)
        for args in (("abc", "g", "a", "P"), ("", "g", "a", "P"), ("1", "", "a", "P"), ("1", "g", "", "P"), ("1", "g", "a", " ")):
            with self.assertRaises(ValueError):
                wf.execute(*args)
        self.assertEqual(adapter.attach_calls, [])


class TestWriteCapabilitiesRegistered(unittest.TestCase):
    EXPECTED = {
        "marketplace_integration.install": ("primitive", "marketplace_integration", "install_marketplace_integration"),
        "integration.instance.create": ("primitive", "integration", "create_integration_instance"),
        "integration.instance.update": ("workflow", "integration", "update_integration_instance"),
        "playbook.attach": ("primitive", "playbook", "attach_playbook_to_alert"),
    }

    def setUp(self):
        self.adapter = _StubAdapter()
        self.engine = SecOpsEngine(adapter=self.adapter)

    def test_capabilities_registered_with_expected_taxonomy(self):
        for cap_id, (kind, category, tool) in self.EXPECTED.items():
            cap = self.engine.registry.get(cap_id)
            self.assertIsNotNone(cap, cap_id)
            self.assertEqual(cap.kind, kind, cap_id)
            self.assertEqual(cap.category, category, cap_id)
            self.assertEqual(cap.mcp_tool_name, tool, cap_id)
            self.assertIsNone(cap.cardinality, f"{cap_id}: only queries carry a cardinality")

    def test_capabilities_declare_tenant_side_effects(self):
        for cap_id in self.EXPECTED:
            cap = self.engine.registry.get(cap_id)
            self.assertTrue(cap.side_effects, cap_id)
            self.assertFalse(is_tenant_read_only_capability(cap, self.engine.registry), f"{cap_id} must never be classified as tenant read-only")

    def test_facade_methods_route_to_the_adapter(self):
        self.engine.install_marketplace_integration("ExampleProduct")
        self.engine.create_integration_instance("ExampleProduct", "Example Env", "Example instance")
        self.engine.update_integration_instance("ExampleProduct", "inst-1", {"API Key": SECRET})
        self.engine.attach_playbook_to_alert("123", "group-1", "alert-1", "Example Playbook")
        self.assertEqual(len(self.adapter.install_calls), 1)
        self.assertEqual(len(self.adapter.create_calls), 1)
        self.assertEqual(len(self.adapter.update_calls), 1)
        self.assertEqual(len(self.adapter.attach_calls), 1)


class TestIntegrationInstanceParameterShapeLive(unittest.TestCase):
    """Live, read-only: the instance parameter shape the update workflow merges against."""

    @classmethod
    def setUpClass(cls):
        try:
            cls.adapter = get_live_adapter()
        except SkipTest:
            raise

    def test_live_instance_exposes_named_parameters(self):
        instances = self.adapter.list_integration_instances()
        if not instances:
            self.skipTest("No integration instances configured in live tenant.")
        checked = 0
        for inst in instances[:25]:
            integration_id = inst.get("integrationIdentifier") or str(inst.get("name", "")).split("/integrations/")[-1].split("/")[0]
            detail = self.adapter.get_integration_instance(integration_id, inst["identifier"])
            params = detail.get("parameters") or []
            if not params:
                continue
            for p in params:
                self.assertTrue(p.get("displayName") or p.get("propertyName"), f"{integration_id}: parameter without a name")
                self.assertIn("type", p)
                self.assertIn("mandatory", p)
            checked += 1
            if checked >= 3:
                break
        if not checked:
            self.skipTest("No live integration instance exposes parameters.")


if __name__ == "__main__":
    unittest.main()
