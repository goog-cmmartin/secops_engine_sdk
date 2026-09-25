#!/usr/bin/env python3
"""Generates a self-contained interactive OKF Cytoscape knowledge graph (viz.html)
from the knowledge/ directory.

Usage:
    python scripts/generate_knowledge_graph.py
    python scripts/generate_knowledge_graph.py --out knowledge/viz.html
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Set, Tuple

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from engine.okf import OKFDocument, is_stale, normalize_verified, trust_tier

_LINK_RE = re.compile(r"\]\(([^)\s]+\.md)(?:#[A-Za-z0-9_\-]*)?\)")

_TYPE_PALETTE = {
    "concept": "#8b5cf6",
    "feature": "#3b82f6",
    "persona": "#f59e0b",
    "task": "#10b981",
    "computation": "#ef4444",
    "Attested Computation": "#ef4444",
    "skill": "#ec4899",
}
_DEFAULT_NODE_COLOR = "#94a3b8"


@dataclass
class KnowledgeNode:
    id: str
    doc_id: str
    type: str
    title: str
    description: str
    resource: str
    tags: List[str]
    body: str
    status: str = "stable"
    generated: Dict[str, Any] = field(default_factory=dict)
    verified: List[Dict[str, Any]] = field(default_factory=list)
    stale_after: str = ""
    sources: List[Dict[str, Any]] = field(default_factory=list)
    trust_tier: str = "unverified"
    stale: bool = False
    links_to: List[str] = field(default_factory=list)

    def to_cytoscape_node(self) -> Dict[str, Any]:
        color = _TYPE_PALETTE.get(self.type, _DEFAULT_NODE_COLOR)
        return {
            "data": {
                "id": self.id,
                "label": self.title or self.id,
                "type": self.type,
                "description": self.description,
                "resource": self.resource,
                "tags": self.tags,
                "status": self.status,
                "generated": self.generated,
                "verified": self.verified,
                "stale_after": self.stale_after,
                "sources": self.sources,
                "trust_tier": self.trust_tier,
                "stale": self.stale,
                "color": color,
                "size": 32 + min(50, len(self.body) // 250),
            }
        }


def _extract_body_links(body: str, doc_dir: Path, knowledge_root: Path) -> List[str]:
    out: List[str] = []
    seen: Set[str] = set()
    knowledge_root_resolved = knowledge_root.resolve()
    for m in _LINK_RE.finditer(body):
        target = m.group(1)
        if "://" in target or target.startswith("/"):
            continue
        try:
            resolved = (doc_dir / target).resolve().relative_to(knowledge_root_resolved)
        except ValueError:
            continue
        rel = resolved.as_posix()
        if rel.endswith(".md"):
            rel = rel[:-3]
        if rel and rel not in seen:
            seen.add(rel)
            out.append(rel)
    return out


def load_knowledge_nodes(knowledge_root: Path) -> Tuple[List[KnowledgeNode], Dict[str, str]]:
    nodes: List[KnowledgeNode] = []
    id_to_node_key: Dict[str, str] = {}  # doc_id (e.g. concept.udm_search_lifecycle) -> node_key

    # Pass 1: discover nodes and index IDs
    for md_path in sorted(knowledge_root.rglob("*.md")):
        if md_path.name in ("index.md", "README.md") or "templates" in md_path.parts:
            continue
        rel = md_path.relative_to(knowledge_root).with_suffix("")
        node_key = "/".join(rel.parts)

        try:
            doc = OKFDocument.load(md_path)
        except Exception:
            continue

        fm = doc.frontmatter
        doc_id = fm.get("id") or node_key
        id_to_node_key[doc_id] = node_key
        id_to_node_key[node_key] = node_key

        tags = fm.get("tags") or []
        if not isinstance(tags, list):
            tags = [str(tags)]

        node = KnowledgeNode(
            id=node_key,
            doc_id=doc_id,
            type=str(fm.get("type") or "concept"),
            title=str(fm.get("title") or node_key),
            description=str(fm.get("description") or ""),
            resource=str(fm.get("resource") or ""),
            tags=[str(t) for t in tags],
            body=doc.body or "",
            status=str(fm.get("status") or "stable"),
            generated=fm.get("generated") if isinstance(fm.get("generated"), dict) else {},
            verified=normalize_verified(fm),
            stale_after=str(fm.get("stale_after") or ""),
            sources=fm.get("sources") if isinstance(fm.get("sources"), list) else [],
            trust_tier=trust_tier(fm),
            stale=is_stale(fm),
            links_to=_extract_body_links(doc.body or "", md_path.parent, knowledge_root),
        )
        nodes.append(node)

    # Pass 2: supplement links with frontmatter relations
    for node in nodes:
        # Link from related_concepts, related_features, primary_tasks, persona
        for md_path in knowledge_root.rglob("*.md"):
            rel = md_path.relative_to(knowledge_root).with_suffix("")
            if "/".join(rel.parts) == node.id:
                doc = OKFDocument.load(md_path)
                fm = doc.frontmatter
                relations: List[str] = []
                for k in ("related_concepts", "related_features", "primary_tasks"):
                    val = fm.get(k)
                    if isinstance(val, list):
                        relations.extend(val)
                p = fm.get("persona")
                if p:
                    relations.append(p)

                for r in relations:
                    target_key = id_to_node_key.get(r)
                    if target_key and target_key != node.id and target_key not in node.links_to:
                        node.links_to.append(target_key)
                break

    return nodes, id_to_node_key


def build_graph_data(nodes: List[KnowledgeNode]) -> Dict[str, Any]:
    all_ids = {n.id for n in nodes}
    cy_nodes = [n.to_cytoscape_node() for n in nodes]
    edges: List[Dict[str, Any]] = []
    seen_edges: Set[Tuple[str, str]] = set()

    for n in nodes:
        for target in n.links_to:
            if target == n.id or target not in all_ids:
                continue
            key = (n.id, target)
            if key in seen_edges:
                continue
            seen_edges.add(key)
            edges.append({
                "data": {
                    "id": f"{n.id}__{target}",
                    "source": n.id,
                    "target": target,
                }
            })

    bodies = {n.id: n.body for n in nodes}
    types = sorted({n.type for n in nodes})
    return {
        "nodes": cy_nodes,
        "edges": edges,
        "bodies": bodies,
        "types": types,
        "palette": _TYPE_PALETTE,
    }


def render_html(graph_data: Dict[str, Any], bundle_name: str = "Google SecOps Engine Knowledge Base") -> str:
    """Render single self-contained HTML page with Cytoscape and Marked.js."""
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>{bundle_name} — OKF Graph Viewer</title>
<script src="https://cdn.jsdelivr.net/npm/cytoscape@3.28.1/dist/cytoscape.min.js"></script>
<script src="https://cdn.jsdelivr.net/npm/marked@12.0.0/marked.min.js"></script>
<style>
* {{ box-sizing: border-box; }}
body {{
  margin: 0;
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, system-ui, sans-serif;
  font-size: 14px;
  color: #0f172a;
  background: #f8fafc;
  display: flex;
  flex-direction: column;
  height: 100vh;
}}
body > header {{
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 10px 18px;
  background: #1e293b;
  color: #f8fafc;
  border-bottom: 1px solid #334155;
  flex-shrink: 0;
}}
.title strong {{ font-size: 16px; margin-right: 8px; color: #38bdf8; }}
.muted {{ color: #94a3b8; font-size: 12px; }}
.controls {{ display: flex; gap: 8px; }}
.controls input, .controls select, .controls button {{
  font-size: 13px;
  padding: 6px 10px;
  border: 1px solid #475569;
  border-radius: 6px;
  background: #0f172a;
  color: #f8fafc;
}}
.controls input {{ width: 240px; }}
.controls button {{ cursor: pointer; background: #334155; }}
.controls button:hover {{ background: #475569; }}

main {{
  display: flex;
  flex: 1;
  min-height: 0;
}}
#graph {{
  flex: 1 1 65%;
  background: #0b0f19;
  border-right: 1px solid #1e293b;
  min-width: 0;
  position: relative;
}}
#detail {{
  flex: 0 0 35%;
  overflow-y: auto;
  padding: 20px 24px;
  background: #ffffff;
  color: #0f172a;
}}
#detail-empty {{
  text-align: center;
  margin-top: 50px;
  color: #64748b;
}}

.detail-header {{ margin-bottom: 14px; }}
.detail-header h1 {{
  font-size: 20px;
  margin: 6px 0 4px;
  font-weight: 700;
  color: #0f172a;
}}
.type-chip {{
  display: inline-block;
  padding: 3px 9px;
  border-radius: 12px;
  font-size: 11px;
  font-weight: 700;
  color: #fff;
  background: #94a3b8;
  text-transform: uppercase;
  letter-spacing: 0.5px;
}}
.trust-badge {{
  display: inline-block;
  padding: 3px 8px;
  border-radius: 6px;
  font-size: 11px;
  font-weight: 600;
  margin-left: 6px;
}}
.trust-human {{ background: #dcfce7; color: #166534; border: 1px solid #86efac; }}
.trust-machine {{ background: #e0f2fe; color: #075985; border: 1px solid #7dd3fc; }}
.trust-unverified {{ background: #fef3c7; color: #92400e; border: 1px solid #fde68a; }}

dl.frontmatter {{
  display: grid;
  grid-template-columns: 100px 1fr;
  row-gap: 6px;
  column-gap: 12px;
  margin: 12px 0 16px;
  font-size: 13px;
  background: #f1f5f9;
  padding: 12px;
  border-radius: 8px;
}}
dl.frontmatter dt {{
  color: #475569;
  font-weight: 600;
}}
dl.frontmatter dd {{
  margin: 0;
  word-break: break-all;
}}
#detail-body {{
  line-height: 1.6;
  font-size: 14px;
}}
#detail-body pre {{
  background: #0f172a;
  color: #f8fafc;
  padding: 12px;
  border-radius: 6px;
  overflow-x: auto;
}}
#detail-body code {{
  background: #f1f5f9;
  padding: 2px 5px;
  border-radius: 4px;
  font-size: 13px;
}}
#detail-body pre code {{
  background: transparent;
  padding: 0;
}}
.tag-badge {{
  display: inline-block;
  background: #e2e8f0;
  color: #334155;
  padding: 2px 6px;
  border-radius: 4px;
  font-size: 11px;
  margin-right: 4px;
}}
</style>
</head>
<body>
<header>
  <div class="title">
    <strong>{bundle_name}</strong>
    <span class="muted">OKF v0.2 Knowledge Graph</span>
  </div>
  <div class="controls">
    <input id="search" type="search" placeholder="Search title / id / tag...">
    <select id="filter-type">
      <option value="">All Types ({len(graph_data["nodes"])} items)</option>
    </select>
    <select id="layout">
      <option value="cose">cose (force layout)</option>
      <option value="concentric">concentric</option>
      <option value="breadthfirst">breadth-first</option>
      <option value="circle">circle</option>
      <option value="grid">grid</option>
    </select>
    <button id="reset">Reset View</button>
  </div>
</header>

<main>
  <section id="graph"></section>
  <section id="detail">
    <div id="detail-empty">
      <svg width="48" height="48" fill="none" stroke="currentColor" viewBox="0 0 24 24" style="margin-bottom:8px; opacity:0.6;"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z"></path></svg>
      <div>Click any node in the graph to inspect its OKF v0.2 frontmatter, verification status, and runbook content.</div>
    </div>
    <article id="detail-content" style="display:none;">
      <header class="detail-header">
        <span class="type-chip" id="detail-type"></span>
        <span class="trust-badge" id="detail-trust"></span>
        <h1 id="detail-title"></h1>
        <div class="muted" id="detail-id"></div>
      </header>
      <dl class="frontmatter">
        <dt>Description</dt><dd id="detail-desc"></dd>
        <dt>Tags</dt><dd id="detail-tags"></dd>
        <dt>Status</dt><dd id="detail-status"></dd>
        <dt>Stale After</dt><dd id="detail-stale"></dd>
        <dt>Generated</dt><dd id="detail-gen"></dd>
        <dt>Verified</dt><dd id="detail-ver"></dd>
        <dt>Sources</dt><dd id="detail-src"></dd>
      </dl>
      <hr style="border:0; border-top:1px solid #e2e8f0; margin:16px 0;">
      <div id="detail-body"></div>
    </article>
  </section>
</main>

<script>
window.GRAPH_DATA = {json.dumps(graph_data, default=str)};
(function() {{
  const data = window.GRAPH_DATA;
  const typeSelect = document.getElementById("filter-type");
  for (const t of data.types) {{
    const opt = document.createElement("option");
    opt.value = t;
    opt.textContent = t.toUpperCase();
    typeSelect.appendChild(opt);
  }}

  const cy = cytoscape({{
    container: document.getElementById("graph"),
    elements: [...data.nodes, ...data.edges],
    style: [
      {{
        selector: "node",
        style: {{
          "background-color": "data(color)",
          "label": "data(label)",
          "color": "#f8fafc",
          "font-size": 11,
          "text-valign": "bottom",
          "text-margin-y": 5,
          "text-wrap": "wrap",
          "text-max-width": 110,
          "width": "data(size)",
          "height": "data(size)",
          "border-width": 2,
          "border-color": "#ffffff",
          "text-background-color": "#0b0f19",
          "text-background-opacity": 0.8,
          "text-background-padding": 2,
          "text-background-shape": "roundrectangle"
        }}
      }},
      {{
        selector: "node:selected",
        style: {{
          "border-width": 4,
          "border-color": "#38bdf8",
          "width": "mapData(size, 20, 80, 35, 95)",
          "height": "mapData(size, 20, 80, 35, 95)"
        }}
      }},
      {{
        selector: "edge",
        style: {{
          "width": 1.5,
          "line-color": "#475569",
          "target-arrow-color": "#475569",
          "target-arrow-shape": "triangle",
          "curve-style": "bezier",
          "arrow-scale": 0.8
        }}
      }},
      {{
        selector: "edge:selected",
        style: {{
          "line-color": "#38bdf8",
          "target-arrow-color": "#38bdf8",
          "width": 2.5
        }}
      }}
    ],
    layout: {{ name: "cose", padding: 30, animate: false }}
  }});

  function showDetail(node) {{
    const d = node.data();
    document.getElementById("detail-empty").style.display = "none";
    const cont = document.getElementById("detail-content");
    cont.style.display = "block";

    document.getElementById("detail-type").textContent = d.type;
    document.getElementById("detail-type").style.backgroundColor = d.color;
    document.getElementById("detail-title").textContent = d.label;
    document.getElementById("detail-id").textContent = d.id;
    document.getElementById("detail-desc").textContent = d.description || "—";
    
    // Trust badge
    const trustEl = document.getElementById("detail-trust");
    trustEl.textContent = d.trust_tier.toUpperCase();
    trustEl.className = "trust-badge trust-" + (d.trust_tier === "human-reviewed" ? "human" : d.trust_tier === "machine-confirmed" ? "machine" : "unverified");

    // Tags
    const tagsEl = document.getElementById("detail-tags");
    tagsEl.innerHTML = (d.tags || []).map(t => `<span class="tag-badge">${{t}}</span>`).join("") || "—";

    document.getElementById("detail-status").textContent = d.status || "stable";
    document.getElementById("detail-stale").textContent = d.stale_after || "—";
    
    // Generated
    const gen = d.generated;
    document.getElementById("detail-gen").textContent = gen && gen.by ? `${{gen.by}} (${{gen.at || ""}})` : "—";

    // Verified
    const ver = d.verified;
    document.getElementById("detail-ver").textContent = ver && ver.length ? ver.map(v => `${{v.by}} (${{v.at || ""}})`).join(", ") : "Unverified";

    // Sources
    const src = d.sources;
    document.getElementById("detail-src").innerHTML = src && src.length ? src.map(s => `<a href="${{s.resource}}" target="_blank" rel="noopener">${{s.title || s.resource}}</a>`).join("<br>") : "—";

    // Markdown body
    const bodyMarkdown = data.bodies[d.id] || "";
    document.getElementById("detail-body").innerHTML = marked.parse(bodyMarkdown);
  }}

  window.cy = cy;
  window.showDetail = showDetail;

  cy.on("tap", "node", e => showDetail(e.target));

  // Auto-select initial node on load
  const initialNode = cy.getElementById("computations/feed_timestamp_skew");
  if (initialNode && initialNode.length) {{
    initialNode.select();
    showDetail(initialNode);
  }} else if (cy.nodes().length) {{
    cy.nodes()[0].select();
    showDetail(cy.nodes()[0]);
  }}

  // Search filter
  document.getElementById("search").addEventListener("input", e => {{
    const q = e.target.value.toLowerCase().trim();
    if (!q) {{
      cy.nodes().show();
      return;
    }}
    cy.nodes().forEach(n => {{
      const d = n.data();
      const match = d.label.toLowerCase().includes(q) || d.id.toLowerCase().includes(q) || (d.tags || []).some(t => t.toLowerCase().includes(q));
      match ? n.show() : n.hide();
    }});
  }});

  // Type filter
  typeSelect.addEventListener("change", e => {{
    const val = e.target.value;
    if (!val) {{
      cy.nodes().show();
      return;
    }}
    cy.nodes().forEach(n => {{
      n.data("type") === val ? n.show() : n.hide();
    }});
  }});

  // Layout change
  document.getElementById("layout").addEventListener("change", e => {{
    cy.layout({{ name: e.target.value, animate: true, animationDuration: 500 }}).run();
  }});

  // Reset view
  document.getElementById("reset").addEventListener("click", () => {{
    cy.fit(null, 30);
  }});
}})();
</script>
</body>
</html>
"""


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate interactive OKF knowledge graph")
    parser.add_argument("--knowledge-dir", default=str(REPO_ROOT / "knowledge"), help="Path to knowledge directory")
    parser.add_argument("--out", default=str(REPO_ROOT / "knowledge" / "viz.html"), help="Output HTML file path")
    args = parser.parse_args()

    knowledge_root = Path(args.knowledge_dir)
    out_path = Path(args.out)

    nodes, _ = load_knowledge_nodes(knowledge_root)
    graph_data = build_graph_data(nodes)
    html = render_html(graph_data)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(html, encoding="utf-8")

    print(f"Generated OKF Knowledge Graph viz: {out_path}")
    print(f"  • Nodes: {len(graph_data['nodes'])} ({', '.join(f'{t}: {sum(1 for n in nodes if n.type == t)}' for t in graph_data['types'])})")
    print(f"  • Edges: {len(graph_data['edges'])}")
    print(f"  • File size: {len(html.encode('utf-8')) / 1024:.1f} KB")
    return 0


if __name__ == "__main__":
    sys.exit(main())
