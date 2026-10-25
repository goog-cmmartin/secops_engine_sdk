"""Tests for SOAR Integration Instance Lifecycle (Affected Items & Deletion).

Verifies:
1. Registration & taxonomy invariants for integration.instance.affected_items and integration.instance.delete.
2. Behavioral unit tests for FetchIntegrationInstanceAffectedItemsWorkflow and DeleteIntegrationInstanceWorkflow.
3. Pre-flight dependency guard refusing to delete instances with active playbooks unless force=True.
4. Live environment execution against GoogleChronicle instance if live credentials present.
"""

import unittest
from typing import Any, Dict, List, Optional
from unittest import SkipTest

from engine.domain import (
    IntegrationInstanceAffectedItems,
    IntegrationInstanceDeleteResult,
)
from engine.facade import SecOpsEngine
from engine.registry import WorkflowRegistry
from engine.workflows.integration import (
    DeleteIntegrationInstanceWorkflow,
    FetchIntegrationInstanceAffectedItemsWorkflow,
)
from tests.test_helpers import get_live_adapter, get_live_engine


class _StubAdapter:
    """Offline test adapter implementing the instance lifecycle methods."""

    def __init__(self, affected_response: Optional[Dict[str, Any]] = None):
        self.affected_response = affected_response or {}
        self.deleted_calls: List[tuple] = []

    def get_integration_instance_affected_items(
        self, integration_id: str, instance_id: str
    ) -> Dict[str, Any]:
        return self.affected_response

    def delete_integration_instance(
        self, integration_id: str, instance_id: str
    ) -> Dict[str, Any]:
        self.deleted_calls.append((integration_id, instance_id))
        return {}


class TestIntegrationInstanceLifecycleOffline(unittest.TestCase):
    """Offline unit test suite for instance lifecycle workflows and registry invariants."""

    def test_affected_items_workflow_parses_playbooks(self):
        adapter = _StubAdapter(
            affected_response={
                "playbooks": [
                    {"displayName": "Detection Coverage Agent"},
                    {"displayName": "C2 Remediation Playbook"},
                ]
            }
        )
        wf = FetchIntegrationInstanceAffectedItemsWorkflow(adapter)
        res = wf.execute("GoogleChronicle", "inst-1234")

        self.assertIsInstance(res, IntegrationInstanceAffectedItems)
        self.assertEqual(res.integration_identifier, "GoogleChronicle")
        self.assertEqual(res.instance_identifier, "inst-1234")
        self.assertEqual(
            res.affected_playbooks,
            ["Detection Coverage Agent", "C2 Remediation Playbook"],
        )
        self.assertTrue(res.has_affected_items)

    def test_affected_items_workflow_empty(self):
        adapter = _StubAdapter(affected_response={})
        wf = FetchIntegrationInstanceAffectedItemsWorkflow(adapter)
        res = wf.execute("GoogleChronicle", "inst-empty")

        self.assertFalse(res.has_affected_items)
        self.assertEqual(res.affected_playbooks, [])

    def test_delete_workflow_aborts_when_playbooks_affected_without_force(self):
        adapter = _StubAdapter(
            affected_response={
                "playbooks": [{"displayName": "Active Threat Response"}]
            }
        )
        wf = DeleteIntegrationInstanceWorkflow(adapter)

        with self.assertRaises(ValueError) as ctx:
            wf.execute("GoogleChronicle", "inst-used", force=False)

        self.assertIn("Active Threat Response", str(ctx.exception))
        self.assertIn("Pass force=True to delete anyway", str(ctx.exception))
        self.assertEqual(len(adapter.deleted_calls), 0)

    def test_delete_workflow_succeeds_when_force_true(self):
        adapter = _StubAdapter(
            affected_response={
                "playbooks": [{"displayName": "Active Threat Response"}]
            }
        )
        wf = DeleteIntegrationInstanceWorkflow(adapter)
        result = wf.execute("GoogleChronicle", "inst-used", force=True)

        self.assertIsInstance(result, IntegrationInstanceDeleteResult)
        self.assertTrue(result.success)
        self.assertEqual(result.affected_playbooks_count, 1)
        self.assertEqual(adapter.deleted_calls, [("GoogleChronicle", "inst-used")])

    def test_delete_workflow_succeeds_when_no_playbooks_affected(self):
        adapter = _StubAdapter(affected_response={})
        wf = DeleteIntegrationInstanceWorkflow(adapter)
        result = wf.execute("GoogleChronicle", "inst-clean", force=False)

        self.assertTrue(result.success)
        self.assertEqual(result.affected_playbooks_count, 0)
        self.assertEqual(adapter.deleted_calls, [("GoogleChronicle", "inst-clean")])

    def test_capabilities_registered_in_engine(self):
        engine = SecOpsEngine(adapter=_StubAdapter())

        affected_cap = engine.registry.get("integration.instance.affected_items")
        self.assertIsNotNone(affected_cap)
        self.assertEqual(affected_cap.kind, "query")
        self.assertEqual(affected_cap.cardinality, "unbounded")
        self.assertEqual(affected_cap.category, "integration")
        self.assertTrue(affected_cap.agent.get("require_filter_for_unbounded_query"))

        delete_cap = engine.registry.get("integration.instance.delete")
        self.assertIsNotNone(delete_cap)
        self.assertEqual(delete_cap.kind, "workflow")
        self.assertTrue(delete_cap.composed)
        self.assertEqual(delete_cap.uses, ("integration.instance.affected_items",))


class TestIntegrationInstanceLifecycleLive(unittest.TestCase):
    """Live verification against real Google SecOps endpoints if environment is configured."""

    @classmethod
    def setUpClass(cls):
        try:
            cls.engine = get_live_engine()
        except SkipTest:
            raise

    def test_live_fetch_affected_items_for_known_instance(self):
        # We know dc6df515-9517-46eb-96cc-21f245bb9dfb is GoogleChronicle system default instance
        affected = self.engine.get_integration_instance_affected_items(
            integration_id="GoogleChronicle",
            instance_id="dc6df515-9517-46eb-96cc-21f245bb9dfb",
        )
        self.assertIsInstance(affected, IntegrationInstanceAffectedItems)
        self.assertEqual(affected.integration_identifier, "GoogleChronicle")
        self.assertEqual(affected.instance_identifier, "dc6df515-9517-46eb-96cc-21f245bb9dfb")
        self.assertIsInstance(affected.affected_playbooks, list)
        self.assertGreaterEqual(len(affected.affected_playbooks), 1)
        self.assertTrue(affected.has_affected_items)


if __name__ == "__main__":
    unittest.main()
