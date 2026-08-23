# SecOps Engine SDK - Examples

This directory contains practical, real-world examples demonstrating how to use the SecOps Engine SDK for security operations automation.

## Prerequisites

All examples require:
- A properly configured `.env` file in the repository root with Google SecOps credentials
- The SecOps Engine SDK installed or the repository root in PYTHONPATH

```bash
export PYTHONPATH=/path/to/secops_engine_sdk:$PYTHONPATH
```

## Examples

### 1. Automated Case Triage (`demo_case_triage.py`)

**Purpose:** Demonstrates automated case triage by analyzing a case, its alerts, and associated entities, then generating a comprehensive triage report.

**What it does:**
1. Searches for and selects the most recent case
2. Retrieves all alerts associated with the case
3. Analyzes entities from each alert (types, suspicious flags, internal/external)
4. Generates a detailed triage report with recommendations
5. Adds an automated triage comment to the case for analyst review

**Usage:**
```bash
python examples/demo_case_triage.py
```

**Key Capabilities Demonstrated:**
- Case search and filtering
- Alert enumeration
- Entity analysis (types, suspicious flags, internal designation)
- Automated risk assessment
- Case comment creation

**Sample Output:**
```
CASE: Moved Alert (ID: 19246)
  Priority: CasePriority.CRITICAL
  Stage: Investigation
  Closed: Yes
  Environment: Demoverse
  Assigned To: @Tier1
  
ALERTS (1 total):
  1. ATI HIGH FIDELITY: EXEC TO OBJECTIVE
     Rule: ATI High Fidelity: Exec To Objective
     Status: CLOSE, Priority: CRITICAL
     Entities: 30
     
ENTITY ANALYSIS:
  Total: 30
  Types: FILEHASH, FILENAME, HOSTNAME, PROCESS, THREATSIGNATURE, USERUNIQNAME
  Suspicious: 0
  Internal: 28
  
TRIAGE RECOMMENDATIONS:
  🚨 HIGH PRIORITY - Immediate attention required
  • Escalate to senior analyst
  • Consider activating incident response playbook
```

### 2. Batch UDM Export (`export_batch_udm.py`)

**Purpose:** Demonstrates how to efficiently export large volumes of UDM events from Chronicle with proper batching and error handling.

**What it does:**
1. Executes a UDM query with time-based filtering
2. Implements pagination to retrieve events in manageable batches
3. Exports results to JSONL format for downstream analysis
4. Provides progress tracking and error handling

**Usage:**
```bash
python examples/export_batch_udm.py
```

**Key Capabilities Demonstrated:**
- UDM query construction and execution
- Batch pagination for large result sets
- Progress tracking and status reporting
- File I/O and JSONL serialization
- Error handling and resilience

**Sample Output:**
```
Starting UDM export...
Query: metadata.event_type = "PROCESS_LAUNCH"
Time Range: 2025-10-01 to 2025-10-02
Batch Size: 1000

Batch 1: Retrieved 1000 events
Batch 2: Retrieved 1000 events
Batch 3: Retrieved 847 events

Export complete!
Total events: 2847
Output file: udm_export_20251001_20251002.jsonl
```

### 3. Threat Hunting Query Reference (`demo_threat_hunting.py`)

**Purpose:** Provides a comprehensive catalog of threat hunting queries and SDK usage patterns for UDM search operations.

**What it includes:**
1. **Query Catalog:** 8 pre-built threat hunting queries covering common attack patterns
   - Lateral Movement via Remote Execution
   - Credential Dumping Tools
   - Suspicious PowerShell Execution
   - Unusual Network Connections
   - Scheduled Task Creation
   - Registry Persistence
   - Suspicious Service Creation
   - Data Exfiltration via Archive

2. **SDK Usage Examples:** Code patterns for UDM search operations
   - Basic UDM search initiation and result retrieval
   - Event data extraction and analysis
   - Creating cases from hunt findings

3. **Best Practices:** Guidance on effective threat hunting
   - Time-boxing and scope management
   - Baseline vs. anomaly detection
   - Documentation and automation

**Usage:**
```bash
python examples/demo_threat_hunting.py
```

**Sample Output:**
```
1. Lateral Movement via Remote Execution
   Severity: HIGH
   MITRE ATT&CK: T1570 - Lateral Tool Transfer, T1021 - Remote Services
   Description: Detects use of remote execution tools like PSExec, WinRM, or WMIC
   
   UDM Query:
   metadata.event_type = "PROCESS_LAUNCH" AND
   (
     target.process.file.full_path = /.*psexec.*/i OR
     target.process.file.full_path = /.*winrm.*/i OR
     ...
   )
```

**Note:** This is a reference guide showing query patterns. For working UDM search execution examples, see the SDK usage section in the script output.

## Building Your Own Examples

When creating new examples, follow these patterns:

### 1. Standard Initialization

```python
from engine import SecOpsEngine

engine = SecOpsEngine()  # Loads config from .env automatically
```

### 2. Error Handling

```python
try:
    result = engine.search_cases(query="priority:CRITICAL")
    cases = result.results
except Exception as e:
    print(f"❌ Error: {e}")
    return
```

### 3. Pagination

```python
page_number = 0
all_results = []

while True:
    batch = engine.search_cases(
        query="",
        page_size=100,
        page_number=page_number
    )
    all_results.extend(batch.results)
    
    if not batch.has_next_page:
        break
    page_number += 1
```

### 4. Working with Entities

```python
# List entities for an alert
entities = engine.adapter.list_alert_entities(alert_name=alert['name'])

# Analyze entity properties
for entity in entities:
    entity_type = entity.get('type')
    identifier = entity.get('identifier')
    is_suspicious = entity.get('suspicious', False)
    is_internal = entity.get('internal', False)
```

### 5. Adding Case Comments

```python
comment_text = "Automated analysis complete. No suspicious activity detected."
result = engine.add_case_comment(case_id="12345", comment=comment_text)
print(f"Comment ID: {result.id}")
```

### 6. UDM Search

```python
from datetime import datetime, timedelta, timezone

# Define time range
end_time = datetime.now(timezone.utc)
start_time = end_time - timedelta(days=7)

# Start search (returns operation_id)
operation_id = engine.adapter.start_search(
    query='metadata.event_type = "PROCESS_LAUNCH"',
    start_time=start_time.isoformat(),
    end_time=end_time.isoformat(),
    max_events=1000
)

# Retrieve results in batches
start_index = 0
all_events = []

while True:
    result = engine.adapter.get_events(
        operation_id=operation_id,
        start_index=start_index,
        batch_size=500
    )
    
    batch_events = result.events if hasattr(result, 'events') else []
    if not batch_events:
        break
    
    all_events.extend(batch_events)
    start_index += len(batch_events)
    
    if not result.has_more or len(batch_events) < 500:
        break
```

## Common Use Cases

### Case Management
- Bulk case triage and categorization
- Automated case assignment based on criteria
- Case status synchronization with external systems
- Batch case closure with standardized comments

### Alert Analysis
- Alert correlation and grouping
- Entity enrichment from multiple sources
- False positive detection and filtering
- Alert-to-case escalation workflows

### Data Export
- UDM event batch export for data lake ingestion
- Case data export for reporting and analytics
- Alert history export for trend analysis
- Entity relationship mapping and visualization

### Investigation Automation
- Automated lateral movement detection
- Threat hunting query execution
- IOC sweep across historical data
- Attack timeline reconstruction

## Best Practices

1. **Always use pagination** for potentially large result sets
2. **Implement error handling** around all API calls
3. **Log progress** for long-running operations
4. **Use batch operations** when processing multiple items
5. **Add context** to automated case comments for analyst review
6. **Validate inputs** before making API calls
7. **Use resource names** (full paths) when working with alerts and entities
8. **Handle time zones properly** using timezone-aware datetime objects
9. **Test with small datasets** before scaling to production volumes
10. **Document your automation** for team knowledge sharing

## UDM Query Tips

- Use `metadata.event_type` to filter by event category
- Use regex patterns with `/pattern/i` for case-insensitive matching
- Combine conditions with `AND`, `OR`, and `NOT` operators
- Use `target.*` for destination/affected resources
- Use `principal.*` for source/initiating entities
- Reference Chronicle UDM field documentation for available fields

## Contributing Examples

When adding new examples:
1. Create a descriptive filename (e.g., `demo_alert_enrichment.py`)
2. Add a module-level docstring explaining the purpose
3. Include usage instructions in the docstring
4. Add error handling and progress indicators
5. Update this README with the new example
6. Test with real SecOps data before committing

## Support

For issues or questions:
- Check the main SDK documentation in the repository root
- Review the API adapter code in `adapters/google_secops.py`
- Examine domain models in `engine/domain.py`
- Consult the Google SecOps API documentation
- Review Chronicle UDM reference documentation

## License

These examples are provided as part of the SecOps Engine SDK project.
