---
id: concept.soar_case_lifecycle
title: SOAR Case Lifecycle, Alert Grouping & Playbook Execution
type: concept
applies_to:
- secops_soar
related_features:
- feature.soar.case_management
- feature.soar.playbooks
tags:
- soar
- cases
- playbooks
status: stable
description: SOAR Case Lifecycle, Alert Grouping & Playbook Execution (concept reference
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

# SOAR Case Lifecycle, Alert Grouping & Playbook Execution

## 1. Overview & Mental Model
Chronicle SIEM detections and external security alerts flow into Chronicle SOAR as raw alerts. Alerts are grouped into **Cases** based on configurable grouping rules (e.g., shared entity, time window, rule category). 

## 2. Case Stages & Automation Flow
1. **Ingestion & Alert Grouping:** Alerts arrive via Chronicle Alerts Connector and are grouped into a Case.
2. **Automatic Triage & Playbook Trigger:** Associated playbooks trigger automatically upon case creation, enriching entities (VirusTotal, Active Directory, DNS).
3. **Analyst Investigation:** Analysts review the Case Wall, timeline, and automated recommendations.
4. **Resolution & Closure:** Case is closed with structured root-cause classification and closing reason definitions.

## 3. Operational Guarantees & SLA Compliance
- Cases carry priority-based SLA targets (Critical, High, Medium, Low).
- Playbook execution timeouts or connector credential failures stall automated triage, causing SLA breaches.
