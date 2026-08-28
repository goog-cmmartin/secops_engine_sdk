"""Command Launcher (Command Palette) for SecOps TUI.

Provides a keyboard-first overlay (`Ctrl+K` / `:`) allowing analysts to
fuzzy search and launch actions, switch workspaces, filter cases, and jump
to platform capabilities.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, List, Optional

from rich.text import Text
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Vertical
from textual.screen import ModalScreen
from textual.widgets import Input, OptionList
from textual.widgets.option_list import Option


@dataclass
class CommandItem:
    """A single executable command or action in the launcher."""

    command_id: str
    title: str
    description: str
    category: str
    shortcut: Optional[str] = None
    payload: Any = None


def default_commands() -> List[CommandItem]:
    """Build the standard command set."""
    return [
        CommandItem(
            command_id="cases.all",
            title="Cases: View All Cases",
            description="Clear case search filter and show all active cases",
            category="Cases",
            shortcut="Alt+C",
        ),
        CommandItem(
            command_id="cases.critical",
            title="Cases: Filter Critical Priority",
            description="Filter case list to Critical priority cases",
            category="Cases",
        ),
        CommandItem(
            command_id="cases.high",
            title="Cases: Filter High Priority",
            description="Filter case list to High priority cases",
            category="Cases",
        ),
        CommandItem(
            command_id="cases.phishing",
            title="Cases: Search Phishing Cases",
            description="Search cases matching query 'phishing'",
            category="Cases",
        ),
        CommandItem(
            command_id="workspace.new",
            title="Workspace: New Workspace (Virtual Desktop)",
            description="Spawn a new isolated workspace tab",
            category="Workspaces",
            shortcut="Ctrl+N",
        ),
        CommandItem(
            command_id="workspace.close",
            title="Workspace: Close Active Workspace",
            description="Close the currently active workspace tab",
            category="Workspaces",
            shortcut="Ctrl+W",
        ),
        CommandItem(
            command_id="workspace.switch.1",
            title="Workspace: Switch to Workspace 1",
            description="Jump to Workspace 1",
            category="Workspaces",
            shortcut="Alt+1",
            payload=0,
        ),
        CommandItem(
            command_id="workspace.switch.2",
            title="Workspace: Switch to Workspace 2",
            description="Jump to Workspace 2",
            category="Workspaces",
            shortcut="Alt+2",
            payload=1,
        ),
        CommandItem(
            command_id="workspace.switch.3",
            title="Workspace: Switch to Workspace 3",
            description="Jump to Workspace 3",
            category="Workspaces",
            shortcut="Alt+3",
            payload=2,
        ),
        CommandItem(
            command_id="udm.search",
            title="UDM: Event Search (CLI / Query)",
            description="Search raw UDM events using Chronicle UDM queries",
            category="UDM Analytics",
        ),
        CommandItem(
            command_id="udm.stats",
            title="UDM: Stats & Aggregations",
            description="Execute match/outcome analytical aggregation metrics",
            category="UDM Analytics",
        ),
        CommandItem(
            command_id="sys.refresh",
            title="System: Refresh Active Workspace",
            description="Reload data and investigations in current workspace",
            category="System",
            shortcut="r",
        ),
        CommandItem(
            command_id="sys.help",
            title="System: Keyboard Shortcuts & Help",
            description="Display keybindings and navigation guide",
            category="System",
            shortcut="?",
        ),
    ]


class CommandLauncherModal(ModalScreen[Optional[CommandItem]]):
    """Modal command launcher with fuzzy search filtering."""

    DEFAULT_CSS = """
    CommandLauncherModal {
        align: center middle;
        background: rgba(0, 0, 0, 0.7);
    }

    #cmd_container {
        width: 70%;
        max-width: 90;
        height: 60%;
        max-height: 28;
        background: $panel;
        border: thick $accent;
        padding: 1 2;
    }

    #cmd_input {
        dock: top;
        margin-bottom: 1;
    }

    #cmd_list {
        height: 1fr;
        background: $surface;
    }
    """

    BINDINGS = [
        Binding("escape", "dismiss_none", "Dismiss", show=False),
        Binding("up", "cursor_up", "Up", show=False),
        Binding("down", "cursor_down", "Down", show=False),
    ]

    def __init__(self, commands: Optional[List[CommandItem]] = None) -> None:
        super().__init__()
        self._all_commands: List[CommandItem] = commands or default_commands()
        self._filtered_commands: List[CommandItem] = list(self._all_commands)

    def compose(self) -> ComposeResult:
        with Vertical(id="cmd_container"):
            yield Input(
                placeholder="Type a command or search (e.g. 'cases', 'workspace', 'critical')…",
                id="cmd_input",
            )
            yield OptionList(id="cmd_list")

    def on_mount(self) -> None:
        self._populate_list()
        self.query_one("#cmd_input", Input).focus()

    def _format_option(self, cmd: CommandItem) -> Text:
        txt = Text()
        txt.append(f"[{cmd.category}] ", style="dim cyan")
        txt.append(cmd.title, style="bold white")
        if cmd.shortcut:
            txt.append(f"  ({cmd.shortcut})", style="bold yellow")
        txt.append(f"\n   {cmd.description}", style="dim")
        return txt

    def _populate_list(self) -> None:
        opt_list = self.query_one("#cmd_list", OptionList)
        opt_list.clear_options()
        for i, cmd in enumerate(self._filtered_commands):
            opt_list.add_option(Option(prompt=self._format_option(cmd), id=str(i)))
        if self._filtered_commands:
            opt_list.highlighted = 0

    def on_input_changed(self, event: Input.Changed) -> None:
        q = event.value.strip().lower()
        if not q:
            self._filtered_commands = list(self._all_commands)
        else:
            self._filtered_commands = [
                cmd
                for cmd in self._all_commands
                if q in cmd.title.lower()
                or q in cmd.description.lower()
                or q in cmd.category.lower()
                or (cmd.shortcut and q in cmd.shortcut.lower())
            ]
        self._populate_list()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        opt_list = self.query_one("#cmd_list", OptionList)
        if opt_list.highlighted is not None and 0 <= opt_list.highlighted < len(self._filtered_commands):
            self.dismiss(self._filtered_commands[opt_list.highlighted])
        elif self._filtered_commands:
            self.dismiss(self._filtered_commands[0])
        else:
            self.dismiss(None)

    def on_option_list_option_selected(self, event: OptionList.OptionSelected) -> None:
        idx = int(event.option.id) if event.option.id is not None else event.option_index
        if 0 <= idx < len(self._filtered_commands):
            self.dismiss(self._filtered_commands[idx])
        else:
            self.dismiss(None)

    def action_cursor_up(self) -> None:
        opt_list = self.query_one("#cmd_list", OptionList)
        if opt_list.highlighted is not None and opt_list.highlighted > 0:
            opt_list.highlighted -= 1

    def action_cursor_down(self) -> None:
        opt_list = self.query_one("#cmd_list", OptionList)
        if opt_list.highlighted is not None and opt_list.highlighted < len(self._filtered_commands) - 1:
            opt_list.highlighted += 1

    def action_dismiss_none(self) -> None:
        self.dismiss(None)
