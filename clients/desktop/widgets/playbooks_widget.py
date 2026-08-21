"""SOAR Playbooks and Automations Explorer Widget."""

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
    QSplitter,
    QTabWidget,
    QTableView,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from clients.desktop.models import GenericItemTableModel, PlaybookTableModel
from clients.desktop.workers import PlaybookDetailWorker, PlaybookSearchWorker
from engine import PlaybookBatch, PlaybookDetail, SecOpsEngine


class PlaybooksWidget(QWidget):
    """Encapsulates SOAR Playbook discovery, trigger conditions, and step execution DAG."""

    status_message_requested = Signal(str, int)

    def __init__(self, engine: SecOpsEngine, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.engine = engine
        self.table_model = PlaybookTableModel(self)

        self._active_search_worker: Optional[PlaybookSearchWorker] = None
        self._active_detail_worker: Optional[PlaybookDetailWorker] = None

        self._init_ui()

    def _init_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(8, 8, 8, 8)
        main_layout.setSpacing(6)

        # 1. Top Search & Controls
        filter_group = QGroupBox("SOAR Playbook Search")
        filter_layout = QHBoxLayout(filter_group)
        filter_layout.setContentsMargins(6, 6, 6, 6)

        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Search playbooks by name or keyword...")
        self.search_input.returnPressed.connect(self._on_search_clicked)
        filter_layout.addWidget(self.search_input, stretch=1)

        self.search_btn = QPushButton("Search Playbooks")
        self.search_btn.setStyleSheet("font-weight: bold; padding: 6px 16px;")
        self.search_btn.clicked.connect(self._on_search_clicked)
        filter_layout.addWidget(self.search_btn)
        main_layout.addWidget(filter_group)

        # 2. Main Splitter: Playbook Table + Playbook Detail Pane
        splitter = QSplitter(Qt.Orientation.Horizontal)

        left_widget = QWidget()
        left_layout = QVBoxLayout(left_widget)
        left_layout.setContentsMargins(0, 0, 0, 0)

        header_row = QHBoxLayout()
        self.count_label = QLabel("0 playbooks")
        self.count_label.setStyleSheet("font-weight: bold;")
        header_row.addWidget(QLabel("Catalog:"))
        header_row.addWidget(self.count_label)
        header_row.addStretch()
        left_layout.addLayout(header_row)

        self.table_view = QTableView()
        self.table_view.setModel(self.table_model)
        self.table_view.setSelectionBehavior(QTableView.SelectionBehavior.SelectRows)
        self.table_view.setSelectionMode(QTableView.SelectionMode.SingleSelection)
        self.table_view.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        self.table_view.horizontalHeader().setStretchLastSection(True)
        self.table_view.clicked.connect(self._on_table_clicked)
        left_layout.addWidget(self.table_view)
        splitter.addWidget(left_widget)

        # Right: Detail Tabs
        right_widget = QWidget()
        right_layout = QVBoxLayout(right_widget)
        right_layout.setContentsMargins(0, 0, 0, 0)

        self.tabs = QTabWidget()

        # Tab 1: Overview & Triggers
        self.overview_text = QTextEdit()
        self.overview_text.setReadOnly(True)
        self.overview_text.setFont(QFont("Monospace", 9))
        self.tabs.addTab(self.overview_text, "Overview & Trigger")

        # Tab 2: Step DAG Table
        self.steps_model = GenericItemTableModel(["Step ID", "Step Name", "Action / Integration", "Type", "On Failure"])
        self.steps_table = QTableView()
        self.steps_table.setModel(self.steps_model)
        self.steps_table.horizontalHeader().setStretchLastSection(True)
        self.tabs.addTab(self.steps_table, "Execution Steps (DAG)")

        right_layout.addWidget(self.tabs)
        splitter.addWidget(right_widget)

        splitter.setSizes([600, 800])
        main_layout.addWidget(splitter, stretch=1)

    @Slot()
    def _on_search_clicked(self):
        query = self.search_input.text().strip()
        self.search_btn.setEnabled(False)
        self.status_message_requested.emit("Searching playbooks...", 2000)

        if self._active_search_worker and self._active_search_worker.isRunning():
            self._active_search_worker.wait()

        self._active_search_worker = PlaybookSearchWorker(
            engine=self.engine,
            query=query,
            limit=100,
            parent=self,
        )
        self._active_search_worker.playbooks_loaded.connect(self._on_playbooks_loaded)
        self._active_search_worker.search_failed.connect(self._on_search_failed)
        self._active_search_worker.start()

    @Slot(object)
    def _on_playbooks_loaded(self, batch: PlaybookBatch):
        self.search_btn.setEnabled(True)
        self.table_model.set_items(batch.items)
        self.count_label.setText(f"{len(batch.items)} playbooks")
        self.status_message_requested.emit(f"Loaded {len(batch.items)} playbooks", 3000)

    @Slot(str)
    def _on_search_failed(self, err: str):
        self.search_btn.setEnabled(True)
        QMessageBox.warning(self, "Playbook Search Failed", f"Error searching playbooks:\n\n{err}")

    @Slot(QModelIndex)
    def _on_table_clicked(self, index: QModelIndex):
        if not index.isValid():
            return
        item = self.table_model.get_item(index.row())
        if not item:
            return

        playbook_id = getattr(item, "playbook_id", getattr(item, "id", str(item)))
        self._load_playbook_detail(playbook_id)

    def _load_playbook_detail(self, playbook_id: str):
        if self._active_detail_worker and self._active_detail_worker.isRunning():
            self._active_detail_worker.wait()

        self.status_message_requested.emit(f"Loading playbook {playbook_id}...", 2000)
        self._active_detail_worker = PlaybookDetailWorker(
            engine=self.engine,
            playbook_id=playbook_id,
            parent=self,
        )
        self._active_detail_worker.detail_loaded.connect(self._on_detail_loaded)
        self._active_detail_worker.detail_failed.connect(self._on_detail_failed)
        self._active_detail_worker.start()

    @Slot(object)
    def _on_detail_loaded(self, detail: PlaybookDetail):
        lines = [
            f"Playbook ID:    {detail.playbook_id}",
            f"Name:           {detail.name}",
            f"Category:       {detail.category}",
            f"Trigger Type:   {detail.trigger_type}",
            f"Enabled:        {detail.is_enabled}",
            f"Created Time:   {detail.created_time}",
            f"Modified Time:  {detail.modified_time}",
            f"Description:    {detail.description or 'None'}",
            "",
            f"Total Steps:    {len(detail.steps)}",
        ]
        if detail.trigger:
            lines.append(f"Trigger Environments: {', '.join(detail.trigger.environments) if detail.trigger.environments else 'All'}")
            lines.append(f"Trigger Conditions:   {len(detail.trigger.conditions)} rule(s)")

        self.overview_text.setText("\n".join(lines))

        # Steps table
        step_rows = []
        for s in detail.steps:
            action_desc = f"{s.integration_name}.{s.action_name}" if s.integration_name else s.action_name
            step_rows.append([
                str(s.step_id),
                str(s.name),
                str(action_desc),
                str(s.step_type),
                str(s.on_failure or "-"),
            ])
        self.steps_model.set_rows(step_rows)
        self.status_message_requested.emit(f"Playbook {detail.name} loaded", 3000)

    @Slot(str)
    def _on_detail_failed(self, err: str):
        self.overview_text.setText(f"Failed to load playbook detail:\n{err}")
        self.status_message_requested.emit(f"Playbook detail load failed: {err}", 5000)
