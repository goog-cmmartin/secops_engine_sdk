# Gas Town Autonomous Fleet: Architecture & Implementation Roadmap

> **Design Alignment**: Modeled upon Steve Yegge's Gas Town autonomous multi-agent coordination architecture, adapted for the Google SecOps (Chronicle SIEM & SOAR) Workflow Engine SDK.

---

## 1. Architectural Philosophy & Roles

Gas Town transforms a fleet of specialized AI agents from a reactive, interactive-only assistant into an **autonomous operational engineering workforce** capable of continuous vigilance, autonomous diagnosis, and gated production remediation.

```
                                  GAS TOWN ARCHITECTURE
                                  
                                    ┌──────────────────┐
                                    │    THE MAYOR     │
                                    │@secops-dispatcher│
                                    └────────┬─────────┘
                                             │ Coordinates
                        ┌────────────────────┴────────────────────┐
                        ▼                                         ▼
              ┌───────────────────┐                     ┌───────────────────┐
              │    THE DEACON     │                     │     POLECATS      │
              │  FleetScheduler   │                     │ Specialized Agents│
              │(Autonomous Cadence│                     │  (@feed-agent,    │
              │   Supervisor)     │                     │  @parser-doctor,  │
              └─────────┬─────────┘                     │  @identity-gov...)│
                        │                               └─────────┬─────────┘
                        │ Autonomous Audits                       │ Picks up beads
                        ▼                                         ▼
              ┌───────────────────┐                     ┌───────────────────┐
              │   EVIDENCE FABRIC │ ◄───────────────────┤   THE REFINERY    │
              │    BEADS/TODOS    │   Submits Proposals │  ProposalManager  │
              │  (secops_todos)   │                     │(Bors Preflight CI)│
              └───────────────────┘                     └───────────────────┘
```

### Core Gas Town Entities

| Entity | Role in Gas Town | SecOps Fleet Implementation |
| :--- | :--- | :--- |
| **The Mayor** | Singleton town orchestrator & dispatcher | [`@secops-dispatcher`](file:///home/admin_1823127835827_altostrat_co/Documents/secops_engine_sdk/agents/core/dispatcher.py) (ADK 2, GEAP engine, multi-agent router) |
| **The Deacon** | Continuous supervisory daemon | [`FleetScheduler`](file:///home/admin_1823127835827_altostrat_co/Documents/secops_engine_sdk/agents/core/fleet_scheduler.py) (30s cadence loop, health check heartbeats, autonomous bead slinging) |
| **Polecats** | Specialized ephemeral worker agents | 10 domain agents (`@feed-agent`, `@parser-doctor`, `@detection-tuning-agent`, `@detection-decay-agent`, `@identity-governor`, `@logjammer-agent`, `@rule-troubleshooter`, `@yaral-optimizer`, `@sql-analyst`) |
| **Beads** | Atomic, persistent tasks & issues | Evidence Fabric [`TodoTask`](file:///home/admin_1823127835827_altostrat_co/Documents/secops_engine_sdk/clients/web/server.py) (`secops_todos`), traceable by ID, stream, and topic |
| **Convoys** | High-level initiatives bundling beads | Multi-agent incident & refactoring initiatives with milestone completion bars |
| **The Refinery** | Gated merge queue & preflight CI | [`ProposalManager`](file:///home/admin_1823127835827_altostrat_co/Documents/secops_engine_sdk/engine/workflows/rule_health.py) (Bors-style invariant tests, unified diffs, HITL 1-click approvals) |

---

## 2. Completed Milestones

### Milestone 1: Slack Ergonomics & 4-Column Gas Town Board (COMPLETE)
- **Fleet Chat Navigation**: Full vertical sidebar for Streams & Topics, collapsible Direct Messages (Slack App model) with automatic thread routing, clean composer with floating `@` autocomplete.
- **Gas Town Tabbed Control Center**: Dedicated board layout featuring The Mayor status banner, summary metrics (Polecats, Telemetry Hooks, Active Issues, Convoys, Escalations), and 4 Kanban columns (Triage, In Progress, HITL Review, Merged).
- **Interactive Diff Inspection Modal**: Side-by-side / unified diff inspector displaying preflight CI check passes before production merge.

### Milestone 2: Proactive Deacon Patrols (COMPLETE & LIVE-VERIFIED)
- **Autonomous Fleet Scheduler (`FleetScheduler`)**: Background daemon running 30-second cadence evaluations with heartbeats and status telemetry (`healthy`, `idle`, `warning`).
- **5 Multi-Domain Patrol Cadences**:
  - `@feed-agent`: Every 4h (`audit_feeds` — Chronicle ingestion transport lag, P95 latency, quota rejections).
  - `@parser-doctor`: Every 6h (`audit_parsers` — SIEM Logstash normalizer drops, Drop Code 1, schema drift).
  - `@detection-tuning-agent`: Every 12h (`find_noisy_rules` — Top firing noisy detection rules, alert fatigue).
  - `@detection-decay-agent`: Every 24h (`run_decay_synchronization` — 90-day detection telemetry aggregation, rule decay).
  - `@identity-governor`: Every 24h (`run_identity_drift_audit` — GCP IAM privileges, custom roles, permission drift).
- **Autonomous Bead Slinging**: Automatically generates atomic `TodoTask` beads in Evidence Fabric (`secops_todos`) when anomalies are discovered.
- **Collaborative Channel Broadcasts**: Formats structured Markdown diagnostic cards and posts them directly to topic streams (`#ingestion > feed-health`, `#identity > iam-audit`, etc.).
- **Gas Town Deacon Patrols UI**: Dedicated tab with active supervisor card, dynamic heartbeat counter, 5 patrol cards with on-demand trigger buttons, and a live audit log table.

---

## 3. Future Gas Town Roadmap & Next Steps

When resuming the Gas Town implementation, execute the following milestones:

### Milestone 3: Autonomous Bead-to-Refinery Loop (Worker Execution)
- **Objective**: Transition pending Evidence Fabric beads into automated agent execution and change proposal generation.
- **Key Capabilities**:
  1. **Autonomous Bead Claiming**: Polecats poll or subscribe to Evidence Fabric for beads assigned to their handle (`status: PENDING`, `target_agent: @agent`).
  2. **Automated Preflight Diagnostics**: Agent runs relevant dry-run workflows (e.g. testing candidate YARA-L rule syntax, evaluating Logstash parser test payloads, validating IAM policy bindings).
  3. **Draft Change Proposal to Refinery**: Automatically converts diagnostic solutions into formal `Proposal` artifacts with diffs, risk classifications, and rollback procedures.
  4. **Bors Preflight CI Automation**: Refinery runs automated invariant verification tests against the proposal before surfacing it in the HITL review column.

### Milestone 4: Multi-Agent Convoys & Step-Level Streaming
- **Objective**: Provide end-to-end visibility into cross-agent incident response.
- **Key Capabilities**:
  1. **Convoy Grouping**: Allow The Mayor or an operator to bundle related beads across multiple agents (e.g., Ingestion Outage Convoy grouping `@feed-agent`, `@parser-doctor`, and `@logjammer-agent`).
  2. **Step-Level SSE Event Streaming**: Stream fine-grained workflow execution events (e.g., `step_started`, `query_executed`, `finding_extracted`) to the frontend chat and Convoy view in real-time.
  3. **Milestone Tracking**: Visual progress bars automatically calculate completion percentage based on child bead transitions (`TRIAGE` → `IN_PROGRESS` → `REFINERY` → `MERGED`).

### Milestone 5: Self-Healing & Closed-Loop Remediation
- **Objective**: Safe closed-loop remediation for low-risk, verified operational issues.
- **Key Capabilities**:
  1. **Policy-Governed Auto-Merge**: Operator-configured policies allowing automatic merge for low-risk changes (e.g., disabling an unparsed feed test source or adding a known benign filter) that pass 100% of preflight gates.
  2. **Automated Post-Merge Verification**: Deacon triggers a verification sweep immediately after a proposal merge to confirm the anomaly is cleared in live telemetry.
  3. **Automatic Rollback**: If post-merge verification detects regression, Refinery immediately creates and merges a reversion proposal.

---

## 4. Mandatory Invariants (AGENTS.md Compliance)

All Gas Town extensions must strictly preserve:
1. **Strict Origin of Production Data (Invariant #1)**: Zero mocks, fixtures, or synthetic data in production paths (`agents/`, `engine/`, `clients/`, `adapters/`). All data must originate from `SecOpsClient` communicating with live Google SecOps endpoints.
2. **Refinery Human-in-the-Loop Gating**: No agent may directly apply destructive mutations or production config changes without passing through the Refinery merge queue.
3. **Traceable Provenance**: Every bead and proposal must preserve the chain:
   `Finding → Workflow Step → API Call / Response → Raw Event IDs / Query`.
