"""Case Triage & Alert Investigation Workspace View.

Provides a dual-pane layout:
- Left: Case search & list (DataTable)
- Right: Case Overview (Header, Alerts Table, Entities, Comments) with
  hierarchical drill-down into individual Alert Investigations.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from rich.text import Text
from rich.panel import Panel
from rich.console import Group
from textual import work
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Container, Horizontal, Vertical, VerticalScroll
from textual.message import Message
from textual.widgets import ContentSwitcher, DataTable, Input, Static

from .. import render


# --- Worker Messages -----------------------------------------------------

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
class CaseDetailLoaded(Message):
    investigation: Any


@dataclass
class CaseDetailFailed(Message):
    error: str
    case_id: str


@dataclass
class AlertDetailLoaded(Message):
    investigation: Any


@dataclass
class AlertDetailFailed(Message):
    error: str
    alert_name: str


class CaseWorkspaceView(Container):
    """Self-contained workspace view for Case Triage and Alert Deep-Dive."""

    DEFAULT_CSS = """
    CaseWorkspaceView {
        layout: horizontal;
        height: 1fr;
    }

    #left_pane {
        width: 38%;
        min-width: 45;
        border-right: solid $accent;
        height: 1fr;
    }

    #search_input {
        dock: top;
        margin: 0 1;
    }

    #cases_table {
        height: 1fr;
    }

    #right_pane {
        width: 1fr;
        height: 1fr;
    }

    #case_content_switcher {
        height: 1fr;
    }

    #case_overview_pane {
        height: 1fr;
        padding: 0 1;
    }

    #case_header_card {
        height: auto;
        margin-bottom: 1;
    }

    #alerts_section_header {
        height: 1;
        color: $accent;
        text-style: bold;
        margin-top: 1;
    }

    #alerts_table {
        height: 12;
        min-height: 8;
        border: round $primary;
        margin-bottom: 1;
    }

    #case_entities_comments {
        height: auto;
    }

    #alert_drilldown_pane {
        height: 1fr;
        padding: 0 1;
    }

    #alert_back_bar {
        height: 1;
        background: $accent;
        color: $text;
        text-style: bold;
        padding: 0 1;
        margin-bottom: 1;
    }

    #alert_detail_content {
        height: auto;
    }
    """

    BINDINGS = [
        Binding("b", "back_to_case", "Back to Case", show=False),
        Binding("escape", "back_to_case", "Back to Case", show=False),
    ]

    def __init__(
        self,
        engine: Any,
        initial_query: str = "",
        page_size: int = 50,
        id: Optional[str] = None,
    ) -> None:
        super().__init__(id=id)
        self._engine = engine
        self._initial_query = initial_query
        self._page_size = page_size
        self._items_by_row: Dict[str, Any] = {}
        self._alerts_by_row: Dict[str, Any] = {}
        self._current_investigation: Optional[Any] = None
        self._current_alert_investigation: Optional[Any] = None

    def compose(self) -> ComposeResult:
        with Horizontal(id="workspace_body"):
            with Vertical(id="left_pane"):
                yield Input(
                    placeholder="Search cases (e.g. AlertName:..., 'phishing', 'amartin')…",
                    id="search_input",
                )
                yield DataTable(id="cases_table", cursor_type="row", zebra_stripes=True)

            with Vertical(id="right_pane"):
                with ContentSwitcher(initial="case_overview_pane", id="case_content_switcher"):
                    with VerticalScroll(id="case_overview_pane"):
                        yield Static(Text("Select a case from the left table to investigate.", style="dim"), id="case_header_card")
                        yield Static("⚡ Associated Alerts (Press Enter to inspect)", id="alerts_section_header")
                        yield DataTable(id="alerts_table", cursor_type="row", zebra_stripes=True)
                        yield Static("", id="case_entities_comments")

                    with VerticalScroll(id="alert_drilldown_pane"):
                        yield Static("⬅ [Esc / b] Return to Case Overview", id="alert_back_bar", markup=False)
                        yield Static(Text("Loading alert deep-dive…", style="dim"), id="alert_detail_content")

    def on_mount(self) -> None:
        cases_tbl = self.query_one("#cases_table", DataTable)
        for col in render.CASE_LIST_COLUMNS:
            cases_tbl.add_column(col, key=col)

        alerts_tbl = self.query_one("#alerts_table", DataTable)
        for col in render.ALERT_LIST_COLUMNS:
            alerts_tbl.add_column(col, key=col)

        self.query_one("#search_input", Input).value = self._initial_query
        self.load_cases(self._initial_query)

    # --- Public Control Methods -------------------------------------------

    def focus_search(self) -> None:
        self.query_one("#search_input", Input).focus()

    def set_query(self, query: str) -> None:
        inp = self.query_one("#search_input", Input)
        inp.value = query
        self.load_cases(query)

    def refresh_view(self) -> None:
        q = self.query_one("#search_input", Input).value
        self.load_cases(q)

    # --- Event Handlers ---------------------------------------------------

    def on_input_submitted(self, event: Input.Submitted) -> None:
        if event.input.id == "search_input":
            self.load_cases(event.value)

    def on_data_table_row_selected(self, event: DataTable.RowSelected) -> None:
        if event.data_table.id == "cases_table":
            item = self._items_by_row.get(event.row_key.value)
            if item is None:
                return
            case_id = getattr(item, "case_id", None)
            if not case_id:
                return
            self._show_case_overview()
            self.query_one("#case_header_card", Static).update(
                Text(f"Loading Case #{case_id} investigation details…", style="dim cyan")
            )
            self._load_case_detail(str(case_id))

        elif event.data_table.id == "alerts_table":
            alert_item = self._alerts_by_row.get(event.row_key.value)
            if alert_item is None:
                return
            alert_identifier = (
                getattr(alert_item, "name", None)
                or getattr(alert_item, "identifier", None)
                or getattr(alert_item, "alert_id", None)
                or ""
            )
            if not alert_identifier:
                return
            self._show_alert_drilldown()
            self.query_one("#alert_detail_content", Static).update(
                Text(f"Loading Alert investigation: {alert_identifier}…", style="dim magenta")
            )
            self._load_alert_detail(str(alert_identifier), alert_item)

    def action_back_to_case(self) -> None:
        self._show_case_overview()

    def _show_case_overview(self) -> None:
        switcher = self.query_one("#case_content_switcher", ContentSwitcher)
        switcher.current = "case_overview_pane"

    def _show_alert_drilldown(self) -> None:
        switcher = self.query_one("#case_content_switcher", ContentSwitcher)
        switcher.current = "alert_drilldown_pane"

    # --- Background Workers -----------------------------------------------

    def load_cases(self, query: str) -> None:
        self._load_cases_worker(query)

    @work(thread=True, exclusive=True, group="workspace_search")
    def _load_cases_worker(self, query: str) -> None:
        try:
            batch = self._engine.search_cases(query=query, page_size=self._page_size)
            items = list(getattr(batch, "items", getattr(batch, "results", batch if isinstance(batch, list) else [])) or [])
            total = int(getattr(batch, "total_count", len(items)))
            self.post_message(CasesLoaded(items=items, total=total, query=query))
        except Exception as exc:
            self.post_message(CasesFailed(error=str(exc), query=query))

    @work(thread=True, exclusive=True, group="workspace_case_detail")
    def _load_case_detail(self, case_id: str) -> None:
        try:
            inv = self._engine.investigate_case(case_id)
            self.post_message(CaseDetailLoaded(investigation=inv))
        except Exception as exc:
            self.post_message(CaseDetailFailed(error=str(exc), case_id=case_id))

    @work(thread=True, exclusive=True, group="workspace_alert_detail")
    def _load_alert_detail(self, alert_name: str, fallback_summary: Optional[Any] = None) -> None:
        try:
            # Check if engine supports investigate_alert
            if hasattr(self._engine, "investigate_alert"):
                alert_inv = self._engine.investigate_alert(alert_name)
                self.post_message(AlertDetailLoaded(investigation=alert_inv))
            else:
                # Synthesize detail from CaseAlertSummary if direct alert deep-dive is unavailable
                from engine.domain import AlertInvestigation
                alert_inv = AlertInvestigation(
                    alert_name=alert_name,
                    case_id=getattr(self._current_investigation, "case_id", ""),
                    display_name=getattr(fallback_summary, "display_name", alert_name) if fallback_summary else alert_name,
                    priority=getattr(fallback_summary, "priority", "UNKNOWN") if fallback_summary else "UNKNOWN",
                    status=getattr(fallback_summary, "status", "UNKNOWN") if fallback_summary else "UNKNOWN",
                    rule_name=getattr(fallback_summary, "rule_name", None) if fallback_summary else None,
                    rule_id=None,
                    risk_score=None,
                    detection_time=getattr(fallback_summary, "start_time", None) if fallback_summary else None,
                    product=getattr(fallback_summary, "product", None) if fallback_summary else None,
                    vendor=getattr(fallback_summary, "vendor", None) if fallback_summary else None,
                    event_count=getattr(fallback_summary, "event_count", 0) if fallback_summary else 0,
                )
                self.post_message(AlertDetailLoaded(investigation=alert_inv))
        except Exception as exc:
            self.post_message(AlertDetailFailed(error=str(exc), alert_name=alert_name))

    # --- UI Message Handlers ----------------------------------------------

    def on_cases_loaded(self, msg: CasesLoaded) -> None:
        table = self.query_one("#cases_table", DataTable)
        table.clear()
        self._items_by_row.clear()
        for item in msg.items:
            row_key = str(getattr(item, "case_id", id(item)))
            table.add_row(*render.case_row(item), key=row_key)
            self._items_by_row[row_key] = item

    def on_cases_failed(self, msg: CasesFailed) -> None:
        self.query_one("#case_header_card", Static).update(
            render.error_panel(msg.error, context=f"search_cases(query={msg.query!r})")
        )

    def on_case_detail_loaded(self, msg: CaseDetailLoaded) -> None:
        inv = msg.investigation
        self._current_investigation = inv
        self.query_one("#case_header_card", Static).update(render.case_summary_card(inv))

        # Fill Alerts DataTable
        alerts_table = self.query_one("#alerts_table", DataTable)
        alerts_table.clear()
        self._alerts_by_row.clear()

        alerts = getattr(inv, "alerts", []) or []
        count_str = f"({len(alerts)} alerts)" if alerts else "(0 alerts)"
        self.query_one("#alerts_section_header", Static).update(
            f"⚡ Associated Alerts {count_str} — [dim]Press Enter / click to inspect[/dim]"
        )

        for i, a in enumerate(alerts):
            row_key = str(getattr(a, "name", None) or getattr(a, "identifier", None) or f"alert_{i}")
            alerts_table.add_row(*render.alert_row(a), key=row_key)
            self._alerts_by_row[row_key] = a

        # Render Entities and Comments
        entities = getattr(inv, "entities", []) or []
        comments = getattr(inv, "comments", []) or []
        lower_group = Group(
            render._entities_table(entities),
            render.case_comments_panel(comments),
        )
        self.query_one("#case_entities_comments", Static).update(lower_group)

    def on_case_detail_failed(self, msg: CaseDetailFailed) -> None:
        self.query_one("#case_header_card", Static).update(
            render.error_panel(msg.error, context=f"investigate_case({msg.case_id})")
        )

    def on_alert_detail_loaded(self, msg: AlertDetailLoaded) -> None:
        self._current_alert_investigation = msg.investigation
        self.query_one("#alert_detail_content", Static).update(
            render.alert_detail_panel(msg.investigation)
        )

    def on_alert_detail_failed(self, msg: AlertDetailFailed) -> None:
        self.query_one("#alert_detail_content", Static).update(
            render.error_panel(msg.error, context=f"investigate_alert({msg.alert_name})")
        )
