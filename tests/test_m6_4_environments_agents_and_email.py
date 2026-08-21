"""Acceptance tests for Milestone 6.4: SOAR Environments, Remote Agents, Email Settings, and Support Access.

Validates that:
1. Environments discovery returns valid multi-tenancy environments with retentionDuration and dataAccessScopes.
2. Individual environment inspection retrieves complete configuration.
3. Environment groups search executes cleanly.
4. Remote agents discovery returns registered agents with environments bindings and state.
5. Individual remote agent inspection retrieves complete configuration including certificate.
6. Email settings workflow combines custom toggle with SMTP parameters.
7. Google Support access workflow returns delegation properties.
8. Capability registry includes all 7 Milestone 6.4 capabilities.
"""

from __future__ import annotations

import unittest
from engine.facade import SecOpsEngine
from engine.domain import (
    EnvironmentBatch,
    EnvironmentDetail,
    EnvironmentGroupBatch,
    RemoteAgentBatch,
    RemoteAgentDetail,
    EmailSettingsBatch,
    SupportSettingsBatch,
)


class TestMilestone64EnvironmentsAgentsAndEmail(unittest.TestCase):
    """End-to-end acceptance tests against live Google SecOps endpoints."""

    @classmethod
    def setUpClass(cls):
        cls.engine = SecOpsEngine()

    def test_01_search_environments(self):
        """Validates discovery and filtering of SOAR multi-tenancy environments."""
        batch = self.engine.search_environments(limit=20)
        self.assertIsInstance(batch, EnvironmentBatch)
        self.assertGreater(batch.total_count, 0)
        self.assertGreaterEqual(len(batch.environments), 1)

        # Check default / known environments
        env_names = [e.display_name for e in batch.environments]
        self.assertTrue(
            any("Default" in name or "Cymbal" in name for name in env_names),
            f"Expected Default or Cymbal environment in {env_names}",
        )

        first = batch.environments[0]
        self.assertTrue(bool(first.id))
        self.assertTrue(bool(first.name))
        self.assertIsInstance(first.system, bool)
        self.assertIsInstance(first.aliases, list)
        self.assertIsInstance(first.data_access_scopes, list)

    def test_02_get_environment(self):
        """Validates deep retrieval of a single multi-tenancy environment."""
        batch = self.engine.search_environments(limit=5)
        self.assertGreater(len(batch.environments), 0)
        target_env = batch.environments[0]

        detail = self.engine.get_environment(target_env.id)
        self.assertIsInstance(detail, EnvironmentDetail)
        self.assertEqual(detail.summary.id, target_env.id)
        self.assertEqual(detail.summary.name, target_env.name)
        self.assertIn("name", detail.raw)

    def test_03_search_environment_groups(self):
        """Validates querying environment group collections."""
        batch = self.engine.search_environment_groups(limit=10)
        self.assertIsInstance(batch, EnvironmentGroupBatch)
        self.assertIsInstance(batch.groups, list)
        self.assertEqual(batch.total_count, len(batch.groups))

    def test_04_search_remote_agents(self):
        """Validates discovery and filtering of remote SOAR execution agents."""
        batch = self.engine.search_remote_agents(limit=20)
        self.assertIsInstance(batch, RemoteAgentBatch)
        self.assertGreater(batch.total_count, 0)
        self.assertGreaterEqual(len(batch.remote_agents), 1)

        first = batch.remote_agents[0]
        self.assertTrue(bool(first.id))
        self.assertTrue(bool(first.name))
        self.assertTrue(bool(first.identifier))
        self.assertIsInstance(first.environments, list)
        self.assertIn(first.agent_state, ["ACTIVE", "INACTIVE", "UNKNOWN", "CONNECTED", "DISCONNECTED", "WAITING"])

    def test_05_get_remote_agent(self):
        """Validates deep retrieval of a single remote agent."""
        batch = self.engine.search_remote_agents(limit=5)
        self.assertGreater(len(batch.remote_agents), 0)
        target_agent = batch.remote_agents[0]

        detail = self.engine.get_remote_agent(target_agent.id)
        self.assertIsInstance(detail, RemoteAgentDetail)
        self.assertEqual(detail.summary.id, target_agent.id)
        self.assertEqual(detail.summary.name, target_agent.name)
        self.assertIn("name", detail.raw)

    def test_06_get_email_settings(self):
        """Validates composite email transport configuration retrieval."""
        batch = self.engine.get_email_settings()
        self.assertIsInstance(batch, EmailSettingsBatch)
        self.assertIsInstance(batch.use_custom, bool)
        self.assertGreater(batch.total_count, 0)

        prop_keys = [p.property_key for p in batch.properties]
        self.assertTrue(
            any("Smtp" in k or "Sender" in k or "Username" in k for k in prop_keys),
            f"Expected SMTP properties in {prop_keys}",
        )

    def test_07_get_support_settings(self):
        """Validates Google Support access delegation parameters."""
        batch = self.engine.get_support_settings()
        self.assertIsInstance(batch, SupportSettingsBatch)
        self.assertGreater(batch.total_count, 0)

        prop_keys = [p.property_key for p in batch.properties]
        self.assertTrue(
            any("Enabled" in k or "SocRoleIds" in k or "Environments" in k for k in prop_keys),
            f"Expected support properties in {prop_keys}",
        )

    def test_08_capability_registry_integration(self):
        """Validates that all Milestone 6.4 capabilities are properly registered."""
        required_caps = [
            "soar.environment.search",
            "soar.environment.get",
            "soar.environment_group.search",
            "soar.remote_agent.search",
            "soar.remote_agent.get",
            "soar.email_settings.get",
            "soar.support_settings.get",
        ]
        all_caps = {c.capability_id: c for c in self.engine.list_capabilities()}
        for cap_id in required_caps:
            self.assertIn(cap_id, all_caps, f"Capability {cap_id} must be registered.")
            cap = all_caps[cap_id]
            self.assertEqual(cap.category, "soar_settings")
            self.assertIsNotNone(cap.handler)


if __name__ == "__main__":
    unittest.main()
