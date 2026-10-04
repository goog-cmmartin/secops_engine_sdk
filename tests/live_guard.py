"""Test-suite guard against unintended calls to live Google Cloud / SecOps tenants.

Having a populated ``.env`` must never be enough to make ``pytest`` talk to (or
mutate) a real tenant. Two explicit opt-ins are required:

- ``SECOPS_LIVE_TESTS=1``         allow live *read* calls to ``*.googleapis.com``.
- ``SECOPS_ALLOW_LIVE_WRITES=1``  additionally allow mutating calls (PATCH/DELETE/PUT,
                                  and POSTs that are not known read-only RPCs,
                                  including log ingestion).

``install()`` wraps ``urllib.request.urlopen`` (the single HTTP chokepoint used by
the SecOps adapter, workflows and the logjammer SecOpsSink). Blocked calls raise
``LiveCallBlocked``, a ``BaseException`` so broad ``except Exception`` handlers in
workflow code cannot swallow it and report a misleading pass.
"""

import os
import urllib.parse
import urllib.request
import unittest

LIVE_TESTS_ENV = "SECOPS_LIVE_TESTS"
LIVE_WRITES_ENV = "SECOPS_ALLOW_LIVE_WRITES"

# POST RPCs that are read-only (no persisted tenant state change).
READ_ONLY_POST_SUFFIXES = (
    "/legacy:legacyFetchUdmSearchView",
    ":searchRawLogs",
    "/legacySearches:legacyCaseSearchEverything",
    "/legacySearches:legacyGetCasesFilterValues",
    "/legacyPlaybooks:legacyGetWorkflowMenuCardsWithEnvFilter",
    "/legacyPlaybooks:legacyGetWorkflowFullInfoWithEnvFilterByIdentifier",
    "/legacyPlaybooks:legacyGetPlaybookStatsMap",
    "/legacyPlaybooks:legacyGetWorkflowInstancesCards",
    "/legacyPlaybooks:legacyGetWorkflowInstance",
    ":countAllCuratedRuleSetDetections",
    ":testFindingsRefinement",
    "/dashboardQueries:execute",
    ":runParser",
    ":verifyRuleText",
    ":validateQuery",
    "logging.googleapis.com/v2/entries:list",
    # Cancelling a long-running operation the test itself started (UDM search timeout path).
    ":cancel",
)


class LiveCallBlocked(BaseException):
    """Raised when a test attempts a live tenant call without explicit opt-in."""


def live_tests_enabled() -> bool:
    return os.environ.get(LIVE_TESTS_ENV) == "1"


def live_writes_enabled() -> bool:
    return live_tests_enabled() and os.environ.get(LIVE_WRITES_ENV) == "1"


def require_live(test_case: unittest.TestCase) -> None:
    """Skip a test that reads from a live tenant / GCP project unless live tests are enabled."""
    if not live_tests_enabled():
        test_case.skipTest(f"Calls a live tenant; set {LIVE_TESTS_ENV}=1 to run.")


def require_gemini(test_case: unittest.TestCase) -> None:
    """Skip a test that needs a real Gemini API key."""
    if not (os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")):
        test_case.skipTest("No GEMINI_API_KEY / GOOGLE_API_KEY set.")


def require_live_writes(test_case: unittest.TestCase) -> None:
    """Skip a test that mutates tenant state unless writes are explicitly allowed."""
    if not live_writes_enabled():
        test_case.skipTest(
            f"Mutates the live tenant; set {LIVE_TESTS_ENV}=1 and {LIVE_WRITES_ENV}=1 to run."
        )


def _is_read_only(method: str, url: str) -> bool:
    if method in ("GET", "HEAD"):
        return True
    if method != "POST":
        return False
    path = url.split("?", 1)[0]
    return path.endswith(READ_ONLY_POST_SUFFIXES)


def check_request(method: str, url: str) -> None:
    host = (urllib.parse.urlparse(url).hostname or "").lower()
    if not host.endswith("googleapis.com"):
        return
    if not live_tests_enabled():
        raise LiveCallBlocked(
            f"Live call blocked in tests: {method} {url.split('?', 1)[0]} "
            f"(set {LIVE_TESTS_ENV}=1 to allow live reads)"
        )
    if not _is_read_only(method, url) and not live_writes_enabled():
        raise LiveCallBlocked(
            f"Live WRITE blocked in tests: {method} {url.split('?', 1)[0]} "
            f"(set {LIVE_WRITES_ENV}=1 to allow tenant mutations)"
        )


_installed = False


def install() -> None:
    global _installed
    if _installed:
        return
    real_urlopen = urllib.request.urlopen

    def guarded_urlopen(url, data=None, *args, **kwargs):
        if isinstance(url, urllib.request.Request):
            full_url, method = url.full_url, url.get_method()
        else:
            full_url, method = str(url), ("POST" if data is not None else "GET")
        check_request(method, full_url)
        return real_urlopen(url, data, *args, **kwargs)

    urllib.request.urlopen = guarded_urlopen
    _installed = True
