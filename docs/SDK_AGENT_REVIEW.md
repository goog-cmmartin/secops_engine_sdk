# SDK Review — Agent Action Path (Phase 1)

Source: Phase 1 of the agent verification plan (2026-09-26). Scope: only the SDK calls agents actually make and the writes `proposal_manager` performs. This is not a general code-quality audit.

Method: built the registry with a stub adapter (`SecOpsEngine(adapter=stub, custom_registry=WorkflowRegistry())`), cross-referenced all 22 manifests, statically scanned `agents/**` for `engine.<method>(` calls, and probed the write paths with a recording adapter. No production calls were made.

## Headline
- **Plumbing is sound.** All 206 capabilities register. Every capability in the 22 manifests exists. All 59 distinct engine methods called from agents exist on `SecOpsEngine`.
- **Three write paths exist:** rule text, rule deployment, curated refinement. Parser, feed, SOAR and IAM have **no write capability** in the SDK.
- **Found 2 silent-corruption bugs** in the write paths (G1, G2) and **1 misleading preflight** (G3). Fix these before any autonomous-path verification.

## Capability matrix (agent-relevant planes)
| Plane | Read | Propose (agent → action_type) | Write executor | Stale-target check | Pre-merge dry-run | Rollback |
|---|---|---|---|---|---|---|
| Rule text | ✅ 9 queries | `@yaral-optimizer`, `@detection-decay-agent` → `UPDATE_RULE_TEXT` | ✅ `patch_rule` | ✅ revision + text hash | ✅ `rule.verify` | ❌ prior text not stored |
| Rule deployment | ✅ | none (human only via `HUMAN_ONLY_ACTIONS`) | ✅ `update_rule_deployment` | ✅ enabled/alerting | n/a | ❌ |
| Curated refinement | ✅ 6 queries | `@detection-tuning-agent` → `CREATE_FINDINGS_REFINEMENT` | ✅ `create_findings_refinement` | ❌ no baseline | ⚠️ `refinements.test` exists; see G3 | ⚠️ `refinements.delete` exists, created ID not linked |
| Parser | ✅ 6 queries | `@parser-doctor` → `PATCH_PARSER_CBN` | ❌ none | ❌ | ✅ `parser.run` (runParser) | ❌ |
| Feed | ✅ 5 queries | `@feed-agent` → `REMEDIATE_FEED` | ❌ none | ❌ | ❌ | ❌ |
| SOAR playbook | ✅ 4 queries | none | ❌ none | — | — | — |
| IAM / posture | ✅ 3 + 30 queries | none | ❌ none | — | — | — |
| Data tables | ✅ 3 | none | writes exist (5) but no agent uses them | — | — | — |
| Cases | ✅ 3 | none | writes exist (10) but no agent uses them | — | — | — |

`GENERIC_CAPABILITY` has an executor (`engine.execute(cap_id, **kwargs)`) and is human-only, but no agent emits it.

## Gaps, ranked by agent paths unblocked or protected
| # | Gap | Evidence | Impact | Fix size |
|---|---|---|---|---|
| G1 | **`curated_rule_ids` given as a string splits into characters.** `create_findings_refinement(..., curated_rule_ids="ur_1")` sends `curatedRules/u`, `/r`, `/_`, `/1`. Breaks Principle 3 (flexible collections) | Adapter probe; `adapters/google_secops.py:1344` iterates the value directly | Tuning path (A2) writes a refinement against the wrong rules. `proposal_manager` wraps the ID in a list, so it's safe today, but LLM tool calls and `GENERIC_CAPABILITY` are not | S: coerce str → `[str]` in facade |
| G2 | **`enabled="false"` is sent as the string `"false"`.** No bool coercion in `update_rule_deployment`; `mutation_payload` is JSON from an LLM or UI | Adapter probe: body `{'enabled': 'false'}` | Deployment toggles could do the opposite of what was approved, or be rejected by the API | S: strict bool coercion in facade, reject anything ambiguous |
| G3 | **The tuning agent's preflight calls `verify_rule` (YARA-L compiler) on a refinement query**, which is UDM filter syntax, not a rule. `curated_detections.refinements.test` is declared but not used for this | `detection_tuning_agent.py:321` | `syntax_verified` on refinement proposals doesn't mean what it says, and the approval policy trusts it | S: call `test_findings_refinement` instead |
| G4 | **No parser write capability.** `parser.run` only tests a parser | Matrix | `parser_drop_spike`, the only complete issue path, ends in manual apply | M: parser extension create/activate in adapter + facade + executor + baseline |
| G5 | **No feed write capability** | Matrix | A1 can only recommend | M: feed patch/enable in adapter + facade + executor + baseline |
| G6 | **Refinement has no stale-target check or idempotency.** `supports_baseline` covers only rule actions | `target_baseline.py:47` | Re-approving or retrying can create duplicate refinements | S–M: pre-merge existence check on display name + query |
| G7 | **No rollback data.** The executor stores `execution_result` but not the prior rule text or created refinement ID in a form a revert can use | `proposal_manager.py` | The verification harness can't assert "undo works"; operators revert by hand | M |
| G8 | **Capability `kind` taxonomy mislabels reads and dry-runs as writes**, and no primitive declares `side_effects` (only `mitre.sync_cache` does). Mislabelled: `curated_detections.tuning.{top_noisy_rules,entity_cardinality,case_history}`, `curated_detections.refinements.test`, `parser.run`, `case_alert.fetch_recommendation` | Registry dump; `derive_kind` defaults everything not in `READ_VERB_SUFFIXES` to `primitive` | Only consumer today is the capability listing (`server.py:439`), but this metadata **can't** be used to limit what an agent may do autonomously until fixed | S: explicit `kind="query"` + `side_effects` on real writes; contract test |
| G9 | Identifier normalisation gaps (Principle 5): `get_feed(123)` raises `AttributeError`; `patch_rule(rule_id=...)` alias rejected | Probe | Tool-call failures from LLM callers; low blast radius (reads, or loud failure) | S |
| G10 | `SecOpsEngine` has no `verify_rule_text`; agents use `verify_rule` (fine). Only the adapter method name differs | Probe | None. Recorded so the harness uses the right name | — |

## Effect on the verification plan (Phase 2)
- **Fix before the harness:** G1, G2, G3. They are small, and they change what the harness should assert on the only writes that run today.
- **The first complete autonomous paths remain A3/A2** (`UPDATE_RULE_TEXT`, `CREATE_FINDINGS_REFINEMENT`), as expected. A2 needs G3 and G6 to be trustworthy.
- **Parser and feed stay "apply manually"** until G4 or G5. The harness should assert `MANUAL_APPLY_REQUIRED` + `mark-applied` for them now, not treat them as failures.
- **G8 is a precondition** for any "tier 1 autonomous" policy based on capability metadata. Not needed for Phase 2.
- Replay harness: the recording-adapter technique used here (stub `_request`, capture method/path/body) is enough for write-path assertions without recorded fixtures.

## Recommended order
1. G1, G2, G3 (one small PR with unit tests)
2. G8 taxonomy fix + contract test
3. G6 refinement idempotency
4. Phase 2 harness
5. G4/G5 (parser/feed writes) as separate designs, each with baseline + rollback (G7)

## Live tenant findings (2026-09-26, internal demo tenant, read-only)
Probe: `scripts/live_probe.py` (blocks everything except GET, `:verifyRuleText`, `:testFindingsRefinement`; log in `.state/live_probe_log.jsonl`). 22/22 calls succeeded; no changes made on the tenant.

| # | Finding | Effect | Fix |
|---|---|---|---|
| **L1 (new, high)** | `_map_rule_deployment` (`engine/workflows/detection_rules.py:99`) treats `executionState == ACTIVE` or any `runFrequency` in LIVE/HOURLY/DAILY as "enabled". The API **leaves out `enabled` / `alerting` when false** and always returns `runFrequency`. On this tenant the SDK reports **200/202 enabled; the true count is 81** (77 alerting) | Every `RuleDeployment.enabled` is effectively always true: CLI output, `rule_agent`, `rule_conflict.is_live` (`rule_conflict.py:405` also ORs `run_frequency == "LIVE"`), and any baseline or approval logic that reads it | S: `enabled=bool(raw.get("enabled", False))`; drop the `run_frequency` OR in `rule_conflict`. Add a unit test using the real response shape (no `enabled` key) |
| G1 | Confirmed the API accepts a list of full `curatedRules/ur_…` names. Couldn't check how the API handles a split-character ID (hit quota) | Unchanged: fix in the SDK, don't rely on the API rejecting it | as planned |
| G3 | `testFindingsRefinement` works on this tenant. Valid query → activity list; invalid query → **400 with a precise parse error**. `verifyRuleText` rejects UDM filter syntax because it expects a full rule | Confirms G3: switch preflight to `test_findings_refinement` and treat 400 as a syntax failure | as planned |
| G3a (new) | `testFindingsRefinement` has a **very low quota** (429 after ~4 calls in a minute, even after 5 backoff retries) | A preflight on every proposal, or a batch retune, will hit 429 | Cache the result per (query, rules) and treat 429 as "unverified", not "invalid" |
| G3b (new) | That endpoint's error body is a **JSON array** `[{"error":…}]`. `_request` expects an object, so the whole raw body ends up in the message | Noisy errors shown to LLMs and operators | S: unwrap `list[0]` in `_request` error parsing |
| G6 | Tenant has **0 findings refinements**, so we can't see whether the API checks `etag` on refinements. Rules do return `etag` | Idempotency has to be client-side (display name + query match), as planned | as planned |
| G9 | Rule IDs: `ru_<uuid>` and full resource names both work; a bogus `ru_` returns 404, a non-`ru_` string returns **400 "invalid rule_id"**. Rule paths work with either project ID or project number | Error messages are clear; the SDK can check the `ru_` prefix locally and give a better hint | S |
| — | Inventory: 202 rules, 474 curated rules / 221 rule sets, 8 feeds (ACTIVE/INACTIVE/SUCCEEDED), 1 data table, 1 reference list, 150 parsers, 2 retrohunts. `verifyRuleText` success/diagnostic shapes match `detection_rules.py:175` | Recorded shapes can seed Phase 2 replay fixtures | — |

**Revised order:** L1 + G1 + G2 + G3 (+G3a/G3b) in one small PR → G8 → G6 → Phase 2 harness.
