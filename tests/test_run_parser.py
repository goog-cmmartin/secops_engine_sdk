"""Acceptance and Behavioral Tests for Parser Run & Unparsed Logs Diagnostics.

Verifies:
1. Low-level :runParser capability (`engine.run_parser`).
2. High-level composite workflow (`engine.diagnose_unparsed_logs`).
3. Deterministic log type display name resolution.
4. Strict anti-mock audit compliance.
"""

import os
import unittest
from datetime import datetime

from engine import (
    ParserRunResult,
    ParserRunResultEntry,
    SecOpsEngine,
    UnparsedLogDiagnostic,
    UnparsedLogsDiagnosticBatch,
)
from tests.test_helpers import get_live_engine


class TestRunParserLive(unittest.TestCase):
    """Live acceptance tests for Parser Run and Unparsed Log Diagnostics."""

    @classmethod
    def setUpClass(cls):
        cls.engine = get_live_engine()

    def test_01_run_parser_live(self):
        """Verifies low-level :runParser execution against a sample log."""
        test_log = "Feb 23 11:22:33 host pan_test: test sample log entry"
        res = self.engine.run_parser(log_type="PAN_FIREWALL", raw_log_text=test_log)

        self.assertIsInstance(res, ParserRunResult)
        self.assertEqual(res.log_type, "PAN_FIREWALL")
        self.assertGreater(res.total_runs, 0)
        self.assertIsInstance(res.retrieved_at, datetime)
        self.assertGreater(len(res.entries), 0)

        entry = res.entries[0]
        self.assertIsInstance(entry, ParserRunResultEntry)
        self.assertIsInstance(entry.is_success, bool)
        self.assertTrue(len(entry.log_b64) > 0)
        self.assertIn("runParserResults", res.raw)

    def test_02_diagnose_unparsed_logs_live(self):
        """Verifies composite diagnosis of unparsed logs for PAN_FIREWALL."""
        batch = self.engine.diagnose_unparsed_logs(
            log_type="PAN_FIREWALL",
            lookback_hours=168,
            limit=2,
        )

        self.assertIsInstance(batch, UnparsedLogsDiagnosticBatch)
        self.assertEqual(batch.log_type, "PAN_FIREWALL")
        self.assertEqual(batch.display_name, "Palo Alto Networks Firewall")
        self.assertIsInstance(batch.total_unparsed_found, int)
        self.assertIsInstance(batch.total_diagnosed, int)
        self.assertIsNotNone(batch.active_parser_summary)

        if batch.diagnostics:
            diag = batch.diagnostics[0]
            self.assertIsInstance(diag, UnparsedLogDiagnostic)
            self.assertTrue(len(diag.log_id) > 0)
            self.assertTrue(len(diag.error_message) > 0)
            self.assertIn(diag.error_category, [
                "TYPE_MISMATCH",
                "CBN_NORMALIZATION_ERROR",
                "EMPTY_PARSE_TREE",
                "SYNTAX_ERROR",
                "PARSER_FAILURE",
                "NO_REPRO_IN_TEST",
            ])

    def test_03_no_mock_data_audit(self):
        """CI Invariant: Ensure zero banned mock/synthetic terms in production files."""
        repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        banned_terms = ["mock", "fixture", "dummy", "fake", "sample_data", "test_data"]

        prod_files = [
            os.path.join(repo_root, "engine", "workflows", "parser.py"),
            os.path.join(repo_root, "engine", "domain.py"),
            os.path.join(repo_root, "adapters", "google_secops.py"),
            os.path.join(repo_root, "engine", "facade.py"),
        ]

        for path in prod_files:
            with open(path, "r", encoding="utf-8") as f:
                content = f.read()
                lines = content.split("\n")
                for line_num, line in enumerate(lines, 1):
                    # Skip comments or strings mentioning banned patterns explicitly if any
                    lower_line = line.lower()
                    for term in banned_terms:
                        if term in lower_line:
                            # Allow if part of variable names like 'mock' is not present
                            # We check exact token matches
                            tokens = [t.strip("\"'()[]{},: ") for t in lower_line.split()]
                            for tok in tokens:
                                if tok == term:
                                    self.fail(
                                        f"Banned term '{term}' found in production file "
                                        f"'{os.path.relpath(path, repo_root)}' line {line_num}: {line}"
                                    )


if __name__ == "__main__":
    unittest.main()
