#!/usr/bin/env python3
"""Exports the interactive OKF knowledge graph as a standalone HTML file.

The web UI builds this on demand (``/knowledge/viz.html``) and rebuilds it
whenever ``knowledge/**/*.md`` changes, so running this script is only needed
for an offline/shareable copy. Output is git-ignored.

Usage:
    python scripts/generate_knowledge_graph.py
    python scripts/generate_knowledge_graph.py --out /tmp/viz.html
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from engine.knowledge_graph import build_graph_data, load_knowledge_nodes, render_html


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate interactive OKF knowledge graph")
    parser.add_argument("--knowledge-dir", default=str(REPO_ROOT / "knowledge"), help="Path to knowledge directory")
    parser.add_argument("--out", default=str(REPO_ROOT / "knowledge" / "viz.html"), help="Output HTML file path")
    args = parser.parse_args()

    nodes, _ = load_knowledge_nodes(Path(args.knowledge_dir))
    graph_data = build_graph_data(nodes)
    html = render_html(graph_data)

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(html, encoding="utf-8")

    print(f"Generated OKF Knowledge Graph viz: {out_path}")
    print(f"  • Nodes: {len(graph_data['nodes'])} ({', '.join(f'{t}: {sum(1 for n in nodes if n.type == t)}' for t in graph_data['types'])})")
    print(f"  • Edges: {len(graph_data['edges'])}")
    print(f"  • File size: {len(html.encode('utf-8')) / 1024:.1f} KB")
    return 0


if __name__ == "__main__":
    sys.exit(main())
