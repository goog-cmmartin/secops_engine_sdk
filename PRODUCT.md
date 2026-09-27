# Product

<!-- impeccable:product-schema 1 -->

## Platform

web (desktop only; no tablet/mobile target at this time)

## Users

Primary: security platform engineers and SecOps leads responsible for the
*health of the SIEM itself*, not alert triage. Their remit spans access and
authorization, log source / feed configuration, parser maintenance, detection
rule hygiene, and data-quality issues. They check in several times a day
rather than living in the console, and approve or action work in batches.

Not the primary user: Tier-1 analysts triaging alerts.

## Product Purpose

A control room that shows a fleet of autonomous agents doing platform
maintenance work against a Google SecOps tenant, and gives a human the
decision points. The operator's two core jobs:

1. **See what needs a human** — which human-in-the-loop (HITL) changes are
   awaiting approval, and which approved changes require manual application in
   the SecOps console — understand why, and act (approve, reject, mark applied,
   abandon, hand back).
2. **Talk to a specific agent** for ad-hoc work (investigate a feed, explain a
   parser failure, draft a rule change) via interactive chat.

Secondary: see that the fleet is working (who is doing what, what finished),
and read posture/briefings.

Success: an operator can open the console and, within a minute, know what is
waiting on them and act on it with enough context to decide confidently.

## Positioning

The agents do the work; the human holds the approval gate. Every change to the
tenant passes through an explicit, reasoned human decision with preflight and
drift evidence (target baseline check), and applied status reflects what was
actually committed to SecOps — never an optimistic guess.

## Operating Context

- Single-page web console (`clients/web/static/`), FastAPI server with SSE
  live updates (`clients/web/server.py`).
- ~22 ADK agents post into chat topics/streams and DMs, open issues, and
  produce change proposals.
- Proposal lifecycle: proposed → approved → applied / manual-apply-required →
  mark-applied or abandoned. Rejections and approvals require a reason.
- Issues/proposals live in an external ledger repo (`$SECOPS_LEDGER_ROOT`).

## Capabilities and Constraints

- No fabricated, sample, or placeholder SecOps data on screen. Unknown values
  render as "—" or an explicit "not measured"/UNKNOWN state.
- API failures must stay visible to the operator; no silent fallbacks.
- UI never orchestrates chained SecOps API calls; it consumes engine/server
  endpoints.
- Operator-facing terminology on screen; internal names (Gas Town, Polecats,
  Deacons, Convoys, Refinery) stay in code only. See terminology map in
  `docs/WEB_UI_REVIEW_PLAN.md`.

## Brand Commitments

Loosely themed on Google SecOps colours (vendored `secops-theme` tokens,
Google Sans). The user is open to UX changes beyond this; theme is a loose
alignment, not a strict brand lock.

## Evidence on Hand

Live tenant data only, via the server. No screenshots, customers, or metrics
exist to cite; do not invent any.

## Product Principles

1. **Human decisions first.** What is waiting on the operator outranks
   everything else on every screen.
2. **Show the work, not the machinery.** Surface what agents did and why in
   operator language; hide orchestration internals.
3. **Truthful state.** Only show what is known; make unknown, stale, and
   disconnected states explicit.
4. **Context at the point of decision.** Approvals carry the evidence
   (diff, preflight, drift, requesting agent) needed to decide without
   hunting.
5. **Direct line to any agent.** Ad-hoc chat with a specific agent is always
   one step away and preserves conversation history.

## Accessibility & Inclusion

No formal standard committed. Working target: WCAG 2.2 AA contrast, keyboard
operability, 11px minimum text (tracked in `docs/WEB_UI_REVIEW_PLAN.md`).
