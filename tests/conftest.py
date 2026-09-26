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
