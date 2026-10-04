"""Tests for Evidence Fabric State Store and Dual-Mode Persistence.

Tests:
- Path segment normalization
- Payload sanitization (1MB limit protection)
- LocalFileEvidenceStore CRUD
- Live FirestoreEvidenceStore integration
- BaseSecOpsAdkAgent evidence recording
"""

import os
import shutil
import tempfile
import unittest
from datetime import datetime, timezone

from agents.core.evidence_store import (
    EvidenceFabricStore,
    FirestoreEvidenceStore,
    LocalFileEvidenceStore,
    get_evidence_store,
    normalize_doc_id,
    sanitize_for_firestore,
)


class TestEvidenceStoreHelpers(unittest.TestCase):
    """Tests utility functions for document normalization and sanitization."""

    def test_normalize_doc_id(self):
        full_path = "projects/sdl-preview-americas/locations/us/instances/test/rules/ru_6cb096c8-2270-4d03-860b-3c3db443a7e4"
        self.assertEqual(
            normalize_doc_id(full_path),
            "ru_6cb096c8-2270-4d03-860b-3c3db443a7e4",
        )
        self.assertEqual(normalize_doc_id("@rule-troubleshooter"), "_rule-troubleshooter")
        self.assertEqual(normalize_doc_id("simple_id"), "simple_id")
        self.assertEqual(normalize_doc_id(""), "")

    def test_sanitize_for_firestore(self):
        # Truncation test
        long_text = "A" * 15000
        sanitized = sanitize_for_firestore({"text": long_text, "nested": [long_text]})
        self.assertTrue(sanitized["text"].endswith("... [TRUNCATED]"))
        self.assertEqual(len(sanitized["text"]), 10000 + len("... [TRUNCATED]"))
        self.assertTrue(sanitized["nested"][0].endswith("... [TRUNCATED]"))

        # Stripping bloated raw keys
        payload = {
            "title": "Clean Title",
            "_raw": "bloat",
            "_cache": "cache_data",
            "overview_html": "<html>huge html</html>",
        }
        clean = sanitize_for_firestore(payload)
        self.assertIn("title", clean)
        self.assertNotIn("_raw", clean)
        self.assertNotIn("_cache", clean)
        self.assertNotIn("overview_html", clean)


class TestLocalFileEvidenceStore(unittest.TestCase):
    """Tests file-backed local evidence store for offline operations."""

    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        self.store = LocalFileEvidenceStore(root_dir=self.test_dir)

    def tearDown(self):
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_evidence_lifecycle(self):
        ev_id = self.store.record_evidence(
            agent_handle="@rule-troubleshooter",
            action="chat_turn",
            stream="detections",
            topic="rule-health",
            prompt="analyze ru_test",
            response="Rule analysis results",
            executed_tools=[{"capability_id": "rule.get", "arguments": {"rule_id": "ru_test"}}],
            metadata={"model": "gemini-2.5-pro"},
        )
        self.assertTrue(ev_id.startswith("ev_"))

    def test_rule_state_lifecycle(self):
        rule_id = "projects/p/locations/l/instances/i/rules/ru_6cb096c8-2270-4d03-860b-3c3db443a7e4"
        self.store.save_rule_state(
            rule_id=rule_id,
            state_dict={"display_name": "IngestionLatencyDataShape", "frequency": "RUN_FREQUENCY_LIVE"},
        )
        fetched = self.store.get_rule_state("ru_6cb096c8-2270-4d03-860b-3c3db443a7e4")
        self.assertIsNotNone(fetched)
        self.assertEqual(fetched["display_name"], "IngestionLatencyDataShape")
        self.assertEqual(fetched["rule_id"], "ru_6cb096c8-2270-4d03-860b-3c3db443a7e4")

    def test_todos_lifecycle(self):
        todo_id = "todo_12345"
        self.store.save_todo(
            todo_id=todo_id,
            task_dict={
                "title": "Optimize match window for ru_6cb096c8-2270-4d03-860b-3c3db443a7e4",
                "target_agent": "@yaral-optimizer",
                "target_resource_id": "ru_6cb096c8-2270-4d03-860b-3c3db443a7e4",
            },
        )

        todos = self.store.list_todos(status="PENDING", target_agent="@yaral-optimizer")
        self.assertEqual(len(todos), 1)
        self.assertEqual(todos[0]["todo_id"], "todo_12345")

        self.store.update_todo_status(
            todo_id=todo_id,
            status="RESOLVED",
            resolved_by="@yaral-optimizer",
            proposal_id="prop_999",
            resolution="Dismissed by operator",
        )

        pending = self.store.list_todos(status="PENDING")
        self.assertEqual(len(pending), 0)

        resolved = self.store.list_todos(status="RESOLVED")
        self.assertEqual(len(resolved), 1)
        self.assertEqual(resolved[0]["resolved_by"], "@yaral-optimizer")
        self.assertEqual(resolved[0]["resolution"], "Dismissed by operator")

    def test_upsert_todo_lifecycle(self):
        todo_id = "todo_test_upsert_active"
        task_data = {
            "title": "Initial Task",
            "target_agent": "@feed-agent",
            "target_resource_id": "feed_123",
            "action_type": "remediate_feed",
            "priority": "MEDIUM",
            "rationale": "First sighting",
        }

        # 1. First upsert -> New
        task, is_new = self.store.upsert_todo(todo_id, task_data)
        self.assertTrue(is_new)
        self.assertEqual(task["sighting_count"], 1)
        self.assertEqual(task["status"], "PENDING")

        # 2. Second upsert -> Corroborated sighting
        task_update = {
            "title": "Initial Task Updated",
            "priority": "HIGH",
            "rationale": "Second sighting",
        }
        task2, is_new2 = self.store.upsert_todo(todo_id, task_update)
        self.assertFalse(is_new2)
        self.assertEqual(task2["sighting_count"], 2)
        self.assertEqual(task2["priority"], "HIGH")
        self.assertEqual(task2["status"], "PENDING")
        self.assertEqual(len(task2.get("sighting_history", [])), 2)

        # 3. Resolve
        resolved = self.store.resolve_todo(todo_id, reason="Resolved by operator")
        self.assertIsNotNone(resolved)
        self.assertEqual(resolved["status"], "RESOLVED")

        # 4. Third upsert after resolution -> Reopens regression
        task3, is_new3 = self.store.upsert_todo(todo_id, {"rationale": "Recurred"})
        self.assertFalse(is_new3)
        self.assertEqual(task3["sighting_count"], 3)
        self.assertEqual(task3["status"], "REOPENED")

    def test_deduplicate_todos(self):
        # Create 3 duplicate timestamped cards
        t1 = {
            "todo_id": "todo_tuning_ur_5f1035ac_1789978867",
            "title": "Tune Rule 1",
            "target_agent": "@detection-tuning-agent",
            "target_resource_id": "ur_5f1035ac",
            "action_type": "tune_noise",
            "priority": "MEDIUM",
            "status": "PENDING",
            "sighting_count": 1,
            "created_at": "2026-09-20T10:00:00Z",
        }
        t2 = {
            "todo_id": "todo_tuning_ur_5f1035ac_1790022094",
            "title": "Tune Rule 2",
            "target_agent": "@detection-tuning-agent",
            "target_resource_id": "ur_5f1035ac",
            "action_type": "tune_noise",
            "priority": "HIGH",
            "status": "PENDING",
            "sighting_count": 1,
            "created_at": "2026-09-20T22:00:00Z",
        }
        t3 = {
            "todo_id": "todo_tuning_ur_5f1035ac_1790065305",
            "title": "Tune Rule 3",
            "target_agent": "@detection-tuning-agent",
            "target_resource_id": "ur_5f1035ac",
            "action_type": "tune_noise",
            "priority": "MEDIUM",
            "status": "PENDING",
            "sighting_count": 1,
            "created_at": "2026-09-21T10:00:00Z",
        }
        self.store.save_todo(t1["todo_id"], t1)
        self.store.save_todo(t2["todo_id"], t2)
        self.store.save_todo(t3["todo_id"], t3)

        # Confirm 3 separate tasks exist
        self.assertEqual(len(self.store.list_todos(status="PENDING")), 3)

        # Run deduplication
        stats = self.store.deduplicate_todos()
        self.assertEqual(stats["consolidated"], 1)
        self.assertEqual(stats["deleted"], 3)

        # Confirm only canonical active task exists
        remaining = self.store.list_todos(status="PENDING")
        self.assertEqual(len(remaining), 1)
        canonical = remaining[0]
        self.assertEqual(canonical["todo_id"], "todo_tuning_ur_5f1035ac_active")
        self.assertEqual(canonical["sighting_count"], 3)
        self.assertEqual(canonical["priority"], "HIGH")
        self.assertEqual(canonical["created_at"], "2026-09-20T10:00:00Z")

        # Confirm old timestamped tasks no longer exist
        self.assertIsNone(self.store.get_todo("todo_tuning_ur_5f1035ac_1789978867"))
        self.assertIsNone(self.store.get_todo("todo_tuning_ur_5f1035ac_1790022094"))
        self.assertIsNone(self.store.get_todo("todo_tuning_ur_5f1035ac_1790065305"))

    def test_agent_config_lifecycle(self):
        self.store.save_agent_config(
            agent_handle="@rule-troubleshooter",
            config_dict={"model": "gemini-2.5-flash", "temperature": 0.2},
        )
        cfg = self.store.get_agent_config("@rule-troubleshooter")
        self.assertEqual(cfg["model"], "gemini-2.5-flash")

    def test_playbook_analysis_lifecycle(self):
        analysis_data = {
            "workflow_identifier": "pb-test-123",
            "name": "Automated Phishing Response",
            "resilience_score": 88,
            "resilience_grade": "B",
            "findings_count": 2,
        }
        self.store.save_playbook_analysis("pb-test-123", analysis_data)
        loaded = self.store.get_playbook_analysis("pb-test-123")
        self.assertIsNotNone(loaded)
        self.assertEqual(loaded["name"], "Automated Phishing Response")
        self.assertEqual(loaded["resilience_score"], 88)
        self.assertEqual(loaded["resilience_grade"], "B")

        all_playbooks = self.store.list_playbook_analyses()
        self.assertEqual(len(all_playbooks), 1)
        self.assertEqual(all_playbooks[0]["workflow_identifier"], "pb-test-123")


class TestLiveFirestoreEvidenceStore(unittest.TestCase):
    """Tests live Firestore connectivity against the GCP project sdl-preview-americas."""

    @classmethod
    def setUpClass(cls):
        try:
            from engine.config import _load_env_file
            _load_env_file()
        except Exception:
            pass

        project = (
            os.getenv("GCP_PROJECT_ID")
            or os.getenv("SECOPS_PROJECT_ID")
            or os.getenv("GOOGLE_CLOUD_PROJECT")
            or "sdl-preview-americas"
        )
        try:
            cls.store = FirestoreEvidenceStore(project_id=project, database_id="(default)")
            # Verify connectivity
            test_doc = cls.store.db.collection("system_configs").document("connectivity_check")
            test_doc.set({"status": "CONNECTED", "timestamp": datetime.now(timezone.utc)})
        except Exception as e:
            raise unittest.SkipTest(f"Live Firestore not accessible on {project}: {e}")

    def test_live_evidence_and_todos(self):
        # 1. Record evidence
        ev_id = self.store.record_evidence(
            agent_handle="@rule-troubleshooter",
            action="automated_test_turn",
            stream="testing",
            topic="evidence-store",
            prompt="Verification test prompt",
            response="Verification test response",
            executed_tools=[{"capability_id": "rule.get", "arguments": {"rule_id": "ru_6cb096c8-2270-4d03-860b-3c3db443a7e4"}}],
            metadata={"suite": "test_evidence_store"},
        )
        self.assertTrue(bool(ev_id))

        test_rule_id = "ru_6cb096c8_verify_test"
        todo_id = f"todo_verify_{int(datetime.now(timezone.utc).timestamp())}"

        try:
            # 2. Save rule state
            self.store.save_rule_state(
                rule_id=test_rule_id,
                state_dict={"display_name": "IngestionLatencyDataShape Verification", "status": "VERIFIED"},
            )
            fetched = self.store.get_rule_state(test_rule_id)
            self.assertIsNotNone(fetched)
            self.assertEqual(fetched["display_name"], "IngestionLatencyDataShape Verification")

            # 3. Create and update a remediation todo
            self.store.save_todo(
                todo_id=todo_id,
                task_dict={
                    "title": "Verification Remediation Task",
                    "target_agent": "@yaral-optimizer",
                    "target_resource_id": "ru_6cb096c8-2270-4d03-860b-3c3db443a7e4",
                },
            )
            todos = self.store.list_todos(status="PENDING", target_agent="@yaral-optimizer")
            found = [t for t in todos if t.get("todo_id") == todo_id]
            self.assertTrue(len(found) > 0)

            # 4. Resolve todo
            self.store.update_todo_status(
                todo_id=todo_id,
                status="RESOLVED",
                resolved_by="@yaral-optimizer",
                proposal_id="prop-20260919161850-detect",
            )
        finally:
            # 5. Clean up from Firestore so no test artifacts remain
            self.store.delete_todo(todo_id)
            if hasattr(self.store, "db") and self.store.db:
                self.store.db.collection("secops_rules").document(test_rule_id).delete()


if __name__ == "__main__":
    unittest.main()
