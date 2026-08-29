# Prompt: Historical UDM Threat Hunt across Multiple Indicators

## Role & Purpose
Act as a Senior Cyber Threat Hunter. Hunt for historical network connections, authentication activity, and process executions across Chronicle SIEM event telemetry involving suspect indicators (`{{INDICATORS}}`).

---

## Prompt Template

```text
Please execute a retrospective threat hunt across Google Chronicle SIEM for the following indicators:
{{INDICATORS}}

Investigation Parameters:
- Time Window: Past {{LOOKBACK_DAYS}} days (or from {{START_TIME}} to {{END_TIME}})
- Ingestion Boundary: Full enterprise event store

For each indicator:
1. Construct normalized UDM queries covering both principal and target roles:
   - For IP Addresses: principal.ip = "{{IP}}" OR target.ip = "{{IP}}"
   - For Domain Names: target.hostname = "{{DOMAIN}}" OR network.dns.questions.name = "{{DOMAIN}}"
   - For File Hashes: target.file.sha256 = "{{HASH}}" OR principal.process.file.sha256 = "{{HASH}}"
2. Analyze telemetry results:
   - Identify first seen and last seen timestamps.
   - List internal assets (hostnames and private IPs) that communicated with external indicators.
   - Summarize the top event types observed (e.g. NETWORK_CONNECTION, USER_LOGIN, PROCESS_LAUNCH).
3. Provide a threat assessment summarizing whether the telemetry indicates scanning, active exploitation, beaconing, or lateral movement.
```

---

## Programmatic Equivalent

### CLI:
```bash
secops search 'principal.ip = "104.168.160.6" OR target.ip = "104.168.160.6"' --limit 50
```
