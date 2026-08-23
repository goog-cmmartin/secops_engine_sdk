
## Dashboard Query Proto Validation (`dashboard_query_proto_demo.py`)

Demonstrates validation of YARA-L 2.0 dashboard queries against all 10 protocol buffer schemas from the [secops_protos](https://github.com/GoogleCloudPlatform/secops_protos) repository.

```bash
# Validate a specific query
python3 examples/dashboard_query_proto_demo.py rules

# Validate all proto queries
python3 examples/dashboard_query_proto_demo.py all
```

**Coverage:**
- ✓ udm.proto (events)
- ✓ case.proto
- ✓ collections.proto (detections)
- ✓ gemini_investigation.proto
- ✓ ioc.proto
- ✓ rule.proto
- ✓ ruleset.proto
- ✗ case_history.proto (schema mismatch)
- ✗ ingestion.proto (schema mismatch)
- ✗ playbooks.proto (schema mismatch)

**Note:** Some proto field definitions may differ from actual backend implementation.

## Proto Schema Reference

All queries in this demo are validated against official proto schemas in `protos/secops_protos/`.

See [`docs/proto-schemas.md`](../docs/proto-schemas.md) for:
- Complete proto schema table
- UDM Search vs Dashboard Query capabilities
- Field reference and query syntax
