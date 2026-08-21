"""SecOps Search Refinement & Entity Pivot Workflows.

Implements SEC-SPEC-SRCH-002:
- search.refine.v1: Refines an active query or session with additive/exclusive field filters.
- search.from_entity.v1: Executes canonical multi-field entity pivot searches.
"""

from datetime import datetime, timezone
from typing import Callable, List, Optional, Union

from engine.domain import (
    EntityType,
    FieldFilter,
    FilterOperator,
    RefinementProvenance,
    SearchBatchResult,
    SearchRequest,
    SearchSession,
)
from engine.workflows.search_udm import SearchUDMWorkflow


class RefineSearchWorkflow:
    """Refines a UDM query or active session by applying field filters."""

    def __init__(self, search_workflow: SearchUDMWorkflow):
        self.search_workflow = search_workflow

    @staticmethod
    def build_refined_query(
        base_query: str,
        filters: List[FieldFilter],
        logic_operator: str = "AND",
    ) -> str:
        """Constructs a composite UDM query string from base query and filter clauses."""
        if not filters:
            return base_query.strip()

        clauses = [f.to_udm_clause() for f in filters]
        joined_clauses = f" {logic_operator} ".join(clauses)

        base_clean = base_query.strip()
        if not base_clean:
            return joined_clauses

        return f"{base_clean} AND ({joined_clauses})"

    def execute(
        self,
        base: Union[str, SearchSession],
        filters: List[FieldFilter],
        start_time: Optional[str] = None,
        end_time: Optional[str] = None,
        receive_limit: int = 10000,
        batch_size: int = 2000,
        parent_event_id: Optional[str] = None,
        on_batch: Optional[Callable[[SearchBatchResult, SearchSession], None]] = None,
        on_state_change: Optional[Callable[[SearchSession], None]] = None,
        cancel_token: Optional[Callable[[], bool]] = None,
    ) -> SearchSession:
        """Executes a refined search workflow with provenance tracking."""
        parent_session_id = None
        if isinstance(base, SearchSession):
            base_query = base.request.query
            parent_session_id = base.session_id
            if start_time is None:
                start_time = base.request.start_time
            if end_time is None:
                end_time = base.request.end_time
        else:
            base_query = str(base)

        refined_query = self.build_refined_query(base_query, filters)

        now = datetime.now(timezone.utc)
        if end_time is None:
            end_time = now.strftime("%Y-%m-%dT%H:%M:%SZ")
        if start_time is None:
            start_time = "1970-01-01T00:00:00Z"

        request = SearchRequest(
            query=refined_query,
            start_time=start_time,
            end_time=end_time,
            receive_limit=receive_limit,
            batch_size=batch_size,
        )

        return self.search_workflow.execute(
            request=request,
            on_batch=on_batch,
            on_state_change=on_state_change,
            cancel_token=cancel_token,
        )


class SearchFromEntityWorkflow:
    """Builds and executes canonical entity pivot searches across all standard UDM entity locations."""

    ENTITY_TEMPLATES = {
        EntityType.IP: 'principal.ip = "{value}" OR target.ip = "{value}" OR src.ip = "{value}"',
        EntityType.HOSTNAME: 'principal.hostname = "{value}" OR target.hostname = "{value}" OR src.hostname = "{value}"',
        EntityType.USER: 'principal.user.userid = "{value}" OR target.user.userid = "{value}" OR src.user.userid = "{value}"',
        EntityType.SHA256: 'principal.process.file.sha256 = "{value}" OR target.process.file.sha256 = "{value}" OR target.file.sha256 = "{value}"',
        EntityType.DOMAIN: 'network.dns.questions.name = "{value}"',
    }

    STRATEGY_DESCRIPTIONS = {
        EntityType.IP: "Searches across principal.ip, target.ip, and src.ip.",
        EntityType.HOSTNAME: "Searches across principal.hostname, target.hostname, and src.hostname.",
        EntityType.USER: "Searches across principal.user.userid, target.user.userid, and src.user.userid.",
        EntityType.SHA256: "Searches across process sha256 (principal & target) and target file sha256.",
        EntityType.DOMAIN: "Searches across network.dns.questions.name.",
    }

    def __init__(self, search_workflow: SearchUDMWorkflow):
        self.search_workflow = search_workflow

    @classmethod
    def get_strategy_description(cls, entity_type: EntityType) -> str:
        """Returns human- and AI-readable explanation of the search strategy for an entity type."""
        return cls.STRATEGY_DESCRIPTIONS.get(entity_type, f"Canonical search for {entity_type.value}")

    @classmethod
    def build_entity_query(cls, entity_type: EntityType, entity_value: str) -> str:
        """Generates standard canonical multi-field UDM query for an entity identifier."""
        template = cls.ENTITY_TEMPLATES.get(entity_type)
        if not template:
            raise ValueError(f"Unsupported entity type: {entity_type}")
        val_clean = entity_value.replace('"', '\\"')
        return template.format(value=val_clean)


    def execute(
        self,
        entity_type: EntityType,
        entity_value: str,
        start_time: str,
        end_time: str,
        receive_limit: int = 10000,
        batch_size: int = 2000,
        on_batch: Optional[Callable[[SearchBatchResult, SearchSession], None]] = None,
        on_state_change: Optional[Callable[[SearchSession], None]] = None,
        cancel_token: Optional[Callable[[], bool]] = None,
    ) -> SearchSession:
        """Executes a canonical entity pivot search."""
        query = self.build_entity_query(entity_type, entity_value)

        request = SearchRequest(
            query=query,
            start_time=start_time,
            end_time=end_time,
            receive_limit=receive_limit,
            batch_size=batch_size,
        )

        return self.search_workflow.execute(
            request=request,
            on_batch=on_batch,
            on_state_change=on_state_change,
            cancel_token=cancel_token,
        )
