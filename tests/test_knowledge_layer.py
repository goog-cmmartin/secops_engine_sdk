"""Unit and integration tests for the SOC Operational Picture, Shared Knowledge Layer,
Communication Router, and Deterministic Shift Aggregation Engine.
"""

from datetime import datetime, timedelta, timezone
from pathlib import Path
import tempfile
import unittest

from agents.core.communication_router import CommunicationRouter
from agents.core.knowledge_store import (
    BaseKnowledgeStore,
    LocalKnowledgeStore,
    _synthesize_entity_dossier,
    get_knowledge_store,
)
from agents.core.materializer import IssueMaterializer
from agents.core.work_queue import LocalWorkQueue, get_work_queue
from engine.domain import (
    ChangeRecord,
    CommunicationClass,
    CommunicationPolicy,
    IssueLifecycleStatus,
    IssueProblem,
    IssueSeverity,
    IssueSource,
    KnowledgeGap,
    KnowledgeSnapshot,
    Lease,
    Observation,
    ObserverRef,
    SOCIssue,
    ShiftBriefing,
    SubjectRef,
)
from engine.facade import SecOpsEngine
from engine.workflows.briefing_aggregation import (
    compute_knowledge_snapshot,
    compute_shift_delta,
    format_slack_posture_report,
    format_slack_shift_brief,
)


class _InertAdapter:
    def __getattr__(self, name: str):
        def _no_op(*args, **kwargs):
            return {"status": "ok"}
        return _no_op


class KnowledgeLayerTest(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root_path = Path(self.temp_dir.name)
        self.knowledge_store = LocalKnowledgeStore(root_dir=self.root_path)
        self.work_queue = LocalWorkQueue(root_dir=self.root_path)
        self.materializer = IssueMaterializer(root_dir=self.root_path)
        self.router = CommunicationRouter(
            knowledge_store=self.knowledge_store,
            work_queue=self.work_queue,
            materializer=self.materializer,
        )
        self.engine = SecOpsEngine(adapter=_InertAdapter())

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_observation_model_and_staleness(self):
        now = datetime.now(timezone.utc)
        valid_until = (now + timedelta(hours=2)).isoformat()
        expired_until = (now - timedelta(hours=1)).isoformat()

        # Active observation
        obs_active = Observation(
            subject=SubjectRef(type="log_type", id="PAN_FIREWALL"),
            predicate="ingestion_status",
            value={"status": "STREAMING", "eps": 450},
            observed_by=ObserverRef(agent="@feed-agent", deacon="deacon_feed_01"),
            policy=CommunicationPolicy(routing_class=CommunicationClass.INFORMATIONAL),
            valid_until=valid_until,
            confidence=0.95,
        )
        self.assertFalse(obs_active.is_stale(as_of=now))
        self.assertEqual(obs_active.subject.id, "PAN_FIREWALL")
        self.assertEqual(obs_active.observed_by.agent, "@feed-agent")

        # Expired observation
        obs_expired = Observation(
            subject=SubjectRef(type="log_type", id="PAN_FIREWALL"),
            predicate="parser_health",
            value={"status": "UNKNOWN"},
            observed_by=ObserverRef(agent="@parser-doctor", deacon="deacon_parser_01"),
            policy=CommunicationPolicy(routing_class=CommunicationClass.INFORMATIONAL),
            valid_until=expired_until,
        )
        self.assertTrue(obs_expired.is_stale(as_of=now))

        # Dict roundtrip
        d = obs_active.to_dict()
        restored = Observation.from_dict(d)
        self.assertEqual(restored.observation_id, obs_active.observation_id)
        self.assertEqual(restored.predicate, "ingestion_status")
        self.assertEqual(restored.value.get("status"), "STREAMING")

    def test_local_knowledge_store_crud_and_query(self):
        obs1 = Observation(
            subject=SubjectRef(type="log_type", id="PAN_FIREWALL"),
            predicate="ingestion_status",
            value={"status": "HEALTHY"},
            observed_by=ObserverRef(agent="@feed-agent"),
            policy=CommunicationPolicy(routing_class=CommunicationClass.INFORMATIONAL),
        )
        obs2 = Observation(
            subject=SubjectRef(type="log_type", id="WINEVTLOG"),
            predicate="ingestion_status",
            value={"status": "HEALTHY"},
            observed_by=ObserverRef(agent="@feed-agent"),
            policy=CommunicationPolicy(routing_class=CommunicationClass.INFORMATIONAL),
        )
        obs3 = Observation(
            subject=SubjectRef(type="log_type", id="PAN_FIREWALL"),
            predicate="drop_rate",
            value={"drop_pct": 0.02},
            observed_by=ObserverRef(agent="@parser-doctor"),
            policy=CommunicationPolicy(routing_class=CommunicationClass.INFORMATIONAL),
        )

        id1 = self.knowledge_store.save_observation(obs1)
        id2 = self.knowledge_store.save_observation(obs2)
        id3 = self.knowledge_store.save_observation(obs3)

        self.assertEqual(id1, obs1.observation_id)
        self.assertEqual(id2, obs2.observation_id)
        self.assertEqual(id3, obs3.observation_id)

        # Query by subject
        pan_obs = self.knowledge_store.list_observations(subject_type="log_type", subject_id="PAN_FIREWALL")
        self.assertEqual(len(pan_obs), 2)

        # Query by observer agent
        parser_obs = self.knowledge_store.list_observations(observer_agent="@parser-doctor")
        self.assertEqual(len(parser_obs), 1)
        self.assertEqual(parser_obs[0].predicate, "drop_rate")

        # Query by predicate
        status_obs = self.knowledge_store.list_observations(predicate="ingestion_status")
        self.assertEqual(len(status_obs), 2)

    def test_communication_router_informational(self):
        obs = Observation(
            subject=SubjectRef(type="rule", id="ru_suspicious_powershell"),
            predicate="execution_cadence",
            value={"eval_interval_seconds": 300, "status": "NOMINAL"},
            observed_by=ObserverRef(agent="@detection-tuning-agent", deacon="deacon_rules_01"),
            policy=CommunicationPolicy(
                routing_class=CommunicationClass.INFORMATIONAL,
                publish_to_chat=False,
            ),
        )

        res = self.router.dispatch(obs)
        self.assertEqual(res["routing_class"], "informational")
        self.assertFalse(res["published_to_chat"])
        self.assertIsNone(res["issue_id"])

        # Saved in knowledge store
        found = self.knowledge_store.list_observations(subject_id="ru_suspicious_powershell")
        self.assertEqual(len(found), 1)

        # Zero issues in work queue
        issues = self.work_queue.list_issues()
        self.assertEqual(len(issues), 0)

    def test_communication_router_operational(self):
        obs = Observation(
            subject=SubjectRef(type="parser", id="cisco_asa"),
            predicate="error_rate_threshold",
            value={"error_pct": 0.15, "threshold": 0.05},
            observed_by=ObserverRef(agent="@parser-doctor", deacon="deacon_parser_01"),
            policy=CommunicationPolicy(
                routing_class=CommunicationClass.OPERATIONAL,
                publish_to_chat=False,
            ),
        )

        res = self.router.dispatch(obs)
        self.assertEqual(res["routing_class"], "operational")
        self.assertIsNotNone(res["issue_id"])

        # Issue created in work queue
        issue = self.work_queue.get_issue(res["issue_id"])
        self.assertIsNotNone(issue)
        self.assertEqual(issue.problem.title, "cisco_asa: error_rate_threshold")
        self.assertEqual(issue.status, IssueLifecycleStatus.AVAILABLE.value)

    def test_communication_router_urgent(self):
        obs = Observation(
            subject=SubjectRef(type="feed", id="feed_aws_cloudtrail_prod"),
            predicate="feed_fatal_auth_outage",
            value={"error": "InvalidCredentialsException", "consecutive_failures": 12},
            observed_by=ObserverRef(agent="@feed-agent", deacon="deacon_feed_01"),
            policy=CommunicationPolicy(
                routing_class=CommunicationClass.URGENT,
                publish_to_chat=True,
            ),
        )

        res = self.router.dispatch(obs)
        self.assertEqual(res["routing_class"], "urgent")
        self.assertTrue(res["published_to_chat"])
        self.assertIsNotNone(res["urgent_alert_card"])
        self.assertEqual(res["urgent_alert_card"]["type"], "urgent_alert_card")
        self.assertIsNotNone(res["issue_id"])

        # Issue created in work queue with CRITICAL severity
        issue = self.work_queue.get_issue(res["issue_id"])
        self.assertIsNotNone(issue)
        self.assertEqual(issue.severity, IssueSeverity.CRITICAL.value)

    def test_deterministic_shift_briefing_aggregation(self):
        now = datetime.now(timezone.utc)

        # 1. Open critical issue (Requires Attention)
        issue_crit = SOCIssue(
            id="SOC-CRIT-001",
            type="feed_outage",
            severity=IssueSeverity.CRITICAL.value,
            status=IssueLifecycleStatus.AVAILABLE.value,
            problem=IssueProblem(title="AWS CloudTrail Feed Ingestion Stalled"),
            created_at=now.isoformat(),
        )
        self.work_queue.create_issue(issue_crit)

        # 2. Closed verified issue in shift window (Changed Since Previous)
        issue_closed = SOCIssue(
            id="SOC-FIX-002",
            type="parser_fix",
            severity=IssueSeverity.MEDIUM.value,
            status=IssueLifecycleStatus.VERIFIED.value,
            problem=IssueProblem(title="Palo Alto Parser Timestamp Format Rectified"),
            created_at=(now - timedelta(hours=3)).isoformat(),
            closed_at=(now - timedelta(hours=1)).isoformat(),
        )
        self.work_queue.create_issue(issue_closed)

        # 3. Active lease (Agent Work In Progress)
        issue_wip = SOCIssue(
            id="SOC-WIP-003",
            type="rule_decay",
            severity=IssueSeverity.MEDIUM.value,
            status=IssueLifecycleStatus.CLAIMED.value,
            problem=IssueProblem(title="Refactoring deprecated UDM fields in rule ru_99"),
            lease=Lease(owner="@yaral-optimizer"),
            created_at=(now - timedelta(hours=2)).isoformat(),
        )
        self.work_queue.create_issue(issue_wip)

        # 4. Old carryover issue (opened 20h ago)
        issue_carryover = SOCIssue(
            id="SOC-OLD-004",
            type="namespace_collision",
            severity=IssueSeverity.LOW.value,
            status=IssueLifecycleStatus.AVAILABLE.value,
            problem=IssueProblem(title="RFC1918 overlap between VPC-A and VPC-B"),
            created_at=(now - timedelta(hours=20)).isoformat(),
        )
        self.work_queue.create_issue(issue_carryover)

        # 5. Verified positive baseline observation (No Action Required)
        obs_healthy = Observation(
            subject=SubjectRef(type="subsystem", id="ingestion"),
            predicate="health_attestation",
            value={"status": "NOMINAL", "feed_count": 42},
            observed_by=ObserverRef(agent="@feed-agent"),
            policy=CommunicationPolicy(routing_class=CommunicationClass.INFORMATIONAL),
        )
        self.knowledge_store.save_observation(obs_healthy)

        # Compute shift delta
        briefing = compute_shift_delta(
            shift_hours=8,
            shift_name="Mid Shift Handover",
            knowledge_store=self.knowledge_store,
            work_queue=self.work_queue,
            materializer=self.materializer,
        )

        self.assertIsInstance(briefing, ShiftBriefing)
        self.assertEqual(len(briefing.requires_attention), 1)
        self.assertEqual(briefing.requires_attention[0]["issue_id"], "SOC-CRIT-001")

        self.assertEqual(len(briefing.changed_since_previous), 1)
        self.assertEqual(briefing.changed_since_previous[0]["issue_id"], "SOC-FIX-002")

        self.assertEqual(len(briefing.agent_work_in_progress), 1)
        self.assertEqual(briefing.agent_work_in_progress[0]["issue_id"], "SOC-WIP-003")

        self.assertEqual(len(briefing.carry_over), 1)
        self.assertEqual(briefing.carry_over[0]["issue_id"], "SOC-OLD-004")

        self.assertIn("ingestion", briefing.no_action_required)
        self.assertIn("Requires Immediate Attention", briefing.summary_narrative)

        # Verify Slack block generator
        slack_blocks = format_slack_shift_brief(briefing)
        self.assertIn("blocks", slack_blocks)
        self.assertGreaterEqual(len(slack_blocks["blocks"]), 5)

    def test_knowledge_snapshot_and_gaps(self):
        now = datetime.now(timezone.utc)

        # Fresh observation (< 1h)
        self.knowledge_store.save_observation(Observation(
            subject=SubjectRef(type="log_type", id="PAN_FIREWALL"),
            predicate="parser_status",
            value={"status": "HEALTHY"},
            observed_by=ObserverRef(agent="@parser-doctor"),
            observed_at=now.isoformat(),
        ))
        # Recent observation (5h ago)
        self.knowledge_store.save_observation(Observation(
            subject=SubjectRef(type="log_type", id="GCP_CLOUDAUDIT"),
            predicate="parser_status",
            value={"status": "HEALTHY"},
            observed_by=ObserverRef(agent="@parser-doctor"),
            observed_at=(now - timedelta(hours=5)).isoformat(),
        ))
        # Stale observation (> 24h ago)
        self.knowledge_store.save_observation(Observation(
            subject=SubjectRef(type="log_type", id="WINEVTLOG"),
            predicate="parser_status",
            value={"status": "UNKNOWN"},
            observed_by=ObserverRef(agent="@parser-doctor"),
            observed_at=(now - timedelta(hours=36)).isoformat(),
        ))

        snapshot = compute_knowledge_snapshot(
            knowledge_store=self.knowledge_store,
            work_queue=self.work_queue,
            materializer=self.materializer,
        )

        self.assertIsInstance(snapshot, KnowledgeSnapshot)
        freshness = snapshot.knowledge_freshness
        self.assertEqual(freshness["fresh_under_1h"], 1)
        self.assertEqual(freshness["recent_1h_to_24h"], 1)
        self.assertEqual(freshness["stale_over_24h"], 1)

        # Check explicit knowledge gaps
        gaps = snapshot.knowledge_gaps
        self.assertGreaterEqual(len(gaps), 1)
        gap_ids = [g.gap_id for g in gaps]
        self.assertIn("gap-001", gap_ids)

        # Verify Slack report
        slack_report = format_slack_posture_report(snapshot)
        self.assertIn("blocks", slack_report)

    def test_composite_entity_dossier_synthesis(self):
        now = datetime.now(timezone.utc)
        observations = [
            Observation(
                subject=SubjectRef(type="log_type", id="PAN_FIREWALL"),
                predicate="source_classification",
                value={"vendor": "Palo Alto Networks", "product": "PAN-OS Firewall"},
                observed_by=ObserverRef(agent="@tenant-cartographer"),
                observed_at=(now - timedelta(hours=2)).isoformat(),
                confidence=1.0,
            ),
            Observation(
                subject=SubjectRef(type="log_type", id="PAN_FIREWALL"),
                predicate="parser_validation",
                value={"state": "HEALTHY", "drop_rate_pct": 0.01},
                observed_by=ObserverRef(agent="@parser-doctor"),
                observed_at=(now - timedelta(hours=1)).isoformat(),
                confidence=0.98,
            ),
            Observation(
                subject=SubjectRef(type="log_type", id="PAN_FIREWALL"),
                predicate="monthly_cost_estimate",
                value={"estimated_gb_day": 120, "tier": "ENTERPRISE"},
                observed_by=ObserverRef(agent="@log-cost-agent"),
                observed_at=now.isoformat(),
                confidence=0.92,
            ),
        ]

        dossier = _synthesize_entity_dossier("log_type", "PAN_FIREWALL", observations)
        self.assertEqual(dossier["subject_id"], "PAN_FIREWALL")
        self.assertEqual(dossier["status"], "HEALTHY")
        self.assertEqual(dossier["overall_health"], "healthy")
        self.assertEqual(len(dossier["contributing_agents"]), 3)
        self.assertIn("@tenant-cartographer", dossier["contributing_agents"])
        self.assertIn("@parser-doctor", dossier["contributing_agents"])
        self.assertIn("@log-cost-agent", dossier["contributing_agents"])

        # Check synthesized facts
        facts = dossier["facts"]
        self.assertIn("source_classification", facts)
        self.assertIn("parser_validation", facts)
        self.assertIn("monthly_cost_estimate", facts)
        self.assertEqual(dossier["confidence"], 0.92)


if __name__ == "__main__":
    unittest.main()
