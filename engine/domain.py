from __future__ import annotations

import os
import re
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from enum import Enum

from typing import Any, Dict, List, Optional, Tuple, Union



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


_ENTITY_TYPE_ALIASES: Dict[str, EntityType] = {
    "ip": EntityType.IP,
    "ipv4": EntityType.IP,
    "ipv6": EntityType.IP,
    "ip_address": EntityType.IP,
    "ipaddress": EntityType.IP,
    "host": EntityType.HOSTNAME,
    "hostname": EntityType.HOSTNAME,
    "user": EntityType.USER,
    "username": EntityType.USER,
    "user_name": EntityType.USER,
    "userid": EntityType.USER,
    "user_id": EntityType.USER,
    "sha256": EntityType.SHA256,
    "hash": EntityType.SHA256,
    "md5": EntityType.MD5,
    "sha1": EntityType.SHA1,
    "domain": EntityType.DOMAIN,
    "domain_name": EntityType.DOMAIN,
    "email": EntityType.EMAIL,
    "email_address": EntityType.EMAIL,
    "mac": EntityType.MAC,
    "mac_address": EntityType.MAC,
    "url": EntityType.URL,
    "windows_sid": EntityType.WINDOWS_SID,
    "sid": EntityType.WINDOWS_SID,
    "resource": EntityType.RESOURCE,
    "file": EntityType.FILE,
    "filename": EntityType.FILE,
}


def coerce_entity_type(val: Union[EntityType, str]) -> EntityType:
    """Coerces a string or EntityType into a canonical EntityType enum member.
    
    Supports case-insensitive lookups, aliases (e.g. 'ip_address', 'host', 'hash'),
    and hyphen/space/underscore variations.
    """
    if isinstance(val, EntityType):
        return val
    if not isinstance(val, str):
        raise TypeError(f"Expected EntityType or str, got {type(val).__name__}")
    key = val.strip().lower().replace("-", "_").replace(" ", "_")
    if key in _ENTITY_TYPE_ALIASES:
        return _ENTITY_TYPE_ALIASES[key]
    upper = val.strip().upper().replace("-", "_").replace(" ", "_")
    try:
        return EntityType[upper]
    except KeyError:
        try:
            return EntityType(upper)
        except ValueError:
            valid = ", ".join(e.value for e in EntityType)
            raise ValueError(f"Unknown entity type '{val}'. Valid types: {valid}")


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


class UniversalDictMixin(dict):
    """Universal dataclass mixin providing backward-compatible dict inheritance and field access."""

    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)
        from dataclasses import fields as dc_fields
        orig_post_init = getattr(cls, "__post_init__", None)

        def __post_init__(self, *args, **post_kwargs):
            try:
                dict.__init__(self, {f.name: getattr(self, f.name) for f in dc_fields(self)})
            except Exception:
                pass
            if orig_post_init:
                orig_post_init(self, *args, **post_kwargs)

        cls.__post_init__ = __post_init__

    def __getitem__(self, key: str) -> Any:
        if hasattr(self, key):
            return getattr(self, key)
        return super().__getitem__(key)

    def get(self, key: str, default: Any = None) -> Any:
        return getattr(self, key, super().get(key, default))

    def __contains__(self, key: Any) -> bool:
        return hasattr(self, key) or super().__contains__(key)

    def to_dict(self) -> Dict[str, Any]:
        from dataclasses import asdict
        try:
            return asdict(self)
        except Exception:
            return dict(self)


@dataclass
class FieldFilter:
    field_path: str = ""
    operator: FilterOperator = FilterOperator.EQUALS
    value: Any = None
    field: Optional[str] = None

    def __post_init__(self):
        if not self.field_path and self.field:
            self.field_path = self.field
        elif self.field_path and not self.field:
            self.field = self.field_path

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


_OPERATOR_ALIASES: Dict[str, FilterOperator] = {
    "=": FilterOperator.EQUALS,
    "==": FilterOperator.EQUALS,
    "eq": FilterOperator.EQUALS,
    "equals": FilterOperator.EQUALS,
    "!=": FilterOperator.NOT_EQUALS,
    "ne": FilterOperator.NOT_EQUALS,
    "not_equals": FilterOperator.NOT_EQUALS,
    "=~": FilterOperator.REGEX_MATCH,
    "regex": FilterOperator.REGEX_MATCH,
    "regex_match": FilterOperator.REGEX_MATCH,
    "contains": FilterOperator.CONTAINS,
    "nocase": FilterOperator.NOCASE_EQUALS,
    "nocase_equals": FilterOperator.NOCASE_EQUALS,
    "= ... nocase": FilterOperator.NOCASE_EQUALS,
}


def coerce_filter_operator(op: Union[FilterOperator, str]) -> FilterOperator:
    """Coerces an operator string or FilterOperator into a canonical FilterOperator."""
    if isinstance(op, FilterOperator):
        return op
    key = str(op).strip().lower()
    if key in _OPERATOR_ALIASES:
        return _OPERATOR_ALIASES[key]
    upper = str(op).strip().upper()
    try:
        return FilterOperator[upper]
    except KeyError:
        try:
            return FilterOperator(str(op).strip())
        except ValueError:
            return FilterOperator.EQUALS


def coerce_field_filters(filters: Union[List[Any], Any]) -> List[FieldFilter]:
    """Normalizes single filters, dicts, or tuples into a canonical List[FieldFilter].
    
    Accepts:
    - Single FieldFilter or List[FieldFilter]
    - Single dict or list of dicts: {"field": "principal.ip", "operator": "=", "value": "1.2.3.4"}
    - Single tuple or list of tuples: ("principal.ip", "=", "1.2.3.4") or ("principal.ip", "1.2.3.4")
    """
    if filters is None:
        return []
    if isinstance(filters, FieldFilter):
        return [filters]
    if isinstance(filters, dict):
        path = filters.get("field_path") or filters.get("field") or filters.get("path")
        op = coerce_filter_operator(filters.get("operator", "="))
        val = filters.get("value")
        if not path:
            raise ValueError("Dictionary filter must contain 'field' or 'field_path'")
        return [FieldFilter(field_path=path, operator=op, value=val)]
    if isinstance(filters, (tuple, list)) and len(filters) in (2, 3) and isinstance(filters[0], str):
        path = filters[0]
        if len(filters) == 3:
            op = coerce_filter_operator(filters[1])
            val = filters[2]
        else:
            op = FilterOperator.EQUALS
            val = filters[1]
        return [FieldFilter(field_path=path, operator=op, value=val)]

    result: List[FieldFilter] = []
    if isinstance(filters, (list, tuple)):
        for f in filters:
            if isinstance(f, FieldFilter):
                result.append(f)
            elif isinstance(f, dict):
                path = f.get("field_path") or f.get("field") or f.get("path")
                op = coerce_filter_operator(f.get("operator", "="))
                val = f.get("value")
                if path:
                    result.append(FieldFilter(field_path=path, operator=op, value=val))
            elif isinstance(f, (tuple, list)) and len(f) in (2, 3) and isinstance(f[0], str):
                path = f[0]
                op = coerce_filter_operator(f[1]) if len(f) == 3 else FilterOperator.EQUALS
                val = f[2] if len(f) == 3 else f[1]
                result.append(FieldFilter(field_path=path, operator=op, value=val))
            else:
                raise TypeError(f"Cannot coerce {type(f).__name__} into FieldFilter")
    return result


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


def _to_camel_case(s: str) -> str:
    components = s.split("_")
    return components[0] + "".join(x.title() for x in components[1:])


class UDMEvent(dict):
    """Smart dictionary wrapper for UDM events supporting both dict indexing and attribute dot-notation.

    Subclasses standard `dict` to maintain 100% backward compatibility with code expecting a dictionary,
    while providing:
    - Transparent unwrapping of Chronicle's nested 'event' field: `ev['metadata']` works even if stored in `ev['event']['metadata']`.
    - Chained dot-notation attribute access: `ev.metadata.event_timestamp`, `ev.principal.ip`, `ev.principal.user.userid`.
    - Automatic camelCase <-> snake_case tolerance on attributes and keys.
    - Path navigation via `ev.get_field("metadata.eventTimestamp")`.
    - Convenience properties: `.timestamp`, `.event_type`, `.log_type`, `.product_name`, `.raw`.
    """

    def __getitem__(self, key: Any) -> Any:
        has_inner_event = super().__contains__("event") and isinstance(super().__getitem__("event"), dict)
        if super().__contains__(key):
            val = super().__getitem__(key)
        elif has_inner_event and key in super().__getitem__("event"):
            val = super().__getitem__("event")[key]
        elif isinstance(key, str):
            camel = _to_camel_case(key)
            if super().__contains__(camel):
                val = super().__getitem__(camel)
            elif has_inner_event and camel in super().__getitem__("event"):
                val = super().__getitem__("event")[camel]
            else:
                raise KeyError(key)
        else:
            raise KeyError(key)

        if isinstance(val, dict) and not isinstance(val, UDMEvent):
            return UDMEvent(val)
        return val

    def get(self, key: Any, default: Any = None) -> Any:
        try:
            return self[key]
        except KeyError:
            return default

    def __contains__(self, key: Any) -> bool:
        if super().__contains__(key):
            return True
        has_inner_event = super().__contains__("event") and isinstance(super().__getitem__("event"), dict)
        if has_inner_event and key in super().__getitem__("event"):
            return True
        if isinstance(key, str):
            camel = _to_camel_case(key)
            if super().__contains__(camel):
                return True
            if has_inner_event and camel in super().__getitem__("event"):
                return True
        return False

    def __getattr__(self, name: str) -> Any:
        if name.startswith("_"):
            raise AttributeError(name)
        try:
            return self[name]
        except KeyError:
            raise AttributeError(f"'UDMEvent' object has no attribute '{name}'")

    def __setattr__(self, name: str, value: Any) -> None:
        if name.startswith("_"):
            super().__setattr__(name, value)
        else:
            self[name] = value

    @property
    def raw(self) -> Dict[str, Any]:
        """Returns the raw underlying dictionary."""
        return dict(self)

    def to_dict(self) -> Dict[str, Any]:
        """Recursively converts UDMEvent back into standard Python dictionaries."""
        res: Dict[str, Any] = {}
        for k, v in self.items():
            if isinstance(v, UDMEvent):
                res[k] = v.to_dict()
            elif isinstance(v, dict):
                res[k] = dict(v)
            elif isinstance(v, list):
                res[k] = [item.to_dict() if isinstance(item, UDMEvent) else item for item in v]
            else:
                res[k] = v
        return res

    def get_field(self, path: str, default: Any = None) -> Any:
        """Retrieves a nested field from the UDM event using dot notation (e.g. 'principal.ip' or 'metadata.event_timestamp')."""
        if path.startswith("udm."):
            path = path[4:]
        elif path.startswith("event."):
            path = path[6:]

        curr: Any = self
        for part in path.split("."):
            if isinstance(curr, dict):
                curr = curr.get(part)
            elif isinstance(curr, list) and part.isdigit() and int(part) < len(curr):
                curr = curr[int(part)]
            else:
                return default
            if curr is None:
                return default
        return curr

    @property
    def timestamp(self) -> Optional[str]:
        """Convenience property for event timestamp."""
        ts = self.get("eventTimestamp") or self.get("event_timestamp") or self.get_field("metadata.eventTimestamp") or self.get_field("metadata.event_timestamp")
        return str(ts) if ts is not None else None

    @property
    def event_type(self) -> Optional[str]:
        """Convenience property for event type."""
        et = self.get("eventType") or self.get("event_type") or self.get_field("metadata.eventType") or self.get_field("metadata.event_type")
        return str(et) if et is not None else None

    @property
    def log_type(self) -> Optional[str]:
        """Convenience property for log type."""
        lt = self.get("logType") or self.get("log_type") or self.get_field("metadata.logType") or self.get_field("metadata.log_type")
        return str(lt) if lt is not None else None

    @property
    def product_name(self) -> Optional[str]:
        """Convenience property for product name."""
        pn = self.get("productName") or self.get("product_name") or self.get_field("metadata.productName") or self.get_field("metadata.product_name")
        return str(pn) if pn is not None else None


@dataclass
class SearchBatchResult(UniversalBatchMixin):
    """A single batch of events received from the provider."""

    events: List[Union[UDMEvent, Dict[str, Any]]] = field(default_factory=list)
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
    materialize_budget: Optional[int] = None
    limit: Optional[int] = None

    def __post_init__(self):
        if self.limit is not None:
            self.receive_limit = self.limit
        else:
            self.limit = self.receive_limit


@dataclass
class SearchSession:
    session_id: Optional[str] = None
    request: Optional[SearchRequest] = None
    lifecycle: LifecycleState = LifecycleState.VALIDATING
    completeness: CompletenessState = CompletenessState.EMPTY
    received_count: int = 0
    next_index: int = 1
    more_data_available: bool = True
    events: List[Union[UDMEvent, Dict[str, Any]]] = field(default_factory=list)
    error: Optional[str] = None
    started_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    completed_at: Optional[datetime] = None

    @property
    def results(self) -> List[Union[UDMEvent, Dict[str, Any]]]:
        """Alias for events."""
        return self.events

    @property
    def rows(self) -> List[Union[UDMEvent, Dict[str, Any]]]:
        """Alias for events."""
        return self.events


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
class ProductSourceStat:
    """Represents data volume statistics for an ingested product log source."""
    product_source: str
    data_size_bytes: int = 0


@dataclass
class ProductSourceStatsBatch:
    """Represents a collection of product source statistics over an evaluation time window."""
    stats: List[ProductSourceStat] = field(default_factory=list)
    start_time: str = ""
    end_time: str = ""
    total_sources: int = 0

    @property
    def items(self) -> List[ProductSourceStat]:
        """Uniform alias for batch results across all engine domains."""
        return self.stats


@dataclass
class RawLogValidationResult:
    """Represents the syntax validation status and query classification of a raw log query."""
    query_type: str = ""
    is_valid: bool = True
    error_message: Optional[str] = None


@dataclass
class RawLogSnippet:
    """Represents a matched snippet from a raw log search."""
    id: str
    summary: str = ""
    snippet: str = ""
    log_type: str = ""
    ingestion_time: Optional[str] = None


@dataclass
class RawLogSearchResult:
    """Represents the paginated results of an enterprise raw log search."""
    matches: List[RawLogSnippet] = field(default_factory=list)
    total_matches: int = 0
    progress: int = 100
    has_more: bool = False
    next_page_token: Optional[Union[str, bool]] = None
    aggregations: Dict[str, Any] = field(default_factory=dict)
    timeline: Dict[str, Any] = field(default_factory=dict)
    retrieved_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    @property
    def items(self) -> List[RawLogSnippet]:
        """Uniform alias for batch results across all engine domains."""
        return self.matches


@dataclass
class EventReference:
    """Stable pointer to a SecOps event for investigation or pivot."""

    event_id: str = ""
    log_token: Optional[str] = None
    structured_event: Optional[Dict[str, Any]] = None
    timestamp: Optional[Union[str, datetime]] = None
    id: Optional[str] = None

    def __post_init__(self):
        if not self.event_id and self.id:
            self.event_id = self.id
        elif self.event_id and not self.id:
            self.id = self.event_id


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
    def id(self) -> str:
        """Alias for event_id."""
        return self.event_id

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


def coerce_case_status(val: Union[CaseStatus, str, None]) -> Optional[CaseStatus]:
    """Coerces a string or CaseStatus into a canonical CaseStatus enum member."""
    if val is None or isinstance(val, CaseStatus):
        return val
    upper = str(val).strip().upper()
    try:
        return CaseStatus[upper]
    except KeyError:
        try:
            return CaseStatus(upper)
        except ValueError:
            return CaseStatus.UNKNOWN


def coerce_case_priority(val: Union[CasePriority, str, None]) -> Optional[CasePriority]:
    """Coerces a string or CasePriority into a canonical CasePriority enum member."""
    if val is None or isinstance(val, CasePriority):
        return val
    upper = str(val).strip().upper()
    try:
        return CasePriority[upper]
    except KeyError:
        try:
            return CasePriority(upper)
        except ValueError:
            return CasePriority.UNKNOWN


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
class CaseWallRecord:
    case_id: str
    activity_id: str
    activity_type: str
    activity_kind: str
    creator_user_id: Optional[str] = None
    create_time: Optional[datetime] = None
    update_time: Optional[datetime] = None
    alert_identifier: Optional[str] = None
    description: str = ""
    details: Dict[str, Any] = field(default_factory=dict)
    favorite: bool = False
    name: Optional[str] = None
    raw: Dict[str, Any] = field(default_factory=dict)

    @property
    def created_time(self) -> Optional[datetime]:
        return self.create_time


@dataclass
class CaseWallResult:
    case_id: str
    records: List[CaseWallRecord] = field(default_factory=list)
    total_size: int = 0
    next_page_token: Optional[str] = None
    provenance: Dict[str, Any] = field(default_factory=dict)

    @property
    def count(self) -> int:
        return len(self.records)


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
    def id(self) -> str:
        return self.case_id

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

    @property
    def is_incident(self) -> bool:
        return bool(
            self.raw_case.get("isIncident", False)
            or self.raw_case.get("is_incident", False)
            or str(self.stage).lower() == "incident"
        )


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

    @property
    def alert_id(self) -> str:
        """Alias for alert_name / resource identifier."""
        return self.alert_name

    @property
    def id(self) -> str:
        """Alias for alert_name / resource identifier."""
        return self.alert_name


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


class TriageVerdict(str, Enum):
    CRITICAL_ESCALATION = "CRITICAL_ESCALATION"
    HIGH_PRIORITY_INVESTIGATION = "HIGH_PRIORITY_INVESTIGATION"
    CONTAINMENT_REQUIRED = "CONTAINMENT_REQUIRED"
    NOVEL_DETECTION = "NOVEL_DETECTION"
    REPEAT_RESOLVED_DUPLICATE = "REPEAT_RESOLVED_DUPLICATE"
    REPEAT_ACTIVE_CAMPAIGN = "REPEAT_ACTIVE_CAMPAIGN"
    STANDARD_TRIAGE = "STANDARD_TRIAGE"
    CLOSED_NO_ACTION = "CLOSED_NO_ACTION"
    INFORMATIONAL = "INFORMATIONAL"


@dataclass
class EntityPrecedentItem:
    """Historical case correlation for a single entity indicator."""
    entity_identifier: str
    entity_type: Optional[str] = None
    prior_case_count: int = 0
    recent_case_ids: List[str] = field(default_factory=list)
    active_incident_count: int = 0
    is_frequent: bool = False
    raw: Dict[str, Any] = field(default_factory=dict)


@dataclass
class CasePrecedentSummary:
    """Historical case precedent correlation across title and involved entities."""
    target_case_id: str
    title_query: str = ""
    title_prior_case_count: int = 0
    title_prior_case_ids: List[str] = field(default_factory=list)
    title_closed_count: int = 0
    title_incident_count: int = 0
    entity_precedents: List[EntityPrecedentItem] = field(default_factory=list)
    total_entity_matches: int = 0
    is_novel: bool = False
    is_repeat: bool = False
    repeat_case_ids: List[str] = field(default_factory=list)
    precedent_notes: List[str] = field(default_factory=list)


@dataclass
class CaseTimelineEvent:
    """A chronological event or milestone within a case's investigation lifecycle."""
    timestamp: Optional[datetime]
    event_type: str  # "CASE_CREATED", "ALERT", "PLAYBOOK", "COMMENT", "CASE_UPDATED"
    title: str
    description: str
    source_id: Optional[str] = None
    severity: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class CaseTimeline:
    """A chronologically sorted sequence of events and milestones associated with a case."""
    case_id: str
    events: List[CaseTimelineEvent] = field(default_factory=list)
    earliest_time: Optional[datetime] = None
    latest_time: Optional[datetime] = None
    provenance: Dict[str, Any] = field(default_factory=dict)

    @property
    def event_count(self) -> int:
        return len(self.events)


@dataclass
class CaseTriageAssessment:
    case_id: str
    title: str
    priority: CasePriority
    status: CaseStatus
    stage: str
    is_closed: bool = False
    is_incident: bool = False
    alert_count: int = 0
    highest_alert_priority: str = "UNKNOWN"
    suspicious_entity_count: int = 0
    suspicious_entities: List[str] = field(default_factory=list)
    comment_count: int = 0
    latest_comment: Optional[str] = None
    triage_verdict: TriageVerdict = TriageVerdict.STANDARD_TRIAGE
    triage_summary: str = ""
    recommended_actions: List[str] = field(default_factory=list)
    suggested_agent_prompt: str = ""
    assigned_user: Optional[str] = None
    create_time: Optional[datetime] = None
    update_time: Optional[datetime] = None
    environment: str = ""
    tags: List[str] = field(default_factory=list)
    raw_case: Dict[str, Any] = field(default_factory=dict)
    investigation: Optional[CaseInvestigation] = None
    gemini_summary: Optional[CaseSummary] = None
    precedent_summary: Optional[CasePrecedentSummary] = None
    is_novel: bool = False
    is_repeat: bool = False
    prior_case_count: int = 0
    suggested_stage_transition: Optional[str] = None
    alert_playbook_statuses: List[AlertPlaybookStatus] = field(default_factory=list)
    timeline: Optional[CaseTimeline] = None

    @property
    def verdict(self) -> TriageVerdict:
        """Alias for triage_verdict."""
        return self.triage_verdict

    @property
    def summary(self) -> str:
        """Alias for triage_summary."""
        return self.triage_summary

    @property
    def id(self) -> str:
        """Alias for case_id."""
        return self.case_id


@dataclass
class CaseTriageBatch(UniversalBatchMixin):
    results: List[CaseTriageAssessment]
    total_cases_analyzed: int = 0
    open_cases_count: int = 0
    closed_cases_count: int = 0
    critical_high_count: int = 0
    provenance: Dict[str, Any] = field(default_factory=dict)

    @property
    def items(self) -> List[CaseTriageAssessment]:
        """Uniform alias for batch results across all engine domains."""
        return self.results


@dataclass
class CaseAiInvestigationResult:
    """Represents the findings and escalation state of an autonomous AI case investigation."""
    case_id: str
    summary_state: str
    summary_text: Optional[str] = None
    extracted_ips: List[str] = field(default_factory=list)
    extracted_users: List[str] = field(default_factory=list)
    extracted_hashes: List[str] = field(default_factory=list)
    hunt_results: Dict[str, int] = field(default_factory=dict)
    primary_alert_id: Optional[str] = None
    incident_marked: bool = False
    alert_escalated: bool = False
    comment_posted: bool = False
    audit_comment: Optional[str] = None
    dry_run: bool = False
    investigation: Optional[CaseInvestigation] = None
    provenance: Dict[str, Any] = field(default_factory=dict)



class PlaybookType(str, Enum):
    REGULAR = "REGULAR"
    NESTED = "NESTED"
    UNKNOWN = "UNKNOWN"


def coerce_playbook_type(val: Union[PlaybookType, str, None]) -> Optional[PlaybookType]:
    """Coerces a string or PlaybookType into a canonical PlaybookType enum member."""
    if val is None or isinstance(val, PlaybookType):
        return val
    upper = str(val).strip().upper()
    if upper in ("STANDARD", "NORMAL"):
        return PlaybookType.REGULAR
    try:
        return PlaybookType[upper]
    except KeyError:
        try:
            return PlaybookType(upper)
        except ValueError:
            return PlaybookType.UNKNOWN


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


@dataclass
class CuratedDetectionHealthReport(UniversalDictMixin):
    """Complete health, deployment, and hygiene audit report for Google SecOps Curated Detections."""
    evaluation_period: Dict[str, Any]
    summary: Dict[str, Any]
    tenant_quotas: Dict[str, Any]
    health_findings: List[Dict[str, Any]]
    top_firing_rulesets: List[Dict[str, Any]]
    newest_rules: List[Dict[str, Any]]
    oldest_rules: List[Dict[str, Any]]
    category_coverage: List[Dict[str, Any]]
    log_source_coverage: List[Dict[str, Any]]
    ruleset_audits: List[Dict[str, Any]]
    raw: Dict[str, Any] = field(default_factory=dict)

    @property
    def findings(self) -> List[Dict[str, Any]]:
        """Alias for health_findings."""
        return self.health_findings

    @property
    def rulesets(self) -> List[Dict[str, Any]]:
        """Alias for ruleset_audits."""
        return self.ruleset_audits


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

    @property
    def display_name(self) -> str:
        """Alias for summary.display_name."""
        return self.summary.display_name if self.summary else ""

    @property
    def id(self) -> str:
        """Alias for summary.id."""
        return self.summary.id if self.summary else ""

    @property
    def dashboard_id(self) -> str:
        """Alias for summary.id."""
        return self.summary.id if self.summary else ""

    @property
    def dashboard_type(self) -> str:
        """Alias for summary.dashboard_type."""
        return self.summary.dashboard_type if self.summary else ""


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


@dataclass
class DashboardHealthCheckResult(UniversalDictMixin):
    """Result of a native dashboard operational health check."""
    dashboard_id: str
    query_results: List[Dict[str, Any]]
    summary: str
    errors: List[str] = field(default_factory=list)
    raw: Dict[str, Any] = field(default_factory=dict)

    @property
    def id(self) -> str:
        return self.dashboard_id

    @property
    def total_queries(self) -> int:
        return len(self.query_results)

    @property
    def successful_queries(self) -> int:
        return sum(1 for r in self.query_results if r.get("success"))

    @property
    def failed_queries(self) -> int:
        return self.total_queries - self.successful_queries


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


class FeedHealthStatus(str, Enum):
    """Health classification status for an ingestion feed."""
    HEALTHY = "HEALTHY"
    IRREGULAR = "IRREGULAR"
    FAILED = "FAILED"
    HIGH_LATENCY = "HIGH_LATENCY"
    SILENT_PUSH_STOP = "SILENT_PUSH_STOP"
    UNKNOWN = "UNKNOWN"


@dataclass
class FeedHealthFinding:
    """Actionable finding representing the operational health of a feed."""
    feed_id: str
    feed_name: str
    source_type: str
    log_type: str
    status: FeedHealthStatus
    state: str = "UNKNOWN"
    collector_name: Optional[str] = None
    latency_p95: Optional[str] = None
    last_event_time: Optional[str] = None
    event_count_recent: int = 0
    volume_funnel: Dict[str, int] = field(default_factory=dict)
    quota_rejected_volume_mb: float = 0.0
    quota_limit_mb_per_sec: float = 0.0
    anomaly_description: str = ""
    remediation_steps: List[str] = field(default_factory=list)
    raw: Dict[str, Any] = field(default_factory=dict)


@dataclass
class FeedHealthReport(UniversalBatchMixin):
    """Comprehensive posture audit report for all ingestion feeds."""
    findings: List[FeedHealthFinding]
    healthy_count: int = 0
    irregular_count: int = 0
    failed_count: int = 0
    high_latency_count: int = 0
    quota_rejections_detected: int = 0
    total_feeds_audited: int = 0
    generated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    @property
    def items(self) -> List[FeedHealthFinding]:
        return self.findings


class ParserHealthStatus(str, Enum):
    """Health classification status for a SIEM parser / log type normalizer."""
    HEALTHY = "HEALTHY"
    IRREGULAR = "IRREGULAR"
    FAILED = "FAILED"
    VERSION_DRIFT = "VERSION_DRIFT"
    EXTENSION_CONFLICT = "EXTENSION_CONFLICT"
    INACTIVE_NO_PARSER = "INACTIVE_NO_PARSER"
    UNKNOWN = "UNKNOWN"


@dataclass
class ParserHealthFinding:
    """Actionable finding representing the operational health of a parser or normalizer."""
    log_type: str
    parser_id: str
    status: ParserHealthStatus
    state: str = "UNKNOWN"
    creator_source: str = "UNKNOWN"
    collector_name: Optional[str] = None
    version: str = ""
    latest_version: str = ""
    rollback_available: bool = False
    has_extension: bool = False
    extension_id: Optional[str] = None
    extension_state: Optional[str] = None
    dynamic_parsing_enabled: bool = False
    opted_fields_count: int = 0
    drop_reason_code: Optional[str] = None
    zscore_anomaly_detail: Optional[str] = None
    anomalous_since: Optional[str] = None
    last_normalization_time: Optional[str] = None
    event_latency: Optional[str] = None
    volume_funnel: Dict[str, int] = field(default_factory=dict)
    quota_rejected_volume_mb: float = 0.0
    quota_limit_mb_per_sec: float = 0.0
    anomaly_description: str = ""
    remediation_steps: List[str] = field(default_factory=list)
    raw: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ParserHealthReport(UniversalBatchMixin):
    """Comprehensive posture audit report for all SIEM parsers and extensions."""
    findings: List[ParserHealthFinding]
    healthy_count: int = 0
    irregular_count: int = 0
    failed_count: int = 0
    version_drift_count: int = 0
    extension_conflict_count: int = 0
    quota_rejections_detected: int = 0
    total_parsers_audited: int = 0
    generated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    @property
    def items(self) -> List[ParserHealthFinding]:
        return self.findings


class RuleHealthStatus(str, Enum):
    """Operational health classification for a Chronicle YARA-L rule."""
    HEALTHY = "HEALTHY"
    EXECUTION_ERROR = "EXECUTION_ERROR"
    COMPILATION_ERROR = "COMPILATION_ERROR"
    HIGH_LATENCY = "HIGH_LATENCY"
    SILENT_DECAY = "SILENT_DECAY"
    MISCONFIGURED_ALERTING = "MISCONFIGURED_ALERTING"
    DISABLED = "DISABLED"
    UNKNOWN = "UNKNOWN"


@dataclass
class RuleHealthFinding:
    """Actionable finding representing the operational health of a detection rule."""
    rule_id: str
    display_name: str
    rule_owner: str = "CUSTOMER"  # CUSTOMER or GOOGLE
    severity: str = "MEDIUM"
    status: RuleHealthStatus = RuleHealthStatus.HEALTHY
    enabled: bool = True
    alerting: bool = True
    run_frequency: str = "LIVE"
    detection_count_recent: int = 0
    execution_error_count: int = 0
    last_error_message: Optional[str] = None
    ingestion_to_detection_latency_min: Optional[float] = None
    event_to_detection_latency_min: Optional[float] = None
    mitre_tactics: List[str] = field(default_factory=list)
    mitre_techniques: List[str] = field(default_factory=list)
    details: str = ""
    remediation_steps: List[str] = field(default_factory=list)
    raw: Dict[str, Any] = field(default_factory=dict)


@dataclass
class RuleHealthReport(UniversalBatchMixin):
    """Comprehensive posture audit report for all SIEM detection rules and curated rulesets."""
    findings: List[RuleHealthFinding]
    healthy_count: int = 0
    failing_count: int = 0
    decay_count: int = 0
    latency_alert_count: int = 0
    misconfigured_count: int = 0
    disabled_count: int = 0
    total_rules_audited: int = 0
    total_detections_24h: int = 0
    average_risk_score: float = 0.0
    top_mitre_tactics: List[Dict[str, Any]] = field(default_factory=list)
    top_threat_categories: List[Dict[str, Any]] = field(default_factory=list)
    generated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    @property
    def items(self) -> List[RuleHealthFinding]:
        return self.findings


@dataclass
class RuleDecayAssessment:
    """Detailed decay risk assessment and telemetry health evaluation for a single detection rule."""
    rule_id: str
    rule_name: str
    dps_score: int
    decay_flags: List[str]
    is_live: bool
    days_stale: int
    detection_count_90d: int
    first_seen: Optional[str] = None
    last_seen: Optional[str] = None
    unpopulated_fields: List[str] = field(default_factory=list)
    compiler_errors: List[str] = field(default_factory=list)
    recommendation: str = "KEEP_ACTIVE"
    raw: Dict[str, Any] = field(default_factory=dict)


@dataclass
class RuleDecayReport(UniversalBatchMixin):
    """Tenant-wide report summarizing detection rule decay, DPS distribution, and telemetry health."""
    assessments: List[RuleDecayAssessment]
    total_audited: int = 0
    broken_compilation_count: int = 0
    silent_count: int = 0
    stale_count: int = 0
    unpopulated_count: int = 0
    average_dps: float = 0.0
    generated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    @property
    def items(self) -> List[RuleDecayAssessment]:
        return self.assessments


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
class ParserRunResultEntry:
    """Individual execution result for a single log passed to run_parser."""
    log_text: str
    log_b64: str
    is_success: bool
    error_message: Optional[str] = None
    parsed_events: List[Dict[str, Any]] = field(default_factory=list)
    raw: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ParserRunResult(UniversalBatchMixin):
    """Container for parser run execution results."""
    log_type: str
    entries: List[ParserRunResultEntry]
    total_runs: int
    error_count: int
    success_count: int
    retrieved_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    raw: Dict[str, Any] = field(default_factory=dict)


@dataclass
class UnparsedLogDiagnostic:
    """Diagnostic analysis of an unparsed raw log."""
    log_id: str
    log_type: str
    display_name: str
    raw_log_preview: str
    error_message: str
    error_category: str
    parser_id: str
    parser_version: str
    parser_creator: str
    raw_log: str = ""
    retrieved_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    raw: Dict[str, Any] = field(default_factory=dict)


@dataclass
class UnparsedLogsDiagnosticBatch(UniversalBatchMixin):
    """Batch of diagnostics for unparsed raw logs of a specific log type."""
    log_type: str
    display_name: str
    total_unparsed_found: int
    total_diagnosed: int
    diagnostics: List[UnparsedLogDiagnostic]
    active_parser_summary: Optional[ParserSummary] = None
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

    @property
    def status(self) -> str:
        """Alias for state."""
        return self.state

    @property
    def id(self) -> str:
        """Alias for recommendation_id."""
        return self.recommendation_id


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

    @property
    def status(self) -> str:
        """Alias for state."""
        return self.state


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
    archived: bool = False
    archive_time: str = ""
    last_alert_status_change_time: str = ""
    display_name: str = ""
    raw: Dict[str, Any] = field(default_factory=dict)

    @property
    def rule_id(self) -> str:
        parts = self.name.split("/")
        if len(parts) >= 2 and parts[-1] == "deployment":
            return parts[-2]
        return parts[-1] if parts else ""


@dataclass
class RuleDeploymentListResult:
    """Result container for rule deployments across rules."""
    deployments: List[RuleDeployment] = field(default_factory=list)
    next_page_token: Optional[str] = None
    provenance: Dict[str, Any] = field(default_factory=dict)

    @property
    def items(self) -> List[RuleDeployment]:
        return self.deployments


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

    @property
    def rule_text(self) -> str:
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


class DashboardHealthStatus(str, Enum):
    """Classification states for Google SecOps Native Dashboards."""
    HEALTHY = "HEALTHY"
    RECENTLY_CREATED = "RECENTLY_CREATED"
    RECENTLY_MODIFIED = "RECENTLY_MODIFIED"
    BROKEN_QUERY = "BROKEN_QUERY"
    EMPTY_DASHBOARD = "EMPTY_DASHBOARD"
    ORPHAN_CHART = "ORPHAN_CHART"
    STALE = "STALE"
    UNKNOWN = "UNKNOWN"


@dataclass
class DashboardHealthFinding:
    """Detailed health, recency, and syntax evaluation for a single dashboard."""
    dashboard_id: str
    display_name: str
    dashboard_type: str  # CUSTOM, CURATED, DEFAULT
    create_user_id: str
    update_user_id: str
    create_time: Optional[datetime]
    update_time: Optional[datetime]
    charts_count: int
    broken_queries_count: int
    status: DashboardHealthStatus
    details: str
    remediation_steps: List[str] = field(default_factory=list)
    broken_query_details: List[Dict[str, Any]] = field(default_factory=list)
    raw: Dict[str, Any] = field(default_factory=dict)


@dataclass
class DashboardHealthReport:
    """Comprehensive health and lifecycle audit report for Google SecOps dashboards."""
    total_dashboards_audited: int
    healthy_count: int
    recently_created_count: int
    recently_modified_count: int
    broken_query_count: int
    empty_dashboard_count: int
    stale_count: int
    custom_count: int
    curated_count: int
    findings: List[DashboardHealthFinding] = field(default_factory=list)
    generated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


class DataTableHealthStatus(str, Enum):
    """Health classification and governance status for Data Tables."""
    HEALTHY = "HEALTHY"
    EMPTY_REFERENCED = "EMPTY_REFERENCED"
    ORPHAN = "ORPHAN"
    RECENTLY_CREATED = "RECENTLY_CREATED"
    RECENTLY_MODIFIED = "RECENTLY_MODIFIED"
    SCHEMA_ISSUE = "SCHEMA_ISSUE"
    STALE = "STALE"
    UNKNOWN = "UNKNOWN"


@dataclass
class DataTableHealthFinding:
    """Actionable health and lineage finding for an individual Data Table."""
    table_id: str
    display_name: str
    description: Optional[str]
    approximate_row_count: Optional[int]
    column_count: int
    key_columns: List[str]
    row_time_to_live: Optional[str]
    create_time: Optional[datetime]
    update_time: Optional[datetime]
    associated_rules: List[str]
    associated_dashboards: List[str]
    rule_associations_count: int
    status: DataTableHealthStatus
    details: str
    remediation_steps: List[str] = field(default_factory=list)
    raw: Dict[str, Any] = field(default_factory=dict)


@dataclass
class DataTableHealthReport:
    """Comprehensive health, lineage, and governance audit report for Data Tables."""
    total_tables_audited: int
    healthy_count: int
    empty_referenced_count: int
    orphan_count: int
    recently_created_count: int
    recently_modified_count: int
    stale_count: int
    schema_issue_count: int
    findings: List[DataTableHealthFinding] = field(default_factory=list)
    generated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


# --- Detection Tuning & UDM Findings Refinements Models ---

@dataclass
class NoisyRuleRecord:
    """Individual rule noise profile aggregated from live detection telemetry."""
    rule_id: str
    rule_name: str
    rule_type: str  # "GOOGLE_MANAGED", "CUSTOMER", or "OTHER"
    alert_state: str  # "ALERTING", "NOT_ALERTING", etc.
    detection_count: int
    first_seen: Optional[datetime] = None
    last_seen: Optional[datetime] = None
    raw: Dict[str, Any] = field(default_factory=dict)

    @property
    def is_curated(self) -> bool:
        return self.rule_type in ("GOOGLE_MANAGED", "GOOGLE_CURATED") or self.rule_id.startswith("ur_")



@dataclass
class NoisyRulesBatch(UniversalBatchMixin):
    """Ranked leaderboard of noisy detection rules."""
    rules: List[NoisyRuleRecord] = field(default_factory=list)
    total_detections: int = 0
    time_window: str = ""
    raw: Dict[str, Any] = field(default_factory=dict)

    def __iter__(self):
        return iter(self.rules)

    def __len__(self):
        return len(self.rules)


@dataclass
class EntityCardinalityRecord:
    """Distinct entity value and its detection frequency count."""
    value: str
    count: int
    raw: Dict[str, Any] = field(default_factory=dict)


@dataclass
class DimensionCardinality:
    """Distribution for a specific UDM entity subfield dimension."""
    dimension: str  # e.g. "principal_ip", "target_hostname", "user_id"
    subfield_path: str
    records: List[EntityCardinalityRecord] = field(default_factory=list)
    total_distinct_values: int = 0


@dataclass
class EntityCardinalityReport(UniversalBatchMixin):
    """Multi-dimensional entity cardinality distribution for a detection rule."""
    rule_id: str
    rule_name: str = ""
    dimensions: List[DimensionCardinality] = field(default_factory=list)
    time_window: str = ""
    raw: Dict[str, Any] = field(default_factory=dict)

    def __iter__(self):
        return iter(self.dimensions)

    def __len__(self):
        return len(self.dimensions)


@dataclass
class RuleCaseHistoryRecord:
    """SOAR case record associated with a detection rule."""
    case_name: str
    display_name: str
    status: str
    close_reason: str
    root_cause: str
    rule_id: str
    raw: Dict[str, Any] = field(default_factory=dict)


@dataclass
class RuleCaseHistoryBatch(UniversalBatchMixin):
    """Batch of SOAR cases associated with a detection rule."""
    cases: List[RuleCaseHistoryRecord] = field(default_factory=list)
    rule_id: str = ""
    total_cases: int = 0
    raw: Dict[str, Any] = field(default_factory=dict)

    def __iter__(self):
        return iter(self.cases)

    def __len__(self):
        return len(self.cases)


@dataclass
class FindingsRefinementSummary:
    """Summary of a Google SecOps UDM Findings Refinement exclusion."""
    id: str
    name: str
    display_name: str
    type: str  # "DETECTION_EXCLUSION"
    query: str
    curated_rule_ids: List[str] = field(default_factory=list)
    create_time: Optional[datetime] = None
    update_time: Optional[datetime] = None
    raw: Dict[str, Any] = field(default_factory=dict)


@dataclass
class FindingsRefinementBatch(UniversalBatchMixin):
    """Batch of tenant UDM findings refinements."""
    refinements: List[FindingsRefinementSummary] = field(default_factory=list)
    raw: Dict[str, Any] = field(default_factory=dict)

    def __iter__(self):
        return iter(self.refinements)

    def __len__(self):
        return len(self.refinements)


@dataclass
class FindingsRefinementTestResult:
    """Dry-run impact simulation metrics for a findings refinement exclusion."""
    curated_rule_id: str
    query: str
    total_detections: int
    excluded_detections: int
    suppression_ratio: float  # e.g. 0.3137 for 31.37%
    raw: List[Dict[str, Any]] = field(default_factory=list)


@dataclass
class DetectionTuningReport:
    """Comprehensive diagnostic and tuning report for a noisy detection rule."""
    rule_id: str
    rule_name: str
    rule_type: str  # "GOOGLE_MANAGED" or "CUSTOMER"
    rule_text: str
    total_detections_baseline: int
    entity_cardinality: EntityCardinalityReport
    linked_cases: RuleCaseHistoryBatch
    proposed_refinement_query: str
    dry_run_impact: Optional[FindingsRefinementTestResult] = None
    validation_status: str = "PENDING"
    validation_errors: List[str] = field(default_factory=list)
    raw: Dict[str, Any] = field(default_factory=dict)

    @property
    def is_curated(self) -> bool:
        return self.rule_type in ("GOOGLE_MANAGED", "GOOGLE_CURATED") or self.rule_id.startswith("ur_")


@dataclass
class CorrelatedDetectionSample:
    """A multi-attribute correlated detection sample isolating benign administrative activity."""
    user: str
    command_line: str
    hostname: str
    ip: str
    hash_val: str = ""
    count: int = 0
    last_seen: Optional[str] = None
    raw: Dict[str, Any] = field(default_factory=dict)


@dataclass
class CorrelatedSamplingBatch(UniversalBatchMixin):
    """Batch of correlated detection event samples for a rule."""
    rule_id: str
    rule_name: str
    samples: List[CorrelatedDetectionSample] = field(default_factory=list)
    total_samples: int = 0
    time_window: str = "14d"
    raw: Dict[str, Any] = field(default_factory=dict)

    @property
    def items(self) -> List[CorrelatedDetectionSample]:
        return self.samples


@dataclass
class MultiFactorExclusion:
    """A safe, multi-factor exclusion filter targeting benign background activity."""
    rule_id: str
    rule_name: str
    factors: Dict[str, str]
    yara_l_condition: str
    udm_refinement_query: str
    is_multi_factor: bool
    safety_guardrail_passed: bool
    guardrail_notes: List[str] = field(default_factory=list)


@dataclass
class DetectionTuningProposal:
    """Complete tuning proposal with quantitative impact projections and compiler verification."""
    proposal_id: str
    rule_id: str
    rule_name: str
    rule_type: str
    status: str
    unsuppressed_trigger_count: int
    projected_suppressed_count: int
    noise_reduction_pct: float
    preserved_real_alerts: int
    multi_factor_exclusion: Optional[MultiFactorExclusion] = None
    entity_distribution: List[Dict[str, Any]] = field(default_factory=list)
    correlated_samples: List[CorrelatedDetectionSample] = field(default_factory=list)
    unified_diff: str = ""
    original_rule_text: str = ""
    tuned_rule_text: str = ""
    compiler_verified: bool = False
    compiler_errors: List[str] = field(default_factory=list)
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    raw: Dict[str, Any] = field(default_factory=dict)


@dataclass
class GcpLogEntry:
    """Individual Google Cloud Logging entry relating to SecOps operations or audit activity."""
    timestamp: str
    severity: str
    log_name: str
    resource_type: str = ""
    resource_labels: Dict[str, str] = field(default_factory=list)
    insert_id: str = ""
    json_payload: Dict[str, Any] = field(default_factory=dict)
    text_payload: str = ""
    proto_payload: Dict[str, Any] = field(default_factory=dict)
    trace: str = ""
    raw: Dict[str, Any] = field(default_factory=dict)

    @property
    def principal_email(self) -> str:
        """Extracts principal email from proto_payload authenticationInfo if available."""
        if self.proto_payload and isinstance(self.proto_payload, dict):
            auth_info = self.proto_payload.get("authenticationInfo", {})
            if isinstance(auth_info, dict):
                return auth_info.get("principalEmail", "")
        return ""

    @property
    def method_name(self) -> str:
        """Extracts method name from proto_payload if available."""
        if self.proto_payload and isinstance(self.proto_payload, dict):
            return self.proto_payload.get("methodName", "")
        return ""


@dataclass
class GcpLogQueryResult(UniversalBatchMixin):
    """Batch of Google Cloud Logging entries returned from a query."""
    entries: List[GcpLogEntry] = field(default_factory=list)
    next_page_token: Optional[str] = None
    total_count: int = 0
    filter_applied: str = ""
    projects_queried: List[str] = field(default_factory=list)

    @property
    def items(self) -> List[GcpLogEntry]:
        return self.entries


@dataclass(frozen=True)
class ChronicleIamMember:
    """Individual or principal granted an IAM role in Google Cloud."""
    raw_member: str
    member_type: str  # user, group, serviceAccount, workforcePool, domain, other
    principal_id: str


@dataclass(frozen=True)
class ChronicleIamRoleBinding:
    """An IAM binding granting a Chronicle-related role to one or more members."""
    role: str
    role_title: str
    is_custom: bool
    members: List[str] = field(default_factory=list)
    condition: Optional[Dict[str, Any]] = None


@dataclass(frozen=True)
class ChronicleCustomRole:
    """A project-level custom IAM role containing chronicle.* permissions."""
    role_name: str
    title: str
    description: str
    stage: str
    chronicle_permissions: List[str] = field(default_factory=list)
    total_permissions_count: int = 0


@dataclass(frozen=True)
class IdentityGovernanceReport:
    """Comprehensive Identity & Access Governance report for a SecOps project."""
    project_id: str
    timestamp: str
    chronicle_bindings: List[ChronicleIamRoleBinding] = field(default_factory=list)
    custom_roles: List[ChronicleCustomRole] = field(default_factory=list)
    total_privileged_users: int = 0
    total_groups: int = 0
    total_service_accounts: int = 0
    total_workforce_pools: int = 0
    inventory_summary: Optional[Dict[str, Any]] = None


@dataclass(frozen=True)
class MetricPoint:
    """Individual data point within a Google Cloud Monitoring time series."""
    start_time: str
    end_time: str
    value: Any  # int, float, str, bool, or dict for distribution


@dataclass
class TimeSeriesData:
    """A single time series stream returned from Google Cloud Monitoring."""
    metric_type: str
    metric_labels: Dict[str, str] = field(default_factory=dict)
    resource_type: str = ""
    resource_labels: Dict[str, str] = field(default_factory=dict)
    metric_kind: str = "GAUGE"  # GAUGE, DELTA, CUMULATIVE
    value_type: str = "INT64"   # INT64, DOUBLE, BOOL, STRING, DISTRIBUTION
    points: List[MetricPoint] = field(default_factory=list)
    raw: Dict[str, Any] = field(default_factory=dict)


@dataclass
class GcpMonitoringQueryResult(UniversalBatchMixin):
    """Batch of Google Cloud Monitoring time series streams."""
    time_series: List[TimeSeriesData] = field(default_factory=list)
    next_page_token: Optional[str] = None
    total_series: int = 0
    filter_applied: str = ""
    time_interval: str = ""
    projects_queried: List[str] = field(default_factory=list)

    @property
    def items(self) -> List[TimeSeriesData]:
        return self.time_series


class TimestampProgressionState(str, Enum):
    """Classification states for telemetry timestamp and latency progression."""
    NEW = "NEW"
    PREVIOUSLY_KNOWN = "PREVIOUSLY KNOWN"
    RESOLVED = "RESOLVED"
    HEALTHY = "HEALTHY"


@dataclass
class TimestampMetricRow:
    """Aggregated timestamp delta and delay distribution for an individual log type."""
    log_type: str
    total: int = 0
    average_difference_minutes: float = 0.0
    cnt_lt_0_hours: int = 0  # Future events / NTP clock skew
    cnt_0_1_hours: int = 0   # 0-1 hour delay (real-time)
    cnt_1_2_hours: int = 0   # 1-2 hour delay (batching)
    cnt_gt_2_hours: int = 0  # >2 hour delay (severe delay)
    progression_state: str = "HEALTHY"
    is_anomaly: bool = False
    raw: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "log_type": self.log_type,
            "total": self.total,
            "average_difference_minutes": self.average_difference_minutes,
            "cnt_lt_0_hours": self.cnt_lt_0_hours,
            "cnt_0_1_hours": self.cnt_0_1_hours,
            "cnt_1_2_hours": self.cnt_1_2_hours,
            "cnt_gt_2_hours": self.cnt_gt_2_hours,
            "progression_state": self.progression_state,
            "is_anomaly": self.is_anomaly,
        }


@dataclass
class TimestampIntegrityReport(UniversalBatchMixin):
    """Comprehensive tenant audit report for timestamp deltas, clock skews, and pipeline latency."""
    timestamp: str
    days: int
    total_log_types_audited: int = 0
    healthy_count: int = 0
    new_anomalies_count: int = 0
    previously_known_count: int = 0
    resolved_count: int = 0
    total_skewed_events: int = 0
    total_delayed_events: int = 0
    metrics: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    comparative_findings: Dict[str, str] = field(default_factory=dict)
    log_types: List[TimestampMetricRow] = field(default_factory=list)
    top_delayed_log_types: List[TimestampMetricRow] = field(default_factory=list)
    top_skewed_log_types: List[TimestampMetricRow] = field(default_factory=list)
    narrative: str = ""
    raw: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        if not self.metrics and self.log_types:
            for lt in self.log_types:
                lt_name = lt.log_type if hasattr(lt, "log_type") else str(lt.get("log_type", ""))
                self.metrics[lt_name] = {
                    "total": getattr(lt, "total", 0),
                    "average_difference_minutes": getattr(lt, "average_difference_minutes", 0.0),
                    "cnt_lt_0_hours": getattr(lt, "cnt_lt_0_hours", 0),
                    "cnt_0_1_hours": getattr(lt, "cnt_0_1_hours", 0),
                    "cnt_1_2_hours": getattr(lt, "cnt_1_2_hours", 0),
                    "cnt_gt_2_hours": getattr(lt, "cnt_gt_2_hours", 0),
                }

    @property
    def items(self) -> List[TimestampMetricRow]:
        return self.log_types

    def to_dict(self) -> Dict[str, Any]:
        return {
            "timestamp": self.timestamp,
            "days": self.days,
            "total_log_types_audited": self.total_log_types_audited,
            "healthy_count": self.healthy_count,
            "new_anomalies_count": self.new_anomalies_count,
            "previously_known_count": self.previously_known_count,
            "resolved_count": self.resolved_count,
            "total_skewed_events": self.total_skewed_events,
            "total_delayed_events": self.total_delayed_events,
            "metrics": self.metrics,
            "comparative_findings": self.comparative_findings,
            "log_types": [lt.to_dict() for lt in self.log_types],
            "top_delayed_log_types": [lt.to_dict() for lt in self.top_delayed_log_types],
            "top_skewed_log_types": [lt.to_dict() for lt in self.top_skewed_log_types],
            "narrative": self.narrative,
        }


@dataclass
class Provenance:
    """Verifiable execution provenance for workflow results and findings."""
    source: str = ""
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    details: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "source": self.source,
            "timestamp": self.timestamp,
            "details": self.details,
        }


class RuleConflictType:
    """Standardized conflict and overlap classifications for YARA-L detection rules."""
    REDUNDANCY = "REDUNDANCY"
    OVERLAP = "OVERLAP"
    CONTRADICTION = "CONTRADICTION"
    SCOPE_GAPS = "SCOPE GAPS"


class ConflictSeverityTier:
    """Operational urgency tiers based on Conflict Overlap Score (COS: 0-100)."""
    CRITICAL = "CRITICAL"
    MODERATE = "MODERATE"
    LOW = "LOW / NO OVERLAP"


@dataclass
class RuleConflictPair:
    """Pairwise conflict and overlap comparison between a target rule and a candidate similar rule."""
    target_rule_id: str = ""
    target_rule_name: str = ""
    similar_rule_id: str = ""
    similar_rule_name: str = ""
    similarity_score: float = 0.0
    conflict_type: str = "OVERLAP"
    impact_severity: str = "MEDIUM"
    cos_score: float = 0.0
    similarity_pts: float = 0.0
    conflict_type_pts: float = 0.0
    impact_severity_pts: float = 0.0
    explanation: str = ""
    consolidation_strategy: str = ""
    recommendation: str = ""
    events_overlap: Optional[Dict[str, Any]] = None
    match_overlap: Optional[Dict[str, Any]] = None
    condition_overlap: Optional[Dict[str, Any]] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "target_rule_id": self.target_rule_id,
            "target_rule_name": self.target_rule_name,
            "similar_rule_id": self.similar_rule_id,
            "similar_rule_name": self.similar_rule_name,
            "similarity_score": self.similarity_score,
            "conflict_type": self.conflict_type,
            "impact_severity": self.impact_severity,
            "cos_score": self.cos_score,
            "similarity_pts": self.similarity_pts,
            "conflict_type_pts": self.conflict_type_pts,
            "impact_severity_pts": self.impact_severity_pts,
            "explanation": self.explanation,
            "consolidation_strategy": self.consolidation_strategy,
            "recommendation": self.recommendation,
            "events_overlap": self.events_overlap,
            "match_overlap": self.match_overlap,
            "condition_overlap": self.condition_overlap,
        }


@dataclass
class RuleConflictAuditResult:
    """Audit result evaluating all semantic overlaps and conflicts for a single detection rule."""
    rule_id: str = ""
    rule_name: str = ""
    highest_cos: float = 0.0
    severity_tier: str = "LOW / NO OVERLAP"
    conflicts: List[RuleConflictPair] = field(default_factory=list)
    is_live: bool = False
    is_silent: bool = False
    strategic_recommendation: str = ""
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    provenance: Optional[Provenance] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "rule_id": self.rule_id,
            "rule_name": self.rule_name,
            "highest_cos": self.highest_cos,
            "severity_tier": self.severity_tier,
            "conflicts": [c.to_dict() for c in self.conflicts],
            "is_live": self.is_live,
            "is_silent": self.is_silent,
            "strategic_recommendation": self.strategic_recommendation,
            "timestamp": self.timestamp,
            "provenance": self.provenance.to_dict() if self.provenance else None,
        }


@dataclass
class BatchRuleConflictAuditResult:
    """Summary of batch rule conflict and overlap discovery across tenant rules."""
    total_rules_scanned: int = 0
    total_pairs_evaluated: int = 0
    conflict_counts: Dict[str, int] = field(default_factory=lambda: {
        "REDUNDANCY": 0,
        "OVERLAP": 0,
        "CONTRADICTION": 0,
        "SCOPE GAPS": 0,
    })
    severity_counts: Dict[str, int] = field(default_factory=lambda: {
        "CRITICAL": 0,
        "MODERATE": 0,
        "LOW": 0,
    })
    highest_cos_rules: List[RuleConflictAuditResult] = field(default_factory=list)
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    provenance: Optional[Provenance] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "total_rules_scanned": self.total_rules_scanned,
            "total_pairs_evaluated": self.total_pairs_evaluated,
            "conflict_counts": self.conflict_counts,
            "severity_counts": self.severity_counts,
            "highest_cos_rules": [r.to_dict() for r in self.highest_cos_rules],
            "timestamp": self.timestamp,
            "provenance": self.provenance.to_dict() if self.provenance else None,
        }

class RuleSourceType(str, Enum):
    """Origin of a detection rule."""
    CUSTOMER = "CUSTOMER"
    GOOGLE_CURATED = "GOOGLE_CURATED"


@dataclass
class RuleAuditFinding:
    """Actionable assessment of a single detection rule across health, decay, and conflict dimensions."""
    rule_id: str
    display_name: str
    rule_source: str = "CUSTOMER"  # CUSTOMER | GOOGLE_CURATED
    severity: str = "MEDIUM"
    status: RuleHealthStatus = RuleHealthStatus.HEALTHY
    enabled: bool = True
    alerting: bool = True
    run_frequency: str = "LIVE"
    dps_score: Optional[float] = None
    decay_status: Optional[str] = None
    detection_count_90d: int = 0
    execution_error_count: int = 0
    last_error_message: Optional[str] = None
    has_embedding: bool = False
    highest_conflict_cos: float = 0.0
    highest_conflict_type: Optional[str] = None
    shadowed_by_curated_id: Optional[str] = None
    shadowed_by_curated_name: Optional[str] = None
    details: str = ""
    remediation_steps: List[str] = field(default_factory=list)
    raw: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "rule_id": self.rule_id,
            "display_name": self.display_name,
            "rule_source": self.rule_source,
            "severity": self.severity,
            "status": self.status.value if isinstance(self.status, Enum) else str(self.status),
            "enabled": self.enabled,
            "alerting": self.alerting,
            "run_frequency": self.run_frequency,
            "dps_score": self.dps_score,
            "decay_status": self.decay_status,
            "detection_count_90d": self.detection_count_90d,
            "execution_error_count": self.execution_error_count,
            "last_error_message": self.last_error_message,
            "has_embedding": self.has_embedding,
            "highest_conflict_cos": self.highest_conflict_cos,
            "highest_conflict_type": self.highest_conflict_type,
            "shadowed_by_curated_id": self.shadowed_by_curated_id,
            "shadowed_by_curated_name": self.shadowed_by_curated_name,
            "details": self.details,
            "remediation_steps": self.remediation_steps,
        }


@dataclass
class RuleAuditReport(UniversalBatchMixin):
    """End-to-end detection repository audit report covering customer and curated rules."""
    findings: List[RuleAuditFinding] = field(default_factory=list)
    total_rules_scanned: int = 0
    customer_rules_count: int = 0
    curated_rules_count: int = 0
    embeddings_synced_count: int = 0
    healthy_count: int = 0
    silent_decay_count: int = 0
    failing_count: int = 0
    misconfigured_count: int = 0
    disabled_count: int = 0
    conflict_count: int = 0
    shadowed_by_curated_count: int = 0
    total_detections_90d: int = 0
    generated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    provenance: Optional[Provenance] = None

    @property
    def items(self) -> List[RuleAuditFinding]:
        return self.findings

    def to_dict(self) -> Dict[str, Any]:
        return {
            "total_rules_scanned": self.total_rules_scanned,
            "customer_rules_count": self.customer_rules_count,
            "curated_rules_count": self.curated_rules_count,
            "embeddings_synced_count": self.embeddings_synced_count,
            "healthy_count": self.healthy_count,
            "silent_decay_count": self.silent_decay_count,
            "failing_count": self.failing_count,
            "misconfigured_count": self.misconfigured_count,
            "disabled_count": self.disabled_count,
            "conflict_count": self.conflict_count,
            "shadowed_by_curated_count": self.shadowed_by_curated_count,
            "total_detections_90d": self.total_detections_90d,
            "findings": [f.to_dict() for f in self.findings],
            "generated_at": self.generated_at.isoformat() if isinstance(self.generated_at, datetime) else str(self.generated_at),
            "provenance": self.provenance.to_dict() if self.provenance else None,
        }


class LogPricingTier(str, Enum):
    """Google SecOps ingestion pricing tiers (USD per GB)."""
    STANDARD = "STANDARD"          # $1.95/GB
    ENTERPRISE = "ENTERPRISE"      # $2.40/GB
    ENTERPRISE_PLUS = "ENTERPRISE_PLUS"  # $4.60/GB

    @property
    def rate_per_gb(self) -> float:
        rates = {
            LogPricingTier.STANDARD: 1.95,
            LogPricingTier.ENTERPRISE: 2.40,
            LogPricingTier.ENTERPRISE_PLUS: 4.60,
        }
        return rates.get(self, 2.40)


@dataclass
class LogTypeCostMetric:
    """Ingestion volume, event sizing, and multi-tier cost metrics for a single log type."""
    log_type: str
    event_count: int = 0
    volume_bytes: int = 0
    volume_gb_decimal: float = 0.0      # bytes / 10^9
    volume_gib_binary: float = 0.0       # bytes / 2^30
    avg_event_size_bytes: float = 0.0    # volume_bytes / event_count
    is_bloated: bool = False             # avg_event_size_bytes > bloat threshold (e.g. 2048 bytes)
    cost_standard: float = 0.0           # volume_gb_decimal * $1.95
    cost_enterprise: float = 0.0         # volume_gb_decimal * $2.40
    cost_enterprise_plus: float = 0.0    # volume_gb_decimal * $4.60
    pct_total_volume: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "log_type": self.log_type,
            "event_count": self.event_count,
            "volume_bytes": self.volume_bytes,
            "volume_gb_decimal": round(self.volume_gb_decimal, 3),
            "volume_gib_binary": round(self.volume_gib_binary, 3),
            "avg_event_size_bytes": round(self.avg_event_size_bytes, 1),
            "is_bloated": self.is_bloated,
            "cost_standard": round(self.cost_standard, 2),
            "cost_enterprise": round(self.cost_enterprise, 2),
            "cost_enterprise_plus": round(self.cost_enterprise_plus, 2),
            "pct_total_volume": round(self.pct_total_volume, 2),
        }


@dataclass
class FinOpsRecommendation:
    """Actionable FinOps reduction recommendation for an expensive or bloated log source."""
    log_type: str
    category: str  # e.g., "UPSTREAM_DROP_FILTER", "PROXY_NOISE_PRUNING", "SAMPLING_AGGREGATION", "PARSER_NORMALIZATION"
    title: str
    description: str
    potential_volume_savings_gb: float = 0.0
    potential_monthly_savings_usd: float = 0.0
    implementation_guidance: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "log_type": self.log_type,
            "category": self.category,
            "title": self.title,
            "description": self.description,
            "potential_volume_savings_gb": round(self.potential_volume_savings_gb, 2),
            "potential_monthly_savings_usd": round(self.potential_monthly_savings_usd, 2),
            "implementation_guidance": self.implementation_guidance,
        }


@dataclass
class LogCostAnalysisReport(UniversalBatchMixin):
    """Holistic tenant ingestion cost, event sizing, and FinOps optimization report."""
    lookback_window: str = "7d"
    pricing_tier: str = "ENTERPRISE"
    total_events: int = 0
    total_volume_bytes: int = 0
    total_volume_gb: float = 0.0
    total_volume_gib: float = 0.0
    total_projected_monthly_spend_standard: float = 0.0
    total_projected_monthly_spend_enterprise: float = 0.0
    total_projected_monthly_spend_enterprise_plus: float = 0.0
    metrics_by_log_type: List[LogTypeCostMetric] = field(default_factory=list)
    top_volume_drivers: List[LogTypeCostMetric] = field(default_factory=list)
    bloated_sources: List[LogTypeCostMetric] = field(default_factory=list)
    recommendations: List[FinOpsRecommendation] = field(default_factory=list)
    total_potential_savings_usd: float = 0.0
    generated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    provenance: Optional[Provenance] = None

    @property
    def items(self) -> List[LogTypeCostMetric]:
        return self.metrics_by_log_type

    def to_dict(self) -> Dict[str, Any]:
        return {
            "lookback_window": self.lookback_window,
            "pricing_tier": self.pricing_tier,
            "total_events": self.total_events,
            "total_volume_bytes": self.total_volume_bytes,
            "total_volume_gb": round(self.total_volume_gb, 3),
            "total_volume_gib": round(self.total_volume_gib, 3),
            "total_projected_monthly_spend_standard": round(self.total_projected_monthly_spend_standard, 2),
            "total_projected_monthly_spend_enterprise": round(self.total_projected_monthly_spend_enterprise, 2),
            "total_projected_monthly_spend_enterprise_plus": round(self.total_projected_monthly_spend_enterprise_plus, 2),
            "metrics_by_log_type": [m.to_dict() for m in self.metrics_by_log_type],
            "top_volume_drivers": [m.to_dict() for m in self.top_volume_drivers],
            "bloated_sources": [m.to_dict() for m in self.bloated_sources],
            "recommendations": [r.to_dict() for r in self.recommendations],
            "total_potential_savings_usd": round(self.total_potential_savings_usd, 2),
            "generated_at": self.generated_at.isoformat() if isinstance(self.generated_at, datetime) else str(self.generated_at),
            "provenance": self.provenance.to_dict() if self.provenance else None,
        }


@dataclass
class IngestionLabelMetric:
    """Telemetry metrics and classification for an active ingestion label key."""
    label_key: str
    log_types: List[str] = field(default_factory=list)
    event_count: int = 0
    is_auto_generated: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "label_key": self.label_key,
            "log_types": self.log_types,
            "event_count": self.event_count,
            "is_auto_generated": self.is_auto_generated,
        }


@dataclass
class NamespaceMetric:
    """Telemetry metrics and classification for an active UDM namespace."""
    namespace: str
    log_types: List[str] = field(default_factory=list)
    event_count: int = 0
    is_network_rfc1918_relevant: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "namespace": self.namespace,
            "log_types": self.log_types,
            "event_count": self.event_count,
            "is_network_rfc1918_relevant": self.is_network_rfc1918_relevant,
        }


@dataclass
class UntaggedTelemetrySummary:
    """Log types with unlabelled or default-namespace telemetry volume."""
    log_type: str
    unlabelled_event_count: int = 0
    untagged_namespace_event_count: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "log_type": self.log_type,
            "unlabelled_event_count": self.unlabelled_event_count,
            "untagged_namespace_event_count": self.untagged_namespace_event_count,
        }


@dataclass
class DataRbacLabelReference:
    """Audit metric evaluating Data RBAC label query coverage against live telemetry."""
    label_id: str
    display_name: str
    udm_query: str
    extracted_label_keys: List[str] = field(default_factory=list)
    extracted_namespaces: List[str] = field(default_factory=list)
    is_telemetry_backed: bool = False
    status: str = "ACTIVE_MATCH"  # "ACTIVE_MATCH", "UNREFERENCED_IN_TELEMETRY", "SYNTAX_MISMATCH"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "label_id": self.label_id,
            "display_name": self.display_name,
            "udm_query": self.udm_query,
            "extracted_label_keys": self.extracted_label_keys,
            "extracted_namespaces": self.extracted_namespaces,
            "is_telemetry_backed": self.is_telemetry_backed,
            "status": self.status,
        }


@dataclass
class NamespaceLabelHygieneFinding:
    """Actionable hygiene finding for telemetry tagging or Data RBAC alignment."""
    finding_id: str
    category: str  # "DATA_RBAC_GAP", "MISSING_INGESTION_LABELS", "RFC1918_OVERLAP_RISK", "INCONSISTENT_TAGGING"
    severity: str  # "HIGH", "MEDIUM", "LOW", "INFO"
    title: str
    description: str
    affected_log_types: List[str] = field(default_factory=list)
    remediation_guidance: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "finding_id": self.finding_id,
            "category": self.category,
            "severity": self.severity,
            "title": self.title,
            "description": self.description,
            "affected_log_types": self.affected_log_types,
            "remediation_guidance": self.remediation_guidance,
        }


@dataclass
class NamespaceLabelAnalysisReport(UniversalBatchMixin):
    """Holistic tenant report on Ingestion Labels, Namespaces, and Data RBAC alignment."""
    lookback_window: str = "7d"
    total_labelled_events: int = 0
    total_namespaced_events: int = 0
    total_untagged_events: int = 0
    active_ingestion_labels: List[IngestionLabelMetric] = field(default_factory=list)
    active_namespaces: List[NamespaceMetric] = field(default_factory=list)
    untagged_telemetry: List[UntaggedTelemetrySummary] = field(default_factory=list)
    data_rbac_references: List[DataRbacLabelReference] = field(default_factory=list)
    findings: List[NamespaceLabelHygieneFinding] = field(default_factory=list)
    generated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    provenance: Optional[Provenance] = None

    @property
    def items(self) -> List[NamespaceLabelHygieneFinding]:
        return self.findings

    def to_dict(self) -> Dict[str, Any]:
        return {
            "lookback_window": self.lookback_window,
            "total_labelled_events": self.total_labelled_events,
            "total_namespaced_events": self.total_namespaced_events,
            "total_untagged_events": self.total_untagged_events,
            "active_ingestion_labels": [m.to_dict() for m in self.active_ingestion_labels],
            "active_namespaces": [m.to_dict() for m in self.active_namespaces],
            "untagged_telemetry": [u.to_dict() for u in self.untagged_telemetry],
            "data_rbac_references": [r.to_dict() for r in self.data_rbac_references],
            "findings": [f.to_dict() for f in self.findings],
            "generated_at": self.generated_at.isoformat() if isinstance(self.generated_at, datetime) else str(self.generated_at),
            "provenance": self.provenance.to_dict() if self.provenance else None,
        }


# ==============================================================================
# SOC Operating System: Issue, Event, Lease & Work Queue Models
# ==============================================================================

class OperationalPlane(str, Enum):
    """The 7 operational planes of the autonomous SOC."""
    DATA = "data"
    DETECTION = "detection"
    AUTOMATION = "automation"
    PLATFORM = "platform"
    GOVERNANCE = "governance"
    IMPROVEMENT = "improvement"
    EXTERNAL = "external"


class IssueLifecycleStatus(str, Enum):
    """Lifecycle states of a SOC work item."""
    OBSERVED = "OBSERVED"
    QUALIFIED = "QUALIFIED"
    AVAILABLE = "AVAILABLE"
    LEASED = "LEASED"
    CLAIMED = "CLAIMED"
    EXECUTING = "EXECUTING"
    VALIDATING = "VALIDATING"
    APPROVED = "APPROVED"
    APPLIED = "APPLIED"
    VERIFIED = "VERIFIED"
    CLOSED = "CLOSED"
    # Failure / escalation states
    BLOCKED = "BLOCKED"
    NEEDS_HUMAN = "NEEDS_HUMAN"
    VALIDATION_FAILED = "VALIDATION_FAILED"
    ROLLED_BACK = "ROLLED_BACK"


class AuthorityTier(str, Enum):
    """Action-bound authority classification."""
    TIER_1_AUTONOMOUS = "TIER_1_AUTONOMOUS"
    TIER_2_PEER_REVIEW = "TIER_2_PEER_REVIEW"
    TIER_3_HUMAN_APPROVAL = "TIER_3_HUMAN_APPROVAL"


class IssueSeverity(str, Enum):
    """Standardized issue severity."""
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


@dataclass
class IssueSource:
    """Provenance and sensing origin of an issue."""
    deacon_id: str
    observed_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    evidence_fabric_uris: List[str] = field(default_factory=list)
    initial_metrics: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "deacon_id": self.deacon_id,
            "observed_at": self.observed_at,
            "evidence_fabric_uris": self.evidence_fabric_uris,
            "initial_metrics": self.initial_metrics,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> IssueSource:
        return cls(
            deacon_id=data.get("deacon_id", ""),
            observed_at=data.get("observed_at", datetime.now(timezone.utc).isoformat()),
            evidence_fabric_uris=data.get("evidence_fabric_uris", []),
            initial_metrics=data.get("initial_metrics", {}),
        )


@dataclass
class IssueProblem:
    """The observed versus desired state definition."""
    title: str
    description: str = ""
    observed_state: Dict[str, Any] = field(default_factory=dict)
    desired_state: Dict[str, Any] = field(default_factory=dict)
    affected_objects: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "title": self.title,
            "description": self.description,
            "observed_state": self.observed_state,
            "desired_state": self.desired_state,
            "affected_objects": self.affected_objects,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> IssueProblem:
        return cls(
            title=data.get("title", ""),
            description=data.get("description", ""),
            observed_state=data.get("observed_state", {}),
            desired_state=data.get("desired_state", {}),
            affected_objects=data.get("affected_objects", []),
        )


@dataclass
class IssueRouting:
    """Capability requirements and claim status."""
    requires_capabilities: Dict[str, int] = field(default_factory=dict)
    claimed_by: Optional[str] = None
    claim_timestamp: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "requires_capabilities": self.requires_capabilities,
            "claimed_by": self.claimed_by,
            "claim_timestamp": self.claim_timestamp,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> IssueRouting:
        return cls(
            requires_capabilities=data.get("requires_capabilities", {}),
            claimed_by=data.get("claimed_by"),
            claim_timestamp=data.get("claim_timestamp"),
        )


@dataclass
class IssueGovernance:
    """Authority tier and validation criteria."""
    required_authority_tier: str = AuthorityTier.TIER_2_PEER_REVIEW.value
    validation_criteria: List[str] = field(default_factory=list)
    rollback_spec: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "required_authority_tier": self.required_authority_tier,
            "validation_criteria": self.validation_criteria,
            "rollback_spec": self.rollback_spec,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> IssueGovernance:
        return cls(
            required_authority_tier=data.get("required_authority_tier", AuthorityTier.TIER_2_PEER_REVIEW.value),
            validation_criteria=data.get("validation_criteria", []),
            rollback_spec=data.get("rollback_spec", {}),
        )


@dataclass
class Lease:
    """Distributed lease tracking worker assignment and heartbeat expiry."""
    owner: str
    acquired_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    expires_at: str = ""
    generation: int = 1

    def is_expired(self) -> bool:
        if not self.expires_at:
            return True
        try:
            clean = self.expires_at.replace("Z", "+00:00")
            exp = datetime.fromisoformat(clean)
            return datetime.now(timezone.utc) > exp
        except Exception:
            return True

    def to_dict(self) -> Dict[str, Any]:
        return {
            "owner": self.owner,
            "holder_agent": self.owner,
            "acquired_at": self.acquired_at,
            "expires_at": self.expires_at,
            "generation": self.generation,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> Lease:
        return cls(
            owner=data.get("owner", ""),
            acquired_at=data.get("acquired_at", datetime.now(timezone.utc).isoformat()),
            expires_at=data.get("expires_at", ""),
            generation=int(data.get("generation", 1)),
        )


@dataclass
class AgentCapabilityProfile:
    """Advertised capability profile of a worker agent in the fleet."""
    agent_handle: str
    capabilities: Dict[str, int] = field(default_factory=dict)
    operational_planes: List[str] = field(default_factory=list)
    status: str = "ONLINE"  # ONLINE, BUSY, OFFLINE
    current_lease_id: Optional[str] = None
    max_concurrent_leases: int = 3
    heartbeat_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    version: str = "1.0.0"

    def satisfies(self, required: Dict[str, int]) -> bool:
        """Evaluates whether this agent possesses all required capabilities at sufficient levels."""
        for cap, min_level in required.items():
            if self.capabilities.get(cap, 0) < min_level:
                return False
        return True

    def to_dict(self) -> Dict[str, Any]:
        return {
            "agent_handle": self.agent_handle,
            "capabilities": self.capabilities,
            "operational_planes": self.operational_planes,
            "status": self.status,
            "current_lease_id": self.current_lease_id,
            "max_concurrent_leases": self.max_concurrent_leases,
            "heartbeat_at": self.heartbeat_at,
            "version": self.version,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> AgentCapabilityProfile:
        return cls(
            agent_handle=data.get("agent_handle", ""),
            capabilities=data.get("capabilities", {}),
            operational_planes=data.get("operational_planes", []),
            status=data.get("status", "ONLINE"),
            current_lease_id=data.get("current_lease_id"),
            max_concurrent_leases=int(data.get("max_concurrent_leases", 3)),
            heartbeat_at=data.get("heartbeat_at", datetime.now(timezone.utc).isoformat()),
            version=data.get("version", "1.0.0"),
        )


@dataclass
class IssueEvent:
    """Append-only state transition event for the durable Git ledger."""
    event_id: str
    issue_id: str
    sequence: int
    transition_type: str  # OBSERVED, QUALIFIED, CLAIMED, PROPOSAL_CREATED, VALIDATION_RECORDED, APPROVED, APPLIED, VERIFIED, CLOSED
    actor: str
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    details: Dict[str, Any] = field(default_factory=dict)
    evidence_refs: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "event_id": self.event_id,
            "issue_id": self.issue_id,
            "sequence": self.sequence,
            "transition_type": self.transition_type,
            "transition": self.transition_type,
            "actor": self.actor,
            "timestamp": self.timestamp,
            "details": self.details,
            "metadata": self.details,
            "evidence_refs": self.evidence_refs,
            "evidence_references": self.evidence_refs,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> IssueEvent:
        return cls(
            event_id=data.get("event_id", ""),
            issue_id=data.get("issue_id", ""),
            sequence=int(data.get("sequence", 0)),
            transition_type=data.get("transition_type", ""),
            actor=data.get("actor", ""),
            timestamp=data.get("timestamp", datetime.now(timezone.utc).isoformat()),
            details=data.get("details", {}),
            evidence_refs=data.get("evidence_refs", []),
        )


@dataclass
class SOCIssue:
    """Canonical SOC Work Item representing an operational condition requiring attention."""
    id: str
    type: str  # e.g. "parser_drop_spike", "rfc1918_collision_risk", "rule_decay"
    plane: str = OperationalPlane.DATA.value
    status: str = IssueLifecycleStatus.AVAILABLE.value
    severity: str = IssueSeverity.MEDIUM.value
    confidence: float = 1.0
    priority_score: int = 50
    source: IssueSource = field(default_factory=lambda: IssueSource(deacon_id=""))
    problem: IssueProblem = field(default_factory=lambda: IssueProblem(title=""))
    routing: IssueRouting = field(default_factory=IssueRouting)
    governance: IssueGovernance = field(default_factory=IssueGovernance)
    lease: Optional[Lease] = None
    attempts: List[Dict[str, Any]] = field(default_factory=list)
    active_proposal_id: Optional[str] = None
    applied_change_id: Optional[str] = None
    references: Dict[str, Any] = field(default_factory=dict)
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    closed_at: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "issue_id": self.id,
            "type": self.type,
            "plane": self.plane,
            "operational_plane": self.plane,
            "status": self.status,
            "severity": self.severity,
            "confidence": self.confidence,
            "priority_score": self.priority_score,
            "source": self.source.to_dict() if hasattr(self.source, "to_dict") else self.source,
            "problem": self.problem.to_dict() if hasattr(self.problem, "to_dict") else self.problem,
            "routing": self.routing.to_dict() if hasattr(self.routing, "to_dict") else self.routing,
            "governance": self.governance.to_dict() if hasattr(self.governance, "to_dict") else self.governance,
            "lease": self.lease.to_dict() if self.lease else None,
            "attempts": self.attempts,
            "active_proposal_id": self.active_proposal_id,
            "applied_change_id": self.applied_change_id,
            "references": self.references,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "closed_at": self.closed_at,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> SOCIssue:
        src_raw = data.get("source", {})
        source = IssueSource.from_dict(src_raw) if isinstance(src_raw, dict) else src_raw
        prob_raw = data.get("problem", {})
        problem = IssueProblem.from_dict(prob_raw) if isinstance(prob_raw, dict) else prob_raw
        rout_raw = data.get("routing", {})
        routing = IssueRouting.from_dict(rout_raw) if isinstance(rout_raw, dict) else rout_raw
        gov_raw = data.get("governance", {})
        governance = IssueGovernance.from_dict(gov_raw) if isinstance(gov_raw, dict) else gov_raw
        lease_raw = data.get("lease")
        lease = Lease.from_dict(lease_raw) if isinstance(lease_raw, dict) else None

        return cls(
            id=data.get("id", ""),
            type=data.get("type", "operational_issue"),
            plane=data.get("plane", OperationalPlane.DATA.value),
            status=data.get("status", IssueLifecycleStatus.AVAILABLE.value),
            severity=data.get("severity", IssueSeverity.MEDIUM.value),
            confidence=float(data.get("confidence", 1.0)),
            priority_score=int(data.get("priority_score", 50)),
            source=source,
            problem=problem,
            routing=routing,
            governance=governance,
            lease=lease,
            attempts=data.get("attempts", []),
            active_proposal_id=data.get("active_proposal_id"),
            applied_change_id=data.get("applied_change_id"),
            references=data.get("references", {}),
            created_at=data.get("created_at", datetime.now(timezone.utc).isoformat()),
            updated_at=data.get("updated_at", datetime.now(timezone.utc).isoformat()),
            closed_at=data.get("closed_at"),
        )


@dataclass
class ChangeRecord:
    """Record of an actually applied mutation to Google SecOps production state."""
    change_id: str
    issue_id: str
    proposal_id: str
    subsystem: str
    target_resource_id: str
    applied_by: str
    applied_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    commit_sha: Optional[str] = None
    api_response: Dict[str, Any] = field(default_factory=dict)
    status: str = "APPLIED"  # APPLIED, ROLLED_BACK

    def to_dict(self) -> Dict[str, Any]:
        return {
            "change_id": self.change_id,
            "issue_id": self.issue_id,
            "proposal_id": self.proposal_id,
            "subsystem": self.subsystem,
            "target_resource_id": self.target_resource_id,
            "applied_by": self.applied_by,
            "applied_at": self.applied_at,
            "commit_sha": self.commit_sha,
            "api_response": self.api_response,
            "status": self.status,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> ChangeRecord:
        return cls(
            change_id=data.get("change_id", ""),
            issue_id=data.get("issue_id", ""),
            proposal_id=data.get("proposal_id", ""),
            subsystem=data.get("subsystem", ""),
            target_resource_id=data.get("target_resource_id", ""),
            applied_by=data.get("applied_by", ""),
            applied_at=data.get("applied_at", datetime.now(timezone.utc).isoformat()),
            commit_sha=data.get("commit_sha"),
            api_response=data.get("api_response", {}),
            status=data.get("status", "APPLIED"),
        )


@dataclass
class VerificationProof:
    """Post-deployment telemetry proof confirming an issue is verified and resolved."""
    verification_id: str
    change_id: str
    issue_id: str
    verified_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    verifier_actor: str = ""
    cleared: bool = True
    metrics_before: Dict[str, Any] = field(default_factory=dict)
    metrics_after: Dict[str, Any] = field(default_factory=dict)
    summary: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "verification_id": self.verification_id,
            "change_id": self.change_id,
            "issue_id": self.issue_id,
            "verified_at": self.verified_at,
            "verifier_actor": self.verifier_actor,
            "cleared": self.cleared,
            "metrics_before": self.metrics_before,
            "metrics_after": self.metrics_after,
            "summary": self.summary,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> VerificationProof:
        return cls(
            verification_id=data.get("verification_id", ""),
            change_id=data.get("change_id", ""),
            issue_id=data.get("issue_id", ""),
            verified_at=data.get("verified_at", datetime.now(timezone.utc).isoformat()),
            verifier_actor=data.get("verifier_actor", ""),
            cleared=bool(data.get("cleared", True)),
            metrics_before=data.get("metrics_before", {}),
            metrics_after=data.get("metrics_after", {}),
            summary=data.get("summary", ""),
        )


@dataclass
class IdentityFidelityMetric:
    """Density of distinct identity keys populated across a log type in events."""
    log_type: str
    principal_user_id: int = 0
    principal_user_email_address: int = 0
    principal_user_windows_sid: int = 0
    principal_user_product_object_id: int = 0
    target_user_id: int = 0
    target_user_email_address: int = 0
    target_user_windows_sid: int = 0
    target_user_product_object_id: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "log_type": self.log_type,
            "principal_user_id": self.principal_user_id,
            "principal_user_email_address": self.principal_user_email_address,
            "principal_user_windows_sid": self.principal_user_windows_sid,
            "principal_user_product_object_id": self.principal_user_product_object_id,
            "target_user_id": self.target_user_id,
            "target_user_email_address": self.target_user_email_address,
            "target_user_windows_sid": self.target_user_windows_sid,
            "target_user_product_object_id": self.target_user_product_object_id,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> IdentityFidelityMetric:
        return cls(
            log_type=str(data.get("log_type", "UNKNOWN")),
            principal_user_id=int(data.get("principal_user_id", 0) or 0),
            principal_user_email_address=int(data.get("principal_user_email_address", 0) or 0),
            principal_user_windows_sid=int(data.get("principal_user_windows_sid", 0) or 0),
            principal_user_product_object_id=int(data.get("principal_user_product_object_id", 0) or 0),
            target_user_id=int(data.get("target_user_id", 0) or 0),
            target_user_email_address=int(data.get("target_user_email_address", 0) or 0),
            target_user_windows_sid=int(data.get("target_user_windows_sid", 0) or 0),
            target_user_product_object_id=int(data.get("target_user_product_object_id", 0) or 0),
        )


@dataclass
class EntityGraphSource:
    """Provenance and longevity metrics of entity graph bindings."""
    log_type: str
    entity_source: str
    vendor_name: str
    product_name: str
    total_entities: int = 0
    first_seen: Optional[str] = None
    last_seen: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "log_type": self.log_type,
            "entity_source": self.entity_source,
            "vendor_name": self.vendor_name,
            "product_name": self.product_name,
            "total_entities": self.total_entities,
            "first_seen": self.first_seen,
            "last_seen": self.last_seen,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> EntityGraphSource:
        return cls(
            log_type=str(data.get("log_type", "UNKNOWN")),
            entity_source=str(data.get("entity_source", "")),
            vendor_name=str(data.get("vendor_name", "")),
            product_name=str(data.get("product_name", "")),
            total_entities=int(data.get("total_entities", data.get("total", 0)) or 0),
            first_seen=data.get("first_seen"),
            last_seen=data.get("last_seen"),
        )


@dataclass
class LogSourceVolumeMetric:
    """Volume baseline and time range metrics for an ingested log type."""
    log_type: str
    event_count: int = 0
    earliest_event: Optional[str] = None
    latest_event: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "log_type": self.log_type,
            "event_count": self.event_count,
            "earliest_event": self.earliest_event,
            "latest_event": self.latest_event,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> LogSourceVolumeMetric:
        return cls(
            log_type=str(data.get("log_type", "UNKNOWN")),
            event_count=int(data.get("event_count", 0) or 0),
            earliest_event=data.get("earliest_event"),
            latest_event=data.get("latest_event"),
        )


@dataclass
class TenantTelemetryProfile:
    """Comprehensive tenant telemetry cartography profile combining graph, identity, and volume."""
    profiled_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    observation_window_days: int = 7
    identity_metrics: List[IdentityFidelityMetric] = field(default_factory=list)
    graph_sources: List[EntityGraphSource] = field(default_factory=list)
    volume_metrics: List[LogSourceVolumeMetric] = field(default_factory=list)
    total_events_observed: int = 0
    total_graph_entities_observed: int = 0
    summary: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "profiled_at": self.profiled_at,
            "observation_window_days": self.observation_window_days,
            "identity_metrics": [m.to_dict() for m in self.identity_metrics],
            "graph_sources": [g.to_dict() for g in self.graph_sources],
            "volume_metrics": [v.to_dict() for v in self.volume_metrics],
            "total_events_observed": self.total_events_observed,
            "total_graph_entities_observed": self.total_graph_entities_observed,
            "summary": self.summary,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> TenantTelemetryProfile:
        return cls(
            profiled_at=data.get("profiled_at", datetime.now(timezone.utc).isoformat()),
            observation_window_days=int(data.get("observation_window_days", 7)),
            identity_metrics=[IdentityFidelityMetric.from_dict(m) for m in data.get("identity_metrics", [])],
            graph_sources=[EntityGraphSource.from_dict(g) for g in data.get("graph_sources", [])],
            volume_metrics=[LogSourceVolumeMetric.from_dict(v) for v in data.get("volume_metrics", [])],
            total_events_observed=int(data.get("total_events_observed", 0)),
            total_graph_entities_observed=int(data.get("total_graph_entities_observed", 0)),
            summary=data.get("summary", ""),
        )


class CommunicationClass(str, Enum):
    """Classification of communication urgency and routing."""
    URGENT = "urgent"              # Immediate notification (Slack alert / urgent stream)
    OPERATIONAL = "operational"    # Issue/update in the work queue (Gas Town durability boundary)
    INFORMATIONAL = "informational"# Rolled into next scheduled shift briefing


@dataclass
class CommunicationPolicy:
    """Routing and notification policy attached to an observation or finding."""
    communication_class: str = CommunicationClass.OPERATIONAL.value
    urgency: str = "medium"  # critical, high, medium, low
    briefing: bool = True
    immediate_notification: bool = False
    target_channel: Optional[str] = None
    routing_class: Optional[Any] = None
    publish_to_chat: Optional[bool] = None
    channel: Optional[str] = None

    def __post_init__(self):
        if self.routing_class is not None:
            val = getattr(self.routing_class, "value", self.routing_class)
            self.communication_class = str(val).lower()
        if self.publish_to_chat is not None and not self.immediate_notification:
            self.immediate_notification = self.publish_to_chat
        if self.channel and not self.target_channel:
            self.target_channel = self.channel

    def to_dict(self) -> Dict[str, Any]:
        return {
            "communication_class": self.communication_class,
            "class": self.communication_class,
            "urgency": self.urgency,
            "briefing": self.briefing,
            "immediate_notification": self.immediate_notification,
            "target_channel": self.target_channel,
            "publish_to_chat": self.immediate_notification,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> CommunicationPolicy:
        if not isinstance(data, dict):
            return cls()
        c_class = data.get("communication_class") or data.get("class") or CommunicationClass.OPERATIONAL.value
        pub_chat = data.get("publish_to_chat")
        immed = bool(data.get("immediate_notification", False)) or bool(pub_chat) if pub_chat is not None else False
        return cls(
            communication_class=str(c_class).lower(),
            urgency=str(data.get("urgency", "medium")).lower(),
            briefing=bool(data.get("briefing", True)),
            immediate_notification=immed,
            target_channel=data.get("target_channel") or data.get("channel"),
            publish_to_chat=pub_chat,
        )



@dataclass
class SubjectRef:
    """Target subject of an observation or relationship."""
    type: str  # log_source, parser, rule, playbook, identity, integration, feed, tenant
    id: str

    def to_dict(self) -> Dict[str, Any]:
        return {"type": self.type, "id": self.id}

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> SubjectRef:
        if not isinstance(data, dict):
            return cls(type="unknown", id=str(data))
        return cls(type=str(data.get("type", "unknown")), id=str(data.get("id", "")))


@dataclass
class ObserverRef:
    """Agent and execution run that produced an observation."""
    agent: str
    run_id: str = ""
    deacon: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {"agent": self.agent, "run_id": self.run_id, "deacon": self.deacon}

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> ObserverRef:
        if not isinstance(data, dict):
            return cls(agent=str(data))
        return cls(
            agent=str(data.get("agent", "")),
            run_id=str(data.get("run_id", "")),
            deacon=str(data.get("deacon", "")),
        )


@dataclass
class Observation:
    """Normalized assertion made by an autonomous agent about tenant operational state."""
    subject: SubjectRef
    predicate: str  # e.g. "parser_health", "volume_24h", "rule_decay", "iam_drift", "identity_density"
    value: Dict[str, Any]
    observed_by: ObserverRef
    observation_id: str = ""
    observed_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    valid_until: str = field(
        default_factory=lambda: (datetime.now(timezone.utc) + timedelta(hours=24)).isoformat()
    )
    confidence: float = 1.0

    scope: Dict[str, str] = field(default_factory=dict)
    evidence_refs: List[str] = field(default_factory=list)
    issue_id: Optional[str] = None
    communication: CommunicationPolicy = field(default_factory=CommunicationPolicy)
    policy: Optional[CommunicationPolicy] = None

    def __post_init__(self):
        if self.policy is not None:
            self.communication = self.policy
        if not self.observation_id:
            now_str = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
            rnd = os.urandom(3).hex()
            self.observation_id = f"obs-{now_str}-{rnd}"


    def is_stale(self, as_of: Optional[datetime] = None) -> bool:
        ref = as_of or datetime.now(timezone.utc)
        try:
            val_dt = datetime.fromisoformat(self.valid_until.replace("Z", "+00:00"))
            return ref > val_dt
        except Exception:
            return False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "observation_id": self.observation_id,
            "subject": self.subject.to_dict(),
            "predicate": self.predicate,
            "value": self.value,
            "observed_by": self.observed_by.to_dict(),
            "observed_at": self.observed_at,
            "valid_until": self.valid_until,
            "confidence": self.confidence,
            "scope": self.scope,
            "evidence_refs": self.evidence_refs,
            "issue_id": self.issue_id,
            "communication": self.communication.to_dict(),
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> Observation:
        return cls(
            observation_id=str(data.get("observation_id", "")),
            subject=SubjectRef.from_dict(data.get("subject", {})),
            predicate=str(data.get("predicate", "")),
            value=data.get("value", {}) if isinstance(data.get("value"), dict) else {},
            observed_by=ObserverRef.from_dict(data.get("observed_by", {})),
            observed_at=data.get("observed_at", datetime.now(timezone.utc).isoformat()),
            valid_until=data.get("valid_until", datetime.now(timezone.utc).isoformat()),
            confidence=float(data.get("confidence", 1.0)),
            scope=data.get("scope", {}) if isinstance(data.get("scope"), dict) else {},
            evidence_refs=list(data.get("evidence_refs", [])),
            issue_id=data.get("issue_id"),
            communication=CommunicationPolicy.from_dict(data.get("communication", {})),
        )


@dataclass
class KnowledgeGap:
    """An explicit unknown or unmapped operational state surfaced by the SOC."""
    gap_id: str
    category: str  # "ownership", "dependency", "governance", "staleness", "coverage"
    title: str
    description: str
    subject: Optional[SubjectRef] = None
    impact: str = "MEDIUM"  # CRITICAL, HIGH, MEDIUM, LOW
    recommendation: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "gap_id": self.gap_id,
            "category": self.category,
            "title": self.title,
            "description": self.description,
            "subject": self.subject.to_dict() if self.subject else None,
            "impact": self.impact,
            "recommendation": self.recommendation,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> KnowledgeGap:
        subj = SubjectRef.from_dict(data.get("subject", {})) if data.get("subject") else None
        return cls(
            gap_id=str(data.get("gap_id", "")),
            category=str(data.get("category", "coverage")),
            title=str(data.get("title", "")),
            description=str(data.get("description", "")),
            subject=subj,
            impact=str(data.get("impact", "MEDIUM")),
            recommendation=str(data.get("recommendation", "")),
        )


@dataclass
class KnowledgeSnapshot:
    """Authoritative snapshot answering: 'What does the SOC currently understand about itself?'"""
    snapshot_id: str
    generated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    tenant_coverage: Dict[str, Any] = field(default_factory=dict)
    telemetry_health: Dict[str, Any] = field(default_factory=dict)
    parsing_health: Dict[str, Any] = field(default_factory=dict)
    detection_health: Dict[str, Any] = field(default_factory=dict)
    soar_health: Dict[str, Any] = field(default_factory=dict)
    governance_health: Dict[str, Any] = field(default_factory=dict)
    cost_metrics: Dict[str, Any] = field(default_factory=dict)
    knowledge_freshness: Dict[str, Any] = field(default_factory=dict)
    knowledge_gaps: List[KnowledgeGap] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "snapshot_id": self.snapshot_id,
            "generated_at": self.generated_at,
            "tenant_coverage": self.tenant_coverage,
            "telemetry_health": self.telemetry_health,
            "parsing_health": self.parsing_health,
            "detection_health": self.detection_health,
            "soar_health": self.soar_health,
            "governance_health": self.governance_health,
            "cost_metrics": self.cost_metrics,
            "knowledge_freshness": self.knowledge_freshness,
            "knowledge_gaps": [g.to_dict() for g in self.knowledge_gaps],
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> KnowledgeSnapshot:
        return cls(
            snapshot_id=str(data.get("snapshot_id", "")),
            generated_at=data.get("generated_at", datetime.now(timezone.utc).isoformat()),
            tenant_coverage=data.get("tenant_coverage", {}),
            telemetry_health=data.get("telemetry_health", {}),
            parsing_health=data.get("parsing_health", {}),
            detection_health=data.get("detection_health", {}),
            soar_health=data.get("soar_health", {}),
            governance_health=data.get("governance_health", {}),
            cost_metrics=data.get("cost_metrics", {}),
            knowledge_freshness=data.get("knowledge_freshness", {}),
            knowledge_gaps=[KnowledgeGap.from_dict(g) for g in data.get("knowledge_gaps", [])],
        )


@dataclass
class ShiftBriefing:
    """Operational handover answering: 'What is happening and what changed since previous shift?'"""
    briefing_id: str
    shift_name: str
    window_start: str
    window_end: str
    generated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    requires_attention: List[Dict[str, Any]] = field(default_factory=list)
    changed_since_previous: List[Dict[str, Any]] = field(default_factory=list)
    agent_work_in_progress: List[Dict[str, Any]] = field(default_factory=list)
    no_action_required: List[str] = field(default_factory=list)
    carry_over: List[Dict[str, Any]] = field(default_factory=list)
    summary_narrative: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "briefing_id": self.briefing_id,
            "shift_name": self.shift_name,
            "window_start": self.window_start,
            "window_end": self.window_end,
            "generated_at": self.generated_at,
            "requires_attention": self.requires_attention,
            "changed_since_previous": self.changed_since_previous,
            "agent_work_in_progress": self.agent_work_in_progress,
            "no_action_required": self.no_action_required,
            "carry_over": self.carry_over,
            "summary_narrative": self.summary_narrative,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> ShiftBriefing:
        return cls(
            briefing_id=str(data.get("briefing_id", "")),
            shift_name=str(data.get("shift_name", "Handover")),
            window_start=str(data.get("window_start", "")),
            window_end=str(data.get("window_end", "")),
            generated_at=data.get("generated_at", datetime.now(timezone.utc).isoformat()),
            requires_attention=list(data.get("requires_attention", [])),
            changed_since_previous=list(data.get("changed_since_previous", [])),
            agent_work_in_progress=list(data.get("agent_work_in_progress", [])),
            no_action_required=list(data.get("no_action_required", [])),
            carry_over=list(data.get("carry_over", [])),
            summary_narrative=str(data.get("summary_narrative", "")),
        )




