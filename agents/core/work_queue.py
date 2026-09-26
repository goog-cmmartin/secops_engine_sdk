"""Coordination Plane: Work Queue & Lease Engine for the Autonomous SOC Operating System.

Provides the ephemeral coordination layer:
- Active issues queue (/soc_issues)
- Distributed atomic leasing with lease expiration & heartbeats
- Dynamic capability matching (finding eligible issues for worker agents)
- Worker registration and capability advertising (/soc_workers)
- Attempt tracking across agent lifecycles

Supports dual-mode execution:
1. Live GCP Firestore Backend (Application Default Credentials)
2. Local File Backend (.state/work_queue/)
"""

from abc import ABC, abstractmethod
from datetime import datetime, timedelta, timezone
import json
import logging
import os
from pathlib import Path
import threading
from typing import Any, Callable, Dict, List, Optional, Tuple

from engine.domain import (
    AgentCapabilityProfile,
    AuthorityTier,
    IssueLifecycleStatus,
    IssueSeverity,
    Lease,
    OperationalPlane,
    SOCIssue,
)
from agents.core.evidence_store import normalize_doc_id, sanitize_for_firestore

logger = logging.getLogger(__name__)


# Statuses in which a worker holds the issue. If the lease on such an issue has
# expired, the worker is presumed dead and the issue returns to the pool.
# VALIDATING and later are post-work states and are never reclaimed.
RECLAIMABLE_STATUSES = frozenset({
    IssueLifecycleStatus.LEASED.value,
    IssueLifecycleStatus.CLAIMED.value,
    IssueLifecycleStatus.EXECUTING.value,
})

LEASE_EXPIRED_OUTCOME = "LEASE_EXPIRED"
# Recorded when an operator returns a stuck issue to the pool; resets the retry budget.
OPERATOR_REQUEUED_OUTCOME = "OPERATOR_REQUEUED"

# Dead-end states that no worker will pick up again: an operator has to act.
ATTENTION_STATUSES = frozenset({
    IssueLifecycleStatus.NEEDS_HUMAN.value,
    IssueLifecycleStatus.BLOCKED.value,
    IssueLifecycleStatus.VALIDATION_FAILED.value,
    IssueLifecycleStatus.ROLLED_BACK.value,
})


def is_reclaimable(issue: SOCIssue) -> bool:
    """True when the issue is held by a worker whose lease has lapsed."""
    return issue.status in RECLAIMABLE_STATUSES and (issue.lease is None or issue.lease.is_expired())


def is_claimable(issue: SOCIssue) -> bool:
    """True when a worker may take the issue now."""
    if issue.status == IssueLifecycleStatus.AVAILABLE.value:
        return issue.lease is None or issue.lease.is_expired()
    return is_reclaimable(issue)


def _capabilities_match(issue: SOCIssue, agent_capabilities: Dict[str, int]) -> bool:
    for cap, min_level in issue.routing.requires_capabilities.items():
        if agent_capabilities.get(cap, 0) < min_level:
            return False
    return True


def _expiry_attempt(issue: SOCIssue, now: datetime) -> Dict[str, Any]:
    owner = issue.lease.owner if issue.lease else (issue.routing.claimed_by or "unknown")
    gen = issue.lease.generation if issue.lease else 0
    expires = issue.lease.expires_at if issue.lease else ""
    return {
        "actor": owner,
        "outcome": LEASE_EXPIRED_OUTCOME,
        "timestamp": now.isoformat(),
        "notes": f"Lease generation {gen} expired at {expires} without release; returned to pool.",
    }


class BaseWorkQueue(ABC):
    """Abstract interface for the SOC Operating System Work Queue."""

    @abstractmethod
    def publish_issue(self, issue: SOCIssue) -> str:
        """Publishes an issue to the work queue, making it AVAILABLE for worker agents."""
        pass

    def create_issue(self, issue: SOCIssue) -> str:
        """Alias for publish_issue."""
        return self.publish_issue(issue)


    @abstractmethod
    def get_issue(self, issue_id: str) -> Optional[SOCIssue]:
        """Retrieves an issue by ID."""
        pass

    @abstractmethod
    def list_issues(
        self,
        status: Optional[str] = None,
        plane: Optional[str] = None,
        limit: int = 50,
    ) -> List[SOCIssue]:
        """Lists issues filtered by status and/or plane."""
        pass

    @abstractmethod
    def find_eligible_issues(
        self,
        agent_capabilities: Dict[str, int],
        plane: Optional[str] = None,
        limit: int = 20,
    ) -> List[SOCIssue]:
        """Finds AVAILABLE issues whose required capabilities are met by agent_capabilities."""
        pass

    @abstractmethod
    def acquire_lease(
        self,
        issue_id: str,
        agent_handle: str,
        duration_seconds: int = 300,
    ) -> Optional[Lease]:
        """Atomically acquires a lease on an issue if it is unleased or the previous lease has expired."""
        pass

    @abstractmethod
    def renew_lease(
        self,
        issue_id: str,
        agent_handle: str,
        duration_seconds: int = 300,
    ) -> bool:
        """Extends an existing active lease owned by agent_handle."""
        pass

    @abstractmethod
    def release_lease(
        self,
        issue_id: str,
        agent_handle: Optional[str] = None,
        force: bool = False,
        new_status: str = IssueLifecycleStatus.AVAILABLE.value,
    ) -> bool:
        """Releases the lease on an issue and transitions its status."""
        pass

    @abstractmethod
    def update_issue_status(
        self,
        issue_id: str,
        new_status: str,
        active_proposal_id: Optional[str] = None,
        applied_change_id: Optional[str] = None,
    ) -> bool:
        """Updates the lifecycle status and linked proposal/change pointers of an issue."""
        pass

    @abstractmethod
    def record_attempt(
        self,
        issue_id: str,
        agent_handle: str,
        outcome: str,
        notes: str = "",
    ) -> None:
        """Records an execution attempt on an issue."""
        pass

    @abstractmethod
    def reclaim_expired_leases(self) -> List[str]:
        """Returns issues with lapsed leases to AVAILABLE. Returns reclaimed issue IDs."""
        pass

    @abstractmethod
    def register_worker(self, profile: AgentCapabilityProfile) -> bool:
        """Registers or heartbeats a worker agent and its advertised capabilities."""
        pass

    @abstractmethod
    def get_worker(self, agent_handle: str) -> Optional[AgentCapabilityProfile]:
        """Retrieves a registered worker profile by handle."""
        pass

    @abstractmethod
    def list_workers(self, active_only: bool = True) -> List[AgentCapabilityProfile]:
        """Lists registered worker agents."""
        pass


class LocalWorkQueue(BaseWorkQueue):
    """Local file-backed work queue persisted under .state/work_queue/."""

    def __init__(self, root_dir: Optional[str] = None):
        base = Path(root_dir) if root_dir else Path.cwd()
        self.queue_dir = base / ".state" / "work_queue"
        self.issues_dir = self.queue_dir / "issues"
        self.workers_dir = self.queue_dir / "workers"

        self.issues_dir.mkdir(parents=True, exist_ok=True)
        self.workers_dir.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        logger.info("Initialized LocalWorkQueue at %s", self.queue_dir)

    def _issue_file(self, issue_id: str) -> Path:
        clean = normalize_doc_id(issue_id)
        return self.issues_dir / f"{clean}.json"

    def _worker_file(self, agent_handle: str) -> Path:
        clean = normalize_doc_id(agent_handle)
        return self.workers_dir / f"{clean}.json"

    def publish_issue(self, issue: SOCIssue) -> str:
        with self._lock:
            if not issue.status:
                issue.status = IssueLifecycleStatus.AVAILABLE.value
            if not issue.updated_at:
                issue.updated_at = datetime.now(timezone.utc).isoformat()
            path = self._issue_file(issue.id)
            with open(path, "w", encoding="utf-8") as f:
                json.dump(issue.to_dict(), f, indent=2)
            logger.info("Published issue %s to LocalWorkQueue (status: %s)", issue.id, issue.status)
            return issue.id


    def get_issue(self, issue_id: str) -> Optional[SOCIssue]:
        path = self._issue_file(issue_id)
        if not path.is_file():
            return None
        with self._lock:
            try:
                with open(path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                return SOCIssue.from_dict(data)
            except Exception as e:
                logger.error("Error reading issue %s: %s", issue_id, e)
                return None

    def list_issues(
        self,
        status: Optional[str] = None,
        plane: Optional[str] = None,
        limit: int = 50,
    ) -> List[SOCIssue]:
        results: List[SOCIssue] = []
        with self._lock:
            for p in self.issues_dir.glob("*.json"):
                try:
                    with open(p, "r", encoding="utf-8") as f:
                        data = json.load(f)
                    issue = SOCIssue.from_dict(data)
                    if status and issue.status != status:
                        continue
                    if plane and issue.plane != plane:
                        continue
                    results.append(issue)
                except Exception:
                    continue
        results.sort(key=lambda x: (x.priority_score, x.created_at), reverse=True)
        return results[:limit]

    def find_eligible_issues(
        self,
        agent_capabilities: Dict[str, int],
        plane: Optional[str] = None,
        limit: int = 20,
    ) -> List[SOCIssue]:
        with self._lock:
            candidates = self.list_issues(plane=plane, limit=10_000)
        eligible = [i for i in candidates if is_claimable(i) and _capabilities_match(i, agent_capabilities)]
        eligible.sort(key=lambda x: x.priority_score, reverse=True)
        return eligible[:limit]

    def acquire_lease(
        self,
        issue_id: str,
        agent_handle: str,
        duration_seconds: int = 300,
    ) -> Optional[Lease]:
        with self._lock:
            issue = self.get_issue(issue_id)
            if not issue:
                return None

            now = datetime.now(timezone.utc)
            # Check if currently leased and active
            if issue.lease and not issue.lease.is_expired():
                if issue.lease.owner != agent_handle:
                    logger.debug("Issue %s is already leased to %s", issue_id, issue.lease.owner)
                    return None
            elif not is_claimable(issue):
                logger.debug("Issue %s is not claimable in status %s", issue_id, issue.status)
                return None
            elif is_reclaimable(issue):
                issue.attempts.append(_expiry_attempt(issue, now))

            # Issue is unleased, expired, or already owned by same agent
            expires_at = (now + timedelta(seconds=duration_seconds)).isoformat()
            last_gen = issue.references.get("lease_generation", 0) if isinstance(issue.references, dict) else 0
            current_gen = issue.lease.generation if issue.lease else last_gen
            gen = current_gen + 1
            new_lease = Lease(
                owner=agent_handle,
                acquired_at=now.isoformat(),
                expires_at=expires_at,
                generation=gen,
            )
            issue.lease = new_lease
            if not isinstance(issue.references, dict):
                issue.references = {}
            issue.references["lease_generation"] = gen
            issue.status = IssueLifecycleStatus.LEASED.value
            issue.routing.claimed_by = agent_handle
            issue.routing.claim_timestamp = now.isoformat()
            issue.updated_at = now.isoformat()

            path = self._issue_file(issue.id)
            with open(path, "w", encoding="utf-8") as f:
                json.dump(issue.to_dict(), f, indent=2)

            logger.info("Agent %s acquired lease on %s (gen: %d, expires: %s)", agent_handle, issue_id, gen, expires_at)
            return new_lease

    def renew_lease(
        self,
        issue_id: str,
        agent_handle: str,
        duration_seconds: int = 300,
    ) -> bool:
        with self._lock:
            issue = self.get_issue(issue_id)
            if not issue or not issue.lease:
                return False
            if issue.lease.owner != agent_handle:
                return False
            if issue.lease.is_expired():
                return False

            now = datetime.now(timezone.utc)
            expires_at = (now + timedelta(seconds=duration_seconds)).isoformat()
            issue.lease.expires_at = expires_at
            issue.updated_at = now.isoformat()

            path = self._issue_file(issue.id)
            with open(path, "w", encoding="utf-8") as f:
                json.dump(issue.to_dict(), f, indent=2)

            logger.debug("Renewed lease on %s for %s until %s", issue_id, agent_handle, expires_at)
            return True

    def release_lease(
        self,
        issue_id: str,
        agent_handle: Optional[str] = None,
        force: bool = False,
        new_status: str = IssueLifecycleStatus.AVAILABLE.value,
    ) -> bool:
        with self._lock:
            issue = self.get_issue(issue_id)
            if not issue:
                return False
            if not force and agent_handle and issue.lease and issue.lease.owner != agent_handle:
                logger.warning("Attempted lease release by non-owner %s on %s", agent_handle, issue_id)
                return False

            now = datetime.now(timezone.utc)
            if issue.lease:
                if not isinstance(issue.references, dict):
                    issue.references = {}
                issue.references["lease_generation"] = issue.lease.generation
            issue.lease = None
            issue.status = new_status
            if new_status == IssueLifecycleStatus.AVAILABLE.value:
                issue.routing.claimed_by = None
                issue.routing.claim_timestamp = None
            issue.updated_at = now.isoformat()

            path = self._issue_file(issue.id)
            with open(path, "w", encoding="utf-8") as f:
                json.dump(issue.to_dict(), f, indent=2)

            logger.info("Released lease on %s (new status: %s)", issue_id, new_status)
            return True

    def update_issue_status(
        self,
        issue_id: str,
        new_status: str,
        active_proposal_id: Optional[str] = None,
        applied_change_id: Optional[str] = None,
    ) -> bool:
        with self._lock:
            issue = self.get_issue(issue_id)
            if not issue:
                return False

            now = datetime.now(timezone.utc)
            issue.status = new_status
            issue.updated_at = now.isoformat()
            if active_proposal_id is not None:
                issue.active_proposal_id = active_proposal_id
            if applied_change_id is not None:
                issue.applied_change_id = applied_change_id
            if new_status in (IssueLifecycleStatus.CLOSED.value, IssueLifecycleStatus.VERIFIED.value):
                issue.closed_at = now.isoformat()

            path = self._issue_file(issue.id)
            with open(path, "w", encoding="utf-8") as f:
                json.dump(issue.to_dict(), f, indent=2)

            logger.info("Updated issue %s status to %s", issue_id, new_status)
            return True

    def record_attempt(
        self,
        issue_id: str,
        agent_handle: str,
        outcome: str,
        notes: str = "",
    ) -> None:
        with self._lock:
            issue = self.get_issue(issue_id)
            if not issue:
                return
            now = datetime.now(timezone.utc)
            attempt = {
                "actor": agent_handle,
                "outcome": outcome,
                "timestamp": now.isoformat(),
                "notes": notes,
            }
            issue.attempts.append(attempt)
            issue.updated_at = now.isoformat()
            path = self._issue_file(issue.id)
            with open(path, "w", encoding="utf-8") as f:
                json.dump(issue.to_dict(), f, indent=2)

    def reclaim_expired_leases(self) -> List[str]:
        reclaimed: List[str] = []
        with self._lock:
            for issue in self.list_issues(limit=10_000):
                if not is_reclaimable(issue):
                    continue
                now = datetime.now(timezone.utc)
                issue.attempts.append(_expiry_attempt(issue, now))
                if not isinstance(issue.references, dict):
                    issue.references = {}
                if issue.lease:
                    issue.references["lease_generation"] = issue.lease.generation
                issue.lease = None
                issue.status = IssueLifecycleStatus.AVAILABLE.value
                issue.routing.claimed_by = None
                issue.routing.claim_timestamp = None
                issue.updated_at = now.isoformat()
                with open(self._issue_file(issue.id), "w", encoding="utf-8") as f:
                    json.dump(issue.to_dict(), f, indent=2)
                reclaimed.append(issue.id)
        if reclaimed:
            logger.warning("Reclaimed %d issue(s) with expired leases: %s", len(reclaimed), ", ".join(reclaimed))
        return reclaimed

    def register_worker(self, profile: AgentCapabilityProfile) -> bool:
        with self._lock:
            profile.heartbeat_at = datetime.now(timezone.utc).isoformat()
            path = self._worker_file(profile.agent_handle)
            with open(path, "w", encoding="utf-8") as f:
                json.dump(profile.to_dict(), f, indent=2)
            logger.info("Registered worker profile: %s", profile.agent_handle)
            return True

    def get_worker(self, agent_handle: str) -> Optional[AgentCapabilityProfile]:
        path = self._worker_file(agent_handle)
        if not path.is_file():
            return None
        with self._lock:
            try:
                with open(path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                return AgentCapabilityProfile.from_dict(data)
            except Exception:
                return None

    def list_workers(self, active_only: bool = True) -> List[AgentCapabilityProfile]:
        results: List[AgentCapabilityProfile] = []
        now = datetime.now(timezone.utc)
        with self._lock:
            for p in self.workers_dir.glob("*.json"):
                try:
                    with open(p, "r", encoding="utf-8") as f:
                        data = json.load(f)
                    profile = AgentCapabilityProfile.from_dict(data)
                    if active_only:
                        hb = datetime.fromisoformat(profile.heartbeat_at.replace("Z", "+00:00"))
                        if now - hb > timedelta(minutes=15):
                            continue
                    results.append(profile)
                except Exception:
                    continue
        return results


class FirestoreWorkQueue(BaseWorkQueue):
    """Live GCP Firestore implementation using Application Default Credentials (ADC)."""

    def __init__(self, project_id: str, database_id: str = "(default)"):
        from google.cloud import firestore

        self.project_id = project_id
        self.database_id = database_id
        self.db = firestore.Client(project=project_id, database=database_id)
        self.issues_col = self.db.collection("soc_issues")
        self.workers_col = self.db.collection("soc_workers")
        logger.info("Connected to Firestore Work Queue: %s / %s", project_id, database_id)

    def publish_issue(self, issue: SOCIssue) -> str:
        clean_id = normalize_doc_id(issue.id)
        issue.id = clean_id
        if not issue.status:
            issue.status = IssueLifecycleStatus.AVAILABLE.value
        if not issue.updated_at:
            issue.updated_at = datetime.now(timezone.utc).isoformat()
        payload = sanitize_for_firestore(issue.to_dict())
        self.issues_col.document(clean_id).set(payload)
        logger.info("Published issue %s to FirestoreWorkQueue (status: %s)", clean_id, issue.status)
        return clean_id


    def get_issue(self, issue_id: str) -> Optional[SOCIssue]:
        clean_id = normalize_doc_id(issue_id)
        doc = self.issues_col.document(clean_id).get()
        if not doc.exists:
            return None
        data = doc.to_dict() or {}
        return SOCIssue.from_dict(data)

    def list_issues(
        self,
        status: Optional[str] = None,
        plane: Optional[str] = None,
        limit: int = 50,
    ) -> List[SOCIssue]:
        from google.cloud import firestore
        from google.cloud.firestore_v1.base_query import FieldFilter

        query = self.issues_col
        if status:
            query = query.where(filter=FieldFilter("status", "==", status))
        if plane:
            query = query.where(filter=FieldFilter("plane", "==", plane))

        try:
            query = query.order_by("priority_score", direction=firestore.Query.DESCENDING).limit(limit)
            docs = query.stream()
            return [SOCIssue.from_dict(d.to_dict()) for d in docs]
        except Exception as e:
            logger.warning("Firestore index fallback in list_issues: %s", e)
            all_docs = self.issues_col.limit(limit * 2).stream()
            results = []
            for d in all_docs:
                item = SOCIssue.from_dict(d.to_dict())
                if status and item.status != status:
                    continue
                if plane and item.plane != plane:
                    continue
                results.append(item)
            results.sort(key=lambda x: x.priority_score, reverse=True)
            return results[:limit]

    def find_eligible_issues(
        self,
        agent_capabilities: Dict[str, int],
        plane: Optional[str] = None,
        limit: int = 20,
    ) -> List[SOCIssue]:
        candidates: List[SOCIssue] = []
        for status in (IssueLifecycleStatus.AVAILABLE.value, *sorted(RECLAIMABLE_STATUSES)):
            candidates.extend(self.list_issues(status=status, plane=plane, limit=100))
        eligible = [i for i in candidates if is_claimable(i) and _capabilities_match(i, agent_capabilities)]
        eligible.sort(key=lambda x: x.priority_score, reverse=True)
        return eligible[:limit]

    def acquire_lease(
        self,
        issue_id: str,
        agent_handle: str,
        duration_seconds: int = 300,
    ) -> Optional[Lease]:
        from google.cloud import firestore

        clean_id = normalize_doc_id(issue_id)
        doc_ref = self.issues_col.document(clean_id)

        @firestore.transactional
        def _txn_acquire(transaction: Any) -> Optional[Lease]:
            snapshot = doc_ref.get(transaction=transaction)
            if not snapshot.exists:
                return None
            data = snapshot.to_dict() or {}
            issue = SOCIssue.from_dict(data)

            now = datetime.now(timezone.utc)
            expiry_attempt = None
            if issue.lease and not issue.lease.is_expired():
                if issue.lease.owner != agent_handle:
                    return None
            elif not is_claimable(issue):
                return None
            elif is_reclaimable(issue):
                expiry_attempt = _expiry_attempt(issue, now)

            expires_at = (now + timedelta(seconds=duration_seconds)).isoformat()
            last_gen = issue.references.get("lease_generation", 0) if isinstance(issue.references, dict) else 0
            current_gen = issue.lease.generation if issue.lease else last_gen
            gen = current_gen + 1
            new_lease = Lease(
                owner=agent_handle,
                acquired_at=now.isoformat(),
                expires_at=expires_at,
                generation=gen,
            )

            updates: Dict[str, Any] = {
                "lease": new_lease.to_dict(),
                "references.lease_generation": gen,
                "status": IssueLifecycleStatus.LEASED.value,
                "routing.claimed_by": agent_handle,
                "routing.claim_timestamp": now.isoformat(),
                "updated_at": now.isoformat(),
            }
            if expiry_attempt:
                updates["attempts"] = list(issue.attempts) + [expiry_attempt]
            transaction.update(doc_ref, updates)
            return new_lease

        transaction = self.db.transaction()
        try:
            return _txn_acquire(transaction)
        except Exception as e:
            logger.error("Transaction failed acquiring lease on %s: %s", clean_id, e)
            return None

    def renew_lease(
        self,
        issue_id: str,
        agent_handle: str,
        duration_seconds: int = 300,
    ) -> bool:
        clean_id = normalize_doc_id(issue_id)
        doc = self.issues_col.document(clean_id).get()
        if not doc.exists:
            return False
        data = doc.to_dict() or {}
        issue = SOCIssue.from_dict(data)
        if not issue.lease or issue.lease.owner != agent_handle or issue.lease.is_expired():
            return False

        now = datetime.now(timezone.utc)
        expires_at = (now + timedelta(seconds=duration_seconds)).isoformat()
        self.issues_col.document(clean_id).update(
            {
                "lease.expires_at": expires_at,
                "updated_at": now.isoformat(),
            }
        )
        return True

    def release_lease(
        self,
        issue_id: str,
        agent_handle: Optional[str] = None,
        force: bool = False,
        new_status: str = IssueLifecycleStatus.AVAILABLE.value,
    ) -> bool:
        clean_id = normalize_doc_id(issue_id)
        doc = self.issues_col.document(clean_id).get()
        if not doc.exists:
            return False
        data = doc.to_dict() or {}
        issue = SOCIssue.from_dict(data)
        if not force and agent_handle and issue.lease and issue.lease.owner != agent_handle:
            return False

        now = datetime.now(timezone.utc)
        updates: Dict[str, Any] = {
            "lease": None,
            "status": new_status,
            "updated_at": now.isoformat(),
        }
        if issue.lease:
            updates["references.lease_generation"] = issue.lease.generation
        if new_status == IssueLifecycleStatus.AVAILABLE.value:
            updates["routing.claimed_by"] = None
            updates["routing.claim_timestamp"] = None

        self.issues_col.document(clean_id).update(updates)
        return True

    def update_issue_status(
        self,
        issue_id: str,
        new_status: str,
        active_proposal_id: Optional[str] = None,
        applied_change_id: Optional[str] = None,
    ) -> bool:
        clean_id = normalize_doc_id(issue_id)
        now = datetime.now(timezone.utc)
        updates: Dict[str, Any] = {
            "status": new_status,
            "updated_at": now.isoformat(),
        }
        if active_proposal_id is not None:
            updates["active_proposal_id"] = active_proposal_id
        if applied_change_id is not None:
            updates["applied_change_id"] = applied_change_id
        if new_status in (IssueLifecycleStatus.CLOSED.value, IssueLifecycleStatus.VERIFIED.value):
            updates["closed_at"] = now.isoformat()

        self.issues_col.document(clean_id).update(updates)
        return True

    def record_attempt(
        self,
        issue_id: str,
        agent_handle: str,
        outcome: str,
        notes: str = "",
    ) -> None:
        from google.cloud import firestore

        clean_id = normalize_doc_id(issue_id)
        now = datetime.now(timezone.utc)
        attempt = {
            "actor": agent_handle,
            "outcome": outcome,
            "timestamp": now.isoformat(),
            "notes": notes,
        }
        self.issues_col.document(clean_id).update(
            {
                "attempts": firestore.ArrayUnion([attempt]),
                "updated_at": now.isoformat(),
            }
        )

    def reclaim_expired_leases(self) -> List[str]:
        from google.cloud import firestore

        candidates: List[SOCIssue] = []
        for status in sorted(RECLAIMABLE_STATUSES):
            candidates.extend(self.list_issues(status=status, limit=500))

        reclaimed: List[str] = []
        for candidate in candidates:
            if not is_reclaimable(candidate):
                continue
            doc_ref = self.issues_col.document(normalize_doc_id(candidate.id))

            @firestore.transactional
            def _txn_reclaim(transaction: Any) -> bool:
                snapshot = doc_ref.get(transaction=transaction)
                if not snapshot.exists:
                    return False
                issue = SOCIssue.from_dict(snapshot.to_dict() or {})
                # Re-check inside the transaction: the owner may have renewed meanwhile.
                if not is_reclaimable(issue):
                    return False
                now = datetime.now(timezone.utc)
                updates: Dict[str, Any] = {
                    "lease": None,
                    "status": IssueLifecycleStatus.AVAILABLE.value,
                    "routing.claimed_by": None,
                    "routing.claim_timestamp": None,
                    "updated_at": now.isoformat(),
                    "attempts": list(issue.attempts) + [_expiry_attempt(issue, now)],
                }
                if issue.lease:
                    updates["references.lease_generation"] = issue.lease.generation
                transaction.update(doc_ref, updates)
                return True

            try:
                if _txn_reclaim(self.db.transaction()):
                    reclaimed.append(candidate.id)
            except Exception as e:
                logger.error("Transaction failed reclaiming lease on %s: %s", candidate.id, e)
        if reclaimed:
            logger.warning("Reclaimed %d issue(s) with expired leases: %s", len(reclaimed), ", ".join(reclaimed))
        return reclaimed

    def register_worker(self, profile: AgentCapabilityProfile) -> bool:
        clean_handle = normalize_doc_id(profile.agent_handle)
        profile.heartbeat_at = datetime.now(timezone.utc).isoformat()
        payload = sanitize_for_firestore(profile.to_dict())
        self.workers_col.document(clean_handle).set(payload, merge=True)
        return True

    def get_worker(self, agent_handle: str) -> Optional[AgentCapabilityProfile]:
        clean_handle = normalize_doc_id(agent_handle)
        doc = self.workers_col.document(clean_handle).get()
        if not doc.exists:
            return None
        return AgentCapabilityProfile.from_dict(doc.to_dict() or {})

    def list_workers(self, active_only: bool = True) -> List[AgentCapabilityProfile]:
        now = datetime.now(timezone.utc)
        docs = self.workers_col.stream()
        results: List[AgentCapabilityProfile] = []
        for d in docs:
            data = d.to_dict() or {}
            profile = AgentCapabilityProfile.from_dict(data)
            if active_only:
                try:
                    hb = datetime.fromisoformat(profile.heartbeat_at.replace("Z", "+00:00"))
                    if now - hb > timedelta(minutes=15):
                        continue
                except Exception:
                    continue
            results.append(profile)
        return results


def get_work_queue(
    project_id: Optional[str] = None,
    database_id: Optional[str] = None,
    root_dir: Optional[str] = None,
) -> BaseWorkQueue:
    """Factory creating FirestoreWorkQueue when available, falling back to LocalWorkQueue."""
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
            queue = FirestoreWorkQueue(project_id=resolved_project, database_id=resolved_db)
            queue.issues_col.document("connectivity_check").set(
                {"status": "CONNECTED", "checked_at": datetime.now(timezone.utc).isoformat()},
                merge=True,
            )
            return queue
        except Exception as e:
            logger.warning(
                "Could not connect to Firestore Work Queue (%s / %s). Falling back to LocalWorkQueue: %s",
                resolved_project,
                resolved_db,
                e,
            )

    return LocalWorkQueue(root_dir=resolved_root)
