import os
import unittest
from datetime import datetime, timezone
from unittest.mock import patch

from engine.config import SecOpsConfig, SecOpsConfigurationError, load_config
from engine.domain import FieldFilter, FilterOperator
from engine.facade import SecOpsEngine
from engine.parsing import parse_priority, parse_status, parse_timestamp


class TestConfigAndParsing(unittest.TestCase):
    def test_load_config_from_env_or_params(self):
        config = load_config(
            project_id="test-proj",
            customer_id="test-cust",
            project_number="12345",
            location="us",
        )
        self.assertEqual(config.project_id, "test-proj")
        self.assertEqual(config.customer_id, "test-cust")
        self.assertEqual(config.project_number, "12345")
        self.assertEqual(config.location, "us")
        self.assertEqual(config.api_base, "https://us-chronicle.googleapis.com")

    def test_load_config_missing_required_raises_error(self):
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaises(SecOpsConfigurationError):
                # Pass a dummy non-existent env_file to ensure isolation
                from pathlib import Path
                load_config(env_file=Path("/tmp/nonexistent.env"))

    def test_parse_timestamp_various_formats(self):
        # Epoch ms
        dt1 = parse_timestamp(1700000000000)
        self.assertIsNotNone(dt1)
        self.assertEqual(dt1.tzinfo, timezone.utc)

        # Epoch seconds
        dt2 = parse_timestamp(1700000000)
        self.assertIsNotNone(dt2)

        # ISO string
        dt3 = parse_timestamp("2026-08-18T12:00:00Z")
        self.assertIsNotNone(dt3)
        self.assertEqual(dt3.year, 2026)

        # None / invalid
        self.assertIsNone(parse_timestamp(None))
        self.assertIsNone(parse_timestamp("invalid-date"))

    def test_parse_status_and_priority(self):
        self.assertEqual(parse_status("OPEN").value, "OPEN")
        self.assertEqual(parse_status("CLOSED").value, "CLOSED")
        self.assertEqual(parse_status("OTHER").value, "UNKNOWN")

        self.assertEqual(parse_priority("CRITICAL").value, "CRITICAL")
        self.assertEqual(parse_priority("HIGH").value, "HIGH")
        self.assertEqual(parse_priority("MEDIUM").value, "MEDIUM")
        self.assertEqual(parse_priority("LOW").value, "LOW")
        self.assertEqual(parse_priority("UNKNOWN").value, "UNKNOWN")

    def test_field_filter_contains_regex_escaping(self):
        # When value contains regex characters like . and (
        filt = FieldFilter("metadata.description", FilterOperator.CONTAINS, "error (code: 404.1)")
        clause = filt.to_udm_clause()
        self.assertIn(r"error\ \(code:\ 404\.1\)", clause)

    def test_secops_engine_lazy_workflow_initialization(self):
        # SecOpsEngine initializes without pre-constructing workflow instances
        dummy_adapter = object()
        engine = SecOpsEngine(adapter=dummy_adapter)
        self.assertEqual(len(engine._wf_cache), 0)

        # Accessing an internal workflow instantiates and caches it
        wf = engine._search_udm_wf
        self.assertIsNotNone(wf)
        self.assertIn("_search_udm_wf", engine._wf_cache)
        self.assertIs(engine._search_udm_wf, wf)


if __name__ == "__main__":
    unittest.main()
