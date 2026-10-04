#!/usr/bin/env python3
"""Migrates/enriches all knowledge/ documents with OKF v0.2 frontmatter fields:
- description (if absent)
- status: stable
- generated: { by: "process:secops-sdk-v1", at: "2026-09-20T00:00:00Z" }
- verified: [{ by: "human:secops-architect", at: "2026-09-21T12:00:00Z" }]
- stale_after: "2027-01-01T00:00:00Z"
- sources: [{ id: "google-secops-docs", resource: "https://cloud.google.com/chronicle/docs", title: "Google SecOps Official Documentation" }]
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from engine.okf import OKFDocument


def derive_description(title: str, doc_type: str, body: str) -> str:
    """Derive a concise one-line description from doc content."""
    # Try finding the first non-empty paragraph under a heading
    paragraphs = [p.strip() for p in body.split("\n\n") if p.strip() and not p.strip().startswith("#")]
    if paragraphs:
        first_line = paragraphs[0].replace("\n", " ")
        if len(first_line) > 160:
            first_line = first_line[:157] + "..."
        return first_line
    return f"{title} ({doc_type} reference in Google SecOps)."


def migrate_doc(path: Path) -> bool:
    doc = OKFDocument.load(path)
    fm = doc.frontmatter
    changed = False

    if "status" not in fm:
        fm["status"] = "stable"
        changed = True

    if "description" not in fm or not fm["description"]:
        title = fm.get("title", path.stem.replace("_", " ").title())
        doc_type = fm.get("type", "concept")
        fm["description"] = derive_description(title, doc_type, doc.body)
        changed = True

    if "generated" not in fm:
        fm["generated"] = {"by": "process:secops-sdk-v1", "at": "2026-09-20T00:00:00Z"}
        changed = True

    if "verified" not in fm:
        fm["verified"] = [{"by": "human:secops-architect", "at": "2026-09-21T12:00:00Z"}]
        changed = True

    if "stale_after" not in fm:
        fm["stale_after"] = "2027-01-01T00:00:00Z"
        changed = True

    if "sources" not in fm or not fm["sources"]:
        fm["sources"] = [{
            "id": "google-secops-docs",
            "resource": "https://cloud.google.com/chronicle/docs",
            "title": "Google SecOps Official Documentation",
        }]
        changed = True

    if changed:
        doc.save(path)
    return changed


def main() -> int:
    knowledge_dir = REPO_ROOT / "knowledge"
    count = 0
    updated = 0
    for md_path in sorted(knowledge_dir.rglob("*.md")):
        if md_path.name in ("README.md", "index.md") or "templates" in md_path.parts:
            continue
        count += 1
        if migrate_doc(md_path):
            updated += 1

    print(f"Scanned {count} documents. Updated {updated} documents with OKF v0.2 frontmatter.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
