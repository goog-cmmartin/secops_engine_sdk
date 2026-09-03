"""Automated test suite for SecOps Textual TUI (clients/tui/app.py & render.py)."""

import asyncio
import os
import unittest
from datetime import datetime, timedelta

try:
    import rich
    import textual
    from clients.tui.app import (
        AddCommentModal,
        SecOpsTUI,
        SelectAlertModal,
        SelectEntityModal,
        ViewerModal,
    )
    from textual.widgets import OptionList, Static
    from clients.tui.tiles import TileFrame, TileLauncherModal
    from clients.tui import render
    _HAS_TUI_DEPS = True
except (ImportError, ModuleNotFoundError):
    _HAS_TUI_DEPS = False

from run_tui import _build_demo_engine


@unittest.skipUnless(_HAS_TUI_DEPS, "textual/rich dependencies not installed in test environment")
class TestTUIRender(unittest.TestCase):
    """Test stateless Rich rendering helpers in clients/tui/render.py."""

    def setUp(self):
        self.engine = _build_demo_engine()
        self.case_search = self.engine.search_cases()
        self.case_inv = self.engine.investigate_case("1000")
        self.alert_inv = self.engine.investigate_alert("alert-1000-1")
        self.entity_report = self.engine.investigate_entity("10.0.4.17")
        self.playbook_run = self.engine.get_alert_playbook_instance("1000", "alert-1000-1")

    def test_case_row_mapping(self):
        item = self.case_search.results[0]
        row = render.case_row(item)
        self.assertEqual(len(row), len(render.CASE_LIST_COLUMNS))
        self.assertEqual(row[0], "1000")

    def test_case_detail_render(self):
        group = render.case_detail(self.case_inv)
        self.assertIsNotNone(group)
        self.assertTrue(len(group.renderables) >= 3)

    def test_alert_detail_render(self):
        group = render.alert_detail(self.alert_inv, self.playbook_run)
        self.assertIsNotNone(group)
        self.assertTrue(len(group.renderables) >= 3)

    def test_entity_investigation_detail_render(self):
        group = render.entity_investigation_detail(self.entity_report)
        self.assertIsNotNone(group)
        self.assertTrue(len(group.renderables) >= 2)

    def test_playbook_run_detail_render(self):
        group = render.playbook_run_detail(self.playbook_run)
        self.assertIsNotNone(group)
        self.assertTrue(len(group.renderables) >= 2)

    def test_help_panel_render(self):
        panel = render.help_panel()
        self.assertIsNotNone(panel)
        self.assertEqual(panel.title, "SecOps TUI Navigation & Keybindings")

    def test_udm_event_row_and_detail_render(self):
        event = {
            "metadata": {
                "eventTimestamp": "2026-08-24T12:00:00Z",
                "eventType": "USER_LOGIN",
                "logType": "OKTA",
                "productName": "Okta Cloud",
            },
            "principal": {"user": {"userid": "analyst@corp.internal"}, "ip": "192.168.1.100"},
            "target": {"hostname": "app.corp.internal", "port": 443},
            "network": {"ipProtocol": "TCP", "direction": "INBOUND"},
        }
        row = render.udm_event_row(event)
        self.assertEqual(len(row), len(render.UDM_EVENT_COLUMNS))
        self.assertEqual(row[1], "USER_LOGIN")
        self.assertEqual(row[2], "analyst@corp.internal")

        detail = render.udm_event_detail(event)
        self.assertIsNotNone(detail)
        self.assertEqual(len(detail.renderables), 4)

    def test_rule_row_and_detail_render(self):
        ruleset_batch = self.engine.search_curated_rulesets()
        ruleset = ruleset_batch.results[0]
        row = render.rule_row(ruleset)
        self.assertEqual(len(row), len(render.RULE_COLUMNS))
        self.assertEqual(row[0], ruleset.title)

        detail_obj = self.engine.get_curated_ruleset(ruleset.id)
        detail = render.ruleset_detail(detail_obj)
        self.assertIsNotNone(detail)
        self.assertTrue(len(detail.renderables) >= 2)

    def test_playbook_catalogue_row_and_detail_render(self):
        pb_batch = self.engine.search_playbooks()
        pb = pb_batch.items[0]
        row = render.playbook_catalogue_row(pb)
        self.assertEqual(len(row), len(render.PLAYBOOK_CATALOGUE_COLUMNS))
        self.assertEqual(row[0], pb.name)

        detail_obj = self.engine.get_playbook(pb.identifier)
        detail = render.playbook_detail_panel(detail_obj)
        self.assertIsNotNone(detail)
        self.assertTrue(len(detail.renderables) >= 2)

    def test_dashboard_row_and_detail_render(self):
        dash_batch = self.engine.search_dashboards()
        dash = dash_batch.dashboards[0]
        row = render.dashboard_row(dash)
        self.assertEqual(len(row), len(render.DASHBOARD_COLUMNS))
        self.assertEqual(row[0], dash.id)

        detail_obj = self.engine.get_dashboard(dash.id)
        # Execute query for live widgets
        query_results = {}
        for c in detail_obj.charts:
            if c.query:
                q_res = self.engine.execute_dashboard_query(c.query.name)
                query_results[c.query.name] = q_res

        detail_panel = render.dashboard_detail_panel(detail_obj, query_results=query_results)
        self.assertIsNotNone(detail_panel)
        self.assertTrue(len(detail_panel.renderables) >= 2)

    def test_udm_enriched_event_and_raw_log_render(self):
        event_inv = self.engine.investigate_event("ev-demo-001", eager_load_raw_log=True)
        enriched_group = render.udm_enriched_event_detail(event_inv)
        self.assertIsNotNone(enriched_group)
        self.assertTrue(len(enriched_group.renderables) >= 3)

        raw_group = render.raw_log_panel(event_inv.raw_log, event_id="ev-demo-001")
        self.assertIsNotNone(raw_group)
        self.assertEqual(len(raw_group.renderables), 2)


@unittest.skipUnless(_HAS_TUI_DEPS, "textual/rich dependencies not installed in test environment")
class TestTUIAppAsync(unittest.IsolatedAsyncioTestCase):
    """Headless integration tests for SecOpsTUI using Textual's run_test()."""

    async def test_app_lifecycle_and_search(self):
        engine = _build_demo_engine()
        app = SecOpsTUI(engine=engine, initial_query="", page_size=20)
        async with app.run_test() as pilot:
            await app.workers.wait_for_complete()
            await pilot.pause()
            cases_table = app.query_one("#cases")
            self.assertEqual(cases_table.row_count, 6)

            # Test search query
            search_input = app.query_one("#search")
            search_input.value = "phishing"
            await search_input.action_submit()
            await app.workers.wait_for_complete()
            await pilot.pause()
            self.assertEqual(cases_table.row_count, 1)

    async def test_tab_switching_fkeys_and_numbers(self):
        engine = _build_demo_engine()
        app = SecOpsTUI(engine=engine, initial_query="", page_size=20)
        async with app.run_test() as pilot:
            await app.workers.wait_for_complete()
            await pilot.pause()

            # Switch to UDM Search via action
            app.action_switch_tab("tab-udm")
            await pilot.pause()
            await app.workers.wait_for_complete()
            await pilot.pause()
            self.assertEqual(app.query_one("#main-tabs").active, "tab-udm")

            # Switch to Curated Rules tab
            app.action_switch_tab("tab-rules")
            await pilot.pause()
            await app.workers.wait_for_complete()
            await pilot.pause()
            self.assertEqual(app.query_one("#main-tabs").active, "tab-rules")

            # Switch to Playbooks tab
            app.action_switch_tab("tab-playbooks")
            await pilot.pause()
            await app.workers.wait_for_complete()
            await pilot.pause()
            self.assertEqual(app.query_one("#main-tabs").active, "tab-playbooks")

            # Switch back to Cases tab
            app.action_switch_tab("tab-cases")
            await pilot.pause()
            await app.workers.wait_for_complete()
            await pilot.pause()
            self.assertEqual(app.query_one("#main-tabs").active, "tab-cases")

    async def test_udm_events_search_and_inspection(self):
        engine = _build_demo_engine()
        app = SecOpsTUI(engine=engine, initial_query="", page_size=20)
        async with app.run_test() as pilot:
            await app.workers.wait_for_complete()
            await pilot.pause()

            app.action_switch_tab("tab-udm")
            await pilot.pause()
            await app.workers.wait_for_complete()
            await pilot.pause()

            udm_table = app.query_one("#udm-table")
            self.assertEqual(udm_table.row_count, 3)

            # Submit search filter
            udm_input = app.query_one("#udm-search")
            udm_input.value = "PROCESS_LAUNCH"
            await udm_input.action_submit()
            await pilot.pause()
            await app.workers.wait_for_complete()
            await pilot.pause()

            self.assertEqual(udm_table.row_count, 1)

            # Select event row
            udm_table.focus()
            udm_table.move_cursor(row=0)
            udm_table.action_select_cursor()
            await pilot.pause()

            detail = app.query_one("#udm-detail")
            self.assertIsNotNone(detail)

    async def test_udm_event_inspect_and_raw_log_inline(self):
        engine = _build_demo_engine()
        app = SecOpsTUI(engine=engine, initial_query="", page_size=20)
        async with app.run_test() as pilot:
            await app.workers.wait_for_complete()
            await pilot.pause()

            # Switch to UDM tab
            app.action_switch_tab("tab-udm")
            await pilot.pause()
            await app.workers.wait_for_complete()
            await pilot.pause()

            udm_table = app.query_one("#udm-table")
            udm_table.focus()
            udm_table.move_cursor(row=0)
            await pilot.pause()
            await app.workers.wait_for_complete()
            await pilot.pause()

            # Live cursor-follow updates both detail and raw log inline
            detail = app.query_one("#udm-detail")
            self.assertIsNotNone(detail)
            raw_log = app.query_one("#udm-raw-log")
            self.assertIsNotNone(raw_log)

            # Trigger Inspect Full UDM Event (i) inline
            app.action_inspect_udm_event()
            await app.workers.wait_for_complete()
            await pilot.pause()
            self.assertNotIsInstance(app.screen, ViewerModal)

            # Trigger View Raw Log (l) inline
            app.action_view_raw_log()
            await app.workers.wait_for_complete()
            await pilot.pause()
            self.assertNotIsInstance(app.screen, ViewerModal)

    async def test_rules_search_and_inspection(self):
        engine = _build_demo_engine()
        app = SecOpsTUI(engine=engine, initial_query="", page_size=20)
        async with app.run_test() as pilot:
            await app.workers.wait_for_complete()
            await pilot.pause()

            app.action_switch_tab("tab-rules")
            await pilot.pause()
            await app.workers.wait_for_complete()
            await pilot.pause()

            rules_table = app.query_one("#rules-table")
            self.assertEqual(rules_table.row_count, 3)

            # Select first ruleset row
            rules_table.focus()
            rules_table.move_cursor(row=0)
            rules_table.action_select_cursor()
            await pilot.pause()
            await app.workers.wait_for_complete()
            await pilot.pause()

            detail = app.query_one("#rules-detail")
            self.assertIsNotNone(detail)

    async def test_playbooks_search_and_inspection(self):
        engine = _build_demo_engine()
        app = SecOpsTUI(engine=engine, initial_query="", page_size=20)
        async with app.run_test() as pilot:
            await app.workers.wait_for_complete()
            await pilot.pause()

            app.action_switch_tab("tab-playbooks")
            await pilot.pause()
            await app.workers.wait_for_complete()
            await pilot.pause()

            pb_table = app.query_one("#playbooks-table")
            self.assertEqual(pb_table.row_count, 3)

            # Select first playbook row
            pb_table.focus()
            pb_table.move_cursor(row=0)
            pb_table.action_select_cursor()
            await pilot.pause()
            await app.workers.wait_for_complete()
            await pilot.pause()

            detail = app.query_one("#playbooks-detail")
            self.assertIsNotNone(detail)

    async def test_case_selection_and_detail(self):
        engine = _build_demo_engine()
        app = SecOpsTUI(engine=engine, initial_query="", page_size=20)
        async with app.run_test() as pilot:
            await app.workers.wait_for_complete()
            await pilot.pause()

            cases_table = app.query_one("#cases")
            cases_table.focus()
            cases_table.move_cursor(row=0)
            cases_table.action_select_cursor()
            await app.workers.wait_for_complete()
            await pilot.pause()

            self.assertIsNotNone(app._current_investigation)
            self.assertEqual(app._current_investigation.case_id, "1000")

    async def test_add_comment_workflow(self):
        engine = _build_demo_engine()
        app = SecOpsTUI(engine=engine, initial_query="", page_size=20)
        async with app.run_test() as pilot:
            await app.workers.wait_for_complete()
            await pilot.pause()

            # Select first case
            cases_table = app.query_one("#cases")
            cases_table.focus()
            cases_table.move_cursor(row=0)
            cases_table.action_select_cursor()
            await app.workers.wait_for_complete()
            await pilot.pause()

            # Open comment modal directly via action
            app.action_add_comment()
            await pilot.pause()
            self.assertIsInstance(app.screen, AddCommentModal)

            # Enter comment text and submit
            modal_textarea = app.screen.query_one("#comment-input")
            modal_textarea.text = "Automated comment: containment confirmed."
            app.screen.action_submit()
            await app.workers.wait_for_complete()
            await pilot.pause()

            # Ensure back on main screen and detail refreshed
            self.assertNotIsInstance(app.screen, AddCommentModal)
            self.assertEqual(app._current_case_id, "1000")
            comments = getattr(app._current_investigation, "comments", [])
            self.assertTrue(any("containment confirmed" in str(getattr(c, "comment", "")) for c in comments))

    async def test_alert_drilldown_workflow(self):
        engine = _build_demo_engine()
        app = SecOpsTUI(engine=engine, initial_query="", page_size=20)
        async with app.run_test() as pilot:
            await app.workers.wait_for_complete()
            await pilot.pause()

            # Select first case
            cases_table = app.query_one("#cases")
            cases_table.focus()
            cases_table.move_cursor(row=0)
            cases_table.action_select_cursor()
            await app.workers.wait_for_complete()
            await pilot.pause()

            # Trigger alert drill-down action
            app.action_investigate_alert()
            await pilot.pause()

            # If multi-alert picker opened, select option
            if isinstance(app.screen, SelectAlertModal):
                option_list = app.screen.query_one("#alerts-option-list")
                option_list.action_select()
                await app.workers.wait_for_complete()
                await pilot.pause()

            # Alert rendered inline in detail pane
            self.assertEqual(app._current_case_subview, "alerts")
            self.assertNotIsInstance(app.screen, ViewerModal)

            # Return to overview
            app.action_case_overview()
            await pilot.pause()
            self.assertEqual(app._current_case_subview, "overview")

    async def test_entity_pivot_workflow(self):
        engine = _build_demo_engine()
        app = SecOpsTUI(engine=engine, initial_query="", page_size=20)
        async with app.run_test() as pilot:
            await app.workers.wait_for_complete()
            await pilot.pause()

            # Select first case
            cases_table = app.query_one("#cases")
            cases_table.focus()
            cases_table.move_cursor(row=0)
            cases_table.action_select_cursor()
            await app.workers.wait_for_complete()
            await pilot.pause()

            # Open entity picker modal
            app.action_investigate_entity()
            await pilot.pause()
            self.assertIsInstance(app.screen, SelectEntityModal)

            # Pick the first involved entity
            option_list = app.screen.query_one("#entities-option-list")
            option_list.action_select()
            await app.workers.wait_for_complete()
            await pilot.pause()

            # Entity pivot rendered inline in detail pane
            self.assertEqual(app._current_case_subview, "entities")
            self.assertNotIsInstance(app.screen, ViewerModal)

            # Return to overview
            app.action_case_overview()
            await pilot.pause()
            self.assertEqual(app._current_case_subview, "overview")

    async def test_playbook_run_view_workflow(self):
        engine = _build_demo_engine()
        app = SecOpsTUI(engine=engine, initial_query="", page_size=20)
        async with app.run_test() as pilot:
            await app.workers.wait_for_complete()
            await pilot.pause()

            # Select first case
            cases_table = app.query_one("#cases")
            cases_table.focus()
            cases_table.move_cursor(row=0)
            cases_table.action_select_cursor()
            await app.workers.wait_for_complete()
            await pilot.pause()

            # Trigger playbook run view
            app.action_view_playbook()
            await app.workers.wait_for_complete()
            await pilot.pause()

            # Playbook rendered inline in detail pane
            self.assertEqual(app._current_case_subview, "playbook")
            self.assertNotIsInstance(app.screen, ViewerModal)

            # Return to overview
            app.action_case_overview()
            await pilot.pause()
            self.assertEqual(app._current_case_subview, "overview")

    async def test_help_modal_workflow(self):
        engine = _build_demo_engine()
        app = SecOpsTUI(engine=engine, initial_query="", page_size=20)
        async with app.run_test() as pilot:
            await pilot.pause()
            app.action_show_help()
            await pilot.pause()
            self.assertIsInstance(app.screen, ViewerModal)
            app.screen.action_close()
            await pilot.pause()
            self.assertNotIsInstance(app.screen, ViewerModal)

    async def test_i3_tiling_split_and_maximize_workflow(self):
        engine = _build_demo_engine()
        app = SecOpsTUI(engine=engine, initial_query="", page_size=20)
        async with app.run_test() as pilot:
            await app.workers.wait_for_complete()
            await pilot.pause()

            # Trigger tile launcher for vertical split
            app.action_split_vertical()
            await pilot.pause()
            self.assertIsInstance(app.screen, TileLauncherModal)

            # Select UDM Search tile option
            options = app.screen.query_one("#launcher-options", OptionList)
            options.action_select()
            await pilot.pause()
            self.assertNotIsInstance(app.screen, TileLauncherModal)

            # Check that a new dynamic tile was mounted
            tiles = list(app.query(TileFrame))
            self.assertTrue(len(tiles) >= 1)

            # Focus the new tile and toggle maximize
            tile = tiles[0]
            tile.focus()
            await pilot.pause()

            app.action_toggle_maximize()
            await pilot.pause()
            self.assertTrue(tile.maximized_state or tile.has_class("-maximized"))

            # Restore tile
            app.action_toggle_maximize()
            await pilot.pause()
            self.assertFalse(tile.maximized_state and tile.has_class("-maximized"))

            # Close tile
            app.action_close_tile()
            await pilot.pause()
            self.assertNotIn(tile, app.query(TileFrame))

    async def test_yank_clipboard_workflow(self):
        engine = _build_demo_engine()
        app = SecOpsTUI(engine=engine, initial_query="", page_size=20)
        async with app.run_test() as pilot:
            await app.workers.wait_for_complete()
            await pilot.pause()

            # Select first case
            cases_table = app.query_one("#cases")
            cases_table.focus()
            cases_table.move_cursor(row=0)
            cases_table.action_select_cursor()
            await app.workers.wait_for_complete()
            await pilot.pause()

            # Trigger yank action
            app.action_yank_context()
            await pilot.pause()
            status = app.query_one("#status", Static).render()
            self.assertIn("clipboard", str(status).lower())

    async def test_dashboards_tab_and_query_execution_workflow(self):
        engine = _build_demo_engine()
        app = SecOpsTUI(engine=engine, initial_query="", page_size=20)
        async with app.run_test() as pilot:
            await app.workers.wait_for_complete()
            await pilot.pause()

            # Switch to Dashboards tab (F5)
            app.action_switch_tab("tab-dashboards")
            await app.workers.wait_for_complete()
            await pilot.pause()

            # Verify table populated with demo dashboards
            dash_table = app.query_one("#dashboards-table")
            self.assertEqual(dash_table.row_count, 3)

            # Move cursor and select first dashboard
            dash_table.focus()
            dash_table.move_cursor(row=0)
            dash_table.action_select_cursor()
            await app.workers.wait_for_complete()
            await pilot.pause()

            # Verify detail pane is populated with dashboard overview and charts
            detail_static = app.query_one("#dashboards-detail", Static)
            self.assertIsNotNone(detail_static)
            self.assertIn("Data Ingestion and Pipeline Health", str(app._current_dashboard_detail.summary.display_name))
            self.assertTrue(len(app._dashboard_query_results) >= 1)

            # Search filter
            search_input = app.query_one("#dashboards-search")
            search_input.value = "Threat"
            search_input.post_message(search_input.Submitted(value="Threat", input=search_input))
            await app.workers.wait_for_complete()
            await pilot.pause()
            self.assertEqual(dash_table.row_count, 1)


if __name__ == "__main__":
    unittest.main()


