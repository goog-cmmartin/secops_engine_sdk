"""Central switch for agent-driven git commits.

Agents (ProposalManager, IssueMaterializer) write durable records to the repo
and commit them. Test suites and dry-run environments must never mutate the
operator's git history, so every committer consults this guard first.

Set ``SECOPS_DISABLE_GIT_COMMITS=1`` (also accepts true/yes/on) to disable.
"""

import os

DISABLE_ENV_VAR = "SECOPS_DISABLE_GIT_COMMITS"
_TRUTHY = {"1", "true", "yes", "on"}


def git_commits_enabled() -> bool:
    """Returns False when agent git commits are disabled via environment."""
    return os.environ.get(DISABLE_ENV_VAR, "").strip().lower() not in _TRUTHY
