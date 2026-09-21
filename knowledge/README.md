# Google SecOps Knowledge Base

This directory contains the operational knowledge, mental models, platform capabilities, and administrative runbooks required for AI agents (and human operators) to administer Google SecOps (SIEM & SOAR), Google Cloud Platform (GCP), and BindPlane OP.

---

## Architecture: The 4-Layer Model

The knowledge base decouples foundational mental models from platform levers and operational roles:

```text
knowledge/
├── templates/                 # Reusable templates for creating new knowledge files
│   ├── concept.template.md
│   ├── feature.template.md
│   ├── persona.template.md
│   └── task.template.md
├── concepts/                  # Layer 1: Foundational mental models, schemas & topologies
├── features/                  # Layer 2: Platform levers, API capabilities & dashboards
│   ├── siem/                  # Google SecOps SIEM
│   ├── soar/                  # Google SecOps SOAR
│   ├── bindplane/             # BindPlane OP telemetry collector
│   └── gcp/                   # Google Cloud Platform dependencies (IAM, Logging, Pub/Sub)
├── personas/                  # Layer 3: Agent roles, scopes of authority & mandates
└── tasks/                     # Layer 4: Executable operational runbooks & procedures
    ├── platform_engineer/
    ├── detection_engineer/
    ├── ingestion_specialist/
    └── soc_analyst/
```

---

## 1. Layer Definitions

| Layer | Folder | Purpose | Key Metadata Fields |
| :--- | :--- | :--- | :--- |
| **1. Concepts** | `concepts/` | Foundational schemas, event taxonomies, latency topology, mental models. | `id`, `type: concept`, `applies_to`, `related_features` |
| **2. Features** | `features/` | System capabilities, API contracts, Looker/Native Dashboards, query limits. | `id`, `type: feature`, `platform`, `sdk_capabilities`, `mcp_tools` |
| **3. Personas** | `personas/` | Agent role definitions, operational mindsets, authority levels, metrics owned. | `id`, `type: persona`, `scope`, `authority_level`, `primary_tasks` |
| **4. Tasks** | `tasks/` | Step-by-step executable runbooks, evaluation thresholds, and remediation steps. | `id`, `type: task`, `persona`, `capabilities_used`, `evaluation_rules` |

---

## 2. Referential Integrity & Validation

Every document in this directory must have valid YAML frontmatter. The repository enforces consistency via an automated validator:

```bash
# Run standalone validator
python scripts/validate_knowledge.py

# Run via unit test suite
python -m unittest tests/test_knowledge_contract.py
```

### Validation Rules
1. **Schema Check:** Every file must have the required fields for its `type`.
2. **Capability Verification:** All `sdk_capabilities` and `capabilities_used` entries must correspond to registered capabilities in `engine/registry.py`.
3. **Graph Integrity:** Referenced concepts, features, personas, and tasks must exist and resolve without broken links.
4. **Anti-Mock Invariant:** Production knowledge files must not contain synthetic identifiers as required by `AGENTS.md`.
