#!/usr/bin/env python3
"""Live integration tests for the autonomous @identity-governor Google ADK 2 Agent.

Verifies:
1. Tool bindings & signatures (audit_chronicle_iam_bindings, query_chronicle_custom_roles, query_inventory_identity_report, run_identity_drift_audit).
2. Live project GCP IAM policy retrieval for Chronicle predefined roles and member classification.
3. Live discovery of custom project IAM roles granting chronicle.* permissions.
4. SecOps Inventory Access Audit integration.
5. Evidence Fabric IAM audit snapshot persistence, retrieval, and privilege drift detection.
6. Live autonomous reasoning and verification loop powered by Gemini 3.8 Flash.
"""

import asyncio
from datetime import datetime, timezone
import os
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from agents.generated.identity_governor import IdentityGovernorAgent
from agents.core.evidence_store import LocalFileEvidenceStore, diff_iam_audits
from agents.core.proposal_manager import ProposalManager
from engine.facade import SecOpsEngine
from engine.registry import WorkflowRegistry
from engine.workflows.identity_governance import PREDEFINED_CHRONICLE_ROLES, classify_member
from tests.test_helpers import get_live_engine


class IdentityGovernorLiveTest(unittest.TestCase):
    """Test suite for @identity-governor IAM and Chronicle access governance."""

    def setUp(self):
        self.temp_dir = TemporaryDirectory()
        self.evidence_dir = Path(self.temp_dir.name) / "evidence_store"
        self.evidence_store = LocalFileEvidenceStore(storage_dir=self.evidence_dir)

        self.proposal_manager = ProposalManager(root_dir=Path(self.temp_dir.name))

        try:
            self.engine = get_live_engine()
        except Exception:
            self.engine = SecOpsEngine(custom_registry=WorkflowRegistry())

        self.agent = IdentityGovernorAgent(
            engine=self.engine,
            proposal_manager=self.proposal_manager,
            evidence_store=self.evidence_store,
        )

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_predefined_chronicle_roles_constants(self):
        """Verifies that all 10 user-requested Chronicle predefined roles are mapped."""
        user_requested_roles = [
            "roles/chronicle.admin",
            "roles/chronicle.dataGovernor",
            "roles/chronicle.editor",
            "roles/chronicle.federationAdmin",
            "roles/chronicle.federationViewer",
            "roles/chronicle.globalDataAccess",
            "roles/chronicle.limitedViewer",
            "roles/chronicle.orgServiceAgent",
            "roles/chronicle.restrictedDataAccess",
            "roles/chronicle.restrictedDataAccessViewer",
        ]
        for role in user_requested_roles:
            self.assertIn(role, PREDEFINED_CHRONICLE_ROLES)
            self.assertTrue(len(PREDEFINED_CHRONICLE_ROLES[role]) > 0)

    def test_member_classification(self):
        """Verifies member classification logic for users, groups, service accounts, and workforce pools."""
        self.assertEqual(classify_member("user:analyst@example.com").member_type, "user")
        self.assertEqual(classify_member("group:secops-team@example.com").member_type, "group")
        self.assertEqual(classify_member("serviceAccount:sa@proj.iam.gserviceaccount.com").member_type, "serviceAccount")
        self.assertEqual(classify_member("principalSet://iam.googleapis.com/locations/global/workforcePools/pool-1/group/secops").member_type, "workforcePool")

    def test_tool_bindings(self):
        """Verifies that all identity governance tools are bound to the agent."""
        tool_names = list(self.agent._tools.keys())
        self.assertIn("audit_chronicle_iam_bindings", tool_names)
        self.assertIn("query_chronicle_custom_roles", tool_names)
        self.assertIn("query_inventory_identity_report", tool_names)
        self.assertIn("run_identity_drift_audit", tool_names)

    def test_live_chronicle_iam_bindings(self):
        """Queries live GCP IAM policy and verifies Chronicle role bindings and member extraction."""
        res = self.agent.audit_chronicle_iam_bindings()
        self.assertEqual(res["status"], "SUCCESS")
        self.assertGreater(res["total_chronicle_roles_assigned"], 0)
        self.assertIsInstance(res["users"], list)
        self.assertIsInstance(res["groups"], list)
        self.assertIsInstance(res["service_accounts"], list)
        self.assertGreater(res["users_count"], 0)

    def test_live_chronicle_custom_roles(self):
        """Queries live GCP IAM for custom roles granting chronicle.* permissions."""
        res = self.agent.query_chronicle_custom_roles()
        self.assertEqual(res["status"], "SUCCESS")
        self.assertGreater(res["custom_roles_count"], 0)
        for role in res["custom_roles"]:
            self.assertTrue(any(p.startswith("chronicle.") for p in role["chronicle_permissions"]))

    def test_evidence_store_iam_persistence_and_drift(self):
        """Verifies saving an IAM audit snapshot and detecting simulated privilege drift."""
        audit_1 = {
            "audit_id": "audit_baseline",
            "project_id": "sdl-preview-americas",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "chronicle_bindings": [
                {
                    "role": "roles/chronicle.admin",
                    "role_title": "Chronicle API Admin",
                    "is_custom": False,
                    "members": ["user:alice@example.com"],
                }
            ],
            "custom_roles": [],
            "total_privileged_users": 1,
            "total_groups": 0,
            "total_service_accounts": 0,
            "total_workforce_pools": 0,
        }
        self.evidence_store.save_iam_audit(audit_1)

        latest = self.evidence_store.get_latest_iam_audit(project_id="sdl-preview-americas")
        self.assertIsNotNone(latest)
        self.assertEqual(latest["audit_id"], "audit_baseline")

        # Create mutated audit with 1 added member and 1 new custom role
        audit_2 = {
            "audit_id": "audit_mutated",
            "project_id": "sdl-preview-americas",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "chronicle_bindings": [
                {
                    "role": "roles/chronicle.admin",
                    "role_title": "Chronicle API Admin",
                    "is_custom": False,
                    "members": ["user:alice@example.com", "user:mallory@example.com"],
                }
            ],
            "custom_roles": [
                {
                    "role_name": "projects/sdl-preview-americas/roles/ShadowAdmin",
                    "title": "Shadow Admin",
                    "chronicle_permissions": ["chronicle.rules.delete"],
                }
            ],
            "total_privileged_users": 2,
            "total_groups": 0,
            "total_service_accounts": 0,
            "total_workforce_pools": 0,
        }

        drift = diff_iam_audits(audit_1, audit_2)
        self.assertTrue(drift["has_drift"])
        self.assertEqual(len(drift["members_added"]), 1)
        self.assertEqual(drift["members_added"][0]["member"], "user:mallory@example.com")
        self.assertEqual(len(drift["custom_roles_added"]), 1)
        self.assertEqual(drift["custom_roles_added"][0], "projects/sdl-preview-americas/roles/ShadowAdmin")

    def test_run_identity_drift_audit_widget(self):
        """Verifies that run_identity_drift_audit attaches an interactive UI card."""
        res = self.agent.run_identity_drift_audit()
        self.assertEqual(res["status"], "SUCCESS")
        self.assertIsNotNone(self.agent.last_widget)
        self.assertEqual(self.agent.last_widget["type"], "identity_governance_card")
        self.assertIn("users_count", self.agent.last_widget)

    def test_autonomous_chat_turn(self):
        """Verifies that the agent responds autonomously using Gemini 3.8 Flash and executes IAM tools."""
        msg = asyncio.run(self.agent.chat("Audit our Chronicle IAM roles and custom roles please."))
        self.assertIn("@identity-governor", msg.sender_handle)
        self.assertTrue(len(msg.content) > 50)
        self.assertGreater(len(self.agent.executed_tool_calls), 0)


if __name__ == "__main__":
    unittest.main()
