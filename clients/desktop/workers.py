"""Qt Background Thread Workers for SecOps Workflow Execution.

Enforces the non-negotiable invariant:
- UI thread never executes workflow or network operations.
- All engine calls run asynchronously on background threads with signal-based dispatch.
- Zero synthetic fallback data anywhere.
"""

import threading
from typing import Any, Callable, Dict, List, Optional

from PySide6.QtCore import QObject, QThread, Signal

from engine import (
    CompletenessState,
    EntityType,
    EventInvestigation,
    FieldFilter,
    LifecycleState,
    SearchBatchResult,
    SearchRequest,
    SearchSession,
    SecOpsEngine,
)


class SearchWorker(QThread):
    """Background worker executing UDM Search, Refinement, or Entity Pivot workflows."""

    batch_received = Signal(list, int)
    state_changed = Signal(str, str)
    search_completed = Signal(object)
    search_failed = Signal(str)

    def __init__(
        self,
        engine: SecOpsEngine,
        mode: str = "search",
        search_request: Optional[SearchRequest] = None,
        base_query: Optional[str] = None,
        filters: Optional[List[FieldFilter]] = None,
        entity_type: Optional[EntityType] = None,
        entity_value: Optional[str] = None,
        parent: Optional[QObject] = None,
    ):
        super().__init__(parent)
        self.engine = engine
        self.mode = mode
        self.search_request = search_request
        self.base_query = base_query
        self.filters = filters or []
        self.entity_type = entity_type
        self.entity_value = entity_value
        self.cancel_token = threading.Event()

    def cancel(self):
        self.cancel_token.set()

    def run(self):
        try:
            def on_batch(batch: SearchBatchResult, session: SearchSession):
                self.batch_received.emit(batch.events, session.received_count)

            def on_state_change(lifecycle: LifecycleState, completeness: CompletenessState, session: SearchSession):
                self.state_changed.emit(lifecycle.value, completeness.value)

            if self.mode == "search":
                if not self.search_request:
                    raise ValueError("SearchRequest required for search mode")
                session = self.engine.search_udm(
                    request=self.search_request,
                    on_batch=on_batch,
                    on_state_change=on_state_change,
                    cancel_token=self.cancel_token,
                )
            elif self.mode == "refine":
                if not self.base_query:
                    raise ValueError("base_query required for refine mode")
                session = self.engine.refine_search(
                    base=self.base_query,
                    filters=self.filters,
                    receive_limit=self.search_request.receive_limit if self.search_request else 1000,
                    batch_size=self.search_request.batch_size if self.search_request else 500,
                    on_batch=on_batch,
                    on_state_change=on_state_change,
                    cancel_token=self.cancel_token,
                )
            elif self.mode == "entity":
                if not self.entity_type or not self.entity_value:
                    raise ValueError("entity_type and entity_value required for entity mode")
                session = self.engine.search_from_entity(
                    entity_type=self.entity_type,
                    entity_value=self.entity_value,
                    receive_limit=self.search_request.receive_limit if self.search_request else 1000,
                    batch_size=self.search_request.batch_size if self.search_request else 500,
                    on_batch=on_batch,
                    on_state_change=on_state_change,
                    cancel_token=self.cancel_token,
                )
            else:
                raise ValueError(f"Unknown worker mode: {self.mode}")

            self.search_completed.emit(session)
        except Exception as e:
            self.search_failed.emit(str(e))


class InvestigationWorker(QThread):
    """Background worker executing single event investigation."""

    investigation_completed = Signal(object)
    investigation_failed = Signal(str)

    def __init__(
        self,
        engine: SecOpsEngine,
        event: Optional[Dict[str, Any]] = None,
        event_id: Optional[str] = None,
        eager_raw_log: bool = False,
        parent: Optional[QObject] = None,
    ):
        super().__init__(parent)
        self.engine = engine
        self.event_payload = event
        self.event_id = event_id
        self.eager_raw_log = eager_raw_log

    def run(self):
        try:
            target = self.event_payload if self.event_payload is not None else self.event_id
            if target is None:
                raise ValueError("Either event dictionary or event_id must be provided")

            investigation = self.engine.investigate_event(
                target,
                eager_load_raw_log=self.eager_raw_log,
            )
            self.investigation_completed.emit(investigation)
        except Exception as e:
            self.investigation_failed.emit(str(e))


class RawLogWorker(QThread):
    """Background worker loading raw log on-demand for an investigation."""

    raw_log_loaded = Signal(object)
    raw_log_failed = Signal(str)

    def __init__(self, investigation: EventInvestigation, parent: Optional[QObject] = None):
        super().__init__(parent)
        self.investigation = investigation

    def run(self):
        try:
            payload = self.investigation.load_raw_log()
            self.raw_log_loaded.emit(payload)
        except Exception as e:
            self.raw_log_failed.emit(str(e))


class EnrichedEventWorker(QThread):
    """Background worker fetching full enriched UDM event by event ID."""

    enriched_event_loaded = Signal(dict)
    enriched_event_failed = Signal(str)

    def __init__(self, engine: SecOpsEngine, event_id: str, parent: Optional[QObject] = None):
        super().__init__(parent)
        self.engine = engine
        self.event_id = event_id

    def run(self):
        try:
            enriched = self.engine.adapter.fetch_enriched_event(self.event_id)
            self.enriched_event_loaded.emit(enriched)
        except Exception as e:
            self.enriched_event_failed.emit(str(e))


# --------------------------------------------------------------------------
# SOAR Case & Alert Workers
# --------------------------------------------------------------------------

class CaseSearchWorker(QThread):
    """Background worker searching SOAR cases with multi-facet filters."""

    cases_loaded = Signal(object)  # CaseSearchBatch
    search_failed = Signal(str)

    def __init__(
        self,
        engine: SecOpsEngine,
        query: Optional[str] = None,
        status: Optional[str] = None,
        priority: Optional[str] = None,
        assignee: Optional[str] = None,
        stage: Optional[str] = None,
        start_time: Optional[str] = None,
        end_time: Optional[str] = None,
        limit: int = 50,
        parent: Optional[QObject] = None,
    ):
        super().__init__(parent)
        self.engine = engine
        self.query = query
        self.status = status
        self.priority = priority
        self.assignee = assignee
        self.stage = stage
        self.start_time = start_time
        self.end_time = end_time
        self.limit = limit

    def run(self):
        try:
            priorities = [self.priority] if self.priority and self.priority != "ALL" else None
            stages = [self.stage] if self.stage else None
            assigned_users = [self.assignee] if self.assignee else None

            batch = self.engine.search_cases(
                query=self.query,
                priorities=priorities,
                stages=stages,
                assigned_users=assigned_users,
                start_time=self.start_time,
                end_time=self.end_time,
                page_size=self.limit,
            )
            self.cases_loaded.emit(batch)
        except Exception as e:
            self.search_failed.emit(str(e))


class CaseInvestigationWorker(QThread):
    """Background worker retrieving full investigation workspace for a SOAR case."""

    investigation_loaded = Signal(object)  # CaseInvestigation
    investigation_failed = Signal(str)

    def __init__(self, engine: SecOpsEngine, case_id: str, parent: Optional[QObject] = None):
        super().__init__(parent)
        self.engine = engine
        self.case_id = case_id

    def run(self):
        try:
            investigation = self.engine.investigate_case(self.case_id)
            self.investigation_loaded.emit(investigation)
        except Exception as e:
            self.investigation_failed.emit(str(e))


class CaseCommentWorker(QThread):
    """Background worker adding an analyst comment to a SOAR case."""

    comment_added = Signal(object)  # CaseCommentRecord
    comment_failed = Signal(str)

    def __init__(self, engine: SecOpsEngine, case_id: str, comment: str, parent: Optional[QObject] = None):
        super().__init__(parent)
        self.engine = engine
        self.case_id = case_id
        self.comment = comment

    def run(self):
        try:
            record = self.engine.add_case_comment(self.case_id, self.comment)
            self.comment_added.emit(record)
        except Exception as e:
            self.comment_failed.emit(str(e))


# --------------------------------------------------------------------------
# Playbooks & Automations Workers
# --------------------------------------------------------------------------

class PlaybookSearchWorker(QThread):
    """Background worker discovering playbooks."""

    playbooks_loaded = Signal(object)  # PlaybookBatch
    search_failed = Signal(str)

    def __init__(
        self,
        engine: SecOpsEngine,
        query: str = "",
        category: Optional[str] = None,
        is_enabled: Optional[bool] = None,
        limit: int = 50,
        parent: Optional[QObject] = None,
    ):
        super().__init__(parent)
        self.engine = engine
        self.query = query
        self.category = category
        self.is_enabled = is_enabled
        self.limit = limit

    def run(self):
        try:
            batch = self.engine.search_playbooks(
                query=self.query,
                category=self.category,
                is_enabled=self.is_enabled,
                limit=self.limit,
            )
            self.playbooks_loaded.emit(batch)
        except Exception as e:
            self.search_failed.emit(str(e))


class PlaybookDetailWorker(QThread):
    """Background worker fetching complete playbook DAG detail."""

    detail_loaded = Signal(object)  # PlaybookDetail
    detail_failed = Signal(str)

    def __init__(self, engine: SecOpsEngine, playbook_id: str, parent: Optional[QObject] = None):
        super().__init__(parent)
        self.engine = engine
        self.playbook_id = playbook_id

    def run(self):
        try:
            detail = self.engine.get_playbook(self.playbook_id)
            self.detail_loaded.emit(detail)
        except Exception as e:
            self.detail_failed.emit(str(e))


# --------------------------------------------------------------------------
# Integrations & Jobs Workers
# --------------------------------------------------------------------------

class IntegrationSearchWorker(QThread):
    """Background worker discovering SOAR integrations."""

    integrations_loaded = Signal(object)  # IntegrationBatch
    search_failed = Signal(str)

    def __init__(
        self,
        engine: SecOpsEngine,
        query: str = "",
        category: Optional[str] = None,
        limit: int = 50,
        parent: Optional[QObject] = None,
    ):
        super().__init__(parent)
        self.engine = engine
        self.query = query
        self.category = category
        self.limit = limit

    def run(self):
        try:
            batch = self.engine.search_integrations(
                query=self.query,
                category=self.category,
                limit=self.limit,
            )
            self.integrations_loaded.emit(batch)
        except Exception as e:
            self.search_failed.emit(str(e))


class JobSearchWorker(QThread):
    """Background worker discovering SOAR scheduled jobs."""

    jobs_loaded = Signal(object)  # JobBatch
    search_failed = Signal(str)

    def __init__(
        self,
        engine: SecOpsEngine,
        query: str = "",
        is_enabled: Optional[bool] = None,
        limit: int = 50,
        parent: Optional[QObject] = None,
    ):
        super().__init__(parent)
        self.engine = engine
        self.query = query
        self.is_enabled = is_enabled
        self.limit = limit

    def run(self):
        try:
            batch = self.engine.search_jobs(
                query=self.query,
                is_enabled=self.is_enabled,
                limit=self.limit,
            )
            self.jobs_loaded.emit(batch)
        except Exception as e:
            self.search_failed.emit(str(e))


# --------------------------------------------------------------------------
# Curated Detections & Rulesets Workers
# --------------------------------------------------------------------------

class CuratedDetectionSearchWorker(QThread):
    """Background worker discovering curated detection rulesets."""

    rulesets_loaded = Signal(object)  # CuratedRuleSetBatch
    search_failed = Signal(str)

    def __init__(
        self,
        engine: SecOpsEngine,
        query: str = "",
        category: str = "",
        limit: int = 50,
        parent: Optional[QObject] = None,
    ):
        super().__init__(parent)
        self.engine = engine
        self.query = query
        self.category = category
        self.limit = limit

    def run(self):
        try:
            batch = self.engine.search_curated_rulesets(
                query=self.query,
                category=self.category,
                limit=self.limit,
            )
            self.rulesets_loaded.emit(batch)
        except Exception as e:
            self.search_failed.emit(str(e))


class CuratedRuleDetailWorker(QThread):
    """Background worker fetching curated rule detail."""

    rule_loaded = Signal(object)  # CuratedRuleDetail
    rule_failed = Signal(str)

    def __init__(self, engine: SecOpsEngine, rule_id: str, parent: Optional[QObject] = None):
        super().__init__(parent)
        self.engine = engine
        self.rule_id = rule_id

    def run(self):
        try:
            rule = self.engine.get_curated_rule(self.rule_id)
            self.rule_loaded.emit(rule)
        except Exception as e:
            self.rule_failed.emit(str(e))


# --------------------------------------------------------------------------
# Feeds & Parsers Workers
# --------------------------------------------------------------------------

class FeedSearchWorker(QThread):
    """Background worker discovering ingestion feeds."""

    feeds_loaded = Signal(object)  # FeedBatch
    search_failed = Signal(str)

    def __init__(
        self,
        engine: SecOpsEngine,
        query: str = "",
        log_type: str = "",
        source_type: str = "",
        limit: int = 50,
        parent: Optional[QObject] = None,
    ):
        super().__init__(parent)
        self.engine = engine
        self.query = query
        self.log_type = log_type
        self.source_type = source_type
        self.limit = limit

    def run(self):
        try:
            batch = self.engine.search_feeds(
                query=self.query,
                log_type=self.log_type,
                source_type=self.source_type,
                limit=self.limit,
            )
            self.feeds_loaded.emit(batch)
        except Exception as e:
            self.search_failed.emit(str(e))


class ParserSearchWorker(QThread):
    """Background worker discovering SIEM parsers and extensions."""

    parsers_loaded = Signal(object)  # ParserBatch
    search_failed = Signal(str)

    def __init__(
        self,
        engine: SecOpsEngine,
        query: str = "",
        parser_type: str = "ALL",
        limit: int = 50,
        parent: Optional[QObject] = None,
    ):
        super().__init__(parent)
        self.engine = engine
        self.query = query
        self.parser_type = parser_type
        self.limit = limit

    def run(self):
        try:
            batch = self.engine.search_parsers(
                query=self.query,
                parser_type=self.parser_type,
                limit=self.limit,
            )
            self.parsers_loaded.emit(batch)
        except Exception as e:
            self.search_failed.emit(str(e))


# --------------------------------------------------------------------------
# Dashboards Workers
# --------------------------------------------------------------------------

class DashboardSearchWorker(QThread):
    """Background worker discovering SIEM dashboards."""

    dashboards_loaded = Signal(object)  # DashboardBatch
    search_failed = Signal(str)

    def __init__(
        self,
        engine: SecOpsEngine,
        query: str = "",
        dashboard_type: str = "",
        limit: int = 50,
        parent: Optional[QObject] = None,
    ):
        super().__init__(parent)
        self.engine = engine
        self.query = query
        self.dashboard_type = dashboard_type
        self.limit = limit

    def run(self):
        try:
            batch = self.engine.search_dashboards(
                query=self.query,
                dashboard_type=self.dashboard_type,
                limit=self.limit,
            )
            self.dashboards_loaded.emit(batch)
        except Exception as e:
            self.search_failed.emit(str(e))


class DashboardQueryWorker(QThread):
    """Background worker executing ad-hoc dashboard queries."""

    query_executed = Signal(object)  # DashboardQueryResult
    query_failed = Signal(str)

    def __init__(
        self,
        engine: SecOpsEngine,
        query: str,
        start_time: str,
        end_time: str,
        parent: Optional[QObject] = None,
    ):
        super().__init__(parent)
        self.engine = engine
        self.query = query
        self.start_time = start_time
        self.end_time = end_time

    def run(self):
        try:
            from engine.domain import DashboardQuery
            req = DashboardQuery(
                query_text=self.query,
                start_time=self.start_time,
                end_time=self.end_time,
            )
            result = self.engine.execute_dashboard_query(req)
            self.query_executed.emit(result)
        except Exception as e:
            self.query_failed.emit(str(e))


# --------------------------------------------------------------------------
# Settings, RBAC & Governance Workers
# --------------------------------------------------------------------------

class SettingsWorker(QThread):
    """Background worker fetching configuration batches across SIEM & SOAR settings."""

    data_loaded = Signal(str, object)  # (category_key, data_object)
    load_failed = Signal(str, str)  # (category_key, error_message)

    def __init__(
        self,
        engine: SecOpsEngine,
        category: str,
        query: str = "",
        limit: int = 50,
        parent: Optional[QObject] = None,
    ):
        super().__init__(parent)
        self.engine = engine
        self.category = category
        self.query = query
        self.limit = limit

    def run(self):
        try:
            if self.category == "preview_features":
                data = self.engine.list_preview_features(query=self.query, limit=self.limit)
            elif self.category == "data_scopes":
                data = self.engine.search_data_access_scopes(query=self.query, limit=self.limit)
            elif self.category == "agent_settings":
                data = self.engine.get_agent_settings()
            elif self.category == "soar_users":
                data = self.engine.search_soar_users(query=self.query, limit=self.limit)
            elif self.category == "soc_roles":
                data = self.engine.list_soc_roles(limit=self.limit)
            elif self.category == "environments":
                data = self.engine.search_environments(query=self.query, limit=self.limit)
            elif self.category == "webhooks":
                data = self.engine.search_soar_webhooks(query=self.query, limit=self.limit)
            elif self.category == "connectors":
                data = self.engine.search_soar_ingestion_connectors(query=self.query, limit=self.limit)
            else:
                raise ValueError(f"Unknown settings category: {self.category}")

            self.data_loaded.emit(self.category, data)
        except Exception as e:
            self.load_failed.emit(self.category, str(e))
