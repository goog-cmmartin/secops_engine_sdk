"""End-to-end async tests for SecOpsTUI running in Textual test pilot."""

import unittest
from datetime import datetime, timezone

from engine.domain import (
    CaseAlertSummary,
    CaseInvestigation,
    CasePriority,
    CaseSearchBatch,
    CaseSearchResultItem,
    CaseStatus,
    InvolvedEntitySummary,
    AlertInvestigation,
)
from clients.tui.app import SecOpsTUI
from clients.tui.views.case_view import CaseWorkspaceView
from clients.tui.command_launcher import CommandLauncherModal


class MockEngine:
    """Mock engine for asynchronous Textual test runner."""

    def __init__(self):
        self.now = datetime.now(timezone.utc)
        self.demo_items = [
            CaseSearchResultItem(
                case_id="1001",
                title="Impossible Travel Detected for amartin",
                create_time=self.now,
                priority=CasePriority.CRITICAL,
                stage="Triage",
                alerts_count=2,
                user_assigned="amartin",
            ),
            CaseSearchResultItem(
                case_id="1002",
                title="Suspected Credential Phishing Burst",
                create_time=self.now,
                priority=CasePriority.HIGH,
                stage="Investigation",
                alerts_count=3,
                user_assigned="jdoe",
            ),
        ]

    def search_cases(self, query: str = "", page_size: int = 50, page_token: str = None):
        filtered = [
            it for it in self.demo_items
            if not query or query.lower() in it.title.lower() or query.lower() in it.priority.name.lower()
        ]
        return CaseSearchBatch(
            items=filtered,
            total_count=len(filtered),
            page_size=page_size,
            page_number=0,
            provenance={"test": True},
        )

    def investigate_case(self, case_id: str):
        item = next((it for it in self.demo_items if it.case_id == str(case_id)), self.demo_items[0])
        return CaseInvestigation(
            case_id=item.case_id,
            name=f"cases/{item.case_id}",
            display_name=item.title,
            status=CaseStatus.OPEN,
            priority=item.priority,
            stage=item.stage,
            create_time=item.create_time,
            update_time=self.now,
            assignee=item.user_assigned,
            alert_count=item.alerts_count,
            alerts=[
                CaseAlertSummary(
                    name=f"cases/{item.case_id}/alerts/{j}",
                    identifier=f"alert-{j}",
                    display_name=f"{item.title} — Alert #{j+1}",
                    priority=item.priority.name,
                    status="OPEN",
                    product="Chronicle",
                    vendor="Google",
                    event_count=10 * (j + 1),
                    start_time=item.create_time,
                    end_time=self.now,
                    rule_name="ru_credential_access",
                    attached_playbook_name="Auto-Triage" if j == 0 else None,
                    playbook_status="Completed" if j == 0 else None,
                )
                for j in range(item.alerts_count)
            ],
            entities=[
                InvolvedEntitySummary(
                    identifier="amartin@example.com",
                    display_name="amartin@example.com",
                    entity_type="USER",
                    role="source",
                    is_suspicious=True,
                )
            ],
            comments=[],
        )

    def investigate_alert(self, alert_name: str):
        return AlertInvestigation(
            alert_name=alert_name,
            case_id="1001",
            display_name="Alert Deep Dive",
            priority="CRITICAL",
            status="OPEN",
            rule_name="ru_credential_access",
            rule_id="ru_12345",
            risk_score=95,
            detection_time=self.now,
            product="Chronicle",
            vendor="Google",
            event_count=20,
            entities=[
                InvolvedEntitySummary(
                    identifier="amartin@example.com",
                    display_name="amartin@example.com",
                    entity_type="USER",
                    role="source",
                    is_suspicious=True,
                )
            ],
            associated_events=[{"event": "AUTH", "result": "FAILED"}],
        )


class TestTUIAppAsync(unittest.IsolatedAsyncioTestCase):
    """Asynchronous testing of SecOpsTUI in Textual pilot mode."""

    async def test_app_pilot_lifecycle(self):
        engine = MockEngine()
        app = SecOpsTUI(engine=engine)

        async with app.run_test() as pilot:
            # Check app mounted properly without MarkupError or render crashes
            self.assertIsNotNone(app.query_one("#status_bar"))
            self.assertIsNotNone(app.query_one("#workspaces_tabbed"))

            # Test new workspace creation
            await pilot.press("ctrl+n")
            await pilot.pause()
            self.assertEqual(app._workspace_counter, 2)

            # Test switching workspace
            await pilot.press("alt+1")
            await pilot.pause()

            # Test command launcher opening and dismissal
            await pilot.press("ctrl+k")
            await pilot.pause()
            self.assertIsInstance(app.screen, CommandLauncherModal)
            await pilot.press("escape")
            await pilot.pause()
            self.assertNotIsInstance(app.screen, CommandLauncherModal)


if __name__ == "__main__":
    unittest.main()
