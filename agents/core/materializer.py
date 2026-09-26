"""Evidence Plane: Issue Materializer for Git-Backed Durable SOC Records.

Bridges the ephemeral coordination state in Firestore to the durable,
audit-grade, append-oriented Git change ledger under `.issues/<issue_id>/`.

Directory Layout per Issue:
.issues/<issue_id>/
├── issue.yaml                     # Canonical issue definition
├── events/                        # Append-only transition events
│   ├── 001-observed.yaml
│   ├── 002-qualified.yaml
│   ├── 003-claimed.yaml
│   ├── 004-proposal-created.yaml
│   ├── 005-validation.yaml
│   ├── 006-approved.yaml
│   ├── 007-applied.yaml
│   └── 008-verified.yaml
├── evidence/                      # Immutable evidence snapshots
│   └── *.json, *.yaml, *.diff
└── resolution.md                  # Executive audit and root cause summary
"""

from datetime import datetime, timezone
import json
import logging
import os
from pathlib import Path
import subprocess
from typing import Any, Dict, List, Optional, Tuple
import yaml

from engine.domain import (
    AuthorityTier,
    ChangeRecord,
    IssueEvent,
    IssueLifecycleStatus,
    IssueSeverity,
    Lease,
    OperationalPlane,
    SOCIssue,
    VerificationProof,
)
from agents.core.evidence_store import normalize_doc_id
from agents.core.git_guard import git_commits_enabled
from agents.core.ledger import resolve_ledger_root

logger = logging.getLogger(__name__)


class IssueMaterializer:
    """Manages the durable Git filesystem representation of SOC work items."""

    def __init__(self, root_dir: Optional[Path] = None):
        """Args:
            root_dir: Ledger root. Defaults to ``SECOPS_LEDGER_ROOT`` or
                ``~/.secops/ledger``; must be outside the SDK repository.
        """
        self.root_dir = resolve_ledger_root(root_dir)
        self.issues_dir = self.root_dir / ".issues"
        self.issues_dir.mkdir(parents=True, exist_ok=True)

    def _issue_path(self, issue_id: str) -> Path:
        clean = normalize_doc_id(issue_id)
        return self.issues_dir / clean

    def _events_dir(self, issue_id: str) -> Path:
        p = self._issue_path(issue_id) / "events"
        p.mkdir(parents=True, exist_ok=True)
        return p

    def _evidence_dir(self, issue_id: str) -> Path:
        p = self._issue_path(issue_id) / "evidence"
        p.mkdir(parents=True, exist_ok=True)
        return p

    def _next_sequence(self, issue_id: str) -> int:
        events_dir = self._events_dir(issue_id)
        existing = list(events_dir.glob("*.yaml"))
        if not existing:
            return 1
        return len(existing) + 1

    def _git_commit(self, file_paths: List[Path], message: str) -> Optional[str]:
        """Safely commits materialized issue files to git if inside a git repository.

        The commit is scoped to ``file_paths`` only, so unrelated staged changes
        in the operator's index are never swept into an agent commit.
        """
        if not git_commits_enabled():
            logger.debug("Git commits disabled via env; skipping: %s", message)
            return None
        try:
            rel_paths = [str(p.relative_to(self.root_dir)) for p in file_paths]
            subprocess.run(
                ["git", "add"] + rel_paths,
                cwd=str(self.root_dir),
                check=True,
                capture_output=True,
                text=True,
            )
            commit_res = subprocess.run(
                ["git", "commit", "-m", message, "--"] + rel_paths,
                cwd=str(self.root_dir),
                check=False,
                capture_output=True,
                text=True,
            )
            if commit_res.returncode == 0:
                rev_res = subprocess.run(
                    ["git", "rev-parse", "HEAD"],
                    cwd=str(self.root_dir),
                    check=True,
                    capture_output=True,
                    text=True,
                )
                sha = rev_res.stdout.strip()
                logger.info("Committed issue event to git: %s (%s)", sha[:8], message)
                return sha
            else:
                logger.debug("Git commit skipped or no changes: %s", commit_res.stderr.strip())
                return None
        except Exception as e:
            logger.warning("Could not create git commit for materialized issue: %s", e)
            return None

    def materialize_issue_opened(
        self,
        issue: SOCIssue,
        evidence_files: Optional[Dict[str, Any]] = None,
        commit: bool = True,
    ) -> Tuple[Path, Optional[str]]:
        """Materializes an opened/observed issue across the durability boundary into Git."""
        issue_dir = self._issue_path(issue.id)
        issue_dir.mkdir(parents=True, exist_ok=True)
        events_dir = self._events_dir(issue.id)
        evidence_dir = self._evidence_dir(issue.id)

        # 1. Write issue.yaml
        issue_file = issue_dir / "issue.yaml"
        with open(issue_file, "w", encoding="utf-8") as f:
            yaml.safe_dump(issue.to_dict(), f, sort_keys=False)

        # 2. Write 001-observed.yaml event
        seq = 1
        event = IssueEvent(
            event_id=f"{issue.id}-evt-{seq:03d}",
            issue_id=issue.id,
            sequence=seq,
            transition_type="OBSERVED",
            actor=issue.source.deacon_id or "sensing_deacon",
            details={
                "title": issue.problem.title,
                "observed_state": issue.problem.observed_state,
                "desired_state": issue.problem.desired_state,
                "severity": issue.severity,
            },
        )
        evt_file = events_dir / f"{seq:03d}-observed.yaml"
        with open(evt_file, "w", encoding="utf-8") as f:
            yaml.safe_dump(event.to_dict(), f, sort_keys=False)

        staged_files = [issue_file, evt_file]

        # 3. Write evidence files if provided
        if evidence_files:
            for fname, content in evidence_files.items():
                ev_path = evidence_dir / fname
                if isinstance(content, (dict, list)):
                    with open(ev_path, "w", encoding="utf-8") as f:
                        json.dump(content, f, indent=2)
                else:
                    with open(ev_path, "w", encoding="utf-8") as f:
                        f.write(str(content))
                staged_files.append(ev_path)

        commit_sha = None
        if commit:
            commit_sha = self._git_commit(
                staged_files,
                f"feat(soc-issue): [{issue.id}] observed by {event.actor}",
            )

        logger.info("Materialized issue %s opened at %s (commit: %s)", issue.id, issue_dir, commit_sha)
        return issue_dir, commit_sha

    def materialize_claimed(
        self,
        issue_id: str,
        agent_handle: str,
        lease: Lease,
        commit: bool = False,
    ) -> Tuple[Path, Optional[str]]:
        """Records work claim event in the append-only ledger."""
        issue_dir = self._issue_path(issue_id)
        events_dir = self._events_dir(issue_id)
        seq = self._next_sequence(issue_id)

        event = IssueEvent(
            event_id=f"{issue_id}-evt-{seq:03d}",
            issue_id=issue_id,
            sequence=seq,
            transition_type="CLAIMED",
            actor=agent_handle,
            details={
                "lease_acquired_at": lease.acquired_at,
                "lease_expires_at": lease.expires_at,
                "generation": lease.generation,
            },
        )
        evt_file = events_dir / f"{seq:03d}-claimed.yaml"
        with open(evt_file, "w", encoding="utf-8") as f:
            yaml.safe_dump(event.to_dict(), f, sort_keys=False)

        # Update issue.yaml
        issue_file = issue_dir / "issue.yaml"
        staged_files = [evt_file]
        if issue_file.is_file():
            try:
                with open(issue_file, "r", encoding="utf-8") as f:
                    data = yaml.safe_load(f) or {}
                data["status"] = IssueLifecycleStatus.LEASED.value
                data["lease"] = lease.to_dict()
                if "routing" in data:
                    data["routing"]["claimed_by"] = agent_handle
                with open(issue_file, "w", encoding="utf-8") as f:
                    yaml.safe_dump(data, f, sort_keys=False)
                staged_files.append(issue_file)
            except Exception as e:
                logger.warning("Could not update issue.yaml on claim: %s", e)

        commit_sha = None
        if commit:
            commit_sha = self._git_commit(
                staged_files,
                f"chore(soc-issue): [{issue_id}] claimed by {agent_handle}",
            )
        return evt_file, commit_sha

    def materialize_proposal_created(
        self,
        issue_id: str,
        proposal_id: str,
        proposal_title: str,
        author: str,
        diff_text: str = "",
        mutation_payload: Optional[Dict[str, Any]] = None,
        commit: bool = True,
    ) -> Tuple[Path, Optional[str]]:
        """Materializes proposal creation across the durability boundary into Git."""
        issue_dir = self._issue_path(issue_id)
        events_dir = self._events_dir(issue_id)
        evidence_dir = self._evidence_dir(issue_id)
        seq = self._next_sequence(issue_id)

        event = IssueEvent(
            event_id=f"{issue_id}-evt-{seq:03d}",
            issue_id=issue_id,
            sequence=seq,
            transition_type="PROPOSAL_CREATED",
            actor=author,
            details={
                "proposal_id": proposal_id,
                "proposal_title": proposal_title,
                "has_diff": bool(diff_text),
            },
        )
        evt_file = events_dir / f"{seq:03d}-proposal-created.yaml"
        with open(evt_file, "w", encoding="utf-8") as f:
            yaml.safe_dump(event.to_dict(), f, sort_keys=False)

        staged_files = [evt_file]

        # Save diff evidence
        if diff_text:
            diff_file = evidence_dir / f"proposal_{proposal_id}.diff"
            with open(diff_file, "w", encoding="utf-8") as f:
                f.write(diff_text)
            staged_files.append(diff_file)

        # Save mutation payload evidence
        if mutation_payload:
            payload_file = evidence_dir / f"proposal_{proposal_id}_mutation.json"
            with open(payload_file, "w", encoding="utf-8") as f:
                json.dump(mutation_payload, f, indent=2)
            staged_files.append(payload_file)

        # Update issue.yaml
        issue_file = issue_dir / "issue.yaml"
        if issue_file.is_file():
            try:
                with open(issue_file, "r", encoding="utf-8") as f:
                    data = yaml.safe_load(f) or {}
                data["active_proposal_id"] = proposal_id
                data["status"] = IssueLifecycleStatus.VALIDATING.value
                with open(issue_file, "w", encoding="utf-8") as f:
                    yaml.safe_dump(data, f, sort_keys=False)
                staged_files.append(issue_file)
            except Exception as e:
                logger.warning("Could not update issue.yaml on proposal creation: %s", e)

        commit_sha = None
        if commit:
            commit_sha = self._git_commit(
                staged_files,
                f"feat(soc-proposal): [{issue_id}] proposal {proposal_id} created by {author}",
            )
        return evt_file, commit_sha

    def materialize_validation_recorded(
        self,
        issue_id: str,
        validator_actor: str,
        passed: bool,
        diagnostics: List[str],
        test_evidence: Optional[Dict[str, Any]] = None,
        commit: bool = True,
    ) -> Tuple[Path, Optional[str]]:
        """Materializes peer validation results across the durability boundary into Git."""
        issue_dir = self._issue_path(issue_id)
        events_dir = self._events_dir(issue_id)
        evidence_dir = self._evidence_dir(issue_id)
        seq = self._next_sequence(issue_id)

        status_label = "VALIDATION_PASSED" if passed else "VALIDATION_FAILED"
        event = IssueEvent(
            event_id=f"{issue_id}-evt-{seq:03d}",
            issue_id=issue_id,
            sequence=seq,
            transition_type=status_label,
            actor=validator_actor,
            details={
                "passed": passed,
                "diagnostics": diagnostics,
            },
        )
        evt_file = events_dir / f"{seq:03d}-validation.yaml"
        with open(evt_file, "w", encoding="utf-8") as f:
            yaml.safe_dump(event.to_dict(), f, sort_keys=False)

        staged_files = [evt_file]

        if test_evidence:
            ev_file = evidence_dir / f"validation_{seq:03d}_results.json"
            with open(ev_file, "w", encoding="utf-8") as f:
                json.dump(test_evidence, f, indent=2)
            staged_files.append(ev_file)

        # Update issue.yaml
        issue_file = issue_dir / "issue.yaml"
        if issue_file.is_file():
            try:
                with open(issue_file, "r", encoding="utf-8") as f:
                    data = yaml.safe_load(f) or {}
                data["status"] = IssueLifecycleStatus.APPROVED.value if passed else IssueLifecycleStatus.VALIDATION_FAILED.value
                with open(issue_file, "w", encoding="utf-8") as f:
                    yaml.safe_dump(data, f, sort_keys=False)
                staged_files.append(issue_file)
            except Exception as e:
                logger.warning("Could not update issue.yaml on validation: %s", e)

        commit_sha = None
        if commit:
            commit_sha = self._git_commit(
                staged_files,
                f"test(soc-issue): [{issue_id}] validation {'passed' if passed else 'failed'} by {validator_actor}",
            )
        return evt_file, commit_sha

    def materialize_decision(
        self,
        issue_id: str,
        decision: str,  # APPROVED or REJECTED
        approver: str,
        rationale: str = "",
        commit: bool = True,
    ) -> Tuple[Path, Optional[str]]:
        """Materializes human or policy decision across the durability boundary into Git."""
        issue_dir = self._issue_path(issue_id)
        events_dir = self._events_dir(issue_id)
        seq = self._next_sequence(issue_id)

        event = IssueEvent(
            event_id=f"{issue_id}-evt-{seq:03d}",
            issue_id=issue_id,
            sequence=seq,
            transition_type=f"DECISION_{decision.upper()}",
            actor=approver,
            details={
                "decision": decision.upper(),
                "rationale": rationale,
            },
        )
        evt_file = events_dir / f"{seq:03d}-decision.yaml"
        with open(evt_file, "w", encoding="utf-8") as f:
            yaml.safe_dump(event.to_dict(), f, sort_keys=False)

        staged_files = [evt_file]
        issue_file = issue_dir / "issue.yaml"
        if issue_file.is_file():
            try:
                with open(issue_file, "r", encoding="utf-8") as f:
                    data = yaml.safe_load(f) or {}
                data["status"] = IssueLifecycleStatus.APPROVED.value if decision.upper() == "APPROVED" else IssueLifecycleStatus.BLOCKED.value
                with open(issue_file, "w", encoding="utf-8") as f:
                    yaml.safe_dump(data, f, sort_keys=False)
                staged_files.append(issue_file)
            except Exception as e:
                logger.warning("Could not update issue.yaml on decision: %s", e)

        commit_sha = None
        if commit:
            commit_sha = self._git_commit(
                staged_files,
                f"governance(soc-issue): [{issue_id}] decision {decision.upper()} by {approver}",
            )
        return evt_file, commit_sha

    def materialize_applied(
        self,
        issue_id: str,
        change_record: ChangeRecord,
        commit: bool = True,
    ) -> Tuple[Path, Optional[str]]:
        """Materializes an applied production change into Git."""
        issue_dir = self._issue_path(issue_id)
        events_dir = self._events_dir(issue_id)
        seq = self._next_sequence(issue_id)

        event = IssueEvent(
            event_id=f"{issue_id}-evt-{seq:03d}",
            issue_id=issue_id,
            sequence=seq,
            transition_type="APPLIED",
            actor=change_record.applied_by,
            details=change_record.to_dict(),
        )
        evt_file = events_dir / f"{seq:03d}-applied.yaml"
        with open(evt_file, "w", encoding="utf-8") as f:
            yaml.safe_dump(event.to_dict(), f, sort_keys=False)

        staged_files = [evt_file]
        issue_file = issue_dir / "issue.yaml"
        if issue_file.is_file():
            try:
                with open(issue_file, "r", encoding="utf-8") as f:
                    data = yaml.safe_load(f) or {}
                data["status"] = IssueLifecycleStatus.APPLIED.value
                data["applied_change_id"] = change_record.change_id
                with open(issue_file, "w", encoding="utf-8") as f:
                    yaml.safe_dump(data, f, sort_keys=False)
                staged_files.append(issue_file)
            except Exception as e:
                logger.warning("Could not update issue.yaml on change application: %s", e)

        commit_sha = None
        if commit:
            commit_sha = self._git_commit(
                staged_files,
                f"fix(soc-change): [{issue_id}] applied change {change_record.change_id} by {change_record.applied_by}",
            )
        return evt_file, commit_sha

    def materialize_verified(
        self,
        issue_id: str,
        verification: VerificationProof,
        resolution_markdown: str = "",
        commit: bool = True,
    ) -> Tuple[Path, Optional[str]]:
        """Materializes post-deployment verification and issue closure into Git."""
        issue_dir = self._issue_path(issue_id)
        events_dir = self._events_dir(issue_id)
        seq = self._next_sequence(issue_id)

        event = IssueEvent(
            event_id=f"{issue_id}-evt-{seq:03d}",
            issue_id=issue_id,
            sequence=seq,
            transition_type="VERIFIED",
            actor=verification.verifier_actor or "sensing_deacon",
            details=verification.to_dict(),
        )
        evt_file = events_dir / f"{seq:03d}-verified.yaml"
        with open(evt_file, "w", encoding="utf-8") as f:
            yaml.safe_dump(event.to_dict(), f, sort_keys=False)

        staged_files = [evt_file]

        # Write resolution.md
        res_file = issue_dir / "resolution.md"
        content = resolution_markdown or f"""# Resolution Summary: {issue_id}

- **Verification ID**: {verification.verification_id}
- **Status**: VERIFIED & CLOSED
- **Verified At**: {verification.verified_at}
- **Verifier**: {verification.verifier_actor}
- **Outcome**: Telemetry cleared successfully.

## Verification Details
{verification.summary}
"""
        with open(res_file, "w", encoding="utf-8") as f:
            f.write(content)
        staged_files.append(res_file)

        # Update issue.yaml
        issue_file = issue_dir / "issue.yaml"
        if issue_file.is_file():
            try:
                with open(issue_file, "r", encoding="utf-8") as f:
                    data = yaml.safe_load(f) or {}
                data["status"] = IssueLifecycleStatus.CLOSED.value
                data["closed_at"] = datetime.now(timezone.utc).isoformat()
                with open(issue_file, "w", encoding="utf-8") as f:
                    yaml.safe_dump(data, f, sort_keys=False)
                staged_files.append(issue_file)
            except Exception as e:
                logger.warning("Could not update issue.yaml on closure: %s", e)

        commit_sha = None
        if commit:
            commit_sha = self._git_commit(
                staged_files,
                f"chore(soc-issue): [{issue_id}] verified & closed by {verification.verifier_actor}",
            )
        return evt_file, commit_sha

    def materialize_operator_action(
        self,
        issue_id: str,
        transition_type: str,
        actor: str,
        new_status: str,
        details: Optional[Dict[str, Any]] = None,
        commit: bool = True,
    ) -> Tuple[Path, Optional[str]]:
        """Records an operator intervention (requeue, manual close) in the append-only ledger."""
        issue_dir = self._issue_path(issue_id)
        events_dir = self._events_dir(issue_id)
        seq = self._next_sequence(issue_id)

        event = IssueEvent(
            event_id=f"{issue_id}-evt-{seq:03d}",
            issue_id=issue_id,
            sequence=seq,
            transition_type=transition_type,
            actor=actor,
            details={"new_status": new_status, **(details or {})},
        )
        evt_file = events_dir / f"{seq:03d}-{transition_type.lower().replace('_', '-')}.yaml"
        with open(evt_file, "w", encoding="utf-8") as f:
            yaml.safe_dump(event.to_dict(), f, sort_keys=False)

        staged_files = [evt_file]
        issue_file = issue_dir / "issue.yaml"
        if issue_file.is_file():
            try:
                with open(issue_file, "r", encoding="utf-8") as f:
                    data = yaml.safe_load(f) or {}
                data["status"] = new_status
                if new_status == IssueLifecycleStatus.CLOSED.value:
                    data["closed_at"] = datetime.now(timezone.utc).isoformat()
                with open(issue_file, "w", encoding="utf-8") as f:
                    yaml.safe_dump(data, f, sort_keys=False)
                staged_files.append(issue_file)
            except Exception as e:
                logger.warning("Could not update issue.yaml on %s: %s", transition_type, e)

        commit_sha = None
        if commit:
            commit_sha = self._git_commit(
                staged_files,
                f"governance(soc-issue): [{issue_id}] {transition_type.lower()} by {actor}",
            )
        return evt_file, commit_sha

    def get_issue(self, issue_id: str) -> Optional[SOCIssue]:
        """Reads durable issue.yaml from Git directory."""
        issue_file = self._issue_path(issue_id) / "issue.yaml"
        if not issue_file.is_file():
            return None
        try:
            with open(issue_file, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f)
            return SOCIssue.from_dict(data)
        except Exception as e:
            logger.error("Error reading durable issue %s: %s", issue_id, e)
            return None

    def list_issue_events(self, issue_id: str) -> List[IssueEvent]:
        """Lists all append-only events for an issue in sequence order."""
        events_dir = self._events_dir(issue_id)
        results: List[IssueEvent] = []
        for p in sorted(events_dir.glob("*.yaml")):
            try:
                with open(p, "r", encoding="utf-8") as f:
                    data = yaml.safe_load(f)
                results.append(IssueEvent.from_dict(data))
            except Exception:
                continue
        results.sort(key=lambda x: x.sequence)
        return results

    def read_resolution(self, issue_id: str) -> str:
        """Reads resolution.md for an issue if present."""
        res_file = self._issue_path(issue_id) / "resolution.md"
        if not res_file.is_file():
            return ""
        try:
            with open(res_file, "r", encoding="utf-8") as f:
                return f.read()
        except Exception as e:
            logger.warning("Error reading resolution.md for %s: %s", issue_id, e)
            return ""

    def list_changes(self, limit: int = 50) -> List[ChangeRecord]:
        """Scans the Git ledger for all recorded applied changes."""
        changes: List[ChangeRecord] = []
        if not self.issues_dir.is_dir():
            return changes
        for applied_file in self.issues_dir.glob("*/events/*-applied.yaml"):
            try:
                with open(applied_file, "r", encoding="utf-8") as f:
                    data = yaml.safe_load(f) or {}
                details = data.get("details", {})
                if details:
                    changes.append(ChangeRecord.from_dict(details))
            except Exception as e:
                logger.debug("Error reading applied change event %s: %s", applied_file, e)
        changes.sort(key=lambda c: c.applied_at or "", reverse=True)
        return changes[:limit]

