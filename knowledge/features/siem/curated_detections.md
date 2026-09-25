---
id: feature.siem.curated_detections
title: Google Curated Detections & Rule Tuning
type: feature
platform: secops_siem
sdk_capabilities:
- curated_detections.search_rulesets
- curated_detections.get_ruleset
- curated_detections.get_rule
- curated_detections.metrics
- curated_detections.set_deployment
- curated_detections.audit_health
- curated_detections.refinements.list
- curated_detections.refinements.test
- curated_detections.refinements.create
- curated_detections.refinements.delete
- curated_detections.tuning.top_noisy_rules
- curated_detections.tuning.entity_cardinality
- curated_detections.tuning.case_history
- curated_detections.tuning.diagnose
mcp_tools:
- analyze_entity_cardinality
- audit_curated_detections_health
- create_findings_refinement
- cross_reference_rule_cases
- delete_findings_refinement
- find_top_noisy_rules
- get_curated_detection_metrics
- get_curated_rule
- get_curated_ruleset
- list_findings_refinements
- search_curated_rulesets
- set_curated_ruleset_deployment
- test_findings_refinement
- tune_detection
status: stable
description: Google Curated Detections & Rule Tuning (feature reference in Google
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

# Google Curated Detections & Rule Tuning

## 1. Feature Purpose & Scope
Provides programmatic operational access to Google Curated Detections & Rule Tuning within secops_siem.

## 2. Capabilities & SDK Workflows
### `curated_detections.search_rulesets`
- **Description:** Discovers and searches Google SecOps Curated Rule Sets with MITRE ATT&CK mappings and log sources.
- **Kind:** `query` | **Cardinality:** `unbounded`
- **MCP Tool:** `search_curated_rulesets`

### `curated_detections.get_ruleset`
- **Description:** Deep-inspects a Curated Rule Set, its broad/precise deployments, member rules, and detection telemetry.
- **Kind:** `query` | **Cardinality:** `single`
- **MCP Tool:** `get_curated_ruleset`

### `curated_detections.get_rule`
- **Description:** Retrieves an individual Curated Rule, its MITRE techniques, false positives, and raw YARA-L logic.
- **Kind:** `query` | **Cardinality:** `single`
- **MCP Tool:** `get_curated_rule`

### `curated_detections.metrics`
- **Description:** Aggregates detection firing counts and retrieves tenant-wide rule quotas and telemetry.
- **Kind:** `query` | **Cardinality:** `single`
- **MCP Tool:** `get_curated_detection_metrics`

### `curated_detections.set_deployment`
- **Description:** Updates enabled and alerting states for a Curated Rule Set precision deployment.
- **Kind:** `primitive` | **Cardinality:** `none`
- **MCP Tool:** `set_curated_ruleset_deployment`

### `curated_detections.audit_health`
- **Description:** Performs a comprehensive deployment posture audit, detects misconfigurations like broad alerting, identifies top firing rules, and ranks newest/oldest content.
- **Kind:** `workflow` | **Cardinality:** `none`
- **MCP Tool:** `audit_curated_detections_health`

### `curated_detections.refinements.list`
- **Description:** Lists active UDM findings refinements and detection exclusions across the tenant.
- **Kind:** `query` | **Cardinality:** `unbounded`
- **MCP Tool:** `list_findings_refinements`

### `curated_detections.refinements.test`
- **Description:** Simulates and dry-runs an exclusion query against historical detections to compute noise suppression ratio.
- **Kind:** `primitive` | **Cardinality:** `none`
- **MCP Tool:** `test_findings_refinement`

### `curated_detections.refinements.create`
- **Description:** Creates a new UDM findings refinement exclusion for curated rules or tenant-wide detections.
- **Kind:** `primitive` | **Cardinality:** `none`
- **MCP Tool:** `create_findings_refinement`

### `curated_detections.refinements.delete`
- **Description:** Removes an active UDM findings refinement exclusion.
- **Kind:** `primitive` | **Cardinality:** `none`
- **MCP Tool:** `delete_findings_refinement`

### `curated_detections.tuning.top_noisy_rules`
- **Description:** Aggregates and ranks top firing detection rules with alert state, volume, and Google vs Customer rule classification.
- **Kind:** `primitive` | **Cardinality:** `none`
- **MCP Tool:** `find_top_noisy_rules`

### `curated_detections.tuning.entity_cardinality`
- **Description:** Profiles multi-dimensional entity subfield distributions (IPs, hostnames, users, processes, DNS) for a detection rule.
- **Kind:** `primitive` | **Cardinality:** `none`
- **MCP Tool:** `analyze_entity_cardinality`

### `curated_detections.tuning.case_history`
- **Description:** Cross-references historical SOAR cases associated with a detection rule to extract analyst resolutions and root causes.
- **Kind:** `primitive` | **Cardinality:** `none`
- **MCP Tool:** `cross_reference_rule_cases`

### `curated_detections.tuning.diagnose`
- **Description:** End-to-end autonomous workflow that analyzes noisy rules, profiles cardinality, cross-references SOAR cases, formulates exclusions, and dry-run tests suppression.
- **Kind:** `workflow` | **Cardinality:** `none`
- **MCP Tool:** `tune_detection`

## 3. Operational Invariants & Constraints
- All queries returning unbounded collections require explicit filtering.
- Mutation capabilities must specify non-empty payloads and valid target IDs.

## 4. Telemetry & Observable Health Indicators
- Correlate changes against Native Dashboards and Health Hub.
