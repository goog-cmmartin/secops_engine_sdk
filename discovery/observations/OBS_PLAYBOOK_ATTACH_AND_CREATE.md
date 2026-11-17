# Discovery Observation: Attaching a Playbook to an Alert, and Creating Playbooks through the API

- **Date:** 2026-11-17
- **Status:** `VERIFIED` (items marked `UNKNOWN` below were not observed)
- **Component:** SOAR Playbooks
- **Tenant:** `<redacted-project-id>` (`<redacted-customer-uuid>`)
- **Capabilities:** `playbook.attach` (new), `playbook.save` and `playbook.delete` (existing, notes only)

## 1. Attach a playbook to an alert

- **HTTP Method:** `POST`
- **URI Path:** `/v1alpha/projects/{project_number}/locations/{location}/instances/{customer_id}/legacyPlaybooks:legacyAttachWorkflowToCase`
- **Request body sent:**
  ```json
  {
    "cyberCaseId": "<numeric case id>",
    "alertGroupIdentifier": "<alert group identifier>",
    "alertIdentifier": "<alert identifier>",
    "wfName": "<playbook name>",
    "originalWorkflowDefinitionIdentifier": "<playbook uuid>",
    "shouldRunAutomatic": true
  }
  ```
- **Observed response:** `{"payload": true}`
- **State after the call:** the playbook appeared in `legacyGetWorkflowInstancesCards` for that
  alert next to the playbook that was already attached, and it started running.

Both identifiers come from the case alert record: `alertGroupIdentifier` and `identifier`.

Attaching a playbook whose stored definition could not be read back (see 2.2) returned
HTTP 500.

## 2. Creating playbooks with `legacySaveWorkflowDefinitions`

These notes describe the existing `playbook.save` capability. Its behavior was not changed.

1. **Names.** A playbook name containing a comma was rejected with HTTP 400,
   `Playbook name cannot contain special characters`. Names made of letters, digits, and spaces
   were accepted.
2. **A save can succeed and leave an unreadable playbook.** A payload assembled by hand saved
   with HTTP 200 and received an id, but `legacyGetWorkflowFullInfoWithEnvFilterByIdentifier`
   then returned HTTP 500 for it. It was still listed by the menu cards call and could be
   deleted. A caller should read a playbook back after creating it.
3. **What worked.** A payload derived from the full definition of an existing playbook saved
   and read back: the top-level fields and each step were copied from an existing playbook of
   the same type, the `id` fields were removed, and names, trigger, steps, and relations were
   replaced.
4. **The server assigns new identifiers on create.** The playbook `identifier` and every step
   `identifier` in the saved playbook differed from the values sent.
   `originalPlaybookIdentifier` equalled the new identifier. A parent playbook that referenced a
   nested block by the identifier that had been sent faulted at that block step at run time.
   Blocks must be saved first and referenced by the identifiers the server returns.
5. **Simulated steps.** With the playbook in debug mode, an action step with
   `isDebugMockData: true` and a `debugData` object (`resultValue`, optional `resultJson`)
   completed without the integration being called. The supplied JSON was returned as the step's
   result in the run instance.
6. **Action steps that really run need a fallback instance.** With
   `IntegrationInstance = AutomaticEnvironment` and no `FallbackIntegrationInstance` value, a
   `Siemplify` action step faulted. The same step completed once
   `FallbackIntegrationInstance` held the identifier of a configured instance.
7. **Delete.** Deleting a playbook that had never run returned status `DELETED`. Deleting one
   that had run returned status `ARCHIVED`.

## 3. Not Observed
- `UNKNOWN`: which field or fields made the hand-assembled payload in 2.2 unreadable. The cause
  was not isolated.
- `UNKNOWN`: `shouldRunAutomatic: false`.
- `UNKNOWN`: attaching by name alone, without `originalWorkflowDefinitionIdentifier`.
- `UNKNOWN`: updating an existing playbook in place by sending its `id`.
