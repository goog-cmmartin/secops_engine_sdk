# Copyright 2026 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Unit tests for engine/okf.py: OKF v0.2 parser, trust tiers, staleness, and actors."""

import unittest
from datetime import datetime, timezone

from engine.okf import (
    OKFDocument,
    OKFDocumentError,
    is_stale,
    is_valid_actor,
    normalize_verified,
    trust_tier,
)


class TestOKFDocument(unittest.TestCase):
    def test_parse_valid_document(self):
        content = """---
type: Concept
title: UDM Search
status: stable
generated: { by: "agent/v1", at: "2026-06-30T14:00:00Z" }
verified:
  - { by: "human:analyst@google.com", at: "2026-07-01T09:00:00Z" }
sources:
  - id: doc1
    resource: https://chronicle.security/docs
---

# UDM Search Overview

This is body content.
"""
        doc = OKFDocument.parse(content)
        self.assertEqual(doc.frontmatter["type"], "Concept")
        self.assertEqual(doc.frontmatter["title"], "UDM Search")
        self.assertEqual(doc.frontmatter["status"], "stable")
        self.assertEqual(doc.frontmatter["generated"]["at"], "2026-06-30T14:00:00Z")
        self.assertIn("# UDM Search Overview", doc.body)
        self.assertEqual(doc.validate_okf(), [])

    def test_trust_tiers(self):
        # 1. Unverified
        self.assertEqual(trust_tier({"type": "Concept"}), "unverified")
        self.assertEqual(trust_tier({"type": "Concept", "verified": []}), "unverified")

        # 2. Machine-confirmed
        self.assertEqual(
            trust_tier({
                "type": "Concept",
                "verified": [{"by": "process:nightly", "at": "2026-07-01T00:00:00Z"}]
            }),
            "machine-confirmed"
        )
        self.assertEqual(
            trust_tier({
                "type": "Concept",
                "verified": {"by": "deacon/v2", "at": "2026-07-01T00:00:00Z"}
            }),
            "machine-confirmed"
        )

        # 3. Human-reviewed
        self.assertEqual(
            trust_tier({
                "type": "Concept",
                "verified": [
                    {"by": "process:nightly", "at": "2026-07-01T00:00:00Z"},
                    {"by": "human:analyst@google.com", "at": "2026-07-01T09:00:00Z"}
                ]
            }),
            "human-reviewed"
        )

    def test_staleness(self):
        ref_time = datetime(2026, 9, 22, 12, 0, 0, tzinfo=timezone.utc)
        # Not stale
        self.assertFalse(is_stale({"stale_after": "2026-12-31T00:00:00Z"}, as_of=ref_time))
        # Stale
        self.assertTrue(is_stale({"stale_after": "2026-06-01T00:00:00Z"}, as_of=ref_time))
        # Absent
        self.assertFalse(is_stale({}, as_of=ref_time))

    def test_actor_validation(self):
        self.assertTrue(is_valid_actor("human:jsmith@acme.com"))
        self.assertTrue(is_valid_actor("human:user_123"))
        self.assertTrue(is_valid_actor("process:nightly-patrol"))
        self.assertTrue(is_valid_actor("agent/gemini-2.5-pro"))
        self.assertTrue(is_valid_actor("timestamp-integrity-agent/1.0"))

        self.assertFalse(is_valid_actor("invalid actor with spaces"))
        self.assertFalse(is_valid_actor("human:"))
        self.assertFalse(is_valid_actor(12345))


if __name__ == "__main__":
    unittest.main()
