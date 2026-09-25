"""Unit and behavioral tests for Gemini token limit discovery, counting, payload budgeting, and error recovery."""

import json
import unittest
from dataclasses import dataclass
from typing import List, Optional

from agents.core.base_adk_agent import (
    DEFAULT_MODEL_TOKEN_LIMIT,
    MAX_COLLECTION_ITEMS,
    MAX_STRING_FIELD_CHARS,
    MAX_TOOL_OUTPUT_BYTES,
    MODEL_TOKEN_LIMITS,
    _sanitize_tool_payload,
    _serialize_for_llm,
    count_tokens,
    get_model_token_limit,
)
from tests.test_helpers import get_live_engine


@dataclass
class InspectionEntity:
    name: str
    code: str
    cbn_raw: Optional[str] = None
    raw: Optional[dict] = None
    items: Optional[List[str]] = None


class TestTokenLimitsAndBudgeting(unittest.TestCase):
    """Verifies token limits, model discovery, serialization pruning, and payload budgeting."""

    def test_model_token_limits_registry(self):
        """Verify canonical model limits for Gemini 3.8 Flash, 2.5 Flash, and Pro models."""
        self.assertEqual(get_model_token_limit("gemini-3.8-flash"), 1_048_576)
        self.assertEqual(get_model_token_limit("gemini-2.5-flash"), 1_048_576)
        self.assertEqual(get_model_token_limit("gemini-2.0-flash"), 1_048_576)
        self.assertEqual(get_model_token_limit("gemini-1.5-flash"), 1_048_576)
        self.assertEqual(get_model_token_limit("gemini-1.5-pro"), 2_097_152)
        self.assertEqual(get_model_token_limit("publishers/google/models/gemini-3.8-flash"), 1_048_576)
        self.assertEqual(get_model_token_limit("unregistered-future-model"), DEFAULT_MODEL_TOKEN_LIMIT)

    def test_count_tokens_heuristic(self):
        """Verify fallback token counting calculates roughly 4 characters per token."""
        short_text = "Hello world! This is a SecOps telemetry test."
        tokens = count_tokens(None, "gemini-3.8-flash", short_text)
        self.assertGreater(tokens, 0)
        self.assertEqual(tokens, len(short_text) // 4)

    def test_serialize_excludes_cbn_raw_and_raw_fields(self):
        """Verify redundant raw payload bytes and cbn_raw are strictly omitted from LLM serialization."""
        entity = InspectionEntity(
            name="CS_EDR_PARSER",
            code="filter { json { source => 'message' } }",
            cbn_raw="ZXh0cmVtZWx5X2xhcmdlX2Jhc2U2NF9zdHJpbmc=",
            raw={"nested_heavy_api_response": "12345"},
        )
        serialized = _serialize_for_llm(entity)
        self.assertIn("name", serialized)
        self.assertIn("code", serialized)
        self.assertNotIn("cbn_raw", serialized)
        self.assertNotIn("raw", serialized)

    def test_serialize_clips_oversized_strings(self):
        """Verify strings exceeding MAX_STRING_FIELD_CHARS are cleanly clipped with an informative notice."""
        oversized_str = "A" * (MAX_STRING_FIELD_CHARS + 5000)
        serialized = _serialize_for_llm(oversized_str)
        self.assertIn("[... TRUNCATED:", serialized)
        self.assertIn("5,000 characters omitted", serialized)
        self.assertIn("Full content accessible via engine/evidence fabric", serialized)

    def test_sanitize_tool_payload_caps_large_collections(self):
        """Verify collections with > 25 items are truncated with metadata to prevent context overflow."""
        huge_list = [f"log_entry_record_{i}" for i in range(100)]
        payload = {"total_events": 100, "events": huge_list}

        # Force exceed byte budget by wrapping in small max_bytes
        sanitized = _sanitize_tool_payload(payload, max_bytes=500)
        events = sanitized.get("events", [])
        self.assertLessEqual(len(events), MAX_COLLECTION_ITEMS + 1)
        # Check truncation note
        last_item = events[-1]
        self.assertIn("_budget_truncation_notice", last_item)
        self.assertEqual(last_item["total_items"], 100)
        self.assertEqual(last_item["returned_items"], MAX_COLLECTION_ITEMS)

    def test_sanitize_tool_payload_preserves_compact_payloads(self):
        """Verify normal tool responses under budget pass through unmodified."""
        compact = {"status": "SUCCESS", "records_processed": 5, "details": "Normal telemetry response"}
        sanitized = _sanitize_tool_payload(compact, max_bytes=MAX_TOOL_OUTPUT_BYTES)
        self.assertEqual(sanitized, compact)

    def test_live_cs_edr_budgeting(self):
        """Verifies live CS_EDR parser retrieval stays well within context token budgets."""
        engine = get_live_engine()
        parser_detail = engine.get_parser("CS_EDR")
        serialized = _serialize_for_llm(parser_detail)
        sanitized = _sanitize_tool_payload(serialized)

        dumped = json.dumps(sanitized)
        # Verify it dropped from 8.5MB to < 150KB
        self.assertLess(len(dumped), 150_000, f"Serialized CS_EDR size {len(dumped)} exceeded 150KB!")
        tokens = count_tokens(None, "gemini-3.8-flash", dumped)
        self.assertLess(tokens, 35_000, f"Token count {tokens} exceeded 35,000!")


if __name__ == "__main__":
    unittest.main()
