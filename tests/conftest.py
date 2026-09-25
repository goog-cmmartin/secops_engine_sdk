"""Session-wide test safety configuration.

Disables agent-driven git commits for the entire test session. This is set at
import time (before test modules are collected) because some modules, e.g.
``clients.web.server``, construct ProposalManager/IssueMaterializer singletons
rooted at the real repository on import. Without this guard, running the suite
creates ``proposal(...)`` / issue commits on the operator's current branch.
"""

import os

from agents.core.git_guard import DISABLE_ENV_VAR

os.environ[DISABLE_ENV_VAR] = "1"
