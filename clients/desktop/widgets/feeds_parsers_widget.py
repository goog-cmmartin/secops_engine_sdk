"""SIEM Ingestion Feeds, Log Pipelines, and Parsers Widget."""

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

from clients.desktop.models import FeedTableModel, ParserTableModel
from clients.desktop.workers import FeedSearchWorker, ParserSearchWorker
from engine import FeedBatch, ParserBatch, SecOpsEngine


class FeedsParsersWidget(QWidget):
    """Encapsulates Ingestion Feeds, Log Processing Pipelines, Parsers, and Extensions."""

    status_message_requested = Signal(str, int)

    def __init__(self, engine: SecOpsEngine, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.engine = engine

        self.feed_model = FeedTableModel(self)
        self.parser_model = ParserTableModel(self)

        self._active_feed_worker: Optional[FeedSearchWorker] = None
        self._active_parser_worker: Optional[ParserSearchWorker] = None

        self._init_ui()

    def _init_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(8, 8, 8, 8)
        main_layout.setSpacing(6)

        self.main_tabs = QTabWidget()

        # Tab 1: Ingestion Feeds
        feed_widget = QWidget()
        feed_layout = QVBoxLayout(feed_widget)
        feed_layout.setContentsMargins(4, 4, 4, 4)

        feed_filter_group = QGroupBox("Ingestion Feeds Search")
        feed_filter_layout = QHBoxLayout(feed_filter_group)
        self.feed_search_input = QLineEdit()
        self.feed_search_input.setPlaceholderText("Search feeds by display name, ID, or log type...")
        self.feed_search_input.returnPressed.connect(self._on_search_feeds)
        feed_filter_layout.addWidget(self.feed_search_input, stretch=1)

        self.feed_search_btn = QPushButton("Search Feeds")
        self.feed_search_btn.setStyleSheet("font-weight: bold; padding: 6px 16px;")
        self.feed_search_btn.clicked.connect(self._on_search_feeds)
        feed_filter_layout.addWidget(self.feed_search_btn)
        feed_layout.addWidget(feed_filter_group)

        feed_splitter = QSplitter(Qt.Orientation.Horizontal)
        self.feed_table = QTableView()
        self.feed_table.setModel(self.feed_model)
        self.feed_table.setSelectionBehavior(QTableView.SelectionBehavior.SelectRows)
        self.feed_table.setSelectionMode(QTableView.SelectionMode.SingleSelection)
        self.feed_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        self.feed_table.horizontalHeader().setStretchLastSection(True)
        self.feed_table.clicked.connect(self._on_feed_clicked)
        feed_splitter.addWidget(self.feed_table)

        self.feed_detail_text = QTextEdit()
        self.feed_detail_text.setReadOnly(True)
        self.feed_detail_text.setFont(QFont("Monospace", 9))
        feed_splitter.addWidget(self.feed_detail_text)
        feed_splitter.setSizes([700, 700])

        feed_layout.addWidget(feed_splitter, stretch=1)
        self.main_tabs.addTab(feed_widget, "Ingestion Feeds")

        # Tab 2: Parsers & Extensions
        parser_widget = QWidget()
        parser_layout = QVBoxLayout(parser_widget)
        parser_layout.setContentsMargins(4, 4, 4, 4)

        parser_filter_group = QGroupBox("SIEM Parsers Search")
        parser_filter_layout = QHBoxLayout(parser_filter_group)
        self.parser_search_input = QLineEdit()
        self.parser_search_input.setPlaceholderText("Search parsers by log type or author...")
        self.parser_search_input.returnPressed.connect(self._on_search_parsers)
        parser_filter_layout.addWidget(self.parser_search_input, stretch=1)

        parser_filter_layout.addWidget(QLabel("Type:"))
        self.parser_type_combo = QComboBox()
        self.parser_type_combo.addItems(["ALL", "CUSTOM", "PREBUILT"])
        parser_filter_layout.addWidget(self.parser_type_combo)

        self.parser_search_btn = QPushButton("Search Parsers")
        self.parser_search_btn.setStyleSheet("font-weight: bold; padding: 6px 16px;")
        self.parser_search_btn.clicked.connect(self._on_search_parsers)
        parser_filter_layout.addWidget(self.parser_search_btn)
        parser_layout.addWidget(parser_filter_group)

        parser_splitter = QSplitter(Qt.Orientation.Horizontal)
        self.parser_table = QTableView()
        self.parser_table.setModel(self.parser_model)
        self.parser_table.setSelectionBehavior(QTableView.SelectionBehavior.SelectRows)
        self.parser_table.setSelectionMode(QTableView.SelectionMode.SingleSelection)
        self.parser_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        self.parser_table.horizontalHeader().setStretchLastSection(True)
        self.parser_table.clicked.connect(self._on_parser_clicked)
        parser_splitter.addWidget(self.parser_table)

        self.parser_detail_text = QTextEdit()
        self.parser_detail_text.setReadOnly(True)
        self.parser_detail_text.setFont(QFont("Monospace", 9))
        parser_splitter.addWidget(self.parser_detail_text)
        parser_splitter.setSizes([700, 700])

        parser_layout.addWidget(parser_splitter, stretch=1)
        self.main_tabs.addTab(parser_widget, "Parsers & Extensions")

        main_layout.addWidget(self.main_tabs)

    @Slot()
    def _on_search_feeds(self):
        query = self.feed_search_input.text().strip()
        self.feed_search_btn.setEnabled(False)
        self.status_message_requested.emit("Searching ingestion feeds...", 2000)

        if self._active_feed_worker and self._active_feed_worker.isRunning():
            self._active_feed_worker.wait()

        self._active_feed_worker = FeedSearchWorker(
            engine=self.engine,
            query=query,
            limit=100,
            parent=self,
        )
        self._active_feed_worker.feeds_loaded.connect(self._on_feeds_loaded)
        self._active_feed_worker.search_failed.connect(self._on_feed_failed)
        self._active_feed_worker.start()

    @Slot(object)
    def _on_feeds_loaded(self, batch: FeedBatch):
        self.feed_search_btn.setEnabled(True)
        self.feed_model.set_items(batch.items)
        self.status_message_requested.emit(f"Loaded {len(batch.items)} feeds", 3000)

    @Slot(str)
    def _on_feed_failed(self, err: str):
        self.feed_search_btn.setEnabled(True)
        QMessageBox.warning(self, "Feed Search Failed", f"Error searching feeds:\n\n{err}")

    @Slot(QModelIndex)
    def _on_feed_clicked(self, index: QModelIndex):
        if not index.isValid():
            return
        item = self.feed_model.get_item(index.row())
        if not item:
            return

        lines = [
            f"Feed ID:        {getattr(item, 'feed_id', '-')}",
            f"Display Name:   {getattr(item, 'display_name', '-')}",
            f"Log Type:       {getattr(item, 'log_type', '-')}",
            f"Source Type:    {getattr(item, 'source_type', '-')}",
            f"State:          {getattr(item, 'state', '-')}",
        ]
        self.feed_detail_text.setText("\n".join(lines))

    @Slot()
    def _on_search_parsers(self):
        query = self.parser_search_input.text().strip()
        p_type = self.parser_type_combo.currentText()
        self.parser_search_btn.setEnabled(False)
        self.status_message_requested.emit("Searching parsers...", 2000)

        if self._active_parser_worker and self._active_parser_worker.isRunning():
            self._active_parser_worker.wait()

        self._active_parser_worker = ParserSearchWorker(
            engine=self.engine,
            query=query,
            parser_type=p_type,
            limit=100,
            parent=self,
        )
        self._active_parser_worker.parsers_loaded.connect(self._on_parsers_loaded)
        self._active_parser_worker.search_failed.connect(self._on_parser_failed)
        self._active_parser_worker.start()

    @Slot(object)
    def _on_parsers_loaded(self, batch: ParserBatch):
        self.parser_search_btn.setEnabled(True)
        self.parser_model.set_items(batch.items)
        self.status_message_requested.emit(f"Loaded {len(batch.items)} parsers", 3000)

    @Slot(str)
    def _on_parser_failed(self, err: str):
        self.parser_search_btn.setEnabled(True)
        QMessageBox.warning(self, "Parser Search Failed", f"Error searching parsers:\n\n{err}")

    @Slot(QModelIndex)
    def _on_parser_clicked(self, index: QModelIndex):
        if not index.isValid():
            return
        item = self.parser_model.get_item(index.row())
        if not item:
            return

        lines = [
            f"Log Type:       {getattr(item, 'log_type', '-')}",
            f"State:          {getattr(item, 'state', '-')}",
            f"Parser Type:    {getattr(item, 'parser_type', '-')}",
            f"Author:         {getattr(item, 'author', '-')}",
        ]
        self.parser_detail_text.setText("\n".join(lines))
