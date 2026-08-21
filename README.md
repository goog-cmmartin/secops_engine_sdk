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
* **Multi-Client Architecture:**
  * **CLI (`clients.cli.secops`)**: Rich terminal CLI with command-line formatting and provenance tracking.
  * **Native Desktop GUI (`clients.desktop`)**: Qt/PySide6 desktop UI with virtualized table models and async background workers.
  * **Universal Capability Registry (`engine.facade`)**: 60+ modular registered capabilities for AI agents and SDK consumers.

---

## 📁 Repository Structure

```
.
├── AGENTS.md                 # Mandatory operational & architectural invariants
├── README.md                 # Project overview and quickstart guide
├── .gitignore                # Git exclusion rules
└── secops-lean/              # Primary production engine & SDK
    ├── adapters/             # Google SecOps REST API transport layer
    ├── engine/               # Workflow runtime, domain models, and facade
    │   ├── domain.py         # Strongly-typed domain models & universal batch protocol
    │   ├── facade.py         # SecOpsEngine unified entrypoint
    │   ├── registry.py       # Capability registry & tool metadata
    │   └── workflows/        # Modular workflow implementations
    ├── clients/              # Multi-tier frontends (CLI, Desktop, Reference Web)
    │   ├── cli/              # Terminal CLI executable
    │   └── desktop/          # Qt / PySide6 Native Desktop application
    ├── specs/                # Declarative YAML workflow contracts
    ├── schemas/              # API & domain JSON schemas
    ├── benchmarks/           # Performance, memory & stress benchmarks
    ├── discovery/            # Observed network traces & live API notes
    └── tests/                # Automated live acceptance test suites
```

---

## 🛠️ Quickstart & Usage

### Prerequisites
* Python 3.10+
* Google Cloud credentials configured with Google SecOps access (`gcloud auth print-access-token` or application default credentials).

### Environment Setup
```bash
cd secops-lean
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### Running the CLI
```bash
# Set PYTHONPATH to include secops-lean
export PYTHONPATH=secops-lean

# Search UDM Events
python3 -m clients.cli.secops search "metadata.event_type = 'PROCESS_UNCATEGORIZED'" --limit 20

# Search SOAR Cases
python3 -m clients.cli.secops cases --limit 10

# Search Ingestion Connectors
python3 -m clients.cli.secops soar-ingestion-connectors

# Search Ingestion Webhooks
python3 -m clients.cli.secops soar-webhooks
```

---

## 🧪 Testing & Verification

Run the full automated live test suite:
```bash
PYTHONPATH=secops-lean python3 -m unittest discover secops-lean/tests -v
```

Run the anti-mock static audit:
```bash
python3 -c "
import os, sys
BANNED = ['mock', 'Mock', 'MOCK', 'fixture', 'Fixture', 'dummy', 'Dummy', 'fake', 'Fake', 'sampleData', 'sample_data', 'placeholderData', 'placeholder_data', 'testData', 'test_data']
DIRS = ['secops-lean/engine', 'secops-lean/adapters', 'secops-lean/clients']
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
* **Live Provenance:** All production data originates from live Google SecOps endpoints. Zero synthetic or dummy data permitted in production code paths.
* **Error Visibility:** API errors, authentication failures, and rate limits propagate explicitly without silent fallbacks.
* **Secrets Protection:** No API keys, passwords, or credentials are hardcoded or tracked in Git.
