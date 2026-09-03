# Prompt: Google SecOps SOAR Playbook & Reusable Block Inventory Audit

## Role & Purpose
Act as a Lead SOAR Automation Engineer and SOC Platform Architect. Perform an exhaustive configuration and topology audit across all Google SecOps SOAR playbooks and modular sub-playbooks (blocks). The goal is to inventory all active and legacy automation workflows, determine their classification, verify enabled/disabled execution state, audit priority assignments, and map multi-tenant SOC environment boundaries.

---

## Prompt Template

```text
Please perform a complete configuration and topology audit of all SOAR Playbooks and Reusable Blocks across our Google SecOps tenant.

For each playbook/block discovered, compile and analyze the following key dimensions:

1. Workflow Identity & Classification:
   - Playbook / Block ID (e.g., 2277) and UUID Identifier
   - Display Name and Description
   - Workflow Type: Standard Playbook ([REGULAR]) vs Reusable Modular Block ([NESTED])
   - Category / Folder Assignment (e.g., GSA, Incident Response, Default, Blocks)

2. Operational & Execution Status:
   - Execution State: [ENABLED] vs [DISABLED]
   - Execution Priority: Priority Level (Priority 1 = Critical/High, Priority 2 = Medium/Default, Priority 3 = Low)
   - Debug Mode Status ([DEBUG_ACTIVE] vs Normal)

3. SOC Topography & Environment Mapping:
   - Mapped SOC Environments (e.g., 'Default Environment', 'Cymbal', 'SDL', 'GSA-Test', or '*' for all environments)
   - Environment Access Restrictions (hasRestrictedEnvironments)

4. Governance & Authoring Attribution:
   - Creator / Author Name
   - Creation Date/Timestamp (UTC)
   - Last Modification / Update Timestamp (UTC)

5. Executive Metrics & Summary:
   - Total Automation Workflows Breakdown:
     * Total Workflows, Standard Playbooks, and Reusable Blocks
     * Enabled vs Disabled ratio
     * Priority Distribution breakdown (P1, P2, P3)
     * Environment Mapping Distribution
   - Identify any orphan, disabled, or unmapped playbooks requiring SOC housekeeping.

Please format your response as a structured Markdown audit report with executive metrics, followed by categorized inventory tables with status badges ([ENABLED], [DISABLED], [P1], [P2], [P3]).
```

---

## Programmatic Execution

### Using SecOps Python SDK:
```python
from engine.facade import SecOpsEngine
from engine.domain import PlaybookType
from runbooks.operations.soar_playbook_inventory import (
    generate_playbook_inventory_report,
    print_playbook_inventory_console,
)

# Run complete inventory audit
report = generate_playbook_inventory_report()
print_playbook_inventory_console(report)
```

### Using SecOps CLI:
```bash
# Run full playbook & block inventory audit
secops runbook run playbook-inventory [--out playbook_audit.json]
secops playbook audit [--out playbook_audit.json]

# Audit only Standard Playbooks
secops playbook list --type REGULAR

# Audit only Reusable Modular Blocks
secops playbook list --type NESTED
```
