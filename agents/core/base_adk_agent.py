"""Base Google ADK 2 Agent implementation for the SecOps Workflow Engine Fleet.

Integrates:
- Google ADK 2 agent patterns (system instructions, declarative tool bindings, model config).
- SecOpsEngine capability invocations via Automatic Function Calling with Gemini.
- ProposalManager integration for Gas Town Lite Git change tracking.
- Zulip stream and topic routing metadata.
"""

import asyncio
from dataclasses import asdict, dataclass, field, is_dataclass
from datetime import date, datetime, timezone
import inspect
import json
import logging
import os
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional
import yaml

from google import genai
from google.genai import types

from agents.core.evidence_store import EvidenceFabricStore
from agents.core.proposal_manager import (
    ChangeProposal,
    PreflightProof,
    ProposalManager,
)
from engine.facade import SecOpsEngine
from engine.registry import WorkflowCapability

logger = logging.getLogger(__name__)


def _serialize_for_llm(obj: Any) -> Any:
    """Serializes complex SDK and domain objects into JSON-compatible dicts for Gemini."""
    if obj is None:
        return None
    if isinstance(obj, (str, int, float, bool)):
        return obj
    if isinstance(obj, (datetime, date)):
        return obj.isoformat()
    if is_dataclass(obj) and not isinstance(obj, type):
        return _serialize_for_llm(asdict(obj))
    if hasattr(obj, "to_dict") and callable(obj.to_dict):
        return _serialize_for_llm(obj.to_dict())
    if hasattr(obj, "__dict__"):
        return {
            k: _serialize_for_llm(v)
            for k, v in obj.__dict__.items()
            if not k.startswith("_") and k != "raw"
        }
    if isinstance(obj, (list, tuple)):
        return [_serialize_for_llm(x) for x in obj]
    if isinstance(obj, dict):
        d = {str(k): _serialize_for_llm(v) for k, v in obj.items() if k != "raw"}
        if "text" in d and "rule_text" not in d:
            d["rule_text"] = d["text"]
        return d
    return str(obj)


@dataclass
class AdkSkill:
    """Represents a modular ADK Skill loaded from the operational knowledge base."""
    id: str
    title: str
    skill_type: str
    triggers: List[str]
    capabilities_used: List[str]
    procedure: str
    evaluation_rules: Dict[str, Any]
    source_path: str


class SkillCatalog:
    """Catalog of operational skills and runbooks loaded dynamically from knowledge/."""

    _instance: Optional["SkillCatalog"] = None

    def __init__(self, knowledge_dir: Optional[Path] = None):
        if knowledge_dir is None:
            knowledge_dir = Path(__file__).resolve().parent.parent.parent / "knowledge"
        self.knowledge_dir = knowledge_dir
        self.skills: Dict[str, AdkSkill] = {}
        self._load_skills()

    @classmethod
    def get_instance(cls) -> "SkillCatalog":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def _load_skills(self) -> None:
        if not self.knowledge_dir.exists():
            return

        for p in self.knowledge_dir.rglob("*.md"):
            if "templates" in p.parts or p.name == "README.md":
                continue
            try:
                content = p.read_text(encoding="utf-8")
                if not content.startswith("---"):
                    continue
                parts = content.split("---", 2)
                if len(parts) < 3:
                    continue
                fm = yaml.safe_load(parts[1])
                if not isinstance(fm, dict):
                    continue
                body = parts[2].strip()
                skill_id = fm.get("id")
                if not skill_id:
                    continue

                raw_triggers = fm.get("trigger", [])
                if isinstance(raw_triggers, str):
                    triggers = [raw_triggers]
                elif isinstance(raw_triggers, list):
                    triggers = [str(t) for t in raw_triggers]
                else:
                    triggers = []

                raw_caps = fm.get("capabilities_used", []) or fm.get("sdk_capabilities", [])
                if isinstance(raw_caps, str):
                    caps = [raw_caps]
                elif isinstance(raw_caps, list):
                    caps = [str(c) for c in raw_caps]
                else:
                    caps = []

                eval_rules = fm.get("evaluation_rules", {})
                if not isinstance(eval_rules, dict):
                    eval_rules = {}

                self.skills[skill_id] = AdkSkill(
                    id=skill_id,
                    title=fm.get("title", p.stem),
                    skill_type=fm.get("type", "task"),
                    triggers=triggers,
                    capabilities_used=caps,
                    procedure=body,
                    evaluation_rules=eval_rules,
                    source_path=str(p.relative_to(self.knowledge_dir.parent)),
                )
            except Exception as e:
                logger.debug("Failed loading skill from %s: %s", p, e)

    def match_skill(
        self, prompt: str, agent_capabilities: List[str]
    ) -> Optional[AdkSkill]:
        """Finds the most relevant ADK skill based on prompt intent and agent capabilities."""
        if not self.skills or not prompt:
            return None

        prompt_lower = prompt.lower()
        cap_set = set(agent_capabilities)

        best_skill: Optional[AdkSkill] = None
        best_score = 0

        for skill in self.skills.values():
            score = 0
            # 1. Capability overlap (strong signal: agent has the tools for this task)
            matched_caps = cap_set.intersection(skill.capabilities_used)
            if matched_caps:
                score += len(matched_caps) * 10
            elif skill.capabilities_used:
                # Skill requires specific capabilities the agent doesn't have
                continue

            # 2. Trigger matches
            for trig in skill.triggers:
                trig_words = [w for w in trig.replace("_", " ").lower().split() if len(w) > 3]
                if any(tw in prompt_lower for tw in trig_words):
                    score += 5

            # 3. Title/ID keyword matches in prompt
            title_keywords = [
                w.lower()
                for w in skill.title.replace("_", " ").replace("-", " ").split()
                if len(w) > 3 and w.lower() not in {"review", "check", "with", "from", "audit"}
            ]
            for kw in title_keywords:
                if kw in prompt_lower:
                    score += 4

            # 4. Domain token triggers
            if "rule" in prompt_lower and "rule" in skill.id:
                score += 3
            if "feed" in prompt_lower and "feed" in skill.id:
                score += 3
            if "parser" in prompt_lower and "parser" in skill.id:
                score += 3
            if ("iam" in prompt_lower or "identity" in prompt_lower) and "identity" in skill.id:
                score += 4
            if ("soar" in prompt_lower or "case" in prompt_lower) and ("case" in skill.id or "soar" in skill.id):
                score += 4

            # 5. Operational task priority: tasks contain executable runbooks and evaluation rules
            if skill.skill_type == "task":
                score += 25
                action_words = {"review", "audit", "diagnose", "optimize", "triage", "check", "fix", "inspect", "remediate"}
                if any(w in prompt_lower for w in action_words):
                    score += 15

            if score > best_score and score >= 10:
                best_score = score
                best_skill = skill

        return best_skill


@dataclass
class AgentMessage:
    """Message formatted for Zulip streams and topics."""
    id: str
    stream: str
    topic: str
    sender_handle: str
    content: str
    proposal_id: Optional[str] = None
    widget: Optional[Dict[str, Any]] = None
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


class BaseSecOpsAdkAgent:
    """Base agent class compliant with Google ADK 2 conventions for GEAP."""

    def __init__(
        self,
        name: str,
        handle: str,
        role: str,
        subsystem: str,
        description: str,
        system_instruction: str,
        model: str = "gemini-3.8-flash",
        default_stream: str = "general",
        default_topic: str = "inbox",
        engine: Optional[SecOpsEngine] = None,
        proposal_manager: Optional[ProposalManager] = None,
        inventory_client: Any = None,
        evidence_store: Optional[EvidenceFabricStore] = None,
    ):
        self.name = name
        self.handle = handle
        self.role = role
        self.subsystem = subsystem
        self.description = description
        self.system_instruction = system_instruction
        self.model = model
        self.default_stream = default_stream
        self.default_topic = default_topic

        self.engine = engine
        self.proposal_manager = proposal_manager or ProposalManager()
        self.inventory_client = inventory_client
        self.evidence_store = evidence_store

        self._tools: Dict[str, Callable[..., Any]] = {
            "get_task_status": self.get_task_status,
        }
        self._capabilities: Dict[str, WorkflowCapability] = {}
        self._outbox: List[AgentMessage] = []
        self.executed_tool_calls: List[Dict[str, Any]] = []
        self.last_submitted_proposal: Optional[Any] = None
        self.skill_catalog = SkillCatalog.get_instance()
        self.last_loaded_skill: Optional[str] = None

    def get_task_status(self, task_id: str) -> Dict[str, Any]:
        """Queries the status and details of a remediation task, proposal, or Chronicle rule.

        Args:
            task_id: The identifier to look up (e.g. 'todo_...', 'prop-...', or 'ru_...').
        """
        clean_id = (task_id or "").strip()

        # 1. Check Evidence Fabric tasks (secops_todos)
        if self.evidence_store:
            todo = self.evidence_store.get_todo(clean_id)
            if todo:
                return {
                    "found": True,
                    "entity_type": "todo_task",
                    "id": clean_id,
                    "title": todo.get("title"),
                    "status": todo.get("status"),
                    "target_agent": todo.get("target_agent"),
                    "target_resource_id": todo.get("target_resource_id"),
                    "action_type": todo.get("action_type"),
                    "rationale": todo.get("rationale"),
                    "stream": todo.get("stream"),
                    "topic": todo.get("topic"),
                    "created_at": todo.get("created_at"),
                }

        # 2. Check Gas Town Proposals
        if self.proposal_manager:
            try:
                proposal = self.proposal_manager.get_proposal(clean_id)
                if proposal:
                    return {
                        "found": True,
                        "entity_type": "change_proposal",
                        "id": proposal.id,
                        "title": proposal.title,
                        "status": proposal.status,
                        "author": proposal.author,
                        "target_resource_id": proposal.target_resource_id,
                        "risk_level": proposal.risk_level,
                        "subsystem": proposal.subsystem,
                        "rationale": proposal.rationale,
                    }
            except Exception:
                pass

        # 3. Check Chronicle Rule if ID looks like a rule (ru_ or ur_)
        if self.engine and (clean_id.startswith("ru_") or clean_id.startswith("ur_")):
            try:
                rule = self.engine.get_rule(clean_id)
                if rule:
                    return {
                        "found": True,
                        "entity_type": "chronicle_rule",
                        "id": getattr(rule, "id", clean_id),
                        "display_name": getattr(rule, "display_name", ""),
                        "revision_id": getattr(rule, "revision_id", ""),
                        "enabled": getattr(rule, "enabled", False),
                    }
            except Exception:
                pass

        return {
            "found": False,
            "id": clean_id,
            "message": f"No active task, proposal, or rule found matching identifier '{clean_id}'.",
        }

    def bind_capability(self, capability: WorkflowCapability) -> None:
        """Binds an engine capability as a callable ADK 2 tool function for Gemini."""
        tool_name = capability.mcp_tool_name or capability.capability_id.replace(".", "_")
        self._capabilities[capability.capability_id] = capability

        orig_sig = inspect.signature(capability.handler)
        clean_params = [
            p for p in orig_sig.parameters.values()
            if "Callable" not in str(p.annotation) and "callback" not in p.name.lower() and p.name != "on_batch"
        ]
        new_sig = orig_sig.replace(parameters=clean_params, return_annotation=Dict[str, Any])

        def _tool_wrapper(*args: Any, **kwargs: Any) -> Any:
            bound = new_sig.bind(*args, **kwargs)
            bound.apply_defaults()
            logger.info("Agent %s invoking live capability %s with %s", self.handle, capability.capability_id, bound.arguments)
            if hasattr(self, "status_callback") and self.status_callback:
                try:
                    self.status_callback(f"Executing {capability.name}...")
                except Exception:
                    pass
            raw_res = capability.handler(**bound.arguments)
            serialized = _serialize_for_llm(raw_res)

            self.executed_tool_calls.append({
                "agent": self.handle,
                "tool": tool_name,
                "capability_id": capability.capability_id,
                "arguments": {k: str(v) for k, v in bound.arguments.items()},
                "timestamp": datetime.now(timezone.utc).isoformat(),
            })

            # Auto-update Evidence Fabric blackboard when rule telemetry is retrieved
            if self.evidence_store and isinstance(serialized, dict):
                rule_id = bound.arguments.get("rule_id") or bound.arguments.get("rule_id_or_name")
                if rule_id and capability.capability_id in ("rule.get", "rule.deployment.get", "rule.errors"):
                    try:
                        self.evidence_store.save_rule_state(str(rule_id), {
                            "last_inspected_by": self.handle,
                            "last_inspected_at": datetime.now(timezone.utc).isoformat(),
                            f"last_{capability.capability_id.replace('.', '_')}": serialized,
                        })
                    except Exception as store_err:
                        logger.debug("Failed updating rule state in Evidence Fabric: %s", store_err)

            return serialized

        _tool_wrapper.__signature__ = new_sig
        _tool_wrapper.__name__ = tool_name
        _tool_wrapper.__doc__ = f"{capability.name}\n\n{capability.description}"
        self._tools[tool_name] = _tool_wrapper

    def get_tools(self) -> List[Callable[..., Any]]:
        """Returns list of callable tool functions exposed to the ADK 2 model."""
        return list(self._tools.values())

    async def chat(
        self,
        prompt: str,
        stream: Optional[str] = None,
        topic: Optional[str] = None,
        history: Optional[List[Dict[str, str]]] = None,
    ) -> AgentMessage:
        """Executes a real Gemini reasoning loop with Automatic Function Calling."""
        self.last_submitted_proposal = None
        turn_start_idx = len(self.executed_tool_calls)

        project_id = (
            os.getenv("GCP_PROJECT_ID")
            or os.getenv("SECOPS_PROJECT_ID")
            or os.getenv("GOOGLE_CLOUD_PROJECT")
            or "sdl-preview-americas"
        )
        api_key = os.getenv("GOOGLE_API_KEY") or os.getenv("GEMINI_API_KEY")

        # Dynamic config resolution from EvidenceFabricStore
        active_system_instruction = self.system_instruction
        raw_model = self.model or "gemini-3.8-flash"
        if self.evidence_store:
            try:
                cfg = self.evidence_store.get_agent_config(self.handle)
                if cfg.get("system_instruction"):
                    active_system_instruction = cfg["system_instruction"]
                if cfg.get("model"):
                    raw_model = cfg["model"]
            except Exception as cfg_err:
                logger.debug("Failed reading dynamic config for %s: %s", self.handle, cfg_err)

        # ADK Modular Skill Resolution: Dynamically match runbooks and operational concepts from knowledge/
        matched_skill = None
        if self.skill_catalog:
            try:
                matched_skill = self.skill_catalog.match_skill(
                    prompt=prompt,
                    agent_capabilities=list(self._capabilities.keys()),
                )
            except Exception as skill_err:
                logger.debug("Skill matching failed for %s: %s", self.handle, skill_err)

        if matched_skill:
            self.last_loaded_skill = matched_skill.id
            skill_block = (
                f"\n\n### Dynamically Injected ADK Skill: {matched_skill.title} (`{matched_skill.id}`)\n"
                f"**Domain Scope:** {matched_skill.skill_type}\n"
                f"**Operational Runbook & Guidance:**\n{matched_skill.procedure}\n"
            )
            if matched_skill.evaluation_rules:
                skill_block += (
                    f"\n**Target Evaluation Rules & Thresholds:**\n"
                    f"{json.dumps(matched_skill.evaluation_rules, indent=2)}\n"
                )
            active_system_instruction = active_system_instruction + skill_block
        else:
            self.last_loaded_skill = None

        # Normalize aliases: gemini-flash-3.8 / flash-3.8 -> gemini-3.8-flash
        target_model = raw_model
        if target_model in ("gemini-flash-3.8", "flash-3.8"):
            target_model = "gemini-3.8-flash"

        # Initialize clients to try: Vertex AI location="global" first, then AI Studio API key
        clients_to_try = []
        try:
            clients_to_try.append(("vertexai_global", genai.Client(vertexai=True, project=project_id, location="global")))
        except Exception as v_err:
            logger.debug("Vertex AI global client init failed: %s", v_err)

        if api_key:
            clients_to_try.append(("ai_studio", genai.Client(api_key=api_key)))

        if not clients_to_try:
            error_content = (
                f"**Agent Configuration Error**: `{self.handle}` requires Google Cloud ADC "
                f"or `GOOGLE_API_KEY` / `GEMINI_API_KEY` to run autonomous LLM reasoning with live tools."
            )
            return self.post_message(content=error_content, stream=stream, topic=topic)

        try:
            tools = self.get_tools()

            config = types.GenerateContentConfig(
                tools=tools if tools else None,
                system_instruction=active_system_instruction,
            )

            response = None
            last_err = None
            for client_name, client in clients_to_try:
                for attempt in range(2):
                    try:
                        chat_session = client.chats.create(model=target_model, config=config)
                        response = await asyncio.to_thread(chat_session.send_message, prompt)
                        break
                    except Exception as call_err:
                        last_err = call_err
                        err_str = str(call_err).lower()
                        if "429" in err_str or "resource_exhausted" in err_str or "quota" in err_str:
                            logger.warning(
                                "Rate limit on %s for %s (attempt %d): %s. Waiting...",
                                client_name, self.handle, attempt + 1, call_err
                            )
                            await asyncio.sleep(2.0 * (attempt + 1))
                            continue
                        else:
                            break
                if response is not None:
                    break

            if response is None:
                raise last_err or RuntimeError("No response returned from model")

            response_text = response.text or "Analysis completed with no additional findings."

            # Append live tool execution provenance and injected skill if invoked
            tools_run_this_turn = self.executed_tool_calls[turn_start_idx:]
            if tools_run_this_turn or self.last_loaded_skill:
                trace_lines = []
                if self.last_loaded_skill:
                    trace_lines.append(f"- **ADK Skill Injected:** `{self.last_loaded_skill}`")
                if tools_run_this_turn:
                    trace_lines.append("- **Live SecOps Tools Executed:**")
                    for t in tools_run_this_turn:
                        args_repr = ", ".join(f"{k}={v}" for k, v in t["arguments"].items())
                        trace_lines.append(f"  - `{t['capability_id']}` ({args_repr})")
                provenance_block = (
                    f"\n\n---\n**Live Operational Provenance:**\n"
                    + "\n".join(trace_lines)
                )
                response_text += provenance_block

            proposal_id = None
            widget = None
            if hasattr(self, "last_widget") and self.last_widget:
                widget = self.last_widget
                self.last_widget = None
            elif self.last_submitted_proposal:
                prop = self.last_submitted_proposal
                proposal_id = getattr(prop, "id", None)
                preflight_dict = None
                if hasattr(prop, "preflight") and prop.preflight:
                    preflight_dict = asdict(prop.preflight) if is_dataclass(prop.preflight) else prop.preflight
                widget = {
                    "type": "hitl_proposal_card",
                    "proposal_id": proposal_id,
                    "status": getattr(prop, "status", "OPEN"),
                    "title": getattr(prop, "title", ""),
                    "target_resource_id": getattr(prop, "target_resource_id", ""),
                    "action_type": getattr(prop, "action_type", ""),
                    "risk_level": getattr(prop, "risk_level", "MEDIUM"),
                    "rationale": getattr(prop, "rationale", ""),
                    "proposed_diff": getattr(prop, "proposed_diff", ""),
                    "preflight": preflight_dict,
                }

            agent_msg = self.post_message(
                content=response_text,
                stream=stream,
                topic=topic,
                proposal_id=proposal_id,
                widget=widget,
            )

            # Persist reasoning turn and provenance to Evidence Fabric Store
            if self.evidence_store:
                try:
                    self.evidence_store.record_evidence(
                        agent_handle=self.handle,
                        action="chat_turn",
                        stream=stream or self.default_stream,
                        topic=topic or self.default_topic,
                        prompt=prompt,
                        response=response_text,
                        executed_tools=tools_run_this_turn,
                        metadata={
                            "model": target_model,
                            "tools_count": len(tools_run_this_turn),
                            "proposal_id": proposal_id,
                        },
                    )
                except Exception as ev_err:
                    logger.warning("Failed persisting evidence for %s: %s", self.handle, ev_err)

            return agent_msg

        except Exception as e:
            logger.exception("Agent %s failed during reasoning loop: %s", self.handle, e)
            error_content = (
                f"**Execution Error in `{self.handle}`**:\n"
                f"> {type(e).__name__}: {e}\n\n"
                f"*Please check the Google SecOps tenant connectivity or prompt parameters.*"
            )
            return self.post_message(content=error_content, stream=stream, topic=topic)

    def post_message(
        self,
        content: str,
        stream: Optional[str] = None,
        topic: Optional[str] = None,
        proposal_id: Optional[str] = None,
        widget: Optional[Dict[str, Any]] = None,
    ) -> AgentMessage:
        """Emits a message into the Zulip stream/topic bus."""
        msg_stream = stream or self.default_stream
        msg_topic = topic or self.default_topic
        msg_id = f"msg_{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}_{len(self._outbox) + 1}"

        msg = AgentMessage(
            id=msg_id,
            stream=msg_stream,
            topic=msg_topic,
            sender_handle=self.handle,
            content=content,
            proposal_id=proposal_id,
            widget=widget,
        )
        self._outbox.append(msg)
        logger.info("[%s > %s] %s: %s", msg_stream, msg_topic, self.handle, content[:80])
        return msg

    def submit_proposal(
        self,
        title: str,
        target_resource_id: str,
        action_type: str,
        rationale: str,
        proposed_diff: str,
        mutation_payload: Dict[str, Any],
        preflight: Optional[PreflightProof] = None,
        risk_level: str = "MEDIUM",
        stream: Optional[str] = None,
        topic: Optional[str] = None,
    ) -> ChangeProposal:
        """Submits a change proposal to Gas Town .proposals/ and notifies the Zulip topic."""
        proof = preflight or PreflightProof()
        proposal = ChangeProposal(
            id="",
            title=title,
            author=self.handle,
            subsystem=self.subsystem,
            target_resource_id=target_resource_id,
            action_type=action_type,
            risk_level=risk_level,
            rationale=rationale,
            proposed_diff=proposed_diff,
            preflight=proof,
            mutation_payload=mutation_payload,
        )

        proposal_id = self.proposal_manager.create_proposal(proposal)

        # Notify topic with interactive HITL proposal widget
        widget = {
            "type": "hitl_proposal_card",
            "proposal_id": proposal_id,
            "status": "OPEN",
            "actions": ["approve_and_merge", "reject", "view_diff"],
        }

        notice = (
            f"**Change Proposal Submitted**: `{proposal_id}`\n\n"
            f"**Target**: `{target_resource_id}` ({action_type})\n"
            f"**Rationale**: {rationale}\n\n"
            f"Pre-flight Verification: Syntax={'PASS' if proof.syntax_verified else 'FAIL'}, "
            f"Replay={'PASS' if proof.replay_verified else 'PENDING'}"
        )

        self.post_message(
            content=notice,
            stream=stream or self.default_stream,
            topic=topic or self.default_topic,
            proposal_id=proposal_id,
            widget=widget,
        )

        created_proposal = self.proposal_manager.get_proposal(proposal_id)
        self.last_submitted_proposal = created_proposal
        return created_proposal
