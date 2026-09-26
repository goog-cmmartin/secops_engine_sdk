# Web UI Review — Work Plan

Source: UI review of `clients/web/static/` (2026-09-25). UX re-review added 2026-09-26 (Groups 5–7). Tracks progress across sessions.

## Status
| # | Item | Group | Status |
|---|------|-------|--------|
| 1 | showToast(type, message) arg order reversed at call sites | 1 Bugs | Done |
| 2 | Fabricated fallback metrics / hardcoded HTML values → "—"/stale | 1 Bugs | Done |
| 3 | Shift-briefing narrative bypasses DOMPurify → use formatMarkdown() | 1 Bugs | Done |
| 4 | SSE disconnect invisible → live dot states + banner + resync | 1 Bugs | Done |
| 5 | Operator-facing terminology (keep internal names in code) | 2 Polish | Done |
| 6 | Replace confirm()/prompt() for approve/reject/claim with modal + required reason | 2 Polish | Done |
| 9 | Tidy top bar: move build tags to About; add open proposals/escalations/connection | 2 Polish | Done |
| 10 | Actions summary cards clickable → sub-tab; alert strip links to review column | 2 Polish | Done |
| 7 | Accessibility: focus-visible, tablist roles, aria-live, icon button labels | 3 A11y | Done |
| 8 | Minimum 11px text | 3 A11y | Done |
| 4a | Inline onclick → delegated `data-act` listener | 4 Cleanup | Done |
| 4b-1 | Hard-coded colours → theme tokens (app.js, index.html, status classes in style.css) + AA contrast | 4 Cleanup | Done |
| 4b-2 | Remaining inline layout `style=` → CSS classes | 4 Cleanup | Todo |
| 4c | Module split of app.js (~8.1k lines) | 4 Cleanup | Todo |
| 11 | Approval surfaces still show fabricated data (see below) | 5 Trust | Done |
| 12 | Diff modal: cancel in approve/reject dialog still closes modal; no Esc/backdrop/focus trap | 5 Trust | Done |
| 13 | Unescaped values interpolated into inline onclick (kanban Triage/Inspect, escalation Resolve) | 5 Trust | Done |
| 14 | Escalation "Ack" is a no-op toast — wire to backend or remove | 5 Trust | Done |
| 15 | Send failure: input cleared before POST, text lost; optimistic msg stuck grey; alert() | 6 Chat | Done |
| 16 | "Sending…" CSS targets `.msg-meta` (doesn't exist; header is `.msg-header`) | 6 Chat | Done |
| 17 | Auto-scroll yanks reader to bottom on every message → stick-if-near-bottom + "New messages ↓" pill | 6 Chat | Done |
| 18 | Day separators + relative dates (history now persists across sessions) | 6 Chat | Done |
| 19 | Unread badges per topic/DM from SSE `new_message` for inactive channels | 6 Chat | Done |
| 20 | Composer auto-grow (rows=1, no resize) | 6 Chat | Done |
| 21 | Agent-status 180s timeout hides silently → show "no response yet — still running?" state | 6 Chat | Done |
| 22 | Back/forward: switchTopic/switchView use replaceState → pushState | 6 Chat | Done |
| 23 | Drawer proposals: click opens diff modal for any subsystem; default filter OPEN; drop ".proposals/" copy | 7 Actions | Done |
| 24 | Lease "Ns left" frozen at render → absolute expiry time or ticking countdown | 7 Actions | Done |
| 25 | Claim dialog free-text handle → select from capable workers (already fetched) | 7 Actions | Done |
| 26 | Toasts: aria-live, close button, errors persist until dismissed | 7 Actions | Done |
| 27 | Audit Rules / MITRE header buttons: check res.ok, toast on failure (currently console-only) | 7 Actions | Done |
| 28 | On-screen load errors with Retry (replaces console-only catch blocks) | 3 Resilience | Done |
| 29 | Empty chat: per-topic suggested prompts instead of trash icon | 3 Resilience | Done |
| 30 | Quick switcher (Ctrl/Cmd+K): topics, DMs, pages, recent & unread | 3 Resilience | Done |
| 31 | Narrow screens (≤1024px): off-canvas sidebar + scrim, overlay proposals drawer, compact top bar | 3 Resilience | Done |
| 32 | Last native confirm()/alert(): tuning deploy + clear topic → openActionDialog + toasts | 8 Follow-up | Done |
| 33 | Work queue: keep rows while refreshing, drop stale responses, "Clear filters" empty state | 8 Follow-up | Done |

## #11 fabricated data on approval surfaces
- `openGastownDiffModal`: preflight box always renders "Invariant/Backtest/Zero-Synthetic: PASS" + "validated against live API" regardless of `p.preflight`.
- `openGastownDiffModal`: fallback fake diff (`- old_statement / + new_statement`) and fallback rationale text.
- `renderGastownRefinery`: gates = syntax + replay **+ 1**, badge always green "✓ N/3 GATES PASSED"; diff stats fall back to `|| 3` / `|| 1`.
- Fix: render from `p.preflight` (same logic as `renderProposalWidget`), "No diff attached" / "No rationale provided", real counts incl. 0, amber/red badge when gates missing.

## Group 5 notes (done 2026-09-26)
- `jsArg()` helper (app.js) = safe JS string literal for inline handlers; applied to all Actions-board/work-queue/escalation/refinery handlers. Older chat-widget handlers (~1263–4948) still use `'${escapeHtml(x)}'` — safe against HTML but break on apostrophes; migrate with #4 Cleanup.
- Escalation acks: `POST /api/gastown/escalations/{id}/ack` → `.state/escalation_acks.json`. `summary.escalation_count` = unacked; `escalation_total` = all. Ages derived from `created_at`.
- Defined missing `.badge-green/-yellow/-red/-blue/-gray` (previously unstyled). SOC issue modal now uses `.gt-modal-overlay`/`.gt-modal-card` (had no CSS).
- Tests: `EscalationAckAndApprovalTrustTest` in tests/test_gas_town_coherence.py.

## Group 6 notes (done 2026-09-26: #15, #16, #17, #20)
- Send: `sendChatMessage()` tracks its own optimistic card; reconciles from POST response (id) or SSE (id, else content match). Failure → red card with Retry/Edit + error toast; no alert().
- De-dupe: cards carry `data-id`; `appendMessageToTimeline()` skips ids already rendered.
- Scroll: `appendMessageToTimeline(msg, {live|forceScroll})`; follows only when within 80px of bottom, otherwise `#newMessagesPill` counts unseen messages.
- Composer: auto-grows 48→200px, including programmatic `input.value = …` prefills (value setter intercepted on the element).
- Verified with a QuickJS DOM-stub harness (failure/edit/retry/dup/race/scroll); autosize needs a browser check.

## #9 / #10 notes (done 2026-09-26)
- Top bar: "ADK 2"/"HITL Review" tags → About dialog (ⓘ; reads `/api/health`, now incl. `version`). Right side = escalations chip (unacked; amber when >0, "—" when overview unavailable; → Actions/Escalations), agents chip (→ Agent Library), connection chip (Live/Connecting…/Offline, replaces unlabeled brand dot). Actions nav badge = open proposals, hidden at 0 (was permanently `display:none`).
- Overview loaded at startup + every 60s while tab visible + on SSE proposal messages, so top-bar counts are live outside Actions.
- Summary cards are `<button data-gt-target>`; sub-tab targets get `.is-active`/`aria-current`. Polecats → Agent Library, Hooks → Dashboards. Alert pill is a button (disabled when all clear) → Kanban, scrolls + flashes review column (reduced-motion safe).
- `openActionDialog` gained `bodyHtml` (trusted, caller-escaped) and `showCancel`.
- Verified: `.venv/_jscheck/g9check.py` (26 checks) + uxcheck/g7check still green.

## #32 / #33 notes (2026-09-26)
- No `confirm()`/`alert()` left in app.js. Deploy and clear-topic dialogs use `variant: "danger"`; `openActionDialog` now focuses **Cancel** by default for danger dialogs with no inputs (stray Enter can't deploy/wipe).
- Deploy: all matching buttons disabled + `aria-busy` "Deploying…" in flight; success leaves "✓ Deployed" (disabled), failure restores. HTTP errors via `describeHttpError`.
- Clear topic: success toast; only wipes the timeline if the operator is still on that topic.
- Work queue: `setTableRefreshing()` dims tbody + `aria-busy` instead of replacing rows; `workQueueRenderSeq` discards out-of-order responses (filter spam, lease ticker, post-action reloads). Issues/workers fetched with `allSettled` so one failing doesn't blank the other. Filtered-empty state has "Clear filters". Inline `onchange` removed from filters.
- Verified: `.venv/_jscheck/g4check.sh` (33 checks) + g3check (34) green.

## #5 terminology map (screen text only)
| Current | Suggested |
|---|---|
| Polecats (Agents) | Agents |
| Deacon Patrols / Heartbeat | Scheduled Audits / Scheduler health |
| Convoys | Work Packages |
| Refinery Merge Queue | Change Queue |
| Telemetry Hooks | Data Sources |
| The Mayor | Fleet Coordinator |
| Beads (dispatched) | Tasks (opened) |
| Patrol / Sweep | Audit / Run |

## Medium priority (backlog)
- Backend: `POST /api/mitre/audit` and MITRE ATT&CK coverage assessment engine/endpoints now merged and operational.
- Diff modal shows raw diff text; chat widget uses coloured formatUnifiedDiff() — unify
- Hardcoded counts in copy ("5 Active Patrols", "Sweeping all 5 fleet patrol cycles")
- 3 pre-existing failures in tests/test_chat_server.py (dispatcher/yaral-optimizer/agent library) — need LLM creds; same stub-vs-live split as test_mitre_agent.py
- Done: /api/mitre/* engine calls offloaded via asyncio.to_thread (add_message stays on loop); test_mitre_agent.py split offline (_InertAdapter + LocalFileEvidenceStore) vs live
- Per-view URLs (hash routing for Actions sub-tabs / briefing tabs)
- Kanban review column: highlight + "oldest: Nh"

## #7 / #8 notes (2026-09-26)
- #8: every `font-size` < 11px (CSS, inline HTML, JS templates; 169 sites) raised to 11px.
- #7: skip link + `#mainContent` landmark; labelled `nav`/`aside`s; all 4 tab groups are `tablist`/`tab`/`tabpanel`
  with arrow/Home/End keys; `aria-selected`, roving tabindex and nav `aria-current` mirror `.active` through a
  MutationObserver in `setupA11y()` (so the switch* functions stay unchanged); drawer tabs are now `<button>`s;
  sidebar stream/topic/DM rows and kanban cards are focusable `role=button` with Enter/Space, and focus survives re-renders;
  drawer toggle / DM section expose `aria-expanded`; 15 unlabelled inputs/selects now labelled; `#srAnnouncer`
  polite live region announces agent replies; global `:focus-visible` ring; `prefers-reduced-motion`; Knowledge Graph shows ↗ + "(opens in new tab)".
- Remaining a11y follow-ups: inline `onclick` buttons in chat widgets still carry low-contrast inline colours (see #4 Cleanup);
  no automated axe run yet.

## #4b-1 notes (done 2026-09-26)
- Semantic palette in style.css: `--c-<tone>` (text), `-solid` (fill behind `--on-solid`), `-bg`/`-faint`/`-bd` (color-mix tints). Tones: ok, danger, warn, high, info, sky, indigo, violet, neutral. Separate dark/light values.
- app.js + index.html: 0 literal hex/rgba colours left. Also defined 7 tokens that were referenced but never defined (`--bg-surface`, `--bg-card`, `--text-bright`, …).
- style.css: badge-open/merged/rejected, badge-green/yellow/red/blue, badge-tag, dps-badge, decay-flag-tag, lease-expiry, btn-approve, preflight-box now use tokens (previously dark-only literals, unreadable in light theme). `.diff-container` stays dark in both themes but now sets its own base text colour.
- Verified: headless-Chrome WCAG contrast scan of all 21 chat-widget renderers (empty + populated fixtures), 0 AA failures in both themes; full index.html load has 0 JS errors; uxcheck/g7check/g9check green.
- About 200 literal colours remain in non-status style.css rules (layout chrome); migrate with 4b-2.

## Group 3 notes (done 2026-09-26: #28–#31)
- `fetchJsonOrThrow()` + `showLoadError(target, {title, error, retry, colspan})`: inline ⚠ + Retry, "Server unreachable" for network errors. Applied to 15 loaders (sidebar, messages, drawer, dashboards, work queue, audits, briefings, library). `keepLoadError()` stops sidebar re-renders from wiping the error while the list is empty.
- `TOPIC_PROMPTS` / `renderEmptyTimeline()`: chips prefill the composer with an @mention of the owning agent (editable before send); hidden if the agent isn't registered.
- Quick switcher: combobox/listbox ARIA, ↑↓/Enter/Esc, focus restore, recent channels in localStorage (`secops_recent_channels_v1`). `anyModalOpen()` checks rendered visibility. The old `:not([hidden])` guard counted the `display:none` diff/SOC modals as open, which blocked Ctrl+K everywhere.
- Verified: `.venv/_jscheck/g3check.sh` (34 headless-Chrome checks: main / fetch-failure / 800px), ovfcheck at 1440/1024/760 with no overflow, uxcheck/g7check/g9check green.
