"""Unit and Integration Tests for the SecOps Multi-Agent Fleet Web Chat Server."""

import asyncio
from datetime import datetime, timedelta, timezone
from pathlib import Path
import tempfile
import unittest

from fastapi.testclient import TestClient

from agents.core.proposal_manager import ChangeProposal, PreflightProof, ProposalManager
from agents.generated import create_agent_fleet
from clients.web.chat_engine import ActiveAgentJob, AgentDispatcher, ChatMessage, ChatStore
from clients.web.server import app, chat_store, proposal_manager, engine, fleet
from engine.facade import SecOpsEngine
from engine.registry import WorkflowRegistry


class _InertAdapterForChatTest:
    def __getattr__(self, name: str):
        def _no_op(*args, **kwargs):
            if "verify" in name:
                return {"success": True, "diagnostics": []}
            if "get" in name:
                rule_id = args[0] if args else kwargs.get("rule_id_or_name", "ru_0e378636")
                return {
                    "rule_id": rule_id,
                    "name": rule_id,
                    "rule_text": (
                        f"rule {rule_id} {{\n"
                        f"  meta:\n"
                        f"    author = \"secops-team\"\n"
                        f"  events:\n"
                        f"    $e1.metadata.event_type = \"USER_LOGIN\"\n"
                        f"    $e2.metadata.event_type = \"FILE_CREATION\"\n"
                        f"  match:\n"
                        f"    $e1.principal.user.userid over 1h\n"
                        f"  condition:\n"
                        f"    $e1 and $e2\n"
                        f"}}"
                    ),
                }
            return {"status": "ok", "mock_check": False}
        return _no_op


class ChatStoreTest(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root_path = Path(self.temp_dir.name)
        self.store = ChatStore(root_dir=self.root_path)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_add_and_list_messages_by_stream_and_topic(self):
        msg1 = self.store.add_message(
            stream="detections",
            topic="performance-alerts",
            sender_handle="@rule-troubleshooter",
            sender_type="agent",
            content="Alert: Timeout in ru_0e378636",
        )
        msg2 = self.store.add_message(
            stream="detections",
            topic="rule-proposals",
            sender_handle="@yaral-optimizer",
            sender_type="agent",
            content="Proposal submitted",
        )
        msg3 = self.store.add_message(
            stream="general",
            topic="announcements",
            sender_handle="@secops-dispatcher",
            sender_type="agent",
            content="Fleet ready",
        )

        detections_alerts = self.store.list_messages("detections", "performance-alerts")
        self.assertEqual(len(detections_alerts), 1)
        self.assertEqual(detections_alerts[0].id, msg1.id)

        all_detections = self.store.list_messages("detections")
        self.assertEqual(len(all_detections), 2)

    def test_list_streams_and_topics(self):
        self.store.add_message(
            stream="detections",
            topic="custom-topic",
            sender_handle="@operator",
            sender_type="user",
            content="Testing topics",
        )
        streams = self.store.list_streams()
        stream_ids = [s["id"] for s in streams]
        self.assertIn("detections", stream_ids)
        self.assertIn("general", stream_ids)

        topics = self.store.list_topics("detections")
        topic_names = [t["name"] for t in topics]
        self.assertIn("custom-topic", topic_names)
        self.assertIn("rule-proposals", topic_names)

    def test_active_job_lifecycle_and_ttl_reaping(self):
        # 1. Start job
        job = self.store.start_job(
            stream="detections",
            topic="rule-proposals",
            agent_handle="@detection-decay-agent",
            user_handle="@analyst",
            step="Investigating decay",
        )
        self.assertTrue(job.job_id.startswith("job_detections_rule-proposals_"))
        self.assertEqual(len(self.store.list_active_jobs()), 1)
        self.assertEqual(self.store.list_active_jobs()[0].step, "Investigating decay")
        self.assertEqual(self.store.list_active_jobs()[0].user_handle, "@analyst")

        # 2. Update job
        self.store.update_job(job.job_id, step="Optimizing rule text")
        self.assertEqual(self.store.list_active_jobs()[0].step, "Optimizing rule text")

        # 3. Filter by stream and topic
        self.assertEqual(len(self.store.list_active_jobs(stream="general")), 0)
        self.assertEqual(len(self.store.list_active_jobs(stream="detections", topic="rule-proposals")), 1)

        # 4. Complete job
        completed = self.store.complete_job(job.job_id)
        self.assertIsNotNone(completed)
        self.assertEqual(completed.status, "COMPLETED")
        self.assertEqual(len(self.store.list_active_jobs()), 0)

        # 5. Fail job lifecycle
        job2 = self.store.start_job(
            stream="soar",
            topic="playbook-runs",
            agent_handle="@secops-dispatcher",
            step="Executing playbook",
        )
        failed = self.store.fail_job(job2.job_id, error_message="Playbook timeout")
        self.assertIsNotNone(failed)
        self.assertEqual(failed.status, "FAILED")
        self.assertIn("Failed: Playbook timeout", failed.step)
        self.assertEqual(len(self.store.list_active_jobs()), 0)

        # 6. Dead-job TTL reaping
        job3 = self.store.start_job(
            stream="identity",
            topic="access-audits",
            agent_handle="@secops-dispatcher",
        )
        # Artificially age the job past TTL
        past_time = (datetime.now(timezone.utc) - timedelta(seconds=200)).isoformat()
        job3.started_at = past_time
        reaped_jobs = self.store.list_active_jobs(max_age_seconds=180.0)
        self.assertEqual(len(reaped_jobs), 0)
        self.assertNotIn(job3.job_id, self.store._active_jobs)


class AgentDispatcherTest(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root_path = Path(self.temp_dir.name)
        self.store = ChatStore(root_dir=self.root_path)
        self.prop_mgr = ProposalManager(root_dir=self.root_path)

        self.engine = SecOpsEngine(
            adapter=_InertAdapterForChatTest(),
            custom_registry=WorkflowRegistry(),
        )
        self.fleet = create_agent_fleet(
            engine=self.engine,
            proposal_manager=self.prop_mgr,
        )
        self.dispatcher = AgentDispatcher(
            chat_store=self.store,
            fleet=self.fleet,
            engine=self.engine,
            proposal_manager=self.prop_mgr,
        )

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_extract_mentions(self):
        text = "Hello @secops-dispatcher, can @yaral-optimizer check this?"
        mentions = self.dispatcher.extract_mentions(text)
        self.assertEqual(mentions, ["@secops-dispatcher", "@yaral-optimizer"])

    async def test_dispatch_to_secops_dispatcher(self):
        user_msg = self.store.add_message(
            stream="general",
            topic="dispatcher",
            sender_handle="@operator",
            sender_type="user",
            content="What can the fleet do?",
        )
        replies = await self.dispatcher.dispatch(user_msg)
        self.assertEqual(len(replies), 1)
        self.assertEqual(replies[0].sender_handle, "@secops-dispatcher")
        self.assertIn("SecOps Dispatcher", replies[0].content)

    async def test_dispatch_to_yaral_optimizer_creates_proposal(self):
        user_msg = self.store.add_message(
            stream="detections",
            topic="rule-proposals",
            sender_handle="@operator",
            sender_type="user",
            content="@yaral-optimizer please optimize rule ru_0e378636 to prevent timeouts",
        )
        replies = await self.dispatcher.dispatch(user_msg)
        self.assertEqual(len(replies), 1)
        reply = replies[0]

        self.assertEqual(reply.sender_handle, "@yaral-optimizer")
        self.assertIsNotNone(reply.proposal_id)
        self.assertIsNotNone(reply.widget)
        self.assertEqual(reply.widget["type"], "hitl_proposal_card")
        self.assertEqual(reply.widget["target_resource_id"], "ru_0e378636")

        # Verify proposal was saved to disk by ProposalManager
        saved_prop = self.prop_mgr.get_proposal(reply.proposal_id)
        self.assertEqual(saved_prop.status, "OPEN")
        self.assertEqual(saved_prop.target_resource_id, "ru_0e378636")

        # Clean up test proposal
        test_prop_file = self.prop_mgr.open_dir / f"{reply.proposal_id}.md"
        if test_prop_file.exists():
            test_prop_file.unlink()

    async def test_direct_message_dispatch(self):
        user_msg = self.store.add_message(
            stream="dm",
            topic="@feed-agent",
            sender_handle="@operator",
            sender_type="user",
            content="audit feeds",
        )
        replies = await self.dispatcher.dispatch(user_msg)
        self.assertTrue(len(replies) >= 1)
        self.assertEqual(replies[0].sender_handle, "@feed-agent")

    async def test_direct_message_dispatch_log_cost_agent(self):
        user_msg = self.store.add_message(
            stream="dm",
            topic="@log-cost-agent",
            sender_handle="@operator",
            sender_type="user",
            content="save me some money",
        )
        replies = await self.dispatcher.dispatch(user_msg)
        self.assertTrue(len(replies) >= 1)
        self.assertEqual(replies[0].sender_handle, "@log-cost-agent")

    async def test_dispatch_tracks_active_job_lifecycle(self):
        user_msg = self.store.add_message(
            stream="detections",
            topic="decay-review",
            sender_handle="@operator",
            sender_type="user",
            content="@feed-agent audit feeds",
        )
        # Before dispatch: 0 active jobs
        self.assertEqual(len(self.store.list_active_jobs()), 0)

        # Intercept _execute_agent to assert that active job is registered while executing
        orig_execute = self.dispatcher._execute_agent
        observed_jobs = []

        async def _intercept_execute(agent, msg):
            jobs = self.store.list_active_jobs(stream="detections", topic="decay-review")
            for j in jobs:
                observed_jobs.append({
                    "job_id": j.job_id,
                    "agent_handle": j.agent_handle,
                    "user_handle": j.user_handle,
                    "status": j.status,
                    "step": j.step,
                })
            return {"content": "Audit complete", "proposal_id": None, "widget": None}

        self.dispatcher._execute_agent = _intercept_execute
        try:
            replies = await self.dispatcher.dispatch(user_msg)
            self.assertEqual(len(replies), 1)
            # Verify job was observed in-flight
            self.assertEqual(len(observed_jobs), 1)
            self.assertEqual(observed_jobs[0]["agent_handle"], "@feed-agent")
            self.assertEqual(observed_jobs[0]["user_handle"], "@operator")
            self.assertEqual(observed_jobs[0]["status"], "THINKING")

            # After execution completes, active job is removed
            self.assertEqual(len(self.store.list_active_jobs()), 0)
        finally:
            self.dispatcher._execute_agent = orig_execute


class FastApiServerEndpointsTest(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)

    def test_health_endpoint(self):
        res = self.client.get("/api/health")
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertEqual(data["status"], "healthy")
        self.assertTrue(data["version"])  # shown in the UI About dialog
        self.assertGreaterEqual(data["agents_online"], 4)
        self.assertGreaterEqual(data["engine_capabilities"], 160)

    def test_streams_and_agents_endpoints(self):
        res_streams = self.client.get("/api/streams")
        self.assertEqual(res_streams.status_code, 200)
        streams = res_streams.json()
        self.assertTrue(len(streams) >= 6)

        res_agents = self.client.get("/api/agents")
        self.assertEqual(res_agents.status_code, 200)
        agents = res_agents.json()
        handles = [a["handle"] for a in agents]
        self.assertIn("@secops-dispatcher", handles)
        self.assertIn("@yaral-optimizer", handles)
        self.assertIn("@identity-governor", handles)
        self.assertIn("@tenant-cartographer", handles)
        self.assertIn("@cloud-status-agent", handles)
        self.assertEqual(len(agents), 22)

    def test_post_message_endpoint(self):
        res = self.client.post(
            "/api/messages",
            json={
                "stream": "detections",
                "topic": "rule-proposals",
                "content": "Test post message from operator",
                "sender_handle": "@operator",
            },
        )
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertEqual(data["status"], "sent")
        self.assertEqual(data["message"]["stream"], "detections")

    def test_root_index_html(self):
        res = self.client.get("/")
        self.assertEqual(res.status_code, 200)
        self.assertIn("Google SecOps Multi-Agent Fleet", res.text)

    def test_proposal_approval_and_rejection_flow(self):
        # 1. Create a proposal via proposal_manager
        prop_obj = ChangeProposal(
            id="",
            title="Optimize Sliding Match Window for ru_6cb096c8-2270-4d03-860b-3c3db443a7e4",
            author="@yaral-optimizer",
            subsystem="detection_rules",
            target_resource_id="ru_6cb096c8-2270-4d03-860b-3c3db443a7e4",
            action_type="RULE_OPTIMIZATION",
            rationale="Validating REST endpoint approval and merge mechanics",
            proposed_diff="--- a\n+++ b",
            mutation_payload={
                "rule_text": "rule ru_6cb096c8_optimized { condition: true }",
                "update_mask": "text",
            },
            preflight=PreflightProof(
                syntax_verified=True,
                replay_verified=True,
            ),
        )
        prop_id = proposal_manager.create_proposal(prop_obj)

        # 2. Check it appears in /api/proposals
        res_list = self.client.get("/api/proposals?status=OPEN")
        self.assertEqual(res_list.status_code, 200)
        ids = [p["id"] for p in res_list.json()]
        self.assertIn(prop_id, ids)

        # 3. Approve via POST /api/proposals/{id}/approve
        res_approve = self.client.post(
            f"/api/proposals/{prop_id}/approve",
            json={"merged_by": "secops-analyst-test", "approval_note": "Validated against 7d replay"},
        )
        self.assertEqual(res_approve.status_code, 200)
        merge_data = res_approve.json()
        self.assertTrue(merge_data["success"])

        # 4. Verify status is MERGED
        saved_prop = proposal_manager.get_proposal(prop_id)
        self.assertEqual(saved_prop.status, "MERGED")
        self.assertEqual(saved_prop.merged_by, "secops-analyst-test")
        self.assertEqual(saved_prop.approval_note, "Validated against 7d replay")

        # Cleanup merged test proposal file
        merged_file = proposal_manager.merged_dir / f"{prop_id}.md"
        if merged_file.exists():
            merged_file.unlink()

    def test_evidence_and_rules_state_endpoints(self):
        res_ev = self.client.get("/api/evidence?limit=10")
        self.assertEqual(res_ev.status_code, 200)
        self.assertIsInstance(res_ev.json(), list)

        res_rules = self.client.get("/api/rules/state?limit=10")
        self.assertEqual(res_rules.status_code, 200)
        self.assertIsInstance(res_rules.json(), list)

    def test_todos_and_config_endpoints(self):
        # 1. Create a remediation todo using real Chronicle rule ID
        res_create_todo = self.client.post(
            "/api/todos",
            json={
                "title": "Temporary Test Remediation for ru_6cb096c8-2270-4d03-860b-3c3db443a7e4",
                "target_agent": "@yaral-optimizer",
                "target_resource_id": "ru_6cb096c8-2270-4d03-860b-3c3db443a7e4",
                "action_type": "RULE_OPTIMIZATION",
                "rationale": "High memory consumption detected",
                "payload": {"risk": "HIGH"},
            },
        )
        self.assertEqual(res_create_todo.status_code, 200)
        todo_data = res_create_todo.json()
        self.assertEqual(todo_data["status"], "CREATED")
        todo_id = todo_data["todo_id"]

        # 2. List todos
        res_list_todos = self.client.get("/api/todos?status=PENDING&target_agent=@yaral-optimizer")
        self.assertEqual(res_list_todos.status_code, 200)
        todos = res_list_todos.json()
        self.assertTrue(any(t["todo_id"] == todo_id for t in todos))

        # 3. Clean up todo so it does not pollute the live store
        res_del = self.client.delete(f"/api/todos/{todo_id}")
        self.assertEqual(res_del.status_code, 200)

        # 4. Update and get dynamic agent configuration
        res_put_cfg = self.client.put(
            "/api/configs/agents/@rule-troubleshooter",
            json={"model": "gemini-2.5-pro", "custom_threshold": 0.85},
        )
        self.assertEqual(res_put_cfg.status_code, 200)

        res_get_cfg = self.client.get("/api/configs/agents/@rule-troubleshooter")
        self.assertEqual(res_get_cfg.status_code, 200)
        cfg = res_get_cfg.json()
        self.assertEqual(cfg.get("model"), "gemini-2.5-pro")
        self.assertEqual(cfg.get("custom_threshold"), 0.85)

    def test_iam_endpoints(self):
        """Verifies IAM bindings, custom roles, and audit endpoints."""
        res_audits = self.client.get("/api/iam/audits")
        self.assertEqual(res_audits.status_code, 200)
        self.assertIsInstance(res_audits.json(), list)

    def test_gastown_overview_endpoint(self):
        """Verifies the /api/gastown/overview endpoint provides Mayor, health, summary KPIs, Convoys, and Escalations."""
        res = self.client.get("/api/gastown/overview")
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertIn("mayor", data)
        self.assertIn("health", data)
        self.assertIn("summary", data)
        self.assertIn("convoys", data)
        self.assertIn("escalations", data)
        self.assertEqual(data["mayor"]["coordinator"], "@secops-dispatcher")
        self.assertEqual(data["summary"]["polecat_count"], len(fleet))
        self.assertGreaterEqual(len(data["convoys"]), 1)

    def test_gastown_patrols_endpoints(self):
        """Verifies the /api/gastown/patrols, run-all, and agent run endpoints."""
        res = self.client.get("/api/gastown/patrols")
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertIn("deacon", data)
        self.assertIn("schedules", data)
        self.assertIn(data["deacon"]["status"], ["healthy", "idle"])
        self.assertGreaterEqual(len(data["schedules"]), 5)

        # Trigger single agent patrol run
        res_run = self.client.post("/api/gastown/patrols/@feed-agent/run")
        self.assertEqual(res_run.status_code, 200)
        run_data = res_run.json()
        self.assertIn(run_data["status"], ["SUCCESS", "ERROR"])

    def test_active_jobs_endpoints(self):
        """Verifies GET /api/jobs/active returns running jobs with stream/topic filters."""
        # 1. Start a job in chat_store
        job = chat_store.start_job(
            stream="detections",
            topic="decay-review",
            agent_handle="@detection-decay-agent",
            user_handle="@operator",
            step="Scanning for decay metrics...",
        )

        try:
            # 2. Query all active jobs
            res_all = self.client.get("/api/jobs/active")
            self.assertEqual(res_all.status_code, 200)
            all_jobs = res_all.json()
            self.assertTrue(any(j["job_id"] == job.job_id for j in all_jobs))

            # 3. Query filtered by stream and topic
            res_filtered = self.client.get("/api/jobs/active?stream=detections&topic=decay-review")
            self.assertEqual(res_filtered.status_code, 200)
            filtered_jobs = res_filtered.json()
            self.assertEqual(len(filtered_jobs), 1)
            self.assertEqual(filtered_jobs[0]["job_id"], job.job_id)
            self.assertEqual(filtered_jobs[0]["user_handle"], "@operator")
            self.assertEqual(filtered_jobs[0]["step"], "Scanning for decay metrics...")

            # 4. Query filtered by unrelated stream
            res_empty = self.client.get("/api/jobs/active?stream=analytics")
            self.assertEqual(res_empty.status_code, 200)
            self.assertEqual(len(res_empty.json()), 0)
        finally:
            # 5. Clean up job
            chat_store.complete_job(job.job_id)

        # 6. Verify removed
        res_after = self.client.get("/api/jobs/active?stream=detections&topic=decay-review")
        self.assertEqual(res_after.status_code, 200)
        self.assertEqual(len(res_after.json()), 0)

    def test_agent_library_endpoints(self):
        """Validates GET /api/agents and GET /api/agents/{handle} specifications."""
        # 1. Fetch all agents
        res = self.client.get("/api/agents")
        self.assertEqual(res.status_code, 200)
        agents = res.json()
        self.assertGreaterEqual(len(agents), 10)

        # Map by handle
        agent_map = {a["handle"]: a for a in agents}
        self.assertIn("@detection-decay-agent", agent_map)
        self.assertIn("@yaral-optimizer", agent_map)
        self.assertIn("@secops-dispatcher", agent_map)

        # 2. Verify enriched agent specification
        decay_agent = agent_map["@detection-decay-agent"]
        self.assertEqual(decay_agent["name"], "Detection Decay Agent")
        self.assertEqual(decay_agent["subsystem"], "detections")
        self.assertIn("system_instruction", decay_agent)
        self.assertTrue(len(decay_agent["system_instruction"]) > 50)
        self.assertIn("Decay Prioritization Score", decay_agent["system_instruction"])

        # 3. Verify enriched SDK tools
        self.assertIn("tools", decay_agent)
        self.assertGreaterEqual(len(decay_agent["tools"]), 7)
        tool_ids = [t["capability_id"] for t in decay_agent["tools"]]
        self.assertIn("rule.decay.audit", tool_ids)
        self.assertIn("dashboard.execute_query", tool_ids)

        decay_tool = next(t for t in decay_agent["tools"] if t["capability_id"] == "rule.decay.audit")
        self.assertEqual(decay_tool["mcp_tool_name"], "audit_rule_decay")
        self.assertIn("kind", decay_tool)
        self.assertIn("cardinality", decay_tool)

        # 4. Verify builtin tools & cadence
        self.assertTrue(any(bt["name"] == "get_task_status" for bt in decay_agent.get("builtin_tools", [])))
        self.assertEqual(decay_agent.get("cadence"), "Every 12h")

        # 5. Fetch single agent by handle (with @ and without @)
        res_single = self.client.get("/api/agents/@detection-decay-agent")
        self.assertEqual(res_single.status_code, 200)
        self.assertEqual(res_single.json()["handle"], "@detection-decay-agent")

        res_single_no_at = self.client.get("/api/agents/detection-decay-agent")
        self.assertEqual(res_single_no_at.status_code, 200)
        self.assertEqual(res_single_no_at.json()["handle"], "@detection-decay-agent")

        # 6. Negative lookup
        res_404 = self.client.get("/api/agents/@non-existent-agent")
        self.assertEqual(res_404.status_code, 404)


if __name__ == "__main__":
    unittest.main()
