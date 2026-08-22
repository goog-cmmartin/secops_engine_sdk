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

---

## 6. Capability "Definition of Done" Checklist

Every new or refined capability must touch each relevant layer below before it
is considered complete. Skipping a layer silently degrades the SDK/CLI/MCP
contract. Treat this as the merge gate.

### 6.1 Discovery & specification
- [ ] Behavior observed against live SecOps and assigned a **status** (§2:
      `VERIFIED` / `OBSERVED_NOT_MAPPED` / …).
- [ ] Live observations recorded under `discovery/observations/`.
- [ ] API/UDM mapping documented (endpoint, params, payload shape).

### 6.2 Engine core
- [ ] Handler implemented in the appropriate `engine/workflows/` module
      (no synthetic data — see §4 banned terms).
- [ ] Registered as a `WorkflowCapability` in `engine/registry.py` with:
      `capability_id`, `name`, `description`, `category`, `handler`,
      `mcp_tool_name`, `evidence_path`.
- [ ] Taxonomy correct (§2 axes): `kind`, `domain`, `cardinality`. Rely on
      `engine/taxonomy.py` derivation; set explicit values only to override,
      and add a comment explaining why.
- [ ] `composed` workflows declare their `uses` edges (composition DAG stays
      acyclic and non-dangling — enforced by the capability contract suite).
- [ ] `unbounded` queries carry the require-filter policy (Invariant #9).
- [ ] Exposed on the SDK facade (`engine/facade.py`) via lazy loading.

### 6.3 Schema
- [ ] Canonical UDM fields / mappings added or updated in `engine/schema.py`
      where the capability introduces new fields.
- [ ] `input_schema` / `output_schema` populated if the capability defines a
      structured contract.

### 6.4 Frontends
- [ ] CLI (`clients/cli/secops.py`) wiring + `--help` text.
- [ ] MCP tool name is unique and stable (matches `mcp_tool_name`).
- [ ] Desktop (`clients/desktop/`) surface updated **if** the capability is
      user-facing there.

### 6.5 Tests (anti-mock; live-decoupled)
- [ ] Capability contract test coverage (`tests/test_capability_contract.py`)
      still passes (registration, DAG, uniqueness invariants).
- [ ] Taxonomy assertions (`tests/test_taxonomy.py`) updated if counts/axes
      change.
- [ ] Behavioral test added for the slice, using `tests/test_helpers.py` so it
      gracefully `SkipTest`s on unconfigured environments.

### 6.6 Docs & provenance
- [ ] **Regenerate the capability reference:**
      `python scripts/generate_capabilities_doc.py`
      (CI enforces freshness via `--check`; a stale `docs/CAPABILITIES.md`
      fails the build).
- [ ] `README.md` counts/claims still accurate (capability + workflow-module
      totals).
- [ ] `MEMORY.md` index updated if a new top-level doc/report was added.
- [ ] `evidence_path` points at a real evidence/report artifact.
