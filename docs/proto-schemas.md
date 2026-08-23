# Protocol Buffer Schema Reference

This SDK includes the official SecOps Proto Schemas as a Git submodule in `protos/secops_protos/`.

## Available Schemas

The protos are located in `protos/secops_protos/protos/`:

| Proto File | Description | UDM Search | Dashboard Query |
|------------|-------------|:----------:|:---------------:|
| `udm.proto` | Unified Data Model events | ✅ (default) | ✅ |
| `case.proto` | SOAR case management | ✅ | ✅ |
| `collections.proto` | Detection/alert collections | ✅ (as `detection`) | ✅ |
| `graph.proto` | Graph entities (uses UDM proto) | ✅ | ✅ |
| `rule.proto` | Detection rules metadata | ❌ | ✅ |
| `ruleset.proto` | Managed rule sets | ❌ | ✅ |
| `ioc.proto` | Indicators of compromise | ❌ | ✅ |
| `gemini_investigation.proto` | AI investigation results | ❌ | ✅ |
| `playbook.proto` | SOAR playbook executions | ❌ | ✅ |
| `ingestion.proto` | Log ingestion statistics | ❌ | ✅ |
| `case_history.proto` | Case audit trail | ❌ | ✅ |

## Query Type Differences

### UDM Search (`udm_search`)

**Supported Tables:**
- `udm.*` (default, no prefix needed) - Security events
- `case.*` - SOAR cases
- `detection.*` - Alert collections (maps to `collections.proto`)
- `graph.*` - Entity relationships (uses `udm.proto` structure)

**Example:**
```python
# Default UDM query (no prefix needed)
engine.udm_search(
    query="metadata.event_type = 'USER_LOGIN'",
    start_time="2024-01-01T00:00:00Z",
    end_time="2024-01-02T00:00:00Z"
)

# Case query
engine.udm_search(
    query="case.status = 'OPEN'",
    start_time="2024-01-01T00:00:00Z",
    end_time="2024-01-02T00:00:00Z"
)
```

### Dashboard Query (`execute_dashboard_query`)

**Supported Tables:** All proto schemas (full Chronicle data model)

**Example:**
```python
# Rule metadata query
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

# IOC match query  
engine.execute_dashboard_query(
    raw_query="""
        SELECT ioc.value, ioc.category
        FROM ioc
        WHERE @event.ingest_time >= timestamp("2024-01-01T00:00:00Z")
    """
)
```

## Query Validation

See `examples/dashboard_query_proto_demo.py` for validated YARA-L 2.0 queries against each proto schema.

```bash
# Validate all proto queries
python3 examples/dashboard_query_proto_demo.py all

# Validate specific proto
python3 examples/dashboard_query_proto_demo.py rules
```

## Schema Updates

Update the submodule to get latest proto definitions:

```bash
# Update to latest
git submodule update --remote protos/secops_protos

# For fresh clones
git submodule update --init --recursive
```

## References

- **Proto Repository:** Your local `~/GitHub/secops_protos`
- **YARA-L 2.0 Syntax:** See Chronicle documentation
- **Dashboard Query Language:** Extended SQL-like syntax for Chronicle data model
