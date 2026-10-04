---
id: task.soc_analyst.audit_soar_playbook_decay
title: Audit SOAR Playbook Inventory, Resilience Scoring & Decay
type: task
persona: persona.soc_analyst
trigger:
- scheduled_daily
- on_demand
capabilities_used:
- playbook.search
- playbook.get
- playbook.decay_audit
related_concepts:
- concept.soar_case_lifecycle
related_features:
- feature.soar.playbooks
evaluation_rules:
  min_resilience_score: 70
  max_failure_rate_pct: 20.0
status: stable
description: Audit SOAR Playbook Inventory, Resilience Scoring & Decay (task reference
  in Google SecOps).
generated:
  by: process:secops-sdk-v1
  at: '2026-09-20T00:00:00Z'
verified:
- by: human:secops-architect
  at: '2026-09-21T12:00:00Z'
stale_after: '2027-01-01T00:00:00Z'
sources:
- id: google-secops-docs
  resource: https://cloud.google.com/chronicle/docs
  title: Google SecOps Official Documentation
---

# Audit SOAR Playbook Inventory, Resilience Scoring & Decay

## 1. Intent & Context
Continuously audit Google SecOps SOAR playbooks and modular nested blocks for configuration hygiene, static topology resilience, and 30-day runtime failure rates. Identify silent containment failures, missing connector retries, and abandoned automation workflows.

## 2. Preconditions & Required Context
- Live Google SecOps SOAR instance and Chronicle dashboard telemetry access.
- Read/Write access to Firestore collection `soar_playbooks` in Evidence Fabric.

## 3. Step-by-Step Execution Procedure

### Step 1: Discover Active Playbooks and DAG Topologies
Invoke `playbook.search` and `playbook.get` to ingest active playbooks, step definitions, and transition edges.

### Step 2: Evaluate 100-Point Resilience Scoring Engine
Evaluate the 15 deterministic scoring rules:
- **HYG-01**: Production Hygiene (Active + Debug Mode)
- **ERR-01..04**: Action retries, enrichment hard-stops, silent containment failure, and single points of failure.
- **PRIO-01..03**: Shadowing risk, global interception, and master orchestrators.
- **MAINT-01..02**: Lifecycle decay and un-tuned playbooks.
- **HITL-01, HITL-OBS**: Human approval SLA timeouts and governance safeguards.

### Step 3: Correlate 30-Day Chronicle Telemetry
Query Chronicle `dashboardQueries:execute` over 30 days to compute total runs, failure rates, and execution durations.

### Step 4: Generate Mermaid.js DAG & Synthesize GenAI Architectural Narrative
Generate interactive Mermaid flowchart and invoke Gemini to produce the 4-part architectural executive brief:
1. Strategic Intent & Trigger Scope
2. Investigation & Data Pipeline
3. Decision Branches & Human-in-the-Loop Governance
4. Automated Containment & Case Resolution

### Step 5: Persist Audit Reports to Firestore
Persist audited playbooks with 1MB sanitization safeguard into collection `soar_playbooks` for multi-agent evidence sharing.

## 4. Remediation & Escalation Runbook
- If resilience score < 70 (Grade D or F) or failure rate > 20%, open remediation task in Evidence Fabric.
- For `HYG-01`, disable debug mode immediately on active playbooks.
- For `ERR-03`, disable auto-skip on critical containment actions and add faulted branch escalation.
