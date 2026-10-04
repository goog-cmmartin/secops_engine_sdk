"""Tests verifying compliance with the SecOps Engine SDK Interface Standard (docs/SDK_INTERFACE_STANDARD.md).

Covers:
1. UDMEvent dual dict & attribute access, root unwrapping, case-mapping, deep path traversal, JSON serialization.
2. Case-insensitive string enum coercion (EntityType, PlaybookType, CaseStatus, CasePriority, FilterOperator).
3. Polymorphic filter and collection coercion (FieldFilter, dict, tuple, scalar-to-list).
4. Case ID normalization (integer, string, resource URI prefixes).
5. Facade method polymorphic signature resolution.
"""

import json
import unittest
from typing import Any, Dict, List, Optional
from unittest.mock import MagicMock

from engine.domain import (
    CasePriority,
    CaseStatus,
    EntityType,
    FieldFilter,
    FilterOperator,
    PlaybookType,
    SearchRequest,
    SearchSession,
    UDMEvent,
    coerce_case_priority,
    coerce_case_status,
    coerce_entity_type,
    coerce_field_filters,
    coerce_filter_operator,
    coerce_playbook_type,
)
from engine.facade import SecOpsEngine, _normalize_case_id
from engine.registry import WorkflowRegistry


class TestUDMEvent(unittest.TestCase):
    """Verifies that UDMEvent fulfills the universal dictionary + attribute standard."""

    def setUp(self):
        self.raw_event_payload = {
            "event": {
                "metadata": {
                    "eventTimestamp": "2026-09-04T12:00:00.123456Z",
                    "eventType": "PROCESS_LAUNCH",
                    "logType": "WINDOWS_SYSMON",
                    "productName": "Microsoft-Windows-Sysmon",
                },
                "principal": {
                    "ip": "192.168.1.100",
                    "hostname": "workstation-01",
                    "user": {
                        "userid": "alice",
                        "emailAddresses": ["alice@corp.internal"],
                    },
                },
                "target": {
                    "process": {
                        "commandLine": "powershell.exe -enc AAAA",
                        "file": {
                            "sha256": "abcdef1234567890abcdef1234567890abcdef1234567890abcdef1234567890",
                        },
                    },
                },
            }
        }

    def test_isinstance_dict(self):
        ev = UDMEvent(self.raw_event_payload)
        self.assertIsInstance(ev, dict)
        self.assertEqual(ev["event"]["metadata"]["eventType"], "PROCESS_LAUNCH")

    def test_root_envelope_transparency(self):
        ev = UDMEvent(self.raw_event_payload)
        # Direct key access without explicit ['event']
        self.assertIn("metadata", ev)
        self.assertIn("principal", ev)
        self.assertEqual(ev["metadata"]["eventType"], "PROCESS_LAUNCH")
        self.assertEqual(ev["principal"]["ip"], "192.168.1.100")
        # Explicit nested access still works
        self.assertEqual(ev["event"]["principal"]["ip"], "192.168.1.100")

    def test_flat_event_without_outer_envelope(self):
        flat = {
            "metadata": {"eventTimestamp": "2026-09-04T12:00:00Z", "eventType": "USER_LOGIN"},
            "principal": {"ip": "10.0.0.5"},
        }
        ev = UDMEvent(flat)
        self.assertEqual(ev["metadata"]["eventType"], "USER_LOGIN")
        self.assertEqual(ev.principal.ip, "10.0.0.5")

    def test_dot_notation_and_case_mapping(self):
        ev = UDMEvent(self.raw_event_payload)
        # CamelCase and snake_case resolution
        self.assertEqual(ev.metadata.event_timestamp, "2026-09-04T12:00:00.123456Z")
        self.assertEqual(ev.metadata.eventTimestamp, "2026-09-04T12:00:00.123456Z")
        self.assertEqual(ev.metadata.event_type, "PROCESS_LAUNCH")
        self.assertEqual(ev.principal.ip, "192.168.1.100")
        self.assertEqual(ev.principal.user.userid, "alice")
        self.assertEqual(
            ev.target.process.file.sha256,
            "abcdef1234567890abcdef1234567890abcdef1234567890abcdef1234567890",
        )

    def test_attribute_error_on_missing_key(self):
        ev = UDMEvent(self.raw_event_payload)
        with self.assertRaises(AttributeError):
            _ = ev.non_existent_field

    def test_convenience_properties(self):
        ev = UDMEvent(self.raw_event_payload)
        self.assertEqual(ev.timestamp, "2026-09-04T12:00:00.123456Z")
        self.assertEqual(ev.event_type, "PROCESS_LAUNCH")
        self.assertEqual(ev.log_type, "WINDOWS_SYSMON")
        self.assertEqual(ev.product_name, "Microsoft-Windows-Sysmon")

    def test_get_field_path(self):
        ev = UDMEvent(self.raw_event_payload)
        self.assertEqual(ev.get_field("principal.ip"), "192.168.1.100")
        self.assertEqual(ev.get_field("principal.user.userid"), "alice")
        self.assertEqual(
            ev.get_field("target.process.file.sha256"),
            "abcdef1234567890abcdef1234567890abcdef1234567890abcdef1234567890",
        )
        self.assertEqual(ev.get_field("non.existent.path", "DEFAULT"), "DEFAULT")

    def test_to_dict_and_json_serialization(self):
        ev = UDMEvent(self.raw_event_payload)
        as_dict = ev.to_dict()
        self.assertIsInstance(as_dict, dict)
        serialized = json.dumps(ev)
        deserialized = json.loads(serialized)
        self.assertEqual(
            deserialized["event"]["principal"]["ip"], "192.168.1.100"
        )


class TestEnumCoercion(unittest.TestCase):
    """Verifies that enum parameters accept case-insensitive string aliases."""

    def test_entity_type_coercion(self):
        self.assertEqual(coerce_entity_type("ip"), EntityType.IP)
        self.assertEqual(coerce_entity_type("IP"), EntityType.IP)
        self.assertEqual(coerce_entity_type("ip_address"), EntityType.IP)
        self.assertEqual(coerce_entity_type("ipv4"), EntityType.IP)
        self.assertEqual(coerce_entity_type("hostname"), EntityType.HOSTNAME)
        self.assertEqual(coerce_entity_type("host"), EntityType.HOSTNAME)
        self.assertEqual(coerce_entity_type("user"), EntityType.USER)
        self.assertEqual(coerce_entity_type("username"), EntityType.USER)
        self.assertEqual(coerce_entity_type("hash"), EntityType.SHA256)
        self.assertEqual(coerce_entity_type("sha256"), EntityType.SHA256)
        self.assertEqual(coerce_entity_type("domain"), EntityType.DOMAIN)
        self.assertEqual(coerce_entity_type(EntityType.URL), EntityType.URL)

        with self.assertRaises(ValueError):
            coerce_entity_type("completely_invalid_entity_type")

    def test_playbook_type_coercion(self):
        self.assertEqual(coerce_playbook_type("regular"), PlaybookType.REGULAR)
        self.assertEqual(coerce_playbook_type("REGULAR"), PlaybookType.REGULAR)
        self.assertEqual(coerce_playbook_type("nested"), PlaybookType.NESTED)
        self.assertEqual(coerce_playbook_type("standard"), PlaybookType.REGULAR)
        self.assertEqual(coerce_playbook_type(PlaybookType.REGULAR), PlaybookType.REGULAR)

        self.assertEqual(coerce_playbook_type("unknown_playbook_type"), PlaybookType.UNKNOWN)

    def test_case_status_and_priority_coercion(self):
        self.assertEqual(coerce_case_status("open"), CaseStatus.OPEN)
        self.assertEqual(coerce_case_status("CLOSED"), CaseStatus.CLOSED)
        self.assertEqual(coerce_case_status(CaseStatus.OPEN), CaseStatus.OPEN)

        self.assertEqual(coerce_case_priority("critical"), CasePriority.CRITICAL)
        self.assertEqual(coerce_case_priority("HIGH"), CasePriority.HIGH)
        self.assertEqual(coerce_case_priority(CasePriority.MEDIUM), CasePriority.MEDIUM)

    def test_filter_operator_coercion(self):
        self.assertEqual(coerce_filter_operator("="), FilterOperator.EQUALS)
        self.assertEqual(coerce_filter_operator("=="), FilterOperator.EQUALS)
        self.assertEqual(coerce_filter_operator("equals"), FilterOperator.EQUALS)
        self.assertEqual(coerce_filter_operator("!="), FilterOperator.NOT_EQUALS)
        self.assertEqual(coerce_filter_operator("ne"), FilterOperator.NOT_EQUALS)
        self.assertEqual(coerce_filter_operator("contains"), FilterOperator.CONTAINS)
        self.assertEqual(coerce_filter_operator("regex"), FilterOperator.REGEX_MATCH)


class TestCollectionAndFilterCoercion(unittest.TestCase):
    """Verifies polymorphic coercion of filters and collections."""

    def test_single_field_filter(self):
        f = FieldFilter(field="principal.ip", operator=FilterOperator.EQUALS, value="10.0.0.1")
        res = coerce_field_filters(f)
        self.assertEqual(len(res), 1)
        self.assertEqual(res[0].field, "principal.ip")
        self.assertEqual(res[0].operator, FilterOperator.EQUALS)
        self.assertEqual(res[0].value, "10.0.0.1")

    def test_dict_spec_and_list_of_dicts(self):
        single_dict = {"field": "target.hostname", "operator": "!=", "value": "server-01"}
        res = coerce_field_filters(single_dict)
        self.assertEqual(len(res), 1)
        self.assertEqual(res[0].field, "target.hostname")
        self.assertEqual(res[0].operator, FilterOperator.NOT_EQUALS)
        self.assertEqual(res[0].value, "server-01")

        list_of_dicts = [
            {"field": "principal.ip", "operator": "=", "value": "10.0.0.1"},
            {"field": "metadata.event_type", "value": "USER_LOGIN"},
        ]
        res2 = coerce_field_filters(list_of_dicts)
        self.assertEqual(len(res2), 2)
        self.assertEqual(res2[0].field, "principal.ip")
        self.assertEqual(res2[1].operator, FilterOperator.EQUALS)

    def test_tuple_spec(self):
        t3 = ("principal.ip", "=", "10.0.0.1")
        res3 = coerce_field_filters(t3)
        self.assertEqual(len(res3), 1)
        self.assertEqual(res3[0].operator, FilterOperator.EQUALS)

        t2 = ("principal.ip", "10.0.0.1")
        res2 = coerce_field_filters(t2)
        self.assertEqual(len(res2), 1)
        self.assertEqual(res2[0].operator, FilterOperator.EQUALS)
        self.assertEqual(res2[0].value, "10.0.0.1")


class TestCaseIdNormalization(unittest.TestCase):
    """Verifies that case IDs in integer or URI form normalize to string IDs."""

    def test_normalize_case_id(self):
        self.assertEqual(_normalize_case_id(104984), "104984")
        self.assertEqual(_normalize_case_id("104984"), "104984")
        self.assertEqual(_normalize_case_id("cases/104984"), "104984")
        self.assertEqual(
            _normalize_case_id("projects/sdl-preview-americas/locations/us/cases/104984"),
            "104984",
        )
        self.assertEqual(_normalize_case_id("  104984  "), "104984")


class TestFacadePolymorphicSignatures(unittest.TestCase):
    """Verifies that SecOpsEngine methods handle polymorphic arguments correctly."""

    def setUp(self):
        self.mock_adapter = MagicMock()
        self.engine = SecOpsEngine(
            adapter=self.mock_adapter, custom_registry=WorkflowRegistry()
        )

    def test_search_udm_polymorphic(self):
        mock_wf = MagicMock()
        self.engine._wf_cache["_search_udm_wf"] = mock_wf

        # Pattern 1: Structured SearchRequest
        req = SearchRequest(
            query='principal.ip = "10.0.0.1"',
            start_time="2026-09-01T00:00:00Z",
            end_time="2026-09-02T00:00:00Z",
            limit=50,
        )
        self.engine.search_udm(req)
        mock_wf.execute.assert_called_with(
            request=req,
            on_batch=None,
            on_state_change=None,
            cancel_token=None,
        )

        # Pattern 2: Positional query string
        self.engine.search_udm(
            'principal.ip = "10.0.0.1"',
            start_time="2026-09-01T00:00:00Z",
            end_time="2026-09-02T00:00:00Z",
            limit=25,
        )
        last_arg = mock_wf.execute.call_args[1]["request"]
        self.assertIsInstance(last_arg, SearchRequest)
        self.assertEqual(last_arg.query, 'principal.ip = "10.0.0.1"')
        self.assertEqual(last_arg.limit, 25)

        # Pattern 3: Keyword arguments
        self.engine.search_udm(
            query='principal.ip = "10.0.0.2"',
            start_time="2026-09-01T00:00:00Z",
            end_time="2026-09-02T00:00:00Z",
            limit=10,
        )
        last_arg = mock_wf.execute.call_args[1]["request"]
        self.assertIsInstance(last_arg, SearchRequest)
        self.assertEqual(last_arg.query, 'principal.ip = "10.0.0.2"')
        self.assertEqual(last_arg.limit, 10)

    def test_search_from_entity_string_coercion(self):
        mock_wf = MagicMock()
        self.engine._wf_cache["_search_from_entity_wf"] = mock_wf

        self.engine.search_from_entity(
            entity_type="ip",
            entity_value="10.0.0.1",
            start_time="2026-09-01T00:00:00Z",
            end_time="2026-09-02T00:00:00Z",
        )
        mock_wf.execute.assert_called_with(
            entity_type=EntityType.IP,
            entity_value="10.0.0.1",
            start_time="2026-09-01T00:00:00Z",
            end_time="2026-09-02T00:00:00Z",
            receive_limit=10000,
            batch_size=2000,
            on_batch=None,
            on_state_change=None,
            cancel_token=None,
        )

    def test_refine_search_tuple_filter(self):
        mock_wf = MagicMock()
        self.engine._wf_cache["_refine_search_wf"] = mock_wf

        self.engine.refine_search(
            base="search_session_123",
            filters=("principal.ip", "10.0.0.1"),
        )
        filters_passed = mock_wf.execute.call_args[1]["filters"]
        self.assertEqual(len(filters_passed), 1)
        self.assertIsInstance(filters_passed[0], FieldFilter)
        self.assertEqual(filters_passed[0].field, "principal.ip")
        self.assertEqual(filters_passed[0].operator, FilterOperator.EQUALS)
        self.assertEqual(filters_passed[0].value, "10.0.0.1")

    def test_search_playbooks_string_type(self):
        mock_wf = MagicMock()
        self.engine._wf_cache["_search_playbooks_wf"] = mock_wf

        self.engine.search_playbooks(query="Ransomware", playbook_type="regular")
        q_passed = mock_wf.execute.call_args[0][0]
        self.assertEqual(q_passed.playbook_type, PlaybookType.REGULAR)

    def test_add_data_table_rows_single_dict(self):
        mock_wf = MagicMock()
        self.engine._wf_cache["_add_data_table_rows_wf"] = mock_wf

        self.engine.add_data_table_rows(
            table_name_or_id="threat_intel_ips",
            rows={"ip": "1.2.3.4", "risk": "high"},
        )
        rows_passed = mock_wf.execute.call_args[1]["rows"]
        self.assertIsInstance(rows_passed, list)
        self.assertEqual(len(rows_passed), 1)
        self.assertEqual(rows_passed[0]["ip"], "1.2.3.4")

    def test_investigate_case_numeric_id(self):
        mock_wf = MagicMock()
        self.engine._wf_cache["_investigate_case_wf"] = mock_wf

        self.engine.investigate_case(104984)
        mock_wf.execute.assert_called_with(case_id="104984")

    def test_default_24h_time_window_in_search_methods(self):
        mock_udm_wf = MagicMock()
        mock_stats_wf = MagicMock()
        mock_pivot_wf = MagicMock()
        self.engine._wf_cache["_search_udm_wf"] = mock_udm_wf
        self.engine._wf_cache["_search_udm_stats_wf"] = mock_stats_wf
        self.engine._wf_cache["_search_from_entity_wf"] = mock_pivot_wf

        self.engine.search_udm(query='principal.ip = "10.0.0.1"')
        req = mock_udm_wf.execute.call_args[1]["request"]
        self.assertTrue(req.start_time.endswith("Z"))
        self.assertTrue(req.end_time.endswith("Z"))

        self.engine.search_udm_stats(query='metadata.event_type = "USER_LOGIN" | count()')
        stats_req = mock_stats_wf.execute.call_args[1]["request"]
        self.assertTrue(stats_req.start_time.endswith("Z"))
        self.assertTrue(stats_req.end_time.endswith("Z"))

        self.engine.search_from_entity(entity_type="ip", entity_value="10.0.0.1")
        pivot_kwargs = mock_pivot_wf.execute.call_args[1]
        self.assertTrue(pivot_kwargs["start_time"].endswith("Z"))
        self.assertTrue(pivot_kwargs["end_time"].endswith("Z"))

    def test_case_priority_coercion_in_search_and_triage(self):
        mock_search_wf = MagicMock()
        mock_triage_wf = MagicMock()
        self.engine._wf_cache["_search_cases_wf"] = mock_search_wf
        self.engine._wf_cache["_orchestrate_case_triage_wf"] = mock_triage_wf

        self.engine.search_cases(priorities="high")
        q_passed = mock_search_wf.execute.call_args[0][0]
        self.assertEqual(q_passed.priorities, ["HIGH"])

        self.engine.orchestrate_case_triage(priorities=["critical", CasePriority.LOW])
        triage_kwargs = mock_triage_wf.execute.call_args[1]
        self.assertEqual(triage_kwargs["priorities"], ["CRITICAL", "LOW"])

    def test_scalar_to_list_normalization_in_facade_methods(self):
        mock_manage_ref_wf = MagicMock()
        mock_test_ref_wf = MagicMock()
        mock_card_wf = MagicMock()
        mock_search_cases_wf = MagicMock()
        self.engine._wf_cache["_manage_findings_refinements_wf"] = mock_manage_ref_wf
        self.engine._wf_cache["_test_findings_refinement_wf"] = mock_test_ref_wf
        self.engine._wf_cache["_analyze_entity_cardinality_wf"] = mock_card_wf
        self.engine._wf_cache["_search_cases_wf"] = mock_search_cases_wf

        self.engine.create_findings_refinement(
            display_name="Exclude scanner",
            query='principal.ip = "10.0.0.1"',
            curated_rule_ids="ur_123",
        )
        self.assertEqual(
            mock_manage_ref_wf.create_refinement.call_args[1]["curated_rule_ids"],
            ["ur_123"],
        )

        self.engine.test_findings_refinement(
            curated_rule_ids="ur_123",
            query='principal.ip = "10.0.0.1"',
        )
        self.assertEqual(
            mock_test_ref_wf.execute.call_args[1]["curated_rule_ids"],
            ["ur_123"],
        )

        self.engine.analyze_entity_cardinality(
            rule_id="ru_123",
            dimensions="principal.ip",
        )
        self.assertEqual(
            mock_card_wf.execute.call_args[1]["dimensions"],
            ["principal.ip"],
        )

        self.engine.search_cases_by_entity(
            entity_value="10.0.0.1",
            environments="Default Environment",
        )
        q_passed = mock_search_cases_wf.execute.call_args[0][0]
        self.assertEqual(q_passed.environments, ["Default Environment"])

    def test_get_case_timeline_uses_cached_workflow_map(self):
        mock_timeline_wf = MagicMock()
        self.engine._wf_cache["_get_case_timeline_wf"] = mock_timeline_wf

        self.engine.get_case_timeline("cases/104984")
        mock_timeline_wf.execute.assert_called_once_with(case_id="104984")

    def test_per_instance_registry_isolation(self):
        adapter_a = MagicMock()
        adapter_b = MagicMock()
        engine_a = SecOpsEngine(adapter=adapter_a)
        engine_b = SecOpsEngine(adapter=adapter_b)

        self.assertIsNot(engine_a.registry, engine_b.registry)
        cap_a = engine_a.registry.get("case.investigate")
        cap_b = engine_b.registry.get("case.investigate")
        self.assertIs(cap_a.handler.__self__, engine_a)
        self.assertIs(cap_b.handler.__self__, engine_b)


class TestPackageExports(unittest.TestCase):
    """Verifies that engine.__init__ exports all public symbols cleanly."""

    def test_all_exports_exist_and_wildcard_import_succeeds(self):
        import engine

        missing = [name for name in engine.__all__ if not hasattr(engine, name)]
        self.assertEqual(missing, [], f"Phantom symbols in engine.__all__: {missing}")

        ns: Dict[str, Any] = {}
        exec("from engine import *", ns)  # noqa: S102
        for name in engine.__all__:
            self.assertIn(name, ns)


class TestDomainAndSchemaLayer3(unittest.TestCase):
    """Verifies Layer 3 domain models, mixins, and schema canonicalization."""

    def test_udm_event_bidirectional_snake_and_camel_case(self):
        ev = UDMEvent(
            {
                "event": {
                    "metadata": {
                        "event_timestamp": "2026-09-04T12:00:00Z",
                        "event_type": "USER_LOGIN",
                    },
                    "principal": {
                        "user": {
                            "user_display_name": "Alice Smith",
                        }
                    },
                }
            }
        )
        self.assertEqual(ev.metadata.eventTimestamp, "2026-09-04T12:00:00Z")
        self.assertEqual(ev.metadata.eventType, "USER_LOGIN")
        self.assertEqual(ev.get_field("metadata.eventType"), "USER_LOGIN")
        self.assertEqual(ev.get_field("principal.user.userDisplayName"), "Alice Smith")
        self.assertTrue("eventType" in ev.metadata)

    def test_event_investigation_envelope_and_case_resolution(self):
        from engine.domain import EventInvestigation

        inv = EventInvestigation(
            event_id="ev-123",
            event={
                "event": {
                    "metadata": {"eventType": "PROCESS_LAUNCH", "productName": "Sysmon"},
                    "principal": {"user": {"windowsSid": "S-1-5-18"}},
                }
            },
        )
        self.assertEqual(inv.event_type, "PROCESS_LAUNCH")
        self.assertEqual(inv.product_name, "Sysmon")
        self.assertEqual(inv.get_field("metadata.event_type"), "PROCESS_LAUNCH")
        self.assertEqual(inv.get_field("principal.user.windows_sid"), "S-1-5-18")
        self.assertEqual(
            inv.build_pivot_filter("principal.user.windowsSid").to_udm_clause(),
            'principal.user.windows_sid = "S-1-5-18"',
        )

    def test_field_filter_udm_escaping_and_schema_canonicalization(self):
        from engine.schema import canonicalize_udm_field

        self.assertEqual(
            canonicalize_udm_field("udm.principal.user.windowsSid"),
            "principal.user.windows_sid",
        )
        self.assertEqual(
            canonicalize_udm_field("event.network.http.referralUrl"),
            "network.http.referral_url",
        )

        f_eq = FieldFilter(
            field_path="target.file.fullPath",
            operator=FilterOperator.EQUALS,
            value=r'C:\Users\alice\file"1".exe',
        )
        self.assertEqual(
            f_eq.to_udm_clause(),
            r'target.file.full_path = "C:\\Users\\alice\\file\"1\".exe"',
        )

        f_regex = FieldFilter(
            field_path="principal.hostname",
            operator=FilterOperator.REGEX_MATCH,
            value=r"^srv-\d+\.corp$",
        )
        self.assertEqual(
            f_regex.to_udm_clause(),
            r'principal.hostname =~ "^srv-\d+\.corp$"',
        )

    def test_dashboard_detail_dashboard_type_alias(self):
        from engine.domain import DashboardDetail, DashboardSummary

        summary = DashboardSummary(
            id="db-1",
            name="projects/p/locations/us/instances/i/nativeDashboards/db-1",
            display_name="SOC Overview",
            description="Main dashboard",
            type="CUSTOM",
            create_time="2026-09-01T00:00:00Z",
            update_time="2026-09-02T00:00:00Z",
        )
        detail = DashboardDetail(summary=summary, charts=[])
        self.assertEqual(summary.dashboard_type, "CUSTOM")
        self.assertEqual(detail.dashboard_type, "CUSTOM")

    def test_playbook_instance_executed_path_mixed_naive_and_aware_datetimes(self):
        from datetime import datetime, timezone
        from engine.domain import PlaybookInstanceRun, PlaybookInstanceStep

        s1 = PlaybookInstanceStep(
            identifier="step_a",
            name="Step A",
            action_name="ActA",
            status="COMPLETED",
            start_time=datetime(2026, 9, 1, 12, 0, 0),  # naive
        )
        s2 = PlaybookInstanceStep(
            identifier="step_b",
            name="Step B",
            action_name="ActB",
            status="COMPLETED",
            start_time=datetime(2026, 9, 1, 11, 0, 0, tzinfo=timezone.utc),  # aware
        )
        run = PlaybookInstanceRun(
            instance_id="inst-1",
            identifier="pb-1",
            name="PB",
            case_id="100",
            alert_identifier="ag-1",
            status="FINISHED",
            steps=[s1, s2],
            relations=[],
        )
        path = run.executed_path()
        self.assertEqual([s.identifier for s in path], ["step_b", "step_a"])

    def test_universal_dict_mixin_post_init_and_mutation_sync(self):
        from dataclasses import dataclass
        from engine.domain import UniversalDictMixin

        @dataclass
        class SampleDictModel(UniversalDictMixin):
            raw_id: str
            normalized_id: str = ""

            def __post_init__(self):
                self.normalized_id = self.raw_id.strip().upper()

        m = SampleDictModel(raw_id="  abc  ")
        self.assertEqual(m.normalized_id, "ABC")
        self.assertEqual(dict(m)["normalized_id"], "ABC")
        self.assertEqual(json.loads(json.dumps(m))["normalized_id"], "ABC")

        m.normalized_id = "XYZ"
        self.assertEqual(dict(m)["normalized_id"], "XYZ")

    def test_universal_batch_mixin_on_list_results_and_health_reports(self):
        from engine.domain import (
            DashboardHealthReport,
            DataTable,
            DataTableHealthReport,
            DataTableListResult,
            RuleListResult,
            RuleSummary,
        )

        dt_res = DataTableListResult(
            tables=[DataTable(name="n", id="t1", display_name="T1")]
        )
        self.assertEqual(len(dt_res), 1)
        self.assertEqual(list(dt_res)[0].id, "t1")

        rule_res = RuleListResult(
            rules=[RuleSummary(name="rules/ru_1", display_name="R1")]
        )
        self.assertEqual(len(rule_res), 1)
        self.assertEqual(rule_res[0].rule_id, "ru_1")

        db_rep = DashboardHealthReport(
            total_dashboards_audited=0,
            healthy_count=0,
            recently_created_count=0,
            recently_modified_count=0,
            broken_query_count=0,
            empty_dashboard_count=0,
            stale_count=0,
            custom_count=0,
            curated_count=0,
            findings=[],
        )
        self.assertEqual(len(db_rep), 0)
        self.assertEqual(db_rep.items, [])

        dt_rep = DataTableHealthReport(
            total_tables_audited=0,
            healthy_count=0,
            empty_referenced_count=0,
            orphan_count=0,
            recently_created_count=0,
            recently_modified_count=0,
            stale_count=0,
            schema_issue_count=0,
            findings=[],
        )
        self.assertEqual(len(dt_rep), 0)
        self.assertEqual(dt_rep.items, [])


if __name__ == "__main__":
    unittest.main()

