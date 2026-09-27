# Agent Alignment — Action Plan

Source: finder-vs-fixer gap analysis (2026-09-26). Tracks progress across sessions.

**Problem:** 9 agents run scheduled patrols and find problems, but only one issue type (`parser_drop_spike`) can be claimed and worked by an agent end to end. All other findings become to-dos that need a human to act.

## Immediate actions (2026-09-26, after peer review)
A second agent reviewed this plan and agreed with S1–S5. Checking the code turned up three more problems (N1–N3). Run these in order. Each is small and has a test.

| # | Item | Where | Status |
|---|------|-------|--------|
| N1 | Running `open_issue` again on an existing issue overwrites it: status goes back to AVAILABLE and `attempts` and the lease are wiped. Every parser patrol resets `NEEDS_HUMAN` and the retry budget, so escalation never sticks. Fix: update in place (refresh observed state and evidence; keep status, attempts, lease; reopen only if CLOSED) | `lifecycle.open_issue` / `work_queue.publish_issue` | Done |
| S1 | Plane map: `detections`, `detection_rules` → `detection`; `soar_automation` → `automation`; `identity_governance`, `configuration_governance` → `governance`; `infrastructure` → `external` | `base_adk_agent.get_capability_profile` | Done |
| S2 | Router no longer creates `SOC-AUTO-*` issues. OPERATIONAL without a linked issue = record the observation only (the to-do already exists). URGENT = alert only. Update `test_knowledge_layer` (asserts at 189 and 214) | `communication_router.dispatch` | Done |
| A5 | Cloud status becomes information only: remove the `upstream_cloud_disruption` issue, keep the to-do and chat alert, close the existing `issue_upstream_cloud_status` once | `fleet_scheduler` cloud branch | Todo |
| N2 | Parser auto-close only runs when the issue is APPLIED/VALIDATING. If the problem clears while the issue is AVAILABLE or NEEDS_HUMAN, the issue stays open and an agent can still claim it. Close those too, as "resolved without a change" | `fleet_scheduler` parser branch | Todo |
| N3 | Merge does nothing for `PATCH_PARSER_CBN`, `REMEDIATE_FEED`, `CREATE_FINDINGS_REFINEMENT`: they fall through to `APPLIED_CUSTOM` and nothing is written to production, yet the proposal shows MERGED and the issue APPLIED. Fix: connect `CREATE_FINDINGS_REFINEMENT` → `curated_detections.refinements.create`. For action types with no executor, record `MERGED_MANUAL_APPLY_REQUIRED`, leave the issue open, and show "Apply manually" in the UI | `proposal_manager.approve_and_merge` | Todo |
| S5 | Test: every `requires_capabilities` set the scheduler emits must be met by at least one agent profile in that issue's plane | `tests/` | Todo |

**Next (after the items above):** A3 decay and A2 tuning. Both use `UPDATE_RULE_TEXT`, which really writes to production and goes through the stale-target check. Feed (A1) waits: there is no feed write capability, so a feed proposal can only recommend.

### Where this plan differs from the peer review
- "`@parser-doctor` is fully functional end to end": no. N3 means merging changes nothing in SecOps, and N1 means each patrol resets the issue.
- "Feed as the second autonomous slice": no feed write capability exists (`feed.*` has only get/search/audit). Rules are the better second slice.
- S2 fix: don't let the router create issues at all, rather than gating on "requests tracking + has playbook". Scheduler branches own issue creation.
- `infrastructure` → `external` (the enum value exists), not `platform`. This mostly stops mattering once A5 lands.
- The ~125 orphaned `SOC-AUTO` issues were cleaned up earlier; 1 remains in `.state/work_queue`.

## How work gets picked up today
Patrol findings take one of two paths:
1. **To-do** (`evidence_store.upsert_todo`): every patrol creates these. Each one carries a canned `action_prompt` and nothing else. A human has to click to send it to chat.
2. **Issue** (`lifecycle.open_issue` → work queue): the only thing `issue_worker` can claim. An agent claims an issue only if **all** of these hold:
   - the agent's plane (operational area) matches the issue's plane (`find_eligible_issues`)
   - the agent has every capability the issue requires
   - `ISSUE_PLAYBOOKS` has an entry for the issue type (today: only `parser_drop_spike`)
   - the agent has a `submit_*_proposal` tool (5 agents)

## Status
| # | Item | Phase | Status |
|---|------|-------|--------|
| S1 | Fix plane map: `"detection"` key vs manifest `"detections"`/`"detection_rules"` makes detection agents fall back to `platform` | 1 Plumbing | Todo |
| S2 | Stop the generic `SOC-AUTO-…` / `patrol_<action>` issue when a real issue already exists for the finding | 1 Plumbing | Todo |
| S5 | Check scheduler `required_capabilities` against the capabilities agents declare; fail loudly on a mismatch | 1 Plumbing | Todo |
| A1 | Feed failing or stale → issue + playbook → `@feed-agent` (`submit_feed_proposal`) | 2 Quick wins | Todo |
| A2 | Noisy rule → issue + playbook → `@detection-tuning-agent` (`submit_tuning_proposal`); depends on S1 | 2 Quick wins | Todo |
| A3 | Broken or decayed rule → issue + playbook → `@detection-decay-agent` (`submit_decay_proposal`); depends on S1 | 2 Quick wins | Todo |
| A4 | Rule performance: add a `@rule-troubleshooter` patrol → issue → `@yaral-optimizer` (`submit_rule_proposal`) | 2 Quick wins | Todo |
| A5 | Cloud status: make it information only (no issue), or fix the `cloud.audit_status` capability and the `data`/`platform` plane mismatch | 3 Cloud status | Todo |
| A6 | Findings agents can only report (IAM drift, posture drift, playbook decay, timestamp skew): per finding, add a proposal tool or send straight to Needs Attention | 4 Report-only | Todo |
| A7 | Shadowed curated rules: give `@rule-conflict-agent` a proposal tool or send to Needs Attention | 4 Report-only | Todo |
| A8 | Wire `@logjammer-agent` (`verify_proposal_with_replay`) into proposal validation before approval | 4 Report-only | Todo |
| S4 | Auto-close issues on a healthy patrol for every issue type (today only parser + cloud status) | 5 Lifecycle | Todo |
| S3 | Merge to-dos and issues: one record per problem, linked lifecycle, one kanban card | 5 Lifecycle | Todo |

## Gap table: patrol findings
| Patrol agent | Finding | To-do | Issue | Playbook | Can propose a fix | Blocker |
|---|---|---|---|---|---|---|
| `@parser-doctor` | Parser drops / unparsed logs | ✅ | ✅ `parser_drop_spike` | ✅ | ✅ `submit_parser_proposal` | None. Works end to end and auto-closes when healthy |
| `@feed-agent` | Feed failing or stale | ✅ | ❌ | ❌ | ✅ `submit_feed_proposal` | Needs issue + playbook (A1) |
| `@detection-tuning-agent` | Noisy rule | ✅ | ❌ | ❌ | ✅ `submit_tuning_proposal` | Needs issue + playbook; plane mismatch (A2, S1) |
| `@detection-decay-agent` | Broken or decayed rules | ✅ | ❌ | ❌ | ✅ `submit_decay_proposal` | Needs issue + playbook; plane mismatch (A3, S1) |
| `@detection-decay-agent` → `@rule-conflict-agent` | Shadowed curated rules | ✅ | ❌ | ❌ | ❌ | No proposal tool (A7) |
| `@identity-governor` | IAM privilege drift | ✅ | ❌ | ❌ | ❌ | Can only report (A6) |
| `@tenant-posture-agent` | Configuration drift | ✅ | ❌ | ❌ | ❌ | Can only report (A6) |
| `@playbook-decay-agent` | SOAR playbooks degrading | ✅ | ❌ | ❌ | ❌ | Can only report (A6) |
| `@timestamp-integrity-agent` | Timestamp skew | ✅ | ❌ | ❌ | ❌ | Can only report; the fix would be a parser or feed change owned by other agents (A6) |
| `@cloud-status-agent` | Upstream Google Cloud incident | ✅ | ✅ `upstream_cloud_disruption` | ❌ | n/a | Can never be claimed: requires `cloud.audit_status` (agent has `gcp_status.*`); agent plane `platform` vs issue plane `data` (A5) |

## Agents that can fix things but never find anything themselves
| Agent | Can propose a fix | Gets work from | Blocker |
|---|---|---|---|
| `@yaral-optimizer` | ✅ `submit_rule_proposal` (`rule.patch`) | Nothing scheduled | No patrol emits rule-performance issues (A4) |
| `@logjammer-agent` | Checks proposals (`verify_proposal_with_replay`) | Nothing | Not wired into proposal validation (A8) |
| `@rule-troubleshooter`, `@raw-log-agent`, `@namespace-label-agent`, `@log-cost-agent`, `@mitre-attack-agent`, `@gcp-telemetry-agent`, `@tenant-cartographer`, `@sql-analyst` | ❌ | Chat only | Not scheduled and can't propose; they only answer questions |

## Structural problems (detail)
| # | Problem | Where | Effect |
|---|---|---|---|
| S1 | Plane lookup has key `"detection"`; manifests say `"detections"` / `"detection_rules"`, so these agents fall back to `platform` | `agents/core/base_adk_agent.py` `get_capability_profile` | Detection issues would be invisible to detection agents even once a playbook exists |
| S2 | Every patrol that creates to-dos also opens a generic issue (no capability requirements, no playbook) | `agents/core/communication_router.py` `_create_issue_for_observation` | Issues that can never be claimed pile up. The parser patrol writes 3 records per finding |
| S3 | To-dos and issues are separate systems with no link between them | `evidence_store` vs `work_queue` | UI shows the same problem twice; resolving one doesn't close the other |
| S4 | Only the parser and cloud-status patrols auto-close their issue when things go healthy again | `agents/core/fleet_scheduler.py` `_create_patrol_beads` | Other issues, once they exist, stay open forever |
| S5 | Capability requirements are hand-written strings in the scheduler | `agents/core/fleet_scheduler.py` | Mismatches fail silently (e.g. `cloud.audit_status`) |

## Notes
- Findings come from reading the code, not from a live patrol run. Confirm S1 and S2 with a quick test before changing anything.
- Adding a playbook = an `ISSUE_PLAYBOOKS` entry + scheduler code that opens the issue (plane, required capabilities) + auto-close on a healthy result (S4).
- Proposals still go through `approval_policy` tier checks and the `target_baseline` stale-target check (409 if the target changed); workers never merge anything directly.
