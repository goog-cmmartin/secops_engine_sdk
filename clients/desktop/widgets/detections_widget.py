"""Curated Detections and Rulesets Explorer Widget."""

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

from clients.desktop.models import CuratedRulesetTableModel, GenericItemTableModel
from clients.desktop.workers import CuratedDetectionSearchWorker
from engine import CuratedRuleSetBatch, SecOpsEngine


class DetectionsWidget(QWidget):
    """Encapsulates Curated Detection rulesets, rule definitions, and metrics."""

    status_message_requested = Signal(str, int)

    def __init__(self, engine: SecOpsEngine, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.engine = engine
        self.ruleset_model = CuratedRulesetTableModel(self)

        self._active_search_worker: Optional[CuratedDetectionSearchWorker] = None

        self._init_ui()

    def _init_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(8, 8, 8, 8)
        main_layout.setSpacing(6)

        # 1. Top Search Bar
        filter_group = QGroupBox("Curated Detection Ruleset Discovery")
        filter_layout = QHBoxLayout(filter_group)
        filter_layout.setContentsMargins(6, 6, 6, 6)

        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Search curated rulesets (e.g. Cloud Threats, Malware, Identity)...")
        self.search_input.returnPressed.connect(self._on_search_clicked)
        filter_layout.addWidget(self.search_input, stretch=1)

        self.search_btn = QPushButton("Search Rulesets")
        self.search_btn.setStyleSheet("font-weight: bold; padding: 6px 16px;")
        self.search_btn.clicked.connect(self._on_search_clicked)
        filter_layout.addWidget(self.search_btn)
        main_layout.addWidget(filter_group)

        # 2. Main Splitter: Rulesets Table + Detail Pane
        splitter = QSplitter(Qt.Orientation.Horizontal)

        left_widget = QWidget()
        left_layout = QVBoxLayout(left_widget)
        left_layout.setContentsMargins(0, 0, 0, 0)

        header_row = QHBoxLayout()
        self.count_label = QLabel("0 rulesets")
        self.count_label.setStyleSheet("font-weight: bold;")
        header_row.addWidget(QLabel("Curated Rulesets:"))
        header_row.addWidget(self.count_label)
        header_row.addStretch()
        left_layout.addLayout(header_row)

        self.table_view = QTableView()
        self.table_view.setModel(self.ruleset_model)
        self.table_view.setSelectionBehavior(QTableView.SelectionBehavior.SelectRows)
        self.table_view.setSelectionMode(QTableView.SelectionMode.SingleSelection)
        self.table_view.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        self.table_view.horizontalHeader().setStretchLastSection(True)
        self.table_view.clicked.connect(self._on_table_clicked)
        left_layout.addWidget(self.table_view)
        splitter.addWidget(left_widget)

        # Right: Detail & Metrics
        right_widget = QWidget()
        right_layout = QVBoxLayout(right_widget)
        right_layout.setContentsMargins(0, 0, 0, 0)

        self.detail_text = QTextEdit()
        self.detail_text.setReadOnly(True)
        self.detail_text.setFont(QFont("Monospace", 9))
        right_layout.addWidget(self.detail_text)
        splitter.addWidget(right_widget)

        splitter.setSizes([700, 700])
        main_layout.addWidget(splitter, stretch=1)

    @Slot()
    def _on_search_clicked(self):
        query = self.search_input.text().strip()
        self.search_btn.setEnabled(False)
        self.status_message_requested.emit("Searching curated rulesets...", 2000)

        if self._active_search_worker and self._active_search_worker.isRunning():
            self._active_search_worker.wait()

        self._active_search_worker = CuratedDetectionSearchWorker(
            engine=self.engine,
            query=query,
            limit=100,
            parent=self,
        )
        self._active_search_worker.rulesets_loaded.connect(self._on_rulesets_loaded)
        self._active_search_worker.search_failed.connect(self._on_search_failed)
        self._active_search_worker.start()

    @Slot(object)
    def _on_rulesets_loaded(self, batch: CuratedRuleSetBatch):
        self.search_btn.setEnabled(True)
        self.ruleset_model.set_items(batch.items)
        self.count_label.setText(f"{len(batch.items)} rulesets")
        self.status_message_requested.emit(f"Loaded {len(batch.items)} curated rulesets", 3000)

    @Slot(str)
    def _on_search_failed(self, err: str):
        self.search_btn.setEnabled(True)
        QMessageBox.warning(self, "Ruleset Search Failed", f"Error searching curated rulesets:\n\n{err}")

    @Slot(QModelIndex)
    def _on_table_clicked(self, index: QModelIndex):
        if not index.isValid():
            return
        item = self.ruleset_model.get_item(index.row())
        if not item:
            return

        lines = [
            f"Ruleset ID:     {getattr(item, 'ruleset_id', '-')}",
            f"Display Name:   {getattr(item, 'display_name', '-')}",
            f"Category:       {getattr(item, 'category', '-')}",
            f"Rule Count:     {getattr(item, 'rule_count', 0)}",
            f"Precision:      {getattr(item, 'precision', '-')}",
            f"Description:    {getattr(item, 'description', 'None')}",
        ]
        self.detail_text.setText("\n".join(lines))
