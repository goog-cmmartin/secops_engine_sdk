"""Knowledge Base Contract & Referential Integrity Unit Tests.

Enforces schema compliance, referential integrity between concepts,
features, personas, and tasks, and verifies that all referenced
capabilities exist in the live engine registry.
"""

from __future__ import annotations

import unittest
from pathlib import Path

from scripts.validate_knowledge import validate_knowledge


class TestKnowledgeContract(unittest.TestCase):
    def test_knowledge_base_integrity(self):
        """Asserts knowledge/ corpus conforms to frontmatter schema and link integrity."""
        errors = validate_knowledge(verbose=False)
        self.assertEqual(
            errors,
            [],
            f"Knowledge validation failed with {len(errors)} error(s):\n" + "\n".join(f"  • {e}" for e in errors)
        )


if __name__ == "__main__":
    unittest.main()
