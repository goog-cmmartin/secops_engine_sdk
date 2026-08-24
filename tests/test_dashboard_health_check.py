"""Tests for dashboard health check workflow (Milestone 5.9)."""

import os

import pytest

from tests.test_helpers import get_live_engine
from engine import SecOpsEngine


@pytest.fixture
def live_engine():
    """Provides configured SecOps engine for live testing."""
    return get_live_engine()


@pytest.mark.skipif(
    os.environ.get("RUN_SLOW_E2E") != "1",
    reason=(
        "Slow live E2E: serially executes every widget query on a large "
        "dashboard and can exceed short CI timeouts. Set RUN_SLOW_E2E=1 to run."
    ),
)
def test_dashboard_health_check_e2e(live_engine):
    """E2E verification that health check workflow executes all dashboard queries."""
    # Target the "Data Ingestion and Health" dashboard
    result = live_engine.run_dashboard_health_check(
        dashboard_name="Data Ingestion and Health"
    )
    
    # Verify structure
    assert "dashboard_id" in result
    assert "query_results" in result
    assert "summary" in result
    assert "errors" in result
    
    # Verify at least one query executed
    assert len(result["query_results"]) > 0
    
    # Verify query result structure
    for qr in result["query_results"]:
        assert "query_name" in qr
        assert "chart_title" in qr
        assert "success" in qr
        
        if qr["success"]:
            assert "row_count" in qr
            assert "columns" in qr
        else:
            assert "error" in qr
    
    # Print summary for manual verification
    print("\n" + result["summary"])
    
    # Verify summary format
    assert "Dashboard Health Check:" in result["summary"]
    assert "Total Queries:" in result["summary"]
    assert "Successful:" in result["summary"]


def test_dashboard_not_found(live_engine):
    """Verify error handling when dashboard doesn't exist."""
    with pytest.raises(ValueError, match="not found"):
        live_engine.run_dashboard_health_check(dashboard_name="NonexistentDashboard")


def test_health_check_capability_registered(live_engine):
    """Verify health check is properly registered in capability registry."""
    cap = live_engine.registry.get("dashboard.health_check")
    
    assert cap is not None
    assert cap.category == "dashboard"
    assert cap.composed is True
    assert cap.mcp_tool_name == "run_dashboard_health_check"
