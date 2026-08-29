# Prompt: Chronicle SIEM Data Table Schema & Inventory Audit

## Role & Purpose
Act as a Senior SecOps Engineer and Detection Architect. Audit all Google Chronicle SIEM Data Tables deployed across the enterprise tenant to provide a full inventory of table identities, schemas, row lifecycle TTLs, governance access scopes, and detection rule associations.

---

## Prompt Template

```text
Please list and audit all Google Chronicle SIEM Data Tables in our environment.

For each data table discovered, retrieve and compile the following details:
1. Table Identity:
   - Table ID and Display Name
   - Description / Business Purpose
   - Resource Path / UUID
2. Schema & Field Definitions:
   - All defined columns and their data types (STRING, REGEX, CIDR, NUMBER, TIMESTAMP, etc.)
   - Identify which columns serve as the primary key ([KEY])
   - Note if any columns accept repeated values ([REPEATED])
3. Governance & Lifecycle:
   - Creation Date/Timestamp and Last Modified/Updated Date/Timestamp
   - Row Time to Live (TTL) / Expiration Policy (or note if persistent)
   - Scope / Ownership Information (RBAC Data Access Scope or tenant default)
4. Telemetry & Rule Association:
   - Approximate row count
   - Associated YARA-L detection rules (if linked)

Please format your output as a clean, structured Markdown table or categorized inventory report. At the end, provide a brief analytical summary highlighting tables with expiring TTLs and tables with zero rule associations.
```

---

## Programmatic Equivalent

### SDK / Runbook:
```python
from runbooks.operations.data_table_inventory import generate_data_table_inventory_report

report = generate_data_table_inventory_report()
print(f"Total tables: {report['total_tables']}")
```

### CLI:
```bash
secops runbook run data-table-inventory [--out dt_inventory.json]
```
