# Discovery Observation: Marketplace Integration Install and Integration Instance Create / Update

- **Date:** 2026-11-17
- **Status:** `VERIFIED` (items marked `UNKNOWN` below were not observed)
- **Component:** SOAR Marketplace Response Integrations / Integration Instances
- **Tenant:** `<redacted-project-id>` (`<redacted-customer-uuid>`)
- **Capabilities:** `marketplace_integration.install`, `integration.instance.create`, `integration.instance.update`

## 1. Endpoints Observed

### A. Install a marketplace integration
- **HTTP Method:** `POST`
- **URI Path:** `/v1alpha/projects/{project_number}/locations/{location}/instances/{customer_id}/marketplaceIntegrations/{identifier}:install`
- **Request body sent:** `{"staging": false, "overrideMapping": false}`
- **Observed response:** `{"identifier": "GoogleCloudIAM", "version": "21"}`
- **State after the call:** the marketplace record reported `installed: true` and
  `installedVersion: 21.0`. The integration's actions were listable under
  `integrations/{identifier}/actions`. The integration had no instances.

Seven integrations were installed this way. Four calls returned within the adapter's default
35 second read timeout. Three raised a client-side read timeout, and each of those three
integrations was found installed when the marketplace record was read afterwards.

### B. Create an integration instance
- **HTTP Method:** `POST`
- **URI Path:** `/v1alpha/projects/{project_number}/locations/{location}/instances/{customer_id}/integrations/{integration_id}/integrationInstances`
- **Request body sent:** `{"environment": "<environment name>", "displayName": "<name>", "description": "<text>"}`
- **Observed response:** the new instance, including `name`, `identifier`, `environment`,
  `displayName`, `description`, `configured`, `systemDefault`, `integrationIdentifier`, and a
  `parameters` list. Each parameter carries `id`, `displayName`, `propertyName`, `type`
  (`STRING`, `PASSWORD`, `BOOLEAN` observed), `mandatory`, `description`, and `value`.
  Parameters with a default came back with that default as `value`.

For an integration with no mandatory parameters the new instance reported `configured: true`
with no credentials supplied.

### C. Update instance parameters
- **HTTP Method:** `PATCH`
- **URI Path:** `/v1alpha/projects/{project_number}/locations/{location}/instances/{customer_id}/integrations/{integration_id}/integrationInstances/{instance_id}`
- **Query Params:** `updateMask=parameters`
- **Request body sent:** `{"parameters": [ ...the full parameter list from the create response, with value edited... ]}`
- **Observed response:** the updated instance. After mandatory parameters were given values the
  instance reported `configured: true`.

## 2. Behavioral Invariants
1. Install is tenant-wide and creates no instance. An integration with no instance cannot be
   used by a playbook step.
2. The install call can outlive a 35 second client read timeout and still complete on the
   server. The adapter therefore sends it with an extended timeout and never retries it. A
   caller that sees a timeout should read the marketplace record before installing again.
3. An instance can exist for an integration that is not installed. Before one install, the
   instance list already returned a configured instance for an integration that was absent from
   the installed integration list. That instance was still present after the install.
4. The SDK update workflow reads the instance, merges values by parameter display name or
   property name, and writes the full list back with `updateMask=parameters`. It rejects an
   unknown parameter name before writing.
5. Results returned by the SDK carry parameter names, types, and whether a value is set. They
   never carry parameter values.

## 3. Not Observed
- `UNKNOWN`: behavior of the extended 300 second timeout. The value was chosen after the
  timeouts above and has not been exercised against a slow install.
- `UNKNOWN`: the `version`, `staging: true`, `overrideMapping: true`, and
  `restoreIntegrationSnapshot` install options. They are documented by the API reference and
  were not sent.
- `UNKNOWN`: sending `parameters` in the create request body.
- `UNKNOWN`: update masks other than `parameters`.
- `UNKNOWN`: whether an environment name that does not exist is rejected on create.
- `UNKNOWN`: whether `PASSWORD` parameter values are returned in clear text by the API. The
  observed values were not inspected.
