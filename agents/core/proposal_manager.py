"""Gas Town / Beads-inspired Lite Git Change Proposal Engine for SecOps Agents.

Manages autonomous change proposals (.proposals/open, .proposals/merged, .proposals/rejected),
frontmatter serialization, unified diffs, pre-flight verification proofs, and automated merge execution.
"""

from dataclasses import asdict, dataclass, field, is_dataclass
from datetime import datetime, timezone
import json
import logging
import os
from pathlib import Path
import subprocess
from typing import Any, Dict, List, Optional
import yaml

from agents.core.approval_policy import ApprovalPolicyError, check_approval, is_agent_actor, required_tier
from agents.core.git_guard import git_commits_enabled
from agents.core.ledger import resolve_ledger_root
from agents.core.target_baseline import capture_baseline, verify_unchanged

logger = logging.getLogger(__name__)

# Action types that approve_and_merge can write to SecOps. Anything else has no
# executor: merging records the decision and a human must apply the change.
RULE_TEXT_ACTIONS = frozenset({"PATCH_RULE", "UPDATE_RULE_TEXT"})
RULE_DEPLOYMENT_ACTIONS = frozenset({
    "UPDATE_RULE_DEPLOYMENT", "TOGGLE_RULE_DEPLOYMENT", "DEPLOY_RULE", "UNDEPLOY_RULE",
})
EXECUTABLE_ACTIONS = RULE_TEXT_ACTIONS | RULE_DEPLOYMENT_ACTIONS | frozenset({
    "GENERIC_CAPABILITY",
    "CREATE_FINDINGS_REFINEMENT",
})

# ChangeProposal.apply_status values (only meaningful once MERGED).
APPLY_STATUS_APPLIED = "APPLIED"
APPLY_STATUS_MANUAL_REQUIRED = "MANUAL_APPLY_REQUIRED"
APPLY_STATUS_MANUALLY_APPLIED = "MANUALLY_APPLIED"
APPLY_STATUS_ABANDONED = "ABANDONED"
MERGED_MANUAL_APPLY_REQUIRED = "MERGED_MANUAL_APPLY_REQUIRED"

MIN_MANUAL_APPLY_NOTE_LEN = 10


def has_executor(action_type: str) -> bool:
    """True when merging this action type writes the change to SecOps."""
    return (action_type or "").upper() in EXECUTABLE_ACTIONS


def _refinement_query(payload: Dict[str, Any]) -> str:
    """UDM exclusion query from a tuning payload; strips the '//' header in tuned_rule_text."""
    explicit = (payload.get("refinement_query") or "").strip()
    if explicit:
        return explicit
    text = payload.get("tuned_rule_text") or ""
    lines = [ln for ln in text.splitlines() if ln.strip() and not ln.strip().startswith("//")]
    return "\n".join(lines).strip()


def _as_dict(result: Any) -> Dict[str, Any]:
    if isinstance(result, dict):
        return result
    if is_dataclass(result) and not isinstance(result, type):
        return asdict(result)
    return {"result": str(result)}


@dataclass
class PreflightProof:
    """Verification results validating a proposed change before human approval."""
    syntax_verified: bool = False
    compiler_diagnostics: List[str] = field(default_factory=list)
    replay_verified: bool = False
    replay_target_tenant: str = ""
    replay_log_count: int = 0
    replay_summary: str = ""
    details: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ChangeProposal:
    """Represents an agent-generated change proposal requiring Human-In-The-Loop review."""
    id: str
    title: str
    author: str
    subsystem: str
    target_resource_id: str
    action_type: str
    status: str = "OPEN"  # OPEN, MERGED, REJECTED
    risk_level: str = "MEDIUM"  # LOW, MEDIUM, HIGH, CRITICAL
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    merged_at: Optional[str] = None
    merged_by: Optional[str] = None
    merge_commit: Optional[str] = None
    rejection_reason: Optional[str] = None
    approval_note: Optional[str] = None
    required_tier: str = ""
    preflight_override_reason: Optional[str] = None
    # State of the target when the proposal was created; checked before applying.
    base_revision: Optional[Dict[str, Any]] = None
    base_verified_at_merge: Optional[bool] = None
    rationale: str = ""
    proposed_diff: str = ""
    issue_id: Optional[str] = None
    preflight: PreflightProof = field(default_factory=PreflightProof)
    mutation_payload: Dict[str, Any] = field(default_factory=dict)
    # Set on merge: APPLIED (written to SecOps), MANUAL_APPLY_REQUIRED (no executor;
    # a human must apply it), MANUALLY_APPLIED (a human confirmed they applied it),
    # or ABANDONED (a human decided not to apply it; the linked issue goes back to a human).
    apply_status: Optional[str] = None
    applied_by: Optional[str] = None
    applied_at: Optional[str] = None
    apply_note: Optional[str] = None
    abandoned_by: Optional[str] = None
    abandoned_at: Optional[str] = None
    abandon_reason: Optional[str] = None


@dataclass
class MergeResult:
    """Result of applying and merging a proposal."""
    proposal_id: str
    success: bool
    status: str
    execution_result: Any = None
    commit_hash: Optional[str] = None
    inventory_snapshot_triggered: bool = False
    error_message: Optional[str] = None


class ProposalManager:
    """Governs the lifecycle of git-backed change proposals under .proposals/."""

    def __init__(self, root_dir: Optional[Path] = None):
        """Args:
            root_dir: Ledger root. Defaults to ``SECOPS_LEDGER_ROOT`` or
                ``~/.secops/ledger``; must be outside the SDK repository.
        """
        self.root_dir = resolve_ledger_root(root_dir)
        self.proposals_dir = self.root_dir / ".proposals"
        self.open_dir = self.proposals_dir / "open"
        self.merged_dir = self.proposals_dir / "merged"
        self.rejected_dir = self.proposals_dir / "rejected"

        for directory in [self.open_dir, self.merged_dir, self.rejected_dir]:
            directory.mkdir(parents=True, exist_ok=True)

    def _format_markdown(self, proposal: ChangeProposal) -> str:
        """Serializes a proposal into YAML frontmatter and Markdown body."""
        frontmatter = {
            "id": proposal.id,
            "title": proposal.title,
            "author": proposal.author,
            "subsystem": proposal.subsystem,
            "target_resource_id": proposal.target_resource_id,
            "action_type": proposal.action_type,
            "issue_id": proposal.issue_id,
            "status": proposal.status,
            "risk_level": proposal.risk_level,
            "created_at": proposal.created_at,
            "updated_at": proposal.updated_at,
            "merged_at": proposal.merged_at,
            "merged_by": proposal.merged_by,
            "merge_commit": proposal.merge_commit,
            "rejection_reason": proposal.rejection_reason,
            "approval_note": proposal.approval_note,
            "required_tier": proposal.required_tier,
            "preflight_override_reason": proposal.preflight_override_reason,
            "base_revision": proposal.base_revision,
            "base_verified_at_merge": proposal.base_verified_at_merge,
            "preflight": asdict(proposal.preflight),
            "mutation_payload": proposal.mutation_payload,
            "apply_status": proposal.apply_status,
            "applied_by": proposal.applied_by,
            "applied_at": proposal.applied_at,
            "apply_note": proposal.apply_note,
            "abandoned_by": proposal.abandoned_by,
            "abandoned_at": proposal.abandoned_at,
            "abandon_reason": proposal.abandon_reason,
        }

        yaml_text = yaml.dump(frontmatter, sort_keys=False, default_flow_style=False)
        return (
            f"---\n{yaml_text}---\n\n"
            f"# {proposal.title}\n\n"
            f"## Problem Rationale\n{proposal.rationale}\n\n"
            f"## Proposed Unified Diff\n```diff\n{proposal.proposed_diff}\n```\n\n"
            f"## Pre-Flight Verification Proof\n"
            f"- Syntax Verified: {proposal.preflight.syntax_verified}\n"
            f"- Replay Verified: {proposal.preflight.replay_verified}\n"
            f"- Replay Log Count: {proposal.preflight.replay_log_count}\n"
            f"- Replay Summary: {proposal.preflight.replay_summary}\n"
        )

    def _parse_markdown(self, file_path: Path) -> ChangeProposal:
        """Parses a proposal markdown file with YAML frontmatter."""
        content = file_path.read_text(encoding="utf-8")
        if not content.startswith("---"):
            raise ValueError(f"Proposal file {file_path} is missing YAML frontmatter.")

        parts = content.split("---", 2)
        if len(parts) < 3:
            raise ValueError(f"Malformed proposal format in {file_path}.")

        frontmatter = yaml.safe_load(parts[1])
        preflight_data = frontmatter.get("preflight", {})
        preflight = PreflightProof(**preflight_data) if isinstance(preflight_data, dict) else PreflightProof()

        # Extract rationale and diff from markdown body
        body = parts[2]
        rationale = ""
        diff = ""

        if "## Problem Rationale" in body:
            rat_section = body.split("## Problem Rationale")[1]
            if "## Proposed Unified Diff" in rat_section:
                rationale = rat_section.split("## Proposed Unified Diff")[0].strip()
            else:
                rationale = rat_section.strip()

        if "```diff" in body:
            diff_section = body.split("```diff")[1]
            diff = diff_section.split("```")[0].strip()

        status = frontmatter.get("status", "OPEN")
        action_type = frontmatter.get("action_type", "")
        apply_status = frontmatter.get("apply_status")
        if status == "MERGED" and not apply_status:
            # Merged before apply_status existed: action types without an executor
            # were never written to SecOps.
            apply_status = APPLY_STATUS_APPLIED if has_executor(action_type) else APPLY_STATUS_MANUAL_REQUIRED

        return ChangeProposal(
            id=frontmatter.get("id", file_path.stem),
            title=frontmatter.get("title", ""),
            author=frontmatter.get("author", ""),
            subsystem=frontmatter.get("subsystem", ""),
            target_resource_id=frontmatter.get("target_resource_id", ""),
            action_type=frontmatter.get("action_type", ""),
            issue_id=frontmatter.get("issue_id"),
            status=frontmatter.get("status", "OPEN"),
            risk_level=frontmatter.get("risk_level", "MEDIUM"),
            created_at=frontmatter.get("created_at", ""),
            updated_at=frontmatter.get("updated_at", ""),
            merged_at=frontmatter.get("merged_at"),
            merged_by=frontmatter.get("merged_by"),
            merge_commit=frontmatter.get("merge_commit"),
            rejection_reason=frontmatter.get("rejection_reason"),
            approval_note=frontmatter.get("approval_note"),
            required_tier=frontmatter.get("required_tier") or required_tier(
                frontmatter.get("action_type", ""), frontmatter.get("risk_level", "MEDIUM")
            ),
            preflight_override_reason=frontmatter.get("preflight_override_reason"),
            base_revision=frontmatter.get("base_revision"),
            base_verified_at_merge=frontmatter.get("base_verified_at_merge"),
            rationale=rationale,
            proposed_diff=diff,
            preflight=preflight,
            mutation_payload=frontmatter.get("mutation_payload", {}),
            apply_status=apply_status,
            applied_by=frontmatter.get("applied_by"),
            applied_at=frontmatter.get("applied_at"),
            apply_note=frontmatter.get("apply_note"),
            abandoned_by=frontmatter.get("abandoned_by"),
            abandoned_at=frontmatter.get("abandoned_at"),
            abandon_reason=frontmatter.get("abandon_reason"),
        )

    def create_proposal(self, proposal: ChangeProposal, engine: Any = None) -> str:
        """Creates an open proposal file and returns the proposal ID.

        If ``engine`` is given and the proposal has no ``base_revision``, the
        target's current state is captured so approval can detect later edits.
        """
        if not proposal.id:
            timestamp = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
            proposal.id = f"prop-{timestamp}-{proposal.subsystem[:6]}"

        proposal.status = "OPEN"
        # Tier is always derived server-side; agents cannot self-declare a lower one.
        proposal.required_tier = required_tier(proposal.action_type, proposal.risk_level)
        proposal.created_at = datetime.now(timezone.utc).isoformat()
        proposal.updated_at = proposal.created_at
        if proposal.base_revision is None:
            proposal.base_revision = capture_baseline(
                engine, proposal.action_type, proposal.target_resource_id
            )

        target_file = self.open_dir / f"{proposal.id}.md"
        content = self._format_markdown(proposal)
        target_file.write_text(content, encoding="utf-8")
        logger.info("Created proposal %s at %s", proposal.id, target_file)
        return proposal.id

    def update_proposal(self, proposal: ChangeProposal) -> None:
        """Updates an existing proposal file in place (e.g. enriching preflight proofs)."""
        target_file = self.open_dir / f"{proposal.id}.md"
        if not target_file.is_file():
            for d in [self.merged_dir, self.rejected_dir]:
                candidate = d / f"{proposal.id}.md"
                if candidate.is_file():
                    target_file = candidate
                    break
        proposal.updated_at = datetime.now(timezone.utc).isoformat()
        content = self._format_markdown(proposal)
        target_file.write_text(content, encoding="utf-8")
        logger.info("Updated proposal %s at %s", proposal.id, target_file)

    def get_proposal(self, proposal_id: str) -> ChangeProposal:
        """Finds and parses a proposal from open, merged, or rejected directories."""
        for directory in [self.open_dir, self.merged_dir, self.rejected_dir]:
            candidate = directory / f"{proposal_id}.md"
            if candidate.is_file():
                return self._parse_markdown(candidate)

        raise FileNotFoundError(f"Proposal '{proposal_id}' was not found in .proposals/.")

    def list_proposals(
        self,
        status: Optional[str] = None,
        subsystem: Optional[str] = None,
    ) -> List[ChangeProposal]:
        """Lists proposals matching the specified status and subsystem filters."""
        directories = []
        if status:
            st = status.upper()
            if st == "OPEN":
                directories = [self.open_dir]
            elif st == "MERGED":
                directories = [self.merged_dir]
            elif st == "REJECTED":
                directories = [self.rejected_dir]
        else:
            directories = [self.open_dir, self.merged_dir, self.rejected_dir]

        results = []
        for d in directories:
            for p in sorted(d.glob("*.md")):
                if p.name == ".gitkeep":
                    continue
                try:
                    proposal = self._parse_markdown(p)
                    if subsystem and proposal.subsystem != subsystem:
                        continue
                    results.append(proposal)
                except Exception as e:
                    logger.warning("Failed parsing proposal %s: %s", p, e)
        return results

    def approve_and_merge(
        self,
        proposal_id: str,
        engine: Any,
        merged_by: str = "human-operator",
        inventory_client: Any = None,
        lifecycle_manager: Any = None,
        approval_note: Optional[str] = None,
        override_preflight: bool = False,
        override_reason: Optional[str] = None,
    ) -> MergeResult:
        """Applies mutation via SecOpsEngine, moves proposal to merged/, and records git commit.

        Action types without an executor (see ``EXECUTABLE_ACTIONS``) are not written
        to SecOps: the proposal is merged with ``apply_status=MANUAL_APPLY_REQUIRED``,
        the result status is ``MERGED_MANUAL_APPLY_REQUIRED``, and the linked issue is
        marked APPROVED (not APPLIED) until ``mark_manually_applied`` is called.

        Raises:
            ValueError: proposal is not OPEN.
            ApprovalPolicyError: approver is not permitted to merge this proposal
                (self-approval, tier requires a human, or failed preflight without override).
            StaleTargetError: the target changed since the proposal was created,
                or could not be read to check.
        """
        open_file = self.open_dir / f"{proposal_id}.md"
        if not open_file.is_file():
            raise ValueError(f"Proposal {proposal_id} is not in OPEN status.")

        proposal = self._parse_markdown(open_file)

        stored_tier = proposal.required_tier
        if proposal.issue_id and lifecycle_manager is not None:
            try:
                issue = lifecycle_manager.work_queue.get_issue(proposal.issue_id)
                if issue is not None:
                    stored_tier = issue.governance.required_authority_tier
            except Exception as tier_err:
                logger.warning("Could not read linked issue tier for %s: %s", proposal_id, tier_err)

        # Policy gate: raises before any production mutation.
        proposal.required_tier = check_approval(
            author=proposal.author,
            approver=merged_by,
            action_type=proposal.action_type,
            risk_level=proposal.risk_level,
            stored_tier=stored_tier,
            syntax_verified=bool(proposal.preflight.syntax_verified),
            override_preflight=override_preflight,
            override_reason=override_reason,
        )
        if override_preflight and not proposal.preflight.syntax_verified:
            proposal.preflight_override_reason = (override_reason or "").strip()

        # Stale-target gate: raises before any production mutation.
        proposal.base_verified_at_merge = verify_unchanged(
            engine, proposal.action_type, proposal.target_resource_id, proposal.base_revision
        )

        execution_res = None
        action = (proposal.action_type or "").upper()
        manual_apply = not has_executor(action)

        try:
            # 1. Execute mutation against live Google SecOps API via SecOpsEngine
            if action in RULE_TEXT_ACTIONS:
                rule_id = proposal.target_resource_id
                rule_text = proposal.mutation_payload.get("rule_text")
                update_mask = proposal.mutation_payload.get("update_mask", "text")
                if not rule_text:
                    raise ValueError(f"{proposal.action_type} mutation requires 'rule_text' in mutation_payload.")
                execution_res = engine.patch_rule(
                    rule_id_or_name=rule_id,
                    rule_text=rule_text,
                    update_mask=update_mask,
                )

            elif action in RULE_DEPLOYMENT_ACTIONS:
                rule_id = proposal.target_resource_id
                enabled = proposal.mutation_payload.get("enabled")
                alerting = proposal.mutation_payload.get("alerting")
                execution_res = engine.update_rule_deployment(
                    rule_id_or_name=rule_id,
                    enabled=enabled,
                    alerting=alerting,
                )

            elif action == "GENERIC_CAPABILITY":
                cap_id = proposal.mutation_payload.get("capability_id")
                kwargs = proposal.mutation_payload.get("kwargs", {})
                execution_res = engine.execute(cap_id, **kwargs)

            elif action == "CREATE_FINDINGS_REFINEMENT":
                query = _refinement_query(proposal.mutation_payload)
                if not query:
                    raise ValueError(
                        "CREATE_FINDINGS_REFINEMENT requires 'refinement_query' (or 'tuned_rule_text') in mutation_payload."
                    )
                if engine is None:
                    raise ValueError("CREATE_FINDINGS_REFINEMENT requires an engine to write the refinement.")
                rule_id = proposal.mutation_payload.get("rule_id") or proposal.target_resource_id
                execution_res = engine.create_findings_refinement(
                    display_name=(proposal.title or f"Exclusion for {rule_id}")[:200],
                    query=query,
                    curated_rule_ids=[rule_id] if rule_id else None,
                )

            else:
                logger.info("No executor for %s; merging %s as manual apply", action, proposal_id)
                execution_res = {
                    "status": MERGED_MANUAL_APPLY_REQUIRED,
                    "action": proposal.action_type,
                    "message": f"No automated write exists for {proposal.action_type}; apply it in SecOps and mark it applied.",
                }

            # 2. Update proposal state
            proposal.status = "MERGED"
            proposal.merged_at = datetime.now(timezone.utc).isoformat()
            proposal.merged_by = merged_by
            proposal.approval_note = approval_note
            proposal.updated_at = proposal.merged_at
            if manual_apply:
                proposal.apply_status = APPLY_STATUS_MANUAL_REQUIRED
            else:
                proposal.apply_status = APPLY_STATUS_APPLIED
                proposal.applied_by = merged_by
                proposal.applied_at = proposal.merged_at

            # 3. Move file from open/ to merged/
            merged_file = self.merged_dir / f"{proposal_id}.md"
            merged_file.write_text(self._format_markdown(proposal), encoding="utf-8")
            open_file.unlink(missing_ok=True)

            # 4. Optional Git commit
            commit_hash = self._commit_merged_proposal(proposal)
            if commit_hash:
                proposal.merge_commit = commit_hash
                merged_file.write_text(self._format_markdown(proposal), encoding="utf-8")

            # 5. Optional Inventory Snapshot Notification
            snapshot_triggered = False
            if inventory_client:
                try:
                    inventory_client.trigger_snapshot(
                        reason=f"Merged proposal {proposal_id} by {merged_by}"
                    )
                    snapshot_triggered = True
                except Exception as snap_err:
                    logger.warning("Failed triggering inventory snapshot: %s", snap_err)

            # 6. Optional SOC Lifecycle Integration
            if proposal.issue_id and lifecycle_manager:
                try:
                    if manual_apply:
                        # Nothing changed in SecOps: record the approval, keep the issue open.
                        lifecycle_manager.decide_issue(
                            issue_id=proposal.issue_id,
                            decision="APPROVED",
                            approver=merged_by,
                            rationale=(
                                f"Approved {proposal.id}; no automated write for {proposal.action_type}, "
                                "awaiting manual apply."
                                + (f" Note: {approval_note}" if approval_note else "")
                            ),
                            commit=False,
                        )
                    else:
                        self._record_applied_change(
                            proposal, lifecycle_manager, merged_by, commit_hash, _as_dict(execution_res)
                        )
                except Exception as lm_err:
                    logger.warning("Failed recording merge in lifecycle manager: %s", lm_err)

            return MergeResult(
                proposal_id=proposal_id,
                success=True,
                status=MERGED_MANUAL_APPLY_REQUIRED if manual_apply else "MERGED",
                execution_result=execution_res,
                commit_hash=commit_hash,
                inventory_snapshot_triggered=snapshot_triggered,
            )

        except Exception as e:
            logger.error("Failed to merge proposal %s: %s", proposal_id, e)
            return MergeResult(
                proposal_id=proposal_id,
                success=False,
                status="FAILED",
                error_message=str(e),
            )

    def _record_applied_change(
        self,
        proposal: ChangeProposal,
        lifecycle_manager: Any,
        applied_by: str,
        commit_hash: Optional[str],
        api_response: Dict[str, Any],
    ) -> None:
        from engine.domain import ChangeRecord
        change_record = ChangeRecord(
            change_id=proposal.id,
            issue_id=proposal.issue_id,
            proposal_id=proposal.id,
            subsystem=proposal.subsystem,
            target_resource_id=proposal.target_resource_id,
            applied_by=applied_by,
            commit_sha=commit_hash or "",
            api_response=api_response,
        )
        lifecycle_manager.apply_change(
            issue_id=proposal.issue_id,
            change_record=change_record,
            commit=False,
        )

    def mark_manually_applied(
        self,
        proposal_id: str,
        applied_by: str,
        note: str,
        lifecycle_manager: Any = None,
    ) -> ChangeProposal:
        """Records that a human applied a merged, manual-apply proposal in SecOps.

        Moves the linked issue to APPLIED so the patrol can verify and close it.

        Raises:
            FileNotFoundError: proposal does not exist.
            ValueError: proposal is not waiting for a manual apply, or the note is too short.
            ApprovalPolicyError: ``applied_by`` is an agent handle.
        """
        merged_file = self.merged_dir / f"{proposal_id}.md"
        if not merged_file.is_file():
            self.get_proposal(proposal_id)  # raises FileNotFoundError if missing entirely
            raise ValueError(f"Proposal {proposal_id} has not been approved yet.")
        proposal = self._parse_markdown(merged_file)
        if proposal.apply_status != APPLY_STATUS_MANUAL_REQUIRED:
            raise ValueError(f"Proposal {proposal_id} is not waiting for a manual apply ({proposal.apply_status}).")
        if is_agent_actor(applied_by):
            raise ApprovalPolicyError(
                ApprovalPolicyError.HUMAN_REQUIRED,
                "Only a human can confirm a change was applied manually.",
                proposal.required_tier,
            )
        note = (note or "").strip()
        if len(note) < MIN_MANUAL_APPLY_NOTE_LEN:
            raise ValueError(f"Describe what was applied (at least {MIN_MANUAL_APPLY_NOTE_LEN} characters).")

        now = datetime.now(timezone.utc).isoformat()
        proposal.apply_status = APPLY_STATUS_MANUALLY_APPLIED
        proposal.applied_by = applied_by
        proposal.applied_at = now
        proposal.apply_note = note
        proposal.updated_at = now
        merged_file.write_text(self._format_markdown(proposal), encoding="utf-8")

        commit_hash = self._commit_merged_proposal(proposal, verb="manually applied")
        if commit_hash:
            proposal.merge_commit = commit_hash
            merged_file.write_text(self._format_markdown(proposal), encoding="utf-8")

        if proposal.issue_id and lifecycle_manager:
            try:
                self._record_applied_change(
                    proposal, lifecycle_manager, applied_by, commit_hash,
                    {"status": APPLY_STATUS_MANUALLY_APPLIED, "manual": True, "note": note},
                )
            except Exception as lm_err:
                logger.warning("Failed recording manual apply in lifecycle manager: %s", lm_err)
        return proposal

    def abandon_manual_apply(
        self,
        proposal_id: str,
        abandoned_by: str,
        reason: str,
        lifecycle_manager: Any = None,
    ) -> ChangeProposal:
        """Records that a human decided not to apply a merged, manual-apply proposal.

        The proposal stays in merged/ (status MERGED) with apply_status ABANDONED; nothing
        was written to SecOps. The linked issue moves from APPROVED to NEEDS_HUMAN so an
        operator can requeue it with guidance or close it.

        Raises:
            FileNotFoundError: proposal does not exist.
            ValueError: proposal is not waiting for a manual apply, or the reason is too short.
            ApprovalPolicyError: ``abandoned_by`` is an agent handle.
        """
        merged_file = self.merged_dir / f"{proposal_id}.md"
        if not merged_file.is_file():
            self.get_proposal(proposal_id)  # raises FileNotFoundError if missing entirely
            raise ValueError(f"Proposal {proposal_id} has not been approved yet.")
        proposal = self._parse_markdown(merged_file)
        if proposal.apply_status != APPLY_STATUS_MANUAL_REQUIRED:
            raise ValueError(f"Proposal {proposal_id} is not waiting for a manual apply ({proposal.apply_status}).")
        if is_agent_actor(abandoned_by):
            raise ApprovalPolicyError(
                ApprovalPolicyError.HUMAN_REQUIRED,
                "Only a human can abandon an approved change.",
                proposal.required_tier,
            )
        reason = (reason or "").strip()
        if len(reason) < MIN_MANUAL_APPLY_NOTE_LEN:
            raise ValueError(f"Explain why it won't be applied (at least {MIN_MANUAL_APPLY_NOTE_LEN} characters).")

        now = datetime.now(timezone.utc).isoformat()
        proposal.apply_status = APPLY_STATUS_ABANDONED
        proposal.abandoned_by = abandoned_by
        proposal.abandoned_at = now
        proposal.abandon_reason = reason
        proposal.updated_at = now
        merged_file.write_text(self._format_markdown(proposal), encoding="utf-8")

        commit_hash = self._commit_merged_proposal(proposal, verb="abandoned")
        if commit_hash:
            proposal.merge_commit = commit_hash
            merged_file.write_text(self._format_markdown(proposal), encoding="utf-8")

        if proposal.issue_id and lifecycle_manager:
            try:
                lifecycle_manager.abandon_approved_change(
                    issue_id=proposal.issue_id,
                    operator=abandoned_by,
                    reason=reason,
                    proposal_id=proposal.id,
                )
            except Exception as lm_err:
                logger.warning("Failed recording abandoned change in lifecycle manager: %s", lm_err)
        return proposal

    def reject_proposal(
        self,
        proposal_id: str,
        reason: str,
        rejected_by: str = "human-operator",
        lifecycle_manager: Any = None,
    ) -> ChangeProposal:
        """Rejects a proposal and moves it to rejected/ directory."""
        open_file = self.open_dir / f"{proposal_id}.md"
        if not open_file.is_file():
            raise ValueError(f"Proposal {proposal_id} is not open for rejection.")

        proposal = self._parse_markdown(open_file)
        proposal.status = "REJECTED"
        proposal.rejection_reason = f"[{rejected_by}]: {reason}"
        proposal.updated_at = datetime.now(timezone.utc).isoformat()

        rejected_file = self.rejected_dir / f"{proposal_id}.md"
        rejected_file.write_text(self._format_markdown(proposal), encoding="utf-8")
        open_file.unlink(missing_ok=True)

        if proposal.issue_id and lifecycle_manager:
            try:
                lifecycle_manager.decide_issue(
                    issue_id=proposal.issue_id,
                    decision="REJECTED",
                    approver=rejected_by,
                    rationale=reason,
                )
            except Exception as lm_err:
                logger.warning("Failed recording proposal rejection in lifecycle manager: %s", lm_err)

        return proposal

    def _commit_merged_proposal(self, proposal: ChangeProposal, verb: str = "merge") -> Optional[str]:
        """Creates a git commit tracking the proposal merge.

        The commit is scoped to ``.proposals/`` only, so unrelated staged changes
        in the operator's index are never swept into an agent commit.
        """
        if not git_commits_enabled():
            logger.debug("Git commits disabled via env; skipping merge commit for %s", proposal.id)
            return None
        try:
            env = os.environ.copy()
            env.setdefault("GIT_AUTHOR_NAME", "SecOps Agent Fleet")
            env.setdefault("GIT_AUTHOR_EMAIL", "agents@secops.local")
            env.setdefault("GIT_COMMITTER_NAME", "SecOps Agent Fleet")
            env.setdefault("GIT_COMMITTER_EMAIL", "agents@secops.local")

            subprocess.run(
                ["git", "add", ".proposals/"],
                cwd=str(self.root_dir),
                env=env,
                capture_output=True,
                check=False,
            )

            commit_msg = (
                f"proposal({proposal.subsystem}): {verb} {proposal.id} - {proposal.title}\n\n"
                f"Author: {proposal.author}\n"
                f"Target: {proposal.target_resource_id}\n"
                f"Action: {proposal.action_type}\n"
            )
            if proposal.approval_note:
                commit_msg += f"Approval-Note: {proposal.approval_note}\n"
            if proposal.merged_by:
                commit_msg += f"Approved-By: {proposal.merged_by}\n"
            if proposal.required_tier:
                commit_msg += f"Authority-Tier: {proposal.required_tier}\n"
            if proposal.apply_status:
                commit_msg += f"Apply-Status: {proposal.apply_status}\n"
            if proposal.apply_note:
                commit_msg += f"Apply-Note: {proposal.apply_note}\n"
            if proposal.abandon_reason:
                commit_msg += f"Abandoned-By: {proposal.abandoned_by}\n"
                commit_msg += f"Abandon-Reason: {proposal.abandon_reason}\n"
            if proposal.preflight_override_reason:
                commit_msg += f"Preflight-Override: {proposal.preflight_override_reason}\n"
            if proposal.base_revision:
                base = proposal.base_revision
                ref = base.get("revision_id") or base.get("text_sha256", "")[:12] or base.get("kind", "")
                state = "verified" if proposal.base_verified_at_merge else "unverified"
                commit_msg += f"Target-Baseline: {ref} ({state})\n"
            elif proposal.action_type in ("PATCH_RULE", "UPDATE_RULE_TEXT", "UPDATE_RULE_DEPLOYMENT",
                                          "TOGGLE_RULE_DEPLOYMENT", "DEPLOY_RULE", "UNDEPLOY_RULE"):
                commit_msg += "Target-Baseline: none (not checked)\n"

            res = subprocess.run(
                ["git", "commit", "-m", commit_msg, "--", ".proposals/"],
                cwd=str(self.root_dir),
                env=env,
                capture_output=True,
                text=True,
                check=False,
            )

            if res.returncode == 0:
                rev_res = subprocess.run(
                    ["git", "rev-parse", "HEAD"],
                    cwd=str(self.root_dir),
                    capture_output=True,
                    text=True,
                    check=False,
                )
                return rev_res.stdout.strip()
            return None
        except Exception as git_err:
            logger.debug("Git commit skipped: %s", git_err)
            return None
