---
id: task.detection_engineer.audit_mitre_coverage
title: Audit Strategic MITRE ATT&CK Threat Coverage & Deficiencies
type: task
persona: persona.detection_engineer
trigger:
- scheduled_weekly
- on_demand
- threat_profile_change
capabilities_used:
- mitre.sync_cache
- mitre.analyze_coverage
- mitre.generate_report
related_concepts:
- concept.detection_lifecycle
related_features:
- feature.siem.rules_engine
- feature.siem.curated_detections
- feature.siem.mitre_coverage_mapping
evaluation_rules:
  min_coverage_score: 65.0
  max_blind_tactics: 0
  max_critical_technique_gaps: 0
status: stable
description: Audit Strategic MITRE ATT&CK Threat Coverage & Deficiencies (task reference in Google SecOps).
generated:
  by: process:secops-sdk-v1
  at: '2026-09-25T16:00:00Z'
verified:
- by: human:secops-architect
  at: '2026-09-25T16:00:00Z'
stale_after: '2027-01-01T00:00:00Z'
sources:
- id: mitre-attack-enterprise
  resource: https://attack.mitre.org/
  title: MITRE ATT&CK Enterprise Matrix
- id: google-secops-docs
  resource: https://cloud.google.com/chronicle/docs
  title: Google SecOps Official Documentation
---

# Audit Strategic MITRE ATT&CK Threat Coverage & Deficiencies

## 1. Intent & Context
Continuously evaluate the tenant's detection engineering posture against the MITRE ATT&CK framework across selected industry threat profiles. Identify blind tactics, visibility gaps (telemetry missing), detection gaps (rules missing), and single points of failure (fragile detections covered by only 1 rule).

## 2. Preconditions & Required Context
- Google SecOps SIEM API credentials active.
- Evidence Fabric or Firestore cache initialized for persistent rule indexing.

## 3. Step-by-Step Execution Procedure

### Step 1: Synchronize Rule Metadata to Cache
Invoke `mitre.sync_cache`:
- Extracts technique codes (`Txxxx` and `Txxxx.xxx`) from custom and curated rule logic and descriptions.
- Commits indexed rules to persistent storage.

### Step 2: Analyze Coverage Across Threat Profile
Invoke `mitre.analyze_coverage`:
- Cross-references tenant ingested telemetry (7-day lookback) with visibility requirements.
- Calculates Contextual Coverage Score with risk weights (1 to 5) and resilience bonuses.
- Isolates critical technique gaps, blind tactics, and single points of failure.

### Step 3: Generate Posture Report
Invoke `mitre.generate_report`:
- Generates an executive Markdown artifact summarizing strategic coverage, tactical health, and immediate gap remediation steps.

### Step 4: Evaluate Against Quality Thresholds
- **Passing:** Contextual Coverage Score >= 65.0, 0 blind tactics, 0 critical technique gaps.
- **Warning:** Contextual Coverage Score between 50.0 and 64.9, or more than 10 fragile detections.
- **Critical:** Any blind tactic detected or critical profile-designated technique missing coverage.

## 4. Remediation & Escalation Runbook
- For **Visibility Gaps**: Engage `@tenant-cartographer` and Ingestion Specialist to enable required log sources (e.g. Cloud Audit, EDR, Auth).
- For **Detection Gaps**: Engage `@yaral-optimizer` to author and test YARA-L rules targeting the uncovered technique.
- For **Fragile Detections**: Author secondary corroborating rules to eliminate single points of failure.
