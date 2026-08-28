"""Multi-Tab Textual TUI for Google SecOps.

Layout (TabbedContent multi-view navigation):

    Tabs: [ Cases (F1) ]  [ UDM Search (F2) ]  [ Curated Rules (F3) ]  [ Playbooks (F4) ]
    +-------------------------------------------------------------------------------+
    | Active Tab Content (Split-pane layout: Search & DataTable -> Rich Detail Pane)|
    +-------------------------------------------------------------------------------+
    | Status bar & Active Shortcuts                                                 |
    +-------------------------------------------------------------------------------+

Keybindings:
    F1 or 1  -> Switch to Cases Triage tab
    F2 or 2  -> Switch to UDM Search & Event Stream tab
    F3 or 3  -> Switch to Detection & Curated Rules tab
    F4 or 4  -> Switch to Playbooks Catalogue tab
    /        -> Focus active tab search input
    Enter    -> Search query or drill into selected table row
    c        -> Add analyst comment to case (Cases tab modal)
    a        -> Drill down into security alert (Cases tab modal)
    e        -> Investigate involved entity / pivot (Cases tab modal)
    p        -> View alert playbook run steps (Cases tab modal)
    r        -> Refresh active tab data
    ? or h   -> Help modal
    q        -> Quit

Invariant: NO facade call happens on the UI thread. All search, investigate,
comment, pivot, rule, and playbook calls are dispatched with ``@work(thread=True)``
and post their results back as custom messages, which message handlers apply to widgets.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from rich.text import Text

from engine.domain import LifecycleState, SearchRequest
from textual import events, work
from textual.app import App, ComposeResult
from textual.containers import Container, Horizontal, Vertical, VerticalScroll
from textual.message import Message
from textual.screen import ModalScreen
from textual.widgets import (
    Button,
    DataTable,
    Footer,
    Header,
    Input,
    Label,
    OptionList,
    Static,
    TabbedContent,
    TabPane,
    TextArea,
)
from textual.widgets.option_list import Option

from . import render
from .tiles import (
    SplitContainer,
    TILE_REGISTRY,
    TileFrame,
    TileLauncherModal,
    create_tile,
)


# --- worker -> UI messages --------------------------------------------

# Case Messages
@dataclass
class CasesLoaded(Message):
    items: List[Any]
    total: int
    query: str


@dataclass
class CasesFailed(Message):
    error: str
    query: str


@dataclass
class DetailLoaded(Message):
    investigation: Any


@dataclass
class DetailFailed(Message):
    error: str
    case_id: str


@dataclass
class AlertLoaded(Message):
    investigation: Any
    playbook_run: Optional[Any] = None


@dataclass
class AlertFailed(Message):
    error: str
    alert_name: str


@dataclass
class EntityLoaded(Message):
    report: Any


@dataclass
class EntityFailed(Message):
    error: str
    indicator: str


@dataclass
class PlaybookLoaded(Message):
    run: Any


@dataclass
class PlaybookFailed(Message):
    error: str
    alert_id: str


@dataclass
class CommentAdded(Message):
    case_id: str
    record: Any


@dataclass
class CommentFailed(Message):
    case_id: str
    error: str


# UDM Search Messages
@dataclass
class UdmEventsLoaded(Message):
    events: List[Dict[str, Any]]
    total: int
    query: str


UDMEventsLoaded = UdmEventsLoaded


@dataclass
class UdmEventsFailed(Message):
    error: str
    query: str


UDMEventsFailed = UdmEventsFailed


@dataclass
class EnrichedEventLoaded(Message):
    investigation: Any
    event_id: str


@dataclass
class EnrichedEventFailed(Message):
    error: str
    event_id: str


@dataclass
class RawLogLoaded(Message):
    raw_log: Any
    event_id: str


@dataclass
class RawLogFailed(Message):
    error: str
    event_id: str


# Curated Detection Rule Messages
@dataclass
class RulesLoaded(Message):
    items: List[Any]
    total: int
    query: str


@dataclass
class RulesFailed(Message):
    error: str
    query: str


@dataclass
class RuleDetailLoaded(Message):
    detail: Any


@dataclass
class RuleDetailFailed(Message):
    error: str
    ruleset_id: str


# Playbook Catalogue Messages
@dataclass
class PlaybooksLoaded(Message):
    items: List[Any]
    total: int
    query: str


@dataclass
class PlaybooksFailed(Message):
    error: str
    query: str


@dataclass
class PlaybookDetailLoaded(Message):
    detail: Any


@dataclass
class PlaybookDetailFailed(Message):
    error: str
    playbook_id: str


# Dashboards Messages
@dataclass
class DashboardsLoaded(Message):
    items: List[Any]
    total: int
    query: str


@dataclass
class DashboardsFailed(Message):
    error: str
    query: str


@dataclass
class DashboardDetailLoaded(Message):
    detail: Any
    query_results: Dict[str, Any]


@dataclass
class DashboardDetailFailed(Message):
    error: str
    dashboard_id: str


# --- Modal Dialogs ----------------------------------------------------

class AddCommentModal(ModalScreen[Optional[str]]):
    """Modal dialog to compose and submit an analyst comment."""

    CSS = """
    AddCommentModal {
        align: center middle;
    }

    #comment-dialog {
        width: 70;
        height: auto;
        max-height: 80%;
        background: $surface;
        border: thick $primary;
        padding: 1 2;
    }

    #comment-title {
        text-style: bold;
        color: $accent;
        margin-bottom: 1;
    }

    #comment-input {
        height: 6;
        margin-bottom: 1;
    }

    #comment-buttons {
        height: auto;
        align: right middle;
    }

    #comment-buttons Button {
        margin-left: 1;
    }
    """

    BINDINGS = [
        ("escape", "cancel", "Cancel"),
        ("ctrl+s", "submit", "Submit"),
    ]

    def __init__(self, case_id: str):
        super().__init__()
        self._case_id = case_id

    def compose(self) -> ComposeResult:
        with Vertical(id="comment-dialog"):
            yield Label(f"Add Analyst Comment — Case #{self._case_id}", id="comment-title")
            yield TextArea(id="comment-input", language=None)
            with Horizontal(id="comment-buttons"):
                yield Button("Cancel", id="btn-cancel", variant="default")
                yield Button("Post Comment (Ctrl+S)", id="btn-submit", variant="primary")

    def on_mount(self) -> None:
        self.query_one("#comment-input", TextArea).focus()

    def action_cancel(self) -> None:
        self.dismiss(None)

    def action_submit(self) -> None:
        text = self.query_one("#comment-input", TextArea).text.strip()
        if text:
            self.dismiss(text)
        else:
            self.dismiss(None)

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn-submit":
            self.action_submit()
        else:
            self.action_cancel()


class SelectAlertModal(ModalScreen[Optional[Any]]):
    """Modal to select which alert to deep-dive when multiple alerts exist."""

    CSS = """
    SelectAlertModal {
        align: center middle;
    }

    #select-alert-dialog {
        width: 75;
        height: auto;
        max-height: 80%;
        background: $surface;
        border: thick $primary;
        padding: 1 2;
    }

    #select-alert-title {
        text-style: bold;
        color: $accent;
        margin-bottom: 1;
    }

    #alerts-option-list {
        height: 10;
        margin-bottom: 1;
    }

    #alert-dialog-buttons {
        height: auto;
        align: right middle;
    }
    """

    BINDINGS = [
        ("escape", "cancel", "Cancel"),
    ]

    def __init__(self, alerts: List[Any]):
        super().__init__()
        self._alerts = alerts

    def compose(self) -> ComposeResult:
        with Vertical(id="select-alert-dialog"):
            yield Label("Select Security Alert to Investigate", id="select-alert-title")
            options = []
            for a in self._alerts:
                name = getattr(a, "display_name", None) or getattr(a, "identifier", None) or getattr(a, "name", "Alert")
                pri = getattr(a, "priority", "UNKNOWN")
                events = getattr(a, "event_count", 0)
                options.append(Option(f"[{pri}] {name} ({events} events)", id=str(id(a))))
            yield OptionList(*options, id="alerts-option-list")
            with Horizontal(id="alert-dialog-buttons"):
                yield Button("Cancel (Esc)", id="btn-cancel-alert", variant="default")

    def on_option_list_option_selected(self, event: OptionList.OptionSelected) -> None:
        selected_idx = event.option_index
        if 0 <= selected_idx < len(self._alerts):
            self.dismiss(self._alerts[selected_idx])
        else:
            self.dismiss(None)

    def action_cancel(self) -> None:
        self.dismiss(None)

    def on_button_pressed(self, event: Button.Pressed) -> None:
        self.action_cancel()


class SelectEntityModal(ModalScreen[Optional[str]]):
    """Modal to select an involved entity or enter an indicator for pivot investigation."""

    CSS = """
    SelectEntityModal {
        align: center middle;
    }

    #select-entity-dialog {
        width: 75;
        height: auto;
        max-height: 85%;
        background: $surface;
        border: thick $primary;
        padding: 1 2;
    }

    #select-entity-title {
        text-style: bold;
        color: $accent;
        margin-bottom: 1;
    }

    #entity-input {
        margin-bottom: 1;
    }

    #entities-option-list {
        height: 8;
        margin-bottom: 1;
    }

    #entity-dialog-buttons {
        height: auto;
        align: right middle;
    }

    #entity-dialog-buttons Button {
        margin-left: 1;
    }
    """

    BINDINGS = [
        ("escape", "cancel", "Cancel"),
    ]

    def __init__(self, entities: List[Any]):
        super().__init__()
        self._entities = entities

    def compose(self) -> ComposeResult:
        with Vertical(id="select-entity-dialog"):
            yield Label("Cross-Engine Entity Pivot Investigation", id="select-entity-title")
            yield Input(placeholder="Or enter indicator (IP, SHA256, domain, user, URL)...", id="entity-input")
            options = []
            for e in self._entities:
                ident = getattr(e, "identifier", None) or getattr(e, "display_name", "")
                etype = getattr(e, "entity_type", "ENTITY")
                susp = " [SUSPICIOUS]" if getattr(e, "is_suspicious", False) else ""
                options.append(Option(f"[{etype}] {ident}{susp}", id=ident))
            if options:
                yield Label("Involved Entities in Current Case:", id="entities-label")
                yield OptionList(*options, id="entities-option-list")
            with Horizontal(id="entity-dialog-buttons"):
                yield Button("Cancel", id="btn-cancel-entity", variant="default")
                yield Button("Investigate (Enter)", id="btn-submit-entity", variant="primary")

    def on_input_submitted(self, event: Input.Submitted) -> None:
        val = event.value.strip()
        if val:
            self.dismiss(val)

    def on_option_list_option_selected(self, event: OptionList.OptionSelected) -> None:
        selected_idx = event.option_index
        if 0 <= selected_idx < len(self._entities):
            ident = getattr(self._entities[selected_idx], "identifier", None) or getattr(self._entities[selected_idx], "display_name", "")
            self.dismiss(ident)
        else:
            self.dismiss(None)

    def action_cancel(self) -> None:
        self.dismiss(None)

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn-submit-entity":
            val = self.query_one("#entity-input", Input).value.strip()
            if val:
                self.dismiss(val)
            else:
                self.dismiss(None)
        else:
            self.action_cancel()


class ViewerModal(ModalScreen[None]):
    """Generic scrollable viewer modal for rich renderables (Alerts, Entities, Playbooks, Help)."""

    CSS = """
    ViewerModal {
        align: center middle;
    }

    #viewer-container {
        width: 85%;
        max-width: 120;
        height: 85%;
        background: $surface;
        border: thick $primary;
        padding: 1 2;
    }

    #viewer-scroll {
        height: 1fr;
        overflow-y: auto;
    }

    #viewer-footer-bar {
        dock: bottom;
        height: 3;
        align: right middle;
        padding-top: 1;
    }
    """

    BINDINGS = [
        ("escape", "close", "Close"),
        ("q", "close", "Close"),
    ]

    def __init__(self, renderable: Any, title: str = "Investigation"):
        super().__init__()
        self._renderable = renderable
        self._title = title

    def compose(self) -> ComposeResult:
        with Vertical(id="viewer-container"):
            with VerticalScroll(id="viewer-scroll"):
                yield Static(self._renderable, id="viewer-content")
            with Horizontal(id="viewer-footer-bar"):
                yield Button("Close (Esc)", id="btn-close-viewer", variant="primary")

    def action_close(self) -> None:
        self.dismiss(None)

    def on_button_pressed(self, event: Button.Pressed) -> None:
        self.action_close()


# --- Main Application -------------------------------------------------

class SecOpsTUI(App):
    """Multi-Tab Google SecOps TUI for Cases, UDM Search, Rules, and Playbooks."""

    CasesLoaded = CasesLoaded
    CasesFailed = CasesFailed
    DetailLoaded = DetailLoaded
    DetailFailed = DetailFailed
    AlertLoaded = AlertLoaded
    AlertFailed = AlertFailed
    EntityLoaded = EntityLoaded
    EntityFailed = EntityFailed
    PlaybookLoaded = PlaybookLoaded
    PlaybookFailed = PlaybookFailed
    CommentAdded = CommentAdded
    CommentFailed = CommentFailed
    UdmEventsLoaded = UdmEventsLoaded
    UDMEventsLoaded = UDMEventsLoaded
    UdmEventsFailed = UdmEventsFailed
    UDMEventsFailed = UDMEventsFailed
    EnrichedEventLoaded = EnrichedEventLoaded
    EnrichedEventFailed = EnrichedEventFailed
    RawLogLoaded = RawLogLoaded
    RawLogFailed = RawLogFailed
    RulesLoaded = RulesLoaded
    RulesFailed = RulesFailed
    RuleDetailLoaded = RuleDetailLoaded
    RuleDetailFailed = RuleDetailFailed
    PlaybooksLoaded = PlaybooksLoaded
    PlaybooksFailed = PlaybooksFailed
    PlaybookDetailLoaded = PlaybookDetailLoaded
    PlaybookDetailFailed = PlaybookDetailFailed
    DashboardsLoaded = DashboardsLoaded
    DashboardsFailed = DashboardsFailed
    DashboardDetailLoaded = DashboardDetailLoaded
    DashboardDetailFailed = DashboardDetailFailed

    CSS = """
    Screen {
        layout: vertical;
    }

    TabbedContent {
        height: 1fr;
    }

    TabPane {
        padding: 0;
    }

    .tab-horizontal {
        height: 1fr;
    }

    .tab-vertical {
        height: 1fr;
        layout: vertical;
    }

    .left-pane {
        width: 44%;
        border-right: solid $accent;
    }

    .search-bar {
        dock: top;
        margin: 0 1;
    }

    .table-pane {
        height: 1fr;
    }

    .right-pane {
        width: 1fr;
        padding: 0 1;
        overflow-y: auto;
    }

    .detail-view {
        height: auto;
    }

    .udm-top-pane {
        height: 52%;
        border-bottom: solid $accent;
    }

    .udm-bottom-pane {
        height: 48%;
        layout: horizontal;
    }

    .udm-bottom-left {
        width: 50%;
        border-right: solid $panel-lighten-2;
        padding: 0 1;
        overflow-y: auto;
    }

    .udm-bottom-right {
        width: 50%;
        padding: 0 1;
        overflow-y: auto;
    }

    .-maximized {
        dock: top;
        width: 100%;
        height: 100%;
    }

    #status {
        dock: bottom;
        height: 1;
        background: $panel;
        color: $text-muted;
        padding: 0 1;
    }
    """

    BINDINGS = [
        ("f1", "switch_tab('tab-cases')", "1: Triage"),
        ("1", "switch_tab('tab-cases')", "1: Triage"),
        ("f2", "switch_tab('tab-udm')", "2: UDM Hunt"),
        ("2", "switch_tab('tab-udm')", "2: UDM Hunt"),
        ("f3", "switch_tab('tab-rules')", "3: Detection"),
        ("3", "switch_tab('tab-rules')", "3: Detection"),
        ("f4", "switch_tab('tab-playbooks')", "4: Automation"),
        ("4", "switch_tab('tab-playbooks')", "4: Automation"),
        ("f5", "switch_tab('tab-dashboards')", "5: Dashboards"),
        ("5", "switch_tab('tab-dashboards')", "5: Dashboards"),
        ("alt+v", "split_vertical", "Split Vert"),
        ("alt+s", "split_horizontal", "Split Horiz"),
        ("alt+d", "quick_launcher", "Launcher"),
        ("alt+f", "toggle_maximize", "Maximize"),
        ("alt+w", "close_tile", "Close Tile"),
        ("alt+q", "close_tile", "Close Tile"),
        ("o", "case_overview", "Overview"),
        ("/", "focus_search", "Search"),
        ("r", "refresh", "Refresh"),
        ("c", "add_comment", "Add Comment"),
        ("a", "investigate_alert", "Alert"),
        ("e", "investigate_entity", "Entity Pivot"),
        ("p", "view_playbook", "Playbook"),
        ("i", "inspect_udm_event", "Inspect Event"),
        ("l", "view_raw_log", "Raw Log"),
        ("y", "yank_context", "Yank / Copy"),
        ("?", "show_help", "Help"),
        ("q", "quit", "Quit"),
    ]

    def __init__(self, engine: Any, initial_query: str = "", page_size: int = 50):
        super().__init__()
        self._engine = engine
        self._initial_query = initial_query
        self._page_size = page_size

        # Case cache
        self._items_by_row: Dict[str, Any] = {}
        self._current_case_id: Optional[str] = None
        self._current_investigation: Optional[Any] = None
        self._current_case_subview: str = "overview"
        self._case_subview_data: Optional[Any] = None

        # UDM cache
        self._udm_items_by_row: Dict[str, Any] = {}
        self._current_udm_row_key: Optional[str] = None

        # Rules cache
        self._rules_by_row: Dict[str, Any] = {}

        # Playbooks cache
        self._playbooks_by_row: Dict[str, Any] = {}

        # Dashboards cache
        self._dashboards_by_row: Dict[str, Any] = {}
        self._current_dashboard_id: Optional[str] = None
        self._current_dashboard_detail: Optional[Any] = None
        self._dashboard_query_results: Dict[str, Any] = {}

    # --- layout ------------------------------------------------------------

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        with TabbedContent(initial="tab-cases", id="main-tabs"):
            with TabPane("Cases [F1]", id="tab-cases"):
                with Horizontal(classes="tab-horizontal"):
                    with Vertical(classes="left-pane"):
                        yield Input(placeholder="Case search (e.g. AlertName:..., Entity:<hash>)", id="search", classes="search-bar")
                        yield DataTable(id="cases", cursor_type="row", zebra_stripes=True, classes="table-pane")
                    with Vertical(classes="right-pane"):
                        yield Static(Text("Select a case to investigate.", style="dim"), id="detail", classes="detail-view")

            with TabPane("UDM Search [F2]", id="tab-udm"):
                with Vertical(classes="tab-vertical"):
                    with Vertical(classes="udm-top-pane"):
                        yield Input(placeholder="UDM Query (e.g. metadata.event_type = \"USER_LOGIN\")", id="udm-search", classes="search-bar")
                        yield DataTable(id="udm-table", cursor_type="row", zebra_stripes=True, classes="table-pane")
                    with Horizontal(classes="udm-bottom-pane"):
                        with VerticalScroll(classes="udm-bottom-left"):
                            yield Static(Text("Select a UDM event to inspect Actor / Target / Network fields.", style="dim"), id="udm-detail", classes="detail-view")
                        with VerticalScroll(classes="udm-bottom-right"):
                            yield Static(Text("Select a UDM event to inspect raw log payload.", style="dim"), id="udm-raw-log", classes="detail-view")

            with TabPane("Curated Rules [F3]", id="tab-rules"):
                with Horizontal(classes="tab-horizontal"):
                    with Vertical(classes="left-pane"):
                        yield Input(placeholder="Search Curated Rule Sets (e.g. Ransomware, Phishing)...", id="rules-search", classes="search-bar")
                        yield DataTable(id="rules-table", cursor_type="row", zebra_stripes=True, classes="table-pane")
                    with Vertical(classes="right-pane"):
                        yield Static(Text("Select a Curated Rule Set to view member rules and MITRE mappings.", style="dim"), id="rules-detail", classes="detail-view")

            with TabPane("Playbooks [F4]", id="tab-playbooks"):
                with Horizontal(classes="tab-horizontal"):
                    with Vertical(classes="left-pane"):
                        yield Input(placeholder="Search Playbooks (e.g. Triage, Containment)...", id="playbooks-search", classes="search-bar")
                        yield DataTable(id="playbooks-table", cursor_type="row", zebra_stripes=True, classes="table-pane")
                    with Vertical(classes="right-pane"):
                        yield Static(Text("Select a Playbook to view definition triggers and step actions.", style="dim"), id="playbooks-detail", classes="detail-view")

            with TabPane("Dashboards [F5]", id="tab-dashboards"):
                with Horizontal(classes="tab-horizontal"):
                    with Vertical(classes="left-pane"):
                        yield Input(placeholder="Search Dashboards (e.g. Ingestion, Health, Threat)...", id="dashboards-search", classes="search-bar")
                        yield DataTable(id="dashboards-table", cursor_type="row", zebra_stripes=True, classes="table-pane")
                    with Vertical(classes="right-pane"):
                        with VerticalScroll():
                            yield Static(Text("Select a Dashboard to inspect composite visual charts and execute queries.", style="dim"), id="dashboards-detail", classes="detail-view")

        yield Static("", id="status")
        yield Footer()

    def on_mount(self) -> None:
        # Initialize Case columns
        for selector, cols in [
            ("#cases", render.CASE_LIST_COLUMNS),
            ("#udm-table", render.UDM_EVENT_COLUMNS),
            ("#rules-table", render.RULE_COLUMNS),
            ("#playbooks-table", render.PLAYBOOK_CATALOGUE_COLUMNS),
            ("#dashboards-table", render.DASHBOARD_COLUMNS),
        ]:
            matches = self.query(selector)
            if matches:
                tbl = matches.first()
                for col in cols:
                    tbl.add_column(col, key=col)

        search_inputs = self.query("#search")
        if search_inputs:
            search_inputs.first().value = self._initial_query
        self._set_status("Loading cases… [F1: Cases, F2: UDM, F3: Rules, F4: Playbooks, F5: Dashboards]")
        self._set_loading("#cases, #tile-cases-table", True)
        self._load_cases(self._initial_query)

    # --- status helper -----------------------------------------------------

    def _set_status(self, text: str) -> None:
        statuses = self.query("#status")
        if statuses:
            statuses.first().update(text)

    def _set_loading(self, selector: str, loading: bool) -> None:
        try:
            for widget in self.query(selector):
                widget.loading = loading
        except Exception:
            pass

    # --- actions -----------------------------------------------------------

    def action_switch_tab(self, tab_id: str) -> None:
        tabs = self.query_one("#main-tabs", TabbedContent)
        tabs.active = tab_id

    def _refresh_udm_table(self) -> None:
        tables = self.query("#udm-table")
        if tables:
            table = tables.first()
            table.clear()
            if not table.columns:
                for col in render.UDM_EVENT_COLUMNS:
                    table.add_column(col, key=col)
            for row_key, event in self._udm_items_by_row.items():
                table.add_row(*render.udm_event_row(event), key=row_key)

    def _refresh_rules_table(self) -> None:
        tables = self.query("#rules-table")
        if tables:
            table = tables.first()
            table.clear()
            if not table.columns:
                for col in render.RULE_COLUMNS:
                    table.add_column(col, key=col)
            for row_key, item in self._rules_by_row.items():
                table.add_row(*render.rule_row(item), key=row_key)

    def _refresh_playbooks_table(self) -> None:
        tables = self.query("#playbooks-table")
        if tables:
            table = tables.first()
            table.clear()
            if not table.columns:
                for col in render.PLAYBOOK_CATALOGUE_COLUMNS:
                    table.add_column(col, key=col)
            for row_key, item in self._playbooks_by_row.items():
                table.add_row(*render.playbook_catalogue_row(item), key=row_key)

    def _refresh_dashboards_table(self) -> None:
        tables = self.query("#dashboards-table")
        if tables:
            table = tables.first()
            table.clear()
            if not table.columns:
                for col in render.DASHBOARD_COLUMNS:
                    table.add_column(col, key=col)
            for row_key, item in self._dashboards_by_row.items():
                table.add_row(*render.dashboard_row(item), key=row_key)

    def action_focus_search(self) -> None:
        active_tab = self.query_one("#main-tabs", TabbedContent).active
        if active_tab == "tab-cases":
            search_box = self.query("#search")
            if search_box:
                search_box.first().focus()
        elif active_tab == "tab-udm":
            search_box = self.query("#udm-search")
            if search_box:
                search_box.first().focus()
        elif active_tab == "tab-rules":
            search_box = self.query("#rules-search")
            if search_box:
                search_box.first().focus()
        elif active_tab == "tab-playbooks":
            search_box = self.query("#playbooks-search")
            if search_box:
                search_box.first().focus()
        elif active_tab == "tab-dashboards":
            search_box = self.query("#dashboards-search")
            if search_box:
                search_box.first().focus()

    def action_show_help(self) -> None:
        self.push_screen(ViewerModal(render.help_panel(), title="Help"))

    def action_refresh(self) -> None:
        active_tab = self.query_one("#main-tabs", TabbedContent).active
        self._set_status("Refreshing…")
        if active_tab == "tab-cases":
            search_box = self.query("#search")
            q = search_box.first().value if search_box else ""
            self._set_loading("#cases, #tile-cases-table", True)
            self._load_cases(q)
            if self._current_case_id:
                self._set_loading("#detail, #tile-case-detail-static", True)
                self._load_detail(self._current_case_id)
        elif active_tab == "tab-udm":
            search_box = self.query("#udm-search")
            q = search_box.first().value if search_box else ""
            self._set_loading("#udm-table, #tile-udm-table", True)
            self._load_udm_events(q)
        elif active_tab == "tab-rules":
            search_box = self.query("#rules-search")
            q = search_box.first().value if search_box else ""
            self._set_loading("#rules-table, #tile-rules-table", True)
            self._load_rules(q)
        elif active_tab == "tab-playbooks":
            search_box = self.query("#playbooks-search")
            q = search_box.first().value if search_box else ""
            self._set_loading("#playbooks-table, #tile-playbooks-table", True)
            self._load_playbooks(q)
        elif active_tab == "tab-dashboards":
            search_box = self.query("#dashboards-search")
            q = search_box.first().value if search_box else ""
            self._set_loading("#dashboards-table, #tile-dashboards-table", True)
            self._load_dashboards(q)

    def on_tabbed_content_tab_activated(self, event: TabbedContent.TabActivated) -> None:
        raw_id = getattr(event.pane, "id", None) or getattr(event.tab, "id", "") or ""
        if "udm" in raw_id:
            pane_id = "tab-udm"
        elif "rules" in raw_id:
            pane_id = "tab-rules"
        elif "playbook" in raw_id:
            pane_id = "tab-playbooks"
        elif "dashboard" in raw_id:
            pane_id = "tab-dashboards"
        else:
            pane_id = "tab-cases"

        if pane_id == "tab-cases":
            self._set_status("Active: Cases Triage. Shortcuts: [c] Comment, [a] Alert, [e] Pivot, [p] Playbook.")
            search_box = self.query("#search")
            if search_box:
                search_box.first().focus()
        elif pane_id == "tab-udm":
            self._set_status("Active: UDM Search & Event Stream. Enter query and press Enter.")
            search_box = self.query("#udm-search")
            if search_box:
                search_box.first().focus()
            if not self._udm_items_by_row:
                q = search_box.first().value if search_box else ""
                if q:
                    self._set_loading("#udm-table, #tile-udm-table", True)
                    self._load_udm_events(q)
                elif hasattr(self._engine, "search_events") and not hasattr(self._engine, "_search_udm_wf"):
                    self._set_loading("#udm-table, #tile-udm-table", True)
                    self._load_udm_events("")
            else:
                self._refresh_udm_table()
        elif pane_id == "tab-rules":
            self._set_status("Active: Curated Detection Rules. Select a ruleset to view logic.")
            search_box = self.query("#rules-search")
            if search_box:
                search_box.first().focus()
            if not self._rules_by_row:
                q = search_box.first().value if search_box else ""
                self._set_loading("#rules-table, #tile-rules-table", True)
                self._load_rules(q)
            else:
                self._refresh_rules_table()
        elif pane_id == "tab-playbooks":
            self._set_status("Active: Playbooks Catalogue. Select a playbook to view definition.")
            search_box = self.query("#playbooks-search")
            if search_box:
                search_box.first().focus()
            if not self._playbooks_by_row:
                q = search_box.first().value if search_box else ""
                self._set_loading("#playbooks-table, #tile-playbooks-table", True)
                self._load_playbooks(q)
            else:
                self._refresh_playbooks_table()
        elif pane_id == "tab-dashboards":
            self._set_status("Active: Google SecOps Dashboards. Select a dashboard to view visual charts.")
            search_box = self.query("#dashboards-search")
            if search_box:
                search_box.first().focus()
            if not self._dashboards_by_row:
                q = search_box.first().value if search_box else ""
                self._set_loading("#dashboards-table, #tile-dashboards-table", True)
                self._load_dashboards(q)
            else:
                self._refresh_dashboards_table()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        input_id = event.input.id
        if input_id in ("search", "tile-cases-search"):
            self._set_status(f"Searching cases: {event.value!r} …")
            self._set_loading("#cases, #tile-cases-table", True)
            self._load_cases(event.value)
        elif input_id in ("udm-search", "tile-udm-search"):
            self._set_status(f"Searching UDM events: {event.value!r} …")
            self._set_loading("#udm-table, #tile-udm-table", True)
            self._load_udm_events(event.value)
        elif input_id in ("rules-search", "tile-rules-search"):
            self._set_status(f"Searching Curated Rules: {event.value!r} …")
            self._set_loading("#rules-table, #tile-rules-table", True)
            self._load_rules(event.value)
        elif input_id in ("playbooks-search", "tile-playbooks-search"):
            self._set_status(f"Searching Playbooks: {event.value!r} …")
            self._set_loading("#playbooks-table, #tile-playbooks-table", True)
            self._load_playbooks(event.value)
        elif input_id in ("dashboards-search", "tile-dashboards-search"):
            self._set_status(f"Searching Dashboards: {event.value!r} …")
            self._set_loading("#dashboards-table, #tile-dashboards-table", True)
            self._load_dashboards(event.value)

    def on_data_table_row_selected(self, event: DataTable.RowSelected) -> None:
        table_id = event.data_table.id
        row_key = event.row_key.value

        if table_id in ("cases", "tile-cases-table"):
            item = self._items_by_row.get(row_key)
            if item is None:
                return
            case_id = getattr(item, "case_id", None)
            if not case_id:
                return
            self._current_case_id = str(case_id)
            self._set_status(f"Investigating case #{case_id} …")
            self._set_loading("#detail, #tile-case-detail-static", True)
            self._load_detail(str(case_id))

        elif table_id in ("udm-table", "tile-udm-table"):
            self._current_udm_row_key = row_key
            event_obj = self._udm_items_by_row.get(row_key)
            if event_obj is not None:
                for detail in self.query("#udm-detail, #tile-udm-detail-static"):
                    detail.update(render.udm_event_detail(event_obj))
                self._set_status("Inspecting selected UDM event fields. [i] Inspect Full Event  ·  [l] View Raw Log")
                self._set_loading("#udm-raw-log, #tile-raw-log-static", True)
                self._load_raw_log(event_obj)

        elif table_id in ("rules-table", "tile-rules-table"):
            ruleset = self._rules_by_row.get(row_key)
            if ruleset is not None:
                rs_id = getattr(ruleset, "id", None) or getattr(ruleset, "title", str(row_key))
                self._set_status(f"Loading Curated Rule Set: {getattr(ruleset, 'title', rs_id)} …")
                self._set_loading("#rules-detail, #tile-rule-detail-static", True)
                self._load_rule_detail(str(rs_id))

        elif table_id in ("playbooks-table", "tile-playbooks-table"):
            pb = self._playbooks_by_row.get(row_key)
            if pb is not None:
                pb_id = getattr(pb, "id", None) or getattr(pb, "identifier", str(row_key))
                self._set_status(f"Loading Playbook: {getattr(pb, 'name', pb_id)} …")
                self._set_loading("#playbooks-detail, #tile-playbook-detail-static", True)
                self._load_playbook_detail(str(pb_id))

        elif table_id in ("dashboards-table", "tile-dashboards-table"):
            dash = self._dashboards_by_row.get(row_key)
            if dash is not None:
                d_id = getattr(dash, "id", None) or getattr(dash, "name", str(row_key))
                self._current_dashboard_id = str(d_id)
                self._set_status(f"Loading Dashboard: {getattr(dash, 'display_name', d_id)} …")
                self._set_loading("#dashboards-detail, #tile-dashboard-detail-static", True)
                self._load_dashboard_composite(str(d_id))

    def on_data_table_row_highlighted(self, event: DataTable.RowHighlighted) -> None:
        table_id = event.data_table.id
        row_key = event.row_key.value

        if table_id in ("cases", "tile-cases-table"):
            item = self._items_by_row.get(row_key)
            if item is not None:
                cid = getattr(item, "case_id", None)
                if cid and str(cid) != self._current_case_id:
                    self._current_case_id = str(cid)
                    self._current_case_subview = "overview"
                    self._case_subview_data = None
                    self._set_loading("#detail, #tile-case-detail-static", True)
                    self._load_detail(str(cid))

        elif table_id in ("udm-table", "tile-udm-table"):
            self._current_udm_row_key = row_key
            event_obj = self._udm_items_by_row.get(row_key)
            if event_obj is not None:
                for detail in self.query("#udm-detail, #tile-udm-detail-static"):
                    detail.update(render.udm_event_detail(event_obj))
                self._set_loading("#udm-raw-log, #tile-raw-log-static", True)
                self._load_raw_log(event_obj)

        elif table_id in ("rules-table", "tile-rules-table"):
            ruleset = self._rules_by_row.get(row_key)
            if ruleset is not None:
                rs_id = getattr(ruleset, "id", None) or getattr(ruleset, "title", str(row_key))
                self._set_loading("#rules-detail, #tile-rule-detail-static", True)
                self._load_rule_detail(str(rs_id))

        elif table_id in ("playbooks-table", "tile-playbooks-table"):
            pb = self._playbooks_by_row.get(row_key)
            if pb is not None:
                pb_id = getattr(pb, "id", None) or getattr(pb, "identifier", str(row_key))
                self._set_loading("#playbooks-detail, #tile-playbook-detail-static", True)
                self._load_playbook_detail(str(pb_id))

        elif table_id in ("dashboards-table", "tile-dashboards-table"):
            dash = self._dashboards_by_row.get(row_key)
            if dash is not None:
                d_id = getattr(dash, "id", None) or getattr(dash, "name", str(row_key))
                if str(d_id) != self._current_dashboard_id:
                    self._current_dashboard_id = str(d_id)
                    self._set_loading("#dashboards-detail, #tile-dashboard-detail-static", True)
                    self._load_dashboard_composite(str(d_id))

    # --- i3-style tiling & window manager actions --------------------------

    def _init_tile_data(self, tile: TileFrame) -> None:
        ttype = tile.tile_type
        if ttype == "cases":
            tbls = tile.query("#tile-cases-table")
            if tbls:
                tbl = tbls.first()
                if not tbl.columns:
                    for col in render.CASE_LIST_COLUMNS:
                        tbl.add_column(col, key=col)
                for rk, itm in self._items_by_row.items():
                    tbl.add_row(*render.case_row(itm), key=rk)
        elif ttype == "case-detail":
            if self._current_investigation:
                details = tile.query("#tile-case-detail-static")
                if details:
                    details.first().update(render.case_detail(self._current_investigation))
        elif ttype == "udm-search":
            tbls = tile.query("#tile-udm-table")
            if tbls:
                tbl = tbls.first()
                if not tbl.columns:
                    for col in render.UDM_EVENT_COLUMNS:
                        tbl.add_column(col, key=col)
                for rk, ev in self._udm_items_by_row.items():
                    tbl.add_row(*render.udm_event_row(ev), key=rk)
        elif ttype == "udm-detail":
            if self._current_udm_row_key and self._current_udm_row_key in self._udm_items_by_row:
                details = tile.query("#tile-udm-detail-static")
                if details:
                    details.first().update(render.udm_event_detail(self._udm_items_by_row[self._current_udm_row_key]))
        elif ttype == "raw-log":
            if self._current_udm_row_key and self._current_udm_row_key in self._udm_items_by_row:
                ev = self._udm_items_by_row[self._current_udm_row_key]
                ev_id = render._normalize_udm_event(ev).get("metadata", {}).get("id", "event")
                details = tile.query("#tile-raw-log-static")
                if details:
                    details.first().update(render.raw_log_panel(f"<raw log for {ev_id}>", event_id=ev_id))
        elif ttype == "rules":
            tbls = tile.query("#tile-rules-table")
            if tbls:
                tbl = tbls.first()
                if not tbl.columns:
                    for col in render.RULE_COLUMNS:
                        tbl.add_column(col, key=col)
                for rk, itm in self._rules_by_row.items():
                    tbl.add_row(*render.rule_row(itm), key=rk)
        elif ttype == "playbooks":
            tbls = tile.query("#tile-playbooks-table")
            if tbls:
                tbl = tbls.first()
                if not tbl.columns:
                    for col in render.PLAYBOOK_CATALOGUE_COLUMNS:
                        tbl.add_column(col, key=col)
                for rk, itm in self._playbooks_by_row.items():
                    tbl.add_row(*render.playbook_catalogue_row(itm), key=rk)
        elif ttype == "dashboards":
            tbls = tile.query("#tile-dashboards-table")
            if tbls:
                tbl = tbls.first()
                if not tbl.columns:
                    for col in render.DASHBOARD_COLUMNS:
                        tbl.add_column(col, key=col)
                for rk, itm in self._dashboards_by_row.items():
                    tbl.add_row(*render.dashboard_row(itm), key=rk)
        elif ttype == "dashboard-detail":
            if self._current_dashboard_detail:
                details = tile.query("#tile-dashboard-detail-static")
                if details:
                    details.first().update(render.dashboard_detail_panel(self._current_dashboard_detail, self._dashboard_query_results))

    def action_split_vertical(self) -> None:
        def _on_tile_selected(result: Optional[Tuple[str, str]]) -> None:
            if not result:
                return
            _, tile_type = result
            active_tab = self.query_one("#main-tabs", TabbedContent).active
            ws_containers = self.query(f"#{active_tab} .tab-horizontal")
            if ws_containers:
                new_tile = create_tile(tile_type)
                ws_containers.first().mount(new_tile)
                self._init_tile_data(new_tile)
                title = TILE_REGISTRY.get(tile_type, (tile_type,))[0]
                self.notify(f"Spawned {title} tile into vertical split.", severity="information")
                self._set_status(f"Tile spawned: {title} (Split Vert).")

        self.push_screen(TileLauncherModal(action_mode="split-v"), _on_tile_selected)

    def action_split_horizontal(self) -> None:
        def _on_tile_selected(result: Optional[Tuple[str, str]]) -> None:
            if not result:
                return
            _, tile_type = result
            active_tab = self.query_one("#main-tabs", TabbedContent).active
            panes = self.query(f"#{active_tab} .left-pane, #{active_tab} .right-pane, #{active_tab} TileFrame")
            target_parent = panes.first() if panes else None
            if target_parent:
                new_tile = create_tile(tile_type)
                target_parent.mount(new_tile)
                self._init_tile_data(new_tile)
                title = TILE_REGISTRY.get(tile_type, (tile_type,))[0]
                self.notify(f"Spawned {title} tile into horizontal split.", severity="information")
                self._set_status(f"Tile spawned: {title} (Split Horiz).")

        self.push_screen(TileLauncherModal(action_mode="split-h"), _on_tile_selected)

    def action_quick_launcher(self) -> None:
        def _on_tile_selected(result: Optional[Tuple[str, str]]) -> None:
            if not result:
                return
            _, tile_type = result
            active_tab = self.query_one("#main-tabs", TabbedContent).active
            ws_containers = self.query(f"#{active_tab} .tab-horizontal")
            if ws_containers:
                new_tile = create_tile(tile_type)
                ws_containers.first().mount(new_tile)
                self._init_tile_data(new_tile)
                title = TILE_REGISTRY.get(tile_type, (tile_type,))[0]
                self.notify(f"Spawned {title} tile.", severity="information")
                self._set_status(f"Tile spawned: {title}.")

        self.push_screen(TileLauncherModal(action_mode="open"), _on_tile_selected)

    def action_toggle_maximize(self) -> None:
        focused_tiles = [t for t in self.query(TileFrame) if t.has_focus or t.query("*:focus")]
        if not focused_tiles:
            active_tab = self.query_one("#main-tabs", TabbedContent).active
            active_tiles = list(self.query(f"#{active_tab} TileFrame"))
            if active_tiles:
                focused_tiles = active_tiles[:1]

        if focused_tiles:
            tile = focused_tiles[0]
            is_max = tile.toggle_maximize()
            status = "Maximized" if is_max else "Restored"
            self.notify(f"Tile {tile.tile_title} {status}", severity="information")
            self._set_status(f"Tile {status.lower()}: {tile.tile_title}")
        else:
            panes = [p for p in self.query(".left-pane, .right-pane") if p.has_focus or p.query("*:focus")]
            if panes:
                p = panes[0]
                if p.has_class("-maximized"):
                    p.remove_class("-maximized")
                    self.notify("Pane restored", severity="information")
                    self._set_status("Pane restored.")
                else:
                    p.add_class("-maximized")
                    self.notify("Pane maximized", severity="information")
                    self._set_status("Pane maximized.")
            else:
                self.notify("Focus a tile or pane to maximize.", severity="warning")

    def action_close_tile(self) -> None:
        focused_tiles = [t for t in self.query(TileFrame) if t.has_focus or t.query("*:focus")]
        if not focused_tiles:
            active_tab = self.query_one("#main-tabs", TabbedContent).active
            active_tiles = list(self.query(f"#{active_tab} TileFrame"))
            if active_tiles:
                focused_tiles = active_tiles[-1:]

        if focused_tiles:
            tile = focused_tiles[0]
            t_name = tile.tile_title
            tile.remove()
            self.notify(f"Closed tile: {t_name}", severity="information")
            self._set_status(f"Closed tile: {t_name}")
        else:
            self.notify("No dynamic tile currently focused to close.", severity="information")


    # --- interactive drill-downs & analyst actions -------------------------

    def action_add_comment(self) -> None:
        if not self._current_case_id:
            self._set_status("Select a case first to add a comment.")
            self.notify("Select a case first.", severity="warning")
            return

        def _on_comment_submitted(comment_text: Optional[str]) -> None:
            if comment_text:
                self._set_status(f"Posting comment to case #{self._current_case_id} …")
                self._set_loading("#detail, #tile-case-detail-static", True)
                self._post_comment(self._current_case_id, comment_text)

        self.push_screen(AddCommentModal(self._current_case_id), _on_comment_submitted)

    def action_investigate_alert(self) -> None:
        if not self._current_investigation:
            self._set_status("Select and load a case first to investigate its alerts.")
            self.notify("Select and load a case first.", severity="warning")
            return

        alerts = getattr(self._current_investigation, "alerts", []) or []
        if not alerts:
            self._set_status("Current case has no alerts to investigate.")
            self.notify("No alerts in current case.", severity="information")
            return

        if len(alerts) == 1:
            alert = alerts[0]
            aname = getattr(alert, "name", None) or getattr(alert, "identifier", "")
            title = getattr(alert, "display_name", None) or getattr(alert, "identifier", aname)
            self._set_status(f"Investigating alert {title} …")
            self._set_loading("#detail, #tile-case-detail-static", True)
            self._load_alert_drilldown(aname, self._current_case_id or "")
        else:
            def _on_alert_picked(alert_obj: Optional[Any]) -> None:
                if alert_obj is not None:
                    aname = getattr(alert_obj, "name", None) or getattr(alert_obj, "identifier", "")
                    title = getattr(alert_obj, "display_name", None) or getattr(alert_obj, "identifier", aname)
                    self._set_status(f"Investigating alert {title} …")
                    self._set_loading("#detail, #tile-case-detail-static", True)
                    self._load_alert_drilldown(aname, self._current_case_id or "")

            self.push_screen(SelectAlertModal(alerts), _on_alert_picked)

    def action_investigate_entity(self) -> None:
        entities = getattr(self._current_investigation, "entities", []) if self._current_investigation else []

        def _on_entity_picked(indicator: Optional[str]) -> None:
            if indicator:
                self._set_status(f"Pivoting on indicator: {indicator} …")
                self._set_loading("#detail, #tile-case-detail-static", True)
                self._load_entity_drilldown(indicator)

        self.push_screen(SelectEntityModal(entities), _on_entity_picked)

    def action_view_playbook(self) -> None:
        if not self._current_investigation:
            self._set_status("Select and load a case first to view attached playbooks.")
            self.notify("Select a case first.", severity="warning")
            return

        alerts = getattr(self._current_investigation, "alerts", []) or []
        alert_with_pb = next((a for a in alerts if getattr(a, "attached_playbook_name", None)), None)
        target_alert = alert_with_pb or (alerts[0] if alerts else None)

        if not target_alert:
            self._set_status("No alerts or playbooks attached to current case.")
            self.notify("No playbook attached to this case.", severity="information")
            return

        alert_id = getattr(target_alert, "alert_group_identifier", None) or getattr(target_alert, "name", None) or getattr(target_alert, "identifier", "")
        self._set_status(f"Loading playbook instance for alert {alert_id} …")
        self._set_loading("#detail, #tile-case-detail-static", True)
        self._load_playbook_run(self._current_case_id or "", alert_id)

    def action_case_overview(self) -> None:
        self._current_case_subview = "overview"
        self._case_subview_data = None
        if self._current_investigation:
            for detail in self.query("#detail, #tile-case-detail-static"):
                detail.update(render.case_detail(self._current_investigation, active_subview="overview"))
            cid = getattr(self._current_investigation, "case_id", self._current_case_id)
            self._set_status(f"Case #{cid} Overview. Inline views: [a] Alerts, [e] Pivot, [p] Playbook, [c] Comment.")

    def on_key(self, event: events.Key) -> None:
        focused = self.focused
        if isinstance(focused, Input):
            if event.key == "escape":
                active_tab = self.query_one("#main-tabs", TabbedContent).active
                matching_tables = list(self.query(f"#{active_tab} DataTable"))
                if matching_tables:
                    matching_tables[0].focus()
                    event.stop()
            elif event.key == "down":
                active_tab = self.query_one("#main-tabs", TabbedContent).active
                matching_tables = list(self.query(f"#{active_tab} DataTable"))
                if matching_tables:
                    matching_tables[0].focus()
                    event.stop()
        elif event.key == "escape":
            if self._current_case_subview != "overview":
                self.action_case_overview()
                event.stop()

    def action_inspect_udm_event(self) -> None:
        if not self._current_udm_row_key or self._current_udm_row_key not in self._udm_items_by_row:
            self._set_status("Select a UDM event row first to inspect full details.")
            self.notify("Select a UDM event row first.", severity="warning")
            return

        event_obj = self._udm_items_by_row[self._current_udm_row_key]
        ev = render._normalize_udm_event(event_obj)
        ev_id = ev.get("metadata", {}).get("id") or str(self._current_udm_row_key)
        self._set_status(f"Inspecting enriched UDM event {ev_id} …")
        self._set_loading("#udm-detail, #tile-udm-detail-static", True)
        self._load_enriched_event(event_obj)

    def action_view_raw_log(self) -> None:
        if not self._current_udm_row_key or self._current_udm_row_key not in self._udm_items_by_row:
            self._set_status("Select a UDM event row first to view raw log.")
            self.notify("Select a UDM event row first.", severity="warning")
            return

        event_obj = self._udm_items_by_row[self._current_udm_row_key]
        ev = render._normalize_udm_event(event_obj)
        ev_id = ev.get("metadata", {}).get("id") or str(self._current_udm_row_key)
        self._set_status(f"Fetching raw log for event {ev_id} …")
        self._set_loading("#udm-raw-log, #tile-raw-log-static", True)
        self._load_raw_log(event_obj)

    def action_yank_context(self) -> None:
        active_tab = self.query_one("#main-tabs", TabbedContent).active
        text_to_copy = ""
        desc = ""

        if active_tab == "tab-cases":
            if self._current_case_subview == "alerts" and self._case_subview_data:
                inv = self._case_subview_data.get("inv")
                text_to_copy = str(getattr(inv, "display_name", "") or getattr(inv, "name", ""))
                desc = "Alert details"
            elif self._current_case_subview == "entities" and self._case_subview_data:
                report = self._case_subview_data
                text_to_copy = str(getattr(report, "indicator", ""))
                desc = f"Entity indicator '{text_to_copy}'"
            elif self._current_case_subview == "playbook" and self._case_subview_data:
                run = self._case_subview_data
                text_to_copy = str(getattr(run, "name", "") or getattr(run, "id", ""))
                desc = "Playbook run"
            elif self._current_investigation:
                cid = getattr(self._current_investigation, "case_id", self._current_case_id)
                title = getattr(self._current_investigation, "title", "")
                text_to_copy = f"Case #{cid}: {title}"
                desc = f"Case #{cid}"
            elif self._current_case_id:
                text_to_copy = str(self._current_case_id)
                desc = f"Case ID #{self._current_case_id}"

        elif active_tab == "tab-udm":
            if self._current_udm_row_key and self._current_udm_row_key in self._udm_items_by_row:
                ev = self._udm_items_by_row[self._current_udm_row_key]
                norm = render._normalize_udm_event(ev)
                import json
                text_to_copy = json.dumps(norm, indent=2, default=str)
                desc = "UDM Event JSON"

        elif active_tab == "tab-rules":
            active_row = None
            tbl = self.query("#rules-table")
            if tbl and tbl.first().cursor_row is not None:
                rows = list(self._rules_by_row.keys())
                idx = tbl.first().cursor_row
                if 0 <= idx < len(rows):
                    active_row = rows[idx]
            if active_row and active_row in self._rules_by_row:
                item = self._rules_by_row[active_row]
                text_to_copy = str(getattr(item, "id", "") or getattr(item, "title", ""))
                desc = f"Rule ID '{text_to_copy}'"

        elif active_tab == "tab-playbooks":
            active_row = None
            tbl = self.query("#playbooks-table")
            if tbl and tbl.first().cursor_row is not None:
                rows = list(self._playbooks_by_row.keys())
                idx = tbl.first().cursor_row
                if 0 <= idx < len(rows):
                    active_row = rows[idx]
            if active_row and active_row in self._playbooks_by_row:
                item = self._playbooks_by_row[active_row]
                text_to_copy = str(getattr(item, "id", "") or getattr(item, "identifier", "") or getattr(item, "name", ""))
                desc = f"Playbook '{text_to_copy}'"

        elif active_tab == "tab-dashboards":
            active_row = None
            tbl = self.query("#dashboards-table")
            if tbl and tbl.first().cursor_row is not None:
                rows = list(self._dashboards_by_row.keys())
                idx = tbl.first().cursor_row
                if 0 <= idx < len(rows):
                    active_row = rows[idx]
            if active_row and active_row in self._dashboards_by_row:
                item = self._dashboards_by_row[active_row]
                text_to_copy = str(getattr(item, "id", "") or getattr(item, "name", "") or getattr(item, "display_name", ""))
                desc = f"Dashboard '{text_to_copy}'"

        if text_to_copy:
            self.copy_to_clipboard(text_to_copy)
            self.notify(f"Copied {desc} to clipboard!", severity="information")
            self._set_status(f"Copied {desc} to system clipboard.")
        else:
            self.notify("No active item to copy.", severity="warning")

    # --- workers (ALL facade access happens here, off the UI thread) -------

    @work(thread=True, exclusive=True, group="search")
    def _load_cases(self, query: str) -> None:
        try:
            batch = self._engine.search_cases(query=query, page_size=self._page_size)
            items = list(getattr(batch, "items", getattr(batch, "results", batch if isinstance(batch, list) else [])) or [])
            total = int(getattr(batch, "total_count", len(items)))
            self.post_message(self.CasesLoaded(items=items, total=total, query=query))
        except Exception as exc:
            self.post_message(self.CasesFailed(error=str(exc), query=query))

    @work(thread=True, exclusive=True, group="detail")
    def _load_detail(self, case_id: str) -> None:
        try:
            inv = self._engine.investigate_case(case_id)
            self.post_message(self.DetailLoaded(investigation=inv))
        except Exception as exc:
            self.post_message(self.DetailFailed(error=str(exc), case_id=case_id))

    @work(thread=True, exclusive=True, group="alert_drilldown")
    def _load_alert_drilldown(self, alert_name: str, case_id: str) -> None:
        try:
            inv = self._engine.investigate_alert(alert_name)
            playbook_run = None
            if hasattr(self._engine, "get_alert_playbook_instance"):
                try:
                    playbook_run = self._engine.get_alert_playbook_instance(case_id=case_id, alert_identifier=alert_name)
                except Exception:
                    pass
            self.post_message(self.AlertLoaded(investigation=inv, playbook_run=playbook_run))
        except Exception as exc:
            self.post_message(self.AlertFailed(error=str(exc), alert_name=alert_name))

    @work(thread=True, exclusive=True, group="entity_drilldown")
    def _load_entity_drilldown(self, indicator: str) -> None:
        try:
            report = self._engine.investigate_entity(indicator)
            self.post_message(self.EntityLoaded(report=report))
        except Exception as exc:
            self.post_message(self.EntityFailed(error=str(exc), indicator=indicator))

    @work(thread=True, exclusive=True, group="playbook_drilldown")
    def _load_playbook_run(self, case_id: str, alert_id: str) -> None:
        try:
            run = self._engine.get_alert_playbook_instance(case_id=case_id, alert_identifier=alert_id)
            self.post_message(self.PlaybookLoaded(run=run))
        except Exception as exc:
            self.post_message(self.PlaybookFailed(error=str(exc), alert_id=alert_id))

    @work(thread=True, exclusive=True, group="comment_action")
    def _post_comment(self, case_id: str, comment: str) -> None:
        try:
            rec = self._engine.add_case_comment(case_id=case_id, comment=comment)
            self.post_message(self.CommentAdded(case_id=case_id, record=rec))
        except Exception as exc:
            self.post_message(self.CommentFailed(case_id=case_id, error=str(exc)))

    @work(thread=True, exclusive=True, group="udm_search")
    def _load_udm_events(self, query: str) -> None:
        try:
            q = query.strip() if query else ""
            if hasattr(self._engine, "search_events") and not hasattr(self._engine, "_search_udm_wf"):
                batch = self._engine.search_events(query=q)
                events = list(getattr(batch, "events", getattr(batch, "results", batch if isinstance(batch, list) else [])) or [])
                total = int(getattr(batch, "total_events", len(events)))
            elif hasattr(self._engine, "search_udm"):
                if not q:
                    events = []
                    total = 0
                else:
                    now = datetime.now(timezone.utc)
                    start_time = (now - timedelta(days=1)).strftime("%Y-%m-%dT%H:%M:%SZ")
                    end_time = now.strftime("%Y-%m-%dT%H:%M:%SZ")
                    req = SearchRequest(
                        query=q,
                        start_time=start_time,
                        end_time=end_time,
                        receive_limit=100,
                        batch_size=100,
                    )
                    session = self._engine.search_udm(request=req)
                    if getattr(session, "lifecycle", None) == LifecycleState.FAILED:
                        raise RuntimeError(session.error or "UDM Search failed against SecOps backend.")
                    events = list(getattr(session, "events", []) or [])
                    total = int(getattr(session, "received_count", len(events)))
            else:
                events = []
                total = 0
            self.post_message(self.UdmEventsLoaded(events=events, total=total, query=query))
        except Exception as exc:
            self.post_message(self.UdmEventsFailed(error=str(exc), query=query))

    @work(thread=True, exclusive=True, group="enriched_event")
    def _load_enriched_event(self, event_ref: Any) -> None:
        ev = render._normalize_udm_event(event_ref)
        ev_id = ev.get("metadata", {}).get("id") or "event"
        try:
            if hasattr(self._engine, "investigate_event"):
                res = self._engine.investigate_event(event_ref=event_ref, eager_load_raw_log=False)
            elif hasattr(self._engine, "fetch_enriched_event"):
                res = self._engine.fetch_enriched_event(event_id=ev_id)
            else:
                res = event_ref
            self.post_message(self.EnrichedEventLoaded(investigation=res, event_id=ev_id))
        except Exception as exc:
            self.post_message(self.EnrichedEventFailed(error=str(exc), event_id=ev_id))

    @work(thread=True, exclusive=True, group="raw_log")
    def _load_raw_log(self, event_ref: Any) -> None:
        ev = render._normalize_udm_event(event_ref)
        ev_id = ev.get("metadata", {}).get("id") or "event"
        try:
            raw_log = None
            if hasattr(self._engine, "investigate_event"):
                res = self._engine.investigate_event(event_ref=event_ref, eager_load_raw_log=True)
                raw_log = getattr(res, "raw_log", None)
                if raw_log is None and hasattr(res, "load_raw_log"):
                    raw_log = res.load_raw_log()
            elif hasattr(self._engine, "get_raw_log"):
                log_token = event_ref.get("eventLogToken") if isinstance(event_ref, dict) else None
                raw_log = self._engine.get_raw_log(event_id=ev_id, log_token=log_token)

            if raw_log is None:
                raise RuntimeError(f"No raw log payload returned for event {ev_id}")
            self.post_message(self.RawLogLoaded(raw_log=raw_log, event_id=ev_id))
        except Exception as exc:
            self.post_message(self.RawLogFailed(error=str(exc), event_id=ev_id))

    @work(thread=True, exclusive=True, group="rules_search")
    def _load_rules(self, query: str) -> None:
        try:
            if hasattr(self._engine, "search_curated_rulesets"):
                batch = self._engine.search_curated_rulesets(query=query or None)
                items = list(getattr(batch, "results", getattr(batch, "items", batch if isinstance(batch, list) else [])) or [])
                total = int(getattr(batch, "total_count", len(items)))
            else:
                items = []
                total = 0
            self.post_message(self.RulesLoaded(items=items, total=total, query=query))
        except Exception as exc:
            self.post_message(self.RulesFailed(error=str(exc), query=query))

    @work(thread=True, exclusive=True, group="rules_detail")
    def _load_rule_detail(self, ruleset_id: str) -> None:
        try:
            if hasattr(self._engine, "get_curated_ruleset"):
                detail = self._engine.get_curated_ruleset(ruleset_id)
            else:
                detail = None
            self.post_message(self.RuleDetailLoaded(detail=detail))
        except Exception as exc:
            self.post_message(self.RuleDetailFailed(error=str(exc), ruleset_id=ruleset_id))

    @work(thread=True, exclusive=True, group="playbooks_search")
    def _load_playbooks(self, query: str) -> None:
        try:
            if hasattr(self._engine, "search_playbooks"):
                batch = self._engine.search_playbooks(query=query or None)
                items = list(getattr(batch, "results", getattr(batch, "items", batch if isinstance(batch, list) else [])) or [])
                total = int(getattr(batch, "total_count", len(items)))
            else:
                items = []
                total = 0
            self.post_message(self.PlaybooksLoaded(items=items, total=total, query=query))
        except Exception as exc:
            self.post_message(self.PlaybooksFailed(error=str(exc), query=query))

    @work(thread=True, exclusive=True, group="playbooks_detail")
    def _load_playbook_detail(self, playbook_id: str) -> None:
        try:
            if hasattr(self._engine, "get_playbook"):
                detail = self._engine.get_playbook(playbook_id)
            else:
                detail = None
            self.post_message(self.PlaybookDetailLoaded(detail=detail))
        except Exception as exc:
            self.post_message(self.PlaybookDetailFailed(error=str(exc), playbook_id=playbook_id))

    @work(thread=True, exclusive=True, group="dashboards_search")
    def _load_dashboards(self, query: str) -> None:
        try:
            if hasattr(self._engine, "search_dashboards"):
                batch = self._engine.search_dashboards(query=query or None)
                items = list(getattr(batch, "dashboards", getattr(batch, "results", [])) or [])
                total = int(getattr(batch, "total_count", len(items)))
            else:
                items = []
                total = 0
            self.post_message(self.DashboardsLoaded(items=items, total=total, query=query))
        except Exception as exc:
            self.post_message(self.DashboardsFailed(error=str(exc), query=query))

    @work(thread=True, exclusive=True, group="dashboard_composite")
    def _load_dashboard_composite(self, dashboard_id: str) -> None:
        try:
            query_results: Dict[str, Any] = {}
            if hasattr(self._engine, "get_dashboard"):
                detail = self._engine.get_dashboard(dashboard_id)
                if detail and hasattr(self._engine, "execute_dashboard_query"):
                    for chart in getattr(detail, "charts", []):
                        q_name = getattr(chart, "query_name", None) or (getattr(getattr(chart, "query", None), "name", None))
                        if q_name:
                            try:
                                q_res = self._engine.execute_dashboard_query(q_name)
                                query_results[q_name] = q_res
                                if hasattr(chart, "id") and chart.id:
                                    query_results[chart.id] = q_res
                            except Exception:
                                pass
            else:
                detail = None
            self.post_message(self.DashboardDetailLoaded(detail=detail, query_results=query_results))
        except Exception as exc:
            self.post_message(self.DashboardDetailFailed(error=str(exc), dashboard_id=dashboard_id))

    # --- message handlers (back on the UI thread) -------------------------

    def on_cases_loaded(self, msg: CasesLoaded) -> None:
        self._set_loading("#cases, #tile-cases-table", False)
        self._items_by_row.clear()
        for item in msg.items:
            row_key = str(getattr(item, "case_id", id(item)))
            self._items_by_row[row_key] = item
        for table in self.query("#cases, #tile-cases-table"):
            table.clear()
            if not table.columns:
                for col in render.CASE_LIST_COLUMNS:
                    table.add_column(col, key=col)
            for item in msg.items:
                row_key = str(getattr(item, "case_id", id(item)))
                table.add_row(*render.case_row(item), key=row_key)
        shown = len(msg.items)
        self._set_status(
            f"Cases: {shown} shown / {msg.total} total"
            + (f"  ·  query={msg.query!r}" if msg.query else "  ·  (no query)")
        )

    def on_cases_failed(self, msg: CasesFailed) -> None:
        self._set_loading("#cases, #tile-cases-table", False)
        for detail in self.query("#detail, #tile-case-detail-static"):
            detail.update(
                render.error_panel(msg.error, context=f"search_cases(query={msg.query!r})")
            )
        self._set_status("Case search failed — see detail pane.")

    def on_detail_loaded(self, msg: DetailLoaded) -> None:
        self._set_loading("#detail, #tile-case-detail-static", False)
        self._current_investigation = msg.investigation
        for detail in self.query("#detail, #tile-case-detail-static"):
            detail.update(render.case_detail(msg.investigation, active_subview=self._current_case_subview, subview_data=self._case_subview_data))
        cid = getattr(msg.investigation, "case_id", "?")
        self._set_status(f"Loaded case #{cid}. Inline views: [a] Alerts, [e] Pivot, [p] Playbook, [o] Overview, [c] Comment.")

    def on_detail_failed(self, msg: DetailFailed) -> None:
        self._set_loading("#detail, #tile-case-detail-static", False)
        self._current_investigation = None
        for detail in self.query("#detail, #tile-case-detail-static"):
            detail.update(
                render.error_panel(msg.error, context=f"investigate_case({msg.case_id})")
            )
        self._set_status(f"Investigate failed for #{msg.case_id}.")

    def on_alert_loaded(self, msg: AlertLoaded) -> None:
        self._set_loading("#detail, #tile-case-detail-static", False)
        self._current_case_subview = "alerts"
        self._case_subview_data = {"inv": msg.investigation, "playbook_run": msg.playbook_run}
        if self._current_investigation:
            for detail in self.query("#detail, #tile-case-detail-static"):
                detail.update(render.case_detail(self._current_investigation, active_subview="alerts", subview_data=self._case_subview_data))
        self._set_status(f"Inline Alert: {getattr(msg.investigation, 'display_name', '')} (Press 'o' for Overview)")

    def on_alert_failed(self, msg: AlertFailed) -> None:
        self._set_loading("#detail, #tile-case-detail-static", False)
        self.notify(f"Alert investigation failed: {msg.error}", severity="error")
        self._set_status(f"Alert investigation failed for {msg.alert_name}.")

    def on_entity_loaded(self, msg: EntityLoaded) -> None:
        self._set_loading("#detail, #tile-case-detail-static", False)
        self._current_case_subview = "entities"
        self._case_subview_data = msg.report
        if self._current_investigation:
            for detail in self.query("#detail, #tile-case-detail-static"):
                detail.update(render.case_detail(self._current_investigation, active_subview="entities", subview_data=self._case_subview_data))
        self._set_status(f"Inline Entity Pivot: {getattr(msg.report, 'indicator', '')} (Press 'o' for Overview)")

    def on_entity_failed(self, msg: EntityFailed) -> None:
        self._set_loading("#detail, #tile-case-detail-static", False)
        self.notify(f"Entity pivot failed: {msg.error}", severity="error")
        self._set_status(f"Entity pivot failed for {msg.indicator}.")

    def on_playbook_loaded(self, msg: PlaybookLoaded) -> None:
        self._set_loading("#detail, #tile-case-detail-static", False)
        self._current_case_subview = "playbook"
        self._case_subview_data = msg.run
        if self._current_investigation:
            for detail in self.query("#detail, #tile-case-detail-static"):
                detail.update(render.case_detail(self._current_investigation, active_subview="playbook", subview_data=self._case_subview_data))
        self._set_status(f"Inline Playbook: {getattr(msg.run, 'name', '')} (Press 'o' for Overview)")

    def on_playbook_failed(self, msg: PlaybookFailed) -> None:
        self._set_loading("#detail, #tile-case-detail-static", False)
        self.notify(f"Playbook fetch failed: {msg.error}", severity="error")
        self._set_status(f"Playbook fetch failed for alert {msg.alert_id}.")

    def on_comment_added(self, msg: CommentAdded) -> None:
        self._set_loading("#detail, #tile-case-detail-static", False)
        self.notify(f"Comment posted to Case #{msg.case_id}!", severity="information")
        self._set_status(f"Comment posted to Case #{msg.case_id}.")
        self._set_loading("#detail, #tile-case-detail-static", True)
        self._load_detail(msg.case_id)

    def on_comment_failed(self, msg: CommentFailed) -> None:
        self._set_loading("#detail, #tile-case-detail-static", False)
        self.notify(f"Failed to post comment: {msg.error}", severity="error")
        self._set_status(f"Comment post failed for Case #{msg.case_id}.")

    # --- UDM message handlers ---------------------------------------------

    def on_udm_events_loaded(self, msg: UDMEventsLoaded) -> None:
        self._set_loading("#udm-table, #tile-udm-table", False)
        self._udm_items_by_row.clear()
        for idx, event in enumerate(msg.events):
            row_key = f"udm-{idx}"
            self._udm_items_by_row[row_key] = event
        for table in self.query("#udm-table, #tile-udm-table"):
            table.clear()
            if not table.columns:
                for col in render.UDM_EVENT_COLUMNS:
                    table.add_column(col, key=col)
            for idx, event in enumerate(msg.events):
                row_key = f"udm-{idx}"
                table.add_row(*render.udm_event_row(event), key=row_key)
        shown = len(msg.events)
        self._set_status(
            f"UDM Events: {shown} events returned"
            + (f"  ·  query={msg.query!r}" if msg.query else "")
        )
        if msg.events:
            self._current_udm_row_key = "udm-0"
            for detail in self.query("#udm-detail, #tile-udm-detail-static"):
                detail.update(render.udm_event_detail(msg.events[0]))
            self._set_loading("#udm-raw-log, #tile-raw-log-static", True)
            self._load_raw_log(msg.events[0])

    def on_udm_events_failed(self, msg: UDMEventsFailed) -> None:
        self._set_loading("#udm-table, #tile-udm-table", False)
        for detail in self.query("#udm-detail, #tile-udm-detail-static"):
            detail.update(
                render.error_panel(msg.error, context=f"search_events(query={msg.query!r})")
            )
        self._set_status("UDM search failed — see detail pane.")

    def on_enriched_event_loaded(self, msg: EnrichedEventLoaded) -> None:
        self._set_loading("#udm-detail, #tile-udm-detail-static", False)
        for detail in self.query("#udm-detail, #tile-udm-detail-static"):
            detail.update(render.udm_enriched_event_detail(msg.investigation))
        self._set_status(f"Inline Enriched UDM Event: {msg.event_id}")

    def on_enriched_event_failed(self, msg: EnrichedEventFailed) -> None:
        self._set_loading("#udm-detail, #tile-udm-detail-static", False)
        self.notify(f"Enriched event inspection failed: {msg.error}", severity="error")
        self._set_status(f"Enriched event inspection failed for {msg.event_id}.")

    def on_raw_log_loaded(self, msg: RawLogLoaded) -> None:
        self._set_loading("#udm-raw-log, #tile-raw-log-static", False)
        self._set_status(f"Live Raw Log loaded for event: {msg.event_id}")
        for raw_view in self.query("#udm-raw-log, #tile-raw-log-static"):
            raw_view.update(render.raw_log_panel(msg.raw_log, event_id=msg.event_id))

    def on_raw_log_failed(self, msg: RawLogFailed) -> None:
        self._set_loading("#udm-raw-log, #tile-raw-log-static", False)
        self.notify(f"Raw log fetch failed: {msg.error}", severity="error")
        self._set_status(f"Raw log fetch failed for {msg.event_id}.")

    # --- Rules message handlers -------------------------------------------

    def on_rules_loaded(self, msg: RulesLoaded) -> None:
        self._set_loading("#rules-table, #tile-rules-table", False)
        self._rules_by_row.clear()
        for item in msg.items:
            row_key = str(getattr(item, "id", getattr(item, "title", id(item))))
            self._rules_by_row[row_key] = item
        for table in self.query("#rules-table, #tile-rules-table"):
            table.clear()
            if not table.columns:
                for col in render.RULE_COLUMNS:
                    table.add_column(col, key=col)
            for item in msg.items:
                row_key = str(getattr(item, "id", getattr(item, "title", id(item))))
                table.add_row(*render.rule_row(item), key=row_key)
        shown = len(msg.items)
        self._set_status(
            f"Curated Rules: {shown} shown / {msg.total} total"
            + (f"  ·  query={msg.query!r}" if msg.query else "")
        )

    def on_rules_failed(self, msg: RulesFailed) -> None:
        self._set_loading("#rules-table, #tile-rules-table", False)
        for detail in self.query("#rules-detail, #tile-rule-detail-static"):
            detail.update(
                render.error_panel(msg.error, context=f"search_curated_rulesets(q={msg.query!r})")
            )
        self._set_status("Curated rules search failed — see detail pane.")

    def on_rule_detail_loaded(self, msg: RuleDetailLoaded) -> None:
        self._set_loading("#rules-detail, #tile-rule-detail-static", False)
        if msg.detail:
            for detail in self.query("#rules-detail, #tile-rule-detail-static"):
                detail.update(render.ruleset_detail(msg.detail))
            title = getattr(getattr(msg.detail, "rule_set", msg.detail), "title", "")
            self._set_status(f"Loaded Curated Rule Set: {title}")

    def on_rule_detail_failed(self, msg: RuleDetailFailed) -> None:
        self._set_loading("#rules-detail, #tile-rule-detail-static", False)
        for detail in self.query("#rules-detail, #tile-rule-detail-static"):
            detail.update(
                render.error_panel(msg.error, context=f"get_curated_ruleset({msg.ruleset_id})")
            )
        self._set_status(f"Failed to load ruleset {msg.ruleset_id}.")

    # --- Playbooks message handlers ---------------------------------------

    def on_playbooks_loaded(self, msg: PlaybooksLoaded) -> None:
        self._set_loading("#playbooks-table, #tile-playbooks-table", False)
        self._playbooks_by_row.clear()
        for item in msg.items:
            row_key = str(getattr(item, "id", getattr(item, "identifier", id(item))))
            self._playbooks_by_row[row_key] = item
        for table in self.query("#playbooks-table, #tile-playbooks-table"):
            table.clear()
            if not table.columns:
                for col in render.PLAYBOOK_CATALOGUE_COLUMNS:
                    table.add_column(col, key=col)
            for item in msg.items:
                row_key = str(getattr(item, "id", getattr(item, "identifier", id(item))))
                table.add_row(*render.playbook_catalogue_row(item), key=row_key)
        shown = len(msg.items)
        self._set_status(
            f"Playbooks: {shown} shown / {msg.total} total"
            + (f"  ·  query={msg.query!r}" if msg.query else "")
        )

    def on_playbooks_failed(self, msg: PlaybooksFailed) -> None:
        self._set_loading("#playbooks-table, #tile-playbooks-table", False)
        for detail in self.query("#playbooks-detail, #tile-playbook-detail-static"):
            detail.update(
                render.error_panel(msg.error, context=f"search_playbooks(query={msg.query!r})")
            )
        self._set_status("Playbooks search failed — see detail pane.")

    def on_playbook_detail_loaded(self, msg: PlaybookDetailLoaded) -> None:
        self._set_loading("#playbooks-detail, #tile-playbook-detail-static", False)
        if msg.detail:
            for detail in self.query("#playbooks-detail, #tile-playbook-detail-static"):
                detail.update(render.playbook_detail_panel(msg.detail))
            name = getattr(msg.detail, "name", "")
            self._set_status(f"Loaded Playbook: {name}")

    def on_playbook_detail_failed(self, msg: PlaybookDetailFailed) -> None:
        self._set_loading("#playbooks-detail, #tile-playbook-detail-static", False)
        for detail in self.query("#playbooks-detail, #tile-playbook-detail-static"):
            detail.update(
                render.error_panel(msg.error, context=f"get_playbook({msg.playbook_id})")
            )
        self._set_status(f"Failed to load playbook {msg.playbook_id}.")

    # --- Dashboards message handlers --------------------------------------

    def on_dashboards_loaded(self, msg: DashboardsLoaded) -> None:
        self._set_loading("#dashboards-table, #tile-dashboards-table", False)
        self._dashboards_by_row.clear()
        for item in msg.items:
            row_key = str(getattr(item, "id", getattr(item, "name", id(item))))
            self._dashboards_by_row[row_key] = item
        for table in self.query("#dashboards-table, #tile-dashboards-table"):
            table.clear()
            if not table.columns:
                for col in render.DASHBOARD_COLUMNS:
                    table.add_column(col, key=col)
            for item in msg.items:
                row_key = str(getattr(item, "id", getattr(item, "name", id(item))))
                table.add_row(*render.dashboard_row(item), key=row_key)
        shown = len(msg.items)
        self._set_status(
            f"Dashboards: {shown} shown / {msg.total} total"
            + (f"  ·  query={msg.query!r}" if msg.query else "")
        )

    def on_dashboards_failed(self, msg: DashboardsFailed) -> None:
        self._set_loading("#dashboards-table, #tile-dashboards-table", False)
        for detail in self.query("#dashboards-detail, #tile-dashboard-detail-static"):
            detail.update(
                render.error_panel(msg.error, context=f"search_dashboards(query={msg.query!r})")
            )
        self._set_status("Dashboards search failed — see detail pane.")

    def on_dashboard_detail_loaded(self, msg: DashboardDetailLoaded) -> None:
        self._set_loading("#dashboards-detail, #tile-dashboard-detail-static", False)
        self._current_dashboard_detail = msg.detail
        self._dashboard_query_results = msg.query_results
        if msg.detail:
            for detail in self.query("#dashboards-detail, #tile-dashboard-detail-static"):
                detail.update(render.dashboard_detail_panel(msg.detail, query_results=msg.query_results))
            name = getattr(getattr(msg.detail, "summary", msg.detail), "display_name", "")
            self._set_status(f"Loaded Dashboard: {name}")

    def on_dashboard_detail_failed(self, msg: DashboardDetailFailed) -> None:
        self._set_loading("#dashboards-detail, #tile-dashboard-detail-static", False)
        for detail in self.query("#dashboards-detail, #tile-dashboard-detail-static"):
            detail.update(
                render.error_panel(msg.error, context=f"get_dashboard({msg.dashboard_id})")
            )
        self._set_status(f"Failed to load dashboard {msg.dashboard_id}.")


