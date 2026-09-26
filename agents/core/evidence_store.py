"""Evidence Fabric State Store for Google SecOps Multi-Agent Fleet.

Provides a shared blackboard architecture for specialized agents:
- Audit trail & provenance persistence in `evidence`
- Rule telemetry, parsed AST, and decay states in `secops_rules`
- Cross-agent remediation tasks and handoffs in `secops_todos`
- Dynamic per-agent prompt and threshold configurations in `system_configs`

Supports dual-mode execution:
1. Live GCP Firestore Backend (using standard Application Default Credentials)
2. Local File Backend (persisting observed data under `.state/evidence_fabric/`)
"""

import json
import logging
import os
import re
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


def _higher_priority(p1: str, p2: str) -> str:
    """Returns the higher priority level between two priority strings."""
    ranks = {"LOW": 1, "MEDIUM": 2, "HIGH": 3, "CRITICAL": 4}
    r1 = ranks.get(str(p1).upper(), 2)
    r2 = ranks.get(str(p2).upper(), 2)
    return p1.upper() if r1 >= r2 else p2.upper()


def normalize_doc_id(resource_id: str) -> str:
    """Normalizes GCP resource names to short document IDs to prevent odd path segment crashes in Firestore.

    Example:
        'projects/123/locations/us/instances/.../rules/ru_6cb096c8' -> 'ru_6cb096c8'
    """
    if not resource_id:
        return ""
    # Strip any trailing slashes
    clean = resource_id.strip().rstrip("/")
    if "/" in clean:
        clean = clean.split("/")[-1]
    # Replace any invalid characters for Firestore document IDs
    return re.sub(r"[^a-zA-Z0-9_\-\.]", "_", clean)


def sanitize_for_firestore(payload: Any, max_string_len: int = 10000) -> Any:
    """Sanitizes document dictionaries to prevent exceeding Firestore's 1MB limit.

    Truncates long string values and converts non-serializable objects.
    """
    if isinstance(payload, dict):
        sanitized = {}
        for k, v in payload.items():
            # Drop bloated raw cache keys if present
            if k in ("_raw", "_cache", "overview_html", "overviewTemplates", "debugData"):
                continue
            sanitized[k] = sanitize_for_firestore(v, max_string_len)
        return sanitized
    elif isinstance(payload, list):
        return [sanitize_for_firestore(item, max_string_len) for item in payload[:200]]
    elif isinstance(payload, str):
        if len(payload) > max_string_len:
            return payload[:max_string_len] + "... [TRUNCATED]"
        return payload
    elif isinstance(payload, datetime):
        return payload.isoformat()
    return payload


def sanitize_playbook_for_firestore(data: Dict[str, Any]) -> Dict[str, Any]:
    """Sanitizes SOAR playbook data to strictly adhere to Firestore's 1MB limit.

    Strips bloated UI template HTML and designer debug data, and truncates
    string parameters longer than 10,000 characters down to 5,000 characters.
    """
    if not isinstance(data, dict):
        return data
    clean = dict(data)
    clean.pop("overviewTemplates", None)
    clean.pop("debugData", None)
    clean.pop("overview_html", None)
    clean.pop("_raw", None)
    for step in clean.get("steps", []):
        if isinstance(step, dict):
            params = step.get("parameters")
            if isinstance(params, list):
                for p in params:
                    if isinstance(p, dict):
                        val = p.get("value")
                        if isinstance(val, str) and len(val) > 10000:
                            p["value"] = val[:5000] + "... [TRUNCATED FOR FIRESTORE]"
            elif isinstance(params, dict):
                for k, val in params.items():
                    if isinstance(val, str) and len(val) > 10000:
                        params[k] = val[:5000] + "... [TRUNCATED FOR FIRESTORE]"
    return clean


class EvidenceFabricStore(ABC):
    """Abstract interface for the shared multi-agent state store."""

    @abstractmethod
    def record_evidence(
        self,
        agent_handle: str,
        action: str,
        stream: str,
        topic: str,
        prompt: str,
        response: str,
        executed_tools: Optional[List[Dict[str, Any]]] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> str:
        """Records an agent execution, reasoning turn, and live tool provenance."""
        pass

    @abstractmethod
    def list_evidence(self, limit: int = 50) -> List[Dict[str, Any]]:
        """Lists recent evidence records."""
        pass

    @abstractmethod
    def save_rule_state(self, rule_id: str, state_dict: Dict[str, Any]) -> None:
        """Saves or updates rule operational telemetry and analysis sub-state."""
        pass

    @abstractmethod
    def get_rule_state(self, rule_id: str) -> Optional[Dict[str, Any]]:
        """Retrieves rule operational state by ID."""
        pass

    @abstractmethod
    def list_rule_states(
        self,
        filter_fn: Optional[Callable[[Dict[str, Any]], bool]] = None,
        limit: int = 1000,
    ) -> List[Dict[str, Any]]:
        """Lists rule states matching an optional filter."""
        pass

    @abstractmethod
    def batch_save_rule_states(self, states: List[Dict[str, Any]]) -> int:
        """Batch saves or merges multiple rule states into the store."""
        pass

    @abstractmethod
    def save_mitre_assessment(self, assessment_dict: Dict[str, Any]) -> str:
        """Persists a MITRE ATT&CK coverage assessment snapshot."""
        pass

    @abstractmethod
    def get_latest_mitre_assessment(self) -> Optional[Dict[str, Any]]:
        """Retrieves the latest MITRE ATT&CK coverage assessment."""
        pass

    @abstractmethod
    def list_mitre_assessments(self, limit: int = 20) -> List[Dict[str, Any]]:
        """Lists historical MITRE ATT&CK coverage assessments."""
        pass

    @abstractmethod
    def save_todo(self, todo_id: str, task_dict: Dict[str, Any]) -> None:
        """Saves an actionable cross-agent remediation task."""
        pass

    def add_todo(
        self,
        title: str,
        description: str,
        assigned_to: str,
        created_by: str = "",
        priority: str = "MEDIUM",
        **kwargs: Any,
    ) -> Dict[str, Any]:
        """Convenience method to create, save, and return a new todo task."""
        todo_id = f"todo_{int(datetime.now(timezone.utc).timestamp() * 1000)}"
        task = {
            "id": todo_id,
            "title": title,
            "description": description,
            "assigned_to": assigned_to,
            "target_agent": assigned_to,
            "created_by": created_by,
            "priority": priority,
            "status": "PENDING",
            "created_at": datetime.now(timezone.utc).isoformat(),
            **kwargs,
        }
        self.save_todo(todo_id, task)
        return task

    @abstractmethod
    def get_todo(self, todo_id: str) -> Optional[Dict[str, Any]]:
        """Retrieves a specific remediation task by ID."""
        pass

    @abstractmethod
    def list_todos(
        self,
        status: Optional[str] = "PENDING",
        target_agent: Optional[str] = None,
        limit: int = 50,
        assigned_to: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """Lists pending or active remediation tasks."""
        pass

    def upsert_todo(self, todo_id: str, task_dict: Dict[str, Any]) -> Tuple[Dict[str, Any], bool]:
        """Upserts an actionable task bead.

        If a task with todo_id already exists:
        - Increments sighting_count by 1
        - Updates last_seen_at and updated_at
        - Refreshes rationale, action_prompt, and title
        - Elevates priority if incoming task has higher severity
        - Appends to sighting_history (capped at 10)
        - Calls save_todo
        - Returns (updated_task, False)

        If task was RESOLVED and anomaly recurs:
        - Reopens the task with status REOPENED
        - Increments sighting_count
        - Appends regression note to history
        - Returns (updated_task, False)

        If task does not exist:
        - Sets sighting_count = 1
        - Sets created_at and last_seen_at
        - Sets status = PENDING
        - Calls save_todo
        - Returns (task_dict, True)
        """
        clean_id = normalize_doc_id(todo_id)
        now_iso = datetime.now(timezone.utc).isoformat()
        existing = self.get_todo(clean_id)

        if existing:
            merged = dict(existing)
            merged["todo_id"] = clean_id
            curr_status = existing.get("status", "PENDING")

            prev_sightings = int(existing.get("sighting_count") or 1)
            merged["sighting_count"] = prev_sightings + 1
            merged["last_seen_at"] = now_iso
            merged["updated_at"] = now_iso

            if "rationale" in task_dict:
                merged["rationale"] = task_dict["rationale"]
            if "title" in task_dict:
                merged["title"] = task_dict["title"]
            if "action_prompt" in task_dict:
                merged["action_prompt"] = task_dict["action_prompt"]
            if "stream" in task_dict:
                merged["stream"] = task_dict["stream"]
            if "topic" in task_dict:
                merged["topic"] = task_dict["topic"]

            if "priority" in task_dict:
                merged["priority"] = _higher_priority(existing.get("priority", "MEDIUM"), task_dict["priority"])

            if curr_status == "RESOLVED":
                merged["status"] = "REOPENED"
                history_entry = {
                    "action": "reopened_regression",
                    "timestamp": now_iso,
                    "rationale": task_dict.get("rationale", "Anomaly recurred after resolution"),
                }
            else:
                merged["status"] = curr_status
                history_entry = {
                    "action": "corroborated_sighting",
                    "timestamp": now_iso,
                    "sighting": merged["sighting_count"],
                    "priority": merged.get("priority"),
                }

            history = list(existing.get("sighting_history") or [])
            history.append(history_entry)
            merged["sighting_history"] = history[-10:]

            self.save_todo(clean_id, merged)
            return (merged, False)

        new_task = dict(task_dict)
        new_task["todo_id"] = clean_id
        new_task.setdefault("sighting_count", 1)
        new_task.setdefault("status", "PENDING")
        new_task.setdefault("created_at", now_iso)
        new_task["last_seen_at"] = now_iso
        new_task["updated_at"] = now_iso
        new_task["sighting_history"] = [
            {
                "action": "initial_sighting",
                "timestamp": now_iso,
                "priority": new_task.get("priority", "MEDIUM"),
            }
        ]
        self.save_todo(clean_id, new_task)
        return (new_task, True)

    def resolve_todo(self, todo_id: str, reason: str = "") -> Optional[Dict[str, Any]]:
        """Transitions an active task to RESOLVED."""
        clean_id = normalize_doc_id(todo_id)
        task = self.get_todo(clean_id)
        if not task:
            return None
        if task.get("status") in ("PENDING", "IN_PROGRESS", "REOPENED"):
            task["status"] = "RESOLVED"
            now_iso = datetime.now(timezone.utc).isoformat()
            task["resolved_at"] = now_iso
            task["updated_at"] = now_iso
            if reason:
                task["resolution_reason"] = reason
            history = list(task.get("sighting_history") or [])
            history.append({
                "action": "resolved",
                "timestamp": now_iso,
                "reason": reason,
            })
            task["sighting_history"] = history[-10:]
            self.save_todo(clean_id, task)
        return task

    def deduplicate_todos(self) -> Dict[str, int]:
        """Consolidates duplicate open tasks by resource and action type.

        Merges sighting counts, retains earliest created_at and latest last_seen_at,
        and deletes redundant timestamped documents.
        """
        all_tasks = self.list_todos(status=None, limit=1000)
        groups: Dict[Tuple[str, str, str], List[Dict[str, Any]]] = {}

        for task in all_tasks:
            agent = task.get("target_agent", "")
            resource = task.get("target_resource_id", "")
            action = task.get("action_type", "")
            if not resource:
                continue
            key = (agent, resource, action)
            groups.setdefault(key, []).append(task)

        scanned = len(all_tasks)
        consolidated = 0
        deleted = 0

        for key, tasks in groups.items():
            has_timestamp_id = any(bool(re.search(r"_\d{10}$", t.get("todo_id", ""))) for t in tasks)
            if len(tasks) > 1 or has_timestamp_id:
                canonical_task_candidate = next((t for t in tasks if "_active" in t.get("todo_id", "")), None)
                if canonical_task_candidate:
                    canonical_id = canonical_task_candidate["todo_id"]
                else:
                    first_id = tasks[0].get("todo_id", "todo_item")
                    clean_base = re.sub(r"_\d{10}$", "", first_id)
                    canonical_id = f"{clean_base}_active"

                total_sightings = sum(int(t.get("sighting_count") or 1) for t in tasks)
                created_ats = [t.get("created_at") for t in tasks if t.get("created_at")]
                earliest_created = min(created_ats) if created_ats else datetime.now(timezone.utc).isoformat()

                updated_ats = [
                    t.get("last_seen_at") or t.get("updated_at") or t.get("created_at")
                    for t in tasks
                    if (t.get("last_seen_at") or t.get("updated_at") or t.get("created_at"))
                ]
                latest_seen = max(updated_ats) if updated_ats else datetime.now(timezone.utc).isoformat()

                best_prio = "LOW"
                for t in tasks:
                    best_prio = _higher_priority(best_prio, t.get("priority", "MEDIUM"))

                statuses = [t.get("status", "PENDING") for t in tasks]
                if "IN_PROGRESS" in statuses:
                    best_status = "IN_PROGRESS"
                elif "PENDING" in statuses or "REOPENED" in statuses:
                    best_status = "PENDING"
                else:
                    best_status = "RESOLVED"

                most_recent = tasks[-1]
                canonical_task = dict(most_recent)
                canonical_task["todo_id"] = canonical_id
                canonical_task["sighting_count"] = total_sightings
                canonical_task["created_at"] = earliest_created
                canonical_task["last_seen_at"] = latest_seen
                canonical_task["updated_at"] = latest_seen
                canonical_task["priority"] = best_prio
                canonical_task["status"] = best_status

                self.save_todo(canonical_id, canonical_task)

                for t in tasks:
                    tid = t.get("todo_id")
                    if tid and tid != canonical_id:
                        if self.delete_todo(tid):
                            deleted += 1

                consolidated += 1

        return {
            "scanned": scanned,
            "consolidated": consolidated,
            "deleted": deleted,
        }

    @staticmethod
    def _enrich_todo(data: Dict[str, Any]) -> Dict[str, Any]:
        task = dict(data)
        agent = task.get("target_agent", "@secops-dispatcher")
        resource = task.get("target_resource_id") or task.get("target_resource") or ""
        if not resource:
            import re
            text = f"{task.get('title', '')} {task.get('description', '')}"
            m = re.search(r"\b(ru_[a-zA-Z0-9_\-]+|ur_[a-zA-Z0-9_\-]+|feed\-[a-zA-Z0-9_\-]+|[A-Z0-9_]{5,20})\b", text)
            if m:
                resource = m.group(1)
            else:
                resource = "SecOps Resource"
        task["target_resource_id"] = resource

        if "action_prompt" not in task:
            if "decay" in agent:
                task["action_prompt"] = f"{agent} audit rule {resource}"
            elif "tuning" in agent:
                task["action_prompt"] = f"{agent} tune rule {resource}"
            elif "parser" in agent:
                task["action_prompt"] = f"{agent} diagnose unparsed logs for {resource}"
            elif "feed" in agent:
                task["action_prompt"] = f"{agent} audit feeds"
            elif "optimizer" in agent:
                task["action_prompt"] = f"{agent} optimize rule {resource}"
            else:
                task["action_prompt"] = f"{agent} inspect {resource}"
        if "stream" not in task:
            if "parser" in agent or "feed" in agent:
                task["stream"] = "ingestion"
            elif "identity" in agent:
                task["stream"] = "governance"
            else:
                task["stream"] = "detections"
        if "topic" not in task:
            if "decay" in agent:
                task["topic"] = "decay-review"
            elif "tuning" in agent:
                task["topic"] = "tuning-review"
            elif "parser" in agent:
                task["topic"] = "parser-drops"
            elif "feed" in agent:
                task["topic"] = "feed-health"
            elif "optimizer" in agent:
                task["topic"] = "rule-proposals"
            else:
                task["topic"] = "inbox"
        return task

    @abstractmethod
    def delete_todo(self, todo_id: str) -> bool:
        """Deletes a remediation task."""
        pass

    @abstractmethod
    def update_todo_status(
        self,
        todo_id: str,
        status: str,
        resolved_by: Optional[str] = None,
        proposal_id: Optional[str] = None,
        resolution: Optional[str] = None,
        **kwargs: Any,
    ) -> None:
        """Updates the status of a remediation task."""
        pass

    @abstractmethod
    def get_agent_config(self, agent_handle: str) -> Dict[str, Any]:
        """Retrieves dynamic runtime configuration for an agent."""
        pass

    @abstractmethod
    def save_agent_config(self, agent_handle: str, config_dict: Dict[str, Any]) -> None:
        """Saves or updates dynamic runtime configuration for an agent."""
        pass

    @abstractmethod
    def save_iam_audit(self, audit_dict: Dict[str, Any]) -> str:
        """Saves an IAM audit snapshot to the Evidence Fabric."""
        pass

    @abstractmethod
    def get_latest_iam_audit(self, project_id: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """Retrieves the most recent prior IAM audit snapshot."""
        pass

    @abstractmethod
    def list_iam_audits(self, limit: int = 20) -> List[Dict[str, Any]]:
        """Lists historical IAM audit snapshots."""
        pass

    @abstractmethod
    def save_tenant_baseline(self, baseline_dict: Dict[str, Any]) -> str:
        """Saves a tenant configuration baseline snapshot to the Evidence Fabric."""
        pass

    @abstractmethod
    def get_latest_tenant_baseline(self, tenant_id: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """Retrieves the most recent prior tenant configuration baseline snapshot."""
        pass

    @abstractmethod
    def list_tenant_baselines(self, limit: int = 20) -> List[Dict[str, Any]]:
        """Lists historical tenant configuration baseline snapshots."""
        pass

    @abstractmethod
    def save_udm_field_schema(self, field_path: str, schema_dict: Dict[str, Any]) -> None:
        """Saves discovered UDM field schema details and array status to the self-healing cache."""
        pass

    @abstractmethod
    def get_udm_field_schema(self, field_path: str) -> Optional[Dict[str, Any]]:
        """Retrieves cached UDM field schema details if known."""
        pass

    @abstractmethod
    def list_decay_candidates(self, min_dps: int = 0, limit: int = 50) -> List[Dict[str, Any]]:
        """Lists rules ranked by Decay Prioritization Score (DPS) descending."""
        pass

    @abstractmethod
    def generate_rule_embeddings(self, texts: List[str]) -> List[List[float]]:
        """Generates 768-dimensional embeddings for rules using text-embedding-004 with fallback."""
        pass

    @abstractmethod
    def save_playbook_analysis(self, workflow_identifier: str, analysis_dict: Dict[str, Any]) -> None:
        """Saves a SOAR playbook analysis and health audit to the Evidence Fabric."""
        pass

    @abstractmethod
    def get_playbook_analysis(self, workflow_identifier: str) -> Optional[Dict[str, Any]]:
        """Retrieves a stored SOAR playbook analysis by workflow identifier."""
        pass

    @abstractmethod
    def list_playbook_analyses(self, limit: int = 100) -> List[Dict[str, Any]]:
        """Lists stored SOAR playbook analyses."""
        pass

    @abstractmethod
    def save_timestamp_integrity_report(self, report_dict: Any) -> str:
        """Saves a timestamp integrity report, updating latest and appending historical snapshot."""
        pass

    @abstractmethod
    def get_latest_timestamp_integrity(self) -> Optional[Dict[str, Any]]:
        """Retrieves the latest timestamp integrity report."""
        pass

    @abstractmethod
    def list_timestamp_integrity_history(self, limit: int = 50) -> List[Dict[str, Any]]:
        """Lists historical timestamp integrity snapshots."""
        pass

    @abstractmethod
    def save_rule_embeddings(self, rule_id: str, embedding: List[float], metadata: Optional[Dict[str, Any]] = None) -> None:
        """Saves a 768-d vector embedding and metadata for a rule."""
        pass

    @abstractmethod
    def batch_save_rule_embeddings(self, rules_with_embeddings: List[Dict[str, Any]]) -> None:
        """Batch saves vector embeddings and metadata for multiple rules."""
        pass

    @abstractmethod
    def find_similar_rules(self, target_rule_id: str, embedding: Optional[List[float]] = None, limit: int = 6) -> List[Dict[str, Any]]:
        """Finds semantically similar rules using vector search with self-healing fallback."""
        pass

    @abstractmethod
    def save_rule_conflict(self, rule_id: str, conflict_data: Dict[str, Any]) -> None:
        """Saves a rule conflict audit result to the Evidence Fabric."""
        pass

    @abstractmethod
    def get_rule_conflict(self, rule_id: str) -> Optional[Dict[str, Any]]:
        """Retrieves a stored rule conflict audit result by rule ID."""
        pass

    @abstractmethod
    def list_rule_conflicts(self, min_cos: float = 0.0, limit: int = 50) -> List[Dict[str, Any]]:
        """Lists stored rule conflict audit results ranked by highest COS score descending."""
        pass

    @abstractmethod
    def save_rule_audit(self, audit_dict: Dict[str, Any]) -> str:
        """Saves a unified detection rule repository audit snapshot to Evidence Fabric."""
        pass

    @abstractmethod
    def get_latest_rule_audit(self) -> Optional[Dict[str, Any]]:
        """Retrieves the most recent detection rule repository audit snapshot."""
        pass

    @abstractmethod
    def save_log_cost_analysis(self, report_dict: Dict[str, Any]) -> str:
        """Saves a tenant log cost and FinOps optimization snapshot to Evidence Fabric."""
        pass

    @abstractmethod
    def get_latest_log_cost_analysis(self) -> Optional[Dict[str, Any]]:
        """Retrieves the most recent log cost and FinOps analysis report."""
        pass


class FirestoreEvidenceStore(EvidenceFabricStore):
    """Live GCP Firestore implementation using Application Default Credentials (ADC)."""

    def __init__(self, project_id: str, database_id: str = "(default)"):
        from google.cloud import firestore

        self.project_id = project_id
        self.database_id = database_id
        self.db = firestore.Client(project=project_id, database=database_id)
        logger.info("Connected to Firestore Evidence Fabric: %s / %s", project_id, database_id)

    def record_evidence(
        self,
        agent_handle: str,
        action: str,
        stream: str,
        topic: str,
        prompt: str,
        response: str,
        executed_tools: Optional[List[Dict[str, Any]]] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> str:
        from google.cloud import firestore

        executed_tools = executed_tools or []
        metadata = metadata or {}

        doc_ref = self.db.collection("evidence").document()
        payload = {
            "evidence_id": doc_ref.id,
            "agent_handle": agent_handle,
            "action": action,
            "stream": stream,
            "topic": topic,
            "prompt": prompt,
            "response": response,
            "executed_tools": sanitize_for_firestore(executed_tools),
            "metadata": sanitize_for_firestore(metadata),
            "created_at": firestore.SERVER_TIMESTAMP,
        }
        doc_ref.set(sanitize_for_firestore(payload))
        return doc_ref.id

    def list_evidence(self, limit: int = 50) -> List[Dict[str, Any]]:
        from google.cloud import firestore
        docs = self.db.collection("evidence").order_by("created_at", direction=firestore.Query.DESCENDING).limit(limit).stream()
        results = []
        for d in docs:
            data = d.to_dict()
            if "created_at" in data and hasattr(data["created_at"], "isoformat"):
                data["created_at"] = data["created_at"].isoformat()
            results.append(data)
        return results

    def save_rule_state(self, rule_id: str, state_dict: Dict[str, Any]) -> None:
        from google.cloud import firestore

        clean_id = normalize_doc_id(rule_id)
        if not clean_id:
            return

        payload = dict(state_dict)
        payload["rule_id"] = clean_id
        payload["updated_at"] = firestore.SERVER_TIMESTAMP

        self.db.collection("secops_rules").document(clean_id).set(
            sanitize_for_firestore(payload),
            merge=True,
        )

    def get_rule_state(self, rule_id: str) -> Optional[Dict[str, Any]]:
        clean_id = normalize_doc_id(rule_id)
        if not clean_id:
            return None
        doc = self.db.collection("secops_rules").document(clean_id).get()
        return doc.to_dict() if doc.exists else None

    def list_rule_states(
        self,
        filter_fn: Optional[Callable[[Dict[str, Any]], bool]] = None,
        limit: int = 1000,
    ) -> List[Dict[str, Any]]:
        docs = self.db.collection("secops_rules").limit(limit).stream()
        results = [d.to_dict() for d in docs]
        if filter_fn:
            results = [r for r in results if filter_fn(r)]
        return results

    def batch_save_rule_states(self, states: List[Dict[str, Any]], chunk_size: int = 400) -> int:
        from google.cloud import firestore

        if not states:
            return 0
        saved_count = 0
        for i in range(0, len(states), chunk_size):
            chunk = states[i : i + chunk_size]
            batch = self.db.batch()
            for item in chunk:
                rid = item.get("rule_id", "")
                clean_id = normalize_doc_id(rid)
                if not clean_id:
                    continue
                payload = dict(item)
                payload["rule_id"] = clean_id
                payload["updated_at"] = firestore.SERVER_TIMESTAMP
                doc_ref = self.db.collection("secops_rules").document(clean_id)
                batch.set(doc_ref, sanitize_for_firestore(payload), merge=True)
                saved_count += 1
            batch.commit()
        return saved_count

    def save_mitre_assessment(self, assessment_dict: Dict[str, Any]) -> str:
        from google.cloud import firestore

        aid = assessment_dict.get("assessment_id") or f"mitre_assess_{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S_%f')}"
        clean_id = normalize_doc_id(aid)
        payload = dict(assessment_dict)
        payload["assessment_id"] = clean_id
        payload["updated_at"] = firestore.SERVER_TIMESTAMP
        if "created_at" not in payload:
            payload["created_at"] = datetime.now(timezone.utc).isoformat()

        sanitized = sanitize_for_firestore(payload)
        self.db.collection("mitre_assessments").document("latest").set(sanitized, merge=False)
        self.db.collection("mitre_assessments").document(clean_id).set(sanitized, merge=False)
        return clean_id

    def get_latest_mitre_assessment(self) -> Optional[Dict[str, Any]]:
        doc = self.db.collection("mitre_assessments").document("latest").get()
        if doc.exists:
            return doc.to_dict()
        assessments = self.list_mitre_assessments(limit=1)
        return assessments[0] if assessments else None

    def list_mitre_assessments(self, limit: int = 20) -> List[Dict[str, Any]]:
        from google.cloud import firestore

        query = self.db.collection("mitre_assessments").order_by(
            "created_at", direction=firestore.Query.DESCENDING
        ).limit(limit)
        results = []
        for d in query.stream():
            if d.id == "latest":
                continue
            data = d.to_dict()
            if "created_at" in data and hasattr(data["created_at"], "isoformat"):
                data["created_at"] = data["created_at"].isoformat()
            results.append(data)
        return results

    def save_todo(self, todo_id: str, task_dict: Dict[str, Any]) -> None:
        from google.cloud import firestore

        clean_id = normalize_doc_id(todo_id)
        payload = dict(task_dict)
        payload["todo_id"] = clean_id
        payload.setdefault("status", "PENDING")
        payload["updated_at"] = firestore.SERVER_TIMESTAMP

        self.db.collection("secops_todos").document(clean_id).set(
            sanitize_for_firestore(payload),
            merge=True,
        )

    def list_todos(
        self,
        status: Optional[str] = "PENDING",
        target_agent: Optional[str] = None,
        limit: int = 50,
        assigned_to: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        from google.cloud.firestore_v1.base_query import FieldFilter

        agent = target_agent or assigned_to
        query = self.db.collection("secops_todos")
        if status:
            if status == "PENDING":
                query = query.where(filter=FieldFilter("status", "in", ["PENDING", "REOPENED"]))
            else:
                query = query.where(filter=FieldFilter("status", "==", status))
        if agent:
            query = query.where(filter=FieldFilter("target_agent", "==", agent))

        docs = query.limit(limit).stream()
        return [self._enrich_todo(d.to_dict()) for d in docs]

    def get_todo(self, todo_id: str) -> Optional[Dict[str, Any]]:
        clean_id = normalize_doc_id(todo_id)
        doc = self.db.collection("secops_todos").document(clean_id).get()
        return self._enrich_todo(doc.to_dict()) if doc.exists else None

    def delete_todo(self, todo_id: str) -> bool:
        clean_id = normalize_doc_id(todo_id)
        doc_ref = self.db.collection("secops_todos").document(clean_id)
        if doc_ref.get().exists:
            doc_ref.delete()
            return True
        return False

    def update_todo_status(
        self,
        todo_id: str,
        status: str,
        resolved_by: Optional[str] = None,
        proposal_id: Optional[str] = None,
        resolution: Optional[str] = None,
        **kwargs: Any,
    ) -> None:
        from google.cloud import firestore

        clean_id = normalize_doc_id(todo_id)
        updates: Dict[str, Any] = {
            "status": status,
            "updated_at": firestore.SERVER_TIMESTAMP,
        }
        if resolved_by:
            updates["resolved_by"] = resolved_by
        if proposal_id:
            updates["proposal_id"] = proposal_id
        if resolution:
            updates["resolution"] = resolution
        for k, v in kwargs.items():
            if v is not None:
                updates[k] = v

        self.db.collection("secops_todos").document(clean_id).set(updates, merge=True)

    def get_agent_config(self, agent_handle: str) -> Dict[str, Any]:
        clean_handle = normalize_doc_id(agent_handle)
        doc = self.db.collection("system_configs").document(clean_handle).get()
        return doc.to_dict() if doc.exists else {}

    def save_agent_config(self, agent_handle: str, config_dict: Dict[str, Any]) -> None:
        from google.cloud import firestore

        clean_handle = normalize_doc_id(agent_handle)
        payload = dict(config_dict)
        payload["agent_handle"] = agent_handle
        payload["updated_at"] = firestore.SERVER_TIMESTAMP

        self.db.collection("system_configs").document(clean_handle).set(
            sanitize_for_firestore(payload),
            merge=True,
        )

    def save_iam_audit(self, audit_dict: Dict[str, Any]) -> str:
        from google.cloud import firestore

        audit_id = audit_dict.get("audit_id") or f"audit_{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}"
        clean_id = normalize_doc_id(audit_id)
        payload = dict(audit_dict)
        payload["audit_id"] = clean_id
        if "created_at" not in payload:
            payload["created_at"] = firestore.SERVER_TIMESTAMP

        self.db.collection("iam_audits").document(clean_id).set(
            sanitize_for_firestore(payload),
            merge=True,
        )
        return clean_id

    def get_latest_iam_audit(self, project_id: Optional[str] = None) -> Optional[Dict[str, Any]]:
        from google.cloud import firestore

        query = self.db.collection("iam_audits").order_by("created_at", direction=firestore.Query.DESCENDING).limit(20)
        for doc in query.stream():
            data = doc.to_dict()
            if not project_id or data.get("project_id") == project_id:
                return data
        return None

    def list_iam_audits(self, limit: int = 20) -> List[Dict[str, Any]]:
        from google.cloud import firestore

        query = self.db.collection("iam_audits").order_by("created_at", direction=firestore.Query.DESCENDING).limit(limit)
        return [doc.to_dict() for doc in query.stream()]

    def save_tenant_baseline(self, baseline_dict: Dict[str, Any]) -> str:
        from google.cloud import firestore

        baseline_id = baseline_dict.get("snapshot_id") or baseline_dict.get("baseline_id") or f"baseline_{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}"
        clean_id = normalize_doc_id(baseline_id)
        payload = dict(baseline_dict)
        payload["snapshot_id"] = clean_id
        if "created_at" not in payload:
            payload["created_at"] = firestore.SERVER_TIMESTAMP

        self.db.collection("tenant_baselines").document(clean_id).set(
            sanitize_for_firestore(payload),
            merge=True,
        )
        return clean_id

    def get_latest_tenant_baseline(self, tenant_id: Optional[str] = None) -> Optional[Dict[str, Any]]:
        from google.cloud import firestore

        query = self.db.collection("tenant_baselines").order_by("created_at", direction=firestore.Query.DESCENDING).limit(20)
        for doc in query.stream():
            data = doc.to_dict()
            if not tenant_id or data.get("tenant_id") == tenant_id:
                return data
        return None

    def list_tenant_baselines(self, limit: int = 20) -> List[Dict[str, Any]]:
        from google.cloud import firestore

        query = self.db.collection("tenant_baselines").order_by("created_at", direction=firestore.Query.DESCENDING).limit(limit)
        return [doc.to_dict() for doc in query.stream()]

    def save_udm_field_schema(self, field_path: str, schema_dict: Dict[str, Any]) -> None:
        from google.cloud import firestore

        clean_id = normalize_doc_id(field_path)
        payload = dict(schema_dict)
        payload["field_path"] = field_path
        payload["updated_at"] = firestore.SERVER_TIMESTAMP

        self.db.collection("udm_schema").document(clean_id).set(
            sanitize_for_firestore(payload),
            merge=True,
        )

    def get_udm_field_schema(self, field_path: str) -> Optional[Dict[str, Any]]:
        clean_id = normalize_doc_id(field_path)
        if not clean_id:
            return None
        doc = self.db.collection("udm_schema").document(clean_id).get()
        return doc.to_dict() if doc.exists else None

    def list_decay_candidates(self, min_dps: int = 0, limit: int = 50) -> List[Dict[str, Any]]:
        try:
            from google.cloud import firestore
            from google.cloud.firestore_v1.base_query import FieldFilter

            query = self.db.collection("secops_rules")
            if min_dps > 0:
                query = query.where(filter=FieldFilter("dps_score", ">=", min_dps))
            query = query.order_by("dps_score", direction=firestore.Query.DESCENDING).limit(limit)
            return [doc.to_dict() for doc in query.stream()]
        except Exception as e:
            logger.warning("Firestore index or query error for decay candidates, falling back to in-memory sort: %s", e)
            docs = self.db.collection("secops_rules").limit(limit * 2).stream()
            candidates = [d.to_dict() for d in docs]
            filtered = [c for c in candidates if c.get("dps_score", 0) >= min_dps]
            filtered.sort(key=lambda x: x.get("dps_score", 0), reverse=True)
            return filtered[:limit]

    def generate_rule_embeddings(self, texts: List[str]) -> List[List[float]]:
        embeddings: List[List[float]] = []
        batch_size = 50

        try:
            from google import genai
            client = genai.Client()
            for i in range(0, len(texts), batch_size):
                chunk = texts[i:i + batch_size]
                response = client.models.embed_content(
                    model="text-embedding-004",
                    contents=chunk,
                )
                if hasattr(response, "embeddings"):
                    for emb in response.embeddings:
                        embeddings.append(list(getattr(emb, "values", [])))
                else:
                    for c in chunk:
                        embeddings.append(_deterministic_fallback_vector(c))
            if len(embeddings) == len(texts):
                return embeddings
        except Exception as e:
            logger.info("Vertex AI embedding API unavailable (%s), using deterministic fallback vectors.", e)

        return [_deterministic_fallback_vector(t) for t in texts]

    def save_playbook_analysis(self, workflow_identifier: str, analysis_dict: Dict[str, Any]) -> None:
        from google.cloud import firestore

        clean_id = normalize_doc_id(workflow_identifier)
        if not clean_id:
            return

        payload = sanitize_playbook_for_firestore(analysis_dict)
        payload["workflow_identifier"] = clean_id
        payload["updated_at"] = firestore.SERVER_TIMESTAMP

        self.db.collection("soar_playbooks").document(clean_id).set(
            sanitize_for_firestore(payload),
            merge=True,
        )

    def get_playbook_analysis(self, workflow_identifier: str) -> Optional[Dict[str, Any]]:
        clean_id = normalize_doc_id(workflow_identifier)
        if not clean_id:
            return None
        doc = self.db.collection("soar_playbooks").document(clean_id).get()
        return doc.to_dict() if doc.exists else None

    def list_playbook_analyses(self, limit: int = 100) -> List[Dict[str, Any]]:
        from google.cloud import firestore

        docs = self.db.collection("soar_playbooks").order_by("updated_at", direction=firestore.Query.DESCENDING).limit(limit).stream()
        results = []
        for d in docs:
            data = d.to_dict()
            if "updated_at" in data and hasattr(data["updated_at"], "isoformat"):
                data["updated_at"] = data["updated_at"].isoformat()
            if "created_at" in data and hasattr(data["created_at"], "isoformat"):
                data["created_at"] = data["created_at"].isoformat()
            results.append(data)
        return results

    def save_timestamp_integrity_report(self, report_dict: Any) -> str:
        from google.cloud import firestore

        if hasattr(report_dict, "to_dict"):
            report_dict = report_dict.to_dict()
        sanitized = sanitize_for_firestore(report_dict)
        latest_doc = dict(sanitized)
        latest_doc["updated_at"] = firestore.SERVER_TIMESTAMP

        col = self.db.collection("timestamp_integrity")
        # 1. Overwrite latest
        col.document("latest").set(latest_doc, merge=True)
        # 2. Append immutable historical snapshot
        history_doc = dict(sanitized)
        history_doc["created_at"] = firestore.SERVER_TIMESTAMP
        _, doc_ref = col.add(history_doc)
        doc_ref.update({"id": doc_ref.id, "snapshot_id": doc_ref.id})
        return doc_ref.id

    def get_latest_timestamp_integrity(self) -> Optional[Dict[str, Any]]:
        doc = self.db.collection("timestamp_integrity").document("latest").get()
        if not doc.exists:
            return None
        data = doc.to_dict()
        if "updated_at" in data and hasattr(data["updated_at"], "isoformat"):
            data["updated_at"] = data["updated_at"].isoformat()
        if "created_at" in data and hasattr(data["created_at"], "isoformat"):
            data["created_at"] = data["created_at"].isoformat()
        return data

    def list_timestamp_integrity_history(self, limit: int = 50) -> List[Dict[str, Any]]:
        from google.cloud import firestore

        docs = self.db.collection("timestamp_integrity").order_by("created_at", direction=firestore.Query.DESCENDING).limit(limit).stream()
        results = []
        for d in docs:
            if d.id == "latest":
                continue
            data = d.to_dict()
            data["id"] = d.id
            if "updated_at" in data and hasattr(data["updated_at"], "isoformat"):
                data["updated_at"] = data["updated_at"].isoformat()
            if "created_at" in data and hasattr(data["created_at"], "isoformat"):
                data["created_at"] = data["created_at"].isoformat()
            results.append(data)
        return results

    def save_rule_embeddings(self, rule_id: str, embedding: List[float], metadata: Optional[Dict[str, Any]] = None) -> None:
        from google.cloud import firestore
        from google.cloud.firestore_v1.vector import Vector

        clean_id = normalize_doc_id(rule_id)
        if not clean_id:
            return
        payload = dict(metadata or {})
        payload["rule_id"] = clean_id
        if embedding:
            payload["embedding"] = Vector(embedding)
        payload["updated_at"] = firestore.SERVER_TIMESTAMP
        self.db.collection("secops_rules").document(clean_id).set(
            sanitize_for_firestore(payload),
            merge=True,
        )

    def batch_save_rule_embeddings(self, rules_with_embeddings: List[Dict[str, Any]]) -> None:
        from google.cloud import firestore
        from google.cloud.firestore_v1.vector import Vector

        batch_chunk_size = 400
        for i in range(0, len(rules_with_embeddings), batch_chunk_size):
            chunk = rules_with_embeddings[i:i + batch_chunk_size]
            batch = self.db.batch()
            for item in chunk:
                rid = normalize_doc_id(item.get("rule_id", ""))
                if not rid:
                    continue
                payload = dict(item)
                payload["rule_id"] = rid
                emb = payload.get("embedding")
                if emb and isinstance(emb, (list, tuple)):
                    payload["embedding"] = Vector(emb)
                payload["updated_at"] = firestore.SERVER_TIMESTAMP
                doc_ref = self.db.collection("secops_rules").document(rid)
                batch.set(doc_ref, sanitize_for_firestore(payload), merge=True)
            batch.commit()

    def find_similar_rules(self, target_rule_id: str, embedding: Optional[List[float]] = None, limit: int = 6) -> List[Dict[str, Any]]:
        clean_target = normalize_doc_id(target_rule_id)
        query_vec = embedding
        if query_vec is None:
            target_state = self.get_rule_state(clean_target)
            if target_state and target_state.get("embedding"):
                emb_val = target_state["embedding"]
                if hasattr(emb_val, "to_map_value"):
                    query_vec = list(emb_val)
                elif isinstance(emb_val, (list, tuple)):
                    query_vec = list(emb_val)

        if not query_vec:
            logger.info("No embedding vector provided or stored for target rule %s", target_rule_id)
            return []

        rules_ref = self.db.collection("secops_rules")
        similar = []

        try:
            from google.cloud.firestore_v1.vector import Vector
            from google.cloud.firestore_v1.base_vector_query import DistanceMeasure

            vector_query = rules_ref.find_nearest(
                vector_field="embedding",
                query_vector=Vector(query_vec),
                distance_measure=DistanceMeasure.COSINE,
                limit=limit + 10,
            )
            docs = vector_query.get()
            for doc in docs:
                data = doc.to_dict()
                cand_id = data.get("rule_id") or doc.id
                if _is_same_rule_identity(clean_target, cand_id):
                    continue
                cand_emb = data.get("embedding")
                if hasattr(cand_emb, "to_map_value"):
                    cand_vec = list(cand_emb)
                elif isinstance(cand_emb, (list, tuple)):
                    cand_vec = list(cand_emb)
                else:
                    cand_vec = None

                if cand_vec:
                    sim_score = _compute_cosine_similarity(query_vec, cand_vec)
                else:
                    sim_score = 0.5

                data["similarity_score"] = round(max(0.0, min(1.0, sim_score)), 4)
                data["rule_id"] = cand_id
                data["embedding"] = cand_vec
                similar.append(data)
                if len(similar) >= limit:
                    break
            if similar:
                return similar
        except Exception as e:
            logger.info("Firestore vector search query unavailable (%s); falling back to in-memory cosine similarity.", e)

        docs = rules_ref.limit(500).stream()
        scored = []
        for doc in docs:
            data = doc.to_dict()
            cand_id = data.get("rule_id") or doc.id
            if _is_same_rule_identity(clean_target, cand_id):
                continue
            cand_emb = data.get("embedding")
            if not cand_emb:
                continue
            if hasattr(cand_emb, "to_map_value"):
                cand_vec = list(cand_emb)
            elif isinstance(cand_emb, (list, tuple)):
                cand_vec = list(cand_emb)
            else:
                continue
            sim = _compute_cosine_similarity(query_vec, cand_vec)
            data["similarity_score"] = round(max(0.0, min(1.0, sim)), 4)
            data["rule_id"] = cand_id
            data["embedding"] = cand_vec
            scored.append(data)
        scored.sort(key=lambda x: x.get("similarity_score", 0.0), reverse=True)
        return scored[:limit]

    def save_rule_conflict(self, rule_id: str, conflict_data: Dict[str, Any]) -> None:
        from google.cloud import firestore

        clean_id = normalize_doc_id(rule_id)
        if not clean_id:
            return
        payload = dict(conflict_data)
        payload["rule_id"] = clean_id
        payload["updated_at"] = firestore.SERVER_TIMESTAMP
        self.db.collection("rule_conflicts").document(clean_id).set(
            sanitize_for_firestore(payload),
            merge=True,
        )

    def get_rule_conflict(self, rule_id: str) -> Optional[Dict[str, Any]]:
        clean_id = normalize_doc_id(rule_id)
        if not clean_id:
            return None
        doc = self.db.collection("rule_conflicts").document(clean_id).get()
        return doc.to_dict() if doc.exists else None

    def list_rule_conflicts(self, min_cos: float = 0.0, limit: int = 50) -> List[Dict[str, Any]]:
        try:
            from google.cloud import firestore
            from google.cloud.firestore_v1.base_query import FieldFilter

            query = self.db.collection("rule_conflicts")
            if min_cos > 0.0:
                query = query.where(filter=FieldFilter("highest_cos", ">=", min_cos))
            query = query.order_by("highest_cos", direction=firestore.Query.DESCENDING).limit(limit)
            return [doc.to_dict() for doc in query.stream()]
        except Exception as e:
            logger.warning("Firestore index error for rule_conflicts, falling back to in-memory filter/sort: %s", e)
            docs = self.db.collection("rule_conflicts").limit(limit * 2).stream()
            results = [d.to_dict() for d in docs]
            filtered = [r for r in results if r.get("highest_cos", 0.0) >= min_cos]
            filtered.sort(key=lambda x: x.get("highest_cos", 0.0), reverse=True)
            return filtered[:limit]

    def save_rule_audit(self, audit_dict: Dict[str, Any]) -> str:
        audit_id = f"rule_audit_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}"
        doc_data = dict(audit_dict)
        doc_data["audit_id"] = audit_id
        doc_data["saved_at"] = datetime.now(timezone.utc).isoformat()
        sanitized = sanitize_for_firestore(doc_data)
        self.db.collection("rule_audits").document(audit_id).set(sanitized)
        return audit_id

    def get_latest_rule_audit(self) -> Optional[Dict[str, Any]]:
        try:
            from google.cloud import firestore
            docs = (
                self.db.collection("rule_audits")
                .order_by("saved_at", direction=firestore.Query.DESCENDING)
                .limit(1)
                .stream()
            )
            for d in docs:
                return d.to_dict()
        except Exception as e:
            logger.warning("Could not query latest rule audit from Firestore: %s", e)
        return None

    def save_log_cost_analysis(self, report_dict: Dict[str, Any]) -> str:
        cost_id = f"log_cost_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}"
        doc_data = dict(report_dict)
        doc_data["cost_id"] = cost_id
        doc_data["saved_at"] = datetime.now(timezone.utc).isoformat()
        sanitized = sanitize_for_firestore(doc_data)
        # Save historical snapshot
        self.db.collection("log_costs").document(cost_id).set(sanitized)
        # Update point-in-time latest document
        try:
            self.db.collection("log_costs").document("latest").set(sanitized)
        except Exception as e:
            logger.warning("Could not update log_cost/latest in Firestore: %s", e)
        return cost_id

    def get_latest_log_cost_analysis(self) -> Optional[Dict[str, Any]]:
        try:
            doc = self.db.collection("log_costs").document("latest").get()
            if doc.exists:
                return doc.to_dict()
            # Fallback to order by saved_at desc
            from google.cloud import firestore
            docs = (
                self.db.collection("log_costs")
                .order_by("saved_at", direction=firestore.Query.DESCENDING)
                .limit(1)
                .stream()
            )
            for d in docs:
                if d.id != "latest":
                    return d.to_dict()
        except Exception as e:
            logger.warning("Could not query latest log cost analysis from Firestore: %s", e)
        return None


def _compute_cosine_similarity(vec1: List[float], vec2: List[float]) -> float:
    """Computes cosine similarity between two numeric vectors in pure Python."""
    import math

    if not vec1 or not vec2 or len(vec1) != len(vec2):
        return 0.0
    dot_product = sum(a * b for a, b in zip(vec1, vec2))
    norm_a = math.sqrt(sum(a * a for a in vec1))
    norm_b = math.sqrt(sum(b * b for b in vec2))
    if norm_a == 0.0 or norm_b == 0.0:
        return 0.0
    sim = dot_product / (norm_a * norm_b)
    return max(-1.0, min(1.0, float(sim)))


def _is_same_rule_identity(rule_id_a: str, rule_id_b: str) -> bool:
    """Checks whether two rule identifiers represent the same rule identity, ignoring prefix variations.

    E.g. 'ru_6cb096c8...' vs 'ur_6cb096c8...' or 'projects/.../rules/ru_...' vs 'ru_...'
    """
    clean_a = normalize_doc_id(rule_id_a).lower()
    clean_b = normalize_doc_id(rule_id_b).lower()
    if not clean_a or not clean_b:
        return False
    if clean_a == clean_b:
        return True
    core_a = re.sub(r"^(ru_|ur_|rule_)", "", clean_a)
    core_b = re.sub(r"^(ru_|ur_|rule_)", "", clean_b)
    return core_a == core_b


def _deterministic_fallback_vector(text: str, dim: int = 768) -> List[float]:
    """Generates a deterministic normalized 768-d float vector from input string.

    Used when live Vertex AI embedding API quota or endpoint is unavailable.
    """
    import hashlib
    import math

    vec = []
    seed = (text or "empty").encode("utf-8")
    for i in range(dim):
        h = hashlib.sha256(seed + i.to_bytes(4, "big")).digest()
        val = (int.from_bytes(h[:4], "big") / 2147483648.0) - 1.0
        vec.append(val)

    norm = math.sqrt(sum(x * x for x in vec)) or 1.0
    return [round(x / norm, 6) for x in vec]


class LocalFileEvidenceStore(EvidenceFabricStore):
    """Local file-backed implementation persisting observed data under `.state/evidence_fabric/`.

    Used when Firestore is unreachable or offline, ensuring strict compliance with anti-synthetic rules.
    """

    def __init__(self, root_dir: Optional[str] = None, storage_dir: Optional[str] = None, base_dir: Optional[str] = None):
        if base_dir:
            self.base_dir = base_dir
        elif storage_dir:
            self.base_dir = storage_dir
        elif root_dir:
            self.base_dir = os.path.join(root_dir, ".state", "evidence_fabric")
        else:
            self.base_dir = os.path.join(os.getcwd(), ".state", "evidence_fabric")
        os.makedirs(self.base_dir, exist_ok=True)
        for col in ("evidence", "secops_rules", "secops_todos", "system_configs", "iam_audits", "udm_schema", "tenant_baselines", "soar_playbooks", "timestamp_integrity", "rule_conflicts"):
            os.makedirs(os.path.join(self.base_dir, col), exist_ok=True)
        logger.info("Initialized LocalFileEvidenceStore at: %s", self.base_dir)

    def _col_path(self, collection: str, doc_id: str) -> str:
        clean_id = normalize_doc_id(doc_id)
        col_dir = os.path.join(self.base_dir, collection)
        os.makedirs(col_dir, exist_ok=True)
        return os.path.join(col_dir, f"{clean_id}.json")

    def record_evidence(
        self,
        agent_handle: str,
        action: str,
        stream: str,
        topic: str,
        prompt: str,
        response: str,
        executed_tools: Optional[List[Dict[str, Any]]] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> str:
        now_str = datetime.now(timezone.utc).isoformat()
        evidence_id = f"ev_{int(datetime.now(timezone.utc).timestamp() * 1000)}"

        payload = {
            "evidence_id": evidence_id,
            "agent_handle": agent_handle,
            "action": action,
            "stream": stream,
            "topic": topic,
            "prompt": prompt,
            "response": response,
            "executed_tools": sanitize_for_firestore(executed_tools or []),
            "metadata": sanitize_for_firestore(metadata or {}),
            "created_at": now_str,
        }

        path = self._col_path("evidence", evidence_id)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2)
        return evidence_id

    def list_evidence(self, limit: int = 50) -> List[Dict[str, Any]]:
        edir = os.path.join(self.base_dir, "evidence")
        results = []
        if not os.path.exists(edir):
            return results
        for fname in sorted(os.listdir(edir), reverse=True)[:limit]:
            if fname.endswith(".json"):
                with open(os.path.join(edir, fname), "r", encoding="utf-8") as f:
                    results.append(json.load(f))
        return results

    def save_rule_state(self, rule_id: str, state_dict: Dict[str, Any]) -> None:
        clean_id = normalize_doc_id(rule_id)
        if not clean_id:
            return

        path = self._col_path("secops_rules", clean_id)
        existing = self.get_rule_state(clean_id) or {}
        payload = {**existing, **state_dict}
        payload["rule_id"] = clean_id
        payload["updated_at"] = datetime.now(timezone.utc).isoformat()

        with open(path, "w", encoding="utf-8") as f:
            json.dump(sanitize_for_firestore(payload), f, indent=2)

    def get_rule_state(self, rule_id: str) -> Optional[Dict[str, Any]]:
        clean_id = normalize_doc_id(rule_id)
        path = self._col_path("secops_rules", clean_id)
        if not os.path.exists(path):
            return None
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)

    def list_rule_states(
        self,
        filter_fn: Optional[Callable[[Dict[str, Any]], bool]] = None,
        limit: int = 1000,
    ) -> List[Dict[str, Any]]:
        dir_path = os.path.join(self.base_dir, "secops_rules")
        if not os.path.isdir(dir_path):
            return []
        results = []
        for fname in sorted(os.listdir(dir_path))[:limit]:
            if not fname.endswith(".json"):
                continue
            with open(os.path.join(dir_path, fname), "r", encoding="utf-8") as f:
                data = json.load(f)
                if not filter_fn or filter_fn(data):
                    results.append(data)
        return results

    def batch_save_rule_states(self, states: List[Dict[str, Any]]) -> int:
        count = 0
        for item in states:
            rid = item.get("rule_id", "")
            if rid:
                self.save_rule_state(rid, item)
                count += 1
        return count

    def save_mitre_assessment(self, assessment_dict: Dict[str, Any]) -> str:
        aid = assessment_dict.get("assessment_id") or f"mitre_assess_{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S_%f')}"
        clean_id = normalize_doc_id(aid)
        payload = dict(assessment_dict)
        payload["assessment_id"] = clean_id
        if "created_at" not in payload:
            payload["created_at"] = datetime.now(timezone.utc).isoformat()
        payload["updated_at"] = datetime.now(timezone.utc).isoformat()

        sanitized = sanitize_for_firestore(payload)
        # 1. Overwrite latest
        latest_path = self._col_path("mitre_assessments", "latest")
        with open(latest_path, "w", encoding="utf-8") as f:
            json.dump(sanitized, f, indent=2, default=str)
        # 2. Historical snapshot
        path = self._col_path("mitre_assessments", clean_id)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(sanitized, f, indent=2, default=str)
        return clean_id

    def get_latest_mitre_assessment(self) -> Optional[Dict[str, Any]]:
        latest_path = self._col_path("mitre_assessments", "latest")
        if not os.path.exists(latest_path):
            assessments = self.list_mitre_assessments(limit=1)
            return assessments[0] if assessments else None
        with open(latest_path, "r", encoding="utf-8") as f:
            return json.load(f)

    def list_mitre_assessments(self, limit: int = 20) -> List[Dict[str, Any]]:
        col_dir = os.path.join(self.base_dir, "mitre_assessments")
        if not os.path.isdir(col_dir):
            return []
        records = []
        for fname in os.listdir(col_dir):
            if fname.endswith(".json") and fname != "latest.json":
                fpath = os.path.join(col_dir, fname)
                try:
                    with open(fpath, "r", encoding="utf-8") as f:
                        records.append(json.load(f))
                except Exception:
                    pass
        records.sort(key=lambda x: str(x.get("created_at", "") or x.get("timestamp", "")), reverse=True)
        return records[:limit]

    def save_todo(self, todo_id: str, task_dict: Dict[str, Any]) -> None:
        clean_id = normalize_doc_id(todo_id)
        path = self._col_path("secops_todos", clean_id)
        payload = dict(task_dict)
        payload["todo_id"] = clean_id
        payload.setdefault("status", "PENDING")
        payload["updated_at"] = datetime.now(timezone.utc).isoformat()

        with open(path, "w", encoding="utf-8") as f:
            json.dump(sanitize_for_firestore(payload), f, indent=2)

    @staticmethod
    def _enrich_todo(data: Dict[str, Any]) -> Dict[str, Any]:
        task = dict(data)
        agent = task.get("target_agent", "@secops-dispatcher")
        resource = task.get("target_resource_id", "")
        if "action_prompt" not in task:
            if "decay" in agent:
                task["action_prompt"] = f"{agent} audit rule {resource}"
            elif "tuning" in agent:
                task["action_prompt"] = f"{agent} tune rule {resource}"
            elif "parser" in agent:
                task["action_prompt"] = f"{agent} diagnose unparsed logs for {resource}"
            elif "feed" in agent:
                task["action_prompt"] = f"{agent} audit feeds"
            elif "optimizer" in agent:
                task["action_prompt"] = f"{agent} optimize rule {resource}"
            else:
                task["action_prompt"] = f"{agent} inspect {resource}"
        if "stream" not in task:
            if "parser" in agent or "feed" in agent:
                task["stream"] = "ingestion"
            elif "identity" in agent:
                task["stream"] = "governance"
            else:
                task["stream"] = "detections"
        if "topic" not in task:
            if "decay" in agent:
                task["topic"] = "decay-review"
            elif "tuning" in agent:
                task["topic"] = "tuning-review"
            elif "parser" in agent:
                task["topic"] = "parser-drops"
            elif "feed" in agent:
                task["topic"] = "feed-health"
            elif "optimizer" in agent:
                task["topic"] = "rule-proposals"
            else:
                task["topic"] = "inbox"
        return task

    def get_todo(self, todo_id: str) -> Optional[Dict[str, Any]]:
        clean_id = normalize_doc_id(todo_id)
        path = self._col_path("secops_todos", clean_id)
        if not os.path.exists(path):
            return None
        with open(path, "r", encoding="utf-8") as f:
            return self._enrich_todo(json.load(f))

    def list_todos(
        self,
        status: Optional[str] = "PENDING",
        target_agent: Optional[str] = None,
        limit: int = 50,
        assigned_to: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        agent = target_agent or assigned_to
        dir_path = os.path.join(self.base_dir, "secops_todos")
        results = []
        for fname in sorted(os.listdir(dir_path)):
            if not fname.endswith(".json"):
                continue
            with open(os.path.join(dir_path, fname), "r", encoding="utf-8") as f:
                data = json.load(f)
                if status:
                    if status == "PENDING" and data.get("status") not in ("PENDING", "REOPENED"):
                        continue
                    elif status != "PENDING" and data.get("status") != status:
                        continue
                if agent and data.get("target_agent") != agent and data.get("assigned_to") != agent:
                    continue
                results.append(self._enrich_todo(data))
                if len(results) >= limit:
                    break
        return results

    def delete_todo(self, todo_id: str) -> bool:
        clean_id = normalize_doc_id(todo_id)
        path = self._col_path("secops_todos", clean_id)
        if os.path.exists(path):
            os.remove(path)
            return True
        return False

    def update_todo_status(
        self,
        todo_id: str,
        status: str,
        resolved_by: Optional[str] = None,
        proposal_id: Optional[str] = None,
        resolution: Optional[str] = None,
        **kwargs: Any,
    ) -> None:
        clean_id = normalize_doc_id(todo_id)
        path = self._col_path("secops_todos", clean_id)
        if not os.path.exists(path):
            return
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        data["status"] = status
        data["updated_at"] = datetime.now(timezone.utc).isoformat()
        if resolved_by:
            data["resolved_by"] = resolved_by
        if proposal_id:
            data["proposal_id"] = proposal_id
        if resolution:
            data["resolution"] = resolution
        for k, v in kwargs.items():
            if v is not None:
                data[k] = v
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)

    def get_agent_config(self, agent_handle: str) -> Dict[str, Any]:
        clean_handle = normalize_doc_id(agent_handle)
        path = self._col_path("system_configs", clean_handle)
        if not os.path.exists(path):
            return {}
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)

    def save_agent_config(self, agent_handle: str, config_dict: Dict[str, Any]) -> None:
        clean_handle = normalize_doc_id(agent_handle)
        path = self._col_path("system_configs", clean_handle)
        payload = dict(config_dict)
        payload["agent_handle"] = agent_handle
        payload["updated_at"] = datetime.now(timezone.utc).isoformat()
        with open(path, "w", encoding="utf-8") as f:
            json.dump(sanitize_for_firestore(payload), f, indent=2)

    def save_iam_audit(self, audit_dict: Dict[str, Any]) -> str:
        audit_id = audit_dict.get("audit_id") or f"audit_{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}"
        clean_id = normalize_doc_id(audit_id)
        payload = dict(audit_dict)
        payload["audit_id"] = clean_id
        if "created_at" not in payload:
            payload["created_at"] = datetime.now(timezone.utc).isoformat()
        path = self._col_path("iam_audits", clean_id)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(sanitize_for_firestore(payload), f, indent=2, default=str)
        return clean_id

    def get_latest_iam_audit(self, project_id: Optional[str] = None) -> Optional[Dict[str, Any]]:
        audits = self.list_iam_audits(limit=50)
        if project_id:
            audits = [a for a in audits if a.get("project_id") == project_id]
        return audits[0] if audits else None

    def list_iam_audits(self, limit: int = 20) -> List[Dict[str, Any]]:
        col_dir = os.path.join(self.base_dir, "iam_audits")
        if not os.path.isdir(col_dir):
            return []
        audits = []
        for fname in os.listdir(col_dir):
            if fname.endswith(".json"):
                fpath = os.path.join(col_dir, fname)
                try:
                    with open(fpath, "r", encoding="utf-8") as f:
                        data = json.load(f)
                        audits.append(data)
                except Exception:
                    pass
        audits.sort(key=lambda x: str(x.get("created_at", "")), reverse=True)
        return audits[:limit]

    def save_tenant_baseline(self, baseline_dict: Dict[str, Any]) -> str:
        baseline_id = baseline_dict.get("snapshot_id") or baseline_dict.get("baseline_id") or f"baseline_{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S_%f')}"
        clean_id = normalize_doc_id(baseline_id)
        payload = dict(baseline_dict)
        payload["snapshot_id"] = clean_id
        if "created_at" not in payload:
            payload["created_at"] = datetime.now(timezone.utc).isoformat()
        path = self._col_path("tenant_baselines", clean_id)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(sanitize_for_firestore(payload), f, indent=2, default=str)
        return clean_id

    def get_latest_tenant_baseline(self, tenant_id: Optional[str] = None) -> Optional[Dict[str, Any]]:
        baselines = self.list_tenant_baselines(limit=50)
        if tenant_id:
            baselines = [b for b in baselines if b.get("tenant_id") == tenant_id]
        return baselines[0] if baselines else None

    def list_tenant_baselines(self, limit: int = 20) -> List[Dict[str, Any]]:
        col_dir = os.path.join(self.base_dir, "tenant_baselines")
        if not os.path.isdir(col_dir):
            return []
        baselines = []
        for fname in os.listdir(col_dir):
            if fname.endswith(".json"):
                fpath = os.path.join(col_dir, fname)
                try:
                    with open(fpath, "r", encoding="utf-8") as f:
                        data = json.load(f)
                        baselines.append(data)
                except Exception:
                    pass
        baselines.sort(key=lambda x: str(x.get("created_at", "") or x.get("timestamp", "")), reverse=True)
        return baselines[:limit]

    def save_udm_field_schema(self, field_path: str, schema_dict: Dict[str, Any]) -> None:
        clean_id = normalize_doc_id(field_path)
        path = self._col_path("udm_schema", clean_id)
        payload = dict(schema_dict)
        payload["field_path"] = field_path
        payload["updated_at"] = datetime.now(timezone.utc).isoformat()
        with open(path, "w", encoding="utf-8") as f:
            json.dump(sanitize_for_firestore(payload), f, indent=2)

    def get_udm_field_schema(self, field_path: str) -> Optional[Dict[str, Any]]:
        clean_id = normalize_doc_id(field_path)
        path = self._col_path("udm_schema", clean_id)
        if not os.path.exists(path):
            return None
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)

    def list_decay_candidates(self, min_dps: int = 0, limit: int = 50) -> List[Dict[str, Any]]:
        rules = self.list_rule_states(limit=1000)
        filtered = [r for r in rules if r.get("dps_score", 0) >= min_dps]
        filtered.sort(key=lambda x: x.get("dps_score", 0), reverse=True)
        return filtered[:limit]

    def generate_rule_embeddings(self, texts: List[str]) -> List[List[float]]:
        return [_deterministic_fallback_vector(t) for t in texts]

    def save_playbook_analysis(self, workflow_identifier: str, analysis_dict: Dict[str, Any]) -> None:
        clean_id = normalize_doc_id(workflow_identifier)
        if not clean_id:
            return
        path = self._col_path("soar_playbooks", clean_id)
        payload = sanitize_playbook_for_firestore(analysis_dict)
        payload["workflow_identifier"] = clean_id
        payload["updated_at"] = datetime.now(timezone.utc).isoformat()
        with open(path, "w", encoding="utf-8") as f:
            json.dump(sanitize_for_firestore(payload), f, indent=2, default=str)

    def get_playbook_analysis(self, workflow_identifier: str) -> Optional[Dict[str, Any]]:
        clean_id = normalize_doc_id(workflow_identifier)
        if not clean_id:
            return None
        path = self._col_path("soar_playbooks", clean_id)
        if not os.path.exists(path):
            return None
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)

    def list_playbook_analyses(self, limit: int = 100) -> List[Dict[str, Any]]:
        col_dir = os.path.join(self.base_dir, "soar_playbooks")
        if not os.path.isdir(col_dir):
            return []
        analyses = []
        for fname in os.listdir(col_dir):
            if fname.endswith(".json"):
                fpath = os.path.join(col_dir, fname)
                try:
                    with open(fpath, "r", encoding="utf-8") as f:
                        analyses.append(json.load(f))
                except Exception:
                    pass
        analyses.sort(key=lambda x: str(x.get("updated_at", "") or x.get("created_at", "")), reverse=True)
        return analyses[:limit]

    def save_timestamp_integrity_report(self, report_dict: Any) -> str:
        import uuid
        if hasattr(report_dict, "to_dict"):
            report_dict = report_dict.to_dict()
        sanitized = sanitize_for_firestore(report_dict)
        now_str = datetime.now(timezone.utc).isoformat()

        # 1. Overwrite latest
        latest_path = self._col_path("timestamp_integrity", "latest")
        latest_doc = dict(sanitized)
        latest_doc["updated_at"] = now_str
        with open(latest_path, "w", encoding="utf-8") as f:
            json.dump(latest_doc, f, indent=2, default=str)

        # 2. Append history
        hist_id = f"snap_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:6]}"
        hist_path = self._col_path("timestamp_integrity", hist_id)
        hist_doc = dict(sanitized)
        hist_doc["id"] = hist_id
        hist_doc["snapshot_id"] = hist_id
        hist_doc["created_at"] = now_str
        with open(hist_path, "w", encoding="utf-8") as f:
            json.dump(hist_doc, f, indent=2, default=str)
        return hist_id

    def get_latest_timestamp_integrity(self) -> Optional[Dict[str, Any]]:
        latest_path = self._col_path("timestamp_integrity", "latest")
        if not os.path.exists(latest_path):
            return None
        with open(latest_path, "r", encoding="utf-8") as f:
            return json.load(f)

    def list_timestamp_integrity_history(self, limit: int = 50) -> List[Dict[str, Any]]:
        col_dir = os.path.join(self.base_dir, "timestamp_integrity")
        if not os.path.isdir(col_dir):
            return []
        records = []
        for fname in os.listdir(col_dir):
            if fname.endswith(".json") and fname != "latest.json":
                fpath = os.path.join(col_dir, fname)
                try:
                    with open(fpath, "r", encoding="utf-8") as f:
                        records.append(json.load(f))
                except Exception:
                    pass
        records.sort(key=lambda x: str(x.get("created_at", "") or x.get("timestamp", "")), reverse=True)
        return records[:limit]

    def save_rule_embeddings(self, rule_id: str, embedding: List[float], metadata: Optional[Dict[str, Any]] = None) -> None:
        clean_id = normalize_doc_id(rule_id)
        if not clean_id:
            return
        path = self._col_path("secops_rules", clean_id)
        payload = dict(metadata or {})
        payload["rule_id"] = clean_id
        payload["embedding"] = list(embedding) if embedding else []
        payload["updated_at"] = datetime.now(timezone.utc).isoformat()
        if os.path.exists(path):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    existing = json.load(f)
                existing.update(payload)
                payload = existing
            except Exception:
                pass
        with open(path, "w", encoding="utf-8") as f:
            json.dump(sanitize_for_firestore(payload), f, indent=2, default=str)

    def batch_save_rule_embeddings(self, rules_with_embeddings: List[Dict[str, Any]]) -> None:
        for item in rules_with_embeddings:
            rid = item.get("rule_id", "")
            emb = item.get("embedding", [])
            self.save_rule_embeddings(rid, emb, item)

    def find_similar_rules(self, target_rule_id: str, embedding: Optional[List[float]] = None, limit: int = 6) -> List[Dict[str, Any]]:
        clean_target = normalize_doc_id(target_rule_id)
        query_vec = embedding
        if query_vec is None:
            target_state = self.get_rule_state(clean_target)
            if target_state and target_state.get("embedding"):
                query_vec = list(target_state["embedding"])

        if not query_vec:
            logger.info("No embedding vector provided or stored for target rule %s", target_rule_id)
            return []

        col_dir = os.path.join(self.base_dir, "secops_rules")
        if not os.path.isdir(col_dir):
            return []

        scored = []
        for fname in os.listdir(col_dir):
            if not fname.endswith(".json"):
                continue
            fpath = os.path.join(col_dir, fname)
            try:
                with open(fpath, "r", encoding="utf-8") as f:
                    data = json.load(f)
            except Exception:
                continue

            cand_id = data.get("rule_id") or fname[:-5]
            if _is_same_rule_identity(clean_target, cand_id):
                continue
            cand_emb = data.get("embedding")
            if not cand_emb or not isinstance(cand_emb, (list, tuple)):
                continue

            sim = _compute_cosine_similarity(query_vec, list(cand_emb))
            data["similarity_score"] = round(max(0.0, min(1.0, sim)), 4)
            data["rule_id"] = cand_id
            scored.append(data)

        scored.sort(key=lambda x: x.get("similarity_score", 0.0), reverse=True)
        return scored[:limit]

    def save_rule_conflict(self, rule_id: str, conflict_data: Dict[str, Any]) -> None:
        clean_id = normalize_doc_id(rule_id)
        if not clean_id:
            return
        path = self._col_path("rule_conflicts", clean_id)
        payload = dict(conflict_data)
        payload["rule_id"] = clean_id
        payload["updated_at"] = datetime.now(timezone.utc).isoformat()
        with open(path, "w", encoding="utf-8") as f:
            json.dump(sanitize_for_firestore(payload), f, indent=2, default=str)

    def get_rule_conflict(self, rule_id: str) -> Optional[Dict[str, Any]]:
        clean_id = normalize_doc_id(rule_id)
        if not clean_id:
            return None
        path = self._col_path("rule_conflicts", clean_id)
        if not os.path.exists(path):
            return None
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)

    def list_rule_conflicts(self, min_cos: float = 0.0, limit: int = 50) -> List[Dict[str, Any]]:
        col_dir = os.path.join(self.base_dir, "rule_conflicts")
        if not os.path.isdir(col_dir):
            return []
        results = []
        for fname in os.listdir(col_dir):
            if fname.endswith(".json"):
                fpath = os.path.join(col_dir, fname)
                try:
                    with open(fpath, "r", encoding="utf-8") as f:
                        results.append(json.load(f))
                except Exception:
                    pass
        filtered = [r for r in results if r.get("highest_cos", 0.0) >= min_cos]
        filtered.sort(key=lambda x: x.get("highest_cos", 0.0), reverse=True)
        return filtered[:limit]

    def save_rule_audit(self, audit_dict: Dict[str, Any]) -> str:
        audit_id = f"rule_audit_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}"
        doc_data = dict(audit_dict)
        doc_data["audit_id"] = audit_id
        doc_data["saved_at"] = datetime.now(timezone.utc).isoformat()
        path = self._col_path("rule_audits", audit_id)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(sanitize_for_firestore(doc_data), f, indent=2, default=str)
        return audit_id

    def get_latest_rule_audit(self) -> Optional[Dict[str, Any]]:
        col_dir = os.path.join(self.base_dir, "rule_audits")
        if not os.path.isdir(col_dir):
            return None
        files = sorted(
            [f for f in os.listdir(col_dir) if f.endswith(".json")],
            reverse=True,
        )
        if not files:
            return None
        try:
            with open(os.path.join(col_dir, files[0]), "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return None

    def save_log_cost_analysis(self, report_dict: Dict[str, Any]) -> str:
        cost_id = f"log_cost_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}"
        doc_data = dict(report_dict)
        doc_data["cost_id"] = cost_id
        doc_data["saved_at"] = datetime.now(timezone.utc).isoformat()
        path = self._col_path("log_costs", cost_id)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(sanitize_for_firestore(doc_data), f, indent=2, default=str)
        # Update latest.json
        latest_path = self._col_path("log_costs", "latest")
        with open(latest_path, "w", encoding="utf-8") as f:
            json.dump(sanitize_for_firestore(doc_data), f, indent=2, default=str)
        return cost_id

    def get_latest_log_cost_analysis(self) -> Optional[Dict[str, Any]]:
        latest_path = self._col_path("log_costs", "latest")
        if os.path.isfile(latest_path):
            try:
                with open(latest_path, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                pass
        col_dir = os.path.join(self.base_dir, "log_costs")
        if not os.path.isdir(col_dir):
            return None
        files = sorted(
            [f for f in os.listdir(col_dir) if f.endswith(".json") and f != "latest.json"],
            reverse=True,
        )
        if not files:
            return None
        try:
            with open(os.path.join(col_dir, files[0]), "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return None


def diff_iam_audits(prior: Optional[Dict[str, Any]], current: Dict[str, Any]) -> Dict[str, Any]:
    """Compares current IAM audit snapshot with prior run to compute privilege drift."""
    if not prior:
        return {
            "has_drift": False,
            "status": "INITIAL_BASELINE",
            "summary": "Initial IAM audit baseline established in Evidence Fabric.",
            "members_added": [],
            "members_removed": [],
            "custom_roles_added": [],
            "custom_roles_removed": [],
            "permission_changes": [],
        }

    # Compare role bindings
    prior_bindings = {b.get("role"): set(b.get("members", [])) for b in prior.get("chronicle_bindings", []) if isinstance(b, dict)}
    curr_bindings = {b.get("role"): set(b.get("members", [])) for b in current.get("chronicle_bindings", []) if isinstance(b, dict)}

    members_added = []
    members_removed = []

    all_roles = set(prior_bindings.keys()).union(set(curr_bindings.keys()))
    for r in sorted(all_roles):
        p_m = prior_bindings.get(r, set())
        c_m = curr_bindings.get(r, set())
        for m in sorted(c_m - p_m):
            members_added.append({"role": r, "member": m})
        for m in sorted(p_m - c_m):
            members_removed.append({"role": r, "member": m})

    # Compare custom roles
    prior_roles = {r.get("role_name"): set(r.get("chronicle_permissions", [])) for r in prior.get("custom_roles", []) if isinstance(r, dict)}
    curr_roles = {r.get("role_name"): set(r.get("chronicle_permissions", [])) for r in current.get("custom_roles", []) if isinstance(r, dict)}

    roles_added = sorted(set(curr_roles.keys()) - set(prior_roles.keys()))
    roles_removed = sorted(set(prior_roles.keys()) - set(curr_roles.keys()))

    permission_changes = []
    for r_name in sorted(set(prior_roles.keys()).intersection(set(curr_roles.keys()))):
        p_perms = prior_roles[r_name]
        c_perms = curr_roles[r_name]
        added_p = sorted(c_perms - p_perms)
        removed_p = sorted(p_perms - c_perms)
        if added_p or removed_p:
            permission_changes.append({
                "role_name": r_name,
                "permissions_added": added_p,
                "permissions_removed": removed_p,
            })

    has_drift = bool(members_added or members_removed or roles_added or roles_removed or permission_changes)
    drift_items = []
    if members_added:
        drift_items.append(f"{len(members_added)} member(s) granted access")
    if members_removed:
        drift_items.append(f"{len(members_removed)} member(s) revoked")
    if roles_added:
        drift_items.append(f"{len(roles_added)} custom role(s) created")
    if roles_removed:
        drift_items.append(f"{len(roles_removed)} custom role(s) deleted")
    if permission_changes:
        drift_items.append(f"{len(permission_changes)} role(s) permissions modified")

    summary = f"Privilege Drift Detected: {', '.join(drift_items)}" if has_drift else "No privilege drift detected since previous audit."

    return {
        "has_drift": has_drift,
        "status": "DRIFT_DETECTED" if has_drift else "CLEAN",
        "summary": summary,
        "members_added": members_added,
        "members_removed": members_removed,
        "custom_roles_added": roles_added,
        "custom_roles_removed": roles_removed,
        "permission_changes": permission_changes,
        "prior_audit_id": prior.get("audit_id"),
        "prior_timestamp": prior.get("timestamp") or str(prior.get("created_at")),
    }


def compute_tenant_subsystem_hashes(baseline: Dict[str, Any]) -> Dict[str, str]:
    """Computes deterministic SHA256 hashes for each operational subsystem in a baseline."""
    import hashlib
    subsystems = ["instance", "gemini_ai", "ueba_risk", "governance", "soar_settings", "topography"]
    hashes = {}
    for sub in subsystems:
        val = baseline.get(sub, {})
        canonical = json.dumps(val, sort_keys=True, default=str)
        hashes[sub] = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    overall = json.dumps(hashes, sort_keys=True)
    hashes["overall_fingerprint"] = hashlib.sha256(overall.encode("utf-8")).hexdigest()
    return hashes


def diff_tenant_baselines(prior: Optional[Dict[str, Any]], current: Dict[str, Any]) -> Dict[str, Any]:
    """Compares current tenant baseline against a prior snapshot to detect configuration drift."""
    curr_fingerprint = current.get("fingerprint") or compute_tenant_subsystem_hashes(current).get("overall_fingerprint")

    if not prior:
        return {
            "has_drift": False,
            "status": "INITIAL_BASELINE",
            "summary": "Initial tenant configuration baseline established in Evidence Fabric.",
            "drift_count": 0,
            "changes": [],
            "critical_changes_count": 0,
            "high_changes_count": 0,
            "medium_changes_count": 0,
            "low_changes_count": 0,
            "subsystems_drifted": [],
            "current_fingerprint": curr_fingerprint,
            "prior_snapshot_id": None,
            "prior_timestamp": None,
        }

    changes = []

    # 1. Instance Level (Root flags & state)
    p_inst = prior.get("instance", {})
    c_inst = current.get("instance", {})
    for key in ["secops_ui_enabled", "data_rbac_enabled", "triage_agent_enabled", "state", "display_name", "customer_code"]:
        p_val = p_inst.get(key)
        c_val = c_inst.get(key)
        if p_val != c_val:
            sev = "CRITICAL" if key in ("data_rbac_enabled", "secops_ui_enabled") else ("HIGH" if key == "triage_agent_enabled" else "LOW")
            changes.append({
                "subsystem": "instance",
                "parameter": f"instance.{key}",
                "old_value": p_val,
                "new_value": c_val,
                "change_type": "MODIFIED",
                "severity": sev,
            })

    # 2. Gemini AI
    p_ai = prior.get("gemini_ai", {})
    c_ai = current.get("gemini_ai", {})
    if p_ai.get("auto_investigation") != c_ai.get("auto_investigation"):
        changes.append({
            "subsystem": "gemini_ai",
            "parameter": "gemini_ai.auto_investigation",
            "old_value": p_ai.get("auto_investigation"),
            "new_value": c_ai.get("auto_investigation"),
            "change_type": "MODIFIED",
            "severity": "HIGH",
        })
    if p_ai.get("alert_filter") != c_ai.get("alert_filter"):
        changes.append({
            "subsystem": "gemini_ai",
            "parameter": "gemini_ai.alert_filter",
            "old_value": p_ai.get("alert_filter"),
            "new_value": c_ai.get("alert_filter"),
            "change_type": "MODIFIED",
            "severity": "HIGH",
        })
    if p_ai.get("delay") != c_ai.get("delay"):
        changes.append({
            "subsystem": "gemini_ai",
            "parameter": "gemini_ai.delay",
            "old_value": p_ai.get("delay"),
            "new_value": c_ai.get("delay"),
            "change_type": "MODIFIED",
            "severity": "LOW",
        })

    # 3. UEBA Risk
    p_risk = prior.get("ueba_risk", {})
    c_risk = current.get("ueba_risk", {})
    for k in ["detection_score", "alert_score", "weighting_factor", "closed_coefficient"]:
        if p_risk.get(k) != c_risk.get(k):
            changes.append({
                "subsystem": "ueba_risk",
                "parameter": f"ueba_risk.{k}",
                "old_value": p_risk.get(k),
                "new_value": c_risk.get(k),
                "change_type": "MODIFIED",
                "severity": "MEDIUM",
            })

    # 4. Governance (Managed Domains, Pipelines, RBAC)
    p_gov = prior.get("governance", {})
    c_gov = current.get("governance", {})
    
    # Domains
    p_doms = set(p_gov.get("managed_domains", []))
    c_doms = set(c_gov.get("managed_domains", []))
    for d in sorted(c_doms - p_doms):
        changes.append({"subsystem": "governance", "parameter": "managed_domains", "old_value": None, "new_value": d, "change_type": "ADDED", "severity": "MEDIUM"})
    for d in sorted(p_doms - c_doms):
        changes.append({"subsystem": "governance", "parameter": "managed_domains", "old_value": d, "new_value": None, "change_type": "REMOVED", "severity": "HIGH"})

    # Pipelines
    p_pipes = {p.get("name"): p for p in p_gov.get("pipelines", []) if isinstance(p, dict)}
    c_pipes = {p.get("name"): p for p in c_gov.get("pipelines", []) if isinstance(p, dict)}
    for name in sorted(set(c_pipes.keys()) - set(p_pipes.keys())):
        changes.append({"subsystem": "governance", "parameter": f"pipelines.{name}", "old_value": None, "new_value": c_pipes[name], "change_type": "ADDED", "severity": "MEDIUM"})
    for name in sorted(set(p_pipes.keys()) - set(c_pipes.keys())):
        changes.append({"subsystem": "governance", "parameter": f"pipelines.{name}", "old_value": p_pipes[name], "new_value": None, "change_type": "REMOVED", "severity": "HIGH"})

    # RBAC scopes
    p_scopes = {s.get("id"): s for s in p_gov.get("rbac_scopes", []) if isinstance(s, dict)}
    c_scopes = {s.get("id"): s for s in c_gov.get("rbac_scopes", []) if isinstance(s, dict)}
    for sid in sorted(set(c_scopes.keys()) - set(p_scopes.keys())):
        changes.append({"subsystem": "governance", "parameter": f"rbac_scope.{sid}", "old_value": None, "new_value": c_scopes[sid], "change_type": "ADDED", "severity": "MEDIUM"})
    for sid in sorted(set(p_scopes.keys()) - set(c_scopes.keys())):
        changes.append({"subsystem": "governance", "parameter": f"rbac_scope.{sid}", "old_value": p_scopes[sid], "new_value": None, "change_type": "REMOVED", "severity": "CRITICAL"})

    # 5. SOAR Settings
    p_soar = prior.get("soar_settings", {})
    c_soar = current.get("soar_settings", {})

    # Data Retention
    p_ret = p_soar.get("data_retention", {})
    c_ret = c_soar.get("data_retention", {})
    p_months = p_ret.get("DataRetentionPeriodInMonths")
    c_months = c_ret.get("DataRetentionPeriodInMonths")
    if p_months != c_months:
        sev = "CRITICAL" if (c_months and p_months and int(c_months) < int(p_months)) else "MEDIUM"
        changes.append({
            "subsystem": "soar_settings",
            "parameter": "soar.data_retention.DataRetentionPeriodInMonths",
            "old_value": p_months,
            "new_value": c_months,
            "change_type": "MODIFIED",
            "severity": sev,
        })
    if p_ret.get("EnableDataRetentionPerEnvironment") != c_ret.get("EnableDataRetentionPerEnvironment"):
        changes.append({
            "subsystem": "soar_settings",
            "parameter": "soar.data_retention.EnableDataRetentionPerEnvironment",
            "old_value": p_ret.get("EnableDataRetentionPerEnvironment"),
            "new_value": c_ret.get("EnableDataRetentionPerEnvironment"),
            "change_type": "MODIFIED",
            "severity": "HIGH",
        })

    # Support Access
    p_sup = p_soar.get("support_access", {})
    c_sup = c_soar.get("support_access", {})
    p_sup_val = p_sup.get("SupportAccessEnabled", p_sup.get("Enabled"))
    c_sup_val = c_sup.get("SupportAccessEnabled", c_sup.get("Enabled"))
    if p_sup_val != c_sup_val:
        is_active = str(c_sup_val).lower() in ("true", "1")
        sev = "CRITICAL" if is_active else "LOW"
        changes.append({
            "subsystem": "soar_settings",
            "parameter": "soar.support_access.Enabled",
            "old_value": p_sup_val,
            "new_value": c_sup_val,
            "change_type": "MODIFIED",
            "severity": sev,
        })

    # Alert Grouping
    p_ag = p_soar.get("alert_grouping", {})
    c_ag = c_soar.get("alert_grouping", {})
    for ag_key in ["TimeframeForGroupingInHours", "OverflowTimeframeForGroupingInHours", "MaxAGroupingForAlerts", "GroupingAlgorithmType"]:
        if p_ag.get(ag_key) != c_ag.get(ag_key):
            changes.append({
                "subsystem": "soar_settings",
                "parameter": f"soar.alert_grouping.{ag_key}",
                "old_value": p_ag.get(ag_key),
                "new_value": c_ag.get(ag_key),
                "change_type": "MODIFIED",
                "severity": "HIGH",
            })

    # 6. Topography
    p_topo = prior.get("topography", {})
    c_topo = current.get("topography", {})
    
    # Roles
    p_roles = {r.get("id"): r.get("display_name") for r in p_topo.get("roles", []) if isinstance(r, dict)}
    c_roles = {r.get("id"): r.get("display_name") for r in c_topo.get("roles", []) if isinstance(r, dict)}
    for rid in sorted(set(c_roles.keys()) - set(p_roles.keys())):
        changes.append({"subsystem": "topography", "parameter": f"role.{c_roles[rid]}", "old_value": None, "new_value": c_roles[rid], "change_type": "ADDED", "severity": "HIGH"})
    for rid in sorted(set(p_roles.keys()) - set(c_roles.keys())):
        changes.append({"subsystem": "topography", "parameter": f"role.{p_roles[rid]}", "old_value": p_roles[rid], "new_value": None, "change_type": "REMOVED", "severity": "HIGH"})

    # Environments
    p_envs = {e.get("name"): e for e in p_topo.get("environments", []) if isinstance(e, dict)}
    c_envs = {e.get("name"): e for e in c_topo.get("environments", []) if isinstance(e, dict)}
    for ename in sorted(set(c_envs.keys()) - set(p_envs.keys())):
        changes.append({"subsystem": "topography", "parameter": f"environment.{ename}", "old_value": None, "new_value": ename, "change_type": "ADDED", "severity": "HIGH"})
    for ename in sorted(set(p_envs.keys()) - set(c_envs.keys())):
        changes.append({"subsystem": "topography", "parameter": f"environment.{ename}", "old_value": ename, "new_value": None, "change_type": "REMOVED", "severity": "HIGH"})

    # Remote Agents
    p_agents = {a.get("name"): a.get("state") for a in p_topo.get("remote_agents", []) if isinstance(a, dict)}
    c_agents = {a.get("name"): a.get("state") for a in c_topo.get("remote_agents", []) if isinstance(a, dict)}
    for aname in sorted(set(c_agents.keys()) - set(p_agents.keys())):
        changes.append({"subsystem": "topography", "parameter": f"remote_agent.{aname}", "old_value": None, "new_value": c_agents[aname], "change_type": "ADDED", "severity": "MEDIUM"})
    for aname in sorted(set(p_agents.keys()) - set(c_agents.keys())):
        changes.append({"subsystem": "topography", "parameter": f"remote_agent.{aname}", "old_value": p_agents[aname], "new_value": None, "change_type": "REMOVED", "severity": "HIGH"})
    for aname in sorted(set(p_agents.keys()).intersection(set(c_agents.keys()))):
        if p_agents[aname] != c_agents[aname]:
            changes.append({"subsystem": "topography", "parameter": f"remote_agent.{aname}.state", "old_value": p_agents[aname], "new_value": c_agents[aname], "change_type": "MODIFIED", "severity": "MEDIUM"})

    # Summary and counts
    has_drift = len(changes) > 0
    crit_count = sum(1 for c in changes if c["severity"] == "CRITICAL")
    high_count = sum(1 for c in changes if c["severity"] == "HIGH")
    med_count = sum(1 for c in changes if c["severity"] == "MEDIUM")
    low_count = sum(1 for c in changes if c["severity"] == "LOW")
    drifted_subs = sorted(list({c["subsystem"] for c in changes}))

    if not has_drift:
        summary = "No configuration drift detected. Tenant posture matches prior baseline."
    else:
        parts = []
        if crit_count > 0:
            parts.append(f"{crit_count} CRITICAL")
        if high_count > 0:
            parts.append(f"{high_count} HIGH")
        if med_count > 0:
            parts.append(f"{med_count} MEDIUM")
        if low_count > 0:
            parts.append(f"{low_count} LOW")
        summary = f"Configuration Drift Detected: {len(changes)} change(s) across {len(drifted_subs)} subsystem(s) [{', '.join(parts)}]."

    return {
        "has_drift": has_drift,
        "status": "DRIFT_DETECTED" if has_drift else "CLEAN",
        "summary": summary,
        "drift_count": len(changes),
        "critical_changes_count": crit_count,
        "high_changes_count": high_count,
        "medium_changes_count": med_count,
        "low_changes_count": low_count,
        "subsystems_drifted": drifted_subs,
        "changes": changes,
        "current_fingerprint": curr_fingerprint,
        "prior_snapshot_id": prior.get("snapshot_id") or prior.get("audit_id"),
        "prior_timestamp": prior.get("timestamp") or str(prior.get("created_at")),
    }


def get_evidence_store(
    project_id: Optional[str] = None,
    database_id: Optional[str] = None,
    root_dir: Optional[str] = None,
) -> EvidenceFabricStore:
    """Factory creating a FirestoreEvidenceStore when available, falling back to LocalFileEvidenceStore."""
    resolved_root = root_dir or os.getcwd()

    try:
        from engine.config import _load_env_file
        _load_env_file()
    except Exception:
        pass

    resolved_db = database_id or os.getenv("FIRESTORE_DATABASE_ID", "(default)")
    resolved_project = (
        project_id
        or os.getenv("GCP_PROJECT_ID")
        or os.getenv("SECOPS_PROJECT_ID")
        or os.getenv("GOOGLE_CLOUD_PROJECT")
        or os.getenv("GCP_PROJECT")
    )

    # If project not explicitly in env, try reading from gcloud config
    if not resolved_project:
        try:
            import subprocess

            res = subprocess.run(
                ["gcloud", "config", "get-value", "project"],
                capture_output=True,
                text=True,
                timeout=3,
            )
            val = res.stdout.strip()
            if val and " " not in val:
                resolved_project = val
        except Exception:
            pass

    if resolved_project:
        try:
            store = FirestoreEvidenceStore(project_id=resolved_project, database_id=resolved_db)
            # Verify connectivity with a quick light check
            store.db.collection("system_configs").document("connectivity_check").set(
                {"status": "CONNECTED", "checked_at": datetime.now(timezone.utc)},
                merge=True,
            )
            return store
        except Exception as e:
            logger.warning(
                "Could not connect to Firestore (%s / %s). Falling back to LocalFileEvidenceStore: %s",
                resolved_project,
                resolved_db,
                e,
            )

    return LocalFileEvidenceStore(root_dir=resolved_root)
