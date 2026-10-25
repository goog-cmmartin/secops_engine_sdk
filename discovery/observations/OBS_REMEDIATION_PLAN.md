# Discovery Observation: Google SecOps Agentic Response / Remediation Plans

## Overview
- **Resource**: `remediationPlans` & `remediationActions`
- **Chronicle API Version**: `v1alpha`
- **Classification Status**: `VERIFIED`

## Endpoint Details
### 1. List Remediation Plans
- **Method**: `GET`
- **Path**: `/v1alpha/projects/{project_number}/locations/{location}/instances/{customer_id}/remediationPlans`
- **Query Parameters**:
  - `filter`: Filter expression (e.g. `caseId = 108188`)
  - `pageSize`: Number of items per page (e.g. `1000`)
  - `pageToken`: Pagination token
- **Response Shape**:
  ```json
  {
    "remediationPlans": [
      {
        "name": "projects/{project_number}/locations/{location}/instances/{customer_id}/remediationPlans/{plan_id}",
        "alertName": "string",
        "caseId": 108188,
        "alertId": "string",
        "siemAlertId": "string",
        "agentSessionId": "string",
        "state": "REMEDIATION_PLAN_STATE_SUGGESTED",
        "triggerType": "REMEDIATION_PLAN_TRIGGER_TYPE_AUTOMATIC",
        "statusDetails": "string",
        "agentClassifiedUseCase": "string",
        "planData": {
          "usage_metadata": {
            "total_token_count": 159911,
            "prompt_token_count": 151426,
            "candidates_token_count": 1123
          },
          "planning_summary": "string",
          "involved_entities": [
            {
              "entity_type": "Hostname",
              "entity_identifier": "RHEL-WEB01"
            }
          ]
        },
        "createTime": "2026-10-23T13:46:51.387Z",
        "updateTime": "2026-10-23T13:48:46.257Z"
      }
    ],
    "totalSize": 1
  }
  ```

### 2. Get Remediation Plan
- **Method**: `GET`
- **Path**: `/v1alpha/projects/{project_number}/locations/{location}/instances/{customer_id}/remediationPlans/{plan_id}`
- **Response**: The complete `RemediationPlan` resource with embedded `actions` list.

### 3. List Remediation Actions
- **Method**: `GET`
- **Path**: `/v1alpha/projects/{project_number}/locations/{location}/instances/{customer_id}/remediationPlans/{plan_id}/remediationActions`
- **Response Shape**:
  ```json
  {
    "remediationActions": [
      {
        "name": "projects/{project_number}/locations/{location}/instances/{customer_id}/remediationPlans/{plan_id}/remediationActions/{action_id}",
        "integrationId": "PaloAltoCortexXDR",
        "integrationInstance": "4c900ec5-2f08-458f-9353-d5a7c77bd80a",
        "displayName": "Isolate Endpoint",
        "type": "ACTION_ORIGIN_TYPE_EXISTING",
        "creator": "ACTION_INSTANCE_CREATOR_AI",
        "actionReasoning": "...",
        "parameters": { ... },
        "targetEntities": [ ... ],
        "additionalData": { ... },
        "metadata": { ... },
        "createTime": "...",
        "updateTime": "..."
      }
    ],
    "totalSize": 1
  }
  ```

### 4. Get Remediation Action
- **Method**: `GET`
- **Path**: `/v1alpha/projects/{project_number}/locations/{location}/instances/{customer_id}/remediationPlans/{plan_id}/remediationActions/{action_id}`
