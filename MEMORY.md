# Project Memory Index

Table of contents for project documentation and governance.

## Documentation

- [README.md](README.md) — Project overview, quickstart, SDK/CLI usage, repository structure.
- [AGENTS.md](AGENTS.md) — Non-negotiable invariants, classification taxonomy (status + kind/domain/cardinality axes), agent role profiles, the discovery→verification loop, and the capability Definition-of-Done checklist.
- [docs/CAPABILITIES.md](docs/CAPABILITIES.md) — Generated capability reference (all registered capabilities by kind/domain/cardinality). Regenerate with `python scripts/generate_capabilities_doc.py`.
- [docs/UDM_STATS_SYNTAX.md](docs/UDM_STATS_SYNTAX.md) — Query language reference and canonical examples for UDM Stats Search (aggregations, match/outcome clauses, entity graph, detections).

## Reports & Artifacts

- [reports/M1_CAPABILITY_REPORT.md](reports/M1_CAPABILITY_REPORT.md) — Milestone 1.1 capability & robustness report (UDM Search slice). Point-in-time record.
- [discovery/observations/01_udm_search_discovery.md](discovery/observations/01_udm_search_discovery.md) — Live UDM search behavior/API observations.
- [discovery/observations/udm_stats_search.md](discovery/observations/udm_stats_search.md) — Live UDM stats search behavior, LRO polling, and schema observations.
- [tests/UDM_SEARCH_TEST_INVENTORY.md](tests/UDM_SEARCH_TEST_INVENTORY.md) — UDM search test inventory.
