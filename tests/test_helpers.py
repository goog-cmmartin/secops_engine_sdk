"""Test helper utilities for Google SecOps live and offline test suites."""

from typing import Optional
import unittest

from adapters.google_secops import GoogleSecOpsAdapter
from engine.config import SecOpsConfigurationError
from engine.facade import SecOpsEngine


def get_live_adapter() -> GoogleSecOpsAdapter:
    """Instantiates GoogleSecOpsAdapter from configured environment or .env.

    If credentials or tenant parameters are missing, raises unittest.SkipTest
    so live test suites skip gracefully on unconfigured environments without failing CI.
    """
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
