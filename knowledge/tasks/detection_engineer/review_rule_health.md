---
id: task.detection_engineer.review_rule_health
title: "Review Detection Rule Compilation, Execution Health, and Curated Drift"
type: task
persona: persona.detection_engineer
trigger:
  - scheduled_weekly
  - on_demand
capabilities_used:
  - rule.audit_health
  - rule.list
  - curated_detections.audit_health
related_concepts:
  - concept.detection_lifecycle
related_features:
  - feature.siem.rules_engine
  - feature.siem.curated_detections
evaluation_rules:
  max_execution_errors: 0
  min_curated_enabled_pct: 60.0
---

# Review Detection Rule Compilation, Execution Health, and Curated Drift

## 1. Intent & Context
Audit active YARA-L detection rules for execution timeouts, memory errors, zero-match anomalies, and review vendor-curated detection updates to ensure threat detection coverage remains high.

## 2. Preconditions & Required Context
- SecOps SIEM API credentials active.

## 3. Step-by-Step Execution Procedure

### Step 1: Audit Custom Rule Execution Health
Invoke `rule.audit_health`:
- Checks for compiler diagnostic errors, execution failure spikes, and latency drift.

### Step 2: Audit Curated Detections Health
Invoke `curated_detections.audit_health`:
- Reviews enablement rates across MITRE ATT&CK categories and flags newly retired or updated rule packs.

### Step 3: Evaluate Against Thresholds
- **Healthy:** 0 runtime execution errors, curated rule enablement >= 60%.
- **Warning:** Curated rule retirement delta > 5 rules, or rules approaching execution timeouts.
- **Critical:** Any production rule failing repeatedly with runtime errors.

## 4. Remediation & Escalation Runbook
- For runtime errors: Examine the rule YARA-L syntax via `rule.list` and tune match window conditions.
- For retired curated rules: Identify if customer custom rules need to be authored to replace retired logic.
