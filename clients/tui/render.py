"""Pure rendering helpers: SDK domain dataclasses -> Rich renderables.

Kept deliberately free of any Textual imports so this module can be reused by a
stateless CLI (option A) as well as the TUI. Everything here is synchronous and
side-effect free.
"""
from __future__ import annotations

from typing import Any, List, Optional

from rich.table import Table
from rich.text import Text
from rich.panel import Panel
from rich.console import Group


# --- priority / status colour mapping -------------------------------------

_PRIORITY_STYLE = {
    "CRITICAL": "bold white on red",
    "HIGH": "bold red",
    "MEDIUM": "yellow",
    "LOW": "green",
    "UNKNOWN": "dim",
}

_STATUS_STYLE = {
    "OPEN": "bold green",
    "CLOSED": "dim",
    "UNKNOWN": "dim",
}


def _enum_name(value: Any) -> str:
    """Return the ``.name`` of an enum, or a best-effort string otherwise."""
    return getattr(value, "name", str(value) if value is not None else "")


def priority_text(value: Any) -> Text:
    name = _enum_name(value) or "UNKNOWN"
    return Text(name, style=_PRIORITY_STYLE.get(name, "dim"))


def status_text(value: Any) -> Text:
    name = _enum_name(value) or "UNKNOWN"
    return Text(name, style=_STATUS_STYLE.get(name, "dim"))


def _fmt_time(dt: Any) -> str:
    if dt is None:
        return "-"
    try:
        return dt.strftime("%Y-%m-%d %H:%M")
    except Exception:
        return str(dt)


# --- case search results (list pane feeds a DataTable via these rows) ------

CASE_LIST_COLUMNS = ("ID", "Priority", "Title", "Stage", "Alerts", "Assignee", "Created")


def case_row(item: Any) -> List[Any]:
    """Map a ``CaseSearchResultItem`` to a DataTable row (order matches columns).

    Returns Rich ``Text``/``str`` cells; DataTable accepts both.
    """
    flags = ""
    if getattr(item, "is_incident", False):
        flags += "!"
    if getattr(item, "is_important", False):
        flags += "*"
    title = getattr(item, "title", "") or "(untitled)"
    if flags:
        title = f"{flags} {title}"

    return [
        str(getattr(item, "case_id", "")),
        priority_text(getattr(item, "priority", None)),
        title,
        getattr(item, "stage", "") or "-",
        str(getattr(item, "alerts_count", 0)),
        getattr(item, "user_assigned", None) or "-",
        _fmt_time(getattr(item, "create_time", None)),
    ]


# --- case investigation detail --------------------------------------------

def _kv_table(pairs: List[tuple]) -> Table:
    t = Table.grid(padding=(0, 2))
    t.add_column(justify="right", style="bold cyan", no_wrap=True)
    t.add_column()
    for k, v in pairs:
        t.add_row(k, v if isinstance(v, Text) else str(v))
    return t


def _alerts_table(alerts: List[Any]) -> Table:
    t = Table(title="Alerts", expand=True, title_style="bold", show_lines=False)
    t.add_column("Priority", no_wrap=True)
    t.add_column("Name")
    t.add_column("Status", no_wrap=True)
    t.add_column("Product", no_wrap=True)
    t.add_column("Events", justify="right", no_wrap=True)
    t.add_column("Playbook")
    if not alerts:
        t.add_row(Text("(no alerts)", style="dim"), "", "", "", "", "")
        return t
    for a in alerts:
        pr = getattr(a, "priority", "") or "-"
        t.add_row(
            Text(str(pr), style=_PRIORITY_STYLE.get(str(pr).upper(), "")),
            getattr(a, "display_name", "") or getattr(a, "identifier", "") or "-",
            getattr(a, "status", "") or "-",
            getattr(a, "product", None) or "-",
            str(getattr(a, "event_count", 0)),
            getattr(a, "attached_playbook_name", None) or "-",
        )
    return t


def _entities_table(entities: List[Any]) -> Table:
    t = Table(title="Involved Entities", expand=True, title_style="bold")
    t.add_column("Type", no_wrap=True)
    t.add_column("Identifier")
    t.add_column("Role", no_wrap=True)
    t.add_column("Susp.", no_wrap=True)
    if not entities:
        t.add_row(Text("(none)", style="dim"), "", "", "")
        return t
    for e in entities:
        susp = getattr(e, "is_suspicious", False)
        t.add_row(
            getattr(e, "entity_type", None) or "-",
            getattr(e, "display_name", "") or getattr(e, "identifier", "") or "-",
            getattr(e, "role", None) or "-",
            Text("YES", style="bold red") if susp else Text("no", style="dim"),
        )
    return t


def case_detail(inv: Any) -> Group:
    """Render a ``CaseInvestigation`` into a stacked Rich renderable group."""
    header = _kv_table([
        ("Case", f"{getattr(inv, 'display_name', '')}  (#{getattr(inv, 'case_id', '')})"),
        ("Status", status_text(getattr(inv, "status", None))),
        ("Priority", priority_text(getattr(inv, "priority", None))),
        ("Stage", getattr(inv, "stage", "") or "-"),
        ("Assignee", getattr(inv, "assignee", None) or "-"),
        ("Alerts", str(getattr(inv, "alert_count", 0))),
        ("Created", _fmt_time(getattr(inv, "create_time", None))),
        ("Updated", _fmt_time(getattr(inv, "update_time", None))),
    ])

    comments = getattr(inv, "comments", []) or []
    comment_lines = []
    for c in comments[:5]:
        txt = getattr(c, "comment", None) or getattr(c, "text", None) or str(c)
        who = getattr(c, "user", None) or getattr(c, "author", None) or "?"
        comment_lines.append(Text(f"• [{who}] {txt}", style="dim"))
    comments_block = Group(*comment_lines) if comment_lines else Text("(no comments)", style="dim")

    return Group(
        Panel(header, title="Case Detail", border_style="cyan"),
        _alerts_table(getattr(inv, "alerts", []) or []),
        _entities_table(getattr(inv, "entities", []) or []),
        Panel(comments_block, title=f"Comments ({len(comments)})", border_style="grey37"),
    )


def error_panel(message: str, context: Optional[str] = None) -> Panel:
    body = Text(message, style="bold red")
    if context:
        body = Group(body, Text(context, style="dim"))
    return Panel(body, title="Error", border_style="red")
