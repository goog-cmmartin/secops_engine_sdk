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

"""Unit tests for knowledge/attesters/yaral_equality.py."""

import unittest

from knowledge.attesters.yaral_equality import attest_yaral, canonicalize_yaral


class TestYaraLEqualityAttester(unittest.TestCase):
    def test_canonicalize_yaral(self):
        query = """
        // Check for timestamp anomalies
        rule feed_timestamp_skew {
            meta:
                author = "Deacon Patrol"
            events:
                $e.metadata.event_timestamp.seconds > 0
                // Match condition
            match:
                $e.metadata.log_type over 1h
            outcome:
                $clock_skew_count = count(if($e.metadata.collected_timestamp.seconds < $e.metadata.event_timestamp.seconds, 1, 0))
            condition:
                $e
        }
        """
        canonical = canonicalize_yaral(query)
        self.assertNotIn("//", canonical)
        self.assertIn("RULE feed_timestamp_skew", canonical)
        self.assertIn("EVENTS:", canonical)
        self.assertIn("OUTCOME:", canonical)

    def test_attest_yaral_exact_and_whitespace_invariance(self):
        sanctioned = """
        rule feed_timestamp_skew {
            events:
                $e.metadata.event_timestamp.seconds > 0
            condition:
                $e
        }
        """
        # Formatted slightly differently with comments
        executed = """
        rule feed_timestamp_skew {
            // strip me
            events:
                $e.metadata.event_timestamp.seconds > 0
            condition:
                $e
        }
        """
        receipt = {
            "query_text": executed,
            "result_rows": [{"log_type": "WINEVTLOG", "skew_count": 0}],
        }
        verdict = attest_yaral(
            sanctioned_yaral=sanctioned,
            receipt=receipt,
            claimed_value=[{"log_type": "WINEVTLOG", "skew_count": 0}],
        )
        self.assertTrue(verdict["ok"])
        self.assertIsNone(verdict["reason"])

    def test_attest_yaral_detects_tampering(self):
        sanctioned = """
        rule feed_timestamp_skew {
            events:
                $e.metadata.event_timestamp.seconds > 0
            condition:
                $e
        }
        """
        # Tampered: added a filter excluding an attacker or log_type
        tampered = """
        rule feed_timestamp_skew {
            events:
                $e.metadata.event_timestamp.seconds > 0 and $e.metadata.log_type != "MALICIOUS"
            condition:
                $e
        }
        """
        receipt = {"query_text": tampered, "result_rows": []}
        verdict = attest_yaral(sanctioned_yaral=sanctioned, receipt=receipt)
        self.assertFalse(verdict["ok"])
        self.assertIn("differs from sanctioned computation", verdict["reason"])

    def test_attest_yaral_detects_claimed_value_mismatch(self):
        sanctioned = "rule r { events: $e.metadata.event_timestamp.seconds > 0 condition: $e }"
        receipt = {
            "query_text": sanctioned,
            "result_rows": [{"skew_count": 42}],
        }
        # Caller claims skew_count is 0 when receipt says 42
        verdict = attest_yaral(
            sanctioned_yaral=sanctioned,
            receipt=receipt,
            claimed_value=[{"skew_count": 0}],
        )
        self.assertFalse(verdict["ok"])
        self.assertIn("claimed_value does not match authoritative receipt", verdict["reason"])


if __name__ == "__main__":
    unittest.main()
