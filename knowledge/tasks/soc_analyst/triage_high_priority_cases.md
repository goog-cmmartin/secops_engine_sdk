---
id: task.soc_analyst.triage_high_priority_cases
title: Triage High-Priority Cases and Monitor Playbook Execution
type: task
persona: persona.soc_analyst
trigger:
- scheduled_daily
- incident_triggered
capabilities_used:
- case.search
- case.triage
- playbook.audit_health
related_concepts:
- concept.soar_case_lifecycle
related_features:
- feature.soar.case_management
- feature.soar.playbooks
evaluation_rules:
  sla_warning_time_minutes: 30
  max_failed_playbook_runs: 0
status: stable
description: Triage High-Priority Cases and Monitor Playbook Execution (task reference
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

# Triage High-Priority Cases and Monitor Playbook Execution

## 1. Intent & Context
Review open Critical and High severity cases in Chronicle SOAR, verify automated playbook execution success, and assess cases at risk of SLA breach.

## 2. Preconditions & Required Context
- Access to Chronicle SOAR API.

## 3. Step-by-Step Execution Procedure

### Step 1: Query Open High-Priority Cases
Invoke `case.search` with filter:
- Priority: `CRITICAL` or `HIGH`
- Status: `OPEN` or `IN_PROGRESS`

### Step 2: Execute Automated Triage Assessment
For unassigned cases, invoke `case.triage` to obtain triage verdicts, precedent case comparisons, and entity reputation summaries.

### Step 3: Audit Playbook Execution Health
Invoke `playbook.audit_health` to verify that enrichment and containment actions completed successfully without connector timeout.

## 4. Remediation & Escalation Runbook
- If a case SLA has < 30 minutes remaining, immediately escalate to the on-call incident commander.
- If playbook failed due to connector error, inspect connector credentials in `feature.soar.integrations`.
