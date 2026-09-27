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
    overlay_agents,
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


class OverlayAgentsTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        _write(self.root, "tasks/t.md", "id: task.t\ntype: task\ntitle: T\ncapabilities_used: [rules.list, rules.get]")
        _write(self.root, "features/f.md", "id: feature.f\ntype: feature\ntitle: F\nsdk_capabilities: feeds.list")
        _write(self.root, "concepts/c.md", "id: concept.c\ntype: concept\ntitle: C")
        self.graph = build_graph(self.root)

    def tearDown(self):
        self._tmp.cleanup()

    def test_agents_link_to_docs_sharing_a_capability(self):
        agents = [
            {"handle": "@rules", "capabilities": ["rules.get", "cases.list"], "subsystem": "detections"},
            {"handle": "@feeds", "capabilities": ["feeds.list"]},
            {"handle": "@lonely", "capabilities": ["x.y"]},
        ]
        g = overlay_agents(self.graph, agents)
        uses = {(e["data"]["source"], e["data"]["target"]): e["data"]["via"]
                for e in g["edges"] if e["data"]["kind"] == "uses"}
        self.assertEqual(uses, {
            ("agent:@rules", "tasks/t"): ["rules.get"],
            ("agent:@feeds", "features/f"): ["feeds.list"],
        })
        lonely = next(n for n in g["nodes"] if n["data"]["id"] == "agent:@lonely")
        self.assertEqual(lonely["data"]["uses"], [])
        self.assertIn("agent", g["types"])

    def test_does_not_mutate_cached_graph(self):
        n_nodes, n_edges = len(self.graph["nodes"]), len(self.graph["edges"])
        overlay_agents(self.graph, [{"handle": "@a", "capabilities": ["rules.list"]}])
        self.assertEqual((len(self.graph["nodes"]), len(self.graph["edges"])), (n_nodes, n_edges))
        self.assertNotIn("agent", self.graph["types"])

    def test_doc_edges_are_tagged_links(self):
        self.assertTrue(all(e["data"]["kind"] == "links" for e in self.graph["edges"]))


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


class GraphApiTest(unittest.TestCase):
    def setUp(self):
        from clients.web.server import app, fleet
        self.client = TestClient(app)
        self.fleet = fleet

    def test_graph_api_includes_agent_layer_matching_library_skills(self):
        from clients.web.server import _serialize_agent
        r = self.client.get("/api/knowledge/graph")
        self.assertEqual(r.status_code, 200)
        g = r.json()
        agent_nodes = [n for n in g["nodes"] if n["data"]["type"] == "agent"]
        self.assertEqual({n["data"]["handle"] for n in agent_nodes}, set(self.fleet.keys()))
        # Graph "uses" edges and the Agent Library's skill list apply the same rule.
        for handle, agent in self.fleet.items():
            lib = {s["source_path"].removeprefix("knowledge/").removesuffix(".md")
                   for s in _serialize_agent(agent)["skills"]}
            graph = {e["data"]["target"] for e in g["edges"]
                     if e["data"]["kind"] == "uses" and e["data"]["source"] == f"agent:{handle}"}
            self.assertEqual(graph, lib, handle)
        ids = {n["data"]["id"] for n in g["nodes"]}
        self.assertTrue(all(e["data"]["source"] in ids and e["data"]["target"] in ids for e in g["edges"]))

    def test_graph_api_docs_only(self):
        g = self.client.get("/api/knowledge/graph", params={"include_agents": "false"}).json()
        self.assertFalse(any(n["data"]["type"] == "agent" for n in g["nodes"]))
        self.assertIn("bodies", g)


class KnowledgeViewWiringTest(unittest.TestCase):
    """Static checks that the in-app view is wired (no browser in CI)."""

    STATIC = Path(__file__).resolve().parent.parent / "clients" / "web" / "static"

    def test_index_has_view_and_in_app_nav(self):
        html = (self.STATIC / "index.html").read_text(encoding="utf-8")
        self.assertIn('id="knowledgeView"', html)
        self.assertRegex(html, r'<button id="navBtnKnowledge"[^>]*type="button"')
        self.assertNotRegex(html, r'id="navBtnKnowledge"[^>]*target="_blank"')
        # Vendored renderer (offline), loaded before the view module.
        self.assertLess(html.index("/static/vendor/cytoscape.min.js"), html.index("/static/knowledge_graph.js"))
        self.assertNotIn("cdn.jsdelivr.net/npm/cytoscape", html)

    def test_vendored_assets_served(self):
        from clients.web.server import app
        client = TestClient(app)
        for path in ("/static/vendor/cytoscape.min.js", "/static/knowledge_graph.js"):
            self.assertEqual(client.get(path).status_code, 200, path)

    def test_app_routes_knowledge_view(self):
        js = (self.STATIC / "app.js").read_text(encoding="utf-8")
        self.assertIn('knowledge: { panel: "knowledgeView", nav: "navBtnKnowledge"', js)
        self.assertIn("|knowledge)(\\/|$)/.test(h)", js)


if __name__ == "__main__":
    unittest.main()
