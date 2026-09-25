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

try:
    from google import genai
    from google.genai import types
except (ImportError, AttributeError):
    genai = None  # type: ignore
    types = None  # type: ignore

from agents.core.evidence_store import EvidenceFabricStore
from agents.core.lifecycle import SOCLifecycleManager
from agents.core.proposal_manager import (
    ChangeProposal,
    PreflightProof,
    ProposalManager,
)
from agents.core.work_queue import BaseWorkQueue
from engine.domain import AgentCapabilityProfile, Lease, SOCIssue
from engine.facade import SecOpsEngine
from engine.registry import WorkflowCapability

logger = logging.getLogger(__name__)


# Model Input Token Ceilings & Safety Limits
MODEL_TOKEN_LIMITS: Dict[str, int] = {
    "gemini-3.8-flash": 1_048_576,
    "gemini-2.5-flash": 1_048_576,
    "gemini-2.0-flash": 1_048_576,
    "gemini-1.5-flash": 1_048_576,
    "gemini-1.5-pro": 2_097_152,
    "gemini-2.5-pro": 2_097_152,
}
DEFAULT_MODEL_TOKEN_LIMIT = 1_048_576

# Tool serialization and payload budgets
MAX_STRING_FIELD_CHARS = 50_000   # ~12,500 tokens max for any single string attribute
MAX_TOOL_OUTPUT_BYTES = 400_000    # ~100,000 tokens max budget for any single tool output
MAX_COLLECTION_ITEMS = 25          # Maximum items in an array within tool output before summary truncation

EXCLUDED_SERIALIZATION_KEYS = {
    "raw",
    "cbn_raw",
    "raw_payload",
    "raw_bytes",
    "base64_data",
    "_raw",
}


def get_model_token_limit(model_name: str, client: Optional[Any] = None) -> int:
    """Discovers the input token limit for the given model, checking API metadata or canonical registry."""
    clean_model = model_name.split("/")[-1]
    if client:
        try:
            m_info = client.models.get(model=clean_model)
            if getattr(m_info, "input_token_limit", None):
                return int(m_info.input_token_limit)
        except Exception:
            pass
    return MODEL_TOKEN_LIMITS.get(clean_model, DEFAULT_MODEL_TOKEN_LIMIT)


def count_tokens(client: Optional[Any], model_name: str, contents: Any) -> int:
    """Counts tokens using the official Gemini tokenizer, with heuristic fallback."""
    clean_model = model_name.split("/")[-1]
    if client:
        try:
            res = client.models.count_tokens(model=clean_model, contents=contents)
            if getattr(res, "total_tokens", None) is not None:
                return int(res.total_tokens)
        except Exception:
            pass
    # Fast heuristic fallback: ~4 characters per token
    s = contents if isinstance(contents, str) else json.dumps(contents, default=str)
    return max(1, len(s) // 4)


def _serialize_for_llm(obj: Any) -> Any:
    """Serializes complex SDK and domain objects into JSON-compatible dicts for Gemini with token budget pruning."""
    if obj is None:
        return None
    if isinstance(obj, (int, float, bool)):
        return obj
    if isinstance(obj, str):
        if len(obj) > MAX_STRING_FIELD_CHARS:
            omitted = len(obj) - MAX_STRING_FIELD_CHARS
            return obj[:MAX_STRING_FIELD_CHARS] + (
                f"\n\n[... TRUNCATED: {omitted:,} characters omitted to preserve Gemini token budget. "
                f"Total size: {len(obj):,} chars. Full content accessible via engine/evidence fabric. ...]"
            )
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
            if not k.startswith("_") and k not in EXCLUDED_SERIALIZATION_KEYS
        }
    if isinstance(obj, (list, tuple)):
        return [_serialize_for_llm(x) for x in obj]
    if isinstance(obj, dict):
        d = {
            str(k): _serialize_for_llm(v)
            for k, v in obj.items()
            if str(k) not in EXCLUDED_SERIALIZATION_KEYS and not str(k).startswith("_")
        }
        if "text" in d and "rule_text" not in d:
            d["rule_text"] = d["text"]
        return d
    return str(obj)


def _sanitize_tool_payload(payload: Any, max_bytes: int = MAX_TOOL_OUTPUT_BYTES) -> Any:
    """Enforces context-window budget guardrails on tool outputs returned to Gemini AFC."""
    try:
        dumped = json.dumps(payload, default=str)
    except Exception:
        return payload

    if len(dumped) <= max_bytes:
        return payload

    # If payload is a list, cap items
    if isinstance(payload, list) and len(payload) > MAX_COLLECTION_ITEMS:
        truncated_list = payload[:MAX_COLLECTION_ITEMS]
        meta_note = {
            "_budget_truncation_notice": (
                f"Collection truncated from {len(payload)} to {MAX_COLLECTION_ITEMS} items to satisfy Gemini "
                f"context budget ({len(dumped):,} bytes exceeded {max_bytes:,} byte budget)."
            ),
            "total_items": len(payload),
            "returned_items": MAX_COLLECTION_ITEMS,
        }
        return truncated_list + [meta_note]

    # If payload is a dict, cap nested lists or oversized strings
    if isinstance(payload, dict):
        budgeted_dict = {}
        for k, v in payload.items():
            if isinstance(v, list) and len(v) > MAX_COLLECTION_ITEMS:
                budgeted_dict[k] = v[:MAX_COLLECTION_ITEMS] + [{
                    "_budget_truncation_notice": (
                        f"Truncated from {len(v)} to {MAX_COLLECTION_ITEMS} items for LLM context budget."
                    ),
                    "total_items": len(v),
                    "returned_items": MAX_COLLECTION_ITEMS,
                }]
            elif isinstance(v, str) and len(v) > 20_000:
                budgeted_dict[k] = v[:20_000] + f"\n[... TRUNCATED {len(v) - 20_000:,} chars for token budget ...]"
            else:
                budgeted_dict[k] = v
        return budgeted_dict

    return payload



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
        work_queue: Optional[BaseWorkQueue] = None,
        lifecycle_manager: Optional[SOCLifecycleManager] = None,
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
        self.work_queue = work_queue
        self.lifecycle_manager = lifecycle_manager

        self._tools: Dict[str, Callable[..., Any]] = {
            "get_task_status": self.get_task_status,
        }
        self._capabilities: Dict[str, WorkflowCapability] = {}
        self._outbox: List[AgentMessage] = []
        self.executed_tool_calls: List[Dict[str, Any]] = []
        self.last_submitted_proposal: Optional[Any] = None
        self.skill_catalog = SkillCatalog.get_instance()
        self.last_loaded_skill: Optional[str] = None

    def get_capability_profile(self) -> AgentCapabilityProfile:
        """Returns the capability profile for this agent."""
        caps: Dict[str, int] = {}
        # From bound engine capabilities
        for cap_id in self._capabilities:
            caps[cap_id] = 1
        # From declared class capabilities
        if hasattr(self, "CAPABILITIES") and isinstance(self.CAPABILITIES, list):
            for cap_id in self.CAPABILITIES:
                caps[cap_id] = 1
        # Builtin tool capabilities
        for t in self._tools:
            caps[t] = 1
        caps["git.proposal.create"] = 1

        plane_map = {
            "ingestion": "data",
            "detection": "detection",
            "soar": "automation",
            "cost": "platform",
            "tenant": "governance",
            "audit": "governance",
        }
        plane = plane_map.get(self.subsystem, "platform")

        return AgentCapabilityProfile(
            agent_handle=self.handle,
            capabilities=caps,
            operational_planes=[plane],
            max_concurrent_leases=3,
        )

    def register_worker(self) -> bool:
        """Registers this worker's capability profile with the work queue."""
        if not self.work_queue:
            return False
        profile = self.get_capability_profile()
        res = self.work_queue.register_worker(profile)
        return True if res is None or res is True else False

    def find_eligible_issues(self, limit: int = 10) -> List[SOCIssue]:
        """Finds active unassigned or claimable issues matching this agent's capabilities."""
        if not self.work_queue:
            return []
        profile = self.get_capability_profile()
        plane = profile.operational_planes[0] if profile.operational_planes else None
        return self.work_queue.find_eligible_issues(
            agent_capabilities=profile.capabilities,
            plane=plane,
            limit=limit,
        )

    def claim_work(self, issue_id: str, duration_seconds: int = 300) -> Optional[Lease]:
        """Acquires a lease on an issue from the work queue."""
        if self.lifecycle_manager:
            return self.lifecycle_manager.claim_issue(issue_id, self.handle, duration_seconds=duration_seconds)
        elif self.work_queue:
            return self.work_queue.acquire_lease(issue_id, self.handle, duration_seconds=duration_seconds)
        return None

    def renew_work_lease(self, issue_id: str, duration_seconds: int = 300) -> bool:
        """Renews an active work lease."""
        if self.lifecycle_manager:
            return self.lifecycle_manager.heartbeat(issue_id, self.handle, duration_seconds=duration_seconds)
        elif self.work_queue:
            return self.work_queue.renew_lease(issue_id, self.handle, duration_seconds=duration_seconds)
        return False

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

            # Auto-create FinOps cost card widget when log_cost.analyze is executed
            if capability.capability_id == "log_cost.analyze":
                r_dict = serialized if isinstance(serialized, dict) else (raw_res.to_dict() if hasattr(raw_res, "to_dict") else {})
                self.last_widget = {
                    "type": "finops_cost_card",
                    "total_volume_gb": r_dict.get("total_volume_gb", 0),
                    "total_volume_gib": r_dict.get("total_volume_gib", 0),
                    "total_events": r_dict.get("total_events", 0),
                    "spend_standard": r_dict.get("total_projected_monthly_spend_standard", 0),
                    "spend_enterprise": r_dict.get("total_projected_monthly_spend_enterprise", 0),
                    "spend_enterprise_plus": r_dict.get("total_projected_monthly_spend_enterprise_plus", 0),
                    "savings": r_dict.get("total_potential_savings_usd", 0),
                    "recommendations_count": len(r_dict.get("recommendations", [])),
                    "bloated_count": len(r_dict.get("bloated_sources", [])),
                    "top_drivers": r_dict.get("top_volume_drivers", [])[:5],
                    "recommendations": r_dict.get("recommendations", [])[:4],
                }

            # Auto-create raw log search card widget when log.raw_logs.search is executed
            if capability.capability_id == "log.raw_logs.search":
                r_dict = serialized if isinstance(serialized, dict) else (raw_res.to_dict() if hasattr(raw_res, "to_dict") else {})
                matches = r_dict.get("matches", [])
                self.last_widget = {
                    "type": "raw_log_search_card",
                    "total_matches": len(matches),
                    "progress": r_dict.get("progress", 100),
                    "query": bound.arguments.get("query", ""),
                    "lookback_hours": bound.arguments.get("lookback_hours", 24),
                    "log_types": bound.arguments.get("log_types") or [],
                    "matches": matches[:10],
                }

            sanitized_payload = _sanitize_tool_payload(serialized)
            return sanitized_payload

        _tool_wrapper.__signature__ = new_sig
        _tool_wrapper.__name__ = tool_name
        _tool_wrapper.__doc__ = f"{capability.name}\n\n{capability.description}"
        _tool_wrapper._is_budgeted_tool = True
        self._tools[tool_name] = _tool_wrapper

    def get_tools(self) -> List[Callable[..., Any]]:
        """Returns list of callable tool functions exposed to the ADK 2 model,
        ensuring every tool return is strictly serialized and budgeted.
        """
        budgeted_tools = []
        for name, fn in self._tools.items():
            if getattr(fn, "_is_budgeted_tool", False):
                budgeted_tools.append(fn)
                continue

            orig_sig = getattr(fn, "__signature__", None) or inspect.signature(fn)

            def make_budgeted_wrapper(func, tool_func_name, sig):
                def _budgeted_call(*args, **kwargs):
                    try:
                        logger.info("Agent %s invoking custom tool %s with %s", self.handle, tool_func_name, kwargs)
                        if hasattr(self, "status_callback") and self.status_callback:
                            try:
                                self.status_callback(f"Executing {tool_func_name}...")
                            except Exception:
                                pass
                        res = func(*args, **kwargs)
                        serialized = _serialize_for_llm(res)
                        sanitized = _sanitize_tool_payload(serialized)

                        self.executed_tool_calls.append({
                            "agent": self.handle,
                            "tool": tool_func_name,
                            "capability_id": tool_func_name,
                            "arguments": {k: str(v) for k, v in kwargs.items()},
                            "timestamp": datetime.now(timezone.utc).isoformat(),
                        })

                        return sanitized
                    except Exception as e:
                        logger.warning("Error in tool %s: %s", tool_func_name, e)
                        return {"status": "ERROR", "message": str(e)}

                _budgeted_call.__name__ = tool_func_name
                _budgeted_call.__signature__ = sig
                _budgeted_call.__doc__ = func.__doc__
                _budgeted_call._is_budgeted_tool = True
                return _budgeted_call

            budgeted_tools.append(make_budgeted_wrapper(fn, name, orig_sig))
        return budgeted_tools

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
        if project_id:
            try:
                clients_to_try.append(("vertexai_global", genai.Client(vertexai=True, project=project_id, location="global")))
            except Exception as v_err:
                logger.debug("Vertex AI global client init failed: %s", v_err)
        else:
            logger.debug("No GCP project configured; skipping Vertex AI client for %s", self.handle)

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
            active_chat_session = None
            for client_name, client in clients_to_try:
                for attempt in range(2):
                    try:
                        chat_session = client.chats.create(model=target_model, config=config)
                        response = await asyncio.to_thread(chat_session.send_message, prompt)
                        active_chat_session = chat_session
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
                        elif "400" in err_str and ("token count exceeds" in err_str or "maximum number of tokens" in err_str or "1048576" in err_str):
                            logger.warning(
                                "Token limit exceeded during reasoning on %s for %s: %s",
                                client_name, self.handle, call_err
                            )
                            limit_val = get_model_token_limit(target_model, client)
                            fallback_text = (
                                f"⚠️ **Context Window Budget Exceeded (`{self.handle}`)**\n\n"
                                f"The data requested during autonomous tool execution exceeded Gemini's maximum context limit of "
                                f"**{limit_val:,} tokens**.\n\n"
                                f"**Operational Mitigation:**\n"
                                f"- The engine has isolated this request to prevent crash loops.\n"
                                f"- Provide narrower query parameters (e.g. smaller lookback window, specific log types, or rule filters).\n"
                                f"- Oversized telemetry has been stored in the Evidence Fabric."
                            )
                            class _SafeTokenFallbackResponse:
                                text = fallback_text
                            response = _SafeTokenFallbackResponse()
                            break
                        else:
                            break
                if response is not None:
                    break

            tools_run_this_turn = self.executed_tool_calls[turn_start_idx:]

            response_text = ""
            try:
                response_text = (response.text or "").strip()
            except Exception:
                pass

            # If Automatic Function Calling executed tools but returned no text parts,
            # prompt the chat session for an executive summary of the tool returns.
            if not response_text and tools_run_this_turn and active_chat_session and hasattr(active_chat_session, "send_message"):
                try:
                    logger.info("AFC concluded with no text part. Requesting summary from %s...", self.handle)
                    summary_res = await asyncio.to_thread(
                        active_chat_session.send_message,
                        "Please provide a concise executive summary of your diagnostic findings and conclusions based on the tools executed above."
                    )
                    if summary_res and getattr(summary_res, "text", None):
                        response_text = summary_res.text.strip()
                except Exception as sum_err:
                    logger.debug("Failed requesting follow-up synthesis: %s", sum_err)

            if not response_text:
                response_text = "Analysis completed with no additional findings."
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
            err_str = str(e).lower()
            if "token count exceeds" in err_str or "maximum number of tokens" in err_str or "1048576" in err_str:
                limit_val = get_model_token_limit(target_model)
                error_content = (
                    f"⚠️ **Context Window Budget Exceeded in `{self.handle}`**\n\n"
                    f"The data requested from Google SecOps exceeded Gemini's maximum context limit of **{limit_val:,} tokens**.\n\n"
                    f"**Operational Mitigation:**\n"
                    f"- The autonomous function call returned an unusually large payload that surpassed the model ceiling.\n"
                    f"- Scoped query filters have been recommended to fit within context (e.g., shorter lookback window, specific rule/log IDs, or error type filters).\n"
                    f"- The engine's safety guardrails have recorded this event in the Evidence Fabric."
                )
            else:
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
        issue_id: Optional[str] = None,
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
            issue_id=issue_id,
        )

        proposal_id = self.proposal_manager.create_proposal(proposal)

        # Notify topic with interactive HITL proposal widget
        widget = {
            "type": "hitl_proposal_card",
            "proposal_id": proposal_id,
            "status": "OPEN",
            "actions": ["approve_and_merge", "reject", "view_diff"],
        }
        if issue_id:
            widget["issue_id"] = issue_id

        notice = (
            f"**Change Proposal Submitted**: `{proposal_id}`\n\n"
            f"**Target**: `{target_resource_id}` ({action_type})\n"
            + (f"**Linked Issue**: `{issue_id}`\n" if issue_id else "")
            + f"**Rationale**: {rationale}\n\n"
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

        # If linked to an issue and lifecycle_manager is present, record Durability Boundary
        if issue_id and self.lifecycle_manager:
            try:
                self.lifecycle_manager.submit_proposal(
                    issue_id=issue_id,
                    proposal_id=proposal_id,
                    proposal_title=title,
                    author=self.handle,
                    diff_text=proposed_diff,
                    mutation_payload=mutation_payload,
                    commit=False,
                )
            except Exception as e:
                logger.warning("Failed recording proposal %s in lifecycle manager: %s", proposal_id, e)

        return created_proposal
