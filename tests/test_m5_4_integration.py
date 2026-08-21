"""Authoritative Live Acceptance Tests for Milestone 5.4: SOAR Integrations, Instances & Remote Agents.

Invariants:
- Zero mocks, fixtures, fakes, or synthetic data structures in production code.
- Strict live data validation from Google SecOps API endpoints.
- Verifies integration search, filtering, instance binding per environment, remote agent mapping,
  and deep inspection with marketplace documentation.
"""

from tests.test_helpers import get_live_adapter, get_live_engine
import unittest
from adapters.google_secops import GoogleSecOpsAdapter
from engine import (
    IntegrationBatch,
    IntegrationDetail,
    IntegrationInstance,
    IntegrationSearchQuery,
    IntegrationSummary,
    IntegrationType,
    RemoteAgent,
    SecOpsEngine,
)
from engine.registry import registry


class TestM54IntegrationLiveAcceptance(unittest.TestCase):
    """Authoritative behavioral test suite for Milestone 5.4 against live Google SecOps."""

    @classmethod
    def setUpClass(cls):
        cls.engine = get_live_engine()
        cls.adapter = get_live_adapter()

    def test_list_all_integrations(self):
        """1. Verify engine lists all live base integrations and wraps in typed summaries."""
        batch = self.engine.search_integrations(limit=200)

        self.assertIsInstance(batch, IntegrationBatch)
        self.assertGreaterEqual(batch.total_count, 100, "Expected at least 100 integrations in catalog")
        self.assertGreaterEqual(len(batch.results), 100)

        first = batch.results[0]
        self.assertIsInstance(first, IntegrationSummary)
        self.assertTrue(bool(first.identifier), "Integration identifier must not be empty")
        self.assertTrue(bool(first.display_name), "Integration display name must not be empty")
        self.assertIsInstance(first.integration_type, IntegrationType)
        self.assertIsInstance(first.instances_count, int)

    def test_search_integration_by_keyword(self):
        """2. Verify keyword search matches specific integration."""
        batch = self.engine.search_integrations(query="CrowdStrike")

        self.assertGreaterEqual(batch.total_count, 1)
        found = next((i for i in batch.results if i.identifier == "CrowdStrikeFalcon"), None)
        self.assertIsNotNone(found, "CrowdStrikeFalcon must be found when searching 'CrowdStrike'")
        self.assertTrue(found.certified)
        self.assertGreaterEqual(found.instances_count, 1)

    def test_filter_integrations_by_environment(self):
        """3. Verify filtering integrations by environment returns instances scoped to environment or global."""
        batch = self.engine.search_integrations(environment="Cymbal")

        self.assertGreater(len(batch.results), 0)
        # Verify that all returned integrations have at least one instance for Cymbal or global *
        for item in batch.results[:5]:
            instances = self.engine.list_integration_instances(integration_id=item.identifier)
            envs = set(inst.environment for inst in instances)
            self.assertTrue("Cymbal" in envs or "*" in envs, f"Integration {item.identifier} should have Cymbal or * instance")

    def test_filter_integrations_by_certified_flag(self):
        """4. Verify filtering by certified status."""
        certified_batch = self.engine.search_integrations(is_certified=True)
        for item in certified_batch.results:
            self.assertTrue(item.certified, f"Integration {item.identifier} must be certified")

    def test_list_integration_instances_across_environments(self):
        """5. Verify listing integration instances across global and tenant environments."""
        all_instances = self.engine.list_integration_instances()

        self.assertGreaterEqual(len(all_instances), 150, "Expected at least 150 configured/unconfigured instances")
        sample = all_instances[0]
        self.assertIsInstance(sample, IntegrationInstance)
        self.assertTrue(bool(sample.identifier))
        self.assertTrue(bool(sample.integration_identifier))

        # Check environments present
        all_envs = set(i.environment for i in all_instances)
        self.assertIn("*", all_envs, "Global environment wildcard '*' must be present in instances")
        self.assertIn("Default Environment", all_envs, "'Default Environment' must be present in instances")

    def test_get_integration_deep_inspection(self):
        """6. Deep inspection of CrowdStrikeFalcon verifying instances and marketplace documentation."""
        detail = self.engine.get_integration("CrowdStrikeFalcon")

        self.assertIsInstance(detail, IntegrationDetail)
        self.assertEqual(detail.identifier, "CrowdStrikeFalcon")
        self.assertEqual(detail.display_name, "CrowdStrike Falcon")
        self.assertTrue(detail.certified)
        self.assertGreaterEqual(len(detail.instances), 6)

        # Check documentation URI and categories from marketplace
        self.assertIsNotNone(detail.documentation_uri)
        self.assertTrue(detail.documentation_uri.startswith("https://cloud.google.com/chronicle/docs/soar/marketplace-integrations/"))
        self.assertIn("Endpoint Security", detail.categories)

        # Verify environments supported
        envs = detail.environments_supported
        self.assertIn("*", envs)
        self.assertIn("Default Environment", envs)

    def test_get_ai_agents_integration_linked_to_playbook(self):
        """7. Verify GoogleSecOpsAiAgents integration details and instance linked to Playbook 2277."""
        detail = self.engine.get_integration("GoogleSecOpsAiAgents")

        self.assertIsInstance(detail, IntegrationDetail)
        self.assertEqual(detail.identifier, "GoogleSecOpsAiAgents")
        self.assertGreaterEqual(len(detail.instances), 1)

        target_inst = next((inst for inst in detail.instances if inst.identifier == "add412bb-1077-480f-b59e-1b161dfdabc8"), None)
        self.assertIsNotNone(target_inst, "Instance add412bb-1077-480f-b59e-1b161dfdabc8 must be present for GoogleSecOpsAiAgents")
        self.assertTrue(target_inst.is_configured)
        self.assertTrue(target_inst.is_global)

    def test_list_remote_agents(self):
        """8. Verify remote proxy execution agents discovery with parsed environments."""
        agents = self.engine.list_remote_agents()

        self.assertGreaterEqual(len(agents), 5, "Expected at least 5 remote execution agents")
        first_agent = agents[0]
        self.assertIsInstance(first_agent, RemoteAgent)
        self.assertTrue(bool(first_agent.id))
        self.assertTrue(bool(first_agent.display_name))
        self.assertTrue(first_agent.is_active)
        self.assertIsInstance(first_agent.environments, list)
        self.assertGreater(len(first_agent.environments), 0, "Remote agent should have at least one environment")

    def test_integration_facade_capability_registration(self):
        """9. Verify integration capabilities are registered in WorkflowRegistry."""
        cap_search = registry.get("integration.search")
        self.assertIsNotNone(cap_search)
        self.assertEqual(cap_search.category, "integration")
        self.assertEqual(cap_search.mcp_tool_name, "search_integrations")

        cap_get = registry.get("integration.get")
        self.assertIsNotNone(cap_get)
        self.assertEqual(cap_get.mcp_tool_name, "get_integration")

        cap_instances = registry.get("integration.instances")
        self.assertIsNotNone(cap_instances)
        self.assertEqual(cap_instances.mcp_tool_name, "list_integration_instances")

        cap_agents = registry.get("integration.remote_agents")
        self.assertIsNotNone(cap_agents)
        self.assertEqual(cap_agents.mcp_tool_name, "list_remote_agents")

    def test_static_anti_mock_audit_for_integration(self):
        """10. Static audit: Ensure zero banned mock/synthetic patterns exist in integration codebase."""
        import os
        banned_terms = ["mock", "fixture", "dummy", "fake", "sample_data", "test_data"]
        target_files = [
            "engine/workflows/integration.py",
            "specs/integration/integration-search-001.yaml",
            "specs/integration/integration-get-001.yaml",
        ]
        base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
        for rel_path in target_files:
            full_path = os.path.join(base_dir, rel_path)
            self.assertTrue(os.path.exists(full_path), f"File missing: {rel_path}")
            with open(full_path, "r", encoding="utf-8") as f:
                content = f.read().lower()
                lines = content.splitlines()
                for idx, line in enumerate(lines, 1):
                    for term in banned_terms:
                        if term in line and "zero mock" not in line and "no-mock" not in line and "anti-mock" not in line:
                            self.fail(f"Banned term '{term}' found in {rel_path}:{idx}: {line}")



if __name__ == "__main__":
    unittest.main()
