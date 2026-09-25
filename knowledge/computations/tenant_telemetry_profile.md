---
id: computation.tenant_telemetry_profile
type: computation
title: Live Tenant Telemetry & Identity Cartography Profile
status: stable
runtime: python
parameters:
  - name: days
    type: integer
    required: false
executor:
  resource: knowledge/tasks/platform_engineer/audit_tenant_configuration_posture.md
  receipt: [query_text, executed_time_range, result_rows]
attester:
  resource: knowledge/attesters/yaral_equality.py
generated: { by: 'agent/tenant-cartographer', at: '2026-09-24T20:22:34.846637+00:00' }
verified:
  - { by: 'process:secops-engine', at: '2026-09-24T20:22:34.846637+00:00' }
stale_after: '2027-09-24T19:50:00Z'
durability_hash: '14b011a8fd9cf0d8'
tags:
  - tenant-profile
  - cartography
  - udm
  - identity-matrix
---

# Live Tenant Telemetry & Identity Cartography Profile

> **Executive Summary**: Surveyed 20 log sources representing 76,566,715 events over 7d. Discovered 20 entity graph sources covering 543,064,569 entities. Top identity log source: GCP_CLOUDAUDIT.
> **Attested At**: `2026-09-24T20:22:34.846637+00:00` &bull; **Observation Window**: 7 Days

---

## 1. Top Identity Providers & Graph Sources (`graph` table)

| Log Type | Source Type | Vendor | Product | Total Entities | First Seen | Last Seen |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| `UNKNOWN` | DERIVED_CONTEXT | - | - | 240,012,309 | - | - |
| `GCP_THREATINTEL` | ENTITY_CONTEXT | Google | Google Threat Intelligence | 172,558,241 | - | - |
| `SDL_GTI_THREAT_FEED` | ENTITY_CONTEXT | Google Threat Intelligence | Categorized Threat Lists | 99,265,024 | - | - |
| `SDL_WEB_RISK` | ENTITY_CONTEXT | Google Cloud | Web Risk Enterprise | 29,864,160 | - | - |
| `GCP_THREATINTEL` | ENTITY_CONTEXT | Google Threat Intelligence | Categorized Threat Lists | 931,659 | - | - |
| `SDL_GTI_IOC_STREAM` | ENTITY_CONTEXT | Google Threat Intelligence | IOC Stream | 237,416 | - | - |
| `UNKNOWN` | SOURCE_TYPE_UNSPECIFIED | - | - | 110,009 | - | - |
| `MANDIANT_ASM_ENTITY` | ENTITY_CONTEXT | Mandiant | Mandiant Attack Surface Management | 45,475 | - | - |
| `GCP_BIGQUERY_CONTEXT` | ENTITY_CONTEXT | Google Cloud Platform | GCP BigQuery | 26,213 | - | - |
| `GCP_STORAGE_CONTEXT` | ENTITY_CONTEXT | Google Cloud Platform | GCP Storage Context | 3,176 | - | - |
| `GCP_COMPUTE_CONTEXT` | ENTITY_CONTEXT | Google Cloud Platform | GCP Compute Context | 3,130 | - | - |
| `GCP_IAM_CONTEXT` | ENTITY_CONTEXT | Google | Identity and Access Management | 2,545 | - | - |
| `WORKSPACE_USERS` | ENTITY_CONTEXT | Google | Cloud Identity | 1,451 | - | - |
| `MISP_IOC` | ENTITY_CONTEXT | MISP | MISP | 1,048 | - | - |
| `GCP_IAM_ANALYSIS` | ENTITY_CONTEXT | Google Cloud Platform | GCP IAM ANALYSIS | 974 | - | - |

---

## 2. UDM Identity Fidelity Density Matrix (`events` table)

Distinct population counts for principal and target user keys across active telemetry sources:

| Log Type | Principal User ID | Principal Email | Principal SID | Principal Obj ID | Target User ID | Target Email | Target SID | Target Obj ID |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| `GCP_CLOUDAUDIT` | 2,477 | 310 | 1 | 58 | 49 | 46 | 0 | 7 |
| `WIZ_IO` | 361 | 3 | 0 | 362 | 0 | 0 | 0 | 0 |
| `CS_EDR` | 97 | 2 | 23 | 59 | 24,692 | 343 | 13 | 6,761 |
| `KUBERNETES_NODE` | 57 | 3 | 0 | 0 | 33 | 0 | 0 | 0 |
| `WINEVTLOG` | 41 | 4 | 27 | 6 | 74 | 4 | 42 | 6 |
| `WINDOWS_SYSMON` | 40 | 7 | 6 | 6 | 8 | 2 | 3 | 3 |
| `CHRONICLE_SOAR_AUDIT` | 35 | 0 | 0 | 0 | 0 | 0 | 0 | 32 |
| `ZSCALER_WEBPROXY` | 16 | 2 | 2 | 3 | 0 | 0 | 0 | 0 |
| `UDM` | 15 | 13 | 1 | 3 | 3 | 3 | 0 | 1 |
| `OKTA` | 11 | 11 | 0 | 11 | 11 | 12 | 0 | 3 |
| `POWERSHELL` | 7 | 1 | 7 | 2 | 0 | 0 | 0 | 0 |
| `TANIUM_TH` | 7 | 2 | 2 | 4 | 0 | 0 | 0 | 0 |
| `GCP_SECURITYCENTER_THREAT` | 6 | 8 | 0 | 2 | 0 | 3 | 0 | 0 |
| `AUDITD` | 6 | 0 | 0 | 0 | 6 | 0 | 0 | 0 |
| `WORKSPACE_ACTIVITY` | 4 | 30 | 0 | 25 | 5 | 21 | 0 | 29 |
| `NIX_SYSTEM` | 3 | 1 | 0 | 1 | 5 | 1 | 0 | 1 |
| `CHROME_MANAGEMENT` | 3 | 13 | 0 | 2 | 0 | 2 | 0 | 0 |
| `WINDOWS_DEFENDER_AV` | 2 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| `WINDOWS_DEFENDER_ATP` | 2 | 3 | 1 | 2 | 0 | 0 | 0 | 0 |
| `SENTINEL_EDR` | 2 | 1 | 2 | 2 | 0 | 0 | 0 | 0 |

---

## 3. Telemetry Volume & Temporal Ingestion Pareto (`events` table)

| Rank | Log Type | Event Count | Ingestion Start | Ingestion End |
| :--- | :--- | :--- | :--- | :--- |
| 1 | `GCP_CLOUDAUDIT` | 52,981,508 | - | - |
| 2 | `GCP_LOADBALANCING` | 16,138,089 | - | - |
| 3 | `CS_EDR` | 3,179,673 | - | - |
| 4 | `KUBERNETES_NODE` | 1,528,298 | - | - |
| 5 | `NIX_SYSTEM` | 535,045 | - | - |
| 6 | `BRO_JSON` | 472,265 | - | - |
| 7 | `GCP_DNS` | 431,108 | - | - |
| 8 | `GCP_IDS` | 370,741 | - | - |
| 9 | `WINEVTLOG` | 215,012 | - | - |
| 10 | `WINDOWS_SYSMON` | 129,898 | - | - |
| 11 | `CHRONICLE_SOAR_AUDIT` | 93,928 | - | - |
| 12 | `POWERSHELL` | 93,784 | - | - |
| 13 | `GCP_CLOUD_NAT` | 90,561 | - | - |
| 14 | `GCP_SECURITYCENTER_VULNERABILITY` | 72,059 | - | - |
| 15 | `OPNSENSE` | 69,735 | - | - |
| 16 | `GCP_RUN` | 63,233 | - | - |
| 17 | `SDL_GTI_CVE` | 43,165 | - | - |
| 18 | `UDM` | 36,710 | - | - |
| 19 | `GCP_FIREWALL` | 11,155 | - | - |
| 20 | `CHROME_MANAGEMENT` | 10,748 | - | - |
