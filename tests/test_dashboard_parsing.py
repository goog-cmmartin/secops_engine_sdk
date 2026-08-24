"""Test dashboard query parsing."""
import pytest
from adapters.google_secops import GoogleSecOpsAdapter
from engine.domain import DashboardQueryResult


def test_dashboard_result_parsing():
    """Test that _parse_dashboard_result correctly transforms column-oriented to row-oriented data."""
    adapter = GoogleSecOpsAdapter()
    
    # Mock raw API response
    raw_response = {
        'results': [
            {
                'column': 'timestamp',
                'values': [
                    {'value': {'stringVal': '2024-01-01T00:00:00Z'}},
                    {'value': {'stringVal': '2024-01-02T00:00:00Z'}},
                ]
            },
            {
                'column': 'count',
                'values': [
                    {'value': {'int64Val': 123}},
                    {'value': {'int64Val': 456}},
                ]
            },
            {
                'column': 'bytes',
                'values': [
                    {'value': {'doubleVal': 1024.5}},
                    {'value': {'doubleVal': 2048.75}},
                ]
            },
        ],
        'timeWindow': {'startTime': '2024-01-01T00:00:00Z', 'endTime': '2024-01-03T00:00:00Z'},
        'dataSources': ['feed_1', 'feed_2'],
        'dialect': 'YL2',
        'lastBackendCacheRefreshedTime': '2024-01-03T12:00:00Z'
    }
    
    result = adapter._parse_dashboard_result(raw_response, 'test_query')
    
    # Verify structure
    assert isinstance(result, DashboardQueryResult)
    assert result.query_name == 'test_query'
    assert result.dialect == 'YL2'
    assert result.data_sources == ['feed_1', 'feed_2']
    assert result.time_window == {'startTime': '2024-01-01T00:00:00Z', 'endTime': '2024-01-03T00:00:00Z'}
    assert result.columns == ['timestamp', 'count', 'bytes']
    assert result.total_rows == 2
    assert result.last_cache_refreshed_time == '2024-01-03T12:00:00Z'
    assert result.raw == raw_response
    
    # Verify rows
    assert len(result.rows) == 2
    assert result.rows[0] == {
        'timestamp': '2024-01-01T00:00:00Z',
        'count': 123,
        'bytes': 1024.5,
    }
    assert result.rows[1] == {
        'timestamp': '2024-01-02T00:00:00Z',
        'count': 456,
        'bytes': 2048.75,
    }
    
    # Verify convenience properties
    assert result.row_count == 2
    assert result.column_count == 3


def test_dashboard_result_empty():
    """Test parsing empty dashboard results."""
    adapter = GoogleSecOpsAdapter()
    
    raw_response = {
        'results': [],
        'timeWindow': {},
        'dataSources': [],
        'dialect': 'YL2'
    }
    
    result = adapter._parse_dashboard_result(raw_response, 'empty_query')
    
    assert result.query_name == 'empty_query'
    assert result.columns == []
    assert result.rows == []
    assert result.total_rows == 0
    assert result.row_count == 0
    assert result.column_count == 0
