"""Gas Town / Beads-inspired Lite Git Change Proposal Engine for SecOps Agents.

Manages autonomous change proposals (.proposals/open, .proposals/merged, .proposals/rejected),
frontmatter serialization, unified diffs, pre-flight verification proofs, and automated merge execution.
"""

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
import json
import logging
import os
from pathlib import Path
import subprocess
from typing import Any, Dict, List, Optional
import yaml

from agents.core.git_guard import git_commits_enabled
from agents.core.ledger import resolve_ledger_root

logger = logging.getLogger(__name__)


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
    rationale: str = ""
    proposed_diff: str = ""
    issue_id: Optional[str] = None
    preflight: PreflightProof = field(default_factory=PreflightProof)
    mutation_payload: Dict[str, Any] = field(default_factory=dict)


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
            "preflight": asdict(proposal.preflight),
            "mutation_payload": proposal.mutation_payload,
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
            rationale=rationale,
            proposed_diff=diff,
            preflight=preflight,
            mutation_payload=frontmatter.get("mutation_payload", {}),
        )

    def create_proposal(self, proposal: ChangeProposal) -> str:
        """Creates an open proposal file and returns the proposal ID."""
        if not proposal.id:
            timestamp = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
            proposal.id = f"prop-{timestamp}-{proposal.subsystem[:6]}"

        proposal.status = "OPEN"
        proposal.created_at = datetime.now(timezone.utc).isoformat()
        proposal.updated_at = proposal.created_at

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
    ) -> MergeResult:
        """Applies mutation via SecOpsEngine, moves proposal to merged/, and records git commit."""
        open_file = self.open_dir / f"{proposal_id}.md"
        if not open_file.is_file():
            raise ValueError(f"Proposal {proposal_id} is not in OPEN status.")

        proposal = self._parse_markdown(open_file)
        execution_res = None

        try:
            # 1. Execute mutation against live Google SecOps API via SecOpsEngine
            if proposal.action_type in ("PATCH_RULE", "UPDATE_RULE_TEXT"):
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

            elif proposal.action_type in ("UPDATE_RULE_DEPLOYMENT", "TOGGLE_RULE_DEPLOYMENT", "DEPLOY_RULE", "UNDEPLOY_RULE"):
                rule_id = proposal.target_resource_id
                enabled = proposal.mutation_payload.get("enabled")
                alerting = proposal.mutation_payload.get("alerting")
                execution_res = engine.update_rule_deployment(
                    rule_id_or_name=rule_id,
                    enabled=enabled,
                    alerting=alerting,
                )

            elif proposal.action_type == "GENERIC_CAPABILITY":
                cap_id = proposal.mutation_payload.get("capability_id")
                kwargs = proposal.mutation_payload.get("kwargs", {})
                execution_res = engine.execute(cap_id, **kwargs)

            else:
                logger.info("Executing custom mutation for action %s", proposal.action_type)
                execution_res = {"status": "APPLIED_CUSTOM", "action": proposal.action_type}

            # 2. Update proposal state
            proposal.status = "MERGED"
            proposal.merged_at = datetime.now(timezone.utc).isoformat()
            proposal.merged_by = merged_by
            proposal.updated_at = proposal.merged_at

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
                    from engine.domain import ChangeRecord
                    change_record = ChangeRecord(
                        change_id=proposal.id,
                        issue_id=proposal.issue_id,
                        proposal_id=proposal.id,
                        subsystem=proposal.subsystem,
                        target_resource_id=proposal.target_resource_id,
                        applied_by=merged_by,
                        commit_sha=commit_hash or "",
                        api_response=execution_res if isinstance(execution_res, dict) else {"result": str(execution_res)},
                    )
                    lifecycle_manager.apply_change(
                        issue_id=proposal.issue_id,
                        change_record=change_record,
                        commit=False,
                    )
                except Exception as lm_err:
                    logger.warning("Failed recording applied change in lifecycle manager: %s", lm_err)

            return MergeResult(
                proposal_id=proposal_id,
                success=True,
                status="MERGED",
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

    def _commit_merged_proposal(self, proposal: ChangeProposal) -> Optional[str]:
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
                f"proposal({proposal.subsystem}): merge {proposal.id} - {proposal.title}\n\n"
                f"Author: {proposal.author}\n"
                f"Target: {proposal.target_resource_id}\n"
                f"Action: {proposal.action_type}\n"
            )

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
