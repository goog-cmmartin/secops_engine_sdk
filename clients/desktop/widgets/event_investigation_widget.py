"""Event Investigation & Raw Log Inspection Widget.

Provides analysts with:
1. Structured UDM field hierarchy and key-value exploration with live filtering.
2. Full indented UDM JSON view with copy capability.
3. Direct 1-click pivot triggers (Filter In, Filter Out, Entity Pivot).
4. Verbatim decoded Raw Log viewer with on-demand fetching and copy capability.
"""

import json
from typing import Any, Dict, Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QApplication,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMenu,
    QPlainTextEdit,
    QPushButton,
    QStackedWidget,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from engine import EntityType, EventInvestigation, FieldFilter, FilterOperator, RawLogPayload


class EventInvestigationWidget(QWidget):
    """Right pane widget inspecting event details and verbatim raw logs."""

    pivot_filter_requested = Signal(object)  # (FieldFilter)
    entity_pivot_requested = Signal(object, str)  # (EntityType, str)
    raw_log_load_requested = Signal(object)  # (EventInvestigation)
    enriched_udm_requested = Signal(str)  # (event_id)

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self._current_investigation: Optional[EventInvestigation] = None
        self._raw_log_loading: bool = False
        self._init_ui()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(6)

        # Header Info Bar
        self.header_label = QLabel("Select an event from search results to investigate.")
        self.header_label.setStyleSheet("font-weight: bold; color: #334155; padding: 4px; background: #f8fafc; border: 1px solid #e2e8f0; border-radius: 4px;")
        layout.addWidget(self.header_label)

        # Tabs for UDM Fields vs Raw Log
        self.tabs = QTabWidget()
        self.tabs.currentChanged.connect(self._on_tab_changed)
        layout.addWidget(self.tabs)

        # =========================================================
        # TAB 1: UDM Event & Fields Explorer
        # =========================================================
        self.udm_tab = QWidget()
        udm_layout = QVBoxLayout(self.udm_tab)
        udm_layout.setContentsMargins(4, 4, 4, 4)
        udm_layout.setSpacing(4)

        # Sub-header: Filter box + view mode toggle + Fetch Enriched button
        top_udm_bar = QHBoxLayout()
        self.field_filter_input = QLineEdit()
        self.field_filter_input.setPlaceholderText("Filter UDM fields (e.g. principal.ip)...")
        self.field_filter_input.textChanged.connect(self._filter_field_rows)
        top_udm_bar.addWidget(self.field_filter_input, stretch=1)

        self.toggle_json_btn = QPushButton("JSON View")
        self.toggle_json_btn.setCheckable(True)
        self.toggle_json_btn.clicked.connect(self._on_toggle_view_mode)
        top_udm_bar.addWidget(self.toggle_json_btn)

        self.fetch_enriched_btn = QPushButton("Fetch Enriched UDM")
        self.fetch_enriched_btn.setStyleSheet("font-weight: bold;")
        self.fetch_enriched_btn.clicked.connect(self._on_fetch_enriched_clicked)
        self.fetch_enriched_btn.setEnabled(False)
        top_udm_bar.addWidget(self.fetch_enriched_btn)

        udm_layout.addLayout(top_udm_bar)

        # Quick Actions Bar for Field Table
        self.actions_bar = QHBoxLayout()
        self.filter_in_btn = QPushButton("+ Filter IN (=)")
        self.filter_in_btn.setStyleSheet("color: #166534; font-weight: bold;")
        self.filter_in_btn.clicked.connect(self._on_filter_in)
        self.filter_in_btn.setEnabled(False)

        self.filter_out_btn = QPushButton("- Filter OUT (!=)")
        self.filter_out_btn.setStyleSheet("color: #991b1b; font-weight: bold;")
        self.filter_out_btn.clicked.connect(self._on_filter_out)
        self.filter_out_btn.setEnabled(False)

        self.entity_pivot_btn = QPushButton("Entity Pivot")
        self.entity_pivot_btn.setStyleSheet("color: #1e40af; font-weight: bold;")
        self.entity_pivot_btn.clicked.connect(self._on_entity_pivot)
        self.entity_pivot_btn.setEnabled(False)

        self.copy_field_btn = QPushButton("Copy Value")
        self.copy_field_btn.clicked.connect(self._on_copy_field_value)
        self.copy_field_btn.setEnabled(False)

        self.actions_bar.addWidget(self.filter_in_btn)
        self.actions_bar.addWidget(self.filter_out_btn)
        self.actions_bar.addWidget(self.entity_pivot_btn)
        self.actions_bar.addWidget(self.copy_field_btn)
        self.actions_bar.addStretch()
        udm_layout.addLayout(self.actions_bar)

        # Stacked view: 0 = Table View, 1 = JSON View
        self.udm_stack = QStackedWidget()

        # View 0: Table View
        self.fields_table = QTableWidget()
        self.fields_table.setColumnCount(2)
        self.fields_table.setHorizontalHeaderLabels(["UDM Field Path", "Value"])
        self.fields_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Interactive)
        self.fields_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.fields_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.fields_table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.fields_table.itemSelectionChanged.connect(self._on_field_selection_changed)
        self.fields_table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.fields_table.customContextMenuRequested.connect(self._on_fields_context_menu)
        self.udm_stack.addWidget(self.fields_table)

        # View 1: Indented JSON View
        self.json_view_widget = QWidget()
        json_layout = QVBoxLayout(self.json_view_widget)
        json_layout.setContentsMargins(0, 0, 0, 0)
        self.json_text_edit = QPlainTextEdit()
        self.json_text_edit.setReadOnly(True)
        mono_font = QFont("Monospace")
        mono_font.setStyleHint(QFont.StyleHint.Monospace)
        mono_font.setPointSize(9)
        self.json_text_edit.setFont(mono_font)
        json_layout.addWidget(self.json_text_edit)
        self.udm_stack.addWidget(self.json_view_widget)

        udm_layout.addWidget(self.udm_stack)
        self.tabs.addTab(self.udm_tab, "UDM Event")

        # =========================================================
        # TAB 2: Verbatim Raw Log Viewer
        # =========================================================
        self.raw_log_tab = QWidget()
        raw_layout = QVBoxLayout(self.raw_log_tab)
        raw_layout.setContentsMargins(4, 4, 4, 4)
        raw_layout.setSpacing(4)

        raw_header = QHBoxLayout()
        self.raw_meta_label = QLabel("No raw log loaded.")
        self.raw_meta_label.setStyleSheet("color: #475569;")
        raw_header.addWidget(self.raw_meta_label)
        raw_header.addStretch()

        self.load_raw_btn = QPushButton("Load Raw Log")
        self.load_raw_btn.setStyleSheet("font-weight: bold;")
        self.load_raw_btn.clicked.connect(self._on_load_raw_log_clicked)
        self.load_raw_btn.setEnabled(False)
        raw_header.addWidget(self.load_raw_btn)

        self.copy_raw_btn = QPushButton("Copy Raw Log")
        self.copy_raw_btn.clicked.connect(self._on_copy_raw_log)
        self.copy_raw_btn.setEnabled(False)
        raw_header.addWidget(self.copy_raw_btn)

        raw_layout.addLayout(raw_header)

        self.raw_log_edit = QPlainTextEdit()
        self.raw_log_edit.setReadOnly(True)
        self.raw_log_edit.setFont(mono_font)
        raw_layout.addWidget(self.raw_log_edit)

        self.tabs.addTab(self.raw_log_tab, "Verbatim Raw Log")

    # =========================================================
    # Display & Data Binding Methods
    # =========================================================
    def display_investigation(self, investigation: EventInvestigation):
        """Populates fields and UDM structure immediately."""
        self._current_investigation = investigation
        event_id = investigation.event_id or "Unknown ID"
        event_type = investigation.event_type
        product = investigation.product_name

        self.header_label.setText(f"Event: {event_type} | Product: {product} | ID: {event_id}")
        self.fetch_enriched_btn.setEnabled(True)
        self.load_raw_btn.setEnabled(True)

        # 1. Populate UDM Table
        flattened = investigation.to_flat_dict()
        self.fields_table.setRowCount(len(flattened))
        for row, (field_path, val) in enumerate(sorted(flattened.items())):
            item_path = QTableWidgetItem(field_path)
            item_val = QTableWidgetItem(str(val))
            self.fields_table.setItem(row, 0, item_path)
            self.fields_table.setItem(row, 1, item_val)

        self.fields_table.resizeColumnToContents(0)
        self._filter_field_rows(self.field_filter_input.text())

        # 2. Populate JSON View
        try:
            formatted_json = json.dumps(investigation.event, indent=2, ensure_ascii=False)
            self.json_text_edit.setPlainText(formatted_json)
        except Exception:
            self.json_text_edit.setPlainText(str(investigation.event))

        # 3. If raw log is already cached, show it; otherwise update status
        if investigation.raw_log and investigation.raw_log.raw_text:
            self.display_raw_log(investigation.raw_log)
        else:
            self.raw_log_edit.setPlainText("Click 'Load Raw Log' or select this tab to fetch verbatim log from Google SecOps.")
            self.raw_meta_label.setText("Raw log not loaded.")
            self.copy_raw_btn.setEnabled(False)

        # If user is already on the Raw Log tab, auto-request raw log load
        if self.tabs.currentIndex() == 1 and (not investigation.raw_log or not investigation.raw_log.raw_text):
            self._on_load_raw_log_clicked()

    def display_raw_log(self, raw_payload: RawLogPayload):
        """Displays fetched verbatim raw log."""
        self._raw_log_loading = False
        self.load_raw_btn.setEnabled(True)
        self.load_raw_btn.setText("Reload Raw Log")

        if self._current_investigation:
            self._current_investigation.raw_log = raw_payload

        if raw_payload and raw_payload.raw_text:
            self.raw_log_edit.setPlainText(raw_payload.raw_text)
            meta_parts = []
            if raw_payload.log_type:
                meta_parts.append(f"Type: {raw_payload.log_type}")
            if raw_payload.source_product:
                meta_parts.append(f"Product: {raw_payload.source_product}")
            if raw_payload.timestamp:
                meta_parts.append(f"Time: {raw_payload.timestamp}")
            meta_parts.append(f"Size: {raw_payload.raw_bytes_size} bytes")
            self.raw_meta_label.setText(" | ".join(meta_parts))
            self.copy_raw_btn.setEnabled(True)
        else:
            self.raw_log_edit.setPlainText("<No raw log available for this event record>")
            self.raw_meta_label.setText("Raw log empty.")
            self.copy_raw_btn.setEnabled(False)

    def set_raw_log_loading(self):
        """Sets loading indicator for raw log."""
        self._raw_log_loading = True
        self.load_raw_btn.setEnabled(False)
        self.load_raw_btn.setText("Loading...")
        self.raw_meta_label.setText("Fetching verbatim raw log from Google SecOps...")
        self.raw_log_edit.setPlainText("Loading raw log from live SecOps backend...")
        self.copy_raw_btn.setEnabled(False)

    def set_raw_log_error(self, err_msg: str):
        """Displays error when raw log fetch fails."""
        self._raw_log_loading = False
        self.load_raw_btn.setEnabled(True)
        self.load_raw_btn.setText("Retry Load Raw Log")
        self.raw_meta_label.setText(f"Error loading raw log: {err_msg}")
        self.raw_log_edit.setPlainText(f"Could not load raw log:\n\n{err_msg}")
        self.copy_raw_btn.setEnabled(False)

    def clear(self):
        self._current_investigation = None
        self._raw_log_loading = False
        self.header_label.setText("Select an event from search results to investigate.")
        self.fields_table.setRowCount(0)
        self.json_text_edit.clear()
        self.raw_log_edit.clear()
        self.raw_meta_label.setText("No raw log loaded.")
        self.filter_in_btn.setEnabled(False)
        self.filter_out_btn.setEnabled(False)
        self.entity_pivot_btn.setEnabled(False)
        self.copy_field_btn.setEnabled(False)
        self.copy_raw_btn.setEnabled(False)
        self.load_raw_btn.setEnabled(False)
        self.fetch_enriched_btn.setEnabled(False)

    # =========================================================
    # Internal Slots & Handlers
    # =========================================================
    def _on_tab_changed(self, index: int):
        """Auto-fetches raw log when analyst switches to Raw Log tab."""
        if index == 1 and self._current_investigation:
            if not self._current_investigation.raw_log or not self._current_investigation.raw_log.raw_text:
                if not self._raw_log_loading:
                    self._on_load_raw_log_clicked()

    def _on_toggle_view_mode(self):
        if self.toggle_json_btn.isChecked():
            self.toggle_json_btn.setText("Table View")
            self.udm_stack.setCurrentIndex(1)
        else:
            self.toggle_json_btn.setText("JSON View")
            self.udm_stack.setCurrentIndex(0)

    def _filter_field_rows(self, filter_text: str):
        query = filter_text.strip().lower()
        for row in range(self.fields_table.rowCount()):
            if not query:
                self.fields_table.setRowHidden(row, False)
                continue
            item_k = self.fields_table.item(row, 0)
            item_v = self.fields_table.item(row, 1)
            text_k = item_k.text().lower() if item_k else ""
            text_v = item_v.text().lower() if item_v else ""
            hidden = (query not in text_k) and (query not in text_v)
            self.fields_table.setRowHidden(row, hidden)

    def _on_field_selection_changed(self):
        selected_rows = self.fields_table.selectionModel().selectedRows()
        has_sel = len(selected_rows) > 0
        self.filter_in_btn.setEnabled(has_sel)
        self.filter_out_btn.setEnabled(has_sel)
        self.entity_pivot_btn.setEnabled(has_sel)
        self.copy_field_btn.setEnabled(has_sel)

    def _get_selected_field_filter(self, operator: FilterOperator) -> Optional[FieldFilter]:
        if not self._current_investigation:
            return None
        selected_rows = self.fields_table.selectionModel().selectedRows()
        if not selected_rows:
            return None
        row = selected_rows[0].row()
        field_path = self.fields_table.item(row, 0).text()
        value = self.fields_table.item(row, 1).text()
        return FieldFilter(field_path=field_path, operator=operator, value=value)

    def _on_filter_in(self):
        f = self._get_selected_field_filter(FilterOperator.EQUALS)
        if f:
            self.pivot_filter_requested.emit(f)

    def _on_filter_out(self):
        f = self._get_selected_field_filter(FilterOperator.NOT_EQUALS)
        if f:
            self.pivot_filter_requested.emit(f)

    def _on_entity_pivot(self):
        if not self._current_investigation:
            return
        selected_rows = self.fields_table.selectionModel().selectedRows()
        if not selected_rows:
            return
        row = selected_rows[0].row()
        field_path = self.fields_table.item(row, 0).text().lower()
        value = self.fields_table.item(row, 1).text()

        # Infer EntityType from field name
        if "ip" in field_path:
            entity_type = EntityType.IP
        elif "host" in field_path:
            entity_type = EntityType.HOSTNAME
        elif "user" in field_path:
            entity_type = EntityType.USER
        elif "sha256" in field_path:
            entity_type = EntityType.SHA256
        elif "domain" in field_path or "dns" in field_path:
            entity_type = EntityType.DOMAIN
        else:
            entity_type = EntityType.HOSTNAME

        self.entity_pivot_requested.emit(entity_type, value)

    def _on_copy_field_value(self):
        selected_rows = self.fields_table.selectionModel().selectedRows()
        if selected_rows:
            val = self.fields_table.item(selected_rows[0].row(), 1).text()
            QApplication.clipboard().setText(val)

    def _on_fields_context_menu(self, pos):
        menu = QMenu(self)
        filter_in_action = menu.addAction("Pivot: Filter IN (=)")
        filter_out_action = menu.addAction("Pivot: Filter OUT (!=)")
        menu.addSeparator()
        entity_pivot_action = menu.addAction("Pivot: Canonical Entity Search")
        copy_action = menu.addAction("Copy Field Value")

        action = menu.exec(self.fields_table.viewport().mapToGlobal(pos))
        if action == filter_in_action:
            self._on_filter_in()
        elif action == filter_out_action:
            self._on_filter_out()
        elif action == entity_pivot_action:
            self._on_entity_pivot()
        elif action == copy_action:
            self._on_copy_field_value()

    def _on_load_raw_log_clicked(self):
        if self._current_investigation:
            self.set_raw_log_loading()
            self.raw_log_load_requested.emit(self._current_investigation)

    def _on_fetch_enriched_clicked(self):
        if self._current_investigation and self._current_investigation.event_id:
            self.fetch_enriched_btn.setEnabled(False)
            self.fetch_enriched_btn.setText("Fetching...")
            self.enriched_udm_requested.emit(self._current_investigation.event_id)

    def _on_copy_raw_log(self):
        if self._current_investigation and self._current_investigation.raw_log:
            QApplication.clipboard().setText(self._current_investigation.raw_log.raw_text)
