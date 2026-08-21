"""UDM Search and Live Event Stream Widget."""

import time
from datetime import datetime, timedelta, timezone
from typing import Optional

from PySide6.QtCore import QModelIndex, Qt, Signal, Slot
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QComboBox,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QSplitter,
    QTableView,
    QVBoxLayout,
    QWidget,
)

from clients.desktop.models import EventTableModel
from clients.desktop.widgets.event_investigation_widget import EventInvestigationWidget
from clients.desktop.workers import (
    EnrichedEventWorker,
    InvestigationWorker,
    RawLogWorker,
    SearchWorker,
)
from engine import (
    EntityType,
    EventInvestigation,
    FieldFilter,
    LifecycleState,
    SearchRequest,
    SearchSession,
    SecOpsEngine,
)


class UdmSearchWidget(QWidget):
    """Encapsulates UDM Search, Virtual Results Table, and Deep Event Investigation."""

    # Signals for parent main window metrics / cross-view pivoting
    search_started = Signal()
    search_finished = Signal(object)  # SearchSession
    time_to_first_row_updated = Signal(float)
    status_message_requested = Signal(str, int)

    def __init__(self, engine: SecOpsEngine, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.engine = engine
        self.table_model = EventTableModel(self)

        self._active_search_worker: Optional[SearchWorker] = None
        self._active_inv_worker: Optional[InvestigationWorker] = None
        self._active_raw_log_worker: Optional[RawLogWorker] = None
        self._active_enriched_worker: Optional[EnrichedEventWorker] = None

        self._search_start_time: float = 0.0
        self._time_to_first_row: Optional[float] = None
        self._current_selected_row: int = -1

        self._init_ui()

    def _init_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(8, 8, 8, 8)
        main_layout.setSpacing(6)

        # 1. Top Query & Control Bar
        query_group = QGroupBox("UDM Search Query")
        query_layout = QVBoxLayout(query_group)
        query_layout.setContentsMargins(6, 6, 6, 6)
        query_layout.setSpacing(6)

        top_row = QHBoxLayout()
        self.query_input = QLineEdit('metadata.event_type = "USER_LOGIN"')
        self.query_input.setPlaceholderText('Enter UDM Search expression (e.g. metadata.event_type = "USER_LOGIN")')
        self.query_input.returnPressed.connect(self._on_search_clicked)
        font = QFont("Monospace")
        font.setStyleHint(QFont.StyleHint.Monospace)
        font.setPointSize(10)
        self.query_input.setFont(font)
        top_row.addWidget(self.query_input, stretch=1)

        self.search_btn = QPushButton("Search")
        self.search_btn.setStyleSheet("font-weight: bold; padding: 6px 16px;")
        self.search_btn.clicked.connect(self._on_search_clicked)
        top_row.addWidget(self.search_btn)

        self.cancel_btn = QPushButton("Cancel")
        self.cancel_btn.setStyleSheet("color: #d9534f; padding: 6px 14px;")
        self.cancel_btn.setEnabled(False)
        self.cancel_btn.clicked.connect(self._on_cancel_clicked)
        top_row.addWidget(self.cancel_btn)

        query_layout.addLayout(top_row)

        # Controls row (Time range, Limit, Batch size)
        controls_row = QHBoxLayout()
        controls_row.addWidget(QLabel("Time Window:"))
        self.time_combo = QComboBox()
        self.time_combo.addItems(["Last 24 Hours", "Last 48 Hours", "Last 7 Days", "Last 30 Days"])
        self.time_combo.setCurrentIndex(1)
        controls_row.addWidget(self.time_combo)

        controls_row.addSpacing(16)
        controls_row.addWidget(QLabel("Receive Limit:"))
        self.limit_spin = QSpinBox()
        self.limit_spin.setRange(10, 100000)
        self.limit_spin.setSingleStep(500)
        self.limit_spin.setValue(1000)
        controls_row.addWidget(self.limit_spin)

        controls_row.addSpacing(16)
        controls_row.addWidget(QLabel("Batch Size:"))
        self.batch_combo = QComboBox()
        self.batch_combo.addItems(["100", "500", "1000"])
        self.batch_combo.setCurrentText("500")
        controls_row.addWidget(self.batch_combo)

        controls_row.addStretch()
        query_layout.addLayout(controls_row)
        main_layout.addWidget(query_group)

        # 2. Main Center Splitter (Results Virtual Table + Event Investigation Pane)
        splitter = QSplitter(Qt.Orientation.Horizontal)

        # Left: Results Table View
        left_widget = QWidget()
        left_layout = QVBoxLayout(left_widget)
        left_layout.setContentsMargins(0, 0, 0, 0)

        table_header = QHBoxLayout()
        self.results_count_label = QLabel("0 events")
        self.results_count_label.setStyleSheet("font-weight: bold;")
        table_header.addWidget(QLabel("Search Results:"))
        table_header.addWidget(self.results_count_label)
        table_header.addStretch()
        left_layout.addLayout(table_header)

        self.table_view = QTableView()
        self.table_view.setModel(self.table_model)
        self.table_view.setSelectionBehavior(QTableView.SelectionBehavior.SelectRows)
        self.table_view.setSelectionMode(QTableView.SelectionMode.SingleSelection)
        self.table_view.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        self.table_view.horizontalHeader().setStretchLastSection(True)
        self.table_view.clicked.connect(self._on_table_clicked)
        self.table_view.activated.connect(self._on_table_clicked)
        left_layout.addWidget(self.table_view)

        splitter.addWidget(left_widget)

        # Right: Event Investigation & Raw Log Widget
        self.investigation_widget = EventInvestigationWidget()
        self.investigation_widget.pivot_filter_requested.connect(self._on_pivot_filter)
        self.investigation_widget.entity_pivot_requested.connect(self._on_entity_pivot)
        self.investigation_widget.raw_log_load_requested.connect(self._on_load_raw_log)
        self.investigation_widget.enriched_udm_requested.connect(self._on_fetch_enriched_udm)
        splitter.addWidget(self.investigation_widget)

        splitter.setSizes([750, 650])
        main_layout.addWidget(splitter, stretch=1)

    def _get_time_window(self) -> tuple[str, str]:
        now = datetime.now(timezone.utc)
        idx = self.time_combo.currentIndex()
        if idx == 0:
            start = now - timedelta(hours=24)
        elif idx == 1:
            start = now - timedelta(hours=48)
        elif idx == 2:
            start = now - timedelta(days=7)
        else:
            start = now - timedelta(days=30)
        return start.strftime("%Y-%m-%dT%H:%M:%SZ"), now.strftime("%Y-%m-%dT%H:%M:%SZ")

    @Slot()
    def _on_search_clicked(self):
        query = self.query_input.text().strip()
        if not query:
            return

        start_time, end_time = self._get_time_window()
        req = SearchRequest(
            query=query,
            start_time=start_time,
            end_time=end_time,
            receive_limit=self.limit_spin.value(),
            batch_size=int(self.batch_combo.currentText()),
        )
        self._start_search_worker(mode="search", search_request=req)

    def _start_search_worker(
        self,
        mode: str = "search",
        search_request: Optional[SearchRequest] = None,
        base_query: Optional[str] = None,
        filters: Optional[list] = None,
        entity_type: Optional[EntityType] = None,
        entity_value: Optional[str] = None,
    ):
        if self._active_search_worker and self._active_search_worker.isRunning():
            self._active_search_worker.cancel()
            self._active_search_worker.wait()

        self.table_model.clear()
        self.investigation_widget.clear()
        self.results_count_label.setText("0 events")
        self._current_selected_row = -1
        self._search_start_time = time.time()
        self._time_to_first_row = None

        self.search_btn.setEnabled(False)
        self.cancel_btn.setEnabled(True)
        self.search_started.emit()

        self._active_search_worker = SearchWorker(
            engine=self.engine,
            mode=mode,
            search_request=search_request,
            base_query=base_query,
            filters=filters,
            entity_type=entity_type,
            entity_value=entity_value,
            parent=self,
        )
        self._active_search_worker.batch_received.connect(self._on_batch_received)
        self._active_search_worker.search_completed.connect(self._on_search_completed)
        self._active_search_worker.search_failed.connect(self._on_search_failed)
        self._active_search_worker.start()

    @Slot()
    def _on_cancel_clicked(self):
        if self._active_search_worker and self._active_search_worker.isRunning():
            self._active_search_worker.cancel()

    @Slot(list, int)
    def _on_batch_received(self, events: list, total_received: int):
        if self._time_to_first_row is None and events:
            self._time_to_first_row = time.time() - self._search_start_time
            self.time_to_first_row_updated.emit(self._time_to_first_row)
        self.table_model.append_events(events)
        self.results_count_label.setText(f"{self.table_model.rowCount()} events")

    @Slot(object)
    def _on_search_completed(self, session: SearchSession):
        self.search_btn.setEnabled(True)
        self.cancel_btn.setEnabled(False)
        self.search_finished.emit(session)

    @Slot(str)
    def _on_search_failed(self, error_message: str):
        self.search_btn.setEnabled(True)
        self.cancel_btn.setEnabled(False)
        QMessageBox.critical(self, "Search Error", f"Workflow execution failed:\n\n{error_message}")

    @Slot(QModelIndex)
    def _on_table_clicked(self, index: QModelIndex):
        if not index.isValid():
            return
        row = index.row()
        self._investigate_row(row)

    def _investigate_row(self, row: int):
        if row == self._current_selected_row:
            return
        self._current_selected_row = row

        event = self.table_model.get_event(row)
        if not event:
            return

        if self._active_inv_worker and self._active_inv_worker.isRunning():
            self._active_inv_worker.wait()

        self._active_inv_worker = InvestigationWorker(
            engine=self.engine,
            event=event,
            eager_raw_log=False,
            parent=self,
        )
        self._active_inv_worker.investigation_completed.connect(self._on_investigation_ready)
        self._active_inv_worker.investigation_failed.connect(self._on_investigation_failed)
        self._active_inv_worker.start()

    @Slot(object)
    def _on_investigation_ready(self, investigation: EventInvestigation):
        self.investigation_widget.display_investigation(investigation)

    @Slot(str)
    def _on_investigation_failed(self, err: str):
        self.status_message_requested.emit(f"Investigation failed: {err}", 5000)

    @Slot(object)
    def _on_load_raw_log(self, investigation: EventInvestigation):
        if self._active_raw_log_worker and self._active_raw_log_worker.isRunning():
            self._active_raw_log_worker.wait()

        self._active_raw_log_worker = RawLogWorker(
            investigation=investigation,
            parent=self,
        )
        self._active_raw_log_worker.raw_log_loaded.connect(self.investigation_widget.display_raw_log)
        self._active_raw_log_worker.raw_log_failed.connect(self.investigation_widget.set_raw_log_error)
        self._active_raw_log_worker.start()

    @Slot(str)
    def _on_fetch_enriched_udm(self, event_id: str):
        if self._active_enriched_worker and self._active_enriched_worker.isRunning():
            self._active_enriched_worker.wait()

        self._active_enriched_worker = EnrichedEventWorker(
            engine=self.engine,
            event_id=event_id,
            parent=self,
        )

        def _on_enriched_ready(enriched_dict: dict):
            if self.investigation_widget._current_investigation:
                self.investigation_widget._current_investigation.event = enriched_dict
                self.investigation_widget.display_investigation(self.investigation_widget._current_investigation)
            self.investigation_widget.fetch_enriched_btn.setEnabled(True)
            self.investigation_widget.fetch_enriched_btn.setText("Fetch Enriched UDM")
            self.status_message_requested.emit(f"Enriched UDM loaded for event: {event_id}", 4000)

        def _on_enriched_failed(err_msg: str):
            self.investigation_widget.fetch_enriched_btn.setEnabled(True)
            self.investigation_widget.fetch_enriched_btn.setText("Fetch Enriched UDM")
            self.status_message_requested.emit(f"Enriched UDM fetch failed: {err_msg}", 5000)

        self._active_enriched_worker.enriched_event_loaded.connect(_on_enriched_ready)
        self._active_enriched_worker.enriched_event_failed.connect(_on_enriched_failed)
        self._active_enriched_worker.start()

    @Slot(object)
    def _on_pivot_filter(self, field_filter: FieldFilter):
        current_query = self.query_input.text().strip()
        clause = field_filter.to_udm_clause()
        refined_query = f"{current_query} AND ({clause})"
        self.query_input.setText(refined_query)

        start_time, end_time = self._get_time_window()
        req = SearchRequest(
            query=refined_query,
            start_time=start_time,
            end_time=end_time,
            receive_limit=self.limit_spin.value(),
            batch_size=int(self.batch_combo.currentText()),
        )
        self._start_search_worker(mode="search", search_request=req)

    @Slot(object, str)
    def _on_entity_pivot(self, entity_type: EntityType, entity_value: str):
        from engine.workflows.refine_search import SearchFromEntityWorkflow
        entity_query = SearchFromEntityWorkflow.build_entity_query(entity_type, entity_value)
        self.query_input.setText(entity_query)

        start_time, end_time = self._get_time_window()
        req = SearchRequest(
            query=entity_query,
            start_time=start_time,
            end_time=end_time,
            receive_limit=self.limit_spin.value(),
            batch_size=int(self.batch_combo.currentText()),
        )
        self._start_search_worker(mode="search", search_request=req)
