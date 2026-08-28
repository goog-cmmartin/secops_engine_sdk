"""i3-style Tiling Window Manager and Modular Tile Widgets for SecOps TUI.

Provides dynamic binary-space tiling (horizontal and vertical splits), workspace
management (Workspaces 1-4+), tile focus navigation, maximize/fullscreen toggle,
tile close/split operations, and a quick launcher palette.
"""
from __future__ import annotations

from typing import Any, Callable, Dict, List, Optional, Tuple, Type

from rich.text import Text
from textual.app import ComposeResult
from textual.containers import Container, Horizontal, Vertical, VerticalScroll
from textual.message import Message
from textual.screen import ModalScreen
from textual.widget import Widget
from textual.widgets import (
    Button,
    DataTable,
    Input,
    Label,
    OptionList,
    Static,
)
from textual.widgets.option_list import Option

from . import render


# --- Base Tile Frame & Header ---------------------------------------------

class TileHeader(Static):
    """Header bar for a tile showing title, type badge, and active status."""

    def __init__(self, title: str, tile_id: str, **kwargs):
        super().__init__(**kwargs)
        self.title_text = title
        self.tile_id = tile_id

    def render(self) -> Text:
        res = Text()
        res.append(" ■ ", style="bold cyan")
        res.append(self.title_text, style="bold")
        res.append(f"  [{self.tile_id}]", style="dim")
        return res


class TileFrame(Container):
    """A single tiled window frame containing a header and content widget."""

    DEFAULT_CSS = """
    TileFrame {
        height: 1fr;
        width: 1fr;
        border: round $panel-lighten-2;
        background: $surface;
        padding: 0;
        margin: 0;
    }

    TileFrame:focus-within {
        border: round $accent;
    }

    TileFrame.-maximized {
        dock: top;
        width: 100%;
        height: 100%;
    }

    .tile-header-bar {
        dock: top;
        height: 1;
        background: $panel;
        color: $text;
        padding: 0 1;
    }

    .tile-body-container {
        height: 1fr;
        width: 1fr;
        padding: 0;
    }
    """

    class TileClosed(Message):
        def __init__(self, tile: TileFrame):
            super().__init__()
            self.tile = tile

    class TileSplitRequested(Message):
        def __init__(self, tile: TileFrame, orientation: str, new_tile_type: str):
            super().__init__()
            self.tile = tile
            self.orientation = orientation
            self.new_tile_type = new_tile_type

    def __init__(
        self,
        tile_type: str,
        title: str,
        content: Widget,
        tile_id: Optional[str] = None,
        **kwargs,
    ):
        super().__init__(**kwargs)
        self.tile_type = tile_type
        self.tile_title = title
        self.content_widget = content
        self.tile_uid = tile_id or f"tile-{id(self)}"
        self.maximized_state = False
        self.can_focus = True

    def compose(self) -> ComposeResult:
        yield TileHeader(self.tile_title, self.tile_uid, classes="tile-header-bar")
        with Container(classes="tile-body-container"):
            yield self.content_widget

    def toggle_maximize(self) -> bool:
        self.maximized_state = not self.maximized_state
        if self.maximized_state:
            self.add_class("-maximized")
        else:
            self.remove_class("-maximized")
        return self.maximized_state


# --- Specific SecOps Tile Contents ---------------------------------------

class CasesListTile(Container):
    """Tile containing case search bar and DataTable."""

    def compose(self) -> ComposeResult:
        yield Input(
            placeholder="Search Cases (e.g. Priority:HIGH, AlertName:...)",
            id="tile-cases-search",
            classes="search-bar",
        )
        yield DataTable(id="tile-cases-table", cursor_type="row", zebra_stripes=True, classes="table-pane")


class CaseDetailTile(VerticalScroll):
    """Tile containing rich case investigation overview."""

    def compose(self) -> ComposeResult:
        yield Static(
            Text("Select a case from the Cases List to inspect investigation details.", style="dim"),
            id="tile-case-detail-static",
            classes="detail-view",
        )


class UdmSearchTile(Container):
    """Tile containing UDM query input and event telemetry stream."""

    def compose(self) -> ComposeResult:
        yield Input(
            placeholder="UDM Query (e.g. metadata.event_type = \"USER_LOGIN\")",
            id="tile-udm-search",
            classes="search-bar",
        )
        yield DataTable(id="tile-udm-table", cursor_type="row", zebra_stripes=True, classes="table-pane")


class UdmDetailTile(VerticalScroll):
    """Tile containing structured UDM event breakdown."""

    def compose(self) -> ComposeResult:
        yield Static(
            Text("Select a UDM event to inspect Actor / Target / Network fields.", style="dim"),
            id="tile-udm-detail-static",
            classes="detail-view",
        )


class RawLogTile(VerticalScroll):
    """Tile containing decoded unparsed raw log payload."""

    def compose(self) -> ComposeResult:
        yield Static(
            Text("Select a UDM event to inspect raw log payload.", style="dim"),
            id="tile-raw-log-static",
            classes="detail-view",
        )


class RulesCatalogueTile(Container):
    """Tile containing GCTI curated rules search and list."""

    def compose(self) -> ComposeResult:
        yield Input(
            placeholder="Search Curated Rulesets (e.g. Cloud, MITRE:...)",
            id="tile-rules-search",
            classes="search-bar",
        )
        yield DataTable(id="tile-rules-table", cursor_type="row", zebra_stripes=True, classes="table-pane")


class RuleDetailTile(VerticalScroll):
    """Tile containing Curated Rule Set logic, deployments, and MITRE matrix."""

    def compose(self) -> ComposeResult:
        yield Static(
            Text("Select a Curated Rule Set to inspect YARA-L logic & MITRE tactics.", style="dim"),
            id="tile-rule-detail-static",
            classes="detail-view",
        )


class PlaybooksTile(Container):
    """Tile containing SOAR playbook catalogue search and list."""

    def compose(self) -> ComposeResult:
        yield Input(
            placeholder="Search Playbooks (e.g. Phishing, Triage)",
            id="tile-playbooks-search",
            classes="search-bar",
        )
        yield DataTable(id="tile-playbooks-table", cursor_type="row", zebra_stripes=True, classes="table-pane")


class PlaybookDetailTile(VerticalScroll):
    """Tile containing playbook definition overview, triggers, and steps DAG."""

    def compose(self) -> ComposeResult:
        yield Static(
            Text("Select a Playbook to inspect triggers, conditions, and action DAG steps.", style="dim"),
            id="tile-playbook-detail-static",
            classes="detail-view",
        )


class DashboardsCatalogueTile(Container):
    """Tile containing Google SecOps native dashboards search and list."""

    def compose(self) -> ComposeResult:
        yield Input(
            placeholder="Search Dashboards (e.g. Ingestion, Health, Threat)",
            id="tile-dashboards-search",
            classes="search-bar",
        )
        yield DataTable(id="tile-dashboards-table", cursor_type="row", zebra_stripes=True, classes="table-pane")


class DashboardDetailTile(VerticalScroll):
    """Tile containing full composite dashboard graph, KPI cards, and charts."""

    def compose(self) -> ComposeResult:
        yield Static(
            Text("Select a Dashboard to inspect composite visual charts and execute queries.", style="dim"),
            id="tile-dashboard-detail-static",
            classes="detail-view",
        )


# --- Tile Registry --------------------------------------------------------

TILE_REGISTRY: Dict[str, Tuple[str, Type[Widget], str]] = {
    "cases": ("Cases Triage", CasesListTile, "SOAR incident queue and case search table"),
    "case-detail": ("Case Investigation", CaseDetailTile, "Case overview, alerts, involved entities, comments"),
    "udm-search": ("UDM Event Stream", UdmSearchTile, "Live UDM query input and event table"),
    "udm-detail": ("UDM Inspector", UdmDetailTile, "Actor, Target, Network, and Security Result telemetry"),
    "raw-log": ("Raw Log Payload", RawLogTile, "Decoded unparsed syslog/JSON log text with byte size"),
    "rules": ("Curated Rules", RulesCatalogueTile, "GCTI detection rulesets and category browser"),
    "rule-detail": ("Rule Heuristic & Logic", RuleDetailTile, "YARA-L rule code, deployments & MITRE ATT&CK tactics"),
    "playbooks": ("Playbooks Catalogue", PlaybooksTile, "SOAR automation workflows and triggers"),
    "playbook-detail": ("Playbook Steps DAG", PlaybookDetailTile, "Trigger criteria and automated action execution sequence"),
    "dashboards": ("Dashboards Hub", DashboardsCatalogueTile, "Google SecOps native dashboards catalogue"),
    "dashboard-detail": ("Dashboard Visualizer", DashboardDetailTile, "Composite dashboard graphs, KPI metrics & charts"),
}


def create_tile(tile_type: str, custom_id: Optional[str] = None) -> TileFrame:
    """Factory creating a configured TileFrame for a registered tile type."""
    if tile_type not in TILE_REGISTRY:
        tile_type = "cases"
    title, content_cls, _ = TILE_REGISTRY[tile_type]
    content_widget = content_cls()
    return TileFrame(tile_type=tile_type, title=title, content=content_widget, tile_id=custom_id)


# --- Tiling Containers (Splits & Workspace Tree) ---------------------------

class SplitContainer(Container):
    """Container holding two or more child tiles or nested splits in a direction."""

    DEFAULT_CSS = """
    SplitContainer {
        height: 1fr;
        width: 1fr;
        padding: 0;
        margin: 0;
    }

    SplitContainer.-horizontal {
        layout: horizontal;
    }

    SplitContainer.-vertical {
        layout: vertical;
    }
    """

    def __init__(self, orientation: str = "horizontal", **kwargs):
        super().__init__(**kwargs)
        self.orientation = orientation

    def on_mount(self) -> None:
        if self.orientation == "horizontal":
            self.add_class("-horizontal")
        else:
            self.add_class("-vertical")


class WorkspaceView(Container):
    """An i3-style tiling workspace holding a dynamic tree of tiled windows."""

    DEFAULT_CSS = """
    WorkspaceView {
        height: 1fr;
        width: 1fr;
        padding: 0;
        margin: 0;
    }
    """

    def __init__(self, workspace_id: str, name: str, default_layout: Callable[[], Widget], **kwargs):
        super().__init__(**kwargs)
        self.workspace_id = workspace_id
        self.workspace_name = name
        self.default_layout_factory = default_layout

    def compose(self) -> ComposeResult:
        yield self.default_layout_factory()

    def get_all_tiles(self) -> List[TileFrame]:
        return list(self.query(TileFrame))

    def get_focused_tile(self) -> Optional[TileFrame]:
        for tile in self.get_all_tiles():
            if tile.has_focus or tile.query("*:focus"):
                return tile
        tiles = self.get_all_tiles()
        return tiles[0] if tiles else None

    def split_focused_tile(self, orientation: str, new_tile_type: str) -> TileFrame:
        """Splits the currently focused tile in the given orientation (horizontal/vertical)."""
        target = self.get_focused_tile()
        new_tile = create_tile(new_tile_type)

        if not target:
            self.mount(new_tile)
            return new_tile

        parent = target.parent
        if parent is None:
            return new_tile

        # If parent already matches the split orientation, we can simply mount sibling next to target
        if isinstance(parent, SplitContainer) and parent.orientation == orientation:
            parent.mount(new_tile, after=target)
        else:
            # Create a new SplitContainer replacing target's spot
            split_box = SplitContainer(orientation=orientation)
            parent.mount(split_box, after=target)
            target.remove()
            split_box.mount(target)
            split_box.mount(new_tile)

        new_tile.focus()
        return new_tile

    def close_tile(self, tile: TileFrame) -> None:
        """Closes the specified tile and cleans up empty split branches."""
        parent = tile.parent
        tile.remove()

        # If parent is a SplitContainer that now only has 1 child, collapse it
        if isinstance(parent, SplitContainer):
            remaining = list(parent.children)
            if len(remaining) == 1:
                grandparent = parent.parent
                if grandparent is not None:
                    only_child = remaining[0]
                    only_child.remove()
                    grandparent.mount(only_child, after=parent)
                    parent.remove()
            elif len(remaining) == 0:
                parent.remove()

        # If workspace is now empty, re-spawn default layout
        if not self.get_all_tiles():
            self.mount(self.default_layout_factory())


# --- Quick Tile Launcher Modal --------------------------------------------

class TileLauncherModal(ModalScreen[Optional[Tuple[str, str]]]):
    """Fuzzy launcher modal (Mod+d) allowing analyst to spawn or switch tiles."""

    DEFAULT_CSS = """
    TileLauncherModal {
        align: center middle;
        background: rgba(0, 0, 0, 0.7);
    }

    #launcher-dialog {
        width: 70;
        height: 22;
        border: thick $accent;
        background: $surface;
        padding: 1 2;
    }

    #launcher-title {
        dock: top;
        text-style: bold;
        color: $accent;
        margin-bottom: 1;
    }

    #launcher-options {
        height: 1fr;
        border: solid $panel-lighten-2;
    }

    #launcher-hint {
        dock: bottom;
        height: 1;
        color: $text-muted;
        margin-top: 1;
    }
    """

    BINDINGS = [
        ("escape", "dismiss_none", "Cancel"),
        ("q", "dismiss_none", "Cancel"),
    ]

    def __init__(self, action_mode: str = "open", **kwargs):
        super().__init__(**kwargs)
        self.action_mode = action_mode  # "open", "split-v", "split-h"

    def compose(self) -> ComposeResult:
        with Container(id="launcher-dialog"):
            header_text = "Spawn SecOps Tile Window"
            if self.action_mode == "split-v":
                header_text = "Split Vertically ➜ Select SecOps Tile"
            elif self.action_mode == "split-h":
                header_text = "Split Horizontally ⬇ Select SecOps Tile"

            yield Label(header_text, id="launcher-title")
            yield OptionList(
                *[
                    Option(f"{title}  —  {desc}", id=ttype)
                    for ttype, (title, _, desc) in TILE_REGISTRY.items()
                ],
                id="launcher-options",
            )
            yield Label("[Enter] Select Tile   [Esc] Cancel", id="launcher-hint")

    def on_mount(self) -> None:
        self.query_one("#launcher-options", OptionList).focus()

    def on_option_list_option_selected(self, event: OptionList.OptionSelected) -> None:
        ttype = str(event.option.id or "cases")
        self.dismiss((self.action_mode, ttype))

    def action_dismiss_none(self) -> None:
        self.dismiss(None)
