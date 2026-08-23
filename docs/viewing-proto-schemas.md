# Viewing Proto Schemas

The official Google SecOps proto schemas are available in `protos/secops_protos/protos/`.

## Quick Reference

```bash
# List all proto files
ls protos/secops_protos/protos/

# View a specific proto schema
cat protos/secops_protos/protos/udm.proto
cat protos/secops_protos/protos/rule.proto
cat protos/secops_protos/protos/case.proto
```

## Verify Schema Availability

Run the verification script to check all proto files are present:

```bash
python3 scripts/verify_proto_schemas.py
```

This validates:
- Proto directory is accessible
- All expected proto files exist
- UDM Search table → proto mappings
- Dashboard Query proto → file mappings

## Understanding Schema Structure

### UDM (Unified Data Model)

The core security event schema. Example fields:

```protobuf
message UDMEvent {
  Metadata metadata = 1;
  Principal principal = 2;
  Target target = 3;
  Network network = 4;
  // ... see protos/secops_protos/protos/udm.proto
}
```

**Query example:**
```python
# UDM Search (default table, no prefix)
engine.udm_search(
    query="metadata.event_type = 'PROCESS_LAUNCH'",
    start_time="2024-01-01T00:00:00Z",
    end_time="2024-01-02T00:00:00Z"
)
```

### Case (SOAR Case Management)

Case metadata and workflow state. Example fields:

```protobuf
message Case {
  string case_id = 1;
  string display_name = 2;
  Priority priority = 3;
  CaseStatus status = 4;
  // ... see protos/secops_protos/protos/case.proto
}
```

**Query example:**
```python
# UDM Search with case table
engine.udm_search(
    query="case.status = 'OPEN' AND case.priority = 'HIGH'",
    start_time="2024-01-01T00:00:00Z",
    end_time="2024-01-02T00:00:00Z"
)
```

### Rule (Detection Rules Metadata)

Detection rule configurations and metrics. Example fields:

```protobuf
message Rule {
  string rule_id = 1;
  string rule_name = 2;
  RuleType rule_type = 3;
  // ... see protos/secops_protos/protos/rule.proto
}
```

**Query example:**
```python
# Dashboard Query (requires explicit table selection)
engine.execute_dashboard_query(
    raw_query="""
        SELECT rule.rule_name, COUNT(*) as trigger_count
        FROM rule
        WHERE @event.ingest_time >= timestamp("2024-01-01T00:00:00Z")
        GROUP BY rule.rule_name
        ORDER BY trigger_count DESC
    """
)
```

## Proto Field Discovery

To explore available fields in a proto:

```bash
# Search for message definitions
grep "^message " protos/secops_protos/protos/udm.proto

# Search for specific field names
grep -n "event_type" protos/secops_protos/protos/udm.proto

# View enum definitions
grep -A 10 "^enum " protos/secops_protos/protos/rule.proto
```

## IDE Integration

For better proto browsing, configure your IDE:

**VS Code:**
- Install "vscode-proto3" extension
- Add `protos/secops_protos/protos/` to proto path

**IntelliJ/PyCharm:**
- Install "Protocol Buffers" plugin
- Mark `protos/secops_protos/protos/` as "Sources Root"

## Updating Schemas

To get the latest proto definitions:

```bash
# Update submodule to latest commit
git submodule update --remote protos/secops_protos

# Verify updated schemas
python3 scripts/verify_proto_schemas.py

# Commit the submodule update
git add protos/secops_protos
git commit -m "chore: Update secops_protos submodule to latest"
```

## See Also

- [`docs/proto-schemas.md`](proto-schemas.md) - Complete proto reference and capabilities table
- [`examples/dashboard_query_proto_demo.py`](../examples/dashboard_query_proto_demo.py) - Working query examples for each proto
- [`engine/query_capabilities.py`](../engine/query_capabilities.py) - Programmatic proto/table validation
