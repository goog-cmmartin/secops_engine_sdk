"""SOAR Cases & Security Alerts Investigation Widget."""

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

from clients.desktop.models import CaseTableModel, GenericItemTableModel
from clients.desktop.workers import CaseCommentWorker, CaseInvestigationWorker, CaseSearchWorker
from engine import CaseInvestigation, CaseSearchBatch, SecOpsEngine


class CasesWidget(QWidget):
    """Encapsulates SOAR Case Search, multi-facet filtering, Alert triage, and Comments."""

    status_message_requested = Signal(str, int)

    def __init__(self, engine: SecOpsEngine, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.engine = engine
        self.table_model = CaseTableModel(self)

        self._active_search_worker: Optional[CaseSearchWorker] = None
        self._active_inv_worker: Optional[CaseInvestigationWorker] = None
        self._active_comment_worker: Optional[CaseCommentWorker] = None
        self._current_investigation: Optional[CaseInvestigation] = None

        self._init_ui()

    def _init_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(8, 8, 8, 8)
        main_layout.setSpacing(6)

        # 1. Top Search & Facet Filters
        filter_group = QGroupBox("SOAR Case Search & Filters")
        filter_layout = QVBoxLayout(filter_group)
        filter_layout.setContentsMargins(6, 6, 6, 6)
        filter_layout.setSpacing(6)

        top_row = QHBoxLayout()
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Search cases by title, ID, or keyword...")
        self.search_input.returnPressed.connect(self._on_search_clicked)
        top_row.addWidget(self.search_input, stretch=1)

        self.search_btn = QPushButton("Search Cases")
        self.search_btn.setStyleSheet("font-weight: bold; padding: 6px 16px;")
        self.search_btn.clicked.connect(self._on_search_clicked)
        top_row.addWidget(self.search_btn)
        filter_layout.addLayout(top_row)

        # Facet selectors row
        facet_row = QHBoxLayout()
        facet_row.addWidget(QLabel("Status:"))
        self.status_combo = QComboBox()
        self.status_combo.addItems(["ALL", "OPEN", "CLOSED"])
        facet_row.addWidget(self.status_combo)

        facet_row.addSpacing(12)
        facet_row.addWidget(QLabel("Priority:"))
        self.priority_combo = QComboBox()
        self.priority_combo.addItems(["ALL", "CRITICAL", "HIGH", "MEDIUM", "LOW"])
        facet_row.addWidget(self.priority_combo)

        facet_row.addSpacing(12)
        facet_row.addWidget(QLabel("Stage:"))
        self.stage_input = QLineEdit()
        self.stage_input.setPlaceholderText("e.g. Triage, Containment")
        self.stage_input.setMaximumWidth(160)
        facet_row.addWidget(self.stage_input)

        facet_row.addSpacing(12)
        facet_row.addWidget(QLabel("Assignee:"))
        self.assignee_input = QLineEdit()
        self.assignee_input.setPlaceholderText("Filter user/email")
        self.assignee_input.setMaximumWidth(160)
        facet_row.addWidget(self.assignee_input)

        facet_row.addStretch()
        filter_layout.addLayout(facet_row)
        main_layout.addWidget(filter_group)

        # 2. Main Center Splitter: Cases Table + Case Investigation Inspector
        splitter = QSplitter(Qt.Orientation.Horizontal)

        # Left: Cases Table View
        left_widget = QWidget()
        left_layout = QVBoxLayout(left_widget)
        left_layout.setContentsMargins(0, 0, 0, 0)

        header_row = QHBoxLayout()
        self.results_label = QLabel("0 cases")
        self.results_label.setStyleSheet("font-weight: bold;")
        header_row.addWidget(QLabel("Case Records:"))
        header_row.addWidget(self.results_label)
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

        # Right: Detail & Investigation Tabs
        right_widget = QWidget()
        right_layout = QVBoxLayout(right_widget)
        right_layout.setContentsMargins(0, 0, 0, 0)

        self.tabs = QTabWidget()

        # Tab 1: Case Overview
        self.overview_text = QTextEdit()
        self.overview_text.setReadOnly(True)
        self.overview_text.setFont(QFont("Monospace", 9))
        self.tabs.addTab(self.overview_text, "Overview")

        # Tab 2: Security Alerts Table
        self.alerts_model = GenericItemTableModel(["Alert ID", "Name", "Severity", "Type", "Created"])
        self.alerts_table = QTableView()
        self.alerts_table.setModel(self.alerts_model)
        self.alerts_table.horizontalHeader().setStretchLastSection(True)
        self.tabs.addTab(self.alerts_table, "Security Alerts")

        # Tab 3: Involved Entities Table
        self.entities_model = GenericItemTableModel(["Entity Identifier", "Entity Type", "Role"])
        self.entities_table = QTableView()
        self.entities_table.setModel(self.entities_model)
        self.entities_table.horizontalHeader().setStretchLastSection(True)
        self.tabs.addTab(self.entities_table, "Involved Entities")

        # Tab 4: Comments Feed & Input
        comments_widget = QWidget()
        comments_layout = QVBoxLayout(comments_widget)
        self.comments_feed = QTextEdit()
        self.comments_feed.setReadOnly(True)
        comments_layout.addWidget(self.comments_feed, stretch=1)

        new_comment_box = QHBoxLayout()
        self.comment_input = QLineEdit()
        self.comment_input.setPlaceholderText("Write analyst comment...")
        self.comment_input.returnPressed.connect(self._on_add_comment)
        new_comment_box.addWidget(self.comment_input, stretch=1)

        self.add_comment_btn = QPushButton("Add Comment")
        self.add_comment_btn.clicked.connect(self._on_add_comment)
        new_comment_box.addWidget(self.add_comment_btn)
        comments_layout.addLayout(new_comment_box)
        self.tabs.addTab(comments_widget, "Analyst Comments")

        right_layout.addWidget(self.tabs)
        splitter.addWidget(right_widget)

        splitter.setSizes([650, 750])
        main_layout.addWidget(splitter, stretch=1)

    @Slot()
    def _on_search_clicked(self):
        query = self.search_input.text().strip() or None
        status = self.status_combo.currentText()
        status_val = None if status == "ALL" else status
        priority = self.priority_combo.currentText()
        priority_val = None if priority == "ALL" else priority
        stage = self.stage_input.text().strip() or None
        assignee = self.assignee_input.text().strip() or None

        self.search_btn.setEnabled(False)
        self.status_message_requested.emit("Searching SOAR cases...", 2000)

        if self._active_search_worker and self._active_search_worker.isRunning():
            self._active_search_worker.wait()

        self._active_search_worker = CaseSearchWorker(
            engine=self.engine,
            query=query,
            status=status_val,
            priority=priority_val,
            assignee=assignee,
            stage=stage,
            limit=100,
            parent=self,
        )
        self._active_search_worker.cases_loaded.connect(self._on_cases_loaded)
        self._active_search_worker.search_failed.connect(self._on_search_failed)
        self._active_search_worker.start()

    @Slot(object)
    def _on_cases_loaded(self, batch: CaseSearchBatch):
        self.search_btn.setEnabled(True)
        items = getattr(batch, "items", getattr(batch, "results", []))
        self.table_model.set_items(items)
        self.results_label.setText(f"{len(items)} cases")
        self.status_message_requested.emit(f"Loaded {len(items)} cases", 3000)

    @Slot(str)
    def _on_search_failed(self, err: str):
        self.search_btn.setEnabled(True)
        QMessageBox.warning(self, "Case Search Failed", f"Error searching cases:\n\n{err}")

    @Slot(QModelIndex)
    def _on_table_clicked(self, index: QModelIndex):
        if not index.isValid():
            return
        item = self.table_model.get_item(index.row())
        if not item:
            return

        case_id = getattr(item, "case_id", str(item))
        self._load_case_investigation(case_id)

    def _load_case_investigation(self, case_id: str):
        if self._active_inv_worker and self._active_inv_worker.isRunning():
            self._active_inv_worker.wait()

        self.status_message_requested.emit(f"Loading case investigation for #{case_id}...", 2000)
        self._active_inv_worker = CaseInvestigationWorker(
            engine=self.engine,
            case_id=case_id,
            parent=self,
        )
        self._active_inv_worker.investigation_loaded.connect(self._on_investigation_loaded)
        self._active_inv_worker.investigation_failed.connect(self._on_investigation_failed)
        self._active_inv_worker.start()

    @Slot(object)
    def _on_investigation_loaded(self, inv: CaseInvestigation):
        self._current_investigation = inv
        # Format Overview
        title = getattr(inv, "title", getattr(inv, "display_name", getattr(inv, "name", "")))
        created = getattr(inv, "created_time", getattr(inv, "create_time", "N/A"))
        updated = getattr(inv, "updated_time", getattr(inv, "update_time", "N/A"))
        env = getattr(inv, "environment", "")
        desc = getattr(inv, "description", "")
        alerts = getattr(inv, "alerts", [])
        entities = getattr(inv, "involved_entities", getattr(inv, "entities", []))
        comments = getattr(inv, "comments", [])

        lines = [
            f"Case ID:        {getattr(inv, 'case_id', '')}",
            f"Title:          {title}",
            f"Priority:       {getattr(inv, 'priority', '')}",
            f"Status:         {getattr(inv, 'status', '')}",
            f"Stage:          {getattr(inv, 'stage', '')}",
            f"Assignee:       {getattr(inv, 'assignee', 'Unassigned')}",
            f"Environment:    {env}",
            f"Created Time:   {created}",
            f"Updated Time:   {updated}",
            f"Description:    {desc or 'None'}",
            "",
            f"Total Alerts:   {len(alerts)}",
            f"Total Entities: {len(entities)}",
            f"Total Comments: {len(comments)}",
        ]
        self.overview_text.setText("\n".join(lines))

        # Populate Alerts Table
        alert_rows = []
        for a in alerts:
            aid = getattr(a, "alert_id", getattr(a, "identifier", getattr(a, "name", "")))
            aname = getattr(a, "display_name", getattr(a, "name", ""))
            asev = getattr(a, "severity", getattr(a, "priority", ""))
            atype = getattr(a, "alert_type", getattr(a, "product", "ALERT"))
            atime = str(getattr(a, "created_time", getattr(a, "start_time", "")))
            alert_rows.append([aid, aname, asev, atype, atime])
        self.alerts_model.set_rows(alert_rows)

        # Populate Entities Table
        entity_rows = [
            [getattr(e, "identifier", ""), getattr(e, "entity_type", ""), getattr(e, "role", "")]
            for e in entities
        ]
        self.entities_model.set_rows(entity_rows)

        # Populate Comments Feed
        comment_lines = []
        for c in comments:
            c_time = getattr(c, "created_time", getattr(c, "create_time", ""))
            c_author = getattr(c, "author_name", getattr(c, "author", "Analyst"))
            c_text = getattr(c, "comment", "")
            comment_lines.append(f"[{c_time}] {c_author}:\n{c_text}\n" + "-" * 40)
        self.comments_feed.setText("\n".join(comment_lines))
        self.status_message_requested.emit(f"Case #{getattr(inv, 'case_id', '')} loaded", 3000)

    @Slot(str)
    def _on_investigation_failed(self, err: str):
        self.overview_text.setText(f"Failed to load case investigation:\n{err}")
        self.status_message_requested.emit(f"Case investigation failed: {err}", 5000)

    @Slot()
    def _on_add_comment(self):
        if not self._current_investigation:
            return
        comment_text = self.comment_input.text().strip()
        if not comment_text:
            return

        self.add_comment_btn.setEnabled(False)
        case_id = self._current_investigation.case_id

        if self._active_comment_worker and self._active_comment_worker.isRunning():
            self._active_comment_worker.wait()

        self._active_comment_worker = CaseCommentWorker(
            engine=self.engine,
            case_id=case_id,
            comment=comment_text,
            parent=self,
        )

        def _on_comment_added(record):
            self.add_comment_btn.setEnabled(True)
            self.comment_input.clear()
            self._load_case_investigation(case_id)
            self.status_message_requested.emit("Comment added successfully", 3000)

        def _on_comment_failed(err):
            self.add_comment_btn.setEnabled(True)
            QMessageBox.warning(self, "Comment Failed", f"Failed to add comment:\n{err}")

        self._active_comment_worker.comment_added.connect(_on_comment_added)
        self._active_comment_worker.comment_failed.connect(_on_comment_failed)
        self._active_comment_worker.start()
