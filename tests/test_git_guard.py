"""Regression tests: agent git commits must be disabled under test and scoped when enabled."""

import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from agents.core.git_guard import DISABLE_ENV_VAR, git_commits_enabled
from agents.core.materializer import IssueMaterializer
from agents.core.proposal_manager import ChangeProposal, ProposalManager

_GIT_ENV = {
    "GIT_AUTHOR_NAME": "t",
    "GIT_AUTHOR_EMAIL": "t@t",
    "GIT_COMMITTER_NAME": "t",
    "GIT_COMMITTER_EMAIL": "t@t",
}


def _git(root: Path, *args: str) -> str:
    return subprocess.run(
        ["git", *args],
        cwd=str(root),
        check=True,
        capture_output=True,
        text=True,
        env={**os.environ, **_GIT_ENV},
    ).stdout.strip()


def _make_proposal() -> ChangeProposal:
    return ChangeProposal(
        id="",
        title="guard test",
        author="@test",
        subsystem="detection_rules",
        target_resource_id="ru_test",
        action_type="RULE_OPTIMIZATION",
        rationale="r",
        proposed_diff="",
    )


class GitGuardTest(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)
        _git(self.root, "init", "-q")
        (self.root / "seed.txt").write_text("seed")
        _git(self.root, "add", "seed.txt")
        _git(self.root, "commit", "-q", "-m", "seed")

    def tearDown(self):
        self.temp_dir.cleanup()

    def _commit_count(self) -> int:
        return int(_git(self.root, "rev-list", "--count", "HEAD"))

    def test_conftest_disables_commits_for_session(self):
        self.assertFalse(git_commits_enabled())

    def test_env_var_parsing(self):
        for val, expected in [("1", False), ("true", False), ("YES", False), ("on", False),
                              ("0", True), ("", True), ("false", True)]:
            with patch.dict(os.environ, {DISABLE_ENV_VAR: val}):
                self.assertEqual(git_commits_enabled(), expected, val)

    def test_proposal_manager_does_not_commit_when_disabled(self):
        mgr = ProposalManager(root_dir=self.root)
        before = self._commit_count()
        self.assertIsNone(mgr._commit_merged_proposal(_make_proposal()))
        self.assertEqual(self._commit_count(), before)

    def test_materializer_does_not_commit_when_disabled(self):
        mat = IssueMaterializer(root_dir=self.root)
        f = mat.issues_dir / "x.yaml"
        f.write_text("a: 1")
        before = self._commit_count()
        self.assertIsNone(mat._git_commit([f], "should not commit"))
        self.assertEqual(self._commit_count(), before)

    def test_enabled_commits_do_not_sweep_unrelated_staged_files(self):
        (self.root / "unrelated.txt").write_text("operator work in progress")
        _git(self.root, "add", "unrelated.txt")

        with patch.dict(os.environ, {DISABLE_ENV_VAR: "0", **_GIT_ENV}):
            mgr = ProposalManager(root_dir=self.root)
            (mgr.merged_dir / "p.md").write_text("merged")
            self.assertIsNotNone(mgr._commit_merged_proposal(_make_proposal()))

            mat = IssueMaterializer(root_dir=self.root)
            f = mat.issues_dir / "x.yaml"
            f.write_text("a: 1")
            self.assertIsNotNone(mat._git_commit([f], "issue commit"))

        committed = _git(self.root, "log", "--name-only", "--format=", "-2").split()
        self.assertNotIn("unrelated.txt", committed)
        # Operator's staged file remains staged, untouched.
        self.assertIn("unrelated.txt", _git(self.root, "diff", "--cached", "--name-only").split())


if __name__ == "__main__":
    unittest.main()
