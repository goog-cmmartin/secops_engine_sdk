"""Tests for the on-demand OKF knowledge graph (engine/knowledge_graph.py)."""

import json
import os
from pathlib import Path
import re
import tempfile
import unittest

from fastapi.testclient import TestClient

from engine.knowledge_graph import (
    KnowledgeGraphCache,
    build_graph,
    render_html,
)

REPO_KNOWLEDGE = Path(__file__).resolve().parent.parent / "knowledge"


def _write(root: Path, rel: str, fm: str, body: str = "Body.") -> Path:
    p = root / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(f"---\n{fm.strip()}\n---\n\n{body}\n", encoding="utf-8")
    return p


class BuildGraphTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        _write(self.root, "concepts/a.md", "id: concept.a\ntype: concept\ntitle: A")
        _write(
            self.root, "tasks/t.md",
            "id: task.t\ntype: task\ntitle: T\nrelated_concepts: [concept.a]",
            "See [B](../features/b.md).",
        )
        _write(self.root, "features/b.md", "id: feature.b\ntype: feature\ntitle: B")
        _write(self.root, "computations/c.md", "id: computation.c\ntype: Attested Computation\ntitle: C")
        _write(self.root, "templates/x.md", "id: concept.x\ntype: concept\ntitle: X")
        _write(self.root, "README.md", "id: concept.r\ntype: concept\ntitle: R")

    def tearDown(self):
        self._tmp.cleanup()

    def test_nodes_edges_and_exclusions(self):
        g = build_graph(self.root)
        ids = {n["data"]["id"] for n in g["nodes"]}
        self.assertEqual(ids, {"concepts/a", "tasks/t", "features/b", "computations/c"})
        edges = {(e["data"]["source"], e["data"]["target"]) for e in g["edges"]}
        self.assertEqual(edges, {("tasks/t", "features/b"), ("tasks/t", "concepts/a")})

    def test_attested_computation_folded_into_computation(self):
        g = build_graph(self.root)
        self.assertEqual(g["types"], ["computation", "concept", "feature", "task"])
        self.assertNotIn("skill", g["palette"])

    def test_missing_root_is_empty(self):
        g = build_graph(self.root / "nope")
        self.assertEqual(g["nodes"], [])
        self.assertEqual(g["edges"], [])

    def test_repo_graph_covers_every_knowledge_doc(self):
        g = build_graph(REPO_KNOWLEDGE)
        expected = {
            p.relative_to(REPO_KNOWLEDGE).with_suffix("").as_posix()
            for p in REPO_KNOWLEDGE.rglob("*.md")
            if p.name not in ("index.md", "README.md") and "templates" not in p.parts
        }
        self.assertEqual({n["data"]["id"] for n in g["nodes"]}, expected)


class RenderHtmlTest(unittest.TestCase):
    def test_embedded_json_cannot_break_out_of_script(self):
        graph = {
            "nodes": [], "edges": [], "types": [], "palette": {},
            "bodies": {"x": "</script><script>alert(1)</script><!--"},
        }
        html = render_html(graph)
        script = html[html.index("window.GRAPH_DATA"):]
        payload_line = script.splitlines()[0]
        self.assertNotIn("</script>", payload_line)
        self.assertNotIn("<!--", payload_line)
        m = re.match(r"window\.GRAPH_DATA = (.*);$", payload_line)
        self.assertEqual(json.loads(m.group(1))["bodies"]["x"], graph["bodies"]["x"])


class CacheTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        _write(self.root, "concepts/a.md", "id: concept.a\ntype: concept\ntitle: A")
        self.cache = KnowledgeGraphCache(self.root)

    def tearDown(self):
        self._tmp.cleanup()

    def test_reuses_until_sources_change(self):
        g1 = self.cache.graph()
        h1 = self.cache.html()
        self.assertIs(self.cache.graph(), g1)
        self.assertIs(self.cache.html(), h1)

        _write(self.root, "concepts/b.md", "id: concept.b\ntype: concept\ntitle: B")
        g2 = self.cache.graph()
        self.assertIsNot(g2, g1)
        self.assertEqual(len(g2["nodes"]), 2)
        self.assertIn("concepts/b", self.cache.html())

    def test_edit_and_delete_invalidate(self):
        p = self.root / "concepts" / "a.md"
        self.cache.graph()
        _write(self.root, "concepts/a.md", "id: concept.a\ntype: concept\ntitle: Renamed A")
        st = p.stat()
        os.utime(p, ns=(st.st_atime_ns, st.st_mtime_ns + 1_000_000_000))
        self.assertEqual(self.cache.graph()["nodes"][0]["data"]["label"], "Renamed A")
        p.unlink()
        self.assertEqual(self.cache.graph()["nodes"], [])


class VizEndpointTest(unittest.TestCase):
    def test_viz_served_from_live_knowledge(self):
        from clients.web.server import app
        client = TestClient(app)
        r = client.get("/knowledge/viz.html")
        self.assertEqual(r.status_code, 200)
        self.assertIn("text/html", r.headers["content-type"])
        self.assertEqual(r.headers.get("cache-control"), "no-cache")
        n_docs = len(build_graph(REPO_KNOWLEDGE)["nodes"])
        self.assertIn(f"All Types ({n_docs} items)", r.text)


if __name__ == "__main__":
    unittest.main()
