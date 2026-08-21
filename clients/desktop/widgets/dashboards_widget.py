"""SIEM Dashboards Explorer and Query Execution Widget."""

from datetime import datetime, timedelta, timezone
from typing import Optional

from PySide6.QtCore import QModelIndex, Qt, Signal, Slot
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QSplitter,
    QTableView,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from clients.desktop.models import DashboardTableModel, GenericItemTableModel
from clients.desktop.workers import DashboardQueryWorker, DashboardSearchWorker
from engine import DashboardBatch, DashboardQueryResult, SecOpsEngine


class DashboardsWidget(QWidget):
    """Encapsulates SIEM Dashboard discovery and ad-hoc dashboard query execution."""

    status_message_requested = Signal(str, int)

    def __init__(self, engine: SecOpsEngine, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.engine = engine
        self.dashboard_model = DashboardTableModel(self)

        self._active_search_worker: Optional[DashboardSearchWorker] = None
        self._active_query_worker: Optional[DashboardQueryWorker] = None

        self._init_ui()

    def _init_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(8, 8, 8, 8)
        main_layout.setSpacing(6)

        # 1. Dashboard Discovery Bar
        filter_group = QGroupBox("SIEM Dashboards Search")
        filter_layout = QHBoxLayout(filter_group)
        filter_layout.setContentsMargins(6, 6, 6, 6)

        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Search dashboards by display name or ID...")
        self.search_input.returnPressed.connect(self._on_search_clicked)
        filter_layout.addWidget(self.search_input, stretch=1)

        self.search_btn = QPushButton("Search Dashboards")
        self.search_btn.setStyleSheet("font-weight: bold; padding: 6px 16px;")
        self.search_btn.clicked.connect(self._on_search_clicked)
        filter_layout.addWidget(self.search_btn)
        main_layout.addWidget(filter_group)

        # 2. Main Splitter: Dashboards Table + Query Workbench & Detail
        splitter = QSplitter(Qt.Orientation.Horizontal)

        left_widget = QWidget()
        left_layout = QVBoxLayout(left_widget)
        left_layout.setContentsMargins(0, 0, 0, 0)

        header_row = QHBoxLayout()
        self.count_label = QLabel("0 dashboards")
        self.count_label.setStyleSheet("font-weight: bold;")
        header_row.addWidget(QLabel("Catalog:"))
        header_row.addWidget(self.count_label)
        header_row.addStretch()
        left_layout.addLayout(header_row)

        self.table_view = QTableView()
        self.table_view.setModel(self.dashboard_model)
        self.table_view.setSelectionBehavior(QTableView.SelectionBehavior.SelectRows)
        self.table_view.setSelectionMode(QTableView.SelectionMode.SingleSelection)
        self.table_view.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        self.table_view.horizontalHeader().setStretchLastSection(True)
        self.table_view.clicked.connect(self._on_table_clicked)
        left_layout.addWidget(self.table_view)
        splitter.addWidget(left_widget)

        # Right: Dashboard Query Workbench
        right_widget = QWidget()
        right_layout = QVBoxLayout(right_widget)
        right_layout.setContentsMargins(0, 0, 0, 0)

        query_group = QGroupBox("Ad-hoc Dashboard Query Runner")
        query_layout = QVBoxLayout(query_group)
        query_layout.setContentsMargins(6, 6, 6, 6)

        self.query_input = QLineEdit()
        self.query_input.setPlaceholderText("Enter dashboard SQL/Aggregation query...")
        self.query_input.returnPressed.connect(self._on_run_query)
        font = QFont("Monospace", 9)
        self.query_input.setFont(font)
        query_layout.addWidget(self.query_input)

        run_row = QHBoxLayout()
        run_row.addStretch()
        self.run_query_btn = QPushButton("Execute Query")
        self.run_query_btn.clicked.connect(self._on_run_query)
        run_row.addWidget(self.run_query_btn)
        query_layout.addLayout(run_row)
        right_layout.addWidget(query_group)

        self.output_text = QTextEdit()
        self.output_text.setReadOnly(True)
        self.output_text.setFont(QFont("Monospace", 9))
        right_layout.addWidget(self.output_text, stretch=1)

        splitter.addWidget(right_widget)
        splitter.setSizes([600, 800])
        main_layout.addWidget(splitter, stretch=1)

    @Slot()
    def _on_search_clicked(self):
        query = self.search_input.text().strip()
        self.search_btn.setEnabled(False)
        self.status_message_requested.emit("Searching dashboards...", 2000)

        if self._active_search_worker and self._active_search_worker.isRunning():
            self._active_search_worker.wait()

        self._active_search_worker = DashboardSearchWorker(
            engine=self.engine,
            query=query,
            limit=100,
            parent=self,
        )
        self._active_search_worker.dashboards_loaded.connect(self._on_dashboards_loaded)
        self._active_search_worker.search_failed.connect(self._on_search_failed)
        self._active_search_worker.start()

    @Slot(object)
    def _on_dashboards_loaded(self, batch: DashboardBatch):
        self.search_btn.setEnabled(True)
        self.dashboard_model.set_items(batch.items)
        self.count_label.setText(f"{len(batch.items)} dashboards")
        self.status_message_requested.emit(f"Loaded {len(batch.items)} dashboards", 3000)

    @Slot(str)
    def _on_search_failed(self, err: str):
        self.search_btn.setEnabled(True)
        QMessageBox.warning(self, "Dashboard Search Failed", f"Error searching dashboards:\n\n{err}")

    @Slot(QModelIndex)
    def _on_table_clicked(self, index: QModelIndex):
        if not index.isValid():
            return
        item = self.dashboard_model.get_item(index.row())
        if not item:
            return

        lines = [
            f"Dashboard ID:   {getattr(item, 'dashboard_id', '-')}",
            f"Display Name:   {getattr(item, 'display_name', '-')}",
            f"Type:           {getattr(item, 'dashboard_type', '-')}",
            f"Charts:         {getattr(item, 'chart_count', 0)}",
            f"Modified Time:  {getattr(item, 'modified_time', '-')}",
            f"Description:    {getattr(item, 'description', 'None')}",
        ]
        self.output_text.setText("\n".join(lines))

    @Slot()
    def _on_run_query(self):
        query = self.query_input.text().strip()
        if not query:
            return

        now = datetime.now(timezone.utc)
        start = (now - timedelta(hours=24)).strftime("%Y-%m-%dT%H:%M:%SZ")
        end = now.strftime("%Y-%m-%dT%H:%M:%SZ")

        self.run_query_btn.setEnabled(False)
        self.status_message_requested.emit("Executing dashboard query...", 2000)

        if self._active_query_worker and self._active_query_worker.isRunning():
            self._active_query_worker.wait()

        self._active_query_worker = DashboardQueryWorker(
            engine=self.engine,
            query=query,
            start_time=start,
            end_time=end,
            parent=self,
        )

        def _on_query_executed(result: DashboardQueryResult):
            self.run_query_btn.setEnabled(True)
            lines = [
                f"Query Execution Status: SUCCESS",
                f"Total Rows:             {result.total_rows}",
                f"Columns:                {', '.join(result.columns)}",
                "",
                "Rows:",
            ]
            for r in result.rows[:50]:
                lines.append(str(r))
            self.output_text.setText("\n".join(lines))
            self.status_message_requested.emit("Query execution complete", 3000)

        def _on_query_failed(err: str):
            self.run_query_btn.setEnabled(True)
            self.output_text.setText(f"Query execution failed:\n{err}")
            self.status_message_requested.emit(f"Query execution failed: {err}", 5000)

        self._active_query_worker.query_executed.connect(_on_query_executed)
        self._active_query_worker.query_failed.connect(_on_query_failed)
        self._active_query_worker.start()
