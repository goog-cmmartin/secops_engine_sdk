---
id: task.<persona_name>.<task_name>
type: task
title: "<Task Title>"
description: "<One-sentence summary of this executable runbook procedure>"
tags:
  - secops
  - runbook
  - task
status: stable  # valid: draft, stable, deprecated
generated: { by: "<actor>", at: "<iso8601>" }
verified:
  - { by: "human:<reviewer_id>", at: "<iso8601>" }
stale_after: "<iso8601>"
sources:
  - id: official-runbook-doc
    resource: "<url_or_path>"
    title: "<Procedure Specification Title>"
persona: persona.<persona_name>
trigger:
  - scheduled_weekly     # valid: scheduled_daily, scheduled_weekly, on_demand, incident_triggered
capabilities_used:
  - <capability_id>      # must match WorkflowCapability in engine/registry.py
related_concepts:
  - concept.<concept_name>
related_features:
  - feature.<platform>.<feature_name>
evaluation_rules:
  warning_threshold: "<condition>"
  critical_threshold: "<condition>"
---

# <Task Title>

## 1. Intent & Context
<!-- Why is this task run, and what question or problem does it resolve? -->

## 2. Preconditions & Required Context
<!-- What credentials, environment variables, or context must be established before running? -->

## 3. Step-by-Step Execution Procedure
<!-- Concrete, agent-executable steps citing exact SDK workflows, dashboard queries, or tool calls. -->

### Step 1: Query Telemetry
<!-- Tool call and arguments. -->

### Step 2: Evaluate Results
<!-- Quantitative checks against evaluation_rules. -->

## 4. Remediation & Escalation Runbook
<!-- Exactly what the agent should do if thresholds are breached. -->
