---
id: concept.<concept_name>
type: concept
title: "<Concept Title>"
description: "<One-sentence summary of this concept for agent progressive disclosure>"
tags:
  - secops
  - schema
  - architecture
status: stable  # valid: draft, stable, deprecated
generated: { by: "<actor>", at: "<iso8601>" }
verified:
  - { by: "human:<reviewer_id>", at: "<iso8601>" }
stale_after: "<iso8601>"
sources:
  - id: official-doc
    resource: "<url_or_path>"
    title: "<Documentation Title>"
applies_to:
  - secops_siem      # valid: secops_siem, secops_soar, bindplane, gcp
related_features:
  - feature.siem.<feature_name>
---

# <Concept Title>

## 1. Overview & Mental Model
<!-- Concise explanation of what this concept is and how an AI agent should reason about it. -->

## 2. Architecture & Data Structures
<!-- Technical breakdown of schemas, state transitions, or pipeline topologies. -->

## 3. Operational Guarantees & Constraints
<!-- Guarantees, boundaries, latency expectations, or quotas. -->

## 4. Cross-System Dependencies
<!-- How this concept touches GCP, BindPlane, SIEM, or SOAR. -->
