# Protocol Buffer Schema Integration

## Overview

The SDK now includes the official **Google SecOps Proto Schemas** as a Git submodule, providing:

1. **Source of truth** for Chronicle data model structures
2. **Query validation** against production schemas
3. **Field discovery** for UDM, Case, Rule, IOC, and other entities
4. **Documentation** of UDM Search vs Dashboard Query capabilities

## Integration Architecture

### Submodule Configuration

```
secops_engine_sdk/
├── .gitmodules              # Submodule configuration
└── protos/
    └── secops_protos/       # Git submodule (relative path: ../secops_protos)
        └── protos/
            ├── udm.proto
            ├── case.proto
            ├── rule.proto
            ├── collections.proto
            ├── ioc.proto
            ├── gemini_investigation.proto
            ├── playbook.proto
            ├── ingestion.proto
            ├── case_history.proto
            ├── ruleset.proto
            └── chronicle_api.proto
```

**Key Design Decision:** Uses **relative path** (`../secops_protos`) to reference the local workspace clone, avoiding external dependencies during development.

### Module Structure

| Module | Purpose |
|--------|---------|
| `engine/query_capabilities.py` | Programmatic query capability validation |
| `scripts/verify_proto_schemas.py` | Automated proto file verification |
| `docs/proto-schemas.md` | Reference table of proto capabilities |
| `docs/viewing-proto-schemas.md` | Practical browsing and IDE integration guide |

## Query Type Capabilities

### UDM Search (`udm_search`)

**Supported Tables:**
```python
UDM_SEARCH_TABLES = {
    "udm",        # Default - Unified Data Model events
    "case",       # SOAR case management  
    "detection",  # Alert collections (maps to collections.proto)
    "graph",      # Entity relationships (uses udm.proto structure)
}
```

**Usage:**
```python
# Default UDM table (no prefix needed)
engine.udm_search(
    query="metadata.event_type = 'PROCESS_LAUNCH'",
    start_time="2024-01-01T00:00:00Z",
    end_time="2024-01-02T00:00:00Z"
)

# Case table
engine.udm_search(
    query="case.status = 'OPEN'",
    start_time="2024-01-01T00:00:00Z",
    end_time="2024-01-02T00:00:00Z"
)
```

### Dashboard Query (`execute_dashboard_query`)

**Supported Protos:**
```python
DASHBOARD_QUERY_PROTOS = {
    # Core data
    "udm",                   # Unified Data Model events
    "case",                  # SOAR case management
    "collections",           # Detection/alert collections
    
    # Detection & rules
    "rule",                  # Detection rules metadata
    "ruleset",               # Managed rule sets
    
    # Threat intelligence
    "ioc",                   # Indicators of compromise
    
    # AI & automation
    "gemini_investigation",  # AI investigation results
    "playbook",              # SOAR playbook executions
    
    # Operations
    "ingestion",             # Log ingestion statistics
    "case_history",          # Case audit trail
}
```

**Usage:**
```python
# Query rule metadata
engine.execute_dashboard_query(
    raw_query="""
        SELECT rule.rule_name, COUNT(*) as trigger_count
        FROM rule
        WHERE @event.ingest_time >= timestamp("2024-01-01T00:00:00Z")
        GROUP BY rule.rule_name
        ORDER BY trigger_count DESC
        LIMIT 10
    """
)

# Query IOC matches
engine.execute_dashboard_query(
    raw_query="""
        SELECT ioc.value, ioc.category, COUNT(*) as match_count
        FROM ioc
        WHERE @event.ingest_time >= timestamp("2024-01-01T00:00:00Z")
        GROUP BY ioc.value, ioc.category
    """
)
```

## Validation Workflow

### 1. Verify Schema Availability

```bash
$ python3 scripts/verify_proto_schemas.py

======================================================================
Proto Schema Verification
======================================================================

✓ Proto directory: protos/secops_protos/protos
✓ Found 12 proto files

======================================================================
UDM Search Capabilities
======================================================================
  ✓ case            → case.proto
  ✓ detection       → collections.proto
  ✓ graph           → udm.proto
  ✓ udm             → udm.proto

======================================================================
Dashboard Query Capabilities
======================================================================
  ✓ case                 → case.proto
  ✓ case_history         → case_history.proto
  ✓ collections          → collections.proto
  ✓ gemini_investigation → gemini_investigation.proto
  ✓ ingestion            → ingestion.proto
  ✓ ioc                  → ioc.proto
  ✓ playbook             → playbook.proto
  ✓ rule                 → rule.proto
  ✓ ruleset              → ruleset.proto
  ✓ udm                  → udm.proto

======================================================================
✓ SUCCESS: All proto schema mappings verified
```

### 2. Validate Dashboard Queries

```bash
# Validate all proto query examples
$ python3 examples/dashboard_query_proto_demo.py all

# Validate specific proto
$ python3 examples/dashboard_query_proto_demo.py rules
```

### 3. Programmatic Validation

```python
from engine.query_capabilities import (
    is_valid_udm_search_table,
    is_valid_dashboard_proto,
    get_proto_file,
    format_capability_help
)

# Check table validity
assert is_valid_udm_search_table("udm")
assert is_valid_udm_search_table("case")
assert not is_valid_udm_search_table("rule")  # Only in Dashboard Query

# Get proto file for table
proto_file = get_proto_file("detection", "udm_search")
# Returns: "collections.proto"

# Display help text
help_text = format_capability_help("dashboard_query")
print(help_text)
```

## Proto Field Discovery

### Browsing Schemas

```bash
# List all proto files
ls protos/secops_protos/protos/

# View specific proto
cat protos/secops_protos/protos/udm.proto

# Search for field names
grep -n "event_type" protos/secops_protos/protos/udm.proto

# View enum definitions
grep -A 10 "^enum " protos/secops_protos/protos/rule.proto
```

### Example: UDM Event Structure

```protobuf
message UDMEvent {
  Metadata metadata = 1;        // Event metadata (timestamp, type, etc.)
  Principal principal = 2;      // Source entity (user, process, host)
  Target target = 3;            // Destination entity
  Network network = 4;          // Network connection details
  File file = 5;                // File operations
  Registry registry = 6;        // Windows registry operations
  // ... additional fields
}
```

**Query examples:**
```python
# Event type filter
query="metadata.event_type = 'PROCESS_LAUNCH'"

# User filter
query="principal.user.userid = 'admin'"

# Network filter
query="network.http.method = 'POST'"
```

## Maintenance

### Updating Schemas

To get the latest proto definitions from the secops_protos repository:

```bash
# Update submodule to latest commit
git submodule update --remote protos/secops_protos

# Verify updated schemas
python3 scripts/verify_proto_schemas.py

# Commit the update
git add protos/secops_protos
git commit -m "chore: Update secops_protos submodule to latest"
```

### Fresh Clone Setup

When cloning the repository on a new machine:

```bash
# Clone with submodules
git clone --recurse-submodules <repo-url>

# OR initialize submodules after clone
git clone <repo-url>
git submodule update --init --recursive
```

### CI/CD Integration

Ensure CI pipelines initialize submodules:

```yaml
# GitHub Actions example
- name: Checkout with submodules
  uses: actions/checkout@v4
  with:
    submodules: recursive

# Manual initialization
- run: git submodule update --init --recursive
```

## Documentation References

| Document | Description |
|----------|-------------|
| [`docs/proto-schemas.md`](proto-schemas.md) | Complete proto reference table with query capabilities |
| [`docs/viewing-proto-schemas.md`](viewing-proto-schemas.md) | Practical guide for browsing and field discovery |
| [`examples/dashboard_query_proto_demo.py`](../examples/dashboard_query_proto_demo.py) | Validated query examples for each proto |
| [`engine/query_capabilities.py`](../engine/query_capabilities.py) | Programmatic validation API |

## Implementation Timeline

| Commit | Description |
|--------|-------------|
| `00a0d44` | Add secops_protos submodule with documentation |
| `e9f7155` | Add verification script and viewing guide |

## Design Decisions

### ✅ Advantages

1. **Single Source of Truth:** Proto schemas match production API exactly
2. **Local Development:** Submodule uses relative path, no external deps during dev
3. **Version Control:** Git tracks exact proto schema version per SDK commit
4. **Programmatic Access:** `query_capabilities.py` enables validation in code
5. **Documentation:** Human-readable references with working examples

### ⚠️ Considerations

1. **Submodule Workflow:** Developers must initialize submodules (`git submodule update --init`)
2. **Relative Path Assumption:** Assumes `secops_protos` repo is cloned as sibling directory
3. **Schema Updates:** Manual `git submodule update --remote` required to pull latest protos

### 🔮 Future Enhancements

- **Automated Proto Parsing:** Generate Python dataclasses from proto definitions
- **Field Autocomplete:** IDE integration for query field suggestions
- **Schema Validation:** Compile-time query validation against proto schemas
- **Proto Diff Reports:** Automated changelog when updating proto submodule
