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
    """Render comments panel for a case."""
    comment_lines = []
    for c in comments[:8]:
        txt = getattr(c, "comment", None) or getattr(c, "text", None) or str(c)
        who = getattr(c, "user", None) or getattr(c, "author", None) or "?"
        time_str = _fmt_time(getattr(c, "create_time", None))
        comment_lines.append(Text(f"• [{who} @ {time_str}] {txt}", style="dim"))
    comments_block = Group(*comment_lines) if comment_lines else Text("(no comments)", style="dim")
    return Panel(comments_block, title=f"Case Comments ({len(comments)})", border_style="grey37")


def case_subnav_bar(active_subview: str = "overview") -> Text:
    res = Text()
    tabs = [
        ("overview", "o", "Overview"),
        ("alerts", "a", "Alerts"),
        ("entities", "e", "Entities"),
        ("playbook", "p", "Playbook DAG"),
        ("comment", "c", "+ Comment"),
    ]
    for key, shortcut, label in tabs:
        if key == active_subview:
            res.append(f" [{shortcut}: {label}] ", style="bold black on cyan")
        else:
            res.append(f" [{shortcut}: {label}] ", style="dim")
        res.append(" ")
    return res


def case_detail(
    inv: Any,
    active_subview: str = "overview",
    subview_data: Optional[Any] = None,
) -> Group:
    """Render a ``CaseInvestigation`` into a stacked Rich renderable group."""
    nav = case_subnav_bar(active_subview)

    if active_subview == "alerts" and subview_data is not None:
        inv_obj = subview_data.get("inv") if isinstance(subview_data, dict) else subview_data
        pb_obj = subview_data.get("playbook_run") if isinstance(subview_data, dict) else None
        return Group(nav, alert_detail(inv_obj, pb_obj))
    elif active_subview == "entities" and subview_data is not None:
        return Group(nav, entity_investigation_detail(subview_data))
    elif active_subview == "playbook" and subview_data is not None:
        return Group(nav, playbook_run_detail(subview_data))

    comments = getattr(inv, "comments", []) or []
    return Group(
        nav,
        case_summary_card(inv),
        _alerts_table(getattr(inv, "alerts", []) or []),
        _entities_table(getattr(inv, "entities", []) or []),
        case_comments_panel(comments),
    )


# --- alert investigation detail -------------------------------------------

def _events_table(events: List[Dict[str, Any]]) -> Table:
    t = Table(title="Associated Events", expand=True, title_style="bold", show_lines=False)
    t.add_column("Event Type", no_wrap=True)
    t.add_column("Timestamp", no_wrap=True)
    t.add_column("Log Type", no_wrap=True)
    t.add_column("Principal / Target")
    if not events:
        t.add_row(Text("(no associated events)", style="dim"), "", "", "")
        return t
    for ev in events[:15]:
        event_type = ev.get("metadata", {}).get("eventType") or ev.get("metadata", {}).get("event_type") or ev.get("eventType") or "-"
        ts = ev.get("metadata", {}).get("eventTimestamp") or ev.get("metadata", {}).get("event_timestamp") or "-"
        log_type = ev.get("metadata", {}).get("logType") or ev.get("metadata", {}).get("log_type") or "-"
        principal = ev.get("principal", {}).get("hostname") or ev.get("principal", {}).get("ip") or ev.get("principal", {}).get("user", {}).get("userid") or ""
        target = ev.get("target", {}).get("hostname") or ev.get("target", {}).get("ip") or ev.get("target", {}).get("file", {}).get("fullPath") or ""
        endpoint_info = f"{principal} -> {target}" if principal and target else (principal or target or "-")
        t.add_row(str(event_type), str(ts), str(log_type), str(endpoint_info))
    return t


def _playbook_steps_table(steps: List[Any]) -> Table:
    t = Table(title="Playbook Executed Steps", expand=True, title_style="bold", show_lines=False)
    t.add_column("#", justify="right", no_wrap=True)
    t.add_column("Step Name")
    t.add_column("Action / Block", no_wrap=True)
    t.add_column("Status", no_wrap=True)
    t.add_column("Duration", no_wrap=True)
    if not steps:
        t.add_row(Text("(no executed steps)", style="dim"), "", "", "", "")
        return t
    for idx, s in enumerate(steps, 1):
        status = getattr(s, "status", None) or getattr(s, "execution_status", "UNKNOWN")
        status_str = str(status)
        style = "bold green" if "complete" in status_str.lower() or "success" in status_str.lower() else ("bold red" if "fail" in status_str.lower() or "error" in status_str.lower() else "yellow")
        dur = f"{getattr(s, 'duration_seconds', 0):.1f}s" if getattr(s, "duration_seconds", None) is not None else "-"
        t.add_row(
            str(idx),
            getattr(s, "display_name", None) or getattr(s, "name", "-"),
            getattr(s, "action_name", None) or getattr(s, "block_name", "-"),
            Text(status_str, style=style),
            dur,
        )
    return t


def alert_detail(inv: Any, playbook_run: Optional[Any] = None) -> Group:
    """Render an ``AlertInvestigation`` into a stacked Rich renderable group."""
    rule = getattr(inv, "rule_name", None) or getattr(inv, "rule_id", None) or "-"
    risk = getattr(inv, "risk_score", None)
    risk_text = Text(str(risk), style="bold red" if (isinstance(risk, int) and risk >= 70) else "yellow") if risk is not None else Text("-", style="dim")

    header = _kv_table([
        ("Alert Name", f"{getattr(inv, 'display_name', '') or getattr(inv, 'alert_name', '')}"),
        ("Case ID", str(getattr(inv, "case_id", "-"))),
        ("Status", status_text(getattr(inv, "status", None))),
        ("Priority", priority_text(getattr(inv, "priority", None))),
        ("Rule", str(rule)),
        ("Risk Score", risk_text),
        ("Product / Vendor", f"{getattr(inv, 'product', '-') or '-'} / {getattr(inv, 'vendor', '-') or '-'}"),
        ("Events Count", str(getattr(inv, "event_count", 0))),
        ("Detection Time", _fmt_time(getattr(inv, "detection_time", None))),
    ])

    sections = [
        Panel(header, title="Alert Investigation", border_style="cyan"),
        _entities_table(getattr(inv, "entities", []) or []),
        _events_table(getattr(inv, "associated_events", []) or []),
    ]

    if playbook_run is not None:
        steps = getattr(playbook_run, "steps", []) or []
        if hasattr(playbook_run, "executed_path"):
            try:
                steps = playbook_run.executed_path()
            except Exception:
                pass
        sections.append(_playbook_steps_table(steps))

    return Group(*sections)


# --- entity investigation detail ------------------------------------------

def _iocs_table(iocs: List[Any]) -> Table:
    t = Table(title="Enterprise IoC Intelligence Matches", expand=True, title_style="bold", show_lines=False)
    t.add_column("Indicator", no_wrap=True)
    t.add_column("Sources")
    t.add_column("Categories")
    t.add_column("First Seen", no_wrap=True)
    t.add_column("Last Seen", no_wrap=True)
    if not iocs:
        t.add_row(Text("(no active IoC matches)", style="dim"), "", "", "", "")
        return t
    for match in iocs[:10]:
        ind = getattr(match, "artifact_indicator", {}).get("value") or "-"
        srcs = ", ".join(getattr(match, "sources", []) or []) or "-"
        cats = ", ".join(getattr(match, "categories", []) or []) or "-"
        t.add_row(
            str(ind),
            str(srcs),
            str(cats),
            _fmt_time(getattr(match, "first_seen", None)),
            _fmt_time(getattr(match, "last_seen", None)),
        )
    return t


def _related_cases_table(cases: List[Any]) -> Table:
    t = Table(title="Correlated SOAR Cases", expand=True, title_style="bold", show_lines=False)
    t.add_column("ID", no_wrap=True)
    t.add_column("Priority", no_wrap=True)
    t.add_column("Title")
    t.add_column("Stage", no_wrap=True)
    t.add_column("Assignee", no_wrap=True)
    t.add_column("Created", no_wrap=True)
    if not cases:
        t.add_row(Text("(no correlated cases)", style="dim"), "", "", "", "", "")
        return t
    for c in cases[:10]:
        t.add_row(
            str(getattr(c, "case_id", getattr(c, "id", ""))),
            priority_text(getattr(c, "priority", None)),
            str(getattr(c, "title", getattr(c, "display_name", "-"))),
            str(getattr(c, "stage", "-")),
            str(getattr(c, "user_assigned", getattr(c, "assignee", "-")) or "-"),
            _fmt_time(getattr(c, "create_time", None)),
        )
    return t


def entity_investigation_detail(report: Any) -> Group:
    """Render an ``EntityInvestigationReport`` into a stacked Rich renderable group."""
    header = _kv_table([
        ("Indicator", Text(str(getattr(report, "indicator", "-")), style="bold yellow")),
        ("Detected Type", Text(str(getattr(report, "detected_type", "-")), style="bold cyan")),
        ("Category", str(getattr(report, "category", "-"))),
        ("Entity Graph Events", str(getattr(report, "entity_graph_events_count", 0))),
        ("UDM Events Found", str(getattr(report, "udm_events_count", 0))),
        ("IoC Threat Matches", str(getattr(report, "enterprise_iocs_count", 0))),
        ("Related SOAR Cases", str(getattr(report, "related_cases_count", 0))),
    ])

    return Group(
        Panel(header, title="Entity Pivot Investigation", border_style="yellow"),
        _iocs_table(getattr(report, "ioc_matches", []) or []),
        _related_cases_table(getattr(report, "related_cases", []) or []),
    )


# --- playbook run detail --------------------------------------------------

def playbook_run_detail(run: Any) -> Group:
    """Render a ``PlaybookInstanceRun`` into a stacked Rich renderable group."""
    status = getattr(run, "status", None) or getattr(run, "execution_status", "UNKNOWN")
    status_str = str(status)
    style = "bold green" if "complete" in status_str.lower() or "success" in status_str.lower() else ("bold red" if "fail" in status_str.lower() else "yellow")

    header = _kv_table([
        ("Playbook", str(getattr(run, "display_name", getattr(run, "name", "-")))),
        ("Instance ID", str(getattr(run, "identifier", getattr(run, "instance_id", "-")))),
        ("Status", Text(status_str, style=style)),
        ("Total Steps", str(getattr(run, "step_count", len(getattr(run, "steps", []))))),
        ("Start Time", _fmt_time(getattr(run, "start_time", None))),
        ("End Time", _fmt_time(getattr(run, "end_time", None))),
    ])

    steps = getattr(run, "steps", []) or []
    if hasattr(run, "executed_path"):
        try:
            steps = run.executed_path()
        except Exception:
            pass

    return Group(
        Panel(header, title="Playbook Run Details", border_style="magenta"),
        _playbook_steps_table(steps),
    )


# --- UDM Event Stream Rendering -------------------------------------------

UDM_EVENT_COLUMNS = ("Timestamp", "Event Type", "Principal", "Target", "Log Type")


def _normalize_udm_event(event: dict) -> dict:
    """Unwraps outer event/udm envelope if present."""
    if not isinstance(event, dict):
        return {}
    return event.get("event") or event.get("udm") or event


def udm_event_row(event: dict) -> List[Any]:
    """Map a UDM event dictionary to a DataTable row."""
    ev = _normalize_udm_event(event)
    metadata = ev.get("metadata", {}) or {}
    principal = ev.get("principal", {}) or {}
    target = ev.get("target", {}) or {}

    ts = (
        metadata.get("eventTimestamp")
        or metadata.get("event_timestamp")
        or metadata.get("collectedTimestamp")
        or metadata.get("collected_timestamp")
        or "-"
    )
    if isinstance(ts, str) and len(ts) > 19:
        ts = ts[:19].replace("T", " ")

    etype = (
        metadata.get("eventType")
        or metadata.get("event_type")
        or "UNKNOWN_EVENT"
    )

    p_user = (
        principal.get("user", {}).get("userid")
        or principal.get("user", {}).get("user_name")
        or principal.get("user", {}).get("email")
        if isinstance(principal.get("user"), dict)
        else None
    )
    p_ip = principal.get("ip")
    p_host = principal.get("hostname")
    p_str = p_user or p_ip or p_host or "-"
    if isinstance(p_ip, list) and p_ip:
        p_str = p_ip[0]

    t_user = (
        target.get("user", {}).get("userid")
        or target.get("user", {}).get("user_name")
        or target.get("user", {}).get("email")
        if isinstance(target.get("user"), dict)
        else None
    )
    t_ip = target.get("ip")
    t_host = target.get("hostname")
    t_str = t_user or t_ip or t_host or "-"
    if isinstance(t_ip, list) and t_ip:
        t_str = t_ip[0]

    log_type = (
        metadata.get("logType")
        or metadata.get("log_type")
        or metadata.get("productName")
        or metadata.get("product_name")
        or "-"
    )

    return [str(ts), str(etype), str(p_str), str(t_str), str(log_type)]


def udm_event_detail(event: dict) -> Group:
    """Render a structured breakdown of a UDM event."""
    ev = _normalize_udm_event(event)
    metadata = ev.get("metadata", {}) or {}
    principal = ev.get("principal", {}) or {}
    target = ev.get("target", {}) or {}
    network = ev.get("network", {}) or {}
    security_result = ev.get("securityResult") or ev.get("security_result") or {}
    if isinstance(security_result, list) and security_result:
        security_result = security_result[0]

    ts = (
        metadata.get("eventTimestamp")
        or metadata.get("event_timestamp")
        or metadata.get("collectedTimestamp")
        or metadata.get("collected_timestamp")
        or "-"
    )
    etype = (
        metadata.get("eventType")
        or metadata.get("event_type")
        or "-"
    )
    log_type = (
        metadata.get("logType")
        or metadata.get("log_type")
        or "-"
    )
    product_name = (
        metadata.get("productName")
        or metadata.get("product_name")
        or "-"
    )
    vendor_name = (
        metadata.get("vendorName")
        or metadata.get("vendor_name")
        or "-"
    )
    description = (
        metadata.get("description")
        or "-"
    )

    meta_rows = [
        ("Event Timestamp", str(ts)),
        ("Event Type", Text(str(etype), style="bold cyan")),
        ("Log Type", str(log_type)),
        ("Product Name", str(product_name)),
        ("Vendor Name", str(vendor_name)),
    ]
    if description and description != "-":
        meta_rows.append(("Description", str(description)))

    p_user = (
        principal.get("user", {}).get("userid")
        or principal.get("user", {}).get("user_name")
        or principal.get("user", {}).get("email")
        if isinstance(principal.get("user"), dict)
        else "-"
    )
    p_process = (
        principal.get("process", {}).get("file", {}).get("name")
        or principal.get("process", {}).get("file", {}).get("full_path")
        if isinstance(principal.get("process"), dict)
        else "-"
    )
    p_ip = principal.get("ip", "-")
    if isinstance(p_ip, list):
        p_ip = ", ".join(str(x) for x in p_ip)
    p_rows = [
        ("User", str(p_user or "-")),
        ("IP Address", str(p_ip or "-")),
        ("Hostname", str(principal.get("hostname", "-"))),
        ("Process Name", str(p_process or "-")),
    ]

    t_user = (
        target.get("user", {}).get("userid")
        or target.get("user", {}).get("user_name")
        or target.get("user", {}).get("email")
        if isinstance(target.get("user"), dict)
        else "-"
    )
    t_file = (
        target.get("file", {}).get("fullPath")
        or target.get("file", {}).get("full_path")
        or target.get("file", {}).get("name")
        if isinstance(target.get("file"), dict)
        else "-"
    )
    t_ip = target.get("ip", "-")
    if isinstance(t_ip, list):
        t_ip = ", ".join(str(x) for x in t_ip)
    t_rows = [
        ("Target User", str(t_user or "-")),
        ("Target IP", str(t_ip or "-")),
        ("Target Hostname", str(target.get("hostname", "-"))),
        ("Target Port", str(target.get("port", "-"))),
        ("Target File Path", str(t_file or "-")),
    ]

    net_rows = [
        ("Protocol", str(network.get("ipProtocol") or network.get("ip_protocol") or "-")),
        ("Direction", str(network.get("direction", "-"))),
        ("Received Bytes", str(network.get("receivedBytes") or network.get("received_bytes") or "-")),
        ("Sent Bytes", str(network.get("sentBytes") or network.get("sent_bytes") or "-")),
    ]

    return Group(
        Panel(_kv_table(meta_rows), title="Event Metadata", border_style="cyan"),
        Panel(_kv_table(p_rows), title="Principal (Actor)", border_style="blue"),
        Panel(_kv_table(t_rows), title="Target (Asset / Endpoint)", border_style="magenta"),
        Panel(_kv_table(net_rows), title="Network & Telemetry", border_style="green"),
    )


def raw_log_panel(raw_log: Any, event_id: str = "") -> Group:
    """Render raw unparsed log payload and decoding metadata."""
    raw_text = getattr(raw_log, "raw_text", str(raw_log))
    source_prod = getattr(raw_log, "source_product", "-") or "-"
    log_type = getattr(raw_log, "log_type", "-") or "-"
    ts = getattr(raw_log, "timestamp", "-") or "-"
    bytes_size = getattr(raw_log, "raw_bytes_size", len(raw_text.encode("utf-8")))

    meta_table = _kv_table([
        ("Event ID", str(event_id or "-")),
        ("Log Type", str(log_type)),
        ("Source Product", str(source_prod)),
        ("Timestamp", str(ts)),
        ("Byte Size", f"{bytes_size} bytes"),
    ])

    return Group(
        Panel(meta_table, title="Raw Log Telemetry Metadata", border_style="cyan"),
        Panel(Text(raw_text, style="bold green"), title="Raw Unparsed Log Text", border_style="green"),
    )


def udm_enriched_event_detail(event_inv: Any) -> Group:
    """Render full enriched UDM event fields and flattened schema mapping."""
    structured = (
        getattr(event_inv, "udm", None)
        or getattr(event_inv, "event", None)
        or (event_inv if isinstance(event_inv, dict) else {})
    )
    ev = _normalize_udm_event(structured)
    event_id = getattr(event_inv, "event_id", "") or ev.get("metadata", {}).get("id", "-")

    std_group = udm_event_detail(ev)

    fields_table = Table(title="Flattened UDM Field Paths & Values", expand=True, border_style="cyan")
    fields_table.add_column("Field Path", style="bold cyan", no_wrap=True)
    fields_table.add_column("Value")

    flat_dict: dict[str, Any] = {}
    if hasattr(event_inv, "flatten_fields") and callable(event_inv.flatten_fields):
        flat_dict = event_inv.flatten_fields()
    else:
        def _flatten(obj: Any, prefix: str):
            if isinstance(obj, dict):
                for k, v in obj.items():
                    _flatten(v, f"{prefix}.{k}" if prefix else k)
            elif isinstance(obj, list):
                for idx, v in enumerate(obj):
                    _flatten(v, f"{prefix}[{idx}]")
            else:
                flat_dict[prefix] = obj
        _flatten(ev, "")

    for k in sorted(flat_dict.keys()):
        val = str(flat_dict[k])
        fields_table.add_row(k, val)

    return Group(
        Panel(_kv_table([("Event ID", Text(str(event_id), style="bold yellow"))]), title="Enriched Event Identifier", border_style="yellow"),
        std_group,
        fields_table,
    )


# --- Curated Rules Rendering ----------------------------------------------

RULE_COLUMNS = ("Title", "Category", "Precision", "Log Sources", "MITRE Tactics")


def rule_row(rs: Any) -> List[Any]:
    """Map a CuratedRuleSetSummary to a DataTable row."""
    title = str(getattr(rs, "title", "-"))
    cat = str(getattr(rs, "category_name", getattr(rs, "category_id", "-")))
    log_sources = ", ".join(getattr(rs, "log_sources", []) or []) or "-"
    tactics = ", ".join(str(getattr(m, "display_name", m)) for m in (getattr(rs, "tactics", []) or [])) or "-"

    deployments = getattr(rs, "deployments", []) or []
    precisions = ", ".join(getattr(d, "precision", "") for d in deployments if getattr(d, "enabled", False)) or (getattr(deployments[0], "precision", "PRECISE") if deployments else "PRECISE")

    return [title, cat, precisions, log_sources, tactics]


def ruleset_detail(detail: Any) -> Group:
    """Render a comprehensive view of a CuratedRuleSetDetail."""
    rs = getattr(detail, "rule_set", detail)
    header = _kv_table([
        ("Title", Text(str(getattr(rs, "title", "-")), style="bold yellow")),
        ("Ruleset ID", str(getattr(rs, "id", "-"))),
        ("Category", str(getattr(rs, "category_name", "-"))),
        ("Description", str(getattr(rs, "description", "-"))),
        ("Log Sources", ", ".join(getattr(rs, "log_sources", []) or []) or "-"),
        ("Authors", ", ".join(getattr(rs, "authors", []) or []) or "-"),
        ("Detections Fired", str(getattr(rs, "detection_count", getattr(detail, "detection_count", 0)))),
    ])

    rules = getattr(detail, "rules", []) or []
    rules_table = Table(title="Member Detection Rules", expand=True, border_style="cyan")
    rules_table.add_column("Rule Title", style="bold")
    rules_table.add_column("Severity")
    rules_table.add_column("Precision")
    rules_table.add_column("MITRE Techniques")
    for r in rules:
        techs = ", ".join(str(getattr(t, "display_name", t)) for t in (getattr(r, "techniques", []) or [])) or "-"
        rules_table.add_row(
            str(getattr(r, "title", "-")),
            str(getattr(r, "severity", "-")),
            str(getattr(r, "precision", "-")),
            techs,
        )

    techniques = getattr(rs, "techniques", []) or []
    mitre_table = Table(title="MITRE ATT&CK Framework Mappings", expand=True, border_style="magenta")
    mitre_table.add_column("ID", style="cyan")
    mitre_table.add_column("Technique / Tactic Name", style="bold")
    for m in techniques:
        mitre_table.add_row(str(getattr(m, "id", "-")), str(getattr(m, "display_name", "-")))

    return Group(
        Panel(header, title="Curated Rule Set Overview", border_style="yellow"),
        rules_table if rules else Text("No individual member rules returned.", style="dim"),
        mitre_table if techniques else Text("No MITRE mappings available.", style="dim"),
    )


# --- Playbook Catalogue Rendering -----------------------------------------

PLAYBOOK_CATALOGUE_COLUMNS = ("Name", "Category", "Type", "Status", "Creator")


def playbook_catalogue_row(pb: Any) -> List[Any]:
    """Map a PlaybookSummary to a DataTable row."""
    name = str(getattr(pb, "name", "-"))
    cat = str(getattr(pb, "category_name", "-"))
    pb_type = str(getattr(pb, "playbook_type", "REGULAR"))
    if hasattr(pb_type, "name"):
        pb_type = pb_type.name
    enabled = "Enabled" if getattr(pb, "is_enabled", True) else "Disabled"
    creator = str(getattr(pb, "creator_full_name", getattr(pb, "creator", "-")))
    return [name, cat, pb_type, enabled, creator]


def playbook_detail_panel(pb: Any) -> Group:
    """Render a comprehensive PlaybookDetail view."""
    pb_type = str(getattr(pb, "playbook_type", "REGULAR"))
    if hasattr(pb_type, "name"):
        pb_type = pb_type.name

    header = _kv_table([
        ("Playbook Name", Text(str(getattr(pb, "name", "-")), style="bold magenta")),
        ("ID", str(getattr(pb, "id", getattr(pb, "identifier", "-")))),
        ("Category", str(getattr(pb, "category_name", "-"))),
        ("Playbook Type", str(pb_type)),
        ("Status", Text("Enabled" if getattr(pb, "is_enabled", True) else "Disabled", style="bold green" if getattr(pb, "is_enabled", True) else "dim")),
        ("Creator", str(getattr(pb, "creator_full_name", getattr(pb, "creator", "-")))),
        ("Environments", ", ".join(getattr(pb, "environments", []) or []) or "All"),
        ("Description", str(getattr(pb, "description", "-"))),
    ])

    trigger = getattr(pb, "trigger", None)
    trigger_rows = []
    if trigger:
        trigger_rows.append(("Trigger Type", str(getattr(trigger, "trigger_type", "-"))))
        trigger_rows.append(("Logical Operator", str(getattr(trigger, "logical_operator", "AND"))))
        conditions = getattr(trigger, "conditions", []) or []
        for idx, cond in enumerate(conditions, 1):
            trigger_rows.append((f"Condition #{idx}", f"{getattr(cond, 'match_type', 'EQUAL')} -> {getattr(cond, 'value', '')}"))

    steps = getattr(pb, "steps", []) or []
    steps_table = Table(title="Playbook Step Actions", expand=True, border_style="blue")
    steps_table.add_column("Step Name", style="bold")
    steps_table.add_column("Action Name")
    steps_table.add_column("Integration")
    steps_table.add_column("Type")
    steps_table.add_column("Automatic")
    for s in steps:
        steps_table.add_row(
            str(getattr(s, "name", "-")),
            str(getattr(s, "action_name", getattr(s, "action_provider", "-"))),
            str(getattr(s, "integration", "-")),
            str(getattr(s, "step_type", "-")),
            "Yes" if getattr(s, "is_automatic", True) else "Manual",
        )

    return Group(
        Panel(header, title="Playbook Definition Overview", border_style="magenta"),
        Panel(_kv_table(trigger_rows), title="Playbook Trigger Criteria", border_style="cyan") if trigger_rows else Text("No explicit trigger conditions configured.", style="dim"),
        steps_table if steps else Text("No step actions defined.", style="dim"),
    )


# --- Native Dashboards Rendering -----------------------------------------

DASHBOARD_COLUMNS = ["ID", "Dashboard Name", "Type", "Charts", "Access"]


def dashboard_row(summary: Any) -> Tuple[str, ...]:
    """Map a DashboardSummary to table row cells."""
    dash_id = getattr(summary, "id", getattr(summary, "name", "-")) or "-"
    display_name = getattr(summary, "display_name", dash_id) or dash_id
    dtype = getattr(summary, "type", "UNKNOWN") or "UNKNOWN"
    charts_count = str(getattr(summary, "charts_count", 0))
    access = getattr(summary, "access", "UNKNOWN") or "UNKNOWN"

    type_style = "bold cyan" if "NATIVE" in str(dtype).upper() or "DEFAULT" in str(dtype).upper() else "magenta"

    return (
        str(dash_id),
        str(display_name),
        f"[{type_style}]{dtype}[/]",
        f"[bold yellow]{charts_count}[/]",
        str(access),
    )


def _render_chart_widget(chart: Any, query_result: Optional[Any] = None) -> Panel:
    """Render an individual dashboard chart widget with its visualization."""
    chart_title = getattr(chart, "display_name", getattr(chart, "id", "Chart Widget")) or "Chart Widget"
    tile_type = getattr(chart, "tile_type", "TILE_TYPE_VISUALIZATION")
    chart_type = getattr(chart, "chart_type", "DASHBOARD_CHART_TYPE_CUSTOM")
    description = getattr(chart, "description", "")
    query = getattr(chart, "query", None)

    parts: List[Any] = []
    if description:
        parts.append(Text(description, style="dim italic"))

    if query_result is not None:
        rows = getattr(query_result, "rows", []) or []
        columns = getattr(query_result, "columns", []) or []

        # Case 1: Single-metric / KPI stat card
        if len(rows) == 1 and len(columns) <= 2:
            row = rows[0]
            val_items = list(row.items())
            if len(val_items) == 1:
                col_name, val = val_items[0]
                stat_text = Text()
                stat_text.append(f"{val}\n", style="bold yellow")
                stat_text.append(str(col_name), style="dim")
                parts.append(stat_text)
            else:
                grid = Table.grid(padding=(0, 4))
                for col_name, val in val_items:
                    grid.add_column()
                grid.add_row(*[Text(f"{v}\n{k}", style="bold yellow") for k, v in val_items])
                parts.append(grid)

        # Case 2: Bar chart / distribution if we have a label column and a numeric value column
        elif rows and len(columns) == 2 and any(isinstance(rows[0].get(c), (int, float)) or str(rows[0].get(c, "")).replace(".", "", 1).isdigit() for c in columns):
            num_col = next((c for c in columns if isinstance(rows[0].get(c), (int, float)) or str(rows[0].get(c, "")).replace(".", "", 1).isdigit()), columns[1])
            label_col = columns[0] if num_col == columns[1] else columns[1]

            numeric_values = []
            for r in rows:
                raw_v = r.get(num_col, 0)
                try:
                    numeric_values.append(float(raw_v))
                except (ValueError, TypeError):
                    numeric_values.append(0.0)

            max_val = max(numeric_values) if numeric_values and max(numeric_values) > 0 else 1.0
            bar_table = Table.grid(padding=(0, 2))
            bar_table.add_column(style="bold cyan", justify="right")
            bar_table.add_column()
            bar_table.add_column(style="bold yellow", justify="right")

            for r, val_num in zip(rows, numeric_values):
                label_text = str(r.get(label_col, "-"))
                pct = val_num / max_val if max_val > 0 else 0
                bar_len = max(1, int(pct * 25))
                bar_str = "█" * bar_len
                bar_table.add_row(label_text, Text(bar_str, style="green" if pct < 0.7 else "yellow"), str(r.get(num_col, val_num)))

            parts.append(bar_table)

        # Case 3: Tabular query output
        elif rows:
            data_tbl = Table(expand=True, border_style="dim")
            for c in columns:
                data_tbl.add_column(str(c), style="bold" if c == columns[0] else "")
            for r in rows[:15]:
                data_tbl.add_row(*[str(r.get(c, "-")) for c in columns])
            if len(rows) > 15:
                parts.append(data_tbl)
                parts.append(Text(f"… and {len(rows) - 15} more rows", style="dim italic"))
            else:
                parts.append(data_tbl)
        else:
            parts.append(Text("Query returned 0 rows.", style="dim italic"))

    elif query:
        query_text = getattr(query, "query_text", "")
        dialect = getattr(query, "dialect", "YL2")
        parts.append(Text(f"Dialect: {dialect}  ·  Query: {query_text}", style="dim"))
    else:
        parts.append(Text(f"Chart Type: {chart_type}  ·  Tile: {tile_type}", style="dim"))

    return Panel(
        Group(*parts) if len(parts) > 1 else (parts[0] if parts else Text("")),
        title=f"📊 {chart_title}",
        border_style="cyan",
    )


def dashboard_detail_panel(
    detail: Any,
    query_results: Optional[Dict[str, Any]] = None,
) -> Group:
    """Render full composite dashboard graph with layout, charts, and live widget results."""
    summary = getattr(detail, "summary", None)
    dash_id = getattr(summary, "id", getattr(detail, "id", "-")) if summary else "-"
    display_name = getattr(summary, "display_name", getattr(detail, "display_name", dash_id)) if summary else dash_id
    description = getattr(summary, "description", getattr(detail, "description", "")) if summary else ""
    dtype = getattr(summary, "type", getattr(detail, "type", "UNKNOWN")) if summary else "UNKNOWN"
    access = getattr(summary, "access", getattr(detail, "access", "UNKNOWN")) if summary else "UNKNOWN"
    create_time = getattr(summary, "create_time", "-") if summary else "-"
    update_time = getattr(summary, "update_time", "-") if summary else "-"

    charts = getattr(detail, "charts", []) or []

    header = _kv_table([
        ("Dashboard ID", Text(str(dash_id), style="bold yellow")),
        ("Display Name", Text(str(display_name), style="bold")),
        ("Type", str(dtype)),
        ("Access Scope", str(access)),
        ("Charts Count", str(len(charts))),
        ("Created", str(create_time)),
        ("Updated", str(update_time)),
        ("Description", str(description or "No description provided.")),
    ])

    results_map = query_results or {}
    chart_panels: List[Any] = []
    for chart in charts:
        q_name = getattr(chart, "query_name", None) or (getattr(getattr(chart, "query", None), "name", None))
        q_id = getattr(chart, "id", None)
        res = results_map.get(q_name) or results_map.get(q_id)
        chart_panels.append(_render_chart_widget(chart, query_result=res))

    content: List[Any] = [
        Panel(header, title="Dashboard Overview", border_style="cyan"),
    ]

    if chart_panels:
        content.append(Panel(Group(*chart_panels), title=f"Visual Widgets ({len(chart_panels)})", border_style="blue"))
    else:
        content.append(Text("No charts or visual widgets attached to this dashboard.", style="dim italic"))

    return Group(*content)


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


# --- help and error panels ------------------------------------------------

def help_panel() -> Panel:
    """Render the keyboard shortcuts help guide."""
    t = Table.grid(padding=(0, 2))
    t.add_column(style="bold cyan", no_wrap=True)
    t.add_column()
    shortcuts = [
        ("F1-F5 / 1-5", "Switch Workspaces (1: Triage, 2: UDM, 3: Detection, 4: Automation, 5: Dashboards)"),
        ("Alt+v", "Split active pane vertically (side-by-side)"),
        ("Alt+s", "Split active pane horizontally (top/bottom)"),
        ("Alt+d", "Tile Launcher modal (spawn any SecOps view)"),
        ("Alt+f", "Toggle maximize / fullscreen on active pane"),
        ("Alt+w / Alt+q", "Close active split pane"),
        ("/", "Focus active workspace search input"),
        ("Escape", "Blur search input / Return to Case Overview / Close modal"),
        ("Down / Enter", "Focus table from search bar or execute query"),
        ("o", "Switch to Case Overview inline view"),
        ("a", "Switch to Alert Investigation inline view"),
        ("e", "Switch to Entity Pivot / Correlation inline view"),
        ("p", "Switch to Playbook Run DAG inline view"),
        ("c", "Add comment to currently selected case (Modal prompt)"),
        ("i", "Inspect Enriched UDM Event fields (Inline UDM view)"),
        ("l", "Inspect Live Raw Log payload (Inline UDM view)"),
        ("y", "Yank / Copy active record/payload to system clipboard"),
        ("r", "Refresh active workspace data"),
        ("Tab / Shift+Tab", "Switch focus between controls and tiles"),
        ("?", "Show this help screen"),
        ("q", "Quit application"),
    ]
    for key, desc in shortcuts:
        t.add_row(Text(f"[{key}]", style="bold cyan"), desc)
    return Panel(t, title="SecOps TUI Navigation & Keybindings", border_style="blue")


def error_panel(message: str, context: Optional[str] = None) -> Panel:
    body = Text(message, style="bold red")
    if context:
        body = Group(body, Text(context, style="dim"))
    return Panel(body, title="Error", border_style="red")

