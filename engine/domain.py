import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional


class LifecycleState(str, Enum):
    VALIDATING = "validating"
    STARTING = "starting"
    RUNNING = "running"
    CANCELLING = "cancelling"
    COMPLETED = "completed"
    CANCELLED = "cancelled"
    FAILED = "failed"


class CompletenessState(str, Enum):
    EMPTY = "empty"
    PARTIAL = "partial"
    COMPLETE = "complete"


class FilterOperator(str, Enum):
    EQUALS = "="
    NOT_EQUALS = "!="
    NOCASE_EQUALS = "= ... nocase"
    REGEX_MATCH = "=~"
    CONTAINS = "contains"


class EntityType(str, Enum):
    IP = "IP"
    HOSTNAME = "HOSTNAME"
    USER = "USER"
    SHA256 = "SHA256"
    MD5 = "MD5"
    SHA1 = "SHA1"
    DOMAIN = "DOMAIN"
    EMAIL = "EMAIL"
    MAC = "MAC"
    URL = "URL"
    WINDOWS_SID = "WINDOWS_SID"
    RESOURCE = "RESOURCE"
    FILE = "FILE"


class CaseSearchPrefix(str, Enum):
    """Typed query prefixes accepted by the SOAR case-search `title`/`query` field.

    IMPORTANT SecOps nuance: the `legacyCaseSearchEverything` `title` field is NOT a
    plain title-substring filter -- it is a prefixed query DSL. A bare, unprefixed
    term (e.g. a raw file hash) matches nothing. To search by entity/case/etc., the
    term MUST be prefixed, e.g. `Entity:<sha256>` or `AlertName:<name>`.

    This prefix set is the complete, closed vocabulary as exposed by the SecOps UX;
    the official API documentation does not enumerate additional prefixes.
    """
    CASE_IDS = "CaseIds"
    TICKET_IDS = "TicketIds"
    PORT = "Port"
    ALERT_NAME = "AlertName"
    ENTITY = "Entity"

    def apply(self, value: str) -> str:
        """Renders a prefixed query term, e.g. CaseSearchPrefix.ENTITY.apply(sha) -> 'Entity:<sha>'."""
        return f"{self.value}:{value}"


from engine.schema import canonicalize_udm_field


class UniversalBatchMixin:
    """Universal batch mixin providing uniform .items property, length, and iteration protocol."""

    @property
    def items(self) -> List[Any]:
        """Uniform alias for the primary resource collection."""
        for attr in (
            "results", "dashboards", "feeds", "parsers", "pipelines", "source_types",
            "log_types", "extensions", "features", "scopes", "labels", "combinations",
            "controls", "users", "roles", "settings", "tags", "stages", "reasons",
            "parameters", "views", "fields", "rules", "environments", "groups",
            "agents", "networks", "domains", "custom_lists", "templates", "blocklists",
            "definitions", "connectors", "webhooks", "events"
        ):
            val = getattr(self, attr, None)
            if isinstance(val, list):
                return val
        for val in getattr(self, "__dict__", {}).values():
            if isinstance(val, list):
                return val
        return []

    def __iter__(self):
        return iter(self.items)

    def __len__(self) -> int:
        return len(self.items)

    def __getitem__(self, index: int):
        return self.items[index]

    def __bool__(self) -> bool:
        return bool(self.items)


@dataclass
class FieldFilter:
    field_path: str
    operator: FilterOperator
    value: Any

    def to_udm_clause(self) -> str:
        """Renders filter into valid Google SecOps UDM query syntax."""
        canonical_path = canonicalize_udm_field(self.field_path)
        val_str = str(self.value).replace('"', '\\"')
        if self.operator == FilterOperator.EQUALS:
            return f'{canonical_path} = "{val_str}"'
        elif self.operator == FilterOperator.NOT_EQUALS:
            return f'{canonical_path} != "{val_str}"'
        elif self.operator == FilterOperator.NOCASE_EQUALS:
            return f'{canonical_path} = "{val_str}" nocase'
        elif self.operator == FilterOperator.REGEX_MATCH:
            return f'{canonical_path} =~ "{val_str}"'
        elif self.operator == FilterOperator.CONTAINS:
            escaped_val = re.escape(str(self.value)).replace('"', '\\"')
            return f'{canonical_path} =~ ".*{escaped_val}.*"'
        else:
            return f'{canonical_path} = "{val_str}"'


@dataclass

class RefinementProvenance:
    parent_session_id: Optional[str] = None
    parent_event_id: Optional[str] = None
    applied_filters: List[FieldFilter] = field(default_factory=list)
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass
class ValidationResult:

    valid: bool
    dialect: str = "udm"
    raw_query_type: Optional[str] = None
    error_message: Optional[str] = None


@dataclass
class SearchBatchResult(UniversalBatchMixin):
    """A single batch of events received from the provider."""

    events: List[Dict[str, Any]] = field(default_factory=list)
    provider_event_count: int = 0
    emitted_event_count: int = 0
    more_data_available: bool = False
    provider: str = "google_secops"
    workflow_id: str = "search.udm"
    operation_id: Optional[str] = None
    requested_start_index: int = 1
    requested_end_index: int = 1
    returned_start_index: int = 1
    returned_end_index: int = 1
    retrieved_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    raw_response: Optional[Dict[str, Any]] = None

    @property
    def batch_count(self) -> int:
        """Backward compatibility helper for emitted count."""
        return self.emitted_event_count


@dataclass
class SearchRequest:
    query: str
    start_time: str
    end_time: str
    receive_limit: int = 10000
    batch_size: int = 2000
    customer_id: Optional[str] = None
    project_id: Optional[str] = None
    location: Optional[str] = None
    # Server-side result materialization budget (maps to eventList.maxReturnedEvents).
    #
    # DISTINCT from `receive_limit`, which is the CLIENT-side cap on delivered events.
    # SecOps `legacyFetchUdmSearchView` uses `maxReturnedEvents` to size the whole
    # result set that also feeds prevalence/aggregation/AI-overview assembly; driving
    # it to very small values (e.g. receive_limit=1) starves the event list and can
    # yield zero events for a query that otherwise has matches. When None, the search
    # workflow derives a floored budget (see MATERIALIZE_BUDGET_FLOOR in
    # search_udm.py). The client-side loop still trims to `receive_limit`, so raising
    # this never over-delivers.
    materialize_budget: Optional[int] = None


@dataclass
class SearchSession:
    session_id: Optional[str] = None
    request: Optional[SearchRequest] = None
    lifecycle: LifecycleState = LifecycleState.VALIDATING
    completeness: CompletenessState = CompletenessState.EMPTY
    received_count: int = 0
    next_index: int = 1
    more_data_available: bool = True
    events: List[Dict[str, Any]] = field(default_factory=list)
    error: Optional[str] = None
    started_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    completed_at: Optional[datetime] = None


@dataclass
class StatsColumnMetadata:
    """Metadata describing a column in a UDM Stats Search result."""

    column: str = ""
    field_path: str = ""
    function_name_used: Optional[str] = None
    data_type: str = "STRING"


@dataclass
class StatsColumn:
    """A single columnar result array from a UDM Stats Search operation."""

    column: str
    values: List[Any] = field(default_factory=list)
    filterable: bool = False
    filter_expression: Optional[str] = None
    column_metadata: Optional[StatsColumnMetadata] = None


@dataclass
class StatsValueCount:
    """Value breakdown and event counts within a stats field aggregation."""

    value: Any = None
    event_count: int = 0
    baseline_event_count: int = 0


@dataclass
class StatsFieldAggregation:
    """Field-level event count and value distribution aggregation."""

    field_name: str
    baseline_event_count: int = 0
    event_count: int = 0
    value_count: int = 0
    all_values: List[StatsValueCount] = field(default_factory=list)


@dataclass
class StatsSearchResult(UniversalBatchMixin):
    """Normalized result of a UDM Stats Search operation with columnar and record views."""

    columns: List[StatsColumn] = field(default_factory=list)
    rows: List[Dict[str, Any]] = field(default_factory=list)
    total_results: int = 0
    filtered_result_count: int = 0
    data_query_expression: str = ""
    aggregations: List[StatsFieldAggregation] = field(default_factory=list)
    progress: float = 1.0
    complete: bool = True
    operation_id: Optional[str] = None
    raw_response: Optional[Dict[str, Any]] = None
    retrieved_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    @property
    def items(self) -> List[Dict[str, Any]]:
        """UniversalBatchMixin support: returns list of row dicts."""
        return self.rows

    def dedup_rows(self) -> List[Dict[str, Any]]:
        """Returns row records with duplicate rows removed while preserving order."""
        seen = set()
        deduped: List[Dict[str, Any]] = []
        for r in self.rows:
            key = tuple((k, str(v)) for k, v in sorted(r.items()))
            if key not in seen:
                seen.add(key)
                deduped.append(r)
        return deduped

    def to_records(self, dedup: bool = False) -> List[Dict[str, Any]]:
        """Returns row records as a list of column-to-value dictionaries."""
        if dedup:
            return self.dedup_rows()
        return self.rows

    def column_names(self) -> List[str]:
        """Returns list of column names in output order."""
        return [col.column for col in self.columns]


@dataclass
class DashboardQueryResult(UniversalBatchMixin):
    """Normalized result of a dashboard query execution with both column and row views.
    
    Dashboard queries return column-oriented data from the SecOps API. This class
    normalizes the response into an easy-to-use row-oriented format while preserving
    access to column metadata and raw responses.
    
    Example:
        >>> result = adapter.execute_dashboard_query(query_name)
        >>> print(f"{result.row_count} rows × {result.column_count} columns")
        >>> for row in result.rows:
        >>>     print(row['timestamp'], row['total_bytes_ingested'])
        >>> timestamps = result.column_values('timestamp')
    """
    
    # Required fields (no defaults)
    query_name: str
    dialect: str
    data_sources: List[str]
    time_window: Dict[str, str]
    columns: List[str]
    rows: List[Dict[str, Any]]
    total_rows: int
    
    # Optional fields (with defaults) - MUST come after required fields
    last_cache_refreshed_time: Optional[str] = None
    raw: Dict[str, Any] = field(default_factory=dict)
    retrieved_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    
    @property
    def items(self) -> List[Dict[str, Any]]:
        """UniversalBatchMixin support: returns list of row dicts."""
        return self.rows
    
    def column_values(self, column_name: str) -> List[Any]:
        """Extract all values for a specific column.
        
        Args:
            column_name: Name of the column to extract.
            
        Returns:
            List of values for the specified column across all rows.
        """
        return [row.get(column_name) for row in self.rows if column_name in row]
    
    def to_records(self) -> List[Dict[str, Any]]:
        """Returns row records as a list of column-to-value dictionaries.
        
        Returns:
            List of dictionaries, one per row, with column names as keys.
        """
        return self.rows
    
    def column_names(self) -> List[str]:
        """Returns list of column names in output order.
        
        Returns:
            List of column name strings.
        """
        return self.columns
    
    @property
    def row_count(self) -> int:
        """Number of result rows."""
        return len(self.rows)
    
    @property
    def column_count(self) -> int:
        """Number of result columns."""
        return len(self.columns)


@dataclass
class StatsSearchRequest:
    """Parameters for initiating a UDM Stats Search query."""

    query: str
    start_time: str
    end_time: str
    max_events: int = 10000
    case_insensitive: bool = True
    generate_ai_overview: bool = True
    max_values_per_field: int = 60
    customer_id: Optional[str] = None
    project_id: Optional[str] = None
    location: Optional[str] = None


@dataclass
class StatsSearchSession:
    """Lifecycle and state management session for a UDM Stats Search operation."""

    session_id: Optional[str] = None
    request: Optional[StatsSearchRequest] = None
    lifecycle: LifecycleState = LifecycleState.VALIDATING
    completeness: CompletenessState = CompletenessState.EMPTY
    result: Optional[StatsSearchResult] = None
    error: Optional[str] = None
    started_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    completed_at: Optional[datetime] = None


@dataclass
class RawLogPayload:
    """Represents the unparsed original raw log associated with an event."""

    raw_text: str
    source_product: str = ""
    log_type: str = ""
    timestamp: Optional[str] = None
    raw_bytes_size: int = 0
    retrieved_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass
class EventReference:
    """Stable pointer to a SecOps event for investigation or pivot."""

    event_id: str
    log_token: Optional[str] = None
    structured_event: Optional[Dict[str, Any]] = None


@dataclass
class InvestigationProvenance:
    """Provenance tracking for investigated event artifacts."""

    provider: str = "google_secops"
    workflow_id: str = "event.investigate"
    event_id: str = ""
    retrieved_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


class EventInvestigation:
    """Domain model representing a fully investigated SecOps event."""

    def __init__(
        self,
        event_id: str,
        event: Optional[Dict[str, Any]] = None,
        log_token: Optional[str] = None,
        raw_log: Optional[RawLogPayload] = None,
        provenance: Optional[InvestigationProvenance] = None,
        adapter: Optional[Any] = None,
    ):
        self.event_id = event_id
        self.event = event or {}
        self.log_token = log_token
        self.raw_log = raw_log
        self.provenance = provenance or InvestigationProvenance(event_id=event_id)
        self._adapter = adapter

    @property
    def udm(self) -> Dict[str, Any]:
        """Convenience alias for structured event payload."""
        return self.event

    @property
    def event_type(self) -> str:
        """Convenience accessor for UDM event type."""
        return str(self.get_field("metadata.eventType") or self.get_field("metadata.event_type") or "Unknown Event")

    @property
    def product_name(self) -> str:
        """Convenience accessor for product name."""
        return str(self.get_field("metadata.productName") or self.get_field("metadata.product_name") or "Unknown Product")

    def get_field(self, path: str, default: Any = None) -> Any:
        """Retrieves a nested field from the UDM event structure using dot notation (e.g. 'principal.hostname')."""
        curr = self.event
        # Support optional leading "udm." or "event." prefix if requested by callers
        if path.startswith("udm."):
            path = path[4:]
        elif path.startswith("event."):
            path = path[6:]

        parts = path.split(".")
        for part in parts:
            if isinstance(curr, dict) and part in curr:
                curr = curr[part]
            elif isinstance(curr, list) and part.isdigit() and int(part) < len(curr):
                curr = curr[int(part)]
            else:
                return default
        return curr

    def flatten_fields(self, prefix: str = "") -> Dict[str, Any]:
        """Flattens all nested UDM fields into dot-separated key-value pairs."""
        result: Dict[str, Any] = {}

        def _flatten(obj: Any, current_prefix: str):
            if isinstance(obj, dict):
                for k, v in obj.items():
                    new_key = f"{current_prefix}.{k}" if current_prefix else k
                    _flatten(v, new_key)
            elif isinstance(obj, list):
                for i, v in enumerate(obj):
                    new_key = f"{current_prefix}[{i}]"
                    _flatten(v, new_key)
            else:
                if current_prefix:
                    result[current_prefix] = obj

        _flatten(self.event, prefix)
        return result

    def to_flat_dict(self, prefix: str = "") -> Dict[str, Any]:
        """Alias for flatten_fields()."""
        return self.flatten_fields(prefix)


    def load_raw_log(self) -> RawLogPayload:
        """Loads and caches the raw log on demand via the adapter."""
        if self.raw_log is not None:
            return self.raw_log

        if not self._adapter:
            raise RuntimeError("Cannot load raw log: no adapter configured on EventInvestigation session.")

        payload = self._adapter.get_raw_log(event_id=self.event_id, log_token=self.log_token)
        self.raw_log = payload
        return payload

    def build_pivot_filter(
        self,
        field_path: str,
        operator: FilterOperator = FilterOperator.EQUALS,
    ) -> FieldFilter:
        """Extracts a field value and produces a typed FieldFilter for query refinement."""
        val = self.get_field(field_path)
        if val is None:
            raise KeyError(f"Field '{field_path}' does not exist in event {self.event_id}")
        return FieldFilter(field_path=field_path, operator=operator, value=val)


class CaseStatus(str, Enum):
    OPEN = "OPEN"
    CLOSED = "CLOSED"
    UNKNOWN = "UNKNOWN"


class CasePriority(str, Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"
    UNKNOWN = "UNKNOWN"


@dataclass
class CaseAlertSummary:
    name: str
    identifier: str
    display_name: str
    priority: str
    status: str
    product: Optional[str] = None
    vendor: Optional[str] = None
    event_count: int = 0
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    rule_name: Optional[str] = None
    # SOAR playbook association + runtime status snapshot (surfaced from the
    # case-alert payload; the authoritative per-run instance record is a Tier-2
    # concern -- see get_alert_playbook_status / playbook-instances endpoint).
    attached_playbook_name: Optional[str] = None
    playbook_status: Optional[str] = None
    playbook_run_count: int = 0
    alert_group_identifier: Optional[str] = None
    raw: Dict[str, Any] = field(default_factory=dict)

    @property
    def alert_id(self) -> str:
        return self.identifier or self.name

    @property
    def has_playbook(self) -> bool:
        """True if a playbook is attached to this alert."""
        return bool(self.attached_playbook_name)

    @property
    def severity(self) -> str:
        return self.priority

    @property
    def alert_type(self) -> str:
        return self.product or self.vendor or "ALERT"

    @property
    def created_time(self) -> Optional[datetime]:
        return self.start_time


@dataclass
class AlertPlaybookStatus:
    """Playbook association + status snapshot for a single alert within a case.

    Tier-1 model: values are surfaced directly from the case-alert payload. The
    ``status`` here is the alert-level snapshot (``playbookStatus``); it is not the
    authoritative per-run instance record (that is a Tier-2 concern keyed by
    ``alert_group_identifier``).
    """
    case_id: str
    alert_id: str
    alert_display_name: str
    attached_playbook_name: Optional[str] = None
    status: Optional[str] = None
    run_count: int = 0
    alert_group_identifier: Optional[str] = None

    @property
    def has_playbook(self) -> bool:
        return bool(self.attached_playbook_name)


@dataclass
class InvolvedEntitySummary:
    identifier: str
    display_name: str
    entity_type: Optional[str] = None
    role: Optional[str] = None
    is_suspicious: bool = False
    raw: Dict[str, Any] = field(default_factory=dict)


@dataclass
class CaseCommentRecord:
    name: str
    comment: str
    author: Optional[str] = None
    author_name: Optional[str] = None
    create_time: Optional[datetime] = None
    is_deleted: bool = False
    raw: Dict[str, Any] = field(default_factory=dict)

    @property
    def created_time(self) -> Optional[datetime]:
        return self.create_time


@dataclass
class CaseInvestigation:
    case_id: str
    name: str
    display_name: str
    status: CaseStatus
    priority: CasePriority
    stage: str
    create_time: Optional[datetime]
    update_time: Optional[datetime]
    assignee: Optional[str]
    alert_count: int
    alerts: List[CaseAlertSummary] = field(default_factory=list)
    entities: List[InvolvedEntitySummary] = field(default_factory=list)
    comments: List[CaseCommentRecord] = field(default_factory=list)
    provenance: Dict[str, Any] = field(default_factory=dict)
    raw_case: Dict[str, Any] = field(default_factory=dict)

    @property
    def title(self) -> str:
        return self.display_name or self.name

    @property
    def created_time(self) -> Optional[datetime]:
        return self.create_time

    @property
    def updated_time(self) -> Optional[datetime]:
        return self.update_time

    @property
    def involved_entities(self) -> List[InvolvedEntitySummary]:
        return self.entities

    @property
    def environment(self) -> str:
        return str(self.raw_case.get("environment", ""))

    @property
    def description(self) -> str:
        return str(self.raw_case.get("description", ""))


@dataclass
class AlertInvestigation:
    alert_name: str
    case_id: str
    display_name: str
    priority: str
    status: str
    rule_name: Optional[str]
    rule_id: Optional[str]
    risk_score: Optional[int]
    detection_time: Optional[datetime]
    product: Optional[str]
    vendor: Optional[str]
    event_count: int
    entities: List[InvolvedEntitySummary] = field(default_factory=list)
    associated_events: List[Dict[str, Any]] = field(default_factory=list)
    provenance: Dict[str, Any] = field(default_factory=dict)
    raw_alert: Dict[str, Any] = field(default_factory=dict)


@dataclass
class CaseSearchQuery:
    query_text: str = ""
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    tags: List[str] = field(default_factory=list)
    priorities: List[str] = field(default_factory=list)
    stages: List[str] = field(default_factory=list)
    environments: List[str] = field(default_factory=list)
    assigned_users: List[str] = field(default_factory=list)
    is_important: Optional[bool] = None
    page_size: int = 50
    page_number: int = 0


@dataclass
class CaseSearchResultItem:
    case_id: str
    title: str
    create_time: Optional[datetime]
    priority: CasePriority
    stage: str
    tags: List[str] = field(default_factory=list)
    products: List[str] = field(default_factory=list)
    user_assigned: Optional[str] = None
    is_important: bool = False
    is_incident: bool = False
    is_closed: bool = False
    alerts_count: int = 0
    environment: str = ""
    ticket_ids: List[str] = field(default_factory=list)
    ports: List[str] = field(default_factory=list)
    raw: Dict[str, Any] = field(default_factory=dict)


@dataclass
class CaseSearchBatch(UniversalBatchMixin):
    results: List[CaseSearchResultItem]
    total_count: int
    page_size: int
    page_number: int
    provenance: Dict[str, Any] = field(default_factory=dict)

    @property
    def items(self) -> List[CaseSearchResultItem]:
        """Uniform alias for batch results across all engine domains."""
        return self.results


class PlaybookType(str, Enum):
    REGULAR = "REGULAR"
    NESTED = "NESTED"
    UNKNOWN = "UNKNOWN"


@dataclass
class PlaybookCategory:
    """SOAR Playbook category/folder taxonomy."""
    id: str
    name: str
    category_state: str = "FULL"
    category_type: str = "REGULAR"
    is_default: bool = False
    raw: Dict[str, Any] = field(default_factory=dict)


@dataclass
class PlaybookSummary:
    """Summary card representation of a SOAR Playbook."""
    id: str
    identifier: str
    original_identifier: str
    name: str
    is_enabled: bool
    is_debug_mode: bool
    priority: int
    category_id: int
    category_name: str
    creator: str
    creator_full_name: str
    environments: List[str] = field(default_factory=list)
    playbook_type: PlaybookType = PlaybookType.REGULAR
    has_restricted_environments: bool = False
    creation_time: Optional[datetime] = None
    modification_time: Optional[datetime] = None
    raw: Dict[str, Any] = field(default_factory=dict)


@dataclass
class PlaybookTriggerCondition:
    value: str
    match_type: str = "EQUAL"


@dataclass
class PlaybookTrigger:
    id: str
    identifier: str
    trigger_type: str
    logical_operator: str = "AND"
    conditions: List[PlaybookTriggerCondition] = field(default_factory=list)
    reaction_logical_operator: str = "OR"
    raw: Dict[str, Any] = field(default_factory=dict)


@dataclass
class PlaybookStepParameter:
    name: str
    value: Optional[str] = None
    is_mandatory: bool = False


@dataclass
class PlaybookStep:
    identifier: str
    original_step_identifier: str
    name: str
    instance_name: str
    integration: str
    action_name: str
    action_provider: str
    step_type: str
    description: str = ""
    is_automatic: bool = True
    is_skippable: bool = False
    auto_skip_on_failure: bool = False
    parameters: List[PlaybookStepParameter] = field(default_factory=list)
    workflow_identifier: str = ""
    raw: Dict[str, Any] = field(default_factory=dict)


@dataclass
class PlaybookDetail:
    """Comprehensive playbook model including trigger and step DAG."""
    id: str
    identifier: str
    name: str
    description: str
    is_enabled: bool
    is_debug_mode: bool
    priority: int
    category_id: int
    category_name: str
    creator: str
    modified_by: Optional[str] = None
    environments: List[str] = field(default_factory=list)
    playbook_type: PlaybookType = PlaybookType.REGULAR
    trigger: Optional[PlaybookTrigger] = None
    steps: List[PlaybookStep] = field(default_factory=list)
    creation_time: Optional[datetime] = None
    modification_time: Optional[datetime] = None
    raw: Dict[str, Any] = field(default_factory=dict)


@dataclass
class PlaybookSearchQuery:
    query: Optional[str] = None
    category: Optional[str] = None
    playbook_type: Optional[PlaybookType] = None
    is_enabled: Optional[bool] = None
    environment: Optional[str] = None
    limit: int = 100


@dataclass
class PlaybookBatch(UniversalBatchMixin):
    results: List[PlaybookSummary]
    total_count: int
    retrieved_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


# -----------------------------------------------------------------------------
# Tier-2: authoritative per-alert playbook *instance* execution records.
# Sourced from legacyPlaybooks:legacyGetWorkflowInstancesCards (summary) and
# legacyGetWorkflowInstance (full run incl. step DAG). Distinct from the Tier-1
# CaseAlertSummary snapshot, these reflect actual run instances keyed by the
# opaque alertGroupIdentifier (alertIdentifier).
# -----------------------------------------------------------------------------


# Playbook step statuses that indicate a step did NOT execute during a run. Any
# other (truthy) status -- COMPLETED, FAILED, TIMED_OUT, etc. -- is treated as
# "executed" (a failed step still ran). Compared case-insensitively.
NON_EXECUTED_STEP_STATUSES = frozenset({
    "",
    "NO_STATUS",
    "PENDING",
    "PENDING_ADDITIONAL_DATA",
    "NOT_STARTED",
    "SKIPPED",
})


def _step_did_execute(status: Optional[str]) -> bool:
    """True if a playbook step's status indicates it actually ran."""
    return (status or "").strip().upper() not in NON_EXECUTED_STEP_STATUSES


@dataclass
class PlaybookInstanceCard:
    """Lightweight summary of a single playbook run instance attached to an alert.

    Returned by ``legacyGetWorkflowInstancesCards``. The ``definition_identifier``
    is the playbook UUID required to drill into the full run via
    ``get_alert_playbook_instance``.
    """
    instance_id: str
    definition_identifier: str
    name: str
    status: Optional[str] = None
    is_enabled: bool = True
    environments: List[str] = field(default_factory=list)
    creation_time: Optional[datetime] = None
    modification_time: Optional[datetime] = None
    raw: Dict[str, Any] = field(default_factory=dict)


@dataclass
class PlaybookInstanceRelation:
    """A directed edge in the playbook execution DAG (``stepsRelations`` entry)."""
    from_step: str
    to_step: str
    destination_action_status: Optional[str] = None
    condition: Optional[str] = None
    raw: Dict[str, Any] = field(default_factory=dict)


@dataclass
class PlaybookInstanceStep:
    """A single executed step within a playbook run instance.

    Extends the definition-level :class:`PlaybookStep` shape with runtime
    execution state (``status``, timing, result summary).
    """
    identifier: str
    name: str
    status: Optional[str] = None
    action_name: str = ""
    integration: str = ""
    instance_name: str = ""
    is_automatic: bool = True
    result_summary: Optional[str] = None
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    raw: Dict[str, Any] = field(default_factory=dict)


@dataclass
class PlaybookInstanceRun:
    """Full authoritative record of a playbook run instance against an alert.

    Returned by ``legacyGetWorkflowInstance``. Combines the playbook definition
    with runtime state: the execution DAG (:attr:`relations`) and per-step
    execution status (:attr:`steps`).
    """
    instance_id: str
    identifier: str
    name: str
    case_id: str
    alert_identifier: str
    status: Optional[str] = None
    is_enabled: bool = True
    is_debug_mode: bool = False
    priority: int = 0
    category_name: str = ""
    original_playbook_identifier: Optional[str] = None
    environments: List[str] = field(default_factory=list)
    trigger: Optional["PlaybookTrigger"] = None
    steps: List[PlaybookInstanceStep] = field(default_factory=list)
    relations: List[PlaybookInstanceRelation] = field(default_factory=list)
    creation_time: Optional[datetime] = None
    modification_time: Optional[datetime] = None
    raw: Dict[str, Any] = field(default_factory=dict)

    @property
    def step_count(self) -> int:
        return len(self.steps)

    @property
    def completed_step_count(self) -> int:
        return sum(1 for s in self.steps if (s.status or "").upper() == "COMPLETED")

    @property
    def executed_step_count(self) -> int:
        """Number of steps that actually ran (any terminal status, incl. failures)."""
        return sum(1 for s in self.steps if _step_did_execute(s.status))

    def executed_path(self) -> List["PlaybookInstanceStep"]:
        """Return only the steps that actually executed, in execution order.

        A playbook *definition* may contain many conditional branches; a single
        *run* traverses only one path through the DAG. This collapses the full
        step list down to the connected subgraph that actually ran, ordered by
        the execution DAG (:attr:`relations`) with ``start_time`` as a tie-break.

        "Executed" means the step has a terminal status (see
        :data:`NON_EXECUTED_STEP_STATUSES`); failed/timed-out steps are included
        because they did run. Steps with no timing and a non-executed status are
        excluded.

        The traversal is defensive against real-world DAG irregularities:
        cycles are broken via a visited-set, executed steps unreachable from a
        root are still appended (ordered by ``start_time``), so the returned list
        always contains exactly the executed steps with no duplicates.
        """
        by_id = {s.identifier: s for s in self.steps}
        executed_ids = {sid for sid, s in by_id.items() if _step_did_execute(s.status)}
        if not executed_ids:
            return []

        # Adjacency restricted to executed->executed edges, preserving edge order.
        adj: Dict[str, List[str]] = {sid: [] for sid in executed_ids}
        indeg: Dict[str, int] = {sid: 0 for sid in executed_ids}
        seen_edge = set()
        for rel in self.relations:
            f, t = rel.from_step, rel.to_step
            if f in executed_ids and t in executed_ids and (f, t) not in seen_edge:
                seen_edge.add((f, t))
                adj[f].append(t)
                indeg[t] += 1

        def _sort_key(sid: str):
            st = by_id[sid].start_time
            # None start_times sort last but stably.
            return (st is None, st or datetime.max.replace(tzinfo=timezone.utc))

        # Roots: executed steps with no executed predecessor, earliest first.
        roots = sorted([sid for sid in executed_ids if indeg[sid] == 0], key=_sort_key)

        ordered: List[str] = []
        visited: set = set()
        # BFS/DFS hybrid: stable DFS from each root following edge order.
        stack = list(reversed(roots))
        while stack:
            sid = stack.pop()
            if sid in visited:
                continue
            visited.add(sid)
            ordered.append(sid)
            # Push successors in reverse so first edge is processed first.
            for nxt in reversed(adj[sid]):
                if nxt not in visited:
                    stack.append(nxt)

        # Append any executed step not reached via edges (disconnected islands),
        # ordered by start_time to keep chronology sensible.
        leftover = sorted([sid for sid in executed_ids if sid not in visited], key=_sort_key)
        ordered.extend(leftover)

        return [by_id[sid] for sid in ordered]


# =============================================================================
# Milestone 5.4: SOAR Integrations, Instances & Remote Agents Domain Models
# =============================================================================


class IntegrationType(str, Enum):
    RESPONSE = "RESPONSE"
    CUSTOM = "CUSTOM"
    UNKNOWN = "UNKNOWN"


@dataclass
class IntegrationInstance:
    """Represents a configured deployment instance of an integration."""
    identifier: str
    integration_identifier: str
    display_name: str
    environment: str  # e.g. '*' for Global, or 'Default Environment', 'Cymbal'
    is_configured: bool
    is_remote: bool
    is_system_default: bool
    name: str = ""
    raw: Dict[str, Any] = field(default_factory=dict)

    @property
    def is_global(self) -> bool:
        return self.environment == "*"


@dataclass
class RemoteAgent:
    """Represents a remote proxy execution agent."""
    id: str
    identifier: str
    display_name: str
    agent_state: str  # e.g. ACTIVE, INACTIVE
    environments: List[str] = field(default_factory=list)
    logging_level: str = "ERROR"
    installer_link: Optional[str] = None
    raw: Dict[str, Any] = field(default_factory=dict)

    @property
    def is_active(self) -> bool:
        return self.agent_state.upper() == "ACTIVE"


@dataclass
class IntegrationSummary:
    """Lightweight summary card for an integration catalog entry."""
    identifier: str
    display_name: str
    description: str
    version: str
    custom: bool
    certified: bool
    staging: bool
    python_version: str
    integration_type: IntegrationType = IntegrationType.RESPONSE
    instances_count: int = 0
    raw: Dict[str, Any] = field(default_factory=dict)


@dataclass
class IntegrationDetail:
    """Comprehensive details for a specific integration with instances and documentation."""
    identifier: str
    display_name: str
    description: str
    version: str
    custom: bool
    certified: bool
    staging: bool
    python_version: str
    integration_type: IntegrationType = IntegrationType.RESPONSE
    documentation_uri: Optional[str] = None
    categories: List[str] = field(default_factory=list)
    instances: List[IntegrationInstance] = field(default_factory=list)
    remote_agents: List[RemoteAgent] = field(default_factory=list)
    raw: Dict[str, Any] = field(default_factory=dict)

    @property
    def configured_instances_count(self) -> int:
        return sum(1 for inst in self.instances if inst.is_configured)

    @property
    def environments_supported(self) -> List[str]:
        return sorted(list(set(inst.environment for inst in self.instances)))


@dataclass
class IntegrationSearchQuery:
    """Multi-facet filter query for integrations."""
    query: Optional[str] = None
    environment: Optional[str] = None
    is_configured: Optional[bool] = None
    is_certified: Optional[bool] = None
    limit: int = 100


@dataclass
class IntegrationBatch(UniversalBatchMixin):
    """Container for integration search and listing results."""
    results: List[IntegrationSummary]
    total_count: int
    retrieved_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


# =====================================================================
# Milestone 5.5: SOAR Jobs, Job Instances & Execution Logs Domain
# =====================================================================

class JobExecutionStatus(str, Enum):
    """Execution status of a job instance run."""
    SUCCESS = "SUCCESS"
    FAILED = "FAILED"
    RUNNING = "RUNNING"
    PENDING = "PENDING"
    UNKNOWN = "UNKNOWN"


@dataclass
class JobSummary:
    """Lightweight catalog representation of a SOAR Job."""
    id: str
    name: str
    display_name: str
    description: str = ""
    integration: str = ""
    enabled: bool = False
    cron_expression: Optional[str] = None
    recurring_type: Optional[str] = None
    interval: Optional[int] = None
    timeout: Optional[int] = None
    instances_count: int = 0
    author: Optional[str] = None
    creation_time: Optional[str] = None
    modification_time: Optional[str] = None
    raw: Dict[str, Any] = field(default_factory=dict)


@dataclass
class JobInstance:
    """Runtime instance of a SOAR job deployed to an environment/agent."""
    id: str
    name: str
    display_name: str
    job_id: str
    job_name: str
    integration: str
    environment: Optional[str] = None
    status: str = "UNKNOWN"
    last_run_status: str = "UNKNOWN"
    last_run_time: Optional[str] = None
    remote_agent_id: Optional[str] = None
    schedule_type: Optional[str] = None
    advanced_config: Dict[str, Any] = field(default_factory=dict)
    unique_identifier: Optional[str] = None
    raw: Dict[str, Any] = field(default_factory=dict)

    @property
    def is_success(self) -> bool:
        return self.last_run_status.upper() == "SUCCESS"


@dataclass
class JobExecutionLog:
    """Execution run record and output log for a job instance."""
    name: str
    start_time: Optional[str] = None
    end_time: Optional[str] = None
    status: str = "UNKNOWN"
    log_text: str = ""
    job_identifier: str = ""
    integration: str = ""
    job_instance_id: str = ""
    raw: Dict[str, Any] = field(default_factory=dict)


@dataclass
class JobDetail:
    """Full detail composite for a SOAR job including instances and logs."""
    job: JobSummary
    instances: List[JobInstance] = field(default_factory=list)
    recent_logs: List[JobExecutionLog] = field(default_factory=list)


@dataclass
class JobSearchQuery:
    """Multi-facet filter query for SOAR jobs."""
    query: Optional[str] = None
    integration: Optional[str] = None
    enabled: Optional[bool] = None
    limit: int = 100


@dataclass
class JobBatch(UniversalBatchMixin):
    """Container for job search and listing results."""
    results: List[JobSummary]
    total_count: int
    retrieved_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


# ==============================================================================
# Milestone 5.6: Content Hub (Marketplace) - Content Packs Domain Types
# ==============================================================================


class ContentPackType(str, Enum):
    """Classification of Content Hub Content Packs."""
    ONBOARDING = "ONBOARDING"
    SEC_OPS_USE_CASE = "SEC_OPS_USE_CASE"
    SOAR_LEGACY = "SOAR_LEGACY"
    EXTERNAL = "EXTERNAL"
    PRODUCT = "PRODUCT"
    UNKNOWN = "UNKNOWN"


@dataclass
class ContentPackItem:
    """Individual bundled component within a Content Pack."""
    id: str
    title: str
    item_type: str  # 'playbook', 'integration', 'dashboard', 'ruleset', 'search_query', 'detection_rule'
    raw: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ContentPackSummary:
    """Lightweight summary of a Content Hub Content Pack."""
    id: str
    identifier: str
    name: str
    title: str
    pack_type: str
    categories: List[str] = field(default_factory=list)
    description: str = ""
    deployed: bool = False
    custom: bool = False
    community: bool = False
    uploader: str = ""
    playbooks_count: int = 0
    integrations_count: int = 0
    dashboards_count: int = 0
    rulesets_count: int = 0
    queries_count: int = 0
    rules_count: int = 0
    raw: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ContentPackDetail:
    """Complete deep-dive composite of a Content Pack with all bundled items."""
    pack: ContentPackSummary
    playbooks: List[ContentPackItem] = field(default_factory=list)
    integrations: List[ContentPackItem] = field(default_factory=list)
    dashboards: List[ContentPackItem] = field(default_factory=list)
    rulesets: List[ContentPackItem] = field(default_factory=list)
    queries: List[ContentPackItem] = field(default_factory=list)
    rules: List[ContentPackItem] = field(default_factory=list)
    pre_guidance: Optional[str] = None
    post_guidance: Optional[str] = None
    raw: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ContentPackSearchQuery:
    """Multi-facet filter query for searching Content Hub Content Packs."""
    query: Optional[str] = None
    category: Optional[str] = None
    pack_type: Optional[str] = None
    deployed: Optional[bool] = None
    limit: int = 100


@dataclass
class ContentPackBatch(UniversalBatchMixin):
    """Container for Content Pack search and listing results."""
    results: List[ContentPackSummary]
    total_count: int
    retrieved_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


# --- Milestone 5.7: Curated Detections Models ---


class CuratedPrecision(str, Enum):
    """Execution and alerting precision modes for Google SecOps Curated Rules."""
    BROAD = "BROAD"
    PRECISE = "PRECISE"
    UNKNOWN = "UNKNOWN"


@dataclass
class MitreAttackMapping:
    """MITRE ATT&CK Framework Tactic or Technique mapping."""
    id: str
    display_name: str
    kind: str = "tactic"  # "tactic" or "technique"


@dataclass
class CuratedRuleSetDeployment:
    """Deployment state for a Curated Rule Set precision mode."""
    precision: str
    enabled: bool
    alerting: bool = False
    resource_name: str = ""


@dataclass
class CuratedRuleSummary:
    """Lightweight metadata for a single Google-curated detection rule."""
    id: str
    title: str
    severity: str
    precision: str
    rule_type: str
    curated_rule_set_id: str
    techniques: List[MitreAttackMapping] = field(default_factory=list)
    description: str = ""
    false_positives: str = ""
    resource_name: str = ""


@dataclass
class CuratedRuleDetail:
    """Complete composite for a Curated Rule, including raw YARA-L logic."""
    rule: CuratedRuleSummary
    rule_text: str = ""
    live_status_enabled: bool = False
    tactics: List[MitreAttackMapping] = field(default_factory=list)
    techniques: List[MitreAttackMapping] = field(default_factory=list)
    raw: Dict[str, Any] = field(default_factory=dict)


@dataclass
class CuratedRuleSetSummary:
    """Metadata and MITRE mappings for a Curated Rule Set."""
    id: str
    title: str
    description: str
    category_id: str = ""
    category_name: str = ""
    log_sources: List[str] = field(default_factory=list)
    tactics: List[MitreAttackMapping] = field(default_factory=list)
    techniques: List[MitreAttackMapping] = field(default_factory=list)
    authors: List[str] = field(default_factory=list)
    quota_size: int = 1
    deployments: List[CuratedRuleSetDeployment] = field(default_factory=list)
    detection_count: int = 0
    resource_name: str = ""


@dataclass
class CuratedRuleSetDetail:
    """Deep-inspection composite for a Curated Rule Set."""
    rule_set: CuratedRuleSetSummary
    rules: List[CuratedRuleSummary] = field(default_factory=list)
    deployments: List[CuratedRuleSetDeployment] = field(default_factory=list)
    detection_count: int = 0
    raw: Dict[str, Any] = field(default_factory=dict)


@dataclass
class CuratedRuleSearchQuery:
    """Filter parameters for querying Curated Rule Sets."""
    query: Optional[str] = None
    category: Optional[str] = None
    mitre_tactic: Optional[str] = None
    mitre_technique: Optional[str] = None
    log_source: Optional[str] = None
    limit: int = 50


@dataclass
class CuratedRuleSetBatch(UniversalBatchMixin):
    """Container for Curated Rule Set search results."""
    results: List[CuratedRuleSetSummary]
    total_count: int
    retrieved_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass
class TenantRuleMetrics:
    """Tenant-wide rule deployment counts and chronicle rules quota usage."""
    total_active_count: int = 0
    total_archived_count: int = 0
    total_live_rule_count: int = 0
    max_live_rule_count: int = 0
    quota_limit: int = 0
    quota_usage: int = 0
    counts_per_type: List[Dict[str, Any]] = field(default_factory=list)
    raw: Dict[str, Any] = field(default_factory=dict)


@dataclass
class CuratedDetectionMetrics:
    """Aggregated detection telemetry and tenant rule quotas."""
    tenant_metrics: TenantRuleMetrics
    top_firing_rulesets: List[Dict[str, Any]] = field(default_factory=list)
    time_interval: Dict[str, str] = field(default_factory=dict)
    retrieved_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


# --- Milestone 5.8: Content Hub Marketplace Response Integrations Domain Models ---


@dataclass
class MarketplaceIntegrationSummary:
    """Lightweight metadata for a Content Hub Marketplace Response Integration."""
    identifier: str
    title: str
    version: str
    installed_version: str = "0.0"
    installed: bool = False
    update_available: bool = False
    categories: List[str] = field(default_factory=list)
    python_version: str = "V3_11"
    certified: bool = False
    custom: bool = False
    description: str = ""
    documentation_uri: str = ""
    item_update_status: str = "REGULAR"
    resource_name: str = ""


@dataclass
class MarketplaceIntegrationReleaseNote:
    """Version changelog release note for a Marketplace Integration."""
    version: str
    publish_time: str
    changelog_items: List[str] = field(default_factory=list)


@dataclass
class MarketplaceIntegrationDetail:
    """Complete composite for a Marketplace Response Integration."""
    integration: MarketplaceIntegrationSummary
    actions: List[str] = field(default_factory=list)
    connectors: List[str] = field(default_factory=list)
    jobs: List[str] = field(default_factory=list)
    managers: List[str] = field(default_factory=list)
    mapping_rules: List[str] = field(default_factory=list)
    release_notes: List[MarketplaceIntegrationReleaseNote] = field(default_factory=list)
    snapshots: List[str] = field(default_factory=list)
    raw: Dict[str, Any] = field(default_factory=dict)


@dataclass
class MarketplaceCommercialDiff:
    """Commercial version upgrade diff structure for a Marketplace Integration."""
    integration_identifier: str
    version: str
    python_version: str
    actions: List[str] = field(default_factory=list)
    connectors: List[str] = field(default_factory=list)
    jobs: List[str] = field(default_factory=list)
    managers: List[str] = field(default_factory=list)
    diff: Dict[str, Any] = field(default_factory=dict)
    mapping_rules_exist: bool = False
    raw: Dict[str, Any] = field(default_factory=dict)


@dataclass
class AffectedDownstreamInstance:
    """Downstream environment integration instance affected by upgrade."""
    display_name: str
    environment: str


@dataclass
class AffectedDownstreamPlaybook:
    """Downstream active SOAR playbook affected by integration upgrade."""
    display_name: str
    environments: List[str] = field(default_factory=list)


@dataclass
class MarketplaceAffectedItems:
    """Downstream dependencies affected by integration upgrade or modification."""
    integration_identifier: str
    affected_instances: List[AffectedDownstreamInstance] = field(default_factory=list)
    affected_playbooks: List[AffectedDownstreamPlaybook] = field(default_factory=list)
    raw: Dict[str, Any] = field(default_factory=dict)


@dataclass
class MarketplaceIntegrationSearchQuery:
    """Filter parameters for querying Marketplace Response Integrations."""
    query: Optional[str] = None
    category: Optional[str] = None
    installed: Optional[bool] = None
    update_available: Optional[bool] = None
    certified: Optional[bool] = None
    limit: int = 50


@dataclass
class MarketplaceIntegrationBatch(UniversalBatchMixin):
    """Container for Marketplace Response Integration search results."""
    results: List[MarketplaceIntegrationSummary]
    total_count: int
    installed_count: int
    updates_count: int
    retrieved_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


# ==========================================
# Milestone 5.9: Dashboards Domain Models
# ==========================================

@dataclass
class DashboardSummary:
    """Lightweight summary of a Google SecOps Native Dashboard."""
    id: str
    name: str
    display_name: str
    description: str
    type: str  # CUSTOM, DEFAULT, etc.
    create_time: str
    update_time: str
    create_user_id: str
    update_user_id: str
    access: str
    charts_count: int = 0
    raw: Dict[str, Any] = field(default_factory=dict)


@dataclass
class DashboardChartLayout:
    """Grid layout placement coordinates for a dashboard chart widget."""
    start_x: int = 0
    span_x: int = 0
    start_y: int = 0
    span_y: int = 0
    filters_ids: List[str] = field(default_factory=list)


@dataclass
class DashboardQuery:
    """Underlying query definition driving a dashboard chart."""
    id: str
    name: str
    query_text: str
    dialect: str
    time_unit: Optional[str] = None
    time_value: Optional[str] = None
    dashboard_chart: Optional[str] = None
    etag: Optional[str] = None
    raw: Dict[str, Any] = field(default_factory=dict)


@dataclass
class DashboardChart:
    """Full detail of a Dashboard Chart Widget."""
    id: str
    name: str
    display_name: str
    description: str
    tile_type: str
    chart_type: str
    data_sources: List[str]
    visualization: Dict[str, Any]
    drill_down_config: Dict[str, Any]
    layout: Optional[DashboardChartLayout] = None
    query: Optional[DashboardQuery] = None
    query_name: Optional[str] = None
    etag: Optional[str] = None
    raw: Dict[str, Any] = field(default_factory=dict)


@dataclass
class DashboardDetail:
    """Complete composite graph for a Google SecOps Native Dashboard."""
    summary: DashboardSummary
    charts: List[DashboardChart]
    filters: List[Dict[str, Any]] = field(default_factory=list)
    raw: Dict[str, Any] = field(default_factory=dict)


@dataclass
@dataclass
class DashboardSearchQuery:
    """Query parameters for filtering dashboards."""
    query: Optional[str] = None
    dashboard_type: Optional[str] = None
    limit: int = 50


@dataclass
class DashboardBatch(UniversalBatchMixin):
    """Container for native dashboard discovery results."""
    dashboards: List[DashboardSummary]
    total_count: int
    retrieved_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


# =============================================================================
# Milestone 5.10: SIEM Settings, Feeds, Pipelines & Feed Schemas Domain Models
# =============================================================================

@dataclass
class ManagedDomain:
    """Approved email domain for report deliveries and alerts."""
    domain: str
    added_time: str = ""
    added_by: str = ""


@dataclass
class ManagedDomainSettings:
    """Container for managed email domain settings."""
    domains: List[ManagedDomain]
    retrieved_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass
class FeedSummary:
    """Summary of a push/pull ingestion feed."""
    id: str
    name: str
    display_name: str
    state: str = "UNKNOWN"
    feed_source_type: str = "UNKNOWN"
    log_type: str = "UNKNOWN"
    reference_id: str = ""
    raw: Dict[str, Any] = field(default_factory=dict)


@dataclass
class FeedDetail:
    """Deep inspection of an ingestion feed with source configuration."""
    summary: FeedSummary
    details: Dict[str, Any] = field(default_factory=dict)
    raw: Dict[str, Any] = field(default_factory=dict)


@dataclass
class FeedSearchQuery:
    """Query parameters for filtering feeds."""
    query: Optional[str] = None
    feed_source_type: Optional[str] = None
    log_type: Optional[str] = None
    state: Optional[str] = None
    limit: int = 50


@dataclass
class FeedBatch(UniversalBatchMixin):
    """Container for feed discovery results."""
    feeds: List[FeedSummary]
    total_count: int
    retrieved_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass
class LogProcessingPipelineSummary:
    """Summary of a Data Processing Pipeline."""
    id: str
    name: str
    display_name: str
    description: str = ""
    streams: List[str] = field(default_factory=list)
    processors_count: int = 0
    bindplane_url: Optional[str] = None
    create_time: str = ""
    update_time: str = ""
    raw: Dict[str, Any] = field(default_factory=dict)


@dataclass
class LogProcessingPipelineDetail:
    """Deep inspection of a Data Processing Pipeline with transform statements."""
    summary: LogProcessingPipelineSummary
    processors: List[Dict[str, Any]] = field(default_factory=list)
    raw: Dict[str, Any] = field(default_factory=dict)


@dataclass
class LogProcessingPipelineBatch(UniversalBatchMixin):
    """Container for pipeline discovery results."""
    pipelines: List[LogProcessingPipelineSummary]
    total_count: int
    retrieved_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass
class FeedSourceTypeSchema:
    """Schema metadata for a supported feed source type."""
    name: str
    feed_source_type: str
    display_name: str
    description: str = ""
    raw: Dict[str, Any] = field(default_factory=dict)


@dataclass
class FeedLogTypeSchema:
    """Schema metadata for a log type under a feed source."""
    name: str
    log_type: str
    display_name: str
    supporting_documentation: str = ""
    details_field_schemas_count: int = 0
    details_field_schemas: Optional[List[Dict[str, Any]]] = None
    raw: Dict[str, Any] = field(default_factory=dict)


@dataclass
class FeedSourceTypeBatch(UniversalBatchMixin):
    """Container for feed source types catalog."""
    source_types: List[FeedSourceTypeSchema]
    total_count: int
    retrieved_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass
class FeedLogTypeBatch(UniversalBatchMixin):
    """Container for feed log type schemas catalog."""
    feed_source_type: str
    log_types: List[FeedLogTypeSchema]
    total_count: int
    retrieved_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


# ==============================================================================
# Milestone 5.11: SIEM Settings - Parsers, Log Types, Extensions & Settings
# ==============================================================================

@dataclass
class LogTypeSummary:
    """Summary of a supported ingestion log type catalog entry."""
    name: str
    id: str
    display_name: str
    raw: Dict[str, Any] = field(default_factory=dict)


@dataclass
class LogTypeBatch(UniversalBatchMixin):
    """Container for log type catalog results."""
    log_types: List[LogTypeSummary]
    total_count: int
    next_page_token: Optional[str] = None
    retrieved_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass
class ParserSummary:
    """Summary representation of an ingestion parser."""
    name: str
    id: str
    log_type: str
    creator_source: str
    create_time: str
    type: str
    state: str
    release_stage: str
    version: str
    latest_version: str
    rollback_available: bool = False
    raw: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ParserDetail:
    """Deep inspection of a parser including decoded Logstash CBN filter code."""
    summary: ParserSummary
    cbn_raw: Optional[str] = None
    cbn_code: Optional[str] = None
    validation_report: Optional[str] = None
    changelogs: Dict[str, Any] = field(default_factory=dict)
    creator_details: Dict[str, Any] = field(default_factory=dict)
    raw: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ParserBatch(UniversalBatchMixin):
    """Container for parser discovery results."""
    parsers: List[ParserSummary]
    total_count: int
    next_page_token: Optional[str] = None
    retrieved_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass
class ParserExtensionSummary:
    """Summary representation of a parser extension."""
    name: str
    id: str
    log_type: str
    state: str
    create_time: str
    state_last_changed_time: str
    last_live_time: Optional[str] = None
    has_dynamic_parsing: bool = False
    opted_fields_count: int = 0
    has_cbn_snippet: bool = False
    raw: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ParserExtensionDetail:
    """Deep inspection of a parser extension with decoded snippet and sample log."""
    summary: ParserExtensionSummary
    cbn_snippet_raw: Optional[str] = None
    cbn_snippet: Optional[str] = None
    sample_log_raw: Optional[str] = None
    sample_log: Optional[str] = None
    opted_fields: List[Dict[str, str]] = field(default_factory=list)
    validation_report: Optional[str] = None
    extension_validation_report: Optional[str] = None
    raw: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ParserExtensionBatch(UniversalBatchMixin):
    """Container for parser extension discovery results."""
    parser_extensions: List[ParserExtensionSummary]
    total_count: int
    next_page_token: Optional[str] = None
    retrieved_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass
class LogTypeSetting:
    """Autonomous parsing settings for a specific log type."""
    log_type: str
    autonomous_parsing_extraction_type: str
    raw_settings: Dict[str, Any] = field(default_factory=dict)
    retrieved_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


# --------------------------------------------------------------------------
# Milestone 5.12: SIEM Settings - Preview Features & Data RBAC
# --------------------------------------------------------------------------


@dataclass
class PreviewFeatureSummary:
    """Summary of a preview feature flag in Google SecOps."""
    name: str
    id: str
    display_name: str
    description: str
    enabled: bool
    stage: str
    public_documentation_link: str
    expected_retirement_date: Optional[Dict[str, int]] = None
    update_time: Optional[str] = None
    raw: Dict[str, Any] = field(default_factory=dict)


@dataclass
class PreviewFeatureBatch(UniversalBatchMixin):
    """Container for preview features discovery."""
    features: List[PreviewFeatureSummary]
    total_count: int
    enabled_count: int
    retrieved_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass
class DataAccessScopeSummary:
    """Summary of a Data Access Scope (RBAC)."""
    name: str
    id: str
    display_name: str
    description: str
    allow_all: bool
    allowed_labels_count: int
    denied_labels_count: int
    author: str
    last_editor: str
    create_time: str
    update_time: str
    raw: Dict[str, Any] = field(default_factory=dict)


@dataclass
class DataAccessScopeDetail:
    """Deep inspection of a Data Access Scope including label attachments."""
    summary: DataAccessScopeSummary
    allowed_data_access_labels: List[Dict[str, Any]] = field(default_factory=list)
    denied_data_access_labels: List[Dict[str, Any]] = field(default_factory=list)
    details: Dict[str, Any] = field(default_factory=dict)
    retrieved_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass
class DataAccessScopeBatch(UniversalBatchMixin):
    """Container for Data Access Scope search results."""
    scopes: List[DataAccessScopeSummary]
    total_count: int
    global_scope_granted: bool = False
    next_page_token: Optional[str] = None
    retrieved_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass
class DataAccessLabelSummary:
    """Summary of a Data Access Label with UDM filter query."""
    name: str
    id: str
    display_name: str
    description: str
    udm_query: str
    author: str
    last_editor: str
    create_time: str
    update_time: str
    raw: Dict[str, Any] = field(default_factory=dict)


@dataclass
class DataAccessLabelDetail:
    """Deep inspection of a Data Access Label configuration."""
    summary: DataAccessLabelSummary
    details: Dict[str, Any] = field(default_factory=dict)
    retrieved_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass
class DataAccessLabelBatch(UniversalBatchMixin):
    """Container for Data Access Label search results."""
    labels: List[DataAccessLabelSummary]
    total_count: int
    next_page_token: Optional[str] = None
    retrieved_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass
class EnvironmentScopeSummary:
    """Summary of a SOAR multi-tenant environment and its bound Data Access Scopes."""
    name: str
    id: str
    display_name: str
    description: str
    contact: str
    contact_emails: str
    data_access_scopes: List[str] = field(default_factory=list)
    raw: Dict[str, Any] = field(default_factory=dict)


@dataclass
class EnvironmentScopeBatch(UniversalBatchMixin):
    """Container for SOAR environment scope search results."""
    environments: List[EnvironmentScopeSummary]
    total_count: int
    next_page_token: Optional[str] = None
    retrieved_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


# -----------------------------------------------------------------------------
# Milestone 5.13: Remaining SIEM Settings & Enrichment Controls Domain Models
# -----------------------------------------------------------------------------

@dataclass
class EnrichmentCombinationRecord:
    """A supported enrichment type, target log type, and source combination."""
    enrichment_type: str
    target_log_type: str
    source_log_type: Optional[str] = None
    external_source: Optional[str] = None
    raw: Dict[str, Any] = field(default_factory=dict)


@dataclass
class EnrichmentCombinationBatch(UniversalBatchMixin):
    """Container for available enrichment combinations."""
    name: str
    records: List[EnrichmentCombinationRecord]
    total_count: int
    retrieved_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass
class EnrichmentControlSummary:
    """Summary of a deployed enrichment control blocking entity enrichment."""
    id: str
    name: str
    enrichment_type: str
    target_log_type: str
    source: str
    description: str
    records_count: int
    raw: Dict[str, Any] = field(default_factory=dict)


@dataclass
class EnrichmentControlDetail:
    """Full detail of a deployed enrichment control including timing records."""
    summary: EnrichmentControlSummary
    records: List[Dict[str, Any]] = field(default_factory=list)
    raw: Dict[str, Any] = field(default_factory=dict)


@dataclass
class EnrichmentControlBatch(UniversalBatchMixin):
    """Container for search/list results of deployed enrichment controls."""
    controls: List[EnrichmentControlSummary]
    total_count: int
    next_page_token: Optional[str] = None
    retrieved_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass
class GeminiAgentSettings:
    """Configuration settings for the Gemini Triage & Investigation Agent."""
    name: str
    auto_investigation_enabled: bool
    alert_filter: str
    auto_investigation_delay: str
    auto_quota_limit: str
    manual_quota_limit: str
    raw: Dict[str, Any] = field(default_factory=dict)


@dataclass
class EntityRiskConfig:
    """Entity Risk Scoring (UEBA) configuration parameters."""
    name: str
    default_detection_risk_score: int
    default_alert_risk_score: int
    default_weighting_factor: float
    default_closed_alert_coefficient: float
    raw: Dict[str, Any] = field(default_factory=dict)


@dataclass
class TenantInstanceDetails:
    """Root tenant instance metadata, endpoints, and configuration flags."""
    id: str
    name: str
    state: str
    display_name: str
    customer_code: str
    create_time: str
    secops_urls: List[str] = field(default_factory=list)
    secops_ui_enabled: bool = False
    data_rbac_enabled: bool = False
    triage_agent_enabled: bool = False
    frontend_paths: List[Dict[str, str]] = field(default_factory=list)
    raw: Dict[str, Any] = field(default_factory=dict)


# --- Milestone 6.1: SOAR Settings & Case Data Configuration ---


@dataclass
class SoarUserSummary:
    """Summary of a local/external SOAR user representation."""
    id: str
    name: str
    user_full_name: str
    first_name: str
    last_name: str
    email: str
    login_identifier: str
    provider_name: str
    user_type: str
    account_state: str
    last_login_time: Optional[str] = None
    soc_roles: List[int] = field(default_factory=list)
    permission_groups: List[Dict[str, str]] = field(default_factory=list)
    has_all_environments_access: bool = False
    raw: Dict[str, Any] = field(default_factory=dict)


@dataclass
class SoarUserDetail:
    """Deep inspection of a single SOAR user."""
    summary: SoarUserSummary
    environments_json: str
    allowed_platforms: List[str] = field(default_factory=list)
    raw: Dict[str, Any] = field(default_factory=dict)


@dataclass
class SoarUserBatch(UniversalBatchMixin):
    """Batch of SOAR users with pagination metadata."""
    users: List[SoarUserSummary]
    total_count: int
    next_page_token: Optional[str] = None
    retrieved_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass
class SocRoleSummary:
    """Summary of a SOC role used for case and task assignment."""
    id: str
    name: str
    display_name: str
    additional_roles_access: List[str] = field(default_factory=list)
    raw: Dict[str, Any] = field(default_factory=dict)


@dataclass
class SocRoleBatch(UniversalBatchMixin):
    """Batch of SOC roles."""
    roles: List[SocRoleSummary]
    total_count: int
    retrieved_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass
class CompanySettingProperty:
    """Company / Rebranding setting property."""
    name: str
    property_key: str
    display_name: str
    value: str
    type: str
    raw: Dict[str, Any] = field(default_factory=dict)


@dataclass
class CompanySettingsBatch(UniversalBatchMixin):
    """Batch of company rebranding settings."""
    properties: List[CompanySettingProperty]
    total_count: int
    retrieved_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass
class CaseTagDefinitionSummary:
    """Summary of a case tag definition rule."""
    id: str
    name: str
    display_name: str
    match_criteria: str
    comparison_type: str
    priority: int
    can_be_case_title: bool = False
    raw: Dict[str, Any] = field(default_factory=dict)


@dataclass
class CaseTagDefinitionBatch(UniversalBatchMixin):
    """Batch of case tag definitions with pagination metadata."""
    tags: List[CaseTagDefinitionSummary]
    total_count: int
    next_page_token: Optional[str] = None
    retrieved_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass
class CaseStageDefinitionSummary:
    """Summary of an ordered SOC case lifecycle stage."""
    id: str
    name: str
    display_name: str
    order: int
    raw: Dict[str, Any] = field(default_factory=dict)


@dataclass
class CaseStageDefinitionBatch(UniversalBatchMixin):
    """Batch of case stage definitions."""
    stages: List[CaseStageDefinitionSummary]
    total_count: int
    retrieved_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass
class CaseCloseDefinitionSummary:
    """Summary of a predefined case close reason and root cause."""
    id: str
    name: str
    close_reason: str
    root_cause: str
    raw: Dict[str, Any] = field(default_factory=dict)


@dataclass
class CaseCloseDefinitionBatch(UniversalBatchMixin):
    """Batch of case close definitions."""
    definitions: List[CaseCloseDefinitionSummary]
    total_count: int
    retrieved_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass
class CaseCloseDynamicParameterSummary:
    """Summary of dynamic parameter and related custom field schema for case closure."""
    id: str
    form_type: str
    order: int
    related_custom_field_id: str
    custom_field_display_name: str
    custom_field_type: str
    allowed_values: List[str] = field(default_factory=list)
    raw: Dict[str, Any] = field(default_factory=dict)


@dataclass
class CaseCloseDynamicParameterBatch(UniversalBatchMixin):
    """Batch of dynamic close case form parameters."""
    parameters: List[CaseCloseDynamicParameterSummary]
    total_count: int
    retrieved_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass
class CaseTitleSettingProperty:
    """Case title naming rule property."""
    name: str
    property_key: str
    display_name: str
    value: str
    type: str
    raw: Dict[str, Any] = field(default_factory=dict)


@dataclass
class CaseTitleSettingsBatch(UniversalBatchMixin):
    """Batch of case title naming properties."""
    properties: List[CaseTitleSettingProperty]
    total_count: int
    retrieved_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

# --- Milestone 6.2: Views, Custom Fields & Calculated Fields ---

@dataclass
class ViewWidgetMetadata:
    """Metadata for a view widget."""
    id: str
    identifier: str
    title: str
    width: str
    order: int
    description: str
    type: str
    template_identifier: str = ""
    present_if_empty: bool = False
    raw: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ViewWidget:
    """Widget layout and configuration inside a view."""
    metadata: ViewWidgetMetadata
    config: Dict[str, Any] = field(default_factory=dict)
    raw: Dict[str, Any] = field(default_factory=dict)


@dataclass
class CaseViewSummary:
    """Summary of a case/alert layout view template."""
    id: str
    name: str
    display_name: str
    identifier: str
    type: Optional[str] = None
    is_default: Optional[bool] = None
    raw: Dict[str, Any] = field(default_factory=dict)


@dataclass
class CaseViewDetail:
    """Deep inspection of a case/alert layout view template."""
    summary: CaseViewSummary
    widgets: List[ViewWidget] = field(default_factory=list)
    raw: Dict[str, Any] = field(default_factory=dict)


@dataclass
class CaseViewBatch(UniversalBatchMixin):
    """Batch of case/alert layout views with pagination metadata."""
    views: List[CaseViewSummary]
    total_count: int
    next_page_token: Optional[str] = None
    retrieved_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass
class CustomFieldSummary:
    """Summary of a custom typed field."""
    id: str
    name: str
    display_name: str
    type: str
    scopes: str
    values: List[str] = field(default_factory=list)
    raw: Dict[str, Any] = field(default_factory=dict)


@dataclass
class CustomFieldDetail:
    """Deep inspection of a custom field definition."""
    summary: CustomFieldSummary
    ordered_values: List[Dict[str, Any]] = field(default_factory=list)
    raw: Dict[str, Any] = field(default_factory=dict)


@dataclass
class CustomFieldBatch(UniversalBatchMixin):
    """Batch of custom fields with pagination metadata."""
    custom_fields: List[CustomFieldSummary]
    total_count: int
    retrieved_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass
class CalculatedFieldSummary:
    """Summary of a calculated field formula definition."""
    id: str
    name: str
    target_field: str
    formula: str
    enabled: bool = True
    description: Optional[str] = None
    raw: Dict[str, Any] = field(default_factory=dict)


@dataclass
class CalculatedFieldDetail:
    """Deep inspection of a calculated field definition."""
    summary: CalculatedFieldSummary
    raw: Dict[str, Any] = field(default_factory=dict)


@dataclass
class CalculatedFieldBatch(UniversalBatchMixin):
    """Batch of calculated field definitions."""
    definitions: List[CalculatedFieldSummary]
    total_count: int
    retrieved_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


# --- Milestone 6.3: Alert Grouping & General SOAR Settings ---

@dataclass
class AlertGroupingCategoryDetail:
    """Specific alert type or product category detail in an alert grouping rule."""
    identifier: str
    display_name: str


@dataclass
class AlertGroupingRuleSummary:
    """Summary of an alert grouping rule."""
    id: str
    name: str
    category: str
    grouping_type: str
    entity_types: List[str] = field(default_factory=list)
    category_details_count: int = 0
    raw: Dict[str, Any] = field(default_factory=dict)


@dataclass
class AlertGroupingRuleDetail:
    """Deep inspection of an alert grouping rule."""
    summary: AlertGroupingRuleSummary
    category_details: List[AlertGroupingCategoryDetail] = field(default_factory=list)
    raw: Dict[str, Any] = field(default_factory=dict)


@dataclass
class AlertGroupingRuleBatch(UniversalBatchMixin):
    """Batch of alert grouping rules."""
    rules: List[AlertGroupingRuleSummary]
    total_count: int
    retrieved_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass
class AlertGroupingSettingProperty:
    """Alert grouping global configuration setting property."""
    name: str
    property_key: str
    display_name: str
    value: str
    type: str
    raw: Dict[str, Any] = field(default_factory=dict)


@dataclass
class AlertGroupingSettingsBatch(UniversalBatchMixin):
    """Batch of alert grouping global settings."""
    properties: List[AlertGroupingSettingProperty]
    total_count: int
    retrieved_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass
class DataRetentionSettingProperty:
    """Data retention configuration setting property."""
    name: str
    property_key: str
    display_name: str
    value: str
    type: str
    raw: Dict[str, Any] = field(default_factory=dict)


@dataclass
class DataRetentionSettingsBatch(UniversalBatchMixin):
    """Batch of data retention configuration properties."""
    properties: List[DataRetentionSettingProperty]
    total_count: int
    retrieved_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass
class EnvironmentSummary:
    """Summary of a SOAR multi-tenancy environment boundary."""
    id: str
    name: str
    display_name: str
    retention_duration: int
    system: bool
    weight: int
    aliases: List[str] = field(default_factory=list)
    data_access_scopes: List[str] = field(default_factory=list)
    raw: Dict[str, Any] = field(default_factory=dict)


@dataclass
class EnvironmentDetail:
    """Deep inspection of a single multi-tenancy environment."""
    summary: EnvironmentSummary
    raw: Dict[str, Any] = field(default_factory=dict)


@dataclass
class EnvironmentBatch(UniversalBatchMixin):
    """Batch of multi-tenancy environments."""
    environments: List[EnvironmentSummary]
    total_count: int
    retrieved_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass
class EnvironmentGroupSummary:
    """Logical grouping of multi-tenancy environments."""
    id: str
    name: str
    display_name: str
    environments: List[str] = field(default_factory=list)
    raw: Dict[str, Any] = field(default_factory=dict)


@dataclass
class EnvironmentGroupBatch(UniversalBatchMixin):
    """Batch of environment groups."""
    groups: List[EnvironmentGroupSummary]
    total_count: int
    retrieved_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass
class RemoteAgentSummary:
    """Summary of a remote SOAR execution agent."""
    id: str
    name: str
    display_name: str
    identifier: str
    environments: List[str]
    agent_state: str
    logging_level: str
    installer_link: str
    raw: Dict[str, Any] = field(default_factory=dict)


@dataclass
class RemoteAgentDetail:
    """Deep inspection of a remote agent including certificate and bindings."""
    summary: RemoteAgentSummary
    certificate: str
    raw: Dict[str, Any] = field(default_factory=dict)


@dataclass
class RemoteAgentBatch(UniversalBatchMixin):
    """Batch of remote SOAR agents."""
    remote_agents: List[RemoteAgentSummary]
    total_count: int
    retrieved_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass
class EmailSettingProperty:
    """Email transport configuration setting property."""
    name: str
    property_key: str
    display_name: str
    value: str
    type: str
    raw: Dict[str, Any] = field(default_factory=dict)


@dataclass
class EmailSettingsBatch(UniversalBatchMixin):
    """Batch of email transport settings combining type and SMTP properties."""
    properties: List[EmailSettingProperty]
    use_custom: bool
    total_count: int
    retrieved_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass
class SupportSettingProperty:
    """Google Support access delegation setting property."""
    name: str
    property_key: str
    display_name: str
    value: str
    type: str
    raw: Dict[str, Any] = field(default_factory=dict)


@dataclass
class SupportSettingsBatch(UniversalBatchMixin):
    """Batch of Google Support access delegation properties."""
    properties: List[SupportSettingProperty]
    total_count: int
    retrieved_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass
class SoarNetworkSummary:
    """Summary of a customer-defined CIDR network address range."""
    id: str
    name: str
    display_name: str
    address: str
    environments: List[str] = field(default_factory=list)
    priority: int = 0
    raw: Dict[str, Any] = field(default_factory=dict)


@dataclass
class SoarNetworkDetail:
    """Deep inspection of a customer-defined CIDR network."""
    summary: SoarNetworkSummary
    raw: Dict[str, Any] = field(default_factory=dict)
    retrieved_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass
class SoarNetworkBatch(UniversalBatchMixin):
    """Batch of customer-defined CIDR network address ranges."""
    networks: List[SoarNetworkSummary]
    total_count: int
    next_page_token: Optional[str] = None
    retrieved_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass
class SoarDomainSummary:
    """Summary of an approved customer domain name."""
    id: str
    name: str
    display_name: str
    environments: List[str] = field(default_factory=list)
    raw: Dict[str, Any] = field(default_factory=dict)


@dataclass
class SoarDomainDetail:
    """Deep inspection of an approved customer domain name."""
    summary: SoarDomainSummary
    raw: Dict[str, Any] = field(default_factory=dict)
    retrieved_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass
class SoarDomainBatch(UniversalBatchMixin):
    """Batch of approved customer domain names."""
    domains: List[SoarDomainSummary]
    total_count: int
    next_page_token: Optional[str] = None
    retrieved_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass
class SoarCustomListSummary:
    """Summary of a SOAR custom list key-value retention entry."""
    id: str
    name: str
    category: str
    entity_identifier: str
    environments: List[str] = field(default_factory=list)
    raw: Dict[str, Any] = field(default_factory=dict)


@dataclass
class SoarCustomListDetail:
    """Deep inspection of a SOAR custom list key-value retention entry."""
    summary: SoarCustomListSummary
    raw: Dict[str, Any] = field(default_factory=dict)
    retrieved_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass
class SoarCustomListBatch(UniversalBatchMixin):
    """Batch of SOAR custom list key-value retention entries."""
    custom_lists: List[SoarCustomListSummary]
    total_count: int
    next_page_token: Optional[str] = None
    retrieved_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass
class EmailTemplateSummary:
    """Summary of an email template used in SOAR playbooks."""
    id: str
    name: str
    display_name: str
    template_type: str
    author: str
    environments: List[str] = field(default_factory=list)
    raw: Dict[str, Any] = field(default_factory=dict)


@dataclass
class EmailTemplateDetail:
    """Deep inspection of an email template including content body/markup."""
    summary: EmailTemplateSummary
    content: str
    raw: Dict[str, Any] = field(default_factory=dict)
    retrieved_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass
class EmailTemplateBatch(UniversalBatchMixin):
    """Batch of email templates."""
    email_templates: List[EmailTemplateSummary]
    total_count: int
    next_page_token: Optional[str] = None
    retrieved_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass
class EntitiesBlocklistSummary:
    """Summary of an entity noise-reduction blocklist rule."""
    id: str
    name: str
    entity_identifier: str
    entity_type: str
    action: str
    environments: List[str] = field(default_factory=list)
    raw: Dict[str, Any] = field(default_factory=dict)


@dataclass
class EntitiesBlocklistDetail:
    """Deep inspection of an entity noise-reduction blocklist rule."""
    summary: EntitiesBlocklistSummary
    raw: Dict[str, Any] = field(default_factory=dict)
    retrieved_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass
class EntitiesBlocklistBatch(UniversalBatchMixin):
    """Batch of entity noise-reduction blocklist rules."""
    blocklist_entries: List[EntitiesBlocklistSummary]
    total_count: int
    next_page_token: Optional[str] = None
    retrieved_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass
class SlaDefinitionSummary:
    """Summary of a Service Level Agreement definition."""
    id: str
    name: str
    sla_type: str
    sla_type_values: List[str] = field(default_factory=list)
    sla_period: int = 0
    sla_period_time_unit: str = "MINUTES"
    critical_sla_period: int = 0
    critical_sla_period_time_unit: str = "MINUTES"
    environments: List[str] = field(default_factory=list)
    raw: Dict[str, Any] = field(default_factory=dict)


@dataclass
class SlaDefinitionDetail:
    """Deep inspection of a Service Level Agreement definition."""
    summary: SlaDefinitionSummary
    raw: Dict[str, Any] = field(default_factory=dict)
    retrieved_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass
class SlaDefinitionBatch(UniversalBatchMixin):
    """Batch of Service Level Agreement definitions."""
    sla_definitions: List[SlaDefinitionSummary]
    total_count: int
    next_page_token: Optional[str] = None
    retrieved_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass
class RequestTemplateFieldDefinition:
    """Typed form field definition within a case request template."""
    name: str
    entity_types: List[str] = field(default_factory=list)
    watermark: str = ""
    field_type: str = "STRING"
    raw: Dict[str, Any] = field(default_factory=dict)


@dataclass
class RequestTemplateSummary:
    """Summary of a manual case request form template."""
    id: str
    name: str
    display_name: str
    visual_family: str
    allow_description: bool = False
    environments: List[str] = field(default_factory=list)
    field_count: int = 0
    raw: Dict[str, Any] = field(default_factory=dict)


@dataclass
class RequestTemplateDetail:
    """Deep inspection of a manual case request form template including field definitions."""
    summary: RequestTemplateSummary
    event_field_definitions: List[RequestTemplateFieldDefinition] = field(default_factory=list)
    raw: Dict[str, Any] = field(default_factory=dict)
    retrieved_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass
class RequestTemplateBatch(UniversalBatchMixin):
    """Batch of manual case request form templates."""
    request_templates: List[RequestTemplateSummary]
    total_count: int
    next_page_token: Optional[str] = None
    retrieved_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


# ==============================================================================
# Milestone 6.6: SOAR Settings - Ingestion Connectors & Webhooks
# ==============================================================================

@dataclass
class SoarIngestionConnectorSummary:
    """Summary of a configured SOAR ingestion connector instance."""
    id: str
    name: str
    display_name: str
    identifier: str = ""
    integration: str = ""
    connector_id: str = ""
    connector_definition_name: str = ""
    environment: str = ""
    enabled: bool = False
    remote: bool = False
    interval_seconds: int = 0
    raw: Dict[str, Any] = field(default_factory=dict)


@dataclass
class SoarIngestionConnectorDetail:
    """Deep inspection of a SOAR ingestion connector instance."""
    summary: SoarIngestionConnectorSummary
    description: str = ""
    product_field_name: str = ""
    event_field_name: str = ""
    timeout_seconds: str = ""
    integration_version: str = ""
    version: str = ""
    update_available: bool = False
    status: str = "UNKNOWN"
    documentation_link: str = ""
    parameters: List[Dict[str, Any]] = field(default_factory=list)
    raw: Dict[str, Any] = field(default_factory=dict)
    retrieved_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass
class SoarIngestionConnectorBatch(UniversalBatchMixin):
    """Batch of SOAR ingestion connector instances."""
    connectors: List[SoarIngestionConnectorSummary]
    total_count: int
    next_page_token: Optional[str] = None
    retrieved_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass
class SoarWebhookSummary:
    """Summary of a SOAR event ingestion webhook."""
    id: str
    name: str
    display_name: str
    environment: str = ""
    enabled: bool = False
    description: str = ""
    raw: Dict[str, Any] = field(default_factory=dict)


@dataclass
class SoarWebhookDetail:
    """Deep inspection of a SOAR event ingestion webhook with schema mapping."""
    summary: SoarWebhookSummary
    webhook_mapping: Dict[str, str] = field(default_factory=dict)
    postfix: str = ""
    raw: Dict[str, Any] = field(default_factory=dict)
    retrieved_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass
class SoarWebhookBatch(UniversalBatchMixin):
    """Batch of SOAR event ingestion webhooks."""
    webhooks: List[SoarWebhookSummary]
    total_count: int
    next_page_token: Optional[str] = None
    retrieved_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass
class EnterpriseIocMatch:
    """Enterprise-wide IoC match with Mandiant intelligence and asset correlations."""
    artifact_indicator: Dict[str, Any] = field(default_factory=dict)
    sources: List[str] = field(default_factory=list)
    categories: List[str] = field(default_factory=list)
    asset_indicators: List[Dict[str, Any]] = field(default_factory=list)
    ioc_ingest_timestamp: Optional[str] = None
    first_seen: Optional[str] = None
    last_seen: Optional[str] = None
    raw: Dict[str, Any] = field(default_factory=dict)


@dataclass
class EnterpriseIocBatch(UniversalBatchMixin):
    """Batch of enterprise-wide IoC matches."""
    matches: List[EnterpriseIocMatch] = field(default_factory=list)
    total_count: int = 0
    searched_value: str = ""
    value_type: str = ""
    retrieved_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    @property
    def results(self) -> List[EnterpriseIocMatch]:
        return self.matches


@dataclass
class EntityTimelineInterval:
    start_time: Optional[str] = None
    end_time: Optional[str] = None


@dataclass
class EntitySummaryResult:
    """Entity summary profile including timeline intervals, prevalence, and metadata."""
    entity_id: str
    entity_type: str = ""
    timeline: List[Dict[str, Any]] = field(default_factory=list)
    prevalence: Dict[str, Any] = field(default_factory=dict)
    file_metadata: Dict[str, Any] = field(default_factory=dict)
    entities: List[Dict[str, Any]] = field(default_factory=list)
    raw: Dict[str, Any] = field(default_factory=dict)
    retrieved_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass
class EntityInvestigationReport:
    """Composite investigation report across Graph Entities, UDM Events, IoCs, and SOAR Cases."""
    indicator: str
    detected_type: str
    category: str
    entity_graph_events_count: int = 0
    udm_events_count: int = 0
    enterprise_iocs_count: int = 0
    related_cases_count: int = 0
    graph_events: List[Dict[str, Any]] = field(default_factory=list)
    udm_events: List[Dict[str, Any]] = field(default_factory=list)
    ioc_matches: List[EnterpriseIocMatch] = field(default_factory=list)
    related_cases: List[Any] = field(default_factory=list)
    entity_summary: Optional[EntitySummaryResult] = None
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass
class CaseUpdateResult:
    """Result of updating a Google SecOps case."""
    case_id: str
    name: str
    assignee: Optional[str] = None
    stage: Optional[str] = None
    incident: Optional[bool] = None
    priority: Optional[str] = None
    status: Optional[str] = None
    display_name: Optional[str] = None
    raw: Dict[str, Any] = field(default_factory=dict)
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass
class CaseAlertUpdateResult:
    """Result of updating a Google SecOps case alert."""
    alert_name: str
    case_id: str
    alert_id: str
    priority: Optional[str] = None
    status: Optional[str] = None
    display_name: Optional[str] = None
    raw: Dict[str, Any] = field(default_factory=dict)
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass
class CaseAlertRecommendationJob:
    """Async generation job handle for a Gemini AI Case Alert Recommendation."""
    case_id: str
    alert_id: str
    recommendation_id: str
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    raw: Dict[str, Any] = field(default_factory=dict)


@dataclass
class CaseAlertRecommendation:
    """Gemini AI Case Alert Recommendation result and diagnostics."""
    case_id: str
    recommendation_id: str
    state: str = "UNSPECIFIED"
    recommendation: Optional[str] = None
    alert_identifier_to_case_id: Dict[str, int] = field(default_factory=dict)
    marketplace_actions_triggered_manually: List[str] = field(default_factory=list)
    status_message: Optional[str] = None
    raw: Dict[str, Any] = field(default_factory=dict)
    fetched_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass
class CaseSummary:
    """Gemini AI Case Summary containing high-level overview, reasons, and recommended next steps."""
    case_id: str
    state: str = "SUMMARY_STATE_UNSPECIFIED"
    summary: Optional[str] = None
    reasons: List[str] = field(default_factory=list)
    next_steps: List[str] = field(default_factory=list)
    markdown_results: Optional[Dict[str, Any]] = None
    update_time: Optional[datetime] = None
    raw: Dict[str, Any] = field(default_factory=dict)
    fetched_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass
class DataTableColumnInfo:
    """Column definition within a Google Chronicle SIEM Data Table."""
    column_index: int
    original_column: str
    column_type: str = "STRING"
    mapped_column_path: Optional[str] = None
    key_column: bool = False
    repeated_values: bool = False
    raw: Dict[str, Any] = field(default_factory=dict)

    @property
    def column_name(self) -> str:
        """Alias for original_column."""
        return self.original_column

    @property
    def data_type(self) -> str:
        """Alias for column_type."""
        return self.column_type

    @property
    def is_key_column(self) -> bool:
        """Alias for key_column."""
        return self.key_column


@dataclass
class DataTableRow:
    """Single row of values inside a Google Chronicle SIEM Data Table."""
    name: str
    values: List[str] = field(default_factory=list)
    id: str = ""
    create_time: Optional[datetime] = None
    update_time: Optional[datetime] = None
    row_time_to_live: Optional[str] = None
    raw: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        if not self.id and self.name:
            self.id = self.name.split("/")[-1]

    @property
    def row_id(self) -> str:
        """Alias for the row identifier."""
        return self.id


@dataclass
class DataTable:
    """Google Chronicle SIEM structured Data Table metadata and schema."""
    name: str
    id: str
    display_name: str
    description: Optional[str] = None
    column_info: List[DataTableColumnInfo] = field(default_factory=list)
    approximate_row_count: Optional[int] = None
    rule_associations_count: Optional[int] = None
    rules: List[str] = field(default_factory=list)
    row_time_to_live: Optional[str] = None
    scope_info: Optional[Dict[str, Any]] = None
    data_table_uuid: Optional[str] = None
    create_time: Optional[datetime] = None
    update_time: Optional[datetime] = None
    raw: Dict[str, Any] = field(default_factory=dict)

    @property
    def table_id(self) -> str:
        """Alias for the data table identifier."""
        return self.id


@dataclass
class DataTableListResult:
    """Result container for listed Chronicle SIEM Data Tables."""
    tables: List[DataTable]
    next_page_token: Optional[str] = None
    total_size: Optional[int] = None
    provenance: Dict[str, Any] = field(default_factory=dict)

    @property
    def items(self) -> List[DataTable]:
        """Uniform alias for batch results across all engine domains."""
        return self.tables

    @property
    def data_tables(self) -> List[DataTable]:
        """Convenience alias for listed tables."""
        return self.tables


@dataclass
class DataTableRowListResult:
    """Result container for listed rows within a Chronicle SIEM Data Table."""
    table_name: str
    rows: List[DataTableRow]
    next_page_token: Optional[str] = None
    total_size: Optional[int] = None
    provenance: Dict[str, Any] = field(default_factory=dict)

    @property
    def items(self) -> List[DataTableRow]:
        """Uniform alias for batch results across all engine domains."""
        return self.rows


@dataclass
class RuleSeverity:
    """Severity classification for a detection rule."""
    name: str = ""
    display_name: str = ""


@dataclass
class RuleCompilationDiagnostic:
    """Diagnostic message from YARA-L rule compilation / validation."""
    message: str = ""
    severity: str = ""
    start_line: Optional[int] = None
    start_column: Optional[int] = None
    end_line: Optional[int] = None
    end_column: Optional[int] = None
    raw: Dict[str, Any] = field(default_factory=dict)


@dataclass
class RuleValidationResult:
    """Result of YARA-L rule verification / validation."""
    success: bool = False
    diagnostics: List[RuleCompilationDiagnostic] = field(default_factory=list)
    raw: Dict[str, Any] = field(default_factory=dict)


@dataclass
class RuleDeployment:
    """Deployment configuration and status for a Chronicle SIEM rule."""
    name: str = ""
    run_frequency: str = "LIVE"
    execution_state: str = "DEFAULT"
    enabled: bool = False
    alerting: bool = False
    last_alert_status_change_time: str = ""
    display_name: str = ""
    raw: Dict[str, Any] = field(default_factory=dict)


@dataclass
class RuleExecutionError:
    """Execution / runtime error record for a detection rule."""
    name: str = ""
    error_code: int = 0
    error_message: str = ""
    start_time: str = ""
    end_time: str = ""
    rule_resource_name: str = ""
    curated_rule: str = ""
    raw: Dict[str, Any] = field(default_factory=dict)

    @property
    def rule_id(self) -> str:
        target = self.rule_resource_name or self.curated_rule
        return target.split("/")[-1] if target else ""


@dataclass
class RuleExecutionErrorListResult:
    """Result container for rule execution errors."""
    errors: List[RuleExecutionError] = field(default_factory=list)
    next_page_token: Optional[str] = None
    provenance: Dict[str, Any] = field(default_factory=dict)

    @property
    def items(self) -> List[RuleExecutionError]:
        return self.errors


@dataclass
class RuleSummary:
    """Summary representation of a Chronicle SIEM custom detection rule."""
    name: str
    display_name: str
    author: str = ""
    severity: str = "INFO"
    rule_type: str = "SINGLE_EVENT"
    allowed_run_frequencies: List[str] = field(default_factory=list)
    near_real_time_live_rule_eligible: bool = False
    etag: str = ""
    rule_text_tags: List[str] = field(default_factory=list)
    time_window_duration: str = ""
    create_time: str = ""
    revision_id: str = ""
    run_frequency: str = ""
    raw: Dict[str, Any] = field(default_factory=dict)

    @property
    def rule_id(self) -> str:
        return self.name.split("/")[-1].split("@")[0] if self.name else ""


@dataclass
class RuleDetail:
    """Full detail of a Chronicle SIEM detection rule including YARA-L logic."""
    name: str
    display_name: str
    text: str
    revision_id: str = ""
    author: str = ""
    severity: str = "INFO"
    metadata: Dict[str, str] = field(default_factory=dict)
    create_time: str = ""
    revision_create_time: str = ""
    compilation_state: str = "SUCCEEDED"
    rule_type: str = "SINGLE_EVENT"
    allowed_run_frequencies: List[str] = field(default_factory=list)
    etag: str = ""
    near_real_time_live_rule_eligible: bool = False
    inputs_used: Dict[str, Any] = field(default_factory=dict)
    rule_owner: str = "CUSTOMER"
    run_frequency: str = "LIVE"
    rule_language: str = "YARA_L_2_0"
    raw: Dict[str, Any] = field(default_factory=dict)

    @property
    def rule_id(self) -> str:
        return self.name.split("/")[-1].split("@")[0] if self.name else ""

    @property
    def yara_l_code(self) -> str:
        return self.text


@dataclass
class RuleListResult:
    """Result container for listed Chronicle SIEM detection rules."""
    rules: List[RuleSummary] = field(default_factory=list)
    next_page_token: Optional[str] = None
    provenance: Dict[str, Any] = field(default_factory=dict)

    @property
    def items(self) -> List[RuleSummary]:
        return self.rules


@dataclass
class RuleRevisionListResult:
    """Result container for listed revisions of a detection rule."""
    rule_id: str
    revisions: List[RuleDetail] = field(default_factory=list)
    next_page_token: Optional[str] = None
    provenance: Dict[str, Any] = field(default_factory=dict)

    @property
    def items(self) -> List[RuleDetail]:
        return self.revisions





















