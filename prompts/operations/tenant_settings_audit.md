# Prompt: Tenant Configuration, Governance & SOC Topography Audit

## Role & Purpose
Act as a Principal SecOps Infrastructure and Governance Auditor. Perform a complete inspection of all Google SecOps tenant configurations, AI settings, UEBA baselines, RBAC scopes, SOAR global parameters, and SOC topography.

---

## Prompt Template

```text
Please generate a complete security configuration and governance audit of our Google SecOps tenant.

Inspect and summarize the following areas:
1. Root Instance & Access:
   - Tenant Instance ID, Customer Code, and UI status
   - Data RBAC status and Gemini Triage Agent enablement
   - Active SecOps / Chronicle / SOAR API endpoints
2. Gemini AI & UEBA Risk Parameters:
   - Automated investigation enablement, alert filters, delay, and execution quotas
   - Risk scoring weights, threshold multipliers, and decay rates
3. Governance, Ingestion & RBAC:
   - Managed domain definitions
   - Active log processing pipelines
   - Configured RBAC data access scopes and security labels
4. SOAR Global Settings:
   - Company information and data retention periods
   - Custom outbound email and support escalation settings
   - Alert grouping rules and case naming templates
5. SOC Topography:
   - Configured SOC analyst roles and permissions
   - Environments and remote execution agent status
   - Defined CIDR networks, domains, and custom blocklists/whitelists

Present the findings organized by category with risk observations for unconfigured or disabled protections.
```

---

## Programmatic Equivalent

### SDK / Runbook:
```python
from runbooks.operations.tenant_settings_audit import generate_tenant_settings_report

report = generate_tenant_settings_report()
```

### CLI:
```bash
secops runbook run tenant-settings-audit [--out tenant_audit.json]
```
