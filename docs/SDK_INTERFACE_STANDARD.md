# SecOps Engine SDK Interface Standard

This document establishes the official design standards, argument patterns, and data model invariants for the SecOps Engine SDK (`goog-cmmartin/secops_engine_sdk`).

---

## 1. Motivation & Background

When autonomous agents or LLM-driven orchestrators invoke Python SDK methods, they often encounter runtime exceptions caused by rigid typing requirements:
1. **Strict Dataclass Requirements:** Requiring callers to import and construct complex container objects (e.g., `SearchRequest`, `CaseSearchQuery`) rather than passing natural keyword arguments.
2. **Strict Enum Identifiers:** Requiring strict imports of enum types (e.g., `EntityType.IP_ADDRESS`, `PlaybookType.PLAYBOOK_TYPE_REGULAR`) instead of case-insensitive string aliases (`"ip"`, `"regular"`).
3. **Strict Collection Types:** Raising `TypeError` when passed a single dictionary or string instead of a `List[...]`.
4. **Deep Dictionary Indexing:** Requiring deep, fragile nested key paths (e.g. `raw_event['event']['metadata']['eventTimestamp']`) instead of intuitive dot-notation (`event.metadata.event_timestamp` or `event.principal.ip`).
5. **Identifier Types:** Rejecting integer case IDs (`104984`) or failing on full resource path names (`"cases/104984"`).

The **SecOps Engine SDK Interface Standard** guarantees that all public SDK interfaces are resilient, caller-friendly, and maintain complete backward compatibility.

---

## 2. Core Interface Principles

### Principle 1: Polymorphic Top-Level Arguments

Any public workflow or facade method that accepts a structured request dataclass must also accept direct positional and keyword arguments:

- **Rule:** If the first argument is an instance of the target dataclass, it is used directly.
- **Rule:** If the first argument is a string (e.g., query text or case ID), or if parameters are supplied as keyword arguments, the method automatically constructs and validates the target dataclass.
- **Example (`search_udm`):**
  ```python
  # Pattern A: Passing structured SearchRequest
  req = SearchRequest(query='principal.ip = "10.0.0.1"', start_time="2026-09-01T00:00:00Z", end_time="2026-09-02T00:00:00Z")
  session = engine.search_udm(req)

  # Pattern B: Positional query string
  session = engine.search_udm('principal.ip = "10.0.0.1"', start_time="2026-09-01T00:00:00Z", end_time="2026-09-02T00:00:00Z")

  # Pattern C: Keyword arguments
  session = engine.search_udm(query='principal.ip = "10.0.0.1"', limit=100)
  ```

### Principle 2: Universal Enum & Alias Coercion

All parameters accepting an `Enum` type must accept case-insensitive string aliases.

- **Standard Coercion Helpers** (in `engine.domain`):
  - `coerce_entity_type(val: Union[EntityType, str]) -> EntityType`
    - Supports canonical aliases: `"ip"`, `"ipv4"`, `"ipv6"`, `"hostname"`, `"host"`, `"user"`, `"username"`, `"email"`, `"hash"`, `"sha256"`, `"md5"`, `"domain"`, `"url"`, `"mac"`.
  - `coerce_playbook_type(val: Union[PlaybookType, str]) -> PlaybookType`
    - Supports `"regular"`, `"standard"`, `"nested"`, `"investigation"`.
  - `coerce_case_status(val: Union[CaseStatus, str]) -> CaseStatus`
  - `coerce_case_priority(val: Union[CasePriority, str]) -> CasePriority`
  - `coerce_filter_operator(val: Union[FilterOperator, str]) -> FilterOperator`
    - Supports `"eq"`, `"equals"`, `"="`, `"=="`, `"ne"`, `"!="`, `"contains"`, `"regex"`.

- **Example (`search_from_entity`):**
  ```python
  # All of the following are valid and equivalent:
  engine.search_from_entity(EntityType.IP_ADDRESS, "10.0.0.1", start_time, end_time)
  engine.search_from_entity("ip", "10.0.0.1", start_time, end_time)
  engine.search_from_entity("IP_ADDRESS", "10.0.0.1", start_time, end_time)
  ```

### Principle 3: Flexible Collection Inputs

Methods expecting lists of items must transparently accept a single item and wrap it into a 1-element list.

- **Data Table Rows:** `add_data_table_rows(table_id, rows)` accepts either a single `dict` (`{"ip": "1.2.3.4"}`) or `List[dict]`.
- **Search Filters:** `refine_search(base, filters)` accepts:
  - A `FieldFilter` object or `List[FieldFilter]`.
  - A dictionary: `{"field": "principal.ip", "operator": "=", "value": "1.2.3.4"}` or `List[dict]`.
  - A tuple: `("principal.ip", "=", "1.2.3.4")`, `("principal.ip", "1.2.3.4")`, or `List[tuple]`.
- **Search Tags & Priorities:** `search_cases(tags="malware", priorities="HIGH")` auto-normalizes scalar strings to single-item lists.
- **Batch Case IDs:** `orchestrate_case_triage(case_ids=104984)` auto-normalizes a scalar ID to `["104984"]`.

### Principle 4: Universal `UDMEvent` Wrapper

Raw Chronicle UDM events have unpredictable nesting (often wrapping the UDM payload under an outer `"event"` envelope) and mixed casing (UDM camelCase vs Python snake_case).

All events returned by `SecOpsEngine` (`search_udm`, `search_from_entity`, `investigate_event`, etc.) are wrapped in `UDMEvent`:

1. **Dictionary Subclass:**
   - `isinstance(event, dict)` is `True`.
   - Full dictionary indexing works as before: `event["metadata"]`, `event["principal"]`.
   - Backward compatible with existing consumers, `json.dumps()`, and pandas DataFrame constructors.

2. **Root Envelope Transparency:**
   - Accessing `event["metadata"]` automatically checks root `self["metadata"]` or nested `self["event"]["metadata"]`.
   - Accessing `event["event"]["metadata"]` continues to work.

3. **Dot-Notation Attribute Access:**
   - Analysts and agents can navigate UDM fields directly:
     ```python
     timestamp = event.metadata.event_timestamp
     src_ip = event.principal.ip
     target_host = event.target.hostname
     ```

4. **Case Mapping:**
   - Both snake_case and camelCase attributes are resolved:
     `event.metadata.event_timestamp == event.metadata.eventTimestamp`.

5. **Helper Properties:**
   - `event.raw`: Returns raw log text string if available.
   - `event.timestamp`: Canonical ISO timestamp string.
   - `event.event_type`: Event type string (e.g. `PROCESS_LAUNCH`, `NETWORK_CONNECTION`).
   - `event.log_type`: Chronicle log type string (e.g. `WINDOWS_SYSMON`, `PUNCHED_IN`).
   - `event.product_name`: Target/source product name.
   - `event.get_field("principal.user.userid")`: Deep dot-path traversal with fallback default.
   - `event.to_dict()`: Clean Python dictionary representation.

### Principle 5: Identifier Normalization

Case identifiers in Google SecOps are represented in various forms: integers (`104984`), strings (`"104984"`), or resource names (`"projects/sdl-preview-americas/locations/us/instances/.../cases/104984"`).

- All case-related methods (`investigate_case`, `triage_case`, `add_case_comment`, `list_case_comments`, `update_case`, `assign_case`, `set_case_stage`, `get_case_wall`, etc.) accept `Union[str, int]`.
- Identifiers are normalized via `_normalize_case_id`:
  ```python
  def _normalize_case_id(case_id: Union[str, int]) -> str:
      s = str(case_id).strip()
      return s.split("/")[-1] if "/" in s else s
  ```

---

## 3. Compliance Checklist for New Methods

When implementing a new workflow or facade capability:
- [ ] Accepts flat keyword arguments alongside structured dataclass requests.
- [ ] Accepts case-insensitive string aliases for any enum parameters using `coerce_*` helpers.
- [ ] Accepts scalar values for list parameters (`List[T]` or `T`).
- [ ] Returns events wrapped in `UDMEvent`.
- [ ] Normalizes resource IDs (`case_id`, `rule_id`, `table_id`).
- [ ] Preserves non-negotiable invariants: zero mock/synthetic data in production paths.
