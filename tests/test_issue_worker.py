"""Tests for the autonomous issue worker (find -> claim -> work -> propose/release)."""

import asyncio
import tempfile
import unittest
import unittest.mock
from pathlib import Path
from typing import Any, Dict, List, Optional

from agents.core.base_adk_agent import AgentMessage, BaseSecOpsAdkAgent
from agents.core.fleet_scheduler import FleetScheduler
from agents.core.issue_worker import (
    AUTONOMOUS_WORKERS_ENV_VAR,
    OUTCOME_ESCALATED,
    OUTCOME_NO_PROPOSAL,
    OUTCOME_PROPOSAL_SUBMITTED,
    OUTCOME_TIMEOUT,
    IssueWorker,
    bound_issue,
    current_issue_id,
)
from agents.core.lifecycle import SOCLifecycleManager
from agents.core.materializer import IssueMaterializer
from agents.core.proposal_manager import PreflightProof, ProposalManager
from agents.core.work_queue import LocalWorkQueue
from engine.domain import (
    IssueLifecycleStatus,
    IssueProblem,
    IssueRouting,
    OperationalPlane,
    SOCIssue,
)

PARSER_CAPS = {"parser.audit_health": 1, "parser.run": 1, "git.proposal.create": 1}


def _parser_issue(issue_id: str = "SOC-DATA-PARSER-WINEVTLOG", caps: Optional[Dict[str, int]] = None) -> SOCIssue:
    return SOCIssue(
        id=issue_id,
        type="parser_drop_spike",
        plane=OperationalPlane.DATA.value,
        problem=IssueProblem(
            title="Elevated Parser Normalization Drops on WINEVTLOG",
            observed_state={"log_type": "WINEVTLOG", "status": "FAILED", "unparsed_count": 420},
            desired_state={"status": "HEALTHY", "unparsed_count": 0},
            affected_objects=["WINEVTLOG"],
        ),
        routing=IssueRouting(requires_capabilities=caps or dict(PARSER_CAPS)),
    )


class ScriptedParserAgent(BaseSecOpsAdkAgent):
    """Real BaseSecOpsAdkAgent whose chat() runs a scripted tool sequence instead of Gemini.

    ``behaviour``: "propose" | "propose_wrong_id" | "decline" | "hang" | "raise"
    """

    CAPABILITIES = ["parser.audit_health", "parser.run"]

    def __init__(self, behaviour: str, **kwargs: Any):
        super().__init__(
            name="Parser Health Agent",
            handle="@parser-doctor",
            role="parser",
            subsystem="ingestion",
            description="",
            system_instruction="",
            default_stream="ingestion",
            default_topic="parser-drops",
            **kwargs,
        )
        self.behaviour = behaviour
        self.prompts: List[str] = []

    def _submit(self, issue_id: Optional[str]) -> None:
        self.submit_proposal(
            title="Fix WINEVTLOG CBN",
            target_resource_id="WINEVTLOG",
            action_type="PATCH_PARSER_CBN",
            rationale="grok pattern missing optional field",
            proposed_diff="--- a\n+++ b\n",
            mutation_payload={"log_type": "WINEVTLOG", "cbn_snippet": "filter {}"},
            preflight=PreflightProof(syntax_verified=True, replay_verified=True),
            issue_id=issue_id,
        )

    async def chat(self, prompt: str, stream=None, topic=None, history=None) -> AgentMessage:
        self.prompts.append(prompt)
        if self.behaviour == "hang":
            await asyncio.sleep(3600)
        if self.behaviour == "raise":
            raise RuntimeError("tenant unreachable")
        if self.behaviour == "propose":
            # Tools run in a worker thread in production (asyncio.to_thread); mirror that.
            await asyncio.to_thread(self._submit, None)
        elif self.behaviour == "propose_wrong_id":
            await asyncio.to_thread(self._submit, "SOC-SOMETHING-ELSE")
        return self.post_message(content=f"done ({self.behaviour})", stream=stream, topic=topic)


class IssueWorkerTestBase(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        root = Path(self._tmp.name)
        self.queue = LocalWorkQueue(root_dir=str(root))
        self.lifecycle = SOCLifecycleManager(
            work_queue=self.queue,
            materializer=IssueMaterializer(root_dir=root / "ledger"),
            root_dir=root,
        )
        self.proposals = ProposalManager(root_dir=root / "ledger")

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def agent(self, behaviour: str) -> ScriptedParserAgent:
        return ScriptedParserAgent(
            behaviour,
            proposal_manager=self.proposals,
            work_queue=self.queue,
            lifecycle_manager=self.lifecycle,
        )

    def worker(self, agent: Any, **kwargs: Any) -> IssueWorker:
        kwargs.setdefault("llm_ready", lambda: True)
        return IssueWorker(fleet={agent.handle: agent}, work_queue=self.queue, **kwargs)

    def run_cycle(self, worker: IssueWorker) -> List[str]:
        async def _go() -> List[str]:
            started = await worker.dispatch()
            await worker.drain()
            return started
        return asyncio.run(_go())


class TestIssueWorkerFlow(IssueWorkerTestBase):
    def test_claims_works_and_links_proposal_deterministically(self) -> None:
        self.lifecycle.open_issue(_parser_issue(), commit=False)
        agent = self.agent("propose")
        worker = self.worker(agent)

        self.assertEqual(self.run_cycle(worker), ["SOC-DATA-PARSER-WINEVTLOG"])

        issue = self.queue.get_issue("SOC-DATA-PARSER-WINEVTLOG")
        self.assertEqual(issue.status, IssueLifecycleStatus.VALIDATING.value)
        self.assertIsNotNone(issue.active_proposal_id)
        self.assertIsNone(issue.lease)
        self.assertEqual(issue.routing.claimed_by, "@parser-doctor")
        self.assertEqual(issue.attempts[-1]["outcome"], OUTCOME_PROPOSAL_SUBMITTED)
        proposal = self.proposals.get_proposal(issue.active_proposal_id)
        self.assertEqual(proposal.issue_id, "SOC-DATA-PARSER-WINEVTLOG")
        self.assertIn("SOC-DATA-PARSER-WINEVTLOG", agent.prompts[0])
        self.assertIn("WINEVTLOG", agent.prompts[0])

    def test_claimed_issue_overrides_model_supplied_issue_id(self) -> None:
        self.lifecycle.open_issue(_parser_issue(), commit=False)
        worker = self.worker(self.agent("propose_wrong_id"))
        self.run_cycle(worker)

        issue = self.queue.get_issue("SOC-DATA-PARSER-WINEVTLOG")
        self.assertEqual(issue.status, IssueLifecycleStatus.VALIDATING.value)
        self.assertEqual(self.proposals.get_proposal(issue.active_proposal_id).issue_id, issue.id)

    def test_no_proposal_releases_to_pool_and_cools_down(self) -> None:
        self.lifecycle.open_issue(_parser_issue(), commit=False)
        agent = self.agent("decline")
        worker = self.worker(agent)
        self.run_cycle(worker)

        issue = self.queue.get_issue("SOC-DATA-PARSER-WINEVTLOG")
        self.assertEqual(issue.status, IssueLifecycleStatus.AVAILABLE.value)
        self.assertIsNone(issue.lease)
        self.assertIsNone(issue.routing.claimed_by)
        self.assertEqual(issue.attempts[-1]["outcome"], OUTCOME_NO_PROPOSAL)
        # Cooldown: next tick must not re-claim immediately.
        self.assertEqual(self.run_cycle(worker), [])
        self.assertEqual(len(agent.prompts), 1)

    def test_timeout_releases_issue(self) -> None:
        self.lifecycle.open_issue(_parser_issue(), commit=False)
        worker = self.worker(self.agent("hang"), run_timeout_seconds=0.05)
        self.run_cycle(worker)

        issue = self.queue.get_issue("SOC-DATA-PARSER-WINEVTLOG")
        self.assertEqual(issue.status, IssueLifecycleStatus.AVAILABLE.value)
        self.assertEqual(issue.attempts[-1]["outcome"], OUTCOME_TIMEOUT)

    def test_agent_exception_releases_issue(self) -> None:
        self.lifecycle.open_issue(_parser_issue(), commit=False)
        worker = self.worker(self.agent("raise"))
        self.run_cycle(worker)
        issue = self.queue.get_issue("SOC-DATA-PARSER-WINEVTLOG")
        self.assertEqual(issue.status, IssueLifecycleStatus.AVAILABLE.value)
        self.assertIn("tenant unreachable", issue.attempts[-1]["notes"])

    def test_escalates_to_needs_human_after_max_failed_attempts(self) -> None:
        self.lifecycle.open_issue(_parser_issue(), commit=False)
        agent = self.agent("decline")
        worker = self.worker(agent, retry_cooldown_seconds=0, max_attempts=2)
        self.run_cycle(worker)
        self.run_cycle(worker)
        self.assertEqual(self.run_cycle(worker), [])

        issue = self.queue.get_issue("SOC-DATA-PARSER-WINEVTLOG")
        self.assertEqual(issue.status, IssueLifecycleStatus.NEEDS_HUMAN.value)
        self.assertEqual(issue.attempts[-1]["outcome"], OUTCOME_ESCALATED)
        self.assertEqual(len(agent.prompts), 2)


class TestIssueWorkerGating(IssueWorkerTestBase):
    def test_skips_when_llm_not_configured(self) -> None:
        self.lifecycle.open_issue(_parser_issue(), commit=False)
        worker = self.worker(self.agent("propose"), llm_ready=lambda: False)
        self.assertEqual(self.run_cycle(worker), [])
        self.assertEqual(self.queue.get_issue("SOC-DATA-PARSER-WINEVTLOG").status, "AVAILABLE")

    def test_skips_issue_types_without_playbook(self) -> None:
        issue = _parser_issue()
        issue.type = "rule_decay"
        self.lifecycle.open_issue(issue, commit=False)
        self.assertEqual(self.run_cycle(self.worker(self.agent("propose"))), [])

    def test_skips_issues_agent_lacks_capabilities_for(self) -> None:
        self.lifecycle.open_issue(_parser_issue(caps={"rule.deploy": 1}), commit=False)
        self.assertEqual(self.run_cycle(self.worker(self.agent("propose"))), [])

    def test_skips_issue_leased_by_another_worker(self) -> None:
        self.lifecycle.open_issue(_parser_issue(), commit=False)
        self.queue.acquire_lease("SOC-DATA-PARSER-WINEVTLOG", "@someone-else", duration_seconds=600)
        self.assertEqual(self.run_cycle(self.worker(self.agent("propose"))), [])

    def test_one_issue_per_agent_per_tick(self) -> None:
        self.lifecycle.open_issue(_parser_issue("SOC-DATA-PARSER-A"), commit=False)
        self.lifecycle.open_issue(_parser_issue("SOC-DATA-PARSER-B"), commit=False)
        self.assertEqual(len(self.run_cycle(self.worker(self.agent("propose")))), 1)


class TestIssueBinding(unittest.TestCase):
    def test_binding_is_scoped(self) -> None:
        self.assertIsNone(current_issue_id())
        with bound_issue("SOC-X"):
            self.assertEqual(current_issue_id(), "SOC-X")
        self.assertIsNone(current_issue_id())

    def test_binding_isolated_between_concurrent_tasks(self) -> None:
        async def work(issue_id: str) -> str:
            with bound_issue(issue_id):
                await asyncio.sleep(0.01)
                return await asyncio.to_thread(current_issue_id)

        async def main() -> List[str]:
            return await asyncio.gather(work("A"), work("B"))

        self.assertEqual(asyncio.run(main()), ["A", "B"])


class TestParserPatrolOpensClaimableIssue(unittest.TestCase):
    """Regression: a local `from engine.domain import SOCIssue` later in
    _auto_create_patrol_beads shadowed the module import, so the parser patrol
    never managed to open an issue (UnboundLocalError, logged and swallowed)."""

    def test_parser_patrol_opens_issue_parser_doctor_can_claim(self) -> None:
        from agents.core.evidence_store import LocalFileEvidenceStore
        from tests.test_fleet_scheduler import PatrolAgentFixture, _isolated_router

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            queue = LocalWorkQueue(root_dir=str(root))
            lifecycle = SOCLifecycleManager(
                work_queue=queue, materializer=IssueMaterializer(root_dir=root / "ledger"), root_dir=root,
            )
            patrol = PatrolAgentFixture("Parser", "@parser-doctor")
            sched = FleetScheduler(
                fleet={"@parser-doctor": patrol},
                evidence_store=LocalFileEvidenceStore(root_dir=str(root)),
                lifecycle_manager=lifecycle,
                work_queue=queue,
                communication_router=_isolated_router(root, None),
            )
            sched._auto_create_patrol_beads("@parser-doctor", patrol.audit_parsers(), {"action": "audit_parsers"}, "now")

            issue = queue.get_issue("SOC-DATA-PARSER-WINEVTLOG")
            self.assertIsNotNone(issue)
            self.assertEqual(issue.type, "parser_drop_spike")
            agent = ScriptedParserAgent("propose", work_queue=queue, lifecycle_manager=lifecycle)
            self.assertEqual([i.id for i in agent.find_eligible_issues()], [issue.id])


class TestSchedulerFeatureFlag(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.queue = LocalWorkQueue(root_dir=self._tmp.name)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def _scheduler(self) -> FleetScheduler:
        from tests.test_fleet_scheduler import _isolated_router
        return FleetScheduler(
            fleet={}, work_queue=self.queue,
            communication_router=_isolated_router(Path(self._tmp.name), None),
        )

    def test_disabled_by_default(self) -> None:
        with unittest.mock.patch.dict("os.environ", {AUTONOMOUS_WORKERS_ENV_VAR: ""}):
            sched = self._scheduler()
        self.assertIsNone(sched.issue_worker)
        self.assertFalse(sched.get_worker_status()["enabled"])
        self.assertEqual(asyncio.run(sched._dispatch_issue_work()), [])

    def test_enabled_by_env(self) -> None:
        with unittest.mock.patch.dict("os.environ", {AUTONOMOUS_WORKERS_ENV_VAR: "1"}):
            sched = self._scheduler()
        self.assertIsNotNone(sched.issue_worker)
        self.assertIn("parser_drop_spike", sched.get_worker_status()["playbooks"])

if __name__ == "__main__":
    unittest.main()
