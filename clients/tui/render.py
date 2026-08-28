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

_PLAYBOOK_STYLE = {
    "COMPLETED": "green",
    "SUCCESS": "green",
    "RUNNING": "bold yellow",
    "IN_PROGRESS": "bold yellow",
    "FAILED": "bold red",
    "ERROR": "bold red",
    "PENDING": "cyan",
    "SKIPPED": "dim",
}


def _enum_name(value: Any) -> str:
    """Return the ``.name`` of an enum, or a best-effort string otherwise."""
    return getattr(value, "name", str(value) if value is not None else "")


def priority_text(value: Any) -> Text:
    name = _enum_name(value).upper() if value is not None else "UNKNOWN"
    return Text(name or "UNKNOWN", style=_PRIORITY_STYLE.get(name, "dim"))


def status_text(value: Any) -> Text:
    name = _enum_name(value).upper() if value is not None else "UNKNOWN"
    return Text(name or "UNKNOWN", style=_STATUS_STYLE.get(name, "dim"))


def playbook_status_text(name: Optional[str], status: Optional[str] = None) -> Text:
    if not name:
        return Text("-", style="dim")
    st = (status or "").upper()
    style = _PLAYBOOK_STYLE.get(st, "cyan")
    if status:
        return Text(f"{name} [{status}]", style=style)
    return Text(name, style="cyan")


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


# --- alert list columns & row mapping ------------------------------------

ALERT_LIST_COLUMNS = ("Priority", "Alert ID / Name", "Status", "Product", "Rule", "Events", "Playbook")


def alert_row(item: Any) -> List[Any]:
    """Map a ``CaseAlertSummary`` to an alerts DataTable row."""
    pr = getattr(item, "priority", "UNKNOWN")
    display_name = (
        getattr(item, "display_name", "")
        or getattr(item, "identifier", "")
        or getattr(item, "name", "")
        or "-"
    )
    product = getattr(item, "product", None) or getattr(item, "vendor", None) or "-"
    rule_name = getattr(item, "rule_name", None) or "-"
    event_count = getattr(item, "event_count", 0)
    playbook_name = getattr(item, "attached_playbook_name", None)
    playbook_status = getattr(item, "playbook_status", None)

    return [
        priority_text(pr),
        display_name,
        status_text(getattr(item, "status", None)),
        str(product),
        str(rule_name),
        str(event_count),
        playbook_status_text(playbook_name, playbook_status),
    ]


# --- case investigation detail --------------------------------------------

def _kv_table(pairs: List[tuple]) -> Table:
    t = Table.grid(padding=(0, 2))
    t.add_column(justify="right", style="bold cyan", no_wrap=True)
    t.add_column()
    for k, v in pairs:
        t.add_row(k, v if isinstance(v, Text) else str(v))
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


def case_summary_card(inv: Any) -> Panel:
    """Render top summary card for a case."""
    header = _kv_table([
        ("Case", f"{getattr(inv, 'display_name', '')}  (#{getattr(inv, 'case_id', '')})"),
        ("Status", status_text(getattr(inv, "status", None))),
        ("Priority", priority_text(getattr(inv, "priority", None))),
        ("Stage", getattr(inv, "stage", "") or "-"),
        ("Assignee", getattr(inv, "assignee", None) or "-"),
        ("Alerts", str(getattr(inv, "alert_count", len(getattr(inv, "alerts", []))))),
        ("Created", _fmt_time(getattr(inv, "create_time", None))),
        ("Updated", _fmt_time(getattr(inv, "update_time", None))),
    ])
    return Panel(header, title="Case Overview", border_style="cyan")


def case_comments_panel(comments: List[Any]) -> Panel:
    comment_lines = []
    for c in comments[:8]:
        txt = getattr(c, "comment", None) or getattr(c, "text", None) or str(c)
        who = getattr(c, "user", None) or getattr(c, "author", None) or "?"
        time_str = _fmt_time(getattr(c, "create_time", None))
        comment_lines.append(Text(f"• [{who} @ {time_str}] {txt}", style="dim"))
    comments_block = Group(*comment_lines) if comment_lines else Text("(no comments)", style="dim")
    return Panel(comments_block, title=f"Case Comments ({len(comments)})", border_style="grey37")


def case_detail(inv: Any) -> Group:
    """Render a ``CaseInvestigation`` into a stacked Rich renderable group."""
    comments = getattr(inv, "comments", []) or []
    return Group(
        case_summary_card(inv),
        _entities_table(getattr(inv, "entities", []) or []),
        case_comments_panel(comments),
    )


def alert_detail_panel(inv: Any) -> Group:
    """Render full deep-dive view for an ``AlertInvestigation``."""
    risk = getattr(inv, "risk_score", None)
    risk_text = Text(str(risk), style="bold red" if risk and risk >= 70 else "yellow" if risk else "dim")

    info_pairs = [
        ("Alert", getattr(inv, "display_name", "") or getattr(inv, "alert_name", "")),
        ("Case ID", f"#{getattr(inv, 'case_id', '-')}") ,
        ("Priority", priority_text(getattr(inv, "priority", "UNKNOWN"))),
        ("Status", status_text(getattr(inv, "status", "UNKNOWN"))),
        ("Rule Name", getattr(inv, "rule_name", None) or "-"),
        ("Rule ID", getattr(inv, "rule_id", None) or "-"),
        ("Risk Score", risk_text),
        ("Product / Vendor", f"{getattr(inv, 'product', '-') or '-'} / {getattr(inv, 'vendor', '-') or '-'}"),
        ("Events Count", str(getattr(inv, "event_count", 0))),
        ("Detected Time", _fmt_time(getattr(inv, "detection_time", None))),
    ]
    meta_table = _kv_table(info_pairs)
    meta_panel = Panel(meta_table, title="Alert Investigation Deep-Dive", border_style="magenta")

    entities = getattr(inv, "entities", []) or []
    entities_table = _entities_table(entities)

    events = getattr(inv, "associated_events", []) or []
    event_lines = []
    for ev in events[:5]:
        event_lines.append(Text(f"• {str(ev)}", style="dim"))
    events_block = Group(*event_lines) if event_lines else Text("(no raw events attached)", style="dim")
    events_panel = Panel(events_block, title=f"Associated Events ({len(events)})", border_style="grey37")

    return Group(meta_panel, entities_table, events_panel)


def error_panel(message: str, context: Optional[str] = None) -> Panel:
    body = Text(message, style="bold red")
    if context:
        body = Group(body, Text(context, style="dim"))
    return Panel(body, title="Error", border_style="red")
