# UDM Search Behavioral & Engine Test Inventory

This document defines the authoritative test inventory for the `search.udm` workflow capability.
All tests must execute against live Google SecOps APIs via `SecOpsClient` (or Playwright oracle where specified).
Zero mocks, fixtures, or synthetic fallback data are permitted.

---

## Test Cases

| Test ID | Name | Type | Description | Invariant / Assertion |
| :--- | :--- | :--- | :--- | :--- |
| **UDM-001** | `test_valid_query_validates` | Unit / Engine | Submits syntactically valid UDM query (`metadata.event_type = "USER_LOGIN"`) to `query.validate`. | Returns `valid: true`, status `200`. |
| **UDM-002** | `test_invalid_query_rejected` | Unit / Engine | Submits malformed UDM query (`invalid syntax !!!`). | Surface explicit validation error without swallow. |
| **UDM-003** | `test_search_operation_starts` | Acceptance | Initiates search job with valid query and time range. | Receives non-empty `session_id` (operation path `projects/.../operations/s-udm-...`). |
| **UDM-004** | `test_session_lifecycle_transitions` | Engine State | Tracks state transitions from `validating` → `starting` → `running` → `completed`. | Session status updates in real-time. |
| **UDM-005** | `test_first_batch_retrieval` | Acceptance | Retrieves events for index range `1..2000`. | Events parsed into `domain.UdmEvent` structure. `received_count` matches event list length. |
| **UDM-006** | `test_subsequent_range_retrieval` | Acceptance | Retrieves next index range `2001..4000`. | Index offset accurately increments; no duplicate event IDs. |
| **UDM-007** | `test_more_data_terminates` | Acceptance | Verifies retrieval loop stops when `moreDataAvailable == false`. | Session marks `completeness: complete`. |
| **UDM-008** | `test_cancellation_stops_operation` | Acceptance / State | Dispatches cancellation while in `running` state. | Lifecycle transitions to `cancelled`; ongoing stream terminates cleanly. |
| **UDM-009** | `test_events_retained_after_cancel` | Engine State | Queries session results after cancellation. | All events received prior to cancel remain fully accessible. |
| **UDM-010** | `test_partial_failure_surfaced` | Engine State | Simulates/encounters upstream failure mid-stream. | Status is `failed`, `completeness: partial`, error details preserved, received events retained. |
| **UDM-011** | `test_receive_limit_respected` | Engine Policy | Sets `receive_limit: 500` for broad query. | Retrieval halts when 500 events collected even if provider has more. |
| **UDM-012** | `test_no_mock_data_audit` | Anti-Mock Audit | Scans engine and adapter runtime for banned mock identifiers and synthetic defaults. | 100% pass; data strictly originated from Google SecOps. |

---

## Oracle Verification Protocol

- **Google SecOps UI Oracle:** Playwright / DevTools trace verifies that `query.validate` and `:streamSearch` behavior on the engine matches live Google SecOps frontend responses within acceptable timing tolerance.
- **Evidence Provenance:** Every test run outputs test evidence linked to the session ID and raw event timestamps.
