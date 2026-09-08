# Google SecOps Detection Tuning Live Observations & API Verification

## Discovery Date
2026-09-06

## Environment
- Project ID: `sdl-preview-americas` (Numeric: `37679061640`)
- Customer ID: `a556547c-1cff-43ef-a2e4-cf5b12a865df`
- Region: `us`

---

## 1. Top Noisy Rules Aggregation
- **Method**: Dashboard statistical query over `detection.*`
- **Query**:
```yara
$rule_name = detection.detection.rule_name
$rule_id = detection.detection.rule_id
$alerting = detection.detection.alert_state 
match: $rule_name, $rule_id, $alerting
outcome:
  $count = count(detection.id)
  $first_seen = min(detection.detection_time.seconds)
  $last_seen = max(detection.detection_time.seconds)
order: $count desc
```
- **Observed**: Returned 299 rows in 13.06s. Top noisy curated rule `ur_5f1035ac-b376-4d6b-ad72-5f6da5d51d02` ("GCP Multiple Audit Log Events From Same IP") produced 44,502 hits over 7 days.
- **Compiler Finding**: YARA-L 2 statistical queries reject repeated string outcome assignments (`if(re.regex(...))` fails). $\mathcal{O}(1)$ classification in Python (`ur_` vs `ru_`) is verified as the optimal deterministic approach.

---

## 2. Multi-Dimensional Entity Cardinality Profiling
- **Method**: Parametric dashboard subfield queries targeting `detection.collection_elements.references.event.*`
- **Observed**:
  - `principal.ip`: Top IP `213.209.159.175` with 22,359 detections (50.24% of all rule firings).
  - Query executed in 6.2s.

---

## 3. UDM Findings Refinements Endpoints
- **List/Get/Create/Delete**:
  - `GET /v1alpha/projects/{project_number}/locations/{location}/instances/{customer_id}/findingsRefinements`
  - Returned active exclusions, e.g. `fr_36603e5a-1748-43ee-b14e-4f275e01eb49` for `target.hostname = /byeserver.com/`.
- **Dry-Run Simulation**:
  - `POST /v1alpha/projects/{project_number}/locations/{location}/instances/{customer_id}/findingsRefinements:testFindingsRefinement`
  - Body structure:
    ```json
    {
      "detectionExclusionApplication": {
        "curatedRules": ["projects/.../curatedRules/ur_5f1035ac-b376-4d6b-ad72-5f6da5d51d02"],
        "type": "DETECTION_EXCLUSION",
        "query": "(principal.ip = /213.209.159.175/)",
        "interval": {
          "startTime": "2026-08-30T17:34:00Z",
          "endTime": "2026-09-06T17:34:00Z"
        }
      }
    }
    ```
  - **Live Output**: `totalDetectionCount: 44,502`, `excludedDetectionCount: 13,959` (31.37% verified noise reduction).

---

## 4. SOAR Historical Case Correlation
- **Query**:
```yara
$case_id = case.id
$display_name = case.display_name
$rule_id = case.alerts.alert.source_rule_id
$status = case.status
$close_reason = case.close_reason
$root_cause = case.root_cause
$rule_id = "ur_5f1035ac-b376-4d6b-ad72-5f6da5d51d02"
match: $case_id, $display_name, $rule_id, $status, $close_reason, $root_cause
outcome:
  $alert_count = count(case.alerts.alert.id)
order: $alert_count desc
```
- **Observed**: Retrieved closed/open cases in 9.2s. Closed cases showed analyst closure reasons like `MAINTENANCE` and root cause `Lab test`, providing direct evidence for tuning justification.
