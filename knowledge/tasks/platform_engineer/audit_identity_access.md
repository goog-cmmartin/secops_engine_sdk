---
id: task.platform_engineer.audit_identity_access
title: Audit Workforce Identity Federation and Admin Role Assignments
type: task
persona: persona.platform_engineer
trigger:
- scheduled_weekly
- on_demand
capabilities_used:
- data_rbac.environment.search
- data_rbac.scope.search
- identity.iam.bindings
related_concepts:
- concept.workforce_identity_federation
related_features:
- feature.gcp.workforce_identity
evaluation_rules:
  max_unassigned_scopes: 0
  unauthorized_role_drift: none
status: stable
description: Audit Workforce Identity Federation and Admin Role Assignments (task
  reference in Google SecOps).
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

# Audit Workforce Identity Federation and Admin Role Assignments

## 1. Intent & Context
Ensure that all administrative access granted through GCP Workforce Identity Pools adheres to least-privilege principles and that data access scopes properly restrict tenant compartment access.

## 2. Preconditions & Required Context
- Tenant initialized with Chronicle Admin credentials.

## 3. Step-by-Step Execution Procedure

### Step 1: Inspect Effective RBAC Context
Invoke `data_rbac.environment.search`:
- Retrieve active scopes, tenant-level data labels, and role mappings.

### Step 2: Query Data Access Scopes
Invoke `data_rbac.scope.search`:
- Verify that restricted data scopes (e.g. PCI-DSS, Executive telemetry) are properly bound to authorized groups.

### Step 3: Evaluate Against Thresholds
- **Healthy:** All admin principals belong to verified workforce pool groups; 0 unassigned data scopes.
- **Warning:** New workforce group added without documented change ticket.
- **Critical:** Discovered direct IAM role assignment bypassing the workforce pool.

## 4. Remediation & Escalation Runbook
- If unauthorized admin accounts are detected, escalate to the Identity Governance team and revoke session credentials.
