# Discovery Observation: Google Cloud Security Status Feed & Outage Correlation

## 1. Executive Summary & Status
- **Classification Status:** `VERIFIED`
- **Capability IDs:**
  - `gcp_status.incidents.query` (`query`, bounded)
  - `gcp_status.report.audit` (`query`, single)
- **Agent Assigned:** `@cloud-status-agent` (Agent #22)
- **Data Fabric Storage:** Firestore / Local Evidence Store (`cloud_status_active`)

## 2. Live Status Feed Endpoints & Schema Mappings

### 2.1 Live Incidents Feed
- **Endpoint:** `https://status.cloud.google.com/security/incidents.json`
- **Schema Reference:** `https://status.cloud.google.com/security/incidents.schema.json`
- **HTTP Method:** `GET`
- **Protocol:** HTTP/1.1 or HTTP/2, JSON payload
- **Observed Structure:**
  - Array of incident objects ordered by recency.
  - Key fields:
    - `id`: Unique Google Cloud incident identifier (e.g. `XAZXzkY1Yg2GwXWnFw6M`).
    - `service_name`: Product name (`Google SecOps`, `Google Cloud Support`, etc.).
    - `service_key`: Stable product identifier (`FHwvkSZ6RzzDYAvDZXMM` for Google SecOps).
    - `status_impact`: Enumerated impact (`SERVICE_OUTAGE`, `SERVICE_DISRUPTION`, `SERVICE_INFORMATION`, `AVAILABLE`).
    - `severity`: Severity ranking (`low`, `medium`, `high`).
    - `begin`: ISO 8601 incident start timestamp.
    - `end`: ISO 8601 incident resolution timestamp (null if active).
    - `external_desc`: Public description of incident and impact.
    - `currently_affected_locations`: Array of `{id, title}` objects (e.g. `europe-west3`, `us-central1`).
    - `updates`: Array of periodic status updates with timestamp, narrative text, status, and affected locations.
    - `uri`: Canonical relative link (e.g. `incidents/XAZXzkY1Yg2GwXWnFw6M`).
    - Public UI Link: `https://status.cloud.google.com/security/incidents/{id}`.

## 3. Operational Correlation Rules

When an upstream incident affects Google SecOps, the agent correlates the disruption with analyst workflows:
1. **Ingestion Latency / Forwarder Buffering:**
   - When an active disruption is detected for log ingestion (e.g. in `europe-west3` or multi-region), advise SOC engineers against restarting forwarders or modifying ingestion pipelines; upstream queues buffer raw telemetry safely.
2. **Case Synchronization Latency:**
   - When case management or alert grouping exhibits delays, notify SOC triage that investigation walls and alerts may experience lag while underlying raw log ingestion remains intact.
3. **Detection Engine Latency:**
   - When YARA-L rule evaluation delays are reported upstream, notify threat hunters and detection engineers that alerts are evaluating behind real-time.
4. **Autonomous Resolution:**
   - Deacon background patrols monitor the incident feed on a 30-minute interval. When all incidents for Google SecOps transition to `end != null` or `AVAILABLE`, active Gas Town beads and issues are automatically marked `RESOLVED`.
