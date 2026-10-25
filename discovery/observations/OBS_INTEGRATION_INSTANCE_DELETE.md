# Discovery Observation: SOAR Integration Instance Lifecycle (Affected Items & Deletion)

- **Date:** 2026-10-23
- **Status:** `VERIFIED`
- **Component:** SOAR Integrations / Instances Lifecycle
- **Tenant:** `sdl-preview-americas` (`a556547c-1cff-43ef-a2e4-cf5b12a865df`)

## 1. Endpoints Observed

### A. Pre-flight Dependency Inspection (`fetchAffectedItems`)
- **HTTP Method:** `GET`
- **URI Path:** `/v1alpha/projects/{project_number}/locations/{location}/instances/{customer_id}/integrations/{integration_id}/integrationInstances/{instance_id}:fetchAffectedItems`
- **Query Params:** `key=<API_KEY>` (standard Google SecOps auth)
- **Observed Response Structure:**
  ```json
  {
    "playbooks": [
      {
        "displayName": "GCPATIRECORDSTEALERC2Response"
      },
      {
        "displayName": "Detection Coverage Agent"
      }
    ]
  }
  ```
  *(Note: If no playbooks or items depend on the instance, `{}` is returned).*

### B. Instance Deletion
- **HTTP Method:** `DELETE`
- **URI Path:** `/v1alpha/projects/{project_number}/locations/{location}/instances/{customer_id}/integrations/{integration_id}/integrationInstances/{instance_id}`
- **Query Params:** `key=<API_KEY>`
- **Observed Response:** `{}` (HTTP 200 on successful deletion)

## 2. Behavioral Invariants
1. Prior to deleting an instance, a pre-flight inspection via `:fetchAffectedItems` allows SOC engineers/automations to prevent breaking active playbooks.
2. In the SDK, `delete_integration_instance` accepts a `force: bool = False` safety parameter. If downstream playbooks exist and `force` is False, the operation halts with an explicit error detailing the dependent playbooks.
