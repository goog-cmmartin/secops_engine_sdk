---
id: feature.<platform>.<feature_name>
type: feature
title: "<Feature Title>"
description: "<One-sentence summary of this platform capability>"
tags:
  - secops
  - capability
status: stable  # valid: draft, stable, deprecated
generated: { by: "<actor>", at: "<iso8601>" }
verified:
  - { by: "human:<reviewer_id>", at: "<iso8601>" }
stale_after: "<iso8601>"
sources:
  - id: official-doc
    resource: "<url_or_path>"
    title: "<API Documentation Title>"
platform: secops_siem     # valid: secops_siem, secops_soar, bindplane, gcp
sdk_capabilities:
  - <capability_id>       # must match WorkflowCapability in engine/registry.py
mcp_tools:
  - <mcp_tool_name>       # must match mcp_tool_name in engine/registry.py
related_concepts:
  - concept.<concept_name>
---

# <Feature Title>

## 1. Feature Purpose & Scope
<!-- What does this feature do, and when should an agent invoke it? -->

## 2. Underlying APIs & SDK Primitives
<!-- Exact Google SecOps / GCP / BindPlane endpoints and SDK workflows involved. -->

## 3. Input Parameters & Constraints
<!-- Cardinality (single, bounded, unbounded), pagination keys, and filter requirements. -->

## 4. Telemetry & Observable Metrics
<!-- Health dashboards, Looker tiles, or error logs associated with this feature. -->
