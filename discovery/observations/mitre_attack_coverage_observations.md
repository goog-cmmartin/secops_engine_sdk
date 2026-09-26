# Discovery Observation: MITRE ATT&CK Strategic Mapping & Ingestion Telemetry Correlation

## 1. Executive Summary & Status
- **Classification Status:** `VERIFIED`
- **Capability IDs:**
  - `mitre.sync_cache` (`primitive`)
  - `mitre.analyze_coverage` (`workflow`, composed of `mitre.sync_cache`)
  - `mitre.get_technique_rules` (`query`, bounded)
  - `mitre.list_threat_profiles` (`query`, bounded)
  - `mitre.generate_report` (`workflow`, composed of `mitre.analyze_coverage`)
- **Agent Assigned:** `@mitre-attack-agent` (Agent #21)
- **Data Fabric Storage:** Firestore / Local Evidence Store (`rule_states`, `mitre_assessments`)

## 2. Live SecOps API Mappings

### 2.1 Customer YARA-L Rules Fetch
- **Endpoint:** `GET /v1alpha/projects/{project}/locations/{location}/instances/{instance}/rules`
- **Query Parameters:** `view=FULL` (retrieves full rule text including `meta:`, `events:`, `condition:` blocks).
- **Extraction Behavior:**
  - Regex pattern: `\bT\d{4}(?:\.\d{3})?\b` (case-insensitive, normalized to uppercase dot notation).
  - Searches `displayName`, `ruleText`, metadata dictionaries, and `tags`.
  - Technique codes validated against official active ATT&CK v18.1 Enterprise Matrix (691 techniques).

### 2.2 Curated Rule Set Deployments Fetch
- **Endpoint:** `GET /v1alpha/projects/{project}/locations/{location}/instances/{instance}/curatedRuleSetDeployments`
- **Query Parameters:** `pageSize=1000`
- **Extraction Behavior:**
  - Curated rule metadata includes ATT&CK technique IDs, categories, and severity rankings.

### 2.3 Live Ingestion Telemetry Profiling
- **Endpoint:** `POST /v1alpha/projects/{project}/locations/{location}/instances/{instance}:executeDashboardQuery`
- **Payload:**
  - Query ID: `825b61da-751f-45c6-b08e-ba7eea249c16` (native Google SecOps dashboard aggregation).
  - Time Range: Lookback window (e.g. 7 days).
- **Correlation Engine:**
  - Ingested log types (`log_type`) categorized into telemetry domains (`EDR`, `IDENTITY`, `CLOUD`, `NETWORK`).
  - Correlated against tactical visibility expectations to differentiate **Visibility Gaps** (telemetry missing) from **Detection Gaps** (rules missing).

## 3. Contextual Coverage Scoring & Resilience
- **Base Weight:** 1.0 per validated covered technique (or 3.0 to 5.0 for profile-designated high-risk techniques).
- **Resilience Bonus:** +0.5 per technique covered by $\ge 2$ independent detection rules.
- **Normalization:** Normalized against target threat profile baseline techniques (e.g. 200 for `global_baseline`, 120 for `financial_services`, 85 for `cloud_native`).
- **Score Formula:**
  $$\text{Coverage Score} = \min\left(100.0, \frac{\sum (\text{Techniques} \times \text{Risk Relevance}) + \text{Resilience Bonus}}{\text{Total Relevant Baseline}} \times 100\right)$$

## 4. Test & Verification Provenance
- Unit & Live Acceptance Suite: `tests/test_mitre_attack_workflow.py` (13 tests passing against live SecOps tenant).
- Contract & Taxonomy Suite: `tests/test_capability_contract.py`, `tests/test_taxonomy.py` (42 tests passing).
