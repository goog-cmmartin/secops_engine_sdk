#!/usr/bin/env python3
"""Acceptance Tests for Milestone 6.1: SOAR Settings & Case Data Configuration.

Validates end-to-end live API execution for:
- SOAR Users (discovery, search, filter, deep profile inspection)
- SOAR SOC Roles (roles list and assignment access hierarchy)
- SOAR Company Settings (rebranding, reporting, system emails)
- Case Tag Definitions (rule criteria, comparison types, title flags)
- Case Stage Definitions (ordered SOC lifecycle stages)
- Case Close Definitions (predefined close reasons and root causes)
- Case Close Dynamic Form Parameters (custom field schemas for case closure)
- Case Title Setting Properties (priority rules for case title generation)
"""

import unittest
from adapters.google_secops import GoogleSecOpsAdapter
from engine import (
    CaseCloseDefinitionBatch,
    CaseCloseDynamicParameterBatch,
    CaseStageDefinitionBatch,
    CaseTagDefinitionBatch,
    CaseTitleSettingsBatch,
    CompanySettingsBatch,
    SecOpsEngine,
    SocRoleBatch,
    SoarUserBatch,
    SoarUserDetail,
)


class TestMilestone61SoarSettings(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.adapter = GoogleSecOpsAdapter()
        cls.engine = SecOpsEngine(adapter=cls.adapter)

    def test_search_soar_users(self):
        batch = self.engine.search_soar_users(limit=10)
        self.assertIsInstance(batch, SoarUserBatch)
        self.assertGreater(batch.total_count, 0)
        self.assertGreater(len(batch.users), 0)

        user = batch.users[0]
        self.assertTrue(bool(user.id))
        self.assertTrue(bool(user.user_full_name))
        self.assertTrue(bool(user.email))
        self.assertTrue(bool(user.account_state))

    def test_get_soar_user_detail(self):
        batch = self.engine.search_soar_users(limit=1)
        self.assertGreater(len(batch.users), 0)
        target_id = batch.users[0].id

        user = self.engine.get_soar_user(target_id)
        self.assertIsInstance(user, SoarUserDetail)
        self.assertEqual(user.summary.id, target_id)
        self.assertTrue(bool(user.summary.email))
        self.assertTrue(bool(user.summary.provider_name))

    def test_list_soc_roles(self):
        batch = self.engine.list_soc_roles(limit=20)
        self.assertIsInstance(batch, SocRoleBatch)
        self.assertGreater(batch.total_count, 0)
        self.assertGreater(len(batch.roles), 0)

        role = batch.roles[0]
        self.assertTrue(bool(role.id))
        self.assertTrue(bool(role.display_name))
        self.assertIsInstance(role.additional_roles_access, list)

    def test_get_company_settings(self):
        batch = self.engine.get_company_settings()
        self.assertIsInstance(batch, CompanySettingsBatch)
        self.assertGreater(batch.total_count, 0)
        self.assertGreater(len(batch.properties), 0)

        prop = batch.properties[0]
        self.assertTrue(bool(prop.property_key))
        self.assertTrue(bool(prop.type))

    def test_search_case_tag_definitions(self):
        batch = self.engine.search_case_tag_definitions(limit=10)
        self.assertIsInstance(batch, CaseTagDefinitionBatch)
        self.assertGreater(batch.total_count, 0)
        self.assertGreater(len(batch.tags), 0)

        tag = batch.tags[0]
        self.assertTrue(bool(tag.id))
        self.assertTrue(bool(tag.display_name))
        self.assertTrue(bool(tag.match_criteria))

    def test_list_case_stage_definitions(self):
        batch = self.engine.list_case_stage_definitions(limit=20)
        self.assertIsInstance(batch, CaseStageDefinitionBatch)
        self.assertGreater(batch.total_count, 0)
        self.assertGreater(len(batch.stages), 0)

        stage = batch.stages[0]
        self.assertTrue(bool(stage.id))
        self.assertTrue(bool(stage.display_name))
        self.assertGreaterEqual(stage.order, 0)

    def test_list_case_close_definitions(self):
        batch = self.engine.list_case_close_definitions(limit=20)
        self.assertIsInstance(batch, CaseCloseDefinitionBatch)
        self.assertGreater(batch.total_count, 0)
        self.assertGreater(len(batch.definitions), 0)

        close_def = batch.definitions[0]
        self.assertTrue(bool(close_def.id))
        self.assertTrue(bool(close_def.close_reason))
        self.assertTrue(bool(close_def.root_cause))

    def test_list_case_close_dynamic_parameters(self):
        batch = self.engine.list_case_close_dynamic_parameters(limit=20)
        self.assertIsInstance(batch, CaseCloseDynamicParameterBatch)
        self.assertGreater(batch.total_count, 0)
        self.assertGreater(len(batch.parameters), 0)

        param = batch.parameters[0]
        self.assertEqual(param.form_type, "CLOSE_CASE")
        self.assertTrue(bool(param.custom_field_display_name))
        self.assertTrue(bool(param.custom_field_type))

    def test_get_case_title_settings(self):
        batch = self.engine.get_case_title_settings()
        self.assertIsInstance(batch, CaseTitleSettingsBatch)
        self.assertGreater(batch.total_count, 0)
        self.assertGreater(len(batch.properties), 0)

        prop = batch.properties[0]
        self.assertTrue(bool(prop.property_key))
        self.assertTrue(bool(prop.value))

    def test_facade_capability_registration(self):
        caps = self.engine.list_capabilities()
        cap_ids = [c.capability_id for c in caps]

        self.assertIn("soar.user.search", cap_ids)
        self.assertIn("soar.user.get", cap_ids)
        self.assertIn("soar.soc_role.list", cap_ids)
        self.assertIn("soar.company.get", cap_ids)
        self.assertIn("case_config.tag.search", cap_ids)
        self.assertIn("case_config.stage.list", cap_ids)
        self.assertIn("case_config.close_definition.list", cap_ids)
        self.assertIn("case_config.close_parameter.list", cap_ids)
        self.assertIn("case_config.title_settings.get", cap_ids)


if __name__ == "__main__":
    unittest.main()
