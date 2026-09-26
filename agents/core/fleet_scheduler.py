"""Fleet Scheduler Subsystem for Autonomous Google SecOps ADK 2 Agents.

Provides per-agent scheduling, cron/interval evaluation, background execution,
and integration with Evidence Fabric and Collaborative Chat Streams.
"""

import asyncio
from datetime import datetime, timedelta, timezone
import json
import logging
import re
from typing import Any, Callable, Dict, List, Optional

from agents.core.base_adk_agent import BaseSecOpsAdkAgent
from agents.core.communication_router import CommunicationRouter, get_communication_router
from agents.core.evidence_store import EvidenceFabricStore, normalize_doc_id
from agents.core.issue_worker import IssueWorker, autonomous_workers_enabled
from agents.core.knowledge_store import BaseKnowledgeStore, get_knowledge_store
from agents.core.lifecycle import SOCLifecycleManager
from agents.core.work_queue import BaseWorkQueue
from engine.domain import (
    AuthorityTier,
    CommunicationClass,
    CommunicationPolicy,
    IssueGovernance,
    IssueProblem,
    IssueRouting,
    IssueSeverity,
    Observation,
    ObserverRef,
    OperationalPlane,
    SOCIssue,
    SubjectRef,
    VerificationProof,
)


logger = logging.getLogger(__name__)


DEFAULT_AGENT_SCHEDULES: Dict[str, Dict[str, Any]] = {
    "@feed-agent": {
        "agent_handle": "@feed-agent",
        "enabled": True,
        "interval_hours": 4,
        "lookback_days": 7,
        "stream": "ingestion",
        "topic": "feed-health",
        "action": "audit_feeds",
        "description": "4-hourly Chronicle ingestion transport latency, drop rates, and quota rejection patrol",
    },
    "@parser-doctor": {
        "agent_handle": "@parser-doctor",
        "enabled": True,
        "interval_hours": 6,
        "lookback_days": 7,
        "stream": "ingestion",
        "topic": "parser-drops",
        "action": "audit_parsers",
        "description": "6-hourly Logstash CBN parser normalization drop codes, extension conflicts, and version drift patrol",
    },
    "@detection-tuning-agent": {
        "agent_handle": "@detection-tuning-agent",
        "enabled": True,
        "interval_hours": 12,
        "lookback_days": 14,
        "stream": "detections",
        "topic": "tuning-review",
        "action": "find_noisy_rules",
        "description": "12-hourly high-firing detection rules and alert fatigue suppressor patrol",
    },
    "@detection-decay-agent": {
        "agent_handle": "@detection-decay-agent",
        "enabled": True,
        "interval_hours": 24,
        "lookback_days": 90,
        "stream": "detections",
        "topic": "decay-review",
        "action": "audit_rules",
        "description": "Daily 24h unified detection repository health, decay, conflict, and embedding patrol",
    },
    "@identity-governor": {
        "agent_handle": "@identity-governor",
        "enabled": True,
        "interval_hours": 24,
        "stream": "identity",
        "topic": "iam-audit",
        "action": "run_identity_drift_audit",
        "description": "Daily GCP IAM privilege and custom role drift audit",
    },
    "@tenant-posture-agent": {
        "agent_handle": "@tenant-posture-agent",
        "enabled": True,
        "interval_hours": 24,
        "stream": "governance",
        "topic": "tenant-posture",
        "action": "audit_tenant_posture",
        "description": "Daily Chronicle SIEM, SOAR, RBAC, and SOC topography configuration baseline and drift audit",
    },
    "@playbook-decay-agent": {
        "agent_handle": "@playbook-decay-agent",
        "enabled": True,
        "interval_hours": 12,
        "lookback_days": 30,
        "stream": "soar",
        "topic": "playbook-health",
        "action": "audit_playbook_decay",
        "description": "12-hourly SOAR playbook resilience scoring, execution failure rates, and topology decay patrol",
    },
    "@timestamp-integrity-agent": {
        "agent_handle": "@timestamp-integrity-agent",
        "enabled": True,
        "interval_hours": 12,
        "days": 7,
        "stream": "ingestion",
        "topic": "timestamp-integrity",
        "action": "audit_timestamp_integrity",
        "description": "12-hourly ingestion timestamp delta auditing, clock drift tracking, and telemetry hygiene patrol",
    },
    "@cloud-status-agent": {
        "agent_handle": "@cloud-status-agent",
        "enabled": True,
        "interval_hours": 0.5,
        "lookback_days": 14,
        "stream": "infrastructure",
        "topic": "service-status",
        "action": "audit_cloud_service_status",
        "description": "30-minute Google Cloud SecOps service status, upstream disruption, and outage monitor patrol",
    },
}


class FleetScheduler:
    """Evaluates agent schedules, triggers periodic workflows, and notifies chat streams."""

    def __init__(
        self,
        fleet: Dict[str, BaseSecOpsAdkAgent],
        evidence_store: Optional[EvidenceFabricStore] = None,
        chat_store: Optional[Any] = None,
        poll_interval_seconds: int = 30,
        lifecycle_manager: Optional[SOCLifecycleManager] = None,
        work_queue: Optional[BaseWorkQueue] = None,
        communication_router: Optional[CommunicationRouter] = None,
        knowledge_store: Optional[BaseKnowledgeStore] = None,
        issue_worker: Optional[IssueWorker] = None,
    ):
        self.fleet = fleet
        self.evidence_store = evidence_store
        self.chat_store = chat_store
        self.poll_interval_seconds = poll_interval_seconds
        self.lifecycle_manager = lifecycle_manager
        self.work_queue = work_queue
        self.communication_router = communication_router or get_communication_router(work_queue=self.work_queue, chat_store=self.chat_store)
        self.knowledge_store = knowledge_store or get_knowledge_store()
        self._running = False
        self._task: Optional[asyncio.Task] = None
        self._schedules: Dict[str, Dict[str, Any]] = {}
        self._last_patrol_run_at: Optional[str] = None
        self._last_heartbeat_at: Optional[str] = datetime.now(timezone.utc).isoformat()
        self._total_patrols_run: int = 0
        self._patrol_history: List[Dict[str, Any]] = []
        # Autonomous issue pickup is opt-in (SECOPS_AUTONOMOUS_WORKERS=1) unless a worker is injected.
        queue = self.work_queue or getattr(self.lifecycle_manager, "work_queue", None)
        if issue_worker is None and queue is not None and autonomous_workers_enabled():
            issue_worker = IssueWorker(fleet=self.fleet, work_queue=queue, chat_store=self.chat_store)
        self.issue_worker = issue_worker
        self._load_all_schedules()


    def _load_all_schedules(self) -> None:
        """Loads agent schedules from Evidence Fabric or applies default settings."""
        for handle, default_cfg in DEFAULT_AGENT_SCHEDULES.items():
            loaded_cfg = {}
            if self.evidence_store:
                try:
                    loaded_cfg = self.evidence_store.get_agent_config(handle) or {}
                except Exception as e:
                    logger.warning("Could not load config for %s: %s", handle, e)

            merged = dict(default_cfg)
            merged.update(loaded_cfg)

            # Ensure timing fields are present
            if "next_run_at" not in merged:
                # Schedule first run within interval_hours
                hours = merged.get("interval_hours", 24)
                merged["next_run_at"] = (datetime.now(timezone.utc) + timedelta(hours=hours)).isoformat()

            self._schedules[handle] = merged

    def has_schedule(self, agent_handle: str) -> bool:
        """True if the agent has a configured (default or persisted) schedule."""
        return agent_handle in self._schedules

    def get_schedule(self, agent_handle: str) -> Dict[str, Any]:
        """Returns the current schedule for an agent handle.

        Read-only: unscheduled agents get a disabled placeholder that is *not*
        stored, so looking an agent up never adds it to ``list_schedules()``.
        Use ``update_schedule()`` to create a schedule.
        """
        if agent_handle not in self._schedules:
            return {
                "agent_handle": agent_handle,
                "enabled": False,
                "interval_hours": 24,
                "stream": "general",
                "topic": "general",
            }
        return dict(self._schedules[agent_handle])

    def list_schedules(self) -> List[Dict[str, Any]]:
        """Returns all configured agent schedules."""
        return list(self._schedules.values())

    def update_schedule(self, agent_handle: str, updates: Dict[str, Any]) -> Dict[str, Any]:
        """Updates and persists the schedule configuration for an agent."""
        curr = self.get_schedule(agent_handle)
        curr.update(updates)
        curr["agent_handle"] = agent_handle
        curr["updated_at"] = datetime.now(timezone.utc).isoformat()

        # Recalculate next run if interval changed or enabled toggled
        if updates.get("enabled") and not curr.get("next_run_at"):
            hours = curr.get("interval_hours", 24)
            curr["next_run_at"] = (datetime.now(timezone.utc) + timedelta(hours=hours)).isoformat()

        self._schedules[agent_handle] = curr

        if self.evidence_store:
            try:
                self.evidence_store.save_agent_config(agent_handle, curr)
            except Exception as e:
                logger.error("Failed to persist schedule for %s to Evidence Fabric: %s", agent_handle, e)

        return curr

    async def trigger_run_now(self, agent_handle: str) -> Dict[str, Any]:
        """Forces an immediate on-demand execution of an agent's scheduled task."""
        # Run against the stored dict (not a copy) so last_run_at / last_status /
        # next_run_at are reflected in list_schedules() and the Audits view.
        sched = self._schedules.get(agent_handle) or self.get_schedule(agent_handle)
        return await self._execute_scheduled_task(sched, forced=True)

    def get_deacon_status(self) -> Dict[str, Any]:
        """Returns live Deacon heartbeat, health metrics, and active patrol cycles."""
        now = datetime.now(timezone.utc)
        enabled_count = sum(1 for s in self._schedules.values() if s.get("enabled", False))

        # Calculate heartbeat freshness
        beat_ts = self._last_heartbeat_at or self._last_patrol_run_at
        heartbeat_str = "<1m ago"
        if beat_ts:
            try:
                last_dt = datetime.fromisoformat(beat_ts)
                if last_dt.tzinfo is None:
                    last_dt = last_dt.replace(tzinfo=timezone.utc)
                diff_sec = max(0, int((now - last_dt).total_seconds()))
                if diff_sec < 60:
                    heartbeat_str = f"Active ({diff_sec}s ago)"
                elif diff_sec < 3600:
                    heartbeat_str = f"Active ({diff_sec // 60}m ago)"
                else:
                    heartbeat_str = f"Active ({diff_sec // 3600}h ago)"
            except Exception:
                heartbeat_str = "Active (<1m)"
        else:
            heartbeat_str = "Active (running)" if self._running else "Standby (Ready)"

        return {
            "status": "healthy" if self._running else "idle",
            "heartbeat_fresh": self._running or bool(self._last_patrol_run_at),
            "deacon_heartbeat": heartbeat_str,
            "last_heartbeat_at": (self._last_heartbeat_at or self._last_patrol_run_at or now.isoformat()),
            "last_patrol_run_at": self._last_patrol_run_at,
            "active_patrols": enabled_count,
            "total_patrols_run": self._total_patrols_run,
            "poll_interval_seconds": self.poll_interval_seconds,
            "recent_patrols": self._patrol_history[-10:],
            "autonomous_workers": self.get_worker_status(),
        }

    async def trigger_patrol_all(self) -> Dict[str, Any]:
        """Triggers all enabled patrols sequentially and returns execution summary."""
        results = {}
        for handle, sched in list(self._schedules.items()):
            if sched.get("enabled", False):
                res = await self._execute_scheduled_task(sched, forced=True)
                results[handle] = res
        return {
            "status": "SUCCESS",
            "executed_count": len(results),
            "results": results,
            "deacon_status": self.get_deacon_status(),
        }

    def _auto_create_patrol_beads(
        self,
        handle: str,
        result: Dict[str, Any],
        sched: Dict[str, Any],
        start_time: str,
    ) -> List[str]:
        """Autonomously creates atomic tasks (beads) in Evidence Fabric upon anomaly detection."""
        if not self.evidence_store:
            return []

        created_bead_ids: List[str] = []
        action = sched.get("action")

        try:
            # 1. Feed Health Anomalies
            if handle == "@feed-agent" or action == "audit_feeds":
                findings = result.get("findings", [])
                for f in findings:
                    status = str(f.get("status", "")).upper()
                    p95 = f.get("latency_p95") or 0.0
                    if status in ("FAILED", "IRREGULAR") or p95 > 4.0:
                        feed_id = str(f.get("feed_id", "feed"))
                        feed_name = f.get("feed_name") or feed_id
                        log_type = f.get("log_type", "UNKNOWN")
                        clean_feed = normalize_doc_id(feed_id[:16])
                        todo_id = f"todo_feed_{clean_feed}_active"
                        task = {
                            "todo_id": todo_id,
                            "title": f"Remediate Ingestion Transport Failure on Feed: {feed_name} ({log_type})",
                            "target_agent": "@feed-agent",
                            "target_resource_id": feed_id,
                            "action_type": "remediate_feed",
                            "stream": "ingestion",
                            "topic": "feed-health",
                            "priority": "HIGH" if status == "FAILED" else "MEDIUM",
                            "status": "PENDING",
                            "action_prompt": f"@feed-agent get feed details {feed_id}",
                            "rationale": f"Deacon feed patrol observed status={status}, latency={p95}h, anomaly={f.get('anomaly_description')}",
                            "created_at": start_time,
                        }
                        self.evidence_store.upsert_todo(todo_id, task)
                        created_bead_ids.append(todo_id)

            # 2. Parser Normalization Drops & Errors
            elif handle == "@parser-doctor" or action == "audit_parsers":
                findings = result.get("findings", [])
                for f in findings:
                    status = str(f.get("status", "")).upper()
                    drop_code = f.get("drop_reason_code")
                    unparsed = f.get("unparsed_log_count") or f.get("unparsed_count") or 0
                    log_type = str(f.get("log_type", "UNKNOWN"))
                    clean_log = normalize_doc_id(log_type.lower())
                    issue_id = f"SOC-DATA-PARSER-{clean_log.upper()}"

                    if status == "FAILED" or drop_code or unparsed > 0:
                        todo_id = f"todo_parser_{clean_log}_active"
                        task = {
                            "todo_id": todo_id,
                            "title": f"Diagnose Parser Normalization Drops on {log_type}",
                            "target_agent": "@parser-doctor",
                            "target_resource_id": log_type,
                            "action_type": "diagnose_parser",
                            "stream": "ingestion",
                            "topic": "parser-drops",
                            "priority": "HIGH" if status == "FAILED" else "MEDIUM",
                            "status": "PENDING",
                            "action_prompt": f"@parser-doctor diagnose unparsed logs for {log_type}",
                            "rationale": f"Deacon parser patrol observed status={status}, drop_reason={drop_code}, unparsed={unparsed}",
                            "created_at": start_time,
                        }
                        if self.evidence_store:
                            self.evidence_store.upsert_todo(todo_id, task)
                        created_bead_ids.append(todo_id)

                        # Emit evidenced SOCIssue to Work Queue & Git Materializer
                        if self.lifecycle_manager:
                            try:
                                issue = SOCIssue(
                                    id=issue_id,
                                    type="parser_drop_spike",
                                    plane=OperationalPlane.DATA.value,
                                    severity=IssueSeverity.HIGH.value if status == "FAILED" else IssueSeverity.MEDIUM.value,
                                    problem=IssueProblem(
                                        title=f"Elevated Parser Normalization Drops on {log_type}",
                                        observed_state={
                                            "log_type": log_type,
                                            "status": status,
                                            "drop_reason_code": drop_code,
                                            "unparsed_count": unparsed,
                                        },
                                        desired_state={
                                            "status": "HEALTHY",
                                            "drop_reason_code": None,
                                            "unparsed_count": 0,
                                        },
                                        affected_objects=[log_type],
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
                                        validation_criteria=[
                                            "cbn_syntax_valid == true",
                                            "unparsed_count == 0",
                                        ],
                                    ),
                                )
                                self.lifecycle_manager.open_issue(
                                    issue=issue,
                                    deacon_id="deacon.parser_patrol",
                                    evidence_files={"sample_findings.json": json.dumps(f, indent=2).encode("utf-8")},
                                    commit=True,
                                )
                            except Exception as issue_err:
                                logger.warning("Failed opening SOCIssue for parser %s: %s", log_type, issue_err)

                    elif status == "HEALTHY" and not drop_code and unparsed == 0:
                        # Auto-verify and close if an open issue exists and drops are resolved!
                        if self.lifecycle_manager:
                            try:
                                existing = self.lifecycle_manager.work_queue.get_issue(issue_id)
                                if existing and existing.status in ("APPLIED", "VALIDATING"):
                                    verification = VerificationProof(
                                        verifier_actor="deacon.parser_patrol",
                                        telemetry_proof_query=f"parser.audit_health(log_type='{log_type}')",
                                        metric_before=str(existing.problem.observed_state),
                                        metric_after="status=HEALTHY, drop_reason=None, unparsed=0",
                                        verified_at=datetime.now(timezone.utc).isoformat(),
                                        success=True,
                                    )
                                    self.lifecycle_manager.verify_and_close(
                                        issue_id=issue_id,
                                        verification=verification,
                                        resolution_markdown=f"Deacon parser patrol verified 0 drops and healthy normalization on {log_type}.",
                                        commit=True,
                                    )
                            except Exception as close_err:
                                logger.warning("Failed verifying/closing SOCIssue %s: %s", issue_id, close_err)

            # 3. Alert Fatigue & Noisy Detection Rules
            elif handle == "@detection-tuning-agent" or action == "find_noisy_rules":
                rules = result.get("rules", [])
                if rules:
                    top_rule = rules[0]
                    rule_id = str(top_rule.get("rule_id", "rule"))
                    rule_name = top_rule.get("rule_name") or rule_id
                    clean_rule = normalize_doc_id(rule_id[:16])
                    todo_id = f"todo_tuning_{clean_rule}_active"
                    task = {
                        "todo_id": todo_id,
                        "title": f"Synthesize Tuning Exclusion Filter for {rule_name}",
                        "target_agent": "@detection-tuning-agent",
                        "target_resource_id": rule_id,
                        "action_type": "tune_noise",
                        "stream": "detections",
                        "topic": "tuning-review",
                        "priority": "MEDIUM",
                        "status": "PENDING",
                        "action_prompt": f"@detection-tuning-agent tune rule {rule_id}",
                        "rationale": f"Deacon tuning patrol identified {top_rule.get('detection_count')} detections ({top_rule.get('ratio_of_total', 0)*100:.1f}% of volume).",
                        "created_at": start_time,
                    }
                    self.evidence_store.upsert_todo(todo_id, task)
                    created_bead_ids.append(todo_id)

            # 4. Detection Rule Decay & Unified Repository Audit
            elif handle == "@detection-decay-agent" or action in ("run_decay_synchronization", "audit_rules"):
                broken_count = result.get("failing_count", result.get("broken_count", 0))
                todo_id = "todo_decay_broken_active"
                if broken_count > 0:
                    task = {
                        "todo_id": todo_id,
                        "title": f"Remediate {broken_count} Broken Detection Rules with Invalid Syntax",
                        "target_agent": "@detection-decay-agent",
                        "target_resource_id": "CHRONICLE_RULES",
                        "action_type": "audit_decay",
                        "stream": "detections",
                        "topic": "decay-review",
                        "priority": "HIGH",
                        "status": "PENDING",
                        "action_prompt": "@detection-decay-agent review broken rules",
                        "rationale": f"Detection repository patrol identified {broken_count} broken rules requiring YARA-L remediation.",
                        "created_at": start_time,
                    }
                    self.evidence_store.upsert_todo(todo_id, task)
                    created_bead_ids.append(todo_id)
                else:
                    self.evidence_store.resolve_todo(
                        todo_id,
                        reason="Detection repository patrol observed 0 broken rules.",
                    )

                shadowed_count = result.get("shadowed_by_curated_count", 0)
                shadowed_todo_id = "todo_shadowed_curated_rules"
                if shadowed_count > 0:
                    task = {
                        "todo_id": shadowed_todo_id,
                        "title": f"Consolidate {shadowed_count} Customer Rules Shadowing Google Curated Rules",
                        "target_agent": "@rule-conflict-agent",
                        "target_resource_id": "CHRONICLE_RULES",
                        "action_type": "consolidate_shadowed_rules",
                        "stream": "detections",
                        "topic": "rule-conflicts",
                        "priority": "MEDIUM",
                        "status": "PENDING",
                        "action_prompt": "@rule-conflict-agent consolidate shadowed curated rules",
                        "rationale": f"Detection repository audit discovered {shadowed_count} customer rules semantically duplicate Google Curated rules.",
                        "created_at": start_time,
                    }
                    self.evidence_store.upsert_todo(shadowed_todo_id, task)
                    created_bead_ids.append(shadowed_todo_id)

            # 5. IAM Privilege Drift
            elif handle == "@identity-governor" or action == "run_identity_drift_audit":
                drift = result.get("drift", {})
                todo_id = "todo_iam_drift_active"
                if drift.get("has_drift"):
                    task = {
                        "todo_id": todo_id,
                        "title": "Remediate GCP IAM Privilege Drift Flagged by Governor",
                        "target_agent": "@identity-governor",
                        "target_resource_id": str(result.get("project_id", "GCP_PROJECT")),
                        "action_type": "iam_remediation",
                        "stream": "identity",
                        "topic": "iam-audit",
                        "priority": "HIGH",
                        "status": "PENDING",
                        "action_prompt": "@identity-governor reconcile IAM drift",
                        "rationale": f"Deacon identity patrol identified IAM privilege drift: {drift.get('summary')}",
                        "created_at": start_time,
                    }
                    self.evidence_store.upsert_todo(todo_id, task)
                    created_bead_ids.append(todo_id)
                else:
                    self.evidence_store.resolve_todo(
                        todo_id,
                        reason="Deacon identity patrol confirmed 0 IAM privilege drift.",
                    )

            # 6. Tenant Posture & Configuration Drift
            elif handle == "@tenant-posture-agent" or action == "audit_tenant_posture":
                todo_id = "todo_posture_drift_active"
                if result.get("has_drift"):
                    subsystems = result.get("subsystems_drifted", [])
                    subsystems_str = ", ".join(subsystems) if subsystems else "subsystems"
                    task = {
                        "todo_id": todo_id,
                        "title": f"Remediate Tenant Configuration Drift in {subsystems_str}",
                        "target_agent": "@tenant-posture-agent",
                        "target_resource_id": str(result.get("tenant_id", "default")),
                        "action_type": "posture_remediation",
                        "stream": "governance",
                        "topic": "tenant-posture",
                        "priority": "HIGH" if result.get("critical_changes_count", 0) > 0 else "MEDIUM",
                        "status": "PENDING",
                        "action_prompt": "@tenant-posture-agent reconcile configuration drift",
                        "rationale": f"Deacon posture patrol identified configuration drift: {result.get('drift_summary') or 'Configuration drift detected against baseline'}",
                        "created_at": start_time,
                    }
                    self.evidence_store.upsert_todo(todo_id, task)
                    created_bead_ids.append(todo_id)
                else:
                    self.evidence_store.resolve_todo(
                        todo_id,
                        reason="Deacon posture patrol confirmed configuration matches baseline.",
                    )

            # 7. Playbook Decay & Automation Resilience
            elif handle == "@playbook-decay-agent" or action == "audit_playbook_decay":
                degraded_count = result.get("summary", {}).get("degraded_playbooks_count", 0)
                todo_id = "todo_playbook_decay_active"
                if degraded_count > 0:
                    task = {
                        "todo_id": todo_id,
                        "title": f"Triage {degraded_count} Degraded SOAR Playbooks",
                        "target_agent": "@playbook-decay-agent",
                        "target_resource_id": "catalog",
                        "action_type": "playbook_remediation",
                        "stream": "soar",
                        "topic": "playbook-health",
                        "priority": "HIGH",
                        "status": "PENDING",
                        "action_prompt": "@playbook-decay-agent audit degraded playbooks",
                        "rationale": f"Deacon playbook patrol identified {degraded_count} degraded playbooks with resilience score < 70 or failure rate > 20%",
                        "created_at": start_time,
                    }
                    self.evidence_store.upsert_todo(todo_id, task)
                    created_bead_ids.append(todo_id)
                else:
                    self.evidence_store.resolve_todo(
                        todo_id,
                        reason="Deacon playbook patrol confirmed 0 degraded playbooks.",
                    )

            # 8. Telemetry Timestamp Integrity & Clock Skew
            elif handle == "@timestamp-integrity-agent" or action == "audit_timestamp_integrity":
                skewed_events = result.get("summary", {}).get("total_skewed_events", 0)
                new_anomalies = result.get("summary", {}).get("new_anomalies_count", 0)
                todo_id = "todo_timestamp_integrity_active"
                if skewed_events > 0 or new_anomalies > 0:
                    task = {
                        "todo_id": todo_id,
                        "title": f"Investigate {skewed_events:,} Future Logs & {new_anomalies} Telemetry Anomalies",
                        "target_agent": "@timestamp-integrity-agent",
                        "target_resource_id": "telemetry",
                        "action_type": "telemetry_remediation",
                        "stream": "ingestion",
                        "topic": "timestamp-integrity",
                        "priority": "HIGH" if skewed_events > 0 else "MEDIUM",
                        "status": "PENDING",
                        "action_prompt": "@timestamp-integrity-agent audit",
                        "rationale": f"Deacon timestamp patrol identified {skewed_events:,} clock-skewed events (Δt < 0) and {new_anomalies} new telemetry delay anomalies.",
                        "created_at": start_time,
                    }
                    self.evidence_store.upsert_todo(todo_id, task)
                    created_bead_ids.append(todo_id)
                else:
                    self.evidence_store.resolve_todo(
                        todo_id,
                        reason="Deacon timestamp patrol observed 0 clock-skewed events and 0 latency anomalies.",
                    )

            # 9. Google Cloud Status & Upstream Service Incidents
            elif handle == "@cloud-status-agent" or action == "audit_cloud_service_status":
                active_incidents = result.get("active_incidents", [])
                overall_health = result.get("overall_health", "HEALTHY")
                todo_id = "todo_cloud_status_active"
                if active_incidents:
                    severities = [i.get("severity", "medium") for i in active_incidents]
                    is_critical = "high" in severities or overall_health == "OUTAGE"
                    desc_snippets = "; ".join(i.get("external_desc", "")[:60] for i in active_incidents[:2])
                    task = {
                        "todo_id": todo_id,
                        "title": f"Track {len(active_incidents)} Upstream Google Cloud Disruption(s) ({overall_health})",
                        "target_agent": "@cloud-status-agent",
                        "target_resource_id": "status.cloud.google.com",
                        "action_type": "status_disruption_tracking",
                        "stream": "infrastructure",
                        "topic": "service-status",
                        "priority": "CRITICAL" if is_critical else "HIGH",
                        "status": "PENDING",
                        "action_prompt": "@cloud-status-agent audit",
                        "rationale": f"Deacon status patrol identified {len(active_incidents)} active cloud incident(s): {desc_snippets}",
                        "created_at": start_time,
                    }
                    self.evidence_store.upsert_todo(todo_id, task)
                    created_bead_ids.append(todo_id)

                    # Also open / update Gas Town SOCIssue if lifecycle_manager is available
                    if self.lifecycle_manager and hasattr(self.lifecycle_manager, "open_issue"):
                        try:
                            sev = IssueSeverity.CRITICAL.value if is_critical else IssueSeverity.HIGH.value
                            cloud_issue = SOCIssue(
                                id="issue_upstream_cloud_status",
                                type="upstream_cloud_disruption",
                                plane=OperationalPlane.DATA.value,
                                severity=sev,
                                problem=IssueProblem(
                                    title=f"Upstream Google Cloud Disruption: {active_incidents[0].get('external_desc', 'Service Incident')}",
                                    observed_state={
                                        "active_incident_count": len(active_incidents),
                                        "incident_descriptions": desc_snippets,
                                        "public_url": active_incidents[0].get("public_url"),
                                    },
                                    desired_state={
                                        "active_incident_count": 0,
                                        "status": "HEALTHY",
                                    },
                                    affected_objects=[inc.get("service_name", "gcp") for inc in active_incidents],
                                ),
                                routing=IssueRouting(
                                    requires_capabilities={
                                        "cloud.audit_status": 1,
                                    },
                                ),
                                governance=IssueGovernance(
                                    required_authority_tier=AuthorityTier.TIER_2_PEER_REVIEW.value,
                                    validation_criteria=[
                                        "cloud_status == HEALTHY",
                                        "active_incidents == 0",
                                    ],
                                ),
                            )
                            self.lifecycle_manager.open_issue(
                                issue=cloud_issue,
                                deacon_id="deacon.cloud_status_patrol",
                                commit=False,
                            )
                        except Exception as ex:
                            logger.warning("Could not open SOCIssue for cloud status: %s", ex)
                else:
                    self.evidence_store.resolve_todo(
                        todo_id,
                        reason="Deacon status patrol observed 0 active Google Cloud disruptions (HEALTHY).",
                    )
                    if self.lifecycle_manager and hasattr(self.lifecycle_manager, "verify_and_close"):
                        try:
                            proof = VerificationProof(
                                verifier_actor="deacon.cloud_status_patrol",
                                telemetry_proof_query="cloud.audit_status()",
                                metric_before="active_incidents > 0",
                                metric_after="active_incidents=0, status=HEALTHY",
                                verified_at=start_time,
                                success=True,
                            )
                            self.lifecycle_manager.verify_and_close("issue_upstream_cloud_status", proof)
                        except Exception:
                            pass

        except Exception as e:
            logger.error("Failed to auto-create patrol beads for %s: %s", handle, e)

        return created_bead_ids

    def _format_patrol_message(
        self,
        handle: str,
        agent_name: str,
        result: Dict[str, Any],
        sched: Dict[str, Any],
        forced: bool,
        created_beads: List[str],
    ) -> str:
        """Constructs domain-tailored, structured chat report for an agent patrol."""
        action = sched.get("action")
        interval = sched.get("interval_hours", 24)
        trigger_label = "MANUAL_OPERATOR_TRIGGER" if forced else f"SCHEDULED_PATROL (Every {interval}h)"

        # 1. Feed Health
        if handle == "@feed-agent" or action == "audit_feeds":
            summary = result.get("summary", {})
            total = summary.get("total_feeds_audited", 0)
            healthy = summary.get("healthy_count", 0)
            irregular = summary.get("irregular_count", 0)
            failed = summary.get("failed_count", 0)
            high_latency = summary.get("high_latency_count", 0)
            quota_rejections = summary.get("quota_rejections_detected", False)

            status_icon = "⚠️" if (failed > 0 or quota_rejections) else "✓"
            msg = (
                f"📡 **Deacon Autonomous Patrol: {agent_name}** (`{handle}`)\n\n"
                f"- **Patrol Status**: `{status_icon} COMPLETED`\n"
                f"- **Trigger**: `{trigger_label}`\n"
                f"- **Audited Ingestion Feeds**: `{total}`\n"
                f"- **Health Breakdown**: `Healthy: {healthy}` | `Irregular: {irregular}` | `Failed: {failed}`\n"
                f"- **Transport Latency (P95 > 4h)**: `{high_latency} feeds exceeding SLA`\n"
                f"- **Ingestion Quota Rejections**: `{'DETECTED (Bandwidth Exceeded)' if quota_rejections else 'None (Within Quota)'}`\n"
            )
            if failed > 0 or quota_rejections:
                msg += f"\n⚠️ **Anomaly Alert**: Ingestion transport interruptions detected. Diagnostic telemetry captured."
            if created_beads:
                bead_list = ", ".join(f"`{b}`" for b in created_beads[:3])
                msg += f"\n📋 **Autonomous Beads Dispatched**: {bead_list}"
            return msg

        # 2. Parser Normalization
        elif handle == "@parser-doctor" or action == "audit_parsers":
            summary = result.get("summary", {})
            total = summary.get("total_parsers_audited", 0)
            healthy = summary.get("healthy_count", 0)
            irregular = summary.get("irregular_count", 0)
            failed = summary.get("failed_count", 0)
            drift = summary.get("version_drift_count", 0)
            conflicts = summary.get("extension_conflict_count", 0)

            status_icon = "⚠️" if (failed > 0 or drift > 0) else "✓"
            msg = (
                f"🔬 **Deacon Autonomous Patrol: {agent_name}** (`{handle}`)\n\n"
                f"- **Patrol Status**: `{status_icon} COMPLETED`\n"
                f"- **Trigger**: `{trigger_label}`\n"
                f"- **Audited SIEM Parsers**: `{total}`\n"
                f"- **Normalization Breakdown**: `Healthy: {healthy}` | `Failed: {failed}` | `Irregular: {irregular}`\n"
                f"- **Logstash Version Drift**: `{drift} parsers with upstream updates`\n"
                f"- **Extension Conflicts**: `{conflicts} conflicting overrides`\n"
            )
            if failed > 0:
                msg += f"\n⚠️ **Anomaly Alert**: Normalizer drops detected across ingested log types."
            if created_beads:
                bead_list = ", ".join(f"`{b}`" for b in created_beads[:3])
                msg += f"\n📋 **Autonomous Beads Dispatched**: {bead_list}"
            return msg

        # 3. Detection Noise & Alert Fatigue
        elif handle == "@detection-tuning-agent" or action == "find_noisy_rules":
            total_rules = result.get("total_rules", 0)
            total_detections = result.get("total_detections", 0)
            window = result.get("lookback_window", "14 days")
            rules = result.get("rules", [])

            msg = (
                f"📉 **Deacon Autonomous Patrol: {agent_name}** (`{handle}`)\n\n"
                f"- **Patrol Status**: `✓ COMPLETED`\n"
                f"- **Trigger**: `{trigger_label}`\n"
                f"- **Lookback Window**: `{window}`\n"
                f"- **Total Detections Evaluated**: `{total_detections:,}`\n"
                f"- **High-Firing Rules Flagged**: `{total_rules}`\n"
            )
            if rules:
                top = rules[0]
                ratio_pct = top.get("ratio_of_total", 0) * 100
                msg += f"- **Top Alert Generator**: `{top.get('rule_name', top.get('rule_id'))}` ({top.get('detection_count', 0):,} alerts, {ratio_pct:.1f}% of total)\n"
            if created_beads:
                bead_list = ", ".join(f"`{b}`" for b in created_beads[:3])
                msg += f"\n📋 **Autonomous Beads Dispatched**: {bead_list}"
            return msg

        # 4. Detection Decay & Unified Repository Audit
        elif handle == "@detection-decay-agent" or action in ("run_decay_synchronization", "audit_rules"):
            total = result.get("total_rules_scanned", result.get("total_rules", 0))
            broken = result.get("failing_count", result.get("broken_count", 0))
            silent = result.get("silent_decay_count", result.get("silent_count", 0))
            avg_dps = result.get("average_dps", 0)
            conflicts = result.get("conflict_count", 0)
            shadowed = result.get("shadowed_by_curated_count", 0)
            synced = result.get("embeddings_synced_count", 0)
            lookback = sched.get("lookback_days", 90)

            status_icon = "⚠️" if (broken > 0 or shadowed > 0) else "✓"
            msg = (
                f"🛡️ **Deacon Autonomous Patrol: {agent_name}** (`{handle}`)\n\n"
                f"- **Patrol Status**: `{status_icon} COMPLETED`\n"
                f"- **Trigger**: `{trigger_label}`\n"
                f"- **Lookback Window**: `{lookback} days`\n"
                f"- **Audited Rules**: `{total}`\n"
                f"- **Rule Health**: `Healthy: {result.get('healthy_count', 0)}` | `Broken: {broken}` | `Silent: {silent}`\n"
                f"- **Repository Hygiene**: `Conflicts (COS≥75): {conflicts}` | `Shadows Curated: {shadowed}` | `Embeddings: {synced}`\n"
            )
            if broken > 0:
                msg += f"\n⚠️ **Anomaly Alert**: {broken} rules have execution failures or invalid syntax."
            if shadowed > 0:
                msg += f"\n💡 **Consolidation Advisory**: {shadowed} customer rules duplicate active Google Curated detections."
            if created_beads:
                bead_list = ", ".join(f"`{b}`" for b in created_beads[:3])
                msg += f"\n📋 **Autonomous Beads Dispatched**: {bead_list}"
            return msg

        # 5. IAM Privilege Drift
        elif handle == "@identity-governor" or action == "run_identity_drift_audit":
            users = result.get("total_users", 0)
            groups = result.get("total_groups", 0)
            roles = result.get("custom_roles_count", 0)
            drift = result.get("drift", {})
            has_drift = drift.get("has_drift", False)

            status_icon = "⚠️" if has_drift else "✓"
            msg = (
                f"🔑 **Deacon Autonomous Patrol: {agent_name}** (`{handle}`)\n\n"
                f"- **Patrol Status**: `{status_icon} COMPLETED`\n"
                f"- **Trigger**: `{trigger_label}`\n"
                f"- **GCP IAM Assets Audited**: `Users: {users}` | `Groups: {groups}` | `Custom Roles: {roles}`\n"
                f"- **Privilege Drift Status**: `{'⚠️ Drift Detected' if has_drift else '✓ Clean (No Drift)'}`\n"
            )
            if has_drift:
                msg += f"- **Drift Details**: {drift.get('summary', 'Unsanctioned privilege expansion observed.')}\n"
            if created_beads:
                bead_list = ", ".join(f"`{b}`" for b in created_beads[:3])
                msg += f"\n📋 **Autonomous Beads Dispatched**: {bead_list}"
            return msg

        # 6. Tenant Posture & Configuration Governance
        elif handle == "@tenant-posture-agent" or action == "audit_tenant_posture":
            has_drift = result.get("has_drift", False)
            status_icon = "⚠️" if has_drift else "✓"
            drift_count = result.get("drift_count", 0)
            crit = result.get("critical_changes_count", 0)
            high = result.get("high_changes_count", 0)
            fingerprint = result.get("fingerprint") or result.get("overall_fingerprint") or "N/A"
            fp_short = fingerprint[:16] + "..." if len(fingerprint) > 16 else fingerprint
            snapshot_id = result.get("snapshot_id", "N/A")

            msg = (
                f"🏛️ **Deacon Autonomous Patrol: {agent_name}** (`{handle}`)\n\n"
                f"- **Patrol Status**: `{status_icon} COMPLETED`\n"
                f"- **Trigger**: `{trigger_label}`\n"
                f"- **Baseline Snapshot**: `{snapshot_id}`\n"
                f"- **Configuration Fingerprint**: `{fp_short}`\n"
                f"- **Posture Status**: `{'⚠️ Configuration Drift Detected' if has_drift else '✓ In Compliance (No Drift)'}`\n"
                f"- **Drift Metrics**: `Total: {drift_count}` | `Critical: {crit}` | `High: {high}`\n"
            )
            if has_drift:
                subsystems = ", ".join(result.get("subsystems_drifted", []))
                msg += f"\n⚠️ **Drift Alert**: Configuration drift detected in subsystems: `{subsystems}`."
            if created_beads:
                bead_list = ", ".join(f"`{b}`" for b in created_beads[:3])
                msg += f"\n📋 **Autonomous Beads Dispatched**: {bead_list}"
            return msg

        # 7. SOAR Playbook Inventory & Decay Patrol
        elif handle == "@playbook-decay-agent" or action == "audit_playbook_decay":
            summary = result.get("summary", {})
            total_audited = summary.get("total_audited", 0)
            avg_score = summary.get("average_resilience_score", 0.0)
            degraded_count = summary.get("degraded_playbooks_count", 0)
            status_icon = "⚠️" if degraded_count > 0 else "✓"

            msg = (
                f"⚡ **Deacon Autonomous Patrol: {agent_name}** (`{handle}`)\n\n"
                f"- **Patrol Status**: `{status_icon} COMPLETED`\n"
                f"- **Trigger**: `{trigger_label}`\n"
                f"- **Playbooks Audited**: `{total_audited}`\n"
                f"- **Catalog Avg Resilience Score**: `{avg_score}/100`\n"
                f"- **Degraded Playbooks**: `{degraded_count}`\n"
            )
            if degraded_count > 0:
                msg += f"\n⚠️ **Degraded Playbook Alert**: {degraded_count} playbooks exhibit resilience score < 70 or failure rate > 20%."
            if created_beads:
                bead_list = ", ".join(f"`{b}`" for b in created_beads[:3])
                msg += f"\n📋 **Autonomous Beads Dispatched**: {bead_list}"
            return msg

        # 8. Timestamp Integrity & Clock Skew Patrol
        elif handle == "@timestamp-integrity-agent" or action == "audit_timestamp_integrity":
            summary = result.get("summary", {})
            total_audited = summary.get("total_log_types", 0)
            new_anomalies = summary.get("new_anomalies_count", 0)
            previously_known = summary.get("previously_known_count", 0)
            skewed_events = summary.get("total_skewed_events", 0)
            delayed_events = summary.get("total_delayed_events", 0)
            status_icon = "⚠️" if (skewed_events > 0 or new_anomalies > 0) else "✓"

            msg = (
                f"⚡ **Deacon Autonomous Patrol: {agent_name}** (`{handle}`)\n\n"
                f"- **Patrol Status**: `{status_icon} COMPLETED`\n"
                f"- **Trigger**: `{trigger_label}`\n"
                f"- **Log Sources Audited**: `{total_audited}`\n"
                f"- **New Latency Anomalies**: `{new_anomalies}`\n"
                f"- **Previously Known Anomalies**: `{previously_known}`\n"
                f"- **Clock Skewed Events (Δt < 0)**: `{skewed_events:,}`\n"
                f"- **Severe Delays (>2h)**: `{delayed_events:,}`\n"
            )
            if skewed_events > 0:
                msg += f"\n⚠️ **Telemetry Clock Skew Alert**: {skewed_events:,} events were ingested with timestamps claiming to be in the future relative to ingestion."
            if created_beads:
                bead_list = ", ".join(f"`{b}`" for b in created_beads[:3])
                msg += f"\n📋 **Autonomous Beads Dispatched**: {bead_list}"
            return msg

        # 9. Google Cloud Status & Disruption Patrol
        elif handle == "@cloud-status-agent" or action == "audit_cloud_service_status":
            overall_health = result.get("overall_health", "HEALTHY")
            active_incidents = result.get("active_incidents", [])
            active_count = len(active_incidents)
            recent_resolved = len(result.get("recent_resolved", []))
            status_icon = "⚠️" if active_count > 0 else "✓"

            msg = (
                f"☁️ **Deacon Autonomous Patrol: {agent_name}** (`{handle}`)\n\n"
                f"- **Patrol Status**: `{status_icon} COMPLETED`\n"
                f"- **Trigger**: `{trigger_label}`\n"
                f"- **Platform Health**: `{overall_health}`\n"
                f"- **Active Disruptions**: `{active_count}`\n"
                f"- **Recently Resolved (14d)**: `{recent_resolved}`\n"
                f"- **Summary**: {result.get('status_summary', 'All services operational.')}\n"
            )
            if active_count > 0:
                msg += "\n⚠️ **Active Incident Details**:\n"
                for inc in active_incidents[:3]:
                    msg += f"  - **{inc.get('id')}**: {inc.get('external_desc')}\n    *Severity*: `{inc.get('severity')}` | *Impact*: `{inc.get('status_impact')}` | [Status Page]({inc.get('public_url')})\n"
            if created_beads:
                bead_list = ", ".join(f"`{b}`" for b in created_beads[:3])
                msg += f"\n📋 **Autonomous Beads Dispatched**: {bead_list}"
            return msg

        # Generic Fallback
        return (
            f"**Deacon Autonomous Patrol: {agent_name}** (`{handle}`)\n\n"
            f"- **Status**: `COMPLETED`\n"
            f"- **Trigger**: `{trigger_label}`\n"
            f"- **Action**: `{action}`\n"
            f"- **Summary**: Routine operational sweep executed against live SecOps endpoints.\n"
        )

    async def _execute_scheduled_task(self, sched: Dict[str, Any], forced: bool = False) -> Dict[str, Any]:
        """Executes the action configured for an agent."""
        handle = sched.get("agent_handle")
        action = sched.get("action")
        stream = sched.get("stream", "detections")
        topic = sched.get("topic", "decay-review")
        agent = self.fleet.get(handle)

        if not agent:
            logger.error("Agent %s not found in fleet for scheduled execution", handle)
            return {"status": "ERROR", "message": f"Agent {handle} not found"}

        logger.info("Executing scheduled task for %s (action=%s, forced=%s)", handle, action, forced)
        now_utc = datetime.now(timezone.utc)
        start_time = now_utc.isoformat()

        result: Dict[str, Any] = {}
        try:
            if action == "audit_feeds" and hasattr(agent, "audit_feeds"):
                lookback = sched.get("lookback_days", 7)
                result = agent.audit_feeds(lookback_days=lookback)
            elif action == "audit_parsers" and hasattr(agent, "audit_parsers"):
                lookback = sched.get("lookback_days", 7)
                result = agent.audit_parsers(lookback_days=lookback)
            elif action == "find_noisy_rules" and hasattr(agent, "find_noisy_rules"):
                lookback = sched.get("lookback_days", 14)
                result = agent.find_noisy_rules(lookback_days=lookback, limit=20)
            elif action == "audit_rules":
                if hasattr(agent, "engine") and agent.engine and hasattr(agent.engine, "audit_rules"):
                    rep = agent.engine.audit_rules(
                        include_curated=sched.get("include_curated", True),
                        sync_embeddings=sched.get("sync_embeddings", True),
                        lookback_days=sched.get("lookback_days", 90),
                    )
                    result = rep.to_dict()
                    result["widget"] = {
                        "type": "rule_audit_card",
                        "title": "Detection Repository Health Audit",
                        "data": result,
                    }
                elif hasattr(agent, "run_decay_synchronization"):
                    lookback = sched.get("lookback_days", 90)
                    result = agent.run_decay_synchronization(lookback_days=lookback)
            elif action == "run_decay_synchronization" and hasattr(agent, "run_decay_synchronization"):
                lookback = sched.get("lookback_days", 90)
                result = agent.run_decay_synchronization(lookback_days=lookback)
            elif action == "run_identity_drift_audit" and hasattr(agent, "run_identity_drift_audit"):
                result = agent.run_identity_drift_audit()
            elif action == "audit_tenant_posture" and hasattr(agent, "audit_tenant_posture"):
                result = agent.audit_tenant_posture(snapshot=True)
            elif action == "audit_playbook_decay":
                lookback = sched.get("lookback_days", 30)
                if hasattr(agent, "audit_playbook_decay"):
                    result = agent.audit_playbook_decay(lookback_days=lookback)
                elif hasattr(agent, "engine") and agent.engine and hasattr(agent.engine, "audit_playbook_decay"):
                    result = agent.engine.audit_playbook_decay(lookback_days=lookback)
            elif action == "audit_cloud_service_status":
                lookback = sched.get("lookback_days", 14)
                if hasattr(agent, "engine") and agent.engine and hasattr(agent.engine, "audit_cloud_service_status"):
                    rep = agent.engine.audit_cloud_service_status(lookback_days=lookback)
                    result = rep.to_dict()
                elif hasattr(agent, "audit_cloud_service_status"):
                    rep = agent.audit_cloud_service_status(lookback_days=lookback)
                    result = rep.to_dict() if hasattr(rep, "to_dict") else rep
                else:
                    from engine.workflows.cloud_status import audit_cloud_service_status
                    rep = audit_cloud_service_status(lookback_days=lookback)
                    result = rep.to_dict()
            elif hasattr(agent, action or ""):
                method = getattr(agent, action)
                result = method()
            else:
                # Chat invocation fallback
                msg = await agent.chat(
                    f"Perform periodic scheduled audit for stream #{stream} topic {topic}.",
                    stream=stream,
                    topic=topic,
                )
                result = {"status": "SUCCESS", "content": msg.content, "widget": msg.widget}

            status = "SUCCESS"
            sched["last_status"] = status
            sched["last_run_at"] = start_time
            sched["last_error"] = None

            # Calculate next run
            interval = sched.get("interval_hours", 24)
            sched["next_run_at"] = (datetime.now(timezone.utc) + timedelta(hours=interval)).isoformat()

            # Autonomously register actionable tasks (beads) in Evidence Fabric
            created_beads = self._auto_create_patrol_beads(handle, result, sched, start_time)

            # Assign interactive card widget
            widget = result.get("widget") or getattr(agent, "last_widget", None)
            if not widget and action == "find_noisy_rules" and result.get("rules"):
                widget = {
                    "type": "data_table",
                    "title": f"Top Noisy Rules ({result.get('lookback_window', '14 days')})",
                    "columns": ["Rule ID", "Rule Name", "Type", "Alert State", "Detections", "% of Total"],
                    "rows": [
                        [
                            r.get("rule_id", ""),
                            r.get("rule_name", ""),
                            r.get("rule_type", ""),
                            r.get("alert_state", ""),
                            f"{r.get('detection_count', 0):,}",
                            f"{r.get('ratio_of_total', 0) * 100:.1f}%",
                        ]
                        for r in result.get("rules", [])[:10]
                    ],
                }

            if hasattr(agent, "last_widget"):
                agent.last_widget = None

            # Format domain-specific chat notification
            content = self._format_patrol_message(
                handle=handle,
                agent_name=agent.name,
                result=result,
                sched=sched,
                forced=forced,
                created_beads=created_beads,
            )

            # Classify communication priority and build structured Observation
            comm_class = CommunicationClass.INFORMATIONAL
            if status in ("ERROR", "FAILED") or any((b.get("severity") if isinstance(b, dict) else None) == "CRITICAL" for b in created_beads):
                comm_class = CommunicationClass.URGENT
            elif created_beads:
                comm_class = CommunicationClass.OPERATIONAL

            obs = Observation(
                observation_id=f"obs-{handle.replace('@', '')}-{int(datetime.now(timezone.utc).timestamp())}",
                subject=SubjectRef(type="subsystem", id=stream),
                observed_by=ObserverRef(agent=handle, run_id=f"run-{int(datetime.now(timezone.utc).timestamp())}", deacon="deacon-scheduler"),
                predicate=f"patrol_{action or 'audit'}",
                value={"status": status, "summary": str(result.get("status") or ""), "created_beads": len(created_beads)},
                communication_policy=CommunicationPolicy(
                    communication_class=comm_class.value,
                    urgency={"urgent": "critical", "operational": "medium"}.get(comm_class.value, "low"),
                    briefing=True,
                    immediate_notification=(comm_class == CommunicationClass.URGENT),
                    target_channel=f"#{stream}",
                ),
                confidence=1.0,
                observed_at=start_time,
                valid_until=(datetime.now(timezone.utc) + timedelta(hours=sched.get("interval_hours", 8) * 2)).isoformat(),
            )

            # Route observation through central CommunicationRouter
            self.communication_router.dispatch(obs)

            # Broadcast to collaborative chat store only if operator-forced or if URGENT / OPERATIONAL (no spam for healthy patrols)
            if self.chat_store and (forced or comm_class in (CommunicationClass.URGENT, CommunicationClass.OPERATIONAL)):
                self.chat_store.add_message(
                    stream=stream,
                    topic=topic,
                    sender_handle=handle,
                    sender_type="agent",
                    content=content,
                    widget=widget,
                )


            # Record in Evidence Fabric
            if self.evidence_store:
                self.evidence_store.record_evidence(
                    agent_handle=handle,
                    action=action or "scheduled_execution",
                    stream=stream,
                    topic=topic,
                    prompt="Periodic automated schedule trigger",
                    response=str(result.get("status")),
                    executed_tools=getattr(agent, "executed_tool_calls", []),
                    metadata={"forced": forced, "summary": result, "created_beads": created_beads},
                )
                self.evidence_store.save_agent_config(handle, sched)

            # Update Deacon internal telemetry
            self._last_patrol_run_at = start_time
            self._total_patrols_run += 1
            self._patrol_history.append({
                "agent_handle": handle,
                "action": action,
                "stream": stream,
                "topic": topic,
                "executed_at": start_time,
                "status": status,
                "forced": forced,
                "created_beads": created_beads,
            })

            return {"status": "SUCCESS", "details": result, "created_beads": created_beads}

        except Exception as e:
            logger.exception("Scheduled task for %s failed: %s", handle, e)
            sched["last_status"] = "ERROR"
            sched["last_error"] = str(e)
            sched["last_run_at"] = start_time
            if self.evidence_store:
                self.evidence_store.save_agent_config(handle, sched)
            return {"status": "ERROR", "error": str(e)}

    async def _worker_loop(self) -> None:
        """Continuous evaluation loop for agent schedules."""
        logger.info("FleetScheduler worker loop started (poll_interval=%ds)", self.poll_interval_seconds)
        while self._running:
            try:
                now = datetime.now(timezone.utc)
                self._last_heartbeat_at = now.isoformat()
                self._reclaim_expired_leases()
                await self._dispatch_issue_work()
                for handle, sched in list(self._schedules.items()):
                    if not sched.get("enabled", False):
                        continue

                    next_run_str = sched.get("next_run_at")
                    if not next_run_str:
                        continue

                    try:
                        next_run = datetime.fromisoformat(next_run_str)
                        if next_run.tzinfo is None:
                            next_run = next_run.replace(tzinfo=timezone.utc)
                    except Exception:
                        continue

                    if now >= next_run:
                        logger.info("Schedule triggered for %s (due %s)", handle, next_run_str)
                        await self._execute_scheduled_task(sched, forced=False)

            except Exception as e:
                logger.error("Error in FleetScheduler worker iteration: %s", e)

            await asyncio.sleep(self.poll_interval_seconds)

    def _reclaim_expired_leases(self) -> List[str]:
        """Returns issues held by crashed/stalled workers to the pool."""
        queue = self.work_queue or getattr(self.lifecycle_manager, "work_queue", None)
        if queue is None or not hasattr(queue, "reclaim_expired_leases"):
            return []
        try:
            return queue.reclaim_expired_leases()
        except Exception as e:
            logger.error("Lease reclamation failed: %s", e)
            return []

    async def _dispatch_issue_work(self) -> List[str]:
        """Lets idle agents claim and work eligible issues (no-op when disabled)."""
        if self.issue_worker is None:
            return []
        try:
            return await self.issue_worker.dispatch()
        except Exception as e:
            logger.error("Issue worker dispatch failed: %s", e)
            return []

    def get_worker_status(self) -> Dict[str, Any]:
        if self.issue_worker is None:
            return {"enabled": False, "in_flight": [], "recent_runs": [], "playbooks": []}
        return self.issue_worker.status()

    def start(self) -> None:
        """Starts the scheduler background task."""
        if self._running:
            return
        self._running = True
        self._task = asyncio.create_task(self._worker_loop())
        logger.info("FleetScheduler background task launched")

    def stop(self) -> None:
        """Stops the scheduler background task."""
        self._running = False
        if self.issue_worker is not None:
            self.issue_worker.cancel_all()
        if self._task and not self._task.done():
            self._task.cancel()
        logger.info("FleetScheduler background task stopped")
