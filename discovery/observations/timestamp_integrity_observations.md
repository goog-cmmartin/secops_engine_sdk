# Discovery Observations: Telemetry Timestamp Integrity & Latency

## 1. Context & Operational Challenge
In production Google SecOps deployments, detection fidelity and forensic investigations depend on two critical timestamp fields in every UDM event:
- `metadata.event_timestamp`: Physical moment when the event occurred on the source endpoint or cloud infrastructure.
- `metadata.ingested_timestamp`: The exact timestamp when Google SecOps received and indexed the event.

The delta $\Delta t = \text{metadata.ingested\_timestamp} - \text{metadata.event\_timestamp}$ diagnoses two severe telemetry pathologies:
1. **Pipeline Latency Bottlenecks ($\Delta t \gg 0$):**
   - Logs arriving hours or days after occurrence.
   - Causes: Forwarder queue backpressure, network throttling, batching misconfigurations.
   - Operational impact: Real-time YARA-L detection rules miss SLA or fire hours after adversary breakout.
2. **Clock Skew / NTP Desynchronization ($\Delta t < 0$):**
   - Logs claiming to occur in the future relative to Google SecOps receipt time.
   - Causes: Host NTP daemon failure (`chronyd`, `w32time`), incorrect timezone formatting (+00:00 vs local) in custom parsers.
   - Operational impact: Timelines are corrupted, correlation windows fail, forensic reconstruction is invalid.

## 2. API Endpoint & Query Structure
The capability utilizes the live Google SecOps API endpoint:
`POST /v1alpha/projects/{project}/locations/{region}/instances/{instance}/dashboardQueries:execute`

### Query Syntax (YARA-L 2)
```yara
$log_type = strings.to_upper(metadata.log_type)

match:
    $log_type

outcome:
    $total = count(metadata.id)
    $average_difference_minutes = math.round(cast.as_int(avg(metadata.ingested_timestamp.seconds - metadata.event_timestamp.seconds)) / 60, 2)
    $cnt_lt_0_hours = sum(
        if(metadata.ingested_timestamp.seconds - metadata.event_timestamp.seconds < 0, 1, 0)
    )
    $cnt_0_1_hours = sum(
        if(metadata.ingested_timestamp.seconds - metadata.event_timestamp.seconds >= 0 AND metadata.ingested_timestamp.seconds - metadata.event_timestamp.seconds <= 3600, 1, 0)
    )
    $cnt_1_2_hours = sum(
        if(metadata.ingested_timestamp.seconds - metadata.event_timestamp.seconds > 3600 AND metadata.ingested_timestamp.seconds - metadata.event_timestamp.seconds <= 7200, 1, 0)
    )
    $cnt_gt_2_hours = sum(
        if(metadata.ingested_timestamp.seconds - metadata.event_timestamp.seconds > 7200, 1, 0)
    )

order:
    $average_difference_minutes desc
```

## 3. Evidence Fabric Dual-Document Persistence
Audits maintain state across runs in Firestore collection `timestamp_integrity`:
- `timestamp_integrity/latest`: Document overwritten on each run to enable instant retrieval and diffing against the historical baseline.
- `timestamp_integrity/{auto_id}`: Append-only immutable historical snapshots with server timestamps.

## 4. State-Aware Progression Engine
Every log type is evaluated on every run against the prior baseline:
- `NEW`: Anomaly detected in current run (`average_difference_minutes > 60` or `cnt_lt_0_hours > 0`), but was Healthy or Absent previously.
- `PREVIOUSLY KNOWN`: Anomaly detected in current run, and was also anomalous in prior baseline.
- `RESOLVED`: Current run is Healthy, but had an anomaly in prior baseline.
- `HEALTHY`: Healthy in both current and prior baseline.
