# AGENTS.md: SecOps Engine Invariants & Operating Guidelines

This document outlines the mandatory operational invariants, architectural boundaries, agent role specifications, and verification rules for all AI agents and contributors working on the SecOps Workflow Engine project.

---

## 1. Non-Negotiable Invariants

1. **Strict Origin of Production Data:**
   - Production data must originate exclusively from `SecOpsClient` communicating with live Google SecOps endpoints.
   - Zero mock, fixture, synthetic, fake, dummy, sample, or fabricated SecOps data is permitted anywhere in production code.

2. **Error Visibility & Integrity:**
   - API failures, timeouts, authentication errors, and unexpected schemas must remain visible as explicit failures.
   - Never catch an API error only to replace it with fallback data or silent defaults.

3. **Immutable Acceptance Tests:**
   - Existing acceptance tests must never be modified, deleted, or weakened to make an implementation pass.
   - If a test is genuinely flawed due to an updated specification, changes require explicit human review and approval.

4. **Definition of "COMPLETE":**
   - A feature or workflow may only be marked `COMPLETE` when all associated unit tests, acceptance tests, lint checks, type checks, and automated no-mock audits pass.
   - A visually plausible or simulated implementation is strictly rejected.

5. **Handling Ambiguity & Unknowns:**
   - Unknown or unverified behavior must be reported explicitly as `UNKNOWN` or `BLOCKED_API_MAPPING`.
   - Never infer, guess, or approximate behavior not backed by observed network traces or official API specifications.

6. **Observable UX Dependency Rule:**
   - An observed Google SecOps UI behavior is not considered understood until its exact API and data dependency has been identified and documented, or explicitly classified as `UNKNOWN_API` / `UNSUPPORTED_API`.

7. **Architectural Separation of Concerns:**
   - UI code (Qt native, reference web, CLI) must **never** directly orchestrate chained SecOps API calls.
   - All chained, multi-step, paginated, and streaming behaviors belong exclusively in the **Workflow Engine**.
   - UI and MCP clients are consumers of workflow engine sessions and primitives.

8. **End-to-End Evidence & Provenance:**
   - Every workflow result and finding must retain verifiable provenance:
     `Finding → Workflow Step → API Call / Response → Raw Event IDs / Query`.

9. **Bounded Autonomy for Unbounded Queries:**
   - Every capability declares a result-set `cardinality` (`single`, `bounded`,
     `unbounded`), auto-derived for queries from their terminal verb; only
     `query` capabilities carry one.
   - Any `unbounded` (collection-returning) query MUST carry the
     `require_filter_for_unbounded_query` agent policy. This is auto-attached
     at registration; unknown query verbs fail safe to `unbounded`.
   - Consumers that execute capabilities autonomously (MCP tools, agents) MUST
     honor this policy and refuse to run a flagged query without a filter, so an
     agent cannot page an entire tenant. An explicit `False` override requires
     documented human justification.

---

## 2. Classification Status Taxonomy

When analyzing, specifying, or implementing SecOps behaviors, every interaction and API mapping must use one of the following explicit statuses:

| Status | Definition |
| :--- | :--- |
| **`VERIFIED`** | Behavior is observed in live Google SecOps, mapped to documented API calls, and covered by automated behavioral tests. |
| **`OBSERVED_NOT_MAPPED`** | Behavior / UI interaction is observed in the product, but the underlying API call or payload structure has not yet been isolated or documented. |
| **`UNKNOWN`** | Behavior or internal state transition cannot be determined from available network traces or documentation. |
| **`UNSUPPORTED_API`** | Capability is implemented via proprietary internal endpoints not exposed or achievable via public Google SecOps APIs. |
| **`BLOCKED_API_MAPPING`** | Engine implementation is blocked because a required API dependency or parameter mapping is missing. |

### Capability Classification Axes

Beyond status, every registered capability is auto-classified on three axes
(explicit values always win over derivation; see `engine/taxonomy.py`):

| Axis | Values | Meaning |
| :--- | :--- | :--- |
| **`kind`** | `query`, `primitive`, `workflow` | Read vs. single mutation vs. composed multi-step. |
| **`domain`** | e.g. `case`, `feed`, `udm` | Functional area, from the capability id / category. |
| **`cardinality`** | `single`, `bounded`, `unbounded`, `None` | Result-set shape of a query; `None` for non-queries. |

`cardinality` drives the require-filter safety policy in Invariant #9.

---

## 3. Specialized Agent Role Profiles

To maintain separation of concerns and avoid contamination, agents must operate under one of three distinct roles.

### Role A: SecOps Behaviour Explorer (Discovery)
* **Objective:** Interactively explore Google SecOps using Chrome DevTools MCP and official Developer Knowledge documentation.
* **Scope:** Discovery and specification generation only. **Do NOT write or modify production code.**
* **Protocol:**
  1. Identify all visible UI states and meaningful user actions.
  2. Record state transitions and exact network requests triggered per action.
  3. Map request dependencies, parallel executions, lazy-loaded components, pagination tokens, and cancellation behaviors.
  4. Output candidate YAML workflow specifications and discovery markdown reports with screenshot/trace references.

### Role B: SecOps Engine Implementer (Implementation)
* **Objective:** Implement workflow contracts in the SecOps Engine.
* **Authoritative Inputs (in priority order):**
  1. Approved workflow specifications (`specs/**/*.yaml`)
  2. Engine acceptance and unit tests (`tests/engine/**/*`)
  3. Generated SecOps API types & client (`engine/api/**/*`)
  4. Architecture invariants in `AGENTS.md`
* **Rules:**
  - Strict compliance with no-mock invariant.
  - Implement through `SecOpsClient`.
  - Preserve cancellation, pagination, error propagation, and streaming semantics.
  - If a specification cannot be fulfilled with known APIs, halt and report `BLOCKED_API_MAPPING`.

### Role C: SecOps Compatibility Verifier (Verification)
* **Objective:** Independently verify that an engine or client implementation strictly adheres to the behavioral contract and live Google SecOps oracle.
* **Scope:** Independent testing and evaluation. **Do NOT modify implementation code. Do NOT modify or weaken acceptance tests.**
* **Protocol:**
  - Execute automated test suites against engine and live endpoints.
  - Audit interaction behavior, sequencing, pagination, cancellation, and error handling.
  - Report findings using explicit statuses: `PASS`, `FAIL`, `BLOCKED`, `NOT_TESTED`.

---

## 4. Anti-Mock Automated CI & Production Banned Terms

Production code (excluding test files located strictly in `tests/` or exploratory scripts in `discovery/`) will be scanned by CI for banned mock identifiers:

- `mock` / `Mock` / `MOCK`
- `fixture` / `Fixture`
- `dummy` / `Dummy`
- `fake` / `Fake`
- `sampleData` / `sample_data`
- `placeholderData` / `placeholder_data`
- `testData` / `test_data` (in production paths)

Any occurrence of synthetic data structures in production source directories (`engine/`, `adapters/`, `clients/`) will immediately fail CI and block merges.

---

## 5. Standard Discovery → Specification → Implementation → Verification Loop

For every vertical slice (starting with **UDM Search**):
```
┌─────────────────────────────────────────────────────────┐
│ 1. EXPLORE: Behaviour Explorer inspects live SecOps      │
│ 2. MAP: Correlate actions to SecOps APIs / UDM schemas  │
│ 3. SPECIFY: Produce candidate YAML workflow contract    │
│ 4. REVIEW: Human validates concurrency & edge cases     │
│ 5. TEST CONTRACT: Create Playwright/engine tests        │
│ 6. IMPLEMENT: Engine Implementer codes against spec     │
│ 7. VERIFY: Compatibility Verifier validates behaviour   │
│ 8. CONSUME: Wire to CLI, Reference UI, Qt & MCP         │
└─────────────────────────────────────────────────────────┘
```
