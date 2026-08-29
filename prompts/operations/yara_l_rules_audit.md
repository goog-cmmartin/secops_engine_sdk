# Prompt: Chronicle SIEM YARA-L Detection Rules Health, Deployment & Error Audit

## Role & Purpose
Act as a Principal Detection Engineer and SOC Architect. Perform a comprehensive audit and health assessment of all custom YARA-L 2.0 detection rules across the Google Chronicle SIEM tenant. The goal is to inventory all rules, inspect their authoring and revision history, evaluate deployment and alerting configurations, and cross-correlate each rule against runtime execution errors to identify malfunctioning or silently failing detections.

---

## Prompt Template

```text
Please generate a comprehensive audit and health assessment report for all custom YARA-L detection rules across our Google Chronicle SIEM tenant.

For each detection rule, retrieve and cross-correlate the following dimensions:

1. Rule Identity & Metadata:
   - Rule ID (e.g., ru_...) and Display Name
   - Author / Creator (from YARA-L meta section)
   - Severity level (LOW, MEDIUM, HIGH, CRITICAL)
   - Rule Type (SINGLE_EVENT vs MULTI_EVENT)
   - Compilation State (SUCCEEDED vs FAILED)

2. Versioning & Timestamps:
   - Created Date/Timestamp (UTC)
   - Last Modified / Revision Timestamp (UTC)
   - Current Revision ID

3. Deployment & Alerting Status:
   - Enabled Status (Enabled vs Disabled)
   - Alerting Status (Alerting Enabled vs Alerting Disabled)
   - Run Frequency (LIVE, HOURLY, DAILY, etc.)
   - Execution State (DEFAULT, PAUSED, etc.)

4. Runtime Error Cross-Correlation:
   - Query rule execution errors (ruleExecutionErrors) and cross-reference each rule ID.
   - Flag any rule that has encountered runtime execution errors, evaluation timeouts, syntax mismatches, or schema lookup failures.
   - For failing rules, include the Error Code, Error Message, and Most Recent Error Timestamp.

5. Health Summary & Executive Recommendations:
   - Total Rules Count breakdown (Total, Active/Enabled, Alerting, Disabled).
   - Summary of Rules in Error State (rules generating execution errors or compilation failures).
   - Actionable recommendations for remediation (e.g., fixing deprecated UDM fields, adjusting aggregation windows, or re-enabling stale detections).

Please format the results as a clean Markdown table with status badges (e.g., [ENABLED], [DISABLED], [ALERTING], [ERROR], [HEALTHY]) followed by a detailed diagnostic section for any erroring rules.
```

---

## Programmatic Execution

### Using SecOps Python SDK:
```python
from engine.facade import SecOpsEngine

engine = SecOpsEngine()

# 1. Fetch rules and execution errors
rules_res = engine.list_rules(page_size=100, view="FULL")
errors_res = engine.list_rule_errors(page_size=100)

# 2. Index runtime errors by rule ID
errors_by_rule = {}
for err in errors_res.errors:
    errors_by_rule.setdefault(err.rule_id, []).append(err)

# 3. Cross-correlate with deployments
for rule in rules_res.rules:
    dep = engine.get_rule_deployment(rule.rule_id)
    rule_errors = errors_by_rule.get(rule.rule_id, [])
    has_errors = len(rule_errors) > 0

    print(f"Rule: {rule.display_name} ({rule.rule_id})")
    print(f"  Author: {rule.author} | Severity: {rule.severity} | Type: {rule.rule_type}")
    print(f"  Created: {rule.create_time} | Modified: {rule.revision_create_time}")
    print(f"  Enabled: {dep.enabled} | Alerting: {dep.alerting} | Frequency: {dep.run_frequency}")
    print(f"  Health: {'[ERROR]' if has_errors else '[HEALTHY]'} ({len(rule_errors)} errors)")
```

### Using SecOps CLI:
```bash
# List all rules
secops rule list --view FULL

# Inspect runtime errors
secops rule errors

# Inspect specific rule deployment
secops rule deployment <RULE_ID>
```
