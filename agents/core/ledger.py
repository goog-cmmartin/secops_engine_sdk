"""Location of the durable SOC ledger (issue records and change proposals).

Issue records (``.issues/``) and change proposals (``.proposals/``) are tenant
operational data, not SDK source. They live in a separate git repository, the
*ledger*, outside the SDK checkout, so that agent commits never land on the SDK's
branches and tenant evidence is never pushed with the code.

Resolution order (see ``resolve_ledger_root``):
1. An explicit ``root_dir`` passed by the caller (tests, tooling).
2. ``SECOPS_LEDGER_ROOT`` environment variable.
3. ``~/.secops/ledger`` default.

A ledger path inside the SDK repository is rejected. When git commits are
enabled (see ``git_guard``), a missing ledger repository is initialized
automatically.
"""

import logging
import os
from pathlib import Path
import subprocess
from typing import Optional, Union

from agents.core.git_guard import git_commits_enabled

logger = logging.getLogger(__name__)

LEDGER_ROOT_ENV_VAR = "SECOPS_LEDGER_ROOT"
DEFAULT_LEDGER_ROOT = Path.home() / ".secops" / "ledger"
SDK_REPO_ROOT = Path(__file__).resolve().parent.parent.parent


class LedgerLocationError(ValueError):
    """Raised when the ledger would be placed inside the SDK repository."""


def _is_within(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
        return True
    except ValueError:
        return False


def resolve_ledger_root(root_dir: Optional[Union[str, Path]] = None) -> Path:
    """Returns the absolute ledger root, creating it (and its git repo) if needed.

    Raises:
        LedgerLocationError: if the resolved path is inside the SDK repository.
    """
    if root_dir is not None:
        raw = Path(root_dir)
    elif os.environ.get(LEDGER_ROOT_ENV_VAR, "").strip():
        raw = Path(os.environ[LEDGER_ROOT_ENV_VAR].strip())
    else:
        raw = DEFAULT_LEDGER_ROOT

    root = raw.expanduser().resolve()
    if _is_within(root, SDK_REPO_ROOT):
        raise LedgerLocationError(
            f"SOC ledger path '{root}' is inside the SDK repository '{SDK_REPO_ROOT}'. "
            f"Set {LEDGER_ROOT_ENV_VAR} to a directory outside the repo "
            f"(default: {DEFAULT_LEDGER_ROOT})."
        )

    root.mkdir(parents=True, exist_ok=True)
    if git_commits_enabled():
        _ensure_git_repo(root)
    return root


def _ensure_git_repo(root: Path) -> None:
    """Initializes ``root`` as a standalone git repository if it is not already one."""
    probe = subprocess.run(
        ["git", "rev-parse", "--show-toplevel"],
        cwd=str(root),
        capture_output=True,
        text=True,
        check=False,
    )
    if probe.returncode == 0 and Path(probe.stdout.strip()).resolve() == root:
        return
    if probe.returncode == 0:
        # Nested inside some other repository; commits would land there. Give the
        # ledger its own repository so its history stays isolated.
        logger.warning("Ledger %s is nested in repo %s; initializing a dedicated repo.",
                       root, probe.stdout.strip())
    res = subprocess.run(["git", "init", "-q"], cwd=str(root), capture_output=True,
                         text=True, check=False)
    if res.returncode == 0:
        logger.info("Initialized SOC ledger git repository at %s", root)
    else:
        logger.warning("Could not initialize ledger repo at %s: %s", root, res.stderr.strip())
