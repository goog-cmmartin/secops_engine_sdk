"""Integration tests verifying Gas Town Board & Multi-Agent Fleet parameter coherence."""

from pathlib import Path
import tempfile
import unittest
from unittest import mock

from fastapi.testclient import TestClient

from agents.core.evidence_store import LocalFileEvidenceStore
import clients.web.server as web_server
from clients.web.server import app, fleet

# Explicit test fixtures. Production no longer seeds default todos, so every test
# that needs tasks creates them in an isolated temp store (never the live store).
FIXTURE_RULE_ID = "ru_test_fixture_0001"
FIXTURE_TODOS = [
    {
        "todo_id": "todo_test_decay",
        "title": "Evaluate rule decay for fixture rule",
        "target_agent": "@detection-decay-agent",
        "target_resource_id": FIXTURE_RULE_ID,
        "action_type": "audit_decay",
        "stream": "detections",
        "topic": "decay-review",
        "priority": "HIGH",
        "status": "PENDING",
        "action_prompt": f"@detection-decay-agent audit rule {FIXTURE_RULE_ID}",
        "rationale": "Test fixture.",
    },
    {
        "todo_id": "todo_test_tuning",
        "title": "Tune noise for fixture rule",
        "target_agent": "@detection-tuning-agent",
        "target_resource_id": FIXTURE_RULE_ID,
        "action_type": "tune_noise",
        "stream": "detections",
        "topic": "tuning-review",
        "priority": "MEDIUM",
        "status": "IN_PROGRESS",
        "action_prompt": f"@detection-tuning-agent tune rule {FIXTURE_RULE_ID}",
        "rationale": "Test fixture.",
    },
]


def _seed(store: LocalFileEvidenceStore) -> None:
    for todo in FIXTURE_TODOS:
        store.save_todo(todo["todo_id"], dict(todo))


class GasTownParameterCoherenceTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.store = LocalFileEvidenceStore(base_dir=self._tmp.name)
        _seed(self.store)

        self._patches = [mock.patch.object(web_server, "evidence_store", self.store)]
        for agent in fleet.values():
            if hasattr(agent, "evidence_store"):
                self._patches.append(mock.patch.object(agent, "evidence_store", self.store))
        for patcher in self._patches:
            patcher.start()

        self.client = TestClient(app)

    def tearDown(self):
        for patcher in reversed(self._patches):
            patcher.stop()
        self._tmp.cleanup()

    def test_no_deprecated_or_fake_handles_in_frontend(self):
        """Ensures no fabricated tasks or non-existent agents exist in app.js."""
        app_js_path = Path(__file__).resolve().parent.parent / "clients" / "web" / "static" / "app.js"
        self.assertTrue(app_js_path.exists(), "app.js should exist")
        content = app_js_path.read_text(encoding="utf-8")

        banned_terms = [
            "@decay-sentinel",
            "@rule-curator",
            "WORK-109",
            "WORK-110",
            "TASK-041",
            "TASK-042",
        ]
        for term in banned_terms:
            self.assertNotIn(term, content, f"Deprecated or fabricated identifier '{term}' found in app.js")

    def test_gastown_overview_coherence(self):
        """Verifies that /api/gastown/overview returns live, cohesive resources and assignees."""
        res = self.client.get("/api/gastown/overview")
        self.assertEqual(res.status_code, 200)
        data = res.json()

        # Check required root keys
        self.assertIn("mayor", data)
        self.assertIn("health", data)
        self.assertIn("summary", data)
        self.assertIn("convoys", data)
        self.assertIn("escalations", data)
        self.assertIn("todos_pending", data)
        self.assertIn("todos_in_progress", data)

        fleet_handles = set(fleet.keys())

        # Verify Todos Pending
        todos_pending = data["todos_pending"]
        self.assertIsInstance(todos_pending, list)
        self.assertGreater(len(todos_pending), 0, "Fixture pending tasks should be listed")
        for task in todos_pending:
            self.assertIn("todo_id", task)
            self.assertIn("target_agent", task)
            self.assertIn(task["target_agent"], fleet_handles, f"Target agent {task['target_agent']} must exist in fleet")
            self.assertIn("target_resource_id", task)
            self.assertIn("action_prompt", task)
            self.assertIn(task["target_agent"], task["action_prompt"])
            self.assertIn("stream", task)
            self.assertIn("topic", task)

        # Verify Todos In Progress
        todos_in_progress = data["todos_in_progress"]
        self.assertIsInstance(todos_in_progress, list)
        self.assertGreater(len(todos_in_progress), 0, "Fixture in-progress tasks should be listed")
        for task in todos_in_progress:
            self.assertIn("todo_id", task)
            self.assertIn("target_agent", task)
            self.assertIn(task["target_agent"], fleet_handles, f"Target agent {task['target_agent']} must exist in fleet")
            self.assertIn("action_prompt", task)
            self.assertIn(task["target_agent"], task["action_prompt"])
            self.assertIn("stream", task)
            self.assertIn("topic", task)

        # Verify Convoys
        convoys = data["convoys"]
        self.assertGreater(len(convoys), 0)
        for convoy in convoys:
            self.assertIn("primary_agent", convoy)
            self.assertIn(convoy["primary_agent"], fleet_handles, f"Primary agent {convoy['primary_agent']} must exist in fleet")
            for assignee in convoy["assignees"]:
                self.assertIn(assignee, fleet_handles, f"Assignee {assignee} must exist in fleet")
            self.assertIn("action_prompt", convoy)
            self.assertIn("stream", convoy)
            self.assertIn("topic", convoy)

        # Verify Escalations
        escalations = data["escalations"]
        self.assertGreater(len(escalations), 0)
        for esc in escalations:
            self.assertIn("escalated_by", esc)
            self.assertIn(esc["escalated_by"], fleet_handles, f"Escalator {esc['escalated_by']} must exist in fleet")
            self.assertIn("action_prompt", esc)
            self.assertIn("stream", esc)
            self.assertIn("topic", esc)

    def test_todos_api_endpoints(self):
        """Verifies GET /api/todos and GET /api/todos/{todo_id}."""
        res = self.client.get("/api/todos?status=PENDING")
        self.assertEqual(res.status_code, 200)
        todos = res.json()
        self.assertGreater(len(todos), 0)
        first_todo_id = todos[0]["todo_id"]

        # Single fetch
        single_res = self.client.get(f"/api/todos/{first_todo_id}")
        self.assertEqual(single_res.status_code, 200)
        single_todo = single_res.json()
        self.assertEqual(single_todo["todo_id"], first_todo_id)

    def test_evidence_store_get_todo(self):
        """Verifies get_todo in LocalFileEvidenceStore."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            store = LocalFileEvidenceStore(base_dir=tmp_dir)
            _seed(store)

            decay_task = store.get_todo("todo_test_decay")
            self.assertIsNotNone(decay_task)
            self.assertEqual(decay_task["target_resource_id"], FIXTURE_RULE_ID)
            self.assertEqual(decay_task["target_agent"], "@detection-decay-agent")

            nonexistent = store.get_todo("nonexistent_task_999")
            self.assertIsNone(nonexistent)

    def test_base_adk_agent_get_task_status_tool(self):
        """Verifies that all fleet agents have get_task_status tool equipped and functioning."""
        for handle, agent in fleet.items():
            self.assertIn("get_task_status", agent._tools, f"Agent {handle} must have get_task_status tool")

        # Test tool execution on detection-tuning-agent
        tuning_agent = fleet["@detection-tuning-agent"]
        status_res = tuning_agent.get_task_status("todo_test_tuning")
        self.assertTrue(status_res["found"])
        self.assertEqual(status_res["id"], "todo_test_tuning")
        self.assertEqual(status_res["target_resource_id"], FIXTURE_RULE_ID)
        self.assertEqual(status_res["target_agent"], "@detection-tuning-agent")

        # Test lookup for unknown identifier
        unknown_res = tuning_agent.get_task_status("unknown_id_xyz")
        self.assertFalse(unknown_res["found"])

    def test_zero_mock_or_synthetic_data_in_api(self):
        """Verifies that no mock, fixture, dummy, fake, or sample data exists in live endpoints."""
        banned_terms = ["sample", "dummy", "fake", "placeholder", "ru_sample"]

        # 1. Inspect GET /api/todos
        res_todos = self.client.get("/api/todos?limit=100")
        self.assertEqual(res_todos.status_code, 200)
        for todo in res_todos.json():
            todo_str = f"{todo.get('todo_id', '')} {todo.get('target_resource_id', '')} {todo.get('title', '')}".lower()
            for banned in banned_terms:
                self.assertNotIn(banned, todo_str, f"Banned term '{banned}' found in todo: {todo}")

        # 2. Inspect GET /api/gastown/overview
        res_gt = self.client.get("/api/gastown/overview")
        self.assertEqual(res_gt.status_code, 200)
        gt_data = res_gt.json()
        for todo in gt_data.get("todos_pending", []):
            todo_str = f"{todo.get('todo_id', '')} {todo.get('target_resource_id', '')} {todo.get('title', '')}".lower()
            for banned in banned_terms:
                self.assertNotIn(banned, todo_str, f"Banned term '{banned}' found in Gas Town todo: {todo}")

        # 3. Inspect GET /api/proposals
        res_props = self.client.get("/api/proposals?limit=100")
        self.assertEqual(res_props.status_code, 200)
        for prop in res_props.json():
            prop_str = f"{prop.get('id', '')} {prop.get('target_resource_id', '')} {prop.get('title', '')}".lower()
            for banned in banned_terms:
                self.assertNotIn(banned, prop_str, f"Banned term '{banned}' found in proposal: {prop}")
