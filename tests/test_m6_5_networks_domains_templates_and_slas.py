"""Acceptance Tests for Milestone 6.5: SOAR Networks, Domains, Custom Lists,
Email Templates, Entities Blocklist, SLA Definitions, and Request Templates.

Verifies live Google SecOps API interactions, engine workflows, domain models,
and capability registrations against live tenant endpoints.
"""

import unittest
from engine.facade import SecOpsEngine
from engine.domain import (
    SoarNetworkSummary,
    SoarNetworkDetail,
    SoarNetworkBatch,
    SoarDomainSummary,
    SoarDomainDetail,
    SoarDomainBatch,
    SoarCustomListSummary,
    SoarCustomListDetail,
    SoarCustomListBatch,
    EmailTemplateSummary,
    EmailTemplateDetail,
    EmailTemplateBatch,
    EntitiesBlocklistSummary,
    EntitiesBlocklistDetail,
    EntitiesBlocklistBatch,
    SlaDefinitionSummary,
    SlaDefinitionDetail,
    SlaDefinitionBatch,
    RequestTemplateSummary,
    RequestTemplateDetail,
    RequestTemplateBatch,
    RequestTemplateFieldDefinition,
)


class TestMilestone65NetworksDomainsTemplatesAndSLAs(unittest.TestCase):
    """Live acceptance tests for Milestone 6.5 SOAR resource families."""

    @classmethod
    def setUpClass(cls):
        cls.engine = SecOpsEngine()

    # 1. SOAR Networks
    def test_search_soar_networks(self):
        """Verifies searching and listing SOAR CIDR network ranges."""
        batch = self.engine.search_soar_networks(limit=20)
        self.assertIsInstance(batch, SoarNetworkBatch)
        self.assertGreaterEqual(batch.total_count, 1)
        self.assertGreaterEqual(len(batch.networks), 1)

        first_net = batch.networks[0]
        self.assertIsInstance(first_net, SoarNetworkSummary)
        self.assertTrue(first_net.id)
        self.assertTrue(first_net.address)
        self.assertIsInstance(first_net.priority, int)
        self.assertIsInstance(first_net.environments, list)

        # Test query filtering
        filtered = self.engine.search_soar_networks(query="172.", limit=10)
        self.assertIsInstance(filtered, SoarNetworkBatch)
        for net in filtered.networks:
            self.assertTrue("172." in net.address or "172." in net.display_name)

    def test_get_soar_network(self):
        """Verifies deep inspection of a single SOAR CIDR network."""
        batch = self.engine.search_soar_networks(limit=1)
        self.assertGreaterEqual(len(batch.networks), 1)
        target_id = batch.networks[0].id

        detail = self.engine.get_soar_network(target_id)
        self.assertIsInstance(detail, SoarNetworkDetail)
        self.assertIsInstance(detail.summary, SoarNetworkSummary)
        self.assertEqual(detail.summary.id, target_id)
        self.assertTrue(detail.summary.address)
        self.assertIsInstance(detail.raw, dict)

    # 2. SOAR Domains
    def test_search_soar_domains(self):
        """Verifies searching and listing approved customer domains."""
        batch = self.engine.search_soar_domains(limit=20)
        self.assertIsInstance(batch, SoarDomainBatch)
        self.assertGreaterEqual(batch.total_count, 1)
        self.assertGreaterEqual(len(batch.domains), 1)

        first_dom = batch.domains[0]
        self.assertIsInstance(first_dom, SoarDomainSummary)
        self.assertTrue(first_dom.id)
        self.assertTrue(first_dom.display_name)
        self.assertIsInstance(first_dom.environments, list)

        # Test query filtering
        filtered = self.engine.search_soar_domains(query="cymbal", limit=10)
        self.assertIsInstance(filtered, SoarDomainBatch)
        for dom in filtered.domains:
            self.assertIn("cymbal", dom.display_name.lower())

    def test_get_soar_domain(self):
        """Verifies deep inspection of a single approved customer domain."""
        batch = self.engine.search_soar_domains(limit=1)
        self.assertGreaterEqual(len(batch.domains), 1)
        target_id = batch.domains[0].id

        detail = self.engine.get_soar_domain(target_id)
        self.assertIsInstance(detail, SoarDomainDetail)
        self.assertIsInstance(detail.summary, SoarDomainSummary)
        self.assertEqual(detail.summary.id, target_id)
        self.assertTrue(detail.summary.display_name)
        self.assertIsInstance(detail.raw, dict)

    # 3. SOAR Custom Lists
    def test_search_soar_custom_lists(self):
        """Verifies searching and listing SOAR custom key-value style retention lists."""
        batch = self.engine.search_soar_custom_lists(limit=20)
        self.assertIsInstance(batch, SoarCustomListBatch)
        self.assertGreaterEqual(batch.total_count, 1)
        self.assertGreaterEqual(len(batch.custom_lists), 1)

        first_cl = batch.custom_lists[0]
        self.assertIsInstance(first_cl, SoarCustomListSummary)
        self.assertTrue(first_cl.id)
        self.assertTrue(first_cl.name)
        self.assertTrue(first_cl.category)
        self.assertIsInstance(first_cl.environments, list)

        # Test category filtering
        cat = first_cl.category
        cat_filtered = self.engine.search_soar_custom_lists(category=cat, limit=10)
        self.assertIsInstance(cat_filtered, SoarCustomListBatch)
        for cl in cat_filtered.custom_lists:
            self.assertEqual(cl.category.lower(), cat.lower())

    def test_get_soar_custom_list(self):
        """Verifies deep inspection of a single SOAR custom list record."""
        batch = self.engine.search_soar_custom_lists(limit=1)
        self.assertGreaterEqual(len(batch.custom_lists), 1)
        target_id = batch.custom_lists[0].id

        detail = self.engine.get_soar_custom_list(target_id)
        self.assertIsInstance(detail, SoarCustomListDetail)
        self.assertIsInstance(detail.summary, SoarCustomListSummary)
        self.assertEqual(detail.summary.id, target_id)
        self.assertTrue(detail.summary.name)
        self.assertIsInstance(detail.raw, dict)

    # 4. SOAR Email Templates
    def test_search_email_templates(self):
        """Verifies searching plain text and HTML email templates."""
        batch = self.engine.search_email_templates(limit=20)
        self.assertIsInstance(batch, EmailTemplateBatch)
        self.assertGreaterEqual(batch.total_count, 1)
        self.assertGreaterEqual(len(batch.email_templates), 1)

        first_t = batch.email_templates[0]
        self.assertIsInstance(first_t, EmailTemplateSummary)
        self.assertTrue(first_t.id)
        self.assertTrue(first_t.name)
        self.assertIn(first_t.template_type, ["TEMPLATE", "HTML_FORMAT"])

        # Test template type filter
        html_batch = self.engine.search_email_templates(template_type="HTML_FORMAT", limit=10)
        self.assertIsInstance(html_batch, EmailTemplateBatch)
        for t in html_batch.email_templates:
            self.assertEqual(t.template_type, "HTML_FORMAT")

    def test_get_email_template(self):
        """Verifies deep inspection of an email template including body content."""
        batch = self.engine.search_email_templates(limit=2)
        self.assertGreaterEqual(len(batch.email_templates), 1)

        for summary in batch.email_templates:
            detail = self.engine.get_email_template(summary.id)
            self.assertIsInstance(detail, EmailTemplateDetail)
            self.assertIsInstance(detail.summary, EmailTemplateSummary)
            self.assertEqual(detail.summary.id, summary.id)
            self.assertIsInstance(detail.content, str)
            self.assertGreater(len(detail.content), 0)

    # 5. SOAR Entities Blocklist
    def test_search_entities_blocklists(self):
        """Verifies searching entity noise-reduction blocklist rules."""
        batch = self.engine.search_entities_blocklists(limit=20)
        self.assertIsInstance(batch, EntitiesBlocklistBatch)
        self.assertGreaterEqual(batch.total_count, 1)
        self.assertGreaterEqual(len(batch.blocklist_entries), 1)

        first_eb = batch.blocklist_entries[0]
        self.assertIsInstance(first_eb, EntitiesBlocklistSummary)
        self.assertTrue(first_eb.id)
        self.assertTrue(first_eb.entity_type)
        self.assertTrue(first_eb.entity_identifier)
        self.assertTrue(first_eb.action)

        # Test entity_type filter
        type_filtered = self.engine.search_entities_blocklists(entity_type=first_eb.entity_type, limit=10)
        self.assertIsInstance(type_filtered, EntitiesBlocklistBatch)
        for eb in type_filtered.blocklist_entries:
            self.assertEqual(eb.entity_type.lower(), first_eb.entity_type.lower())

    def test_get_entities_blocklist(self):
        """Verifies deep inspection of a single entity blocklist entry."""
        batch = self.engine.search_entities_blocklists(limit=1)
        self.assertGreaterEqual(len(batch.blocklist_entries), 1)
        target_id = batch.blocklist_entries[0].id

        detail = self.engine.get_entities_blocklist(target_id)
        self.assertIsInstance(detail, EntitiesBlocklistDetail)
        self.assertIsInstance(detail.summary, EntitiesBlocklistSummary)
        self.assertEqual(detail.summary.id, target_id)
        self.assertTrue(detail.summary.entity_identifier)
        self.assertIsInstance(detail.raw, dict)

    # 6. SOAR SLA Definitions
    def test_search_sla_definitions(self):
        """Verifies searching Service Level Agreement definitions."""
        batch = self.engine.search_sla_definitions(limit=20)
        self.assertIsInstance(batch, SlaDefinitionBatch)
        self.assertGreaterEqual(batch.total_count, 1)
        self.assertGreaterEqual(len(batch.sla_definitions), 1)

        first_sla = batch.sla_definitions[0]
        self.assertIsInstance(first_sla, SlaDefinitionSummary)
        self.assertTrue(first_sla.id)
        self.assertTrue(first_sla.name)
        self.assertIn(first_sla.sla_type, ["CASE_STAGE", "CASE_PRIORITY"])
        self.assertIsInstance(first_sla.environments, list)

        # Test sla_type filter
        stage_batch = self.engine.search_sla_definitions(sla_type="CASE_STAGE", limit=10)
        self.assertIsInstance(stage_batch, SlaDefinitionBatch)
        for s in stage_batch.sla_definitions:
            self.assertEqual(s.sla_type, "CASE_STAGE")

    def test_get_sla_definition(self):
        """Verifies deep inspection of a single SLA definition."""
        batch = self.engine.search_sla_definitions(limit=1)
        self.assertGreaterEqual(len(batch.sla_definitions), 1)
        target_id = batch.sla_definitions[0].id

        detail = self.engine.get_sla_definition(target_id)
        self.assertIsInstance(detail, SlaDefinitionDetail)
        self.assertIsInstance(detail.summary, SlaDefinitionSummary)
        self.assertEqual(detail.summary.id, target_id)
        self.assertTrue(detail.summary.name)
        self.assertIsInstance(detail.raw, dict)

    # 7. SOAR Request Templates
    def test_search_request_templates(self):
        """Verifies searching manual case request form templates."""
        batch = self.engine.search_request_templates(limit=20)
        self.assertIsInstance(batch, RequestTemplateBatch)
        self.assertGreaterEqual(batch.total_count, 1)
        self.assertGreaterEqual(len(batch.request_templates), 1)

        first_rt = batch.request_templates[0]
        self.assertIsInstance(first_rt, RequestTemplateSummary)
        self.assertTrue(first_rt.id)
        self.assertTrue(first_rt.name)
        self.assertIsInstance(first_rt.field_count, int)
        self.assertIsInstance(first_rt.environments, list)

    def test_get_request_template(self):
        """Verifies deep inspection of a request template including form fields."""
        batch = self.engine.search_request_templates(limit=1)
        self.assertGreaterEqual(len(batch.request_templates), 1)
        target_id = batch.request_templates[0].id

        detail = self.engine.get_request_template(target_id)
        self.assertIsInstance(detail, RequestTemplateDetail)
        self.assertIsInstance(detail.summary, RequestTemplateSummary)
        self.assertEqual(detail.summary.id, target_id)
        self.assertTrue(detail.summary.name)
        self.assertIsInstance(detail.event_field_definitions, list)
        if detail.event_field_definitions:
            first_field = detail.event_field_definitions[0]
            self.assertIsInstance(first_field, RequestTemplateFieldDefinition)
            self.assertTrue(first_field.name)
            self.assertTrue(first_field.field_type)

    # 8. Capability Registry Integration
    def test_capability_registry(self):
        """Verifies all 14 Milestone 6.5 capabilities are registered and invokable."""
        expected_caps = [
            "soar.network.search",
            "soar.network.get",
            "soar.domain.search",
            "soar.domain.get",
            "soar.custom_list.search",
            "soar.custom_list.get",
            "soar.email_template.search",
            "soar.email_template.get",
            "soar.entities_blocklist.search",
            "soar.entities_blocklist.get",
            "soar.sla_definition.search",
            "soar.sla_definition.get",
            "soar.request_template.search",
            "soar.request_template.get",
        ]
        registered = {c.capability_id: c for c in self.engine.registry.list_capabilities()}
        for cap_id in expected_caps:
            self.assertIn(cap_id, registered, f"Capability {cap_id} must be registered")
            cap = registered[cap_id]
            self.assertEqual(cap.category, "soar_settings")
            self.assertTrue(callable(cap.handler))


if __name__ == "__main__":
    unittest.main()
