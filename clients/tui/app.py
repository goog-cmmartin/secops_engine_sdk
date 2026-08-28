"""SecOps Console Textual TUI Application.

Features:
- Workspaces (Virtual Desktops) via TabbedContent
- Command Launcher / Palette (`Ctrl+K` / `:`)
- Case Triage & Alert Deep-Dive Inspection Views
"""
from __future__ import annotations

from typing import Any, Optional

from rich.text import Text
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Container
from textual.widgets import Footer, Header, Static, TabPane, TabbedContent

from .command_launcher import CommandItem, CommandLauncherModal
from .views.case_view import CaseWorkspaceView


class SecOpsTUI(App):
    """Google SecOps SOC Analyst Console TUI."""

    TITLE = "Google SecOps Console"
    SUB_TITLE = "TUI SOC Station"

    CSS = """
    Screen {
        layout: vertical;
    }

    #workspaces_tabbed {
        height: 1fr;
    }

    #status_bar {
        dock: bottom;
        height: 1;
        background: $panel;
        color: $text-muted;
        padding: 0 1;
    }
    """

    BINDINGS = [
        Binding("ctrl+k", "open_launcher", "Launcher", priority=True),
        Binding("colon", "open_launcher", "Launcher"),
        Binding("ctrl+n", "new_workspace", "New Workspace"),
        Binding("ctrl+w", "close_workspace", "Close Workspace"),
        Binding("alt+1", "switch_workspace(0)", "WS 1", show=False),
        Binding("alt+2", "switch_workspace(1)", "WS 2", show=False),
        Binding("alt+3", "switch_workspace(2)", "WS 3", show=False),
        Binding("alt+4", "switch_workspace(3)", "WS 4", show=False),
        Binding("alt+5", "switch_workspace(4)", "WS 5", show=False),
        Binding("alt+6", "switch_workspace(5)", "WS 6", show=False),
        Binding("alt+7", "switch_workspace(6)", "WS 7", show=False),
        Binding("alt+8", "switch_workspace(7)", "WS 8", show=False),
        Binding("alt+9", "switch_workspace(8)", "WS 9", show=False),
        Binding("slash", "focus_search", "Search"),
        Binding("r", "refresh_active", "Refresh"),
        Binding("q", "quit", "Quit"),
    ]

    def __init__(self, engine: Any, initial_query: str = "", page_size: int = 50) -> None:
        super().__init__()
        self._engine = engine
        self._initial_query = initial_query
        self._page_size = page_size
        self._workspace_counter = 1

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        with TabbedContent(id="workspaces_tabbed"):
            with TabPane("1: Cases Triage", id="ws_pane_1"):
                yield CaseWorkspaceView(
                    engine=self._engine,
                    initial_query=self._initial_query,
                    page_size=self._page_size,
                    id="ws_view_1",
                )
        yield Static(
            Text("Ready. Press [Ctrl+K] for Command Launcher | [/] Search | [Ctrl+N] New Workspace"),
            id="status_bar",
        )
        yield Footer()

    # --- Active Workspace Resolution --------------------------------------

    def get_active_case_view(self) -> Optional[CaseWorkspaceView]:
        tabbed = self.query_one("#workspaces_tabbed", TabbedContent)
        try:
            active_pane = tabbed.get_pane(tabbed.active) if tabbed.active else None
            if active_pane:
                return active_pane.query_one(CaseWorkspaceView)
        except Exception:
            pass
        # Fallback to first available CaseWorkspaceView
        views = list(self.query(CaseWorkspaceView))
        return views[0] if views else None

    # --- Actions -----------------------------------------------------------

    def action_open_launcher(self) -> None:
        self.push_screen(CommandLauncherModal(), callback=self._on_command_selected)

    def _on_command_selected(self, cmd: Optional[CommandItem]) -> None:
        if cmd is None:
            return

        cid = cmd.command_id

        if cid == "workspace.new":
            self.action_new_workspace()
        elif cid == "workspace.close":
            self.action_close_workspace()
        elif cid.startswith("workspace.switch."):
            idx = int(cmd.payload) if cmd.payload is not None else 0
            self.action_switch_workspace(idx)
        elif cid == "cases.all":
            v = self.get_active_case_view()
            if v:
                v.set_query("")
        elif cid == "cases.critical":
            v = self.get_active_case_view()
            if v:
                v.set_query("Priority:CRITICAL")
        elif cid == "cases.high":
            v = self.get_active_case_view()
            if v:
                v.set_query("Priority:HIGH")
        elif cid == "cases.phishing":
            v = self.get_active_case_view()
            if v:
                v.set_query("phishing")
        elif cid == "sys.refresh":
            self.action_refresh_active()
        elif cid == "sys.help":
            self.notify(
                "Shortcuts:\n"
                "• Ctrl+K or : -> Command Launcher\n"
                "• Ctrl+N -> New Workspace\n"
                "• Ctrl+W -> Close Workspace\n"
                "• Alt+1..9 -> Switch Workspace\n"
                "• / -> Focus Case Search\n"
                "• Enter on Case -> Load Case Detail\n"
                "• Enter on Alert -> Drilldown Alert Deep-Dive\n"
                "• Esc / b -> Back to Case Overview\n"
                "• r -> Refresh View",
                title="Google SecOps Console Help",
                timeout=8,
            )
        elif cid.startswith("udm."):
            self.notify(
                f"{cmd.title} launched. Use CLI `secops.py search` or `search-stats` for background operations.",
                title="UDM Analytics",
            )

    def action_new_workspace(self, title: Optional[str] = None, initial_query: str = "") -> None:
        self._workspace_counter += 1
        num = self._workspace_counter
        pane_id = f"ws_pane_{num}"
        view_id = f"ws_view_{num}"
        tab_title = title or f"{num}: Case Triage"

        tabbed = self.query_one("#workspaces_tabbed", TabbedContent)
        new_view = CaseWorkspaceView(
            engine=self._engine,
            initial_query=initial_query,
            page_size=self._page_size,
            id=view_id,
        )
        tabbed.add_pane(TabPane(tab_title, new_view, id=pane_id))
        tabbed.active = pane_id
        self.notify(f"Spawned Virtual Workspace '{tab_title}'")

    def action_close_workspace(self) -> None:
        tabbed = self.query_one("#workspaces_tabbed", TabbedContent)
        panes = list(tabbed.query(TabPane))
        if len(panes) <= 1:
            self.notify("Cannot close the only remaining workspace.", severity="warning")
            return
        active_id = tabbed.active
        if active_id:
            tabbed.remove_pane(active_id)
            self.notify("Closed active workspace.")

    def action_switch_workspace(self, index: int) -> None:
        tabbed = self.query_one("#workspaces_tabbed", TabbedContent)
        panes = list(tabbed.query(TabPane))
        if 0 <= index < len(panes):
            target_pane = panes[index]
            tabbed.active = target_pane.id
            self.notify(f"Switched to Workspace {index + 1}")

    def action_focus_search(self) -> None:
        view = self.get_active_case_view()
        if view:
            view.focus_search()

    def action_refresh_active(self) -> None:
        view = self.get_active_case_view()
        if view:
            view.refresh_view()
            self.notify("Refreshed active workspace.")
