"""Issue Lifecycle Coordinator for the Autonomous SOC Operating System.

Coordinates state transitions between the ephemeral coordination plane (Firestore)
and the durable evidence plane (Git), ensuring atomic state updates and durability
boundary checkpoints.
"""

from datetime import datetime, timezone
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from engine.domain import (
    AgentCapabilityProfile,
    AuthorityTier,
    ChangeRecord,
    IssueLifecycleStatus,
    IssueSeverity,
    IssueSource,
    Lease,
    OperationalPlane,
    SOCIssue,
    VerificationProof,
)
from agents.core.materializer import IssueMaterializer
from agents.core.work_queue import BaseWorkQueue, get_work_queue

logger = logging.getLogger(__name__)


class SOCLifecycleManager:
    """Orchestrates issue lifecycle state transitions across Firestore and Git."""

    def __init__(
        self,
        work_queue: Optional[BaseWorkQueue] = None,
        materializer: Optional[IssueMaterializer] = None,
        root_dir: Optional[Path] = None,
    ):
        self.root_dir = Path(root_dir) if root_dir else Path.cwd()
        self.work_queue = work_queue or get_work_queue(root_dir=str(self.root_dir))
        self.materializer = materializer or IssueMaterializer()

    def open_issue(
        self,
        issue: SOCIssue,
        deacon_id: Optional[str] = None,
        evidence_files: Optional[Dict[str, Any]] = None,
        commit: bool = True,
    ) -> SOCIssue:
        """Opens a new issue, publishing to the work queue and materializing to Git."""
        if deacon_id:
            if not issue.source:
                issue.source = IssueSource(deacon_id=deacon_id)
            else:
                issue.source.deacon_id = deacon_id
        issue.status = IssueLifecycleStatus.AVAILABLE.value
        clean_id = self.work_queue.publish_issue(issue)
        issue.id = clean_id

        # Durability Boundary 1: ISSUE OPENED
        self.materializer.materialize_issue_opened(
            issue=issue,
            evidence_files=evidence_files,
            commit=commit,
        )
        logger.info("Opened SOC issue: %s (%s)", issue.id, issue.problem.title)
        return issue

    def find_work(
        self,
        agent_capabilities: Dict[str, int],
        plane: Optional[str] = None,
        limit: int = 20,
    ) -> List[SOCIssue]:
        """Queries the work queue for available work matching agent capabilities."""
        return self.work_queue.find_eligible_issues(
            agent_capabilities=agent_capabilities,
            plane=plane,
            limit=limit,
        )

    def claim_issue(
        self,
        issue_id: str,
        agent_handle: str,
        duration_seconds: int = 300,
        commit: bool = False,
    ) -> Optional[Lease]:
        """Claims an issue lease in the coordination plane and appends claim event to Git."""
        lease = self.work_queue.acquire_lease(
            issue_id=issue_id,
            agent_handle=agent_handle,
            duration_seconds=duration_seconds,
        )
        if not lease:
            return None

        # Record claim in durable append ledger
        self.materializer.materialize_claimed(
            issue_id=issue_id,
            agent_handle=agent_handle,
            lease=lease,
            commit=commit,
        )
        return lease

    def heartbeat(
        self,
        issue_id: str,
        agent_handle: str,
        duration_seconds: int = 300,
    ) -> bool:
        """Heartbeat renewal of an active lease in the coordination plane."""
        return self.work_queue.renew_lease(
            issue_id=issue_id,
            agent_handle=agent_handle,
            duration_seconds=duration_seconds,
        )

    def submit_proposal(
        self,
        issue_id: str,
        proposal_id: str,
        proposal_title: str,
        author: str,
        diff_text: str = "",
        mutation_payload: Optional[Dict[str, Any]] = None,
        commit: bool = True,
    ) -> bool:
        """Submits a proposed change, moving status to VALIDATING."""
        updated = self.work_queue.update_issue_status(
            issue_id=issue_id,
            new_status=IssueLifecycleStatus.VALIDATING.value,
            active_proposal_id=proposal_id,
        )
        if not updated:
            return False

        # Durability Boundary 2: PROPOSAL CREATED
        self.materializer.materialize_proposal_created(
            issue_id=issue_id,
            proposal_id=proposal_id,
            proposal_title=proposal_title,
            author=author,
            diff_text=diff_text,
            mutation_payload=mutation_payload,
            commit=commit,
        )
        return True

    def record_validation(
        self,
        issue_id: str,
        validator_actor: str,
        passed: bool,
        diagnostics: List[str],
        test_evidence: Optional[Dict[str, Any]] = None,
        commit: bool = True,
    ) -> bool:
        """Records peer validation results across the durability boundary."""
        target_status = (
            IssueLifecycleStatus.APPROVED.value
            if passed
            else IssueLifecycleStatus.VALIDATION_FAILED.value
        )
        self.work_queue.update_issue_status(
            issue_id=issue_id,
            new_status=target_status,
        )

        # Durability Boundary 3: VALIDATION RECORDED
        self.materializer.materialize_validation_recorded(
            issue_id=issue_id,
            validator_actor=validator_actor,
            passed=passed,
            diagnostics=diagnostics,
            test_evidence=test_evidence,
            commit=commit,
        )
        return True

    def decide_issue(
        self,
        issue_id: str,
        decision: str,  # APPROVED or REJECTED
        approver: str,
        rationale: str = "",
        commit: bool = True,
    ) -> bool:
        """Records human or policy gate decision."""
        target_status = (
            IssueLifecycleStatus.APPROVED.value
            if decision.upper() == "APPROVED"
            else IssueLifecycleStatus.BLOCKED.value
        )
        self.work_queue.update_issue_status(
            issue_id=issue_id,
            new_status=target_status,
        )

        # Durability Boundary 4: DECISION RECORDED
        self.materializer.materialize_decision(
            issue_id=issue_id,
            decision=decision,
            approver=approver,
            rationale=rationale,
            commit=commit,
        )
        return True

    def apply_change(
        self,
        issue_id: str,
        change_record: ChangeRecord,
        commit: bool = True,
    ) -> bool:
        """Applies mutation to production and records change event in Git."""
        self.work_queue.update_issue_status(
            issue_id=issue_id,
            new_status=IssueLifecycleStatus.APPLIED.value,
            applied_change_id=change_record.change_id,
        )

        # Durability Boundary 5: CHANGE APPLIED
        self.materializer.materialize_applied(
            issue_id=issue_id,
            change_record=change_record,
            commit=commit,
        )
        return True

    def verify_and_close(
        self,
        issue_id: str,
        verification: VerificationProof,
        resolution_markdown: str = "",
        commit: bool = True,
    ) -> bool:
        """Records post-deployment verification proof, releases lease, and closes issue."""
        self.work_queue.update_issue_status(
            issue_id=issue_id,
            new_status=IssueLifecycleStatus.CLOSED.value,
        )
        self.work_queue.release_lease(
            issue_id=issue_id,
            agent_handle=verification.verifier_actor,
            force=True,
            new_status=IssueLifecycleStatus.CLOSED.value,
        )

        # Durability Boundary 6: ISSUE VERIFIED & CLOSED
        self.materializer.materialize_verified(
            issue_id=issue_id,
            verification=verification,
            resolution_markdown=resolution_markdown,
            commit=commit,
        )
        logger.info("Successfully verified and closed issue %s", issue_id)
        return True
