# Google SecOps AI Prompt Library & Playbook Templates

This directory serves as the centralized, version-controlled repository of production AI prompts designed for security operations, autonomous triage, threat hunting, and governance audits in Google SecOps.

---

## 1. Directory Structure

```
prompts/
├── README.md                           # Prompt catalog architecture and authoring guidelines
├── operations/
│   ├── data_table_inventory.md         # Data Table schema, lifecycle & metadata inventory
│   ├── tenant_settings_audit.md        # Comprehensive tenant governance & configuration audit
│   ├── yara_l_rules_audit.md           # Detection rules health, deployment & error audit
│   ├── soar_playbook_inventory.md      # SOAR playbooks & modular blocks configuration audit
│   ├── soar_playbook_health.md         # SOAR playbook health, telemetry & dashboard operational audit
│   └── curated_detections_health.md    # Curated detections deployment, hygiene & misconfiguration audit
├── incident_response/
│   ├── case_ai_triage.md               # 4-stage case triage, indicator extraction & escalation
│   └── alert_investigation_brief.md    # Single-alert forensic summary & next steps
├── threat_hunting/
│   ├── udm_ioc_hunt.md                 # Multi-indicator historical UDM telemetry hunt
│   └── entity_pivot_analysis.md        # Entity risk score & lateral movement pivot
└── remediation/
    └── ioc_containment_plan.md         # Reference list & perimeter firewall blocklist update
```

---

## 2. Parameter Interpolation Conventions

Prompts in this repository use mustache-style placeholders (`{{VARIABLE_NAME}}`) for programmatic and human execution:

| Parameter | Example Value | Description |
|:---|:---|:---|
| `{{CASE_ID}}` | `104655` | SOAR Case identifier |
| `{{ALERT_ID}}` | `392365` | SOAR Alert identifier |
| `{{LOOKBACK_DAYS}}` | `7` | Historical threat hunt window |
| `{{INDICATORS}}` | `104.168.160.6, evil.com` | Comma-separated indicators of compromise |
| `{{TABLE_NAME}}` | `monitored_users` | Chronicle SIEM Data Table ID |
| `{{OUTPUT_FORMAT}}` | `markdown_table` | Desired report format (`json`, `markdown_table`, `summary`) |

---

## 3. Authoring Best Practices for SecOps Prompts

1. **Explicit Output Schema**: Always specify exact field names and required structural sections (e.g. Identity, Schema, Lifecycle, Scope).
2. **Evidence-Based Answers**: Require the model to link findings directly to raw event IDs, UDM queries, or case indicators without hallucinated facts.
3. **Execution Safety**: Distinguish clearly between analytical read-only prompts and destructive mutation actions (case closing, alert escalation, rule creation).
