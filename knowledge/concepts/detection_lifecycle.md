---
id: concept.detection_lifecycle
title: "YARA-L Rule Engine & Curated Detections Lifecycle"
type: concept
applies_to:
  - secops_siem
related_features:
  - feature.siem.rules_engine
  - feature.siem.curated_detections
tags:
  - detections
  - yara_l
  - alerts
---

# YARA-L Rule Engine & Curated Detections Lifecycle

## 1. Overview & Mental Model
Google SecOps provides two detection tiers:
1. **Customer-Authored YARA-L Rules:** Custom rules supporting single-event matching and multi-event sliding window correlations.
2. **Google Curated Detections:** Vendor-maintained rule packs maintained by Mandiant and Google threat intelligence teams, mapped to MITRE ATT&CK.

## 2. Rule Execution States & Scheduling
- **Frequency:** Live rules run on recurring schedules (e.g., 10 minutes, hourly, daily).
- **Execution Latency:** Multi-event correlation rules with wide sliding windows (`match` variables over 24-48 hours) consume higher execution capacity.
- **Zero-Match Rules:** Rules that evaluate continuously but generate zero alerts over long periods may be misconfigured, referencing retired log types, or missing prerequisite UDM fields.

## 3. Curated Rule Drift & Retrenchment
Google regularly updates curated packs—deploying new detections for emerging threat campaigns and retiring rules that generate excessive false positives or have been superseded. SOC engineering teams must monitor weekly curated drift to ensure coverage remains stable.
