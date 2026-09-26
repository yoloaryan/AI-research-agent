/**
 * app.js — AI Research Studio frontend
 * =====================================
 * Handles: research submission, pipeline state, markdown rendering,
 * report storage (via backend), share URL, copy/download, history.
 *
 * lucide, DOMPurify, marked are loaded synchronously in <head>
 * so they are guaranteed available when this script runs.
 */

// Base API endpoint: dynamic relative URL for production/Render and port 8000,
// with localhost:8000 fallback for local python3 -m http.server 5500
const API = (window.location.port === "5500" || window.location.port === "3000")
  ? "http://localhost:8000"
  : "";

// Init icons immediately — lucide.min.js is in <head> so it's ready
if (typeof lucide !== "undefined") lucide.createIcons();

// ── DOM references ────────────────────────────────────────────────────────────
const input        = document.getElementById("topicInput");
const runBtn       = document.getElementById("runBtn");
const hero         = document.getElementById("hero");
const researchView = document.getElementById("researchView");
const queryTitle   = document.getElementById("queryTitle");
const resultLayout = document.getElementById("resultLayout");
const progressBar  = document.getElementById("progressBar");
const toastEl      = document.getElementById("toast");
const breadcrumb   = document.getElementById("breadcrumbTitle");

// ── State ─────────────────────────────────────────────────────────────────────
const PIPELINE_STAGES = ["search", "reader", "writer", "critic"];
let currentReport = null;   // Full report object from backend
let isRunning     = false;

// ── Markdown renderer (safe) ──────────────────────────────────────────────────
function renderMd(text, target) {
  if (!text) { target.innerHTML = ""; return; }
  const rawHtml = (typeof marked !== "undefined" && marked.parse)
    ? marked.parse(text)
    : text.replace(/\n/g, "<br>");
  target.innerHTML = (typeof DOMPurify !== "undefined")
    ? DOMPurify.sanitize(rawHtml, { USE_PROFILES: { html: true } })
    : rawHtml; // fallback if DOMPurify didn't load
}

// ── Toast ─────────────────────────────────────────────────────────────────────
let toastTimer = null;
function toast(msg, type = "default") {
  toastEl.textContent = msg;
  toastEl.className = `toast show ${type}`;
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => toastEl.classList.remove("show"), 2800);
}

// ── Escape HTML ───────────────────────────────────────────────────────────────
function esc(s) {
  return String(s ?? "").replace(/[&<>"']/g, c =>
    ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#039;" }[c])
  );
}

// ── Pipeline stage management ─────────────────────────────────────────────────
function setStage(name, state, text) {
  const el = document.querySelector(`[data-stage="${name}"]`);
  if (!el) return;
  el.classList.remove("active", "done", "error");
  if (state) el.classList.add(state);
  el.querySelector(".status-text").textContent = text;
}

function resetStages() {
  PIPELINE_STAGES.forEach(s => setStage(s, "", "Waiting"));
  progressBar.style.width = "0%";
}

function applyStages(stages = {}) {
  const map = {
    "complete": ["done", "Complete"],
    "running":  ["active", "Running"],
    "failed":   ["error", "Failed"],
    "pending":  ["", "Waiting"],
  };
  PIPELINE_STAGES.forEach(name => {
    const status = stages[name] || "pending";
    const [cls, label] = map[status] || ["", status];
    setStage(name, cls, label);
  });
}

// ── Recent list ───────────────────────────────────────────────────────────────
let recent = JSON.parse(localStorage.getItem("rs_recent") || "[]");

function renderRecent() {
  const box = document.getElementById("recentList");
  if (!box) return;
  box.innerHTML = recent.slice(0, 8).map((x, i) =>
    `<button class="recent-item" data-index="${i}" title="${esc(x.topic)}" role="listitem">
       <i data-lucide="clock-3" aria-hidden="true"></i>
       <span>${esc(x.topic)}</span>
     </button>`
  ).join("");
  box.querySelectorAll(".recent-item").forEach(btn => {
    btn.onclick = () => {
      input.value = recent[Number(btn.dataset.index)].topic;
      input.focus();
    };
  });
  if (typeof lucide !== "undefined") lucide.createIcons();
}

function addToRecent(report) {
  const entry = { topic: report.topic, report_id: report.report_id };
  recent = [entry, ...recent.filter(x => x.report_id !== report.report_id)].slice(0, 12);
  localStorage.setItem("rs_recent", JSON.stringify(recent));
  renderRecent();
}

// ── Source cards ──────────────────────────────────────────────────────────────
function renderSources(sources) {
  const section = document.getElementById("sourcesSection");
  const grid    = document.getElementById("sourcesGrid");
  if (!sources || sources.length === 0) {
    section.classList.add("hidden");
    return;
  }
  section.classList.remove("hidden");
  grid.innerHTML = sources.slice(0, 10).map(s => {
    const url   = esc(s.url || "");
    const title = esc(s.title || s.domain || url);
    const domain = esc(s.domain || "");
    return `
      <div class="source-card">
        <div class="source-top">
          <span class="source-domain">${domain}</span>
          ${url ? `<a href="${url}" target="_blank" rel="noopener noreferrer" class="source-link" aria-label="Open ${title} in new tab">
            <i data-lucide="external-link"></i>
          </a>` : ""}
        </div>
        <div class="source-title">${title}</div>
        ${url ? `<div class="source-url">${esc(url.replace(/https?:\/\//, "").substring(0, 60))}…</div>` : `<div class="source-url muted">URL unavailable</div>`}
      </div>`;
  }).join("");
  if (typeof lucide !== "undefined") lucide.createIcons();
}

// ── Share / URL routing ───────────────────────────────────────────────────────
function getShareUrl(report_id) {
  const base = `${location.protocol}//${location.host}${location.pathname}`;
  return `${base}?report=${report_id}`;
}

async function shareReport() {
  if (!currentReport) { toast("No report to share.", "error"); return; }
  const url = getShareUrl(currentReport.report_id);
  const shareData = {
    title: `Research: ${currentReport.topic}`,
    text: `AI Research Studio report — ${currentReport.topic}`,
    url,
  };

  if (navigator.share && navigator.canShare && navigator.canShare(shareData)) {
    try {
      await navigator.share(shareData);
      toast("Report shared ✓");
      return;
    } catch (e) {
      if (e.name === "AbortError") return; // user cancelled — no error
    }
  }
  // Fallback: copy to clipboard
  try {
    await navigator.clipboard.writeText(url);
    toast("Share link copied to clipboard ✓");
  } catch (_) {
    // Fallback for browsers without clipboard API
    const ta = document.createElement("textarea");
    ta.value = url;
    document.body.appendChild(ta);
    ta.select();
    document.execCommand("copy");
    document.body.removeChild(ta);
    toast("Share link copied ✓");
  }
}

// ── Load report from URL param ────────────────────────────────────────────────
async function loadReportFromUrl() {
  const params = new URLSearchParams(location.search);
  const rid = params.get("report");
  if (!rid) return;

  // Show loading state
  breadcrumb.textContent = "Loading report…";
  hero.classList.add("hidden");
  researchView.classList.remove("hidden");
  queryTitle.textContent = "Loading…";

  try {
    const resp = await fetch(`${API}/reports/${encodeURIComponent(rid)}`);
    if (!resp.ok) throw new Error("Report not found.");
    const json = await resp.json();
    const report = json.data;
    displayReport(report, /* fromUrl= */ true);
  } catch (err) {
    toast("Report could not be loaded: " + err.message, "error");
    breadcrumb.textContent = "New session";
    hero.classList.remove("hidden");
    researchView.classList.add("hidden");
  }
}

// ── Display a completed report ────────────────────────────────────────────────
function displayReport(report, fromUrl = false) {
  currentReport = report;

  // Update header
  queryTitle.textContent = report.topic;
  breadcrumb.textContent = report.topic;
  document.getElementById("shareTopBtn").style.display = "";

  // Apply stages if available
  if (report.stages) applyStages(report.stages);
  progressBar.style.width = "100%";

  // Render markdown report
  const reportEl = document.getElementById("report");
  renderMd(report.report || "*(No report generated.)*", reportEl);

  // Render critic feedback (markdown)
  const feedbackEl = document.getElementById("feedbackMd");
  renderMd(report.feedback || "*(No critic feedback.)*", feedbackEl);

  // Trace panel
  document.getElementById("searchResults").textContent = report.search_results || "—";
  document.getElementById("scrapedContent").textContent = report.scraped_content || "—";

  // Sources
  renderSources(report.sources || []);

  // Show result layout
  resultLayout.classList.remove("hidden");

  // Update URL (without reload) — only when freshly generated, not when loading from URL
  if (!fromUrl && report.report_id) {
    const newUrl = getShareUrl(report.report_id);
    history.replaceState(null, "", newUrl);
  }

  // Scroll to report smoothly
  setTimeout(() => resultLayout.scrollIntoView({ behavior: "smooth", block: "start" }), 100);

  if (typeof lucide !== "undefined") lucide.createIcons();
}

// ── Main research runner ───────────────────────────────────────────────────────
async function runResearch() {
  if (isRunning) return;
  const topic = input.value.trim();
  if (!topic) { input.focus(); toast("Please enter a research topic.", "error"); return; }

  isRunning = true;

  // Switch to research view
  hero.classList.add("hidden");
  researchView.classList.remove("hidden");
  resultLayout.classList.add("hidden");
  queryTitle.textContent = topic;
  breadcrumb.textContent = topic;
  resetStages();
  document.getElementById("shareTopBtn").style.display = "none";

  // Disable run button
  runBtn.disabled = true;
  runBtn.innerHTML = '<i data-lucide="loader-circle"></i>';
  lucide.createIcons();

  // Animated stage progression while backend runs
  setStage("search", "active", "Searching…");
  progressBar.style.width = "10%";

  const timers = [
    setTimeout(() => { setStage("search", "done", "Complete"); setStage("reader", "active", "Reading…"); progressBar.style.width = "35%"; }, 5000),
    setTimeout(() => { setStage("reader", "done", "Complete"); setStage("writer", "active", "Writing…"); progressBar.style.width = "62%"; }, 14000),
    setTimeout(() => { setStage("writer", "done", "Complete"); setStage("critic", "active", "Reviewing…"); progressBar.style.width = "85%"; }, 26000),
  ];

  const controller = new AbortController();
  const fetchTimeout = setTimeout(() => controller.abort(), 300000); // 5-min guard

  try {
    const response = await fetch(`${API}/research`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ topic }),
      signal: controller.signal,
    });
    clearTimeout(fetchTimeout);

    const json = await response.json();

    timers.forEach(clearTimeout);

    if (!response.ok) {
      // Partial result on 422
      const errData = json.data || json.detail;
      if (errData && errData.report) {
        displayReport(errData);
        toast("Research completed with some errors. See report.", "warn");
      } else {
        const msg = (json.detail && json.detail.error) || json.detail || "Research failed.";
        throw new Error(msg);
      }
      return;
    }

    const report = json.data;
    displayReport(report);
    addToRecent(report);
    toast("Research complete ✓");

  } catch (err) {
    timers.forEach(clearTimeout);
    clearTimeout(fetchTimeout);

    // Mark the active stage as failed
    const failing = PIPELINE_STAGES.find(s =>
      document.querySelector(`[data-stage="${s}"]`)?.classList.contains("active")
    );
    if (failing) setStage(failing, "error", "Failed");

    let userMsg = "Research could not be completed.";
    if (err.name === "AbortError") userMsg = "Request timed out. Please try again.";
    else if (err.message) userMsg = err.message;

    toast(userMsg, "error");
    console.error("[Research error]", err);
  } finally {
    isRunning = false;
    runBtn.disabled = false;
    runBtn.innerHTML = '<i data-lucide="arrow-up"></i>';
    lucide.createIcons();
  }
}

// ── Copy report ───────────────────────────────────────────────────────────────
async function copyReport() {
  if (!currentReport) return;
  try {
    await navigator.clipboard.writeText(currentReport.report || "");
    toast("Report copied ✓");
  } catch (_) {
    toast("Could not copy to clipboard.", "error");
  }
}

// ── Download Markdown ─────────────────────────────────────────────────────────
async function downloadMarkdown() {
  if (!currentReport) return;
  const rid = currentReport.report_id;
  if (rid) {
    // Try server download first (persisted file)
    try {
      const a = document.createElement("a");
      a.href = `${API}/reports/${rid}/download/markdown`;
      a.download = `research-report-${rid.substring(0, 8)}.md`;
      a.click();
      toast("Markdown downloaded ✓");
      return;
    } catch (_) { /* fall through to client-side */ }
  }
  // Client-side fallback
  const blob = new Blob([currentReport.report || ""], { type: "text/markdown" });
  const url  = URL.createObjectURL(blob);
  const a    = document.createElement("a");
  a.href = url;
  a.download = "research-report.md";
  a.click();
  URL.revokeObjectURL(url);
  toast("Markdown downloaded ✓");
}

// ── Download PDF ──────────────────────────────────────────────────────────────
async function downloadPdf() {
  if (!currentReport) return;
  const rid = currentReport.report_id;
  if (!rid) { toast("No report ID — cannot download PDF.", "error"); return; }

  toast("Generating PDF…");
  try {
    const resp = await fetch(`${API}/reports/${rid}/download/pdf`);
    if (!resp.ok) {
      const err = await resp.json().catch(() => ({}));
      throw new Error((err.detail && err.detail.error) || "PDF generation failed.");
    }
    const blob = await resp.blob();
    const url  = URL.createObjectURL(blob);
    const a    = document.createElement("a");
    a.href = url;
    a.download = `research-report-${rid.substring(0, 8)}.pdf`;
    a.click();
    URL.revokeObjectURL(url);
    toast("PDF downloaded ✓");
  } catch (err) {
    toast(err.message || "PDF download failed.", "error");
    console.error("[PDF error]", err);
  }
}

// ── History panel ─────────────────────────────────────────────────────────────
function renderHistory() {
  const list = document.getElementById("historyList");
  if (recent.length === 0) {
    list.innerHTML = `<p class="empty-state">No research history yet.</p>`;
    return;
  }
  list.innerHTML = recent.map(r => `
    <button class="history-item" data-rid="${esc(r.report_id || "")}" data-topic="${esc(r.topic)}">
      <i data-lucide="file-text" aria-hidden="true"></i>
      <div class="history-item-info">
        <span class="history-topic">${esc(r.topic)}</span>
      </div>
      <i data-lucide="arrow-right" class="history-arrow" aria-hidden="true"></i>
    </button>`
  ).join("");

  list.querySelectorAll(".history-item").forEach(btn => {
    btn.onclick = async () => {
      const rid = btn.dataset.rid;
      closeHistory();
      if (!rid) { input.value = btn.dataset.topic; return; }
      try {
        const resp = await fetch(`${API}/reports/${encodeURIComponent(rid)}`);
        if (!resp.ok) throw new Error("Not found");
        const json = await resp.json();
        hero.classList.add("hidden");
        researchView.classList.remove("hidden");
        displayReport(json.data);
        // Update URL
        history.pushState(null, "", getShareUrl(rid));
      } catch (_) {
        // Fallback: just pre-fill topic
        input.value = btn.dataset.topic;
        toast("Could not reload report — try researching again.", "warn");
      }
    };
  });
  if (typeof lucide !== "undefined") lucide.createIcons();
}

function openHistory() {
  renderHistory();
  document.getElementById("historyOverlay").classList.remove("hidden");
}
function closeHistory() {
  document.getElementById("historyOverlay").classList.add("hidden");
}

// ── New research ──────────────────────────────────────────────────────────────
function newResearch() {
  researchView.classList.add("hidden");
  hero.classList.remove("hidden");
  input.value = "";
  breadcrumb.textContent = "New session";
  currentReport = null;
  document.getElementById("shareTopBtn").style.display = "none";
  input.focus();
  history.replaceState(null, "", location.pathname);
}

// ── Theme ─────────────────────────────────────────────────────────────────────
function applyTheme() {
  const saved = localStorage.getItem("rs_theme");
  if (saved === "light") document.body.classList.remove("dark");
  else document.body.classList.add("dark");
}
function toggleTheme() {
  document.body.classList.toggle("dark");
  localStorage.setItem("rs_theme", document.body.classList.contains("dark") ? "dark" : "light");
}

// ── Wire up all events ────────────────────────────────────────────────────────
document.addEventListener("DOMContentLoaded", () => {
  // Re-run createIcons after all HTML is parsed (picks up any late-added elements)
  if (typeof lucide !== "undefined") lucide.createIcons();

  applyTheme();
  renderRecent();

  // Run research
  runBtn.addEventListener("click", runResearch);
  input.addEventListener("keydown", e => {
    if ((e.metaKey || e.ctrlKey) && e.key === "Enter") runResearch();
  });

  // Suggestions
  document.querySelectorAll(".suggestions button").forEach(btn => {
    btn.addEventListener("click", () => {
      input.value = btn.dataset.topic;
      input.focus();
    });
  });

  // New research buttons
  document.getElementById("newResearch").onclick = newResearch;
  document.getElementById("newResearch2").onclick = newResearch;

  // Toolbar buttons
  document.getElementById("copyBtn").onclick = copyReport;
  document.getElementById("downloadMdBtn").onclick = downloadMarkdown;
  document.getElementById("downloadPdfBtn").onclick = downloadPdf;
  document.getElementById("shareBtn").onclick = shareReport;
  document.getElementById("shareTopBtn").onclick = shareReport;

  // Theme
  document.getElementById("themeBtn").onclick = toggleTheme;

  // Mobile sidebar
  document.getElementById("menuBtn").onclick = () =>
    document.getElementById("sidebar").classList.toggle("open");

  // History nav
  document.getElementById("navHistory").onclick = openHistory;
  document.getElementById("closeHistory").onclick = closeHistory;
  document.getElementById("historyOverlay").addEventListener("click", e => {
    if (e.target === document.getElementById("historyOverlay")) closeHistory();
  });

  // Keyboard shortcuts
  document.addEventListener("keydown", e => {
    if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") {
      e.preventDefault();
      if (!document.getElementById("hero").classList.contains("hidden")) {
        input.focus();
      } else {
        newResearch();
      }
    }
    if (e.key === "Escape") {
      if (!document.getElementById("historyOverlay").classList.contains("hidden")) closeHistory();
    }
  });

  // ── URL-based report loading ─────────────────────────────────────────────
  loadReportFromUrl();
});
