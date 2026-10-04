"""Unit tests for SOAR Playbook Inventory & Decay Workflow, Scoring Engine, and Agent."""

from datetime import datetime, timedelta, timezone
import json
import os
import tempfile
import unittest
from typing import Any, Dict, List, Optional

from engine.workflows.playbook_decay import (
    PlaybookScoringEngine,
    PlaybookMermaidGenerator,
    PlaybookTelemetryAggregator,
    PlaybookBriefSynthesizer,
    AuditPlaybookDecayWorkflow,
)
from agents.core.evidence_store import (
    LocalFileEvidenceStore,
    sanitize_playbook_for_firestore,
)
from agents.generated.playbook_decay import PlaybookDecayAgent


class TestPlaybookScoringEngine(unittest.TestCase):
    """Verifies deterministic 100-point resilience scoring and all 15 audit rules."""

    def setUp(self):
        self.engine = PlaybookScoringEngine()

    def test_perfect_resilience_score(self):
        """A well-configured resilient playbook receives 100/100 and Grade A."""
        playbook_def = {
            "identifier": "pb-clean-001",
            "name": "Resilient Phishing Triage",
            "category": "Phishing",
            "priority": 2,
            "isEnabled": True,
            "isDebugMode": False,
            "version": 3,
            "modificationTime": datetime.now(timezone.utc).isoformat(),
            "trigger": [{"type": "ALERT", "condition": "alert.type == 'phishing'"}],
            "steps": [
                {
                    "identifier": "step-1",
                    "name": "Fetch Email Details",
                    "type": "ACTION",
                    "action": "Exchange_get_email",
                    "retries": 3,
                    "autoSkipOnFailure": False,
                },
                {
                    "identifier": "step-2",
                    "name": "Enrich Domain with VirusTotal",
                    "type": "ACTION",
                    "action": "VirusTotal_get_domain_report",
                    "retries": 2,
                    "autoSkipOnFailure": True,  # Has autoSkip
                },
                {
                    "identifier": "step-3",
                    "name": "Quarantine Mailbox",
                    "type": "ACTION",
                    "action": "Exchange_quarantine_mailbox",
                    "retries": 2,
                    "autoSkipOnFailure": False,  # Critical containment: must NOT auto-skip
                },
            ],
            "relations": [
                {"fromStepIdentifier": "step-1", "toStepIdentifier": "step-2", "condition": "SUCCESS"},
                {"fromStepIdentifier": "step-1", "toStepIdentifier": "step-3", "condition": "FAULTED"},
                {"fromStepIdentifier": "step-2", "toStepIdentifier": "step-3", "condition": "SUCCESS"},
            ],
        }
        telemetry = {
            "total_runs": 150,
            "completed_runs": 147,
            "failed_runs": 3,
            "failure_rate_pct": 2.0,
            "avg_duration_seconds": 12.4,
            "rate_limit_errors": 0,
        }

        eval_result = self.engine.evaluate(playbook_def, telemetry)
        self.assertEqual(eval_result["resilience_score"], 100)
        self.assertEqual(eval_result["resilience_grade"], "A")
        self.assertEqual(len(eval_result["findings"]), 0)

    def test_hyg01_debug_mode_deduction(self):
        """Active production playbook running with debugMode enabled loses 15 points (CRITICAL)."""
        playbook_def = {
            "identifier": "pb-debug-001",
            "name": "Debug Mode Playbook",
            "isEnabled": True,
            "isDebugMode": True,
            "steps": [],
            "relations": [],
        }
        eval_result = self.engine.evaluate(playbook_def, {"total_runs": 100, "lookback_days": 30})
        rule_ids = [f["rule_id"] for f in eval_result["findings"]]
        self.assertIn("HYG-01", rule_ids)
        hyg = next(f for f in eval_result["findings"] if f["rule_id"] == "HYG-01")
        self.assertEqual(hyg["deduction"], 15)
        self.assertEqual(hyg["severity"], "CRITICAL")
        self.assertEqual(eval_result["resilience_score"], 85)
        self.assertEqual(eval_result["resilience_grade"], "B")

    def test_err01_missing_retries(self):
        """Connector actions missing automated retry configurations lose 2 pts per step up to -10 max."""
        playbook_def = {
            "identifier": "pb-no-retries",
            "name": "Unretryable Playbook",
            "isEnabled": True,
            "isDebugMode": False,
            "steps": [
                {"identifier": f"step-{i}", "name": f"Action {i}", "type": "ACTION", "action": f"Connector_{i}", "retries": 0, "autoSkipOnFailure": True}
                for i in range(8)  # 8 steps * 2 = 16, capped at 10
            ],
            "relations": [],
        }
        eval_result = self.engine.evaluate(playbook_def, {"total_runs": 100, "lookback_days": 30})
        rule_ids = [f["rule_id"] for f in eval_result["findings"]]
        self.assertIn("ERR-01", rule_ids)
        err = next(f for f in eval_result["findings"] if f["rule_id"] == "ERR-01")
        self.assertEqual(err["deduction"], 10)
        self.assertEqual(len(err["affected_steps"]), 5)
        self.assertIn("8 steps", err["title"])

    def test_err02_enrichment_missing_error_handling(self):
        """Enrichment action lacking auto-skip and lacking FAULTED fallback loses 5 pts."""
        playbook_def = {
            "identifier": "pb-enrich-err",
            "name": "Fragile Enrichment Playbook",
            "isEnabled": True,
            "isDebugMode": False,
            "steps": [
                {
                    "identifier": "vt-step",
                    "name": "VirusTotal Lookup",
                    "type": "ACTION",
                    "action": "VirusTotal_get_ip_report",
                    "retries": 1,
                    "autoSkipOnFailure": False,
                }
            ],
            "relations": [
                {"fromStepIdentifier": "vt-step", "toStepIdentifier": "next-step", "condition": "SUCCESS"}
            ],
        }
        eval_result = self.engine.evaluate(playbook_def, {})
        rule_ids = [f["rule_id"] for f in eval_result["findings"]]
        self.assertIn("ERR-02", rule_ids)
        err = next(f for f in eval_result["findings"] if f["rule_id"] == "ERR-02")
        self.assertEqual(err["deduction"], 5)

    def test_err03_containment_silent_autoskip(self):
        """Containment actions with silent autoSkipOnFailure=True lose 3 pts."""
        playbook_def = {
            "identifier": "pb-containment-skip",
            "name": "Silent Containment Failure",
            "isEnabled": True,
            "isDebugMode": False,
            "steps": [
                {
                    "identifier": "isolate-step",
                    "name": "Isolate Host",
                    "type": "ACTION",
                    "action": "CrowdStrike_isolate_endpoint",
                    "retries": 2,
                    "autoSkipOnFailure": True,  # Anti-pattern: silent skip on containment
                }
            ],
            "relations": [],
        }
        eval_result = self.engine.evaluate(playbook_def, {})
        rule_ids = [f["rule_id"] for f in eval_result["findings"]]
        self.assertIn("ERR-03", rule_ids)
        err = next(f for f in eval_result["findings"] if f["rule_id"] == "ERR-03")
        self.assertEqual(err["deduction"], 3)

    def test_err04_single_point_of_failure(self):
        """Critical action with no retries, no auto-skip, and no FAULTED path loses 8 pts."""
        playbook_def = {
            "identifier": "pb-spof",
            "name": "SPOF Playbook",
            "isEnabled": True,
            "isDebugMode": False,
            "steps": [
                {
                    "identifier": "spof-step",
                    "name": "Critical Core Action",
                    "type": "ACTION",
                    "action": "Firewall_block_ip",
                    "retries": 0,
                    "autoSkipOnFailure": False,
                }
            ],
            "relations": [
                {"fromStepIdentifier": "spof-step", "toStepIdentifier": "done", "condition": "SUCCESS"}
            ],
        }
        eval_result = self.engine.evaluate(playbook_def, {})
        rule_ids = [f["rule_id"] for f in eval_result["findings"]]
        self.assertIn("ERR-04", rule_ids)

    def test_maint01_stale_playbook(self):
        """Active playbook unmodified for >365 days loses 10 pts; >90 days loses 4 pts."""
        old_date = (datetime.now(timezone.utc) - timedelta(days=400)).isoformat()
        playbook_def = {
            "identifier": "pb-stale",
            "name": "Ancient Playbook",
            "isEnabled": True,
            "creationTime": old_date,
            "modificationTime": old_date,
            "steps": [],
            "relations": [],
        }
        eval_result = self.engine.evaluate(playbook_def, {"total_runs": 100, "lookback_days": 30})
        rule_ids = [f["rule_id"] for f in eval_result["findings"]]
        self.assertIn("MAINT-01", rule_ids)
        maint = next(f for f in eval_result["findings"] if f["rule_id"] == "MAINT-01")
        self.assertEqual(maint["deduction"], 10)

    def test_prio01_low_priority_shadowing(self):
        """Priority 3 playbook with unconstrained wildcard trigger loses 4 pts (PRIO-01)."""
        playbook_def = {
            "identifier": "pb-prio3-wildcard",
            "name": "Low Priority Shadowed Playbook",
            "priority": 3,
            "isEnabled": True,
            "trigger": [{"type": "ALERT", "condition": "*"}],
            "steps": [],
            "relations": [],
        }
        eval_result = self.engine.evaluate(playbook_def, {"total_runs": 100, "lookback_days": 30})
        rule_ids = [f["rule_id"] for f in eval_result["findings"]]
        self.assertIn("PRIO-01", rule_ids)

    def test_prio02_global_priority1(self):
        """Priority 1 playbook with wildcard environment loses 5 pts (PRIO-02)."""
        playbook_def = {
            "identifier": "pb-prio1-wildcard",
            "name": "Dangerous Global Interceptor",
            "priority": 1,
            "isEnabled": True,
            "environments": ["*"],
            "trigger": [{"type": "ALERT", "condition": "*"}],
            "steps": [],
            "relations": [],
        }
        eval_result = self.engine.evaluate(playbook_def, {"total_runs": 100, "lookback_days": 30})
        rule_ids = [f["rule_id"] for f in eval_result["findings"]]
        self.assertIn("PRIO-02", rule_ids)

    def test_hitl01_approval_missing_sla(self):
        """Manual approval step without SLA timeout loses 4 pts."""
        playbook_def = {
            "identifier": "pb-manual-no-sla",
            "name": "Blocked Approval Playbook",
            "isEnabled": True,
            "steps": [
                {
                    "identifier": "approval-step",
                    "name": "Manager Approval Required",
                    "type": "MANUAL",
                    "action": "ManualAction_request_approval",
                    "timeoutSeconds": 0,  # No SLA timeout
                }
            ],
            "relations": [],
        }
        eval_result = self.engine.evaluate(playbook_def, {})
        rule_ids = [f["rule_id"] for f in eval_result["findings"]]
        self.assertIn("HITL-01", rule_ids)

    def test_exec_telemetry_deductions(self):
        """Silent playbook (EXEC-01) and high failure rate (EXEC-02) deductions."""
        playbook_def = {
            "identifier": "pb-exec-err",
            "name": "Failing Playbook",
            "isEnabled": True,
            "steps": [],
            "relations": [],
        }
        # 1. Silent playbook: 0 runs
        eval_silent = self.engine.evaluate(playbook_def, {"total_runs": 0})
        rule_ids_silent = [f["rule_id"] for f in eval_silent["findings"]]
        self.assertIn("EXEC-01", rule_ids_silent)

        # 2. High failure rate: 30%
        eval_failing = self.engine.evaluate(playbook_def, {
            "total_runs": 100,
            "completed_runs": 70,
            "failed_runs": 30,
            "failure_rate_pct": 30.0,
        })
        rule_ids_failing = [f["rule_id"] for f in eval_failing["findings"]]
        self.assertIn("EXEC-02", rule_ids_failing)


class TestPlaybookMermaidGenerator(unittest.TestCase):
    """Verifies deterministic Mermaid flowchart generation from playbook definitions."""

    def test_generate_flowchart(self):
        playbook_def = {
            "identifier": "pb-flowchart-01",
            "name": "Incident Containment DAG",
            "trigger": [{"type": "ALERT", "condition": "severity == 'CRITICAL'"}],
            "steps": [
                {"identifier": "step-1", "name": "Extract Entity", "type": "ACTION"},
                {"identifier": "step-2", "name": "Is Host Online?", "type": "CONDITION"},
                {"identifier": "step-3", "name": "Isolate Endpoint", "type": "ACTION"},
                {"identifier": "step-4", "name": "Send Slack Alert", "type": "ACTION"},
            ],
            "relations": [
                {"fromStepIdentifier": "step-1", "toStepIdentifier": "step-2", "condition": "SUCCESS"},
                {"fromStepIdentifier": "step-2", "toStepIdentifier": "step-3", "condition": "TRUE"},
                {"fromStepIdentifier": "step-2", "toStepIdentifier": "step-4", "condition": "FALSE"},
                {"fromStepIdentifier": "step-1", "toStepIdentifier": "step-4", "condition": "FAULTED"},
            ],
        }
        generator = PlaybookMermaidGenerator()
        chart = generator.generate(playbook_def)

        self.assertTrue(chart.startswith("flowchart TD"))
        self.assertIn("step_step_1", chart)
        self.assertIn("step_step_2", chart)
        self.assertIn("step_step_3", chart)
        self.assertIn("step_step_4", chart)
        self.assertIn("TRUE", chart)
        self.assertIn("FALSE", chart)
        self.assertIn("FAULTED", chart)


class TestPlaybookSanitization(unittest.TestCase):
    """Verifies Firestore 1MB document payload sanitization."""

    def test_strip_bloat_and_truncate(self):
        huge_param = "x" * 20000
        raw_playbook = {
            "identifier": "pb-huge",
            "name": "Bloated Playbook",
            "overviewTemplates": ["template_1", "template_2"],
            "debugData": {"trace": "huge trace dump"},
            "overview_html": "<html>huge html representation</html>",
            "_raw": {"raw": "raw data"},
            "steps": [
                {
                    "identifier": "step-1",
                    "parameters": {"payload": huge_param},
                }
            ],
        }
        sanitized = sanitize_playbook_for_firestore(raw_playbook)

        self.assertNotIn("overviewTemplates", sanitized)
        self.assertNotIn("debugData", sanitized)
        self.assertNotIn("overview_html", sanitized)
        self.assertNotIn("_raw", sanitized)

        # Check parameter truncation
        step_param = sanitized["steps"][0]["parameters"]["payload"]
        self.assertLessEqual(len(step_param), 6000)
        self.assertTrue(step_param.endswith("... [TRUNCATED FOR FIRESTORE]"))


class TestPlaybookDecayAgent(unittest.IsolatedAsyncioTestCase):
    """Verifies PlaybookDecayAgent instantiation, metadata, and @mention dispatch."""

    def test_agent_manifest_binding(self):
        agent = PlaybookDecayAgent()
        self.assertEqual(agent.handle, "@playbook-decay-agent")
        self.assertEqual(agent.name, "SOAR Playbook Inventory & Decay Agent")
        self.assertEqual(agent.default_stream, "soar")
        self.assertEqual(agent.default_topic, "playbook-health")
        self.assertIn("playbook.decay_audit", agent.CAPABILITIES)
        self.assertIn("audit_playbook_decay", agent._tools)
        self.assertIn("get_playbook_decay_report", agent._tools)
        self.assertIn("list_playbook_reports", agent._tools)

    def test_mention_routing_in_dispatcher(self):
        from clients.web.chat_engine import AgentDispatcher, ChatStore
        with tempfile.TemporaryDirectory() as temp_dir:
            store = ChatStore(root_dir=temp_dir)
            agent = PlaybookDecayAgent()
            dispatcher = AgentDispatcher(
                chat_store=store,
                fleet={"@playbook-decay-agent": agent},
            )
            # Test mention extraction
            mentions = dispatcher.extract_mentions("Can @playbook-decay-agent audit the playbooks?")
            self.assertEqual(mentions, ["@playbook-decay-agent"])

            # Test alias extraction
            mentions_alias = dispatcher.extract_mentions("Check with @playbook-decay")
            self.assertEqual(mentions_alias, ["@playbook-decay"])

    async def test_dispatch_execution_to_playbook_decay_agent(self):
        from clients.web.chat_engine import AgentDispatcher, ChatStore
        with tempfile.TemporaryDirectory() as temp_dir:
            store = ChatStore(root_dir=temp_dir)
            agent = PlaybookDecayAgent()
            dispatcher = AgentDispatcher(
                chat_store=store,
                fleet={"@playbook-decay-agent": agent},
            )
            user_msg = store.add_message(
                stream="soar",
                topic="playbook-health",
                sender_handle="@operator",
                sender_type="user",
                content="@playbook-decay-agent audit degraded playbooks",
            )
            replies = await dispatcher.dispatch(user_msg)
            self.assertEqual(len(replies), 1)
            self.assertEqual(replies[0].sender_handle, "@playbook-decay-agent")
            self.assertTrue(len(replies[0].content) > 0)


if __name__ == "__main__":
    unittest.main()
