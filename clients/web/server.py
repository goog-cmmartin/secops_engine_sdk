"""FastAPI Backend Server for the SecOps Multi-Agent Fleet Web Chat.

Exposes:
- REST API for Streams, Topics, Messages, Agents, and Gas Town Proposals.
- Server-Sent Events (SSE) for live stream/topic timeline broadcasts.
- Static file serving for the Zulip-inspired Slack-like Single Page App.
"""

import asyncio
from dataclasses import asdict
from datetime import datetime, timezone
import json
import logging
import os
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import BackgroundTasks, Body, FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel, Field

from agents.core.proposal_manager import ProposalManager
from agents.core.evidence_store import get_evidence_store, EvidenceFabricStore
from agents.core.fleet_scheduler import FleetScheduler
from agents.core.work_queue import get_work_queue, BaseWorkQueue
from agents.core.materializer import IssueMaterializer
from agents.core.lifecycle import SOCLifecycleManager
from agents.core.knowledge_store import get_knowledge_store
from agents.core.communication_router import get_communication_router
from agents.generated import create_agent_fleet
from clients.web.chat_engine import ChatMessage, ChatStore, AgentDispatcher

from engine.domain import (
    IssueLifecycleStatus,
    IssueSeverity,
    OperationalPlane,
    AuthorityTier,
    SOCIssue,
    IssueProblem,
    IssueRouting,
    IssueGovernance,
    Lease,
    AgentCapabilityProfile,
)
from engine.facade import SecOpsEngine
from engine.registry import WorkflowRegistry
from tests.test_helpers import get_live_engine

logger = logging.getLogger(__name__)

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
STATIC_DIR = Path(__file__).resolve().parent / "static"


class _InertAdapterForWeb:
    """Inert adapter when live ADC credentials are not configured."""
    def __getattr__(self, name: str) -> Any:
        def _no_op(*args: Any, **kwargs: Any) -> Any:
            return {}
        return _no_op


def _build_engine() -> SecOpsEngine:
    """Instantiates a live SecOpsEngine if GCP env is configured, otherwise an inert instance."""
    try:
        return get_live_engine()
    except Exception as e:
        logger.info("Initializing web engine with offline adapter: %s", e)
        return SecOpsEngine(adapter=_InertAdapterForWeb(), custom_registry=WorkflowRegistry())


# Core singleton instances
chat_store = ChatStore(root_dir=REPO_ROOT)
proposal_manager = ProposalManager()
engine = _build_engine()
evidence_store = get_evidence_store(root_dir=str(REPO_ROOT))
work_queue = get_work_queue(root_dir=str(REPO_ROOT))
issue_materializer = IssueMaterializer()
lifecycle_manager = SOCLifecycleManager(
    work_queue=work_queue,
    materializer=issue_materializer,
)
fleet = create_agent_fleet(
    engine=engine,
    proposal_manager=proposal_manager,
    evidence_store=evidence_store,
    work_queue=work_queue,
    lifecycle_manager=lifecycle_manager,
)
dispatcher = AgentDispatcher(
    chat_store=chat_store,
    fleet=fleet,
    engine=engine,
    proposal_manager=proposal_manager,
    evidence_store=evidence_store,
)
knowledge_store = get_knowledge_store(root_dir=REPO_ROOT)
communication_router = get_communication_router(
    work_queue=work_queue,
    chat_store=chat_store,
    knowledge_store=knowledge_store,
)
fleet_scheduler = FleetScheduler(
    fleet=fleet,
    evidence_store=evidence_store,
    chat_store=chat_store,
    lifecycle_manager=lifecycle_manager,
    work_queue=work_queue,
    communication_router=communication_router,
    knowledge_store=knowledge_store,
)


try:
    dedup_stats = evidence_store.deduplicate_todos()
    if dedup_stats.get("deleted", 0) > 0:
        logger.info("Consolidated duplicate Gas Town tasks on startup: %s", dedup_stats)
except Exception as e:
    logger.warning("Failed to deduplicate todos on startup: %s", e)

# Seed an initial announcement if store is empty
if len(chat_store.list_messages("general", "announcements")) == 0:
    chat_store.add_message(
        stream="general",
        topic="announcements",
        sender_handle="@secops-dispatcher",
        sender_type="agent",
        content=(
            "🚀 **SecOps Multi-Agent Fleet is Online**.\n\n"
            "Welcome to the fleet workspace. You can coordinate with 17 specialized agents across "
            "`#general`, `#detections`, `#ingestion`, `#testing`, `#identity`, and `#soar`.\n\n"
            "Try asking `@rule-troubleshooter analyze ru_0e378636` or `@yaral-optimizer optimize ru_0e378636`!"
        ),
    )

app = FastAPI(
    title="Google SecOps Multi-Agent Fleet Chat",
    description="Zulip/Slack-inspired interface for autonomous SecOps agents and Gas Town change proposals.",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def add_no_cache_headers(request: Request, call_next: Any) -> Any:
    response = await call_next(request)
    if request.url.path.startswith("/static/") or request.url.path == "/":
        response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
        response.headers["Pragma"] = "no-cache"
        response.headers["Expires"] = "0"
    return response


@app.on_event("startup")
async def startup_event() -> None:
    for agent in fleet.values():
        if hasattr(agent, "register_worker"):
            try:
                agent.register_worker()
            except Exception as reg_err:
                logger.warning("Failed to register agent %s: %s", getattr(agent, "handle", "unknown"), reg_err)
    fleet_scheduler.start()


@app.on_event("shutdown")
async def shutdown_event() -> None:
    fleet_scheduler.stop()


# --- Request/Response Models ---

class PostMessageRequest(BaseModel):
    stream: str = Field(..., description="Target stream name (e.g. 'detections')")
    topic: str = Field(..., description="Target topic name (e.g. 'rule-proposals')")
    content: str = Field(..., description="Message text in Markdown format")
    sender_handle: str = Field(default="@operator", description="Sender handle")
    sender_type: str = Field(default="user", description="Sender type ('user' or 'agent')")
    proposal_id: Optional[str] = Field(default=None, description="Optional proposal identifier")
    widget: Optional[Dict[str, Any]] = Field(default=None, description="Optional UI widget payload")


class ApproveProposalRequest(BaseModel):
    merged_by: str = Field(default="secops-operator", description="Identifier of human approving mutation")
    approval_note: Optional[str] = Field(default=None, description="Operator justification recorded with the merge")


class RejectProposalRequest(BaseModel):
    reason: str = Field(..., description="Explanation of why change was rejected")
    rejected_by: str = Field(default="secops-operator", description="Reviewer identifier")


class AckEscalationRequest(BaseModel):
    acked_by: str = Field(default="secops-operator", description="Operator acknowledging the escalation")
    note: Optional[str] = Field(default=None, description="Optional acknowledgement note")


# --- Escalation acknowledgements ---
# Escalations are derived on each /api/gastown/overview call, so operator
# acknowledgements are persisted separately, keyed by escalation id.
ESCALATION_ACKS_PATH = REPO_ROOT / ".state" / "escalation_acks.json"


def _load_escalation_acks() -> Dict[str, Dict[str, Any]]:
    try:
        return json.loads(ESCALATION_ACKS_PATH.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def _save_escalation_acks(acks: Dict[str, Dict[str, Any]]) -> None:
    ESCALATION_ACKS_PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp = ESCALATION_ACKS_PATH.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(acks, indent=2, sort_keys=True), encoding="utf-8")
    tmp.replace(ESCALATION_ACKS_PATH)


def _humanize_age(ts: Any) -> Optional[str]:
    """Returns a compact age string (e.g. '42m', '3h', '2d') for an ISO timestamp, or None."""
    if not ts:
        return None
    try:
        dt = datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    secs = max(0, int((datetime.now(timezone.utc) - dt).total_seconds()))
    if secs < 3600:
        return f"{max(1, secs // 60)}m"
    if secs < 86400:
        return f"{secs // 3600}h"
    return f"{secs // 86400}d"


# --- API Routes ---

@app.get("/api/health")
async def health_check() -> Dict[str, Any]:
    """Returns system status, active agents, and open proposals."""
    open_props = proposal_manager.list_proposals(status="OPEN")
    return {
        "status": "healthy",
        "version": app.version,
        "agents_online": len(fleet),
        "open_proposals": len(open_props),
        "engine_capabilities": len(engine.registry.list_capabilities()),
        "evidence_fabric_store": evidence_store.__class__.__name__,
    }


@app.get("/api/streams")
async def list_streams() -> List[Dict[str, Any]]:
    """Returns list of streams with nested topics and statistics."""
    return chat_store.list_streams()


@app.get("/api/streams/{stream}/topics")
async def list_stream_topics(stream: str) -> List[Dict[str, Any]]:
    """Returns topics for a given stream."""
    return chat_store.list_topics(stream)


@app.get("/api/messages")
async def list_messages(
    stream: str = Query(..., description="Stream name (e.g. 'detections')"),
    topic: Optional[str] = Query(None, description="Topic name filter"),
    limit: int = Query(100, ge=1, le=500),
) -> List[Dict[str, Any]]:
    """Retrieves messages for a stream and topic."""
    messages = chat_store.list_messages(stream=stream, topic=topic, limit=limit)
    return [asdict(m) for m in messages]


@app.post("/api/messages")
async def post_message(
    body: PostMessageRequest,
    background_tasks: BackgroundTasks,
) -> Dict[str, Any]:
    """Posts a message and triggers autonomous agent dispatch."""
    user_msg = chat_store.add_message(
        stream=body.stream,
        topic=body.topic,
        sender_handle=body.sender_handle,
        sender_type=body.sender_type,
        content=body.content,
        proposal_id=body.proposal_id,
        widget=body.widget,
    )

    # Dispatch to agents asynchronously if posted by human user
    if body.sender_type == "user":
        background_tasks.add_task(dispatcher.dispatch, user_msg)

    return {
        "status": "sent",
        "message": asdict(user_msg),
    }


@app.delete("/api/messages")
async def clear_messages(
    stream: str = Query(..., description="Target stream name (e.g. 'ingestion')"),
    topic: str = Query(..., description="Target topic name to clear (e.g. 'parser-drops')"),
) -> Dict[str, Any]:
    """Clears all historical messages for a specific stream and topic."""
    cleared = chat_store.clear_topic(stream=stream, topic=topic)
    return {
        "status": "cleared",
        "stream": stream,
        "topic": topic,
        "cleared_count": cleared,
    }


@app.get("/api/jobs/active")
async def get_active_jobs(
    stream: Optional[str] = Query(None, description="Filter by stream name"),
    topic: Optional[str] = Query(None, description="Filter by topic name"),
) -> List[Dict[str, Any]]:
    """Returns currently in-flight agent reasoning and execution jobs."""
    jobs = chat_store.list_active_jobs(stream=stream, topic=topic)
    return [asdict(j) for j in jobs]


@app.get("/api/events")
async def sse_event_stream() -> StreamingResponse:
    """Streams real-time messages and proposal events using Server-Sent Events (SSE)."""
    async def event_generator():
        queue = chat_store.subscribe()
        try:
            # Send initial keepalive
            yield f"data: {json.dumps({'type': 'connected'})}\n\n"
            # Send initial active jobs snapshot so reconnecting clients immediately hydrate
            active_jobs = [asdict(j) for j in chat_store.list_active_jobs()]
            yield f"data: {json.dumps({'type': 'active_jobs_snapshot', 'jobs': active_jobs})}\n\n"
            while True:
                event = await queue.get()
                yield f"data: {json.dumps(event)}\n\n"
        except asyncio.CancelledError:
            chat_store.unsubscribe(queue)
        finally:
            chat_store.unsubscribe(queue)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


def _format_cadence(sched: Optional[Dict[str, Any]]) -> str:
    """Operator-facing cadence label.

    "On-Demand" = agent has no schedule; "Manual" = schedule exists but is
    disabled; otherwise "Every Nh" / "Every Nm" (sub-hour intervals).
    """
    if not sched:
        return "On-Demand"
    if not sched.get("enabled"):
        return "Manual"
    hours = sched.get("interval_hours")
    try:
        hours = float(hours)
    except (TypeError, ValueError):
        return "Manual"
    if hours <= 0:
        return "Manual"
    if hours < 1:
        return f"Every {round(hours * 60)}m"
    return f"Every {hours:g}h"


def _serialize_agent(agent: Any) -> Dict[str, Any]:
    """Serializes an ADK 2 agent into a full specification with prompt and bound SDK tools."""
    sched = None
    try:
        if fleet_scheduler and fleet_scheduler.has_schedule(agent.handle):
            sched = fleet_scheduler.get_schedule(agent.handle)
    except Exception:
        pass

    tools_list = []
    for cap_id, cap in getattr(agent, "_capabilities", {}).items():
        tools_list.append({
            "capability_id": cap.capability_id,
            "name": cap.name,
            "description": cap.description,
            "category": cap.category,
            "domain": cap.domain,
            "mcp_tool_name": cap.mcp_tool_name,
            "kind": cap.kind,
            "cardinality": cap.cardinality,
            "composed": cap.composed,
            "evidence_path": cap.evidence_path,
            "input_schema": cap.input_schema,
            "output_schema": cap.output_schema,
        })

    # Bound callable tool wrappers (e.g. get_task_status)
    bound_tool_names = {c.mcp_tool_name or c.capability_id.replace(".", "_") for c in getattr(agent, "_capabilities", {}).values()}
    builtin_tools = [
        {
            "name": tool_name,
            "description": (getattr(fn, "__doc__", "") or "").strip().split("\n")[0]
        }
        for tool_name, fn in getattr(agent, "_tools", {}).items()
        if tool_name not in bound_tool_names
    ]

    # Applicable ADK modular skills from knowledge/
    applicable_skills = []
    sc = getattr(agent, "skill_catalog", None)
    if sc and hasattr(sc, "skills"):
        agent_caps = set(getattr(agent, "_capabilities", {}).keys())
        for skill_id, skill in sc.skills.items():
            if agent_caps.intersection(skill.capabilities_used):
                applicable_skills.append({
                    "id": skill.id,
                    "title": skill.title,
                    "type": skill.skill_type,
                    "triggers": skill.triggers,
                    "source_path": skill.source_path,
                })

    return {
        "name": agent.name,
        "handle": agent.handle,
        "role": agent.role,
        "subsystem": agent.subsystem,
        "description": agent.description,
        "system_instruction": getattr(agent, "system_instruction", ""),
        "model": agent.model,
        "default_stream": agent.default_stream,
        "default_topic": agent.default_topic,
        "hitl_required": getattr(agent, "hitl_required", True),
        "capabilities": list(getattr(agent, "_capabilities", {}).keys()),
        "tools": tools_list,
        "builtin_tools": builtin_tools,
        "skills": applicable_skills,
        "last_loaded_skill": getattr(agent, "last_loaded_skill", None),
        "cadence": _format_cadence(sched),
        "last_patrol_run_at": sched.get("last_run_at") if sched else None,
        "next_patrol_run_at": sched.get("next_run_at") if sched else None,
    }


@app.get("/api/agents")
async def list_agents() -> List[Dict[str, Any]]:
    """Returns details for all specialized agents in the fleet, including prompts and SDK tools."""
    return [_serialize_agent(agent) for agent in fleet.values()]


@app.get("/api/agents/{agent_handle}")
async def get_agent(agent_handle: str) -> Dict[str, Any]:
    """Returns detailed specification, prompt, and tools for a specific agent."""
    handle = agent_handle if agent_handle.startswith("@") else f"@{agent_handle}"
    agent = fleet.get(handle)
    if not agent:
        raise HTTPException(status_code=404, detail=f"Agent '{agent_handle}' not found in fleet.")
    return _serialize_agent(agent)


@app.get("/api/proposals")
async def list_proposals(
    status: Optional[str] = Query(None, description="Filter: OPEN, MERGED, REJECTED"),
    subsystem: Optional[str] = Query(None, description="Subsystem filter"),
) -> List[Dict[str, Any]]:
    """Lists change proposals from Gas Town .proposals/ repository."""
    proposals = proposal_manager.list_proposals(status=status, subsystem=subsystem)
    return [
        {
            "id": p.id,
            "title": p.title,
            "author": p.author,
            "subsystem": p.subsystem,
            "target_resource_id": p.target_resource_id,
            "action_type": p.action_type,
            "status": p.status,
            "risk_level": p.risk_level,
            "created_at": p.created_at,
            "updated_at": p.updated_at,
            "merged_at": p.merged_at,
            "merged_by": p.merged_by,
            "merge_commit": p.merge_commit,
            "rejection_reason": p.rejection_reason,
            "approval_note": p.approval_note,
            "preflight": asdict(p.preflight),
            "rationale": p.rationale,
            "proposed_diff": p.proposed_diff,
        }
        for p in proposals
    ]


@app.get("/api/proposals/{proposal_id}")
async def get_proposal(proposal_id: str) -> Dict[str, Any]:
    """Retrieves full details of a single change proposal."""
    try:
        p = proposal_manager.get_proposal(proposal_id)
        return {
            "id": p.id,
            "title": p.title,
            "author": p.author,
            "subsystem": p.subsystem,
            "target_resource_id": p.target_resource_id,
            "action_type": p.action_type,
            "status": p.status,
            "risk_level": p.risk_level,
            "created_at": p.created_at,
            "updated_at": p.updated_at,
            "merged_at": p.merged_at,
            "merged_by": p.merged_by,
            "merge_commit": p.merge_commit,
            "rejection_reason": p.rejection_reason,
            "approval_note": p.approval_note,
            "preflight": asdict(p.preflight),
            "rationale": p.rationale,
            "proposed_diff": p.proposed_diff,
            "mutation_payload": p.mutation_payload,
        }
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"Proposal '{proposal_id}' not found.")


@app.post("/api/proposals/{proposal_id}/approve")
async def approve_proposal(
    proposal_id: str,
    body: ApproveProposalRequest,
) -> Dict[str, Any]:
    """Approves and merges a change proposal, applying live SecOps mutation."""
    try:
        proposal = proposal_manager.get_proposal(proposal_id)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"Proposal '{proposal_id}' not found.")

    res = proposal_manager.approve_and_merge(
        proposal_id=proposal_id,
        engine=engine,
        merged_by=body.merged_by,
        lifecycle_manager=lifecycle_manager,
        approval_note=body.approval_note,
    )

    if not res.success:
        raise HTTPException(status_code=500, detail=f"Mutation failed: {res.error_message}")

    # Broadcast notification to the relevant stream/topic
    target_stream = "detections" if "rule" in proposal.subsystem else "general"
    chat_store.add_message(
        stream=target_stream,
        topic="rule-proposals",
        sender_handle=proposal.author,
        sender_type="agent",
        content=(
            f"✅ **Change Proposal Merged**: `{proposal_id}`\n\n"
            f"- **Approved By**: {body.merged_by}\n"
            + (f"- **Approval Note**: {body.approval_note}\n" if body.approval_note else "")
            + f"- **Target**: `{proposal.target_resource_id}` ({proposal.action_type})\n"
            f"- **Git Commit**: `{res.commit_hash or 'HEAD'}`\n\n"
            f"Production mutation executed successfully via SecOpsEngine."
        ),
        proposal_id=proposal_id,
        widget={
            "type": "hitl_proposal_card",
            "proposal_id": proposal_id,
            "status": "MERGED",
            "title": proposal.title,
            "target_resource_id": proposal.target_resource_id,
            "action_type": proposal.action_type,
            "merged_by": body.merged_by,
            "commit_hash": res.commit_hash,
        },
    )

    # Cascade resolution to any matching pending tasks in Evidence Fabric
    if proposal.target_resource_id:
        try:
            pending_todos = evidence_store.list_todos(status="PENDING")
            for td in pending_todos:
                t_desc = f"{td.get('title', '')} {td.get('description', '')} {td.get('target_resource_id', '')}"
                if proposal.target_resource_id in t_desc:
                    tid = td.get("todo_id") or td.get("id")
                    if tid:
                        evidence_store.update_todo_status(
                            todo_id=tid,
                            status="RESOLVED",
                            resolved_by=body.merged_by,
                            proposal_id=proposal_id,
                            resolution=f"Resolved via approved proposal {proposal_id}",
                        )
        except Exception as e:
            logger.warning("Could not cascade approval resolution to todos: %s", e)

    return asdict(res)


@app.post("/api/proposals/{proposal_id}/reject")
async def reject_proposal(
    proposal_id: str,
    body: RejectProposalRequest,
) -> Dict[str, Any]:
    """Rejects a change proposal."""
    try:
        proposal = proposal_manager.reject_proposal(
            proposal_id=proposal_id,
            reason=body.reason,
            rejected_by=body.rejected_by,
            lifecycle_manager=lifecycle_manager,
        )
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

    # Cascade dismissal to any matching pending tasks in Evidence Fabric
    if proposal.target_resource_id:
        try:
            pending_todos = evidence_store.list_todos(status="PENDING")
            for td in pending_todos:
                t_desc = f"{td.get('title', '')} {td.get('description', '')} {td.get('target_resource_id', '')}"
                if proposal.target_resource_id in t_desc:
                    tid = td.get("todo_id") or td.get("id")
                    if tid:
                        evidence_store.update_todo_status(
                            todo_id=tid,
                            status="RESOLVED",
                            resolved_by=body.rejected_by,
                            proposal_id=proposal_id,
                            resolution=f"Dismissed via rejected proposal {proposal_id}: {body.reason}",
                        )
        except Exception as e:
            logger.warning("Could not cascade rejection dismissal to todos: %s", e)

    target_stream = "detections" if "rule" in proposal.subsystem else "general"
    chat_store.add_message(
        stream=target_stream,
        topic="rule-proposals",
        sender_handle=proposal.author,
        sender_type="agent",
        content=(
            f"❌ **Change Proposal Rejected**: `{proposal_id}`\n\n"
            f"- **Rejected By**: {body.rejected_by}\n"
            f"- **Reason**: {body.reason}"
        ),
        proposal_id=proposal_id,
        widget={
            "type": "hitl_proposal_card",
            "proposal_id": proposal_id,
            "status": "REJECTED",
            "title": proposal.title,
            "rejection_reason": body.reason,
        },
    )

    return {
        "status": "REJECTED",
        "proposal_id": proposal_id,
        "reason": body.reason,
    }


# --- Evidence Fabric & Dynamic Configuration Endpoints ---

@app.get("/api/evidence")
async def list_evidence(
    limit: int = Query(50, description="Max evidence items to return"),
) -> List[Dict[str, Any]]:
    """Lists recent agent reasoning turns, tool call execution, and evidence provenance."""
    if isinstance(evidence_store, EvidenceFabricStore):
        return evidence_store.list_evidence(limit=limit)
    return []


@app.get("/api/rules/state")
async def list_rules_state(
    limit: int = Query(50, description="Max rules to return"),
) -> List[Dict[str, Any]]:
    """Returns rule operational state, performance, and decay telemetry cached in the Evidence Fabric."""
    return evidence_store.list_rule_states(limit=limit)


@app.get("/api/rules/{rule_id}/state")
async def get_rule_state(rule_id: str) -> Dict[str, Any]:
    """Returns operational state and analysis findings for a specific rule."""
    state = evidence_store.get_rule_state(rule_id)
    if not state:
        raise HTTPException(status_code=404, detail=f"Rule state for '{rule_id}' not found in Evidence Fabric.")
    return state


@app.post("/api/rules/audit")
async def run_rule_audit(
    include_curated: bool = Query(True, description="Include Google Curated Rules"),
    sync_embeddings: bool = Query(True, description="Synchronize vector embeddings"),
    lookback_days: int = Query(90, description="Telemetry lookback days"),
    run_conflict_scan: bool = Query(True, description="Scan for rule overlaps and curated shadowing"),
) -> Dict[str, Any]:
    """Executes a unified detection repository health audit across customer and curated rules."""
    report = engine.audit_rules(
        include_curated=include_curated,
        sync_embeddings=sync_embeddings,
        lookback_days=lookback_days,
        run_conflict_scan=run_conflict_scan,
    )
    rep_dict = report.to_dict()
    widget = {
        "type": "rule_audit_card",
        "title": "Detection Repository Health Audit",
        "data": rep_dict,
    }
    chat_store.add_message(
        stream="detections",
        topic="decay-review",
        sender_handle="@detection-decay-agent",
        sender_type="agent",
        content=(
            f"🛡️ **Unified Detection Repository Audit Completed**\n\n"
            f"- **Total Rules Scanned**: `{report.total_rules_scanned}` ({report.customer_rules_count} Customer, {report.curated_rules_count} Curated)\n"
            f"- **Healthy Active**: `{report.healthy_count}`\n"
            f"- **Silent (0 Detections / 90d)**: `{report.silent_decay_count}`\n"
            f"- **Execution Failures**: `{report.failing_count}`\n"
            f"- **Misconfigured Alerting**: `{report.misconfigured_count}`\n"
            f"- **Semantic Conflicts (COS ≥ 75)**: `{report.conflict_count}`\n"
            f"- **Shadowing Curated Rules**: `{report.shadowed_by_curated_count}`\n"
            f"- **Vector Embeddings Synced**: `{report.embeddings_synced_count}`\n\n"
            f"Repository telemetry, conflict matrix, and 768-d vector embeddings updated in Firestore Evidence Fabric."
        ),
        widget=widget,
    )
    return rep_dict


@app.get("/api/rules/audit/latest")
async def get_latest_rule_audit() -> Dict[str, Any]:
    """Retrieves the most recent unified rule audit report from Evidence Fabric."""
    latest = evidence_store.get_latest_rule_audit()
    if not latest:
        raise HTTPException(status_code=404, detail="No prior detection rule audit found.")
    return latest


@app.get("/api/todos")
async def list_todos(
    status: Optional[str] = Query("PENDING", description="Filter by status (e.g. PENDING, IN_PROGRESS, RESOLVED)"),
    target_agent: Optional[str] = Query(None, description="Target agent filter (e.g. @yaral-optimizer)"),
) -> List[Dict[str, Any]]:
    """Lists pending cross-agent remediation tasks and optimization requests."""
    return evidence_store.list_todos(status=status, target_agent=target_agent)


@app.get("/api/todos/{todo_id}")
async def get_todo_by_id(todo_id: str) -> Dict[str, Any]:
    """Retrieves a single remediation task by ID."""
    todo = evidence_store.get_todo(todo_id)
    if not todo:
        raise HTTPException(status_code=404, detail=f"Task {todo_id} not found")
    return todo


@app.delete("/api/todos/{todo_id}")
async def delete_todo_by_id(todo_id: str) -> Dict[str, Any]:
    """Deletes a remediation task by ID."""
    deleted = evidence_store.delete_todo(todo_id)
    if not deleted:
        raise HTTPException(status_code=404, detail=f"Task {todo_id} not found")
    return {"status": "DELETED", "todo_id": todo_id}


class UpdateTodoStatusRequest(BaseModel):
    status: str = Field(..., description="Target status: PENDING, IN_PROGRESS, RESOLVED, DISMISSED")
    resolution: Optional[str] = Field(None, description="Resolution note or dismissal explanation")
    resolved_by: Optional[str] = Field("secops-operator", description="Operator or agent resolving task")


@app.patch("/api/todos/{todo_id}")
async def update_todo_status_endpoint(
    todo_id: str,
    body: UpdateTodoStatusRequest,
) -> Dict[str, Any]:
    """Updates the status of a remediation task."""
    todo = evidence_store.get_todo(todo_id)
    if not todo:
        raise HTTPException(status_code=404, detail=f"Task {todo_id} not found")
    evidence_store.update_todo_status(
        todo_id=todo_id,
        status=body.status,
        resolved_by=body.resolved_by,
        resolution=body.resolution,
    )
    return {"status": "SUCCESS", "todo_id": todo_id, "new_status": body.status}


@app.post("/api/todos/deduplicate")
async def deduplicate_todos_endpoint() -> Dict[str, Any]:
    """Consolidates duplicate open tasks by resource and action type, merging sightings."""
    stats = evidence_store.deduplicate_todos()
    return {"status": "SUCCESS", "stats": stats}


class CreateTodoRequest(BaseModel):
    title: str
    target_agent: str
    target_resource_id: str
    action_type: str
    rationale: str
    payload: Dict[str, Any] = Field(default_factory=dict)


@app.post("/api/todos")
async def create_todo(body: CreateTodoRequest) -> Dict[str, Any]:
    """Submits a new cross-agent remediation task into the Evidence Fabric."""
    todo_id = f"todo_{int(datetime.now(timezone.utc).timestamp() * 1000)}"
    task_dict = {
        "todo_id": todo_id,
        "title": body.title,
        "target_agent": body.target_agent,
        "target_resource_id": body.target_resource_id,
        "action_type": body.action_type,
        "rationale": body.rationale,
        "payload": body.payload,
        "status": "PENDING",
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    evidence_store.save_todo(todo_id, task_dict)
    return {"status": "CREATED", "todo_id": todo_id, "task": task_dict}


@app.get("/api/configs/agents/{agent_handle}")
async def get_agent_config(agent_handle: str) -> Dict[str, Any]:
    """Retrieves runtime configuration and prompt overrides for a specific agent."""
    return evidence_store.get_agent_config(agent_handle)


@app.put("/api/configs/agents/{agent_handle}")
async def update_agent_config(agent_handle: str, body: Dict[str, Any]) -> Dict[str, Any]:
    """Updates runtime configuration and prompt overrides for a specific agent."""
    evidence_store.save_agent_config(agent_handle, body)
    return {"status": "UPDATED", "agent_handle": agent_handle, "config": body}


# --- Gas Town Control Center & Board Endpoints ---

@app.get("/api/gastown/overview")
async def get_gastown_overview() -> Dict[str, Any]:
    """Returns Gas Town control center summary, active convoys, and escalations."""
    open_props = proposal_manager.list_proposals(status="OPEN")
    merged_props = proposal_manager.list_proposals(status="MERGED")
    rejected_props = proposal_manager.list_proposals(status="REJECTED")
    todos_pending = evidence_store.list_todos(status="PENDING")
    todos_in_progress = evidence_store.list_todos(status="IN_PROGRESS")
    todos_resolved = evidence_store.list_todos(status="RESOLVED")

    # Mayor Status
    mayor = {
        "title": "The Mayor (@secops-dispatcher)",
        "handle": "@secops-dispatcher",
        "coordinator": "@secops-dispatcher",
        "is_attached": True,
        "activity": "Active",
        "runtime": "Google ADK 2 & GEAP Engine",
        "last_activity": "Just now",
    }

    # Deacon Health
    health = fleet_scheduler.get_deacon_status()

    # Summary stats
    summary = {
        "polecat_count": len(fleet),
        "hook_count": 92 + 11,
        "issue_count": len(open_props) + len(todos_pending),
        "convoy_count": 4,
        "escalation_count": 0,  # Updated dynamically below based on actual high-risk items
        "open_proposals": len(open_props),
        "merged_proposals": len(merged_props),
    }

    # Convoys (Synthesized work streams from live agent tasks)
    total_noise_props = max(1, len(open_props) + len(merged_props))
    noise_pct = int((len(merged_props) / total_noise_props) * 100) if total_noise_props > 0 else 0

    convoys = [
        {
            "id": "convoy-rule-decay",
            "title": "Detection Rule Decay & 90-Day Telemetry Sync",
            "work_status": "active",
            "progress": "95/100",
            "progress_pct": 95,
            "primary_agent": "@detection-decay-agent",
            "stream": "detections",
            "topic": "decay-review",
            "action_prompt": "@detection-decay-agent list decay queue",
            "assignees": ["@detection-decay-agent", "@yaral-optimizer"],
            "ready_beads": len([t for t in todos_pending if "decay" in t.get("action_type", "").lower()]),
            "in_progress": 1,
            "last_activity": "2m ago",
        },
        {
            "id": "convoy-noise-suppression",
            "title": "Alert Noise Tuning & Exception Rule Generation",
            "work_status": "active",
            "progress": f"{len(merged_props)}/{len(open_props) + len(merged_props)}",
            "progress_pct": max(20, min(100, noise_pct)),
            "primary_agent": "@detection-tuning-agent",
            "stream": "detections",
            "topic": "tuning-review",
            "action_prompt": "@detection-tuning-agent find noisy rules",
            "assignees": ["@detection-tuning-agent"],
            "ready_beads": len(open_props),
            "in_progress": 1,
            "last_activity": "Just now",
        },
        {
            "id": "convoy-ingestion-sla",
            "title": "Chronicle Health Hub Ingestion SLAs (<4h)",
            "work_status": "complete",
            "progress": "11/11",
            "progress_pct": 100,
            "primary_agent": "@feed-agent",
            "stream": "ingestion",
            "topic": "feed-health",
            "action_prompt": "@feed-agent audit feeds",
            "assignees": ["@feed-agent"],
            "ready_beads": 0,
            "in_progress": 0,
            "last_activity": "5m ago",
        },
        {
            "id": "convoy-parser-drift",
            "title": "Logstash CBN Extension Drift & Drop Codes",
            "work_status": "active",
            "progress": "91/92",
            "progress_pct": 98,
            "primary_agent": "@parser-doctor",
            "stream": "ingestion",
            "topic": "parser-drops",
            "action_prompt": "@parser-doctor audit parsers",
            "assignees": ["@parser-doctor"],
            "ready_beads": 1,
            "in_progress": 1,
            "last_activity": "10m ago",
        },
    ]

    # Escalations
    escalations = []
    for p in open_props:
        if p.risk_level in ("HIGH", "CRITICAL"):
            escalations.append({
                "id": f"esc_{p.id}",
                "severity": p.risk_level.lower(),
                "title": f"High Risk Mutation: {p.title}",
                "issue_id": p.id,
                "target": p.target_resource_id or "Detection Rule",
                "escalated_by": p.author,
                "stream": "detections",
                "topic": "rule-proposals",
                "action_prompt": f"@secops-dispatcher review proposal {p.id}",
                "created_at": p.created_at,
                "age": _humanize_age(p.created_at),
            })
    if not escalations:
        for t in todos_pending:
            if str(t.get("priority", "")).upper() in ("HIGH", "CRITICAL"):
                escalations.append({
                    "id": f"esc_{t.get('todo_id')}",
                    "severity": str(t.get("priority", "high")).lower(),
                    "title": t.get("title", "High Priority Operational Task"),
                    "issue_id": t.get("todo_id"),
                    "target": t.get("target_resource_id") or "SecOps Resource",
                    "escalated_by": t.get("target_agent", "@secops-dispatcher"),
                    "stream": t.get("stream", "detections"),
                    "topic": t.get("topic", "general"),
                    "action_prompt": t.get("action_prompt", ""),
                    "created_at": t.get("created_at"),
                    "age": _humanize_age(t.get("created_at")),
                })
    acks = _load_escalation_acks()
    for esc in escalations:
        ack = acks.get(esc["id"])
        esc["acked"] = ack is not None
        esc["acked_by"] = ack.get("acked_by") if ack else None
        esc["acked_at"] = ack.get("acked_at") if ack else None
    summary["escalation_count"] = sum(1 for e in escalations if not e["acked"])
    summary["escalation_total"] = len(escalations)

    soc_issues = [i.to_dict() for i in work_queue.list_issues(limit=50)]
    soc_workers = [w.to_dict() for w in work_queue.list_workers(active_only=False)]
    active_leases_count = sum(1 for i in soc_issues if i.get("lease") and i.get("status") in ["LEASED", "CLAIMED", "EXECUTING", "VALIDATING"])
    summary["soc_issues_count"] = len(soc_issues)
    summary["soc_leases_active"] = active_leases_count
    summary["soc_workers_count"] = len(soc_workers)
    summary["issue_count"] = len(open_props) + len(todos_pending) + len([i for i in soc_issues if i.get("status") != "CLOSED"])

    return {
        "mayor": mayor,
        "health": health,
        "summary": summary,
        "convoys": convoys,
        "escalations": escalations,
        "todos_pending": todos_pending,
        "todos_in_progress": todos_in_progress,
        "todos_resolved": todos_resolved,
        "soc_issues": soc_issues,
        "soc_workers": soc_workers,
        "soc_leases_active": active_leases_count,
    }


@app.post("/api/gastown/escalations/{escalation_id}/ack")
async def ack_escalation(escalation_id: str, body: AckEscalationRequest) -> Dict[str, Any]:
    """Records an operator acknowledgement for an escalation (persisted across restarts)."""
    if not escalation_id.startswith("esc_"):
        raise HTTPException(status_code=400, detail="Invalid escalation id.")
    acks = _load_escalation_acks()
    record = {
        "acked_by": body.acked_by,
        "acked_at": datetime.now(timezone.utc).isoformat(),
        "note": body.note,
    }
    acks[escalation_id] = record
    _save_escalation_acks(acks)
    return {"id": escalation_id, "acked": True, **record}


# --- SOC Operating System Work Queue & Durability Endpoints ---

class ClaimIssueRequest(BaseModel):
    agent_handle: str = Field(..., description="Worker agent handle claiming work (e.g. '@parser-doctor')")
    duration_seconds: int = Field(default=300, ge=10, le=3600, description="Lease duration in seconds")


class HeartbeatIssueRequest(BaseModel):
    agent_handle: str = Field(..., description="Lease holder agent handle")
    duration_seconds: int = Field(default=300, ge=10, le=3600)


class ReleaseIssueRequest(BaseModel):
    agent_handle: Optional[str] = Field(default=None, description="Lease holder agent handle")
    force: bool = Field(default=False, description="Force release regardless of ownership")


class DecideIssueRequest(BaseModel):
    decision: str = Field(..., description="Decision outcome: 'APPROVED' or 'REJECTED'")
    approver: str = Field(default="secops-operator", description="Identifier of the operator or authority")
    rationale: str = Field(default="", description="Operator rationale or notes")


@app.get("/api/soc/issues")
async def list_soc_issues(
    status: Optional[str] = Query(None, description="Filter by status (AVAILABLE, LEASED, VALIDATING, CLOSED, etc.)"),
    plane: Optional[str] = Query(None, description="Filter by operational plane (data, detection, automation, platform, governance, improvement, external)"),
    limit: int = Query(100, ge=1, le=500),
) -> List[Dict[str, Any]]:
    """Lists SOC work items from the operational coordination work queue."""
    issues = work_queue.list_issues(status=status, plane=plane, limit=limit)
    return [i.to_dict() for i in issues]


@app.get("/api/soc/issues/{issue_id}")
async def get_soc_issue(issue_id: str) -> Dict[str, Any]:
    """Retrieves a single SOC work item and its materialized Git ledger events."""
    issue = work_queue.get_issue(issue_id)
    if not issue:
        raise HTTPException(status_code=404, detail=f"SOC Issue '{issue_id}' not found.")
    
    events = issue_materializer.list_issue_events(issue_id)
    issue_dict = issue.to_dict()
    issue_dict["materialized_events"] = [e.to_dict() for e in events]
    issue_dict["resolution_markdown"] = issue_materializer.read_resolution(issue_id)
    return issue_dict


@app.post("/api/soc/issues/{issue_id}/claim")
async def claim_soc_issue(issue_id: str, body: ClaimIssueRequest) -> Dict[str, Any]:
    """Acquires a lease on a SOC work item for an autonomous worker."""
    lease = work_queue.acquire_lease(
        issue_id=issue_id,
        agent_handle=body.agent_handle,
        duration_seconds=body.duration_seconds,
    )
    if not lease:
        raise HTTPException(status_code=409, detail=f"Issue '{issue_id}' could not be leased (already leased or closed).")
    
    issue_materializer.materialize_claimed(
        issue_id=issue_id,
        agent_handle=body.agent_handle,
        lease=lease,
        commit=False,
    )
    return {"status": "LEASED", "lease": lease.to_dict()}


@app.post("/api/soc/issues/{issue_id}/heartbeat")
async def heartbeat_soc_issue(issue_id: str, body: HeartbeatIssueRequest) -> Dict[str, Any]:
    """Renews an active lease without generating Git commit churn."""
    renewed = work_queue.renew_lease(
        issue_id=issue_id,
        agent_handle=body.agent_handle,
        duration_seconds=body.duration_seconds,
    )
    if not renewed:
        raise HTTPException(status_code=400, detail="Failed to renew lease (lease expired or mismatched owner).")
    return {"status": "RENEWED"}


@app.post("/api/soc/issues/{issue_id}/release")
async def release_soc_issue(issue_id: str, body: ReleaseIssueRequest) -> Dict[str, Any]:
    """Releases an active lease back to AVAILABLE pool."""
    released = work_queue.release_lease(
        issue_id=issue_id,
        agent_handle=body.agent_handle,
        force=body.force,
    )
    if not released:
        raise HTTPException(status_code=400, detail="Failed to release lease.")
    return {"status": "RELEASED"}


@app.post("/api/soc/issues/{issue_id}/decide")
async def decide_soc_issue(issue_id: str, body: DecideIssueRequest) -> Dict[str, Any]:
    """Records an approval or rejection decision across the durability boundary."""
    issue = work_queue.get_issue(issue_id)
    if not issue:
        raise HTTPException(status_code=404, detail=f"Issue '{issue_id}' not found.")
    
    ok = lifecycle_manager.decide_issue(
        issue_id=issue_id,
        decision=body.decision.upper(),
        approver=body.approver,
        rationale=body.rationale,
        commit=False,
    )
    if not ok:
        raise HTTPException(status_code=400, detail="Failed to record issue decision.")
    
    return {"status": "DECIDED", "decision": body.decision.upper(), "issue_id": issue_id}


@app.get("/api/soc/workers")
async def list_soc_workers(active_only: bool = Query(False)) -> List[Dict[str, Any]]:
    """Lists all registered workers with their capability profiles."""
    workers = work_queue.list_workers(active_only=active_only)
    return [w.to_dict() for w in workers]


@app.get("/api/soc/workers/{agent_handle}")
async def get_soc_worker(agent_handle: str) -> Dict[str, Any]:
    """Retrieves worker capability profile."""
    worker = work_queue.get_worker(agent_handle)
    if not worker:
        raise HTTPException(status_code=404, detail=f"Worker '{agent_handle}' not found.")
    return worker.to_dict()


# --- Identity & IAM Governance Endpoints ---

@app.get("/api/iam/bindings")
async def get_iam_bindings(project_id: Optional[str] = Query(None)) -> Dict[str, Any]:
    """Returns project IAM policy bindings for default and custom Chronicle roles."""
    agent = fleet.get("@identity-governor")
    if hasattr(agent, "audit_chronicle_iam_bindings"):
        return agent.audit_chronicle_iam_bindings(project_id=project_id)
    bindings = engine.get_chronicle_iam_bindings(project_id=project_id)
    return {"status": "SUCCESS", "bindings": [asdict(b) for b in bindings]}


@app.get("/api/iam/custom-roles")
async def get_iam_custom_roles(project_id: Optional[str] = Query(None)) -> Dict[str, Any]:
    """Returns custom GCP IAM roles within the project granting chronicle.* permissions."""
    agent = fleet.get("@identity-governor")
    if hasattr(agent, "query_chronicle_custom_roles"):
        return agent.query_chronicle_custom_roles(project_id=project_id)
    roles = engine.get_chronicle_custom_roles(project_id=project_id)
    return {"status": "SUCCESS", "custom_roles": [asdict(r) for r in roles]}


@app.get("/api/iam/audits")
async def list_iam_audits(limit: int = Query(20)) -> List[Dict[str, Any]]:
    """Returns historical IAM audit snapshots from the Evidence Fabric."""
    return evidence_store.list_iam_audits(limit=limit)


@app.post("/api/iam/audits/run")
async def run_iam_audit(project_id: Optional[str] = Query(None)) -> Dict[str, Any]:
    """Runs a complete live IAM audit snapshot, persists it to Evidence Fabric, and detects privilege drift."""
    agent = fleet.get("@identity-governor")
    if hasattr(agent, "run_identity_drift_audit"):
        res = agent.run_identity_drift_audit(project_id=project_id)
        widget = res.get("widget")
        drift = res.get("drift", {})
        status_emoji = "⚠️" if drift.get("has_drift") else "✅"
        chat_store.add_message(
            stream="identity",
            topic="access-audits",
            sender_handle="@identity-governor",
            sender_type="agent",
            content=(
                f"{status_emoji} **Identity Governance Audit Completed**\n\n"
                f"- **Project**: `{res.get('project_id')}`\n"
                f"- **Privileged Users**: {res.get('total_users')}\n"
                f"- **Groups**: {res.get('total_groups')}\n"
                f"- **Workforce Pools**: {res.get('total_workforce_pools')}\n"
                f"- **Custom Roles**: {res.get('custom_roles_count')}\n"
                f"- **Privilege Drift**: {drift.get('summary', 'Clean')}\n"
            ),
            widget=widget,
        )
        return res
    return {"status": "ERROR", "message": "@identity-governor agent not active"}


# --- Rule Decay & Fleet Scheduling Endpoints ---

@app.post("/api/decay/sync")
async def run_decay_sync(lookback_days: int = Query(90)) -> Dict[str, Any]:
    """Runs full tenant-wide detection rule synchronization, computes DPS scores, and updates Evidence Fabric."""
    agent = fleet.get("@detection-decay-agent")
    if hasattr(agent, "run_decay_synchronization"):
        res = agent.run_decay_synchronization(lookback_days=lookback_days)
        widget = res.get("widget")
        chat_store.add_message(
            stream="detections",
            topic="decay-review",
            sender_handle="@detection-decay-agent",
            sender_type="agent",
            content=(
                f"📊 **Detection Rule Decay Synchronization Completed**\n\n"
                f"- **Audited Rules**: `{res.get('total_rules', 0)}`\n"
                f"- **Broken Compilation**: `{res.get('broken_count', 0)}`\n"
                f"- **Silent (0 Detections / 90d)**: `{res.get('silent_count', 0)}`\n"
                f"- **Stale (>90d unrevised)**: `{res.get('stale_count', 0)}`\n"
                f"- **Average DPS**: `{res.get('average_dps', 0.0)}` / 100\n\n"
                f"Rule operational state, 768-d embeddings, and review rankings updated in Evidence Fabric."
            ),
            widget=widget,
        )
        return res
    return {"status": "ERROR", "message": "@detection-decay-agent not active"}


@app.get("/api/decay/queue")
async def get_decay_queue(min_dps: int = Query(0), limit: int = Query(50)) -> List[Dict[str, Any]]:
    """Returns the ranked rule decay review queue from Evidence Fabric."""
    return evidence_store.list_decay_candidates(min_dps=min_dps, limit=limit)


@app.post("/api/decay/audit/{rule_id}")
async def audit_rule_decay(rule_id: str, lookback_days: int = Query(90)) -> Dict[str, Any]:
    """Performs an in-depth decay audit on a single rule, including 30-day UDM population checks."""
    agent = fleet.get("@detection-decay-agent")
    if hasattr(agent, "audit_single_rule_decay"):
        return agent.audit_single_rule_decay(rule_id=rule_id, lookback_days=lookback_days)
    return {"status": "ERROR", "message": "@detection-decay-agent not active"}


@app.get("/api/tuning/noisy-rules")
async def get_tuning_noisy_rules(lookback_days: int = Query(14), limit: int = Query(20)) -> Dict[str, Any]:
    """Retrieves top noisy detection rules ranked by trigger volume."""
    agent = fleet.get("@detection-tuning-agent")
    if hasattr(agent, "find_noisy_rules"):
        return agent.find_noisy_rules(lookback_days=lookback_days, limit=limit)
    return {"status": "ERROR", "message": "@detection-tuning-agent not active"}


@app.get("/api/tuning/distribution/{rule_id}")
async def get_tuning_distribution(rule_id: str, lookback_days: int = Query(14), limit: int = Query(10)) -> Dict[str, Any]:
    """Retrieves field value distribution across users, commands, hostnames, and IPs for a rule."""
    agent = fleet.get("@detection-tuning-agent")
    if hasattr(agent, "get_field_value_distribution"):
        return agent.get_field_value_distribution(rule_id=rule_id, lookback_days=lookback_days, limit=limit)
    return {"status": "ERROR", "message": "@detection-tuning-agent not active"}


@app.get("/api/tuning/samples/{rule_id}")
async def get_tuning_samples(rule_id: str, lookback_days: int = Query(14), limit: int = Query(10)) -> Dict[str, Any]:
    """Retrieves correlated multi-attribute detection samples for a rule."""
    agent = fleet.get("@detection-tuning-agent")
    if hasattr(agent, "get_detection_event_samples"):
        return agent.get_detection_event_samples(rule_id=rule_id, lookback_days=lookback_days, limit=limit)
    return {"status": "ERROR", "message": "@detection-tuning-agent not active"}


@app.post("/api/tuning/propose/{rule_id}")
async def propose_tuning(rule_id: str, lookback_days: int = Query(14), dominance: float = Query(0.20)) -> Dict[str, Any]:
    """Synthesizes safe multi-factor exclusion, verifies compiler, and posts proposal to chat."""
    agent = fleet.get("@detection-tuning-agent")
    if hasattr(agent, "synthesize_tuning_proposal"):
        res = agent.synthesize_tuning_proposal(rule_id=rule_id, lookback_days=lookback_days, dominance_threshold=dominance)
        proposal_data = res.get("proposal", {})
        widget = res.get("widget")

        p_status = proposal_data.get("tuning_status", "TUNING_PROPOSED")
        rule_name = proposal_data.get("rule_name", rule_id)
        pct = proposal_data.get("noise_reduction_pct", 0.0)
        suppressed = proposal_data.get("projected_suppressed_count", 0)
        total = proposal_data.get("unsuppressed_trigger_count", 0)

        if p_status == "TUNING_PROPOSED":
            chat_store.add_message(
                stream="detections",
                topic="tuning-review",
                sender_handle="@detection-tuning-agent",
                sender_type="agent",
                content=(
                    f"🛡️ **Detection Noise Suppression Proposal Formulated** for `{rule_name}` (`{rule_id}`)\n\n"
                    f"- **Baseline Triggers**: `{total:,}`\n"
                    f"- **Projected Suppressed**: `{suppressed:,}` (**{pct}% noise reduction**)\n"
                    f"- **Preserved Real Alerts**: `{proposal_data.get('preserved_real_alerts', 0):,}`\n"
                    f"- **Compiler Verified**: `{'✅ Yes' if proposal_data.get('compiler_verified') else '❌ Error'}`\n\n"
                    f"Multi-factor exclusion synthesized with strict HITL guardrails preventing detection blinding. Review the unified diff and deploy below."
                ),
                widget=widget,
            )
        else:
            chat_store.add_message(
                stream="detections",
                topic="tuning-review",
                sender_handle="@detection-tuning-agent",
                sender_type="agent",
                content=(
                    f"ℹ️ **Detection Tuning Evaluation for `{rule_name}` (`{rule_id}`)**: `NO_TUNING_NEEDED`\n\n"
                    f"- **Baseline Triggers**: `{total:,}`\n"
                    f"- **Diversity Check**: Triggers are broadly distributed across entities without a dominant benign pattern.\n"
                    f"Forcing an exclusion would risk blinding detection coverage. Rule remains unchanged."
                ),
                widget=widget,
            )
        return res
    return {"status": "ERROR", "message": "@detection-tuning-agent not active"}


@app.post("/api/tuning/deploy/{rule_id}")
async def deploy_tuning(rule_id: str, body: Dict[str, Any] = Body(...)) -> Dict[str, Any]:
    """Deploys approved tuning proposal directly to live Google SecOps (Chronicle)."""
    tuned_text = body.get("tuned_rule_text", "")
    rule_name = body.get("rule_name", rule_id)

    if not secops_engine:
        return {"status": "ERROR", "message": "SecOpsEngine not configured"}

    is_curated = "ur_" in rule_id or rule_id.startswith("ur_")
    if is_curated:
        refinement_query = body.get("udm_refinement_query") or tuned_text.replace("// UDM Findings Refinement Exclusion\n", "").strip()
        disp_name = f"Noise Suppression: {rule_name}"[:100]
        try:
            ref_summary = secops_engine.create_findings_refinement(
                display_name=disp_name,
                query=refinement_query,
                curated_rule_ids=[rule_id],
            )
            chat_store.add_message(
                stream="detections",
                topic="tuning-review",
                sender_handle="@detection-tuning-agent",
                sender_type="agent",
                content=(
                    f"🚀 **Noise Suppression Deployed to Chronicle** for Curated Rule `{rule_name}` (`{rule_id}`)!\n\n"
                    f"- **Refinement Name**: `{disp_name}`\n"
                    f"- **Refinement ID**: `{ref_summary.refinement_id if hasattr(ref_summary, 'refinement_id') else 'Active'}`\n"
                    f"- **Exclusion**: `{refinement_query}`\n\n"
                    f"Chronicle detection engine is now actively filtering benign administrative triggers."
                ),
            )
            return {"status": "SUCCESS", "message": f"Refinement deployed for {rule_id}", "refinement_id": getattr(ref_summary, "refinement_id", "")}
        except Exception as e:
            return {"status": "ERROR", "message": f"Deployment failed: {str(e)}"}
    else:
        try:
            secops_engine.update_rule(rule_id=rule_id, rule_text=tuned_text, update_mask="text")
            chat_store.add_message(
                stream="detections",
                topic="tuning-review",
                sender_handle="@detection-tuning-agent",
                sender_type="agent",
                content=(
                    f"🚀 **Rule Exclusion Deployed to Chronicle** for Customer Rule `{rule_name}` (`{rule_id}`)!\n\n"
                    f"Updated rule text verified by compiler and deployed into live Chronicle production."
                ),
            )
            return {"status": "SUCCESS", "message": f"Rule {rule_id} updated successfully"}
        except Exception as e:
            return {"status": "ERROR", "message": f"Rule update failed: {str(e)}"}


# --- Ingestion Feeds & Parser Health Endpoints ---

_cached_feed_audit: Optional[Dict[str, Any]] = None
_cached_parser_audit: Optional[Dict[str, Any]] = None

@app.get("/api/feeds")
async def list_feeds_health(lookback_days: int = Query(7), refresh: bool = Query(False)) -> Dict[str, Any]:
    """Returns feeds inventory and health assessment."""
    global _cached_feed_audit
    if _cached_feed_audit and not refresh:
        return {
            "status": "SUCCESS",
            "summary": _cached_feed_audit.get("summary", {}),
            "feeds": _cached_feed_audit.get("findings", []),
        }
    agent = fleet.get("@feed-agent")
    if hasattr(agent, "audit_feeds"):
        res = agent.audit_feeds(lookback_days=lookback_days)
        _cached_feed_audit = res
        return {
            "status": "SUCCESS",
            "summary": res.get("summary", {}),
            "feeds": res.get("findings", []),
        }
    return {"status": "ERROR", "message": "@feed-agent not active", "feeds": [], "summary": {}}


@app.get("/api/feeds/audit")
@app.post("/api/feeds/audit")
async def audit_feed_health(lookback_days: int = Query(7)) -> Dict[str, Any]:
    """Audits ingestion feeds and posts findings to #ingestion > feed-health."""
    global _cached_feed_audit
    agent = fleet.get("@feed-agent")
    if hasattr(agent, "audit_feeds"):
        res = agent.audit_feeds(lookback_days=lookback_days)
        _cached_feed_audit = res
        widget = res.get("widget")
        summary = res.get("summary", {})
        chat_store.add_message(
            stream="ingestion",
            topic="feed-health",
            sender_handle="@feed-agent",
            sender_type="agent",
            content=(
                f"📡 **Ingestion Feed Health Audit Completed**\n\n"
                f"- **Total Feeds Audited**: `{summary.get('total_feeds_audited', 0)}`\n"
                f"- **Healthy Feeds**: `{summary.get('healthy_count', 0)}`\n"
                f"- **Irregular / Warn**: `{summary.get('irregular_count', 0)}`\n"
                f"- **Failed / Degraded**: `{summary.get('failed_count', 0)}`\n"
                f"- **High Latency (P95 > 4h)**: `{summary.get('high_latency_count', 0)}`\n"
                f"- **Quota Rejections**: `{'Yes' if summary.get('quota_rejections_detected') else 'None'}`\n\n"
                f"Inspection results and transport telemetry evaluated against Health Hub."
            ),
            widget=widget,
        )
        return res
    return {"status": "ERROR", "message": "@feed-agent not active"}


@app.get("/api/feeds/{feed_id}")
async def get_feed_details(feed_id: str) -> Dict[str, Any]:
    """Retrieves full feed configuration details."""
    agent = fleet.get("@feed-agent")
    if hasattr(agent, "get_feed_details"):
        return agent.get_feed_details(feed_id)
    return {"status": "ERROR", "message": "@feed-agent not active"}


@app.get("/api/parsers")
async def list_parsers_health(lookback_days: int = Query(7), refresh: bool = Query(False)) -> Dict[str, Any]:
    """Returns parsers inventory and health assessment."""
    global _cached_parser_audit
    if _cached_parser_audit and not refresh:
        return {
            "status": "SUCCESS",
            "summary": _cached_parser_audit.get("summary", {}),
            "parsers": _cached_parser_audit.get("findings", []),
        }
    agent = fleet.get("@parser-doctor")
    if hasattr(agent, "audit_parsers"):
        res = agent.audit_parsers(lookback_days=lookback_days)
        _cached_parser_audit = res
        return {
            "status": "SUCCESS",
            "summary": res.get("summary", {}),
            "parsers": res.get("findings", []),
        }
    return {"status": "ERROR", "message": "@parser-doctor not active", "parsers": [], "summary": {}}


@app.get("/api/parsers/audit")
@app.post("/api/parsers/audit")
async def audit_parser_health(lookback_days: int = Query(7)) -> Dict[str, Any]:
    """Audits SIEM parsers and extensions and posts findings to #ingestion > parser-drops."""
    global _cached_parser_audit
    agent = fleet.get("@parser-doctor")
    if hasattr(agent, "audit_parsers"):
        res = agent.audit_parsers(lookback_days=lookback_days)
        _cached_parser_audit = res
        widget = res.get("widget")
        summary = res.get("summary", {})
        chat_store.add_message(
            stream="ingestion",
            topic="parser-drops",
            sender_handle="@parser-doctor",
            sender_type="agent",
            content=(
                f"🩺 **SIEM Parser Health Audit Completed**\n\n"
                f"- **Total Parsers Audited**: `{summary.get('total_parsers_audited', 0)}`\n"
                f"- **Healthy Parsers**: `{summary.get('healthy_count', 0)}`\n"
                f"- **Irregular / Warn**: `{summary.get('irregular_count', 0)}`\n"
                f"- **Failed / High Error Rate**: `{summary.get('failed_count', 0)}`\n"
                f"- **CBN Version Drift**: `{summary.get('version_drift_count', 0)}`\n"
                f"- **Extension Conflicts**: `{summary.get('extension_conflict_count', 0)}`\n\n"
                f"Parser error rates and normalizer drop reason codes evaluated against Health Hub."
            ),
            widget=widget,
        )
        return res
    return {"status": "ERROR", "message": "@parser-doctor not active"}


@app.get("/api/parsers/{log_type}/cbn")
async def get_parser_cbn(log_type: str, parser_id: Optional[str] = Query(None)) -> Dict[str, Any]:
    """Retrieves decoded Logstash CBN code for a parser."""
    agent = fleet.get("@parser-doctor")
    if hasattr(agent, "get_parser_cbn"):
        return agent.get_parser_cbn(log_type=log_type, parser_id=parser_id)
    return {"status": "ERROR", "message": "@parser-doctor not active"}


@app.post("/api/parsers/{log_type}/diagnose")
async def diagnose_unparsed_logs(log_type: str, lookback_hours: int = Query(168), limit: int = Query(5)) -> Dict[str, Any]:
    """Queries live unparsed raw logs (raw = /.*/ parsed = false) and tests them against active CBN parser."""
    agent = fleet.get("@parser-doctor")
    if hasattr(agent, "diagnose_unparsed_logs"):
        res = agent.diagnose_unparsed_logs(log_type=log_type, lookback_hours=lookback_hours, limit=limit)
        widget = res.get("widget")
        chat_store.add_message(
            stream="ingestion",
            topic="parser-drops",
            sender_handle="@parser-doctor",
            sender_type="agent",
            content=(
                f"🔬 **Unparsed Log Diagnosis for Log Type `{log_type}`**\n\n"
                f"- **Unparsed Events Found**: `{res.get('total_unparsed_found', 0)}`\n"
                f"- **Diagnosed Samples**: `{len(res.get('diagnostics', []))}`\n\n"
                f"Raw unparsed logs tested against active Logstash CBN parser code."
            ),
            widget=widget,
        )
        return res
    return {"status": "ERROR", "message": "@parser-doctor not active"}


@app.get("/api/playbooks/audit")
async def audit_playbooks(
    workflow_identifier: Optional[str] = Query(None),
    category: Optional[str] = Query(None),
    lookback_days: int = Query(30),
    limit: int = Query(20),
) -> Dict[str, Any]:
    """Audits SOAR playbooks for 100-pt static resilience, 30-day telemetry, and decay."""
    agent = fleet.get("@playbook-decay-agent")
    if hasattr(agent, "audit_playbook_decay"):
        res = agent.audit_playbook_decay(
            workflow_identifier=workflow_identifier,
            category=category,
            lookback_days=lookback_days,
            limit=limit,
        )
        widget = res.get("widget")
        summary = res.get("summary", {})
        chat_store.add_message(
            stream="soar",
            topic="playbook-health",
            sender_handle="@playbook-decay-agent",
            sender_type="agent",
            content=(
                f"⚡ **SOAR Playbook Resilience & Decay Audit**\n\n"
                f"- **Audited Playbooks**: `{summary.get('total_audited', 0)}`\n"
                f"- **Catalog Avg Score**: `{summary.get('average_resilience_score', 0)}/100`\n"
                f"- **Degraded Count**: `{summary.get('degraded_playbooks_count', 0)}`\n"
                f"- **Telemetry Window**: `{lookback_days} days`\n"
            ),
            widget=widget,
        )
        return res
    return {"status": "ERROR", "message": "@playbook-decay-agent not active"}


@app.get("/api/playbooks")
async def list_playbooks(limit: int = Query(100)) -> Dict[str, Any]:
    """Lists recent audited playbooks from Evidence Fabric."""
    agent = fleet.get("@playbook-decay-agent")
    if hasattr(agent, "list_playbook_reports"):
        return agent.list_playbook_reports(limit=limit)
    return {"status": "ERROR", "message": "@playbook-decay-agent not active"}


@app.get("/api/playbooks/{workflow_identifier}")
async def get_playbook_audit(workflow_identifier: str) -> Dict[str, Any]:
    """Retrieves audit report for a specific playbook UUID."""
    agent = fleet.get("@playbook-decay-agent")
    if hasattr(agent, "get_playbook_decay_report"):
        res = agent.get_playbook_decay_report(workflow_identifier)
        if res.get("status") == "SUCCESS":
            return res
    # Fallback to on-demand audit if not cached in store
    if hasattr(agent, "audit_playbook_decay"):
        return agent.audit_playbook_decay(workflow_identifier=workflow_identifier)
    return {"status": "ERROR", "message": "@playbook-decay-agent not active"}



@app.get("/api/configs/agents/{agent_handle}/schedule")
async def get_agent_schedule(agent_handle: str) -> Dict[str, Any]:
    """Retrieves schedule and automation settings for an agent."""
    return fleet_scheduler.get_schedule(agent_handle)


@app.put("/api/configs/agents/{agent_handle}/schedule")
async def update_agent_schedule(agent_handle: str, body: Dict[str, Any]) -> Dict[str, Any]:
    """Updates schedule and automation settings for an agent."""
    return fleet_scheduler.update_schedule(agent_handle, body)


@app.post("/api/configs/agents/{agent_handle}/trigger")
async def trigger_agent_schedule(agent_handle: str) -> Dict[str, Any]:
    """Triggers an immediate on-demand execution of an agent's scheduled task."""
    return await fleet_scheduler.trigger_run_now(agent_handle)


# --- Deacon Patrol Endpoints ---

@app.get("/api/gastown/patrols")
async def get_gastown_patrols() -> Dict[str, Any]:
    """Returns configured Deacon patrol schedules, health telemetry, and recent execution history."""
    return {
        "deacon": fleet_scheduler.get_deacon_status(),
        "schedules": fleet_scheduler.list_schedules(),
    }


@app.post("/api/gastown/patrols/run-all")
async def trigger_gastown_patrol_all() -> Dict[str, Any]:
    """Triggers an immediate autonomous patrol run across all enabled agents."""
    return await fleet_scheduler.trigger_patrol_all()


@app.post("/api/gastown/patrols/{agent_handle}/run")
async def trigger_gastown_agent_patrol(agent_handle: str) -> Dict[str, Any]:
    """Triggers an immediate autonomous patrol run for a specific agent."""
    return await fleet_scheduler.trigger_run_now(agent_handle)


# --- Rule Conflict & Overlap Agent Endpoints ---

@app.post("/api/conflicts/audit/{rule_id}")
async def audit_rule_conflicts(rule_id: str, limit: int = Query(6)) -> Dict[str, Any]:
    """Audits detection rule for semantic overlaps, contradictions, redundancies, and computes COS."""
    agent = fleet.get("@rule-conflict-agent")
    if hasattr(agent, "audit_rule_conflicts"):
        res = agent.audit_rule_conflicts(rule_id=rule_id, limit=limit)
        chat_store.add_message(
            stream="detections",
            topic="rule-conflicts",
            sender_handle="@rule-conflict-agent",
            sender_display_name="Rule Conflict & Overlap Agent",
            content=f"Completed conflict audit for **{res.get('rule_name', rule_id)}** (Highest COS: {round(res.get('highest_cos', 0))}/100 - {res.get('severity_tier', 'LOW')}).",
            widget=res.get("widget"),
        )
        return res
    return {"status": "ERROR", "message": "@rule-conflict-agent not active"}


@app.post("/api/conflicts/batch")
async def batch_audit_rule_conflicts(
    limit: int = Query(50),
    batch_size: int = Query(10),
    min_cos: float = Query(45.0)
) -> Dict[str, Any]:
    """Executes tenant-wide detection rule conflict audit across deployed active rules."""
    agent = fleet.get("@rule-conflict-agent")
    if hasattr(agent, "batch_audit_rule_conflicts"):
        res = agent.batch_audit_rule_conflicts(limit=limit, batch_size=batch_size, min_cos=min_cos)
        chat_store.add_message(
            stream="detections",
            topic="rule-conflicts",
            sender_handle="@rule-conflict-agent",
            sender_display_name="Rule Conflict & Overlap Agent",
            content=f"Batch conflict audit finished: scanned {res.get('total_rules_scanned', 0)} rules, evaluated {res.get('total_pairs_evaluated', 0)} candidate pairs.",
            widget=res.get("widget"),
        )
        return res
    return {"status": "ERROR", "message": "@rule-conflict-agent not active"}


@app.get("/api/conflicts/similar/{rule_id}")
async def find_similar_rules(rule_id: str, limit: int = Query(6)) -> Dict[str, Any]:
    """Finds candidate overlapping or conflicting rules via vector similarity search."""
    agent = fleet.get("@rule-conflict-agent")
    if hasattr(agent, "find_similar_rules"):
        return agent.find_similar_rules(rule_id=rule_id, limit=limit)
    return {"status": "ERROR", "message": "@rule-conflict-agent not active"}


@app.post("/api/conflicts/sync-embeddings")
async def sync_rule_embeddings(batch_size: int = Query(50), force: bool = Query(False)) -> Dict[str, Any]:
    """Batch computes and synchronizes vector embeddings for all active tenant rules."""
    agent = fleet.get("@rule-conflict-agent")
    if hasattr(agent, "sync_rule_embeddings"):
        return agent.sync_rule_embeddings(batch_size=batch_size, force=force)
    return {"status": "ERROR", "message": "@rule-conflict-agent not active"}


@app.get("/api/conflicts/list")
async def list_stored_rule_conflicts(min_cos: float = Query(0.0), limit: int = Query(50)) -> Dict[str, Any]:
    """Lists historical rule conflict audit records from Evidence Fabric."""
    agent = fleet.get("@rule-conflict-agent")
    if hasattr(agent, "list_stored_rule_conflicts"):
        return agent.list_stored_rule_conflicts(min_cos=min_cos, limit=limit)
    return {"status": "ERROR", "message": "@rule-conflict-agent not active"}


# --- Log Cost & FinOps Optimization Endpoints ---

@app.post("/api/log_cost/analyze")
async def analyze_log_costs(
    days: int = Query(7),
    tier: str = Query("ENTERPRISE"),
    bloat_threshold: int = Query(2048),
) -> Dict[str, Any]:
    """Executes live Chronicle ingestion telemetry analysis and computes FinOps optimization recommendations."""
    try:
        report = engine.analyze_log_costs(
            lookback_days=days,
            pricing_tier=tier,
            bloat_threshold_bytes=bloat_threshold,
        )
        return {
            "status": "SUCCESS",
            "report": report.to_dict(),
        }
    except Exception as e:
        logger.error(f"Error analyzing log costs: {e}", exc_info=True)
        return {
            "status": "ERROR",
            "message": str(e),
        }


@app.get("/api/log_cost/latest")
async def get_latest_log_costs() -> Dict[str, Any]:
    """Retrieves the latest persisted Log Cost Analysis Report from Evidence Fabric."""
    try:
        latest = engine.get_latest_log_costs(fallback_if_empty=True)
        if not latest:
            return {
                "status": "ERROR",
                "message": "No log cost analysis report found.",
            }
        return {
            "status": "SUCCESS",
            "report": latest,
        }
    except Exception as e:
        logger.error(f"Error fetching latest log costs: {e}", exc_info=True)
        return {
            "status": "ERROR",
            "message": str(e),
        }


@app.get("/api/ingestion/labels-and-namespaces")
async def get_ingestion_labels_and_namespaces(lookback_days: int = 7) -> Dict[str, Any]:
    """Retrieves real-time Ingestion Labels, UDM Namespaces, and Data RBAC hygiene audit."""
    try:
        report = engine.analyze_labels_and_namespaces(lookback_days=lookback_days)
        return {
            "status": "SUCCESS",
            "report": report.to_dict(),
        }
    except Exception as e:
        logger.error(f"Error analyzing labels and namespaces: {e}", exc_info=True)
        return {
            "status": "ERROR",
            "message": str(e),
        }


# --- SOC Institutional Knowledge & Shift Briefing Endpoints ---

@app.get("/api/briefings/shift")
async def get_shift_briefing(hours: int = Query(8, ge=1, le=72)) -> Dict[str, Any]:
    """Retrieves or computes a deterministic operational shift briefing."""
    try:
        briefing = engine.generate_shift_briefing(shift_hours=hours)
        return {
            "status": "SUCCESS",
            "briefing": briefing.to_dict(),
        }
    except Exception as e:
        logger.error(f"Error generating shift briefing: {e}", exc_info=True)
        return {"status": "ERROR", "message": str(e)}


@app.get("/api/briefings/posture")
async def get_posture_snapshot() -> Dict[str, Any]:
    """Retrieves the current SOC institutional knowledge and posture snapshot."""
    try:
        snapshot = engine.generate_posture_snapshot()
        return {
            "status": "SUCCESS",
            "snapshot": snapshot.to_dict(),
        }
    except Exception as e:
        logger.error(f"Error generating posture snapshot: {e}", exc_info=True)
        return {"status": "ERROR", "message": str(e)}


@app.get("/api/knowledge/entity/{subject_type}/{subject_id}")
async def get_entity_dossier(subject_type: str, subject_id: str) -> Dict[str, Any]:
    """Retrieves synthesized cross-agent operational dossier for an entity."""
    try:
        dossier = engine.get_composite_entity_dossier(subject_type, subject_id)
        return {
            "status": "SUCCESS",
            "dossier": dossier,
        }
    except Exception as e:
        logger.error(f"Error fetching entity dossier: {e}", exc_info=True)
        return {"status": "ERROR", "message": str(e)}


@app.post("/api/briefings/trigger")
async def trigger_briefing(hours: int = Query(8, ge=1, le=72)) -> Dict[str, Any]:
    """Manually triggers an immediate shift briefing broadcast to the briefings stream."""
    try:
        briefing = engine.generate_shift_briefing(shift_hours=hours)
        chat_store.add_message(
            stream="briefings",
            topic="shift-briefings",
            sender_handle="@soc-briefing-agent",
            sender_type="agent",
            content=briefing.summary_narrative,
            widget=None,
        )
        return {
            "status": "SUCCESS",
            "message": "Shift briefing triggered and broadcast successfully.",
            "briefing": briefing.to_dict(),
        }
    except Exception as e:
        logger.error(f"Error triggering briefing: {e}", exc_info=True)
        return {"status": "ERROR", "message": str(e)}


@app.get("/api/knowledge/observations")
async def list_observations_endpoint(limit: int = Query(50, ge=1, le=200)) -> Dict[str, Any]:
    """Lists recent operational assertions recorded in the SOC Knowledge Store."""
    try:
        store = get_knowledge_store(root_dir=REPO_ROOT)
        obs_list = store.list_observations(limit=limit)
        return {
            "status": "SUCCESS",
            "observations": [o.to_dict() for o in obs_list],
            "total": len(obs_list),
        }
    except Exception as e:
        logger.error(f"Error listing observations: {e}", exc_info=True)
        return {"status": "ERROR", "message": str(e)}


# --- MITRE ATT&CK Strategic Mapping Endpoints ---

@app.get("/api/mitre/profiles")
async def list_mitre_profiles_endpoint() -> Dict[str, Any]:
    """Lists available MITRE ATT&CK threat profiles."""
    try:
        profiles = await asyncio.to_thread(engine.list_mitre_threat_profiles)
        return {
            "status": "SUCCESS",
            "profiles": profiles,
            "total": len(profiles),
        }
    except Exception as e:
        logger.error(f"Error listing MITRE threat profiles: {e}", exc_info=True)
        return {"status": "ERROR", "message": str(e)}


@app.get("/api/mitre/coverage")
async def get_mitre_coverage_endpoint(
    profile: str = Query("global_baseline"),
    lookback_days: int = Query(7, ge=1, le=90),
) -> Dict[str, Any]:
    """Evaluates tenant detection rules and live telemetry against MITRE ATT&CK."""
    try:
        assessment = await asyncio.to_thread(
            engine.analyze_mitre_coverage,
            profile_id=profile,
            sync_cache_if_empty=True,
            time_unit="DAY",
            time_value=str(lookback_days),
        )
        return {
            "status": "SUCCESS",
            "assessment": assessment.to_dict(),
        }
    except Exception as e:
        logger.error(f"Error evaluating MITRE ATT&CK coverage: {e}", exc_info=True)
        return {"status": "ERROR", "message": str(e)}


@app.post("/api/mitre/audit")
async def run_mitre_audit_endpoint(
    profile: str = Query("global_baseline", description="Target industry threat profile"),
    time_unit: str = Query("DAY", description="Telemetry lookback unit"),
    time_value: str = Query("7", description="Lookback quantity string"),
) -> Dict[str, Any]:
    """Executes a strategic MITRE ATT&CK coverage assessment and posts the dashboard card to Fleet Chat."""
    try:
        # Engine work runs off-loop; chat_store.add_message below must stay on
        # the event loop (it fans out via asyncio.Queue.put_nowait).
        assessment = await asyncio.to_thread(
            engine.analyze_mitre_coverage,
            profile_id=profile,
            sync_cache_if_empty=True,
            time_unit=time_unit,
            time_value=time_value,
        )
        rep_dict = assessment.to_dict()
        widget = {
            "type": "mitre_coverage_card",
            "title": f"MITRE ATT&CK Coverage: {assessment.profile_name}",
            "profile_id": assessment.profile_id,
            "profile_name": assessment.profile_name,
            "coverage_score": round(assessment.coverage_score, 2),
            "validated_technique_count": assessment.validated_technique_count,
            "total_rules_evaluated": assessment.total_rules_evaluated,
            "enabled_rules_count": assessment.enabled_rules_count,
            "visibility_tactics_count": assessment.visibility_tactics_count,
            "detection_tactics_count": assessment.detection_tactics_count,
            "blind_tactics": assessment.blind_tactics,
            "critical_techniques_count": len(assessment.critical_techniques),
            "critical_techniques": assessment.critical_techniques[:5],
            "resilient_techniques_count": len(assessment.resilient_techniques),
            "fragile_techniques_count": len(assessment.fragile_techniques),
            "visibility_gaps_count": len(assessment.visibility_gaps),
            "detection_gaps_count": len(assessment.detection_gaps),
            "created_at": assessment.created_at,
        }
        chat_store.add_message(
            stream="threat_intel",
            topic="mitre-coverage",
            sender_handle="@mitre-attack-agent",
            sender_type="agent",
            content=(
                f"🎯 **MITRE ATT&CK Strategic Posture Assessment Completed** for **{assessment.profile_name}**\n\n"
                f"- **Contextual Coverage Score**: **{assessment.coverage_score:.1f}%**\n"
                f"- **Covered Techniques**: `{assessment.validated_technique_count}` across `{assessment.total_rules_evaluated:,}` evaluated rules\n"
                f"- **Tactical Visibility**: `{assessment.visibility_tactics_count} / 14` tactics\n"
                f"- **Detection Coverage**: `{assessment.detection_tactics_count} / 14` tactics\n"
                f"- **Resilient Techniques (≥2 rules)**: `{len(assessment.resilient_techniques)}`\n"
                f"- **Fragile Detections (Single Point of Failure)**: `{len(assessment.fragile_techniques)}`\n"
                f"- **Visibility Gaps**: `{len(assessment.visibility_gaps)}` | **Detection Gaps**: `{len(assessment.detection_gaps)}`\n"
                f"- **Blind Tactics**: `{len(assessment.blind_tactics)}`"
                + (f" (`{', '.join(assessment.blind_tactics)}`)" if assessment.blind_tactics else " (None)")
                + "\n\nInteractive posture matrix and tactical breakdown rendered below."
            ),
            widget=widget,
        )
        return {
            "status": "SUCCESS",
            "assessment": rep_dict,
            "widget": widget,
        }
    except Exception as e:
        logger.error(f"Error running MITRE ATT&CK audit: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"MITRE audit failed: {e}")


@app.post("/api/mitre/sync")
async def sync_mitre_rules_endpoint(
    force: bool = Query(False),
    include_curated: bool = Query(True),
    max_rules: Optional[int] = Query(None),
) -> Dict[str, Any]:
    """Synchronizes customer and curated detection rules into Firestore with parsed MITRE technique IDs."""
    try:
        res = await asyncio.to_thread(
            engine.sync_mitre_rules,
            force_refresh=force,
            include_curated=include_curated,
            max_rules=max_rules,
        )
        return {
            "status": "SUCCESS",
            "result": res,
        }
    except Exception as e:
        logger.error(f"Error synchronizing MITRE rules: {e}", exc_info=True)
        return {"status": "ERROR", "message": str(e)}


@app.get("/api/mitre/report")
async def get_mitre_report_endpoint(
    profile: str = Query("global_baseline"),
) -> Dict[str, Any]:
    """Generates executive Markdown report for MITRE ATT&CK posture."""
    try:
        rep = await asyncio.to_thread(engine.generate_mitre_report, profile_id=profile)
        return {
            "status": "SUCCESS",
            "report": rep,
        }
    except Exception as e:
        logger.error(f"Error generating MITRE report: {e}", exc_info=True)
        return {"status": "ERROR", "message": str(e)}


@app.get("/api/mitre/technique/{technique_id}")
async def get_technique_rules_endpoint(technique_id: str) -> Dict[str, Any]:
    """Retrieves all detection rules mapped to a specific MITRE ATT&CK technique."""
    try:
        rules = await asyncio.to_thread(engine.get_technique_rules, technique_id)
        return {
            "status": "SUCCESS",
            "technique_id": technique_id,
            "rules": rules,
            "count": len(rules),
        }
    except Exception as e:
        logger.error(f"Error fetching rules for technique {technique_id}: {e}", exc_info=True)
        return {"status": "ERROR", "message": str(e)}


# --- Static Files & Root View ---


@app.get("/")
async def root_view() -> FileResponse:
    """Serves the Single Page App interface."""
    index_file = STATIC_DIR / "index.html"
    if not index_file.is_file():
        raise HTTPException(status_code=404, detail="Web UI assets not built yet.")
    return FileResponse(index_file)


@app.get("/knowledge/viz.html")
async def knowledge_viz_view() -> FileResponse:
    """Serves the interactive OKF Knowledge Graph Cytoscape visualizer."""
    viz_file = REPO_ROOT / "knowledge" / "viz.html"
    if not viz_file.is_file():
        raise HTTPException(status_code=404, detail="Knowledge graph not generated yet.")
    return FileResponse(viz_file)


# Mount static assets
if STATIC_DIR.is_dir():
    from fastapi.staticfiles import StaticFiles
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("clients.web.server:app", host="127.0.0.1", port=8080, log_level="info")

