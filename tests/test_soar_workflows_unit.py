"""Offline unit tests for Layer 4b SOAR workflows and playbook health runbook."""

from datetime import datetime, timezone
import unittest
from unittest.mock import MagicMock

from engine.domain import (
    CaseAlertSummary,
    CaseCommentRecord,
    CaseInvestigation,
    CasePriority,
    CaseStatus,
    CaseSummary,
    InvolvedEntitySummary,
    PlaybookBatch,
    PlaybookSummary,
    PlaybookType,
    SearchSession,
)
from engine.workflows.case_ai_investigation import InvestigateCaseWithAIWorkflow
from engine.workflows.case_triage import CaseTriageWorkflow, OrchestrateCaseTriageWorkflow
from engine.workflows.case_wall import ListCaseCommentsWorkflow
from engine.workflows.content_pack import GetContentPackDetailWorkflow
from engine.workflows.integration import (
    GetIntegrationDetailWorkflow,
    ListIntegrationInstancesWorkflow,
    SearchIntegrationsWorkflow,
    _extract_integration_id_from_instance,
)
from engine.workflows.playbook import (
    GetPlaybookWorkflow,
    SearchPlaybooksWorkflow,
    _parse_playbook_timestamp,
)
from engine.workflows.soar_settings import SearchEnvironmentsWorkflow
from runbooks.operations.soar_playbook_health import generate_soar_playbook_health_report


class TestSoarWorkflowsUnit(unittest.TestCase):
    """Unit tests verifying Layer 4b SOAR workflow fixes."""

    def test_case_triage_apply_stage_update_and_naive_comment_timestamps(self):
        """CaseTriageWorkflow.execute passes updates dict to update_case and sorts naive/aware comments."""
        adapter = MagicMock()
        wf = CaseTriageWorkflow(adapter=adapter)
        inv = CaseInvestigation(
            case_id="101",
            name="cases/101",
            display_name="Critical Intrusion",
            status=CaseStatus.OPEN,
            priority=CasePriority.CRITICAL,
            stage="Triage",
            create_time=datetime(2026, 5, 1, 10, 0, tzinfo=timezone.utc),
            update_time=datetime(2026, 5, 1, 11, 0, tzinfo=timezone.utc),
            assignee="analyst@example.com",
            alert_count=1,
            alerts=[
                CaseAlertSummary(
                    name="alerts/1",
                    identifier="a1",
                    display_name="Malware Alert",
                    priority="CRITICAL",
                    status="OPEN",
                )
            ],
            entities=[
                InvolvedEntitySummary(
                    identifier="198.51.100.10",
                    display_name="198.51.100.10",
                    entity_type="ADDRESS",
                    is_suspicious=True,
                )
            ],
            comments=[
                CaseCommentRecord(
                    name="c1",
                    comment="Older naive timestamp comment",
                    create_time=datetime(2026, 5, 1, 9, 0),
                ),
                CaseCommentRecord(
                    name="c2",
                    comment="Newer aware timestamp comment",
                    create_time=datetime(2026, 5, 1, 10, 30, tzinfo=timezone.utc),
                ),
            ],
        )
        wf.investigate_workflow = MagicMock()
        wf.investigate_workflow.execute.return_value = inv

        assessment = wf.execute(
            case_id="101",
            fetch_summary=False,
            search_precedents=False,
            apply_stage_update=True,
            post_comment=False,
        )
        self.assertEqual(assessment.latest_comment, "Newer aware timestamp comment")
        adapter.update_case.assert_called_once_with(
            case_id="101",
            updates={"stage": "Incident"},
            update_mask="stage",
        )
        self.assertEqual(inv.stage, "Incident")

    def test_orchestrate_case_triage_records_per_case_errors(self):
        """OrchestrateCaseTriageWorkflow records failed case IDs in provenance['errors']."""
        adapter = MagicMock()
        wf = OrchestrateCaseTriageWorkflow(adapter=adapter)
        wf.triage_workflow = MagicMock()
        wf.triage_workflow.execute.side_effect = RuntimeError("Case lookup timeout")

        batch = wf.execute(case_ids=["201"])
        self.assertEqual(len(batch.results), 0)
        self.assertIn("errors", batch.provenance)
        self.assertIn("201", batch.provenance["errors"])

    def test_list_case_comments_sorts_mixed_naive_and_aware_timestamps(self):
        """ListCaseCommentsWorkflow sorts comments even when timestamps mix naive and aware datetimes."""
        adapter = MagicMock()
        adapter.list_case_comments.return_value = [
            {"name": "c1", "comment": "First", "createTime": "2026-05-01T08:00:00Z"},
            {"name": "c2", "comment": "Second", "createTime": "2026-05-01T12:00:00Z"},
        ]
        wf = ListCaseCommentsWorkflow(adapter=adapter)
        res = wf.execute("101")
        self.assertEqual([r.comment for r in res], ["Second", "First"])

    def test_ai_investigation_hunts_hashes_and_escapes_udm(self):
        """InvestigateCaseWithAIWorkflow hunts extracted hashes and escapes UDM literals."""
        adapter = MagicMock()
        wf = InvestigateCaseWithAIWorkflow(adapter=adapter)
        wf.investigate_workflow = MagicMock()
        wf.investigate_workflow.execute.return_value = CaseInvestigation(
            case_id="500",
            name="cases/500",
            display_name="Hash Case",
            status=CaseStatus.OPEN,
            priority=CasePriority.HIGH,
            stage="Triage",
            create_time=None,
            update_time=None,
            assignee=None,
            alert_count=0,
        )
        wf.case_summary_workflow = MagicMock()
        wf.case_summary_workflow.execute.return_value = CaseSummary(
            case_id="500",
            state="SUCCESSFUL",
            summary="Suspicious file 44d88612fea8a8f36de82e1278abb02f from 198.51.100.7",
        )
        wf.search_udm_workflow = MagicMock()
        wf.search_udm_workflow.execute.return_value = SearchSession(received_count=3)

        result = wf.execute(case_id="500", dry_run=True)
        self.assertIn("44d88612fea8a8f36de82e1278abb02f", result.extracted_hashes)
        self.assertEqual(result.hunt_results.get("44d88612fea8a8f36de82e1278abb02f"), 3)
        self.assertEqual(result.hunt_results.get("198.51.100.7"), 3)

    def test_integration_instance_id_extraction_and_unknown_integration_error(self):
        """Integration workflows preserve integrationIdentifier and reject nonexistent integrations."""
        self.assertEqual(
            _extract_integration_id_from_instance(
                {"integrationIdentifier": "CrowdStrikeFalcon", "name": "inst-1"}
            ),
            "CrowdStrikeFalcon",
        )
        self.assertEqual(
            _extract_integration_id_from_instance(
                {"name": "integrations/Wiz/integrationInstances/99"}
            ),
            "Wiz",
        )

        adapter = MagicMock()
        adapter.list_integrations.return_value = [
            {"identifier": "CrowdStrikeFalcon", "displayName": "CrowdStrike Falcon", "certified": True}
        ]
        adapter.list_integration_instances.return_value = [
            {"identifier": "inst-1", "integrationIdentifier": "CrowdStrikeFalcon", "configured": True}
        ]
        batch = SearchIntegrationsWorkflow(adapter).execute()
        self.assertEqual(len(batch.results), 1)
        self.assertEqual(batch.results[0].instances_count, 1)

        instances = ListIntegrationInstancesWorkflow(adapter).execute()
        self.assertEqual(instances[0].integration_identifier, "CrowdStrikeFalcon")

        adapter.list_integrations.return_value = []
        adapter.list_integration_instances.return_value = []
        adapter.get_marketplace_integration.return_value = {}
        with self.assertRaises(ValueError):
            GetIntegrationDetailWorkflow(adapter).execute("NonExistentIntegration")

    def test_content_pack_exact_match_takes_precedence_over_substring(self):
        """GetContentPackDetailWorkflow matches exact title before substring matches."""
        adapter = MagicMock()
        adapter.list_content_packs.return_value = {
            "contentPacks": [
                {"identifier": "id-1", "name": "packs/id-1", "title": "Cloud AWS Extended"},
                {"identifier": "id-2", "name": "packs/id-2", "title": "AWS"},
            ]
        }
        detail = GetContentPackDetailWorkflow(adapter).execute("AWS")
        self.assertEqual(detail.pack.identifier, "id-2")
        self.assertEqual(detail.pack.title, "AWS")

    def test_playbook_timestamp_parsing_iso_and_ms(self):
        """_parse_playbook_timestamp supports both ISO-8601 strings and epoch ms."""
        dt_iso = _parse_playbook_timestamp("2026-05-01T12:00:00Z", None)
        self.assertIsNotNone(dt_iso)
        self.assertEqual(dt_iso.year, 2026)

        dt_ms = _parse_playbook_timestamp(None, "1787421765613")
        self.assertIsNotNone(dt_ms)
        self.assertIsNotNone(dt_ms.tzinfo)

        adapter = MagicMock()
        adapter.get_playbook_full_info.return_value = {
            "id": "1",
            "identifier": "pb-uuid-1",
            "name": "Test Playbook",
            "creationTime": "2026-05-01T12:00:00Z",
            "modificationTime": "2026-05-02T12:00:00Z",
        }
        detail = GetPlaybookWorkflow(adapter).execute("pb-uuid-1")
        self.assertIsNotNone(detail.creation_time)
        self.assertIsNotNone(detail.modification_time)

    def test_playbook_health_report_surfaces_query_errors(self):
        """generate_soar_playbook_health_report surfaces dashboard query errors."""
        engine = MagicMock()
        engine.search_playbooks.return_value = PlaybookBatch(
            results=[
                PlaybookSummary(
                    id="1",
                    identifier="pb-1",
                    original_identifier="pb-1",
                    name="PB 1",
                    is_enabled=True,
                    is_debug_mode=False,
                    priority=2,
                    category_id=1,
                    category_name="Default",
                    creator="admin",
                    creator_full_name="Admin",
                    playbook_type=PlaybookType.REGULAR,
                )
            ],
            total_count=1,
        )
        engine.adapter.execute_dashboard_query.side_effect = RuntimeError("Dashboard query denied")

        report = generate_soar_playbook_health_report(engine=engine, days=7, scan_deep=True)
        self.assertIn("query_errors", report)
        self.assertGreater(len(report["query_errors"]), 0)
        codes = [f["code"] for f in report["health_findings"]]
        self.assertIn("TELEMETRY_QUERY_ERRORS", codes)

    def test_soar_settings_search_workflows_handle_zero_limit(self):
        """SearchEnvironmentsWorkflow returns all matching items when limit=0."""
        adapter = MagicMock()
        adapter.list_environments.return_value = {
            "environments": [
                {"name": "environments/1", "displayName": "Env 1"},
                {"name": "environments/2", "displayName": "Env 2"},
                {"name": "environments/3", "displayName": "Env 3"},
            ]
        }
        batch = SearchEnvironmentsWorkflow(adapter).execute(limit=0)
        self.assertEqual(len(batch.environments), 3)


if __name__ == "__main__":
    unittest.main()
