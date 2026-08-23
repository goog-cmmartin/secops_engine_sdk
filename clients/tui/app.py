"""Two-pane Textual TUI: case search list -> case investigation detail.

Layout (tiling-WM friendly, composed in TCSS):

    +----------------------+---------------------------------+
    |  search input        |                                 |
    +----------------------+   detail pane                   |
    |  cases DataTable     |   (CaseInvestigation render)    |
    |  (CaseSearchResult)  |                                 |
    +----------------------+---------------------------------+
    |  status / key hints                                    |
    +-------------------------------------------------------+

Invariant: NO facade call happens on the UI thread. Both the search and the
investigate calls are dispatched with ``@work(thread=True)`` and post their
results back as custom messages, which the message handlers apply to widgets.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, List, Optional

from rich.text import Text

from textual.app import App, ComposeResult
from textual.containers import Horizontal, Vertical
from textual.message import Message
from textual.widgets import DataTable, Footer, Header, Input, Static
from textual.worker import Worker  # noqa: F401  (imported for type clarity)
from textual import work

from . import render


# --- worker -> UI messages --------------------------------------------

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


class SecOpsTUI(App):
    """Proof-of-concept SecOps case triage TUI."""

    CasesLoaded = CasesLoaded
    CasesFailed = CasesFailed
    DetailLoaded = DetailLoaded
    DetailFailed = DetailFailed

    CSS = """
    Screen {
        layout: vertical;
    }

    #body {
        height: 1fr;
    }

    #left {
        width: 40%;
        border-right: solid $accent;
    }

    #search {
        dock: top;
        margin: 0 1;
    }

    #cases {
        height: 1fr;
    }

    #right {
        width: 1fr;
        padding: 0 1;
        overflow-y: auto;
    }

    #detail {
        height: auto;
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
        ("/", "focus_search", "Search"),
        ("r", "refresh", "Refresh"),
        ("q", "quit", "Quit"),
    ]

    def __init__(self, engine: Any, initial_query: str = "", page_size: int = 50):
        super().__init__()
        self._engine = engine
        self._initial_query = initial_query
        self._page_size = page_size
        self._items_by_row: dict = {}

    # --- layout ------------------------------------------------------------

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        with Horizontal(id="body"):
            with Vertical(id="left"):
                yield Input(placeholder="Case search (e.g. AlertName:..., Entity:<hash>)", id="search")
                yield DataTable(id="cases", cursor_type="row", zebra_stripes=True)
            with Vertical(id="right"):
                yield Static(Text("Select a case to investigate.", style="dim"), id="detail")
        yield Static("", id="status")
        yield Footer()

    def on_mount(self) -> None:
        table = self.query_one("#cases", DataTable)
        for col in render.CASE_LIST_COLUMNS:
            table.add_column(col, key=col)
        self.query_one("#search", Input).value = self._initial_query
        self._set_status("Loading cases…")
        self._load_cases(self._initial_query)

    # --- status helper -----------------------------------------------------

    def _set_status(self, text: str) -> None:
        self.query_one("#status", Static).update(text)

    # --- actions -----------------------------------------------------------

    def action_focus_search(self) -> None:
        self.query_one("#search", Input).focus()

    def action_refresh(self) -> None:
        self._set_status("Refreshing…")
        self._load_cases(self.query_one("#search", Input).value)

    def on_input_submitted(self, event: Input.Submitted) -> None:
        if event.input.id == "search":
            self._set_status(f"Searching: {event.value!r} …")
            self._load_cases(event.value)

    def on_data_table_row_selected(self, event: DataTable.RowSelected) -> None:
        item = self._items_by_row.get(event.row_key.value)
        if item is None:
            return
        case_id = getattr(item, "case_id", None)
        if not case_id:
            return
        self._set_status(f"Investigating case #{case_id} …")
        self.query_one("#detail", Static).update(Text(f"Loading case #{case_id} …", style="dim"))
        self._load_detail(str(case_id))

    # --- workers (ALL facade access happens here, off the UI thread) -------

    @work(thread=True, exclusive=True, group="search")
    def _load_cases(self, query: str) -> None:
        try:
            batch = self._engine.search_cases(query=query, page_size=self._page_size)
            items = list(getattr(batch, "items", getattr(batch, "results", batch if isinstance(batch, list) else [])) or [])
            total = int(getattr(batch, "total_count", len(items)))
            self.post_message(self.CasesLoaded(items=items, total=total, query=query))
        except Exception as exc:  # facade surfaces RuntimeError on API errors
            self.post_message(self.CasesFailed(error=str(exc), query=query))

    @work(thread=True, exclusive=True, group="detail")
    def _load_detail(self, case_id: str) -> None:
        try:
            inv = self._engine.investigate_case(case_id)
            self.post_message(self.DetailLoaded(investigation=inv))
        except Exception as exc:
            self.post_message(self.DetailFailed(error=str(exc), case_id=case_id))

    # --- message handlers (back on the UI thread) -------------------------

    def on_cases_loaded(self, msg: CasesLoaded) -> None:
        table = self.query_one("#cases", DataTable)
        table.clear()
        self._items_by_row.clear()
        for item in msg.items:
            row_key = str(getattr(item, "case_id", id(item)))
            table.add_row(*render.case_row(item), key=row_key)
            self._items_by_row[row_key] = item
        shown = len(msg.items)
        self._set_status(
            f"{shown} shown / {msg.total} total"
            + (f"  ·  query={msg.query!r}" if msg.query else "  ·  (no query)")
        )

    def on_cases_failed(self, msg: CasesFailed) -> None:
        self.query_one("#detail", Static).update(
            render.error_panel(msg.error, context=f"search_cases(query={msg.query!r})")
        )
        self._set_status("Search failed — see detail pane.")

    def on_detail_loaded(self, msg: DetailLoaded) -> None:
        self.query_one("#detail", Static).update(render.case_detail(msg.investigation))
        cid = getattr(msg.investigation, "case_id", "?")
        self._set_status(f"Loaded case #{cid}.")

    def on_detail_failed(self, msg: DetailFailed) -> None:
        self.query_one("#detail", Static).update(
            render.error_panel(msg.error, context=f"investigate_case({msg.case_id})")
        )
        self._set_status(f"Investigate failed for #{msg.case_id}.")
