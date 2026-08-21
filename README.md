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
  * **Universal Capability Registry (`engine.facade`)**: 100+ modular registered capabilities for direct Python SDK and AI agent integration.

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
│   ├── registry.py           # Capability registry & tool metadata
│   ├── schema.py             # Canonical UDM schemas & field mappings
│   └── workflows/            # Modular workflow implementations (60+ workflows)
├── clients/                  # Multi-tier frontends
│   ├── cli/                  # Terminal CLI executable (secops.py)
│   └── desktop/              # Qt / PySide6 Native Desktop application
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

# Configure tenant parameters
cp .env.example .env
# Edit .env with your GCP project ID and SecOps customer ID:
# GCP_PROJECT_ID=your-project-id
# SECOPS_CUSTOMER_ID=your-customer-uuid
# SECOPS_PROJECT_NUMBER=your-project-number
# SECOPS_REGION=us
```

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
