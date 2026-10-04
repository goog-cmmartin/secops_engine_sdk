"""Knowledge Base Contract & Referential Integrity Unit Tests.

Enforces schema compliance, referential integrity between concepts,
features, personas, tasks, and computations, verifies that all referenced
capabilities exist in the live engine registry, and validates OKF v0.2 conformance.
"""

from __future__ import annotations

import unittest
from pathlib import Path

from engine.okf import OKFDocument, trust_tier, is_stale
from scripts.validate_knowledge import validate_knowledge, REPO_ROOT


class TestKnowledgeContract(unittest.TestCase):
    def test_knowledge_base_integrity(self):
        """Asserts knowledge/ corpus conforms to frontmatter schema and link integrity."""
        errors = validate_knowledge(verbose=False)
        self.assertEqual(
            errors,
            [],
            f"Knowledge validation failed with {len(errors)} error(s):\n" + "\n".join(f"  • {e}" for e in errors)
        )

    def test_okf_trust_tiers_and_staleness(self):
        """Asserts OKF document parsing and trust tier derivation on knowledge/ files."""
        knowledge_dir = REPO_ROOT / "knowledge"
        count = 0
        for md_path in knowledge_dir.rglob("*.md"):
            if md_path.name in ("README.md", "index.md") or "templates" in md_path.parts:
                continue
            doc = OKFDocument.load(md_path)
            tier = trust_tier(doc.frontmatter)
            self.assertIn(tier, ("unverified", "machine-confirmed", "human-reviewed"))
            stale = is_stale(doc.frontmatter)
            self.assertIsInstance(stale, bool)
            count += 1
        self.assertGreaterEqual(count, 35, f"Expected at least 35 knowledge docs, found {count}")


if __name__ == "__main__":
    unittest.main()
