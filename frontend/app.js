"use strict";

/* ============================================================
   Skylark Intelligence — frontend workspace
   Vanilla JS, no framework. Reads the deterministic BI API and
   presents it as a calm business-intelligence workspace.
   ============================================================ */

const REPO_URL = "https://github.com/niranjanagopinath/Skylark-Drones-Agent";

/* ---------- Professional icon set (Lucide-style, stroke = currentColor) ---------- */
const ICONS = {
  spark: '<path d="M4 14l5-5 4 3 7-8"/><path d="M4 20h16"/>',
  overview: '<rect x="3" y="3" width="7" height="9" rx="1"/><rect x="14" y="3" width="7" height="5" rx="1"/><rect x="14" y="12" width="7" height="9" rx="1"/><rect x="3" y="16" width="7" height="5" rx="1"/>',
  sales: '<polyline points="22 7 13.5 15.5 8.5 10.5 2 17"/><polyline points="16 7 22 7 22 13"/>',
  operations: '<polyline points="22 12 18 12 15 21 9 3 6 12 2 12"/>',
  financials: '<path d="M21 12V7H5a2 2 0 0 1 0-4h14v4"/><path d="M3 5v14a2 2 0 0 0 2 2h16v-5"/><path d="M18 12a2 2 0 0 0 0 4h4v-4z"/>',
  ask: '<circle cx="11" cy="11" r="7"/><line x1="21" y1="21" x2="16.65" y2="16.65"/>',
  github: '<path d="M9 19c-5 1.5-5-2.5-7-3m14 6v-3.87a3.37 3.37 0 0 0-.94-2.61c3.14-.35 6.44-1.54 6.44-7A5.44 5.44 0 0 0 20 4.77 5.07 5.07 0 0 0 19.91 1S18.73.65 16 2.48a13.38 13.38 0 0 0-7 0C6.27.65 5.09 1 5.09 1A5.07 5.07 0 0 0 5 4.77a5.44 5.44 0 0 0-1.5 3.78c0 5.42 3.3 6.61 6.44 7A3.37 3.37 0 0 0 9 18.13V22"/>',
  menu: '<line x1="3" y1="6" x2="21" y2="6"/><line x1="3" y1="12" x2="21" y2="12"/><line x1="3" y1="18" x2="21" y2="18"/>',
  refresh: '<path d="M3 12a9 9 0 0 1 15-6.7L21 8"/><path d="M21 3v5h-5"/><path d="M21 12a9 9 0 0 1-15 6.7L3 16"/><path d="M3 21v-5h5"/>',
  barchart: '<line x1="12" y1="20" x2="12" y2="10"/><line x1="18" y1="20" x2="18" y2="4"/><line x1="6" y1="20" x2="6" y2="16"/>',
  layers: '<polygon points="12 2 2 7 12 12 22 7 12 2"/><polyline points="2 17 12 22 22 17"/><polyline points="2 12 12 17 22 12"/>',
  alert: '<path d="M10.29 3.86 1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"/><line x1="12" y1="9" x2="12" y2="13"/><line x1="12" y1="17" x2="12.01" y2="17"/>',
  info: '<circle cx="12" cy="12" r="10"/><line x1="12" y1="16" x2="12" y2="12"/><line x1="12" y1="8" x2="12.01" y2="8"/>',
  check: '<path d="M22 11.08V12a10 10 0 1 1-5.93-9.14"/><polyline points="22 4 12 14.01 9 11.01"/>',
  external: '<path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6"/><polyline points="15 3 21 3 21 9"/><line x1="10" y1="14" x2="21" y2="3"/>',
  chev: '<polyline points="9 18 15 12 9 6"/>',
  clock: '<circle cx="12" cy="12" r="10"/><polyline points="12 6 12 12 16 14"/>',
  database: '<ellipse cx="12" cy="5" rx="9" ry="3"/><path d="M21 12c0 1.66-4 3-9 3s-9-1.34-9-3"/><path d="M3 5v14c0 1.66 4 3 9 3s9-1.34 9-3V5"/>',
  wallet: '<path d="M21 12V7H5a2 2 0 0 1 0-4h14v4"/><path d="M3 5v14a2 2 0 0 0 2 2h16v-5"/><path d="M18 12a2 2 0 0 0 0 4h4v-4z"/>',
  target: '<circle cx="12" cy="12" r="9"/><circle cx="12" cy="12" r="5"/><circle cx="12" cy="12" r="1"/>',
};
function svg(name, size = 18) {
  return `<svg viewBox="0 0 24 24" width="${size}" height="${size}" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">${ICONS[name] || ""}</svg>`;
}

/* ---------- Utilities ---------- */
const $ = (id) => document.getElementById(id);
const esc = (s) => String(s ?? "").replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));

function money(v) {
  if (v === null || v === undefined || isNaN(v)) return "—";
  const a = Math.abs(v), s = v < 0 ? "-" : "";
  if (a >= 1e7) return `${s}₹${(a / 1e7).toFixed(2)} Cr`;
  if (a >= 1e5) return `${s}₹${(a / 1e5).toFixed(2)} L`;
  return `${s}₹${Math.round(a).toLocaleString("en-IN")}`;
}
const num = (v) => (v === null || v === undefined ? "—" : Number(v).toLocaleString("en-IN"));
const pct = (v) => (v === null || v === undefined ? "—" : `${v}%`);
const humanize = (k) => k.replace(/_inr$/, "").replace(/_pct$/, "").replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());

/* ---------- Minimal, safe markdown (bold, bullets, line breaks) ---------- */
function mdToHtml(text) {
  const lines = esc(text).split("\n");
  let html = "", inList = false;
  for (const raw of lines) {
    const line = raw.replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>").replace(/(?<!\*)\*(?!\*)(.+?)\*/g, "<em>$1</em>");
    if (/^\s*[-•]\s+/.test(raw)) {
      if (!inList) { html += "<ul>"; inList = true; }
      html += "<li>" + line.replace(/^\s*[-•]\s+/, "") + "</li>";
    } else {
      if (inList) { html += "</ul>"; inList = false; }
      if (line.trim()) html += "<p>" + line + "</p>";
    }
  }
  if (inList) html += "</ul>";
  return html;
}

async function api(path) {
  const res = await fetch(path);
  const body = await res.json().catch(() => ({}));
  return { ok: res.ok, status: res.status, body };
}

/* ---------- App state ---------- */
const state = { dashboard: null, health: null, view: "overview", loading: false, error: null, ask: [] };

const VIEWS = {
  overview: { title: "Overview", desc: "What's happening across the business." },
  sales: { title: "Sales", desc: "Pipeline, sectors, stages and win rate." },
  operations: { title: "Operations", desc: "Work-order execution and delivery health." },
  financials: { title: "Financials", desc: "Billing, collections and receivables." },
  ask: { title: "Ask", desc: "Analyse the business with natural-language questions." },
};

/* ---------- Reusable pieces ---------- */
function kpi(label, value, context, iconName, accent) {
  return `<div class="kpi">
    <div class="label">${svg(iconName, 14)}${esc(label)}</div>
    <div class="value ${accent ? "accent-teal" : ""}">${value}</div>
    <div class="context">${context ? esc(context) : ""}</div>
  </div>`;
}
function card(title, sub, body, headRight) {
  return `<div class="card">
    <div class="card-head"><h3>${esc(title)}</h3>${headRight || (sub ? `<span class="sub">${esc(sub)}</span>` : "")}</div>
    ${body}
  </div>`;
}
function barChart(rows, { nameKey, valueKey, format = num, variant = "" }) {
  const vals = rows.map((r) => Number(r[valueKey]) || 0);
  const max = Math.max(1, ...vals.map(Math.abs));
  if (!rows.length) return `<div class="empty-hint">No data available.</div>`;
  return `<div class="bars">` + rows.map((r) => {
    const v = Number(r[valueKey]) || 0;
    const w = Math.max(2, Math.round((Math.abs(v) / max) * 100));
    return `<div class="bar-row">
      <div class="name" title="${esc(r[nameKey])}">${esc(r[nameKey])}</div>
      <div class="bar-track" role="img" aria-label="${esc(r[nameKey])}: ${esc(format(v))}"><div class="bar-fill ${variant}" style="width:${w}%"></div></div>
      <div class="val">${format(v)}</div>
    </div>`;
  }).join("") + `</div>`;
}
// Turn internal snake_case field names in caveats into plain words for readers,
// e.g. 'deal_value' -> "deal value". Leaves single-word quotes (e.g. 'energy') alone.
function humanizeCaveat(text) {
  return String(text).replace(/'([a-z]+(?:_[a-z]+)+)'/g, (_, f) => `"${f.replace(/_/g, " ")}"`);
}
// Broader: turn any bare snake_case field token into plain words for prose.
function humanizeFields(text) {
  return String(text).replace(/\b([a-z]{2,}(?:_[a-z]{2,})+)\b/g, (m) => m.replace(/_/g, " "));
}
function noteRow(kind, iconName, text) {
  return `<div class="note ${kind}">${svg(iconName, 15)}<span>${esc(humanizeCaveat(text))}</span></div>`;
}
function qualityStrip(q) {
  const d = q.deals, w = q.work_orders;
  const dv = d.coverage.deal_value ?? 0;
  const cv = w.coverage.collected_amount ?? 0;
  return `<div class="dq">
    <div class="dq-item"><div class="k">Deals analysed</div><div class="v">${num(d.raw_count)}</div></div>
    <div class="dq-item"><div class="k">Usable deal records</div><div class="v">${num(d.clean_count)}</div><div class="k" style="margin-top:4px">${num(d.duplicates_removed)} duplicates removed</div></div>
    <div class="dq-item"><div class="k">Deal-value coverage</div><div class="v">${dv}%</div><div class="meter"><span style="width:${dv}%"></span></div></div>
    <div class="dq-item"><div class="k">Collections coverage</div><div class="v">${cv}%</div><div class="meter"><span style="width:${cv}%"></span></div></div>
    <div class="dq-item"><div class="k">Work orders</div><div class="v">${num(w.clean_count)}</div></div>
  </div>`;
}

/* ---------- Views ---------- */
function renderOverview(d) {
  const p = d.pipeline.values, r = d.revenue.values, ops = d.operations.values;
  const kpis = `<div class="grid grid-kpi">
    ${kpi("Open Pipeline", money(p.open_pipeline_value_inr), `${num(p.open_deals)} open deals`, "sales", true)}
    ${kpi("Weighted Pipeline", money(p.weighted_pipeline_value_inr), "Probability-weighted", "target")}
    ${kpi("Active Work Orders", num(ops.total_work_orders), `${num(ops.execution_status_recorded)} with recorded status`, "operations")}
    ${kpi("Net Receivables", money(r.amount_receivable_inr), "Outstanding, incl. GST", "wallet")}
  </div>`;

  const sectorRows = [...d.sectors].sort((a, b) => (b.open_pipeline_value_inr || 0) - (a.open_pipeline_value_inr || 0)).slice(0, 7);
  const stageRows = [...d.stages].sort((a, b) => b.deals - a.deals).slice(0, 8);

  const row1 = `<div class="grid grid-2">
    ${card("Pipeline by sector", "Open value", barChart(sectorRows, { nameKey: "sector", valueKey: "open_pipeline_value_inr", format: money }))}
    ${card("Pipeline by stage", "Deal count", barChart(stageRows, { nameKey: "stage", valueKey: "deals", format: num, variant: "alt" }))}
  </div>`;

  const opsRows = d.operations.breakdown.slice(0, 6);
  const collEff = r.collection_efficiency_pct, billEff = r.billing_efficiency_pct;
  const financialMini = `
    <div style="display:flex;flex-direction:column;gap:14px">
      <div style="display:flex;gap:24px;flex-wrap:wrap">
        <div><div class="context">Billed</div><div style="font-size:18px;font-weight:650">${money(r.billed_value_inr)}</div></div>
        <div><div class="context">Collected</div><div style="font-size:18px;font-weight:650">${money(r.collected_amount_inr)}</div></div>
        <div><div class="context">Receivable</div><div style="font-size:18px;font-weight:650">${money(r.amount_receivable_inr)}</div></div>
      </div>
      <div><div class="context" style="margin-bottom:4px">Collection efficiency · ${pct(collEff)}</div><div class="meter"><span style="width:${collEff || 0}%"></span></div></div>
      <div><div class="context" style="margin-bottom:4px">Billing efficiency · ${pct(billEff)}</div><div class="meter"><span style="width:${billEff || 0}%"></span></div></div>
    </div>`;
  const row2 = `<div class="grid grid-2">
    ${card("Operational health", "Work orders by execution status", barChart(opsRows, { nameKey: "status", valueKey: "work_orders", format: num, variant: "pos" }))}
    ${card("Financial health", "Billing & collections", financialMini)}
  </div>`;

  const dq = `<div class="card">
    <div class="card-head"><h3>Data quality</h3><span class="sub">Source coverage &amp; cleaning</span></div>
    ${qualityStrip(d.quality)}
  </div>`;

  return kpis + `<div class="section-title">Business snapshot</div>` + row1 + row2 + `<div class="section-title">Trust &amp; coverage</div>` + dq;
}

function renderSales(d) {
  const p = d.pipeline.values, w = d.win_rate.values;
  const kpis = `<div class="grid grid-kpi">
    ${kpi("Open Pipeline", money(p.open_pipeline_value_inr), `${num(p.open_deals)} open deals`, "sales", true)}
    ${kpi("Weighted Pipeline", money(p.weighted_pipeline_value_inr), "Probability-weighted", "target")}
    ${kpi("Win Rate", pct(w.win_rate_pct), `${num(w.won)} won of ${num(w.closed_total)} closed`, "check")}
    ${kpi("Total Deals", num(p.total_deals), `${num(p.won_deals)} won · ${num(p.lost_deals)} lost`, "overview")}
  </div>`;

  const sectors = [...d.sectors].sort((a, b) => (b.open_pipeline_value_inr || 0) - (a.open_pipeline_value_inr || 0));
  const table = `<div class="table-wrap"><table class="data">
    <thead><tr><th>Sector</th><th class="num">Deals</th><th class="num">Win rate</th><th class="num">Open pipeline</th><th class="num">Billed</th></tr></thead>
    <tbody>${sectors.map((s) => `<tr>
      <td>${esc(s.sector)}</td>
      <td class="num">${num(s.deals)}</td>
      <td class="num">${s.win_rate_pct === null ? "—" : pct(s.win_rate_pct)}</td>
      <td class="num">${money(s.open_pipeline_value_inr)}</td>
      <td class="num">${money(s.billed_value_inr)}</td>
    </tr>`).join("")}</tbody></table></div>`;

  const stageRows = [...d.stages].sort((a, b) => b.deals - a.deals);
  const stages = card("Pipeline by stage", "Where deals sit in the funnel", barChart(stageRows, { nameKey: "stage", valueKey: "deals", format: num, variant: "alt" }));

  const notes = (d.pipeline.caveats || []).length
    ? `<div class="notes">${(d.pipeline.caveats || []).slice(0, 2).map((c) => noteRow("dq", "alert", c)).join("")}</div>` : "";

  return kpis + `<div class="section-title">Sector performance</div>` + card("Deals & pipeline by sector", "", table) +
    `<div class="section-title">Funnel</div>` + stages + notes;
}

function renderOperations(d) {
  const ops = d.operations.values;
  const kpis = `<div class="grid grid-kpi">
    ${kpi("Work Orders", num(ops.total_work_orders), "Total in scope", "operations", true)}
    ${kpi("Status Recorded", num(ops.execution_status_recorded), "Execution status present", "check")}
    ${kpi("Not Recorded", num(ops.execution_status_not_recorded), "Awaiting status update", "alert")}
    ${kpi("Sectors", num(new Set(d.sectors.filter((s) => s.work_orders > 0).map((s) => s.sector)).size), "With active work orders", "layers")}
  </div>`;

  const opsRows = d.operations.breakdown;
  const statusCard = card("Execution status", "Includes explicitly unrecorded work orders", barChart(opsRows, { nameKey: "status", valueKey: "work_orders", format: num, variant: "pos" }));

  const sectors = [...d.sectors].filter((s) => s.work_orders > 0).sort((a, b) => b.work_orders - a.work_orders);
  const table = `<div class="table-wrap"><table class="data">
    <thead><tr><th>Sector</th><th class="num">Work orders</th><th class="num">Billed</th><th class="num">Collected</th></tr></thead>
    <tbody>${sectors.map((s) => `<tr>
      <td>${esc(s.sector)}</td><td class="num">${num(s.work_orders)}</td>
      <td class="num">${money(s.billed_value_inr)}</td><td class="num">${money(s.collected_amount_inr)}</td>
    </tr>`).join("")}</tbody></table></div>`;

  const notes = (d.operations.caveats || []).length
    ? `<div class="notes">${d.operations.caveats.slice(0, 2).map((c) => noteRow("dq", "info", c)).join("")}</div>` : "";

  return kpis + `<div class="section-title">Delivery status</div>` + statusCard + notes +
    `<div class="section-title">By sector</div>` + card("Work orders by sector", "", table);
}

function renderFinancials(d) {
  const r = d.revenue.values;
  const kpis = `<div class="grid grid-kpi">
    ${kpi("Order Value", money(r.order_value_inr), "Total incl. GST", "financials", true)}
    ${kpi("Billed", money(r.billed_value_inr), `Billing efficiency ${pct(r.billing_efficiency_pct)}`, "wallet")}
    ${kpi("Collected", money(r.collected_amount_inr), `Collection efficiency ${pct(r.collection_efficiency_pct)}`, "check")}
    ${kpi("Net Receivables", money(r.amount_receivable_inr), "Outstanding", "clock")}
  </div>`;

  const eff = `<div class="grid grid-2">
    ${card("Collection efficiency", "Collected ÷ billed", `<div style="font-size:26px;font-weight:700">${pct(r.collection_efficiency_pct)}</div><div class="meter" style="margin-top:10px"><span style="width:${r.collection_efficiency_pct || 0}%"></span></div>`)}
    ${card("Billing efficiency", "Billed ÷ order value", `<div style="font-size:26px;font-weight:700">${pct(r.billing_efficiency_pct)}</div><div class="meter" style="margin-top:10px"><span style="width:${r.billing_efficiency_pct || 0}%"></span></div>`)}
  </div>`;

  const sectors = [...d.sectors].filter((s) => s.billed_value_inr).sort((a, b) => b.billed_value_inr - a.billed_value_inr);
  const table = `<div class="table-wrap"><table class="data">
    <thead><tr><th>Sector</th><th class="num">Billed</th><th class="num">Collected</th></tr></thead>
    <tbody>${sectors.map((s) => `<tr><td>${esc(s.sector)}</td><td class="num">${money(s.billed_value_inr)}</td><td class="num">${money(s.collected_amount_inr)}</td></tr>`).join("")}</tbody></table></div>`;

  const cav = (d.revenue.caveats || []).concat(d.collections.caveats || []);
  const uniq = [...new Set(cav)].slice(0, 3);
  const notes = uniq.length ? `<div class="notes">${uniq.map((c) => noteRow("dq", "info", c)).join("")}</div>` : "";

  return kpis + `<div class="section-title">Efficiency</div>` + eff +
    `<div class="section-title">Billing by sector</div>` + card("Billed & collected by sector", "", table) + notes;
}

/* ---------- Ask workspace ---------- */
const SUGGESTIONS = [
  "What is our open pipeline?",
  "Which sectors have the strongest pipeline?",
  "What is our win rate in mining?",
  "How are work orders performing?",
  "What is our receivables position?",
];

function renderAsk() {
  const suggestions = SUGGESTIONS.map((s) => `<button class="suggestion" data-q="${esc(s)}">${esc(s)}</button>`).join("");
  return `<div class="ask-hero">
      <h2>Ask about your business</h2>
      <p>Explore pipeline, operations and financial performance using natural-language questions. Every answer is computed from live Monday.com data and can be audited.</p>
      <form class="ask-form" id="ask-form">
        <label class="ask-input">${svg("ask", 17)}<input id="ask-input" placeholder="e.g. Which sectors have the strongest pipeline?" autocomplete="off" /></label>
        <button class="btn btn-primary" type="submit" id="ask-send">Analyse</button>
      </form>
      <div class="suggestions">${suggestions}</div>
    </div>
    <div id="ask-results">${state.ask.map((r) => insightHtml(r.question, r.data)).join("")}</div>`;
}

function methodologyHtml(result) {
  const defs = Object.entries(result.audit || {}).filter(([, v]) => typeof v === "string");
  const figures = Object.entries(result.summary_values || {}).filter(([, v]) => typeof v === "number");
  const defsHtml = defs.length ? `<dl>${defs.map(([k, v]) => `<dt>${esc(humanize(k))}</dt><dd>${esc(v)}</dd>`).join("")}</dl>` : "";
  const figHtml = figures.length ? `<dl>${figures.map(([k, v]) => {
    const val = k.endsWith("_inr") ? money(v) : k.endsWith("_pct") ? pct(v) : num(v);
    return `<dt>${esc(humanize(k))}</dt><dd>${val}</dd>`;
  }).join("")}</dl>` : "";
  const raw = JSON.stringify({ metric: result.metric, summary_values: result.summary_values, audit: result.audit }, null, 2);
  return `<details class="method">
    <summary><span class="chev">${svg("chev", 14)}</span>How this was calculated</summary>
    <div class="method-body">
      ${defsHtml ? `<div class="context" style="margin-bottom:6px">Definitions &amp; assumptions</div>${defsHtml}` : ""}
      ${figHtml ? `<div class="context" style="margin:12px 0 6px">Figures used</div>${figHtml}` : ""}
      <details class="advanced"><summary>Advanced — structured audit</summary><pre>${esc(raw)}</pre></details>
    </div>
  </details>`;
}

function insightHtml(question, data) {
  const label = state.dashboard ? state.dashboard.data_source.label : "Monday.com · Live data";
  if (data.type === "clarification") {
    return `<div class="insight"><div class="q">${svg("ask", 15)}${esc(question)}</div><div class="body">
      <div class="prose">${mdToHtml(humanizeFields(data.answer))}</div></div></div>`;
  }
  if (data.type === "error") {
    return `<div class="insight"><div class="q">${svg("ask", 15)}${esc(question)}</div><div class="body">
      ${noteRow("dq", "alert", data.answer)}</div></div>`;
  }
  const result = data.result;
  const headline = result ? `<div class="headline">${esc(result.title)}</div>` : "";
  const notes = [];
  (data.assumptions || []).forEach((a) => notes.push(noteRow("assume", "info", a)));
  (data.caveats || []).forEach((c) => notes.push(noteRow("dq", "alert", c)));
  const notesHtml = notes.length ? `<div class="notes">${notes.join("")}</div>` : "";
  return `<div class="insight"><div class="q">${svg("ask", 15)}${esc(question)}</div>
    <div class="body">
      ${headline}
      <div class="prose">${mdToHtml(humanizeFields(data.answer))}</div>
      ${notesHtml}
      ${result ? methodologyHtml(result) : ""}
      <div class="src-line">${svg("database", 13)}${esc(label)}</div>
    </div></div>`;
}

async function ask(question) {
  const box = $("ask-results");
  const pending = document.createElement("div");
  pending.className = "insight";
  pending.innerHTML = `<div class="q">${svg("ask", 15)}${esc(question)}</div><div class="body"><div class="typing"><span></span><span></span><span></span></div></div>`;
  box.prepend(pending);
  $("ask-send").disabled = true;
  try {
    const res = await fetch("/api/chat", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ question }) });
    const data = await res.json();
    state.ask.unshift({ question, data });   // persist across navigation
    pending.outerHTML = insightHtml(question, data);
  } catch (e) {
    pending.querySelector(".body").innerHTML = noteRow("dq", "alert", "Could not reach the analysis service. Please try again.");
  } finally {
    const send = $("ask-send"); if (send) send.disabled = false;
  }
}

function wireAsk() {
  const form = $("ask-form");
  if (!form) return;
  form.addEventListener("submit", (e) => {
    e.preventDefault();
    const q = $("ask-input").value.trim();
    if (!q) return;
    $("ask-input").value = "";
    ask(q);
  });
  document.querySelectorAll(".suggestion").forEach((b) => b.addEventListener("click", () => ask(b.dataset.q)));
}

/* ---------- View orchestration ---------- */
function loadingSkeleton() {
  return `<div class="grid grid-kpi">${"<div class='kpi skeleton sk-kpi'></div>".repeat(4)}</div>
    <div class="section-title">&nbsp;</div><div class="grid grid-2"><div class="skeleton sk-card"></div><div class="skeleton sk-card"></div></div>`;
}
function errorState(msg) {
  return `<div class="card"><div class="state">
    ${svg("alert", 30)}
    <h3>Live business data is temporarily unavailable</h3>
    <p>${esc(msg || "The Monday.com data source could not be reached.")}</p>
    <button class="btn btn-primary" id="retry-btn">${svg("refresh", 15)}Retry</button>
  </div></div>`;
}

function renderView() {
  const view = state.view;
  const meta = VIEWS[view] || VIEWS.overview;
  $("page-title").textContent = meta.title;
  $("page-desc").textContent = meta.desc;
  document.querySelectorAll(".nav-item[data-view]").forEach((n) => n.classList.toggle("active", n.dataset.view === view));
  const host = $("view");
  host.focus({ preventScroll: true });

  if (view === "ask") { host.innerHTML = renderAsk(); wireAsk(); return; }

  if (state.loading && !state.dashboard) { host.innerHTML = loadingSkeleton(); return; }
  if (state.error && !state.dashboard) { host.innerHTML = errorState(state.error); const r = $("retry-btn"); if (r) r.onclick = () => loadDashboard(true); return; }
  if (!state.dashboard) { host.innerHTML = loadingSkeleton(); return; }

  const d = state.dashboard;
  const map = { overview: renderOverview, sales: renderSales, operations: renderOperations, financials: renderFinancials };
  host.innerHTML = (map[view] || renderOverview)(d);
}

function setView(view) {
  if (!VIEWS[view]) view = "overview";
  state.view = view;
  if (location.hash !== "#/" + view) history.replaceState(null, "", "#/" + view);
  renderView();
  closeNav();
}

/* ---------- Data + header ---------- */
function paintDataStatus() {
  const h = state.health, ds = state.dashboard ? state.dashboard.data_source : null;
  const live = ds ? ds.live : (h && h.board_config_present && h.monday_configured);
  const dot = $("data-dot"), topDot = $("top-dot");
  dot.className = "dot " + (live ? "live" : "stale");
  topDot.className = "dot " + (live ? "live" : "stale");
  $("top-status-text").textContent = live ? "Live data" : "Data unavailable";
  if (ds) $("data-meta").textContent = `${num(ds.deals_count)} deals · ${num(ds.work_orders_count)} work orders`;
  else if (h) $("data-meta").textContent = live ? "Connected" : "Not configured";
}

async function loadDashboard(force) {
  state.loading = true; state.error = null;
  if (!state.dashboard) renderView();
  const { ok, status, body } = await api("/api/dashboard" + (force ? "?refresh=true" : ""));
  state.loading = false;
  if (!ok) { state.error = body.error || `Service error (${status}).`; }
  else { state.dashboard = body; state.error = null; }
  paintDataStatus();
  // Don't re-render the Ask view — it owns transient query state we'd clobber.
  if (state.view !== "ask") renderView();
}

async function loadHealth() {
  const { ok, body } = await api("/health");
  if (ok) state.health = body;
  paintDataStatus();
}

/* ---------- Navigation / shell ---------- */
function closeNav() { $("app").classList.remove("nav-open"); }
function initShell() {
  // inject icons into static placeholders
  document.querySelectorAll("[data-icon]").forEach((el) => { el.innerHTML = svg(el.dataset.icon, el.classList.contains("brand-mark") ? 19 : 17); });
  $("repo-link").href = REPO_URL;
  $("hamburger").addEventListener("click", () => $("app").classList.toggle("nav-open"));
  $("backdrop").addEventListener("click", closeNav);
  $("refresh-btn").addEventListener("click", () => { if (state.view !== "ask") loadDashboard(true); });
  document.querySelectorAll(".nav-item[data-view]").forEach((n) => n.addEventListener("click", () => setView(n.dataset.view)));
  window.addEventListener("hashchange", () => { const v = (location.hash || "").replace("#/", ""); if (VIEWS[v]) setView(v); });
}

/* ---------- Boot ---------- */
(function boot() {
  initShell();
  const preQuery = new URLSearchParams(location.search).get("q");
  const initial = (location.hash || "").replace("#/", "");
  state.view = preQuery ? "ask" : (VIEWS[initial] ? initial : "overview");
  renderView();
  loadHealth();
  loadDashboard(false);
  if (preQuery) { setView("ask"); ask(preQuery); }   // deep-linkable question
})();
