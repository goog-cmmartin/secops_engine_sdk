/**
 * SecOps Multi-Agent Fleet - Frontend SPA Client
 * Inspired by Zulip streams/topics and Slack collaboration UX.
 */

const state = {
  activeStream: "detections",
  activeTopic: "rule-proposals",
  streams: [],
  messages: [],
  agents: [],
  proposals: [],
  activeDrawerTab: "proposals",
  evtSource: null,
  isRightDrawerOpen: false,
  currentView: "chat",
};

// --- Routing (#22): pushState for user navigation, replaceState while restoring ---
let routeRestoring = false;

function setRoute(hash, { replace = false } = {}) {
  if (window.location.hash === hash) return;
  if (replace || routeRestoring) history.replaceState(null, "", hash);
  else history.pushState(null, "", hash);
}

function isViewHash(h) {
  return /^(dashboards|ingestion|gastown|board|actions|issues|todos?|library|briefings|posture)(\/|$)/.test(h);
}

// Applies the current URL hash to the UI. Callers set routeRestoring.
function routeFromHash() {
  const hash = window.location.hash.replace(/^#/, "");
  if (hash.startsWith("dashboards") || hash.startsWith("ingestion")) {
    switchView("dashboards");
    const sub = hash.includes("/") ? hash.split("/")[1] : null;
    if (sub && ["feeds", "parsers", "diagnostics", "finops", "namespacelabels"].includes(sub)) {
      switchIngestionSubtab(sub);
    }
  } else if (/^(gastown|board|actions|issues|todos?)$/.test(hash)) {
    switchView("gastown");
  } else if (hash.startsWith("library")) {
    switchView("library");
  } else if (hash.startsWith("briefings") || hash === "posture") {
    switchView("briefings");
  } else if (hash.includes("/")) {
    const parts = hash.split("/");
    const stream = decodeURIComponent(parts[0]);
    const topic = decodeURIComponent(parts.slice(1).join("/"));
    if (state.currentView !== "chat") switchView("chat", { skipRoute: true });
    if (stream !== state.activeStream || topic !== state.activeTopic) {
      switchTopic(stream, topic);
    }
  } else if (state.currentView !== "chat") {
    switchView("chat");
  }
}

// --- Unread counts (#19): live SSE counts per channel, persisted locally ---
const UNREAD_STORAGE_KEY = "secops_unread_v1";
const unreadCounts = (() => {
  try { return JSON.parse(localStorage.getItem(UNREAD_STORAGE_KEY)) || {}; } catch (_) { return {}; }
})();

function channelKey(stream, topic) {
  return `${stream}/${topic}`;
}

function saveUnread() {
  try { localStorage.setItem(UNREAD_STORAGE_KEY, JSON.stringify(unreadCounts)); } catch (_) { /* quota / private mode */ }
}

function unreadFor(stream, topic) {
  return unreadCounts[channelKey(stream, topic)] || 0;
}

function unreadForStream(stream) {
  const prefix = `${stream}/`;
  return Object.keys(unreadCounts).reduce((n, k) => (k.startsWith(prefix) ? n + unreadCounts[k] : n), 0);
}

function bumpUnread(stream, topic) {
  const key = channelKey(stream, topic);
  unreadCounts[key] = (unreadCounts[key] || 0) + 1;
  saveUnread();
  const known = stream === "dm" || (state.streams || []).some(
    (s) => s.id === stream && (s.topics || []).some((t) => t.name === topic)
  );
  if (known) renderUnreadIndicators();
  else loadStreams().then(renderUnreadIndicators); // new topic: refresh sidebar
}

function clearUnread(stream, topic) {
  const key = channelKey(stream, topic);
  if (!unreadCounts[key]) return;
  delete unreadCounts[key];
  saveUnread();
  renderUnreadIndicators();
}

function renderUnreadIndicators() {
  renderStreams();
  renderDirectMessages();
  const total = Object.values(unreadCounts).reduce((a, b) => a + b, 0);
  const navBadge = document.getElementById("navChatBadge");
  if (navBadge) {
    navBadge.textContent = total > 99 ? "99+" : String(total);
    navBadge.hidden = total === 0;
    navBadge.setAttribute("aria-label", `${total} unread message${total === 1 ? "" : "s"}`);
  }
  const baseTitle = "Google SecOps Multi-Agent Fleet";
  document.title = total > 0 ? `(${total}) ${baseTitle}` : baseTitle;
}

function unreadBadgeHtml(n) {
  if (!n) return "";
  return `<span class="unread-badge" aria-label="${n} unread">${n > 99 ? "99+" : n}</span>`;
}

// --- Theme Management ---
function getPreferredTheme() {
  const saved = localStorage.getItem("secops_theme");
  if (saved) return saved;
  return window.matchMedia && window.matchMedia("(prefers-color-scheme: light)").matches ? "light" : "dark";
}

function applyTheme(theme) {
  document.documentElement.setAttribute("data-theme", theme);
  if (theme === "light") {
    document.documentElement.classList.add("smp-theme-light");
    document.documentElement.classList.remove("smp-theme-dark");
  } else {
    document.documentElement.classList.add("smp-theme-dark");
    document.documentElement.classList.remove("smp-theme-light");
  }
  localStorage.setItem("secops_theme", theme);
  const icon = document.getElementById("themeToggleIcon");
  if (icon) {
    icon.textContent = theme === "light" ? "☀️" : "🌙";
  }
}

function initTheme() {
  const current = getPreferredTheme();
  applyTheme(current);
  const btn = document.getElementById("themeToggleBtn");
  if (btn) {
    btn.addEventListener("click", () => {
      const active = document.documentElement.getAttribute("data-theme") || "dark";
      const target = active === "dark" ? "light" : "dark";
      applyTheme(target);
    });
  }
}

// Pre-apply theme before render to eliminate flash
(function() {
  const t = localStorage.getItem("secops_theme") || (window.matchMedia && window.matchMedia("(prefers-color-scheme: light)").matches ? "light" : "dark");
  document.documentElement.setAttribute("data-theme", t);
  if (t === "light") {
    document.documentElement.classList.add("smp-theme-light");
  } else {
    document.documentElement.classList.add("smp-theme-dark");
  }
})();

// --- Initialization ---
document.addEventListener("DOMContentLoaded", async () => {
  initTheme();
  const hash = window.location.hash.replace(/^#/, "");
  if (hash.includes("/") && !isViewHash(hash)) {
    const parts = hash.split("/");
    state.activeStream = decodeURIComponent(parts[0]);
    state.activeTopic = decodeURIComponent(parts.slice(1).join("/"));
  }
  setupEventListeners();
  setupA11y();
  setupActions();
  setupQuickSwitcher();
  setupResponsiveLayout();
  await Promise.all([loadStreams(), loadAgents(), loadProposals()]);
  routeRestoring = true;
  try {
    routeFromHash();
    // Always load the active chat topic (in the background if another view is showing).
    await switchTopic(state.activeStream, state.activeTopic);
  } finally {
    routeRestoring = false;
  }
  renderUnreadIndicators();
  initSSE();
  // Top-bar escalation count needs the overview even when Actions isn't open.
  if (state.currentView !== "gastown") loadGastownOverview();
  setInterval(() => {
    if (!document.hidden) loadGastownOverview();
  }, TOPBAR_REFRESH_MS);
});

const TOPBAR_REFRESH_MS = 60000;

function setupEventListeners() {
  const composerInput = document.getElementById("composerInput");
  const sendBtn = document.getElementById("sendBtn");

  sendBtn.addEventListener("click", handleSendMessage);
  setupComposerAutosize(composerInput);
  composerInput.addEventListener("keydown", (e) => {
    if (e.key === "Enter" && !e.shiftKey) {
      if (mentionState.active) {
        // Handled by mention dropdown autocomplete
        return;
      }
      e.preventDefault();
      handleSendMessage();
    }
  });

  // Top Navigation Tabs
  const navBtnChat = document.getElementById("navBtnChat");
  const navBtnGastown = document.getElementById("navBtnGastown");
  const navBtnDashboards = document.getElementById("navBtnDashboards") || document.getElementById("navBtnIngestion");
  const navBtnLibrary = document.getElementById("navBtnLibrary");
  const navBtnBriefings = document.getElementById("navBtnBriefings");
  if (navBtnChat) navBtnChat.addEventListener("click", () => switchView("chat"));
  if (navBtnGastown) navBtnGastown.addEventListener("click", () => switchView("gastown"));
  if (navBtnDashboards) navBtnDashboards.addEventListener("click", () => switchView("dashboards"));
  if (navBtnLibrary) navBtnLibrary.addEventListener("click", () => switchView("library"));
  if (navBtnBriefings) navBtnBriefings.addEventListener("click", () => switchView("briefings"));


  // Right Drawer Toggles
  const toggleRightDrawerBtn = document.getElementById("toggleRightDrawerBtn");
  const btnCloseDrawer = document.getElementById("btnCloseDrawer");
  const btnOpenFullBoard = document.getElementById("btnOpenFullBoard");
  const sidebarRight = document.getElementById("sidebarRight");

  if (toggleRightDrawerBtn) {
    toggleRightDrawerBtn.addEventListener("click", () => {
      state.isRightDrawerOpen = !state.isRightDrawerOpen;
      if (state.isRightDrawerOpen) {
        sidebarRight.classList.remove("sidebar-right-closed");
        toggleRightDrawerBtn.classList.add("active");
      } else {
        sidebarRight.classList.add("sidebar-right-closed");
        toggleRightDrawerBtn.classList.remove("active");
      }
    });
  }

  const clearTopicBtn = document.getElementById("clearTopicBtn");
  if (clearTopicBtn) {
    clearTopicBtn.addEventListener("click", handleClearTopic);
  }

  const btnTriggerRuleAudit = document.getElementById("btnTriggerRuleAudit");
  if (btnTriggerRuleAudit) {
    btnTriggerRuleAudit.addEventListener("click", async () => {
      btnTriggerRuleAudit.disabled = true;
      btnTriggerRuleAudit.innerHTML = "<span>⏳ Auditing...</span>";
      try {
        const res = await fetch("/api/rules/audit?include_curated=true&sync_embeddings=true&lookback_days=90&run_conflict_scan=true", { method: "POST" });
        if (!res.ok) throw new Error(await describeHttpError(res));
        showToast("success", "Rule audit complete — opening Decay Review.");
        await switchTopic("detections", "decay-review");
      } catch (err) {
        console.error("Rule audit failed:", err);
        showToast("error", `Rule audit failed: ${err.message}`);
      } finally {
        btnTriggerRuleAudit.disabled = false;
        btnTriggerRuleAudit.innerHTML = "<span>🛡️ Audit Rules</span>";
      }
    });
  }
  const btnTriggerMitreAudit = document.getElementById("btnTriggerMitreAudit");
  if (btnTriggerMitreAudit) {
    btnTriggerMitreAudit.addEventListener("click", async () => {
      btnTriggerMitreAudit.disabled = true;
      btnTriggerMitreAudit.innerHTML = "<span>⏳ Analyzing...</span>";
      try {
        const res = await fetch("/api/mitre/audit?profile=global_baseline", { method: "POST" });
        if (!res.ok) throw new Error(await describeHttpError(res));
        const data = await res.json().catch(() => ({}));
        if (data && data.status === "ERROR") throw new Error(data.message || "Audit returned an error");
        showToast("success", "MITRE coverage assessment complete.");
        await switchTopic("threat_intel", "mitre-coverage");
      } catch (err) {
        console.error("MITRE audit failed:", err);
        showToast("error", `MITRE coverage assessment failed: ${err.message}`);
      } finally {
        btnTriggerMitreAudit.disabled = false;
        btnTriggerMitreAudit.innerHTML = "<span>🎯 MITRE Coverage</span>";
      }
    });
  }

  if (btnCloseDrawer) {
    btnCloseDrawer.addEventListener("click", () => {
      state.isRightDrawerOpen = false;
      sidebarRight.classList.add("sidebar-right-closed");
      if (toggleRightDrawerBtn) toggleRightDrawerBtn.classList.remove("active");
    });
  }

  if (btnOpenFullBoard) {
    btnOpenFullBoard.addEventListener("click", () => {
      switchView("gastown");
    });
  }

  // Slack-Style Collapsible Direct Messages Section
  const dmSectionHeader = document.getElementById("dmSectionHeader");
  const dmToggleIcon = document.getElementById("dmToggleIcon");
  const dmList = document.getElementById("dmList");
  const dmSearchContainer = document.getElementById("dmSearchContainer");
  const dmSearchInput = document.getElementById("dmSearchInput");
  const dmClearFilterBtn = document.getElementById("dmClearFilterBtn");

  if (dmSectionHeader && dmList) {
    dmSectionHeader.addEventListener("click", () => {
      dmList.classList.toggle("collapsed");
      if (dmSearchContainer) dmSearchContainer.classList.toggle("collapsed");
      if (dmToggleIcon) dmToggleIcon.classList.toggle("collapsed");
    });
  }

  if (dmSearchInput) {
    dmSearchInput.addEventListener("input", (e) => {
      dmSearchQuery = e.target.value || "";
      if (dmClearFilterBtn) {
        dmClearFilterBtn.style.display = dmSearchQuery ? "inline-flex" : "none";
      }
      renderDirectMessages();
    });
    dmSearchInput.addEventListener("keydown", (e) => {
      if (e.key === "Escape") {
        dmSearchInput.value = "";
        dmSearchQuery = "";
        if (dmClearFilterBtn) dmClearFilterBtn.style.display = "none";
        renderDirectMessages();
      }
    });
  }

  if (dmClearFilterBtn) {
    dmClearFilterBtn.addEventListener("click", () => {
      if (dmSearchInput) dmSearchInput.value = "";
      dmSearchQuery = "";
      dmClearFilterBtn.style.display = "none";
      renderDirectMessages();
      if (dmSearchInput) dmSearchInput.focus();
    });
  }

  // Gas Town Subtabs
  const tabGtKanban = document.getElementById("tabGtKanban");
  const tabGtWorkQueue = document.getElementById("tabGtWorkQueue");
  const tabGtConvoys = document.getElementById("tabGtConvoys");
  const tabGtRefinery = document.getElementById("tabGtRefinery");
  const tabGtEscalations = document.getElementById("tabGtEscalations");
  const tabGtPatrols = document.getElementById("tabGtPatrols");
  const btnRefreshGastown = document.getElementById("btnRefreshGastown");

  if (tabGtKanban) tabGtKanban.addEventListener("click", () => switchGastownSubtab("kanban"));
  if (tabGtWorkQueue) tabGtWorkQueue.addEventListener("click", () => switchGastownSubtab("work_queue"));
  ["socFilterPlane", "socFilterStatus"].forEach((id) => {
    const el = document.getElementById(id);
    if (el) el.addEventListener("change", () => renderGastownWorkQueue());
  });
  if (tabGtConvoys) tabGtConvoys.addEventListener("click", () => switchGastownSubtab("convoys"));
  if (tabGtRefinery) tabGtRefinery.addEventListener("click", () => switchGastownSubtab("refinery"));
  if (tabGtEscalations) tabGtEscalations.addEventListener("click", () => switchGastownSubtab("escalations"));
  if (tabGtPatrols) tabGtPatrols.addEventListener("click", () => switchGastownSubtab("patrols"));
  if (btnRefreshGastown) btnRefreshGastown.addEventListener("click", () => loadGastownOverview(true));

  // #10: summary cards jump to their sub-tab (or top-level view); alert strip -> review column.
  document.querySelectorAll(".gt-summary-card[data-gt-target]").forEach((card) => {
    card.addEventListener("click", () => {
      const target = card.dataset.gtTarget;
      if (target === "library" || target === "dashboards") switchView(target);
      else switchGastownSubtab(target);
    });
  });
  const gtAlertItem = document.getElementById("gtAlertItem");
  if (gtAlertItem) gtAlertItem.addEventListener("click", focusReviewColumn);

  // #9: top-bar status chips + About.
  const topbarEscalations = document.getElementById("topbarEscalations");
  if (topbarEscalations) topbarEscalations.addEventListener("click", () => openActionsSubtab("escalations"));
  const fleetStatusTag = document.getElementById("fleetStatusTag");
  if (fleetStatusTag) fleetStatusTag.addEventListener("click", () => switchView("library"));
  const aboutBtn = document.getElementById("aboutBtn");
  if (aboutBtn) aboutBtn.addEventListener("click", openAboutDialog);

  // Diff Modal Close
  const btnCloseDiffModal = document.getElementById("btnCloseDiffModal");
  if (btnCloseDiffModal) {
    btnCloseDiffModal.addEventListener("click", closeGastownDiffModal);
  }

  // Drawer Tabs
  const tabProposals = document.getElementById("tabProposals");
  const tabTuning = document.getElementById("tabTuning");
  const tabDecay = document.getElementById("tabDecay");
  const tabFleet = document.getElementById("tabFleet");
  if (tabProposals) tabProposals.addEventListener("click", () => switchDrawerTab("proposals"));
  if (tabTuning) tabTuning.addEventListener("click", () => switchDrawerTab("tuning"));
  if (tabDecay) tabDecay.addEventListener("click", () => switchDrawerTab("decay"));
  if (tabFleet) tabFleet.addEventListener("click", () => switchDrawerTab("fleet"));

  // Dedicated Ingestion Page Actions
  const pageBtnAuditFeeds = document.getElementById("pageBtnAuditFeeds");
  const pageBtnAuditParsers = document.getElementById("pageBtnAuditParsers");
  const pageBtnAuditRules = document.getElementById("pageBtnAuditRules");
  const pageBtnAnalyzeCost = document.getElementById("pageBtnAnalyzeCost");
  const pageBtnRefresh = document.getElementById("pageBtnRefresh");
  if (pageBtnAuditFeeds) pageBtnAuditFeeds.addEventListener("click", handleAuditFeedsAction);
  if (pageBtnAuditParsers) pageBtnAuditParsers.addEventListener("click", handleAuditParsersAction);
  if (pageBtnAuditRules) pageBtnAuditRules.addEventListener("click", handleAuditRulesPageAction);
  if (pageBtnAnalyzeCost) {
    pageBtnAnalyzeCost.addEventListener("click", () => {
      switchIngestionSubtab("finops");
      fetchFinopsData(true);
    });
  }
  if (pageBtnRefresh) pageBtnRefresh.addEventListener("click", () => renderIngestionPage(true));

  // Dedicated Ingestion Subpage Tabs
  const tabIngFeeds = document.getElementById("tabIngestionFeeds");
  const tabIngParsers = document.getElementById("tabIngestionParsers");
  const tabIngDiag = document.getElementById("tabIngestionDiagnostics");
  const tabIngFinOps = document.getElementById("tabIngestionFinOps");
  const tabIngNsLabels = document.getElementById("tabIngestionNamespaceLabels");
  if (tabIngFeeds) tabIngFeeds.addEventListener("click", () => switchIngestionSubtab("feeds"));
  if (tabIngParsers) tabIngParsers.addEventListener("click", () => switchIngestionSubtab("parsers"));
  if (tabIngDiag) tabIngDiag.addEventListener("click", () => switchIngestionSubtab("diagnostics"));
  if (tabIngFinOps) tabIngFinOps.addEventListener("click", () => switchIngestionSubtab("finops"));
  if (tabIngNsLabels) tabIngNsLabels.addEventListener("click", () => switchIngestionSubtab("namespacelabels"));

  // FinOps Action Button
  const btnRunFinopsAnalysis = document.getElementById("btnRunFinopsAnalysis");
  if (btnRunFinopsAnalysis) btnRunFinopsAnalysis.addEventListener("click", () => fetchFinopsData(true));

  // Namespace & Labels Audit Action Button
  const btnRunNsLabelsAudit = document.getElementById("btnRunNsLabelsAudit");
  if (btnRunNsLabelsAudit) btnRunNsLabelsAudit.addEventListener("click", () => fetchNamespaceLabelsData());

  // Chat CTA buttons on Ingestion tables
  const btnChatFeed = document.getElementById("btnChatFeedAgent");
  if (btnChatFeed) {
    btnChatFeed.addEventListener("click", () => {
      switchTopicAndChat("ingestion", "feed-health", "@feed-agent audit feeds");
    });
  }
  const btnChatParser = document.getElementById("btnChatParserDoctor");
  if (btnChatParser) {
    btnChatParser.addEventListener("click", () => {
      switchTopicAndChat("ingestion", "parser-drops", "@parser-doctor audit parsers");
    });
  }
  const btnChatLogCost = document.getElementById("btnChatLogCostAgent");
  if (btnChatLogCost) {
    btnChatLogCost.addEventListener("click", () => {
      switchTopicAndChat("ingestion", "finops", "@log-cost-agent analyze log costs");
    });
  }
  const btnChatNamespaceAgent = document.getElementById("btnChatNamespaceAgent");
  if (btnChatNamespaceAgent) {
    btnChatNamespaceAgent.addEventListener("click", () => {
      switchTopicAndChat("ingestion", "namespace-labels", "@namespace-label-agent audit telemetry labels and namespaces");
    });
  }

  // Diagnostic Lab
  const btnRunLabDiagnose = document.getElementById("btnRunLabDiagnose");
  if (btnRunLabDiagnose) btnRunLabDiagnose.addEventListener("click", handleRunLabDiagnose);

  // Filters & Search for Dedicated Ingestion Page
  setupIngestionFilters();

  // Setup Mention Autocomplete
  setupMentionAutocomplete();

  // Scroll-follow: hide the "new messages" pill once the reader reaches the bottom.
  const timelineEl = document.getElementById("messageTimeline");
  if (timelineEl) {
    timelineEl.addEventListener("scroll", () => {
      if (isNearBottom(timelineEl)) resetNewMessagesPill();
    }, { passive: true });
  }
  const newMessagesPill = document.getElementById("newMessagesPill");
  if (newMessagesPill) {
    newMessagesPill.addEventListener("click", () => {
      resetNewMessagesPill();
      scrollToBottom(true);
    });
  }

  // URL navigation: Back/Forward and manual hash edits both fire popstate.
  window.addEventListener("popstate", () => {
    routeRestoring = true;
    try {
      routeFromHash();
    } finally {
      routeRestoring = false;
    }
  });
}

// --- SSE Real-time Feed ---
let agentStatusTimeout = null;
let agentStatusTicker = null;
const AGENT_STALE_MS = 120000; // no progress update for 2 min -> show "no recent updates"

function formatElapsed(ms) {
  const total = Math.max(0, Math.floor(ms / 1000));
  const m = Math.floor(total / 60);
  const sec = total % 60;
  return m > 0 ? `${m}m ${String(sec).padStart(2, "0")}s` : `${sec}s`;
}

function tickAgentElapsed() {
  const card = document.getElementById("agentStatusCard");
  const el = document.getElementById("agentStatusElapsed");
  if (!card || !el) {
    if (agentStatusTicker) { clearInterval(agentStatusTicker); agentStatusTicker = null; }
    return;
  }
  el.textContent = formatElapsed(Date.now() - card._startedAt);
}

function armAgentStaleTimer() {
  if (agentStatusTimeout) clearTimeout(agentStatusTimeout);
  agentStatusTimeout = setTimeout(markAgentStatusStale, AGENT_STALE_MS);
}

function markAgentStatusStale() {
  agentStatusTimeout = null;
  const card = document.getElementById("agentStatusCard");
  if (!card || card.classList.contains("is-stale")) return;
  card.classList.add("is-stale");
  const badge = card.querySelector(".agent-status-badge");
  if (badge) badge.textContent = "No recent updates";
  const label = document.getElementById("agentStatusLabel");
  if (label) {
    label.textContent = `No update from ${card.dataset.agent || "the agent"} for ${Math.round(AGENT_STALE_MS / 60000)} min. It may still be working, or it may have stopped.`;
  }
  const actions = document.createElement("div");
  actions.className = "agent-status-actions";
  actions.innerHTML = `
    <button type="button" class="agent-status-action-btn" data-act="refresh">Check again</button>
    <button type="button" class="agent-status-action-btn" data-act="dismiss">Dismiss</button>
  `;
  actions.querySelector('[data-act="refresh"]').addEventListener("click", recheckAgentStatus);
  actions.querySelector('[data-act="dismiss"]').addEventListener("click", hideAgentStatusIndicator);
  (card.querySelector(".agent-status-body") || card).appendChild(actions);
}

// Reload the topic (picks up any reply missed while disconnected) and re-hydrate the active job.
async function recheckAgentStatus() {
  await loadMessages(state.activeStream, state.activeTopic);
  if (!document.getElementById("agentStatusCard")) {
    showToast("info", "No active job for this topic. The agent has finished or stopped — any reply is shown in the timeline.");
  }
}

function showAgentStatusIndicator(agentHandle, statusText, userHandle, startedAt) {
  hideAgentStatusIndicator();
  const container = document.getElementById("messageTimeline");
  if (!container) return;

  const card = document.createElement("div");
  card.id = "agentStatusCard";
  card.className = "agent-status-card";
  card.dataset.agent = agentHandle || "@secops-agent";
  card.dataset.user = userHandle || "";
  const startedMs = startedAt ? Date.parse(startedAt) : NaN;
  card._startedAt = Number.isFinite(startedMs) ? startedMs : Date.now();
  const userContextHtml = userHandle ? `<span class="agent-status-user-context">working on ${escapeHtml(userHandle)}'s request</span>` : "";
  card.innerHTML = `
    <div class="msg-avatar avatar-agent pulsing-avatar">
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
        <rect x="3" y="11" width="18" height="10" rx="2"></rect>
        <circle cx="12" cy="5" r="2"></circle>
        <path d="M12 7v4"></path>
        <line x1="8" y1="16" x2="8" y2="16"></line>
        <line x1="16" y1="16" x2="16" y2="16"></line>
      </svg>
    </div>
    <div class="agent-status-body">
      <div class="agent-status-header">
        <span class="agent-status-handle">${escapeHtml(agentHandle || "@secops-agent")}</span>
        <span class="agent-status-badge">
          <span class="badge-pulse-dot"></span>
          THINKING
        </span>
        ${userContextHtml}
        <span class="agent-status-elapsed" id="agentStatusElapsed" title="Time since the request started"></span>
      </div>
      <div class="agent-status-text-row">
        <div class="agent-status-spinner"></div>
        <div class="agent-status-label" id="agentStatusLabel">${escapeHtml(statusText || "Processing request...")}</div>
      </div>
      <div class="agent-progress-track">
        <div class="agent-progress-shimmer"></div>
      </div>
    </div>
  `;

  const wasNearBottom = isNearBottom(container);
  container.appendChild(card);
  if (wasNearBottom) scrollToBottom();

  armAgentStaleTimer();
  tickAgentElapsed();
  agentStatusTicker = setInterval(tickAgentElapsed, 1000);
}

function updateAgentStatusIndicator(agentHandle, statusText, userHandle, startedAt) {
  const card = document.getElementById("agentStatusCard");
  if (!card || card.classList.contains("is-stale")) {
    // New job, or progress resumed after going quiet: rebuild the live card.
    const since = startedAt || (card ? new Date(card._startedAt).toISOString() : undefined);
    showAgentStatusIndicator(agentHandle, statusText, userHandle || (card && card.dataset.user), since);
    return;
  }
  armAgentStaleTimer();
  const label = document.getElementById("agentStatusLabel");
  if (label) {
    label.style.opacity = "0.4";
    setTimeout(() => {
      label.textContent = statusText;
      label.style.opacity = "1";
    }, 120);
  }
  const container = document.getElementById("messageTimeline");
  if (container && isNearBottom(container)) scrollToBottom();
}

function hideAgentStatusIndicator() {
  if (agentStatusTimeout) {
    clearTimeout(agentStatusTimeout);
    agentStatusTimeout = null;
  }
  if (agentStatusTicker) {
    clearInterval(agentStatusTicker);
    agentStatusTicker = null;
  }
  const card = document.getElementById("agentStatusCard");
  if (card) {
    card.remove();
  }
}

function setLiveStatus(status) {
  const titles = {
    connected: "Live: connected to event stream",
    connecting: "Connecting to event stream…",
    disconnected: "Disconnected from event stream — data may be stale. Reconnecting…",
  };
  document.querySelectorAll(".live-indicator").forEach((el) => {
    el.classList.remove("is-connected", "is-connecting", "is-disconnected");
    el.classList.add(`is-${status}`);
    el.title = titles[status];
    el.setAttribute("aria-label", titles[status]);
  });
  const banner = document.getElementById("connectionBanner");
  if (banner) banner.hidden = status !== "disconnected";
  const chip = document.getElementById("connChip");
  if (chip) {
    chip.classList.remove("is-connected", "is-connecting", "is-disconnected");
    chip.classList.add(`is-${status}`);
    chip.title = titles[status];
    const label = document.getElementById("connChipLabel");
    if (label) label.textContent = { connected: "Live", connecting: "Connecting…", disconnected: "Offline" }[status];
  }
  state.liveStatus = status;
}

function initSSE() {
  if (state.evtSource) state.evtSource.close();
  if (state.sseReconnectTimer) {
    clearTimeout(state.sseReconnectTimer);
    state.sseReconnectTimer = null;
  }
  setLiveStatus("connecting");
  state.evtSource = new EventSource("/api/events");

  state.evtSource.onopen = () => {
    const wasDisconnected = state.sseWasDisconnected;
    state.sseWasDisconnected = false;
    setLiveStatus("connected");
    if (wasDisconnected) {
      // Events may have been missed while offline; resync the key views.
      loadProposals();
      if (typeof loadGastownOverview === "function") loadGastownOverview();
    }
  };

  state.evtSource.onmessage = (e) => {
    try {
      const data = JSON.parse(e.data);

      if (data.type === "active_jobs_snapshot") {
        if (data.jobs && Array.isArray(data.jobs)) {
          const matchingJob = data.jobs.find(
            (j) => j.stream === state.activeStream && j.topic === state.activeTopic
          );
          if (matchingJob) {
            showAgentStatusIndicator(matchingJob.agent_handle, matchingJob.step || matchingJob.status, matchingJob.user_handle, matchingJob.started_at);
          }
        }
      } else if (data.type === "agent_status") {
        if (data.stream === state.activeStream && data.topic === state.activeTopic) {
          const userH = data.user_handle || (data.job && data.job.user_handle);
          const stepText = data.step || data.status;
          updateAgentStatusIndicator(data.agent_handle, stepText, userH, data.job && data.job.started_at);
        }
      } else if (data.type === "job_completed" || data.type === "job_failed") {
        if (data.stream === state.activeStream && data.topic === state.activeTopic) {
          hideAgentStatusIndicator();
        }
      } else if (data.type === "topic_cleared") {
        clearUnread(data.stream, data.topic);
        if (data.stream === state.activeStream && data.topic === state.activeTopic) {
          state.messages = [];
          hideAgentStatusIndicator();
          renderTimeline();
        }
        loadStreams();
      } else if (data.type === "new_message") {
        const msg = data.message;
        const isActiveChannel = msg.stream === state.activeStream && msg.topic === state.activeTopic;
        // Count messages from others that the operator isn't currently looking at.
        if (msg.sender_handle !== "@operator" && !(isActiveChannel && state.currentView === "chat")) {
          bumpUnread(msg.stream, msg.topic);
        }
        // If message belongs to current stream and topic, handle timeline update
        if (isActiveChannel) {
          if (msg.sender_type !== "user") {
            // Agent message arrived! Hide the status indicator
            hideAgentStatusIndicator();
          }
          if (findMessageCard(msg.id)) {
            // Already rendered (e.g. reconciled from the POST response).
          } else if (msg.sender_type === "user" && reconcilePendingByContent(msg)) {
            // Matched our own optimistic message.
          } else {
            state.messages.push(msg);
            appendMessageToTimeline(msg, { live: true });
            if (msg.sender_type !== "user" && state.currentView === "chat") {
              announce(`New message from ${msg.sender_handle || "agent"}`);
            }
          }
        }
        // Refresh proposals list if message carries a proposal
        if (msg.proposal_id) {
          loadProposals();
          loadGastownOverview();
        }
      }
    } catch (err) {
      console.warn("SSE parse error:", err);
    }
  };

  state.evtSource.onerror = () => {
    console.debug("SSE disconnected, attempting reconnection in 3s...");
    state.sseWasDisconnected = true;
    setLiveStatus("disconnected");
    // Close so the browser's built-in retry doesn't race our own.
    state.evtSource.close();
    if (!state.sseReconnectTimer) {
      state.sseReconnectTimer = setTimeout(() => {
        state.sseReconnectTimer = null;
        initSSE();
      }, 3000);
    }
  };
}

// --- API Calls ---
async function loadStreams() {
  try {
    state.streams = await fetchJsonOrThrow("/api/streams");
    renderStreams();
  } catch (err) {
    console.error("Failed loading streams:", err);
    // Background refreshes keep the last good list; only an empty sidebar shows the error.
    if (!state.streams.length) {
      showLoadError(document.getElementById("streamsList"), { title: "Couldn't load streams", error: err, retry: loadStreams });
    }
  }
}

async function loadAgents() {
  try {
    state.agents = await fetchJsonOrThrow("/api/agents");
    renderAgents();
  } catch (err) {
    console.error("Failed loading agents:", err);
    if (!state.agents.length) {
      showLoadError(document.getElementById("dmList"), { title: "Couldn't load agents", error: err, retry: loadAgents });
    }
  }
}

// Top-bar "Actions" badge + drawer toggle: open proposals awaiting operator review.
function setOpenProposalBadges(openCount) {
  const navBoardBadge = document.getElementById("navBoardBadge");
  if (navBoardBadge) {
    navBoardBadge.textContent = openCount > 99 ? "99+" : String(openCount);
    navBoardBadge.hidden = !openCount;
    navBoardBadge.title = `${openCount} proposal${openCount === 1 ? "" : "s"} awaiting review`;
    navBoardBadge.setAttribute("aria-label", navBoardBadge.title);
  }
  const drawerToggleBadge = document.getElementById("drawerToggleBadge");
  if (drawerToggleBadge) drawerToggleBadge.textContent = openCount;
}

// Top-bar escalation chip. `count` is null when the overview is unavailable.
function setTopbarEscalations(count) {
  const chip = document.getElementById("topbarEscalations");
  if (!chip) return;
  const countEl = document.getElementById("topbarEscCount");
  const labelEl = document.getElementById("topbarEscLabel");
  const known = typeof count === "number";
  if (countEl) countEl.textContent = known ? String(count) : UNKNOWN_METRIC;
  if (labelEl) labelEl.textContent = known && count === 1 ? "escalation" : "escalations";
  chip.classList.toggle("is-alert", known && count > 0);
  chip.classList.toggle("is-unknown", !known);
  chip.title = known
    ? `${count} unacknowledged escalation${count === 1 ? "" : "s"} — open Escalations`
    : "Escalation count unavailable — open Escalations";
}

// Jump into a specific Actions sub-tab from anywhere (top bar, summary cards).
function openActionsSubtab(subtab) {
  switchGastownSubtab(subtab);
  if (state.currentView !== "gastown") switchView("gastown");
}
window.openActionsSubtab = openActionsSubtab;

async function loadProposals() {
  try {
    state.proposals = await fetchJsonOrThrow("/api/proposals");
    renderProposalsDrawer();
    const openCount = state.proposals.filter(p => p.status === "OPEN").length;
    const openPropCount = document.getElementById("openPropCount");
    if (openPropCount) openPropCount.textContent = openCount;
    setOpenProposalBadges(openCount);
  } catch (err) {
    console.error("Failed loading proposals:", err);
    if (state.activeDrawerTab === "proposals") {
      showLoadError(document.getElementById("drawerContent"), { title: "Couldn't load proposals", error: err, retry: loadProposals });
    }
  }
}

async function loadMessages(stream, topic) {
  try {
    const messages = await fetchJsonOrThrow(`/api/messages?stream=${encodeURIComponent(stream)}&topic=${encodeURIComponent(topic)}`);
    // The operator may have moved on while this was in flight.
    if (stream !== state.activeStream || topic !== state.activeTopic) return;
    state.messages = messages;
    renderTimeline();

    // Hydrate active in-flight jobs for this channel (persists across page reloads & multi-user sync)
    try {
      const jobsRes = await fetch(`/api/jobs/active?stream=${encodeURIComponent(stream)}&topic=${encodeURIComponent(topic)}`);
      if (jobsRes.ok) {
        const activeJobs = await jobsRes.json();
        if (activeJobs && activeJobs.length > 0) {
          const job = activeJobs[0];
          showAgentStatusIndicator(job.agent_handle, job.step || job.status, job.user_handle, job.started_at);
        } else {
          hideAgentStatusIndicator();
        }
      }
    } catch (jobErr) {
      console.debug("Could not hydrate active jobs:", jobErr);
    }
  } catch (err) {
    console.error("Failed loading messages:", err);
    if (stream !== state.activeStream || topic !== state.activeTopic) return;
    const label = stream === "dm" ? topic : `#${stream} › ${topic}`;
    showLoadError(document.getElementById("messageTimeline"), {
      title: `Couldn't load messages for ${label}`,
      error: err,
      retry: () => loadMessages(stream, topic),
    });
  }
}

// --- Stream & Topic Navigation ---
async function switchTopic(stream, topic) {
  hideAgentStatusIndicator();
  state.activeStream = stream;
  state.activeTopic = topic;
  recordRecentChannel(stream, topic);
  setSidebarOpen(false);
  // Only the visible chat view owns the URL (background loads must not clobber #actions etc.).
  if (state.currentView === "chat") {
    setRoute(`#${stream}/${topic}`);
    clearUnread(stream, topic);
  }

  // Update Breadcrumbs
  if (stream === "dm") {
    document.getElementById("currentStreamLabel").textContent = "Direct Message";
    document.getElementById("currentTopicLabel").textContent = topic;
    document.getElementById("composerInput").placeholder = `Direct message ${topic}… (Shift+Enter for new line)`;
  } else {
    document.getElementById("currentStreamLabel").textContent = `#${stream}`;
    document.getElementById("currentTopicLabel").textContent = topic;
    document.getElementById("composerInput").placeholder = `Message #${stream} > ${topic}… (@ to mention, Shift+Enter for new line)`;
  }

  const btnAuditHeader = document.getElementById("btnTriggerRuleAudit");
  if (btnAuditHeader) {
    btnAuditHeader.style.display = (stream === "detections") ? "inline-flex" : "none";
  }

  const btnMitreHeader = document.getElementById("btnTriggerMitreAudit");
  if (btnMitreHeader) {
    btnMitreHeader.style.display = (stream === "threat_intel" || stream === "detections") ? "inline-flex" : "none";
  }

  renderStreams();
  renderDirectMessages();
  await loadMessages(stream, topic);
  scrollToBottom();
}

// While a list has nothing to show, keep its load error (and Retry) on screen.
// Other code re-renders the sidebar on every topic switch / unread change.
function keepLoadError(container, items) {
  return (!Array.isArray(items) || items.length === 0) && !!container.querySelector(".load-error");
}

function renderStreams() {
  const container = document.getElementById("streamsList");
  if (!container) return;
  if (keepLoadError(container, state.streams)) return;
  const focusKey = focusedKeyWithin(container);
  container.innerHTML = "";

  state.streams.forEach((s) => {
    const isActive = s.id === state.activeStream;
    const streamEl = document.createElement("div");
    streamEl.className = `stream-item ${isActive ? "active" : ""}`;

    const headerEl = document.createElement("div");
    headerEl.className = "stream-header";
    headerEl.setAttribute("role", "button");
    headerEl.tabIndex = 0;
    headerEl.dataset.focusKey = `stream:${s.id}`;
    if (isActive) headerEl.setAttribute("aria-current", "true");
    const streamUnread = isActive ? 0 : unreadForStream(s.id);
    headerEl.innerHTML = `
      <span># ${escapeHtml(s.name)}</span>
      <span class="stream-header-badges">
        ${unreadBadgeHtml(streamUnread)}
        <span class="stream-badge" title="Topics">${s.topics ? s.topics.length : 0}</span>
      </span>
    `;

    headerEl.addEventListener("click", () => {
      const defaultTopic = s.topics && s.topics.length > 0 ? s.topics[0].name : "general";
      switchTopic(s.id, defaultTopic);
    });

    // Topic children
    const topicsEl = document.createElement("div");
    topicsEl.className = "topic-list";

    if (s.topics) {
      s.topics.forEach((t) => {
        const isTopicActive = isActive && t.name === state.activeTopic;
        const topicEl = document.createElement("div");
        const topicUnread = unreadFor(s.id, t.name);
        topicEl.className = `topic-item ${isTopicActive ? "active" : ""} ${topicUnread ? "has-unread" : ""}`;
        topicEl.setAttribute("role", "button");
        topicEl.tabIndex = 0;
        topicEl.dataset.focusKey = `topic:${s.id}/${t.name}`;
        if (isTopicActive) topicEl.setAttribute("aria-current", "true");
        topicEl.innerHTML = `
          <span>${escapeHtml(t.name)}</span>
          ${topicUnread
            ? unreadBadgeHtml(topicUnread)
            : (t.message_count > 0 ? `<span class="topic-count" title="Messages">${t.message_count}</span>` : "")}
        `;
        topicEl.addEventListener("click", (e) => {
          e.stopPropagation();
          switchTopic(s.id, t.name);
        });
        topicsEl.appendChild(topicEl);
      });
    }

    streamEl.appendChild(headerEl);
    streamEl.appendChild(topicsEl);
    container.appendChild(streamEl);
  });
  restoreFocusKey(container, focusKey);
}

// Re-renders replace sidebar rows; keep keyboard focus on the same logical row.
function focusedKeyWithin(container) {
  const el = document.activeElement;
  return el && container.contains(el) && el.dataset ? el.dataset.focusKey || null : null;
}
function restoreFocusKey(container, key) {
  if (!key) return;
  const target = Array.from(container.querySelectorAll("[data-focus-key]")).find((el) => el.dataset.focusKey === key);
  if (target) target.focus();
}

let dmSearchQuery = "";

function renderDirectMessages() {
  const container = document.getElementById("dmList");
  if (!container) return;
  if (keepLoadError(container, state.agents)) return;
  const focusKey = focusedKeyWithin(container);
  container.innerHTML = "";

  const query = (dmSearchQuery || "").trim().toLowerCase();
  const countBadge = document.getElementById("dmCountBadge");

  const totalCount = Array.isArray(state.agents) ? state.agents.length : 0;
  const filtered = (state.agents || []).filter((a) => {
    if (!query) return true;
    const handle = (a.handle || "").toLowerCase();
    const name = (a.name || "").toLowerCase();
    const role = (a.role || "").toLowerCase();
    const desc = (a.description || "").toLowerCase();
    const subsystem = (a.subsystem || "").toLowerCase();
    const tools = (a.capabilities || []).some((c) => c.toLowerCase().includes(query));
    return (
      handle.includes(query) ||
      name.includes(query) ||
      role.includes(query) ||
      desc.includes(query) ||
      subsystem.includes(query) ||
      tools
    );
  });

  if (countBadge) {
    countBadge.textContent = query ? `${filtered.length}/${totalCount}` : `${totalCount}`;
  }

  if (filtered.length === 0) {
    const emptyRow = document.createElement("div");
    emptyRow.style.padding = "12px 8px";
    emptyRow.style.textAlign = "center";
    emptyRow.style.fontSize = "11.5px";
    emptyRow.style.color = "var(--text-dim)";
    emptyRow.innerHTML = `
      <div>No agents matching "<strong>${escapeHtml(query)}</strong>"</div>
      <button id="dmResetSearchBtn" style="margin-top:6px; background:none; border:none; color:var(--text-accent); font-size:11px; cursor:pointer; text-decoration:underline;">Clear filter</button>
    `;
    container.appendChild(emptyRow);
    const resetBtn = document.getElementById("dmResetSearchBtn");
    if (resetBtn) {
      resetBtn.addEventListener("click", () => {
        const searchInput = document.getElementById("dmSearchInput");
        if (searchInput) searchInput.value = "";
        dmSearchQuery = "";
        const clearBtn = document.getElementById("dmClearFilterBtn");
        if (clearBtn) clearBtn.style.display = "none";
        renderDirectMessages();
      });
    }
    return;
  }

  filtered.forEach((a) => {
    const isDmActive = state.activeStream === "dm" && state.activeTopic === a.handle;
    const row = document.createElement("div");
    const dmUnread = unreadFor("dm", a.handle);
    row.className = `dm-item ${isDmActive ? "active" : ""} ${dmUnread ? "has-unread" : ""}`;
    row.setAttribute("role", "button");
    row.tabIndex = 0;
    row.dataset.focusKey = `dm:${a.handle}`;
    row.setAttribute("aria-label", `Direct message ${a.handle}${dmUnread ? `, ${dmUnread} unread` : ""}`);
    if (isDmActive) row.setAttribute("aria-current", "true");
    row.innerHTML = `
      <div class="dm-avatar-wrap">
        <div class="dm-avatar">${renderAvatar("agent", a.handle)}</div>
        <span class="dm-status-dot"></span>
      </div>
      <div class="dm-info-wrap" style="overflow:hidden; text-overflow:ellipsis; white-space:nowrap; flex:1;">
        <div class="dm-handle" title="${escapeHtml(a.role || a.name || a.handle)}">${escapeHtml(a.handle)}</div>
        ${query ? `<div style="font-size:11px; color:var(--text-dim); overflow:hidden; text-overflow:ellipsis;">${escapeHtml(a.role || a.name || "")}</div>` : ""}
      </div>
      ${unreadBadgeHtml(dmUnread)}
    `;
    row.addEventListener("click", () => {
      switchTopic("dm", a.handle);
    });
    container.appendChild(row);
  });
  restoreFocusKey(container, focusKey);
}

function renderAgents() {
  renderDirectMessages();
  const fleetTag = document.getElementById("fleetStatusTag");
  if (fleetTag && Array.isArray(state.agents) && state.agents.length > 0) {
    const n = state.agents.length;
    fleetTag.textContent = `${n} agent${n === 1 ? "" : "s"}`;
    fleetTag.title = `${n} registered agent${n === 1 ? "" : "s"} — open Agent Library`;
  }
  const gtFleet = document.getElementById("gtFleetOnline");
  if (gtFleet && Array.isArray(state.agents) && state.agents.length > 0) {
    gtFleet.textContent = `${state.agents.length} Agents Online`;
  }
}

function insertMention(handle) {
  const input = document.getElementById("composerInput");
  input.value = `${handle} ` + input.value;
  input.focus();
}

// --- Timeline Rendering ---
function renderTimeline() {
  const container = document.getElementById("messageTimeline");
  container.innerHTML = "";
  container._lastDayKey = null;
  resetNewMessagesPill();

  if (state.messages.length === 0) {
    container.innerHTML = renderEmptyTimeline(state.activeStream, state.activeTopic);
    return;
  }

  state.messages.forEach((m) => appendMessageToTimeline(m));
  scrollToBottom();
}

function renderAvatar(senderType, senderHandle) {
  const isAgent = senderType === "agent";
  if (isAgent) {
    return `
      <div class="msg-avatar avatar-agent" title="${escapeHtml(senderHandle)}">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
          <rect x="3" y="11" width="18" height="10" rx="2"></rect>
          <circle cx="12" cy="5" r="2"></circle>
          <path d="M12 7v4"></path>
          <line x1="8" y1="16" x2="8" y2="16"></line>
          <line x1="16" y1="16" x2="16" y2="16"></line>
        </svg>
      </div>`;
  }
  return `
    <div class="msg-avatar avatar-user" title="${escapeHtml(senderHandle)}">
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
        <path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"></path>
        <circle cx="12" cy="7" r="4"></circle>
      </svg>
    </div>`;
}

/**
 * Appends a message card and returns it.
 * opts.live: arrived via SSE -> follow only if reader is at the bottom, else bump the "new messages" pill.
 * opts.forceScroll: always scroll to the new card (e.g. the operator's own send).
 */
function appendMessageToTimeline(msg, opts = {}) {
  const container = document.getElementById("messageTimeline");
  const existing = findMessageCard(msg.id);
  if (existing) return existing;

  const wasNearBottom = isNearBottom(container);
  const card = document.createElement("div");
  card.className = "message-card";
  if (msg.id && !String(msg.id).startsWith("temp-")) card.dataset.id = msg.id;

  const isAgent = msg.sender_type === "agent";
  const avatarHtml = renderAvatar(msg.sender_type, msg.sender_handle);
  const created = new Date(msg.created_at);
  const validDate = !isNaN(created.getTime());
  const timeFormatted = validDate ? created.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }) : "";
  const timeFull = validDate ? created.toLocaleString([], { dateStyle: "full", timeStyle: "short" }) : "";

  const dayKey = validDate ? localDayKey(created) : null;
  if (dayKey) card.dataset.day = dayKey;
  if (dayKey && container._lastDayKey !== dayKey) {
    const sep = document.createElement("div");
    sep.className = "day-separator";
    sep.setAttribute("role", "separator");
    sep.innerHTML = `<span>${escapeHtml(formatDayLabel(created))}</span>`;
    insertIntoTimeline(container, sep);
    container._lastDayKey = dayKey;
  }

  let widgetHtml = "";
  if (msg.widget && msg.widget.type === "hitl_proposal_card") {
    widgetHtml = renderProposalWidget(msg.widget);
  } else if (msg.widget && msg.widget.type === "logjammer_replay_card") {
    widgetHtml = renderReplayWidget(msg.widget);
  } else if (msg.widget && msg.widget.type === "identity_governance_card") {
    widgetHtml = renderIdentityWidget(msg.widget);
  } else if (msg.widget && msg.widget.type === "decay_audit_card") {
    widgetHtml = renderDecayAuditWidget(msg.widget);
  } else if (msg.widget && msg.widget.type === "decay_sync_card") {
    widgetHtml = renderDecaySyncWidget(msg.widget);
  } else if (msg.widget && msg.widget.type === "noise_tuning_card") {
    widgetHtml = renderNoiseTuningWidget(msg.widget);
  } else if (msg.widget && msg.widget.type === "feed_health_card") {
    widgetHtml = renderFeedHealthWidget(msg.widget);
  } else if (msg.widget && msg.widget.type === "parser_health_card") {
    widgetHtml = renderParserHealthWidget(msg.widget);
  } else if (msg.widget && msg.widget.type === "unparsed_diagnostic_card") {
    widgetHtml = renderUnparsedDiagnosticWidget(msg.widget);
  } else if (msg.widget && (msg.widget.type === "data_table" || msg.widget.type === "sql_query_card")) {
    widgetHtml = renderDataTableWidget(msg.widget);
  } else if (msg.widget && msg.widget.type === "gcp_telemetry_card") {
    widgetHtml = renderGcpTelemetryWidget(msg.widget);
  } else if (msg.widget && msg.widget.type === "tenant_drift_card") {
    widgetHtml = renderTenantDriftWidget(msg.widget);
  } else if (msg.widget && msg.widget.type === "playbook_health_card") {
    widgetHtml = renderPlaybookHealthWidget(msg.widget);
  } else if (msg.widget && msg.widget.type === "timestamp_integrity_card") {
    widgetHtml = renderTimestampIntegrityWidget(msg.widget);
  } else if (msg.widget && msg.widget.type === "rule_conflict_card") {
    widgetHtml = renderRuleConflictWidget(msg.widget);
  } else if (msg.widget && msg.widget.type === "rule_conflict_batch_card") {
    widgetHtml = renderRuleConflictBatchWidget(msg.widget);
  } else if (msg.widget && msg.widget.type === "rule_audit_card") {
    widgetHtml = renderRuleAuditCard(msg.widget);
  } else if (msg.widget && msg.widget.type === "finops_cost_card") {
    widgetHtml = renderFinopsCostCard(msg.widget);
  } else if (msg.widget && msg.widget.type === "raw_log_search_card") {
    widgetHtml = renderRawLogSearchCard(msg.widget);
  } else if (msg.widget && msg.widget.type === "mitre_coverage_card") {
    widgetHtml = renderMitreCoverageCard(msg.widget);
  }

  card.innerHTML = `
    ${avatarHtml}
    <div class="msg-body">
      <div class="msg-header">
        <span class="msg-handle">${escapeHtml(msg.sender_handle)}</span>
        ${isAgent ? `<span class="msg-role-tag">AGENT</span>` : `<span class="msg-role-tag" style="background:var(--c-neutral-bg); color:var(--text-muted)">USER</span>`}
        <time class="msg-timestamp" datetime="${escapeHtml(msg.created_at || "")}" title="${escapeHtml(timeFull)}">${timeFormatted}</time>
      </div>
      <div class="msg-content">${formatMarkdown(msg.content)}</div>
      ${widgetHtml}
    </div>
  `;

  // Attach interactive widget button events if present
  if (msg.widget && msg.widget.type === "hitl_proposal_card" && msg.widget.status === "OPEN") {
    const approveBtn = card.querySelector(".btn-approve");
    const rejectBtn = card.querySelector(".btn-reject");

    if (approveBtn) {
      approveBtn.addEventListener("click", () => handleApproveProposal(msg.widget.proposal_id));
    }
    if (rejectBtn) {
      rejectBtn.addEventListener("click", () => handleRejectProposal(msg.widget.proposal_id));
    }
  }

  insertIntoTimeline(container, card);
  if (opts.forceScroll || (opts.live && wasNearBottom)) {
    scrollToBottom();
  } else if (opts.live) {
    bumpNewMessagesPill();
  }
  return card;
}

// Keep the agent status card last in the timeline.
function insertIntoTimeline(container, el) {
  const statusCard = document.getElementById("agentStatusCard");
  if (statusCard && statusCard.parentNode === container) {
    container.insertBefore(el, statusCard);
  } else {
    container.appendChild(el);
  }
}

function localDayKey(d) {
  return `${d.getFullYear()}-${d.getMonth() + 1}-${d.getDate()}`;
}

function formatDayLabel(d) {
  const startOf = (x) => new Date(x.getFullYear(), x.getMonth(), x.getDate()).getTime();
  const now = new Date();
  const diffDays = Math.round((startOf(now) - startOf(d)) / 86400000);
  if (diffDays === 0) return "Today";
  if (diffDays === 1) return "Yesterday";
  const opts = { weekday: "long", month: "short", day: "numeric" };
  if (d.getFullYear() !== now.getFullYear()) opts.year = "numeric";
  return d.toLocaleDateString([], opts);
}

// Remove a message card; drop its day separator if it's now empty.
function removeMessageCard(card) {
  const container = card.parentNode;
  if (!container) return;
  const kids = container.children;
  const idx = Array.prototype.indexOf.call(kids, card);
  const prev = idx > 0 ? kids[idx - 1] : null;
  card.remove();
  const next = container.children[idx] || null; // element that took the card's place
  if (prev && prev.classList.contains("day-separator") && !(next && next.classList.contains("message-card"))) {
    prev.remove();
  }
  let lastDay = null;
  for (let i = container.children.length - 1; i >= 0; i--) {
    const el = container.children[i];
    if (el.classList.contains("message-card") && el.dataset.day) { lastDay = el.dataset.day; break; }
  }
  container._lastDayKey = lastDay;
}

function renderProposalWidget(widget) {
  const status = widget.status || "OPEN";
  const statusClass = `status-${status.toLowerCase()}`;
  const badgeClass = `badge-${status.toLowerCase()}`;
  const actionType = widget.action_type || "PROPOSAL";
  const riskLevel = widget.risk_level || "MEDIUM";
  const proposalId = widget.proposal_id || "";

  let diffHtml = "";
  if (widget.proposed_diff) {
    diffHtml = `
      <div style="font-size:11px; font-weight:600; color:var(--text-muted); margin-bottom:3px; text-transform:uppercase; letter-spacing:0.5px;">Proposed Mutation Diff</div>
      <div class="diff-container">${formatUnifiedDiff(widget.proposed_diff)}</div>
    `;
  }

  let preflightHtml = "";
  if (widget.preflight) {
    const synOk = !!widget.preflight.syntax_verified;
    const repOk = !!widget.preflight.replay_verified;
    preflightHtml = `
      <div class="preflight-box">
        <div style="font-weight:700; font-size:11.5px; margin-bottom:4px; display:flex; justify-content:space-between; align-items:center;">
          <span>Empirical Pre-Flight Proof</span>
          <span style="font-size:11px; color:${synOk && repOk ? 'var(--c-ok)' : 'var(--c-warn)'};">${synOk && repOk ? 'VERIFIED' : 'PENDING EMPIRICAL'}</span>
        </div>
        <div class="kpi-grid" style="grid-template-columns: 1fr 1fr; margin-bottom:0;">
          <div class="kpi-card" style="padding:4px 6px; text-align:left;">
            <div class="kpi-lbl">Syntax Compiler</div>
            <div style="font-size:11.5px; font-weight:600; color:${synOk ? 'var(--c-ok)' : 'var(--c-danger)'};">${synOk ? '✅ PASSED (0 errors)' : '❌ FAILED'}</div>
          </div>
          <div class="kpi-card" style="padding:4px 6px; text-align:left;">
            <div class="kpi-lbl">Empirical Replay</div>
            <div style="font-size:11.5px; font-weight:600; color:${repOk ? 'var(--c-ok)' : 'var(--text-dim)'};">${repOk ? '✅ ' + (widget.preflight.replay_summary || 'Verified') : '⏳ Awaiting Log Replay'}</div>
          </div>
        </div>
      </div>
    `;
  }

  let actionsHtml = "";
  if (status === "OPEN") {
    actionsHtml = `
      <div class="prop-action-bar">
        <button class="btn-approve" data-id="${proposalId}">
          <span>${ICONS.zap}</span> Approve & Apply Mutation
        </button>
        <button class="btn-reject" data-id="${proposalId}">Reject</button>
      </div>
    `;
  } else if (status === "MERGED") {
    actionsHtml = `
      <div style="font-size:11.5px; color:var(--accent-green); font-weight:600; margin-top:6px; display:flex; align-items:center; gap:5px;">
        <span>${ICONS.check}</span> Live Mutation Merged (${widget.commit_hash ? widget.commit_hash.slice(0, 7) : "HEAD"})
      </div>
    `;
  } else if (status === "REJECTED") {
    actionsHtml = `
      <div style="font-size:11.5px; color:var(--accent-rose); font-weight:600; margin-top:6px; display:flex; align-items:center; gap:5px;">
        <span>${ICONS.cross}</span> Rejected (${escapeHtml(widget.rejection_reason || "Declined by operator")})
      </div>
    `;
  }

  return `
    <div class="proposal-card ${statusClass}">
      <div class="prop-meta-bar">
        <span class="badge ${badgeClass}">${status}</span>
        <span class="badge badge-risk">${actionType}</span>
        <span class="badge badge-risk">RISK: ${riskLevel}</span>
        <span style="font-family:var(--font-mono); font-size:11px; color:var(--text-dim); margin-left:auto;">${proposalId}</span>
      </div>
      <div class="prop-title">${escapeHtml(widget.title || "Change Proposal")}</div>
      ${widget.rationale ? `<div class="prop-rationale">${escapeHtml(widget.rationale)}</div>` : ""}
      ${preflightHtml}
      ${diffHtml}
      ${actionsHtml}
    </div>
  `;
}

function renderReplayWidget(widget) {
  const playbooks = Array.isArray(widget.log_types)
    ? widget.log_types
    : (widget.log_types ? [widget.log_types] : ["GENERIC"]);
  const status = widget.status || "VERIFIED";
  const eventCount = widget.event_count || 0;
  const tenantId = widget.target_tenant ? widget.target_tenant.slice(0, 8) + "..." : "Default";
  const targetRule = widget.target_resource_id || widget.proposal_id || "N/A";

  const playbookTags = playbooks
    .map(p => `<span class="badge-tag">${escapeHtml(p)}</span>`)
    .join(" ");

  return `
    <div class="proposal-card status-open" style="border-left: 3px solid var(--accent-blue); margin-top: 8px;">
      <div class="prop-meta-bar">
        <span class="badge" style="background:var(--c-info-bg); color:var(--c-info);">EMPIRICAL REPLAY</span>
        <span class="badge" style="background:var(--c-ok-bg); color:var(--c-ok);">${status}</span>
        <span style="font-family:var(--font-mono); font-size:11px; color:var(--text-dim); margin-left:auto;">rule: ${escapeHtml(targetRule)}</span>
      </div>
      <div class="prop-title" style="font-size:13px; margin-bottom:4px;">${escapeHtml(widget.scenario_title || "Attack Vector Simulation")}</div>

      <!-- High Density KPI Grid -->
      <div class="kpi-grid" style="grid-template-columns: repeat(4, 1fr);">
        <div class="kpi-card">
          <div class="kpi-val" style="color:var(--c-ok);">${eventCount}</div>
          <div class="kpi-lbl">Events Streamed</div>
        </div>
        <div class="kpi-card">
          <div class="kpi-val" style="font-size:12px; font-family:var(--font-mono);">${tenantId}</div>
          <div class="kpi-lbl">Target Tenant</div>
        </div>
        <div class="kpi-card">
          <div class="kpi-val" style="color:var(--c-info); font-size:12px;">SecOpsSink</div>
          <div class="kpi-lbl">Live Ingestion</div>
        </div>
        <div class="kpi-card">
          <div class="kpi-val" style="color:var(--c-violet); font-size:12px;">0 Errors</div>
          <div class="kpi-lbl">Compilation</div>
        </div>
      </div>

      <!-- Log Types & Playbooks -->
      <div style="margin: 6px 0 4px; display:flex; align-items:center; gap:5px; flex-wrap:wrap;">
        <span style="font-size:11px; color:var(--text-dim); text-transform:uppercase; font-weight:600;">Playbooks:</span>
        ${playbookTags}
      </div>

      ${widget.summary ? `
      <div style="background:var(--surface-inset-strong); border:1px solid var(--border-color); border-radius:4px; padding:6px 8px; font-family:var(--font-mono); font-size:11px; color:var(--c-info); margin-top:6px;">
        <span style="color:var(--c-ok);">&gt;</span> ${escapeHtml(widget.summary)}
      </div>` : ""}
    </div>
  `;
}

function renderIdentityWidget(widget) {
  const hasDrift = !!widget.has_drift;
  const driftColor = hasDrift ? "var(--accent-amber)" : "var(--accent-green)";
  const driftBadgeBg = hasDrift ? "var(--c-warn-bg)" : "var(--c-ok-bg)";
  const driftBadgeText = hasDrift ? "var(--c-warn)" : "var(--c-ok)";
  const driftStatus = hasDrift ? "DRIFT DETECTED" : "BASELINE STABLE";
  const projectId = widget.project_id || "sdl-preview-americas";

  let driftDetails = "";
  if (hasDrift) {
    let diffRows = [];
    if (widget.members_added && widget.members_added.length > 0) {
      widget.members_added.forEach(m => {
        diffRows.push(`<tr style="background:var(--c-danger-faint);"><td style="color:var(--c-danger); font-weight:700;">➕ ADDED</td><td><code>${escapeHtml(m.role || "")}</code></td><td>${escapeHtml(m.member || "")}</td></tr>`);
      });
    }
    if (widget.members_removed && widget.members_removed.length > 0) {
      widget.members_removed.forEach(m => {
        diffRows.push(`<tr style="background:var(--c-info-faint);"><td style="color:var(--c-info); font-weight:700;">➖ REMOVED</td><td><code>${escapeHtml(m.role || "")}</code></td><td>${escapeHtml(m.member || "")}</td></tr>`);
      });
    }
    if (widget.custom_roles_added && widget.custom_roles_added.length > 0) {
      widget.custom_roles_added.forEach(r => {
        diffRows.push(`<tr style="background:var(--c-danger-faint);"><td style="color:var(--c-danger); font-weight:700;">➕ ROLE</td><td><code>${escapeHtml(r)}</code></td><td>Custom Role with chronicle.*</td></tr>`);
      });
    }
    if (widget.custom_roles_removed && widget.custom_roles_removed.length > 0) {
      widget.custom_roles_removed.forEach(r => {
        diffRows.push(`<tr style="background:var(--c-info-faint);"><td style="color:var(--c-info); font-weight:700;">➖ ROLE</td><td><code>${escapeHtml(r)}</code></td><td>Custom Role Deleted</td></tr>`);
      });
    }

    if (diffRows.length > 0) {
      driftDetails = `
        <div style="margin-top:6px;">
          <table style="width:100%; font-size:11px; margin:4px 0;">
            <thead><tr><th style="padding:4px 8px;">Action</th><th style="padding:4px 8px;">Role</th><th style="padding:4px 8px;">Principal</th></tr></thead>
            <tbody>${diffRows.join("")}</tbody>
          </table>
        </div>
      `;
    }
  } else {
    driftDetails = `
      <div style="margin-top:6px; padding:5px 8px; background:var(--c-ok-faint); border-radius:4px; font-size:11.5px; color:var(--c-ok); display:flex; align-items:center; gap:6px;">
        <span>✅</span> Verified: 31 Chronicle bindings &amp; 29 custom roles match baseline in Firestore.
      </div>
    `;
  }

  return `
    <div class="proposal-card status-open" style="border-left: 3px solid ${driftColor}; margin-top: 8px;">
      <div class="prop-meta-bar">
        <span class="badge" style="background:var(--c-violet-bg); color:var(--c-violet);">IAM GOVERNANCE</span>
        <span class="badge" style="background:${driftBadgeBg}; color:${driftBadgeText};">${driftStatus}</span>
        <span style="font-family:var(--font-mono); font-size:11px; color:var(--text-dim); margin-left:auto;">project: ${escapeHtml(projectId)}</span>
      </div>
      <div class="prop-title" style="font-size:13px; margin-bottom:4px;">Chronicle IAM Permissions &amp; Custom Roles Audit</div>

      <!-- 5-Column High-Density KPI Grid -->
      <div class="kpi-grid" style="grid-template-columns: repeat(5, 1fr);">
        <div class="kpi-card">
          <div class="kpi-val" style="color:var(--c-info);">${widget.users_count || 0}</div>
          <div class="kpi-lbl">Users</div>
        </div>
        <div class="kpi-card">
          <div class="kpi-val" style="color:var(--c-indigo);">${widget.groups_count || 0}</div>
          <div class="kpi-lbl">Groups</div>
        </div>
        <div class="kpi-card">
          <div class="kpi-val" style="color:var(--c-ok);">${widget.service_accounts_count || 0}</div>
          <div class="kpi-lbl">Svc Accounts</div>
        </div>
        <div class="kpi-card">
          <div class="kpi-val" style="color:var(--c-violet);">${widget.workforce_pools_count || 0}</div>
          <div class="kpi-lbl">Workforce</div>
        </div>
        <div class="kpi-card">
          <div class="kpi-val" style="color:var(--c-warn);">${widget.custom_roles_count || 0}</div>
          <div class="kpi-lbl">Custom Roles</div>
        </div>
      </div>

      ${driftDetails}
    </div>
  `;
}

function renderDecayAuditWidget(widget) {
  const dps = widget.dps_score || 0;
  let dpsClass = "dps-low";
  let dpsLabel = "HEALTHY";
  if (dps >= 70) {
    dpsClass = "dps-high";
    dpsLabel = "CRITICAL DECAY";
  } else if (dps >= 40) {
    dpsClass = "dps-med";
    dpsLabel = "MODERATE DECAY";
  }

  const flags = Array.isArray(widget.decay_flags) ? widget.decay_flags : [];
  const flagsHtml = flags.map(f => `<span class="decay-flag-tag tag-${f.toLowerCase()}">${escapeHtml(f)}</span>`).join(" ");

  const isLive = !!widget.is_live;
  const liveBadge = isLive
    ? `<span class="badge" style="background:var(--c-ok-bg); color:var(--c-ok); border:1px solid var(--c-ok-bd);">🟢 LIVE (ENABLED)</span>`
    : `<span class="badge" style="background:var(--c-neutral-bg); color:var(--text-muted); border:1px solid var(--c-neutral-bd);">⚪ DISABLED</span>`;

  let diagnosticsHtml = "";
  if (widget.compiler_errors && widget.compiler_errors.length > 0) {
    diagnosticsHtml += `
      <div style="margin-top:8px; padding:8px 10px; background:var(--c-danger-faint); border:1px solid var(--c-danger-bd); border-radius:4px; font-size:11.5px; color:var(--c-danger);">
        <div style="font-weight:700; margin-bottom:2px;">⚠️ YARA-L Compilation Diagnostics:</div>
        <div>${escapeHtml(widget.compiler_errors.join("; "))}</div>
      </div>
    `;
  }
  if (widget.unpopulated_fields && widget.unpopulated_fields.length > 0) {
    diagnosticsHtml += `
      <div style="margin-top:8px; padding:8px 10px; background:var(--c-warn-faint); border:1px solid var(--c-warn-bd); border-radius:4px; font-size:11.5px; color:var(--c-warn);">
        <div style="font-weight:700; margin-bottom:2px;">⚠️ Unpopulated UDM Fields (0 events observed in 30d):</div>
        <div style="font-family:var(--font-mono); font-size:11px;">${escapeHtml(widget.unpopulated_fields.join(", "))}</div>
      </div>
    `;
  }

  return `
    <div class="proposal-card status-open" style="border-left: 3px solid ${dps >= 70 ? 'var(--c-danger)' : (dps >= 40 ? 'var(--c-warn)' : 'var(--c-ok)')};">
      <div class="prop-header" style="display:flex; justify-content:space-between; align-items:center; margin-bottom:6px;">
        <div style="display:flex; align-items:center; gap:8px;">
          <span class="badge" style="background:var(--c-indigo-bg); color:var(--c-indigo); border:1px solid var(--c-indigo-bd);">RULE DECAY AUDIT</span>
          ${liveBadge}
        </div>
        <div class="dps-badge ${dpsClass}">
          <span class="dps-number">${dps}</span>
          <span class="dps-text">/ 100 DPS &bull; ${dpsLabel}</span>
        </div>
      </div>

      <div class="prop-title" style="font-size:13.5px; font-weight:700; margin-bottom:3px;">
        ${escapeHtml(widget.rule_name || widget.rule_id)}
      </div>
      <div style="font-family:var(--font-mono); font-size:11px; color:var(--text-dim); margin-bottom:8px;">
        ID: ${escapeHtml(widget.rule_id)}
      </div>

      <div class="kpi-grid" style="grid-template-columns: repeat(4, 1fr); margin: 8px 0;">
        <div class="kpi-card">
          <div class="kpi-val" style="color:${dps >= 70 ? 'var(--c-danger)' : (dps >= 40 ? 'var(--c-warn)' : 'var(--c-ok)')};">${dps}</div>
          <div class="kpi-lbl">DPS Score</div>
        </div>
        <div class="kpi-card">
          <div class="kpi-val" style="color:var(--c-info);">${widget.detection_count_90d || 0}</div>
          <div class="kpi-lbl">90d Detections</div>
        </div>
        <div class="kpi-card">
          <div class="kpi-val" style="color:var(--c-warn);">${widget.days_stale || 0}d</div>
          <div class="kpi-lbl">Staleness</div>
        </div>
        <div class="kpi-card">
          <div class="kpi-val" style="color:${(widget.unpopulated_fields && widget.unpopulated_fields.length > 0) ? 'var(--c-danger)' : 'var(--c-ok)'};">
            ${(widget.unpopulated_fields ? widget.unpopulated_fields.length : 0)}
          </div>
          <div class="kpi-lbl">Unpop Fields</div>
        </div>
      </div>

      <div style="display:flex; flex-wrap:wrap; gap:5px; margin: 6px 0;">
        ${flagsHtml}
      </div>

      ${diagnosticsHtml}

      <div style="margin-top:10px; display:flex; justify-content:space-between; align-items:center; background:var(--surface-inset); padding:8px 10px; border-radius:6px;">
        <div style="font-size:12px;">
          <strong style="color:var(--text-main);">Action:</strong>
          <span style="color:var(--c-info); font-weight:600; margin-left:4px;">${escapeHtml(widget.recommendation || "INVESTIGATE")}</span>
        </div>
        <div style="display:flex; gap:6px;">
          <button class="btn-approve" style="background:var(--c-indigo-solid); padding:4px 10px; font-size:11px;" ${act("promptRemediateRule", widget.rule_id)}>
            ✨ Ask @DecayAgent to Remediate
          </button>
        </div>
      </div>
    </div>
  `;
}

function renderDecaySyncWidget(widget) {
  const avgDps = widget.average_dps || 0;
  const topCandidates = widget.top_candidates || [];

  let rowsHtml = "";
  topCandidates.forEach((c) => {
    const dps = c.dps_score || 0;
    const dpsColor = dps >= 70 ? 'var(--c-danger)' : (dps >= 40 ? 'var(--c-warn)' : 'var(--c-ok)');
    rowsHtml += `
      <tr style="border-bottom:1px solid var(--border-color); font-size:11.5px;">
        <td style="padding:6px 8px;">
          <div style="font-weight:600; color:var(--text-bright);">${escapeHtml(c.rule_name || c.rule_id)}</div>
          ${c.rule_id && c.rule_id !== c.rule_name ? `<div style="font-size:11px; font-weight:400; color:var(--text-dim); font-family:monospace; margin-top:2px;">${escapeHtml(c.rule_id)}</div>` : ''}
        </td>
        <td style="padding:6px 8px; text-align:center;">
          <span style="font-weight:700; color:${dpsColor}; background:var(--surface-inset); padding:2px 6px; border-radius:4px;">${dps}</span>
        </td>
        <td style="padding:6px 8px; text-align:center;">${c.detection_count_90d || 0}</td>
        <td style="padding:6px 8px; text-align:center;" title="${c.is_live ? 'Live in production' : 'Not live / disabled'}">
          <span style="display:inline-block; width:9px; height:9px; border-radius:50%; background-color:${c.is_live ? 'var(--c-ok-solid)' : 'var(--c-neutral-solid)'}; box-shadow:${c.is_live ? '0 0 6px var(--c-ok-bd)' : 'none'}; vertical-align:middle;"></span>
        </td>
        <td style="padding:6px 8px; text-align:right;">
          <button style="background:var(--c-indigo-bg); border:1px solid var(--c-indigo); color:var(--c-indigo); border-radius:4px; padding:2px 8px; font-size:11px; cursor:pointer;" ${act("auditRuleInChat", c.rule_id)}>
            Audit
          </button>
        </td>
      </tr>
    `;
  });

  return `
    <div class="proposal-card status-open" style="border-left: 3px solid var(--c-indigo);">
      <div class="prop-header" style="display:flex; justify-content:space-between; align-items:center; margin-bottom:6px;">
        <span class="badge" style="background:var(--c-indigo-bg); color:var(--c-indigo); border:1px solid var(--c-indigo-bd);">
          SYNCHRONIZATION COMPLETED
        </span>
        <span style="font-size:11px; color:var(--text-dim);">${new Date(widget.timestamp || Date.now()).toLocaleTimeString()}</span>
      </div>

      <div class="prop-title" style="font-size:13.5px; font-weight:700; margin-bottom:6px;">
        Tenant Rule Inventory 90-Day Telemetry Synchronization
      </div>

      <div class="kpi-grid" style="grid-template-columns: repeat(5, 1fr); margin: 8px 0;">
        <div class="kpi-card">
          <div class="kpi-val" style="color:var(--c-info);">${widget.total_rules || 0}</div>
          <div class="kpi-lbl">Audited</div>
        </div>
        <div class="kpi-card">
          <div class="kpi-val" style="color:var(--c-danger);">${widget.broken_count || 0}</div>
          <div class="kpi-lbl">Broken</div>
        </div>
        <div class="kpi-card">
          <div class="kpi-val" style="color:var(--c-warn);">${widget.silent_count || 0}</div>
          <div class="kpi-lbl">Silent (0 det)</div>
        </div>
        <div class="kpi-card">
          <div class="kpi-val" style="color:var(--c-violet);">${widget.stale_count || 0}</div>
          <div class="kpi-lbl">Stale (&gt;90d)</div>
        </div>
        <div class="kpi-card">
          <div class="kpi-val" style="color:${avgDps >= 50 ? 'var(--c-danger)' : 'var(--c-ok)'};">${avgDps}</div>
          <div class="kpi-lbl">Avg DPS</div>
        </div>
      </div>

      <div style="margin-top:10px;">
        <div style="font-size:11.5px; font-weight:700; color:var(--text-muted); margin-bottom:4px; text-transform:uppercase;">
          Top Priority Decay Candidates
        </div>
        <table style="width:100%; border-collapse:collapse; background:var(--surface-inset-strong); border-radius:6px; overflow:hidden;">
          <thead>
            <tr style="background:var(--surface-inset-strong); font-size:11px; color:var(--text-muted);">
              <th style="padding:4px 8px; text-align:left;">Rule</th>
              <th style="padding:4px 8px; text-align:center;">DPS</th>
              <th style="padding:4px 8px; text-align:center;">90d Dets</th>
              <th style="padding:4px 8px; text-align:center;">Live</th>
              <th style="padding:4px 8px; text-align:right;">Action</th>
            </tr>
          </thead>
          <tbody>
            ${rowsHtml}
          </tbody>
        </table>
      </div>
    </div>
  `;
}

function promptRemediateRule(ruleId) {
  const input = document.getElementById("composerInput");
  input.value = `@detection-decay-agent remediate rule ${ruleId} and submit proposal`;
  input.focus();
}

function auditRuleInChat(ruleId) {
  const input = document.getElementById("composerInput");
  input.value = `@detection-decay-agent audit rule ${ruleId}`;
  handleSendMessage();
}

function renderNoiseTuningWidget(widget) {
  const status = widget.status || "TUNING_PROPOSED";
  const ruleId = widget.rule_id || "";
  const ruleName = widget.rule_name || ruleId;
  const ruleType = widget.rule_type || (ruleId.startsWith("ur_") ? "Google Curated Rule" : "Customer Rule");
  const baseline = widget.unsuppressed_trigger_count || 0;
  const suppressed = widget.projected_suppressed_count || 0;
  const pct = widget.noise_reduction_pct || 0.0;
  const preserved = widget.preserved_real_alerts || 0;
  const compilerOk = !!widget.compiler_verified;
  const factors = widget.multi_factor_factors || {};
  const guardrailsPassed = !!widget.multi_factor_guardrails_passed;
  const guardrailNotes = Array.isArray(widget.guardrail_notes) ? widget.guardrail_notes : [];

  let statusBadge = "";
  let borderLeft = "var(--c-indigo)";
  if (status === "TUNING_PROPOSED") {
    statusBadge = `<span class="badge" style="background:var(--c-ok-bg); color:var(--c-ok); border:1px solid var(--c-ok-bd);">🟢 ${pct}% NOISE REDUCTION PROPOSAL</span>`;
    borderLeft = "var(--c-ok)";
  } else if (status === "NO_TUNING_NEEDED") {
    statusBadge = `<span class="badge" style="background:var(--c-neutral-bg); color:var(--text-dim); border:1px solid var(--c-neutral-bd);">⚪ DIVERSITY CHECK: NO TUNING NEEDED</span>`;
    borderLeft = "var(--c-neutral)";
  } else {
    statusBadge = `<span class="badge" style="background:var(--c-danger-bg); color:var(--c-danger); border:1px solid var(--c-danger-bd);">🛡️ BLINDING GUARD PREVENTED CUT</span>`;
    borderLeft = "var(--c-danger)";
  }

  let conjunctionHtml = "";
  if (Object.keys(factors).length > 0) {
    const factorBadges = Object.entries(factors).map(([k, v]) =>
      `<span style="background:var(--c-indigo-bg); color:var(--c-indigo); border:1px solid var(--c-indigo-bd); border-radius:4px; padding:2px 8px; font-size:11px; font-family:var(--font-mono);"><strong>${escapeHtml(k)}:</strong> ${escapeHtml(v)}</span>`
    ).join(" ");
    conjunctionHtml = `
      <div style="margin: 8px 0;">
        <div style="font-size:11px; font-weight:600; color:var(--text-muted); text-transform:uppercase; margin-bottom:4px;">Multi-Factor Exclusion Conjunction</div>
        <div style="display:flex; flex-wrap:wrap; gap:6px;">${factorBadges}</div>
      </div>
    `;
  }

  let distributionHtml = "";
  if (widget.entity_distribution) {
    let grouped = {};
    if (Array.isArray(widget.entity_distribution)) {
      widget.entity_distribution.forEach(it => {
        const dim = it.dimension || "entity";
        if (!grouped[dim]) grouped[dim] = [];
        grouped[dim].push(it);
      });
    } else if (typeof widget.entity_distribution === "object") {
      grouped = widget.entity_distribution;
    }

    let dimBlocks = [];
    for (const [dim, items] of Object.entries(grouped)) {
      if (Array.isArray(items) && items.length > 0) {
        const topItems = items.slice(0, 3).map(it => {
          const val = typeof it === "object" ? (it.value || JSON.stringify(it)) : String(it);
          const cnt = typeof it === "object" ? (it.count || 0) : 0;
          return `<div style="display:flex; justify-content:space-between; font-size:11px; font-family:var(--font-mono); padding:2px 0;">
            <span style="overflow:hidden; text-overflow:ellipsis; white-space:nowrap; max-width:80%; color:var(--text-muted);">${escapeHtml(val)}</span>
            <span style="color:var(--text-dim); font-weight:600;">${cnt.toLocaleString()}</span>
          </div>`;
        }).join("");
        dimBlocks.push(`
          <div style="background:var(--surface-inset-strong); padding:6px 8px; border-radius:4px; border:1px solid var(--border-color);">
            <div style="font-size:11px; font-weight:700; color:var(--text-muted); text-transform:uppercase; margin-bottom:3px;">${escapeHtml(dim)}</div>
            ${topItems}
          </div>
        `);
      }
    }
    if (dimBlocks.length > 0) {
      distributionHtml = `
        <div style="margin: 8px 0;">
          <div style="font-size:11px; font-weight:600; color:var(--text-muted); text-transform:uppercase; margin-bottom:4px;">Observed Entity Distribution (Sampled)</div>
          <div style="display:grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap:6px;">
            ${dimBlocks.join("")}
          </div>
        </div>
      `;
    }
  }

  let diffHtml = "";
  if (widget.unified_diff) {
    diffHtml = `
      <div style="margin-top:8px;">
        <div style="font-size:11px; font-weight:600; color:var(--text-muted); text-transform:uppercase; margin-bottom:3px;">Exclusion Patch Diff</div>
        <div class="diff-container">${formatUnifiedDiff(widget.unified_diff)}</div>
      </div>
    `;
  }

  let actionButtonsHtml = "";
  if (status === "TUNING_PROPOSED") {
    actionButtonsHtml = `
      <div style="margin-top:10px; display:flex; justify-content:space-between; align-items:center; background:var(--surface-inset); padding:8px 10px; border-radius:6px;">
        <div style="display:flex; align-items:center; gap:6px; font-size:11.5px; color:var(--c-ok); font-weight:600;">
          <span>${ICONS.shield || "🛡️"}</span> Multi-Factor Verified (Zero Blinding)
        </div>
        <div style="display:flex; gap:6px;">
          <button class="btn-approve" style="background:var(--c-ok-solid); padding:5px 12px; font-size:11.5px; font-weight:700;" ${act("deployTuningProposal", widget.rule_id, widget.rule_name || widget.rule_id)}>
            🚀 Approve & Deploy to Chronicle
          </button>
        </div>
      </div>
    `;
  } else {
    actionButtonsHtml = `
      <div style="margin-top:10px; display:flex; justify-content:space-between; align-items:center; background:var(--surface-inset); padding:8px 10px; border-radius:6px;">
        <div style="font-size:11.5px; color:var(--text-dim);">
          ${guardrailNotes.length > 0 ? escapeHtml(guardrailNotes.join("; ")) : "Rule has low trigger concentration or benign diversity"}
        </div>
        <div>
          <button class="btn-approve" style="background:var(--c-neutral-solid); padding:4px 10px; font-size:11px;" ${act("promptTuneRule", widget.rule_id)}>
            🔄 Re-Evaluate (10% Threshold)
          </button>
        </div>
      </div>
    `;
  }

  return `
    <div class="proposal-card status-open" style="border-left: 3px solid ${borderLeft};">
      <div class="prop-header" style="display:flex; justify-content:space-between; align-items:center; margin-bottom:6px;">
        <div style="display:flex; align-items:center; gap:8px;">
          <span class="badge" style="background:var(--c-indigo-bg); color:var(--c-indigo); border:1px solid var(--c-indigo-bd);">DETECTION TUNING</span>
          <span class="badge" style="background:var(--c-neutral-bg); color:var(--text-muted);">${escapeHtml(ruleType)}</span>
        </div>
        ${statusBadge}
      </div>

      <div class="prop-title" style="font-size:13.5px; font-weight:700; margin-bottom:3px;">
        ${escapeHtml(ruleName)}
      </div>
      <div style="font-family:var(--font-mono); font-size:11px; color:var(--text-dim); margin-bottom:8px;">
        Rule ID: ${escapeHtml(ruleId)}
      </div>

      <div class="kpi-grid" style="grid-template-columns: repeat(4, 1fr); margin: 8px 0;">
        <div class="kpi-card">
          <div class="kpi-val" style="color:var(--text-dim);">${baseline.toLocaleString()}</div>
          <div class="kpi-lbl">Baseline Triggers</div>
        </div>
        <div class="kpi-card">
          <div class="kpi-val" style="color:var(--c-ok);">${suppressed.toLocaleString()}</div>
          <div class="kpi-lbl">Suppressed</div>
        </div>
        <div class="kpi-card">
          <div class="kpi-val" style="color:${pct >= 20 ? 'var(--c-info)' : 'var(--text-dim)'};">${pct}%</div>
          <div class="kpi-lbl">Noise Reduction</div>
        </div>
        <div class="kpi-card">
          <div class="kpi-val" style="color:var(--c-warn);">${preserved.toLocaleString()}</div>
          <div class="kpi-lbl">Preserved Alerts</div>
        </div>
      </div>

      <div style="background:var(--surface-inset); padding:6px 10px; border-radius:4px; font-size:11.5px; display:flex; justify-content:space-between; margin:6px 0;">
        <span><strong>Chronicle Compiler:</strong> <span style="color:${compilerOk ? 'var(--c-ok)' : 'var(--c-danger)'}; font-weight:600;">${compilerOk ? '✅ Syntax & Logic Verified' : '❌ Syntax Diagnostic'}</span></span>
        <span><strong>Blinding Guard:</strong> <span style="color:${guardrailsPassed ? 'var(--c-ok)' : 'var(--c-warn)'}; font-weight:600;">${guardrailsPassed ? '🛡️ Multi-Factor Enforced' : '⚠️ Diversity Check Blocked'}</span></span>
      </div>

      ${conjunctionHtml}
      ${distributionHtml}
      ${diffHtml}
      ${actionButtonsHtml}
    </div>
  `;
}

async function triggerCrossAgentHandoff(stream, topic, messageText) {
  switchView("chat");
  await switchTopic(stream, topic);
  const input = document.getElementById("composerInput");
  if (input) {
    input.value = messageText;
    input.focus();
    const sendBtn = document.getElementById("sendBtn");
    if (sendBtn) {
      sendBtn.click();
    }
  }
}


function renderFeedHealthWidget(widget) {
  const summary = widget.summary || {};
  const total = summary.total_feeds_audited || 0;
  const healthy = summary.healthy_count || 0;
  const irregular = summary.irregular_count || 0;
  const failed = summary.failed_count || 0;
  const highLatency = summary.high_latency_count || 0;
  const quotaRejections = !!summary.quota_rejections_detected;
  const findings = widget.findings || [];
  const parsingErrorFeeds = widget.parsing_error_feeds || [];

  let statusBadge = "";
  let borderLeft = "var(--c-ok)";
  if (failed > 0 || quotaRejections) {
    statusBadge = `<span class="badge" style="background:var(--c-danger-bg); color:var(--c-danger); border:1px solid var(--c-danger-bd);">🔴 CRITICAL FEED FAILURES</span>`;
    borderLeft = "var(--c-danger)";
  } else if (irregular > 0 || highLatency > 0) {
    statusBadge = `<span class="badge" style="background:var(--c-warn-bg); color:var(--c-warn); border:1px solid var(--c-warn-bd);">🟡 TRANSPORT IRREGULARITIES</span>`;
    borderLeft = "var(--c-warn)";
  } else {
    statusBadge = `<span class="badge" style="background:var(--c-ok-bg); color:var(--c-ok); border:1px solid var(--c-ok-bd);">🟢 ALL FEEDS HEALTHY</span>`;
  }

  let handoffHtml = "";
  if (parsingErrorFeeds.length > 0) {
    handoffHtml = `
      <div style="background:var(--c-indigo-faint); border:1px solid var(--c-indigo-bd); border-radius:6px; padding:8px 12px; margin-top:10px; display:flex; justify-content:space-between; align-items:center;">
        <span style="font-size:12px; color:var(--c-indigo);">⚠️ <strong>Volume Funnel Drop Detected:</strong> Feeds for <code>${escapeHtml(parsingErrorFeeds.join(", "))}</code> are ingesting raw logs, but downstream normalization errors were detected.</span>
        <button class="btn btn-sm" style="background:var(--c-indigo-solid); color:var(--on-solid); font-size:11px; padding:3px 10px;" ${act("triggerCrossAgentHandoff", "ingestion", "parser-drops", `@parser-doctor diagnose unparsed logs for ${parsingErrorFeeds[0]}`)}>Hand off to @parser-doctor</button>
      </div>
    `;
  }

  const rows = findings.slice(0, 8).map(f => {
    let sBadge = `<span style="color:var(--c-ok); font-weight:600;">HEALTHY</span>`;
    if (f.status === "FAILED") sBadge = `<span style="color:var(--c-danger); font-weight:600;">FAILED</span>`;
    else if (f.status === "IRREGULAR") sBadge = `<span style="color:var(--c-warn); font-weight:600;">IRREGULAR</span>`;
    else if (f.status === "HIGH_LATENCY") sBadge = `<span style="color:var(--c-high); font-weight:600;">LAGGING</span>`;

    return `
      <tr style="border-bottom:1px solid var(--border-subtle); font-size:11.5px;">
        <td style="padding:6px 8px; font-weight:600; color:var(--text-main);">${escapeHtml(f.feed_name || f.feed_id)}</td>
        <td style="padding:6px 8px; font-family:var(--font-mono); color:var(--text-muted);">${escapeHtml(f.log_type || "-")}</td>
        <td style="padding:6px 8px; font-size:11px; color:var(--text-dim);">${escapeHtml(f.source_type || "-")}</td>
        <td style="padding:6px 8px;">${sBadge}</td>
        <td style="padding:6px 8px; font-family:var(--font-mono); font-size:11px; color:var(--text-dim);">${escapeHtml(f.latency_p95 || "-")}</td>
      </tr>
    `;
  }).join("");

  return `
    <div class="custom-card" style="border-left: 4px solid ${borderLeft}; margin-top:8px; padding:12px 14px; background:var(--bg-surface); border-radius:6px;">
      <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:10px;">
        <div style="display:flex; align-items:center; gap:8px;">
          <span style="font-size:16px;">📡</span>
          <span style="font-weight:700; font-size:13px; color:var(--text-main);">Chronicle Ingestion Transport Telemetry</span>
          ${statusBadge}
        </div>
        <div style="font-size:11px; color:var(--text-muted);">Health Hub P95 Telemetry</div>
      </div>

      <div class="kpi-grid" style="grid-template-columns: repeat(5, 1fr); margin-bottom:12px;">
        <div class="kpi-card" style="padding:6px 8px; text-align:center;">
          <div class="kpi-lbl">Total Feeds</div>
          <div style="font-size:14px; font-weight:700; color:var(--text-main);">${total}</div>
        </div>
        <div class="kpi-card" style="padding:6px 8px; text-align:center;">
          <div class="kpi-lbl">Healthy</div>
          <div style="font-size:14px; font-weight:700; color:var(--c-ok);">${healthy}</div>
        </div>
        <div class="kpi-card" style="padding:6px 8px; text-align:center;">
          <div class="kpi-lbl">Irregular</div>
          <div style="font-size:14px; font-weight:700; color:var(--c-warn);">${irregular}</div>
        </div>
        <div class="kpi-card" style="padding:6px 8px; text-align:center;">
          <div class="kpi-lbl">Failed</div>
          <div style="font-size:14px; font-weight:700; color:var(--c-danger);">${failed}</div>
        </div>
        <div class="kpi-card" style="padding:6px 8px; text-align:center;">
          <div class="kpi-lbl">Quota Reject</div>
          <div style="font-size:14px; font-weight:700; color:${quotaRejections ? 'var(--c-danger)' : 'var(--c-ok)'};">${quotaRejections ? 'YES' : '0 MB'}</div>
        </div>
      </div>

      ${findings.length > 0 ? `
        <table style="width:100%; border-collapse:collapse; margin-top:6px;">
          <thead>
            <tr style="border-bottom:1px solid var(--border-color); font-size:11px; color:var(--text-muted); text-transform:uppercase;">
              <th style="padding:4px 8px; text-align:left;">Feed Name</th>
              <th style="padding:4px 8px; text-align:left;">Log Type</th>
              <th style="padding:4px 8px; text-align:left;">Source</th>
              <th style="padding:4px 8px; text-align:left;">Status</th>
              <th style="padding:4px 8px; text-align:left;">Latency (P95)</th>
            </tr>
          </thead>
          <tbody>
            ${rows}
          </tbody>
        </table>
      ` : ''}

      ${handoffHtml}
    </div>
  `;
}

function renderParserHealthWidget(widget) {
  const summary = widget.summary || {};
  const total = summary.total_parsers_audited || 0;
  const healthy = summary.healthy_count || 0;
  const irregular = summary.irregular_count || 0;
  const failed = summary.failed_count || 0;
  const drift = summary.version_drift_count || 0;
  const conflicts = summary.extension_conflict_count || 0;
  const findings = widget.findings || [];

  let statusBadge = "";
  let borderLeft = "var(--c-ok)";
  if (failed > 0 || conflicts > 0) {
    statusBadge = `<span class="badge" style="background:var(--c-danger-bg); color:var(--c-danger); border:1px solid var(--c-danger-bd);">🔴 PARSER NORMALIZATION ERRORS</span>`;
    borderLeft = "var(--c-danger)";
  } else if (irregular > 0 || drift > 0) {
    statusBadge = `<span class="badge" style="background:var(--c-warn-bg); color:var(--c-warn); border:1px solid var(--c-warn-bd);">🟡 VERSION DRIFT / IRREGULARITIES</span>`;
    borderLeft = "var(--c-warn)";
  } else {
    statusBadge = `<span class="badge" style="background:var(--c-ok-bg); color:var(--c-ok); border:1px solid var(--c-ok-bd);">🟢 PARSER HYGIENE OPTIMAL</span>`;
  }

  const rows = findings.slice(0, 8).map(f => {
    let sBadge = `<span style="color:var(--c-ok); font-weight:600;">HEALTHY</span>`;
    if (f.status === "FAILED") sBadge = `<span style="color:var(--c-danger); font-weight:600;">FAILED</span>`;
    else if (f.status === "IRREGULAR") sBadge = `<span style="color:var(--c-warn); font-weight:600;">IRREGULAR</span>`;

    let driftBadge = f.version && f.latest_version && f.version !== f.latest_version
      ? `<span style="color:var(--c-warn); font-size:11px;">v${escapeHtml(f.version)} &rarr; v${escapeHtml(f.latest_version)}</span>`
      : `<span style="color:var(--text-dim); font-size:11px;">v${escapeHtml(f.version || "1.0")}</span>`;

    return `
      <tr style="border-bottom:1px solid var(--border-subtle); font-size:11.5px;">
        <td style="padding:6px 8px; font-weight:600; font-family:var(--font-mono); color:var(--text-main);">${escapeHtml(f.log_type)}</td>
        <td style="padding:6px 8px; font-size:11px; color:var(--text-muted);">${escapeHtml(f.creator_source || "GOOGLE")}</td>
        <td style="padding:6px 8px;">${sBadge}</td>
        <td style="padding:6px 8px;">${driftBadge}</td>
        <td style="padding:6px 8px; font-size:11px; color:var(--c-danger);">${escapeHtml(f.drop_reason_code || "-")}</td>
        <td style="padding:6px 8px; text-align:right;">
          <button class="btn btn-sm" style="font-size:11px; padding:2px 8px; background:var(--c-indigo-bg); color:var(--c-indigo); border:1px solid var(--c-indigo-bd);" ${act("triggerCrossAgentHandoff", "ingestion", "parser-drops", `@parser-doctor diagnose unparsed logs for ${f.log_type}`)}>Diagnose</button>
        </td>
      </tr>
    `;
  }).join("");

  return `
    <div class="custom-card" style="border-left: 4px solid ${borderLeft}; margin-top:8px; padding:12px 14px; background:var(--bg-surface); border-radius:6px;">
      <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:10px;">
        <div style="display:flex; align-items:center; gap:8px;">
          <span style="font-size:16px;">🩺</span>
          <span style="font-weight:700; font-size:13px; color:var(--text-main);">SIEM Parser Hygiene & Normalization Telemetry</span>
          ${statusBadge}
        </div>
        <div style="font-size:11px; color:var(--text-muted);">Health Hub Parser Drop Diagnostics</div>
      </div>

      <div class="kpi-grid" style="grid-template-columns: repeat(5, 1fr); margin-bottom:12px;">
        <div class="kpi-card" style="padding:6px 8px; text-align:center;">
          <div class="kpi-lbl">Total Parsers</div>
          <div style="font-size:14px; font-weight:700; color:var(--text-main);">${total}</div>
        </div>
        <div class="kpi-card" style="padding:6px 8px; text-align:center;">
          <div class="kpi-lbl">Healthy</div>
          <div style="font-size:14px; font-weight:700; color:var(--c-ok);">${healthy}</div>
        </div>
        <div class="kpi-card" style="padding:6px 8px; text-align:center;">
          <div class="kpi-lbl">Failed</div>
          <div style="font-size:14px; font-weight:700; color:var(--c-danger);">${failed}</div>
        </div>
        <div class="kpi-card" style="padding:6px 8px; text-align:center;">
          <div class="kpi-lbl">Version Drift</div>
          <div style="font-size:14px; font-weight:700; color:var(--c-warn);">${drift}</div>
        </div>
        <div class="kpi-card" style="padding:6px 8px; text-align:center;">
          <div class="kpi-lbl">Extension Conflicts</div>
          <div style="font-size:14px; font-weight:700; color:var(--c-danger);">${conflicts}</div>
        </div>
      </div>

      ${findings.length > 0 ? `
        <table style="width:100%; border-collapse:collapse; margin-top:6px;">
          <thead>
            <tr style="border-bottom:1px solid var(--border-color); font-size:11px; color:var(--text-muted); text-transform:uppercase;">
              <th style="padding:4px 8px; text-align:left;">Log Type</th>
              <th style="padding:4px 8px; text-align:left;">Author</th>
              <th style="padding:4px 8px; text-align:left;">Status</th>
              <th style="padding:4px 8px; text-align:left;">Version</th>
              <th style="padding:4px 8px; text-align:left;">Drop Reason</th>
              <th style="padding:4px 8px; text-align:right;">Action</th>
            </tr>
          </thead>
          <tbody>
            ${rows}
          </tbody>
        </table>
      ` : ''}
    </div>
  `;
}

function renderUnparsedDiagnosticWidget(widget) {
  const logType = widget.log_type || "";
  const totalFound = widget.total_unparsed_found || 0;
  const diagnostics = widget.diagnostics || [];

  const sampleBlocks = diagnostics.map((d, idx) => {
    const errorMsg = d.syntax_error || d.error_details || "Unparsed raw log failed normalizer filter";
    return `
      <div style="margin-top:8px; padding:8px 10px; background:var(--surface-inset); border-radius:4px; border:1px solid var(--border-subtle);">
        <div style="display:flex; justify-content:space-between; font-size:11px; margin-bottom:4px;">
          <span style="color:var(--c-danger); font-weight:600;">Sample #${idx + 1} Error: ${escapeHtml(errorMsg)}</span>
          <span style="color:var(--text-dim); font-family:var(--font-mono);">${escapeHtml(d.timestamp || "")}</span>
        </div>
        <div style="font-family:var(--font-mono); font-size:11px; color:var(--text-main); background:var(--surface-inset-strong); padding:6px 8px; border-radius:4px; overflow-x:auto; white-space:pre-wrap;">${escapeHtml(d.raw_log)}</div>
      </div>
    `;
  }).join("");

  return `
    <div class="custom-card" style="border-left: 4px solid var(--c-violet); margin-top:8px; padding:12px 14px; background:var(--bg-surface); border-radius:6px;">
      <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:8px;">
        <div style="display:flex; align-items:center; gap:8px;">
          <span style="font-size:16px;">🔬</span>
          <span style="font-weight:700; font-size:13px; color:var(--text-main);">Unparsed Logs Diagnostic: <code>${escapeHtml(logType)}</code></span>
          <span class="badge" style="background:var(--c-violet-bg); color:var(--c-violet); border:1px solid var(--c-violet-bd);">${totalFound} UNPARSED FOUND</span>
        </div>
      </div>

      <div style="font-size:12px; color:var(--text-muted); margin-bottom:8px;">
        Queried raw events (<code>raw = /.*/ parsed = false</code>) and dry-ran against active CBN filter code:
      </div>

      ${sampleBlocks}

      <div style="margin-top:10px; display:flex; justify-content:flex-end;">
        <button class="btn btn-sm" style="background:var(--c-violet-solid); color:var(--on-solid); font-size:11.5px; padding:4px 12px;" ${act("triggerCrossAgentHandoff", "ingestion", "parser-drops", `@parser-doctor propose CBN patch for ${logType}`)}>Propose Logstash CBN Patch</button>
      </div>
    </div>
  `;
}

function renderDataTableWidget(widget) {
  const title = widget.title || "GoogleSQL Query Results";
  const columns = widget.columns || [];
  const rows = widget.rows || [];
  const totalRows = widget.total_rows || rows.length;

  let headerHtml = columns.map(c => `<th style="padding: 8px 12px; text-align: left; font-size: 11px; text-transform: uppercase; color: var(--text-muted); border-bottom: 1px solid var(--border-color); font-weight: 600;">${escapeHtml(c)}</th>`).join("");
  
  let rowsHtml = "";
  if (rows.length === 0) {
    rowsHtml = `<tr><td colspan="${Math.max(columns.length, 1)}" style="padding: 16px; text-align: center; color: var(--text-muted); font-style: italic;">No records returned for this query window.</td></tr>`;
  } else {
    rowsHtml = rows.slice(0, 50).map((r, idx) => {
      const bg = idx % 2 === 0 ? "var(--surface-stripe)" : "transparent";
      const cells = columns.map(c => {
        let val = r[c];
        if (val === null || val === undefined) val = '<span style="color:var(--text-muted); font-style:italic;">null</span>';
        else if (typeof val === "object") val = escapeHtml(JSON.stringify(val));
        else val = escapeHtml(String(val));
        return `<td style="padding: 7px 12px; font-size: 12px; font-family: var(--font-mono); border-bottom: 1px solid var(--border-subtle);">${val}</td>`;
      }).join("");
      return `<tr style="background:${bg};">${cells}</tr>`;
    }).join("");
  }

  return `
    <div class="sql-data-table-card" style="margin-top: 10px; background: var(--bg-secondary); border: 1px solid var(--border-color); border-radius: 8px; overflow: hidden;">
      <div style="padding: 10px 14px; background: var(--c-info-faint); border-bottom: 1px solid var(--border-color); display: flex; align-items: center; justify-content: space-between;">
        <div style="display: flex; align-items: center; gap: 8px;">
          <span style="font-size: 14px;">📊</span>
          <span style="font-weight: 600; font-size: 12.5px; color: var(--text-primary);">${escapeHtml(title)}</span>
          <span style="font-size: 11px; background: var(--c-info-bg); color: var(--c-info); padding: 2px 7px; border-radius: 10px; font-weight: 600;">GoogleSQL</span>
        </div>
        <span style="font-size: 11px; color: var(--text-muted);">${totalRows} row${totalRows === 1 ? '' : 's'} returned</span>
      </div>
      <div style="max-height: 320px; overflow: auto;">
        <table style="width: 100%; border-collapse: collapse; text-align: left;">
          <thead>
            <tr style="background: var(--surface-inset);">${headerHtml}</tr>
          </thead>
          <tbody>
            ${rowsHtml}
          </tbody>
        </table>
      </div>
      ${totalRows > 50 ? `<div style="padding: 6px 14px; font-size: 11px; color: var(--text-muted); background: var(--bg-tertiary); border-top: 1px solid var(--border-color); text-align: center;">Showing first 50 rows of ${totalRows} total records.</div>` : ''}
    </div>
  `;
}

function renderGcpTelemetryWidget(widget) {
  const summary = widget.summary || {};
  const ingestionCount = summary.ingestion_streams_count || 0;
  const normalizerCount = summary.normalizer_streams_count || 0;
  const apiCount = summary.api_streams_count || 0;
  const errorCount = summary.error_logs_count || 0;
  const hours = summary.hours || 24;
  const logType = summary.log_type || "ALL";

  let statusBadge = "";
  let borderLeft = "var(--c-ok)";
  if (errorCount > 0) {
    statusBadge = `<span class="badge" style="background:var(--c-danger-bg); color:var(--c-danger); border:1px solid var(--c-danger-bd);">🔴 ${errorCount} TELEMETRY / AUDIT ERRORS</span>`;
    borderLeft = "var(--c-danger)";
  } else {
    statusBadge = `<span class="badge" style="background:var(--c-ok-bg); color:var(--c-ok); border:1px solid var(--c-ok-bd);">🟢 TELEMETRY STREAMS HEALTHY</span>`;
  }

  const errors = widget.recent_errors || [];
  let errorRows = "";
  if (errors.length > 0) {
    errorRows = errors.map(e => `
      <tr style="border-bottom:1px solid var(--border-subtle); font-size:11.5px;">
        <td style="padding:6px 8px; font-weight:600; color:var(--c-danger);">${escapeHtml(e.severity || "ERROR")}</td>
        <td style="padding:6px 8px; font-family:var(--font-mono); color:var(--text-muted);">${escapeHtml(e.timestamp ? new Date(e.timestamp).toLocaleTimeString() : "-")}</td>
        <td style="padding:6px 8px; font-family:var(--font-mono); color:var(--c-info);">${escapeHtml(e.resource_type || "chronicle")}</td>
        <td style="padding:6px 8px; color:var(--text-main);">${escapeHtml(e.summary || "Error logged")}</td>
      </tr>
    `).join("");
  }

  return `
    <div class="custom-card" style="border-left: 4px solid ${borderLeft}; margin-top:8px; padding:12px 14px; background:var(--bg-surface); border-radius:6px;">
      <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:10px;">
        <div style="display:flex; align-items:center; gap:8px;">
          <span style="font-size:16px;">📈</span>
          <span style="font-weight:700; font-size:13px; color:var(--text-main);">GCP Cloud Logging & Monitoring Telemetry</span>
          ${statusBadge}
        </div>
        <div style="font-size:11px; color:var(--text-muted);">Window: Last ${hours}h | Target: ${escapeHtml(logType)}</div>
      </div>

      <div class="kpi-grid" style="grid-template-columns: repeat(4, 1fr); margin-bottom:12px;">
        <div class="kpi-card" style="padding:6px 8px; text-align:center;">
          <div style="font-size:11px; color:var(--text-muted);">Ingestion Streams</div>
          <div style="font-size:16px; font-weight:700; color:var(--c-sky);">${ingestionCount}</div>
        </div>
        <div class="kpi-card" style="padding:6px 8px; text-align:center;">
          <div style="font-size:11px; color:var(--text-muted);">Normalizer Streams</div>
          <div style="font-size:16px; font-weight:700; color:var(--c-indigo);">${normalizerCount}</div>
        </div>
        <div class="kpi-card" style="padding:6px 8px; text-align:center;">
          <div style="font-size:11px; color:var(--text-muted);">API Metric Streams</div>
          <div style="font-size:16px; font-weight:700; color:var(--c-ok);">${apiCount}</div>
        </div>
        <div class="kpi-card" style="padding:6px 8px; text-align:center;">
          <div style="font-size:11px; color:var(--text-muted);">Logging Errors</div>
          <div style="font-size:16px; font-weight:700; color:${errorCount > 0 ? 'var(--c-danger)' : 'var(--c-ok)'};">${errorCount}</div>
        </div>
      </div>

      ${errors.length > 0 ? `
        <div style="font-size:11.5px; font-weight:600; color:var(--c-danger); margin-bottom:6px;">Recent Diagnostic & Audit Error Events:</div>
        <table style="width:100%; border-collapse:collapse; margin-bottom:8px;">
          <thead>
            <tr style="border-bottom:1px solid var(--border-color); font-size:11px; color:var(--text-muted); text-align:left;">
              <th style="padding:4px 8px;">Severity</th>
              <th style="padding:4px 8px;">Time</th>
              <th style="padding:4px 8px;">Resource</th>
              <th style="padding:4px 8px;">Error Summary</th>
            </tr>
          </thead>
          <tbody>
            ${errorRows}
          </tbody>
        </table>
      ` : '<div style="font-size:11.5px; color:var(--c-ok); font-style:italic;">No warning or error events recorded in Cloud Logging for this time window.</div>'}
    </div>
  `;
}

function renderTenantDriftWidget(widget) {
  const snapshotId = widget.snapshot_id || "live_audit";
  const tenantId = widget.tenant_id || "default";
  const hasDrift = widget.has_drift || false;
  const driftStatus = widget.drift_status || (hasDrift ? "DRIFT_DETECTED" : "CLEAN");
  const driftCount = widget.drift_count || 0;
  const criticalCount = widget.critical_changes_count || 0;
  const highCount = widget.high_changes_count || 0;
  const mediumCount = widget.medium_changes_count || 0;
  const lowCount = widget.low_changes_count || 0;
  const subsystemsDrifted = widget.subsystems_drifted || [];
  const changes = widget.changes || [];
  const fingerprint = widget.current_fingerprint || widget.fingerprint || "";
  const tag = widget.tag ? ` | Tag: ${escapeHtml(widget.tag)}` : "";

  let statusBadge = "";
  let borderLeft = "var(--c-ok)";

  if (driftStatus === "INITIAL_BASELINE") {
    statusBadge = `<span class="badge" style="background:var(--c-info-bg); color:var(--c-info); border:1px solid var(--c-info-bd);">🔵 INITIAL BASELINE RECORDED</span>`;
    borderLeft = "var(--c-info)";
  } else if (criticalCount > 0) {
    statusBadge = `<span class="badge" style="background:var(--c-danger-bg); color:var(--c-danger); border:1px solid var(--c-danger-bd);">🔴 ${criticalCount} CRITICAL CONFIG DRIFT(S)</span>`;
    borderLeft = "var(--c-danger)";
  } else if (hasDrift) {
    statusBadge = `<span class="badge" style="background:var(--c-warn-bg); color:var(--c-warn); border:1px solid var(--c-warn-bd);">🟡 ${driftCount} CONFIG DRIFT(S) DETECTED</span>`;
    borderLeft = "var(--c-warn)";
  } else {
    statusBadge = `<span class="badge" style="background:var(--c-ok-bg); color:var(--c-ok); border:1px solid var(--c-ok-bd);">🟢 TENANT POSTURE IN SYNC</span>`;
    borderLeft = "var(--c-ok)";
  }

  let changesRows = "";
  if (changes.length > 0) {
    changesRows = changes.map(c => {
      const sev = c.severity || "LOW";
      let sevColor = "var(--c-info)";
      if (sev === "CRITICAL") sevColor = "var(--c-danger)";
      else if (sev === "HIGH") sevColor = "var(--c-high)";
      else if (sev === "MEDIUM") sevColor = "var(--c-warn)";

      const priorStr = typeof c.prior_value === "object" ? JSON.stringify(c.prior_value) : String(c.prior_value ?? "none");
      const newStr = typeof c.new_value === "object" ? JSON.stringify(c.new_value) : String(c.new_value ?? "none");

      return `
        <tr style="border-bottom:1px solid var(--border-subtle); font-size:11.5px;">
          <td style="padding:6px 8px; font-weight:700; color:${sevColor};">${escapeHtml(sev)}</td>
          <td style="padding:6px 8px; font-family:var(--font-mono); color:var(--c-violet);">${escapeHtml(c.subsystem || "-")}</td>
          <td style="padding:6px 8px; font-family:var(--font-mono); color:var(--text-main);">${escapeHtml(c.parameter || "-")}</td>
          <td style="padding:6px 8px; color:var(--text-dim); text-decoration:line-through; font-family:var(--font-mono);">${escapeHtml(priorStr)}</td>
          <td style="padding:6px 8px; color:var(--c-ok); font-weight:600; font-family:var(--font-mono);">${escapeHtml(newStr)}</td>
        </tr>
      `;
    }).join("");
  }

  return `
    <div class="custom-card" style="border-left: 4px solid ${borderLeft}; margin-top:8px; padding:12px 14px; background:var(--bg-surface); border-radius:6px;">
      <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:10px;">
        <div style="display:flex; align-items:center; gap:8px;">
          <span style="font-size:16px;">🏛️</span>
          <span style="font-weight:700; font-size:13px; color:var(--text-main);">SecOps Tenant Posture & Configuration Baseline</span>
          ${statusBadge}
        </div>
        <div style="font-size:11px; color:var(--text-muted);">Tenant: <code style="color:var(--c-info);">${escapeHtml(tenantId)}</code>${tag}</div>
      </div>

      <div class="kpi-grid" style="grid-template-columns: repeat(4, 1fr); margin-bottom:12px;">
        <div class="kpi-card" style="padding:6px 8px; text-align:center;">
          <div style="font-size:11px; color:var(--text-muted);">Critical Drift</div>
          <div style="font-size:16px; font-weight:700; color:${criticalCount > 0 ? 'var(--c-danger)' : 'var(--c-ok)'};">${criticalCount}</div>
        </div>
        <div class="kpi-card" style="padding:6px 8px; text-align:center;">
          <div style="font-size:11px; color:var(--text-muted);">High Drift</div>
          <div style="font-size:16px; font-weight:700; color:${highCount > 0 ? 'var(--c-high)' : 'var(--c-ok)'};">${highCount}</div>
        </div>
        <div class="kpi-card" style="padding:6px 8px; text-align:center;">
          <div style="font-size:11px; color:var(--text-muted);">Total Deltas</div>
          <div style="font-size:16px; font-weight:700; color:${driftCount > 0 ? 'var(--c-warn)' : 'var(--c-ok)'};">${driftCount}</div>
        </div>
        <div class="kpi-card" style="padding:6px 8px; text-align:center;">
          <div style="font-size:11px; color:var(--text-muted);">Subsystems Drifted</div>
          <div style="font-size:16px; font-weight:700; color:${subsystemsDrifted.length > 0 ? 'var(--c-violet)' : 'var(--c-ok)'};">${subsystemsDrifted.length}</div>
        </div>
      </div>

      ${subsystemsDrifted.length > 0 ? `
        <div style="display:flex; align-items:center; gap:6px; margin-bottom:10px; flex-wrap:wrap;">
          <span style="font-size:11px; color:var(--text-muted);">Affected Subsystems:</span>
          ${subsystemsDrifted.map(s => `<span class="badge" style="background:var(--c-violet-bg); color:var(--c-violet); font-size:11px;">${escapeHtml(s)}</span>`).join(" ")}
        </div>
      ` : ''}

      ${changes.length > 0 ? `
        <div style="font-size:11.5px; font-weight:600; color:var(--c-warn); margin-bottom:6px;">Detected Configuration Parameter Deltas:</div>
        <table style="width:100%; border-collapse:collapse; margin-bottom:8px;">
          <thead>
            <tr style="border-bottom:1px solid var(--border-color); font-size:11px; color:var(--text-muted); text-align:left;">
              <th style="padding:4px 8px;">Severity</th>
              <th style="padding:4px 8px;">Subsystem</th>
              <th style="padding:4px 8px;">Parameter</th>
              <th style="padding:4px 8px;">Prior Value</th>
              <th style="padding:4px 8px;">Current Value</th>
            </tr>
          </thead>
          <tbody>
            ${changesRows}
          </tbody>
        </table>
      ` : (driftStatus === "INITIAL_BASELINE" ? `
        <div style="font-size:11.5px; color:var(--c-info); font-style:italic;">First baseline captured for tenant. Future audits will detect drift against this cryptographic fingerprint.</div>
      ` : `
        <div style="font-size:11.5px; color:var(--c-ok); font-style:italic;">All tenant configuration parameters match the active Evidence Fabric baseline. No configuration drift detected.</div>
      `)}

      <div style="margin-top:8px; padding-top:6px; border-top:1px solid var(--border-subtle); display:flex; justify-content:space-between; align-items:center; font-size:11px; color:var(--text-muted);">
        <div>Snapshot: <code style="color:var(--text-muted);">${escapeHtml(snapshotId)}</code></div>
        ${fingerprint ? `<div>Fingerprint: <code style="color:var(--text-muted);">${escapeHtml(fingerprint.substring(0, 16))}...</code></div>` : ''}
      </div>
    </div>
  `;
}

function renderPlaybookHealthWidget(widget) {
  const summary = widget.summary || {};
  const playbooks = widget.playbooks || [];
  const totalAudited = summary.total_audited || playbooks.length;
  const avgScore = summary.average_resilience_score != null ? summary.average_resilience_score : 100;
  const degradedCount = summary.degraded_playbooks_count || 0;
  const lookbackDays = summary.lookback_days || 30;

  let catalogBadge = "";
  let catalogBorder = "var(--c-ok)";
  if (degradedCount > 0) {
    catalogBadge = `<span class="badge" style="background:var(--c-danger-bg); color:var(--c-danger); border:1px solid var(--c-danger-bd);">⚠️ ${degradedCount} DEGRADED PLAYBOOKS</span>`;
    catalogBorder = "var(--c-danger)";
  } else {
    catalogBadge = `<span class="badge" style="background:var(--c-ok-bg); color:var(--c-ok); border:1px solid var(--c-ok-bd);">🟢 PLAYBOOK CATALOG HEALTHY</span>`;
  }

  let playbookCardsHtml = "";
  if (playbooks.length > 0) {
    playbookCardsHtml = playbooks.map((pb, idx) => {
      const score = pb.resilience_score != null ? pb.resilience_score : 100;
      const grade = pb.resilience_grade || "A";
      const tel = pb.telemetry || {};
      const findings = pb.findings || [];
      const brief = pb.executive_brief || "";
      const mermaidDag = pb.mermaid_dag || "";
      const cardId = `pb_card_${idx}_${(pb.workflow_identifier || "id").substring(0, 8)}`;

      let gradeColor = "var(--c-ok)";
      if (grade === "B") gradeColor = "var(--c-info)";
      else if (grade === "C") gradeColor = "var(--c-warn)";
      else if (grade === "D") gradeColor = "var(--c-high)";
      else if (grade === "F") gradeColor = "var(--c-danger)";

      const failRate = tel.failure_rate_pct != null ? tel.failure_rate_pct : 0.0;
      const failColor = failRate > 20 ? "var(--c-danger)" : (failRate > 0 ? "var(--c-warn)" : "var(--c-ok)");

      let findingsRows = "";
      if (findings.length > 0) {
        findingsRows = findings.map(f => {
          let sevColor = "var(--c-info)";
          if (f.severity === "CRITICAL") sevColor = "var(--c-danger)";
          else if (f.severity === "HIGH") sevColor = "var(--c-high)";
          else if (f.severity === "MEDIUM") sevColor = "var(--c-warn)";

          const affectedStr = f.affected_steps && f.affected_steps.length > 0
            ? `<div style="font-size:11px; color:var(--text-dim); margin-top:2px;">Steps: <code>${escapeHtml(f.affected_steps.join(", "))}</code></div>`
            : "";

          return `
            <tr style="border-bottom:1px solid var(--border-subtle); font-size:11px;">
              <td style="padding:5px 6px; font-family:var(--font-mono); font-weight:700; color:var(--c-violet);">${escapeHtml(f.rule_id)}</td>
              <td style="padding:5px 6px; font-weight:700; color:${sevColor};">${escapeHtml(f.severity)}</td>
              <td style="padding:5px 6px; color:var(--text-main);">
                <div style="font-weight:600;">${escapeHtml(f.title)}</div>
                <div style="color:var(--text-dim); font-size:11px;">${escapeHtml(f.description)}</div>
                ${affectedStr}
              </td>
              <td style="padding:5px 6px; font-weight:700; color:var(--c-danger); text-align:right;">-${f.deduction} pts</td>
            </tr>
          `;
        }).join("");
      }

      return `
        <div style="background:var(--surface-inset-strong); border:1px solid var(--border-subtle); border-radius:6px; padding:10px 12px; margin-bottom:10px;">
          <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:8px;">
            <div style="display:flex; align-items:center; gap:8px;">
              <span style="display:inline-flex; align-items:center; justify-content:center; width:28px; height:28px; border-radius:6px; background:color-mix(in srgb, ${gradeColor} 13%, transparent); border:1px solid color-mix(in srgb, ${gradeColor} 40%, transparent); color:${gradeColor}; font-weight:800; font-size:14px;">
                ${grade}
              </span>
              <div>
                <div style="font-weight:700; font-size:12.5px; color:var(--text-main);">${escapeHtml(pb.name || "Playbook")}</div>
                <div style="font-size:11px; color:var(--text-muted); display:flex; gap:6px; align-items:center; margin-top:2px;">
                  <span class="badge" style="background:var(--c-info-bg); color:var(--c-info); font-size:11px; padding:1px 5px;">${escapeHtml(pb.category || "General")}</span>
                  <span class="badge" style="background:var(--c-neutral-bg); color:var(--text-muted); font-size:11px; padding:1px 5px;">P${pb.priority ?? 2}</span>
                  ${pb.is_enabled ? '<span style="color:var(--c-ok);">● Active</span>' : '<span style="color:var(--c-neutral);">○ Inactive</span>'}
                  ${pb.is_debug_mode ? '<span style="color:var(--c-danger); font-weight:700;">[DEBUG MODE]</span>' : ''}
                </div>
              </div>
            </div>
            <div style="text-align:right;">
              <div style="font-size:15px; font-weight:800; color:${gradeColor};">${score}<span style="font-size:11px; color:var(--text-muted);">/100</span></div>
              <div style="font-size:11px; color:var(--text-muted);">${pb.step_count || 0} steps | ${pb.relation_count || 0} edges</div>
            </div>
          </div>

          <!-- 30-Day Telemetry Strip -->
          <div style="display:flex; gap:8px; margin-bottom:8px; background:var(--surface-inset); padding:6px 8px; border-radius:4px; font-size:11px;">
            <div style="flex:1;"><span style="color:var(--text-muted);">30d Runs:</span> <b style="color:var(--text-main);">${tel.total_runs || 0}</b></div>
            <div style="flex:1;"><span style="color:var(--text-muted);">Completed:</span> <b style="color:var(--c-ok);">${tel.completed_runs || 0}</b></div>
            <div style="flex:1;"><span style="color:var(--text-muted);">Failed:</span> <b style="color:${tel.failed_runs ? 'var(--c-danger)' : 'var(--c-ok)'};">${tel.failed_runs || 0}</b></div>
            <div style="flex:1;"><span style="color:var(--text-muted);">Failure Rate:</span> <b style="color:${failColor};">${failRate}%</b></div>
            <div style="flex:1;"><span style="color:var(--text-muted);">Avg Dur:</span> <b style="color:var(--c-info);">${tel.avg_duration_seconds || 0}s</b></div>
          </div>

          <!-- Findings Table -->
          ${findings.length > 0 ? `
            <table style="width:100%; border-collapse:collapse; margin-bottom:8px;">
              <thead>
                <tr style="border-bottom:1px solid var(--border-subtle); font-size:11px; color:var(--text-muted); text-align:left;">
                  <th style="padding:3px 6px;">Rule</th>
                  <th style="padding:3px 6px;">Severity</th>
                  <th style="padding:3px 6px;">Finding Details</th>
                  <th style="padding:3px 6px; text-align:right;">Penalty</th>
                </tr>
              </thead>
              <tbody>
                ${findingsRows}
              </tbody>
            </table>
          ` : `
            <div style="font-size:11px; color:var(--c-ok); margin-bottom:6px;">✓ Clean static resilience topology. Zero anti-pattern deductions.</div>
          `}

          <!-- Interactive Expanders: Mermaid Flowchart & Executive Brief -->
          <div style="display:flex; gap:6px; margin-top:6px;">
            ${mermaidDag ? `
              <button ${act("toggleDisplay", `${cardId}_dag`)} 
                      class="btn btn-secondary" style="font-size:11px; padding:3px 8px; border-radius:4px;">
                ⚡ Toggle Flowchart DAG
              </button>
            ` : ''}
            ${brief ? `
              <button ${act("toggleDisplay", `${cardId}_brief`)} 
                      class="btn btn-secondary" style="font-size:11px; padding:3px 8px; border-radius:4px;">
                📋 View GenAI Brief
              </button>
            ` : ''}
          </div>

          ${mermaidDag ? `
            <div id="${cardId}_dag" style="display:none; margin-top:8px; padding:8px; background:var(--surface-inset); border-radius:4px; border:1px solid var(--border-color);">
              <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:4px;">
                <span style="font-size:11px; color:var(--text-muted); font-weight:600;">Mermaid.js Flowchart DAG</span>
                <button ${act("copyText", mermaidDag, "Mermaid DAG copied to clipboard")} 
                        class="btn btn-secondary" style="font-size:11px; padding:2px 6px;">Copy Syntax</button>
              </div>
              <pre class="mermaid" style="font-family:var(--font-mono); font-size:11px; color:var(--c-info); white-space:pre-wrap; margin:0; overflow-x:auto;">${escapeHtml(mermaidDag)}</pre>
            </div>
          ` : ''}

          ${brief ? `
            <div id="${cardId}_brief" style="display:none; margin-top:8px; padding:10px 12px; background:var(--surface-inset-strong); border-radius:4px; border:1px solid var(--c-indigo-bd); font-size:11px; line-height:1.5;">
              <div style="font-size:11px; color:var(--c-indigo); font-weight:700; margin-bottom:6px;">Architectural Executive Brief (Gemini)</div>
              ${formatMarkdown(brief)}
            </div>
          ` : ''}
        </div>
      `;
    }).join("");
  }

  return `
    <div class="custom-card" style="border-left: 4px solid ${catalogBorder}; margin-top:8px; padding:12px 14px; background:var(--bg-surface); border-radius:6px;">
      <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:10px;">
        <div style="display:flex; align-items:center; gap:8px;">
          <span style="font-size:16px;">⚡</span>
          <span style="font-weight:700; font-size:13px; color:var(--text-main);">SOAR Playbook Resilience &amp; Decay Audit</span>
          ${catalogBadge}
        </div>
        <div style="font-size:11px; color:var(--text-muted);">Window: <code style="color:var(--c-info);">${lookbackDays} Days</code></div>
      </div>

      <div class="kpi-grid" style="grid-template-columns: repeat(4, 1fr); margin-bottom:12px;">
        <div class="kpi-card" style="padding:6px 8px; text-align:center;">
          <div style="font-size:11px; color:var(--text-muted);">Playbooks Audited</div>
          <div style="font-size:16px; font-weight:700; color:var(--text-main);">${totalAudited}</div>
        </div>
        <div class="kpi-card" style="padding:6px 8px; text-align:center;">
          <div style="font-size:11px; color:var(--text-muted);">Catalog Avg Score</div>
          <div style="font-size:16px; font-weight:700; color:${avgScore >= 80 ? 'var(--c-ok)' : (avgScore >= 70 ? 'var(--c-warn)' : 'var(--c-danger)')};">${avgScore}/100</div>
        </div>
        <div class="kpi-card" style="padding:6px 8px; text-align:center;">
          <div style="font-size:11px; color:var(--text-muted);">Degraded Playbooks</div>
          <div style="font-size:16px; font-weight:700; color:${degradedCount > 0 ? 'var(--c-danger)' : 'var(--c-ok)'};">${degradedCount}</div>
        </div>
        <div class="kpi-card" style="padding:6px 8px; text-align:center;">
          <div style="font-size:11px; color:var(--text-muted);">Active Storage</div>
          <div style="font-size:14px; font-weight:700; color:var(--c-violet);">soar_playbooks</div>
        </div>
      </div>

      ${playbookCardsHtml}
    </div>
  `;
}

function renderTimestampIntegrityWidget(widget) {
  const summary = widget.summary || {};
  const total = summary.total_log_types || 0;
  const healthy = summary.healthy_count || 0;
  const newAnomalies = summary.new_anomalies_count || 0;
  const previouslyKnown = summary.previously_known_count || 0;
  const resolved = summary.resolved_count || 0;
  const skewedEvents = summary.total_skewed_events || 0;
  const delayedEvents = summary.total_delayed_events || 0;
  const days = widget.days || 7;
  const topDelayed = widget.top_delayed || [];
  const topSkewed = widget.top_skewed || [];
  const narrative = widget.narrative || "";

  let statusBadge = "";
  let borderLeft = "var(--c-ok)";
  if (skewedEvents > 0) {
    statusBadge = `<span class="badge" style="background:var(--c-danger-bg); color:var(--c-danger); border:1px solid var(--c-danger-bd);">🔴 CLOCK SKEW / NTP ERRORS DETECTED</span>`;
    borderLeft = "var(--c-danger)";
  } else if (newAnomalies > 0 || delayedEvents > 0) {
    statusBadge = `<span class="badge" style="background:var(--c-warn-bg); color:var(--c-warn); border:1px solid var(--c-warn-bd);">🟡 INGESTION DELAY BOTTLENECK</span>`;
    borderLeft = "var(--c-warn)";
  } else {
    statusBadge = `<span class="badge" style="background:var(--c-ok-bg); color:var(--c-ok); border:1px solid var(--c-ok-bd);">🟢 TELEMETRY TIMESTAMPS OPTIMAL</span>`;
  }

  // Combined unique rows from top_delayed and top_skewed
  const seenLts = new Set();
  const displayRows = [];
  topSkewed.forEach(r => {
    if (!seenLts.has(r.log_type)) {
      seenLts.add(r.log_type);
      displayRows.push(r);
    }
  });
  topDelayed.forEach(r => {
    if (!seenLts.has(r.log_type)) {
      seenLts.add(r.log_type);
      displayRows.push(r);
    }
  });

  let rowsHtml = "";
  if (displayRows.length > 0) {
    rowsHtml = displayRows.map(r => {
      let stateBadge = `<span style="color:var(--c-ok); font-weight:700;">HEALTHY</span>`;
      if (r.progression_state === "NEW") {
        stateBadge = `<span class="badge" style="background:var(--c-danger-bg); color:var(--c-danger); font-weight:700;">🔴 NEW</span>`;
      } else if (r.progression_state === "PREVIOUSLY KNOWN") {
        stateBadge = `<span class="badge" style="background:var(--c-warn-bg); color:var(--c-warn); font-weight:700;">🟡 PREV KNOWN</span>`;
      } else if (r.progression_state === "RESOLVED") {
        stateBadge = `<span class="badge" style="background:var(--c-ok-bg); color:var(--c-ok); font-weight:700;">🟢 RESOLVED</span>`;
      }

      const skewColor = r.cnt_lt_0_hours > 0 ? "var(--c-danger)" : "var(--text-dim)";
      const delayColor = r.cnt_gt_2_hours > 0 ? "var(--c-high)" : "var(--text-dim)";
      const avgColor = r.average_difference_minutes > 60 ? "var(--c-warn)" : "var(--c-ok)";

      return `
        <tr style="border-bottom:1px solid var(--border-subtle); font-size:11px;">
          <td style="padding:6px 8px; font-weight:700; font-family:var(--font-mono); color:var(--text-main);">${escapeHtml(r.log_type)}</td>
          <td style="padding:6px 8px; color:var(--text-muted); text-align:right;">${(r.total || 0).toLocaleString()}</td>
          <td style="padding:6px 8px; color:${avgColor}; font-weight:700; text-align:right;">${r.average_difference_minutes}m</td>
          <td style="padding:6px 8px; color:${skewColor}; font-weight:${r.cnt_lt_0_hours > 0 ? '700' : '400'}; text-align:right;">${(r.cnt_lt_0_hours || 0).toLocaleString()}</td>
          <td style="padding:6px 8px; color:var(--text-dim); text-align:right;">${(r.cnt_0_1_hours || 0).toLocaleString()}</td>
          <td style="padding:6px 8px; color:var(--text-dim); text-align:right;">${(r.cnt_1_2_hours || 0).toLocaleString()}</td>
          <td style="padding:6px 8px; color:${delayColor}; font-weight:${r.cnt_gt_2_hours > 0 ? '700' : '400'}; text-align:right;">${(r.cnt_gt_2_hours || 0).toLocaleString()}</td>
          <td style="padding:6px 8px; text-align:center;">${stateBadge}</td>
        </tr>
      `;
    }).join("");
  } else {
    rowsHtml = `
      <tr>
        <td colspan="8" style="padding:10px; text-align:center; color:var(--c-ok); font-size:11px;">
          ✨ All active log streams exhibit nominal real-time flow and zero NTP clock drift.
        </td>
      </tr>
    `;
  }

  const briefId = `ti_brief_${Math.random().toString(36).substring(2, 8)}`;

  return `
    <div class="custom-card" style="border-left: 4px solid ${borderLeft}; margin-top:8px; padding:12px 14px; background:var(--bg-surface); border-radius:6px;">
      <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:10px;">
        <div style="display:flex; align-items:center; gap:8px;">
          <span style="font-size:16px;">⏱️</span>
          <span style="font-weight:700; font-size:13px; color:var(--text-main);">Telemetry Ingestion Latency & Clock Drift Audit</span>
          ${statusBadge}
        </div>
        <span style="font-size:11px; color:var(--text-muted);">${days}-Day Window</span>
      </div>

      <div style="display:grid; grid-template-columns: repeat(auto-fit, minmax(100px, 1fr)); gap:8px; margin-bottom:12px;">
        <div class="kpi-card" style="padding:6px 8px; text-align:center;">
          <div style="font-size:11px; color:var(--text-muted);">Audited Feeds</div>
          <div style="font-size:15px; font-weight:700; color:var(--text-main);">${total}</div>
        </div>
        <div class="kpi-card" style="padding:6px 8px; text-align:center;">
          <div style="font-size:11px; color:var(--text-muted);">Healthy</div>
          <div style="font-size:15px; font-weight:700; color:var(--c-ok);">${healthy}</div>
        </div>
        <div class="kpi-card" style="padding:6px 8px; text-align:center;">
          <div style="font-size:11px; color:var(--text-muted);">New Anomalies</div>
          <div style="font-size:15px; font-weight:700; color:${newAnomalies > 0 ? 'var(--c-danger)' : 'var(--text-muted)'};">${newAnomalies}</div>
        </div>
        <div class="kpi-card" style="padding:6px 8px; text-align:center;">
          <div style="font-size:11px; color:var(--text-muted);">Prev Known</div>
          <div style="font-size:15px; font-weight:700; color:${previouslyKnown > 0 ? 'var(--c-warn)' : 'var(--text-muted)'};">${previouslyKnown}</div>
        </div>
        <div class="kpi-card" style="padding:6px 8px; text-align:center;">
          <div style="font-size:11px; color:var(--text-muted);">Resolved</div>
          <div style="font-size:15px; font-weight:700; color:var(--c-sky);">${resolved}</div>
        </div>
        <div class="kpi-card" style="padding:6px 8px; text-align:center;">
          <div style="font-size:11px; color:var(--text-muted);">Clock Skews (Δt&lt;0)</div>
          <div style="font-size:15px; font-weight:700; color:${skewedEvents > 0 ? 'var(--c-danger)' : 'var(--c-ok)'};">${skewedEvents.toLocaleString()}</div>
        </div>
        <div class="kpi-card" style="padding:6px 8px; text-align:center;">
          <div style="font-size:11px; color:var(--text-muted);">Delayed (&gt;2h)</div>
          <div style="font-size:15px; font-weight:700; color:${delayedEvents > 0 ? 'var(--c-high)' : 'var(--c-ok)'};">${delayedEvents.toLocaleString()}</div>
        </div>
      </div>

      <div style="background:var(--surface-inset-strong); border:1px solid var(--border-subtle); border-radius:6px; overflow-x:auto; margin-bottom:10px;">
        <table style="width:100%; border-collapse:collapse;">
          <thead>
            <tr style="border-bottom:1px solid var(--border-color); font-size:11px; color:var(--text-muted); text-transform:uppercase;">
              <th style="padding:6px 8px; text-align:left;">Log Type</th>
              <th style="padding:6px 8px; text-align:right;">Total Logs</th>
              <th style="padding:6px 8px; text-align:right;">Avg Delay</th>
              <th style="padding:6px 8px; text-align:right; color:var(--c-danger);">Δt &lt; 0h (NTP)</th>
              <th style="padding:6px 8px; text-align:right;">0-1h</th>
              <th style="padding:6px 8px; text-align:right;">1-2h</th>
              <th style="padding:6px 8px; text-align:right; color:var(--c-high);">&gt;2h Delay</th>
              <th style="padding:6px 8px; text-align:center;">State</th>
            </tr>
          </thead>
          <tbody>
            ${rowsHtml}
          </tbody>
        </table>
      </div>

      ${narrative ? `
        <div style="display:flex; gap:6px; margin-top:6px;">
          <button ${act("toggleDisplay", briefId)} 
                  class="btn btn-secondary" style="font-size:11px; padding:3px 8px; border-radius:4px;">
            📋 Toggle Operational Runbook & Brief
          </button>
        </div>
        <div id="${briefId}" style="display:none; margin-top:8px; padding:10px 12px; background:var(--surface-inset-strong); border-radius:4px; border:1px solid var(--c-indigo-bd); font-size:11px; line-height:1.5;">
          <div style="font-size:11px; color:var(--c-indigo); font-weight:700; margin-bottom:6px;">GenAI Infrastructure Advisory</div>
          ${formatMarkdown(narrative)}
        </div>
      ` : ''}
    </div>
  `;
}

function renderRuleConflictWidget(widget) {
  const cos = typeof widget.highest_cos === "number" ? Math.round(widget.highest_cos) : 0;
  let cosClass = "dps-low";
  let cosLabel = "LOW / NO OVERLAP";
  let borderLeft = "var(--c-ok)";

  if (cos >= 75) {
    cosClass = "dps-high";
    cosLabel = "CRITICAL OVERLAP";
    borderLeft = "var(--c-danger)";
  } else if (cos >= 45) {
    cosClass = "dps-med";
    cosLabel = "MODERATE OVERLAP";
    borderLeft = "var(--c-warn)";
  }

  const isLive = !!widget.is_live;
  const isSilent = !!widget.is_silent;
  const liveBadge = isLive
    ? `<span class="badge" style="background:var(--c-ok-bg); color:var(--c-ok); border:1px solid var(--c-ok-bd);">🟢 LIVE (ENABLED)</span>`
    : `<span class="badge" style="background:var(--c-neutral-bg); color:var(--text-muted); border:1px solid var(--c-neutral-bd);">⚪ DISABLED</span>`;

  const silentBadge = isSilent
    ? `<span class="badge" style="background:var(--c-danger-bg); color:var(--c-danger); border:1px solid var(--c-danger-bd);">⚠️ 0 DETECTIONS (90d)</span>`
    : `<span class="badge" style="background:var(--c-info-bg); color:var(--c-info); border:1px solid var(--c-info-bd);">ACTIVE DETECTIONS</span>`;

  const conflicts = Array.isArray(widget.conflicts) ? widget.conflicts : [];

  let conflictsHtml = "";
  if (conflicts.length === 0) {
    conflictsHtml = `<div style="padding:10px; color:var(--text-muted); font-size:12px; font-style:italic;">No semantically overlapping or conflicting rules discovered.</div>`;
  } else {
    conflictsHtml = `
      <div style="margin-top:10px; display:flex; flex-direction:column; gap:8px;">
        <div style="font-size:11.5px; font-weight:700; color:var(--text-muted); text-transform:uppercase; letter-spacing:0.5px;">
          Candidate Sibling Rules (${conflicts.length})
        </div>
        ${conflicts.map(c => {
          const cCos = Math.round(c.cos_score || 0);
          const simPct = ((c.similarity_score || 0) * 100).toFixed(1);
          let typeBadgeColor = "var(--c-violet)";
          if (c.conflict_type === "CONTRADICTION") typeBadgeColor = "var(--c-danger)";
          else if (c.conflict_type === "OVERLAP") typeBadgeColor = "var(--c-warn)";
          else if (c.conflict_type === "SCOPE GAPS") typeBadgeColor = "var(--c-info)";

          let sevColor = "var(--text-dim)";
          if (c.impact_severity === "HIGH") sevColor = "var(--c-danger)";
          else if (c.impact_severity === "MEDIUM") sevColor = "var(--c-warn)";

          return `
            <div style="background:var(--surface-inset-strong); border:1px solid var(--border-color); border-radius:6px; padding:10px 12px;">
              <div style="display:flex; justify-content:space-between; align-items:flex-start; margin-bottom:6px;">
                <div>
                  <div style="font-weight:700; font-size:12.5px; color:var(--text-main);">${escapeHtml(c.similar_rule_name || c.similar_rule_id)}</div>
                  <div style="font-family:var(--font-mono); font-size:11px; color:var(--text-dim);">${escapeHtml(c.similar_rule_id)}</div>
                </div>
                <div style="display:flex; align-items:center; gap:6px;">
                  <span class="badge" style="background:color-mix(in srgb, ${typeBadgeColor} 13%, transparent); color:${typeBadgeColor}; border:1px solid color-mix(in srgb, ${typeBadgeColor} 27%, transparent); font-weight:700;">${escapeHtml(c.conflict_type)}</span>
                  <span class="badge" style="background:color-mix(in srgb, ${sevColor} 13%, transparent); color:${sevColor}; border:1px solid color-mix(in srgb, ${sevColor} 27%, transparent);">${escapeHtml(c.impact_severity)}</span>
                  <span class="badge" style="background:var(--c-indigo-bg); color:var(--c-indigo); border:1px solid var(--c-indigo-bd); font-weight:700;">${cCos} COS</span>
                </div>
              </div>

              <div style="display:grid; grid-template-columns: repeat(4, 1fr); gap:6px; margin:8px 0; background:var(--surface-inset); padding:6px 8px; border-radius:4px; font-size:11px;">
                <div><span style="color:var(--text-muted);">Vector Sim:</span> <strong style="color:var(--c-info);">${simPct}%</strong></div>
                <div><span style="color:var(--text-muted);">Events:</span> <strong style="color:${c.events_overlap ? 'var(--c-ok)' : 'var(--text-dim)'};">${c.events_overlap ? 'Shared' : 'Distinct'}</strong></div>
                <div><span style="color:var(--text-muted);">Match:</span> <strong style="color:${c.match_overlap ? 'var(--c-warn)' : 'var(--text-dim)'};">${c.match_overlap ? 'Overlap' : 'None'}</strong></div>
                <div><span style="color:var(--text-muted);">Condition:</span> <strong style="color:${c.condition_overlap ? 'var(--c-danger)' : 'var(--text-dim)'};">${c.condition_overlap ? 'Overlap' : 'Distinct'}</strong></div>
              </div>

              ${c.explanation ? `<div style="font-size:11.5px; color:var(--text-muted); margin-bottom:6px; line-height:1.4;">${escapeHtml(c.explanation)}</div>` : ''}
              ${c.consolidation_strategy ? `
                <div style="font-size:11px; color:var(--c-ok); background:var(--c-ok-faint); border-left:3px solid var(--c-ok); padding:4px 8px; border-radius:0 4px 4px 0; margin-bottom:8px;">
                  <strong>Consolidation Strategy:</strong> ${escapeHtml(c.consolidation_strategy)}
                </div>
              ` : ''}

              <div style="display:flex; justify-content:flex-end; gap:6px; margin-top:6px;">
                <button ${act("promptRuleConflictAudit", c.similar_rule_id)} style="background:var(--c-indigo-bg); border:1px solid var(--c-indigo-bd); color:var(--c-indigo); font-size:11px; padding:3px 8px; border-radius:4px; cursor:pointer;">
                  🔍 Deep Audit Sibling
                </button>
                <button ${act("promptRuleConflictConsolidate", widget.rule_id, c.similar_rule_id)} style="background:var(--c-violet-bg); border:1px solid var(--c-violet-bd); color:var(--c-violet); font-size:11px; padding:3px 8px; border-radius:4px; cursor:pointer; font-weight:600;">
                  ⚡ Propose Consolidation
                </button>
              </div>
            </div>
          `;
        }).join("")}
      </div>
    `;
  }

  return `
    <div class="proposal-card status-open" style="border-left: 4px solid ${borderLeft}; padding:14px; margin-top:8px; background:var(--bg-surface); border-radius:6px;">
      <div class="prop-header" style="display:flex; justify-content:space-between; align-items:center; margin-bottom:8px;">
        <div style="display:flex; align-items:center; gap:8px;">
          <span style="font-size:16px;">⚖️</span>
          <span class="badge" style="background:var(--c-violet-bg); color:var(--c-violet); border:1px solid var(--c-violet-bd); font-weight:700;">RULE CONFLICT AUDIT</span>
          ${liveBadge}
          ${silentBadge}
        </div>
        <div class="dps-badge ${cosClass}">
          <span class="dps-number">${cos}</span>
          <span class="dps-text">/ 100 COS &bull; ${cosLabel}</span>
        </div>
      </div>

      <div class="prop-title" style="font-size:14px; font-weight:700; margin-bottom:2px; color:var(--text-main);">
        ${escapeHtml(widget.rule_name || widget.rule_id)}
      </div>
      <div style="font-family:var(--font-mono); font-size:11px; color:var(--text-dim); margin-bottom:10px;">
        Target Rule ID: ${escapeHtml(widget.rule_id)}
      </div>

      ${widget.strategic_recommendation ? `
        <div style="margin-bottom:10px; padding:8px 10px; background:var(--surface-inset-strong); border:1px solid var(--c-indigo-bd); border-radius:4px; font-size:11.5px; color:var(--text-muted); line-height:1.4;">
          <strong>Strategic Recommendation:</strong> ${escapeHtml(widget.strategic_recommendation)}
        </div>
      ` : ''}

      ${conflictsHtml}
    </div>
  `;
}

function renderRuleConflictBatchWidget(widget) {
  const totalScanned = widget.total_rules_scanned || 0;
  const totalPairs = widget.total_pairs_evaluated || 0;
  const conflictCounts = widget.conflict_counts || {};
  const severityCounts = widget.severity_counts || {};
  const highestCosRules = Array.isArray(widget.highest_cos_rules) ? widget.highest_cos_rules : [];

  return `
    <div class="custom-card" style="border-left: 4px solid var(--c-violet); margin-top:8px; padding:14px; background:var(--bg-surface); border-radius:6px;">
      <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:10px;">
        <div style="display:flex; align-items:center; gap:8px;">
          <span style="font-size:16px;">⚖️</span>
          <span style="font-weight:700; font-size:13.5px; color:var(--text-main);">Tenant Detection Rule Conflict Audit</span>
          <span class="badge" style="background:var(--c-violet-bg); color:var(--c-violet); border:1px solid var(--c-violet-bd);">BATCH AUDIT</span>
        </div>
        <span style="font-size:11px; color:var(--text-muted);">${totalScanned} Rules Scanned &bull; ${totalPairs} Pairs Evaluated</span>
      </div>

      <div style="display:grid; grid-template-columns: repeat(4, 1fr); gap:8px; margin-bottom:12px;">
        <div class="kpi-card" style="padding:6px 8px; text-align:center;">
          <div style="font-size:11px; color:var(--text-muted);">Critical Overlaps</div>
          <div style="font-size:16px; font-weight:700; color:var(--c-danger);">${severityCounts['CRITICAL'] || 0}</div>
        </div>
        <div class="kpi-card" style="padding:6px 8px; text-align:center;">
          <div style="font-size:11px; color:var(--text-muted);">Moderate Overlaps</div>
          <div style="font-size:16px; font-weight:700; color:var(--c-warn);">${severityCounts['MODERATE'] || 0}</div>
        </div>
        <div class="kpi-card" style="padding:6px 8px; text-align:center;">
          <div style="font-size:11px; color:var(--text-muted);">Redundancies</div>
          <div style="font-size:16px; font-weight:700; color:var(--c-violet);">${conflictCounts['REDUNDANCY'] || 0}</div>
        </div>
        <div class="kpi-card" style="padding:6px 8px; text-align:center;">
          <div style="font-size:11px; color:var(--text-muted);">Contradictions</div>
          <div style="font-size:16px; font-weight:700; color:var(--c-danger);">${conflictCounts['CONTRADICTION'] || 0}</div>
        </div>
      </div>

      ${highestCosRules.length > 0 ? `
        <div style="font-size:11.5px; font-weight:700; color:var(--text-muted); text-transform:uppercase; margin-bottom:6px;">
          Highest Conflict Overlap Rules (${highestCosRules.length})
        </div>
        <div style="display:flex; flex-direction:column; gap:6px;">
          ${highestCosRules.map(r => `
            <div style="display:flex; justify-content:space-between; align-items:center; background:var(--surface-inset-strong); border:1px solid var(--border-color); border-radius:4px; padding:8px 10px;">
              <div>
                <div style="font-weight:600; font-size:12px; color:var(--text-main);">${escapeHtml(r.rule_name || r.rule_id)}</div>
                <div style="font-family:var(--font-mono); font-size:11px; color:var(--text-dim);">${escapeHtml(r.rule_id)}</div>
              </div>
              <div style="display:flex; align-items:center; gap:8px;">
                <span class="badge" style="background:${r.highest_cos >= 75 ? 'var(--c-danger-bg)' : 'var(--c-warn-bg)'}; color:${r.highest_cos >= 75 ? 'var(--c-danger)' : 'var(--c-warn)'}; font-weight:700;">
                  ${Math.round(r.highest_cos)} COS
                </span>
                <button ${act("promptRuleConflictAudit", r.rule_id)} style="background:var(--c-indigo-bg); border:1px solid var(--c-indigo-bd); color:var(--c-indigo); font-size:11px; padding:2px 8px; border-radius:3px; cursor:pointer;">
                  Audit
                </button>
              </div>
            </div>
          `).join("")}
        </div>
      ` : ''}
    </div>
  `;
}

function promptRuleConflictAudit(ruleId) {
  const input = document.getElementById("composerInput");
  if (!input) return;
  input.value = `@rule-conflict-agent audit rule ${ruleId}`;
  input.focus();
}

function promptRuleConflictConsolidate(ruleId, siblingId) {
  const input = document.getElementById("composerInput");
  if (!input) return;
  input.value = `@rule-conflict-agent consolidate rule ${ruleId} with ${siblingId} and propose resolution`;
  input.focus();
}

function promptRuleDecayInvestigate(ruleId) {
  const input = document.getElementById("composerInput");
  if (!input) return;
  input.value = `@detection-decay-agent investigate rule ${ruleId}`;
  input.focus();
}

function promptRuleSyntaxFix(ruleId) {
  const input = document.getElementById("composerInput");
  if (!input) return;
  input.value = `@yaral-optimizer diagnose execution errors for rule ${ruleId}`;
  input.focus();
}

function renderRuleAuditCard(widget) {
  const data = widget.data || widget;
  const totalScanned = data.total_rules_scanned || 0;
  const customerCount = data.customer_rules_count || 0;
  const curatedCount = data.curated_rules_count || 0;
  const healthyCount = data.healthy_count || 0;
  const silentCount = data.silent_decay_count || 0;
  const failingCount = data.failing_count || 0;
  const misconfiguredCount = data.misconfigured_count || 0;
  const conflictCount = data.conflict_count || 0;
  const shadowedCuratedCount = data.shadowed_by_curated_count || 0;
  const embeddingsSynced = data.embeddings_synced_count || 0;
  const totalDetections = (data.total_detections_90d || 0).toLocaleString();
  const findings = Array.isArray(data.findings) ? data.findings : [];

  const attentionItems = findings.filter(f => {
    const st = typeof f.status === "object" ? f.status.value : f.status;
    return st !== "HEALTHY" || (f.highest_conflict_cos && f.highest_conflict_cos >= 75) || f.shadowed_by_curated_id;
  });

  return `
    <div class="custom-card" style="border-left: 4px solid var(--c-ok); margin-top:8px; padding:14px; background:var(--bg-surface); border-radius:6px;">
      <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:10px;">
        <div style="display:flex; align-items:center; gap:8px;">
          <span style="font-size:18px;">🛡️</span>
          <div>
            <div style="font-weight:700; font-size:14px; color:var(--text-main);">Detection Repository Health Audit</div>
            <div style="font-size:11px; color:var(--text-muted);">
              Tri-Pillar Assessment &bull; Ingestion &amp; Embeddings &bull; Decay Telemetry &bull; Conflict &amp; Shadowing
            </div>
          </div>
        </div>
        <div style="display:flex; align-items:center; gap:6px;">
          <span class="badge" style="background:var(--c-ok-bg); color:var(--c-ok); border:1px solid var(--c-ok-bd); font-weight:700;">
            ${embeddingsSynced > 0 ? `✨ ${embeddingsSynced} EMBEDDINGS SYNCED` : "EMBEDDINGS READY"}
          </span>
          <span class="badge" style="background:var(--c-info-bg); color:var(--c-info); border:1px solid var(--c-info-bd); font-weight:700;">
            ${curatedCount > 0 ? `${curatedCount} CURATED + ${customerCount} CUSTOM` : `${totalScanned} RULES`}
          </span>
        </div>
      </div>

      <div style="display:grid; grid-template-columns: repeat(6, 1fr); gap:8px; margin-bottom:12px;">
        <div class="kpi-card" style="padding:6px 8px; text-align:center;">
          <div style="font-size:11px; color:var(--text-muted);">Total Scanned</div>
          <div style="font-size:16px; font-weight:700; color:var(--text-main);">${totalScanned}</div>
        </div>
        <div class="kpi-card" style="padding:6px 8px; text-align:center;">
          <div style="font-size:11px; color:var(--text-muted);">Healthy Active</div>
          <div style="font-size:16px; font-weight:700; color:var(--c-ok);">${healthyCount}</div>
        </div>
        <div class="kpi-card" style="padding:6px 8px; text-align:center;">
          <div style="font-size:11px; color:var(--text-muted);">Silent (0 Det/90d)</div>
          <div style="font-size:16px; font-weight:700; color:${silentCount > 0 ? 'var(--c-warn)' : 'var(--text-muted)'};">${silentCount}</div>
        </div>
        <div class="kpi-card" style="padding:6px 8px; text-align:center;">
          <div style="font-size:11px; color:var(--text-muted);">Execution Errors</div>
          <div style="font-size:16px; font-weight:700; color:${failingCount > 0 ? 'var(--c-danger)' : 'var(--c-ok)'};">${failingCount}</div>
        </div>
        <div class="kpi-card" style="padding:6px 8px; text-align:center;">
          <div style="font-size:11px; color:var(--text-muted);">Conflicts (COS≥75)</div>
          <div style="font-size:16px; font-weight:700; color:${conflictCount > 0 ? 'var(--c-violet)' : 'var(--text-muted)'};">${conflictCount}</div>
        </div>
        <div class="kpi-card" style="padding:6px 8px; text-align:center;">
          <div style="font-size:11px; color:var(--text-muted);">Shadows Curated</div>
          <div style="font-size:16px; font-weight:700; color:${shadowedCuratedCount > 0 ? 'var(--c-high)' : 'var(--c-ok)'};">${shadowedCuratedCount}</div>
        </div>
      </div>

      ${attentionItems.length > 0 ? `
        <div style="font-size:11px; font-weight:700; color:var(--text-muted); text-transform:uppercase; margin-bottom:6px; display:flex; justify-content:space-between; align-items:center;">
          <span>Action Required Rules (${attentionItems.length})</span>
          <span style="font-size:11px; font-weight:normal; color:var(--text-dim);">Showing prioritized findings</span>
        </div>
        <div style="display:flex; flex-direction:column; gap:6px; max-height:360px; overflow-y:auto;">
          ${attentionItems.slice(0, 25).map(f => {
            const st = typeof f.status === "object" ? f.status.value : f.status;
            let stBadge = `<span class="badge" style="background:var(--c-danger-bg); color:var(--c-danger); border:1px solid var(--c-danger-bd); font-size:11px;">${st}</span>`;
            if (st === "SILENT_DECAY") {
              stBadge = `<span class="badge" style="background:var(--c-warn-bg); color:var(--c-warn); border:1px solid var(--c-warn-bd); font-size:11px;">SILENT DECAY</span>`;
            } else if (st === "MISCONFIGURED_ALERTING") {
              stBadge = `<span class="badge" style="background:var(--c-violet-bg); color:var(--c-violet); border:1px solid var(--c-violet-bd); font-size:11px;">MISCONFIGURED</span>`;
            }
            const isCurated = f.rule_source === "GOOGLE_CURATED" || (f.rule_id && f.rule_id.startsWith("ur_"));
            const srcBadge = isCurated
              ? `<span class="badge" style="background:var(--c-info-bg); color:var(--c-info); border:1px solid var(--c-info-bd); font-size:11px;">CURATED</span>`
              : `<span class="badge" style="background:var(--c-neutral-bg); color:var(--text-muted); border:1px solid var(--c-neutral-bd); font-size:11px;">CUSTOM</span>`;

            return `
              <div style="background:var(--surface-inset-strong); border:1px solid var(--border-color); border-radius:4px; padding:8px 10px;">
                <div style="display:flex; justify-content:space-between; align-items:flex-start; margin-bottom:4px;">
                  <div>
                    <div style="display:flex; align-items:center; gap:6px;">
                      ${srcBadge}
                      <span style="font-weight:600; font-size:12px; color:var(--text-main);">${escapeHtml(f.rule_name || f.rule_id)}</span>
                    </div>
                    <div style="font-family:var(--font-mono); font-size:11px; color:var(--text-dim); margin-top:1px;">
                      ${escapeHtml(f.rule_id)} &bull; DPS: <strong>${Math.round(f.dps_score || 0)}</strong> &bull; 90d Det: <strong>${f.detection_count_90d || 0}</strong>
                    </div>
                  </div>
                  <div style="display:flex; align-items:center; gap:6px;">
                    ${stBadge}
                    ${f.highest_conflict_cos >= 75 ? `<span class="badge" style="background:var(--c-violet-bg); color:var(--c-violet); border:1px solid var(--c-violet-bd); font-size:11px;">${Math.round(f.highest_conflict_cos)}% COS</span>` : ''}
                  </div>
                </div>

                ${f.shadowed_by_curated_id ? `
                  <div style="margin-top:4px; padding:4px 6px; background:var(--c-high-faint); border:1px solid var(--c-high-bd); border-radius:3px; font-size:11px; color:var(--c-high);">
                    ⚠️ <strong>Shadows Google Curated Rule:</strong> ${escapeHtml(f.shadowed_by_curated_name || f.shadowed_by_curated_id)} (<code>${escapeHtml(f.shadowed_by_curated_id)}</code>)
                  </div>
                ` : ''}

                ${f.remediation_steps && f.remediation_steps.length > 0 ? `
                  <div style="font-size:11px; color:var(--text-dim); margin-top:4px;">
                    💡 ${escapeHtml(f.remediation_steps[0])}
                  </div>
                ` : ''}

                <div style="display:flex; justify-content:flex-end; gap:6px; margin-top:6px;">
                  ${f.shadowed_by_curated_id ? `
                    <button ${act("promptRuleConflictConsolidate", f.rule_id, f.shadowed_by_curated_id)} style="background:var(--c-high-bg); border:1px solid var(--c-high-bd); color:var(--c-high); font-size:11px; padding:2px 8px; border-radius:3px; cursor:pointer; font-weight:600;">
                      ⚡ Retire in Favor of Curated
                    </button>
                  ` : ''}
                  ${f.highest_conflict_cos >= 75 ? `
                    <button ${act("promptRuleConflictAudit", f.rule_id)} style="background:var(--c-violet-bg); border:1px solid var(--c-violet-bd); color:var(--c-violet); font-size:11px; padding:2px 8px; border-radius:3px; cursor:pointer;">
                      🔍 Inspect Conflict
                    </button>
                  ` : ''}
                  ${st === "SILENT_DECAY" ? `
                    <button ${act("promptRuleDecayInvestigate", f.rule_id)} style="background:var(--c-warn-bg); border:1px solid var(--c-warn-bd); color:var(--c-warn); font-size:11px; padding:2px 8px; border-radius:3px; cursor:pointer;">
                      📉 Investigate Decay
                    </button>
                  ` : ''}
                  ${st === "EXECUTION_ERROR" ? `
                    <button ${act("promptRuleSyntaxFix", f.rule_id)} style="background:var(--c-danger-bg); border:1px solid var(--c-danger-bd); color:var(--c-danger); font-size:11px; padding:2px 8px; border-radius:3px; cursor:pointer;">
                      🛠️ Inspect Runtime Error
                    </button>
                  ` : ''}
                </div>
              </div>
            `;
          }).join("")}
        </div>
      ` : `
        <div style="text-align:center; padding:12px; color:var(--c-ok); font-size:12px;">
          ✨ All scanned detection rules are healthy, operational, and free from conflicts.
        </div>
      `}
    </div>
  `;
}

function renderFinopsCostCard(widget) {
  const data = widget.data || widget;
  const totalVolumeGb = Number(data.total_volume_gb || 0).toLocaleString(undefined, { maximumFractionDigits: 1 });
  const totalEvents = Number(data.total_events || 0).toLocaleString();
  const spendEnterprise = Number(data.spend_enterprise || 0).toLocaleString(undefined, { style: 'currency', currency: 'USD', maximumFractionDigits: 0 });
  const savings = Number(data.savings || 0).toLocaleString(undefined, { style: 'currency', currency: 'USD', maximumFractionDigits: 0 });
  const bloatedCount = data.bloated_count || 0;
  const recsCount = data.recommendations_count || 0;
  const topDrivers = Array.isArray(data.top_drivers) ? data.top_drivers : [];

  return `
    <div class="custom-card" style="border-left: 4px solid var(--c-ok); margin-top:8px; padding:14px; background:var(--bg-surface); border-radius:6px;">
      <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:10px;">
        <div style="display:flex; align-items:center; gap:8px;">
          <span style="font-size:18px;">💰</span>
          <div>
            <div style="font-weight:700; font-size:14px; color:var(--text-main);">Google SecOps FinOps &amp; Log Sizing Analysis</div>
            <div style="font-size:11px; color:var(--text-muted);">
              7-Day Chronicle Telemetry &bull; Multi-Tier Pricing &bull; Upstream Drop &amp; Micro-Tuning
            </div>
          </div>
        </div>
        <div style="display:flex; align-items:center; gap:6px;">
          <span class="badge" style="background:var(--c-ok-bg); color:var(--c-ok); border:1px solid var(--c-ok-bd); font-weight:700;">
            ${recsCount} RECOMMENDATIONS
          </span>
          <span class="badge" style="background:var(--c-warn-bg); color:var(--c-warn); border:1px solid var(--c-warn-bd); font-weight:700;">
            ${bloatedCount} BLOATED TYPES
          </span>
        </div>
      </div>

      <div style="display:grid; grid-template-columns: repeat(4, 1fr); gap:8px; margin-bottom:12px;">
        <div class="kpi-card" style="padding:6px 8px; text-align:center;">
          <div style="font-size:11px; color:var(--text-muted);">Ingested Volume (7d)</div>
          <div style="font-size:16px; font-weight:700; color:var(--c-info);">${totalVolumeGb} GB</div>
        </div>
        <div class="kpi-card" style="padding:6px 8px; text-align:center;">
          <div style="font-size:11px; color:var(--text-muted);">Total Ingested Events</div>
          <div style="font-size:16px; font-weight:700; color:var(--text-main);">${totalEvents}</div>
        </div>
        <div class="kpi-card" style="padding:6px 8px; text-align:center;">
          <div style="font-size:11px; color:var(--text-muted);">Projected Spend (Enterprise)</div>
          <div style="font-size:16px; font-weight:700; color:var(--c-danger);">${spendEnterprise}/mo</div>
        </div>
        <div class="kpi-card" style="padding:6px 8px; text-align:center;">
          <div style="font-size:11px; color:var(--text-muted);">Potential Savings</div>
          <div style="font-size:16px; font-weight:700; color:var(--c-ok);">${savings}/mo</div>
        </div>
      </div>

      ${topDrivers.length > 0 ? `
        <div style="font-size:11px; font-weight:700; text-transform:uppercase; color:var(--text-muted); margin-bottom:6px;">Top Volume Drivers</div>
        <div style="display:flex; flex-wrap:wrap; gap:6px; margin-bottom:10px;">
          ${topDrivers.slice(0, 5).map(d => `
            <span style="background:var(--surface-stripe); border:1px solid var(--border-color); border-radius:4px; padding:3px 8px; font-size:11px; font-family:var(--font-mono); color:var(--text-main);">
              ${escapeHtml(d.log_type)}: <strong style="color:var(--c-info);">${(d.volume_gb_decimal || d.volume_gb || 0).toFixed(1)} GB</strong> (${(d.pct_total_volume || d.percentage_of_total_volume || 0).toFixed(1)}%)
            </span>
          `).join("")}
        </div>
      ` : ''}

      <div style="display:flex; justify-content:flex-end; gap:8px; margin-top:8px;">
        <button ${act("openFinopsDashboard")} style="background:var(--c-ok-solid); border:none; color:var(--on-solid); font-size:11px; font-weight:600; padding:4px 12px; border-radius:4px; cursor:pointer; display:flex; align-items:center; gap:4px;">
          <span>📊 Open Full FinOps Dashboard</span>
        </button>
      </div>
    </div>
  `;
}

function renderRawLogSearchCard(w) {
  if (!w) return "";
  const totalMatches = w.total_matches ?? 0;
  const progress = w.progress ?? 100;
  const query = w.query || "";
  const lookbackHours = w.lookback_hours ?? 24;
  const matches = Array.isArray(w.matches) ? w.matches : [];

  return `
    <div class="raw-log-search-card" style="margin-top:8px; border:1px solid var(--c-info-bd); background:var(--surface-inset-strong); border-radius:8px; padding:12px; font-family:var(--font-sans);">
      <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:8px; border-bottom:1px solid var(--border-subtle); padding-bottom:6px;">
        <div style="display:flex; align-items:center; gap:8px;">
          <span style="font-size:14px;">🔎</span>
          <span style="font-size:12px; font-weight:700; color:var(--c-info); text-transform:uppercase; letter-spacing:0.5px;">Chronicle Raw Log Search</span>
        </div>
        <div style="display:flex; gap:6px; align-items:center;">
          <span style="background:var(--c-info-bg); border:1px solid var(--c-info-bd); color:var(--c-info); font-size:11px; font-weight:700; padding:2px 6px; border-radius:4px;">
            ${totalMatches} ${totalMatches === 1 ? 'MATCH' : 'MATCHES'}
          </span>
          <span style="background:var(--c-ok-bg); border:1px solid var(--c-ok-bd); color:var(--c-ok); font-size:11px; font-weight:700; padding:2px 6px; border-radius:4px;">
            ${progress}% SCANNED
          </span>
        </div>
      </div>

      <div style="display:flex; flex-wrap:wrap; gap:8px; margin-bottom:10px; font-size:11px;">
        <div style="background:var(--surface-inset); border:1px solid var(--border-subtle); border-radius:4px; padding:3px 8px; font-family:var(--font-mono); color:var(--text-muted); flex:1; min-width:200px; overflow:hidden; text-overflow:ellipsis; white-space:nowrap;">
          <span style="color:var(--text-muted); font-size:11px;">QUERY:</span> <span style="color:var(--c-sky);">${escapeHtml(query || "*")}</span>
        </div>
        <div style="background:var(--surface-inset); border:1px solid var(--border-subtle); border-radius:4px; padding:3px 8px; font-family:var(--font-mono); color:var(--text-dim);">
          <span style="color:var(--text-muted); font-size:11px;">WINDOW:</span> ${lookbackHours}h lookback
        </div>
      </div>

      ${matches.length > 0 ? `
        <div style="font-size:11px; font-weight:700; text-transform:uppercase; color:var(--text-muted); margin-bottom:6px;">Sample Matches (${matches.length})</div>
        <div style="display:flex; flex-direction:column; gap:6px; max-height:240px; overflow-y:auto; padding-right:4px;">
          ${matches.map((m, idx) => {
            const snippet = m.snippet || m.raw_text || JSON.stringify(m, null, 2);
            const id = m.id || m.event_id || `match-${idx}`;
            const logType = m.log_type || "UNKNOWN_SOURCE";
            const time = m.ingestion_time || m.timestamp || "";
            return `
              <div style="background:var(--surface-inset); border:1px solid var(--border-subtle); border-radius:4px; padding:6px 8px; font-size:11px;">
                <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:4px; font-size:11px;">
                  <div style="display:flex; align-items:center; gap:6px;">
                    <span style="background:var(--c-indigo-bg); border:1px solid var(--c-indigo-bd); color:var(--c-indigo); font-weight:700; padding:1px 5px; border-radius:3px;">
                      ${escapeHtml(logType)}
                    </span>
                    ${time ? `<span style="color:var(--text-muted);">${escapeHtml(time)}</span>` : ''}
                  </div>
                  <button ${act("copyText", snippet, "Raw log snippet copied to clipboard")} style="background:transparent; border:1px solid var(--border-color); color:var(--text-muted); font-size:11px; padding:1px 6px; border-radius:3px; cursor:pointer;" title="Copy verbatim payload">
                    📋 Copy Raw Log
                  </button>
                </div>
                <pre style="margin:0; padding:4px 6px; background:var(--surface-inset); border-radius:3px; font-family:var(--font-mono); font-size:11px; color:var(--text-main); max-height:80px; overflow:auto; white-space:pre-wrap; word-break:break-all;"><code>${escapeHtml(snippet)}</code></pre>
              </div>
            `;
          }).join("")}
        </div>
      ` : `
        <div style="font-size:11px; color:var(--text-muted); font-style:italic; padding:8px; text-align:center;">
          No matching raw log entries found in the specified lookback window.
        </div>
      `}
    </div>
  `;
}

function promptMitreCoverageAudit(profileId) {
  const input = document.getElementById("composerInput");
  if (!input) return;
  input.value = `@mitre-attack-agent audit coverage for ${profileId}`;
  input.focus();
}

function promptMitreTechniqueInspect(techniqueId) {
  const input = document.getElementById("composerInput");
  if (!input) return;
  input.value = `@mitre-attack-agent inspect rules for ${techniqueId}`;
  input.focus();
}

async function copyMitreExecutiveReport(profileId) {
  try {
    showToast("info", "Generating executive MITRE ATT&CK report...");
    const res = await fetch(`/api/mitre/report?profile=${encodeURIComponent(profileId)}`);
    const data = await res.json();
    const markdown = data.report?.markdown || data.report || "";
    if (!markdown) {
      showToast("error", "Received empty MITRE report");
      return;
    }
    await navigator.clipboard.writeText(markdown);
    showToast("success", "Executive MITRE Report copied to clipboard!");
  } catch (err) {
    showToast("error", "Failed copying report: " + err.message);
  }
}

function renderMitreCoverageCard(widget) {
  const data = widget.assessment || widget.data || widget;
  const score = Math.round(data.coverage_score || 0);
  const profileName = data.profile_name || "Global Baseline";
  const profileId = data.profile_id || "global_baseline";
  const validatedTechniques = data.validated_technique_count || 0;
  const totalRules = (data.total_rules_evaluated || 0).toLocaleString();
  const enabledRules = (data.enabled_rules_count || 0).toLocaleString();
  const visTactics = data.visibility_tactics_count || 0;
  const detTactics = data.detection_tactics_count || 0;
  const blindTactics = Array.isArray(data.blind_tactics) ? data.blind_tactics : [];
  const resilientCount = data.resilient_techniques_count || (Array.isArray(data.resilient_techniques) ? data.resilient_techniques.length : 0);
  const fragileCount = data.fragile_techniques_count || (Array.isArray(data.fragile_techniques) ? data.fragile_techniques.length : 0);
  const visibilityGapsCount = data.visibility_gaps_count || (Array.isArray(data.visibility_gaps) ? data.visibility_gaps.length : 0);
  const detectionGapsCount = data.detection_gaps_count || (Array.isArray(data.detection_gaps) ? data.detection_gaps.length : 0);
  const criticalTechniques = Array.isArray(data.critical_techniques) ? data.critical_techniques : [];

  let scoreColor = "var(--c-ok)";
  let scoreBg = "var(--c-ok-bg)";
  let scoreBorder = "var(--c-ok-bd)";
  if (score < 50) {
    scoreColor = "var(--c-danger)";
    scoreBg = "var(--c-danger-bg)";
    scoreBorder = "var(--c-danger-bd)";
  } else if (score < 80) {
    scoreColor = "var(--c-warn)";
    scoreBg = "var(--c-warn-bg)";
    scoreBorder = "var(--c-warn-bd)";
  }

  const totalDenom = (resilientCount + fragileCount + detectionGapsCount) || 1;
  const resPct = Math.min(100, Math.round((resilientCount / totalDenom) * 100));
  const fragPct = Math.min(100 - resPct, Math.round((fragileCount / totalDenom) * 100));
  const gapPct = Math.max(0, 100 - resPct - fragPct);

  return `
    <div class="custom-card" style="border-left: 4px solid var(--c-violet); margin-top:8px; padding:14px; background:var(--bg-surface); border-radius:6px;">
      <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:12px;">
        <div style="display:flex; align-items:center; gap:8px;">
          <span style="font-size:20px;">🎯</span>
          <div>
            <div style="font-weight:700; font-size:14px; color:var(--text-main);">MITRE ATT&CK Strategic Posture</div>
            <div style="font-size:11px; color:var(--text-muted);">
              Threat Profile: <strong style="color:var(--c-violet);">${escapeHtml(profileName)}</strong> &bull; ATT&CK v18.1 Enterprise Matrix
            </div>
          </div>
        </div>
        <div style="display:flex; align-items:center; gap:8px;">
          <div style="padding:4px 10px; border-radius:4px; font-weight:800; font-size:13px; color:${scoreColor}; background:${scoreBg}; border:1px solid ${scoreBorder};">
            ${score}% COVERAGE
          </div>
        </div>
      </div>

      <!-- KPI Grid -->
      <div style="display:grid; grid-template-columns: repeat(6, 1fr); gap:8px; margin-bottom:12px;">
        <div class="kpi-card" style="padding:6px 8px; text-align:center;">
          <div style="font-size:11px; color:var(--text-muted);">Covered Techs</div>
          <div style="font-size:16px; font-weight:700; color:var(--c-ok);">${validatedTechniques}</div>
        </div>
        <div class="kpi-card" style="padding:6px 8px; text-align:center;">
          <div style="font-size:11px; color:var(--text-muted);">Evaluated Rules</div>
          <div style="font-size:16px; font-weight:700; color:var(--text-main);">${totalRules}</div>
        </div>
        <div class="kpi-card" style="padding:6px 8px; text-align:center;">
          <div style="font-size:11px; color:var(--text-muted);">Resilient (≥2)</div>
          <div style="font-size:16px; font-weight:700; color:var(--c-sky);">${resilientCount}</div>
        </div>
        <div class="kpi-card" style="padding:6px 8px; text-align:center;">
          <div style="font-size:11px; color:var(--text-muted);">Fragile (SPoF)</div>
          <div style="font-size:16px; font-weight:700; color:${fragileCount > 0 ? 'var(--c-warn)' : 'var(--c-ok)'};">${fragileCount}</div>
        </div>
        <div class="kpi-card" style="padding:6px 8px; text-align:center;">
          <div style="font-size:11px; color:var(--text-muted);">Tactical Vis</div>
          <div style="font-size:16px; font-weight:700; color:var(--c-violet);">${visTactics}/14</div>
        </div>
        <div class="kpi-card" style="padding:6px 8px; text-align:center;">
          <div style="font-size:11px; color:var(--text-muted);">Blind Tactics</div>
          <div style="font-size:16px; font-weight:700; color:${blindTactics.length > 0 ? 'var(--c-danger)' : 'var(--c-ok)'};">${blindTactics.length}</div>
        </div>
      </div>

      <!-- Resilience & Posture Progress Bar -->
      <div style="margin-bottom:12px; background:var(--surface-inset); padding:8px 10px; border-radius:4px; border:1px solid var(--border-color);">
        <div style="display:flex; justify-content:space-between; font-size:11px; margin-bottom:4px;">
          <span style="color:var(--text-muted);">Technique Defense Posture:</span>
          <span style="font-weight:600; color:var(--text-main);">${resilientCount} Resilient &bull; ${fragileCount} Fragile SPoF &bull; ${detectionGapsCount} Gap</span>
        </div>
        <div style="height:6px; background:var(--surface-inset); border-radius:3px; overflow:hidden; display:flex;">
          <div style="width:${resPct}%; background:var(--c-sky-solid);" title="${resilientCount} Resilient (>=2 rules)"></div>
          <div style="width:${fragPct}%; background:var(--c-warn-solid);" title="${fragileCount} Fragile (1 rule)"></div>
          <div style="width:${gapPct}%; background:var(--c-danger-solid);" title="${detectionGapsCount} Detection Gap"></div>
        </div>
      </div>

      <!-- Critical Gaps / Recommendations Section -->
      ${criticalTechniques.length > 0 ? `
        <div style="margin-bottom:10px;">
          <div style="font-size:11px; font-weight:700; color:var(--text-muted); text-transform:uppercase; margin-bottom:6px; display:flex; justify-content:space-between; align-items:center;">
            <span>High-Risk Uncovered Techniques (${criticalTechniques.length})</span>
            <span style="font-size:11px; color:var(--c-danger); font-weight:600;">Priority Defenses Required</span>
          </div>
          <div style="display:flex; flex-direction:column; gap:4px; max-height:160px; overflow-y:auto;">
            ${criticalTechniques.slice(0, 5).map(t => `
              <div style="display:flex; justify-content:space-between; align-items:center; background:var(--c-danger-faint); border:1px solid var(--c-danger-bd); border-radius:4px; padding:5px 8px;">
                <div style="display:flex; align-items:center; gap:6px;">
                  <button ${act("promptMitreTechniqueInspect", t.technique_id || '')} class="badge" style="background:var(--c-danger-bg); color:var(--c-danger); font-size:11px; font-family:var(--font-mono); border:none; cursor:pointer;" title="Click to inspect mapped rules">
                    ${escapeHtml(t.technique_id || '')}
                  </button>
                  <span style="font-size:11.5px; font-weight:600; color:var(--text-main);">${escapeHtml(t.name || '')}</span>
                </div>
                <div style="font-size:11px; color:var(--text-muted);">
                  Risk Weight: <strong style="color:var(--c-warn);">${t.risk_weight || 5}</strong>
                </div>
              </div>
            `).join('')}
          </div>
        </div>
      ` : ''}

      <!-- Interactive Actions -->
      <div style="display:flex; gap:8px; justify-content:flex-end; border-top:1px solid var(--border-color); padding-top:10px; margin-top:8px;">
        <button class="btn-drawer-action" ${act("copyMitreExecutiveReport", profileId)} style="background:var(--c-info-bg); color:var(--c-info); border:1px solid var(--c-info-bd); padding:4px 10px; border-radius:4px; font-size:11px; cursor:pointer;">
          📄 Copy Full Report
        </button>
        <button class="btn-drawer-action" ${act("promptMitreCoverageAudit", "financial_services")} style="background:var(--c-violet-bg); color:var(--c-violet); border:1px solid var(--c-violet-bd); padding:4px 10px; border-radius:4px; font-size:11px; cursor:pointer;">
          🏦 FinServ Profile
        </button>
        <button class="btn-drawer-action" ${act("promptMitreCoverageAudit", "cloud_native")} style="background:var(--c-sky-bg); color:var(--c-sky); border:1px solid var(--c-sky-bd); padding:4px 10px; border-radius:4px; font-size:11px; cursor:pointer;">
          ☁️ Cloud-Native Profile
        </button>
      </div>
    </div>
  `;
}

async function renderTuningDrawer() {
  const container = document.getElementById("drawerContent");
  container.innerHTML = `
    <div style="padding: 12px; border-bottom: 1px solid var(--border-color); display:flex; flex-direction:column; gap:8px;">
      <div style="display:flex; justify-content:space-between; align-items:center;">
        <span style="font-weight:700; font-size:12px; color:var(--text-muted); text-transform:uppercase;">Noisy Detection Rules</span>
        <button id="btnRefreshNoisy" style="background:var(--c-ok-solid); border:none; color:var(--on-solid); padding:4px 10px; border-radius:4px; font-size:11px; font-weight:600; cursor:pointer; display:flex; align-items:center; gap:4px;">
          <span>🔄 Refresh 14d</span>
        </button>
      </div>
      <div style="font-size:11px; color:var(--text-dim); background:var(--surface-inset); padding:6px 8px; border-radius:4px;">
        🎯 <strong>Tuning Agent:</strong> Analyzes high-trigger rules and synthesizes safe multi-factor exclusions.
      </div>
    </div>
    <div id="tuningRuleItems" style="overflow-y:auto; padding:8px;">
      <div style="text-align:center; padding:20px; color:var(--text-dim); font-size:12px;">Loading top noisy rules...</div>
    </div>
  `;

  document.getElementById("btnRefreshNoisy").addEventListener("click", () => renderTuningDrawer());

  try {
    const res = await fetch("/api/tuning/noisy-rules?lookback_days=14&limit=20");
    const data = await res.json();
    const rules = data.rules || [];
    const itemsContainer = document.getElementById("tuningRuleItems");

    if (rules.length === 0) {
      itemsContainer.innerHTML = `
        <div style="text-align:center; padding:30px 15px; color:var(--text-muted); font-size:12.5px;">
          🎉 No high-trigger detection rules detected in 14-day window.
        </div>
      `;
      return;
    }

    itemsContainer.innerHTML = rules.map(r => {
      const isCurated = r.rule_id.startsWith("ur_");
      const typeBadge = isCurated
        ? `<span class="badge" style="background:var(--c-indigo-bg); color:var(--c-indigo); font-size:11px;">CURATED</span>`
        : `<span class="badge" style="background:var(--c-ok-bg); color:var(--c-ok); font-size:11px;">CUSTOMER</span>`;

      return `
        <div class="proposal-card status-open" style="padding:10px; margin-bottom:8px; border-left:3px solid var(--c-indigo);">
          <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:4px;">
            <div style="font-size:12.5px; font-weight:700; color:var(--text-main); overflow:hidden; text-overflow:ellipsis; white-space:nowrap; max-width:180px;" title="${escapeHtml(r.rule_name)}">
              ${escapeHtml(r.rule_name)}
            </div>
            ${typeBadge}
          </div>
          <div style="font-family:var(--font-mono); font-size:11px; color:var(--text-dim); margin-bottom:6px;">
            ${escapeHtml(r.rule_id)}
          </div>
          <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:8px; font-size:11px;">
            <span style="color:var(--c-info); font-weight:700;">${r.detection_count.toLocaleString()} triggers</span>
            <span style="color:var(--text-dim);">${(r.ratio_of_total * 100).toFixed(1)}% of tenant</span>
          </div>
          <div style="display:flex; gap:6px;">
            <button class="btn-approve" style="background:var(--c-indigo-solid); flex:1; padding:4px 8px; font-size:11px;" ${act("promptTuneRule", r.rule_id)}>
              🛡️ Tune Rule
            </button>
            <button class="btn-reject" style="flex:1; padding:4px 8px; font-size:11px;" ${act("promptViewSamples", r.rule_id)}>
              🔍 Samples
            </button>
          </div>
        </div>
      `;
    }).join("");
  } catch (err) {
    const itemsContainer = document.getElementById("tuningRuleItems");
    if (itemsContainer) {
      itemsContainer.innerHTML = `<div style="color:var(--c-danger); font-size:12px; padding:12px;">Failed to load noisy rules: ${escapeHtml(err.message)}</div>`;
    }
  }
}

window.promptTuneRule = async function(ruleId) {
  await switchTopic("detections", "tuning-review");
  const input = document.getElementById("composerInput");
  input.value = `@detection-tuning-agent evaluate and synthesize tuning proposal for ${ruleId}`;
  input.focus();
  try {
    await fetch(`/api/tuning/propose/${ruleId}?lookback_days=14`, { method: "POST" });
    input.value = "";
  } catch (e) {
    console.error("Error proposing tuning:", e);
  }
};

window.promptViewSamples = async function(ruleId) {
  await switchTopic("detections", "tuning-review");
  const input = document.getElementById("composerInput");
  input.value = `@detection-tuning-agent sample correlated detection events for ${ruleId}`;
  input.focus();
};

function tuningDeployButtons(ruleId) {
  return Array.from(document.querySelectorAll('[data-act="deployTuningProposal"]')).filter((b) => {
    try { return JSON.parse(b.dataset.actArgs || "[]")[0] === ruleId; } catch (_) { return false; }
  });
}

window.deployTuningProposal = async function(ruleId, ruleName) {
  const ok = await openActionDialog({
    title: "Deploy noise suppression",
    message: `This writes the exclusion shown in the diff to the live Chronicle rule "${ruleName}". Matching events will stop generating detections for this rule.`,
    confirmLabel: "Deploy to Chronicle",
    variant: "danger",
  });
  if (!ok) return;

  const buttons = tuningDeployButtons(ruleId);
  const labels = buttons.map((b) => b.innerHTML);
  buttons.forEach((b) => { b.disabled = true; b.setAttribute("aria-busy", "true"); b.textContent = "Deploying…"; });
  let deployed = false;
  try {
    const res = await fetch(`/api/tuning/deploy/${encodeURIComponent(ruleId)}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ rule_name: ruleName }),
    });
    if (!res.ok) {
      showToast("error", `Deploy failed for ${ruleName}: ${await describeHttpError(res)}`);
      return;
    }
    const result = await res.json().catch(() => ({}));
    if (result.status === "SUCCESS") {
      deployed = true;
      showToast("success", `Noise suppression deployed for ${ruleName}.${result.message ? " " + result.message : ""}`);
    } else {
      showToast("error", `Deploy failed for ${ruleName}: ${result.message || "unknown error"}`);
    }
  } catch (err) {
    showToast("error", `Deploy failed for ${ruleName}: ${friendlyErrorText(err)}`);
  } finally {
    buttons.forEach((b, i) => {
      b.removeAttribute("aria-busy");
      if (deployed) {
        b.textContent = "✓ Deployed";
      } else {
        b.disabled = false;
        b.innerHTML = labels[i];
      }
    });
  }
};

// --- Message Sending ---
async function handleSendMessage() {
  const input = document.getElementById("composerInput");
  const content = input.value.trim();
  if (!content) return;

  input.value = "";
  closeMentionDropdown();
  await sendChatMessage(content);
}

let tempMessageSeq = 0;

async function sendChatMessage(content) {
  const stream = state.activeStream;
  const topic = state.activeTopic;

  // 1. Optimistically append the operator's message; track this exact card.
  const tempUserMsg = {
    id: `temp-${Date.now()}-${++tempMessageSeq}`,
    stream,
    topic,
    sender_handle: "@operator",
    sender_type: "user",
    content,
    created_at: new Date().toISOString(),
  };
  state.messages.push(tempUserMsg);
  const card = appendMessageToTimeline(tempUserMsg, { forceScroll: true });
  card.classList.add("optimistic-sending");
  card._pendingMsg = tempUserMsg;

  // 2. Show the Slack-style status indicator for the mentioned (or default) agent.
  const mentionMatch = content.match(/@([\w-]+)/);
  const targetAgent = mentionMatch ? `@${mentionMatch[1]}` : "@secops-dispatcher";
  showAgentStatusIndicator(targetAgent, "Reasoning with Gemini and evaluating workflows...", "@operator");

  // 3. Post to backend; reconcile from the response (SSE may also reconcile first).
  let errorText;
  try {
    const res = await fetch("/api/messages", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ stream, topic, content, sender_handle: "@operator" }),
    });
    if (res.ok) {
      const data = await res.json().catch(() => ({}));
      reconcilePendingCard(card, data && data.message);
      return;
    }
    errorText = await readErrorDetail(res);
  } catch (err) {
    errorText = (err && err.message) || String(err);
  }

  if (state.activeStream === stream && state.activeTopic === topic) {
    hideAgentStatusIndicator();
  }
  markMessageFailed(card, errorText);
}

async function readErrorDetail(res) {
  const text = await res.text().catch(() => "");
  try {
    const parsed = JSON.parse(text);
    if (parsed && parsed.detail) return typeof parsed.detail === "string" ? parsed.detail : JSON.stringify(parsed.detail);
  } catch (_) { /* not JSON */ }
  return text || `HTTP ${res.status}`;
}

function findMessageCard(id) {
  if (!id || String(id).startsWith("temp-")) return null;
  const container = document.getElementById("messageTimeline");
  if (!container) return null;
  return Array.from(container.querySelectorAll(".message-card[data-id]")).find((el) => el.dataset.id === String(id)) || null;
}

// Mark an optimistic card as persisted and swap the temp record for the server record.
function reconcilePendingCard(card, savedMsg) {
  if (!card || !card._pendingMsg) return;
  const temp = card._pendingMsg;
  card._pendingMsg = null;
  card.classList.remove("optimistic-sending");
  if (savedMsg && savedMsg.id) {
    card.dataset.id = savedMsg.id;
    const idx = state.messages.indexOf(temp);
    if (idx !== -1) state.messages[idx] = savedMsg;
  }
}

// SSE fallback: match the oldest pending card with identical content.
function reconcilePendingByContent(msg) {
  const container = document.getElementById("messageTimeline");
  if (!container) return false;
  const card = Array.from(container.querySelectorAll(".message-card.optimistic-sending"))
    .find((el) => el._pendingMsg && el._pendingMsg.content === msg.content);
  if (!card) return false;
  reconcilePendingCard(card, msg);
  return true;
}

function markMessageFailed(card, errorText) {
  const temp = card && card._pendingMsg;
  showToast("error", `Message not sent: ${errorText}`);
  if (!card || !temp) return;
  card._pendingMsg = null;
  card.classList.remove("optimistic-sending");
  card.classList.add("send-failed");

  const bar = document.createElement("div");
  bar.className = "msg-send-error";
  bar.setAttribute("role", "alert");
  bar.innerHTML = `
    <span class="msg-send-error-text">Not sent — ${escapeHtml(errorText)}</span>
    <button type="button" class="msg-send-error-btn" data-act="retry">Retry</button>
    <button type="button" class="msg-send-error-btn" data-act="edit">Edit</button>
  `;
  const discard = () => {
    const idx = state.messages.indexOf(temp);
    if (idx !== -1) state.messages.splice(idx, 1);
    removeMessageCard(card);
  };
  bar.querySelector('[data-act="retry"]').addEventListener("click", () => {
    discard();
    sendChatMessage(temp.content);
  });
  bar.querySelector('[data-act="edit"]').addEventListener("click", () => {
    const input = document.getElementById("composerInput");
    discard();
    if (input) {
      input.value = input.value.trim() ? `${temp.content}\n${input.value}` : temp.content;
      input.focus();
    }
  });
  const body = card.querySelector(".msg-body") || card;
  body.appendChild(bar);
}

async function handleClearTopic() {
  const stream = state.activeStream;
  const topic = state.activeTopic;
  const label = stream === "dm" ? `@${topic}` : `#${stream} > ${topic}`;

  const ok = await openActionDialog({
    title: "Clear message history",
    message: `Permanently delete every message in ${label}, including previous agent runs and test output. This can't be undone.`,
    confirmLabel: "Clear history",
    variant: "danger",
  });
  if (!ok) return;

  try {
    const res = await fetch(`/api/messages?stream=${encodeURIComponent(stream)}&topic=${encodeURIComponent(topic)}`, {
      method: "DELETE",
    });

    if (!res.ok) {
      showToast("error", `Couldn't clear ${label}: ${await describeHttpError(res)}`);
      return;
    }

    // Only wipe the view if the operator is still looking at the cleared topic.
    if (state.activeStream === stream && state.activeTopic === topic) {
      state.messages = [];
      hideAgentStatusIndicator();
      renderTimeline();
    }
    loadStreams();
    showToast("success", `Cleared message history in ${label}.`);
  } catch (err) {
    console.error("Failed to clear topic:", err);
    showToast("error", `Couldn't clear ${label}: ${friendlyErrorText(err)}`);
  }
}

// --- Action Dialog (replaces native confirm()/prompt() for HITL actions) ---
/**
 * Opens an accessible modal dialog and resolves with the field values on confirm,
 * or null on cancel / Escape / backdrop click.
 * fields: [{ name, label, type: "text"|"textarea", required, value, placeholder, minLength }]
 */
function openActionDialog({ title, message = "", confirmLabel = "Confirm", variant = "primary", fields = [], bodyHtml = "", showCancel = true }) {
  return new Promise((resolve) => {
    const previouslyFocused = document.activeElement;
    const overlay = document.createElement("div");
    overlay.className = "action-dialog-overlay";
    const titleId = `actionDialogTitle-${Date.now()}`;

    const fieldsHtml = fields.map((f, i) => {
      const id = `actionDialogField-${i}`;
      const req = f.required ? ' required aria-required="true"' : "";
      const minLen = f.minLength ? ` minlength="${f.minLength}"` : "";
      const ph = f.placeholder ? ` placeholder="${escapeHtml(f.placeholder)}"` : "";
      const renderOption = (o) => `<option value="${escapeHtml(o.value)}"${o.value === f.value ? " selected" : ""}${o.disabled ? " disabled" : ""}>${escapeHtml(o.label || o.value)}</option>`;
      let input;
      if (f.type === "textarea") {
        input = `<textarea id="${id}" name="${escapeHtml(f.name)}" rows="3"${req}${minLen}${ph}>${escapeHtml(f.value || "")}</textarea>`;
      } else if (f.type === "select") {
        const body = (f.groups || [{ options: f.options || [] }])
          .filter((g) => g.options && g.options.length)
          .map((g) => g.label
            ? `<optgroup label="${escapeHtml(g.label)}">${g.options.map(renderOption).join("")}</optgroup>`
            : g.options.map(renderOption).join(""))
          .join("");
        input = `<select id="${id}" name="${escapeHtml(f.name)}"${req}>${body}</select>`;
      } else {
        input = `<input id="${id}" name="${escapeHtml(f.name)}" type="text" value="${escapeHtml(f.value || "")}"${req}${minLen}${ph} />`;
      }
      const hint = f.hint ? `<div class="action-dialog-hint" id="${id}-hint">${escapeHtml(f.hint)}</div>` : "";
      return `<div class="action-dialog-field" data-field-wrap="${escapeHtml(f.name)}">
        <label class="action-dialog-label" for="${id}">
          ${escapeHtml(f.label)}${f.required ? ' <span class="action-dialog-req" aria-hidden="true">*</span>' : ' <span class="action-dialog-opt">(optional)</span>'}
        </label>
        ${input}${hint}</div>`;
    }).join("");

    overlay.innerHTML = `
      <form class="action-dialog" role="dialog" aria-modal="true" aria-labelledby="${titleId}" novalidate>
        <h2 id="${titleId}" class="action-dialog-title">${escapeHtml(title)}</h2>
        ${message ? `<p class="action-dialog-message">${escapeHtml(message)}</p>` : ""}
        ${bodyHtml}
        ${fieldsHtml}
        <div class="action-dialog-error" role="alert" hidden></div>
        <div class="action-dialog-actions">
          ${showCancel ? '<button type="button" class="btn btn-secondary" data-action="cancel">Cancel</button>' : ""}
          <button type="submit" class="btn ${variant === "danger" ? "btn-danger" : "btn-primary"}">${escapeHtml(confirmLabel)}</button>
        </div>
      </form>`;

    const form = overlay.querySelector("form");
    const errorEl = overlay.querySelector(".action-dialog-error");

    const close = (result) => {
      document.removeEventListener("keydown", onKey, true);
      overlay.remove();
      if (previouslyFocused && typeof previouslyFocused.focus === "function") previouslyFocused.focus();
      resolve(result);
    };

    const onKey = (e) => {
      if (e.key === "Escape") {
        e.preventDefault();
        e.stopPropagation();
        close(null);
      } else if (e.key === "Tab") {
        // Simple focus trap
        const focusables = Array.from(form.querySelectorAll("input, textarea, select, button")).filter((el) => !el.disabled && !el.hidden && el.offsetParent !== null);
        const first = focusables[0];
        const last = focusables[focusables.length - 1];
        if (e.shiftKey && document.activeElement === first) { e.preventDefault(); last.focus(); }
        else if (!e.shiftKey && document.activeElement === last) { e.preventDefault(); first.focus(); }
      }
    };

    form.addEventListener("submit", (e) => {
      e.preventDefault();
      const values = {};
      for (const f of fields) {
        const el = form.elements[f.name];
        const wrap = el.closest("[data-field-wrap]");
        if (wrap && wrap.hidden) { values[f.name] = ""; continue; }
        const v = (el.value || "").trim();
        if (f.required && !v) {
          errorEl.textContent = `${f.label} is required.`;
          errorEl.hidden = false;
          el.focus();
          return;
        }
        if (f.minLength && v && v.length < f.minLength) {
          errorEl.textContent = `${f.label} must be at least ${f.minLength} characters.`;
          errorEl.hidden = false;
          el.focus();
          return;
        }
        values[f.name] = v;
      }
      close(values);
    });
    fields.forEach((f) => {
      if (typeof f.onChange === "function") {
        const el = form.elements[f.name];
        const fire = () => f.onChange(el.value, form);
        el.addEventListener("change", fire);
        fire();
      }
    });
    const cancelBtn = overlay.querySelector('[data-action="cancel"]');
    if (cancelBtn) cancelBtn.addEventListener("click", () => close(null));
    overlay.addEventListener("mousedown", (e) => { if (e.target === overlay) close(null); });
    document.addEventListener("keydown", onKey, true);

    document.body.appendChild(overlay);
    const firstInput = form.querySelector("input, textarea, select");
    // Destructive confirmations with no inputs start on Cancel so a stray Enter can't fire them.
    const safeDefault = variant === "danger" && !firstInput ? cancelBtn : null;
    (firstInput || safeDefault || form.querySelector('button[type="submit"]')).focus();
    if (firstInput && firstInput.select) firstInput.select();
  });
}

// --- About (#9): build/runtime details moved out of the top bar ---
async function openAboutDialog() {
  let health = null;
  try {
    const res = await fetch("/api/health");
    if (res.ok) health = await res.json();
  } catch (_) { /* rendered as unavailable */ }
  const val = (v) => (v === undefined || v === null || v === "" ? UNKNOWN_METRIC : String(v));
  const connLabel = { connected: "Live", connecting: "Connecting…", disconnected: "Offline — reconnecting" }[state.liveStatus] || UNKNOWN_METRIC;
  const rows = [
    ["Agent runtime", "Google ADK 2"],
    ["Change control", "Human-in-the-loop review — every production mutation requires operator approval"],
    ["Server version", health ? val(health.version) : UNKNOWN_METRIC],
    ["Server status", health ? val(health.status) : "Unreachable"],
    ["Agents registered", health ? val(health.agents_online) : UNKNOWN_METRIC],
    ["Open proposals", health ? val(health.open_proposals) : UNKNOWN_METRIC],
    ["Engine capabilities", health ? val(health.engine_capabilities) : UNKNOWN_METRIC],
    ["Evidence store", health ? val(health.evidence_fabric_store) : UNKNOWN_METRIC],
    ["Event stream", connLabel],
  ];
  const bodyHtml = `<dl class="about-grid">${rows
    .map(([k, v]) => `<dt>${escapeHtml(k)}</dt><dd>${escapeHtml(v)}</dd>`)
    .join("")}</dl>`;
  await openActionDialog({ title: "About Google SecOps Multi-Agent Fleet", bodyHtml, confirmLabel: "Close", showCancel: false });
}
window.openAboutDialog = openAboutDialog;

// --- Proposal Approvals & Rejections ---
async function handleApproveProposal(proposalId) {
  const result = await openActionDialog({
    title: "Approve & apply change",
    message: `Approving ${proposalId} executes a live production mutation in SecOps. This is recorded in the audit trail.`,
    confirmLabel: "Approve & Apply",
    fields: [{ name: "note", label: "Approval note", type: "textarea", placeholder: "Why is this change safe to apply?" }],
  });
  if (!result) return false;

  try {
    const res = await fetch(`/api/proposals/${encodeURIComponent(proposalId)}/approve`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ merged_by: "secops-operator", approval_note: result.note || null }),
    });

    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      showToast("error", `Approval failed: ${err.detail || res.status}`);
      return false;
    }
    showToast("success", `Proposal ${proposalId} approved and merged to production!`);
    await Promise.all([loadProposals(), loadGastownOverview()]);
    return true;
  } catch (err) {
    showToast("error", "Network error approving proposal: " + err);
    return false;
  }
}

async function handleRejectProposal(proposalId) {
  const result = await openActionDialog({
    title: "Reject proposal",
    message: `Rejecting ${proposalId} closes it without applying any change. The reason is sent back to the authoring agent.`,
    confirmLabel: "Reject",
    variant: "danger",
    fields: [{ name: "reason", label: "Rejection reason", type: "textarea", required: true, minLength: 5 }],
  });
  if (!result) return false;
  const reason = result.reason;

  try {
    const res = await fetch(`/api/proposals/${encodeURIComponent(proposalId)}/reject`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ reason: reason, rejected_by: "secops-operator" }),
    });

    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      showToast("error", `Rejection failed: ${err.detail || res.status}`);
      return false;
    }
    showToast("info", `Proposal ${proposalId} rejected.`);
    await Promise.all([loadProposals(), loadGastownOverview()]);
    return true;
  } catch (err) {
    showToast("error", "Network error rejecting proposal: " + err);
    return false;
  }
}

window.handleProposalAction = async function (proposalId, action) {
  if (action === "approve") return handleApproveProposal(proposalId);
  if (action === "reject") return handleRejectProposal(proposalId);
  return false;
};

async function handleDismissTodo(todoId) {
  const result = await openActionDialog({
    title: "Dismiss task",
    message: `Mark ${todoId} as resolved.`,
    confirmLabel: "Dismiss",
    fields: [{ name: "reason", label: "Resolution reason", type: "textarea", required: true, minLength: 5 }],
  });
  if (!result) return;
  const reason = result.reason;

  try {
    const res = await fetch(`/api/todos/${encodeURIComponent(todoId)}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        status: "RESOLVED",
        resolution: `Dismissed by operator: ${reason}`,
        resolved_by: "secops-operator"
      }),
    });
    if (!res.ok) {
      await fetch(`/api/todos/${encodeURIComponent(todoId)}`, { method: "DELETE" });
    }
    showToast("info", `Task ${todoId} dismissed.`);
    await loadGastownOverview();
  } catch (err) {
    showToast("error", "Error dismissing task: " + err);
  }
}
window.handleDismissTodo = handleDismissTodo;

// --- Right Drawer ---
function switchDrawerTab(tab) {
  state.activeDrawerTab = tab;
  const tabProposals = document.getElementById("tabProposals");
  const tabTuning = document.getElementById("tabTuning");
  const tabDecay = document.getElementById("tabDecay");
  const tabFleet = document.getElementById("tabFleet");

  if (tabProposals) tabProposals.className = `drawer-tab ${tab === "proposals" ? "active" : ""}`;
  if (tabTuning) tabTuning.className = `drawer-tab ${tab === "tuning" ? "active" : ""}`;
  if (tabDecay) tabDecay.className = `drawer-tab ${tab === "decay" ? "active" : ""}`;
  if (tabFleet) tabFleet.className = `drawer-tab ${tab === "fleet" ? "active" : ""}`;

  if (tab === "proposals") {
    renderProposalsDrawer();
  } else if (tab === "tuning") {
    renderTuningDrawer();
  } else if (tab === "decay") {
    renderDecayDrawer();
  } else {
    renderFleetDrawer();
  }
}

async function renderIngestionDrawer() {
  const container = document.getElementById("drawerContent");
  container.innerHTML = `
    <div style="padding: 12px; border-bottom: 1px solid var(--border-color); display:flex; flex-direction:column; gap:8px;">
      <div style="display:flex; justify-content:space-between; align-items:center;">
        <span style="font-weight:700; font-size:12px; color:var(--text-muted); text-transform:uppercase;">Ingestion & Normalization</span>
      </div>
      <div style="display:flex; gap:6px;">
        <button id="btnAuditFeedsNow" style="flex:1; background:var(--c-sky-solid); border:none; color:var(--on-solid); padding:5px 8px; border-radius:4px; font-size:11px; font-weight:600; cursor:pointer; display:flex; align-items:center; justify-content:center; gap:4px;">
          <span>📡 Audit Feeds</span>
        </button>
        <button id="btnAuditParsersNow" style="flex:1; background:var(--c-ok-solid); border:none; color:var(--on-solid); padding:5px 8px; border-radius:4px; font-size:11px; font-weight:600; cursor:pointer; display:flex; align-items:center; justify-content:center; gap:4px;">
          <span>🩺 Audit Parsers</span>
        </button>
      </div>
      <div style="font-size:11px; color:var(--text-dim); background:var(--surface-inset); padding:6px 8px; border-radius:4px; margin-top:4px;">
        ⏱️ <strong>Schedules:</strong> Feeds: Every 6h &bull; Parsers: Every 12h
      </div>
    </div>
    <div style="padding: 12px; border-bottom: 1px solid var(--border-color);">
      <div style="font-weight:600; font-size:11.5px; color:var(--text-muted); margin-bottom:6px;">Quick Unparsed Log Diagnostic</div>
      <div style="display:flex; gap:6px;">
        <input id="quickDiagnoseLogType" type="text" placeholder="e.g. CS_EDR" style="flex:1; background:var(--surface-inset-strong); border:1px solid var(--border-color); border-radius:4px; color:var(--on-solid); font-size:11.5px; padding:4px 8px; font-family:var(--font-mono);" />
        <button id="btnQuickDiagnose" style="background:var(--c-violet-solid); border:none; color:var(--on-solid); padding:4px 10px; border-radius:4px; font-size:11px; font-weight:600; cursor:pointer;">Diagnose</button>
      </div>
    </div>
    <div id="ingestionDrawerStatus" style="padding:12px; font-size:11.5px; color:var(--text-dim);">
      Click <strong>Audit Feeds</strong> or <strong>Audit Parsers</strong> to stream live telemetry from Health Hub into the ingestion workspace.
    </div>
  `;

  document.getElementById("btnAuditFeedsNow").addEventListener("click", async () => {
    const btn = document.getElementById("btnAuditFeedsNow");
    btn.innerHTML = "<span>⏳ Auditing...</span>";
    btn.disabled = true;
    try {
      const res = await fetch("/api/feeds/audit?lookback_days=7", { method: "POST" });
      if (!res.ok) throw new Error(await describeHttpError(res));
      await switchTopic("ingestion", "feed-health");
    } catch (e) {
      console.error(e);
      showToast("error", `Feed audit failed: ${e.message}`);
    } finally {
      btn.innerHTML = "<span>📡 Audit Feeds</span>";
      btn.disabled = false;
    }
  });

  document.getElementById("btnAuditParsersNow").addEventListener("click", async () => {
    const btn = document.getElementById("btnAuditParsersNow");
    btn.innerHTML = "<span>⏳ Auditing...</span>";
    btn.disabled = true;
    try {
      const res = await fetch("/api/parsers/audit?lookback_days=7", { method: "POST" });
      if (!res.ok) throw new Error(await describeHttpError(res));
      await switchTopic("ingestion", "parser-drops");
    } catch (e) {
      console.error(e);
      showToast("error", `Parser audit failed: ${e.message}`);
    } finally {
      btn.innerHTML = "<span>🩺 Audit Parsers</span>";
      btn.disabled = false;
    }
  });

  document.getElementById("btnQuickDiagnose").addEventListener("click", async () => {
    const logType = (document.getElementById("quickDiagnoseLogType").value || "").trim();
    if (!logType) return;
    const btn = document.getElementById("btnQuickDiagnose");
    btn.innerHTML = "⏳";
    btn.disabled = true;
    try {
      const res = await fetch(`/api/parsers/${encodeURIComponent(logType)}/diagnose?lookback_hours=168&limit=5`, { method: "POST" });
      if (!res.ok) throw new Error(await describeHttpError(res));
      await switchTopic("ingestion", "parser-drops");
    } catch (e) {
      console.error(e);
      showToast("error", `Parser diagnosis for ${logType} failed: ${e.message}`);
    } finally {
      btn.innerHTML = "Diagnose";
      btn.disabled = false;
    }
  });
}

async function renderDecayDrawer() {
  const container = document.getElementById("drawerContent");
  container.innerHTML = `
    <div style="padding: 12px; border-bottom: 1px solid var(--border-color); display:flex; flex-direction:column; gap:8px;">
      <div style="display:flex; justify-content:space-between; align-items:center;">
        <span style="font-weight:700; font-size:12px; color:var(--text-muted); text-transform:uppercase;">Rule Decay &amp; Health</span>
        <div style="display:flex; gap:6px;">
          <button id="btnAuditRulesNow" style="background:var(--c-ok-solid); border:none; color:var(--on-solid); padding:4px 8px; border-radius:4px; font-size:11px; font-weight:600; cursor:pointer; display:flex; align-items:center; gap:3px;" title="Unified repository audit across custom and curated rules">
            <span>🛡️ Audit Rules</span>
          </button>
          <button id="btnRunSyncNow" style="background:var(--c-indigo-solid); border:none; color:var(--on-solid); padding:4px 8px; border-radius:4px; font-size:11px; font-weight:600; cursor:pointer; display:flex; align-items:center; gap:3px;">
            <span>🔄 Sync 90d</span>
          </button>
        </div>
      </div>
      <div style="font-size:11px; color:var(--text-dim); background:var(--surface-inset); padding:6px 8px; border-radius:4px;">
        ⏱️ <strong>Schedule:</strong> Daily 24h &bull; <span id="decayNextRun">Next: Evaluating</span>
      </div>
    </div>
    <div id="decayQueueItems" style="overflow-y:auto; padding:8px;">
      <div style="text-align:center; padding:20px; color:var(--text-dim); font-size:12px;">Loading decay queue...</div>
    </div>
  `;

  const btnAuditDrawer = document.getElementById("btnAuditRulesNow");
  if (btnAuditDrawer) {
    btnAuditDrawer.addEventListener("click", async () => {
      btnAuditDrawer.innerHTML = "<span>⏳ Auditing...</span>";
      btnAuditDrawer.disabled = true;
      try {
        const res = await fetch("/api/rules/audit?include_curated=true&sync_embeddings=true&lookback_days=90&run_conflict_scan=true", { method: "POST" });
        if (!res.ok) throw new Error(await describeHttpError(res));
        showToast("success", "Rule audit complete.");
        await switchTopic("detections", "decay-review");
        renderDecayDrawer();
      } catch (e) {
        console.error(e);
        showToast("error", `Rule audit failed: ${e.message}`);
      } finally {
        btnAuditDrawer.innerHTML = "<span>🛡️ Audit Rules</span>";
        btnAuditDrawer.disabled = false;
      }
    });
  }

  document.getElementById("btnRunSyncNow").addEventListener("click", async () => {
    const btn = document.getElementById("btnRunSyncNow");
    btn.innerHTML = "<span>⏳ Syncing...</span>";
    btn.disabled = true;
    try {
      const res = await fetch("/api/decay/sync?lookback_days=90", { method: "POST" });
      if (!res.ok) throw new Error(await describeHttpError(res));
      showToast("success", "90-day telemetry sync complete.");
      await switchTopic("detections", "decay-review");
      renderDecayDrawer();
    } catch (e) {
      console.error(e);
      showToast("error", `Telemetry sync failed: ${e.message}`);
    } finally {
      btn.innerHTML = "<span>🔄 Sync 90d</span>";
      btn.disabled = false;
    }
  });

  try {
    const [queueRes, schedRes] = await Promise.all([
      fetch("/api/decay/queue?limit=50"),
      fetch("/api/configs/agents/@detection-decay-agent/schedule"),
    ]);
    const queue = await queueRes.json();
    const sched = await schedRes.json();

    const nextRunEl = document.getElementById("decayNextRun");
    if (nextRunEl && sched.next_run_at) {
      const d = new Date(sched.next_run_at);
      nextRunEl.textContent = `Next: ${d.toLocaleDateString()} ${d.toLocaleTimeString([], {hour: '2-digit', minute:'2-digit'})}`;
    }

    const itemsContainer = document.getElementById("decayQueueItems");
    itemsContainer.innerHTML = "";

    if (!queue || queue.length === 0) {
      itemsContainer.innerHTML = `
        <div style="text-align:center; padding:24px; color:var(--text-dim); font-size:12px;">
          No rules in decay queue.<br><br>
          <button ${act("runTelemetrySync")} style="background:var(--btn-primary-bg); border:none; color:var(--on-solid); padding:6px 12px; border-radius:4px; font-size:11.5px; cursor:pointer;">
            Run Initial 90-Day Telemetry Sync
          </button>
        </div>
      `;
      return;
    }

    queue.forEach(item => {
      const dps = item.dps_score || 0;
      const dpsColor = dps >= 70 ? 'var(--c-danger)' : (dps >= 40 ? 'var(--c-warn)' : 'var(--c-ok)');
      const div = document.createElement("div");
      div.className = "drawer-proposal-item";
      div.style.borderLeft = `3px solid ${dpsColor}`;
      div.innerHTML = `
        <div style="display:flex; justify-content:space-between; align-items:center;">
          <span style="font-weight:700; font-size:12.5px; color:var(--text-main);">${escapeHtml(item.rule_name || item.rule_id)}</span>
          <span style="font-weight:700; font-size:11px; padding:2px 6px; border-radius:4px; background:var(--surface-inset); color:${dpsColor};">
            ${dps} DPS
          </span>
        </div>
        <div style="font-size:11px; color:var(--text-dim); font-family:var(--font-mono); margin:2px 0;">
          ${escapeHtml(item.rule_id)}
        </div>
        <div style="font-size:11px; color:var(--text-muted); display:flex; gap:10px; margin-top:4px;">
          <span>90d Dets: <strong>${item.detection_count_90d || 0}</strong></span>
          <span>Stale: <strong>${item.days_stale || 0}d</strong></span>
          <span>Live: <strong>${item.is_live ? '🟢 Yes' : '⚪ No'}</strong></span>
        </div>
        <div style="margin-top:6px; display:flex; justify-content:flex-end;">
          <button style="background:var(--c-indigo-bg); border:1px solid var(--c-indigo); color:var(--c-indigo); border-radius:4px; padding:2px 8px; font-size:11px; cursor:pointer;" ${act("auditRuleInChat", item.rule_id)}>
            Deep Audit &rarr;
          </button>
        </div>
      `;
      itemsContainer.appendChild(div);
    });

  } catch (err) {
    const itemsContainer = document.getElementById("decayQueueItems");
    if (itemsContainer) {
      itemsContainer.innerHTML = `<div style="color:var(--c-danger); font-size:12px; padding:12px;">Failed to load decay queue: ${escapeHtml(err.message)}</div>`;
    }
  }
}

let drawerProposalFilter = "OPEN";

function renderProposalsDrawer() {
  const container = document.getElementById("drawerContent");
  // loadProposals() refreshes in the background; don't clobber another drawer tab.
  if (!container || state.activeDrawerTab !== "proposals") return;
  container.innerHTML = "";

  const all = Array.isArray(state.proposals) ? state.proposals : [];
  const openCount = all.filter((p) => (p.status || "").toUpperCase() === "OPEN").length;
  const list = drawerProposalFilter === "OPEN"
    ? all.filter((p) => (p.status || "").toUpperCase() === "OPEN")
    : all;

  const filterBar = document.createElement("div");
  filterBar.className = "drawer-filter-bar";
  filterBar.setAttribute("role", "group");
  filterBar.setAttribute("aria-label", "Filter proposals");
  filterBar.innerHTML = `
    <button type="button" class="drawer-filter-chip ${drawerProposalFilter === "OPEN" ? "active" : ""}" data-filter="OPEN" aria-pressed="${drawerProposalFilter === "OPEN"}">Needs review (${openCount})</button>
    <button type="button" class="drawer-filter-chip ${drawerProposalFilter === "ALL" ? "active" : ""}" data-filter="ALL" aria-pressed="${drawerProposalFilter === "ALL"}">All (${all.length})</button>
  `;
  filterBar.querySelectorAll("[data-filter]").forEach((btn) => {
    btn.addEventListener("click", () => {
      drawerProposalFilter = btn.dataset.filter;
      renderProposalsDrawer();
    });
  });
  container.appendChild(filterBar);

  if (list.length === 0) {
    const empty = document.createElement("div");
    empty.className = "drawer-empty";
    empty.textContent = drawerProposalFilter === "OPEN"
      ? (all.length ? "Nothing waiting for review." : "No proposals yet.")
      : "No proposals yet.";
    container.appendChild(empty);
    return;
  }

  list.forEach((p) => {
    const status = String(p.status || "UNKNOWN").toUpperCase();
    const item = document.createElement("button");
    item.type = "button";
    item.className = "drawer-proposal-item";
    item.title = status === "OPEN" ? "Review diff and approve or reject" : "View proposal details";
    item.innerHTML = `
      <div class="drawer-prop-title">${escapeHtml(p.title || p.id || "Untitled proposal")}</div>
      <div class="drawer-prop-sub">
        <span>${escapeHtml(p.subsystem || "—")} &bull; ${escapeHtml(p.action_type || "—")}</span>
        <span class="badge badge-${escapeHtml(status.toLowerCase())}">${escapeHtml(status)}</span>
      </div>
    `;
    item.addEventListener("click", () => openGastownDiffModal(p.id));
    container.appendChild(item);
  });
}

let drawerFleetFilter = "";

function renderFleetDrawer() {
  const container = document.getElementById("drawerContent");
  container.innerHTML = "";

  const total = Array.isArray(state.agents) ? state.agents.length : 0;
  const header = document.createElement("div");
  header.style.padding = "10px 12px 8px";
  header.style.borderBottom = "1px solid var(--border-color)";
  header.innerHTML = `
    <div style="font-size:11px; font-weight:700; color:var(--text-muted); text-transform:uppercase; margin-bottom:6px; display:flex; justify-content:space-between; align-items:center;">
      <span>Fleet Roster</span>
      <span style="font-size:11px; background:var(--bg-tertiary); padding:1px 6px; border-radius:8px;">${total} Online</span>
    </div>
    <input
      type="text"
      id="drawerFleetSearchInput"
      placeholder="Filter fleet roster..."
      value="${escapeHtml(drawerFleetFilter)}"
      style="width:100%; box-sizing:border-box; background:var(--bg-secondary); border:1px solid var(--border-color); border-radius:4px; padding:4px 8px; font-size:11.5px; color:var(--text-main); outline:none;"
    />
  `;
  container.appendChild(header);

  const searchInput = header.querySelector("#drawerFleetSearchInput");
  if (searchInput) {
    searchInput.addEventListener("input", (e) => {
      drawerFleetFilter = e.target.value || "";
      renderFleetDrawerItems();
    });
  }

  const listContainer = document.createElement("div");
  listContainer.id = "drawerFleetItemsContainer";
  container.appendChild(listContainer);

  renderFleetDrawerItems();
}

function renderFleetDrawerItems() {
  const listContainer = document.getElementById("drawerFleetItemsContainer");
  if (!listContainer) return;
  listContainer.innerHTML = "";

  const query = (drawerFleetFilter || "").trim().toLowerCase();
  const filtered = (state.agents || []).filter((a) => {
    if (!query) return true;
    const handle = (a.handle || "").toLowerCase();
    const name = (a.name || "").toLowerCase();
    const role = (a.role || "").toLowerCase();
    const desc = (a.description || "").toLowerCase();
    const subsystem = (a.subsystem || "").toLowerCase();
    const tools = (a.capabilities || []).some((c) => c.toLowerCase().includes(query));
    return (
      handle.includes(query) ||
      name.includes(query) ||
      role.includes(query) ||
      desc.includes(query) ||
      subsystem.includes(query) ||
      tools
    );
  });

  if (filtered.length === 0) {
    listContainer.innerHTML = `
      <div style="text-align:center; padding:24px 12px; color:var(--text-dim); font-size:12px;">
        No agents found matching "${escapeHtml(query)}".
      </div>
    `;
    return;
  }

  filtered.forEach((a) => {
    const item = document.createElement("div");
    item.className = "drawer-proposal-item";
    item.innerHTML = `
      <div style="font-weight:700; font-size:13px; color:var(--text-accent);">${escapeHtml(a.handle)}</div>
      <div style="font-size:12px; font-weight:600; color:var(--text-main); margin: 2px 0;">${escapeHtml(a.role)}</div>
      <div style="font-size:11.5px; color:var(--text-muted); margin-bottom:6px;">${escapeHtml(a.description)}</div>
      <div style="font-size:11px; color:var(--text-dim); display:flex; justify-content:space-between; align-items:center;">
        <span>Capabilities: <strong>${a.capabilities.length}</strong></span>
        <span>Subsystem: <code>${escapeHtml(a.subsystem || "general")}</code></span>
      </div>
    `;
    listContainer.appendChild(item);
  });
}

// --- Helpers ---
const NEAR_BOTTOM_PX = 80;

function isNearBottom(el) {
  if (!el) return true;
  return el.scrollHeight - el.scrollTop - el.clientHeight <= NEAR_BOTTOM_PX;
}

let newMessagesCount = 0;

function bumpNewMessagesPill() {
  const pill = document.getElementById("newMessagesPill");
  if (!pill) return;
  newMessagesCount += 1;
  pill.textContent = `${newMessagesCount} new message${newMessagesCount === 1 ? "" : "s"} ↓`;
  pill.hidden = false;
}

function resetNewMessagesPill() {
  newMessagesCount = 0;
  const pill = document.getElementById("newMessagesPill");
  if (pill) pill.hidden = true;
}

const COMPOSER_MAX_HEIGHT = 200;

function autosizeComposer(el) {
  if (!el || !el.offsetParent) return; // hidden: measure when visible
  el.style.height = "auto";
  const borders = el.offsetHeight - el.clientHeight;
  const needed = el.scrollHeight + borders;
  el.style.height = `${Math.min(needed, COMPOSER_MAX_HEIGHT)}px`;
  el.style.overflowY = needed > COMPOSER_MAX_HEIGHT ? "auto" : "hidden";
}

function setupComposerAutosize(el) {
  if (!el) return;
  // Many features prefill the composer via `input.value = ...`; intercept the
  // setter on this element so every programmatic change resizes too.
  const desc = Object.getOwnPropertyDescriptor(HTMLTextAreaElement.prototype, "value");
  if (desc && desc.get && desc.set) {
    Object.defineProperty(el, "value", {
      configurable: true,
      get() { return desc.get.call(this); },
      set(v) { desc.set.call(this, v); autosizeComposer(this); },
    });
  }
  el.addEventListener("input", () => autosizeComposer(el));
  el.addEventListener("focus", () => autosizeComposer(el));
  window.addEventListener("resize", () => autosizeComposer(el));
}

function scrollToBottom(smooth = false) {
  const el = document.getElementById("messageTimeline");
  if (!el) return;
  requestAnimationFrame(() => {
    el.scrollTop = el.scrollHeight;
    const lastChild = el.lastElementChild;
    if (lastChild && typeof lastChild.scrollIntoView === "function") {
      lastChild.scrollIntoView({ behavior: smooth ? "smooth" : "auto", block: "end" });
    }
  });
  setTimeout(() => {
    if (el) el.scrollTop = el.scrollHeight;
  }, 50);
}

/**
 * Declarative click actions for rendered HTML (replaces inline onclick=).
 * Usage in templates: <button ${act("openGastownDiffModal", p.id)}>…</button>
 * Emits data-act / data-act-args attributes; a single delegated listener
 * (setupActions) looks the name up in ACTIONS and calls it with the args.
 * Args are JSON-encoded then HTML-escaped, so no value is ever evaluated as JS.
 * The innermost [data-act] wins, so buttons inside clickable cards don't
 * need event.stopPropagation().
 */
function act(name, ...args) {
  const argAttr = args.length
    ? ` data-act-args="${escapeHtml(JSON.stringify(args.map((a) => (a == null ? "" : a))))}"`
    : "";
  return `data-act="${name}"${argAttr}`;
}

const ACTIONS = {
  // Small UI helpers that used to be inline multi-statement handlers.
  toggleDisplay(id) {
    const el = document.getElementById(id);
    if (el) el.style.display = el.style.display === "none" ? "block" : "none";
  },
  async copyText(text, message) {
    try {
      await navigator.clipboard.writeText(text);
      showToast("success", message || "Copied to clipboard");
    } catch (e) {
      showToast("error", "Copy failed — clipboard unavailable");
    }
  },
  openFinopsDashboard() {
    switchView("ingestion");
    switchIngestionSubtab("finops");
    fetchFinopsData();
  },
  runTelemetrySync() {
    document.getElementById("btnRunSyncNow")?.click();
  },
  useSuggestedPrompt(text) {
    const input = document.getElementById("composerInput");
    if (!input) return;
    input.value = text;
    input.focus();
    if (typeof input.setSelectionRange === "function") input.setSelectionRange(text.length, text.length);
  },
};

// Anything not in ACTIONS resolves to the (existing) named function, so
// templates can reference handlers defined anywhere in this file.
const ACTION_FNS = {
  promptRemediateRule: () => promptRemediateRule,
  auditRuleInChat: () => auditRuleInChat,
  deployTuningProposal: () => window.deployTuningProposal,
  clearSocQueueFilters: () => window.clearSocQueueFilters,
  promptTuneRule: () => window.promptTuneRule,
  promptViewSamples: () => window.promptViewSamples,
  triggerCrossAgentHandoff: () => triggerCrossAgentHandoff,
  promptRuleConflictAudit: () => promptRuleConflictAudit,
  promptRuleConflictConsolidate: () => promptRuleConflictConsolidate,
  promptRuleDecayInvestigate: () => promptRuleDecayInvestigate,
  promptRuleSyntaxFix: () => promptRuleSyntaxFix,
  promptMitreTechniqueInspect: () => promptMitreTechniqueInspect,
  copyMitreExecutiveReport: () => copyMitreExecutiveReport,
  promptMitreCoverageAudit: () => promptMitreCoverageAudit,
  switchTopicAndChat: () => window.switchTopicAndChat,
  viewSocIssueDetail: () => viewSocIssueDetail,
  handleDismissTodo: () => handleDismissTodo,
  openGastownDiffModal: () => openGastownDiffModal,
  handleProposalAction: () => window.handleProposalAction,
  handleAckEscalation: () => handleAckEscalation,
  triggerGastownAgentPatrol: () => triggerGastownAgentPatrol,
  triggerGastownPatrolAll: () => triggerGastownPatrolAll,
  handleClaimSocIssue: () => handleClaimSocIssue,
  handleReleaseSocIssue: () => handleReleaseSocIssue,
  handleDecideSocIssue: () => handleDecideSocIssue,
  closeSocIssueModal: () => closeSocIssueModal,
};

function resolveAction(name) {
  if (Object.prototype.hasOwnProperty.call(ACTIONS, name)) return ACTIONS[name];
  if (Object.prototype.hasOwnProperty.call(ACTION_FNS, name)) return ACTION_FNS[name]();
  return null;
}

function setupActions() {
  document.addEventListener("click", (e) => {
    const el = e.target instanceof Element ? e.target.closest("[data-act]") : null;
    if (!el || el.disabled) return;
    const fn = resolveAction(el.dataset.act);
    if (typeof fn !== "function") {
      console.warn("Unknown data-act action:", el.dataset.act);
      return;
    }
    let args = [];
    try {
      args = el.dataset.actArgs ? JSON.parse(el.dataset.actArgs) : [];
    } catch (err) {
      console.error("Bad data-act-args on", el, err);
      return;
    }
    Promise.resolve()
      .then(() => fn(...args))
      .catch((err) => {
        console.error(`Action ${el.dataset.act} failed:`, err);
        showToast("error", `Action failed: ${err?.message || err}`);
      });
  });
}

function escapeHtml(str) {
  if (!str) return "";
  return String(str)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#039;");
}

function formatTime(ts) {
  if (!ts) return "Recent";
  try {
    return new Date(ts).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
  } catch (e) {
    return String(ts);
  }
}


const ICONS = {
  check: `<svg class="icon-svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round" style="color:var(--c-ok);width:14px;height:14px;display:inline-block;vertical-align:-2px;"><polyline points="20 6 9 17 4 12"></polyline></svg>`,
  cross: `<svg class="icon-svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round" style="color:var(--c-danger);width:14px;height:14px;display:inline-block;vertical-align:-2px;"><line x1="18" y1="6" x2="6" y2="18"></line><line x1="6" y1="6" x2="18" y2="18"></line></svg>`,
  zap: `<svg class="icon-svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round" style="color:var(--c-warn);width:14px;height:14px;display:inline-block;vertical-align:-2px;"><polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2"></polygon></svg>`,
  shield: `<svg class="icon-svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="color:var(--c-info);width:14px;height:14px;display:inline-block;vertical-align:-2px;"><path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"></path></svg>`,
};

function replaceEmojiGlyphs(html) {
  if (!html) return "";
  return html
    .replace(/\u2705|✅/g, ICONS.check)
    .replace(/\u274c|❌/g, ICONS.cross)
    .replace(/\u26a1|⚡/g, ICONS.zap)
    .replace(/\ud83d\ude80|🚀/g, ICONS.zap)
    .replace(/\u2795|➕/g, '<span style="color:var(--c-danger);font-weight:700;">+</span>');
}

function formatMarkdown(text) {
  if (!text) return "";

  // 1. Try marked.js + DOMPurify if available in browser
  if (typeof marked !== "undefined" && typeof marked.parse === "function") {
    try {
      if (typeof marked.setOptions === "function") {
        marked.setOptions({
          gfm: true,
          breaks: false,
          headerIds: false,
          mangle: false,
        });
      }
      const rawHtml = marked.parse(text);
      let cleanHtml = rawHtml;
      if (typeof DOMPurify !== "undefined" && typeof DOMPurify.sanitize === "function") {
        cleanHtml = DOMPurify.sanitize(rawHtml, {
          ADD_ATTR: ['target', 'rel'],
        });
      }
      return replaceEmojiGlyphs(cleanHtml);
    } catch (e) {
      console.warn("marked.parse encountered error, falling back:", e);
    }
  }

  // 2. Intelligent Built-in Fallback Markdown Parser
  return replaceEmojiGlyphs(fallbackFormatMarkdown(text));
}

function fallbackFormatMarkdown(text) {
  if (!text) return "";
  const lines = text.split("\n");
  const output = [];
  let inCode = false;
  let codeBuffer = [];
  let inTable = false;
  let tableRows = [];
  let inList = false;
  let listType = "ul";

  function closeList() {
    if (inList) {
      output.push(`</${listType}>`);
      inList = false;
    }
  }

  function closeTable() {
    if (inTable) {
      if (tableRows.length >= 2) {
        let tableHtml = "<table>";
        // Header
        const headerCols = tableRows[0].split("|").map(s => s.trim()).filter((s, i, a) => !(i === 0 && s === "") && !(i === a.length - 1 && s === ""));
        tableHtml += "<thead><tr>";
        headerCols.forEach(col => {
          tableHtml += `<th>${inlineFormat(col)}</th>`;
        });
        tableHtml += "</tr></thead><tbody>";

        // Body rows (skip separator at index 1)
        for (let r = 2; r < tableRows.length; r++) {
          const cols = tableRows[r].split("|").map(s => s.trim()).filter((s, i, a) => !(i === 0 && s === "") && !(i === a.length - 1 && s === ""));
          tableHtml += "<tr>";
          cols.forEach(c => {
            tableHtml += `<td>${inlineFormat(c)}</td>`;
          });
          tableHtml += "</tr>";
        }
        tableHtml += "</tbody></table>";
        output.push(tableHtml);
      }
      inTable = false;
      tableRows = [];
    }
  }

  function inlineFormat(str) {
    if (!str) return "";
    let s = str
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;");
    s = s.replace(/`([^`]+)`/g, "<code>$1</code>");
    s = s.replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>");
    s = s.replace(/\*([^*]+)\*/g, "<em>$1</em>");
    s = s.replace(/\[([^\]]+)\]\(([^)]+)\)/g, '<a href="$2" target="_blank" rel="noopener">$1</a>');
    return s;
  }

  for (let i = 0; i < lines.length; i++) {
    const line = lines[i];

    // Code blocks
    if (line.trim().startsWith("```")) {
      closeList();
      closeTable();
      if (!inCode) {
        inCode = true;
        codeBuffer = [];
      } else {
        inCode = false;
        output.push(`<pre><code>${inlineFormat(codeBuffer.join("\n"))}</code></pre>`);
        codeBuffer = [];
      }
      continue;
    }
    if (inCode) {
      codeBuffer.push(line);
      continue;
    }

    // Table rows
    const trimmed = line.trim();
    if (trimmed.startsWith("|") && trimmed.endsWith("|")) {
      closeList();
      inTable = true;
      tableRows.push(trimmed);
      continue;
    } else {
      closeTable();
    }

    // Horizontal rule
    if (/^(?:---|\*\*\*|___)\s*$/.test(trimmed)) {
      closeList();
      output.push("<hr>");
      continue;
    }

    // Headings
    if (/^#### (.*)$/.test(trimmed)) {
      closeList();
      output.push(`<h4>${inlineFormat(trimmed.slice(5))}</h4>`);
      continue;
    }
    if (/^### (.*)$/.test(trimmed)) {
      closeList();
      output.push(`<h3>${inlineFormat(trimmed.slice(4))}</h3>`);
      continue;
    }
    if (/^## (.*)$/.test(trimmed)) {
      closeList();
      output.push(`<h2>${inlineFormat(trimmed.slice(3))}</h2>`);
      continue;
    }
    if (/^# (.*)$/.test(trimmed)) {
      closeList();
      output.push(`<h1>${inlineFormat(trimmed.slice(2))}</h1>`);
      continue;
    }

    // Bullet lists
    const ulMatch = line.match(/^(\s*)[\-\*\+]\s+(.*)$/);
    if (ulMatch) {
      if (!inList || listType !== "ul") {
        closeList();
        output.push("<ul>");
        inList = true;
        listType = "ul";
      }
      output.push(`<li>${inlineFormat(ulMatch[2])}</li>`);
      continue;
    }

    // Numbered lists
    const olMatch = line.match(/^(\s*)\d+\.\s+(.*)$/);
    if (olMatch) {
      if (!inList || listType !== "ol") {
        closeList();
        output.push("<ol>");
        inList = true;
        listType = "ol";
      }
      output.push(`<li>${inlineFormat(olMatch[2])}</li>`);
      continue;
    }

    closeList();

    // Blockquotes
    if (trimmed.startsWith("> ")) {
      output.push(`<blockquote>${inlineFormat(trimmed.slice(2))}</blockquote>`);
      continue;
    }

    // Empty lines
    if (trimmed === "") {
      continue;
    }

    // Regular paragraphs
    output.push(`<p>${inlineFormat(trimmed)}</p>`);
  }

  closeList();
  closeTable();
  return output.join("\n");
}

function formatUnifiedDiff(diffText) {
  if (!diffText) return "";
  const lines = diffText.split("\n");
  return lines.map((l) => {
    let cls = "diff-line";
    if (l.startsWith("+") && !l.startsWith("+++")) cls += " add";
    else if (l.startsWith("-") && !l.startsWith("---")) cls += " del";
    else if (l.startsWith("@@")) cls += " hunk";
    return `<div class="${cls}">${escapeHtml(l)}</div>`;
  }).join("");
}

// ====================================================================
// Toast Notification System
// ====================================================================
// Errors stay until dismissed; everything else auto-dismisses (paused while hovered/focused).
// Pass duration = 0 to make any toast sticky.
const TOAST_MAX_VISIBLE = 5;

function showToast(type, message, duration) {
  const container = document.getElementById("toastContainer");
  if (!container) return;
  if (duration === undefined) duration = type === "error" ? 0 : 4500;

  const toast = document.createElement("div");
  toast.className = `toast toast-${type}`;
  // Errors interrupt screen readers; others are announced politely via the container's live region.
  if (type === "error") toast.setAttribute("role", "alert");
  const icon = type === "success" ? "✅" : type === "error" ? "❌" : type === "warning" ? "⚠️" : "ℹ️";
  toast.innerHTML = `
    <span class="toast-icon" aria-hidden="true">${icon}</span>
    <span class="toast-message">${escapeHtml(message)}</span>`;
  const closeBtn = document.createElement("button");
  closeBtn.type = "button";
  closeBtn.className = "toast-close";
  closeBtn.setAttribute("aria-label", "Dismiss notification");
  closeBtn.textContent = "×";
  toast.appendChild(closeBtn);

  let timer = null;
  const dismiss = () => {
    if (toast._dismissed) return;
    toast._dismissed = true;
    clearTimeout(timer);
    toast.style.opacity = "0";
    setTimeout(() => toast.remove(), 250);
  };
  const arm = () => {
    if (duration > 0 && !toast._dismissed) timer = setTimeout(dismiss, duration);
  };
  closeBtn.addEventListener("click", dismiss);
  toast.addEventListener("mouseenter", () => clearTimeout(timer));
  toast.addEventListener("mouseleave", arm);
  toast.addEventListener("focusin", () => clearTimeout(timer));
  toast.addEventListener("focusout", arm);

  container.appendChild(toast);
  // Cap the stack: drop the oldest non-error toasts first, then oldest overall.
  const live = Array.from(container.children).filter((t) => !t._dismissed);
  if (live.length > TOAST_MAX_VISIBLE) {
    const victim = live.find((t) => !t.classList.contains("toast-error")) || live[0];
    if (victim && victim !== toast) {
      victim._dismissed = true;
      victim.remove();
    }
  }
  arm();
  return dismiss;
}

async function describeHttpError(res) {
  let detail = "";
  try {
    const data = await res.clone().json();
    detail = data && (data.detail || data.error || data.message);
    if (detail && typeof detail !== "string") detail = JSON.stringify(detail);
  } catch (_) { /* non-JSON body */ }
  if (res.status === 404 && !detail) return "endpoint not available on this server (404)";
  return detail ? `${detail} (HTTP ${res.status})` : `HTTP ${res.status}${res.statusText ? " " + res.statusText : ""}`;
}

// ====================================================================
// Load errors with Retry (replaces console-only catch blocks)
// ====================================================================
async function fetchJsonOrThrow(url, opts) {
  const res = await fetch(url, opts);
  if (!res.ok) throw new Error(await describeHttpError(res));
  return res.json();
}

function friendlyErrorText(err) {
  const msg = (err && err.message) || String(err || "");
  // fetch() rejects with a bare TypeError when the server is down or the network drops.
  if (err instanceof TypeError || /failed to fetch|networkerror|load failed/i.test(msg)) {
    return "Server unreachable. Check the fleet server is running, then retry.";
  }
  return msg || "Unknown error";
}

/**
 * Replaces `target`'s content with an inline error + Retry button.
 * Pass `colspan` when `target` is a <tbody>. `retry` may return a promise.
 */
function showLoadError(target, { title, error, retry, colspan } = {}) {
  if (!target) return;
  const inner = `
    <div class="load-error" role="alert">
      <span class="load-error-icon" aria-hidden="true">⚠</span>
      <div class="load-error-text">
        <strong>${escapeHtml(title || "Couldn't load this section")}</strong>
        <span class="load-error-detail">${escapeHtml(friendlyErrorText(error))}</span>
      </div>
      ${typeof retry === "function" ? '<button type="button" class="btn btn-sm btn-secondary load-error-retry">Retry</button>' : ""}
    </div>`;
  target.innerHTML = colspan ? `<tr><td colspan="${colspan}" class="load-error-cell">${inner}</td></tr>` : inner;
  const btn = target.querySelector(".load-error-retry");
  if (!btn) return;
  btn.addEventListener("click", async () => {
    btn.disabled = true;
    btn.textContent = "Retrying…";
    try {
      await retry();
    } finally {
      // Still in the DOM means the retry failed again without re-rendering.
      if (btn.isConnected) {
        btn.disabled = false;
        btn.textContent = "Retry";
      }
    }
  });
}

// ====================================================================
// Empty chat state: suggested prompts per topic
// ====================================================================
// Keyed by "stream/topic". Each prompt mentions the agent that owns that work,
// so sending it routes straight there instead of via the dispatcher.
const TOPIC_PROMPTS = {
  "general/dispatcher": [
    ["@secops-dispatcher", "What needs my attention this shift?"],
    ["@secops-dispatcher", "Which agent should investigate a sudden drop in ingested events?"],
    ["@secops-dispatcher", "Summarize open proposals awaiting my review"],
  ],
  "general/announcements": [
    ["@secops-dispatcher", "Summarize fleet activity from the last 24 hours"],
  ],
  "detections/rule-proposals": [
    ["@yaral-optimizer", "Find rules with Cartesian joins or unbounded match windows and propose fixes"],
    ["@yaral-optimizer", "Review the slowest rules and suggest optimizations"],
  ],
  "detections/decay-review": [
    ["@detection-decay-agent", "Audit rules that haven't produced a detection in 30 days"],
    ["@detection-decay-agent", "Which rules are broken or failing to compile?"],
  ],
  "detections/rule-conflicts": [
    ["@rule-conflict-agent", "Find duplicate or overlapping detection rules"],
    ["@rule-conflict-agent", "Which rules contradict each other's exclusions?"],
  ],
  "detections/performance-alerts": [
    ["@rule-troubleshooter", "Which rules hit execution errors or timeouts this week?"],
    ["@rule-troubleshooter", "Diagnose rules being throttled by resource limits"],
  ],
  "detections/triage": [
    ["@detection-tuning-agent", "Which rules generate the most alerts, and what can be tuned?"],
    ["@detection-tuning-agent", "Find benign admin activity that's triggering noisy rules"],
  ],
  "ingestion/feed-health": [
    ["@feed-agent", "Audit all feeds for failures and latency over SLA"],
    ["@feed-agent", "Which push feeds have gone silent?"],
    ["@feed-agent", "Are we hitting ingestion quota rejections?"],
  ],
  "ingestion/parser-drops": [
    ["@parser-doctor", "Which log types have the highest parser drop rates?"],
    ["@parser-doctor", "Check for parser version drift or extension conflicts"],
  ],
  "testing/logjammer-replays": [
    ["@logjammer-agent", "Replay test events for a rule and confirm it fires"],
  ],
  "testing/benchmark-runs": [
    ["@logjammer-agent", "Measure end-to-end ingestion latency with a test replay"],
  ],
  "identity/access-audits": [
    ["@identity-governor", "Who holds Chronicle admin roles?"],
    ["@identity-governor", "List custom roles that include chronicle.* permissions"],
  ],
  "identity/service-accounts": [
    ["@identity-governor", "Which service accounts have Chronicle access?"],
  ],
  "soar/case-escalations": [
    ["@playbook-decay-agent", "Which playbooks failed on escalated cases this week?"],
  ],
  "soar/playbook-runs": [
    ["@playbook-decay-agent", "Summarize playbook execution failures from the last 30 days"],
  ],
  "soar/playbook-health": [
    ["@playbook-decay-agent", "Audit playbooks for resilience and execution health"],
  ],
  "analytics/sql-queries": [
    ["@sql-analyst", "Top 10 log types by event volume in the last 24 hours"],
    ["@sql-analyst", "Count failed logins by user over the last 7 days"],
  ],
  "analytics/reports": [
    ["@sql-analyst", "Daily event volume by log type for the last week"],
  ],
  "analytics/udm-aggregations": [
    ["@sql-analyst", "Top source IPs by event count in the last 24 hours"],
  ],
  "threat_intel/mitre-coverage": [
    ["@mitre-attack-agent", "Assess our ATT&CK coverage against the global baseline"],
    ["@mitre-attack-agent", "Which tactics have no enabled detections?"],
  ],
  "threat_intel/threat-profiles": [
    ["@mitre-attack-agent", "Assess coverage for the financial services threat profile"],
  ],
  "threat_intel/blind-spots": [
    ["@mitre-attack-agent", "Find techniques we have telemetry for but no detections"],
  ],
};

function agentKnown(handle) {
  // Before /api/agents loads, don't hide anything.
  if (!Array.isArray(state.agents) || state.agents.length === 0) return true;
  return state.agents.some((a) => a.handle === handle);
}

// Returns [{ text, agent }] where `text` is what goes into the composer.
function suggestedPromptsFor(stream, topic) {
  if (stream === "dm") {
    const handle = topic.startsWith("@") ? topic : `@${topic}`;
    const own = Object.values(TOPIC_PROMPTS).flat().filter(([h]) => h === handle).map(([, t]) => t);
    const texts = own.length ? own.slice(0, 3) : ["What can you help me with?", "What have you found recently?"];
    return texts.map((text) => ({ text, agent: handle }));
  }
  let pairs = TOPIC_PROMPTS[`${stream}/${topic}`];
  if (!pairs) {
    // Custom topic: offer the agent that defaults to it, else the dispatcher.
    const owner = (state.agents || []).find((a) => a.default_stream === stream && a.default_topic === topic);
    pairs = owner
      ? [[owner.handle, "What can you help me with in this topic?"]]
      : [["@secops-dispatcher", `Which agent handles ${topic.replace(/-/g, " ")}?`]];
  }
  return pairs.filter(([h]) => agentKnown(h)).map(([agent, t]) => ({ text: `${agent} ${t}`, agent }));
}

function renderEmptyTimeline(stream, topic) {
  const isDm = stream === "dm";
  const where = isDm
    ? `your direct messages with <strong>${escapeHtml(topic)}</strong>`
    : `<strong>#${escapeHtml(stream)} › ${escapeHtml(topic)}</strong>`;
  const prompts = suggestedPromptsFor(stream, topic);
  const chips = prompts.map((p) => {
    const label = isDm ? p.text : p.text.slice(p.agent.length + 1);
    return `<li><button type="button" class="suggested-prompt" ${act("useSuggestedPrompt", p.text)}>
        ${isDm ? "" : `<span class="suggested-prompt-agent">${escapeHtml(p.agent)}</span>`}
        <span class="suggested-prompt-text">${escapeHtml(label)}</span>
      </button></li>`;
  }).join("");
  return `
    <div class="timeline-empty">
      <div class="timeline-empty-icon" aria-hidden="true">
        <svg class="ui-icon" viewBox="0 0 24 24" width="28" height="28" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/></svg>
      </div>
      <p class="timeline-empty-title">No messages yet in ${where}.</p>
      ${chips ? `
        <p class="timeline-empty-sub">Try one of these. It goes into the message box so you can edit it before sending.</p>
        <ul class="suggested-prompts" aria-label="Suggested prompts">${chips}</ul>` : ""}
      <p class="timeline-empty-hint">${isDm ? "Messages here go straight to this agent." : "Type <kbd>@</kbd> to mention any agent. Messages without a mention go to the dispatcher."}</p>
    </div>`;
}

// ====================================================================
// Quick switcher (Ctrl/Cmd+K): topics, DMs, agents, pages
// ====================================================================
const RECENT_CHANNELS_KEY = "secops_recent_channels_v1";
const RECENT_CHANNELS_MAX = 8;

function loadRecentChannels() {
  try {
    const v = JSON.parse(localStorage.getItem(RECENT_CHANNELS_KEY));
    return Array.isArray(v) ? v : [];
  } catch (_) {
    return [];
  }
}

function recordRecentChannel(stream, topic) {
  const key = channelKey(stream, topic);
  const list = loadRecentChannels().filter((k) => k !== key);
  list.unshift(key);
  try { localStorage.setItem(RECENT_CHANNELS_KEY, JSON.stringify(list.slice(0, RECENT_CHANNELS_MAX))); } catch (_) { /* quota / private mode */ }
}

const IS_MAC = typeof navigator !== "undefined" && /Mac|iPhone|iPad/.test(navigator.platform || navigator.userAgent || "");

function quickSwitcherItems() {
  const items = [];
  const go = (view) => () => switchView(view);
  const dash = (sub) => () => { switchView("dashboards"); switchIngestionSubtab(sub); };
  const pages = [
    ["Fleet Chat", "", go("chat")],
    ["Actions: Kanban board", "Proposals and tasks by state", () => openActionsSubtab("kanban")],
    ["Actions: Work queue & leases", "", () => openActionsSubtab("work_queue")],
    ["Actions: Work packages", "", () => openActionsSubtab("convoys")],
    ["Actions: Change queue", "Proposals awaiting merge", () => openActionsSubtab("refinery")],
    ["Actions: Escalations", "", () => openActionsSubtab("escalations")],
    ["Actions: Scheduled audits", "", () => openActionsSubtab("patrols")],
    ["Briefings & Posture", "Shift handover, knowledge gaps, entity dossiers", go("briefings")],
    ["Dashboards: Feed pipelines", "", dash("feeds")],
    ["Dashboards: Normalizers & CBN", "Parsers", dash("parsers")],
    ["Dashboards: Unparsed log diagnostics", "", dash("diagnostics")],
    ["Dashboards: FinOps & log costs", "", dash("finops")],
    ["Dashboards: Labels & namespaces", "", dash("namespacelabels")],
    ["Agent Library", "", go("library")],
  ];
  pages.forEach(([label, sub, run]) => items.push({ kind: "page", label, sub, run }));

  (state.streams || []).forEach((s) => {
    (s.topics || []).forEach((t) => {
      items.push({
        kind: "topic",
        key: channelKey(s.id, t.name),
        label: `#${s.name} › ${t.name}`,
        sub: s.display_name || "",
        unread: unreadFor(s.id, t.name),
        run: () => window.switchTopicAndChat(s.id, t.name),
      });
    });
  });

  (state.agents || []).forEach((a) => {
    items.push({
      kind: "dm",
      key: channelKey("dm", a.handle),
      label: a.handle,
      sub: a.role || a.name || "",
      keywords: `${a.name || ""} ${a.subsystem || ""}`,
      unread: unreadFor("dm", a.handle),
      run: () => window.switchTopicAndChat("dm", a.handle),
    });
    items.push({
      kind: "agent",
      label: `${a.name || a.handle}`,
      sub: `Agent Library · ${a.handle}`,
      keywords: `${a.role || ""} ${a.subsystem || ""}`,
      run: () => {
        setRoute(`#library/${encodeURIComponent(a.handle)}`);
        switchView("library");
      },
    });
  });
  return items;
}

// Higher is better; 0 = no match. Every query token must match somewhere.
function scoreQuickSwitcherItem(item, tokens) {
  const label = item.label.toLowerCase();
  const hay = `${label} ${(item.sub || "").toLowerCase()} ${(item.keywords || "").toLowerCase()}`;
  let score = 0;
  for (const tok of tokens) {
    const idx = label.indexOf(tok);
    if (idx === 0) score += 100;
    else if (idx > 0 && /[\s#@›:\-_/]/.test(label[idx - 1])) score += 70;
    else if (idx > 0) score += 45;
    else if (hay.includes(tok)) score += 20;
    else if (isSubsequence(tok, label)) score += 8;
    else return 0;
  }
  return score;
}

function isSubsequence(needle, hay) {
  let i = 0;
  for (let j = 0; j < hay.length && i < needle.length; j++) if (hay[j] === needle[i]) i++;
  return i === needle.length;
}

const QS_KIND_LABEL = { page: "Page", topic: "Topic", dm: "Direct message", agent: "Agent profile" };
const QS_KIND_ORDER = { topic: 0, dm: 1, page: 2, agent: 3 };

function rankQuickSwitcher(query, items) {
  const tokens = query.trim().toLowerCase().split(/\s+/).filter(Boolean);
  if (!tokens.length) {
    const byKey = new Map(items.filter((i) => i.key).map((i) => [i.key, i]));
    const current = channelKey(state.activeStream, state.activeTopic);
    const recent = loadRecentChannels().filter((k) => k !== current).map((k) => byKey.get(k)).filter(Boolean).slice(0, 5);
    const unread = items.filter((i) => i.unread && !recent.includes(i)).slice(0, 5);
    return [...recent, ...unread, ...items.filter((i) => i.kind === "page")];
  }
  return items
    .map((item) => ({ item, s: scoreQuickSwitcherItem(item, tokens) }))
    .filter((r) => r.s > 0)
    .sort((a, b) => b.s - a.s || QS_KIND_ORDER[a.item.kind] - QS_KIND_ORDER[b.item.kind] || a.item.label.localeCompare(b.item.label))
    .slice(0, 50)
    .map((r) => r.item);
}

const quickSwitcher = { overlay: null, results: [], index: 0, previousFocus: null };

function openQuickSwitcher() {
  if (quickSwitcher.overlay) return;
  quickSwitcher.previousFocus = document.activeElement;
  const overlay = document.createElement("div");
  overlay.className = "qs-overlay";
  overlay.innerHTML = `
    <div class="qs-dialog" role="dialog" aria-modal="true" aria-label="Jump to">
      <div class="qs-input-row">
        <svg class="ui-icon" viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/></svg>
        <input id="qsInput" class="qs-input" type="text" autocomplete="off" spellcheck="false"
          placeholder="Jump to a topic, agent or page…"
          role="combobox" aria-expanded="true" aria-controls="qsList" aria-autocomplete="list" />
      </div>
      <ul id="qsList" class="qs-list" role="listbox" aria-label="Results"></ul>
      <div class="qs-footer" aria-hidden="true"><span><kbd>↑</kbd><kbd>↓</kbd> move</span><span><kbd>Enter</kbd> open</span><span><kbd>Esc</kbd> close</span></div>
    </div>`;
  document.body.appendChild(overlay);
  quickSwitcher.overlay = overlay;

  const input = overlay.querySelector("#qsInput");
  const list = overlay.querySelector("#qsList");
  const items = quickSwitcherItems();

  const render = () => {
    const results = quickSwitcher.results;
    if (!results.length) {
      list.innerHTML = `<li class="qs-empty" role="presentation">No matches for “${escapeHtml(input.value.trim())}”</li>`;
      input.removeAttribute("aria-activedescendant");
      return;
    }
    const noQuery = !input.value.trim();
    list.innerHTML = results.map((it, i) => {
      const heading = noQuery && (i === 0 || (results[i - 1].kind === "page") !== (it.kind === "page"))
        ? `<li class="qs-group" role="presentation">${it.kind === "page" ? "Pages" : "Recent &amp; unread"}</li>` : "";
      return `${heading}<li id="qsOpt-${i}" class="qs-item${i === quickSwitcher.index ? " is-active" : ""}" role="option" aria-selected="${i === quickSwitcher.index}" data-qs-index="${i}">
          <span class="qs-item-main">
            <span class="qs-item-label">${escapeHtml(it.label)}</span>
            ${it.sub ? `<span class="qs-item-sub">${escapeHtml(it.sub)}</span>` : ""}
          </span>
          ${it.unread ? `<span class="unread-badge" aria-label="${it.unread} unread">${it.unread > 99 ? "99+" : it.unread}</span>` : ""}
          <span class="qs-item-kind">${QS_KIND_LABEL[it.kind]}</span>
        </li>`;
    }).join("");
    input.setAttribute("aria-activedescendant", `qsOpt-${quickSwitcher.index}`);
    list.querySelector(".qs-item.is-active")?.scrollIntoView({ block: "nearest" });
  };

  const update = () => {
    quickSwitcher.results = rankQuickSwitcher(input.value, items);
    quickSwitcher.index = 0;
    render();
  };

  const choose = (i) => {
    const item = quickSwitcher.results[i];
    if (!item) return;
    closeQuickSwitcher({ restoreFocus: false });
    item.run();
    if (item.kind === "topic" || item.kind === "dm") document.getElementById("composerInput")?.focus();
  };

  input.addEventListener("input", update);
  input.addEventListener("keydown", (e) => {
    const n = quickSwitcher.results.length;
    if (e.key === "ArrowDown" && n) {
      e.preventDefault();
      quickSwitcher.index = (quickSwitcher.index + 1) % n;
      render();
    } else if (e.key === "ArrowUp" && n) {
      e.preventDefault();
      quickSwitcher.index = (quickSwitcher.index - 1 + n) % n;
      render();
    } else if (e.key === "Enter") {
      e.preventDefault();
      choose(quickSwitcher.index);
    } else if (e.key === "Escape") {
      e.preventDefault();
      e.stopPropagation();
      closeQuickSwitcher();
    } else if (e.key === "Tab") {
      e.preventDefault(); // Only the input is focusable; keep focus in the dialog.
    }
  });
  list.addEventListener("mousedown", (e) => e.preventDefault()); // keep focus in the input
  list.addEventListener("click", (e) => {
    const li = e.target instanceof Element ? e.target.closest("[data-qs-index]") : null;
    if (li) choose(Number(li.dataset.qsIndex));
  });
  overlay.addEventListener("mousedown", (e) => { if (e.target === overlay) closeQuickSwitcher(); });

  update();
  input.focus();
}

function closeQuickSwitcher({ restoreFocus = true } = {}) {
  if (!quickSwitcher.overlay) return;
  quickSwitcher.overlay.remove();
  quickSwitcher.overlay = null;
  const prev = quickSwitcher.previousFocus;
  quickSwitcher.previousFocus = null;
  if (restoreFocus && prev && typeof prev.focus === "function" && prev.isConnected) prev.focus();
}

// Modals hide in different ways (hidden attr, style.display, removal), so test what's actually rendered.
function anyModalOpen() {
  return Array.from(document.querySelectorAll(".action-dialog-overlay, .gt-modal-overlay"))
    .some((el) => !el.hidden && el.getClientRects().length > 0);
}

function setupQuickSwitcher() {
  const hint = IS_MAC ? "⌘K" : "Ctrl K";
  document.querySelectorAll("[data-shortcut-hint]").forEach((el) => { el.textContent = hint; });
  ["quickSwitcherBtn", "quickSwitcherTopBtn"].forEach((id) => {
    const btn = document.getElementById(id);
    if (!btn) return;
    btn.addEventListener("click", openQuickSwitcher);
    btn.title = `Jump to a topic, agent or page (${IS_MAC ? "⌘K" : "Ctrl+K"})`;
  });
  document.addEventListener("keydown", (e) => {
    if ((e.ctrlKey || e.metaKey) && !e.altKey && !e.shiftKey && (e.key === "k" || e.key === "K")) {
      // Don't stack on top of another modal dialog.
      if (!quickSwitcher.overlay && anyModalOpen()) return;
      e.preventDefault();
      if (quickSwitcher.overlay) closeQuickSwitcher();
      else openQuickSwitcher();
    }
  });
}

// ====================================================================
// Narrow screens: off-canvas left sidebar, overlay proposals drawer
// ====================================================================
const NARROW_LAYOUT_QUERY = "(max-width: 1024px)";

function isNarrowLayout() {
  return typeof window.matchMedia === "function" && window.matchMedia(NARROW_LAYOUT_QUERY).matches;
}

function setSidebarOpen(open) {
  const sidebar = document.getElementById("sidebarLeft");
  const scrim = document.getElementById("sidebarScrim");
  const btn = document.getElementById("toggleSidebarBtn");
  const effective = !!open && isNarrowLayout();
  if (sidebar) sidebar.classList.toggle("is-open", effective);
  if (scrim) scrim.hidden = !effective;
  if (btn) {
    btn.setAttribute("aria-expanded", effective ? "true" : "false");
    btn.setAttribute("aria-label", effective ? "Hide streams and direct messages" : "Show streams and direct messages");
  }
}

function setupResponsiveLayout() {
  const btn = document.getElementById("toggleSidebarBtn");
  const sidebar = document.getElementById("sidebarLeft");
  if (btn && sidebar) {
    btn.addEventListener("click", () => {
      const opening = !sidebar.classList.contains("is-open");
      setSidebarOpen(opening);
      if (opening) document.getElementById("quickSwitcherBtn")?.focus();
    });
  }
  document.getElementById("sidebarScrim")?.addEventListener("click", () => setSidebarOpen(false));
  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape" && sidebar && sidebar.classList.contains("is-open") && !quickSwitcher.overlay) {
      setSidebarOpen(false);
      btn?.focus();
    }
  });
  if (typeof window.matchMedia === "function") {
    const mq = window.matchMedia(NARROW_LAYOUT_QUERY);
    const onChange = () => { if (!mq.matches) setSidebarOpen(false); };
    if (mq.addEventListener) mq.addEventListener("change", onChange);
  }
}

// ====================================================================
// Floating Mention Autocomplete Popup System
// ====================================================================
const mentionState = {
  active: false,
  query: "",
  matches: [],
  selectedIndex: 0,
  mentionStart: -1,
  mentionEnd: -1,
};

function getAgentAvatar(handle) {
  const map = {
    "@feed-agent": "📡",
    "@parser-doctor": "🩺",
    "@secops-dispatcher": "🧭",
    "@rule-troubleshooter": "🔍",
    "@yaral-optimizer": "⚡",
    "@logjammer-agent": "🪵",
    "@identity-governor": "🛡️",
    "@detection-decay-agent": "📉",
    "@detection-tuning-agent": "🎯",
    "@sql-analyst": "📊",
    "@gcp-telemetry-agent": "📈",
    "@tenant-posture-agent": "🏛️",
    "@playbook-decay-agent": "📜",
    "@timestamp-integrity-agent": "⏱️",
    "@rule-conflict-agent": "⚖️",
    "@log-cost-agent": "💰",
    "@raw-log-agent": "🔎",
    "@namespace-label-agent": "🏷️",
  };
  return map[handle] || "🤖";
}

function setupMentionAutocomplete() {
  const input = document.getElementById("composerInput");
  const dropdown = document.getElementById("mentionDropdown");
  if (!input || !dropdown) return;

  input.addEventListener("input", () => {
    const val = input.value;
    const cursorPos = input.selectionStart;
    
    // Find if cursor is inside an @word
    const textBefore = val.slice(0, cursorPos);
    const atMatch = textBefore.match(/@([a-zA-Z0-9_-]*)$/);

    if (atMatch) {
      const query = atMatch[1].toLowerCase();
      mentionState.query = query;
      mentionState.mentionStart = cursorPos - atMatch[0].length;
      mentionState.mentionEnd = cursorPos;

      // Filter agents
      const matches = state.agents.filter(a => {
        const handle = (a.handle || "").replace(/^@/, "").toLowerCase();
        const name = (a.name || "").toLowerCase();
        const role = (a.role || "").toLowerCase();
        return handle.includes(query) || name.includes(query) || role.includes(query);
      });

      if (matches.length > 0) {
        mentionState.active = true;
        mentionState.matches = matches;
        mentionState.selectedIndex = 0;
        renderMentionDropdown();
      } else {
        closeMentionDropdown();
      }
    } else {
      closeMentionDropdown();
    }
  });

  input.addEventListener("keydown", (e) => {
    if (!mentionState.active) return;

    if (e.key === "ArrowDown") {
      e.preventDefault();
      mentionState.selectedIndex = (mentionState.selectedIndex + 1) % mentionState.matches.length;
      updateMentionDropdownSelection();
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      mentionState.selectedIndex = (mentionState.selectedIndex - 1 + mentionState.matches.length) % mentionState.matches.length;
      updateMentionDropdownSelection();
    } else if (e.key === "Enter" || e.key === "Tab") {
      if (mentionState.matches[mentionState.selectedIndex]) {
        e.preventDefault();
        applyMentionSelection(mentionState.matches[mentionState.selectedIndex]);
      }
    } else if (e.key === "Escape") {
      closeMentionDropdown();
    }
  });

  document.addEventListener("click", (e) => {
    if (!dropdown.contains(e.target) && e.target !== input) {
      closeMentionDropdown();
    }
  });
}

function renderMentionDropdown() {
  const dropdown = document.getElementById("mentionDropdown");
  if (!dropdown) return;

  dropdown.innerHTML = "";
  mentionState.matches.forEach((agent, idx) => {
    const item = document.createElement("div");
    item.className = `mention-item ${idx === mentionState.selectedIndex ? "selected" : ""}`;
    const avatar = getAgentAvatar(agent.handle);
    item.innerHTML = `
      <div class="mention-avatar">${avatar}</div>
      <div class="mention-info">
        <span class="mention-handle">${agent.handle}</span>
        <span class="mention-role">${escapeHtml(agent.role || agent.name || "Specialized SecOps Agent")}</span>
      </div>
    `;
    item.addEventListener("mousedown", (e) => {
      e.preventDefault();
      applyMentionSelection(agent);
    });
    dropdown.appendChild(item);
  });
  dropdown.style.display = "block";
}

function updateMentionDropdownSelection() {
  const items = document.querySelectorAll(".mention-item");
  items.forEach((item, idx) => {
    if (idx === mentionState.selectedIndex) {
      item.classList.add("selected");
      item.scrollIntoView({ block: "nearest" });
    } else {
      item.classList.remove("selected");
    }
  });
}

function applyMentionSelection(agent) {
  const input = document.getElementById("composerInput");
  if (!input) return;

  const val = input.value;
  const before = val.slice(0, mentionState.mentionStart);
  const after = val.slice(mentionState.mentionEnd);
  
  input.value = `${before}${agent.handle} ${after}`;
  const newCursor = `${before}${agent.handle} `.length;
  input.selectionStart = newCursor;
  input.selectionEnd = newCursor;
  input.focus();
  closeMentionDropdown();
}

function closeMentionDropdown() {
  mentionState.active = false;
  const dropdown = document.getElementById("mentionDropdown");
  if (dropdown) dropdown.style.display = "none";
}

// ====================================================================
// View Switcher (Chat vs Dedicated Ingestion Page)
// ====================================================================
function switchView(viewName, opts = {}) {
  state.currentView = viewName === "ingestion" ? "dashboards"
    : (["gastown", "dashboards", "library", "briefings"].includes(viewName) ? viewName : "chat");
  const navChat = document.getElementById("navBtnChat");
  const navGastown = document.getElementById("navBtnGastown");
  const navDashboards = document.getElementById("navBtnDashboards") || document.getElementById("navBtnIngestion");
  const navLibrary = document.getElementById("navBtnLibrary");
  const navBriefings = document.getElementById("navBtnBriefings");
  const chatView = document.getElementById("chatView");
  const gastownView = document.getElementById("gastownView");
  const ingestionView = document.getElementById("ingestionView");
  const libraryView = document.getElementById("libraryView");
  const briefingsView = document.getElementById("briefingsView");
  const sidebarLeft = document.getElementById("sidebarLeft");
  const sidebarRight = document.getElementById("sidebarRight");
  const toggleRightDrawerBtn = document.getElementById("toggleRightDrawerBtn");

  if (viewName === "gastown") {
    if (navChat) navChat.classList.remove("active");
    if (navDashboards) navDashboards.classList.remove("active");
    if (navLibrary) navLibrary.classList.remove("active");
    if (navBriefings) navBriefings.classList.remove("active");
    if (navGastown) navGastown.classList.add("active");

    if (chatView) chatView.style.display = "none";
    if (ingestionView) ingestionView.style.display = "none";
    if (libraryView) libraryView.style.display = "none";
    if (briefingsView) briefingsView.style.display = "none";
    if (gastownView) gastownView.style.display = "flex";

    if (sidebarLeft) sidebarLeft.style.display = "none";
    if (sidebarRight) sidebarRight.style.display = "none";

    document.body.classList.remove("view-ingestion-active");
    document.body.classList.remove("view-library-active");
    document.body.classList.remove("view-briefings-active");
    document.body.classList.add("view-gastown-active");

    if (window.location.hash !== "#gastown" && window.location.hash !== "#board" && window.location.hash !== "#actions") {
      setRoute("#actions");
    }
    loadGastownOverview();
  } else if (viewName === "dashboards" || viewName === "ingestion") {
    if (navChat) navChat.classList.remove("active");
    if (navGastown) navGastown.classList.remove("active");
    if (navLibrary) navLibrary.classList.remove("active");
    if (navBriefings) navBriefings.classList.remove("active");
    if (navDashboards) navDashboards.classList.add("active");

    if (chatView) chatView.style.display = "none";
    if (gastownView) gastownView.style.display = "none";
    if (libraryView) libraryView.style.display = "none";
    if (briefingsView) briefingsView.style.display = "none";
    if (ingestionView) ingestionView.style.display = "flex";

    if (sidebarLeft) sidebarLeft.style.display = "none";
    if (sidebarRight) sidebarRight.style.display = "none";

    document.body.classList.remove("view-gastown-active");
    document.body.classList.remove("view-library-active");
    document.body.classList.remove("view-briefings-active");
    document.body.classList.add("view-ingestion-active");

    const cur = window.location.hash;
    if (!cur.startsWith("#dashboards") && !cur.startsWith("#ingestion")) {
      const activeSub = (ingestionData && ingestionData.activeSubtab) || "feeds";
      setRoute(`#dashboards/${activeSub}`);
    }
    renderIngestionPage();
  } else if (viewName === "library") {
    if (navChat) navChat.classList.remove("active");
    if (navGastown) navGastown.classList.remove("active");
    if (navDashboards) navDashboards.classList.remove("active");
    if (navBriefings) navBriefings.classList.remove("active");
    if (navLibrary) navLibrary.classList.add("active");

    if (chatView) chatView.style.display = "none";
    if (gastownView) gastownView.style.display = "none";
    if (ingestionView) ingestionView.style.display = "none";
    if (briefingsView) briefingsView.style.display = "none";
    if (libraryView) libraryView.style.display = "flex";

    if (sidebarLeft) sidebarLeft.style.display = "none";
    if (sidebarRight) sidebarRight.style.display = "none";

    document.body.classList.remove("view-gastown-active");
    document.body.classList.remove("view-ingestion-active");
    document.body.classList.remove("view-briefings-active");
    document.body.classList.add("view-library-active");

    if (!window.location.hash.startsWith("#library")) {
      setRoute("#library");
    }
    loadAgentLibrary();
  } else if (viewName === "briefings") {
    if (navChat) navChat.classList.remove("active");
    if (navGastown) navGastown.classList.remove("active");
    if (navDashboards) navDashboards.classList.remove("active");
    if (navLibrary) navLibrary.classList.remove("active");
    if (navBriefings) navBriefings.classList.add("active");

    if (chatView) chatView.style.display = "none";
    if (gastownView) gastownView.style.display = "none";
    if (ingestionView) ingestionView.style.display = "none";
    if (libraryView) libraryView.style.display = "none";
    if (briefingsView) briefingsView.style.display = "flex";

    if (sidebarLeft) sidebarLeft.style.display = "none";
    if (sidebarRight) sidebarRight.style.display = "none";

    document.body.classList.remove("view-gastown-active");
    document.body.classList.remove("view-ingestion-active");
    document.body.classList.remove("view-library-active");
    document.body.classList.add("view-briefings-active");

    if (!window.location.hash.startsWith("#briefings")) {
      setRoute("#briefings");
    }
    loadBriefingsView();
  } else {
    // Default: Fleet Chat
    if (navGastown) navGastown.classList.remove("active");
    if (navDashboards) navDashboards.classList.remove("active");
    if (navLibrary) navLibrary.classList.remove("active");
    if (navBriefings) navBriefings.classList.remove("active");
    if (navChat) navChat.classList.add("active");

    if (gastownView) gastownView.style.display = "none";
    if (ingestionView) ingestionView.style.display = "none";
    if (libraryView) libraryView.style.display = "none";
    if (briefingsView) briefingsView.style.display = "none";
    if (chatView) chatView.style.display = "flex";

    if (sidebarLeft) sidebarLeft.style.display = "flex";
    if (sidebarRight) {
      sidebarRight.style.display = "flex";
      if (!state.isRightDrawerOpen) {
        sidebarRight.classList.add("sidebar-right-closed");
        if (toggleRightDrawerBtn) toggleRightDrawerBtn.classList.remove("active");
      } else {
        sidebarRight.classList.remove("sidebar-right-closed");
        if (toggleRightDrawerBtn) toggleRightDrawerBtn.classList.add("active");
      }
    }

    document.body.classList.remove("view-gastown-active");
    document.body.classList.remove("view-ingestion-active");
    document.body.classList.remove("view-library-active");
    document.body.classList.remove("view-briefings-active");

    const curHash = window.location.hash.replace(/^#/, "");
    if (!opts.skipRoute && (curHash === "" || isViewHash(curHash))) {
      setRoute(`#${state.activeStream}/${state.activeTopic}`);
    }
    clearUnread(state.activeStream, state.activeTopic);
    scrollToBottom();
  }

}

window.switchTopicAndChat = async function (stream, topic, initialText = "") {
  // One history entry for the jump (not one for "chat" plus one for the topic).
  switchView("chat", { skipRoute: true });
  await switchTopic(stream, topic);
  if (initialText) {
    const input = document.getElementById("composerInput");
    if (input) {
      input.value = initialText;
      input.focus();
    }
  }
};

// ====================================================================
// Dedicated Ingestion & Normalization Page Controller
// ====================================================================
const ingestionData = {
  feeds: [],
  parsers: [],
  finopsReport: null,
  nsLabelsReport: null,
  feedFilter: "all",
  parserFilter: "all",
  feedSearch: "",
  parserSearch: "",
  activeSubtab: "feeds",
};

function setupIngestionFilters() {
  const feedSearch = document.getElementById("feedSearchInput");
  if (feedSearch) {
    feedSearch.addEventListener("input", (e) => {
      ingestionData.feedSearch = e.target.value.trim();
      renderFeedsTable();
    });
  }

  const parserSearch = document.getElementById("parserSearchInput");
  if (parserSearch) {
    parserSearch.addEventListener("input", (e) => {
      ingestionData.parserSearch = e.target.value.trim();
      renderParsersTable();
    });
  }

  const feedChips = document.querySelectorAll(".filter-chip[data-ffilter]");
  feedChips.forEach(chip => {
    chip.addEventListener("click", () => {
      feedChips.forEach(c => c.classList.remove("active"));
      chip.classList.add("active");
      ingestionData.feedFilter = chip.getAttribute("data-ffilter");
      renderFeedsTable();
    });
  });

  const parserChips = document.querySelectorAll(".filter-chip[data-pfilter]");
  parserChips.forEach(chip => {
    chip.addEventListener("click", () => {
      parserChips.forEach(c => c.classList.remove("active"));
      chip.classList.add("active");
      ingestionData.parserFilter = chip.getAttribute("data-pfilter");
      renderParsersTable();
    });
  });
}

function switchIngestionSubtab(subtab) {
  ingestionData.activeSubtab = subtab;
  const tabFeeds = document.getElementById("tabIngestionFeeds");
  const tabParsers = document.getElementById("tabIngestionParsers");
  const tabDiag = document.getElementById("tabIngestionDiagnostics");
  const tabFinOps = document.getElementById("tabIngestionFinOps");
  const tabNsLabels = document.getElementById("tabIngestionNamespaceLabels");
  const secFeeds = document.getElementById("secIngestionFeeds");
  const secParsers = document.getElementById("secIngestionParsers");
  const secDiag = document.getElementById("secIngestionDiagnostics");
  const secFinOps = document.getElementById("secIngestionFinOps");
  const secNsLabels = document.getElementById("secIngestionNamespaceLabels");

  if (tabFeeds) tabFeeds.classList.toggle("active", subtab === "feeds");
  if (tabParsers) tabParsers.classList.toggle("active", subtab === "parsers");
  if (tabDiag) tabDiag.classList.toggle("active", subtab === "diagnostics");
  if (tabFinOps) tabFinOps.classList.toggle("active", subtab === "finops");
  if (tabNsLabels) tabNsLabels.classList.toggle("active", subtab === "namespacelabels");

  if (secFeeds) secFeeds.style.display = subtab === "feeds" ? "flex" : "none";
  if (secParsers) secParsers.style.display = subtab === "parsers" ? "flex" : "none";
  if (secDiag) secDiag.style.display = subtab === "diagnostics" ? "flex" : "none";
  if (secFinOps) secFinOps.style.display = subtab === "finops" ? "flex" : "none";
  if (secNsLabels) secNsLabels.style.display = subtab === "namespacelabels" ? "flex" : "none";

  if (window.location.hash.startsWith("#dashboards") || window.location.hash.startsWith("#ingestion")) {
    setRoute(`#dashboards/${subtab}`, { replace: true });
  }

  if (subtab === "finops" && !ingestionData.finopsReport) {
    fetchFinopsData(false);
  }
  if (subtab === "namespacelabels" && !ingestionData.nsLabelsReport) {
    fetchNamespaceLabelsData();
  }
}

async function fetchFinopsData(forceAnalyze = false) {
  const tier = (document.getElementById("finopsTierSelect") || {}).value || "ENTERPRISE";
  const days = (document.getElementById("finopsDaysSelect") || {}).value || "7";
  const btn = document.getElementById("btnRunFinopsAnalysis");
  if (btn) {
    btn.disabled = true;
    btn.innerHTML = `<span class="spinner-sm"></span> Analyzing...`;
  }

  try {
    const url = forceAnalyze 
      ? `/api/log_cost/analyze?days=${days}&tier=${tier}`
      : `/api/log_cost/latest`;
    
    const res = await fetch(url, {
      method: forceAnalyze ? "POST" : "GET"
    });
    const data = await res.json();
    if (data.status === "SUCCESS" && data.report) {
      ingestionData.finopsReport = data.report;
      renderFinopsSection();
      showToast("success", `FinOps analysis complete: $${(data.report.total_potential_savings_usd || 0).toFixed(2)}/mo savings identified.`);
    } else {
      showToast("error", data.message || "Failed to retrieve FinOps report.");
    }
  } catch (err) {
    console.error("FinOps fetch error:", err);
    showToast("error", "Error fetching FinOps analysis: " + err.message);
  } finally {
    if (btn) {
      btn.disabled = false;
      btn.innerHTML = `
        <svg class="btn-svg" viewBox="0 0 24 24" width="13" height="13" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><line x1="12" y1="1" x2="12" y2="23"/><path d="M17 5H9.5a3.5 3.5 0 0 0 0 7h5a3.5 3.5 0 0 1 0 7H6"/></svg>
        <span>Analyze Costs</span>
      `;
    }
  }
}

function renderFinopsSection() {
  const r = ingestionData.finopsReport;
  if (!r) return;

  const elVol = document.getElementById("finopsTotalVolume");
  if (elVol) elVol.textContent = `${(r.total_volume_gb || 0).toLocaleString(undefined, {minimumFractionDigits: 1, maximumFractionDigits: 1})} GB`;
  const elVolSub = document.getElementById("finopsVolumeSub");
  if (elVolSub) elVolSub.textContent = `Total events: ${(r.total_events || 0).toLocaleString()} • ${(r.total_volume_gib || 0).toFixed(1)} GiB`;

  const elSpend = document.getElementById("finopsProjectedSpend");
  if (elSpend) elSpend.textContent = `$${(r.total_projected_monthly_spend_enterprise || 0).toLocaleString(undefined, {minimumFractionDigits: 2, maximumFractionDigits: 2})} / mo`;
  const elSpendSub = document.getElementById("finopsSpendSub");
  if (elSpendSub) elSpendSub.textContent = `Standard: $${(r.total_projected_monthly_spend_standard || 0).toFixed(0)} • Ent+: $${(r.total_projected_monthly_spend_enterprise_plus || 0).toFixed(0)}`;

  const elSavings = document.getElementById("finopsPotentialSavings");
  if (elSavings) elSavings.textContent = `$${(r.total_potential_savings_usd || 0).toLocaleString(undefined, {minimumFractionDigits: 2, maximumFractionDigits: 2})} / mo`;

  const elBloated = document.getElementById("finopsBloatedCount");
  if (elBloated) elBloated.textContent = (r.bloated_sources || []).length;
  const elBloatedSub = document.getElementById("finopsBloatedSub");
  if (elBloatedSub) elBloatedSub.textContent = `${(r.bloated_sources || []).length} sources exceed 2 KB/event`;

  const kpiProjectedSpend = document.getElementById("kpiProjectedSpend");
  if (kpiProjectedSpend) kpiProjectedSpend.textContent = `$${(r.total_projected_monthly_spend_enterprise || 0).toLocaleString(undefined, {minimumFractionDigits: 0, maximumFractionDigits: 0})}/mo`;

  // Render Recommendations
  const recContainer = document.getElementById("finopsRecommendationsList");
  if (recContainer) {
    const recs = r.recommendations || [];
    if (recs.length === 0) {
      recContainer.innerHTML = `<div style="font-size:12px; color:var(--text-muted);">No optimization recommendations identified for this window.</div>`;
    } else {
      recContainer.innerHTML = recs.map((rec, idx) => `
        <div style="background:var(--surface-stripe); border:1px solid var(--border-subtle); border-radius:6px; padding:12px;">
          <div style="display:flex; justify-content:space-between; align-items:flex-start; margin-bottom:6px;">
            <div style="display:flex; align-items:center; gap:8px;">
              <span class="status-badge" style="background:var(--c-ok-bg); color:var(--c-ok); border:1px solid var(--c-ok-bd); font-size:11px;">${escapeHtml(rec.category)}</span>
              <span style="font-weight:600; font-size:13px; color:var(--text-main);">${escapeHtml(rec.title)}</span>
            </div>
            <span style="font-size:12px; font-weight:700; color:var(--c-ok);">+$${(rec.potential_monthly_savings_usd || 0).toFixed(2)}/mo</span>
          </div>
          <div style="font-size:11.5px; color:var(--text-muted); margin-bottom:6px;">
            Target Log Type: <code style="color:var(--c-sky);">${escapeHtml(rec.log_type)}</code> • Estimated Volume Reduction: <strong>${(rec.potential_volume_savings_gb || 0).toFixed(2)} GB/mo</strong>
          </div>
          <div style="font-size:11px; background:var(--surface-inset); border-radius:4px; padding:6px 8px; color:var(--text-dim); font-family:monospace; white-space:pre-wrap;">${escapeHtml(rec.implementation_guidance || rec.description)}</div>
          <div style="margin-top:8px; display:flex; justify-content:flex-end;">
            <button class="btn btn-sm btn-ghost" style="font-size:11px; padding:2px 8px;" ${act("switchTopicAndChat", "ingestion", "finops", `@log-cost-agent optimize ${rec.log_type} via ${rec.category}`)}>
              Apply via @log-cost-agent
            </button>
          </div>
        </div>
      `).join("");
    }
  }

  // Render Volume Drivers Table
  const tableBody = document.getElementById("finopsDriversTableBody");
  if (tableBody) {
    const drivers = r.top_volume_drivers || [];
    if (drivers.length === 0) {
      tableBody.innerHTML = `<tr><td colspan="7" class="table-loading">No volume driver metrics available.</td></tr>`;
    } else {
      tableBody.innerHTML = drivers.map(d => {
        const isBloated = d.is_bloated;
        const bloatBadge = isBloated 
          ? `<span class="status-badge status-WARN" style="font-size:11px;">BLOATED (>2KB)</span>`
          : `<span class="status-badge status-HEALTHY" style="font-size:11px;">OPTIMAL</span>`;
        return `
          <tr>
            <td style="font-weight:600; color:var(--text-main);"><code style="color:var(--c-sky); font-size:11.5px;">${escapeHtml(d.log_type)}</code></td>
            <td>${(d.event_count || 0).toLocaleString()}</td>
            <td>${(d.volume_gb_decimal || 0).toFixed(2)} GB</td>
            <td>${(d.avg_event_size_bytes || 0).toFixed(1)} B</td>
            <td>${bloatBadge}</td>
            <td style="font-weight:600; color:var(--c-warn);">$${(d.cost_enterprise || 0).toFixed(2)}/mo</td>
            <td>
              <button class="btn btn-sm btn-ghost" ${act("switchTopicAndChat", "ingestion", "finops", `@log-cost-agent analyze log source ${d.log_type}`)}>
                Inspect
              </button>
            </td>
          </tr>
        `;
      }).join("");
    }
  }
}

async function fetchNamespaceLabelsData() {
  const days = (document.getElementById("nsLabelsDaysSelect") || {}).value || "7";
  const btn = document.getElementById("btnRunNsLabelsAudit");
  if (btn) {
    btn.disabled = true;
    btn.innerHTML = `<span class="spinner-sm"></span> Auditing...`;
  }

  try {
    const res = await fetch(`/api/ingestion/labels-and-namespaces?lookback_days=${days}`);
    const data = await res.json();
    if (data.status === "SUCCESS" && data.report) {
      ingestionData.nsLabelsReport = data.report;
      renderNamespaceLabelsSection();
    } else {
      console.warn("Failed to audit labels and namespaces:", data.message);
      showToast("error", `Labels & namespaces audit failed: ${data.message || "no report returned"}`);
    }
  } catch (err) {
    console.error("Error fetching labels & namespaces report:", err);
    showToast("error", `Labels & namespaces audit failed: ${err.message}`);
  } finally {
    if (btn) {
      btn.disabled = false;
      btn.innerHTML = `<svg class="btn-svg" viewBox="0 0 24 24" width="13" height="13" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M20.59 13.41l-7.17 7.17a2 2 0 0 1-2.83 0L2 12V2h10l8.59 8.59a2 2 0 0 1 0 2.82z"/><line x1="7" y1="7" x2="7.01" y2="7"/></svg> <span>Audit Hygiene</span>`;
    }
  }
}

function renderNamespaceLabelsSection() {
  const report = ingestionData.nsLabelsReport;
  if (!report) return;

  const totalLabelledEl = document.getElementById("nsTotalLabelledEvents");
  const activeLabelsCountEl = document.getElementById("nsActiveLabelsCount");
  const totalNamespacedEl = document.getElementById("nsTotalNamespacedEvents");
  const activeNamespacesCountEl = document.getElementById("nsActiveNamespacesCount");
  const totalUntaggedEl = document.getElementById("nsTotalUntaggedEvents");
  const rbacStatusEl = document.getElementById("nsRbacAlignmentStatus");
  const rbacCountEl = document.getElementById("nsRbacLabelCount");

  const activeLabels = report.active_ingestion_labels || [];
  const activeNs = report.active_namespaces || [];
  const rbacRefs = report.data_rbac_references || [];
  const findings = report.findings || [];

  if (totalLabelledEl) totalLabelledEl.textContent = (report.total_labelled_events || 0).toLocaleString();
  if (activeLabelsCountEl) activeLabelsCountEl.textContent = `${activeLabels.length} active tag keys`;
  if (totalNamespacedEl) totalNamespacedEl.textContent = (report.total_namespaced_events || 0).toLocaleString();
  if (activeNamespacesCountEl) activeNamespacesCountEl.textContent = `${activeNs.length} active namespaces`;
  if (totalUntaggedEl) totalUntaggedEl.textContent = (report.total_untagged_events || 0).toLocaleString();

  const rbacMatches = rbacRefs.filter(r => r.status === "ACTIVE_MATCH").length;
  if (rbacStatusEl) {
    if (rbacRefs.length === 0) {
      rbacStatusEl.textContent = "NO LABELS";
      rbacStatusEl.style.color = "var(--text-dim)";
    } else if (rbacMatches === rbacRefs.length) {
      rbacStatusEl.textContent = "ALIGNED (100%)";
      rbacStatusEl.style.color = "var(--c-ok)";
    } else {
      rbacStatusEl.textContent = `${rbacMatches}/${rbacRefs.length} ALIGNED`;
      rbacStatusEl.style.color = "var(--c-warn)";
    }
  }
  if (rbacCountEl) rbacCountEl.textContent = `${rbacRefs.length} Data Access Labels`;

  const findingsList = document.getElementById("nsLabelsFindingsList");
  if (findingsList) {
    if (findings.length === 0) {
      findingsList.innerHTML = `<div style="font-size:12px; color:var(--c-ok);">✓ No hygiene or Data RBAC tagging deficiencies identified.</div>`;
    } else {
      findingsList.innerHTML = findings.map(f => {
        const sevClass = f.severity === "HIGH" ? "status-FAILED" : (f.severity === "MEDIUM" ? "status-WARN" : "status-HEALTHY");
        const typesBadge = f.affected_log_types && f.affected_log_types.length
          ? `<div style="margin-top:4px; font-size:11px; color:var(--text-dim);">Affected log types: <code>${escapeHtml(f.affected_log_types.join(", "))}</code></div>`
          : "";
        return `
          <div style="background:var(--bg-table-header); border:1px solid var(--border-color); border-radius:6px; padding:10px 12px;">
            <div style="display:flex; justify-content:space-between; align-items:center;">
              <span style="font-weight:700; font-size:12.5px; color:var(--text-main);">${escapeHtml(f.title)}</span>
              <span class="status-badge ${sevClass}" style="font-size:11px;">${escapeHtml(f.severity)}</span>
            </div>
            <div style="font-size:11.5px; color:var(--text-muted); margin-top:4px;">${escapeHtml(f.description)}</div>
            ${typesBadge}
            <div style="font-size:11px; color:var(--c-sky); margin-top:6px;"><strong>Remediation:</strong> ${escapeHtml(f.remediation_guidance)}</div>
          </div>
        `;
      }).join("");
    }
  }

  const labelsTableBody = document.getElementById("ingestionLabelsTableBody");
  if (labelsTableBody) {
    if (activeLabels.length === 0) {
      labelsTableBody.innerHTML = `<tr><td colspan="4" style="text-align:center; color:var(--text-muted);">No active ingestion labels found.</td></tr>`;
    } else {
      labelsTableBody.innerHTML = activeLabels.map(l => {
        const typeBadge = l.is_auto_generated
          ? `<span class="status-badge" style="background:var(--c-sky-bg); color:var(--c-sky); font-size:11px;">AUTO</span>`
          : `<span class="status-badge" style="background:var(--c-neutral-bg); color:var(--text-dim); font-size:11px;">CUSTOM</span>`;
        const logTypesStr = (l.log_types || []).slice(0, 3).join(", ") + ((l.log_types || []).length > 3 ? ` (+${l.log_types.length - 3})` : "");
        return `
          <tr>
            <td style="font-weight:600;"><code style="color:var(--text-main); font-size:11.5px;">${escapeHtml(l.label_key)}</code></td>
            <td>${(l.event_count || 0).toLocaleString()}</td>
            <td>${typeBadge}</td>
            <td style="font-size:11px; color:var(--text-dim);">${escapeHtml(logTypesStr)}</td>
          </tr>
        `;
      }).join("");
    }
  }

  const nsTableBody = document.getElementById("udmNamespacesTableBody");
  if (nsTableBody) {
    if (activeNs.length === 0) {
      nsTableBody.innerHTML = `<tr><td colspan="4" style="text-align:center; color:var(--text-muted);">No active UDM namespaces found.</td></tr>`;
    } else {
      nsTableBody.innerHTML = activeNs.map(n => {
        const rfcBadge = n.is_network_rfc1918_relevant
          ? `<span class="status-badge status-WARN" style="font-size:11px;">RFC 1918</span>`
          : `<span class="status-badge status-HEALTHY" style="font-size:11px;">STANDARD</span>`;
        const logTypesStr = (n.log_types || []).slice(0, 3).join(", ") + ((n.log_types || []).length > 3 ? ` (+${n.log_types.length - 3})` : "");
        return `
          <tr>
            <td style="font-weight:600;"><code style="color:var(--c-indigo); font-size:11.5px;">${escapeHtml(n.namespace)}</code></td>
            <td>${(n.event_count || 0).toLocaleString()}</td>
            <td>${rfcBadge}</td>
            <td style="font-size:11px; color:var(--text-dim);">${escapeHtml(logTypesStr)}</td>
          </tr>
        `;
      }).join("");
    }
  }
}

async function renderIngestionPage(forceRefresh = false) {
  try {
    const [feedsRes, parsersRes] = await Promise.all([
      fetchJsonOrThrow(`/api/feeds?lookback_days=7${forceRefresh ? '&refresh=true' : ''}`).catch((e) => ({ feeds: [], summary: {}, _error: e })),
      fetchJsonOrThrow(`/api/parsers?lookback_days=7${forceRefresh ? '&refresh=true' : ''}`).catch((e) => ({ parsers: [], summary: {}, _error: e })),
    ]);

    ingestionData.feeds = feedsRes.feeds || [];
    ingestionData.parsers = parsersRes.parsers || [];

    const feedSummary = feedsRes.summary || {};
    const parserSummary = parsersRes.summary || {};

    const totalFeeds = feedSummary.total_feeds_audited || ingestionData.feeds.length || 0;
    const totalParsers = parserSummary.total_parsers_audited || ingestionData.parsers.length || 0;
    const versionDrifts = parserSummary.version_drift_count || 0;
    const p95Latency = feedSummary.high_latency_count ? `${feedSummary.high_latency_count} lagging` : "SLA Met";
    const dropCodes = parserSummary.failed_count || 0;

    const elTotalFeeds = document.getElementById("kpiTotalFeeds");
    if (elTotalFeeds) elTotalFeeds.textContent = totalFeeds;
    const elFeedSub = document.getElementById("kpiFeedSub");
    if (elFeedSub) elFeedSub.textContent = `${feedSummary.healthy_count || totalFeeds} healthy • 0 failed`;

    const elP95Latency = document.getElementById("kpiP95Latency");
    if (elP95Latency) elP95Latency.textContent = p95Latency;

    const elTotalParsers = document.getElementById("kpiTotalParsers");
    if (elTotalParsers) elTotalParsers.textContent = totalParsers;
    const elParserSub = document.getElementById("kpiParserSub");
    if (elParserSub) elParserSub.textContent = `${parserSummary.healthy_count || totalParsers} active normalizers`;

    const elVersionDrift = document.getElementById("kpiVersionDrift");
    if (elVersionDrift) elVersionDrift.textContent = versionDrifts;

    const elDropCodes = document.getElementById("kpiDropCodes");
    if (elDropCodes) elDropCodes.textContent = dropCodes;

    // Fetch latest log cost report for Spend KPI card
    fetch('/api/log_cost/latest')
      .then(r => r.json())
      .then(data => {
        if (data.status === "SUCCESS" && data.report) {
          ingestionData.finopsReport = data.report;
          const elSpend = document.getElementById("kpiProjectedSpend");
          if (elSpend) elSpend.textContent = `$${(data.report.total_projected_monthly_spend_enterprise || 0).toLocaleString(undefined, {minimumFractionDigits: 0, maximumFractionDigits: 0})}/mo`;
          if (ingestionData.activeSubtab === "finops") {
            renderFinopsSection();
          }
        }
      })
      .catch(() => {});

    renderFeedsTable();
    renderParsersTable();

    const retryIngestion = () => renderIngestionPage(forceRefresh);
    if (feedsRes._error) {
      ["kpiTotalFeeds", "kpiP95Latency"].forEach((id) => { const el = document.getElementById(id); if (el) el.textContent = UNKNOWN_METRIC; });
      const sub = document.getElementById("kpiFeedSub");
      if (sub) sub.textContent = "Feed telemetry unavailable";
      showLoadError(document.getElementById("feedsTableBody"), { title: "Couldn't load feed telemetry", error: feedsRes._error, retry: retryIngestion, colspan: 7 });
    }
    if (parsersRes._error) {
      ["kpiTotalParsers", "kpiVersionDrift", "kpiDropCodes"].forEach((id) => { const el = document.getElementById(id); if (el) el.textContent = UNKNOWN_METRIC; });
      const sub = document.getElementById("kpiParserSub");
      if (sub) sub.textContent = "Parser telemetry unavailable";
      showLoadError(document.getElementById("parsersTableBody"), { title: "Couldn't load parser health", error: parsersRes._error, retry: retryIngestion, colspan: 7 });
    }
  } catch (err) {
    console.error("Error loading ingestion page:", err);
    showToast("error", "Failed loading telemetry: " + err.message);
  }
}

function renderFeedsTable() {
  const tbody = document.getElementById("feedsTableBody");
  if (!tbody) return;

  let feeds = ingestionData.feeds || [];
  
  if (ingestionData.feedFilter !== "all") {
    feeds = feeds.filter(f => (f.status || "").toUpperCase() === ingestionData.feedFilter);
  }

  if (ingestionData.feedSearch) {
    const q = ingestionData.feedSearch.toLowerCase();
    feeds = feeds.filter(f => 
      (f.feed_name || "").toLowerCase().includes(q) ||
      (f.log_type || "").toLowerCase().includes(q) ||
      (f.source_type || "").toLowerCase().includes(q)
    );
  }

  if (feeds.length === 0) {
    tbody.innerHTML = `<tr><td colspan="7" class="table-loading">No feeds found matching filters.</td></tr>`;
    return;
  }

  tbody.innerHTML = feeds.map(f => {
    const status = f.status || "HEALTHY";
    const statusClass = status === "HEALTHY" ? "status-HEALTHY" : status === "WARN" || status === "HIGH_LATENCY" ? "status-WARN" : "status-FAILED";
    const latency = f.latency_p95_hours ? `${f.latency_p95_hours.toFixed(1)}h` : (f.latency_p95 || "Normal (<1h)");
    const lastHeartbeat = f.last_event_time ? formatTime(f.last_event_time) : (f.last_ingestion_time || "Recent");

    return `
      <tr>
        <td><span class="status-badge ${statusClass}">${escapeHtml(status)}</span></td>
        <td style="font-weight:600; color:var(--text-main);">${escapeHtml(f.feed_name || f.feed_id || "Feed")}</td>
        <td><code style="color:var(--text-code); font-size:11.5px; background:var(--code-bg); padding:1.5px 5.5px; border-radius:3px; border:1px solid var(--code-border);">${escapeHtml(f.log_type || "N/A")}</code></td>
        <td style="color:var(--text-muted); font-size:11.5px;">${escapeHtml(f.source_type || "CHRONICLE_API")}</td>
        <td>${escapeHtml(String(latency))}</td>
        <td style="color:var(--text-dim); font-size:11px;">${escapeHtml(String(lastHeartbeat))}</td>
        <td>
          <button class="btn btn-sm btn-ghost" ${act("switchTopicAndChat", "ingestion", "feed-health", `@feed-agent check feed latency for ${f.log_type || f.feed_name}`)}>
            Inspect
          </button>
        </td>
      </tr>
    `;
  }).join("");
}

function renderParsersTable() {
  const tbody = document.getElementById("parsersTableBody");
  if (!tbody) return;

  let parsers = ingestionData.parsers || [];

  if (ingestionData.parserFilter !== "all") {
    parsers = parsers.filter(p => (p.status || "").toUpperCase() === ingestionData.parserFilter);
  }

  if (ingestionData.parserSearch) {
    const q = ingestionData.parserSearch.toLowerCase();
    parsers = parsers.filter(p =>
      (p.log_type || "").toLowerCase().includes(q) ||
      (p.creator_source || "").toLowerCase().includes(q) ||
      (p.author || "").toLowerCase().includes(q) ||
      (p.message || "").toLowerCase().includes(q)
    );
  }

  if (parsers.length === 0) {
    tbody.innerHTML = `<tr><td colspan="7" class="table-loading">No parsers found matching filters.</td></tr>`;
    return;
  }

  tbody.innerHTML = parsers.map(p => {
    const status = p.status || "HEALTHY";
    const statusClass = status === "HEALTHY" ? "status-HEALTHY" : status === "WARN" || status === "VERSION_DRIFT" ? "status-WARN" : "status-FAILED";
    const hasDrift = p.version_drift_detected || (p.version && p.latest_version && p.version !== p.latest_version);
    const driftText = hasDrift ? "⚠️ Version Drift" : "Current";
    const dropReason = p.drop_reason_code || (p.drop_reasons && p.drop_reasons.length ? p.drop_reasons.join(", ") : "None");
    const author = p.creator_source || p.author || "Google SecOps";

    return `
      <tr>
        <td><span class="status-badge ${statusClass}">${escapeHtml(status)}</span></td>
        <td><code style="color:var(--accent-purple); font-weight:700; font-size:12px;">${escapeHtml(p.log_type || "N/A")}</code></td>
        <td style="color:var(--text-main);">${escapeHtml(p.state || "ACTIVE")}</td>
        <td style="color:var(--text-muted); font-size:11.5px;">${escapeHtml(author)}</td>
        <td style="font-size:11px; ${hasDrift ? 'color:var(--c-warn);' : 'color:var(--text-dim);'}">${escapeHtml(driftText)}</td>
        <td style="font-size:11px; color:var(--text-muted);">${escapeHtml(dropReason)}</td>
        <td>
          <button class="btn btn-sm btn-ghost" ${act("switchTopicAndChat", "ingestion", "parser-drops", `@parser-doctor diagnose unparsed logs for ${p.log_type}`)}>
            Diagnose
          </button>
        </td>
      </tr>
    `;
  }).join("");
}

async function handleAuditFeedsAction() {
  const btn = document.getElementById("pageBtnAuditFeeds");
  const banner = document.getElementById("ingestionStatusBanner");
  if (!btn) return;

  btn.disabled = true;
  const originalHtml = btn.innerHTML;
  btn.innerHTML = `<svg class="btn-svg spinner" viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 2v4M12 18v4M4.93 4.93l2.83 2.83M16.24 16.24l2.83 2.83M2 12h4M18 12h4M4.93 19.07l2.83-2.83M16.24 7.76l2.83-2.83"/></svg><span class="btn-text">Auditing Feeds...</span>`;
  
  if (banner) {
    banner.style.display = "flex";
    banner.innerHTML = `<span>Connecting to Chronicle Health Hub and evaluating all transport pipelines...</span>`;
  }
  
  try {
    const res = await fetch("/api/feeds/audit?lookback_days=7", { method: "POST" });
    if (!res.ok) {
      throw new Error(`HTTP ${res.status}: ${res.statusText}`);
    }
    const data = await res.json();
    const summary = data.summary || {};
    showToast("success", `Feed audit completed! ${summary.total_feeds_audited || 11} feeds evaluated against Health Hub.`);
    if (banner) {
      banner.innerHTML = `
        <span><strong>Feed Audit Completed:</strong> Evaluated ${summary.total_feeds_audited || 11} feeds (${summary.healthy_count || 11} healthy, ${summary.irregular_count || 0} warn, ${summary.failed_count || 0} degraded). Transport telemetry posted to <strong>#ingestion > feed-health</strong>.</span>
        <button class="btn btn-sm btn-ghost" ${act("switchTopicAndChat", "ingestion", "feed-health")}>View in Chat →</button>
      `;
    }
    await renderIngestionPage(true);
  } catch (err) {
    console.error("Feed audit failed:", err);
    showToast("error", `Feed audit failed: ${err.message}`);
    if (banner) {
      banner.innerHTML = `<span style="color:var(--c-danger);"><strong>Feed Audit Failed:</strong> ${escapeHtml(err.message)}</span>`;
    }
  } finally {
    btn.disabled = false;
    btn.innerHTML = originalHtml;
  }
}

async function handleAuditParsersAction() {
  const btn = document.getElementById("pageBtnAuditParsers");
  const banner = document.getElementById("ingestionStatusBanner");
  if (!btn) return;

  btn.disabled = true;
  const originalHtml = btn.innerHTML;
  btn.innerHTML = `<svg class="btn-svg spinner" viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 2v4M12 18v4M4.93 4.93l2.83 2.83M16.24 16.24l2.83 2.83M2 12h4M18 12h4M4.93 19.07l2.83-2.83M16.24 7.76l2.83-2.83"/></svg><span class="btn-text">Auditing Parsers...</span>`;

  if (banner) {
    banner.style.display = "flex";
    banner.innerHTML = `<span>Auditing SIEM normalizers and checking CBN syntax against Health Hub...</span>`;
  }

  try {
    const res = await fetch("/api/parsers/audit?lookback_days=7", { method: "POST" });
    if (!res.ok) {
      throw new Error(`HTTP ${res.status}: ${res.statusText}`);
    }
    const data = await res.json();
    const summary = data.summary || {};
    showToast("success", `Parser audit completed! ${summary.total_parsers_audited || 0} normalizers evaluated.`);
    if (banner) {
      banner.innerHTML = `
        <span><strong>Parser Audit Completed:</strong> Evaluated ${summary.total_parsers_audited || 0} parsers (${summary.healthy_count || 0} healthy, ${summary.version_drift_count || 0} version drifts, ${summary.extension_conflict_count || 0} conflicts). Normalization report posted to <strong>#ingestion > parser-drops</strong>.</span>
        <button class="btn btn-sm btn-ghost" ${act("switchTopicAndChat", "ingestion", "parser-drops")}>View in Chat →</button>
      `;
    }
    await renderIngestionPage(true);
  } catch (err) {
    console.error("Parser audit failed:", err);
    showToast("error", `Parser audit failed: ${err.message}`);
    if (banner) {
      banner.innerHTML = `<span style="color:var(--c-danger);"><strong>Parser Audit Failed:</strong> ${escapeHtml(err.message)}</span>`;
    }
  } finally {
    btn.disabled = false;
    btn.innerHTML = originalHtml;
  }
}

async function handleAuditRulesPageAction() {
  const btn = document.getElementById("pageBtnAuditRules");
  const banner = document.getElementById("ingestionStatusBanner");
  if (!btn) return;

  btn.disabled = true;
  const originalHtml = btn.innerHTML;
  btn.innerHTML = `<svg class="btn-svg spinner" viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 2v4M12 18v4M4.93 4.93l2.83 2.83M16.24 16.24l2.83 2.83M2 12h4M18 12h4M4.93 19.07l2.83-2.83M16.24 7.76l2.83-2.83"/></svg><span class="btn-text">Auditing Rules...</span>`;

  if (banner) {
    banner.style.display = "flex";
    banner.innerHTML = `<span>Evaluating unified detection repository health across custom &amp; curated rules...</span>`;
  }

  try {
    const res = await fetch("/api/rules/audit?include_curated=true&sync_embeddings=true&run_conflict_scan=true", { method: "POST" });
    if (!res.ok) {
      throw new Error(`HTTP ${res.status}: ${res.statusText}`);
    }
    const report = await res.json();
    showToast("success", `Rule audit completed! ${report.total_rules_scanned || 0} rules evaluated.`);
    if (banner) {
      banner.innerHTML = `
        <span><strong>Rule Repository Audit Completed:</strong> Evaluated ${report.total_rules_scanned || 0} rules (${report.healthy_count || 0} healthy, ${report.silent_decay_count || 0} silent, ${report.failing_count || 0} errors). Results posted to <strong>#detections &gt; decay-review</strong>.</span>
        <button class="btn btn-sm btn-ghost" ${act("switchTopicAndChat", "detections", "decay-review")}>View in Chat →</button>
      `;
    }
  } catch (err) {
    console.error("Rule audit failed:", err);
    showToast("error", `Rule audit failed: ${err.message}`);
    if (banner) {
      banner.innerHTML = `<span style="color:var(--c-danger);"><strong>Rule Audit Failed:</strong> ${escapeHtml(err.message)}</span>`;
    }
  } finally {
    btn.disabled = false;
    btn.innerHTML = originalHtml;
  }
}

async function handleRunLabDiagnose() {
  const logType = (document.getElementById("labLogTypeInput").value || "").trim();
  const lookback = parseInt(document.getElementById("labLookbackInput").value || "168", 10);
  const limit = parseInt(document.getElementById("labLimitInput").value || "5", 10);
  const resultsContainer = document.getElementById("labDiagnosticResults");
  const btn = document.getElementById("btnRunLabDiagnose");

  if (!logType) {
    showToast("error", "Please enter a log type (e.g. CS_EDR, WINEVTLOG, PAN_FIREWALL)");
    return;
  }

  btn.disabled = true;
  btn.innerHTML = "<span>⏳ Diagnosing...</span>";
  resultsContainer.innerHTML = `<div style="text-align:center; padding:24px; color:var(--text-dim);">🔬 Querying Chronicle raw unparsed events for <code>${escapeHtml(logType)}</code> and testing against active Logstash CBN code...</div>`;

  try {
    const res = await fetch(`/api/parsers/${encodeURIComponent(logType)}/diagnose?lookback_hours=${lookback}&limit=${limit}`, { method: "POST" });
    if (!res.ok) throw new Error(`HTTP ${res.status}: ${res.statusText}`);
    const data = await res.json();
    
    showToast("success", `✅ Diagnosed unparsed logs for ${logType}!`);
    renderDiagnosticResults(data, logType);
  } catch (err) {
    showToast("error", `Diagnosis failed: ${err.message}`);
    resultsContainer.innerHTML = `<div style="color:var(--c-danger); padding:16px;">❌ Error diagnosing logs: ${escapeHtml(err.message)}</div>`;
  } finally {
    btn.disabled = false;
    btn.innerHTML = "<span>Run Diagnosis</span>";
  }
}

function renderDiagnosticResults(data, logType) {
  const container = document.getElementById("labDiagnosticResults");
  if (!container) return;

  const result = data.diagnostic_result || data;
  const rawEvents = result.unparsed_samples || result.raw_events || [];
  const cbnCode = result.active_cbn_snippet || result.cbn_snippet || "No active CBN snippet available";
  const dropReason = result.primary_drop_code || result.error || "No explicit parser drop error detected";
  const totalAnalyzed = result.total_analyzed || rawEvents.length || 0;

  let samplesHtml = "";
  if (rawEvents.length > 0) {
    samplesHtml = rawEvents.map((ev, idx) => `
      <div style="background:var(--surface-inset-strong); border:1px solid var(--border-subtle); border-radius:4px; padding:8px 10px; margin-top:6px;">
        <div style="display:flex; justify-content:space-between; font-size:11px; color:var(--text-dim); margin-bottom:4px;">
          <span>Sample #${idx + 1}</span>
          <span>${escapeHtml(ev.timestamp || "Recent")}</span>
        </div>
        <pre style="margin:0; font-family:var(--font-mono); font-size:11px; color:var(--text-dim); white-space:pre-wrap; word-break:break-all;">${escapeHtml(ev.raw_log || ev.raw_text || JSON.stringify(ev))}</pre>
      </div>
    `).join("");
  } else {
    samplesHtml = `<div style="color:var(--text-dim); font-style:italic; padding:8px 0;">No unparsed raw log events found in lookback window.</div>`;
  }

  container.innerHTML = `
    <div style="display:flex; flex-direction:column; gap:12px;">
      <div style="display:flex; justify-content:space-between; align-items:center; border-bottom:1px solid var(--border-color); padding-bottom:8px;">
        <span style="font-weight:700; color:var(--text-main);">Diagnostic Report: <code>${escapeHtml(logType)}</code></span>
        <span style="font-size:11px; color:var(--text-accent);">${totalAnalyzed} unparsed events inspected</span>
      </div>
      <div>
        <div style="font-size:11px; font-weight:700; color:var(--text-dim); text-transform:uppercase;">Primary Normalization Drop Issue:</div>
        <div style="color:var(--c-danger); font-weight:600; margin-top:2px;">${escapeHtml(dropReason)}</div>
      </div>
      <div>
        <div style="font-size:11px; font-weight:700; color:var(--text-dim); text-transform:uppercase;">Active Logstash CBN Parser:</div>
        <pre style="background:var(--surface-inset); border:1px solid var(--border-subtle); border-radius:4px; padding:10px; font-size:11px; color:var(--c-violet); overflow-x:auto; margin-top:4px;">${escapeHtml(cbnCode)}</pre>
      </div>
      <div>
        <div style="font-size:11px; font-weight:700; color:var(--text-dim); text-transform:uppercase;">Raw Unparsed Event Samples:</div>
        ${samplesHtml}
      </div>
      <div style="margin-top:6px; display:flex; justify-content:flex-end;">
        <button class="btn btn-sm btn-ghost" ${act("switchTopicAndChat", "ingestion", "parser-drops", `@parser-doctor fix unparsed logs for ${logType}`)}>
          💬 Hand off to @parser-doctor for automated patch proposal
        </button>
      </div>
    </div>
  `;
}

// ====================================================================
// Gas Town Tabbed Control Center Controller (Gastown Replica)
// ====================================================================
const gastownState = {
  overview: null,
  proposals: [],
  activeSubtab: "kanban", // kanban, convoys, refinery, escalations
};

async function loadGastownOverview(force = false) {
  try {
    const [resOverview, resProposals] = await Promise.all([
      fetch("/api/gastown/overview"),
      fetch("/api/proposals"),
    ]);
    if (!resOverview.ok || !resProposals.ok) {
      throw new Error(`HTTP ${resOverview.status}/${resProposals.status}`);
    }
    gastownState.overview = await resOverview.json();
    gastownState.proposals = await resProposals.json();

    const banner = document.getElementById("gtLoadError");
    if (banner) { banner.hidden = true; banner.innerHTML = ""; }
    renderGastownHeader();
    renderGastownCurrentSubtab();
  } catch (err) {
    console.error("Failed loading Gas Town overview:", err);
    markGastownHeaderStale();
    const banner = document.getElementById("gtLoadError");
    if (banner) {
      banner.hidden = false;
      showLoadError(banner, {
        title: "Couldn't load the Actions overview — counts below are unavailable",
        error: err,
        retry: () => loadGastownOverview(true),
      });
    }
  }
}

const UNKNOWN_METRIC = "—";

// Replace header metrics with explicit "unknown" markers when the overview
// endpoint cannot be reached, so stale or placeholder values are never shown
// as live.
function markGastownHeaderStale() {
  [
    "gtStatPolecats",
    "gtStatHooks",
    "gtStatWork",
    "gtStatLeases",
    "gtStatConvoys",
    "gtStatEscalations",
  ].forEach((id) => {
    const el = document.getElementById(id);
    if (el) el.textContent = UNKNOWN_METRIC;
  });
  const hb = document.getElementById("gtDeaconHeartbeat");
  if (hb) {
    hb.textContent = "Scheduler: unavailable";
    hb.className = "gt-stat-val unknown";
  }
  const fleet = document.getElementById("gtFleetOnline");
  if (fleet) fleet.textContent = "Agents Online: unavailable";
  const alert = document.getElementById("gtAlertItem");
  if (alert) {
    alert.textContent = "⚠ Overview unavailable — pending review count unknown";
    alert.className = "gt-alert-pill gt-alert-unknown";
    alert.disabled = true;
    alert.removeAttribute("title");
  }
  setTopbarEscalations(null);
}

function renderGastownHeader() {
  if (!gastownState.overview) return;
  const ov = gastownState.overview;

  // Mayor
  const gtMayorHandle = document.getElementById("gtMayorHandle");
  if (gtMayorHandle && ov.mayor) {
    gtMayorHandle.textContent = ov.mayor.coordinator || "@secops-dispatcher";
  }

  // Health
  const gtDeaconHeartbeat = document.getElementById("gtDeaconHeartbeat");
  if (gtDeaconHeartbeat) {
    const hb = ov.health && ov.health.deacon_heartbeat;
    if (hb) {
      gtDeaconHeartbeat.textContent = `✓ Scheduler healthy (${hb})`;
      gtDeaconHeartbeat.className = "gt-stat-val healthy";
    } else {
      gtDeaconHeartbeat.textContent = "Scheduler: unknown";
      gtDeaconHeartbeat.className = "gt-stat-val unknown";
    }
  }

  // Summary Metrics — never substitute fabricated numbers for missing data.
  const summary = ov.summary || {};
  const polecatCount = summary.polecat_count ?? UNKNOWN_METRIC;
  const hookCount = summary.hook_count ?? UNKNOWN_METRIC;
  const issueCount = summary.issue_count ?? UNKNOWN_METRIC;
  const convoyCount = summary.convoy_count ?? UNKNOWN_METRIC;
  const escalationCount = summary.escalation_count ?? UNKNOWN_METRIC;

  const statPolecats = document.getElementById("gtStatPolecats");
  const statFleetOnline = document.getElementById("gtFleetOnline");
  const statHooks = document.getElementById("gtStatHooks");
  const statWork = document.getElementById("gtStatWork");
  const statLeases = document.getElementById("gtStatLeases");
  const statConvoys = document.getElementById("gtStatConvoys");
  const statEscalations = document.getElementById("gtStatEscalations");

  if (statPolecats) statPolecats.textContent = polecatCount;
  if (statFleetOnline) {
    statFleetOnline.textContent =
      polecatCount === UNKNOWN_METRIC ? "Agents Online: unknown" : `${polecatCount} Agents Online`;
  }
  if (statHooks) statHooks.textContent = hookCount;
  if (statWork) statWork.textContent = issueCount;
  if (statLeases) statLeases.textContent = summary.soc_leases_active ?? UNKNOWN_METRIC;
  if (statConvoys) statConvoys.textContent = convoyCount;
  if (statEscalations) statEscalations.textContent = escalationCount;
  setTopbarEscalations(typeof summary.escalation_count === "number" ? summary.escalation_count : null);

  // Alerts Strip
  const gtAlertItem = document.getElementById("gtAlertItem");
  const openProps = (gastownState.proposals || []).filter((p) => p.status === "OPEN").length;
  if (gtAlertItem) {
    if (openProps > 0) {
      gtAlertItem.textContent = `⏰ ${openProps} proposal${openProps > 1 ? "s" : ""} awaiting HITL operator review →`;
      gtAlertItem.className = "gt-alert-pill";
      gtAlertItem.disabled = false;
      gtAlertItem.title = "Show the HITL Review column";
    } else {
      gtAlertItem.textContent = "✓ All clear — 0 pending reviews";
      gtAlertItem.className = "gt-alert-pill gt-alert-green";
      gtAlertItem.disabled = true;
      gtAlertItem.removeAttribute("title");
    }
  }

  // Update Top Nav and Drawer Badges
  setOpenProposalBadges(openProps);
}

// Alert strip -> Kanban board, scrolled to and briefly highlighting the review column.
function focusReviewColumn() {
  switchGastownSubtab("kanban");
  const col = document.getElementById("kanbanColReview");
  if (!col) return;
  if (col.scrollIntoView) col.scrollIntoView({ behavior: "smooth", block: "nearest", inline: "nearest" });
  col.classList.remove("kanban-col-flash");
  void col.offsetWidth; // restart the animation if clicked repeatedly
  col.classList.add("kanban-col-flash");
  const first = col.querySelector(".kanban-card, .kanban-card-action-btn");
  if (first && first.focus) {
    if (!first.hasAttribute("tabindex") && first.tagName !== "BUTTON") first.setAttribute("tabindex", "-1");
    first.focus({ preventScroll: true });
  }
}

function switchGastownSubtab(subtabName) {
  gastownState.activeSubtab = subtabName;

  const tabs = [
    { id: "tabGtKanban", sec: "secGtKanban", name: "kanban" },
    { id: "tabGtWorkQueue", sec: "secGtWorkQueue", name: "work_queue" },
    { id: "tabGtConvoys", sec: "secGtConvoys", name: "convoys" },
    { id: "tabGtRefinery", sec: "secGtRefinery", name: "refinery" },
    { id: "tabGtEscalations", sec: "secGtEscalations", name: "escalations" },
    { id: "tabGtPatrols", sec: "secGtPatrols", name: "patrols" },
  ];

  tabs.forEach((t) => {
    const tabEl = document.getElementById(t.id);
    const secEl = document.getElementById(t.sec);
    if (tabEl) {
      if (t.name === subtabName) {
        tabEl.classList.add("active");
      } else {
        tabEl.classList.remove("active");
      }
    }
    if (secEl) {
      secEl.style.display = t.name === subtabName ? "block" : "none";
    }
  });
  document.querySelectorAll(".gt-summary-card[data-gt-target]").forEach((card) => {
    const on = card.dataset.gtTarget === subtabName;
    card.classList.toggle("is-active", on);
    if (on) card.setAttribute("aria-current", "true");
    else card.removeAttribute("aria-current");
  });

  renderGastownCurrentSubtab();
}
window.switchGastownSubtab = switchGastownSubtab;

function renderGastownCurrentSubtab() {
  switch (gastownState.activeSubtab) {
    case "kanban":
      renderGastownKanban();
      break;
    case "work_queue":
      renderGastownWorkQueue();
      break;
    case "convoys":
      renderGastownConvoys();
      break;
    case "refinery":
      renderGastownRefinery();
      break;
    case "escalations":
      renderGastownEscalations();
      break;
    case "patrols":
      renderGastownPatrols();
      break;
  }
}

function renderSocKanbanCard(iss) {
  const id = escapeHtml(iss.issue_id);
  const title = escapeHtml(iss.problem?.title || iss.title || "Operational Issue");
  const target = escapeHtml(iss.problem?.target_resource_id || "Resource");
  const sev = (iss.problem?.severity || "MEDIUM").toUpperCase();
  const sevClass = (sev === "CRITICAL" || sev === "HIGH") ? "badge-risk-high" : (sev === "MEDIUM" ? "badge-risk-medium" : "badge-risk-low");
  const plane = (iss.operational_plane || "data").toUpperCase();
  const holder = iss.lease?.holder_agent || "unassigned";

  return `
    <div class="kanban-card" role="button" tabindex="0" ${act("viewSocIssueDetail", iss.issue_id)} style="border-left: 3px solid var(--c-indigo);">
      <div class="kanban-card-head">
        <span class="kanban-card-id" style="color:var(--c-indigo);">${id}</span>
        <div style="display:flex; align-items:center; gap:4px;">
          <span class="kanban-card-badge" style="background:var(--c-indigo-bg); color:var(--c-indigo); font-size:11px;">${plane}</span>
          <span class="kanban-card-badge ${sevClass}">${sev}</span>
        </div>
      </div>
      <div class="kanban-card-title">${title}</div>
      <div class="kanban-card-target">${target}</div>
      <div class="kanban-card-footer">
        <span class="kanban-card-author">${getAgentAvatarSvg(holder, 13)} ${escapeHtml(holder)}</span>
        <button class="kanban-card-action-btn" ${act("viewSocIssueDetail", iss.issue_id)}>Ledger 📜</button>
      </div>
    </div>
  `;
}

function renderGastownKanban() {
  const proposals = gastownState.proposals || [];
  const overview = gastownState.overview || {};
  const socIssues = overview.soc_issues || [];

  // Col 1: Triage / Backlog
  const colTriage = document.getElementById("cardsColTriage");
  const countColTriage = document.getElementById("countColTriage");
  const triageItems = overview.todos_pending || [];
  const socTriage = socIssues.filter(i => i.status === "AVAILABLE" || i.status === "OBSERVED");
  const totalTriage = triageItems.length + socTriage.length;
  if (countColTriage) countColTriage.textContent = totalTriage;
  if (colTriage) {
    if (totalTriage === 0) {
      colTriage.innerHTML = `<div style="color:var(--text-dim); font-size:12px; text-align:center; padding:24px 8px;">No pending triage items.</div>`;
    } else {
      const socCards = socTriage.map(renderSocKanbanCard).join("");
      const todoCards = triageItems.map((item) => {
        const id = item.todo_id || item.id || "TODO";
        const priority = (item.priority || "MEDIUM").toUpperCase();
        const badgeClass = priority === "HIGH" || priority === "CRITICAL" ? "badge-risk-high" : (priority === "MEDIUM" ? "badge-risk-medium" : "badge-risk-low");
        const author = item.target_agent || item.author || "@detection-decay-agent";
        const target = item.target_resource_id || item.target || "Chronicle Resource";
        const stream = item.stream || "detections";
        const topic = item.topic || "decay-review";
        const prompt = item.action_prompt || `${author} audit rule ${target}`;
        const sightingBadge = (item.sighting_count && item.sighting_count > 1)
          ? `<span class="kanban-card-badge badge-sighting" title="Seen in ${item.sighting_count} audit runs">👁️ ${item.sighting_count}x</span>`
          : "";
        return `
          <div class="kanban-card">
            <div class="kanban-card-head">
              <span class="kanban-card-id">${escapeHtml(id)}</span>
              <div style="display:flex; align-items:center; gap:6px;">
                ${sightingBadge}
                <span class="kanban-card-badge ${badgeClass}">${priority} PRIORITY</span>
              </div>
            </div>
            <div class="kanban-card-title">${escapeHtml(item.title || "Remediation Task")}</div>
            <div class="kanban-card-target">${escapeHtml(target)}</div>
            <div class="kanban-card-footer">
              <span class="kanban-card-author">${renderAvatar("agent", author)} ${escapeHtml(author)}</span>
              <div style="display:flex; gap:6px;">
                <button class="kanban-card-action-btn" ${act("switchTopicAndChat", stream, topic, prompt)}>Triage</button>
                <button class="kanban-card-action-btn" style="background:transparent; border-color:var(--border-subtle); color:var(--text-muted);" ${act("handleDismissTodo", id)} title="Dismiss or resolve this task">Dismiss</button>
              </div>
            </div>
          </div>
        `;
      }).join("");
      colTriage.innerHTML = socCards + todoCards;
    }
  }

  // Col 2: In Progress (Agents)
  const colProgress = document.getElementById("cardsColProgress");
  const countColProgress = document.getElementById("countColProgress");
  const progressItems = overview.todos_in_progress || [];
  const socProgress = socIssues.filter(i => i.status === "LEASED" || i.status === "CLAIMED" || i.status === "EXECUTING");
  const totalProgress = progressItems.length + socProgress.length;
  if (countColProgress) countColProgress.textContent = totalProgress;
  if (colProgress) {
    if (totalProgress === 0) {
      colProgress.innerHTML = `<div style="color:var(--text-dim); font-size:12px; text-align:center; padding:24px 8px;">No active agent tasks in progress.</div>`;
    } else {
      const socCards = socProgress.map(renderSocKanbanCard).join("");
      const todoCards = progressItems.map((item) => {
        const id = item.todo_id || item.id || "WORK";
        const priority = (item.priority || "MEDIUM").toUpperCase();
        const badgeClass = priority === "HIGH" || priority === "CRITICAL" ? "badge-risk-high" : (priority === "MEDIUM" ? "badge-risk-medium" : "badge-risk-low");
        const author = item.target_agent || item.author || "@detection-tuning-agent";
        const target = item.target_resource_id || item.target || "Chronicle Resource";
        const stream = item.stream || "detections";
        const topic = item.topic || "tuning-review";
        const prompt = item.action_prompt || `${author} tune rule ${target}`;
        const sightingBadge = (item.sighting_count && item.sighting_count > 1)
          ? `<span class="kanban-card-badge badge-sighting" title="Seen in ${item.sighting_count} audit runs">👁️ ${item.sighting_count}x</span>`
          : "";
        return `
          <div class="kanban-card">
            <div class="kanban-card-head">
              <span class="kanban-card-id">${escapeHtml(id)}</span>
              <div style="display:flex; align-items:center; gap:6px;">
                ${sightingBadge}
                <span class="kanban-card-badge ${badgeClass}">ACTIVE</span>
              </div>
            </div>
            <div class="kanban-card-title">${escapeHtml(item.title || "Optimization Task")}</div>
            <div class="kanban-card-target">${escapeHtml(target)}</div>
            <div class="kanban-card-footer">
              <span class="kanban-card-author">${renderAvatar("agent", author)} ${escapeHtml(author)}</span>
              <div style="display:flex; gap:6px;">
                <button class="kanban-card-action-btn" ${act("switchTopicAndChat", stream, topic, prompt)}>Inspect</button>
                <button class="kanban-card-action-btn" style="background:transparent; border-color:var(--border-subtle); color:var(--text-muted);" ${act("handleDismissTodo", id)} title="Dismiss or resolve this task">Dismiss</button>
              </div>
            </div>
          </div>
        `;
      }).join("");
      colProgress.innerHTML = socCards + todoCards;
    }
  }

  // Col 3: HITL Review (Proposals & Validations)
  const colReview = document.getElementById("cardsColReview");
  const countColReview = document.getElementById("countColReview");
  const openProposals = proposals.filter((p) => p.status === "OPEN");
  const socReview = socIssues.filter(i => i.status === "VALIDATING");
  const totalReview = openProposals.length + socReview.length;
  if (countColReview) countColReview.textContent = totalReview;
  if (colReview) {
    if (totalReview === 0) {
      colReview.innerHTML = `<div style="color:var(--text-dim); font-size:12px; text-align:center; padding:24px 8px;">No pending proposals awaiting review.</div>`;
    } else {
      const socCards = socReview.map(renderSocKanbanCard).join("");
      const propCards = openProposals.map((p) => {
        const riskClass = p.risk_level === "CRITICAL" ? "badge-risk-high" : (p.risk_level === "MEDIUM" ? "badge-risk-medium" : "badge-risk-low");
        const author = p.author || p.author_agent || "@secops-dispatcher";
        const target = p.target_resource_id || p.target_resource || "SecOps Resource";
        return `
          <div class="kanban-card" role="button" tabindex="0" ${act("openGastownDiffModal", p.id)}>
            <div class="kanban-card-head">
              <span class="kanban-card-id">${escapeHtml(p.id)}</span>
              <span class="kanban-card-badge ${riskClass}">${p.risk_level || "PROPOSAL"}</span>
            </div>
            <div class="kanban-card-title">${escapeHtml(p.title || p.rationale || "Rule update proposal")}</div>
            <div class="kanban-card-target">${escapeHtml(target)}</div>
            <div class="kanban-card-footer">
              <span class="kanban-card-author">${renderAvatar("agent", author)} ${escapeHtml(author)}</span>
              <button class="kanban-card-action-btn" ${act("openGastownDiffModal", p.id)}>Review Diff ↗</button>
              <button class="kanban-card-action-btn" style="margin-left:4px;" ${act("switchTopicAndChat", "detections", "rule-proposals", `${author} review proposal ${p.id}`)}>Discuss 💬</button>
            </div>
          </div>
        `;
      }).join("");
      colReview.innerHTML = socCards + propCards;
    }
  }

  // Col 4: Merged / Resolved
  const colMerged = document.getElementById("cardsColMerged");
  const countColMerged = document.getElementById("countColMerged");
  const closedProposals = proposals.filter((p) => p.status === "MERGED" || p.status === "APPLIED" || p.status === "CLOSED" || p.status === "REJECTED");
  const socMerged = socIssues.filter(i => i.status === "APPROVED" || i.status === "APPLIED" || i.status === "CLOSED" || i.status === "VERIFIED");
  const totalMerged = closedProposals.length + socMerged.length;
  if (countColMerged) countColMerged.textContent = totalMerged;
  if (colMerged) {
    if (totalMerged === 0) {
      colMerged.innerHTML = `<div style="color:var(--text-dim); font-size:12px; text-align:center; padding:24px 8px;">No applied proposals yet.</div>`;
    } else {
      const socCards = socMerged.map(renderSocKanbanCard).join("");
      const propCards = closedProposals.map((p) => {
        const isMerged = p.status === "MERGED" || p.status === "APPLIED";
        const author = p.author || p.author_agent || "@secops-dispatcher";
        const target = p.target_resource_id || p.target_resource || "SecOps Resource";
        return `
          <div class="kanban-card" role="button" tabindex="0" ${act("openGastownDiffModal", p.id)} style="opacity:0.85;">
            <div class="kanban-card-head">
              <span class="kanban-card-id">${escapeHtml(p.id)}</span>
              <span class="kanban-card-badge ${isMerged ? 'badge-risk-low' : 'badge-risk-high'}">${p.status}</span>
            </div>
            <div class="kanban-card-title">${escapeHtml(p.title || p.rationale || "Resolved mutation")}</div>
            <div class="kanban-card-target">${escapeHtml(target)}</div>
            <div class="kanban-card-footer">
              <span class="kanban-card-author">${renderAvatar("agent", author)} ${escapeHtml(author)}</span>
              <button class="kanban-card-action-btn" ${act("openGastownDiffModal", p.id)}>View Details</button>
            </div>
          </div>
        `;
      }).join("");
      colMerged.innerHTML = socCards + propCards;
    }
  }
}

function renderGastownConvoys() {
  const tbody = document.getElementById("gtConvoysTableBody");
  if (!tbody) return;
  const convoys = (gastownState.overview && gastownState.overview.convoys) || [];
  if (convoys.length === 0) {
    tbody.innerHTML = `<tr><td colspan="6" style="text-align:center; color:var(--text-dim); padding:20px;">No active work packages.</td></tr>`;
    return;
  }

  tbody.innerHTML = convoys.map((c) => {
    const status = (c.status || c.work_status || "ACTIVE").toUpperCase();
    const ready = c.ready_beads ?? c.work_ready ?? 0;
    const active = c.in_progress ?? c.work_active ?? 0;
    const done = c.work_done ?? (c.progress_pct === 100 ? (c.progress ? c.progress.split('/')[1] : 11) : 0);
    return `
    <tr>
      <td>
        <span class="badge ${status === 'ACTIVE' ? 'badge-blue' : 'badge-green'}">${status}</span>
      </td>
      <td>
        <div style="font-weight:600; color:var(--text-main); font-size:13px;">${escapeHtml(c.title)}</div>
        <div style="font-family:var(--font-mono); font-size:11px; color:var(--c-info);">${c.id}</div>
      </td>
      <td>
        <div style="display:flex; justify-content:space-between; font-size:11px; font-weight:600; margin-bottom:2px;">
          <span>Completion</span>
          <span style="font-family:var(--font-mono);">${c.progress_pct}%</span>
        </div>
        <div class="gt-progress-bar">
          <div class="gt-progress-fill" style="width: ${c.progress_pct}%;"></div>
        </div>
      </td>
      <td>
        <span class="work-chip work-chip-ready">${ready} ready</span>
        <span class="work-chip work-chip-active">${active} active</span>
        <span class="work-chip work-chip-done">${done} done</span>
      </td>
      <td>
        <div style="display:flex; gap:6px; flex-wrap:wrap;">
          ${(c.assignees || []).map((a) => `<span class="tag-cell" style="font-size:11px;">${renderAvatar("agent", a)} ${a}</span>`).join("")}
        </div>
      </td>
      <td>
        <button class="btn btn-secondary btn-sm" ${act("switchTopicAndChat", c.stream || "detections", c.topic || "rule-proposals", c.action_prompt || `${c.primary_agent || "@secops-dispatcher"} status convoy ${c.id}`)}>Inspect</button>
      </td>
    </tr>
  `;
  }).join("");
}

function renderGastownRefinery() {
  const tbody = document.getElementById("gtRefineryTableBody");
  if (!tbody) return;
  const proposals = gastownState.proposals || [];
  if (proposals.length === 0) {
    tbody.innerHTML = `<tr><td colspan="7" style="text-align:center; color:var(--text-dim); padding:20px;">No changes awaiting review.</td></tr>`;
    return;
  }

  tbody.innerHTML = proposals.map((p) => {
    const isMerged = p.status === "MERGED" || p.status === "APPLIED";
    const isRejected = p.status === "REJECTED";
    const author = p.author || p.author_agent || "@secops-dispatcher";
    const target = p.target_resource_id || p.target_resource || "SecOps Resource";
    const diff = p.proposed_diff || p.diff || "";
    const gates = getPreflightGates(p);
    const gatesPassed = gates.filter((g) => g.ok).length;
    const totalGates = gates.length;
    const gateBadge = gatesPassed === totalGates ? "badge-green" : (gatesPassed === 0 ? "badge-red" : "badge-yellow");
    const gateTitle = gates.map((g) => `${g.ok ? "✓" : "✗"} ${g.label}`).join("\n");
    const stats = getDiffStats(diff);
    return `
      <tr>
        <td>
          <code style="font-size:11px; color:var(--c-info);">${escapeHtml(p.id)}</code>
        </td>
        <td>
          <div style="font-size:12.5px; font-weight:600; color:var(--text-main);">${escapeHtml(p.title || target)}</div>
          <code style="font-size:11px; color:var(--text-dim);">${escapeHtml(target)}</code>
        </td>
        <td>
          <span style="display:flex; align-items:center; gap:5px; font-size:12px;">
            ${renderAvatar("agent", author)} ${escapeHtml(author)}
          </span>
        </td>
        <td>
          <span class="badge ${gateBadge}" title="${escapeHtml(gateTitle)}">${gatesPassed}/${totalGates} gates passed</span>
        </td>
        <td>
          <span class="badge ${isMerged ? 'badge-green' : (isRejected ? 'badge-red' : 'badge-blue')}">${p.status}</span>
        </td>
        <td>
          ${diff ? `
          <span style="font-family:var(--font-mono); font-size:11px; color:var(--c-ok);">+${stats.added}</span>
          <span style="font-family:var(--font-mono); font-size:11px; color:var(--c-danger); margin-left:4px;">-${stats.removed}</span>
          ` : `<span style="font-size:11px; color:var(--text-dim);">No diff</span>`}
        </td>
        <td>
          <div style="display:flex; gap:6px;">
            <button class="btn btn-secondary btn-sm" ${act("openGastownDiffModal", p.id)}>Inspect</button>
            ${p.status === 'OPEN' ? `
              <button class="btn btn-primary btn-sm" ${act("handleProposalAction", p.id, "approve")}>Approve</button>
              <button class="btn btn-danger btn-sm" ${act("handleProposalAction", p.id, "reject")}>Reject</button>
            ` : ''}
          </div>
        </td>
      </tr>
    `;
  }).join("");
}

function renderGastownEscalations() {
  const tbody = document.getElementById("gtEscalationsTableBody");
  if (!tbody) return;
  const escalations = (gastownState.overview && gastownState.overview.escalations) || [];
  if (escalations.length === 0) {
    tbody.innerHTML = `<tr><td colspan="6" style="text-align:center; color:var(--text-dim); padding:20px;">No active escalations.</td></tr>`;
    return;
  }

  tbody.innerHTML = escalations.map((esc) => {
    const escStream = esc.stream || (esc.target && esc.target.startsWith("ru_") ? "detections" : "ingestion");
    const escTopic = esc.topic || (escStream === "detections" ? "rule-proposals" : "parser-drops");
    const escPrompt = esc.action_prompt || `${esc.escalated_by} diagnose unparsed logs for ${esc.target || esc.id}`;
    const sev = String(esc.severity || "").toUpperCase();
    const ackCell = esc.acked
      ? `<span class="badge badge-gray" title="Acknowledged by ${escapeHtml(esc.acked_by || "operator")}${esc.acked_at ? " at " + escapeHtml(new Date(esc.acked_at).toLocaleString()) : ""}">Acked</span>`
      : `<button class="btn btn-secondary btn-sm" ${act("handleAckEscalation", esc.id)}>Ack</button>`;
    return `
    <tr class="${esc.acked ? "row-acked" : ""}">
      <td>
        <span class="badge ${sev === 'CRITICAL' ? 'badge-red' : 'badge-yellow'}">${escapeHtml(sev)}</span>
      </td>
      <td>
        <div style="font-weight:600; color:var(--text-main); font-size:12.5px;">${escapeHtml(esc.title)}</div>
        <div style="font-size:11px; color:var(--text-muted);">${escapeHtml(esc.details || "")}</div>
      </td>
      <td>
        <code style="font-size:11px; color:var(--text-dim);">${escapeHtml(esc.target || "")}</code>
      </td>
      <td>
        <span style="font-size:12px; color:var(--text-muted);">${renderAvatar("agent", esc.escalated_by)} ${escapeHtml(esc.escalated_by)}</span>
      </td>
      <td style="font-family:var(--font-mono); font-size:11px; color:var(--text-dim);" title="${escapeHtml(esc.created_at || "")}">
        ${escapeHtml(esc.age || UNKNOWN_METRIC)}
      </td>
      <td>
        <div style="display:flex; gap:6px; align-items:center;">
          ${ackCell}
          <button class="btn btn-primary btn-sm" ${act("switchTopicAndChat", escStream, escTopic, escPrompt)}>Resolve</button>
        </div>
      </td>
    </tr>
  `;
  }).join("");
}

async function handleAckEscalation(escalationId) {
  try {
    const res = await fetch(`/api/gastown/escalations/${encodeURIComponent(escalationId)}/ack`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ acked_by: "secops-operator" }),
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      showToast("error", `Acknowledge failed: ${err.detail || res.status}`);
      return;
    }
    showToast("success", `Escalation ${escalationId} acknowledged`);
    await loadGastownOverview(true);
  } catch (err) {
    showToast("error", `Acknowledge error: ${err.message}`);
  }
}
window.handleAckEscalation = handleAckEscalation;

// Real preflight gates for a proposal — only what the proposal record actually proves.
function getPreflightGates(p) {
  const pf = p.preflight_proof || p.preflight || {};
  return [
    { label: "Syntax compiler", ok: !!pf.syntax_verified, detail: (pf.compiler_diagnostics || []).join("; ") },
    { label: "Empirical replay", ok: !!pf.replay_verified, detail: pf.replay_summary || "" },
  ];
}

function getDiffStats(diff) {
  const lines = (diff || "").split("\n");
  return {
    added: lines.filter((l) => l.startsWith("+") && !l.startsWith("+++")).length,
    removed: lines.filter((l) => l.startsWith("-") && !l.startsWith("---")).length,
  };
}

// Modal a11y: Esc closes, backdrop click closes, Tab is trapped, focus is restored.
function activateModal(modal, closeFn) {
  deactivateModal(modal);
  const state = { previouslyFocused: document.activeElement };
  state.onKey = (e) => {
    // An action dialog stacked above owns the keyboard.
    if (document.querySelector(".action-dialog-overlay")) return;
    if (e.key === "Escape") {
      e.preventDefault();
      closeFn();
    } else if (e.key === "Tab") {
      const focusables = Array.from(modal.querySelectorAll("button, [href], input, select, textarea, [tabindex]:not([tabindex='-1'])"))
        .filter((el) => !el.disabled && el.offsetParent !== null);
      if (focusables.length === 0) return;
      const first = focusables[0];
      const last = focusables[focusables.length - 1];
      if (e.shiftKey && document.activeElement === first) { e.preventDefault(); last.focus(); }
      else if (!e.shiftKey && document.activeElement === last) { e.preventDefault(); first.focus(); }
    }
  };
  state.onMouseDown = (e) => { if (e.target === modal) closeFn(); };
  document.addEventListener("keydown", state.onKey);
  modal.addEventListener("mousedown", state.onMouseDown);
  modal._a11y = state;
  const closeBtn = modal.querySelector(".gt-modal-close-btn");
  if (closeBtn) closeBtn.focus();
}

function deactivateModal(modal) {
  const state = modal && modal._a11y;
  if (!state) return;
  document.removeEventListener("keydown", state.onKey);
  modal.removeEventListener("mousedown", state.onMouseDown);
  modal._a11y = null;
  if (state.previouslyFocused && document.contains(state.previouslyFocused) && typeof state.previouslyFocused.focus === "function") {
    state.previouslyFocused.focus();
  }
}

function openGastownDiffModal(proposalId) {
  const p = (gastownState.proposals || []).find((item) => item.id === proposalId)
    || (state.proposals || []).find((item) => item.id === proposalId);
  if (!p) {
    showToast("warning", `Proposal ${proposalId} is no longer available — it may have been resolved.`);
    return;
  }

  const modal = document.getElementById("gastownDiffModal");
  if (!modal) return;

  const author = p.author || p.author_agent || "@secops-dispatcher";
  const target = p.target_resource_id || p.target_resource || "SecOps Resource";
  const diff = p.proposed_diff || p.diff || "";

  const badgeEl = document.getElementById("modalProposalBadge");
  const titleEl = document.getElementById("modalProposalTitle");
  const targetEl = document.getElementById("modalTargetResource");
  const authorEl = document.getElementById("modalAuthorAgent");
  const riskEl = document.getElementById("modalRiskLevel");
  const subEl = document.getElementById("modalSubsystem");
  const ratEl = document.getElementById("modalRationale");

  if (badgeEl) badgeEl.textContent = p.risk_level || "PROPOSAL";
  if (titleEl) titleEl.textContent = p.title || `Proposal ${p.id}`;
  if (targetEl) targetEl.textContent = target;
  if (authorEl) authorEl.textContent = author;
  if (riskEl) riskEl.textContent = p.risk_level || "MEDIUM";
  if (subEl) subEl.textContent = p.subsystem || "Detections";
  if (ratEl) {
    ratEl.textContent = p.rationale || "No rationale provided by the authoring agent.";
    ratEl.classList.toggle("is-empty", !p.rationale);
  }

  const proofBox = document.getElementById("modalPreflightProof");
  if (proofBox) {
    const gates = getPreflightGates(p);
    const allOk = gates.every((g) => g.ok);
    proofBox.innerHTML = `
      <div class="gt-gate-list">
        ${gates.map((g) => `
          <div class="gt-gate ${g.ok ? "is-pass" : "is-missing"}">
            <span class="gt-gate-status">${g.ok ? "✓ PASS" : "✗ NOT VERIFIED"}</span>
            <span class="gt-gate-label">${escapeHtml(g.label)}</span>
            ${g.detail ? `<span class="gt-gate-detail">${escapeHtml(g.detail)}</span>` : ""}
          </div>`).join("")}
      </div>
      ${allOk ? "" : `<div class="gt-gate-warning">⚠ Not all preflight gates are verified. Review the diff carefully before merging.</div>`}
    `;
  }

  const diffBlock = document.getElementById("modalDiffContent");
  if (diffBlock) {
    if (diff) {
      diffBlock.innerHTML = formatUnifiedDiff(diff);
      diffBlock.classList.remove("is-empty");
    } else {
      diffBlock.textContent = "No diff attached to this proposal.";
      diffBlock.classList.add("is-empty");
    }
  }

  const isOpen = p.status === "OPEN";
  const btnApprove = document.getElementById("modalBtnApprove");
  const btnReject = document.getElementById("modalBtnReject");
  const setBusy = (busy) => {
    if (btnApprove) btnApprove.disabled = busy;
    if (btnReject) btnReject.disabled = busy;
  };
  if (btnApprove) {
    btnApprove.hidden = !isOpen;
    btnApprove.onclick = async () => {
      setBusy(true);
      const done = await handleApproveProposal(p.id);
      setBusy(false);
      if (done) closeGastownDiffModal();
    };
  }
  if (btnReject) {
    btnReject.hidden = !isOpen;
    btnReject.onclick = async () => {
      setBusy(true);
      const done = await handleRejectProposal(p.id);
      setBusy(false);
      if (done) closeGastownDiffModal();
    };
  }

  modal.style.display = "flex";
  activateModal(modal, closeGastownDiffModal);
}
window.openGastownDiffModal = openGastownDiffModal;

function closeGastownDiffModal() {
  const modal = document.getElementById("gastownDiffModal");
  if (!modal) return;
  modal.style.display = "none";
  deactivateModal(modal);
}
window.closeGastownDiffModal = closeGastownDiffModal;

async function renderGastownPatrols() {
  const grid = document.getElementById("gtDeaconPatrolsGrid");
  const logTbody = document.getElementById("gtPatrolAuditLogBody");
  if (!grid) return;

  try {
    const res = await fetch("/api/gastown/patrols");
    if (!res.ok) throw new Error(await describeHttpError(res));
    const data = await res.json();
    const deacon = data.deacon || {};
    const schedules = data.schedules || [];

    // Update Header Badges
    const statusBadge = document.getElementById("gtDeaconStatusBadge");
    const heartbeatDetail = document.getElementById("gtDeaconHeartbeatDetail");
    const activePatrolsPill = document.getElementById("gtDeaconActivePatrolsPill");

    if (statusBadge) {
      const isHealthy = deacon.status === "healthy";
      statusBadge.textContent = isHealthy ? "SCHEDULER ONLINE" : "SCHEDULER STANDBY";
      statusBadge.className = `gt-badge ${isHealthy ? "gt-badge-green" : "gt-badge-yellow"}`;
    }
    if (heartbeatDetail) {
      heartbeatDetail.textContent = deacon.deacon_heartbeat
        ? `Last check-in: ${deacon.deacon_heartbeat}`
        : "Last check-in: unknown";
    }
    if (activePatrolsPill) {
      activePatrolsPill.textContent = `${deacon.active_patrols || schedules.length} scheduled audits (${deacon.total_patrols_run || 0} runs)`;
    }

    // Agent Avatars & Descriptions
    const agentMeta = {
      "@feed-agent": { icon: "📡", name: "Feed Health Agent", desc: "Monitors transport lag, P95 latency SLAs, HTTP 429 quota rejections, and ingestion pipeline faults." },
      "@parser-doctor": { icon: "🔬", name: "Parser Doctor", desc: "Audits Logstash CBN normalizers, unparsed log drops (Drop Code 1), and schema field drift." },
      "@detection-tuning-agent": { icon: "📉", name: "Detection Tuning Agent", desc: "Detects alert fatigue anomalies, analyzes top firing rules, and synthesizes exclusion filters." },
      "@detection-decay-agent": { icon: "🛡️", name: "Detection Decay Agent", desc: "Verifies YARA-L rule inventory syntax, broken references, and silent rules with zero telemetry." },
      "@identity-governor": { icon: "🔑", name: "Identity Governor", desc: "Audits GCP IAM roles, detects privilege escalation drift, and reconciles unsanctioned permissions." },
      "@gcp-telemetry-agent": { icon: "📈", name: "GCP Telemetry Agent", desc: "Correlates Cloud Monitoring ingestion & API metrics with Cloud Logging audit and error logs." },
      "@tenant-posture-agent": { icon: "🏛️", name: "Tenant Posture Governor", desc: "Audits SIEM/SOAR configuration baselines, tracks cryptographic fingerprints, and detects configuration drift." },
      "@playbook-decay-agent": { icon: "📜", name: "SOAR Playbook Decay Agent", desc: "Audits SOAR playbooks against a 100-point resilience model, 30-day failure rates, and synthesizes Mermaid DAGs." },
      "@timestamp-integrity-agent": { icon: "⏱️", name: "Timestamp Integrity Agent", desc: "Audits log sources for ingestion latency bottlenecks (Δt ≫ 0) and NTP clock skews (Δt < 0)." },
      "@rule-conflict-agent": { icon: "⚖️", name: "Rule Conflict & Overlap Agent", desc: "Detects semantic rule overlap, contradiction, and redundancy with COS scoring (0-100) and consolidation proposals." },
    };

    if (schedules.length === 0) {
      grid.innerHTML = `<div class="table-loading">No audit schedules configured.</div>`;
    } else {
      grid.innerHTML = schedules.map((sched) => {
        const handle = sched.agent_handle || "@agent";
        const meta = agentMeta[handle] || { icon: "🤖", name: handle, desc: "Scheduled background audit." };
        const isEnabled = sched.enabled !== false;
        const lastRunStr = sched.last_run_at ? new Date(sched.last_run_at).toLocaleTimeString() : "Pending (Queued)";
        const nextRunStr = sched.next_run_at ? new Date(sched.next_run_at).toLocaleTimeString() : "On Schedule";
        const lastStatus = sched.last_status || "READY";
        const statusClass = lastStatus === "SUCCESS" ? "badge-green" : (lastStatus === "ERROR" ? "badge-red" : "badge-blue");

        return `
          <div class="deacon-patrol-card">
            <div>
              <div class="patrol-card-header">
                <div class="patrol-agent-info">
                  <div class="patrol-icon-avatar">${meta.icon}</div>
                  <div>
                    <div class="patrol-agent-name">${meta.name}</div>
                    <div class="patrol-agent-handle">${handle}</div>
                  </div>
                </div>
                <span class="patrol-cadence-badge">Every ${sched.interval_hours || 24}h</span>
              </div>
              <p class="patrol-desc">${meta.desc}</p>
              <div class="patrol-meta-grid">
                <div>
                  <div class="patrol-meta-label">Stream / Topic</div>
                  <div class="patrol-meta-val">#${sched.stream || "ops"} &gt; ${sched.topic || "audit"}</div>
                </div>
                <div>
                  <div class="patrol-meta-label">Audit</div>
                  <div class="patrol-meta-val"><code>${sched.action}</code></div>
                </div>
                <div>
                  <div class="patrol-meta-label">Last Run</div>
                  <div class="patrol-meta-val">${lastRunStr}</div>
                </div>
                <div>
                  <div class="patrol-meta-label">Next Run</div>
                  <div class="patrol-meta-val">${nextRunStr}</div>
                </div>
              </div>
            </div>
            <div class="patrol-card-actions">
              <div style="display:flex; align-items:center; gap:8px;">
                <span class="badge ${statusClass}">${lastStatus}</span>
                <span style="font-size:11px; color:var(--text-dim);">${isEnabled ? "✓ Enabled" : "Paused"}</span>
              </div>
              <button class="btn btn-primary btn-sm" ${act("triggerGastownAgentPatrol", handle)}>
                <svg class="ui-icon" viewBox="0 0 24 24" width="12" height="12" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2"/></svg>
                <span>Run Audit</span>
              </button>
            </div>
          </div>
        `;
      }).join("");
    }

    // Render Recent Patrol Audit Logs
    if (logTbody) {
      const logs = (deacon.recent_patrols || []).slice().reverse();
      if (logs.length === 0) {
        logTbody.innerHTML = `<tr><td colspan="7" class="table-loading">No audit runs yet. Click "Run All Audits Now" to start one.</td></tr>`;
      } else {
        logTbody.innerHTML = logs.map((log) => {
          const ts = log.executed_at ? new Date(log.executed_at).toLocaleTimeString() : "<1m ago";
          const handle = log.agent_handle || "@agent";
          const beads = log.created_beads || [];
          const beadMarkup = beads.length > 0
            ? beads.map((b) => `<code style="font-size:11px; color:var(--c-ok);">${b}</code>`).join(", ")
            : `<span style="color:var(--text-dim); font-size:11px;">None (clean)</span>`;
          return `
            <tr>
              <td style="font-family:var(--font-mono); font-size:11px; color:var(--text-dim);">${ts}</td>
              <td><span style="font-weight:600; color:var(--c-info);">${handle}</span></td>
              <td><code style="font-size:11px;">${log.action}</code></td>
              <td><span style="font-size:11.5px; color:var(--text-muted);">#${log.stream} &gt; ${log.topic}</span></td>
              <td><span class="badge ${log.forced ? 'badge-yellow' : 'badge-blue'}">${log.forced ? 'MANUAL' : 'SCHEDULED'}</span></td>
              <td>${beadMarkup}</td>
              <td><span class="badge ${log.status === 'SUCCESS' ? 'badge-green' : 'badge-red'}">${log.status}</span></td>
            </tr>
          `;
        }).join("");
      }
    }
  } catch (err) {
    console.error("Error rendering Deacon patrols:", err);
    showLoadError(grid, { title: "Couldn't load scheduled audits", error: err, retry: renderGastownPatrols });
  }
}
window.renderGastownPatrols = renderGastownPatrols;

// ====================================================================
// SOC Operating System: Work Queue, Leases & Git Durability Ledger
// ====================================================================

// Marks a table as refreshing without discarding its rows (no flash-to-empty on
// filter changes or post-action reloads). First load keeps the HTML placeholder.
function setTableRefreshing(tbody, on) {
  const table = tbody && tbody.closest("table");
  if (!table) return;
  table.classList.toggle("is-refreshing", on);
  if (on) table.setAttribute("aria-busy", "true");
  else table.removeAttribute("aria-busy");
}

let workQueueRenderSeq = 0;

window.clearSocQueueFilters = function () {
  const plane = document.getElementById("socFilterPlane");
  const status = document.getElementById("socFilterStatus");
  if (plane) plane.value = "";
  if (status) status.value = "";
  return renderGastownWorkQueue();
};

async function renderGastownWorkQueue() {
  const issuesTableBody = document.getElementById("gtSocIssuesTableBody");
  const workersTableBody = document.getElementById("gtSocWorkersTableBody");
  const planeFilter = document.getElementById("socFilterPlane")?.value || "";
  const statusFilter = document.getElementById("socFilterStatus")?.value || "";
  const seq = ++workQueueRenderSeq;

  setTableRefreshing(issuesTableBody, true);
  setTableRefreshing(workersTableBody, true);

  try {
    let url = "/api/soc/issues?limit=100";
    if (planeFilter) url += `&plane=${encodeURIComponent(planeFilter)}`;
    if (statusFilter) url += `&status=${encodeURIComponent(statusFilter)}`;

    const [issuesResult, workersResult] = await Promise.allSettled([
      fetchJsonOrThrow(url),
      fetchJsonOrThrow("/api/soc/workers?active_only=false"),
    ]);
    // A newer render (filter changed again, or an action reloaded) owns the tables now.
    if (seq !== workQueueRenderSeq) return;
    if (issuesResult.status === "rejected") throw issuesResult.reason;

    const issues = Array.isArray(issuesResult.value) ? issuesResult.value : [];
    socQueueCache.issues = issues;

    // Render Issues Table
    if (issuesTableBody) {
      if (issues.length === 0) {
        const filtered = planeFilter || statusFilter;
        issuesTableBody.innerHTML = `<tr><td colspan="9" class="table-empty">${filtered
          ? `No issues match the current filters. <button type="button" class="btn btn-xs btn-secondary" ${act("clearSocQueueFilters")}>Clear filters</button>`
          : "No SOC issues in the work queue."}</td></tr>`;
      } else {
        const nowSec = Date.now() / 1000;
        issuesTableBody.innerHTML = issues.map((iss) => {
          const id = escapeHtml(iss.issue_id || iss.id);
          const plane = escapeHtml(iss.operational_plane || iss.plane || "data");
          const title = escapeHtml(iss.problem?.title || iss.title || "Operational Issue");
          const target = escapeHtml((iss.problem?.affected_objects && iss.problem.affected_objects.length > 0) ? iss.problem.affected_objects.join(", ") : (iss.problem?.target_resource_id || "Resource"));
          const sev = (iss.problem?.severity || iss.severity || "MEDIUM").toUpperCase();
          const status = (iss.status || "AVAILABLE").toUpperCase();
          const authority = escapeHtml(iss.governance?.required_authority_tier || iss.governance?.authority_tier || "TIER_1_AUTONOMOUS");

          // Badges
          const sevClass = (sev === "CRITICAL" || sev === "HIGH") ? "badge-risk-high" : (sev === "MEDIUM" ? "badge-risk-medium" : "badge-risk-low");
          let statusBadgeClass = "badge-blue";
          if (status === "AVAILABLE") statusBadgeClass = "badge-gray";
          else if (status === "LEASED" || status === "CLAIMED") statusBadgeClass = "badge-yellow";
          else if (status === "VALIDATING") statusBadgeClass = "badge-purple";
          else if (status === "APPROVED" || status === "APPLIED") statusBadgeClass = "badge-green";
          else if (status === "VERIFIED" || status === "CLOSED") statusBadgeClass = "badge-teal";

          // Lease Owner & Expiry
          let ownerHtml = `<span style="color:var(--text-dim); font-style:italic;">Unassigned</span>`;
          let expiresHtml = `<span style="color:var(--text-dim);">-</span>`;
          if (iss.lease && (iss.lease.holder_agent || iss.lease.owner)) {
            const holder = iss.lease.holder_agent || iss.lease.owner;
            ownerHtml = `<span style="font-weight:600; color:var(--text-bright); display:flex; align-items:center; gap:4px;">${getAgentAvatarSvg(holder, 14)} ${escapeHtml(holder)}</span>`;
            const expSec = leaseExpirySeconds(iss.lease);
            if (expSec) {
              const abs = new Date(expSec * 1000);
              expiresHtml = `<span class="lease-expiry" data-lease-expires="${expSec}" title="Lease expires ${escapeHtml(abs.toLocaleString())}">${formatLeaseRemaining(expSec - nowSec)}</span>
                <span class="lease-expiry-abs">${escapeHtml(abs.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }))}</span>`;
            }
          }
          const leaseExpired = !!(iss.lease && leaseExpirySeconds(iss.lease) && leaseExpirySeconds(iss.lease) <= nowSec);

          // Action buttons
          let actionButtons = `
            <button class="btn btn-xs btn-secondary" ${act("viewSocIssueDetail", iss.issue_id || iss.id)} title="Inspect durable Git ledger & events">Ledger</button>
          `;
          if (status === "AVAILABLE" || leaseExpired) {
            actionButtons += `
              <button class="btn btn-xs btn-primary" ${act("handleClaimSocIssue", iss.issue_id || iss.id)} title="Claim lease for autonomous worker">Claim</button>
            `;
          } else if (status === "LEASED" || status === "CLAIMED") {
            actionButtons += `
              <button class="btn btn-xs btn-outline" ${act("handleReleaseSocIssue", iss.issue_id || iss.id)} title="Release lease back to pool">Release</button>
            `;
          }
          if (status === "VALIDATING" || status === "LEASED") {
            actionButtons += `
              <button class="btn btn-xs btn-success" ${act("handleDecideSocIssue", iss.issue_id || iss.id, "APPROVED")} title="Approve issue change">Approve</button>
            `;
          }

          return `
            <tr>
              <td style="font-family:var(--font-mono); font-size:11.5px; font-weight:700; color:var(--color-primary-light); cursor:pointer;" ${act("viewSocIssueDetail", iss.issue_id || iss.id)}>${id}</td>
              <td><span class="badge" style="background:var(--c-indigo-bg); color:var(--c-indigo); font-size:11px; font-weight:700;">${plane.toUpperCase()}</span></td>
              <td>
                <div style="font-weight:600; color:var(--text-bright); font-size:12.5px;">${title}</div>
                <div style="font-size:11px; color:var(--text-dim); font-family:var(--font-mono); margin-top:2px;">${target}</div>
              </td>
              <td><span class="kanban-card-badge ${sevClass}" style="font-size:11px;">${sev}</span></td>
              <td><span class="badge ${statusBadgeClass}" style="font-size:11px; font-weight:700;">${status}</span></td>
              <td>${ownerHtml}</td>
              <td>${expiresHtml}</td>
              <td style="font-size:11px; color:var(--text-muted); font-family:var(--font-mono);">${authority}</td>
              <td><div style="display:flex; gap:4px;">${actionButtons}</div></td>
            </tr>
          `;
        }).join("");
      }
    }

    // Render Workers Table (independent of the issues request)
    if (workersResult.status === "rejected") {
      showLoadError(workersTableBody, { title: "Couldn't load workers", error: workersResult.reason, retry: renderGastownWorkQueue, colspan: 6 });
    } else if (workersTableBody) {
      const workers = Array.isArray(workersResult.value) ? workersResult.value : [];
      socQueueCache.workers = workers;
      if (workers.length === 0) {
        workersTableBody.innerHTML = `<tr><td colspan="6" style="text-align:center; padding:24px; color:var(--text-muted);">No workers registered in coordination plane.</td></tr>`;
      } else {
        workersTableBody.innerHTML = workers.map((w) => {
          const handle = escapeHtml(w.agent_handle || "@agent");
          const authority = escapeHtml(w.max_authority_tier || "TIER_1_AUTONOMOUS");
          const planeList = w.operational_planes || w.supported_planes || [];
          const planes = planeList.map(p => `<span class="badge" style="background:var(--c-info-bg); color:var(--c-info); font-size:11px; margin-right:3px;">${escapeHtml(p)}</span>`).join("");
          const rawCaps = Array.isArray(w.capabilities) ? w.capabilities : Object.keys(w.capabilities || {});
          const caps = rawCaps.slice(0, 8).map(c => `<span class="tag-chip" style="font-size:11px; padding:2px 6px; margin:2px; display:inline-block; background:var(--surface-stripe); border-radius:3px; font-family:var(--font-mono);">${escapeHtml(c)}</span>`).join("") + (rawCaps.length > 8 ? `<span style="font-size:11px; color:var(--text-dim); margin-left:4px;">+${rawCaps.length - 8} more</span>` : "");
          const maxLeases = w.max_concurrent_leases ?? 3;

          return `
            <tr>
              <td>
                <div style="display:flex; align-items:center; gap:6px; font-weight:600; color:var(--text-bright);">
                  ${getAgentAvatarSvg(w.agent_handle, 16)}
                  <span>${handle}</span>
                </div>
              </td>
              <td style="font-family:var(--font-mono); font-size:11.5px; color:var(--text-muted);">${authority}</td>
              <td>${planes || '<span style="color:var(--text-dim);">-</span>'}</td>
              <td><div style="max-width:340px; display:flex; flex-wrap:wrap;">${caps || '<span style="color:var(--text-dim);">-</span>'}</div></td>
              <td style="font-family:var(--font-mono); font-weight:600; color:var(--text-muted);">${maxLeases}</td>
              <td><span class="badge badge-green" style="font-size:11px; font-weight:700;">READY</span></td>
            </tr>
          `;
        }).join("");
      }
    }
  } catch (err) {
    if (seq !== workQueueRenderSeq) return;
    console.error("Failed to render SOC work queue:", err);
    showLoadError(issuesTableBody, { title: "Couldn't load the work queue", error: err, retry: renderGastownWorkQueue, colspan: 9 });
  } finally {
    if (seq === workQueueRenderSeq) {
      setTableRefreshing(issuesTableBody, false);
      setTableRefreshing(workersTableBody, false);
    }
  }
}
window.renderGastownWorkQueue = renderGastownWorkQueue;

const socQueueCache = { issues: [], workers: [] };

function leaseExpirySeconds(lease) {
  if (!lease) return 0;
  let v = lease.expires_at;
  if (typeof v === "string") {
    const n = Number(v);
    v = Number.isFinite(n) ? n : new Date(v).getTime() / 1000;
  }
  return Number.isFinite(v) && v > 0 ? v : 0;
}

function formatLeaseRemaining(remSec) {
  const rem = Math.floor(remSec);
  if (rem <= 0) return "Expired";
  if (rem < 60) return `${rem}s left`;
  const m = Math.floor(rem / 60), s = rem % 60;
  if (m < 60) return `${m}m ${String(s).padStart(2, "0")}s left`;
  const h = Math.floor(m / 60);
  return `${h}h ${m % 60}m left`;
}

// One shared ticker for every visible lease countdown. When a lease crosses zero we
// re-render the queue once so the Claim button appears without a manual refresh.
let leaseTickerHandle = null;
function tickLeaseCountdowns() {
  const els = document.querySelectorAll("[data-lease-expires]");
  if (!els.length) return;
  const now = Date.now() / 1000;
  let crossed = false;
  els.forEach((el) => {
    const exp = Number(el.dataset.leaseExpires);
    const rem = exp - now;
    const wasExpired = el.classList.contains("is-expired");
    el.textContent = formatLeaseRemaining(rem);
    el.classList.toggle("is-expired", rem <= 0);
    el.classList.toggle("is-expiring", rem > 0 && rem <= 60);
    if (rem <= 0 && !wasExpired) crossed = true;
  });
  if (crossed && !document.hidden) renderGastownWorkQueue();
}
function ensureLeaseTicker() {
  if (leaseTickerHandle) return;
  leaseTickerHandle = setInterval(tickLeaseCountdowns, 1000);
}
ensureLeaseTicker();

function workerCoversIssue(worker, issue) {
  const plane = String(issue?.operational_plane || issue?.plane || "").toLowerCase();
  if (!plane) return false;
  const planes = (worker.operational_planes || worker.supported_planes || []).map((x) => String(x).toLowerCase());
  return planes.includes(plane);
}

async function viewSocIssueDetail(issueId) {
  const modal = document.getElementById("modalSocIssue");
  const titleEl = document.getElementById("modalSocIssueTitle");
  const bodyEl = document.getElementById("modalSocIssueBody");
  if (!modal || !bodyEl) return;

  if (titleEl) titleEl.textContent = `SOC Issue: ${issueId}`;
  bodyEl.innerHTML = `<div style="text-align:center; padding:32px; color:var(--text-muted);">Loading Git evidence ledger & state transitions for ${escapeHtml(issueId)}...</div>`;
  modal.style.display = "flex";
  if (!modal._a11y) activateModal(modal, closeSocIssueModal);

  try {
    const res = await fetch(`/api/soc/issues/${encodeURIComponent(issueId)}`);
    if (!res.ok) {
      bodyEl.innerHTML = `<div style="color:var(--c-danger); padding:16px;">Failed to load issue details (${res.status})</div>`;
      return;
    }
    const iss = await res.json();
    const prob = iss.problem || {};
    const rout = iss.routing || {};
    const gov = iss.governance || {};
    const lease = iss.lease || null;
    const events = iss.materialized_events || [];
    const resolution = iss.resolution_markdown || "";

    // Build timeline HTML
    let eventsHtml = `<div style="color:var(--text-dim); font-size:12px; padding:8px;">No durability events recorded in Git ledger yet.</div>`;
    if (events.length > 0) {
      eventsHtml = events.map((ev, idx) => {
        const evName = escapeHtml(ev.transition || `Event ${idx + 1}`);
        const actor = escapeHtml(ev.actor || "system");
        const ts = escapeHtml(ev.timestamp || "-");
        const meta = ev.metadata ? `<pre style="margin:4px 0 0; background:var(--surface-inset); padding:6px; border-radius:4px; font-size:11px; max-height:100px; overflow-y:auto;">${escapeHtml(JSON.stringify(ev.metadata, null, 2))}</pre>` : "";
        const evidenceRefs = (ev.evidence_references && ev.evidence_references.length > 0)
          ? `<div style="margin-top:4px; font-size:11px; color:var(--c-info);">📎 Evidence: ${ev.evidence_references.map(r => `<code>${escapeHtml(r)}</code>`).join(", ")}</div>`
          : "";

        return `
          <div style="border-left: 2px solid var(--c-indigo); padding: 6px 0 10px 14px; position: relative; margin-left: 6px;">
            <div style="position: absolute; left: -6px; top: 8px; width: 10px; height: 10px; border-radius: 50%; background: var(--c-indigo-solid);"></div>
            <div style="display:flex; justify-content:space-between; align-items:center;">
              <span style="font-weight:700; color:var(--text-bright); font-size:12px;">${evName}</span>
              <span style="font-family:var(--font-mono); font-size:11px; color:var(--text-dim);">${ts}</span>
            </div>
            <div style="font-size:11.5px; color:var(--text-muted); margin-top:2px;">
              Actor: <span style="font-weight:600; color:var(--text-main);">${actor}</span>
            </div>
            ${evidenceRefs}
            ${meta}
          </div>
        `;
      }).join("");
    }

    let resolutionHtml = "";
    if (resolution) {
      resolutionHtml = `
        <div style="margin-top:16px; background:var(--c-ok-faint); border:1px solid var(--c-ok-bd); border-radius:6px; padding:12px;">
          <h4 style="font-size:12px; font-weight:700; color:var(--c-ok); margin:0 0 6px; display:flex; align-items:center; gap:6px;">
            <span>✅ Resolution Proof &amp; Verification</span>
          </h4>
          <div style="font-size:12px; color:var(--text-main); line-height:1.5; white-space:pre-wrap;">${escapeHtml(resolution)}</div>
        </div>
      `;
    }

    bodyEl.innerHTML = `
      <div style="display:grid; grid-template-columns: 1fr 1fr; gap:12px; margin-bottom:16px;">
        <div style="background:var(--bg-secondary); padding:10px 12px; border-radius:6px; border:1px solid var(--border-subtle);">
          <div style="font-size:11px; color:var(--text-dim); text-transform:uppercase; font-weight:700;">Issue Problem &amp; Target</div>
          <div style="font-size:13px; font-weight:700; color:var(--text-bright); margin-top:4px;">${escapeHtml(prob.title || iss.title || "-")}</div>
          <div style="font-size:11.5px; font-family:var(--font-mono); color:var(--text-muted); margin-top:4px;">Target: ${escapeHtml((prob.affected_objects && prob.affected_objects.length > 0) ? prob.affected_objects.join(", ") : (prob.target_resource_id || "-"))}</div>
          <div style="font-size:11.5px; color:var(--text-muted); margin-top:4px;">Severity: <span style="font-weight:700;">${escapeHtml(prob.severity || iss.severity || "MEDIUM")}</span> &bull; Plane: <span style="font-weight:700;">${escapeHtml(iss.operational_plane || iss.plane || "data")}</span></div>
        </div>

        <div style="background:var(--bg-secondary); padding:10px 12px; border-radius:6px; border:1px solid var(--border-subtle);">
          <div style="font-size:11px; color:var(--text-dim); text-transform:uppercase; font-weight:700;">Routing &amp; Governance</div>
          <div style="font-size:11.5px; color:var(--text-muted); margin-top:4px;">Required Capabilities: <span style="font-family:var(--font-mono); color:var(--c-info);">${escapeHtml((Array.isArray(rout.requires_capabilities) ? rout.requires_capabilities : Object.keys(rout.requires_capabilities || {})).join(", ") || "None")}</span></div>
          <div style="font-size:11.5px; color:var(--text-muted); margin-top:4px;">Authority: <span style="font-family:var(--font-mono); color:var(--c-warn);">${escapeHtml(gov.required_authority_tier || gov.authority_tier || "TIER_1_AUTONOMOUS")}</span></div>
          <div style="font-size:11.5px; color:var(--text-muted); margin-top:4px;">Status: <span style="font-weight:700; color:var(--text-bright);">${escapeHtml(iss.status || "AVAILABLE")}</span></div>
        </div>
      </div>

      <div style="background:var(--bg-secondary); padding:12px; border-radius:6px; border:1px solid var(--border-subtle); margin-bottom:16px;">
        <h4 style="font-size:12px; font-weight:700; color:var(--text-bright); margin:0 0 10px; display:flex; align-items:center; gap:6px;">
          <span>📜 Git Append-Only Evidence Ledger (Durability Boundaries)</span>
        </h4>
        <div style="padding-left:4px;">${eventsHtml}</div>
      </div>

      ${resolutionHtml}
    `;

    // Modal footer actions
    const footerEl = document.getElementById("modalSocIssueFooter");
    if (footerEl) {
      let footerBtns = `<button class="btn btn-secondary" ${act("closeSocIssueModal")}>Close</button>`;
      if (iss.status === "AVAILABLE") {
        footerBtns += `<button class="btn btn-primary" ${act("handleClaimSocIssue", issueId)}>Claim Issue</button>`;
      } else if (iss.status === "LEASED" || iss.status === "VALIDATING") {
        footerBtns += `
          <button class="btn btn-danger" ${act("handleDecideSocIssue", issueId, "REJECTED")}>Reject</button>
          <button class="btn btn-success" ${act("handleDecideSocIssue", issueId, "APPROVED")}>Approve Decision</button>
        `;
      }
      footerEl.innerHTML = footerBtns;
    }
  } catch (err) {
    bodyEl.innerHTML = `<div style="color:var(--c-danger); padding:16px;">Error inspecting issue: ${escapeHtml(err.message)}</div>`;
  }
}
window.viewSocIssueDetail = viewSocIssueDetail;

function closeSocIssueModal() {
  const modal = document.getElementById("modalSocIssue");
  if (!modal) return;
  modal.style.display = "none";
  deactivateModal(modal);
}
window.closeSocIssueModal = closeSocIssueModal;

const CLAIM_CUSTOM_HANDLE = "__custom__";

async function handleClaimSocIssue(issueId) {
  const issue = (socQueueCache.issues || []).find((i) => (i.issue_id || i.id) === issueId);
  const plane = issue ? String(issue.operational_plane || issue.plane || "") : "";
  const workers = (socQueueCache.workers || []).filter((w) => w.agent_handle);
  const toOpt = (w) => ({ value: w.agent_handle, label: `${w.agent_handle} — ${w.max_authority_tier || "tier ?"}` });
  const capable = workers.filter((w) => workerCoversIssue(w, issue)).map(toOpt);
  const others = workers.filter((w) => !workerCoversIssue(w, issue)).map(toOpt);

  const fields = [];
  if (workers.length) {
    fields.push({
      name: "worker",
      label: "Worker",
      type: "select",
      required: true,
      value: (capable[0] || others[0]).value,
      groups: [
        { label: plane ? `Covers ${plane} plane` : "Registered workers", options: capable },
        { label: capable.length ? "Other registered workers" : "", options: others },
        { label: "", options: [{ value: CLAIM_CUSTOM_HANDLE, label: "Other handle…" }] },
      ],
      hint: plane && !capable.length ? `No registered worker lists the ${plane} plane.` : "",
      onChange: (val, form) => {
        const wrap = form.querySelector('[data-field-wrap="handle"]');
        if (wrap) wrap.hidden = val !== CLAIM_CUSTOM_HANDLE;
      },
    });
  }
  fields.push({ name: "handle", label: "Worker agent handle", type: "text", required: true, placeholder: "@parser-doctor" });

  const result = await openActionDialog({
    title: "Claim issue",
    message: `Assign a 5-minute lease on ${issueId}${plane ? ` (${plane} plane)` : ""} to a worker agent.`,
    confirmLabel: "Claim",
    fields,
  });
  if (!result) return;
  const raw = (result.worker && result.worker !== CLAIM_CUSTOM_HANDLE) ? result.worker : result.handle;
  const handle = raw.startsWith("@") ? raw : `@${raw}`;
  try {
    const res = await fetch(`/api/soc/issues/${encodeURIComponent(issueId)}/claim`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ agent_handle: handle.trim(), duration_seconds: 300 }),
    });
    const data = await res.json();
    if (res.ok) {
      showToast("success", `Acquired lease on ${issueId} for ${handle}`);
      closeSocIssueModal();
      await renderGastownWorkQueue();
    } else {
      showToast("error", `Claim failed: ${data.detail || data.error}`);
    }
  } catch (err) {
    showToast("error", `Claim error: ${err.message}`);
  }
}
window.handleClaimSocIssue = handleClaimSocIssue;

async function handleReleaseSocIssue(issueId) {
  const confirmed = await openActionDialog({
    title: "Release lease",
    message: `Force-release the lease on ${issueId} and return it to the available queue? The current holder will lose its claim.`,
    confirmLabel: "Release",
    variant: "danger",
  });
  if (!confirmed) return;
  try {
    const res = await fetch(`/api/soc/issues/${encodeURIComponent(issueId)}/release`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ force: true }),
    });
    const data = await res.json();
    if (res.ok) {
      showToast("success", `Lease on ${issueId} released`);
      await renderGastownWorkQueue();
    } else {
      showToast("error", `Release failed: ${data.detail || data.error}`);
    }
  } catch (err) {
    showToast("error", `Release error: ${err.message}`);
  }
}
window.handleReleaseSocIssue = handleReleaseSocIssue;

async function handleDecideSocIssue(issueId, decision) {
  const isReject = String(decision).toUpperCase() === "REJECTED";
  const result = await openActionDialog({
    title: isReject ? "Reject issue" : "Approve issue",
    message: `Record a ${String(decision).toUpperCase()} decision on ${issueId}. This is written to the audit trail.`,
    confirmLabel: isReject ? "Reject" : "Approve",
    variant: isReject ? "danger" : "primary",
    fields: [{ name: "rationale", label: "Rationale", type: "textarea", required: true, minLength: 5 }],
  });
  if (!result) return;
  const rationale = result.rationale;
  try {
    const res = await fetch(`/api/soc/issues/${encodeURIComponent(issueId)}/decide`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ decision, approver: "secops-operator", rationale }),
    });
    const data = await res.json();
    if (res.ok) {
      showToast("success", `Recorded ${decision} on ${issueId}`);
      closeSocIssueModal();
      await renderGastownWorkQueue();
    } else {
      showToast("error", `Decision failed: ${data.detail || data.error}`);
    }
  } catch (err) {
    showToast("error", `Decision error: ${err.message}`);
  }
}
window.handleDecideSocIssue = handleDecideSocIssue;

async function triggerGastownPatrolAll() {
  const btn = document.getElementById("btnTriggerPatrolAll");
  const headerBtn = document.getElementById("btnHeaderPatrolAll");
  if (btn) btn.disabled = true;
  if (headerBtn) headerBtn.disabled = true;
  showToast("info", "Running all scheduled audits…");
  try {
    const res = await fetch("/api/gastown/patrols/run-all", { method: "POST" });
    const data = await res.json();
    if (res.ok) {
      showToast("success", `Audits complete (${data.executed_count} agents audited)`);
      await loadGastownOverview(true);
      await renderGastownPatrols();
    } else {
      showToast("error", `Audit run failed: ${data.detail || data.error}`);
    }
  } catch (err) {
    showToast("error", `Audit run error: ${err.message}`);
  } finally {
    if (btn) btn.disabled = false;
    if (headerBtn) headerBtn.disabled = false;
  }
}
window.triggerGastownPatrolAll = triggerGastownPatrolAll;

async function triggerGastownAgentPatrol(agentHandle) {
  showToast("info", `Running audit for ${agentHandle}…`);
  try {
    const res = await fetch(`/api/gastown/patrols/${encodeURIComponent(agentHandle)}/run`, { method: "POST" });
    const data = await res.json();
    if (res.ok && data.status === "SUCCESS") {
      const beads = data.created_beads || [];
      const beadMsg = beads.length > 0 ? ` (${beads.length} task${beads.length === 1 ? "" : "s"} opened)` : "";
      showToast("success", `Audit complete for ${agentHandle}${beadMsg}`);
      await loadGastownOverview(true);
      await renderGastownPatrols();
    } else {
      showToast("error", `Audit failed for ${agentHandle}: ${data.error || data.detail}`);
    }
  } catch (err) {
    showToast("error", `Error running audit: ${err.message}`);
  }
}
window.triggerGastownAgentPatrol = triggerGastownAgentPatrol;

function getAgentAvatarSvg(handle, size = 16) {
  const svgs = {
    "@feed-agent": `<svg viewBox="0 0 24 24" width="${size}" height="${size}" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M4.9 19.1C1 15.2 1 8.8 4.9 4.9"/><path d="M7.8 16.2c-2.3-2.3-2.3-6.1 0-8.5"/><circle cx="12" cy="12" r="2"/><path d="M16.2 7.8c2.3 2.3 2.3 6.1 0 8.5"/><path d="M19.1 4.9C23 8.8 23 15.1 19.1 19"/></svg>`,
    "@parser-doctor": `<svg viewBox="0 0 24 24" width="${size}" height="${size}" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M22 12h-4l-3 9L9 3l-3 9H2"/></svg>`,
    "@secops-dispatcher": `<svg viewBox="0 0 24 24" width="${size}" height="${size}" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"/><polygon points="16.24 7.76 14.12 14.12 7.76 16.24 9.88 9.88 16.24 7.76"/></svg>`,
    "@rule-troubleshooter": `<svg viewBox="0 0 24 24" width="${size}" height="${size}" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/></svg>`,
    "@yaral-optimizer": `<svg viewBox="0 0 24 24" width="${size}" height="${size}" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2"/></svg>`,
    "@logjammer-agent": `<svg viewBox="0 0 24 24" width="${size}" height="${size}" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/><line x1="16" y1="13" x2="8" y2="13"/><line x1="16" y1="17" x2="8" y2="17"/></svg>`,
    "@identity-governor": `<svg viewBox="0 0 24 24" width="${size}" height="${size}" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/></svg>`,
    "@detection-decay-agent": `<svg viewBox="0 0 24 24" width="${size}" height="${size}" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="23 18 13.5 8.5 8.5 13.5 1 6"/><polyline points="17 18 23 18 23 12"/></svg>`,
    "@detection-tuning-agent": `<svg viewBox="0 0 24 24" width="${size}" height="${size}" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"/><circle cx="12" cy="12" r="6"/><circle cx="12" cy="12" r="2"/></svg>`,
    "@sql-analyst": `<svg viewBox="0 0 24 24" width="${size}" height="${size}" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><line x1="18" y1="20" x2="18" y2="10"/><line x1="12" y1="20" x2="12" y2="4"/><line x1="6" y1="20" x2="6" y2="14"/></svg>`,
    "@gcp-telemetry-agent": `<svg viewBox="0 0 24 24" width="${size}" height="${size}" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="22 12 18 12 15 21 9 3 6 12 2 12"/></svg>`,
    "@tenant-posture-agent": `<svg viewBox="0 0 24 24" width="${size}" height="${size}" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M3 21h18"/><path d="M5 21V7l7-4 7 4v14"/><path d="M9 10a2 2 0 1 1-2-2"/><path d="M19 10a2 2 0 1 1-2-2"/></svg>`,
    "@playbook-decay-agent": `<svg viewBox="0 0 24 24" width="${size}" height="${size}" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M4 19.5A2.5 2.5 0 0 1 6.5 17H20"/><path d="M6.5 2H20v20H6.5A2.5 2.5 0 0 1 4 19.5v-15A2.5 2.5 0 0 1 6.5 2z"/><polyline points="10 8 13 11 16 8"/></svg>`,
    "@timestamp-integrity-agent": `<svg viewBox="0 0 24 24" width="${size}" height="${size}" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"/><polyline points="12 6 12 12 16 14"/></svg>`,
    "@rule-conflict-agent": `<svg viewBox="0 0 24 24" width="${size}" height="${size}" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="m16 16 3-8 3 8c-.87.65-1.92 1-3 1s-2.13-.35-3-1Z"/><path d="m2 16 3-8 3 8c-.87.65-1.92 1-3 1s-2.13-.35-3-1Z"/><path d="M7 21h10"/><path d="M12 3v18"/><path d="M3 7h2c2 0 5-1 7-2 2 1 5 2 7 2h2"/></svg>`,
    "@log-cost-agent": `<svg viewBox="0 0 24 24" width="${size}" height="${size}" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><line x1="12" y1="1" x2="12" y2="23"/><path d="M17 5H9.5a3.5 3.5 0 0 0 0 7h5a3.5 3.5 0 0 1 0 7H6"/></svg>`,
    "@raw-log-agent": `<svg viewBox="0 0 24 24" width="${size}" height="${size}" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/><circle cx="11.5" cy="14.5" r="2.5"/><line x1="13.5" y1="16.5" x2="16" y2="19"/></svg>`,
    "@namespace-label-agent": `<svg viewBox="0 0 24 24" width="${size}" height="${size}" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M20.59 13.41l-7.17 7.17a2 2 0 0 1-2.83 0L2 12V2h10l8.59 8.59a2 2 0 0 1 0 2.82z"/><line x1="7" y1="7" x2="7.01" y2="7"/></svg>`,
  };
  return svgs[handle] || `<svg viewBox="0 0 24 24" width="${size}" height="${size}" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="11" width="18" height="10" rx="2"/><circle cx="12" cy="5" r="2"/><path d="M12 7v4"/><line x1="8" y1="16" x2="8" y2="16"/><line x1="16" y1="16" x2="16" y2="16"/></svg>`;
}

// ====================================================================
// Agent Library & Capabilities Directory Subsystem
// ====================================================================
const libraryState = {
  agents: [],
  selectedAgentHandle: null,
  activeSubsystemFilter: "ALL",
  searchQuery: "",
  listenersAttached: false,
};

async function loadAgentLibrary(preselectedHandle) {
  setupLibraryListeners();
  try {
    libraryState.agents = await fetchJsonOrThrow("/api/agents");
  } catch (err) {
    console.error("Failed to fetch agent library:", err);
    if (!libraryState.agents.length) {
      showLoadError(document.getElementById("agentLibraryList"), {
        title: "Couldn't load the agent library",
        error: err,
        retry: () => loadAgentLibrary(preselectedHandle),
      });
      return;
    }
  }

  // If hash has target agent, or preselectedHandle passed, use it
  let targetHandle = preselectedHandle;
  if (!targetHandle && window.location.hash.startsWith("#library/")) {
    targetHandle = decodeURIComponent(window.location.hash.split("/")[1]);
    if (!targetHandle.startsWith("@")) targetHandle = "@" + targetHandle;
  }
  if (!targetHandle && libraryState.agents.length > 0) {
    targetHandle = libraryState.selectedAgentHandle || libraryState.agents[0].handle;
  }

  renderAgentLibraryList();

  if (targetHandle) {
    selectAgentInLibrary(targetHandle);
  }
}

function setupLibraryListeners() {
  if (libraryState.listenersAttached) return;
  libraryState.listenersAttached = true;

  const searchInput = document.getElementById("agentSearchInput");
  if (searchInput) {
    searchInput.addEventListener("input", (e) => {
      libraryState.searchQuery = (e.target.value || "").trim().toLowerCase();
      renderAgentLibraryList();
    });
  }

  const chips = document.querySelectorAll(".lib-filter-chip");
  chips.forEach((chip) => {
    chip.addEventListener("click", () => {
      chips.forEach((c) => c.classList.remove("active"));
      chip.classList.add("active");
      libraryState.activeSubsystemFilter = chip.getAttribute("data-subsystem") || "ALL";
      renderAgentLibraryList();
    });
  });
}

function renderAgentLibraryList() {
  const container = document.getElementById("agentLibraryList");
  if (!container) return;

  const libBadge = document.getElementById("libraryAgentCountBadge");
  if (libBadge && Array.isArray(libraryState.agents) && libraryState.agents.length > 0) {
    libBadge.textContent = `${libraryState.agents.length} Active Agents`;
  }

  const query = libraryState.searchQuery;
  const filter = (libraryState.activeSubsystemFilter || "all").toLowerCase();

  const filtered = libraryState.agents.filter((a) => {
    // Subsystem filter
    if (filter !== "all") {
      const sub = (a.subsystem || "").toLowerCase();
      const match =
        sub === filter ||
        sub.includes(filter) ||
        (filter === "detections" && (sub.includes("detection") || sub.includes("rule"))) ||
        (filter === "ingestion" && (sub.includes("ingestion") || sub.includes("telemetry") || sub.includes("replay"))) ||
        (filter === "identity" && sub.includes("identity")) ||
        (filter === "analytics" && (sub.includes("analytics") || sub.includes("sql"))) ||
        (filter === "cartography" && (sub.includes("cartography") || sub.includes("survey"))) ||
        (filter === "governance" && (sub.includes("governance") || sub.includes("posture"))) ||
        (filter === "soar" && sub.includes("soar"));
      if (!match) {
        return false;
      }
    }
    // Search query filter
    if (query) {
      const matchName = (a.name || "").toLowerCase().includes(query);
      const matchHandle = (a.handle || "").toLowerCase().includes(query);
      const matchRole = (a.role || "").toLowerCase().includes(query);
      const matchDesc = (a.description || "").toLowerCase().includes(query);
      const matchSubsystem = (a.subsystem || "").toLowerCase().includes(query);
      const matchTools = (a.capabilities || []).some((c) => c.toLowerCase().includes(query));
      if (!matchName && !matchHandle && !matchRole && !matchDesc && !matchSubsystem && !matchTools) {
        return false;
      }
    }
    return true;
  });

  if (filtered.length === 0) {
    const filterDesc = query
      ? `matching "${escapeHtml(query)}"`
      : `in category "${escapeHtml(libraryState.activeSubsystemFilter)}"`;
    container.innerHTML = `
      <div style="padding: 24px 12px; text-align: center; color: var(--c-neutral); font-size: 12px;">
        No agents found ${filterDesc}.
      </div>
    `;
    return;
  }

  container.innerHTML = filtered
    .map((agent) => {
      const isSelected = agent.handle === libraryState.selectedAgentHandle;
      const avatarSvg = getAgentAvatarSvg(agent.handle, 16);
      const toolCount = (agent.tools || []).length;
      const cadence = agent.cadence || "On-Demand";

      return `
        <div class="lib-agent-card ${isSelected ? "active" : ""}" data-handle="${escapeHtml(agent.handle)}">
          <div class="lib-agent-top-row">
            <div class="lib-agent-header-info">
              <span class="lib-agent-avatar">${avatarSvg}</span>
              <div class="lib-agent-name-group">
                <span class="lib-agent-name">${escapeHtml(agent.name)}</span>
                <span class="lib-agent-handle">${escapeHtml(agent.handle)}</span>
              </div>
            </div>
            <span class="lib-agent-subsystem-badge">${escapeHtml(agent.subsystem || "fleet")}</span>
          </div>
          <div class="lib-agent-role">${escapeHtml(agent.role || agent.description || "")}</div>
          <div class="lib-agent-footer-row">
            <span class="lib-agent-tool-count">
              <svg viewBox="0 0 24 24" width="11" height="11" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="vertical-align:-1px;margin-right:3px;"><path d="M14.7 6.3a1 1 0 0 0 0 1.4l1.6 1.6a1 1 0 0 0 1.4 0l3.77-3.77a6 6 0 0 1-7.94 7.94l-6.91 6.91a2.12 2.12 0 0 1-3-3l6.91-6.91a6 6 0 0 1 7.94-7.94l-3.76 3.76z"/></svg>${toolCount} SDK Tools
            </span>
            ${
              (agent.skills || []).length > 0
                ? `<span class="lib-agent-skill-count"><svg viewBox="0 0 24 24" width="10" height="10" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="vertical-align:-1px;margin-right:2px;"><path d="M4 19.5A2.5 2.5 0 0 1 6.5 17H20"/><path d="M6.5 2H20v20H6.5A2.5 2.5 0 0 1 4 19.5v-15A2.5 2.5 0 0 1 6.5 2z"/></svg>${agent.skills.length} Skills</span>`
                : ""
            }
            <span class="lib-agent-cadence">
              <svg viewBox="0 0 24 24" width="10" height="10" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="vertical-align:-1px;margin-right:2px;"><polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2"/></svg>${escapeHtml(cadence)}
            </span>
          </div>
        </div>
      `;
    })
    .join("");

  // Attach card click handlers
  container.querySelectorAll(".lib-agent-card").forEach((card) => {
    card.addEventListener("click", () => {
      const handle = card.getAttribute("data-handle");
      selectAgentInLibrary(handle);
    });
  });

  // If currently selected agent is not among filtered agents, auto-select first filtered agent
  if (filtered.length > 0) {
    const isSelectedVisible = filtered.some((a) => a.handle === libraryState.selectedAgentHandle);
    if (!isSelectedVisible) {
      selectAgentInLibrary(filtered[0].handle);
    }
  }
}

function selectAgentInLibrary(handle) {
  libraryState.selectedAgentHandle = handle;

  // Update URL hash
  if (window.location.hash.startsWith("#library")) {
    setRoute(`#library/${encodeURIComponent(handle)}`, { replace: true });
  }

  // Update card active classes
  const cards = document.querySelectorAll(".lib-agent-card");
  cards.forEach((c) => {
    if (c.getAttribute("data-handle") === handle) {
      c.classList.add("active");
    } else {
      c.classList.remove("active");
    }
  });

  const agent = libraryState.agents.find((a) => a.handle === handle);
  const detailContainer = document.getElementById("agentLibraryDetail");
  if (!detailContainer) return;

  if (!agent) {
    detailContainer.innerHTML = `
      <div class="library-placeholder-detail">
        <div class="library-empty-icon">
          <svg viewBox="0 0 24 24" width="48" height="48" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" style="color:var(--c-danger);"><circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/></svg>
        </div>
        <h3>Agent Not Found</h3>
        <p>The requested agent handle <code>${escapeHtml(handle)}</code> was not found in the fleet.</p>
      </div>
    `;
    return;
  }

  const avatarSvg = getAgentAvatarSvg(agent.handle, 24);
  const cadence = agent.cadence || "On-Demand";
  const hitlBadge = agent.hitl_required
    ? `<span class="agent-meta-chip hitl-req"><svg viewBox="0 0 24 24" width="11" height="11" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="vertical-align:-1px;margin-right:3px;"><path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/></svg>HITL Required</span>`
    : `<span class="agent-meta-chip"><svg viewBox="0 0 24 24" width="11" height="11" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="vertical-align:-1px;margin-right:3px;"><polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2"/></svg>Autonomous</span>`;

  // Render detail view
  detailContainer.innerHTML = `
    <!-- Top Identity Header Card -->
    <div class="agent-detail-header-card">
      <div class="agent-detail-identity">
        <div class="agent-detail-avatar-lg">${avatarSvg}</div>
        <div>
          <div class="agent-detail-name">
            ${escapeHtml(agent.name)}
            <span class="agent-detail-handle">${escapeHtml(agent.handle)}</span>
          </div>
          <div class="agent-detail-meta-row">
            <span class="agent-meta-chip">${escapeHtml(agent.subsystem || "fleet")}</span>
            <span class="agent-meta-chip model">${escapeHtml(agent.model || "gemini-3.8-flash")}</span>
            <span class="agent-meta-chip patrol"><svg viewBox="0 0 24 24" width="11" height="11" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="vertical-align:-1px;margin-right:3px;"><polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2"/></svg>${escapeHtml(cadence)}</span>
            ${hitlBadge}
            <span class="agent-meta-chip"><svg viewBox="0 0 24 24" width="11" height="11" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="vertical-align:-1px;margin-right:3px;"><path d="M21 10c0 7-9 13-9 13s-9-6-9-13a9 9 0 0 1 18 0z"/><circle cx="12" cy="10" r="3"/></svg>#${escapeHtml(agent.default_stream || "general")} &gt; ${escapeHtml(agent.default_topic || "general")}</span>
          </div>
        </div>
      </div>
      <div class="agent-detail-actions">
        <button id="btnLibMsgAgent" class="btn btn-secondary" title="Open channel in Fleet Chat">
          <svg viewBox="0 0 24 24" width="13" height="13" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/></svg>
          <span>Chat</span>
        </button>
        <button id="btnLibRunPatrol" class="btn btn-primary" title="Run this agent's scheduled audit now">
          <svg viewBox="0 0 24 24" width="12" height="12" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2"/></svg>
          <span>Run Audit</span>
        </button>
      </div>
    </div>

    <!-- Section: Role & Operational Scope -->
    <div class="lib-detail-section">
      <div class="lib-section-header">
        <div class="lib-section-title">
          <svg viewBox="0 0 24 24" width="15" height="15" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"/><circle cx="12" cy="12" r="6"/><circle cx="12" cy="12" r="2"/></svg>
          <span>Role &amp; Operational Mission</span>
        </div>
      </div>
      <div class="lib-desc-text">
        <strong>${escapeHtml(agent.role || "")}</strong><br />
        ${escapeHtml(agent.description || "")}
      </div>
    </div>

    <!-- Section: System Instructions & Operational Protocol (The Prompt) -->
    <div class="lib-detail-section">
      <div class="lib-section-header">
        <div class="lib-section-title">
          <svg viewBox="0 0 24 24" width="15" height="15" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/><line x1="16" y1="13" x2="8" y2="13"/><line x1="16" y1="17" x2="8" y2="17"/></svg>
          <span>System Instruction &amp; Operational Protocol</span>
          <span class="lib-section-subtitle">(Gemini Function Calling Prompt)</span>
        </div>
        <button id="btnCopyPrompt" class="btn-copy-prompt" title="Copy Raw System Instruction">
          <svg viewBox="0 0 24 24" width="13" height="13" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="9" y="9" width="13" height="13" rx="2" ry="2"/><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"/></svg>
          <span>Copy Prompt</span>
        </button>
      </div>
      <div class="lib-prompt-viewer-wrap">
        <pre class="lib-prompt-pre">${escapeHtml(agent.system_instruction || "No system instruction specified.")}</pre>
      </div>
    </div>

    <!-- Section: Bound SDK Tools & Workflow Capabilities -->
    <div class="lib-detail-section">
      <div class="lib-section-header">
        <div class="lib-section-title">
          <svg viewBox="0 0 24 24" width="15" height="15" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M14.7 6.3a1 1 0 0 0 0 1.4l1.6 1.6a1 1 0 0 0 1.4 0l3.77-3.77a6 6 0 0 1-7.94 7.94l-6.91 6.91a2.12 2.12 0 0 1-3-3l6.91-6.91a6 6 0 0 1 7.94-7.94l-3.76 3.76z"/></svg>
          <span>Bound SDK Tools &amp; Workflow Capabilities</span>
          <span class="lib-section-subtitle">(${(agent.tools || []).length} registered)</span>
        </div>
        <span class="meta-tag">100% Live GEAP Ready</span>
      </div>
      <div class="lib-tools-grid">
        ${renderToolCards(agent.tools || [])}
      </div>
    </div>

    <!-- Section: ADK Modular Skills & Runbooks -->
    ${
      (agent.skills || []).length > 0
        ? `
    <div class="lib-detail-section">
      <div class="lib-section-header">
        <div class="lib-section-title">
          <svg viewBox="0 0 24 24" width="15" height="15" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M4 19.5A2.5 2.5 0 0 1 6.5 17H20"/><path d="M6.5 2H20v20H6.5A2.5 2.5 0 0 1 4 19.5v-15A2.5 2.5 0 0 1 6.5 2z"/></svg>
          <span>ADK Modular Skills &amp; Runbooks</span>
          <span class="lib-section-subtitle">(${(agent.skills || []).length} available from knowledge/)</span>
        </div>
        <span class="meta-tag">ADK 2 Dynamic Grounding</span>
      </div>
      <div class="lib-skills-grid">
        ${(agent.skills || []).map(skill => `
          <div class="lib-skill-card">
            <div class="lib-skill-header">
              <span class="lib-skill-type-badge ${skill.type === 'task' ? 'type-task' : 'type-concept'}">${escapeHtml(skill.type.toUpperCase())}</span>
              <span class="lib-skill-id">${escapeHtml(skill.id)}</span>
            </div>
            <div class="lib-skill-title">${escapeHtml(skill.title)}</div>
            ${skill.triggers && skill.triggers.length > 0 ? `
              <div class="lib-skill-triggers">
                <span class="trigger-label">Triggers:</span>
                ${skill.triggers.map(t => `<span class="trigger-pill">${escapeHtml(t)}</span>`).join("")}
              </div>
            ` : ""}
            <div class="lib-skill-path"><code>${escapeHtml(skill.source_path)}</code></div>
          </div>
        `).join("")}
      </div>
    </div>
    `
        : ""
    }

    <!-- Section: Built-in ADK Primitives -->
    ${
      (agent.builtin_tools || []).length > 0
        ? `
    <div class="lib-detail-section">
      <div class="lib-section-header">
        <div class="lib-section-title">
          <svg viewBox="0 0 24 24" width="15" height="15" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1 0 2.83 2 2 0 0 1-2.83 0l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-2 2 2 2 0 0 1-2-2v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83 0 2 2 0 0 1 0-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1-2-2 2 2 0 0 1 2-2h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 0-2.83 2 2 0 0 1 2.83 0l.06.06a1.65 1.65 0 0 0 1.82.33H9a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 2-2 2 2 0 0 1 2 2v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 0 2 2 0 0 1 0 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 2 2 2 2 0 0 1-2 2h-.09a1.65 1.65 0 0 0-1.51 1z"/></svg>
          <span>Built-in ADK 2 Tools</span>
        </div>
      </div>
      <div class="lib-builtin-tools-list">
        ${agent.builtin_tools
          .map(
            (bt) => `
          <div class="lib-builtin-tool-pill">
            <span class="lib-builtin-name">${escapeHtml(bt.name)}()</span>
            <span class="lib-builtin-desc">${escapeHtml(bt.description || "ADK core method")}</span>
          </div>
        `
          )
          .join("")}
      </div>
    </div>
    `
        : ""
    }
  `;

  // Attach button events
  const btnMsg = document.getElementById("btnLibMsgAgent");
  if (btnMsg) {
    btnMsg.addEventListener("click", () => {
      window.switchTopicAndChat(agent.default_stream || "general", agent.default_topic || "general", `${agent.handle} `);
    });
  }

  const btnPatrol = document.getElementById("btnLibRunPatrol");
  if (btnPatrol) {
    btnPatrol.addEventListener("click", () => {
      triggerGastownAgentPatrol(agent.handle);
    });
  }

  const btnCopy = document.getElementById("btnCopyPrompt");
  if (btnCopy) {
    btnCopy.addEventListener("click", () => {
      copyAgentPrompt(agent.system_instruction);
    });
  }
}

function renderToolCards(tools) {
  if (!tools || tools.length === 0) {
    return `<div style="padding: 16px; color: var(--c-neutral); font-size: 12px;">No specific SDK tools bound.</div>`;
  }

  return tools
    .map((tool) => {
      const kind = (tool.kind || "workflow").toLowerCase();
      const cardinality = tool.cardinality || (kind === "query" ? "unbounded" : "single");
      const kindClass = kind === "query" ? "query" : kind === "primitive" ? "primitive" : "workflow";

      return `
      <div class="lib-tool-card">
        <div class="lib-tool-header">
          <div class="lib-tool-id-group">
            <span class="lib-tool-id">${escapeHtml(tool.capability_id)}</span>
            <span class="lib-tool-mcp">MCP: ${escapeHtml(tool.mcp_tool_name || tool.capability_id)}</span>
          </div>
          <div class="lib-tool-badges">
            <span class="tool-kind-badge ${kindClass}">${escapeHtml(kind)}</span>
            <span class="tool-cardinality-badge">${escapeHtml(cardinality)}</span>
          </div>
        </div>
        <div class="lib-tool-name">${escapeHtml(tool.name || tool.capability_id)}</div>
        <div class="lib-tool-desc">${escapeHtml(tool.description || "")}</div>
        ${
          tool.evidence_path
            ? `<div class="lib-tool-evidence-link">
                <svg viewBox="0 0 24 24" width="11" height="11" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="vertical-align:-1px;margin-right:2px;"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/></svg>Evidence: <code>${escapeHtml(tool.evidence_path)}</code>
              </div>`
            : ""
        }
      </div>
    `;
    })
    .join("");
}

function copyAgentPrompt(instruction) {
  if (!instruction) return;
  if (navigator.clipboard && navigator.clipboard.writeText) {
    navigator.clipboard.writeText(instruction).then(
      () => {
        showToast("success", "System instruction copied to clipboard!");
      },
      () => {
        showToast("error", "Failed to copy to clipboard");
      }
    );
  } else {
    // Fallback
    const textarea = document.createElement("textarea");
    textarea.value = instruction;
    document.body.appendChild(textarea);
    textarea.select();
    try {
      document.execCommand("copy");
      showToast("success", "System instruction copied to clipboard!");
    } catch (e) {
      showToast("error", "Failed to copy prompt");
    }
    document.body.removeChild(textarea);
  }
}

window.openAgentInLibrary = function (handle) {
  switchView("library");
  selectAgentInLibrary(handle);
};

// ====================================================================
// SOC Operational Picture & Shift Briefings Controller
// ====================================================================
let currentShiftSlackBlocks = null;
let briefingsInitialized = false;

function loadBriefingsView() {
  if (!briefingsInitialized) {
    briefingsInitialized = true;
    setupBriefingTabs();

    const lookbackSelect = document.getElementById("shiftWindowSelect");
    if (lookbackSelect) {
      lookbackSelect.addEventListener("change", () => {
        const hours = parseInt(lookbackSelect.value, 10) || 8;
        loadShiftBriefing(hours);
      });
    }

    const btnTrigger = document.getElementById("btnTriggerShiftBrief");
    if (btnTrigger) {
      btnTrigger.addEventListener("click", () => triggerShiftBrief());
    }

    const btnRefresh = document.getElementById("btnRefreshPosture");
    if (btnRefresh) {
      btnRefresh.addEventListener("click", () => {
        loadPostureSnapshot();
        const hours = parseInt(document.getElementById("shiftWindowSelect")?.value || "8", 10);
        loadShiftBriefing(hours);
      });
    }

    const btnCopyBlocks = document.getElementById("btnCopySlackBlock");
    if (btnCopyBlocks) {
      btnCopyBlocks.addEventListener("click", () => copySlackBlocks());
    }

    const btnFetchDossier = document.getElementById("btnFetchDossier");
    if (btnFetchDossier) {
      btnFetchDossier.addEventListener("click", () => {
        const type = document.getElementById("dossierSubjectType")?.value;
        const id = document.getElementById("dossierSubjectId")?.value?.trim();
        if (type && id) {
          fetchEntityDossier(type, id);
        } else {
          showToast("warning", "Please enter an Entity Identifier");
        }
      });
    }
  }

  const hours = parseInt(document.getElementById("shiftWindowSelect")?.value || "8", 10);
  loadShiftBriefing(hours);
  loadPostureSnapshot();
}

function setupBriefingTabs() {
  const tabs = [
    { btn: "tabBtnShiftBrief", pane: "tabContentShiftBrief" },
    { btn: "tabBtnPostureGaps", pane: "tabContentPostureGaps" },
    { btn: "tabBtnEntityDossier", pane: "tabContentEntityDossier" }
  ];

  tabs.forEach(t => {
    const btnEl = document.getElementById(t.btn);
    if (!btnEl) return;
    btnEl.addEventListener("click", () => {
      tabs.forEach(other => {
        const ob = document.getElementById(other.btn);
        const op = document.getElementById(other.pane);
        if (ob) ob.classList.remove("active");
        if (op) {
          op.classList.remove("active");
          op.style.display = "none";
        }
      });
      btnEl.classList.add("active");
      const targetPane = document.getElementById(t.pane);
      if (targetPane) {
        targetPane.classList.add("active");
        targetPane.style.display = "block";
      }
    });
  });
}

async function loadShiftBriefing(hours = 8) {
  const narrativeBody = document.getElementById("shiftNarrativeBody");
  if (narrativeBody) {
    narrativeBody.innerHTML = `<p class="empty-state-muted">Aggregating operational delta across last ${hours} hours...</p>`;
  }

  try {
    const res = await fetch(`/api/briefings/shift?hours=${hours}`);
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const raw = await res.json();
    const briefing = raw.briefing || raw;


    currentShiftSlackBlocks = briefing.slack_blocks;

    // Update banner metadata
    const timeBadge = document.getElementById("shiftTimestampBadge");
    if (timeBadge) {
      const s = briefing.start_time ? new Date(briefing.start_time).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }) : "";
      const e = briefing.end_time ? new Date(briefing.end_time).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }) : "";
      timeBadge.textContent = `${briefing.shift_name || "Shift"} (${s} – ${e})`;
    }

    // Render 5 delta categories
    renderDeltaSection("countRequiresAttention", "listRequiresAttention", briefing.requires_attention, "⚠️ No critical issues requiring operator attention.");
    renderDeltaSection("countChangedSincePrevious", "listChangedSincePrevious", briefing.changed_since_previous, "🔄 No configuration mutations in this shift window.");
    renderDeltaSection("countAgentWip", "listAgentWip", briefing.agent_work_in_progress, "🤖 No active agent leases or pending proposals.");
    renderDeltaSection("countHealthy", "listHealthy", briefing.no_action_required, "🛡️ No baseline assertions recorded.");
    renderDeltaSection("countCarryover", "listCarryover", briefing.carry_over, "⏳ No carry-over issues.");

    // Render markdown narrative
    if (narrativeBody) {
      narrativeBody.innerHTML = formatMarkdown(briefing.summary_narrative || "*No shift narrative generated.*");
    }
  } catch (err) {
    console.error("Failed to load shift briefing:", err);
    if (narrativeBody) {
      showLoadError(narrativeBody, { title: "Couldn't load the shift briefing", error: err, retry: () => loadShiftBriefing(hours) });
    }
  }
}

function renderDeltaSection(countElemId, listElemId, items, emptyText) {
  const countEl = document.getElementById(countElemId);
  const listEl = document.getElementById(listElemId);
  if (!listEl) return;

  const count = Array.isArray(items) ? items.length : 0;
  if (countEl) countEl.textContent = count;

  if (count === 0) {
    listEl.innerHTML = `<p class="empty-state-muted" style="color:var(--c-neutral); margin:0; font-style:italic;">${escapeHtml(emptyText)}</p>`;
    return;
  }

  listEl.innerHTML = items.map(item => {
    const title = item.title || item.summary || item.headline || item.id || JSON.stringify(item);
    const id = item.id || item.issue_id || "";
    const agent = item.agent || item.author || "";
    const severity = item.severity || item.priority || "";
    const sevBadge = severity ? `<span style="font-size:11px; font-weight:700; padding:1px 5px; border-radius:3px; background:var(--surface-inset-strong); color:var(--text-muted); text-transform:uppercase;">${escapeHtml(severity)}</span>` : "";
    return `
      <div style="padding:4px 0; border-bottom:1px solid var(--border-subtle); display:flex; align-items:center; justify-content:space-between; gap:6px;">
        <span style="overflow:hidden; text-overflow:ellipsis; white-space:nowrap; flex:1;" title="${escapeHtml(title)}">${escapeHtml(title)}</span>
        <div style="display:flex; align-items:center; gap:4px; flex-shrink:0;">
          ${sevBadge}
          ${agent ? `<span style="font-size:11px; color:var(--c-sky);">@${escapeHtml(agent.replace('@', ''))}</span>` : ""}
        </div>
      </div>
    `;
  }).join("");
}

async function loadPostureSnapshot() {
  try {
    const res = await fetch("/api/briefings/posture");
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const raw = await res.json();
    const snapshot = raw.snapshot || raw;

    // Freshness bar
    const freshSeg = document.getElementById("freshnessBarFresh");
    const recentSeg = document.getElementById("freshnessBarRecent");
    const staleSeg = document.getElementById("freshnessBarStale");
    const legendEl = document.getElementById("freshnessLegend");

    const counts = snapshot.knowledge_freshness || snapshot.metrics?.assertion_freshness || { fresh_under_1h: 0, recent_1h_to_24h: 0, stale_over_24h: 0 };

    const total = (counts.fresh_under_1h || 0) + (counts.recent_1h_to_24h || 0) + (counts.stale_over_24h || 0);

    if (total > 0) {
      const fPct = Math.round((counts.fresh_under_1h / total) * 100);
      const rPct = Math.round((counts.recent_1h_to_24h / total) * 100);
      const sPct = Math.round((counts.stale_over_24h / total) * 100);
      if (freshSeg) freshSeg.style.width = `${fPct}%`;
      if (recentSeg) recentSeg.style.width = `${rPct}%`;
      if (staleSeg) staleSeg.style.width = `${sPct}%`;
    }
    if (legendEl) {
      legendEl.textContent = `Fresh: ${counts.fresh_under_1h || 0} | Recent: ${counts.recent_1h_to_24h || 0} | Stale: ${counts.stale_over_24h || 0}`;
    }

    // Knowledge gaps
    const gaps = snapshot.knowledge_gaps || [];
    const gapsCountEl = document.getElementById("postureGapsCount");
    if (gapsCountEl) gapsCountEl.textContent = gaps.length;

    const tbody = document.getElementById("bodyKnowledgeGaps");
    if (tbody) {
      if (gaps.length === 0) {
        tbody.innerHTML = `<tr><td colspan="6" style="padding:12px; color:var(--c-ok); text-align:center;">🛡️ Zero unverified knowledge gaps identified across registered entities.</td></tr>`;
      } else {
        tbody.innerHTML = gaps.map(g => `
          <tr style="border-bottom:1px solid var(--border-color);">
            <td style="padding:8px 10px; font-family:monospace; color:var(--text-muted);">${escapeHtml(g.gap_id || "-")}</td>
            <td style="padding:8px 10px; text-transform:uppercase; font-size:11px; color:var(--text-dim);">${escapeHtml(g.category || "-")}</td>
            <td style="padding:8px 10px; font-weight:600; color:var(--text-main);">${escapeHtml(g.subject || "-")}</td>
            <td style="padding:8px 10px; color:var(--text-muted);">${escapeHtml(g.description || "-")}</td>
            <td style="padding:8px 10px;">
              <span style="font-size:11px; font-weight:700; padding:2px 6px; border-radius:3px; background:${g.severity === 'high' ? 'var(--c-danger-bg)' : 'var(--c-warn-bg)'}; color:${g.severity === 'high' ? 'var(--c-danger)' : 'var(--c-warn)'}; text-transform:uppercase;">
                ${escapeHtml(g.severity || "medium")}
              </span>
            </td>
            <td style="padding:8px 10px; color:var(--c-sky);">@${escapeHtml((g.recommended_agent || "tenant-cartographer").replace('@', ''))}</td>
          </tr>
        `).join("");
      }
    }
  } catch (err) {
    console.error("Failed to load posture snapshot:", err);
    showLoadError(document.getElementById("bodyKnowledgeGaps"), { title: "Couldn't load the posture snapshot", error: err, retry: loadPostureSnapshot, colspan: 6 });
  }
}

async function fetchEntityDossier(subjectType, subjectId) {
  const container = document.getElementById("dossierResultContainer");
  if (!container) return;
  container.style.display = "block";
  container.innerHTML = `<p class="empty-state-muted">Synthesizing multi-agent dossier for ${escapeHtml(subjectType)}: <code>${escapeHtml(subjectId)}</code>...</p>`;

  try {
    const res = await fetch(`/api/knowledge/entity/${encodeURIComponent(subjectType)}/${encodeURIComponent(subjectId)}`);
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const raw = await res.json();
    const dossier = raw.dossier || raw;


    const facts = dossier.facts || {};
    const observers = dossier.contributing_agents || [];
    const health = dossier.overall_health || "unknown";
    const healthColor = health === "healthy" ? "var(--c-ok)" : health === "degraded" ? "var(--c-warn)" : health === "failing" ? "var(--c-danger)" : "var(--text-dim)";
    const gaps = dossier.knowledge_gaps || [];
    const issues = dossier.linked_issues || [];


    container.innerHTML = `
      <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:12px; border-bottom:1px solid var(--border-color); padding-bottom:10px;">
        <div style="display:flex; align-items:center; gap:10px;">
          <span style="font-size:14px; font-weight:700; color:var(--text-main);">${escapeHtml(subjectId)}</span>
          <span style="font-size:11px; padding:2px 7px; border-radius:4px; background:var(--surface-inset-strong); color:var(--text-dim); text-transform:uppercase;">${escapeHtml(subjectType)}</span>
        </div>
        <div style="display:flex; align-items:center; gap:8px;">
          <span style="font-size:11px; text-transform:uppercase; font-weight:700; padding:3px 8px; border-radius:4px; background:var(--surface-stripe); color:${healthColor};">Health: ${escapeHtml(health)}</span>
        </div>
      </div>
      <div style="font-size:12px; color:var(--text-dim); margin-bottom:10px;">
        <strong>Contributing Observers:</strong> ${observers.map(o => `<span style="color:var(--c-sky); margin-right:6px;">@${escapeHtml(o.replace('@', ''))}</span>`).join("") || "None"}
      </div>
      ${gaps.length > 0 ? `
        <div style="margin-top:12px; margin-bottom:12px; padding:10px; background:var(--c-warn-faint); border-left:3px solid var(--c-warn); border-radius:4px;">
          <h4 style="font-size:11px; font-weight:700; color:var(--c-warn); text-transform:uppercase; margin-bottom:4px;">Entity Knowledge Gaps / Unknowns</h4>
          <ul style="margin:0; padding-left:16px; font-size:12px; color:var(--text-muted);">
            ${gaps.map(g => `<li>${escapeHtml(g)}</li>`).join("")}
          </ul>
        </div>
      ` : ""}
      <div style="margin-top:12px;">
        <h4 style="font-size:12px; font-weight:700; color:var(--text-main); text-transform:uppercase; margin-bottom:6px;">Established Facts &amp; Attestations</h4>
        <pre style="background:var(--surface-inset-strong); border:1px solid var(--border-color); border-radius:6px; padding:10px; font-size:11px; color:var(--text-muted); overflow-x:auto;">${escapeHtml(JSON.stringify(facts, null, 2))}</pre>
      </div>
    `;

  } catch (err) {
    console.error("Failed to fetch entity dossier:", err);
    showLoadError(container, { title: "Couldn't build the entity dossier", error: err, retry: () => fetchEntityDossier(subjectType, subjectId) });
  }
}

async function triggerShiftBrief() {
  const hours = parseInt(document.getElementById("shiftWindowSelect")?.value || "8", 10);
  try {
    showToast("info", `Triggering shift handover brief across last ${hours}h...`);
    const res = await fetch(`/api/briefings/trigger?hours=${hours}`, { method: "POST" });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const data = await res.json();
    showToast("success", "Shift brief computed and broadcast to #briefings/shift-briefings!");
    await loadShiftBriefing(hours);
  } catch (err) {
    console.error("Failed to trigger shift brief:", err);
    showToast("error", `Failed to trigger briefing: ${err.message}`);
  }
}

function copySlackBlocks() {
  if (!currentShiftSlackBlocks) {
    showToast("warning", "No Slack Blocks available to copy");
    return;
  }
  const payloadStr = JSON.stringify(currentShiftSlackBlocks, null, 2);
  if (navigator.clipboard && navigator.clipboard.writeText) {
    navigator.clipboard.writeText(payloadStr).then(
      () => showToast("success", "Slack Block Kit payload copied to clipboard!"),
      () => showToast("error", "Failed to copy Slack Blocks to clipboard")
    );
  }
}





// --- Accessibility helpers (#7) ---
// Screen-reader announcements via a single polite live region.
function announce(text) {
  const el = document.getElementById("srAnnouncer");
  if (!el || !text) return;
  el.textContent = "";
  // Re-set on next frame so repeated identical messages are still announced.
  requestAnimationFrame(() => { el.textContent = text; });
}
window.announce = announce;

// Elements rendered as divs that behave like buttons: Enter/Space activates.
const A11Y_CLICKABLE = ".stream-header, .topic-item, .dm-item, .kanban-card, #dmSectionHeader, div.drawer-proposal-item[tabindex]";

function syncTabState(tab) {
  const on = tab.classList.contains("active");
  tab.setAttribute("aria-selected", on ? "true" : "false");
  tab.tabIndex = on ? 0 : -1;
  if (on && tab.getAttribute("aria-controls") === "drawerContent") {
    document.getElementById("drawerContent")?.setAttribute("aria-labelledby", tab.id);
  }
}

function syncNavState(nav) {
  if (nav.classList.contains("active")) nav.setAttribute("aria-current", "page");
  else nav.removeAttribute("aria-current");
}

function setupA11y() {
  // Tabs: aria-selected / roving tabindex mirror the existing `.active` class,
  // so the individual switch* functions don't need to know about ARIA.
  const tabs = Array.from(document.querySelectorAll('[role="tab"]'));
  const navs = Array.from(document.querySelectorAll(".topbar-nav .nav-tab"));
  tabs.forEach(syncTabState);
  navs.forEach(syncNavState);
  const classObserver = new MutationObserver((records) => {
    records.forEach((r) => {
      const el = r.target;
      if (el.getAttribute("role") === "tab") syncTabState(el);
      else if (el.classList.contains("nav-tab")) syncNavState(el);
    });
  });
  [...tabs, ...navs].forEach((el) => classObserver.observe(el, { attributes: true, attributeFilter: ["class"] }));

  // Arrow-key navigation within tablists (automatic activation).
  document.querySelectorAll('[role="tablist"]').forEach((list) => {
    list.addEventListener("keydown", (e) => {
      const keys = ["ArrowLeft", "ArrowRight", "Home", "End"];
      if (!keys.includes(e.key)) return;
      const items = Array.from(list.querySelectorAll('[role="tab"]')).filter((t) => t.offsetParent !== null);
      const idx = items.indexOf(document.activeElement);
      if (idx === -1) return;
      e.preventDefault();
      let next = idx;
      if (e.key === "ArrowLeft") next = (idx - 1 + items.length) % items.length;
      else if (e.key === "ArrowRight") next = (idx + 1) % items.length;
      else if (e.key === "Home") next = 0;
      else next = items.length - 1;
      items[next].focus();
      items[next].click();
    });
  });

  // Right drawer toggle: aria-expanded follows the drawer's closed class.
  const drawer = document.getElementById("sidebarRight");
  const drawerBtn = document.getElementById("toggleRightDrawerBtn");
  if (drawer && drawerBtn) {
    const syncDrawer = () => drawerBtn.setAttribute("aria-expanded", drawer.classList.contains("sidebar-right-closed") ? "false" : "true");
    syncDrawer();
    new MutationObserver(syncDrawer).observe(drawer, { attributes: true, attributeFilter: ["class"] });
  }

  // DM section collapse: aria-expanded follows the list's collapsed class.
  const dmHeader = document.getElementById("dmSectionHeader");
  const dmList = document.getElementById("dmList");
  if (dmHeader && dmList) {
    const syncDm = () => dmHeader.setAttribute("aria-expanded", dmList.classList.contains("collapsed") ? "false" : "true");
    syncDm();
    new MutationObserver(syncDm).observe(dmList, { attributes: true, attributeFilter: ["class"] });
  }

  // Keyboard activation for div-based controls.
  document.addEventListener("keydown", (e) => {
    if (e.key !== "Enter" && e.key !== " ") return;
    const el = e.target;
    if (!(el instanceof Element) || !el.matches(A11Y_CLICKABLE)) return;
    e.preventDefault();
    el.click();
  });

  // Skip link: move focus into the main region.
  document.querySelector(".skip-link")?.addEventListener("click", (e) => {
    e.preventDefault();
    document.getElementById("mainContent")?.focus();
  });
}
