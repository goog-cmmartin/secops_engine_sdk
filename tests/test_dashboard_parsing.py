"""Test dashboard query parsing."""
import unittest
from adapters.google_secops import GoogleSecOpsAdapter
from engine.domain import DashboardQueryResult


class TestDashboardParsing(unittest.TestCase):
    def test_dashboard_result_parsing(self):
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
        self.assertIsInstance(result, DashboardQueryResult)
        self.assertEqual(result.query_name, 'test_query')
        self.assertEqual(result.dialect, 'YL2')
        self.assertEqual(result.data_sources, ['feed_1', 'feed_2'])
        self.assertEqual(result.time_window, {'startTime': '2024-01-01T00:00:00Z', 'endTime': '2024-01-03T00:00:00Z'})
        self.assertEqual(result.columns, ['timestamp', 'count', 'bytes'])
        self.assertEqual(result.total_rows, 2)
        self.assertEqual(result.last_cache_refreshed_time, '2024-01-03T12:00:00Z')
        self.assertEqual(result.raw, raw_response)

        # Verify rows
        self.assertEqual(len(result.rows), 2)
        self.assertEqual(result.rows[0], {
            'timestamp': '2024-01-01T00:00:00Z',
            'count': 123,
            'bytes': 1024.5,
        })
        self.assertEqual(result.rows[1], {
            'timestamp': '2024-01-02T00:00:00Z',
            'count': 456,
            'bytes': 2048.75,
        })

        # Verify convenience properties
        self.assertEqual(result.row_count, 2)
        self.assertEqual(result.column_count, 3)

    def test_dashboard_result_empty(self):
        """Test parsing empty dashboard results."""
        adapter = GoogleSecOpsAdapter()

        raw_response = {
            'results': [],
            'timeWindow': {},
            'dataSources': [],
            'dialect': 'YL2'
        }

        result = adapter._parse_dashboard_result(raw_response, 'empty_query')

        self.assertEqual(result.query_name, 'empty_query')
        self.assertEqual(result.columns, [])
        self.assertEqual(result.rows, [])
        self.assertEqual(result.total_rows, 0)
        self.assertEqual(result.row_count, 0)
        self.assertEqual(result.column_count, 0)
