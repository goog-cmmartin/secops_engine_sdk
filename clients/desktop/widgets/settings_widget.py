"""SIEM & SOAR Settings, RBAC Scopes, and Administration Widget."""

from typing import Optional
from PySide6.QtCore import Qt, Signal, Slot
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
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

from clients.desktop.models import GenericItemTableModel
from clients.desktop.workers import SettingsWorker
from engine import SecOpsEngine


class SettingsWidget(QWidget):
    """Encapsulates RBAC Scopes, Preview Flags, Gemini Agent Settings, and SOAR Administration."""

    status_message_requested = Signal(str, int)

    def __init__(self, engine: SecOpsEngine, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.engine = engine

        self.preview_model = GenericItemTableModel(["Feature ID", "Display Name", "Enabled", "State"])
        self.scopes_model = GenericItemTableModel(["Scope ID", "Display Name", "Description"])
        self.users_model = GenericItemTableModel(["User ID", "Name", "Role", "Email", "Status"])
        self.env_model = GenericItemTableModel(["Environment ID", "Name", "Description"])
        self.webhooks_model = GenericItemTableModel(["Webhook ID", "Name", "State"])

        self._active_worker: Optional[SettingsWorker] = None

        self._init_ui()

    def _init_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(8, 8, 8, 8)
        main_layout.setSpacing(6)

        self.tabs = QTabWidget()

        # Tab 1: Preview Features
        self.tabs.addTab(self._create_table_tab(self.preview_model, "preview_features"), "Preview Features")

        # Tab 2: Data Access Scopes
        self.tabs.addTab(self._create_table_tab(self.scopes_model, "data_scopes"), "Data Scopes (RBAC)")

        # Tab 3: Gemini AI Agent Settings
        agent_widget = QWidget()
        agent_layout = QVBoxLayout(agent_widget)
        agent_btn_row = QHBoxLayout()
        load_agent_btn = QPushButton("Refresh Gemini Agent Settings")
        load_agent_btn.clicked.connect(lambda: self._load_category("agent_settings"))
        agent_btn_row.addWidget(load_agent_btn)
        agent_btn_row.addStretch()
        agent_layout.addLayout(agent_btn_row)

        self.agent_text = QTextEdit()
        self.agent_text.setReadOnly(True)
        self.agent_text.setFont(QFont("Monospace", 9))
        agent_layout.addWidget(self.agent_text)
        self.tabs.addTab(agent_widget, "Gemini AI Agent")

        # Tab 4: SOAR Users
        self.tabs.addTab(self._create_table_tab(self.users_model, "soar_users"), "SOAR Users & Roles")

        # Tab 5: Environments
        self.tabs.addTab(self._create_table_tab(self.env_model, "environments"), "Environments")

        # Tab 6: Webhooks & Ingestion
        self.tabs.addTab(self._create_table_tab(self.webhooks_model, "webhooks"), "Webhooks")

        main_layout.addWidget(self.tabs)

    def _create_table_tab(self, model: GenericItemTableModel, category_key: str) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(4, 4, 4, 4)

        btn_row = QHBoxLayout()
        refresh_btn = QPushButton(f"Refresh {category_key.replace('_', ' ').title()}")
        refresh_btn.clicked.connect(lambda: self._load_category(category_key))
        btn_row.addWidget(refresh_btn)
        btn_row.addStretch()
        layout.addLayout(btn_row)

        table = QTableView()
        table.setModel(model)
        table.setSelectionBehavior(QTableView.SelectionBehavior.SelectRows)
        table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        table.horizontalHeader().setStretchLastSection(True)
        layout.addWidget(table)
        return widget

    def _on_tab_changed(self, index: int):
        categories = ["preview_features", "data_scopes", "agent_settings", "soar_users", "environments", "webhooks"]
        if 0 <= index < len(categories):
            self._load_category(categories[index])

    def _load_category(self, category_key: str):
        self.status_message_requested.emit(f"Loading {category_key}...", 2000)

        if self._active_worker and self._active_worker.isRunning():
            self._active_worker.wait()

        self._active_worker = SettingsWorker(
            engine=self.engine,
            category=category_key,
            limit=50,
            parent=self,
        )
        self._active_worker.data_loaded.connect(self._on_data_loaded)
        self._active_worker.load_failed.connect(self._on_load_failed)
        self._active_worker.start()

    @Slot(str, object)
    def _on_data_loaded(self, category_key: str, data: object):
        if category_key == "preview_features":
            rows = [
                [getattr(item, "feature_id", "-"), getattr(item, "display_name", "-"), str(getattr(item, "is_enabled", "-")), getattr(item, "state", "-")]
                for item in getattr(data, "items", [])
            ]
            self.preview_model.set_rows(rows)

        elif category_key == "data_scopes":
            rows = [
                [getattr(item, "scope_id", "-"), getattr(item, "display_name", "-"), getattr(item, "description", "-")]
                for item in getattr(data, "items", [])
            ]
            self.scopes_model.set_rows(rows)

        elif category_key == "agent_settings":
            lines = [
                f"Agent Enabled:        {getattr(data, 'is_enabled', '-')}",
                f"Model Version:        {getattr(data, 'model_version', '-')}",
                f"Summary Level:        {getattr(data, 'summary_level', '-')}",
                f"Investigation Assist: {getattr(data, 'investigation_assist_enabled', '-')}",
                f"Playbook Gen Enabled: {getattr(data, 'playbook_generation_enabled', '-')}",
            ]
            self.agent_text.setText("\n".join(lines))

        elif category_key == "soar_users":
            rows = [
                [getattr(item, "user_id", "-"), getattr(item, "name", "-"), getattr(item, "role", "-"), getattr(item, "email", "-"), getattr(item, "status", "-")]
                for item in getattr(data, "items", [])
            ]
            self.users_model.set_rows(rows)

        elif category_key == "environments":
            rows = [
                [getattr(item, "environment_id", "-"), getattr(item, "name", "-"), getattr(item, "description", "-")]
                for item in getattr(data, "items", [])
            ]
            self.env_model.set_rows(rows)

        elif category_key == "webhooks":
            rows = [
                [getattr(item, "webhook_id", "-"), getattr(item, "name", "-"), getattr(item, "state", "-")]
                for item in getattr(data, "items", [])
            ]
            self.webhooks_model.set_rows(rows)

        self.status_message_requested.emit(f"{category_key.replace('_', ' ').title()} updated", 3000)

    @Slot(str, str)
    def _on_load_failed(self, category_key: str, err: str):
        self.status_message_requested.emit(f"Failed to load {category_key}: {err}", 5000)

    def cleanup(self):
        if self._active_worker and self._active_worker.isRunning():
            self._active_worker.wait(1000)
