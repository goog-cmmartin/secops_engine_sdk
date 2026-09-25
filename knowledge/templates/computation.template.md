---
id: computation.<computation_name>
type: Attested Computation
title: "<Computation Title>"
description: "<Brief description of what this computation calculates>"
tags:
  - secops
  - yaral
  - attested
runtime: yaral_2  # valid: yaral_2, bigquery, looker, python
parameters:
  - name: <param_name>
    type: integer
    required: true
executor:
  resource: knowledge/tasks/<persona_name>/<task_name>.md
  receipt: [query_text, executed_time_range, result_rows]
attester:
  resource: knowledge/attesters/yaral_equality.py
generated: { by: "<actor>", at: "<iso8601>" }
verified:
  - { by: "human:<reviewer_id>", at: "<iso8601>" }
status: stable  # valid: draft, stable, deprecated
stale_after: "<iso8601>"
sources:
  - id: <source_id>
    resource: "<url_or_path>"
    title: "<Source Title>"
---

# Computation

```sql
// Sanctioned query body here
```

# Description & Logic

<!-- Narrative explanation of the computation and its business/security rules. -->

# Attestation Contract

<!-- Notes on what the deterministic attester verifies in the executor's receipt. -->
