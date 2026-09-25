"""Chat Engine and Message Store for the Zulip/Slack-inspired SecOps Web Interface.

Provides:
- Persistent JSONL message storage (.chat/messages.jsonl).
- Stream & Topic partitioning matching Zulip semantics.
- Pub/Sub broadcasting for real-time Server-Sent Events (SSE).
- Autonomous agent mention detection and dispatch to the Google ADK 2 fleet.
"""

import asyncio
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
import json
import logging
from pathlib import Path
import re
from typing import Any, Dict, List, Optional, Set

from agents.core.base_adk_agent import BaseSecOpsAdkAgent
from agents.core.proposal_manager import ChangeProposal, PreflightProof, ProposalManager
from agents.core.evidence_store import EvidenceFabricStore
from engine.facade import SecOpsEngine

logger = logging.getLogger(__name__)


@dataclass
class ChatMessage:
    """Represents a message in a stream and topic."""
    id: str
    stream: str
    topic: str
    sender_handle: str
    sender_type: str  # "user" or "agent"
    content: str
    proposal_id: Optional[str] = None
    widget: Optional[Dict[str, Any]] = None
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


@dataclass
class ActiveAgentJob:
    """Represents an active, in-flight agent reasoning or execution task."""
    job_id: str
    stream: str
    topic: str
    agent_handle: str
    user_handle: str = "@operator"
    status: str = "THINKING"  # "THINKING", "TOOL_EXECUTION", "COMPLETED", "FAILED"
    step: str = "Reasoning with Gemini and evaluating workflows..."
    started_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


DEFAULT_STREAMS = [
    {
        "id": "general",
        "name": "general",
        "display_name": "General & Dispatch",
        "description": "Central coordinator topics and fleet announcements",
        "default_topics": ["dispatcher", "announcements"],
    },
    {
        "id": "detections",
        "name": "detections",
        "display_name": "Detection Rules & YARA-L",
        "description": "Rule performance, compilation, triage, and optimization proposals",
        "default_topics": ["rule-proposals", "decay-review", "rule-conflicts", "performance-alerts", "triage"],
    },
    {
        "id": "ingestion",
        "name": "ingestion",
        "display_name": "Ingestion & Parsers",
        "description": "Feeds, BindPlane, raw log drops, and parser health",
        "default_topics": ["feed-health", "parser-drops"],
    },
    {
        "id": "testing",
        "name": "testing",
        "display_name": "Testing & Replay",
        "description": "LogJammer empirical replays and pre-flight verifications",
        "default_topics": ["logjammer-replays", "benchmark-runs"],
    },
    {
        "id": "identity",
        "name": "identity",
        "display_name": "Identity & IAM",
        "description": "IAM role governance and Cloud Logging audit telemetry",
        "default_topics": ["access-audits", "service-accounts"],
    },
    {
        "id": "soar",
        "name": "soar",
        "display_name": "SOAR & Automation",
        "description": "Playbooks, cases, SLAs, and webhook connectors",
        "default_topics": ["case-escalations", "playbook-runs", "playbook-health"],
    },
    {
        "id": "analytics",
        "name": "analytics",
        "display_name": "Analytics & GoogleSQL",
        "description": "Natural language queries, GoogleSQL compilations, aggregations, and metrics",
        "default_topics": ["sql-queries", "reports", "udm-aggregations"],
    },
]


class ChatStore:
    """Manages chat persistence and real-time subscriber queues."""

    def __init__(self, root_dir: Optional[Path] = None):
        self.root_dir = Path(root_dir) if root_dir else Path.cwd()
        self.chat_dir = self.root_dir / ".chat"
        self.chat_dir.mkdir(parents=True, exist_ok=True)
        self.messages_file = self.chat_dir / "messages.jsonl"

        self._messages: List[ChatMessage] = []
        self._subscribers: Set[asyncio.Queue] = set()
        self._active_jobs: Dict[str, ActiveAgentJob] = {}
        self._load_messages()

    def _load_messages(self) -> None:
        """Loads historical messages from JSONL file."""
        if not self.messages_file.is_file():
            return

        with open(self.messages_file, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    data = json.loads(line)
                    self._messages.append(ChatMessage(**data))
                except Exception as e:
                    logger.warning("Skipping corrupted message line: %s", e)

    def add_message(
        self,
        stream: str,
        topic: str,
        sender_handle: str,
        sender_type: str,
        content: str,
        proposal_id: Optional[str] = None,
        widget: Optional[Dict[str, Any]] = None,
    ) -> ChatMessage:
        """Persists a new message and broadcasts it to active SSE subscribers."""
        timestamp = datetime.now(timezone.utc)
        msg_id = f"msg-{timestamp.strftime('%Y%m%d%H%M%S')}-{len(self._messages) + 1}"

        message = ChatMessage(
            id=msg_id,
            stream=stream,
            topic=topic,
            sender_handle=sender_handle,
            sender_type=sender_type,
            content=content,
            proposal_id=proposal_id,
            widget=widget,
            created_at=timestamp.isoformat(),
        )

        self._messages.append(message)

        # Append to JSONL on disk
        with open(self.messages_file, "a", encoding="utf-8") as f:
            f.write(json.dumps(asdict(message)) + "\n")

        # Broadcast to async listeners
        self.broadcast(message)
        return message

    def clear_topic(self, stream: str, topic: str) -> int:
        """Removes all messages for a specific stream and topic, rewriting messages.jsonl.

        Returns the number of messages cleared.
        """
        initial_count = len(self._messages)
        self._messages = [
            m for m in self._messages
            if not (m.stream == stream and m.topic == topic)
        ]
        cleared = initial_count - len(self._messages)

        # Rewrite JSONL file
        temp_file = self.messages_file.with_suffix(".tmp")
        with open(temp_file, "w", encoding="utf-8") as f:
            for m in self._messages:
                f.write(json.dumps(asdict(m)) + "\n")
        temp_file.replace(self.messages_file)

        # Broadcast topic_cleared event to active SSE subscribers
        event_payload = {
            "type": "topic_cleared",
            "stream": stream,
            "topic": topic,
            "cleared_count": cleared,
        }
        for q in list(self._subscribers):
            try:
                q.put_nowait(event_payload)
            except Exception:
                pass

        logger.info(f"Cleared {cleared} messages for stream='{stream}', topic='{topic}'")
        return cleared

    def list_messages(
        self,
        stream: str,
        topic: Optional[str] = None,
        limit: int = 100,
    ) -> List[ChatMessage]:
        """Returns messages matching stream and optional topic filter."""
        filtered = [
            m for m in self._messages
            if m.stream == stream and (topic is None or m.topic == topic)
        ]
        return filtered[-limit:]

    def list_streams(self) -> List[Dict[str, Any]]:
        """Returns registered streams with topic lists and unread counts."""
        streams_copy = []
        for s in DEFAULT_STREAMS:
            s_dict = dict(s)
            s_dict["topics"] = self.list_topics(s["id"])
            streams_copy.append(s_dict)
        return streams_copy

    def list_topics(self, stream: str) -> List[Dict[str, Any]]:
        """Returns unique topics for a stream with message counts and last activity."""
        topics_map: Dict[str, Dict[str, Any]] = {}

        # Initialize with default stream topics
        for s in DEFAULT_STREAMS:
            if s["id"] == stream:
                for default_topic in s.get("default_topics", []):
                    topics_map[default_topic] = {
                        "name": default_topic,
                        "message_count": 0,
                        "last_activity": None,
                    }
                break

        # Tally messages
        for m in self._messages:
            if m.stream == stream:
                if m.topic not in topics_map:
                    topics_map[m.topic] = {
                        "name": m.topic,
                        "message_count": 0,
                        "last_activity": None,
                    }
                topics_map[m.topic]["message_count"] += 1
                topics_map[m.topic]["last_activity"] = m.created_at

        return sorted(list(topics_map.values()), key=lambda t: t["name"])

    def subscribe(self) -> asyncio.Queue:
        """Subscribes to live chat broadcast events."""
        queue: asyncio.Queue = asyncio.Queue()
        self._subscribers.add(queue)
        return queue

    def unsubscribe(self, queue: asyncio.Queue) -> None:
        """Removes a subscriber queue."""
        self._subscribers.discard(queue)

    def broadcast(self, message: ChatMessage) -> None:
        """Pushes a message event into all active subscriber queues."""
        event_payload = {
            "type": "new_message",
            "message": asdict(message),
        }
        for q in list(self._subscribers):
            try:
                q.put_nowait(event_payload)
            except Exception as e:
                logger.debug("Failed to deliver broadcast to subscriber: %s", e)

    def start_job(
        self,
        stream: str,
        topic: str,
        agent_handle: str,
        user_handle: str = "@operator",
        step: str = "Reasoning with Gemini and evaluating workflows...",
    ) -> ActiveAgentJob:
        """Registers a new active agent execution job and broadcasts status."""
        job_id = f"job_{stream}_{topic}_{agent_handle}_{int(datetime.now(timezone.utc).timestamp() * 1000)}"
        now_iso = datetime.now(timezone.utc).isoformat()
        job = ActiveAgentJob(
            job_id=job_id,
            stream=stream,
            topic=topic,
            agent_handle=agent_handle,
            user_handle=user_handle,
            status="THINKING",
            step=step,
            started_at=now_iso,
            updated_at=now_iso,
        )
        self._active_jobs[job_id] = job
        self.broadcast_job_status(job)
        return job

    def update_job(
        self,
        job_id: str,
        step: Optional[str] = None,
        status: Optional[str] = None,
    ) -> Optional[ActiveAgentJob]:
        """Updates in-flight job progress and broadcasts to clients."""
        job = self._active_jobs.get(job_id)
        if not job:
            return None
        if step is not None:
            job.step = step
        if status is not None:
            job.status = status
        job.updated_at = datetime.now(timezone.utc).isoformat()
        self.broadcast_job_status(job)
        return job

    def complete_job(self, job_id: str) -> Optional[ActiveAgentJob]:
        """Marks a job completed and removes it from active registry."""
        job = self._active_jobs.pop(job_id, None)
        if job:
            job.status = "COMPLETED"
            event_payload = {
                "type": "job_completed",
                "job_id": job.job_id,
                "stream": job.stream,
                "topic": job.topic,
                "agent_handle": job.agent_handle,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
            for q in list(self._subscribers):
                try:
                    q.put_nowait(event_payload)
                except Exception as e:
                    logger.debug("Failed to deliver complete broadcast: %s", e)
        return job

    def fail_job(self, job_id: str, error_message: str = "") -> Optional[ActiveAgentJob]:
        """Marks a job failed and removes it from active registry."""
        job = self._active_jobs.pop(job_id, None)
        if job:
            job.status = "FAILED"
            job.step = f"Failed: {error_message}"
            event_payload = {
                "type": "job_failed",
                "job_id": job.job_id,
                "stream": job.stream,
                "topic": job.topic,
                "agent_handle": job.agent_handle,
                "error": error_message,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
            for q in list(self._subscribers):
                try:
                    q.put_nowait(event_payload)
                except Exception as e:
                    logger.debug("Failed to deliver failed broadcast: %s", e)
        return job

    def list_active_jobs(
        self,
        stream: Optional[str] = None,
        topic: Optional[str] = None,
        max_age_seconds: float = 180.0,
    ) -> List[ActiveAgentJob]:
        """Returns all currently active jobs, reaping any timed-out zombie jobs."""
        now = datetime.now(timezone.utc)
        active: List[ActiveAgentJob] = []
        to_reap: List[str] = []

        for job_id, job in self._active_jobs.items():
            try:
                started = datetime.fromisoformat(job.started_at)
                age = (now - started).total_seconds()
                if age > max_age_seconds:
                    to_reap.append(job_id)
                    continue
            except Exception:
                pass

            if stream and job.stream != stream:
                continue
            if topic and job.topic != topic:
                continue
            active.append(job)

        for job_id in to_reap:
            logger.warning("Reaping stale in-flight agent job %s (exceeded TTL)", job_id)
            self._active_jobs.pop(job_id, None)

        return active

    def broadcast_job_status(self, job: ActiveAgentJob) -> None:
        """Broadcasts active job state to all SSE subscribers."""
        event_payload = {
            "type": "agent_status",
            "job": asdict(job),
            "job_id": job.job_id,
            "stream": job.stream,
            "topic": job.topic,
            "agent_handle": job.agent_handle,
            "user_handle": job.user_handle,
            "status": job.step,
            "step": job.step,
            "timestamp": job.updated_at,
        }
        for q in list(self._subscribers):
            try:
                q.put_nowait(event_payload)
            except Exception as e:
                logger.debug("Failed to deliver job status broadcast: %s", e)

    def broadcast_status(
        self,
        stream: str,
        topic: str,
        agent_handle: str,
        status: str,
        step: Optional[str] = None,
    ) -> None:
        """Pushes a real-time agent execution status update to all active subscriber queues."""
        event_payload = {
            "type": "agent_status",
            "stream": stream,
            "topic": topic,
            "agent_handle": agent_handle,
            "status": status,
            "step": step or status,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        for q in list(self._subscribers):
            try:
                q.put_nowait(event_payload)
            except Exception as e:
                logger.debug("Failed to deliver status broadcast to subscriber: %s", e)


class AgentDispatcher:
    """Dispatches user messages to Google ADK 2 agents based on @mentions or intent."""

    def __init__(
        self,
        chat_store: ChatStore,
        fleet: Dict[str, BaseSecOpsAdkAgent],
        engine: Optional[SecOpsEngine] = None,
        proposal_manager: Optional[ProposalManager] = None,
        evidence_store: Optional[EvidenceFabricStore] = None,
    ):
        self.chat_store = chat_store
        self.fleet = fleet
        self.engine = engine
        self.proposal_manager = proposal_manager or ProposalManager()
        self.evidence_store = evidence_store

        # Ensure dispatcher has fleet reference
        dispatcher = self.fleet.get("@secops-dispatcher")
        if dispatcher and hasattr(dispatcher, "set_fleet"):
            dispatcher.set_fleet(self.fleet)

    def extract_mentions(self, text: str) -> List[str]:
        """Extracts @handle mentions from message text."""
        return re.findall(r"@[\w-]+", text)

    async def dispatch(self, user_message: ChatMessage) -> List[ChatMessage]:
        """Routes message to relevant agents and records responses in the stream/topic."""
        if user_message.sender_type != "user":
            return []

        replies: List[ChatMessage] = []

        # If in direct message (dm) stream, route automatically to the agent named in the topic
        if user_message.stream == "dm":
            target_topic = user_message.topic if user_message.topic.startswith("@") else f"@{user_message.topic}"
            target_handles = [target_topic]
        else:
            # If no specific agent mentioned, default to @secops-dispatcher
            mentions = self.extract_mentions(user_message.content)
            target_handles = mentions if mentions else ["@secops-dispatcher"]

        for handle in target_handles:
            h_lower = handle.lower()
            if h_lower in ("@decayagent", "@decay-agent", "@detection-decay-agent"):
                resolved_handle = "@detection-decay-agent"
            elif h_lower in ("@rule-conflict-agent", "@conflict-agent", "@conflictagent", "@ruleconflictagent", "@rule-conflict", "@ruleconflict", "@ruleconflictagent"):
                resolved_handle = "@rule-conflict-agent"
            elif h_lower in ("@tuningagent", "@tuning-agent", "@detection-tuning-agent", "@noise-suppression-agent"):
                resolved_handle = "@detection-tuning-agent"
            elif h_lower in ("@feed-agent", "@feedagent", "@ingestion-doctor"):
                resolved_handle = "@feed-agent"
            elif h_lower in ("@parser-doctor", "@parserdoctor", "@cbn-optimizer"):
                resolved_handle = "@parser-doctor"
            elif h_lower in ("@sql-analyst", "@sqlagent", "@sql-agent", "@nl2sql", "@udm-sql-agent"):
                resolved_handle = "@sql-analyst"
            elif h_lower in ("@gcp-telemetry-agent", "@gcptelemetry", "@telemetry-agent", "@gcp-telemetry", "@gcp-agent", "@cloud-telemetry"):
                resolved_handle = "@gcp-telemetry-agent"
            elif h_lower in ("@tenant-posture-agent", "@posture-agent", "@config-governor", "@tenant-baseline-agent", "@postureagent", "@tenantposture"):
                resolved_handle = "@tenant-posture-agent"
            elif h_lower in ("@playbook-decay-agent", "@playbook-decay", "@playbook-agent", "@playbookdecay", "@playbook"):
                resolved_handle = "@playbook-decay-agent"
            elif h_lower in ("@timestamp-integrity-agent", "@timestamp-agent", "@timestamp", "@ntp-agent", "@clock-skew-agent", "@timestampintegrity"):
                resolved_handle = "@timestamp-integrity-agent"
            elif h_lower in ("@log-cost-agent", "@cost-agent", "@log-cost", "@finops-agent", "@cost-optimization-agent", "@logcostagent", "@logcost", "@costagent"):
                resolved_handle = "@log-cost-agent"
            elif h_lower in ("@raw-log-agent", "@raw-logs", "@log-search-agent", "@raw-log", "@rawlogs", "@rawlogagent", "@rawlog"):
                resolved_handle = "@raw-log-agent"
            elif h_lower in ("@namespace-label-agent", "@namespace-agent", "@ingestion-label-agent", "@label-agent", "@namespacelabelagent", "@namespacelabels", "@namespace", "@ingestion-labels"):
                resolved_handle = "@namespace-label-agent"
            else:
                resolved_handle = handle
            agent = self.fleet.get(resolved_handle)
            if not agent:
                continue

            # Register active job in persistent server-side store & broadcast status
            job = self.chat_store.start_job(
                stream=user_message.stream,
                topic=user_message.topic,
                agent_handle=agent.handle,
                user_handle=user_message.sender_handle,
                step="Reasoning with Gemini and evaluating workflows...",
            )

            # Attach dynamic status callback for intermediate tool executions
            def _status_cb(status_text: str) -> None:
                self.chat_store.update_job(job.job_id, step=status_text)
            agent.status_callback = _status_cb

            try:
                response = await self._execute_agent(agent, user_message)
                if response:
                    reply = self.chat_store.add_message(
                        stream=user_message.stream,
                        topic=user_message.topic,
                        sender_handle=agent.handle,
                        sender_type="agent",
                        content=response["content"],
                        proposal_id=response.get("proposal_id"),
                        widget=response.get("widget"),
                    )
                    replies.append(reply)
                self.chat_store.complete_job(job.job_id)
            except Exception as e:
                logger.error("Agent %s failed during execution: %s", agent.handle, e, exc_info=True)
                self.chat_store.fail_job(job.job_id, error_message=str(e))
                err_reply = self.chat_store.add_message(
                    stream=user_message.stream,
                    topic=user_message.topic,
                    sender_handle=agent.handle,
                    sender_type="agent",
                    content=f"⚠️ **Execution Error**: Failed processing request: `{str(e)}`",
                )
                replies.append(err_reply)

        return replies

    async def _execute_agent(
        self,
        agent: BaseSecOpsAdkAgent,
        message: ChatMessage,
    ) -> Optional[Dict[str, Any]]:
        """Executes domain logic for a specialized agent in the context of the chat conversation."""
        prompt = message.content.strip()

        # Handle @secops-dispatcher (Live Autonomous Google ADK 2 Agent with Gemini 3.8 Flash)
        if agent.handle == "@secops-dispatcher":
            agent_msg = await agent.chat(prompt, stream=message.stream, topic=message.topic)
            return {
                "content": agent_msg.content,
                "proposal_id": agent_msg.proposal_id,
                "widget": agent_msg.widget,
            }

        # Handle @rule-troubleshooter (Live Autonomous Google ADK 2 Agent with Gemini)
        elif agent.handle == "@rule-troubleshooter":
            agent_msg = await agent.chat(prompt, stream=message.stream, topic=message.topic)
            return {
                "content": agent_msg.content,
                "proposal_id": agent_msg.proposal_id,
                "widget": agent_msg.widget,
            }

        # Handle @yaral-optimizer (Live Autonomous Google ADK 2 Agent with Gemini 3.8 Flash)
        elif agent.handle == "@yaral-optimizer":
            agent_msg = await agent.chat(prompt, stream=message.stream, topic=message.topic)
            return {
                "content": agent_msg.content,
                "proposal_id": agent_msg.proposal_id,
                "widget": agent_msg.widget,
            }

        # Handle @logjammer-agent (Live Autonomous Google ADK 2 Agent with Gemini 3.8 Flash & Log Jammer)
        elif agent.handle == "@logjammer-agent":
            agent_msg = await agent.chat(prompt, stream=message.stream, topic=message.topic)
            widget = agent_msg.widget or getattr(agent, "last_widget", None)
            if hasattr(agent, "last_widget"):
                agent.last_widget = None
            return {
                "content": agent_msg.content,
                "proposal_id": agent_msg.proposal_id,
                "widget": widget,
            }

        # Handle @identity-governor (Live Autonomous Google ADK 2 Agent with Gemini 3.8 Flash & GCP IAM)
        elif agent.handle == "@identity-governor":
            agent_msg = await agent.chat(prompt, stream=message.stream, topic=message.topic)
            widget = agent_msg.widget or getattr(agent, "last_widget", None)
            if hasattr(agent, "last_widget"):
                agent.last_widget = None
            return {
                "content": agent_msg.content,
                "proposal_id": agent_msg.proposal_id,
                "widget": widget,
            }

        # Handle @detection-decay-agent (Live Autonomous Google ADK 2 Agent with Gemini 3.8 Flash & Rule Decay)
        elif agent.handle in ("@detection-decay-agent", "@DecayAgent"):
            agent_msg = await agent.chat(prompt, stream=message.stream, topic=message.topic)
            widget = agent_msg.widget or getattr(agent, "last_widget", None)
            if hasattr(agent, "last_widget"):
                agent.last_widget = None
            return {
                "content": agent_msg.content,
                "proposal_id": agent_msg.proposal_id,
                "widget": widget,
            }

        # Handle @rule-conflict-agent (Live Autonomous Google ADK 2 Agent with Gemini 3.8 Flash & Rule Conflicts)
        elif agent.handle in ("@rule-conflict-agent", "@RuleConflictAgent", "@conflict-agent", "@RuleConflict"):
            agent_msg = await agent.chat(prompt, stream=message.stream, topic=message.topic)
            widget = agent_msg.widget or getattr(agent, "last_widget", None)
            if hasattr(agent, "last_widget"):
                agent.last_widget = None
            return {
                "content": agent_msg.content,
                "proposal_id": agent_msg.proposal_id,
                "widget": widget,
            }

        # Handle @detection-tuning-agent (Live Autonomous Google ADK 2 Agent with Gemini 3.8 Flash & Noise Suppression)
        elif agent.handle in ("@detection-tuning-agent", "@TuningAgent"):
            agent_msg = await agent.chat(prompt, stream=message.stream, topic=message.topic)
            widget = agent_msg.widget or getattr(agent, "last_widget", None)
            if hasattr(agent, "last_widget"):
                agent.last_widget = None
            return {
                "content": agent_msg.content,
                "proposal_id": agent_msg.proposal_id,
                "widget": widget,
            }

        # Handle @feed-agent (Live Autonomous Google ADK 2 Agent with Gemini 3.8 Flash & Feed Health)
        elif agent.handle in ("@feed-agent", "@ingestion-doctor", "@FeedAgent"):
            agent_msg = await agent.chat(prompt, stream=message.stream, topic=message.topic)
            widget = agent_msg.widget or getattr(agent, "last_widget", None)
            if hasattr(agent, "last_widget"):
                agent.last_widget = None
            return {
                "content": agent_msg.content,
                "proposal_id": agent_msg.proposal_id,
                "widget": widget,
            }

        # Handle @parser-doctor (Live Autonomous Google ADK 2 Agent with Gemini 3.8 Flash & Parser Health)
        elif agent.handle in ("@parser-doctor", "@cbn-optimizer", "@ParserDoctor"):
            agent_msg = await agent.chat(prompt, stream=message.stream, topic=message.topic)
            widget = agent_msg.widget or getattr(agent, "last_widget", None)
            if hasattr(agent, "last_widget"):
                agent.last_widget = None
            return {
                "content": agent_msg.content,
                "proposal_id": agent_msg.proposal_id,
                "widget": widget,
            }

        # Handle @sql-analyst (Live Autonomous Google ADK 2 Agent with Gemini 3.8 Flash & GoogleSQL)
        elif agent.handle in ("@sql-analyst", "@sqlagent", "@sql-agent", "@nl2sql", "@udm-sql-agent"):
            agent_msg = await agent.chat(prompt, stream=message.stream, topic=message.topic)
            widget = agent_msg.widget or getattr(agent, "last_widget", None)
            if hasattr(agent, "last_widget"):
                agent.last_widget = None
            return {
                "content": agent_msg.content,
                "proposal_id": agent_msg.proposal_id,
                "widget": widget,
            }

        # Handle @gcp-telemetry-agent (Live Autonomous Google ADK 2 Agent with Gemini 3.8 Flash & GCP Telemetry)
        elif agent.handle in ("@gcp-telemetry-agent", "@telemetry-agent", "@gcp-telemetry", "@GcpTelemetryAgent"):
            agent_msg = await agent.chat(prompt, stream=message.stream, topic=message.topic)
            widget = agent_msg.widget or getattr(agent, "last_widget", None)
            if hasattr(agent, "last_widget"):
                agent.last_widget = None
            return {
                "content": agent_msg.content,
                "proposal_id": agent_msg.proposal_id,
                "widget": widget,
            }

        # Handle @tenant-posture-agent (Live Autonomous Google ADK 2 Agent with Gemini 3.8 Flash & Evidence Fabric Baselines)
        elif agent.handle in ("@tenant-posture-agent", "@posture-agent", "@config-governor", "@tenant-baseline-agent", "@TenantPostureAgent"):
            agent_msg = await agent.chat(prompt, stream=message.stream, topic=message.topic)
            widget = agent_msg.widget or getattr(agent, "last_widget", None)
            if hasattr(agent, "last_widget"):
                agent.last_widget = None
            return {
                "content": agent_msg.content,
                "proposal_id": agent_msg.proposal_id,
                "widget": widget,
            }

        # Handle @playbook-decay-agent (Live Autonomous Google ADK 2 Agent with Gemini 3.8 Flash & Playbook Decay Audit)
        elif agent.handle in ("@playbook-decay-agent", "@playbook-decay", "@playbook-agent", "@playbookdecay", "@PlaybookDecayAgent"):
            agent_msg = await agent.chat(prompt, stream=message.stream, topic=message.topic)
            widget = agent_msg.widget or getattr(agent, "last_widget", None)
            if hasattr(agent, "last_widget"):
                agent.last_widget = None
            return {
                "content": agent_msg.content,
                "proposal_id": agent_msg.proposal_id,
                "widget": widget,
            }

        # Handle @timestamp-integrity-agent (Live Autonomous Google ADK 2 Agent with Gemini 3.8 Flash & Timestamp Integrity Audit)
        elif agent.handle in ("@timestamp-integrity-agent", "@timestamp-agent", "@timestamp", "@ntp-agent", "@clock-skew-agent", "@TimestampIntegrityAgent"):
            agent_msg = await agent.chat(prompt, stream=message.stream, topic=message.topic)
            widget = agent_msg.widget or getattr(agent, "last_widget", None)
            if hasattr(agent, "last_widget"):
                agent.last_widget = None

            content = agent_msg.content
            tracking = getattr(agent, "last_tracking", None)
            if hasattr(agent, "last_tracking"):
                agent.last_tracking = None

            if tracking:
                todo_id = tracking.get("todo_id", "todo_timestamp_integrity_active")
                prio = tracking.get("priority", "HIGH")
                sightings = tracking.get("sighting_count", 1)
                if tracking.get("is_new"):
                    banner = f"\n\n🚨 **Tracked in Actions**: Created actionable task [`{todo_id}`](#actions) in Triage ({prio} PRIORITY)."
                elif tracking.get("auto_resolved"):
                    banner = f"\n\n🟢 **Actions**: Telemetry nominal. Actionable task [`{todo_id}`](#actions) marked **RESOLVED**."
                elif sightings > 1:
                    banner = f"\n\nℹ️ **Tracked in Actions**: Corroborated active issue [`{todo_id}`](#actions) in Triage (Sighted {sightings}x, {prio} PRIORITY)."
                else:
                    banner = f"\n\nℹ️ **Tracked in Actions**: Active issue [`{todo_id}`](#actions) in Triage ({prio} PRIORITY)."
                content += banner

            return {
                "content": content,
                "proposal_id": agent_msg.proposal_id,
                "widget": widget,
            }

        # Handle @log-cost-agent (Live Autonomous Google ADK 2 Agent with Gemini 3.8 Flash & FinOps)
        elif agent.handle in ("@log-cost-agent", "@cost-agent", "@finops-agent", "@LogCostAgent", "@ingestion-cost-agent"):
            agent_msg = await agent.chat(prompt, stream=message.stream, topic=message.topic)
            widget = agent_msg.widget or getattr(agent, "last_widget", None)
            if hasattr(agent, "last_widget"):
                agent.last_widget = None
            return {
                "content": agent_msg.content,
                "proposal_id": agent_msg.proposal_id,
                "widget": widget,
            }

        # Handle @raw-log-agent (Live Autonomous Google ADK 2 Agent with Gemini 3.8 Flash & Raw Log Search)
        elif agent.handle in ("@raw-log-agent", "@raw-logs", "@log-search-agent", "@raw-log", "@rawlogs", "@rawlogagent"):
            agent_msg = await agent.chat(prompt, stream=message.stream, topic=message.topic)
            widget = agent_msg.widget or getattr(agent, "last_widget", None)
            if hasattr(agent, "last_widget"):
                agent.last_widget = None
            return {
                "content": agent_msg.content,
                "proposal_id": agent_msg.proposal_id,
                "widget": widget,
            }

        # Dynamic fallback for any ADK 2 agent with chat method
        if hasattr(agent, "chat") and callable(agent.chat):
            agent_msg = await agent.chat(prompt, stream=message.stream, topic=message.topic)
            widget = getattr(agent_msg, "widget", None) or getattr(agent, "last_widget", None)
            if hasattr(agent, "last_widget"):
                agent.last_widget = None
            return {
                "content": getattr(agent_msg, "content", str(agent_msg)),
                "proposal_id": getattr(agent_msg, "proposal_id", None),
                "widget": widget,
            }

        # Default fallback for other agents
        return {
            "content": f"**{agent.name}** (`{agent.handle}`) received your instruction: {prompt}"
        }
