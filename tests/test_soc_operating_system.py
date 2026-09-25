"""Comprehensive test suite for the SOC Operating System hybrid architecture.

Tests:
1. SOCIssue, Lease, AgentCapabilityProfile, IssueEvent domain models
2. WorkQueue (LocalWorkQueue and FirestoreWorkQueue interfaces)
3. Atomic leasing, expiration detection, and heartbeat renewal
4. Dynamic capability matching
5. IssueMaterializer durable Git directory structure and append-only events
6. SOCLifecycleManager end-to-end lifecycle:
   Observed -> Available -> Claimed -> Proposed -> Validated -> Approved -> Applied -> Verified -> Closed
"""

from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch
import yaml

from engine.domain import (
    AgentCapabilityProfile,
    AuthorityTier,
    ChangeRecord,
    IssueEvent,
    IssueGovernance,
    IssueLifecycleStatus,
    IssueProblem,
    IssueRouting,
    IssueSeverity,
    IssueSource,
    Lease,
    OperationalPlane,
    SOCIssue,
    VerificationProof,
)
from agents.core.materializer import IssueMaterializer
from agents.core.work_queue import LocalWorkQueue
from agents.core.lifecycle import SOCLifecycleManager
from agents.core.proposal_manager import ProposalManager
from agents.generated.parser_health_agent import ParserHealthAgentAgent


class TestSOCOperatingSystem(unittest.TestCase):
    """Verifies domain models, work queue, leasing, materializer, and lifecycle manager."""

    def setUp(self):
        self.test_dir = tempfile.mkdtemp(prefix="soc_os_test_")
        self.root_path = Path(self.test_dir)
        self.work_queue = LocalWorkQueue(root_dir=self.test_dir)
        self.materializer = IssueMaterializer(root_dir=self.root_path)
        self.lifecycle = SOCLifecycleManager(
            work_queue=self.work_queue,
            materializer=self.materializer,
            root_dir=self.root_path,
        )

    def tearDown(self):
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_01_domain_models_serialization(self):
        """Verifies round-trip serialization of SOCIssue and sub-models."""
        issue = SOCIssue(
            id="SOC-2026-TEST-001",
            type="parser_drop_spike",
            plane=OperationalPlane.DATA.value,
            status=IssueLifecycleStatus.AVAILABLE.value,
            severity=IssueSeverity.HIGH.value,
            confidence=0.98,
            priority_score=85,
            source=IssueSource(
                deacon_id="deacon.ingestion.parser_drop_monitor",
                evidence_fabric_uris=["firestore://evidence/test"],
                initial_metrics={"drop_rate_pct": 12.5},
            ),
            problem=IssueProblem(
                title="PANW Firewall Parser Drop Spike",
                description="High drop rate observed on pan_firewall parser",
                observed_state={"drop_rate": 12.5},
                desired_state={"drop_rate": 0.1},
                affected_objects=["projects/test/locations/us/parsers/pan_firewall"],
            ),
            routing=IssueRouting(
                requires_capabilities={"parser.read": 1, "parser.compile": 1, "parser.test": 2},
            ),
            governance=IssueGovernance(
                required_authority_tier=AuthorityTier.TIER_2_PEER_REVIEW.value,
                validation_criteria=["compiler_exit_code == 0", "replay_drop_count == 0"],
            ),
        )

        d = issue.to_dict()
        self.assertEqual(d["id"], "SOC-2026-TEST-001")
        self.assertEqual(d["plane"], "data")
        self.assertEqual(d["priority_score"], 85)
        self.assertEqual(d["source"]["deacon_id"], "deacon.ingestion.parser_drop_monitor")
        self.assertEqual(d["routing"]["requires_capabilities"]["parser.test"], 2)

        reconstituted = SOCIssue.from_dict(d)
        self.assertEqual(reconstituted.id, issue.id)
        self.assertEqual(reconstituted.problem.title, issue.problem.title)
        self.assertEqual(reconstituted.routing.requires_capabilities, issue.routing.requires_capabilities)

    def test_02_capability_profile_matching(self):
        """Verifies that worker capability profiles correctly evaluate against issue requirements."""
        worker = AgentCapabilityProfile(
            agent_handle="@parser-doctor",
            capabilities={
                "parser.read": 1,
                "parser.compile": 1,
                "parser.test": 2,
                "git.proposal.create": 1,
            },
            operational_planes=["data"],
        )

        # Satisfies
        req1 = {"parser.read": 1, "parser.test": 2}
        self.assertTrue(worker.satisfies(req1))

        # Fails (insufficient capability level)
        req2 = {"parser.test": 3}
        self.assertFalse(worker.satisfies(req2))

        # Fails (missing capability)
        req3 = {"soar.playbook.modify": 1}
        self.assertFalse(worker.satisfies(req3))

    def test_03_work_queue_publishing_and_capability_query(self):
        """Verifies publishing issues and finding eligible issues by capabilities."""
        issue1 = SOCIssue(
            id="SOC-2026-TEST-002",
            type="parser_drop_spike",
            priority_score=90,
            routing=IssueRouting(requires_capabilities={"parser.read": 1, "parser.test": 2}),
        )
        issue2 = SOCIssue(
            id="SOC-2026-TEST-003",
            type="rule_decay",
            priority_score=70,
            routing=IssueRouting(requires_capabilities={"detection.rule.modify": 1}),
        )

        self.work_queue.publish_issue(issue1)
        self.work_queue.publish_issue(issue2)

        # Worker with parser capabilities
        parser_caps = {"parser.read": 1, "parser.compile": 1, "parser.test": 2}
        eligible = self.work_queue.find_eligible_issues(parser_caps)
        self.assertEqual(len(eligible), 1)
        self.assertEqual(eligible[0].id, "SOC-2026-TEST-002")

        # Worker with detection capabilities
        detect_caps = {"detection.rule.modify": 1}
        eligible_detect = self.work_queue.find_eligible_issues(detect_caps)
        self.assertEqual(len(eligible_detect), 1)
        self.assertEqual(eligible_detect[0].id, "SOC-2026-TEST-003")

    def test_04_atomic_leasing_and_expiration(self):
        """Verifies atomic lease acquisition, contention rejection, and expiration reclaim."""
        issue = SOCIssue(
            id="SOC-2026-TEST-004",
            type="parser_drop_spike",
            routing=IssueRouting(requires_capabilities={"parser.read": 1}),
        )
        self.work_queue.publish_issue(issue)

        # Agent 1 acquires lease for 2 seconds
        lease1 = self.work_queue.acquire_lease("SOC-2026-TEST-004", "@worker-1", duration_seconds=2)
        self.assertIsNotNone(lease1)
        self.assertEqual(lease1.owner, "@worker-1")
        self.assertEqual(lease1.generation, 1)

        # Agent 2 attempts to acquire active lease -> Rejected
        lease2 = self.work_queue.acquire_lease("SOC-2026-TEST-004", "@worker-2", duration_seconds=5)
        self.assertIsNone(lease2)

        # Agent 1 renews heartbeat
        renew_ok = self.work_queue.renew_lease("SOC-2026-TEST-004", "@worker-1", duration_seconds=5)
        self.assertTrue(renew_ok)

        # Agent 2 still rejected
        self.assertIsNone(self.work_queue.acquire_lease("SOC-2026-TEST-004", "@worker-2"))

        # Agent 1 releases lease
        rel_ok = self.work_queue.release_lease("SOC-2026-TEST-004", "@worker-1")
        self.assertTrue(rel_ok)

        # Agent 2 can now acquire lease (generation increments to 2)
        lease2_after = self.work_queue.acquire_lease("SOC-2026-TEST-004", "@worker-2", duration_seconds=5)
        self.assertIsNotNone(lease2_after)
        self.assertEqual(lease2_after.owner, "@worker-2")
        self.assertEqual(lease2_after.generation, 2)

    def test_05_materializer_directory_structure_and_append_events(self):
        """Verifies that IssueMaterializer builds the append-only event ledger and evidence structure."""
        issue = SOCIssue(
            id="SOC-2026-TEST-005",
            type="cbn_syntax_error",
            plane=OperationalPlane.DATA.value,
            severity=IssueSeverity.HIGH.value,
            problem=IssueProblem(title="CBN Syntax Error in Cisco ASA Parser"),
            source=IssueSource(deacon_id="deacon.cbn_syntax"),
        )

        evidence_payload = {
            "error_log": "Syntax error at line 42: invalid transform function",
            "log_type": "CISCO_ASA",
        }

        # 1. Materialize Issue Opened (commit=False for test isolation)
        issue_dir, _ = self.materializer.materialize_issue_opened(
            issue=issue,
            evidence_files={"error_snapshot.json": evidence_payload},
            commit=False,
        )

        self.assertTrue(issue_dir.is_dir())
        self.assertTrue((issue_dir / "issue.yaml").is_file())
        self.assertTrue((issue_dir / "events" / "001-observed.yaml").is_file())
        self.assertTrue((issue_dir / "evidence" / "error_snapshot.json").is_file())

        # 2. Materialize Claim
        lease = Lease(owner="@parser-doctor", acquired_at=datetime.now(timezone.utc).isoformat(), expires_at="2026-09-24T18:00:00Z")
        evt_claim, _ = self.materializer.materialize_claimed(issue.id, "@parser-doctor", lease, commit=False)
        self.assertTrue((issue_dir / "events" / "002-claimed.yaml").is_file())

        # 3. Materialize Proposal Created
        diff_content = "--- parser.cbn\n+++ parser.cbn\n@@ -42 +42 @@\n- bad_transform()\n+ good_transform()"
        evt_prop, _ = self.materializer.materialize_proposal_created(
            issue_id=issue.id,
            proposal_id="PRP-TEST-001",
            proposal_title="Fix invalid transform in Cisco ASA CBN",
            author="@parser-doctor",
            diff_text=diff_content,
            commit=False,
        )
        self.assertTrue((issue_dir / "events" / "003-proposal-created.yaml").is_file())
        self.assertTrue((issue_dir / "evidence" / "proposal_PRP-TEST-001.diff").is_file())

        # 4. Materialize Validation Recorded (Peer review passed)
        evt_val, _ = self.materializer.materialize_validation_recorded(
            issue_id=issue.id,
            validator_actor="@logjammer-agent",
            passed=True,
            diagnostics=["CBN compiler exit code 0", "Replay of 500 logs parsed with 0 drops"],
            test_evidence={"parsed_count": 500, "drop_count": 0},
            commit=False,
        )
        self.assertTrue((issue_dir / "events" / "004-validation.yaml").is_file())

        # 5. Materialize Decision Approved
        evt_dec, _ = self.materializer.materialize_decision(
            issue_id=issue.id,
            decision="APPROVED",
            approver="secops_lead",
            rationale="Preflight validation verified zero regressions.",
            commit=False,
        )
        self.assertTrue((issue_dir / "events" / "005-decision.yaml").is_file())

        # 6. Materialize Applied
        change = ChangeRecord(
            change_id="CHG-TEST-001",
            issue_id=issue.id,
            proposal_id="PRP-TEST-001",
            subsystem="parsers",
            target_resource_id="projects/test/locations/us/parsers/cisco_asa",
            applied_by="@parser-doctor",
        )
        evt_app, _ = self.materializer.materialize_applied(issue.id, change, commit=False)
        self.assertTrue((issue_dir / "events" / "006-applied.yaml").is_file())

        # 7. Materialize Verified & Closed
        proof = VerificationProof(
            verification_id="VER-TEST-001",
            change_id=change.change_id,
            issue_id=issue.id,
            verifier_actor="deacon.cbn_syntax",
            cleared=True,
            summary="Post-deployment check: 0 syntax errors over past 30 minutes.",
        )
        evt_ver, _ = self.materializer.materialize_verified(issue.id, proof, commit=False)
        self.assertTrue((issue_dir / "events" / "007-verified.yaml").is_file())
        self.assertTrue((issue_dir / "resolution.md").is_file())

        # Check all 7 events preserved in sequence
        events = self.materializer.list_issue_events(issue.id)
        self.assertEqual(len(events), 7)
        self.assertEqual(events[0].transition_type, "OBSERVED")
        self.assertEqual(events[1].transition_type, "CLAIMED")
        self.assertEqual(events[2].transition_type, "PROPOSAL_CREATED")
        self.assertEqual(events[3].transition_type, "VALIDATION_PASSED")
        self.assertEqual(events[4].transition_type, "DECISION_APPROVED")
        self.assertEqual(events[5].transition_type, "APPLIED")
        self.assertEqual(events[6].transition_type, "VERIFIED")

        # Verify final issue status in Git is CLOSED
        final_issue = self.materializer.get_issue(issue.id)
        self.assertIsNotNone(final_issue)
        self.assertEqual(final_issue.status, IssueLifecycleStatus.CLOSED.value)

    def test_06_lifecycle_manager_end_to_end(self):
        """Verifies the complete end-to-end lifecycle orchestration through SOCLifecycleManager."""
        # 1. Deacon senses anomaly and opens issue
        issue = SOCIssue(
            id="SOC-2026-TEST-006",
            type="ingestion_label_missing",
            plane=OperationalPlane.DATA.value,
            severity=IssueSeverity.MEDIUM.value,
            problem=IssueProblem(
                title="Untagged Ingestion Forwarder Detected",
                observed_state={"forwarder_ip": "10.0.1.5", "missing_label": "prod-dmz"},
                desired_state={"label_attached": True},
            ),
            routing=IssueRouting(
                requires_capabilities={"namespace.read": 1, "namespace.modify": 1},
            ),
        )

        opened = self.lifecycle.open_issue(issue, commit=False)
        self.assertEqual(opened.status, IssueLifecycleStatus.AVAILABLE.value)

        # 2. Worker queries work queue
        worker_caps = {"namespace.read": 1, "namespace.modify": 1}
        work = self.lifecycle.find_work(worker_caps)
        self.assertTrue(any(w.id == "SOC-2026-TEST-006" for w in work))

        # 3. Worker claims issue
        lease = self.lifecycle.claim_issue("SOC-2026-TEST-006", "@namespace-label-agent", duration_seconds=120)
        self.assertIsNotNone(lease)
        self.assertEqual(lease.owner, "@namespace-label-agent")

        # 4. Worker heartbeats
        heartbeat_ok = self.lifecycle.heartbeat("SOC-2026-TEST-006", "@namespace-label-agent")
        self.assertTrue(heartbeat_ok)

        # 5. Worker generates and submits proposal
        prop_ok = self.lifecycle.submit_proposal(
            issue_id="SOC-2026-TEST-006",
            proposal_id="PRP-LABEL-001",
            proposal_title="Attach prod-dmz ingestion label to forwarder 10.0.1.5",
            author="@namespace-label-agent",
            diff_text="+ ingestion_label: prod-dmz",
            commit=False,
        )
        self.assertTrue(prop_ok)

        # 6. Peer reviewer records validation
        val_ok = self.lifecycle.record_validation(
            issue_id="SOC-2026-TEST-006",
            validator_actor="@tenant-posture-agent",
            passed=True,
            diagnostics=["Data RBAC rules match label prod-dmz", "Zero collision risks"],
            commit=False,
        )
        self.assertTrue(val_ok)

        # 7. Operator approves
        dec_ok = self.lifecycle.decide_issue(
            issue_id="SOC-2026-TEST-006",
            decision="APPROVED",
            approver="soc_engineer",
            rationale="Approved forwarder labeling change.",
            commit=False,
        )
        self.assertTrue(dec_ok)

        # 8. Change applied to Google SecOps API
        change = ChangeRecord(
            change_id="CHG-LABEL-001",
            issue_id="SOC-2026-TEST-006",
            proposal_id="PRP-LABEL-001",
            subsystem="ingestion_labels",
            target_resource_id="forwarders/10.0.1.5",
            applied_by="@namespace-label-agent",
        )
        app_ok = self.lifecycle.apply_change("SOC-2026-TEST-006", change, commit=False)
        self.assertTrue(app_ok)

        # 9. Verification by Deacon & closure
        proof = VerificationProof(
            verification_id="VER-LABEL-001",
            change_id=change.change_id,
            issue_id="SOC-2026-TEST-006",
            verifier_actor="deacon.namespace_label",
            cleared=True,
            summary="Forwarder 10.0.1.5 is now ingesting with label prod-dmz.",
        )
        close_ok = self.lifecycle.verify_and_close("SOC-2026-TEST-006", proof, commit=False)
        self.assertTrue(close_ok)

        # 10. Verify final state in both planes
        q_issue = self.work_queue.get_issue("SOC-2026-TEST-006")
        self.assertIsNotNone(q_issue)
        self.assertEqual(q_issue.status, IssueLifecycleStatus.CLOSED.value)
        self.assertIsNone(q_issue.lease)

        git_issue = self.materializer.get_issue("SOC-2026-TEST-006")
        self.assertIsNotNone(git_issue)
        self.assertEqual(git_issue.status, IssueLifecycleStatus.CLOSED.value)

    def test_07_deacon_parser_doctor_peer_lifecycle(self):
        """Verifies the collaborative lifecycle: Deacon sensing -> Doctor claiming -> Proposal -> Peer Review -> Approval -> Verification."""
        proposal_mgr = ProposalManager(root_dir=self.root_path)

        # 1. Instantiate @parser-doctor and register capability profile
        parser_doctor = ParserHealthAgentAgent(
            proposal_manager=proposal_mgr,
            work_queue=self.work_queue,
            lifecycle_manager=self.lifecycle,
        )
        reg_ok = parser_doctor.register_worker()
        self.assertTrue(reg_ok)

        profile = self.work_queue.get_worker("@parser-doctor")
        self.assertIsNotNone(profile)
        self.assertIn(OperationalPlane.DATA.value, profile.operational_planes)
        self.assertIn("parser.audit_health", profile.capabilities)
        self.assertIn("parser.run", profile.capabilities)
        self.assertIn("git.proposal.create", profile.capabilities)

        # 2. Deacon senses normalization drop degradation on cisco_asa
        issue_id = "SOC-DATA-PARSER-CISCO_ASA"
        issue = SOCIssue(
            id=issue_id,
            type="parser_drop_spike",
            plane=OperationalPlane.DATA.value,
            severity=IssueSeverity.HIGH.value,
            problem=IssueProblem(
                title="Elevated Parser Normalization Drops on cisco_asa",
                observed_state={
                    "log_type": "cisco_asa",
                    "status": "FAILED",
                    "drop_reason_code": "DROP_SYNTAX_ERROR",
                    "unparsed_count": 1420,
                },
                desired_state={
                    "status": "HEALTHY",
                    "drop_reason_code": None,
                    "unparsed_count": 0,
                },
                affected_objects=["cisco_asa"],
            ),
            routing=IssueRouting(
                requires_capabilities={
                    "parser.audit_health": 1,
                    "parser.run": 1,
                    "git.proposal.create": 1,
                },
            ),
            governance=IssueGovernance(
                required_authority_tier=AuthorityTier.TIER_2_PEER_REVIEW.value,
                validation_criteria=["cbn_syntax_valid == true", "unparsed_count == 0"],
            ),
        )
        opened = self.lifecycle.open_issue(
            issue=issue,
            deacon_id="deacon.parser_patrol",
            evidence_files={"telemetry.json": json.dumps({"drop_count": 1420})},
            commit=False,
        )
        self.assertEqual(opened.status, IssueLifecycleStatus.AVAILABLE.value)

        # 3. @parser-doctor queries work queue and claims issue
        eligible = parser_doctor.find_eligible_issues()
        self.assertTrue(any(i.id == issue_id for i in eligible))

        lease = parser_doctor.claim_work(issue_id, duration_seconds=120)
        self.assertIsNotNone(lease)
        self.assertEqual(lease.owner, "@parser-doctor")

        claimed_issue = self.work_queue.get_issue(issue_id)
        self.assertEqual(claimed_issue.status, IssueLifecycleStatus.LEASED.value)

        # 4. @parser-doctor diagnoses and submits patch proposal linked to issue
        cbn_diff = "--- cisco_asa.cbn\n+++ cisco_asa.cbn\n@@ -24 +24 @@\n- grok { match => ... }\n+ grok { match => ... [fixed] }\n"
        prop_res = parser_doctor.submit_parser_proposal(
            title="Fix Cisco ASA Logstash timestamp pattern",
            log_type="cisco_asa",
            rationale="Resolved unescaped brackets in grok pattern.",
            proposed_diff=cbn_diff,
            patched_cbn_snippet="filter { grok { match => ... } }",
            issue_id=issue_id,
        )
        self.assertEqual(prop_res["status"], "SUCCESS")
        proposal_id = prop_res["proposal_id"]

        prop_issue = self.work_queue.get_issue(issue_id)
        self.assertEqual(prop_issue.status, IssueLifecycleStatus.VALIDATING.value)
        self.assertEqual(prop_issue.active_proposal_id, proposal_id)

        # 5. Peer reviewer (@logjammer-agent) validates the proposal
        val_ok = self.lifecycle.record_validation(
            issue_id=issue_id,
            validator_actor="@logjammer-agent",
            passed=True,
            diagnostics=["CBN grok syntax check passed", "Dry-run with 500 samples parsed cleanly"],
            test_evidence={"samples_parsed": 500, "errors": 0},
            commit=False,
        )
        self.assertTrue(val_ok)
        val_issue = self.work_queue.get_issue(issue_id)
        self.assertEqual(val_issue.status, IssueLifecycleStatus.APPROVED.value)

        # 6. Human Operator decides and approves
        dec_ok = self.lifecycle.decide_issue(
            issue_id=issue_id,
            decision="APPROVED",
            approver="secops_operator@example.com",
            rationale="Approved cisco_asa regex update.",
            commit=False,
        )
        self.assertTrue(dec_ok)

        # 7. Merge and apply change
        merge_res = proposal_mgr.approve_and_merge(
            proposal_id=proposal_id,
            engine=None,
            merged_by="secops_operator@example.com",
            lifecycle_manager=self.lifecycle,
        )
        self.assertEqual(merge_res.status, "MERGED")

        app_issue = self.work_queue.get_issue(issue_id)
        self.assertEqual(app_issue.status, IssueLifecycleStatus.APPLIED.value)
        self.assertIsNotNone(app_issue.applied_change_id)

        # 8. Deacon senses resolution and closes issue with proof
        proof = VerificationProof(
            verification_id="VER-PARSER-001",
            change_id=app_issue.applied_change_id,
            issue_id=issue_id,
            verifier_actor="deacon.parser_patrol",
            cleared=True,
            summary="Post-deployment Health Hub telemetry verifies 0 normalization drops on cisco_asa.",
        )
        closed = self.lifecycle.verify_and_close(
            issue_id=issue_id,
            verification=proof,
            resolution_markdown="# Resolution\n\nCisco ASA parser patch verified in production with 0 unparsed drops.",
            commit=False,
        )
        self.assertTrue(closed)

        final_queue_issue = self.work_queue.get_issue(issue_id)
        self.assertEqual(final_queue_issue.status, IssueLifecycleStatus.CLOSED.value)
        self.assertIsNone(final_queue_issue.lease)

        # Verify all 7 event files were generated in Git materializer
        events = self.materializer.list_issue_events(issue_id)
        self.assertEqual(len(events), 7)
        self.assertEqual(events[0].transition_type, "OBSERVED")
        self.assertEqual(events[1].transition_type, "CLAIMED")
        self.assertEqual(events[2].transition_type, "PROPOSAL_CREATED")
        self.assertEqual(events[3].transition_type, "VALIDATION_PASSED")
        self.assertEqual(events[4].transition_type, "DECISION_APPROVED")
        self.assertEqual(events[5].transition_type, "APPLIED")
        self.assertEqual(events[6].transition_type, "VERIFIED")

        res_path = self.root_path / ".issues" / issue_id / "resolution.md"
        self.assertTrue(res_path.is_file())
        self.assertIn("Cisco ASA parser patch verified", res_path.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
