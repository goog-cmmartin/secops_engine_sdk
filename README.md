# Google SecOps Workflow Engine & SDK

A high-performance, verifiable Python SDK and Workflow Engine for **Google Security Operations (SIEM & SOAR)**, strictly modeled against live Google SecOps APIs with zero mock data.

---

## 🚀 Key Features & Capabilities

* **SIEM Core & Ingestion:**
  * Real-time async UDM search with streaming pagination, cancellation, and local refinement filters.
  * Deep event investigation, base64 raw log extraction, and dot-notation field flattening.
  * Ingestion Log Types, Feeds, Log Processing Pipelines, and Parser discovery.
* **Detection & Content Hub:**
  * Rule management, YARA-L compiler validation, detection queries, and live rule errors.
  * Curated Detections catalog (MITRE ATT&CK filtering, broad/precise deployment profiles, metric counts).
  * Content Packs & Marketplace Integrations (catalog search, installation state, update management).
* **SOAR & Case Workspace:**
  * Case search, deep composite workspace loading, alert grouping, dynamic parameters, tags, stages, and SLA tracking.
  * Playbook search, visual graph inspection, step parameters, and execution lifecycle.
  * Scheduled Ingestion Connectors & HTTPS Event Ingestion Webhooks with JSON schema mapping.
  * Multi-tenancy Environments, Remote Agent execution workers, and Email/Support settings.
* **Client Interfaces & Integration:**
  * **CLI (`clients.cli.secops`)**: Feature-complete terminal CLI with rich tabular formatting, streaming output, and provenance tracking.
  * **Native Desktop GUI (`clients.desktop`)**: Qt / PySide6 desktop application with virtualized table models, faceted search, and async background workers.
  * **TUI (`clients/tui/`, `run_tui.py`)**: Textual-based two-pane terminal UI for case triage with responsive threading, offline demo mode, and clean domain/presentation separation (proof-of-concept).
  * **Universal Capability Registry (`engine.facade`)**: 100+ modular registered capabilities for direct Python SDK and AI agent integration.
  * **Agent-Safe Metadata**: each capability is classified by `kind`, `domain`, and result-set `cardinality`; collection-returning (`unbounded`) queries carry a `require_filter_for_unbounded_query` policy so MCP tools and autonomous agents cannot enumerate an entire tenant unfiltered.

---

## 📁 Repository Structure

```
.
├── AGENTS.md                 # Mandatory operational & architectural invariants
├── README.md                 # Project overview and quickstart guide
├── requirements.txt          # Python dependencies
├── .env.example              # Environment variables template
├── .gitignore                # Git exclusion rules
├── adapters/                 # Google SecOps REST API transport layer
│   └── google_secops.py      # Authenticated HTTP adapter & endpoint definitions
├── engine/                   # Workflow runtime, domain models, config, and facade
│   ├── config.py             # Centralized tenant configuration loader
│   ├── domain.py             # Strongly-typed domain models & universal batch protocol
│   ├── facade.py             # SecOpsEngine unified entrypoint & lazy workflow loader
│   ├── parsing.py            # Centralized timestamp, status, and priority parsers
│   ├── registry.py           # Capability registry, taxonomy & agent-safety metadata
│   ├── taxonomy.py           # kind/domain/cardinality derivation & safety policy
│   ├── schema.py             # Canonical UDM schemas & field mappings
│   └── workflows/            # Modular workflow implementations (21 workflow modules)
├── clients/                  # Multi-tier frontends
│   ├── cli/                  # Terminal CLI executable (secops.py)
│   └── desktop/              # Qt / PySide6 Native Desktop application
├── tui/                      # Textual TUI proof-of-concept
│   ├── app.py                # Two-pane Textual App with background workers
│   ├── render.py             # Stateless Rich-based rendering (Tables, Panels)
│   ├── requirements-tui.txt  # TUI-only dependencies (textual, rich)
│   └── README.md             # TUI design, threading, and demo mode docs
├── runbooks/                 # Autonomous incident response, threat hunting & operational runbooks
│   ├── README.md             # Runbook catalog & execution guide
│   ├── incident_response/    # Automated triage and indicator scoping
│   └── operations/           # Tenant settings and data table inventory audits
├── prompts/                  # Version-controlled SecOps AI prompt library & templates
│   ├── README.md             # Prompt catalog architecture and interpolation conventions
│   ├── operations/           # Governance & inventory prompt templates
│   ├── incident_response/    # Triage and forensic prompt templates
│   └── threat_hunting/       # Retrospective UDM hunt templates
├── docs/                     # Documentation & specifications
│   ├── CAPABILITIES.md       # Full registered SDK capability reference
│   └── CLI_REFERENCE.md      # Exhaustive SecOps CLI commands and argument manual
├── specs/                    # Declarative YAML workflow contracts
├── schemas/                  # API & domain JSON schemas
├── benchmarks/               # Performance, memory & stress benchmarks
├── discovery/                # Observed network traces & live API notes
└── tests/                    # Automated live acceptance & unit test suites
```

---

## 🛠️ Quickstart & Usage

### 1. Prerequisites
* Python 3.10+
* Google Cloud CLI (`gcloud`) with credentials configured for your Google SecOps project:
  ```bash
  gcloud auth application-default login
  ```

### 2. Installation & Configuration
```bash
# Create and activate virtual environment
python3 -m venv .venv
source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# (Optional) Install TUI dependencies
pip install -r clients/tui/requirements-tui.txt

# Configure tenant parameters
cp .env.example .env
# Edit .env with your GCP project ID and SecOps customer ID:
# GCP_PROJECT_ID=your-project-id
# SECOPS_CUSTOMER_ID=your-customer-uuid
# SECOPS_PROJECT_NUMBER=your-project-number
# SECOPS_REGION=us
```

### Authentication

Token acquisition is centralized in `engine/auth.py` (`CredentialProvider`) and
resolves credentials via a prioritized chain, controllable with `SECOPS_AUTH_MODE`:

1. **Static override** — `SECOPS_AUTH_TOKEN` (or an injected token). No I/O or
   refresh; intended for CI and constrained runners.
2. **Library ADC** — `google-auth` Application Default Credentials, scoped to
   `cloud-platform` and auto-refreshed. The enterprise default.
3. **gcloud subprocess** — `gcloud auth application-default print-access-token`,
   used when `google-auth` is unavailable.

> Note: the fallback uses the **application-default** credential store, which
> carries the `cloud-platform` scope. The bare `gcloud auth print-access-token`
> command emits an unscoped user token that the SecOps API rejects with HTTP 401.

Set `SECOPS_AUTH_MODE` to `auto` (default), `adc`, `gcloud`, or `static` to pin a
specific strategy.

### 3. Python SDK Usage
```python
from engine import SecOpsEngine
from adapters.google_secops import GoogleSecOpsAdapter

# Automatically resolves configuration from .env or environment variables
engine = SecOpsEngine()

# Search UDM Events
result = engine.search_udm(
    query="metadata.event_type = 'PROCESS_UNCATEGORIZED'",
    page_size=20
)
for event in result:
    print(event.id, event.timestamp)

# Search SOAR Cases
cases = engine.search_cases(page_size=10)
for case in cases:
    print(case.id, case.title, case.priority)
```

### 4. Running the CLI
```bash
# Search UDM Events
python3 -m clients.cli.secops search "metadata.event_type = 'PROCESS_UNCATEGORIZED'" --limit 20

# Search SOAR Cases
python3 -m clients.cli.secops cases --limit 10

# Search Playbooks
python3 -m clients.cli.secops playbooks

# Search Ingestion Connectors & Webhooks
python3 -m clients.cli.secops soar-ingestion-connectors
python3 -m clients.cli.secops soar-webhooks
```

### 5. Running the Native Desktop GUI
```bash
python3 -m clients.desktop.app
```

### 6. Running the TUI (Terminal UI)
```bash
# Live mode (requires configured credentials):
python3 run_tui.py

# Offline demo mode (synthetic data, no API calls):
python3 run_tui.py --demo

# With initial search query:
python3 run_tui.py --query "Priority:HIGH"
```

See [`clients/tui/README.md`](clients/tui/README.md) for design notes, threading architecture, and extension patterns.

---

## 🧪 Testing & Verification

Run the full automated test suite:
```bash
python3 -m unittest discover tests -v
```

Run the anti-mock static audit:
```bash
python3 -c "
import os, sys
BANNED = ['mock', 'Mock', 'MOCK', 'fixture', 'Fixture', 'dummy', 'Dummy', 'fake', 'Fake', 'sampleData', 'sample_data', 'placeholderData', 'placeholder_data', 'testData', 'test_data']
DIRS = ['engine', 'adapters', 'clients']
for d in DIRS:
    for root, _, files in os.walk(d):
        for f in files:
            if f.endswith('.py'):
                p = os.path.join(root, f)
                with open(p, 'r', encoding='utf-8') as fh:
                    for idx, line in enumerate(fh, 1):
                        for b in BANNED:
                            if b in line:
                                print(f'VIOLATION: {p}:{idx}: {line.strip()}')
                                sys.exit(1)
print('PASS: Zero mock violations found.')
"
```

---

## 🔒 Security & Governance

This project adheres to the strict operational invariants defined in [AGENTS.md](AGENTS.md):
* **Live Provenance:** All production data originates from live Google SecOps endpoints. Zero synthetic, dummy, or fabricated data is permitted in production code paths.
* **Error Visibility:** API errors, authentication failures, and rate limits propagate explicitly without silent fallbacks.
* **Secrets Protection:** No API keys, passwords, or credentials are hardcoded or tracked in Git.

---

## 📋 Protocol Buffer Schemas

This SDK includes the official **Google SecOps Proto Schemas** as a Git submodule. These protos define the Chronicle data model and are used for query validation.

**Key Distinctions:**
- **UDM Search** supports: `udm`, `case`, `detection` (collections), `graph` tables
- **Dashboard Query** supports: All proto schemas (full Chronicle data model)

See [`docs/proto-schemas.md`](docs/proto-schemas.md) for:
- Complete proto reference table
- UDM Search vs Dashboard Query differences
- Query validation examples
- Schema update instructions

**Quickstart:**
```bash
# Initialize submodule (for fresh clones)
git submodule update --init --recursive

# Validate dashboard queries against proto schemas
python3 examples/dashboard_query_proto_demo.py all
```
