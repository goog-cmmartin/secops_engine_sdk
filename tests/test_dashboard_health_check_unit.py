"""Unit tests for dashboard health check workflow orchestration."""

import pytest
from unittest.mock import Mock
from engine.workflows.dashboards import run_dashboard_health_check
from engine.domain import (
    DashboardSummary,
    DashboardDetail,
    DashboardChart,
    DashboardQuery,
    DashboardQueryResult,
)


@pytest.fixture
def mock_adapter():
    """Create a mock adapter with basic properties."""
    adapter = Mock()
    adapter.project_id = "test-project"
    adapter.customer_id = "test-customer"
    adapter.region = "us"
    return adapter


@pytest.fixture
def sample_dashboard_raw():
    """Raw dashboard data from list API."""
    return {
        "name": "projects/test-project/locations/us/instances/test-customer/dashboards/dash-1",
        "displayName": "My Dashboard",
        "description": "Test dashboard",
        "type": "CUSTOM",
        "createTime": "2024-01-01T00:00:00Z",
        "updateTime": "2024-01-01T00:00:00Z",
        "createUserId": "user-1",
        "updateUserId": "user-1",
        "access": "OWNER",
    }


@pytest.fixture
def other_dashboard_raw():
    """Raw data for a different dashboard."""
    return {
        "name": "projects/test-project/locations/us/instances/test-customer/dashboards/dash-other",
        "displayName": "Other Dashboard",
        "description": "Different dashboard",
        "type": "CUSTOM",
        "createTime": "2024-01-01T00:00:00Z",
        "updateTime": "2024-01-01T00:00:00Z",
        "createUserId": "user-1",
        "updateUserId": "user-1",
        "access": "OWNER",
    }


@pytest.fixture
def sample_dashboard_detail_raw():
    """Raw dashboard detail with chart references."""
    return {
        "name": "projects/test-project/locations/us/instances/test-customer/dashboards/dash-1",
        "displayName": "My Dashboard",
        "definition": {
            "charts": [
                {"dashboardChart": "chart-1"},
                {"dashboardChart": "chart-2"},
            ],
        },
    }


@pytest.fixture
def batch_charts_response():
    """Batch get charts response."""
    return {
        "dashboardCharts": [
            {
                "name": "chart-1",
                "displayName": "Chart 1",
                "chartDatasource": {"dashboardQuery": "query-1"},
            },
            {
                "name": "chart-2",
                "displayName": "Chart 2",
                "chartDatasource": {"dashboardQuery": "query-2"},
            },
        ]
    }


@pytest.fixture
def query_response():
    """Dashboard query response."""
    return {
        "name": "query-1",
        "queryText": "SELECT * FROM logs",
        "dialect": "SOAR_QUERY",
        "dataSources": ["logs"],
        "timeWindow": {},
    }


def test_health_check_validates_dashboard_not_found(mock_adapter, other_dashboard_raw):
    """Verify error handling when dashboard name doesn't match."""
    # Mock list_native_dashboards to return different dashboard
    mock_adapter.list_native_dashboards = Mock(
        return_value={"nativeDashboards": [other_dashboard_raw]}
    )
    
    with pytest.raises(ValueError, match="Dashboard 'My Dashboard' not found"):
        run_dashboard_health_check(mock_adapter, "My Dashboard")


def test_health_check_executes_all_queries(
    mock_adapter,
    sample_dashboard_raw,
    sample_dashboard_detail_raw,
    batch_charts_response,
    query_response,
):
    """Verify health check executes all dashboard queries."""
    # Mock list_native_dashboards
    mock_adapter.list_native_dashboards = Mock(
        return_value={"nativeDashboards": [sample_dashboard_raw]}
    )
    
    # Mock get_native_dashboard
    mock_adapter.get_native_dashboard = Mock(return_value=sample_dashboard_detail_raw)
    
    # Mock batch_get_dashboard_charts
    mock_adapter.batch_get_dashboard_charts = Mock(return_value=batch_charts_response)
    
    # Mock get_dashboard_query
    mock_adapter.get_dashboard_query = Mock(return_value=query_response)
    
    # Mock execute_dashboard_query
    mock_adapter.execute_dashboard_query = Mock(
        return_value=DashboardQueryResult(
            query_name="query-1",
            dialect="SOAR_QUERY",
            data_sources=["logs"],
            time_window={"start": "2024-01-01", "end": "2024-01-02"},
            columns=["col1"],
            rows=[{"col1": "value1"}],
            total_rows=1,
        )
    )
    
    # Execute health check
    result = run_dashboard_health_check(mock_adapter, "My Dashboard")
    
    # Validate structure
    assert "dashboard_id" in result
    assert "query_results" in result
    assert "summary" in result
    assert "errors" in result
    
    # Validate query execution
    assert len(result["query_results"]) == 2
    assert result["query_results"][0]["success"] is True
    assert result["query_results"][0]["chart_title"] == "Chart 1"
    assert result["query_results"][1]["chart_title"] == "Chart 2"
    
    # Validate adapter calls
    assert mock_adapter.execute_dashboard_query.call_count == 2
    mock_adapter.batch_get_dashboard_charts.assert_called_once_with(["chart-1", "chart-2"])
    assert mock_adapter.get_dashboard_query.call_count == 2
