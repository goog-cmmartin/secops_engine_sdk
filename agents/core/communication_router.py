"""Three-Tier Communication Router for the Autonomous Google SecOps Multi-Agent Fleet.

Enforces the operational communication contract:
- URGENT: Real-time immediate alerts (Slack webhook / urgent stream)
- OPERATIONAL: Issues created/updated in the work queue (Gas Town Git ledger)
- INFORMATIONAL: Buffered into the SOC Knowledge Store for the next shift briefing

Prevents autonomous agents from uncoordinated direct messaging and chat channel spam.
"""

from datetime import datetime, timezone
import json
import logging
import os
from typing import Any, Callable, Dict, List, Optional
import uuid

from engine.domain import (
    CommunicationClass,
    CommunicationPolicy,
    IssueLifecycleStatus,
    IssueProblem,
    IssueSeverity,
    IssueSource,
    Observation,
    OperationalPlane,
    SOCIssue,
)
from agents.core.knowledge_store import BaseKnowledgeStore, get_knowledge_store
from agents.core.lifecycle import SOCLifecycleManager
from agents.core.work_queue import BaseWorkQueue, get_work_queue

logger = logging.getLogger(__name__)


class CommunicationRouter:
    """Routes observations, issues, and alerts according to strict communication policy classes."""

    def __init__(
        self,
        knowledge_store: Optional[BaseKnowledgeStore] = None,
        work_queue: Optional[BaseWorkQueue] = None,
        lifecycle_manager: Optional[SOCLifecycleManager] = None,
        materializer: Optional[Any] = None,
        chat_store: Optional[Any] = None,
        slack_webhook_url: Optional[str] = None,
    ):
        self.knowledge_store = knowledge_store or get_knowledge_store()
        self.work_queue = work_queue or get_work_queue()
        self.materializer = materializer
        self.lifecycle_manager = lifecycle_manager or SOCLifecycleManager(
            work_queue=self.work_queue,
            materializer=materializer,
        )
        self.chat_store = chat_store
        self.slack_webhook_url = slack_webhook_url or os.environ.get("SLACK_WEBHOOK_URL")
        self._urgent_alerts_log: List[Dict[str, Any]] = []

    def _create_issue_for_observation(self, observation: Observation, severity: str) -> SOCIssue:
        now_str = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
        rnd = uuid.uuid4().hex[:6]
        subj = observation.subject.id
        title = f"{subj}: {observation.predicate}"
        issue = SOCIssue(
            id=f"SOC-AUTO-{now_str}-{rnd}",
            type=observation.predicate,
            severity=severity,
            source=IssueSource(deacon_id=observation.observed_by.agent),
            problem=IssueProblem(
                title=title,
                observed_state=str(observation.value),
                desired_state="NOMINAL",
            ),
        )
        return self.lifecycle_manager.open_issue(issue, deacon_id=observation.observed_by.agent)

    def dispatch(
        self,
        observation: Observation,
        linked_issue: Optional[SOCIssue] = None,
    ) -> Dict[str, Any]:
        """Dispatches an agent observation according to its communication class."""
        policy = observation.communication
        c_class = (policy.communication_class or CommunicationClass.OPERATIONAL.value).lower()

        # Step 1: Record observation in institutional knowledge store
        obs_id = self.knowledge_store.publish_observation(observation)
        observation.observation_id = obs_id

        result = {
            "observation_id": obs_id,
            "class": c_class,
            "routing_class": c_class,
            "action_taken": [],
            "issue_id": None,
            "alert_dispatched": False,
            "published_to_chat": False,
        }

        # Step 2: Handle Class-Specific Routing
        if c_class == CommunicationClass.URGENT.value or policy.immediate_notification:
            # URGENT: Immediate notification to operators
            alert_payload = self._dispatch_urgent_alert(observation)
            result["alert_dispatched"] = True
            result["published_to_chat"] = True
            result["urgent_alert_card"] = alert_payload
            result["action_taken"].append("URGENT_ALERT_DISPATCHED")
            result["alert_payload"] = alert_payload

            # Also ensure an issue is opened if not already existing
            if linked_issue:
                issue = self.lifecycle_manager.open_issue(linked_issue, deacon_id=observation.observed_by.agent)
                observation.issue_id = issue.id
                result["issue_id"] = issue.id
                result["action_taken"].append(f"SOC_ISSUE_OPENED_{issue.id}")
            elif not observation.issue_id:
                issue = self._create_issue_for_observation(observation, severity=IssueSeverity.CRITICAL.value)
                observation.issue_id = issue.id
                result["issue_id"] = issue.id
                result["action_taken"].append(f"SOC_ISSUE_OPENED_{issue.id}")

        elif c_class == CommunicationClass.OPERATIONAL.value:
            # OPERATIONAL: Register in Work Queue / Git ledger, zero Slack noise
            if linked_issue and not observation.issue_id:
                issue = self.lifecycle_manager.open_issue(linked_issue, deacon_id=observation.observed_by.agent)
                observation.issue_id = issue.id
                result["issue_id"] = issue.id
                result["action_taken"].append(f"SOC_ISSUE_OPENED_{issue.id}")
            elif observation.issue_id:
                result["issue_id"] = observation.issue_id
                result["action_taken"].append(f"OBSERVATION_ATTACHED_TO_{observation.issue_id}")
            else:
                issue = self._create_issue_for_observation(observation, severity=IssueSeverity.MEDIUM.value)
                observation.issue_id = issue.id
                result["issue_id"] = issue.id
                result["action_taken"].append(f"SOC_ISSUE_OPENED_{issue.id}")

        else:
            # INFORMATIONAL: Buffered into next briefing, zero chat/queue noise
            result["action_taken"].append("BUFFERED_FOR_NEXT_SHIFT_BRIEFING")

        return result

    def _dispatch_urgent_alert(self, observation: Observation) -> Dict[str, Any]:
        """Dispatches an urgent alert to the chat urgent stream and Slack webhook if configured."""
        subj = f"{observation.subject.type}:{observation.subject.id}"
        agent = observation.observed_by.agent
        predicate = observation.predicate
        val = observation.value

        title = f"🚨 URGENT SECOPS ALERT: {subj} ({predicate})"
        summary = (
            f"**Critical Operational Condition Detected**\n\n"
            f"- **Subject**: `{subj}`\n"
            f"- **Observed By**: `{agent}`\n"
            f"- **Predicate**: `{predicate}`\n"
            f"- **Confidence**: `{observation.confidence * 100:.0f}%`\n"
            f"- **Details**: `{json.dumps(val, default=str)[:300]}`\n"
            f"- **Time**: `{observation.observed_at}`"
        )

        alert_entry = {
            "type": "urgent_alert_card",
            "title": title,
            "summary": summary,
            "observation_id": observation.observation_id,
            "subject": subj,
            "agent": agent,
            "timestamp": observation.observed_at,
        }
        self._urgent_alerts_log.append(alert_entry)


        # 1. Collaborative Chat Urgent Stream
        if self.chat_store:
            try:
                self.chat_store.add_message(
                    stream="general",
                    topic="urgent-alerts",
                    sender_handle=agent,
                    sender_type="agent",
                    content=summary,
                    widget={
                        "type": "urgent_alert_card",
                        "title": title,
                        "data": alert_entry,
                    },
                )
            except Exception as e:
                logger.error("Failed to post urgent alert to chat store: %s", e)

        # 2. Slack Webhook Integration (if configured)
        if self.slack_webhook_url:
            self._send_slack_webhook(title, summary, observation)

        logger.critical("DISPATCHED URGENT SECOPS ALERT: %s by %s", subj, agent)
        return alert_entry

    def _send_slack_webhook(self, title: str, summary: str, observation: Observation) -> None:
        """Sends an urgent alert block to the configured Slack webhook URL."""
        import urllib.request
        payload = {
            "text": f"🚨 *{title}*",
            "blocks": [
                {
                    "type": "header",
                    "text": {"type": "plain_text", "text": title, "emoji": True},
                },
                {
                    "type": "section",
                    "fields": [
                        {"type": "mrkdwn", "text": f"*Subject:*\n`{observation.subject.type}:{observation.subject.id}`"},
                        {"type": "mrkdwn", "text": f"*Agent:*\n`{observation.observed_by.agent}`"},
                        {"type": "mrkdwn", "text": f"*Urgency:*\n`{observation.communication.urgency.upper()}`"},
                        {"type": "mrkdwn", "text": f"*Confidence:*\n`{observation.confidence * 100:.0f}%`"},
                    ],
                },
                {
                    "type": "context",
                    "elements": [
                        {"type": "mrkdwn", "text": f"Observation ID: `{observation.observation_id}` | Time: `{observation.observed_at}`"}
                    ],
                },
            ],
        }
        try:
            req = urllib.request.Request(
                self.slack_webhook_url,
                data=json.dumps(payload).encode("utf-8"),
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=5) as resp:
                logger.info("Sent urgent alert to Slack (status: %d)", resp.status)
        except Exception as e:
            logger.error("Failed to post urgent alert to Slack webhook: %s", e)


_DEFAULT_ROUTER: Optional[CommunicationRouter] = None


def get_communication_router(
    chat_store: Optional[Any] = None,
    knowledge_store: Optional[BaseKnowledgeStore] = None,
    work_queue: Optional[BaseWorkQueue] = None,
) -> CommunicationRouter:
    """Singleton factory for the communication router."""
    global _DEFAULT_ROUTER
    if _DEFAULT_ROUTER is None:
        _DEFAULT_ROUTER = CommunicationRouter(
            knowledge_store=knowledge_store,
            work_queue=work_queue,
            chat_store=chat_store,
        )
    elif chat_store and not _DEFAULT_ROUTER.chat_store:
        _DEFAULT_ROUTER.chat_store = chat_store
    return _DEFAULT_ROUTER
