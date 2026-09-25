"""SOC Knowledge Store for the Autonomous Google SecOps Multi-Agent Fleet.

Provides institutional state persistence:
- Normalized agent assertions (/soc_observations)
- Cross-agent composite entity dossiers (/soc_entities)
- Historical shift handover briefings (/soc_briefings)
- Posture snapshots and knowledge gaps (/soc_knowledge_snapshots)

Supports dual-mode execution:
1. Live GCP Firestore Backend (using standard Application Default Credentials)
2. Local File Backend (persisting state under `.state/knowledge/`)
"""

from abc import ABC, abstractmethod
from datetime import datetime, timezone
import json
import logging
import os
from pathlib import Path
import threading
from typing import Any, Callable, Dict, List, Optional, Tuple

from engine.domain import (
    CommunicationClass,
    CommunicationPolicy,
    KnowledgeGap,
    KnowledgeSnapshot,
    Observation,
    ObserverRef,
    ShiftBriefing,
    SubjectRef,
)
from agents.core.evidence_store import normalize_doc_id, sanitize_for_firestore

logger = logging.getLogger(__name__)


class BaseKnowledgeStore(ABC):
    """Abstract interface for the SOC Institutional Knowledge Store."""

    @abstractmethod
    def publish_observation(self, observation: Observation) -> str:
        """Publishes an agent observation/assertion to the knowledge store."""
        pass

    def save_observation(self, observation: Observation) -> str:
        """Alias for publish_observation."""
        return self.publish_observation(observation)

    @abstractmethod
    def get_observation(self, observation_id: str) -> Optional[Observation]:
        """Retrieves an observation by ID."""
        pass

    @abstractmethod
    def list_observations(
        self,
        subject_type: Optional[str] = None,
        subject_id: Optional[str] = None,
        predicate: Optional[str] = None,
        agent: Optional[str] = None,
        observer_agent: Optional[str] = None,
        valid_only: bool = True,
        limit: int = 100,
    ) -> List[Observation]:
        """Lists observations matching optional filters."""
        pass


    @abstractmethod
    def get_composite_entity(self, subject_type: str, subject_id: str) -> Dict[str, Any]:
        """Synthesizes all active assertions across disparate agents into a unified entity dossier."""
        pass

    @abstractmethod
    def save_briefing(self, briefing: ShiftBriefing) -> str:
        """Saves a shift briefing record."""
        pass

    @abstractmethod
    def get_latest_briefing(self) -> Optional[ShiftBriefing]:
        """Retrieves the most recent shift briefing."""
        pass

    @abstractmethod
    def list_briefings(self, limit: int = 10) -> List[ShiftBriefing]:
        """Lists recent shift briefings in reverse chronological order."""
        pass

    @abstractmethod
    def save_knowledge_snapshot(self, snapshot: KnowledgeSnapshot) -> str:
        """Saves a SOC knowledge and posture snapshot."""
        pass

    @abstractmethod
    def get_latest_knowledge_snapshot(self) -> Optional[KnowledgeSnapshot]:
        """Retrieves the latest knowledge snapshot."""
        pass


class LocalKnowledgeStore(BaseKnowledgeStore):
    """Local file-based knowledge store persisting to `.state/knowledge/`."""

    def __init__(self, root_dir: Optional[str] = None):
        base = Path(root_dir) if root_dir else Path.cwd()
        self.state_dir = base / ".state" / "knowledge"
        self.obs_dir = self.state_dir / "observations"
        self.briefings_dir = self.state_dir / "briefings"
        self.snapshots_dir = self.state_dir / "snapshots"
        for d in (self.obs_dir, self.briefings_dir, self.snapshots_dir):
            d.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()

    def publish_observation(self, observation: Observation) -> str:
        with self._lock:
            if not observation.observation_id:
                now_str = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
                rnd = os.urandom(3).hex()
                observation.observation_id = f"obs-{now_str}-{rnd}"
            file_path = self.obs_dir / f"{normalize_doc_id(observation.observation_id)}.json"
            data = sanitize_for_firestore(observation.to_dict())
            with open(file_path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, default=str)
            return observation.observation_id

    def get_observation(self, observation_id: str) -> Optional[Observation]:
        with self._lock:
            file_path = self.obs_dir / f"{normalize_doc_id(observation_id)}.json"
            if not file_path.exists():
                return None
            try:
                with open(file_path, "r", encoding="utf-8") as f:
                    return Observation.from_dict(json.load(f))
            except Exception as e:
                logger.error("Failed to load observation %s: %s", observation_id, e)
                return None

    def list_observations(
        self,
        subject_type: Optional[str] = None,
        subject_id: Optional[str] = None,
        predicate: Optional[str] = None,
        agent: Optional[str] = None,
        observer_agent: Optional[str] = None,
        valid_only: bool = True,
        limit: int = 100,
    ) -> List[Observation]:
        with self._lock:
            results: List[Observation] = []
            now = datetime.now(timezone.utc)
            target_agent = observer_agent or agent
            files = sorted(self.obs_dir.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
            for file_path in files:
                try:
                    with open(file_path, "r", encoding="utf-8") as f:
                        obs = Observation.from_dict(json.load(f))
                    if valid_only and obs.is_stale(as_of=now):
                        continue
                    if subject_type and obs.subject.type.lower() != subject_type.lower():
                        continue
                    if subject_id and obs.subject.id.lower() != subject_id.lower():
                        continue
                    if predicate and obs.predicate.lower() != predicate.lower():
                        continue
                    if target_agent and obs.observed_by.agent.lower() != target_agent.lower():
                        continue
                    results.append(obs)
                    if len(results) >= limit:
                        break
                except Exception as e:
                    logger.warning("Error reading observation file %s: %s", file_path, e)
            return results


    def get_composite_entity(self, subject_type: str, subject_id: str) -> Dict[str, Any]:
        with self._lock:
            observations = self.list_observations(
                subject_type=subject_type,
                subject_id=subject_id,
                valid_only=False,
                limit=100,
            )
            return _synthesize_entity_dossier(subject_type, subject_id, observations)

    def save_briefing(self, briefing: ShiftBriefing) -> str:
        with self._lock:
            if not briefing.briefing_id:
                now_str = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
                briefing.briefing_id = f"brief-{now_str}"
            file_path = self.briefings_dir / f"{normalize_doc_id(briefing.briefing_id)}.json"
            data = sanitize_for_firestore(briefing.to_dict())
            with open(file_path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, default=str)
            return briefing.briefing_id

    def get_latest_briefing(self) -> Optional[ShiftBriefing]:
        briefings = self.list_briefings(limit=1)
        return briefings[0] if briefings else None

    def list_briefings(self, limit: int = 10) -> List[ShiftBriefing]:
        with self._lock:
            results: List[ShiftBriefing] = []
            files = sorted(self.briefings_dir.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
            for file_path in files[:limit]:
                try:
                    with open(file_path, "r", encoding="utf-8") as f:
                        results.append(ShiftBriefing.from_dict(json.load(f)))
                except Exception as e:
                    logger.warning("Error reading briefing file %s: %s", file_path, e)
            return results

    def save_knowledge_snapshot(self, snapshot: KnowledgeSnapshot) -> str:
        with self._lock:
            if not snapshot.snapshot_id:
                now_str = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
                snapshot.snapshot_id = f"snap-{now_str}"
            file_path = self.snapshots_dir / f"{normalize_doc_id(snapshot.snapshot_id)}.json"
            data = sanitize_for_firestore(snapshot.to_dict())
            with open(file_path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, default=str)
            return snapshot.snapshot_id

    def get_latest_knowledge_snapshot(self) -> Optional[KnowledgeSnapshot]:
        with self._lock:
            files = sorted(self.snapshots_dir.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
            if not files:
                return None
            try:
                with open(files[0], "r", encoding="utf-8") as f:
                    return KnowledgeSnapshot.from_dict(json.load(f))
            except Exception as e:
                logger.warning("Error reading snapshot file %s: %s", files[0], e)
                return None


class FirestoreKnowledgeStore(BaseKnowledgeStore):
    """Production Firestore-backed knowledge store."""

    def __init__(self, project_id: str, database_id: str = "(default)"):
        from google.cloud import firestore
        self.project_id = project_id
        self.database_id = database_id
        self.db = firestore.Client(project=project_id, database=database_id)
        self.obs_col = self.db.collection("soc_observations")
        self.briefings_col = self.db.collection("soc_briefings")
        self.snapshots_col = self.db.collection("soc_knowledge_snapshots")

    def publish_observation(self, observation: Observation) -> str:
        if not observation.observation_id:
            now_str = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
            rnd = os.urandom(3).hex()
            observation.observation_id = f"obs-{now_str}-{rnd}"
        doc_id = normalize_doc_id(observation.observation_id)
        data = sanitize_for_firestore(observation.to_dict())
        self.obs_col.document(doc_id).set(data)
        return observation.observation_id

    def get_observation(self, observation_id: str) -> Optional[Observation]:
        doc_id = normalize_doc_id(observation_id)
        doc = self.obs_col.document(doc_id).get()
        if not doc.exists:
            return None
        return Observation.from_dict(doc.to_dict())

    def list_observations(
        self,
        subject_type: Optional[str] = None,
        subject_id: Optional[str] = None,
        predicate: Optional[str] = None,
        agent: Optional[str] = None,
        observer_agent: Optional[str] = None,
        valid_only: bool = True,
        limit: int = 100,
    ) -> List[Observation]:
        target_agent = observer_agent or agent
        query = self.obs_col
        if subject_type:
            query = query.where("subject.type", "==", subject_type)
        if subject_id:
            query = query.where("subject.id", "==", subject_id)
        if predicate:
            query = query.where("predicate", "==", predicate)
        if target_agent:
            query = query.where("observed_by.agent", "==", target_agent)


        results: List[Observation] = []
        now = datetime.now(timezone.utc)
        for doc in query.order_by("observed_at", direction="DESCENDING").limit(limit * 2).stream():
            obs = Observation.from_dict(doc.to_dict())
            if valid_only and obs.is_stale(as_of=now):
                continue
            results.append(obs)
            if len(results) >= limit:
                break
        return results

    def get_composite_entity(self, subject_type: str, subject_id: str) -> Dict[str, Any]:
        observations = self.list_observations(
            subject_type=subject_type,
            subject_id=subject_id,
            valid_only=False,
            limit=100,
        )
        return _synthesize_entity_dossier(subject_type, subject_id, observations)

    def save_briefing(self, briefing: ShiftBriefing) -> str:
        if not briefing.briefing_id:
            now_str = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
            briefing.briefing_id = f"brief-{now_str}"
        doc_id = normalize_doc_id(briefing.briefing_id)
        data = sanitize_for_firestore(briefing.to_dict())
        self.briefings_col.document(doc_id).set(data)
        return briefing.briefing_id

    def get_latest_briefing(self) -> Optional[ShiftBriefing]:
        briefings = self.list_briefings(limit=1)
        return briefings[0] if briefings else None

    def list_briefings(self, limit: int = 10) -> List[ShiftBriefing]:
        results: List[ShiftBriefing] = []
        for doc in self.briefings_col.order_by("generated_at", direction="DESCENDING").limit(limit).stream():
            results.append(ShiftBriefing.from_dict(doc.to_dict()))
        return results

    def save_knowledge_snapshot(self, snapshot: KnowledgeSnapshot) -> str:
        if not snapshot.snapshot_id:
            now_str = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
            snapshot.snapshot_id = f"snap-{now_str}"
        doc_id = normalize_doc_id(snapshot.snapshot_id)
        data = sanitize_for_firestore(snapshot.to_dict())
        self.snapshots_col.document(doc_id).set(data)
        return snapshot.snapshot_id

    def get_latest_knowledge_snapshot(self) -> Optional[KnowledgeSnapshot]:
        docs = list(self.snapshots_col.order_by("generated_at", direction="DESCENDING").limit(1).stream())
        if not docs:
            return None
        return KnowledgeSnapshot.from_dict(docs[0].to_dict())


def _synthesize_entity_dossier(
    subject_type: str,
    subject_id: str,
    observations: List[Observation],
) -> Dict[str, Any]:
    """Combines assertions from multiple agents into a unified, authoritative entity dossier."""
    now = datetime.now(timezone.utc)
    active_obs = [o for o in observations if not o.is_stale(as_of=now)]
    contributing_agents = sorted(list({o.observed_by.agent for o in observations}))
    
    facts: Dict[str, Any] = {}
    linked_issues = sorted(list({o.issue_id for o in observations if o.issue_id}))
    evidence_refs: List[str] = []
    
    overall_status = "HEALTHY"
    min_confidence = 1.0
    latest_verified: Optional[str] = None

    for obs in sorted(observations, key=lambda o: o.observed_at):
        facts[obs.predicate] = obs.value
        min_confidence = min(min_confidence, obs.confidence)
        if not latest_verified or obs.observed_at > latest_verified:
            latest_verified = obs.observed_at
        if obs.evidence_refs:
            evidence_refs.extend(obs.evidence_refs)
            
        val = obs.value
        if isinstance(val, dict):
            state = str(val.get("state") or val.get("status") or "").upper()
            if state in ("DEGRADED", "FAILING", "FAILED", "BROKEN"):
                overall_status = "DEGRADED"
            elif state in ("WARNING", "IRREGULAR", "SKEWED") and overall_status != "DEGRADED":
                overall_status = "WARNING"

    if linked_issues and overall_status == "HEALTHY":
        overall_status = "DEGRADED"

    gaps: List[str] = []
    if "business_owner" not in facts and "owner" not in facts:
        gaps.append(f"No business owner registered for {subject_type} {subject_id}")
    if not active_obs and observations:
        gaps.append(f"All observations for {subject_id} are stale (>24h since verification)")
    elif not observations:
        gaps.append(f"No observations recorded for {subject_type} {subject_id}")

    return {
        "subject": {"type": subject_type, "id": subject_id},
        "subject_type": subject_type,
        "subject_id": subject_id,
        "status": overall_status,
        "overall_health": overall_status.lower(),
        "facts": facts,
        "contributing_agents": contributing_agents,
        "total_observations": len(observations),
        "active_observations": len(active_obs),
        "linked_issues": linked_issues,
        "latest_verified": latest_verified,
        "confidence": round(min_confidence, 2) if observations else 0.0,
        "knowledge_gaps": gaps,
        "evidence_refs": sorted(list(set(evidence_refs)))[:10],
    }



_DEFAULT_KNOWLEDGE_STORE: Optional[BaseKnowledgeStore] = None
_STORE_LOCK = threading.RLock()


def get_knowledge_store(
    root_dir: Optional[str] = None,
    force_local: bool = False,
) -> BaseKnowledgeStore:
    """Singleton factory providing the appropriate knowledge store."""
    global _DEFAULT_KNOWLEDGE_STORE
    with _STORE_LOCK:
        if _DEFAULT_KNOWLEDGE_STORE is not None and not force_local:
            return _DEFAULT_KNOWLEDGE_STORE

        project_id = os.environ.get("GOOGLE_CLOUD_PROJECT") or os.environ.get("GCP_PROJECT")
        use_firestore = not force_local and bool(project_id)

        if use_firestore:
            try:
                store = FirestoreKnowledgeStore(project_id=project_id)
                store.snapshots_col.limit(1).get()
                _DEFAULT_KNOWLEDGE_STORE = store
                logger.info("Initialized FirestoreKnowledgeStore for project %s", project_id)
                return store
            except Exception as e:
                logger.warning("Firestore knowledge store unavailable (%s); falling back to LocalKnowledgeStore", e)

        local_store = LocalKnowledgeStore(root_dir=root_dir)
        if not _DEFAULT_KNOWLEDGE_STORE:
            _DEFAULT_KNOWLEDGE_STORE = local_store
        return local_store
