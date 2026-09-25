"""Tests for SOC ledger location: issue/proposal records must live outside the SDK repo."""

import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from agents.core.git_guard import DISABLE_ENV_VAR
from agents.core.ledger import (
    LEDGER_ROOT_ENV_VAR,
    SDK_REPO_ROOT,
    LedgerLocationError,
    resolve_ledger_root,
)
from agents.core.materializer import IssueMaterializer
from agents.core.proposal_manager import ProposalManager


def _toplevel(path: Path) -> str:
    return subprocess.run(
        ["git", "rev-parse", "--show-toplevel"], cwd=str(path),
        capture_output=True, text=True, check=True,
    ).stdout.strip()


class TestLedgerLocation(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name).resolve()

    def tearDown(self):
        self._tmp.cleanup()

    def test_session_ledger_is_outside_repo(self):
        root = resolve_ledger_root()
        self.assertFalse(str(root).startswith(str(SDK_REPO_ROOT) + os.sep))
        self.assertNotEqual(root, SDK_REPO_ROOT)

    def test_env_var_is_honored(self):
        target = self.tmp / "tenant-a"
        with patch.dict(os.environ, {LEDGER_ROOT_ENV_VAR: str(target)}):
            self.assertEqual(resolve_ledger_root(), target)
            self.assertEqual(ProposalManager().root_dir, target)
            self.assertEqual(IssueMaterializer().issues_dir, target / ".issues")
        self.assertTrue((target / ".proposals" / "open").is_dir())

    def test_explicit_root_overrides_env(self):
        with patch.dict(os.environ, {LEDGER_ROOT_ENV_VAR: str(self.tmp / "env")}):
            self.assertEqual(resolve_ledger_root(self.tmp / "explicit"), self.tmp / "explicit")

    def test_rejects_path_inside_sdk_repo(self):
        for bad in (SDK_REPO_ROOT, SDK_REPO_ROOT / "somewhere" / "ledger"):
            with self.subTest(bad=bad):
                with self.assertRaises(LedgerLocationError):
                    resolve_ledger_root(bad)
                with patch.dict(os.environ, {LEDGER_ROOT_ENV_VAR: str(bad)}):
                    with self.assertRaises(LedgerLocationError):
                        ProposalManager()
                    with self.assertRaises(LedgerLocationError):
                        IssueMaterializer()
        self.assertFalse((SDK_REPO_ROOT / "somewhere").exists())

    def test_no_git_init_when_commits_disabled(self):
        root = resolve_ledger_root(self.tmp / "noinit")
        self.assertFalse((root / ".git").exists())

    def test_git_repo_initialized_when_commits_enabled(self):
        with patch.dict(os.environ, {DISABLE_ENV_VAR: "0"}):
            root = resolve_ledger_root(self.tmp / "ledger")
            self.assertTrue((root / ".git").is_dir())
            self.assertEqual(Path(_toplevel(root)).resolve(), root)
            # Idempotent.
            resolve_ledger_root(root)

    def test_nested_ledger_gets_its_own_repo(self):
        outer = self.tmp / "outer"
        outer.mkdir()
        subprocess.run(["git", "init", "-q"], cwd=str(outer), check=True)
        with patch.dict(os.environ, {DISABLE_ENV_VAR: "0"}):
            root = resolve_ledger_root(outer / "nested")
        self.assertEqual(Path(_toplevel(root)).resolve(), root)


if __name__ == "__main__":
    unittest.main()
