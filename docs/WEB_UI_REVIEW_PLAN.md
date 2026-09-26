# Web UI Review — Work Plan

Source: UI review of `clients/web/static/` (2026-09-25). UX re-review added 2026-09-26 (Groups 5–7). Tracks progress across sessions.

## Status
| # | Item | Group | Status |
|---|------|-------|--------|
| 1 | showToast(type, message) arg order reversed at call sites | 1 Bugs | Done |
| 2 | Fabricated fallback metrics / hardcoded HTML values → "—"/stale | 1 Bugs | Done |
| 3 | Shift-briefing narrative bypasses DOMPurify → use formatMarkdown() | 1 Bugs | Done |
| 4 | SSE disconnect invisible → live dot states + banner + resync | 1 Bugs | Done |
| 5 | Operator-facing terminology (keep internal names in code) | 2 Polish | Todo |
| 6 | Replace confirm()/prompt() for approve/reject/claim with modal + required reason | 2 Polish | Done |
| 9 | Tidy top bar: move build tags to About; add open proposals/escalations/connection | 2 Polish | Todo |
| 10 | Actions summary cards clickable → sub-tab; alert strip links to review column | 2 Polish | Todo |
| 7 | Accessibility: focus-visible, tablist roles, aria-live, icon button labels | 3 A11y | Todo |
| 8 | Minimum 11px text | 3 A11y | Todo |
| — | Module split, inline styles → theme tokens, inline onclick → listeners | 4 Cleanup | Todo |
| 11 | Approval surfaces still show fabricated data (see below) | 5 Trust | Done |
| 12 | Diff modal: cancel in approve/reject dialog still closes modal; no Esc/backdrop/focus trap | 5 Trust | Done |
| 13 | Unescaped values interpolated into inline onclick (kanban Triage/Inspect, escalation Resolve) | 5 Trust | Done |
| 14 | Escalation "Ack" is a no-op toast — wire to backend or remove | 5 Trust | Done |
| 15 | Send failure: input cleared before POST, text lost; optimistic msg stuck grey; alert() | 6 Chat | Todo |
| 16 | "Sending…" CSS targets `.msg-meta` (doesn't exist; header is `.msg-header`) | 6 Chat | Todo |
| 17 | Auto-scroll yanks reader to bottom on every message → stick-if-near-bottom + "New messages ↓" pill | 6 Chat | Todo |
| 18 | Day separators + relative dates (history now persists across sessions) | 6 Chat | Todo |
| 19 | Unread badges per topic/DM from SSE `new_message` for inactive channels | 6 Chat | Todo |
| 20 | Composer auto-grow (rows=1, no resize) | 6 Chat | Todo |
| 21 | Agent-status 180s timeout hides silently → show "no response yet — still running?" state | 6 Chat | Todo |
| 22 | Back/forward: switchTopic/switchView use replaceState → pushState | 6 Chat | Todo |
| 23 | Drawer proposals: click opens diff modal for any subsystem; default filter OPEN; drop ".proposals/" copy | 7 Actions | Todo |
| 24 | Lease "Ns left" frozen at render → absolute expiry time or ticking countdown | 7 Actions | Todo |
| 25 | Claim dialog free-text handle → select from capable workers (already fetched) | 7 Actions | Todo |
| 26 | Toasts: aria-live, close button, errors persist until dismissed | 7 Actions | Todo |
| 27 | Audit Rules / MITRE header buttons: check res.ok, toast on failure (currently console-only) | 7 Actions | Todo |

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

## #5 terminology map (screen text only)
| Current | Suggested |
|---|---|
| Polecats (Agents) | Agents |
| Deacon Patrols / Heartbeat | Scheduled Audits / Scheduler health |
| Convoys | Work Packages |
| Refinery Merge Queue | Change Queue |
| Telemetry Hooks | Data Sources |

## Medium priority (backlog)
- Remaining native confirm()/alert(): noise-exclusion deploy, clear-topic, send failure — migrate to openActionDialog()/showToast()
- Diff modal shows raw diff text; chat widget uses coloured formatUnifiedDiff() — unify
- Work-queue filter change wipes table with "Refreshing…" — keep rows, show inline spinner
- Hardcoded counts in copy ("5 Active Patrols", "Sweeping all 5 fleet patrol cycles")
- Empty chat state uses trash icon; offer per-topic suggested prompts instead
- Quick switcher (Ctrl/Cmd+K) for streams/topics/DMs
- 4 pre-existing failures in tests/test_chat_server.py (agent library/dispatcher) — unrelated to UI work
- Knowledge Graph nav opens new tab — add external-link icon or bring in-app
- Per-view URLs (hash routing for Actions sub-tabs / briefing tabs)
- On-screen errors with Retry instead of console-only catch blocks
- Kanban review column: highlight + "oldest: Nh"
- Narrow-screen breakpoints (<1200px)
- prefers-reduced-motion
