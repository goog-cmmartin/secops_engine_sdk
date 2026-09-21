---
name: secops-knowledge-authoring
description: >-
  Author, update, and validate operational knowledge base entries across Google SecOps
  (SIEM & SOAR), GCP, and BindPlane OP. Use this skill when creating or refining concepts,
  features, personas, and executable tasks.
---

# SecOps Knowledge Authoring Guide

This skill guides AI agents and contributors in authoring, expanding, and maintaining the **Google SecOps Knowledge Base** located in `knowledge/`.

---

## 1. The 4-Layer Architecture

Every operational domain must be mapped across four decoupled layers:

1. **Concepts (`knowledge/concepts/`)**: Mental models, schemas, taxonomies, and operational guarantees.
   - Example: `concept.udm_search_lifecycle`, `concept.ingestion_pipeline_topology`
2. **Features (`knowledge/features/{platform}/`)**: Platform capabilities, APIs, Looker dashboard queries, and parameter limits.
   - Platforms: `secops_siem`, `secops_soar`, `bindplane`, `gcp`
   - Example: `feature.siem.native_dashboards`, `feature.siem.rules_engine`
3. **Personas (`knowledge/personas/`)**: Operational roles, scopes of authority, and cadences.
   - Example: `persona.platform_engineer`, `persona.detection_engineer`, `persona.ingestion_specialist`
4. **Tasks (`knowledge/tasks/{persona}/`)**: Executable runbooks tying Persona + Trigger + Features/Tools + Evaluation Rules + Remediation.
   - Example: `task.platform_engineer.check_udm_search_performance`

---

## 2. Standard YAML Frontmatter Schemas

Every `.md` file in `knowledge/` (except `README.md` and `templates/`) MUST begin with strict YAML frontmatter.

### Concept Schema
```yaml
---
id: concept.<concept_name>             # regex: ^concept\.[a-z0-9_]+$
title: "Human Readable Title"
type: concept
applies_to:
  - secops_siem                        # options: secops_siem, secops_soar, bindplane, gcp
related_features:
  - feature.siem.<feature_name>        # must exist in knowledge/features/
tags:
  - schema
  - latency
---
```

### Feature Schema
```yaml
---
id: feature.<platform>.<feature_name>  # regex: ^feature\.[a-z0-9_]+\.[a-z0-9_]+$
title: "Human Readable Title"
type: feature
platform: secops_siem                  # options: secops_siem, secops_soar, bindplane, gcp
sdk_capabilities:
  - dashboard.execute_query            # MUST exist in WorkflowRegistry (engine/registry.py)
mcp_tools:
  - execute_dashboard_query            # matching mcp_tool_name in WorkflowRegistry
related_concepts:
  - concept.<concept_name>             # must exist in knowledge/concepts/
---
```

### Persona Schema
```yaml
---
id: persona.<persona_name>             # regex: ^persona\.[a-z0-9_]+$
title: "Human Readable Role Title"
type: persona
scope:
  - secops_siem
  - secops_soar
authority_level: L2_OPERATIONS         # e.g., L1_TRIAGE, L2_OPERATIONS, L3_ARCHITECTURE, AUDITOR
primary_tasks:
  - task.<persona>.<task_name>         # must exist in knowledge/tasks/
---
```

### Task Schema
```yaml
---
id: task.<persona>.<task_name>         # regex: ^task\.[a-z0-9_]+\.[a-z0-9_]+$
title: "Human Readable Task Title"
type: task
persona: persona.<persona_name>        # must exist in knowledge/personas/
trigger:
  - scheduled_weekly                   # options: scheduled_daily, scheduled_weekly, on_demand, incident_triggered
capabilities_used:
  - dashboard.execute_query            # MUST exist in WorkflowRegistry
related_concepts:
  - concept.<concept_name>             # must exist in knowledge/concepts/
related_features:
  - feature.<platform>.<feature_name>  # must exist in knowledge/features/
evaluation_rules:
  warning_latency_ms: 15000
  critical_failure_pct: 5.0
---
```

---

## 3. Authoring Workflow

Follow these steps whenever creating or refining knowledge entries:

1. **Copy from Template:**
   Use the canonical templates in `knowledge/templates/`:
   - `concept.template.md`
   - `feature.template.md`
   - `persona.template.md`
   - `task.template.md`

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

4. **Validate Cross-References and Integrity:**
   Always run the validation script before finalizing:
   ```bash
   python scripts/validate_knowledge.py --verbose
   ```
   Ensure 0 errors and that your new files are counted in the summary.

5. **Run the Unit Test Suite:**
   ```bash
   python -m unittest tests/test_knowledge_contract.py
   ```
