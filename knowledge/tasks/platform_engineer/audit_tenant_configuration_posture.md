---
id: task.platform_engineer.audit_tenant_configuration_posture
title: Audit Tenant Configuration Posture & Drift
type: task
persona: persona.platform_engineer
trigger:
- scheduled_daily
- on_demand
capabilities_used:
- siem.tenant.get
- siem.agent_settings.get
- siem.risk_config.get
- soar.company.get
- soar.data_retention.get
- soar.support_settings.get
- case_config.alert_grouping.settings.get
related_concepts:
- concept.workforce_identity_federation
- concept.ingestion_pipeline_topology
related_features:
- feature.siem.siem_settings
- feature.soar.soar_settings
evaluation_rules:
  critical_configuration_drift: 0
  unauthorized_support_access: false
status: stable
description: Audit Tenant Configuration Posture & Drift (task reference in Google
  SecOps).
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

# Audit Tenant Configuration Posture & Drift

## 1. Intent & Context
Continuously audit, baseline, and verify the configuration posture across Google SecOps SIEM and SOAR. Ensure that high-risk posture changes (e.g. reduction in data retention, unintended Google support delegation, disabling of Gemini autonomous triage, or alteration of alert grouping windows) are immediately identified as configuration drift and flagged for governance review.

## 2. Preconditions & Required Context
- Tenant initialized with active Chronicle SIEM and SOAR instance.
- Access to SecOpsEngine with valid credentials and Evidence Fabric store.

## 3. Step-by-Step Execution Procedure

### Step 1: Snapshot Current Tenant Baseline
Execute the comprehensive tenant posture audit:
- Query Root Instance details, state, and feature flags.
- Query Gemini AI Agent triage configuration and alert filter expressions.
- Query UEBA risk scoring parameters and coefficients.
- Query Data Processing Pipelines, managed domains, and RBAC scopes.
- Query SOAR global settings (data retention, company parameters, email transport, support delegation).
- Query SOC topography (SOC roles, environments, remote agents, networks, domains, custom lists).

### Step 2: Retrieve Historical Baseline
- Query Evidence Fabric (`tenant_baselines`) for the latest approved baseline or golden standard.

### Step 3: Compute Configuration Drift
- Compare current snapshot against the baseline using cryptographic subsystem fingerprinting and recursive diffing.
- Categorize changes by severity (`CRITICAL`, `HIGH`, `MEDIUM`, `LOW`).

### Step 4: Evaluate Against Governance Thresholds
- **Healthy:** 0 drift detected compared to golden standard; data retention and RBAC intact.
- **Warning:** Low or medium drift detected (e.g. display name update, new remote agent registered, or non-security email template update).
- **Critical:** Critical posture drift detected (e.g. data retention period reduced, Google support access delegation enabled, Gemini autonomous triage turned off, or alert grouping timeframe altered).

## 4. Remediation & Escalation Runbook
- For critical configuration drift, automatically generate an actionable task (`add_todo`) in the Evidence Fabric assigned to `@tenant-posture-agent`.
- Notify the Platform Engineer and SOC Manager with the parameter diff and prior timestamp.
