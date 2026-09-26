"""Autonomous issue worker: find eligible issue -> claim -> investigate -> propose or release.

Opt-in via ``SECOPS_AUTONOMOUS_WORKERS=1``. The FleetScheduler calls
:meth:`IssueWorker.dispatch` on each tick; each idle agent picks up at most one
issue whose ``type`` has a registered playbook.

Proposal linking is deterministic: while an agent works an issue, the issue id
is bound to a ContextVar that ``BaseSecOpsAdkAgent.submit_proposal`` reads, so
the LLM never has to supply ``issue_id``.
"""

from __future__ import annotations

import asyncio
from contextlib import contextmanager
from contextvars import ContextVar
from datetime import datetime, timezone
import json
import logging
import os
from typing import Any, Callable, Dict, Iterator, List, Optional

from agents.core.work_queue import OPERATOR_REQUEUED_OUTCOME
from engine.domain import IssueLifecycleStatus, SOCIssue

logger = logging.getLogger(__name__)

AUTONOMOUS_WORKERS_ENV_VAR = "SECOPS_AUTONOMOUS_WORKERS"

# Outcomes recorded in SOCIssue.attempts by this worker.
OUTCOME_PROPOSAL_SUBMITTED = "PROPOSAL_SUBMITTED"
OUTCOME_NO_PROPOSAL = "NO_PROPOSAL"
OUTCOME_TIMEOUT = "TIMEOUT"
OUTCOME_ERROR = "ERROR"
OUTCOME_ESCALATED = "ESCALATED_TO_HUMAN"
# Attempts that count toward the retry budget (LEASE_EXPIRED comes from the work queue).
FAILED_OUTCOMES = frozenset({OUTCOME_NO_PROPOSAL, OUTCOME_TIMEOUT, OUTCOME_ERROR, "LEASE_EXPIRED"})

_active_issue: ContextVar[Optional[str]] = ContextVar("secops_active_issue_id", default=None)


def autonomous_workers_enabled() -> bool:
    return os.getenv(AUTONOMOUS_WORKERS_ENV_VAR, "").strip().lower() in ("1", "true", "yes", "on")


def current_issue_id() -> Optional[str]:
    """Issue the calling worker is bound to, or None outside a worker run."""
    return _active_issue.get()


@contextmanager
def bound_issue(issue_id: str) -> Iterator[None]:
    token = _active_issue.set(issue_id)
    try:
        yield
    finally:
        _active_issue.reset(token)


# --- Playbooks: issue.type -> prompt builder ---------------------------------

def _parser_drop_spike_prompt(issue: SOCIssue) -> str:
    observed = issue.problem.observed_state or {}
    log_type = observed.get("log_type") or (issue.problem.affected_objects or ["UNKNOWN"])[0]
    criteria = "\n".join(f"- {c}" for c in (issue.governance.validation_criteria or [])) or "- none specified"
    return (
        f"You have claimed SOC issue `{issue.id}`: {issue.problem.title}.\n\n"
        f"Observed state:\n```json\n{json.dumps(observed, indent=2, default=str)}\n```\n"
        f"Desired state:\n```json\n{json.dumps(issue.problem.desired_state or {}, indent=2, default=str)}\n```\n"
        f"Validation criteria:\n{criteria}\n\n"
        f"Procedure:\n"
        f"1. Call diagnose_unparsed_logs for log_type `{log_type}` to get failing samples and the exact error.\n"
        f"2. Call get_parser_cbn for `{log_type}` (and get_parser_extension if an extension is involved).\n"
        f"3. Draft a minimal CBN fix and verify it with run_parser_test against at least one failing sample.\n"
        f"4. Only if the test passes, call submit_parser_proposal with a unified diff. The proposal is linked "
        f"to `{issue.id}` automatically; you do not need to pass issue_id.\n"
        f"5. If you cannot produce a verified fix, do NOT submit a proposal. State what blocks you and what a "
        f"human should check.\n\n"
        f"Finish with a short summary: root cause, fix (or blocker), and test evidence."
    )


ISSUE_PLAYBOOKS: Dict[str, Callable[[SOCIssue], str]] = {
    "parser_drop_spike": _parser_drop_spike_prompt,
}


def _parse_ts(value: Any) -> Optional[datetime]:
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def _attempts_since_requeue(issue: SOCIssue) -> List[Dict[str, Any]]:
    """Attempts after the most recent operator requeue (the current retry budget window)."""
    attempts = [a for a in issue.attempts if isinstance(a, dict)]
    for idx in range(len(attempts) - 1, -1, -1):
        if attempts[idx].get("outcome") == OPERATOR_REQUEUED_OUTCOME:
            return attempts[idx + 1:]
    return attempts


def failed_attempt_count(issue: SOCIssue) -> int:
    return sum(1 for a in _attempts_since_requeue(issue) if a.get("outcome") in FAILED_OUTCOMES)


def in_cooldown(issue: SOCIssue, cooldown_seconds: float, now: Optional[datetime] = None) -> bool:
    """True if the most recent failed attempt is younger than the cooldown."""
    now = now or datetime.now(timezone.utc)
    stamps = [
        _parse_ts(a.get("timestamp"))
        for a in _attempts_since_requeue(issue)
        if a.get("outcome") in FAILED_OUTCOMES
    ]
    stamps = [s for s in stamps if s]
    return bool(stamps) and (now - max(stamps)).total_seconds() < cooldown_seconds


class IssueWorker:
    """Runs agents against claimable issues. One in-flight issue per agent."""

    def __init__(
        self,
        fleet: Dict[str, Any],
        work_queue: Any,
        chat_store: Optional[Any] = None,
        playbooks: Optional[Dict[str, Callable[[SOCIssue], str]]] = None,
        lease_seconds: int = 600,
        heartbeat_seconds: float = 120.0,
        run_timeout_seconds: float = 900.0,
        retry_cooldown_seconds: float = 3600.0,
        max_attempts: int = 3,
        max_concurrent: int = 2,
        llm_ready: Optional[Callable[[], bool]] = None,
    ):
        self.fleet = fleet
        self.work_queue = work_queue
        self.chat_store = chat_store
        self.playbooks = playbooks if playbooks is not None else dict(ISSUE_PLAYBOOKS)
        self.lease_seconds = lease_seconds
        self.heartbeat_seconds = heartbeat_seconds
        self.run_timeout_seconds = run_timeout_seconds
        self.retry_cooldown_seconds = retry_cooldown_seconds
        self.max_attempts = max_attempts
        self.max_concurrent = max_concurrent
        self._llm_ready = llm_ready or _default_llm_ready
        self._tasks: Dict[str, asyncio.Task] = {}  # agent handle -> task
        self._in_flight: Dict[str, str] = {}  # agent handle -> issue id
        self.history: List[Dict[str, Any]] = []

    # --- status ---------------------------------------------------------

    def status(self) -> Dict[str, Any]:
        return {
            "enabled": True,
            "llm_ready": self._llm_ready(),
            "playbooks": sorted(self.playbooks),
            "in_flight": [{"agent": h, "issue_id": i} for h, i in self._in_flight.items()],
            "recent_runs": self.history[-10:],
        }

    # --- dispatch -------------------------------------------------------

    def _prune_finished(self) -> None:
        for handle in [h for h, t in self._tasks.items() if t.done()]:
            self._tasks.pop(handle, None)
            self._in_flight.pop(handle, None)

    def _escalate_if_exhausted(self, issue: SOCIssue) -> bool:
        if failed_attempt_count(issue) < self.max_attempts:
            return False
        self.work_queue.record_attempt(
            issue.id, "fleet-worker", OUTCOME_ESCALATED,
            f"{self.max_attempts} autonomous attempts without a proposal; needs a human.",
        )
        self.work_queue.update_issue_status(issue.id, IssueLifecycleStatus.NEEDS_HUMAN.value)
        logger.info("Issue %s escalated to NEEDS_HUMAN after %d failed attempts", issue.id, self.max_attempts)
        return True

    def _pick_issue(self, agent: Any) -> Optional[SOCIssue]:
        busy = set(self._in_flight.values())
        for issue in agent.find_eligible_issues(limit=20):
            if issue.type not in self.playbooks or issue.id in busy:
                continue
            if self._escalate_if_exhausted(issue):
                continue
            if in_cooldown(issue, self.retry_cooldown_seconds):
                continue
            return issue
        return None

    async def dispatch(self) -> List[str]:
        """Claims at most one issue per idle agent and starts work in the background.

        Returns the issue ids started on this call.
        """
        self._prune_finished()
        if not self.playbooks or not self._llm_ready():
            return []

        started: List[str] = []
        for handle, agent in self.fleet.items():
            if len(self._tasks) >= self.max_concurrent:
                break
            if handle in self._tasks:
                continue
            if not (hasattr(agent, "find_eligible_issues") and hasattr(agent, "claim_work")):
                continue
            try:
                issue = self._pick_issue(agent)
                if issue is None:
                    continue
                lease = agent.claim_work(issue.id, duration_seconds=self.lease_seconds)
            except Exception as e:
                logger.warning("Worker dispatch failed for %s: %s", handle, e)
                continue
            if not lease:
                continue  # lost the race to another worker
            self._in_flight[handle] = issue.id
            self._tasks[handle] = asyncio.create_task(self._work(agent, issue))
            started.append(issue.id)
            logger.info("%s claimed %s (lease gen %s)", handle, issue.id, lease.generation)
        return started

    async def drain(self) -> None:
        """Waits for in-flight work (tests / shutdown)."""
        if self._tasks:
            await asyncio.gather(*self._tasks.values(), return_exceptions=True)
        self._prune_finished()

    def cancel_all(self) -> None:
        for task in self._tasks.values():
            task.cancel()

    # --- one issue -------------------------------------------------------

    async def _heartbeat(self, agent: Any, issue_id: str) -> None:
        while True:
            await asyncio.sleep(self.heartbeat_seconds)
            try:
                if not agent.renew_work_lease(issue_id, duration_seconds=self.lease_seconds):
                    logger.warning("%s lost lease on %s", agent.handle, issue_id)
                    return
            except Exception as e:
                logger.warning("Lease renewal failed for %s on %s: %s", agent.handle, issue_id, e)

    async def _work(self, agent: Any, issue: SOCIssue) -> str:
        handle = agent.handle
        stream = getattr(agent, "default_stream", None) or "general"
        topic = getattr(agent, "default_topic", None) or "fleet-work"
        prompt = self.playbooks[issue.type](issue)
        outcome, notes, reply = OUTCOME_ERROR, "", None

        self.work_queue.update_issue_status(issue.id, IssueLifecycleStatus.EXECUTING.value)
        heartbeat = asyncio.create_task(self._heartbeat(agent, issue.id))
        try:
            with bound_issue(issue.id):
                reply = await asyncio.wait_for(
                    agent.chat(prompt, stream=stream, topic=topic),
                    timeout=self.run_timeout_seconds,
                )
            current = self.work_queue.get_issue(issue.id)
            if current and current.status == IssueLifecycleStatus.VALIDATING.value and current.active_proposal_id:
                outcome = OUTCOME_PROPOSAL_SUBMITTED
                notes = f"Proposal {current.active_proposal_id} submitted."
            else:
                outcome = OUTCOME_NO_PROPOSAL
                notes = (getattr(reply, "content", "") or "")[:500]
        except asyncio.TimeoutError:
            outcome, notes = OUTCOME_TIMEOUT, f"No result within {int(self.run_timeout_seconds)}s."
        except asyncio.CancelledError:
            outcome, notes = OUTCOME_ERROR, "Worker cancelled (shutdown)."
            raise
        except Exception as e:
            logger.exception("%s failed working %s", handle, issue.id)
            outcome, notes = OUTCOME_ERROR, f"{type(e).__name__}: {e}"
        finally:
            heartbeat.cancel()
            self._finish(agent, issue, outcome, notes)

        self._post_result(agent, issue, outcome, notes, reply, stream, topic)
        return outcome

    def _finish(self, agent: Any, issue: SOCIssue, outcome: str, notes: str) -> None:
        handle = agent.handle
        try:
            self.work_queue.record_attempt(issue.id, handle, outcome, notes)
            # Proposal submitted: keep VALIDATING (and claimed_by) but drop the lease.
            # Anything else: return to the pool; cooldown/max-attempts gate the retry.
            new_status = (
                IssueLifecycleStatus.VALIDATING.value
                if outcome == OUTCOME_PROPOSAL_SUBMITTED
                else IssueLifecycleStatus.AVAILABLE.value
            )
            self.work_queue.release_lease(issue.id, agent_handle=handle, new_status=new_status)
        except Exception as e:
            logger.error("Failed finalising %s for %s: %s", issue.id, handle, e)
        self.history.append({
            "agent": handle,
            "issue_id": issue.id,
            "outcome": outcome,
            "finished_at": datetime.now(timezone.utc).isoformat(),
        })
        self.history = self.history[-50:]

    def _post_result(
        self, agent: Any, issue: SOCIssue, outcome: str, notes: str,
        reply: Any, stream: str, topic: str,
    ) -> None:
        if not self.chat_store:
            return
        headline = {
            OUTCOME_PROPOSAL_SUBMITTED: "submitted a proposal for review",
            OUTCOME_NO_PROPOSAL: "released the issue without a proposal",
            OUTCOME_TIMEOUT: "timed out; issue returned to the queue",
            OUTCOME_ERROR: "hit an error; issue returned to the queue",
        }.get(outcome, outcome)
        body = getattr(reply, "content", None) or notes
        content = f"**Autonomous work on `{issue.id}`**: {headline}.\n\n{body}"
        try:
            self.chat_store.add_message(
                stream=stream,
                topic=topic,
                sender_handle=agent.handle,
                sender_type="agent",
                content=content,
                proposal_id=getattr(reply, "proposal_id", None),
                widget=getattr(reply, "widget", None),
            )
        except Exception as e:
            logger.warning("Failed posting worker result for %s: %s", issue.id, e)


def _default_llm_ready() -> bool:
    from agents.core.base_adk_agent import llm_credentials_status
    return bool(llm_credentials_status()["configured"])
