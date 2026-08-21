"""SecOps Desktop Main Window.

Provides a unified native desktop analyst console for the entire SecOps Workflow Engine:
- Sidebar navigation across 8 operational domains (SIEM + SOAR + Detection + Administration).
- Asynchronous workflow dispatch with signal-based UI reactivity (zero GUI thread blocking).
- Real-time RSS memory tracking and status reporting.
- Production data originates exclusively from SecOpsEngine.
"""

import os
import time
from typing import Optional

import psutil
from PySide6.QtCore import Qt, QTimer, Slot
from PySide6.QtGui import QFont, QIcon
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QSplitter,
    QStackedWidget,
    QStatusBar,
    QVBoxLayout,
    QWidget,
)

from clients.desktop.models import EventTableModel
from clients.desktop.widgets import (
    CasesWidget,
    DashboardsWidget,
    DetectionsWidget,
    FeedsParsersWidget,
    IntegrationsJobsWidget,
    PlaybooksWidget,
    SettingsWidget,
    UdmSearchWidget,
)
from engine import SecOpsEngine


class SecOpsMainWindow(QMainWindow):
    """Unified desktop interface for Google SecOps Workflows."""

    NAV_ITEMS = [
        ("🔍 UDM Search & Events", "UDM Search, event timeline & raw log investigation"),
        ("🛡️ Cases & Alerts", "SOAR Case triage, alerts, entities & comments"),
        ("⚡ Playbooks & DAGs", "Playbook catalog, triggers & step DAG execution"),
        ("🔌 Integrations & Jobs", "Integrations, instances, remote agents & jobs"),
        ("🎯 Curated Detections", "Curated detection rulesets, rules & metrics"),
        ("📡 Feeds & Parsers", "Ingestion feeds, pipelines, parsers & extensions"),
        ("📊 SIEM Dashboards", "Dashboards catalog & ad-hoc query execution"),
        ("⚙️ Settings & RBAC", "Data access scopes, preview features & SOAR admin"),
    ]

    def __init__(self, engine: SecOpsEngine, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.engine = engine

        self._process = psutil.Process(os.getpid())
        self._init_ui()
        self._init_status_timer()

    def _init_ui(self):
        self.setWindowTitle("SecOps Workflow Engine — Analyst Desktop Console")
        self.resize(1500, 920)

        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QHBoxLayout(central_widget)
        main_layout.setContentsMargins(4, 4, 4, 4)
        main_layout.setSpacing(4)

        # 1. Left Navigation Sidebar
        self.nav_list = QListWidget()
        self.nav_list.setFixedWidth(240)
        self.nav_list.setStyleSheet(
            """
            QListWidget {
                background-color: #1e1e24;
                color: #e0e0e0;
                border: 1px solid #33333d;
                border-radius: 4px;
                font-size: 13px;
                outline: none;
            }
            QListWidget::item {
                padding: 12px 10px;
                border-bottom: 1px solid #282830;
            }
            QListWidget::item:selected {
                background-color: #0d6efd;
                color: #ffffff;
                font-weight: bold;
                border-radius: 4px;
            }
            QListWidget::item:hover:!selected {
                background-color: #2b2b36;
            }
            """
        )

        for title, tooltip in self.NAV_ITEMS:
            item = QListWidgetItem(title)
            item.setToolTip(tooltip)
            self.nav_list.addItem(item)

        main_layout.addWidget(self.nav_list)

        # 2. Stacked Workspace Views
        self.stack = QStackedWidget()

        # Domain Widgets
        self.udm_widget = UdmSearchWidget(self.engine, self)
        self.cases_widget = CasesWidget(self.engine, self)
        self.playbooks_widget = PlaybooksWidget(self.engine, self)
        self.integrations_widget = IntegrationsJobsWidget(self.engine, self)
        self.detections_widget = DetectionsWidget(self.engine, self)
        self.feeds_parsers_widget = FeedsParsersWidget(self.engine, self)
        self.dashboards_widget = DashboardsWidget(self.engine, self)
        self.settings_widget = SettingsWidget(self.engine, self)

        # Backward-compatibility alias
        self.table_model = self.udm_widget.table_model
        self.investigation_widget = self.udm_widget.investigation_widget
        self.query_input = self.udm_widget.query_input
        self.search_btn = self.udm_widget.search_btn
        self.cancel_btn = self.udm_widget.cancel_btn

        self.stack.addWidget(self.udm_widget)
        self.stack.addWidget(self.cases_widget)
        self.stack.addWidget(self.playbooks_widget)
        self.stack.addWidget(self.integrations_widget)
        self.stack.addWidget(self.detections_widget)
        self.stack.addWidget(self.feeds_parsers_widget)
        self.stack.addWidget(self.dashboards_widget)
        self.stack.addWidget(self.settings_widget)

        main_layout.addWidget(self.stack, stretch=1)

        # Connect Sidebar to Stack
        self.nav_list.currentRowChanged.connect(self.stack.setCurrentIndex)
        self.nav_list.setCurrentRow(0)

        # Connect Status Messages from Child Widgets
        self.udm_widget.status_message_requested.connect(self._show_status)
        self.cases_widget.status_message_requested.connect(self._show_status)
        self.playbooks_widget.status_message_requested.connect(self._show_status)
        self.integrations_widget.status_message_requested.connect(self._show_status)
        self.detections_widget.status_message_requested.connect(self._show_status)
        self.feeds_parsers_widget.status_message_requested.connect(self._show_status)
        self.dashboards_widget.status_message_requested.connect(self._show_status)
        self.settings_widget.status_message_requested.connect(self._show_status)

        # 3. Status Bar Setup
        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)

        self.status_engine_label = QLabel("Engine: Connected")
        self.status_engine_label.setStyleSheet("color: #28a745; font-weight: bold; margin-right: 12px;")
        self.status_bar.addPermanentWidget(self.status_engine_label)

        self.status_mem_label = QLabel("RSS: 0.0 MB")
        self.status_mem_label.setStyleSheet("color: #888888; font-family: monospace; margin-right: 12px;")
        self.status_bar.addPermanentWidget(self.status_mem_label)

        self.status_bar.showMessage("Ready. Select a workflow from the left sidebar to begin.", 4000)

    def _init_status_timer(self):
        self._status_timer = QTimer(self)
        self._status_timer.setInterval(2000)
        self._status_timer.timeout.connect(self._update_process_metrics)
        self._status_timer.start()

    @Slot()
    def _update_process_metrics(self):
        try:
            mem_info = self._process.memory_info()
            rss_mb = mem_info.rss / (1024 * 1024)
            self.status_mem_label.setText(f"RSS: {rss_mb:.1f} MB")
        except Exception:
            pass

    @Slot(str, int)
    def _show_status(self, message: str, timeout: int = 3000):
        self.status_bar.showMessage(message, timeout)

    def closeEvent(self, event):
        if hasattr(self, "_status_timer") and self._status_timer.isActive():
            self._status_timer.stop()
        for w in [
            getattr(self, "udm_widget", None),
            getattr(self, "cases_widget", None),
            getattr(self, "playbooks_widget", None),
            getattr(self, "integrations_widget", None),
            getattr(self, "detections_widget", None),
            getattr(self, "feeds_parsers_widget", None),
            getattr(self, "dashboards_widget", None),
            getattr(self, "settings_widget", None),
        ]:
            if w and hasattr(w, "cleanup"):
                w.cleanup()
        event.accept()
