"""Qt Data Models for SecOps Desktop Client.

Maintains clean separation of concerns:
- Storage is decoupled from GUI widgets.
- Materializes tabular views with safe dot-notation extraction.
- Strictly adheres to production live data invariants.
"""

from typing import Any, Dict, List, Optional
from PySide6.QtCore import QAbstractTableModel, QModelIndex, Qt


class EventTableModel(QAbstractTableModel):
    """Virtual high-performance table model for UDM Search results."""

    COLUMNS = [
        ("Timestamp", "metadata.eventTimestamp"),
        ("Event Type", "metadata.eventType"),
        ("Principal Host", "principal.hostname"),
        ("Principal IP", "principal.ip"),
        ("Principal User", "principal.user.userid"),
        ("Target Host", "target.hostname"),
        ("Target IP", "target.ip"),
        ("Target User", "target.user.userid"),
        ("Product", "metadata.productName"),
    ]

    def __init__(self, parent=None):
        super().__init__(parent)
        self._events: List[Dict[str, Any]] = []

    def rowCount(self, parent: QModelIndex = QModelIndex()) -> int:
        if parent.isValid():
            return 0
        return len(self._events)

    def columnCount(self, parent: QModelIndex = QModelIndex()) -> int:
        if parent.isValid():
            return 0
        return len(self.COLUMNS)

    def headerData(self, section: int, orientation: Qt.Orientation, role: int = Qt.ItemDataRole.DisplayRole) -> Any:
        if orientation == Qt.Orientation.Horizontal and role == Qt.ItemDataRole.DisplayRole:
            if 0 <= section < len(self.COLUMNS):
                return self.COLUMNS[section][0]
        elif orientation == Qt.Orientation.Vertical and role == Qt.ItemDataRole.DisplayRole:
            return str(section + 1)
        return None

    def data(self, index: QModelIndex, role: int = Qt.ItemDataRole.DisplayRole) -> Any:
        if not index.isValid() or not (0 <= index.row() < len(self._events)):
            return None

        if role == Qt.ItemDataRole.DisplayRole:
            event = self._events[index.row()]
            raw_event = event.get("event") or event.get("udm") or event
            field_path = self.COLUMNS[index.column()][1]
            return self._extract_field_value(raw_event, field_path)

        elif role == Qt.ItemDataRole.TextAlignmentRole:
            return int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)

        return None

    def _extract_field_value(self, data: Dict[str, Any], path: str) -> str:
        """Navigates dot notation safely for table cell display."""
        parts = path.split(".")
        curr = data
        for part in parts:
            if not isinstance(curr, dict):
                return "-"
            if part in curr:
                curr = curr[part]
            else:
                alt_part = "".join(w.capitalize() if i > 0 else w for i, w in enumerate(part.split("_")))
                if alt_part in curr:
                    curr = curr[alt_part]
                else:
                    return "-"
        if curr is None or curr == "":
            return "-"
        if isinstance(curr, (list, tuple)):
            return ", ".join(str(x) for x in curr)
        return str(curr)

    def append_events(self, new_events: List[Dict[str, Any]]):
        if not new_events:
            return
        start_row = len(self._events)
        end_row = start_row + len(new_events) - 1
        self.beginInsertRows(QModelIndex(), start_row, end_row)
        self._events.extend(new_events)
        self.endInsertRows()

    def clear(self):
        if not self._events:
            return
        self.beginResetModel()
        self._events.clear()
        self.endResetModel()

    def get_event(self, row: int) -> Optional[Dict[str, Any]]:
        if 0 <= row < len(self._events):
            return self._events[row]
        return None


class CaseTableModel(QAbstractTableModel):
    """Table model for SOAR Cases."""

    COLUMNS = [
        ("Case ID", "case_id"),
        ("Title", "title"),
        ("Priority", "priority"),
        ("Status", "status"),
        ("Stage", "stage"),
        ("Assignee", "assignee"),
        ("Alerts", "alert_count"),
        ("Created", "created_time"),
        ("Environment", "environment"),
    ]

    def __init__(self, parent=None):
        super().__init__(parent)
        self._items: List[Any] = []

    def rowCount(self, parent: QModelIndex = QModelIndex()) -> int:
        if parent.isValid():
            return 0
        return len(self._items)

    def columnCount(self, parent: QModelIndex = QModelIndex()) -> int:
        if parent.isValid():
            return 0
        return len(self.COLUMNS)

    def headerData(self, section: int, orientation: Qt.Orientation, role: int = Qt.ItemDataRole.DisplayRole) -> Any:
        if orientation == Qt.Orientation.Horizontal and role == Qt.ItemDataRole.DisplayRole:
            if 0 <= section < len(self.COLUMNS):
                return self.COLUMNS[section][0]
        elif orientation == Qt.Orientation.Vertical and role == Qt.ItemDataRole.DisplayRole:
            return str(section + 1)
        return None

    def data(self, index: QModelIndex, role: int = Qt.ItemDataRole.DisplayRole) -> Any:
        if not index.isValid() or not (0 <= index.row() < len(self._items)):
            return None

        if role == Qt.ItemDataRole.DisplayRole:
            item = self._items[index.row()]
            attr_name = self.COLUMNS[index.column()][1]
            if hasattr(item, attr_name):
                val = getattr(item, attr_name)
            elif isinstance(item, dict):
                val = item.get(attr_name, "-")
            else:
                val = "-"
            return str(val) if val is not None else "-"

        elif role == Qt.ItemDataRole.TextAlignmentRole:
            return int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)

        return None

    def set_items(self, items: List[Any]):
        self.beginResetModel()
        self._items = list(items)
        self.endResetModel()

    def clear(self):
        self.beginResetModel()
        self._items.clear()
        self.endResetModel()

    def get_item(self, row: int) -> Optional[Any]:
        if 0 <= row < len(self._items):
            return self._items[row]
        return None


class PlaybookTableModel(QAbstractTableModel):
    """Table model for SOAR Playbooks."""

    COLUMNS = [
        ("Playbook ID", "playbook_id"),
        ("Name", "name"),
        ("Category", "category"),
        ("Trigger Type", "trigger_type"),
        ("Enabled", "is_enabled"),
        ("Modified Time", "modified_time"),
    ]

    def __init__(self, parent=None):
        super().__init__(parent)
        self._items: List[Any] = []

    def rowCount(self, parent: QModelIndex = QModelIndex()) -> int:
        if parent.isValid():
            return 0
        return len(self._items)

    def columnCount(self, parent: QModelIndex = QModelIndex()) -> int:
        if parent.isValid():
            return 0
        return len(self.COLUMNS)

    def headerData(self, section: int, orientation: Qt.Orientation, role: int = Qt.ItemDataRole.DisplayRole) -> Any:
        if orientation == Qt.Orientation.Horizontal and role == Qt.ItemDataRole.DisplayRole:
            if 0 <= section < len(self.COLUMNS):
                return self.COLUMNS[section][0]
        elif orientation == Qt.Orientation.Vertical and role == Qt.ItemDataRole.DisplayRole:
            return str(section + 1)
        return None

    def data(self, index: QModelIndex, role: int = Qt.ItemDataRole.DisplayRole) -> Any:
        if not index.isValid() or not (0 <= index.row() < len(self._items)):
            return None

        if role == Qt.ItemDataRole.DisplayRole:
            item = self._items[index.row()]
            attr_name = self.COLUMNS[index.column()][1]
            val = getattr(item, attr_name, "-") if hasattr(item, attr_name) else (item.get(attr_name, "-") if isinstance(item, dict) else "-")
            return str(val) if val is not None else "-"

        elif role == Qt.ItemDataRole.TextAlignmentRole:
            return int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)

        return None

    def set_items(self, items: List[Any]):
        self.beginResetModel()
        self._items = list(items)
        self.endResetModel()

    def clear(self):
        self.beginResetModel()
        self._items.clear()
        self.endResetModel()

    def get_item(self, row: int) -> Optional[Any]:
        if 0 <= row < len(self._items):
            return self._items[row]
        return None


class IntegrationTableModel(QAbstractTableModel):
    """Table model for SOAR Integrations."""

    COLUMNS = [
        ("Identifier", "identifier"),
        ("Display Name", "display_name"),
        ("Category", "category"),
        ("Instances", "instance_count"),
        ("Certified", "is_certified"),
    ]

    def __init__(self, parent=None):
        super().__init__(parent)
        self._items: List[Any] = []

    def rowCount(self, parent: QModelIndex = QModelIndex()) -> int:
        if parent.isValid():
            return 0
        return len(self._items)

    def columnCount(self, parent: QModelIndex = QModelIndex()) -> int:
        if parent.isValid():
            return 0
        return len(self.COLUMNS)

    def headerData(self, section: int, orientation: Qt.Orientation, role: int = Qt.ItemDataRole.DisplayRole) -> Any:
        if orientation == Qt.Orientation.Horizontal and role == Qt.ItemDataRole.DisplayRole:
            if 0 <= section < len(self.COLUMNS):
                return self.COLUMNS[section][0]
        elif orientation == Qt.Orientation.Vertical and role == Qt.ItemDataRole.DisplayRole:
            return str(section + 1)
        return None

    def data(self, index: QModelIndex, role: int = Qt.ItemDataRole.DisplayRole) -> Any:
        if not index.isValid() or not (0 <= index.row() < len(self._items)):
            return None

        if role == Qt.ItemDataRole.DisplayRole:
            item = self._items[index.row()]
            attr_name = self.COLUMNS[index.column()][1]
            val = getattr(item, attr_name, "-") if hasattr(item, attr_name) else (item.get(attr_name, "-") if isinstance(item, dict) else "-")
            return str(val) if val is not None else "-"

        return None

    def set_items(self, items: List[Any]):
        self.beginResetModel()
        self._items = list(items)
        self.endResetModel()

    def clear(self):
        self.beginResetModel()
        self._items.clear()
        self.endResetModel()

    def get_item(self, row: int) -> Optional[Any]:
        if 0 <= row < len(self._items):
            return self._items[row]
        return None


class JobTableModel(QAbstractTableModel):
    """Table model for SOAR Scheduled Jobs."""

    COLUMNS = [
        ("Job Identifier", "identifier"),
        ("Display Name", "display_name"),
        ("Interval (s)", "interval_seconds"),
        ("Enabled", "is_enabled"),
        ("Status", "running_status"),
        ("Modified", "modified_time"),
    ]

    def __init__(self, parent=None):
        super().__init__(parent)
        self._items: List[Any] = []

    def rowCount(self, parent: QModelIndex = QModelIndex()) -> int:
        if parent.isValid():
            return 0
        return len(self._items)

    def columnCount(self, parent: QModelIndex = QModelIndex()) -> int:
        if parent.isValid():
            return 0
        return len(self.COLUMNS)

    def headerData(self, section: int, orientation: Qt.Orientation, role: int = Qt.ItemDataRole.DisplayRole) -> Any:
        if orientation == Qt.Orientation.Horizontal and role == Qt.ItemDataRole.DisplayRole:
            if 0 <= section < len(self.COLUMNS):
                return self.COLUMNS[section][0]
        elif orientation == Qt.Orientation.Vertical and role == Qt.ItemDataRole.DisplayRole:
            return str(section + 1)
        return None

    def data(self, index: QModelIndex, role: int = Qt.ItemDataRole.DisplayRole) -> Any:
        if not index.isValid() or not (0 <= index.row() < len(self._items)):
            return None

        if role == Qt.ItemDataRole.DisplayRole:
            item = self._items[index.row()]
            attr_name = self.COLUMNS[index.column()][1]
            val = getattr(item, attr_name, "-") if hasattr(item, attr_name) else (item.get(attr_name, "-") if isinstance(item, dict) else "-")
            return str(val) if val is not None else "-"

        return None

    def set_items(self, items: List[Any]):
        self.beginResetModel()
        self._items = list(items)
        self.endResetModel()

    def clear(self):
        self.beginResetModel()
        self._items.clear()
        self.endResetModel()

    def get_item(self, row: int) -> Optional[Any]:
        if 0 <= row < len(self._items):
            return self._items[row]
        return None


class CuratedRulesetTableModel(QAbstractTableModel):
    """Table model for Curated Detections Rulesets."""

    COLUMNS = [
        ("Ruleset ID", "ruleset_id"),
        ("Display Name", "display_name"),
        ("Category", "category"),
        ("Rule Count", "rule_count"),
        ("Precision", "precision"),
    ]

    def __init__(self, parent=None):
        super().__init__(parent)
        self._items: List[Any] = []

    def rowCount(self, parent: QModelIndex = QModelIndex()) -> int:
        if parent.isValid():
            return 0
        return len(self._items)

    def columnCount(self, parent: QModelIndex = QModelIndex()) -> int:
        if parent.isValid():
            return 0
        return len(self.COLUMNS)

    def headerData(self, section: int, orientation: Qt.Orientation, role: int = Qt.ItemDataRole.DisplayRole) -> Any:
        if orientation == Qt.Orientation.Horizontal and role == Qt.ItemDataRole.DisplayRole:
            if 0 <= section < len(self.COLUMNS):
                return self.COLUMNS[section][0]
        elif orientation == Qt.Orientation.Vertical and role == Qt.ItemDataRole.DisplayRole:
            return str(section + 1)
        return None

    def data(self, index: QModelIndex, role: int = Qt.ItemDataRole.DisplayRole) -> Any:
        if not index.isValid() or not (0 <= index.row() < len(self._items)):
            return None

        if role == Qt.ItemDataRole.DisplayRole:
            item = self._items[index.row()]
            attr_name = self.COLUMNS[index.column()][1]
            val = getattr(item, attr_name, "-") if hasattr(item, attr_name) else (item.get(attr_name, "-") if isinstance(item, dict) else "-")
            return str(val) if val is not None else "-"

        return None

    def set_items(self, items: List[Any]):
        self.beginResetModel()
        self._items = list(items)
        self.endResetModel()

    def clear(self):
        self.beginResetModel()
        self._items.clear()
        self.endResetModel()

    def get_item(self, row: int) -> Optional[Any]:
        if 0 <= row < len(self._items):
            return self._items[row]
        return None


class FeedTableModel(QAbstractTableModel):
    """Table model for SIEM Ingestion Feeds."""

    COLUMNS = [
        ("Feed ID", "feed_id"),
        ("Display Name", "display_name"),
        ("Log Type", "log_type"),
        ("Source Type", "source_type"),
        ("State", "state"),
    ]

    def __init__(self, parent=None):
        super().__init__(parent)
        self._items: List[Any] = []

    def rowCount(self, parent: QModelIndex = QModelIndex()) -> int:
        if parent.isValid():
            return 0
        return len(self._items)

    def columnCount(self, parent: QModelIndex = QModelIndex()) -> int:
        if parent.isValid():
            return 0
        return len(self.COLUMNS)

    def headerData(self, section: int, orientation: Qt.Orientation, role: int = Qt.ItemDataRole.DisplayRole) -> Any:
        if orientation == Qt.Orientation.Horizontal and role == Qt.ItemDataRole.DisplayRole:
            if 0 <= section < len(self.COLUMNS):
                return self.COLUMNS[section][0]
        elif orientation == Qt.Orientation.Vertical and role == Qt.ItemDataRole.DisplayRole:
            return str(section + 1)
        return None

    def data(self, index: QModelIndex, role: int = Qt.ItemDataRole.DisplayRole) -> Any:
        if not index.isValid() or not (0 <= index.row() < len(self._items)):
            return None

        if role == Qt.ItemDataRole.DisplayRole:
            item = self._items[index.row()]
            attr_name = self.COLUMNS[index.column()][1]
            val = getattr(item, attr_name, "-") if hasattr(item, attr_name) else (item.get(attr_name, "-") if isinstance(item, dict) else "-")
            return str(val) if val is not None else "-"

        return None

    def set_items(self, items: List[Any]):
        self.beginResetModel()
        self._items = list(items)
        self.endResetModel()

    def clear(self):
        self.beginResetModel()
        self._items.clear()
        self.endResetModel()

    def get_item(self, row: int) -> Optional[Any]:
        if 0 <= row < len(self._items):
            return self._items[row]
        return None


class ParserTableModel(QAbstractTableModel):
    """Table model for SIEM Parsers."""

    COLUMNS = [
        ("Log Type", "log_type"),
        ("State", "state"),
        ("Type", "parser_type"),
        ("Author", "author"),
    ]

    def __init__(self, parent=None):
        super().__init__(parent)
        self._items: List[Any] = []

    def rowCount(self, parent: QModelIndex = QModelIndex()) -> int:
        if parent.isValid():
            return 0
        return len(self._items)

    def columnCount(self, parent: QModelIndex = QModelIndex()) -> int:
        if parent.isValid():
            return 0
        return len(self.COLUMNS)

    def headerData(self, section: int, orientation: Qt.Orientation, role: int = Qt.ItemDataRole.DisplayRole) -> Any:
        if orientation == Qt.Orientation.Horizontal and role == Qt.ItemDataRole.DisplayRole:
            if 0 <= section < len(self.COLUMNS):
                return self.COLUMNS[section][0]
        elif orientation == Qt.Orientation.Vertical and role == Qt.ItemDataRole.DisplayRole:
            return str(section + 1)
        return None

    def data(self, index: QModelIndex, role: int = Qt.ItemDataRole.DisplayRole) -> Any:
        if not index.isValid() or not (0 <= index.row() < len(self._items)):
            return None

        if role == Qt.ItemDataRole.DisplayRole:
            item = self._items[index.row()]
            attr_name = self.COLUMNS[index.column()][1]
            val = getattr(item, attr_name, "-") if hasattr(item, attr_name) else (item.get(attr_name, "-") if isinstance(item, dict) else "-")
            return str(val) if val is not None else "-"

        return None

    def set_items(self, items: List[Any]):
        self.beginResetModel()
        self._items = list(items)
        self.endResetModel()

    def clear(self):
        self.beginResetModel()
        self._items.clear()
        self.endResetModel()

    def get_item(self, row: int) -> Optional[Any]:
        if 0 <= row < len(self._items):
            return self._items[row]
        return None


class DashboardTableModel(QAbstractTableModel):
    """Table model for SIEM Dashboards."""

    COLUMNS = [
        ("Dashboard ID", "dashboard_id"),
        ("Display Name", "display_name"),
        ("Type", "dashboard_type"),
        ("Charts", "chart_count"),
        ("Updated", "modified_time"),
    ]

    def __init__(self, parent=None):
        super().__init__(parent)
        self._items: List[Any] = []

    def rowCount(self, parent: QModelIndex = QModelIndex()) -> int:
        if parent.isValid():
            return 0
        return len(self._items)

    def columnCount(self, parent: QModelIndex = QModelIndex()) -> int:
        if parent.isValid():
            return 0
        return len(self.COLUMNS)

    def headerData(self, section: int, orientation: Qt.Orientation, role: int = Qt.ItemDataRole.DisplayRole) -> Any:
        if orientation == Qt.Orientation.Horizontal and role == Qt.ItemDataRole.DisplayRole:
            if 0 <= section < len(self.COLUMNS):
                return self.COLUMNS[section][0]
        elif orientation == Qt.Orientation.Vertical and role == Qt.ItemDataRole.DisplayRole:
            return str(section + 1)
        return None

    def data(self, index: QModelIndex, role: int = Qt.ItemDataRole.DisplayRole) -> Any:
        if not index.isValid() or not (0 <= index.row() < len(self._items)):
            return None

        if role == Qt.ItemDataRole.DisplayRole:
            item = self._items[index.row()]
            attr_name = self.COLUMNS[index.column()][1]
            val = getattr(item, attr_name, "-") if hasattr(item, attr_name) else (item.get(attr_name, "-") if isinstance(item, dict) else "-")
            return str(val) if val is not None else "-"

        return None

    def set_items(self, items: List[Any]):
        self.beginResetModel()
        self._items = list(items)
        self.endResetModel()

    def clear(self):
        self.beginResetModel()
        self._items.clear()
        self.endResetModel()

    def get_item(self, row: int) -> Optional[Any]:
        if 0 <= row < len(self._items):
            return self._items[row]
        return None


class GenericItemTableModel(QAbstractTableModel):
    """Flexible 2-column key-value or 3-column name-type-detail model for settings & configuration."""

    def __init__(self, headers: List[str], parent=None):
        super().__init__(parent)
        self._headers = headers
        self._rows: List[List[str]] = []

    def rowCount(self, parent: QModelIndex = QModelIndex()) -> int:
        if parent.isValid():
            return 0
        return len(self._rows)

    def columnCount(self, parent: QModelIndex = QModelIndex()) -> int:
        if parent.isValid():
            return 0
        return len(self._headers)

    def headerData(self, section: int, orientation: Qt.Orientation, role: int = Qt.ItemDataRole.DisplayRole) -> Any:
        if orientation == Qt.Orientation.Horizontal and role == Qt.ItemDataRole.DisplayRole:
            if 0 <= section < len(self._headers):
                return self._headers[section]
        elif orientation == Qt.Orientation.Vertical and role == Qt.ItemDataRole.DisplayRole:
            return str(section + 1)
        return None

    def data(self, index: QModelIndex, role: int = Qt.ItemDataRole.DisplayRole) -> Any:
        if not index.isValid() or not (0 <= index.row() < len(self._rows)):
            return None

        if role == Qt.ItemDataRole.DisplayRole:
            row_data = self._rows[index.row()]
            if 0 <= index.column() < len(row_data):
                return row_data[index.column()]
            return "-"

        return None

    def set_rows(self, rows: List[List[str]]):
        self.beginResetModel()
        self._rows = [list(r) for r in rows]
        self.endResetModel()

    def clear(self):
        self.beginResetModel()
        self._rows.clear()
        self.endResetModel()
