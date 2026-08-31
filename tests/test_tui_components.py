import unittest
from datetime import datetime, timezone
from engine.domain import (
    CaseAlertSummary,
    CaseInvestigation,
    CasePriority,
    CaseSearchResultItem,
    CaseStatus,
    InvolvedEntitySummary,
    AlertInvestigation,
)

try:
    from clients.tui import render
    from clients.tui.command_launcher import CommandItem, CommandLauncherModal, default_commands
    from clients.tui.app import SecOpsTUI
    from clients.tui.views.case_view import CaseWorkspaceView
    HAS_TUI = True
except ImportError:
    HAS_TUI = False


@unittest.skipUnless(HAS_TUI, "Textual and Rich packages not installed")
class TestTUIRenderHelpers(unittest.TestCase):
    """Test pure rendering functions in render.py."""

    def test_alert_row_rendering(self):
        alert = CaseAlertSummary(
            name="cases/1001/alerts/1",
            identifier="alert-1",
            display_name="Phishing Token Burst",
            priority="CRITICAL",
            status="OPEN",
            product="Chronicle",
            vendor="Google",
            event_count=42,
            rule_name="ru_phish_01",
            attached_playbook_name="Auto-Triage",
            playbook_status="Completed",
        )
        row = render.alert_row(alert)
        self.assertEqual(len(row), len(render.ALERT_LIST_COLUMNS))
        self.assertIn("CRITICAL", str(row[0]))
        self.assertEqual(row[1], "Phishing Token Burst")
        self.assertIn("OPEN", str(row[2]))
        self.assertEqual(row[3], "Chronicle")
        self.assertEqual(row[4], "ru_phish_01")
        self.assertEqual(row[5], "42")
        self.assertIn("Auto-Triage", str(row[6]))
        self.assertIn("Completed", str(row[6]))

    def test_alert_detail_panel(self):
        alert_inv = AlertInvestigation(
            alert_name="cases/1001/alerts/1",
            case_id="1001",
            display_name="Phishing Token Burst",
            priority="HIGH",
            status="OPEN",
            rule_name="Suspicious Token",
            rule_id="ru_123",
            risk_score=90,
            detection_time=datetime.now(timezone.utc),
            product="Chronicle",
            vendor="Google",
            event_count=10,
            entities=[
                InvolvedEntitySummary(
                    identifier="user@corp.example",
                    display_name="user@corp.example",
                    entity_type="USER",
                    role="source",
                    is_suspicious=True,
                )
            ],
            associated_events=[{"event": "login", "ip": "1.2.3.4"}],
        )
        group = render.alert_detail_panel(alert_inv)
        self.assertIsNotNone(group)
        self.assertEqual(len(group.renderables), 3)

    def test_case_row_and_summary_card(self):
        item = CaseSearchResultItem(
            case_id="1005",
            title="Suspicious Outbound SSH",
            create_time=datetime.now(timezone.utc),
            priority=CasePriority.HIGH,
            stage="Triage",
            alerts_count=3,
            user_assigned="amartin",
        )
        row = render.case_row(item)
        self.assertEqual(len(row), len(render.CASE_LIST_COLUMNS))
        self.assertEqual(row[0], "1005")
        self.assertEqual(row[2], "Suspicious Outbound SSH")

        inv = CaseInvestigation(
            case_id="1005",
            name="cases/1005",
            display_name="Suspicious Outbound SSH",
            status=CaseStatus.OPEN,
            priority=CasePriority.HIGH,
            stage="Triage",
            create_time=datetime.now(timezone.utc),
            update_time=datetime.now(timezone.utc),
            assignee="amartin",
            alert_count=3,
        )
        card = render.case_summary_card(inv)
        self.assertIsNotNone(card)


@unittest.skipUnless(HAS_TUI, "Textual and Rich packages not installed")
class TestCommandLauncher(unittest.TestCase):
    """Test command launcher items and filtering."""

    def test_default_commands(self):
        cmds = default_commands()
        self.assertGreaterEqual(len(cmds), 8)
        ids = [c.command_id for c in cmds]
        self.assertIn("workspace.new", ids)
        self.assertIn("cases.critical", ids)
        self.assertIn("udm.search", ids)

    def test_modal_construction(self):
        modal = CommandLauncherModal()
        self.assertIsNotNone(modal)
        self.assertEqual(len(modal._filtered_commands), len(default_commands()))


@unittest.skipUnless(HAS_TUI, "Textual and Rich packages not installed")
class TestTUIAppInit(unittest.TestCase):
    """Test TUI application instantiation and workspace composition."""

    class DummyEngine:
        def search_cases(self, *args, **kwargs):
            return []

        def investigate_case(self, case_id):
            return None

    def test_app_instantiation(self):
        engine = self.DummyEngine()
        app = SecOpsTUI(engine=engine, initial_query="test query")
        self.assertEqual(app._initial_query, "test query")
        self.assertEqual(app._workspace_counter, 1)


if __name__ == "__main__":
    unittest.main()
