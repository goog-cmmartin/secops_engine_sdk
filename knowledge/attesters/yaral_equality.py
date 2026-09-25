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

"""Deterministic attester for Attested Computations with runtime: yaral_2.

Verifies two invariant properties about a receipt produced by a SecOps query executor:
  1. Provenance: the YARA-L 2 rule/query that actually executed (`receipt.query_text`
     or `receipt.executed_yaral`) equals the sanctioned `# Computation` body after
     normalizing whitespace, stripping comments, and canonicalizing keywords.
     Parameters (e.g. `$window_days`, `@window_days`) are compared symbolically.
  2. Fidelity: the value the caller claimed/displayed to the user (`claimed_value`)
     matches the authentic authoritative payload in `receipt.result` or
     `receipt.result_rows`.

Returns a verdict dict:
  { "ok": bool, "reason": str | None, "details": { ... } }

Never uses an LLM. Never makes network calls. Safe to run consumer-side.
"""

from __future__ import annotations

import re
from typing import Any, Dict, Optional


# ---- YARA-L 2 normalization helpers -------------------------------------------

_COMMENT_LINE = re.compile(r"(?://|#)[^\n]*")
_COMMENT_BLOCK = re.compile(r"/\*.*?\*/", flags=re.DOTALL)
_WHITESPACE = re.compile(r"\s+")

_YARAL_KEYWORDS = frozenset({
    "RULE", "META", "EVENTS", "MATCH", "OUTCOME", "CONDITION",
    "AND", "OR", "NOT", "NOCASE", "ALL", "ANY",
    "COUNT", "COUNT_DISTINCT", "SUM", "AVG", "MIN", "MAX",
    "ARRAY_DISTINCT", "TIMESTAMP", "COALESCE", "IF",
})


def canonicalize_yaral(query: str) -> str:
    """Strip comments, collapse whitespace, and canonicalize YARA-L keywords."""
    s = _COMMENT_BLOCK.sub(" ", query)
    s = _COMMENT_LINE.sub(" ", s)
    s = _WHITESPACE.sub(" ", s).strip()

    def _upper_kw(match: re.Match[str]) -> str:
        w = match.group(0)
        return w.upper() if w.upper() in _YARAL_KEYWORDS else w

    # Uppercase only known YARA-L keywords; leave identifiers, UDM paths, and values alone
    s = re.sub(r"[A-Za-z_][A-Za-z_0-9]*", _upper_kw, s)
    return s


# ---- Verification entrypoint --------------------------------------------------

def attest_yaral(
    *,
    sanctioned_yaral: str,
    receipt: Dict[str, Any],
    claimed_value: Optional[Any] = None,
) -> Dict[str, Any]:
    """Verify a SecOps YARA-L receipt against a sanctioned computation.

    Args:
      sanctioned_yaral: The canonical YARA-L 2 string from the concept's `# Computation` fence.
      receipt: The receipt dictionary returned by the executor, containing `query_text`
               and optionally `result_rows` / `result`.
      claimed_value: The value/metrics the caller intends to display to the user.

    Returns:
      A verdict dictionary. Consumers MUST refuse to display or action `claimed_value`
      when verdict["ok"] is False.
    """
    if not isinstance(receipt, dict):
        return {
            "ok": False,
            "reason": "receipt must be a dictionary",
            "details": {"type": str(type(receipt))},
        }

    executed = receipt.get("query_text") or receipt.get("executed_yaral")
    if not executed or not isinstance(executed, str):
        return {
            "ok": False,
            "reason": "receipt is missing executed query_text/executed_yaral string",
            "details": {"receipt_keys": sorted(receipt.keys())},
        }

    can_sanctioned = canonicalize_yaral(sanctioned_yaral)
    can_executed = canonicalize_yaral(executed)

    if can_sanctioned != can_executed:
        return {
            "ok": False,
            "reason": "executed YARA-L query differs from sanctioned computation",
            "details": {
                "sanctioned_normalized": can_sanctioned,
                "executed_normalized": can_executed,
            },
        }

    # Fidelity check if claimed_value was provided
    if claimed_value is not None:
        result_payload = receipt.get("result_rows") if "result_rows" in receipt else receipt.get("result")
        if result_payload != claimed_value:
            return {
                "ok": False,
                "reason": "claimed_value does not match authoritative receipt result",
                "details": {
                    "claimed": str(claimed_value),
                    "receipt_result": str(result_payload),
                },
            }

    return {
        "ok": True,
        "reason": None,
        "details": {
            "attested_runtime": "yaral_2",
            "query_hash": hash(can_sanctioned),
        },
    }
