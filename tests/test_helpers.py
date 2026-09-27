"""Test helper utilities for Google SecOps live and offline test suites."""

from typing import Optional
import unittest

from adapters.google_secops import GoogleSecOpsAdapter
from engine.config import SecOpsConfigurationError
from engine.facade import SecOpsEngine
from tests.live_guard import LIVE_TESTS_ENV, live_tests_enabled


def get_live_adapter() -> GoogleSecOpsAdapter:
    """Instantiates GoogleSecOpsAdapter from configured environment or .env.

    If credentials or tenant parameters are missing, raises unittest.SkipTest
    so live test suites skip gracefully on unconfigured environments without failing CI.
    Also skips unless SECOPS_LIVE_TESTS=1: credentials alone are not an opt-in.
    """
    if not live_tests_enabled():
        raise unittest.SkipTest(f"Live tenant tests disabled; set {LIVE_TESTS_ENV}=1 to run.")
    try:
        return GoogleSecOpsAdapter()
    except SecOpsConfigurationError as e:
        raise unittest.SkipTest(f"Live Google SecOps tenant not configured: {e}") from e
    except Exception as e:
        # Catch ADC / credential resolution errors when run on bare CI runners
        err_str = str(e).lower()
        if "credential" in err_str or "auth" in err_str or "gcloud" in err_str:
            raise unittest.SkipTest(f"Google Cloud ADC credentials not found: {e}") from e
        raise


def get_live_engine(adapter: Optional[GoogleSecOpsAdapter] = None) -> SecOpsEngine:
    """Instantiates SecOpsEngine with live adapter.

    If credentials or tenant parameters are missing, raises unittest.SkipTest.
    """
    if adapter is None:
        adapter = get_live_adapter()
    return SecOpsEngine(adapter=adapter)
