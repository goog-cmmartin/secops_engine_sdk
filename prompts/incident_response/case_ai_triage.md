# Prompt: Autonomous SOAR Case AI Triage, IOC Extraction & Threat Hunt

## Role & Purpose
Act as a Lead Incident Responder and Security Automation Specialist. Execute a structured, multi-stage triage workflow for target SOAR Case `{{CASE_ID}}`. Extract all high-confidence indicators of compromise, scope historical activity across Chronicle SIEM historical telemetry, and determine incident escalation requirements.

---

## Prompt Template

```text
Please execute an autonomous incident response triage loop for SOAR Case {{CASE_ID}}.

Follow this 4-stage investigation protocol:

Stage 1: Gemini AI Narrative & MITRE ATT&CK Mapping
- Fetch the AI case summary and structured findings for Case {{CASE_ID}}.
- Identify the primary threat actor, attacked entity, and mapped MITRE ATT&CK tactics/techniques.

Stage 2: Indicator & Entity Boundary Extraction
- Inspect attached alerts (primary alert {{ALERT_ID}}) and case evidence.
- Extract all IPv4 / IPv6 addresses, domains, URL endpoints, and targeted user identities.

Stage 3: Historical UDM Threat Hunting
- For each extracted indicator, construct and execute a Chronicle SIEM UDM search across a {{LOOKBACK_DAYS}}-day lookback window:
  - For IPs: principal.ip = "<IP>" OR target.ip = "<IP>"
  - For Users: target.user.userid = "<USER>" OR principal.user.userid = "<USER>"
- Quantify matched event counts, unique host interactions, and temporal bounds.

Stage 4: Incident Assessment & Escalation Plan
- Determine if the case meets the threshold for an active Security Incident (`is_incident = True`).
- Recommend alert priority adjustments (e.g. elevate to CRITICAL).
- Provide a formatted Markdown audit log ready to be appended to the case investigation timeline.
```

---

## Programmatic Equivalent

### SDK / Runbook:
```python
from runbooks.incident_response.autonomous_case_ai_triage import run_autonomous_case_ai_triage

res = run_autonomous_case_ai_triage(
    case_id="104655",
    hunt_lookback_days=7,
    dry_run=True,
)
```

### CLI:
```bash
secops runbook run case-ai-triage --case-id 104655 [--dry-run]
```
