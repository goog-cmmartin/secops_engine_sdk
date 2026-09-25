---
name: secops-knowledge-authoring
description: >-
  Author, update, and validate operational knowledge base entries across Google SecOps
  (SIEM & SOAR), GCP, and BindPlane OP conforming to Open Knowledge Format (OKF v0.2).
  Use this skill when creating or refining concepts, features, personas, executable tasks,
  and Attested Computations.
---

# SecOps Knowledge Authoring Guide (OKF v0.2 Compliant)

This skill guides AI agents and contributors in authoring, expanding, and maintaining the **Google SecOps Knowledge Base** located in `knowledge/`, conforming to the **Open Knowledge Format (OKF v0.2)** standard.

---

## 1. The 5-Layer OKF Architecture

Every operational domain must be mapped across five decoupled layers:

1. **Concepts (`knowledge/concepts/`)**: Mental models, schemas, taxonomies, and operational guarantees.
   - Example: `concept.udm_search_lifecycle`, `concept.ingestion_pipeline_topology`
2. **Features (`knowledge/features/{platform}/`)**: Platform capabilities, APIs, Looker dashboard queries, and parameter limits.
   - Platforms: `secops_siem`, `secops_soar`, `bindplane`, `gcp`
   - Example: `feature.siem.native_dashboards`, `feature.siem.rules_engine`
3. **Personas (`knowledge/personas/`)**: Operational roles, scopes of authority, and cadences.
   - Example: `persona.platform_engineer`, `persona.detection_engineer`, `persona.ingestion_specialist`
4. **Tasks (`knowledge/tasks/{persona}/`)**: Executable runbooks tying Persona + Trigger + Features/Tools + Evaluation Rules + Remediation.
   - Example: `task.platform_engineer.check_udm_search_performance`
5. **Attested Computations (`knowledge/computations/`)**: Sanctioned computational queries (YARA-L 2, Looker aggregations, BigQuery metrics) bound to typed parameters, executor runbooks, and deterministic attesters.
   - Example: `computation.feed_timestamp_skew`

---

## 2. OKF v0.2 Metadata & Trust Tiers

Every `.md` file in `knowledge/` (except `index.md`, `README.md`, and `templates/`) MUST begin with valid YAML frontmatter including OKF v0.2 provenance and verification metadata.

### Standard OKF v0.2 Keys

| Key | Type | Description |
| :--- | :--- | :--- |
| `type` | string | **Required**. One of `concept`, `feature`, `persona`, `task`, `Attested Computation`. |
| `id` | string | Unique namespaced identifier (`concept.<name>`, `feature.<p>.<f>`, `persona.<name>`, `task.<p>.<t>`, `computation.<name>`). |
| `title` | string | Human-readable document title. |
| `description` | string | Concise one-line description for progressive disclosure and search indexing. |
| `tags` | list[str] | Categorization tags (e.g. `[secops, yaral, ingestion]`). |
| `status` | string | `draft`, `stable`, or `deprecated`. |
| `generated` | mapping | `{ by: "<actor>", at: "<iso8601>" }` timestamped author/producer. |
| `verified` | list | List of verifications `[{ by: "<actor>", at: "<iso8601>" }]`. |
| `stale_after` | string | ISO 8601 UTC timestamp indicating when the knowledge must be re-validated. |
| `sources` | list | External references `[{ id: "<id>", resource: "<url_or_path>", title: "<title>" }]`. |

### Actor Conventions (OKF v0.2 §7)
- `human:<id>`: Verified by a human engineer/architect (e.g. `human:secops-architect`, `human:analyst@google.com`).
- `process:<id>`: Generated/verified by an automated CI or batch process (e.g. `process:secops-sdk-v1`, `process:nightly-patrol`).
- `<producer>/<version>`: Produced by an agent model (e.g. `agent/gemini-2.5-pro`, `deacon/v2`).

### Trust Tiers (OKF v0.2 §5.3)
1. **`unverified`**: No `verified` block present.
2. **`machine-confirmed`**: Verified exclusively by non-human actors (`process:...` or `<agent>/<ver>`).
3. **`human-reviewed`**: Verified by at least one `human:<id>` actor.

---

## 3. Schemas & Templates

Use canonical templates in `knowledge/templates/`:
- `concept.template.md`
- `feature.template.md`
- `persona.template.md`
- `task.template.md`
- `computation.template.md`

### Attested Computation Schema
```yaml
---
id: computation.feed_timestamp_skew
type: Attested Computation
title: Feed Ingestion Timestamp Skew & Latency Audit
description: Sanctioned YARA-L 2 query calculating event-to-collected latency delta and clock skew counts.
tags: [secops, yaral, ingestion, timestamp, attested]
runtime: yaral_2
parameters:
  - name: lookback_days
    type: integer
    required: true
executor:
  resource: knowledge/tasks/ingestion_specialist/audit_feed_health.md
  receipt: [query_text, executed_time_range, result_rows]
attester:
  resource: knowledge/attesters/yaral_equality.py
generated: { by: timestamp-integrity-agent/gemini-2.5-pro, at: "2026-09-22T08:00:00Z" }
verified:
  - { by: human:secops-architect, at: "2026-09-22T09:00:00Z" }
status: stable
stale_after: "2027-01-01T00:00:00Z"
sources:
  - id: chronicle-udm-doc
    resource: https://cloud.google.com/chronicle/docs/unified-data-model/udm-overview
    title: Google SecOps Unified Data Model Overview
---

# Computation

```sql
rule feed_timestamp_skew { ... }
```
```

---

## 4. Authoring Workflow

Follow these steps whenever creating or refining knowledge entries:

1. **Copy from Template:**
   Select the appropriate template from `knowledge/templates/`.

2. **Verify Capability IDs against the SDK Registry:**
   Never guess or approximate capability names. Verify the registered capability ID:
   ```bash
   python -c "
   from engine.facade import SecOpsEngine
   from scripts.generate_capabilities_doc import _InertAdapter
   from engine.registry import WorkflowRegistry
   reg = SecOpsEngine(adapter=_InertAdapter(), custom_registry=WorkflowRegistry()).registry
   for c in reg.list_capabilities():
       if '<keyword>' in c.capability_id:
           print(c.capability_id, '->', c.mcp_tool_name)
   "
   ```

3. **Enforce Non-Negotiable Rules (`AGENTS.md`):**
   - **Zero Synthetic/Mock Data:** Do not invent sample payload structures or mock API responses. Only reference documented SecOps/GCP/BindPlane fields.
   - **Bounded Autonomy:** For query capabilities (`kind: query`), ensure the task notes required filters (`require_filter_for_unbounded_query`).

4. **Validate Cross-References, Schema, & OKF Conformance:**
   Run the automated knowledge validator:
   ```bash
   python scripts/validate_knowledge.py --verbose
   ```
   Ensure 0 errors and that all documents pass OKF v0.2 verification.

5. **Regenerate the Knowledge Graph Visualizer:**
   After adding or updating knowledge files, update the interactive visualization:
   ```bash
   python scripts/generate_knowledge_graph.py
   ```

6. **Run the Full Contract Test Suite:**
   ```bash
   python -m unittest tests/test_knowledge_contract.py tests/test_okf_attester.py
   ```
