"""Tests for the live-tenant guard (tests/live_guard.py)."""

import os
import unittest
import urllib.request
from unittest import mock

from tests import live_guard
from tests.live_guard import LiveCallBlocked, check_request

BASE = "https://us-chronicle.googleapis.com/v1alpha/projects/1/locations/us/instances/c"


class LiveGuardTest(unittest.TestCase):
    def _env(self, live=None, writes=None):
        env = {k: v for k, v in os.environ.items() if k not in (live_guard.LIVE_TESTS_ENV, live_guard.LIVE_WRITES_ENV)}
        if live:
            env[live_guard.LIVE_TESTS_ENV] = live
        if writes:
            env[live_guard.LIVE_WRITES_ENV] = writes
        return mock.patch.dict(os.environ, env, clear=True)

    def test_blocks_all_googleapis_calls_without_opt_in(self):
        with self._env():
            with self.assertRaises(LiveCallBlocked):
                check_request("GET", f"{BASE}/rules")

    def test_non_google_hosts_are_not_guarded(self):
        with self._env():
            check_request("POST", "http://localhost:8000/api/tenants")
            check_request("POST", "https://hooks.slack.com/services/x")

    def test_live_reads_allowed_but_writes_blocked(self):
        with self._env(live="1"):
            check_request("GET", f"{BASE}/rules?pageSize=5")
            check_request("POST", f"{BASE}:verifyRuleText")
            check_request("POST", f"{BASE}/legacySearches:legacyCaseSearchEverything")
            for method, url in [
                ("PATCH", f"{BASE}/cases/1"),
                ("DELETE", f"{BASE}/rules/ru_1"),
                ("POST", f"{BASE}/cases/1/caseComments"),
                ("POST", f"{BASE}/findingsRefinements"),
                ("POST", f"{BASE}/curatedRuleSets/x/curatedRuleSetDeployments:batchUpdate"),
                ("POST", f"{BASE}/logTypes/AUDITD/logs:import"),
                ("POST", f"{BASE}/events:import"),
                ("POST", "https://us-malachiteingestion-pa.googleapis.com/v2/unstructuredlogentries:batchCreate"),
            ]:
                with self.subTest(method=method, url=url):
                    with self.assertRaises(LiveCallBlocked):
                        check_request(method, url)

    def test_writes_require_both_flags(self):
        with self._env(writes="1"):
            with self.assertRaises(LiveCallBlocked):
                check_request("PATCH", f"{BASE}/cases/1")
        with self._env(live="1", writes="1"):
            check_request("PATCH", f"{BASE}/cases/1")

    def test_blocked_error_escapes_broad_except_exception(self):
        self.assertFalse(issubclass(LiveCallBlocked, Exception))

    def test_urlopen_is_patched_in_this_session(self):
        req = urllib.request.Request(f"{BASE}/cases/1", data=b"{}", method="PATCH")
        with self._env(live="1"):
            with self.assertRaises(LiveCallBlocked):
                urllib.request.urlopen(req, timeout=1)

    def test_live_helpers_skip_without_opt_in(self):
        from tests.test_helpers import get_live_adapter

        with self._env():
            with self.assertRaises(unittest.SkipTest):
                get_live_adapter()


if __name__ == "__main__":
    unittest.main()
