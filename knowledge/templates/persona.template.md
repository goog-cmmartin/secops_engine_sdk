---
id: persona.<persona_name>
type: persona
title: "<Persona Title>"
description: "<One-sentence summary of this operational agent persona>"
tags:
  - secops
  - persona
  - operations
status: stable  # valid: draft, stable, deprecated
generated: { by: "<actor>", at: "<iso8601>" }
verified:
  - { by: "human:<reviewer_id>", at: "<iso8601>" }
stale_after: "<iso8601>"
sources:
  - id: official-role-doc
    resource: "<url_or_path>"
    title: "<Role Specification Title>"
scope:
  - secops_siem
  - secops_soar
  - bindplane
  - gcp
authority_level: L2_OPERATIONS   # e.g., L1_TRIAGE, L2_OPERATIONS, L3_ARCHITECTURE, AUDITOR
primary_tasks:
  - task.<persona_name>.<task_name>
---

# <Persona Title>

## 1. Role Mandate & Core Objective
<!-- Who is this persona, what is their primary operational objective, and what is out of scope? -->

## 2. Operational Cadence
<!-- What does this persona check daily, weekly, or upon incident triggers? -->

## 3. Safety Guardrails & Autonomy Boundaries
<!-- Invariants, read-only vs mutation rules, approval escalation gates. -->

## 4. Key Metrics Owned
<!-- What metrics (latency, error rate, SLA compliance, coverage) does this persona monitor? -->
