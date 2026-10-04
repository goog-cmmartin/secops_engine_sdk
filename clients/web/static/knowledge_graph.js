// ====================================================================
// Knowledge Graph view (#knowledge)
// OKF knowledge docs + the agents grounded on them, from /api/knowledge/graph.
// Depends on app.js globals: escapeHtml, formatMarkdown, fetchJsonOrThrow,
// showLoadError, setRoute, switchView.
// ====================================================================
const kgState = {
  data: null,
  cy: null,
  loading: null,
  selectedId: null,
  query: "",
  hiddenTypes: new Set(),
  listenersAttached: false,
  pendingSelect: null,
};

// Type -> theme token (resolved at runtime so light/dark both work).
const KG_TYPE_TOKENS = {
  agent: "--c-sky",
  persona: "--c-warn",
  task: "--c-ok",
  feature: "--c-info",
  concept: "--c-violet",
  computation: "--c-danger",
};
const KG_TYPE_LABELS = {
  agent: "Agents",
  persona: "Personas",
  task: "Tasks",
  feature: "Features",
  concept: "Concepts",
  computation: "Computations",
};
const KG_TYPE_ORDER = ["agent", "persona", "task", "feature", "concept", "computation"];
const KG_TRUST_LABELS = {
  "human-reviewed": ["Human reviewed", "is-human"],
  "machine-confirmed": ["Machine confirmed", "is-machine"],
  unverified: ["Unverified", "is-unverified"],
};

function kgCssVar(name, fallback) {
  const v = getComputedStyle(document.documentElement).getPropertyValue(name).trim();
  return v || fallback;
}

function kgTypeColor(type) {
  return kgCssVar(KG_TYPE_TOKENS[type] || "--c-neutral", "#94a3b8");
}

function kgNodeHash(id) {
  return id ? `#knowledge/${encodeURIComponent(id)}` : "#knowledge";
}

function kgNodeIdFromHash() {
  const h = window.location.hash.replace(/^#/, "");
  if (!h.startsWith("knowledge/")) return null;
  try { return decodeURIComponent(h.slice("knowledge/".length)) || null; } catch (_) { return null; }
}

// Knowledge doc path ("knowledge/tasks/x.md") -> graph node id ("tasks/x").
function kgNodeIdFromSourcePath(path) {
  return String(path || "").replace(/^knowledge\//, "").replace(/\.md$/, "");
}

async function loadKnowledgeGraphView() {
  kgSetupListeners();
  const target = kgNodeIdFromHash();
  if (target) kgState.pendingSelect = target;

  if (kgState.cy) {
    // Returning to the view: canvas was display:none, so re-measure.
    kgState.cy.resize();
    if (kgState.pendingSelect) kgApplyPendingSelection();
    else if (kgState.selectedId) kgSelect(null, { skipRoute: true }); // Back to bare #knowledge
    return;
  }
  if (kgState.loading) return kgState.loading;

  const canvas = document.getElementById("kgCanvas");
  const status = document.getElementById("kgCanvasStatus");
  if (typeof cytoscape === "undefined") {
    if (status) {
      status.hidden = false;
      showLoadError(status, {
        title: "Graph renderer failed to load",
        error: new Error("cytoscape.min.js is missing from /static/vendor."),
      });
    }
    return;
  }
  if (status) {
    status.hidden = false;
    status.innerHTML = '<div class="kg-canvas-loading">Loading knowledge graph…</div>';
  }

  kgState.loading = (async () => {
    try {
      kgState.data = await fetchJsonOrThrow("/api/knowledge/graph");
    } catch (err) {
      console.error("Failed to load knowledge graph:", err);
      if (status) {
        showLoadError(status, {
          title: "Couldn't load the knowledge graph",
          error: err,
          retry: () => { kgState.loading = null; return loadKnowledgeGraphView(); },
        });
      }
      return;
    } finally {
      kgState.loading = null;
    }
    if (!kgState.data.nodes.length) {
      if (status) status.innerHTML = '<div class="kg-canvas-loading">No knowledge documents found in knowledge/.</div>';
      return;
    }
    if (status) status.hidden = true;
    kgInitCytoscape(canvas);
    kgRenderTypeChips();
    kgUpdateCountBadge();
    if (!kgState.pendingSelect && !kgState.selectedId) kgRenderEmptyDetail();
    kgApplyPendingSelection();
  })();
  return kgState.loading;
}

function kgStyles() {
  const text = kgCssVar("--text-main", "#e2e8f0");
  const bg = kgCssVar("--bg-secondary", "#0f172a");
  const edge = kgCssVar("--border-color", "#475569");
  const focus = kgCssVar("--accent-blue", "#38bdf8");
  const agentEdge = kgCssVar("--c-sky", "#38bdf8");
  return [
    {
      selector: "node",
      style: {
        "background-color": "data(color)",
        label: "data(label)",
        color: text,
        "font-family": kgCssVar("--font-sans", "sans-serif"),
        "font-size": 11,
        "text-valign": "bottom",
        "text-margin-y": 5,
        "text-wrap": "ellipsis",
        "text-max-width": 130,
        width: "data(size)",
        height: "data(size)",
        "border-width": 2,
        "border-color": bg,
        "text-background-color": bg,
        "text-background-opacity": 0.85,
        "text-background-padding": 2,
        "text-background-shape": "roundrectangle",
        "transition-property": "opacity",
        "transition-duration": "150ms",
      },
    },
    { selector: 'node[type = "agent"]', style: { shape: "round-hexagon" } },
    { selector: 'node[type = "persona"]', style: { shape: "round-diamond" } },
    { selector: "node[?stale]", style: { "border-style": "dashed", "border-color": kgCssVar("--c-warn", "#f59e0b") } },
    {
      selector: "edge",
      style: {
        width: 1.2,
        "line-color": edge,
        "target-arrow-color": edge,
        "target-arrow-shape": "triangle",
        "curve-style": "bezier",
        "arrow-scale": 0.7,
        opacity: 0.7,
      },
    },
    {
      selector: 'edge[kind = "uses"]',
      style: { "line-style": "dashed", "line-color": agentEdge, "target-arrow-color": agentEdge, opacity: 0.45 },
    },
    { selector: ".kg-faded", style: { opacity: 0.12, "text-opacity": 0 } },
    { selector: "edge.kg-hl", style: { width: 2.2, opacity: 1 } },
    { selector: "node:selected", style: { "border-width": 4, "border-color": focus, "z-index": 10 } },
  ];
}

function kgInitCytoscape(container) {
  const d = kgState.data;
  const nodes = d.nodes.map((n) => {
    const nd = { ...n.data };
    nd.color = kgTypeColor(nd.type);
    if (nd.type === "agent") nd.size = 30 + Math.min(24, (nd.uses || []).length * 2);
    else nd.size = nd.size || 32;
    return { data: nd };
  });
  const cy = cytoscape({
    container,
    elements: [...nodes, ...d.edges],
    style: kgStyles(),
    layout: kgLayoutOptions("cose"),
    minZoom: 0.2,
    maxZoom: 3,
    boxSelectionEnabled: false,
    selectionType: "single",
  });
  kgState.cy = cy;

  cy.on("tap", "node", (e) => kgSelect(e.target.id()));
  cy.on("tap", (e) => { if (e.target === cy) kgSelect(null); });
  cy.on("mouseover", "node", () => { container.style.cursor = "pointer"; });
  cy.on("mouseout", "node", () => { container.style.cursor = ""; });

  // Re-colour when the operator flips light/dark.
  new MutationObserver(() => {
    if (!kgState.cy) return;
    kgState.cy.nodes().forEach((n) => n.data("color", kgTypeColor(n.data("type"))));
    kgState.cy.style(kgStyles());
    kgRenderTypeChips();
  }).observe(document.documentElement, { attributes: true, attributeFilter: ["data-theme"] });
}

function kgLayoutOptions(name) {
  const reduce = window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  const base = { name, padding: 30, animate: !reduce && name !== "cose", animationDuration: 400, fit: true };
  if (name === "cose") Object.assign(base, { animate: false, nodeRepulsion: 9000, idealEdgeLength: 90, randomize: false });
  if (name === "concentric") {
    // Agents outermost, then personas, tasks, features, concepts at the core.
    const ring = { agent: 5, persona: 4, task: 3, computation: 2, feature: 2, concept: 1 };
    base.concentric = (n) => ring[n.data("type")] || 1;
    base.levelWidth = () => 1;
    base.minNodeSpacing = 20;
  }
  if (name === "breadthfirst") base.directed = true;
  return base;
}

function kgSetupListeners() {
  if (kgState.listenersAttached) return;
  kgState.listenersAttached = true;

  const search = document.getElementById("kgSearchInput");
  if (search) {
    search.addEventListener("input", () => {
      kgState.query = search.value.trim().toLowerCase();
      kgApplyFilters();
    });
    search.addEventListener("keydown", (e) => {
      if (e.key === "Enter") {
        const first = document.querySelector("#kgSearchResults [data-kg-node]");
        if (first) { e.preventDefault(); kgSelect(first.getAttribute("data-kg-node"), { center: true }); }
      } else if (e.key === "Escape" && search.value) {
        e.stopPropagation();
        search.value = "";
        kgState.query = "";
        kgApplyFilters();
      }
    });
  }

  const layout = document.getElementById("kgLayoutSelect");
  if (layout) layout.addEventListener("change", () => {
    if (kgState.cy) kgState.cy.elements(":visible").layout(kgLayoutOptions(layout.value)).run();
  });

  const fit = document.getElementById("kgFitBtn");
  if (fit) fit.addEventListener("click", () => kgState.cy && kgState.cy.animate({ fit: { eles: kgState.cy.elements(":visible"), padding: 30 } }, { duration: 250 }));

  const chips = document.getElementById("kgTypeChips");
  if (chips) chips.addEventListener("click", (e) => {
    const chip = e.target.closest("[data-kg-type]");
    if (!chip) return;
    const t = chip.getAttribute("data-kg-type");
    if (kgState.hiddenTypes.has(t)) kgState.hiddenTypes.delete(t);
    else kgState.hiddenTypes.add(t);
    kgRenderTypeChips();
    kgApplyFilters();
  });

  // Any [data-kg-node] button in the view (detail links, search results) selects that node.
  const view = document.getElementById("knowledgeView");
  if (view) view.addEventListener("click", (e) => {
    const link = e.target.closest("[data-kg-node]");
    if (link) { e.preventDefault(); kgSelect(link.getAttribute("data-kg-node"), { center: true }); return; }
    const lib = e.target.closest("[data-kg-library]");
    if (lib) { e.preventDefault(); kgOpenInLibrary(lib.getAttribute("data-kg-library")); }
  });

  document.addEventListener("keydown", (e) => {
    if (e.key !== "Escape" || state.currentView !== "knowledge" || !kgState.selectedId) return;
    // Let open dialogs (quick switcher, modals) own Escape.
    if ([...document.querySelectorAll('[role="dialog"]')].some((el) => el.offsetParent !== null)) return;
    const tag = (e.target && e.target.tagName) || "";
    if (tag === "INPUT" || tag === "TEXTAREA" || tag === "SELECT") return;
    kgSelect(null);
  });
}

function kgOpenInLibrary(handle) {
  setRoute(`#library/${encodeURIComponent(handle)}`);
  switchView("library");
}

function kgMatches(d, q) {
  if (!q) return true;
  return String(d.label || "").toLowerCase().includes(q)
    || String(d.id || "").toLowerCase().includes(q)
    || String(d.description || "").toLowerCase().includes(q)
    || (d.tags || []).some((t) => String(t).toLowerCase().includes(q))
    || (d.capabilities || []).some((c) => String(c).toLowerCase().includes(q));
}

function kgApplyFilters() {
  const cy = kgState.cy;
  if (!cy) return;
  const q = kgState.query;
  const matches = [];
  cy.batch(() => {
    cy.nodes().forEach((n) => {
      const d = n.data();
      const typeOk = !kgState.hiddenTypes.has(d.type);
      const ok = typeOk && kgMatches(d, q);
      n.style("display", typeOk ? "element" : "none");
      if (q) n.toggleClass("kg-faded", !ok);
      else n.removeClass("kg-faded");
      if (ok && q) matches.push(d);
    });
    cy.edges().forEach((e) => e.toggleClass("kg-faded", !!q && (e.source().hasClass("kg-faded") || e.target().hasClass("kg-faded"))));
  });
  if (!q && kgState.selectedId) kgHighlightNeighbourhood(kgState.selectedId);
  kgRenderSearchResults(matches);
  kgUpdateCountBadge();
}

function kgRenderSearchResults(matches) {
  const box = document.getElementById("kgSearchResults");
  if (!box) return;
  if (!kgState.query) { box.hidden = true; box.innerHTML = ""; return; }
  box.hidden = false;
  if (!matches.length) {
    box.innerHTML = '<div class="kg-results-empty">No matches. Try a capability (e.g. <code>mitre.</code>), tag or agent handle.</div>';
    return;
  }
  const shown = matches.slice(0, 8);
  box.innerHTML = `
    <div class="kg-results-head">${matches.length} match${matches.length === 1 ? "" : "es"}${matches.length > shown.length ? ` · showing ${shown.length}` : ""} · Enter opens first</div>
    <ul class="kg-results-list">
      ${shown.map((d) => `<li><button type="button" class="kg-result" data-kg-node="${escapeHtml(d.id)}">
        <span class="kg-dot" style="background:${kgTypeColor(d.type)}"></span>
        <span class="kg-result-label">${escapeHtml(d.label)}</span>
        <span class="kg-result-type">${escapeHtml(d.type)}</span>
      </button></li>`).join("")}
    </ul>`;
}

function kgRenderTypeChips() {
  const box = document.getElementById("kgTypeChips");
  if (!box || !kgState.data) return;
  const counts = {};
  kgState.data.nodes.forEach((n) => { counts[n.data.type] = (counts[n.data.type] || 0) + 1; });
  const types = [...KG_TYPE_ORDER.filter((t) => counts[t]), ...Object.keys(counts).filter((t) => !KG_TYPE_ORDER.includes(t)).sort()];
  box.innerHTML = types.map((t) => {
    const on = !kgState.hiddenTypes.has(t);
    return `<button type="button" class="kg-type-chip${on ? " is-on" : ""}" data-kg-type="${escapeHtml(t)}" aria-pressed="${on}">
      <span class="kg-dot" style="background:${kgTypeColor(t)}"></span>${escapeHtml(KG_TYPE_LABELS[t] || t)}<span class="kg-chip-count">${counts[t]}</span>
    </button>`;
  }).join("");
}

function kgUpdateCountBadge() {
  const badge = document.getElementById("kgCountBadge");
  if (!badge || !kgState.data) return;
  const all = kgState.data.nodes;
  const docs = all.filter((n) => n.data.type !== "agent").length;
  const agents = all.length - docs;
  badge.textContent = `${docs} docs · ${agents} agents`;
}

function kgApplyPendingSelection() {
  if (!kgState.cy) return;
  const id = kgState.pendingSelect;
  kgState.pendingSelect = null;
  if (id && kgState.cy.getElementById(id).length) kgSelect(id, { center: true, skipRoute: true });
  else if (id) kgRenderEmptyDetail(`“${id}” isn't in the knowledge graph. It may have been renamed or removed.`);
}

function kgSelect(id, opts = {}) {
  const cy = kgState.cy;
  if (!cy) return;
  kgState.selectedId = id;
  cy.elements().unselect();
  if (!id) {
    cy.elements().removeClass("kg-faded kg-hl");
    if (kgState.query) kgApplyFilters();
    kgRenderEmptyDetail();
    if (!opts.skipRoute) setRoute("#knowledge", { replace: true });
    return;
  }
  const node = cy.getElementById(id);
  if (!node.length) return;
  // Selecting a node of a hidden type brings that type back.
  if (kgState.hiddenTypes.has(node.data("type"))) {
    kgState.hiddenTypes.delete(node.data("type"));
    kgRenderTypeChips();
    kgApplyFilters();
  }
  node.select();
  kgHighlightNeighbourhood(id);
  if (opts.center) cy.animate({ center: { eles: node }, zoom: Math.max(cy.zoom(), 1) }, { duration: 250 });
  kgRenderDetail(node);
  if (!opts.skipRoute) setRoute(kgNodeHash(id));
}

function kgHighlightNeighbourhood(id) {
  const cy = kgState.cy;
  const node = cy.getElementById(id);
  if (!node.length) return;
  const hood = node.closedNeighborhood();
  cy.batch(() => {
    cy.elements().removeClass("kg-hl").addClass("kg-faded");
    hood.removeClass("kg-faded");
    node.connectedEdges().addClass("kg-hl");
  });
}

function kgRenderEmptyDetail(message) {
  const pane = document.getElementById("kgDetail");
  if (!pane) return;
  const d = kgState.data;
  const hubs = d ? d.nodes
    .filter((n) => n.data.type !== "agent")
    .map((n) => ({ d: n.data, deg: kgState.cy ? kgState.cy.getElementById(n.data.id).degree() : 0 }))
    .sort((a, b) => b.deg - a.deg)
    .slice(0, 5) : [];
  pane.innerHTML = `
    <div class="kg-empty">
      ${message ? `<div class="kg-empty-warn" role="status">${escapeHtml(message)}</div>` : ""}
      <h2 class="kg-empty-title">What the fleet knows, and who uses it</h2>
      <p class="kg-empty-text">Knowledge docs in <code>knowledge/</code> and the agents grounded on them. An agent links to a doc when they share an SDK capability. Select a node, or search by title, tag, capability or agent handle.</p>
      <ul class="kg-legend">
        <li><span class="kg-dot" style="background:${kgTypeColor("agent")}"></span><strong>Agents</strong>: hexagons; dashed lines show the docs they're grounded on</li>
        <li><span class="kg-dot" style="background:${kgTypeColor("persona")}"></span><strong>Personas</strong>: roles that own tasks</li>
        <li><span class="kg-dot" style="background:${kgTypeColor("task")}"></span><strong>Tasks</strong>: runbooks agents load as skills</li>
        <li><span class="kg-dot" style="background:${kgTypeColor("feature")}"></span><strong>Features</strong> / <span class="kg-dot" style="background:${kgTypeColor("concept")}"></span><strong>Concepts</strong>: platform reference and mental models</li>
        <li><span class="kg-legend-dash"></span>A dashed outline marks a doc past its <code>stale_after</code> date</li>
      </ul>
      ${hubs.length ? `<div class="kg-empty-sub">Most connected</div>
      <ul class="kg-link-list">${hubs.map((h) => kgLinkItem(h.d)).join("")}</ul>` : ""}
    </div>`;
}

function kgLinkItem(d, extra) {
  return `<li><button type="button" class="kg-link" data-kg-node="${escapeHtml(d.id)}">
    <span class="kg-dot" style="background:${kgTypeColor(d.type)}"></span>
    <span class="kg-link-label">${escapeHtml(d.label)}</span>
    ${extra ? `<span class="kg-link-extra">${extra}</span>` : ""}
  </button></li>`;
}

function kgRelatedSections(node) {
  const byKind = (eles) => eles.map((e) => e.data());
  const out = [];
  const outLinks = node.outgoers('edge[kind = "links"]').targets();
  const inLinks = node.incomers('edge[kind = "links"]').sources();
  const agents = node.incomers('edge[kind = "uses"]');
  if (agents.length) {
    out.push(`<section class="kg-section"><h3 class="kg-section-title">Used by ${agents.length} agent${agents.length === 1 ? "" : "s"}</h3>
      <ul class="kg-link-list">${agents.map((e) => kgLinkItem(e.source().data(), (e.data("via") || []).map((c) => `<code>${escapeHtml(c)}</code>`).join(" "))).join("")}</ul></section>`);
  }
  if (outLinks.length) {
    out.push(`<section class="kg-section"><h3 class="kg-section-title">Links to (${outLinks.length})</h3>
      <ul class="kg-link-list">${byKind(outLinks).map((d) => kgLinkItem(d, escapeHtml(d.type))).join("")}</ul></section>`);
  }
  if (inLinks.length) {
    out.push(`<section class="kg-section"><h3 class="kg-section-title">Referenced by (${inLinks.length})</h3>
      <ul class="kg-link-list">${byKind(inLinks).map((d) => kgLinkItem(d, escapeHtml(d.type))).join("")}</ul></section>`);
  }
  return out.join("");
}

function kgRenderDetail(node) {
  const pane = document.getElementById("kgDetail");
  if (!pane) return;
  const d = node.data();
  pane.scrollTop = 0;
  if (d.type === "agent") return kgRenderAgentDetail(pane, node);

  const [trustLabel, trustCls] = KG_TRUST_LABELS[d.trust_tier] || KG_TRUST_LABELS.unverified;
  const gen = d.generated && d.generated.by ? `${escapeHtml(d.generated.by)}${d.generated.at ? ` · ${escapeHtml(d.generated.at)}` : ""}` : "—";
  const ver = (d.verified || []).length ? d.verified.map((v) => `${escapeHtml(v.by)}${v.at ? ` · ${escapeHtml(v.at)}` : ""}`).join("<br>") : "Not yet verified";
  const safeUrl = (u) => (/^https?:\/\//i.test(String(u || "")) ? u : null);
  const sources = (d.sources || []).map((s) => {
    const url = safeUrl(s.resource);
    const label = escapeHtml(s.title || s.resource || "source");
    return url ? `<a href="${escapeHtml(url)}" target="_blank" rel="noopener noreferrer">${label} <span aria-hidden="true">↗</span><span class="sr-only">(opens in new tab)</span></a>` : label;
  }).join("<br>") || "—";
  const body = (kgState.data.bodies || {})[d.id] || "";

  pane.innerHTML = `
    <header class="kg-detail-head">
      <div class="kg-detail-badges">
        <span class="kg-type-badge" style="--kg-type:${kgTypeColor(d.type)}">${escapeHtml(d.type)}</span>
        <span class="kg-trust ${trustCls}">${trustLabel}</span>
        ${d.stale ? '<span class="kg-trust is-stale">Stale</span>' : ""}
        ${d.status && d.status !== "stable" ? `<span class="kg-trust is-unverified">${escapeHtml(d.status)}</span>` : ""}
      </div>
      <h2 class="kg-detail-title">${escapeHtml(d.label)}</h2>
      <div class="kg-detail-id"><code>knowledge/${escapeHtml(d.id)}.md</code></div>
      ${d.description ? `<p class="kg-detail-desc">${escapeHtml(d.description)}</p>` : ""}
    </header>
    ${d.stale ? `<div class="kg-callout is-warn" role="note">Past its review date${d.stale_after ? ` (<code>stale_after: ${escapeHtml(d.stale_after)}</code>)` : ""}. Agents still use it; re-verify before relying on it.</div>` : ""}
    ${kgRelatedSections(node)}
    <details class="kg-section kg-meta">
      <summary class="kg-section-title">Provenance &amp; metadata</summary>
      <dl class="kg-dl">
        ${(d.capabilities || []).length ? `<dt>Capabilities</dt><dd>${d.capabilities.map((c) => `<code>${escapeHtml(c)}</code>`).join(" ")}</dd>` : ""}
        ${(d.tags || []).length ? `<dt>Tags</dt><dd>${d.tags.map((t) => `<span class="kg-tag">${escapeHtml(t)}</span>`).join("")}</dd>` : ""}
        <dt>Generated</dt><dd>${gen}</dd>
        <dt>Verified</dt><dd>${ver}</dd>
        <dt>Review by</dt><dd>${escapeHtml(d.stale_after || "—")}</dd>
        <dt>Sources</dt><dd>${sources}</dd>
      </dl>
    </details>
    ${body ? `<section class="kg-section"><h3 class="kg-section-title">Content</h3><div class="kg-body msg-content">${formatMarkdown(body)}</div></section>` : ""}`;
}

function kgRenderAgentDetail(pane, node) {
  const d = node.data();
  const uses = node.outgoers('edge[kind = "uses"]');
  const byType = {};
  uses.forEach((e) => {
    const t = e.target().data();
    (byType[t.type] = byType[t.type] || []).push({ d: t, via: e.data("via") || [] });
  });
  const groups = KG_TYPE_ORDER.filter((t) => byType[t]).map((t) => `
    <section class="kg-section"><h3 class="kg-section-title">${escapeHtml(KG_TYPE_LABELS[t] || t)} (${byType[t].length})</h3>
      <ul class="kg-link-list">${byType[t].map((x) => kgLinkItem(x.d, x.via.map((c) => `<code>${escapeHtml(c)}</code>`).join(" "))).join("")}</ul>
    </section>`).join("");

  pane.innerHTML = `
    <header class="kg-detail-head">
      <div class="kg-detail-badges">
        <span class="kg-type-badge" style="--kg-type:${kgTypeColor("agent")}">agent</span>
        ${d.subsystem ? `<span class="kg-tag">${escapeHtml(d.subsystem)}</span>` : ""}
      </div>
      <h2 class="kg-detail-title">${escapeHtml(d.role || d.name)}</h2>
      <div class="kg-detail-id"><code>${escapeHtml(d.handle)}</code></div>
      ${d.description ? `<p class="kg-detail-desc">${escapeHtml(d.description)}</p>` : ""}
      <div class="kg-detail-actions">
        <button type="button" class="btn btn-sm btn-secondary" data-kg-library="${escapeHtml(d.handle)}">Open in Agent Library</button>
      </div>
    </header>
    ${uses.length
      ? `<p class="kg-detail-lead">Grounded on <strong>${uses.length}</strong> knowledge doc${uses.length === 1 ? "" : "s"} through shared capabilities.</p>${groups}`
      : `<div class="kg-callout" role="note">No knowledge docs list any of this agent's ${(d.capabilities || []).length} capabilities in <code>capabilities_used</code>, so it runs on its system prompt alone. Add a task under <code>knowledge/tasks/</code> to give it a runbook.</div>`}
    ${(d.capabilities || []).length ? `<details class="kg-section kg-meta"><summary class="kg-section-title">Capabilities (${d.capabilities.length})</summary>
      <div class="kg-cap-list">${d.capabilities.map((c) => `<code>${escapeHtml(c)}</code>`).join(" ")}</div></details>` : ""}`;
}

window.loadKnowledgeGraphView = loadKnowledgeGraphView;
window.kgNodeIdFromSourcePath = kgNodeIdFromSourcePath;
