---
id: feature.soar.case_management
title: "SOAR Case Management & Triage"
type: feature
platform: secops_soar
sdk_capabilities:
  - case.investigate
  - case.comment
  - case.list_comments
  - case.get_wall
  - case.update
  - case.assign
  - case.set_stage
  - case.set_incident
  - case_alert.update
  - case_alert.set_priority
  - case_alert.create_recommendation
  - case_alert.fetch_recommendation
  - case_alert.get_recommendation
  - case.get_or_create_summary
  - case.get_summary
  - case.search
  - case.orchestrate_triage
  - case.triage
  - case.timeline
  - case.ai_investigate
mcp_tools:
  - add_case_comment
  - ai_investigate_case
  - assign_case
  - create_case_alert_recommendation
  - fetch_case_alert_recommendation
  - get_case_alert_recommendation
  - get_case_summary
  - get_case_timeline
  - get_case_wall
  - get_or_create_case_summary
  - investigate_case
  - list_case_comments
  - orchestrate_case_triage
  - search_cases
  - set_case_alert_priority
  - set_case_incident
  - set_case_stage
  - triage_case
  - update_case
  - update_case_alert
---

# SOAR Case Management & Triage

## 1. Feature Purpose & Scope
Provides programmatic operational access to SOAR Case Management & Triage within secops_soar.

## 2. Capabilities & SDK Workflows
### `case.investigate`
- **Description:** Aggregates case metadata, security alerts, involved entities, and analyst comments.
- **Kind:** `workflow` | **Cardinality:** `none`
- **MCP Tool:** `investigate_case`

### `case.comment`
- **Description:** Adds structured analyst investigation comments to a SOAR case.
- **Kind:** `primitive` | **Cardinality:** `none`
- **MCP Tool:** `add_case_comment`

### `case.list_comments`
- **Description:** Lists all analyst comments and AI assessment notes for a SOAR case.
- **Kind:** `query` | **Cardinality:** `unbounded`
- **MCP Tool:** `list_case_comments`

### `case.get_wall`
- **Description:** Retrieves the complete SOAR case activity stream including status changes, tag updates, and playbook execution steps.
- **Kind:** `query` | **Cardinality:** `unbounded`
- **MCP Tool:** `get_case_wall`

### `case.update`
- **Description:** Mutates case attributes such as assignee, stage, incident flag, or priority.
- **Kind:** `primitive` | **Cardinality:** `none`
- **MCP Tool:** `update_case`

### `case.assign`
- **Description:** Assigns a SOAR case to a SOC role (@Role) or user GUID.
- **Kind:** `primitive` | **Cardinality:** `none`
- **MCP Tool:** `assign_case`

### `case.set_stage`
- **Description:** Updates the lifecycle stage of a SOAR case.
- **Kind:** `primitive` | **Cardinality:** `none`
- **MCP Tool:** `set_case_stage`

### `case.set_incident`
- **Description:** Marks or unmarks a SOAR case as an incident.
- **Kind:** `primitive` | **Cardinality:** `none`
- **MCP Tool:** `set_case_incident`

### `case_alert.update`
- **Description:** Mutates case alert attributes such as priority or status.
- **Kind:** `primitive` | **Cardinality:** `none`
- **MCP Tool:** `update_case_alert`

### `case_alert.set_priority`
- **Description:** Updates the priority level of a specific case alert.
- **Kind:** `primitive` | **Cardinality:** `none`
- **MCP Tool:** `set_case_alert_priority`

### `case_alert.create_recommendation`
- **Description:** Initiates asynchronous generation of a Gemini AI recommendation for a case alert.
- **Kind:** `primitive` | **Cardinality:** `none`
- **MCP Tool:** `create_case_alert_recommendation`

### `case_alert.fetch_recommendation`
- **Description:** Fetches a previously generated Gemini AI recommendation for a case alert by recommendation ID.
- **Kind:** `primitive` | **Cardinality:** `none`
- **MCP Tool:** `fetch_case_alert_recommendation`

### `case_alert.get_recommendation`
- **Description:** End-to-end workflow to trigger Gemini AI recommendation generation and poll until completion or failure.
- **Kind:** `workflow` | **Cardinality:** `none`
- **MCP Tool:** `get_case_alert_recommendation`

### `case.get_or_create_summary`
- **Description:** Gets or initiates generation of a Gemini AI-driven overview, reasons, and next steps for a SOAR case.
- **Kind:** `primitive` | **Cardinality:** `none`
- **MCP Tool:** `get_or_create_case_summary`

### `case.get_summary`
- **Description:** Requests Gemini AI case summary and polls until generation is complete or timeout.
- **Kind:** `workflow` | **Cardinality:** `none`
- **MCP Tool:** `get_case_summary`

### `case.search`
- **Description:** Searches, lists, and filters SOAR cases across time ranges, status, priority, and stages.
- **Kind:** `query` | **Cardinality:** `unbounded`
- **MCP Tool:** `search_cases`

### `case.orchestrate_triage`
- **Description:** Batched retrieval, parallel investigation, and automated initial triage assessment for SOAR cases.
- **Kind:** `workflow` | **Cardinality:** `none`
- **MCP Tool:** `orchestrate_case_triage`

### `case.triage`
- **Description:** End-to-end single case triage: deep investigation, Gemini AI summary, title and entity precedent correlation, novelty assessment, and stage transitions.
- **Kind:** `workflow` | **Cardinality:** `none`
- **MCP Tool:** `triage_case`

### `case.timeline`
- **Description:** Synthesizes a chronologically ordered event timeline across Case Creation, Alert Detections, Playbook Milestones, Analyst Comments, and Case Updates.
- **Kind:** `workflow` | **Cardinality:** `none`
- **MCP Tool:** `get_case_timeline`

### `case.ai_investigate`
- **Description:** Executes deep AI-driven case investigation: fetches AI summary, extracts network and user indicators, runs automated UDM searches across Chronicle event logs, and assesses enterprise impact.
- **Kind:** `workflow` | **Cardinality:** `none`
- **MCP Tool:** `ai_investigate_case`

## 3. Operational Invariants & Constraints
- All queries returning unbounded collections require explicit filtering.
- Mutation capabilities must specify non-empty payloads and valid target IDs.

## 4. Telemetry & Observable Health Indicators
- Correlate changes against Native Dashboards and Health Hub.
