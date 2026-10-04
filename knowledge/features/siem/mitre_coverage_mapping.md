---
id: feature.siem.mitre_coverage_mapping
title: MITRE ATT&CK Strategic Coverage Mapping & Gap Analysis
type: feature
platform: secops_siem
sdk_capabilities:
- mitre.sync_cache
- mitre.analyze_coverage
- mitre.get_technique_rules
- mitre.list_threat_profiles
- mitre.generate_report
mcp_tools:
- sync_mitre_rules_cache
- analyze_mitre_coverage
- get_technique_rules
- list_mitre_threat_profiles
- generate_mitre_report
status: stable
description: Strategic mapping of customer detection rules and telemetry against MITRE ATT&CK Enterprise Matrix (v18.1) across threat profiles.
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

# MITRE ATT&CK Strategic Coverage Mapping & Gap Analysis

## 1. Feature Purpose & Scope
Provides continuous alignment between Google SecOps detection content (custom YARA-L rules and Google Curated Rule Sets), live ingestion telemetry, and the MITRE ATT&CK Enterprise Matrix (v18.1). Evaluates security posture against industry-specific threat profiles (global baseline, financial services, cloud native, ransomware defense) and computes Contextual Coverage Scores.

## 2. Capabilities & SDK Workflows

### `mitre.sync_cache`
- **Description:** Synchronizes customer and curated Google SecOps detection rules into Firestore cache with parsed MITRE technique IDs and tactics.
- **Kind:** `primitive` | **Cardinality:** `None`
- **Tool:** `sync_mitre_rules_cache`

### `mitre.analyze_coverage`
- **Description:** Evaluates cached detection rules and live ingestion telemetry against MITRE ATT&CK matrix and threat profiles to determine coverage score and gaps.
- **Kind:** `workflow` | **Cardinality:** `None`
- **Tool:** `analyze_mitre_coverage`

### `mitre.get_technique_rules`
- **Description:** Retrieves all custom and curated detection rules mapped to a specific MITRE ATT&CK technique ID.
- **Kind:** `query` | **Cardinality:** `bounded`
- **Tool:** `get_technique_rules`

### `mitre.list_threat_profiles`
- **Description:** Lists available threat profiles with baseline technique counts and high-risk weight mappings.
- **Kind:** `query` | **Cardinality:** `bounded`
- **Tool:** `list_mitre_threat_profiles`

### `mitre.generate_report`
- **Description:** Generates an executive Markdown report and tactical gap analysis for MITRE ATT&CK posture.
- **Kind:** `workflow` | **Cardinality:** `None`
- **Tool:** `generate_mitre_report`

## 3. Operational Guarantees
- Rules are parsed using regex validation against active MITRE ATT&CK techniques (`T\d{4}(?:\.\d{3})?`).
- Log source telemetry is cross-referenced with tactical visibility domains (EDR, IDENTITY, CLOUD, NETWORK) to distinguish visibility gaps from detection gaps.
- Resilience bonuses incentivize defense-in-depth by rewarding multiple independent detection rules per technique.
