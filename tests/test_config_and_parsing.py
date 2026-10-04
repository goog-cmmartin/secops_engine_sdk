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

    def test_project_number_falls_back_to_project_id(self):
        from pathlib import Path
        with patch.dict(os.environ, {}, clear=True):
            cfg = load_config(
                project_id="my-gcp-project",
                customer_id="cust-uuid",
                env_file=Path("/tmp/nonexistent.env"),
            )
            self.assertEqual(cfg.project_number, "my-gcp-project")

    def test_env_file_handles_export_and_inline_comments(self):
        import tempfile
        from pathlib import Path
        content = (
            "export GCP_PROJECT_ID=proj-from-export # inline comment\n"
            "SECOPS_CUSTOMER_ID='cust-quoted#1'\n"
            "SECOPS_REGION=europe-west2   # region comment\n"
        )
        with tempfile.NamedTemporaryFile("w", suffix=".env", delete=False, encoding="utf-8") as tf:
            tf.write(content)
            env_path = Path(tf.name)
        try:
            with patch.dict(os.environ, {}, clear=True):
                cfg = load_config(env_file=env_path)
                self.assertEqual(cfg.project_id, "proj-from-export")
                self.assertEqual(cfg.customer_id, "cust-quoted#1")
                self.assertEqual(cfg.location, "europe-west2")
        finally:
            env_path.unlink(missing_ok=True)

    def test_adapter_has_no_duplicate_method_definitions(self):
        import ast
        adapter_path = os.path.abspath(
            os.path.join(os.path.dirname(__file__), "..", "adapters", "google_secops.py")
        )
        with open(adapter_path, "r", encoding="utf-8") as fh:
            tree = ast.parse(fh.read(), adapter_path)
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef):
                seen = set()
                for item in node.body:
                    if isinstance(item, ast.FunctionDef):
                        self.assertNotIn(
                            item.name,
                            seen,
                            f"Duplicate method '{item.name}' in {node.name}",
                        )
                        seen.add(item.name)

    def test_adapter_request_preserves_pre_encoded_percent_sequences(self):
        from unittest.mock import MagicMock
        from adapters.google_secops import GoogleSecOpsAdapter
        from engine.auth import CredentialProvider

        cfg = SecOpsConfig(project_id="p", customer_id="c", project_number="123")
        prov = CredentialProvider(static_token="tok")
        adapter = GoogleSecOpsAdapter(config=cfg, credential_provider=prov)

        ok_resp = MagicMock()
        ok_resp.read.return_value = b'{"name": "projects/p/locations/us/instances/c/cases/100"}'
        ok_resp.__enter__.return_value = ok_resp
        ok_resp.__exit__.return_value = False

        with patch("urllib.request.urlopen", return_value=ok_resp) as uopen:
            adapter.update_case("case id/with space", {"displayName": "test"})
            req_obj = uopen.call_args.args[0]
            self.assertIn("with%20space", req_obj.full_url)
            self.assertNotIn("with%2520space", req_obj.full_url)


if __name__ == "__main__":
    unittest.main()
