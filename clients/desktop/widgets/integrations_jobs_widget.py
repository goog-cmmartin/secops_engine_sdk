"""SOAR Integrations, Remote Agents, and Scheduled Jobs Widget."""

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
    QTabWidget,
    QTableView,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from clients.desktop.models import GenericItemTableModel, IntegrationTableModel, JobTableModel
from clients.desktop.workers import IntegrationSearchWorker, JobSearchWorker
from engine import IntegrationBatch, JobBatch, SecOpsEngine


class IntegrationsJobsWidget(QWidget):
    """Encapsulates SOAR Integrations, Instances, Remote Agents, and Scheduled Jobs."""

    status_message_requested = Signal(str, int)

    def __init__(self, engine: SecOpsEngine, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.engine = engine

        self.integration_model = IntegrationTableModel(self)
        self.job_model = JobTableModel(self)

        self._active_int_worker: Optional[IntegrationSearchWorker] = None
        self._active_job_worker: Optional[JobSearchWorker] = None

        self._init_ui()

    def _init_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(8, 8, 8, 8)
        main_layout.setSpacing(6)

        self.main_tabs = QTabWidget()

        # Tab 1: Integrations View
        int_widget = QWidget()
        int_layout = QVBoxLayout(int_widget)
        int_layout.setContentsMargins(4, 4, 4, 4)

        int_filter_group = QGroupBox("SOAR Integrations Search")
        int_filter_layout = QHBoxLayout(int_filter_group)
        self.int_search_input = QLineEdit()
        self.int_search_input.setPlaceholderText("Search integrations by name, identifier, or category...")
        self.int_search_input.returnPressed.connect(self._on_search_integrations)
        int_filter_layout.addWidget(self.int_search_input, stretch=1)

        self.int_search_btn = QPushButton("Search Integrations")
        self.int_search_btn.setStyleSheet("font-weight: bold; padding: 6px 16px;")
        self.int_search_btn.clicked.connect(self._on_search_integrations)
        int_filter_layout.addWidget(self.int_search_btn)
        int_layout.addWidget(int_filter_group)

        int_splitter = QSplitter(Qt.Orientation.Horizontal)
        self.int_table = QTableView()
        self.int_table.setModel(self.integration_model)
        self.int_table.setSelectionBehavior(QTableView.SelectionBehavior.SelectRows)
        self.int_table.setSelectionMode(QTableView.SelectionMode.SingleSelection)
        self.int_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        self.int_table.horizontalHeader().setStretchLastSection(True)
        self.int_table.clicked.connect(self._on_int_clicked)
        int_splitter.addWidget(self.int_table)

        self.int_detail_text = QTextEdit()
        self.int_detail_text.setReadOnly(True)
        self.int_detail_text.setFont(QFont("Monospace", 9))
        int_splitter.addWidget(self.int_detail_text)
        int_splitter.setSizes([700, 700])

        int_layout.addWidget(int_splitter, stretch=1)
        self.main_tabs.addTab(int_widget, "Integrations & Remote Agents")

        # Tab 2: Scheduled Jobs View
        job_widget = QWidget()
        job_layout = QVBoxLayout(job_widget)
        job_layout.setContentsMargins(4, 4, 4, 4)

        job_filter_group = QGroupBox("SOAR Scheduled Jobs Search")
        job_filter_layout = QHBoxLayout(job_filter_group)
        self.job_search_input = QLineEdit()
        self.job_search_input.setPlaceholderText("Search jobs by identifier or display name...")
        self.job_search_input.returnPressed.connect(self._on_search_jobs)
        job_filter_layout.addWidget(self.job_search_input, stretch=1)

        self.job_search_btn = QPushButton("Search Jobs")
        self.job_search_btn.setStyleSheet("font-weight: bold; padding: 6px 16px;")
        self.job_search_btn.clicked.connect(self._on_search_jobs)
        job_filter_layout.addWidget(self.job_search_btn)
        job_layout.addWidget(job_filter_group)

        job_splitter = QSplitter(Qt.Orientation.Horizontal)
        self.job_table = QTableView()
        self.job_table.setModel(self.job_model)
        self.job_table.setSelectionBehavior(QTableView.SelectionBehavior.SelectRows)
        self.job_table.setSelectionMode(QTableView.SelectionMode.SingleSelection)
        self.job_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        self.job_table.horizontalHeader().setStretchLastSection(True)
        self.job_table.clicked.connect(self._on_job_clicked)
        job_splitter.addWidget(self.job_table)

        self.job_detail_text = QTextEdit()
        self.job_detail_text.setReadOnly(True)
        self.job_detail_text.setFont(QFont("Monospace", 9))
        job_splitter.addWidget(self.job_detail_text)
        job_splitter.setSizes([700, 700])

        job_layout.addWidget(job_splitter, stretch=1)
        self.main_tabs.addTab(job_widget, "Scheduled Jobs")

        main_layout.addWidget(self.main_tabs)

    @Slot()
    def _on_search_integrations(self):
        query = self.int_search_input.text().strip()
        self.int_search_btn.setEnabled(False)
        self.status_message_requested.emit("Searching integrations...", 2000)

        if self._active_int_worker and self._active_int_worker.isRunning():
            self._active_int_worker.wait()

        self._active_int_worker = IntegrationSearchWorker(
            engine=self.engine,
            query=query,
            limit=100,
            parent=self,
        )
        self._active_int_worker.integrations_loaded.connect(self._on_integrations_loaded)
        self._active_int_worker.search_failed.connect(self._on_int_failed)
        self._active_int_worker.start()

    @Slot(object)
    def _on_integrations_loaded(self, batch: IntegrationBatch):
        self.int_search_btn.setEnabled(True)
        self.integration_model.set_items(batch.items)
        self.status_message_requested.emit(f"Loaded {len(batch.items)} integrations", 3000)

    @Slot(str)
    def _on_int_failed(self, err: str):
        self.int_search_btn.setEnabled(True)
        QMessageBox.warning(self, "Integration Search Failed", f"Error searching integrations:\n\n{err}")

    @Slot(QModelIndex)
    def _on_int_clicked(self, index: QModelIndex):
        if not index.isValid():
            return
        item = self.integration_model.get_item(index.row())
        if not item:
            return

        lines = [
            f"Identifier:     {getattr(item, 'identifier', '-')}",
            f"Display Name:   {getattr(item, 'display_name', '-')}",
            f"Category:       {getattr(item, 'category', '-')}",
            f"Instances:      {getattr(item, 'instance_count', 0)}",
            f"Certified:      {getattr(item, 'is_certified', False)}",
            f"Description:    {getattr(item, 'description', 'None')}",
        ]
        self.int_detail_text.setText("\n".join(lines))

    @Slot()
    def _on_search_jobs(self):
        query = self.job_search_input.text().strip()
        self.job_search_btn.setEnabled(False)
        self.status_message_requested.emit("Searching scheduled jobs...", 2000)

        if self._active_job_worker and self._active_job_worker.isRunning():
            self._active_job_worker.wait()

        self._active_job_worker = JobSearchWorker(
            engine=self.engine,
            query=query,
            limit=100,
            parent=self,
        )
        self._active_job_worker.jobs_loaded.connect(self._on_jobs_loaded)
        self._active_job_worker.search_failed.connect(self._on_job_failed)
        self._active_job_worker.start()

    @Slot(object)
    def _on_jobs_loaded(self, batch: JobBatch):
        self.job_search_btn.setEnabled(True)
        self.job_model.set_items(batch.items)
        self.status_message_requested.emit(f"Loaded {len(batch.items)} jobs", 3000)

    @Slot(str)
    def _on_job_failed(self, err: str):
        self.job_search_btn.setEnabled(True)
        QMessageBox.warning(self, "Job Search Failed", f"Error searching jobs:\n\n{err}")

    @Slot(QModelIndex)
    def _on_job_clicked(self, index: QModelIndex):
        if not index.isValid():
            return
        item = self.job_model.get_item(index.row())
        if not item:
            return

        lines = [
            f"Job Identifier: {getattr(item, 'identifier', '-')}",
            f"Display Name:   {getattr(item, 'display_name', '-')}",
            f"Interval (s):   {getattr(item, 'interval_seconds', '-')}",
            f"Enabled:        {getattr(item, 'is_enabled', False)}",
            f"Running Status: {getattr(item, 'running_status', '-')}",
            f"Modified Time:  {getattr(item, 'modified_time', '-')}",
            f"Description:    {getattr(item, 'description', 'None')}",
        ]
        self.job_detail_text.setText("\n".join(lines))
