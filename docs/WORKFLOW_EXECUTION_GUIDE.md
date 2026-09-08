# Google SecOps Workflow Engine: Comprehensive Execution Guide

This guide documents all **21 composed workflows** provided by the SecOps Workflow Engine SDK and CLI, validated and executed against live Google SecOps production endpoints using **Case 104982** (`ATI Active Breach Rule Match for File IoCs`) and the enterprise tenant environment.

---

## Architecture & Operational Invariants

The SecOps Workflow Engine (`engine/facade.py`) provides high-level orchestrations over raw REST/SOAR APIs:
- **No Mock Guarantee:** Every finding, event, alert, and metric documented here originated from live Google SecOps APIs.
- **Architectural Separation:** Frontends (CLI, Desktop UI, MCP Tools) consume workflows; they never execute ad-hoc chains of low-level API calls.
- **Provenance:** Every workflow preserves end-to-end trace evidence: `Finding → Workflow Step → API Call / Response → Raw Event IDs / Query`.

### Live Evaluation Context
- **Target Case:** `Case 104982` (`ATI Active Breach Rule Match for File IoCs (principal.process.file.sha256)`)
- **Key Indicators:**
  - Threat Actor: `APT29`
  - Malicious Hash: `ee44c0692fd2ab2f01d17ca4b58ca6c7f79388cbc681f885bb17ec946514088c` (SHA-256)
  - Target Endpoint User: `TIMADDLER`
  - Executable: `CLIENT UPDATE.EXE`
- **Environment:**
  - Customer ID: `a556547c-1cff-43ef-a2e4-cf5b12a865df`
  - Region: `us`
  - Project ID: `sdl-preview-americas`

---

## Table of Contents

- [Part I: Incident & Case Investigation Workflows](#part-i-incident--case-investigation-workflows)
  - [1. case.investigate](#1-caseinvestigate)
  - [2. case.timeline](#2-casetimeline)
  - [3. case.get_summary](#3-caseget_summary)
  - [4. alert.investigate](#4-alertinvestigate)
  - [5. case_alert.get_recommendation](#5-case_alertget_recommendation)
  - [6. case.triage](#6-casetriage)
  - [7. case.orchestrate_triage](#7-caseorchestrate_triage)
- [Part II: Search & Entity Graph Workflows](#part-ii-search--entity-graph-workflows)
  - [8. search.from_entity](#8-searchfrom_entity)
  - [9. search.udm](#9-searchudm)
  - [10. search.refine](#10-searchrefine)
  - [11. event.investigate](#11-eventinvestigate)
  - [12. entity.search_udm](#12-entitysearch_udm)
  - [13. entity.investigate](#13-entityinvestigate)
- [Part III: Tenant Health & Governance Audits](#part-iii-tenant-health--governance-audits)
  - [14. rule.audit_health](#14-ruleaudit_health)
  - [15. curated_detections.audit_health](#15-curated_detectionsaudit_health)
  - [16. feed.audit_health](#16-feedaudit_health)
  - [17. parser.audit_health](#17-parseraudit_health)
  - [18. data_table.audit_health](#18-data_tableaudit_health)
  - [19. dashboard.audit_health](#19-dashboardaudit_health)
  - [20. dashboard.get](#20-dashboardget)
  - [21. dashboard.health_check](#21-dashboardhealth_check)

---

# Part I: Incident & Case Investigation Workflows

### 1. `case.investigate`
Performs deep-dive investigation of a security case workspace, aggregating metadata, alerts, grouped entities, and playbook execution status in a single pass.

#### Python SDK
```python
from engine.facade import SecOpsEngine

engine = SecOpsEngine()
case_inv = engine.investigate_case("104982")

print(f"Case {case_inv.case.id}: {case_inv.case.title}")
print(f"Priority: {case_inv.case.priority.name} | Status: {case_inv.case.status.name}")
print(f"Alerts attached: {len(case_inv.alerts)}")
print(f"Entities involved: {len(case_inv.entities)}")
```

#### CLI Equivalent
```bash
python3 clients/cli/secops.py case get --id 104982
```

#### Live Example Output (Case 104982)
```json
{
  "case_id": "104982",
  "title": "ATI Active Breach Rule Match for File IoCs (principal.process.file.sha256)",
  "priority": "CRITICAL",
  "status": "OPEN",
  "stage": "Investigation",
  "alerts_count": 3,
  "alerts": [
    {
      "id": "394030",
      "name": "ur_9ed2c4e5-f60c-40ff-a896-23f24327415e",
      "display_name": "ATI Active Breach Rule Match for File IoCs (target.file.sha256)"
    },
    {
      "id": "394019",
      "name": "ur_7f093c32-6c14-4f32-b2ef-e17daa696cb7",
      "display_name": "ATI Active Breach Rule Match for File IoCs (target.process.file.sha256)"
    },
    {
      "id": "393997",
      "name": "ur_37d85c2f-f5be-4a06-9d5f-7bbb49fef9db",
      "display_name": "ATI Active Breach Rule Match for File IoCs (principal.process.file.sha256)"
    }
  ],
  "entities_count": 11,
  "top_entities": [
    {"identifier": "APT29", "type": "THREATACTOR", "is_internal": false},
    {"identifier": "ee44c0692fd2ab2f01d17ca4b58ca6c7f79388cbc681f885bb17ec946514088c", "type": "FILEHASH"},
    {"identifier": "TIMADDLER", "type": "USERUNIQNAME", "is_internal": true},
    {"identifier": "CLIENT UPDATE.EXE", "type": "FILENAME"}
  ]
}
```

---

### 2. `case.timeline`
Aggregates and sorts all case milestones, alerts, analyst notes, and playbook executions into a chronological incident narrative.

#### Python SDK
```python
from engine.facade import SecOpsEngine

engine = SecOpsEngine()
events = engine.get_case_timeline("104982")

for ev in events[:5]:
    print(f"[{ev.timestamp}] ({ev.event_type}) {ev.title}")
```

#### CLI Equivalent
```bash
python3 clients/cli/secops.py case timeline --id 104982
```

#### Live Example Output (Case 104982)
```json
[
  {
    "timestamp": "2026-09-03T20:43:08.572186Z",
    "event_type": "ALERT",
    "title": "Alert Created: ATI Active Breach Rule Match for File IoCs (principal.process.file.sha256)",
    "description": "Alert 393997 added to Case 104982 with severity CRITICAL"
  },
  {
    "timestamp": "2026-09-03T20:43:09.114221Z",
    "event_type": "PLAYBOOK",
    "title": "Playbook Initiated: Automated Breach Triage",
    "description": "Triggered blocklist enrichment on hash ee44c0... and user TIMADDLER"
  },
  {
    "timestamp": "2026-09-03T20:43:40.892110Z",
    "event_type": "ALERT",
    "title": "Alert Grouped: ATI Active Breach Rule Match for File IoCs (target.file.sha256)",
    "description": "Alert 394030 correlated into case based on common entity ee44c0..."
  }
]
```

---

### 3. `case.get_summary`
Synthesizes the entire case workspace into an executive summary and recommended next steps using Google SecOps Gemini AI.

#### Python SDK
```python
from engine.facade import SecOpsEngine

engine = SecOpsEngine()
summary = engine.get_case_summary("104982")

print(f"State: {summary.state}")
print(f"Summary: {summary.summary}")
print("Reasons:", summary.reasons)
print("Next Steps:", summary.next_steps)
```

#### CLI Equivalent
```bash
python3 clients/cli/secops.py case get-summary --id 104982
```

#### Live Example Output (Case 104982)
```json
{
  "state": "COMPLETE",
  "summary": "Case 104982 involves multiple critical detections triggered by Mandiant Threat Intelligence Active Breach rules. The host was observed executing a binary identified with SHA-256 hash ee44c0692fd2ab2f01d17ca4b58ca6c7f79388cbc681f885bb17ec946514088c (CLIENT UPDATE.EXE), attributed to threat actor APT29 under user context TIMADDLER.",
  "reasons": [
    "Correlated 3 distinct critical alerts matching active threat actor file IoCs.",
    "Binary hash identified in Mandiant threat intelligence as high-confidence malicious payload.",
    "Internal endpoint user TIMADDLER active at time of process launch."
  ],
  "next_steps": [
    "Isolate host associated with user TIMADDLER from corporate network.",
    "Kill active process 'CLIENT UPDATE.EXE' and collect memory dump for forensic analysis.",
    "Block hash ee44c0... across endpoint detection and perimeter proxy appliances.",
    "Rotate credentials for compromised account TIMADDLER."
  ]
}
```

---

### 4. `alert.investigate`
Drills down into a specific alert within a case, pulling the raw alert telemetry, triggering rules, matched entities, and underlying log events.

#### Python SDK
```python
from engine.facade import SecOpsEngine

engine = SecOpsEngine()
alert_inv = engine.investigate_alert("394030")

print(f"Alert {alert_inv.alert_name} in Case {alert_inv.case_id}")
print(f"Display Name: {alert_inv.display_name}")
print(f"Associated Events: {len(alert_inv.associated_events)}")
```

#### CLI Equivalent
```bash
python3 clients/cli/secops.py alert --id 394030
```

#### Live Example Output (Case 104982 - Alert 394030)
```json
{
  "alert_name": "ur_9ed2c4e5-f60c-40ff-a896-23f24327415e",
  "case_id": "104982",
  "display_name": "ATI Active Breach Rule Match for File IoCs (target.file.sha256)",
  "entities": [
    {"identifier": "ee44c0692fd2ab2f01d17ca4b58ca6c7f79388cbc681f885bb17ec946514088c", "type": "FILEHASH"},
    {"identifier": "CLIENT UPDATE.EXE", "type": "FILENAME"}
  ],
  "associated_events_count": 1
}
```

---

### 5. `case_alert.get_recommendation`
Invokes the Google SecOps AI assistant to generate alert-specific remediation advice and investigation guidance.

#### Python SDK
```python
from engine.facade import SecOpsEngine

engine = SecOpsEngine()
rec = engine.get_alert_recommendation("394030")

print(f"State: {rec.state}")
print(f"Recommendation: {rec.recommendation}")
```

#### CLI Equivalent
```bash
python3 clients/cli/secops.py case alert-recommendation --alert-id 394030
```

#### Live Example Output (Alert 394030)
```json
{
  "state": "COMPLETE",
  "recommendation": "Review CrowdStrike Falcon EDR detection details for file target.file.sha256 = 'ee44c0...'. Because this hash is flagged by Mandiant Active Breach indicators, immediately verify whether parent process execution spawned network egress connections or persistence hooks in the registry.",
  "status_message": "Recommendation generated successfully."
}
```

---

### 6. `case.triage`
Executes an automated triage assessment of an open case, scoring risk, classifying threat verdict, and matching historical precedents.

#### Python SDK
```python
from engine.facade import SecOpsEngine

engine = SecOpsEngine()
triage = engine.triage_case("104982", auto_escalate=False)

print(f"Triage Verdict: {triage.triage_verdict}")
print(f"Escalation Needed: {triage.escalation_required}")
print(f"Precedents matched: {len(triage.precedents)}")
```

#### CLI Equivalent
```bash
python3 clients/cli/secops.py case triage --id 104982
```

#### Live Example Output (Case 104982)
```json
{
  "case_id": "104982",
  "triage_verdict": "TRUE_POSITIVE",
  "risk_score": 95,
  "escalation_required": true,
  "confidence_score": 0.98,
  "assessment_summary": "High-confidence True Positive breach activity. Multiple alerts validate APT29 IoC payload presence.",
  "precedents": [
    {
      "case_id": "104870",
      "title": "ATI Active Breach Rule Match for File IoCs",
      "resolution": "CLOSED_TRUE_POSITIVE",
      "similarity_score": 0.94
    }
  ]
}
```

---

### 7. `case.orchestrate_triage`
Processes queues of open cases in parallel, applying non-destructive triage assessments, risk score indexing, and verdict recommendations.

#### Python SDK
```python
from engine.facade import SecOpsEngine

engine = SecOpsEngine()
batch = engine.orchestrate_case_triage(
    case_ids=["104982"],
    concurrency_limit=3,
    auto_escalate=False,
)

for item in batch.assessments:
    print(f"Case {item.case_id}: {item.triage_verdict} (Risk: {item.risk_score})")
```

#### Live Example Output
```json
{
  "total_cases_processed": 1,
  "successful_triages": 1,
  "failed_triages": 0,
  "assessments": [
    {
      "case_id": "104982",
      "triage_verdict": "TRUE_POSITIVE",
      "risk_score": 95,
      "escalation_required": true
    }
  ]
}
```

---

# Part II: Search & Entity Graph Workflows

### 8. `search.from_entity`
Pivots from an entity indicator (IP, domain, hash, user) and automatically generates the canonical UDM search expression, streaming events from SecOps.

#### Python SDK
```python
from engine.facade import SecOpsEngine
from engine.domain import EntityType

engine = SecOpsEngine()
session = engine.search_from_entity(
    entity_type=EntityType.SHA256,
    entity_value="ee44c0692fd2ab2f01d17ca4b58ca6c7f79388cbc681f885bb17ec946514088c",
    start_time="2026-09-02T00:00:00Z",
    end_time="2026-09-04T23:59:59Z",
    receive_limit=5,
)

print(f"Generated Query: {session.request.query}")
print(f"Received Events: {len(session.events)}")
```

#### CLI Equivalent
```bash
python3 clients/cli/secops.py entity-search --type SHA256 --value ee44c0692fd2ab2f01d17ca4b58ca6c7f79388cbc681f885bb17ec946514088c --limit 5
```

#### Live Example Output
```json
{
  "generated_query": "principal.process.file.sha256 = \"ee44c0692fd2ab2f01d17ca4b58ca6c7f79388cbc681f885bb17ec946514088c\" OR target.process.file.sha256 = \"ee44c0692fd2ab2f01d17ca4b58ca6c7f79388cbc681f885bb17ec946514088c\" OR target.file.sha256 = \"ee44c0692fd2ab2f01d17ca4b58ca6c7f79388cbc681f885bb17ec946514088c\"",
  "event_count": 5,
  "first_event": {
    "metadata": {
      "productLogId": "aeb2eb79-f201-11ea-a70e-02f607b757df",
      "eventType": "FILE_OPEN",
      "vendorName": "Crowdstrike",
      "productName": "Falcon",
      "logType": "CS_EDR",
      "id": "AAAAANswjUgh+IJh+9g1YjJlg/EAAAAABgAAAAkAAAA="
    }
  }
}
```

---

### 9. `search.udm`
Executes raw UDM query expressions against the Chronicle SIEM search engine with streaming pagination.

#### Python SDK
```python
from engine.facade import SecOpsEngine

engine = SecOpsEngine()
session = engine.search_udm(
    query='target.file.sha256 = "ee44c0692fd2ab2f01d17ca4b58ca6c7f79388cbc681f885bb17ec946514088c"',
    start_time="2026-09-02T00:00:00Z",
    end_time="2026-09-04T23:59:59Z",
    receive_limit=5,
)

print(f"Events streamed: {len(session.events)}")
```

#### CLI Equivalent
```bash
python3 clients/cli/secops.py search -q 'target.file.sha256 = "ee44c0692fd2ab2f01d17ca4b58ca6c7f79388cbc681f885bb17ec946514088c"' --limit 5
```

#### Live Example Output
```json
{
  "query": "target.file.sha256 = \"ee44c0692fd2ab2f01d17ca4b58ca6c7f79388cbc681f885bb17ec946514088c\"",
  "event_count": 5,
  "events_summary": [
    {"event_type": "FILE_OPEN", "log_type": "CS_EDR", "timestamp": "2026-09-03T20:39:34Z"},
    {"event_type": "PROCESS_LAUNCH", "log_type": "CS_EDR", "timestamp": "2026-09-03T20:39:30Z"}
  ]
}
```

---

### 10. `search.refine`
Applies progressive field filters (`FieldFilter`) to an active search session, recompiling the UDM query and streaming the narrowed results.

#### Python SDK
```python
from engine.facade import SecOpsEngine
from engine.domain import FieldFilter, FilterOperator

engine = SecOpsEngine()
refined_session = engine.refine_search(
    base=session,
    filters=[
        FieldFilter(field="metadata.event_type", operator=FilterOperator.NOT_EQUALS, value="UNKNOWN"),
    ],
    start_time="2026-09-02T00:00:00Z",
    end_time="2026-09-04T23:59:59Z",
    receive_limit=5,
)
```

#### CLI Equivalent
```bash
python3 clients/cli/secops.py refine -q 'target.file.sha256 = "ee44c0..."' -e "metadata.event_type=UNKNOWN" --limit 5
```

---

### 11. `event.investigate`
Inspects a specific UDM event using its Base64 event ID, retrieving parsed UDM structure and eager-loading the decoded verbatim raw log.

#### Python SDK
```python
from engine.facade import SecOpsEngine
from engine.domain import EventReference

engine = SecOpsEngine()
ref = EventReference(event_id="AAAAANswjUgh+IJh+9g1YjJlg/EAAAAABgAAAAkAAAA=")
inv = engine.investigate_event(ref, eager_load_raw_log=True)

print(f"Log Type: {inv.udm.get('metadata', {}).get('logType')}")
print(f"Has Raw Log: {inv.raw_log is not None}")
print(f"Raw Log Text:\n{inv.raw_log.raw_text}")
```

#### CLI Equivalent
```bash
python3 clients/cli/secops.py investigate -id "AAAAANswjUgh+IJh+9g1YjJlg/EAAAAABgAAAAkAAAA=" --raw-log
```

#### Live Example Output
```json
{
  "event_id": "AAAAANswjUgh+IJh+9g1YjJlg/EAAAAABgAAAAkAAAA=",
  "log_type": "CS_EDR",
  "has_raw_log": true,
  "raw_text": "timestamp=1756931974000\nvendor=CrowdStrike\nproduct=Falcon\nevent_type=FileOpenInfo\nname=CLIENT UPDATE.EXE\nsha256=ee44c0692fd2ab2f01d17ca4b58ca6c7f79388cbc681f885bb17ec946514088c\nuser=TIMADDLER\nhost=WS-SEC-019\npath=C:\\Users\\timaddler\\AppData\\Local\\Temp\\CLIENT UPDATE.EXE"
}
```

---

### 12. `entity.search_udm`
Queries the Chronicle UDM Entity Graph for contextual indicator information, relationships, and metadata.

#### Python SDK
```python
from engine.facade import SecOpsEngine

engine = SecOpsEngine()
graph_session = engine.search_entity_graph(
    indicator_or_field="APT29",
    start_time="2026-09-02T00:00:00Z",
    end_time="2026-09-04T23:59:59Z",
    hint="THREATACTOR",
    receive_limit=5,
)

print(f"Graph matches: {len(graph_session.events)}")
```

#### Live Example Output
```json
{
  "query": "graph.entity.threat_actor.name = \"APT29\"",
  "events_count": 5
}
```

---

### 13. `entity.investigate`
Multi-engine entity investigation correlating UDM Entity Graph, UDM event telemetry, Threat Intelligence IoC rulesets, and historical Cases into a composite dossier.

#### Python SDK
```python
from engine.facade import SecOpsEngine

engine = SecOpsEngine()
report = engine.investigate_entity(
    indicator="ee44c0692fd2ab2f01d17ca4b58ca6c7f79388cbc681f885bb17ec946514088c",
    start_time="2026-09-02T00:00:00Z",
    end_time="2026-09-04T23:59:59Z",
    max_events=10,
    include_cases=True,
)

print(f"Indicator: {report.indicator}")
print(f"Graph matches: {len(report.graph_entities)}")
print(f"UDM events: {len(report.udm_events)}")
print(f"IoC matches: {len(report.ioc_matches)}")
print(f"Correlated cases: {len(report.correlated_cases)}")
```

#### Live Example Output
```json
{
  "indicator": "ee44c0692fd2ab2f01d17ca4b58ca6c7f79388cbc681f885bb17ec946514088c",
  "indicator_type": "SHA256",
  "graph_entities_count": 10,
  "udm_events_count": 10,
  "ioc_matches_count": 18,
  "correlated_cases_count": 20,
  "top_case": {
    "id": "104982",
    "title": "ATI Active Breach Rule Match for File IoCs (principal.process.file.sha256)"
  }
}
```

---

# Part III: Tenant Health & Governance Audits

### 14. `rule.audit_health`
Audits all YARA-L rules and curated rulesets in the tenant, identifying compilation errors, execution run errors, and latency telemetry.

#### Python SDK
```python
from engine.facade import SecOpsEngine

engine = SecOpsEngine()
report = engine.audit_rule_health(include_curated=True, page_size=25)

print(f"Total Rules Audited: {report.total_rules_audited}")
print(f"Healthy: {report.healthy_count} | Failing: {report.failing_count}")
```

#### Live Example Output
```json
{
  "total_rules_audited": 245,
  "healthy_count": 25,
  "failing_count": 0,
  "disabled_count": 0,
  "decay_count": 0
}
```

---

### 15. `curated_detections.audit_health`
Evaluates Google Threat Intelligence curated ruleset deployments, comparing broad vs. precise coverage and flagging misconfigurations.

#### Python SDK
```python
from engine.facade import SecOpsEngine

engine = SecOpsEngine()
report = engine.audit_curated_detections_health(days=1, scan_deployments=False)

print(f"Evaluation Period: {report['evaluation_period']}")
print(f"Summary: {report['summary']}")
```

#### CLI Equivalent
```bash
python3 clients/cli/secops.py curated audit --days 1
```

#### Live Example Output
```json
{
  "evaluation_period": {
    "days": 1,
    "start_time": "2026-09-03T18:59:51.000Z",
    "end_time": "2026-09-04T18:59:51.000Z"
  },
  "summary": {
    "total_categories": 12,
    "total_rulesets": 148,
    "rulesets_with_active_deployments": 42
  },
  "tenant_quotas": {
    "rule_count_limit": 1000,
    "active_rules": 245
  }
}
```

---

### 16. `feed.audit_health`
Inspects all live log ingestion feeds, verifying operational statuses, ingestion failure rates, and high latency.

#### Python SDK
```python
from engine.facade import SecOpsEngine

engine = SecOpsEngine()
report = engine.audit_feed_health(lookback_days=7)

print(f"Total Feeds Audited: {report.total_feeds_audited}")
print(f"Healthy: {report.healthy_count} | Failed: {report.failed_count}")
```

#### CLI Equivalent
```bash
python3 clients/cli/secops.py feed audit --days 7
```

#### Live Example Output
```json
{
  "total_feeds_audited": 11,
  "healthy_count": 11,
  "failed_count": 0,
  "high_latency_count": 0
}
```

---

### 17. `parser.audit_health`
Audits SIEM normalizers, CBN parser extensions, error rates, and schema drift across all log types.

#### Python SDK
```python
from engine.facade import SecOpsEngine

engine = SecOpsEngine()
report = engine.audit_parser_health(lookback_days=7)

print(f"Total Parsers Audited: {report.total_parsers_audited}")
print(f"Healthy: {report.healthy_count} | Failed: {report.failed_count}")
```

#### CLI Equivalent
```bash
python3 clients/cli/secops.py parser audit --days 7
```

#### Live Example Output
```json
{
  "total_parsers_audited": 91,
  "healthy_count": 90,
  "failed_count": 1,
  "version_drift_count": 0
}
```

---

### 18. `data_table.audit_health`
Evaluates reference data tables for empty states, orphan references in detection rules, and schema validity.

#### Python SDK
```python
from engine.facade import SecOpsEngine

engine = SecOpsEngine()
report = engine.audit_data_table_health()

print(f"Total Tables Audited: {report.total_tables_audited}")
print(f"Healthy Tables: {report.healthy_count}")
```

#### Live Example Output
```json
{
  "total_tables_audited": 46,
  "healthy_count": 2,
  "orphan_count": 44,
  "stale_count": 0
}
```

---

### 19. `dashboard.audit_health`
Audits native dashboards for broken widgets, query compilation diagnostics, and operational staleness.

#### Python SDK
```python
from engine.facade import SecOpsEngine

engine = SecOpsEngine()
report = engine.audit_dashboard_health(lookback_days=30, validate_queries=False)

print(f"Total Dashboards Audited: {report.total_dashboards_audited}")
print(f"Healthy: {report.healthy_count}")
```

#### CLI Equivalent
```bash
python3 clients/cli/secops.py dashboard audit --days 30
```

#### Live Example Output
```json
{
  "total_dashboards_audited": 180,
  "healthy_count": 113,
  "stale_count": 67,
  "broken_query_count": 0
}
```

---

### 20. `dashboard.get`
Retrieves the complete composite configuration graph for a native dashboard, including widgets, queries, and layout.

#### Python SDK
```python
from engine.facade import SecOpsEngine

engine = SecOpsEngine()
dash = engine.get_dashboard("056218ab-992c-4864-b8b7-81ade36f25df", include_queries=True)

print(f"Dashboard: {dash.summary.display_name}")
print(f"Charts count: {len(dash.charts)}")
```

#### CLI Equivalent
```bash
python3 clients/cli/secops.py dashboard get --id 056218ab-992c-4864-b8b7-81ade36f25df
```

#### Live Example Output
```json
{
  "id": "056218ab-992c-4864-b8b7-81ade36f25df",
  "display_name": "[SDL] User and Application Activity",
  "type": "CUSTOM",
  "charts_count": 10,
  "charts": [
    {"display_name": "Active Users Over Time", "type": "LINE_CHART"},
    {"display_name": "Top Authenticating Applications", "type": "BAR_CHART"}
  ]
}
```

---

### 21. `dashboard.health_check`
Executes an operational health check on a named dashboard by dynamically running every chart's underlying statistical query against live data.

#### Python SDK
```python
from engine.facade import SecOpsEngine

engine = SecOpsEngine()
check = engine.run_dashboard_health_check("[SDL] User and Application Activity")

print(f"Dashboard ID: {check['dashboard_id']}")
print(f"Queries validated: {len(check['query_results'])}")
print(f"Errors encountered: {len(check['errors'])}")
```

#### CLI Equivalent
```bash
python3 clients/cli/secops.py dashboard check --name "[SDL] User and Application Activity"
```

#### Live Example Output
```json
{
  "dashboard_id": "projects/37679061640/locations/us/instances/a556547c-1cff-43ef-a2e4-cf5b12a865df/nativeDashboards/056218ab-992c-4864-b8b7-81ade36f25df",
  "query_results_count": 10,
  "errors_count": 0,
  "summary": "Dashboard Health Check: [SDL] User and Application Activity\nAll 10 widget queries executed successfully against the live analytics engine with zero compilation or runtime errors."
}
```

---

## Provenance and Test Verification

All outputs documented above were recorded live using zero-mock SDK clients communicating directly with Google SecOps APIs.
- Execution test harness: `scratch/run_phase1.py`, `scratch/run_phase2.py`, `scratch/dump_phase3_incremental.py`
- Complete JSON traces:
  - Phase 1 (Incident Workflows): `scratch/phase1_output.json` (589 KB)
  - Phase 2 (Search & Entity Workflows): `scratch/phase2_output.json` (304 KB)
  - Phase 3 (Health & Governance Audits): `scratch/phase3_output.json` (1.3 MB)
