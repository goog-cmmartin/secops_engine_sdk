"""Fleet Scheduler Subsystem for Autonomous Google SecOps ADK 2 Agents.

Provides per-agent scheduling, cron/interval evaluation, background execution,
and integration with Evidence Fabric and Collaborative Chat Streams.
"""

import asyncio
from datetime import datetime, timedelta, timezone
import logging
from typing import Any, Callable, Dict, List, Optional

from agents.core.base_adk_agent import BaseSecOpsAdkAgent
from agents.core.evidence_store import EvidenceFabricStore

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
        "action": "run_decay_synchronization",
        "description": "Daily 90-day detection telemetry aggregation and DPS rule decay audit",
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
}


class FleetScheduler:
    """Evaluates agent schedules, triggers periodic workflows, and notifies chat streams."""

    def __init__(
        self,
        fleet: Dict[str, BaseSecOpsAdkAgent],
        evidence_store: Optional[EvidenceFabricStore] = None,
        chat_store: Optional[Any] = None,
        poll_interval_seconds: int = 30,
    ):
        self.fleet = fleet
        self.evidence_store = evidence_store
        self.chat_store = chat_store
        self.poll_interval_seconds = poll_interval_seconds
        self._running = False
        self._task: Optional[asyncio.Task] = None
        self._schedules: Dict[str, Dict[str, Any]] = {}
        self._last_patrol_run_at: Optional[str] = None
        self._last_heartbeat_at: Optional[str] = datetime.now(timezone.utc).isoformat()
        self._total_patrols_run: int = 0
        self._patrol_history: List[Dict[str, Any]] = []
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

    def get_schedule(self, agent_handle: str) -> Dict[str, Any]:
        """Returns the current schedule for an agent handle."""
        if agent_handle not in self._schedules:
            self._schedules[agent_handle] = {
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
        sched = self.get_schedule(agent_handle)
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
        timestamp = int(datetime.now(timezone.utc).timestamp())

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
                        todo_id = f"todo_feed_{feed_id[:16]}_{timestamp}"
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
                        self.evidence_store.save_todo(todo_id, task)
                        created_bead_ids.append(todo_id)

            # 2. Parser Normalization Drops & Errors
            elif handle == "@parser-doctor" or action == "audit_parsers":
                findings = result.get("findings", [])
                for f in findings:
                    status = str(f.get("status", "")).upper()
                    drop_code = f.get("drop_reason_code")
                    unparsed = f.get("unparsed_log_count") or f.get("unparsed_count") or 0
                    if status == "FAILED" or drop_code or unparsed > 0:
                        log_type = str(f.get("log_type", "UNKNOWN"))
                        todo_id = f"todo_parser_{log_type.lower()}_{timestamp}"
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
                        self.evidence_store.save_todo(todo_id, task)
                        created_bead_ids.append(todo_id)

            # 3. Alert Fatigue & Noisy Detection Rules
            elif handle == "@detection-tuning-agent" or action == "find_noisy_rules":
                rules = result.get("rules", [])
                if rules:
                    top_rule = rules[0]
                    rule_id = str(top_rule.get("rule_id", "rule"))
                    rule_name = top_rule.get("rule_name") or rule_id
                    todo_id = f"todo_tuning_{rule_id[:16]}_{timestamp}"
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
                    self.evidence_store.save_todo(todo_id, task)
                    created_bead_ids.append(todo_id)

            # 4. Detection Rule Decay
            elif handle == "@detection-decay-agent" or action == "run_decay_synchronization":
                broken_count = result.get("broken_count", 0)
                if broken_count > 0:
                    todo_id = f"todo_decay_broken_{timestamp}"
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
                        "rationale": f"Deacon decay patrol identified {broken_count} broken rules requiring YARA-L remediation.",
                        "created_at": start_time,
                    }
                    self.evidence_store.save_todo(todo_id, task)
                    created_bead_ids.append(todo_id)

            # 5. IAM Privilege Drift
            elif handle == "@identity-governor" or action == "run_identity_drift_audit":
                drift = result.get("drift", {})
                if drift.get("has_drift"):
                    todo_id = f"todo_iam_drift_{timestamp}"
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
                    self.evidence_store.save_todo(todo_id, task)
                    created_bead_ids.append(todo_id)

            # 6. Tenant Posture & Configuration Drift
            elif handle == "@tenant-posture-agent" or action == "audit_tenant_posture":
                if result.get("has_drift"):
                    todo_id = f"todo_posture_drift_{timestamp}"
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
                    self.evidence_store.save_todo(todo_id, task)
                    created_bead_ids.append(todo_id)

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

        # 4. Detection Decay
        elif handle == "@detection-decay-agent" or action == "run_decay_synchronization":
            total = result.get("total_rules", 0)
            broken = result.get("broken_count", 0)
            silent = result.get("silent_count", 0)
            avg_dps = result.get("average_dps", 0)
            lookback = sched.get("lookback_days", 90)

            status_icon = "⚠️" if broken > 0 else "✓"
            msg = (
                f"🛡️ **Deacon Autonomous Patrol: {agent_name}** (`{handle}`)\n\n"
                f"- **Patrol Status**: `{status_icon} COMPLETED`\n"
                f"- **Trigger**: `{trigger_label}`\n"
                f"- **Lookback Window**: `{lookback} days`\n"
                f"- **Audited Rules**: `{total}`\n"
                f"- **Rule Health**: `Broken: {broken}` | `Silent: {silent}` | `Average DPS: {avg_dps}`\n"
            )
            if broken > 0:
                msg += f"\n⚠️ **Anomaly Alert**: {broken} rules have broken syntax or missing UDM fields."
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
            elif action == "run_decay_synchronization" and hasattr(agent, "run_decay_synchronization"):
                lookback = sched.get("lookback_days", 90)
                result = agent.run_decay_synchronization(lookback_days=lookback)
            elif action == "run_identity_drift_audit" and hasattr(agent, "run_identity_drift_audit"):
                result = agent.run_identity_drift_audit()
            elif action == "audit_tenant_posture" and hasattr(agent, "audit_tenant_posture"):
                result = agent.audit_tenant_posture(snapshot=True)
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

            # Broadcast to collaborative chat store
            if self.chat_store:
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
        if self._task and not self._task.done():
            self._task.cancel()
        logger.info("FleetScheduler background task stopped")
