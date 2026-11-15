"""Phase 3 verification tests: PEP 621 packaging, CI workflow, socket-level live guard, and dotenv isolation."""

from __future__ import annotations

import os
from pathlib import Path
import socket
import tempfile
import tomllib
import unittest
from unittest import mock

import yaml

from engine.config import SecOpsConfigurationError, load_config
from tests import live_guard
from tests.live_guard import LiveCallBlocked

REPO_ROOT = Path(__file__).resolve().parent.parent


class Phase3PackagingAndGuardsTests(unittest.TestCase):
    def test_pyproject_toml_is_valid_pep621_and_declares_cli_and_dev_extras(self) -> None:
        pyproject_path = REPO_ROOT / "pyproject.toml"
        self.assertTrue(pyproject_path.is_file())
        data = tomllib.loads(pyproject_path.read_text(encoding="utf-8"))

        project = data["project"]
        self.assertEqual(project["name"], "secops-engine-sdk")
        self.assertIn("dependencies", project)
        self.assertIn("dev", project["optional-dependencies"])
        self.assertIn("pytest>=8.0.0", project["optional-dependencies"]["dev"])
        self.assertEqual(project["scripts"]["secops"], "clients.cli.secops:main")
        self.assertEqual(project["scripts"]["secops-tui"], "run_tui:main")

    def test_github_actions_ci_workflow_runs_gates_and_pytest(self) -> None:
        ci_path = REPO_ROOT / ".github" / "workflows" / "ci.yml"
        self.assertTrue(ci_path.is_file())
        ci_cfg = yaml.safe_load(ci_path.read_text(encoding="utf-8"))
        verify_job = ci_cfg["jobs"]["verify"]
        env_cfg = verify_job["env"]
        self.assertEqual(env_cfg["SECOPS_IGNORE_DOTENV"], "1")
        self.assertEqual(env_cfg["SECOPS_DISABLE_GIT_COMMITS"], "1")
        self.assertEqual(env_cfg["SECOPS_DISABLE_FIRESTORE"], "1")

        step_cmds = "\n".join(s.get("run", "") for s in verify_job["steps"])
        self.assertIn("ruff check .", step_cmds)
        self.assertIn("python scripts/ci_checks.py", step_cmds)
        self.assertIn("pytest", step_cmds)

    def test_gitmodules_registers_both_gitlinks(self) -> None:
        gitmodules = (REPO_ROOT / ".gitmodules").read_text(encoding="utf-8")
        self.assertIn("path = protos/secops_protos", gitmodules)
        self.assertIn("path = clients/chrome_extension", gitmodules)

    def test_socket_guard_blocks_external_tcp_while_allowing_loopback(self) -> None:
        live_guard.install()
        env = {k: v for k, v in os.environ.items() if k not in (live_guard.LIVE_TESTS_ENV, live_guard.LIVE_WRITES_ENV)}
        with mock.patch.dict(os.environ, env, clear=True):
            # External socket connection (e.g. requests / raw TCP) is blocked before any packet leaves
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            try:
                with self.assertRaises(LiveCallBlocked):
                    sock.connect(("8.8.8.8", 443))
                with self.assertRaises(LiveCallBlocked):
                    socket.create_connection(("chronicle.googleapis.com", 443), timeout=0.5)
            finally:
                sock.close()

            # Loopback socket server + client round-trip remains allowed for local FastAPI/IPC tests
            srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            srv.bind(("127.0.0.1", 0))
            srv.listen(1)
            port = srv.getsockname()[1]
            try:
                with socket.create_connection(("127.0.0.1", port), timeout=1.0) as client_sock:
                    conn, _ = srv.accept()
                    with conn:
                        client_sock.sendall(b"ping")
                        self.assertEqual(conn.recv(4), b"ping")
            finally:
                srv.close()

    def test_secops_ignore_dotenv_prevents_implicit_dotenv_leakage(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            dotenv = tmp_path / ".env"
            dotenv.write_text(
                "GCP_PROJECT_ID=leaked-project\nSECOPS_CUSTOMER_ID=leaked-cust\n",
                encoding="utf-8",
            )
            orig_cwd = Path.cwd()
            os.chdir(tmp_path)
            try:
                with mock.patch.dict(os.environ, {"SECOPS_IGNORE_DOTENV": "1"}, clear=True):
                    with self.assertRaises(SecOpsConfigurationError):
                        load_config()
                # Explicit env_file= still loads when requested by config unit tests
                with mock.patch.dict(os.environ, {"SECOPS_IGNORE_DOTENV": "1"}, clear=True):
                    cfg = load_config(env_file=dotenv)
                    self.assertEqual(cfg.project_id, "leaked-project")
            finally:
                os.chdir(orig_cwd)


if __name__ == "__main__":
    unittest.main()
