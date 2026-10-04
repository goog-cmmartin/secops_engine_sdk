"""Session-wide test safety configuration.

Set at import time (before test modules are collected) because some modules,
e.g. ``clients.web.server``, construct ProposalManager/IssueMaterializer
singletons on import.

- Disables agent-driven git commits, so the suite never commits anywhere.
- Points the SOC ledger at a throwaway temp directory, so the suite never writes
  issue/proposal records into the operator's real ledger (~/.secops/ledger).
- Points the web server's runtime state (chat history, .state, work queue,
  evidence, knowledge store) at a temp directory, so API tests never post
  messages into the operator's live chat.
"""

import atexit
import os
import shutil
import tempfile

from agents.core.git_guard import DISABLE_ENV_VAR
from agents.core.ledger import LEDGER_ROOT_ENV_VAR

os.environ[DISABLE_ENV_VAR] = "1"

_LEDGER_TMP = tempfile.mkdtemp(prefix="secops-test-ledger-")
os.environ[LEDGER_ROOT_ENV_VAR] = _LEDGER_TMP
atexit.register(shutil.rmtree, _LEDGER_TMP, ignore_errors=True)

_WEB_STATE_TMP = tempfile.mkdtemp(prefix="secops-test-webstate-")
os.environ["SECOPS_WEB_STATE_ROOT"] = _WEB_STATE_TMP
atexit.register(shutil.rmtree, _WEB_STATE_TMP, ignore_errors=True)

# Live-tenant guard: a populated .env must never make pytest call (or mutate) a real
# tenant. Live reads need SECOPS_LIVE_TESTS=1; writes also need
# SECOPS_ALLOW_LIVE_WRITES=1. See tests/live_guard.py.
from tests import live_guard  # noqa: E402

live_guard.install()

# Firestore clients use gRPC (not urllib), so keep the evidence store / work queue
# factories on local backends unless live tests are explicitly enabled.
if not live_guard.live_tests_enabled():
    os.environ["SECOPS_DISABLE_FIRESTORE"] = "1"
