"use strict";

const $ = (id) => document.getElementById(id);
const messages = $("messages");

// --- tiny, safe markdown-ish renderer (bold, bullets, line breaks) ---
function esc(s) {
  return String(s).replace(/[&<>]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;" }[c]));
}
function mdToHtml(text) {
  const lines = esc(text).split("\n");
  let html = "", inList = false;
  for (let raw of lines) {
    let line = raw.replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>")
                  .replace(/\*(.+?)\*/g, "<em>$1</em>");
    if (/^\s*[-•]\s+/.test(raw)) {
      if (!inList) { html += "<ul>"; inList = true; }
      html += "<li>" + line.replace(/^\s*[-•]\s+/, "") + "</li>";
    } else {
      if (inList) { html += "</ul>"; inList = false; }
      if (line.trim() === "") html += "";
      else html += "<p>" + line + "</p>";
    }
  }
  if (inList) html += "</ul>";
  return html;
}

function fmtINR(v) {
  if (v === null || v === undefined) return "n/a";
  const a = Math.abs(v), s = v < 0 ? "-" : "";
  if (a >= 1e7) return `${s}₹${(a / 1e7).toFixed(2)} Cr`;
  if (a >= 1e5) return `${s}₹${(a / 1e5).toFixed(2)} L`;
  return `${s}₹${Math.round(a).toLocaleString("en-IN")}`;
}

function addMessage(role, html) {
  const msg = document.createElement("div");
  msg.className = "msg " + role;
  msg.innerHTML = `<div class="bubble">${html}</div>`;
  messages.appendChild(msg);
  messages.scrollTop = messages.scrollHeight;
  return msg;
}

function renderAnswer(data) {
  let html = mdToHtml(data.answer || "");

  const tags = [];
  (data.assumptions || []).forEach((a) => tags.push(`<span class="tag assume">📌 ${esc(a)}</span>`));
  (data.caveats || []).forEach((c) => tags.push(`<span class="tag caveat">⚠️ ${esc(c)}</span>`));
  if (tags.length) html += `<div class="tag-row">${tags.join("")}</div>`;

  if (data.result) {
    const audit = {
      metric: data.result.metric,
      summary_values: data.result.summary_values,
      audit: data.result.audit,
    };
    html += `<details class="audit"><summary>🔍 How this was computed (auditable)</summary>
      <pre>${esc(JSON.stringify(audit, null, 2))}</pre></details>`;
  }
  if (data.data_source) {
    const ds = data.data_source;
    html += `<div class="src">Source: ${esc(ds.source || "monday")}` +
      (ds.monday_account ? ` · ${esc(ds.monday_account)}` : "") +
      (ds.age_seconds !== undefined ? ` · cache age ${ds.age_seconds}s` : "") + `</div>`;
  }
  return html;
}

async function ask(question) {
  addMessage("user", `<p>${esc(question)}</p>`);
  const thinking = addMessage("agent", `<span class="typing"><span></span><span></span><span></span></span>`);
  $("send").disabled = true;
  try {
    const res = await fetch("/api/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ question }),
    });
    const data = await res.json();
    thinking.querySelector(".bubble").innerHTML = renderAnswer(data);
  } catch (e) {
    thinking.querySelector(".bubble").innerHTML =
      `<p>⚠️ Something went wrong reaching the server. Please try again.</p>`;
  } finally {
    $("send").disabled = false;
    messages.scrollTop = messages.scrollHeight;
  }
}

// --- dashboard ---
async function loadHealth() {
  try {
    const h = await (await fetch("/health")).json();
    const src = $("pill-source");
    if (h.board_config_present && h.monday_configured) {
      src.textContent = "● live monday data"; src.className = "pill ok";
    } else {
      src.textContent = "● data not configured"; src.className = "pill warn";
    }
    const llm = $("pill-llm");
    llm.textContent = "AI: " + (h.llm_provider || (h.llm_enabled ? "on" : "deterministic"));
    llm.className = "pill" + (h.llm_enabled ? " ok" : "");
  } catch {}
}

async function loadOverview() {
  try {
    const res = await fetch("/api/overview");
    if (!res.ok) {
      $("kpis").innerHTML = `<div class="qnote">Live data unavailable — run ingestion & set token.</div>`;
      return;
    }
    const o = await res.json();
    const p = o.pipeline || {}, r = o.revenue || {};
    $("kpis").innerHTML = [
      ["Open pipeline", fmtINR(p.open_pipeline_value_inr)],
      ["Open deals", p.open_deals ?? "–"],
      ["Billed", fmtINR(r.billed_value_inr)],
      ["Collected", fmtINR(r.collected_amount_inr)],
    ].map(([l, v]) => `<div class="kpi"><div class="v">${v}</div><div class="l">${l}</div></div>`).join("");

    $("sectors").innerHTML = (o.sectors || []).slice(0, 6).map((s) =>
      `<div class="sector-row"><b>${esc(s.sector)}</b>
        <span class="amt">${fmtINR(s.billed_value_inr)}</span></div>`).join("")
      || `<div class="loading">No sector data.</div>`;

    const dq = o.quality || {};
    const q = [];
    for (const [board, rep] of Object.entries(dq)) {
      q.push(`<div><b>${board.replace("_", " ")}</b>: ${rep.clean_count} records` +
        (rep.duplicates_removed ? `, ${rep.duplicates_removed} dup removed` : "") + `</div>`);
      const cov = rep.coverage || {};
      const key = board === "deals" ? "deal_value" : "collected_amount";
      if (cov[key] !== undefined) {
        q.push(`<div class="qbar"><span>${key} ${cov[key]}%</span>
          <span class="track"><span class="fill" style="width:${cov[key]}%"></span></span></div>`);
      }
    }
    $("quality").innerHTML = q.join("") || `<div class="loading">…</div>`;
  } catch {
    $("kpis").innerHTML = `<div class="qnote">Could not load overview.</div>`;
  }
}

async function loadExamples() {
  try {
    const { examples } = await (await fetch("/api/examples")).json();
    $("examples").innerHTML = examples.map((q) =>
      `<span class="chip">${esc(q)}</span>`).join("");
    document.querySelectorAll(".chip").forEach((c) =>
      c.addEventListener("click", () => { $("input").value = c.textContent; ask(c.textContent); }));
  } catch {}
}

$("composer").addEventListener("submit", (e) => {
  e.preventDefault();
  const q = $("input").value.trim();
  if (!q) return;
  $("input").value = "";
  ask(q);
});

loadHealth();
loadOverview();
loadExamples();
