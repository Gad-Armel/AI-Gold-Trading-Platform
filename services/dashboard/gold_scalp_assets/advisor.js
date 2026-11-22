"use strict";
const el = id => document.getElementById(id);
const names = ["SCALP", "INTRADAY", "SWING"];
const fmt = (v, digits = 2) => typeof v === "number" && Number.isFinite(v) ? v.toFixed(digits) : "--";
const local = value => new Date(value).toLocaleString(undefined, {year:"numeric", month:"2-digit", day:"2-digit", hour:"2-digit", minute:"2-digit", second:"2-digit", hour12:false});
const text = (tag, value, cls) => { const n = document.createElement(tag); n.textContent = value; if (cls) n.className = cls; return n; };
const tone = value => value === "BUY" ? "green" : value === "SELL" ? "red" : "amber";
const badge = value => text("span", value, "pill " + tone(value));
const list = items => { const n = document.createElement("ul"); items.forEach(s => n.append(text("li", s))); return n; };
let state = null;
let receivedAt = 0;
function render() {
  el("clock").textContent = new Date().toLocaleTimeString();
  if (!state) return;
  // Elapsed monotonic time prevents a browser clock adjustment from reviving old advice.
  const now = state.server_time * 1000 + performance.now() - receivedAt;
  const r = state.report;
  const age = r ? (now - Date.parse(r.generated_at)) / 1000 : null;
  const fresh = state.state === "live" && age >= -5 && age <= 90;
  el("heartbeat").textContent = fresh ? "LIVE ANALYSIS" : state.state === "live" ? "STALE" : state.state.toUpperCase();
  el("heartbeat").className = "pill " + (fresh ? "green" : "amber");
  el("notice").className = "notice " + (fresh ? "live" : "stale");
  el("notice").textContent = !fresh && state.state === "live" ? "Report is stale. Last analysis only; awaiting a fresh Advisor 1 report." : state.message;
  el("report").hidden = !r;
  el("support").textContent = state.support?.advisor || "Reading the original Advisor 1 report.";
  if (!r) return;
  el("decision-label").textContent = fresh ? "ADVISOR DECISION" : "LAST REPORTED DECISION / NOT A LIVE SIGNAL";
  el("decision").textContent = r.overall === "WAIT" ? "WAIT - NO ENTRY" : r.overall + " SETUP AVAILABLE";
  el("market").textContent = `${r.symbol} | Bid ${fmt(r.bid)} | Ask ${fmt(r.ask)} | Spread $${fmt(r.spread)} | Session ${r.session || "--"}`;
  el("analyzed").textContent = "Analysis completed: " + local(r.generated_at);
  el("age").textContent = `Report age: ${Math.max(0, Math.floor(age))} seconds | Page checks every 2 seconds`;
  const offset = -new Date(r.generated_at).getTimezoneOffset();
  el("timezone").textContent = `${Intl.DateTimeFormat().resolvedOptions().timeZone} / UTC${offset >= 0 ? "+" : "-"}${String(Math.floor(Math.abs(offset)/60)).padStart(2,"0")}:${String(Math.abs(offset)%60).padStart(2,"0")}`;
  el("horizons").replaceChildren(); el("details").replaceChildren();
  const allBlocks = new Set();
  let actionable = false;
  names.forEach(name => {
    const h = r.horizons[name], expired = now >= Date.parse(h.valid_until), reviewDue = now >= Date.parse(h.review_at);
    const tr = document.createElement("tr");
    [name, h.action, h.bias, `${fmt(h.directional_score, 1)}/100`, `${h.valid_for_minutes} min`].forEach((value,i) => {
      const td = document.createElement("td"); td.append(i === 1 || i === 2 ? badge(value) : text("span", value)); tr.append(td);
    });
    const windowCell = text("td", local(r.generated_at)); windowCell.append(text("small", "to " + local(h.valid_until))); tr.append(windowCell);
    const reviewCell = text("td", local(h.review_at)); if(reviewDue) reviewCell.append(text("small", "Review due", "amber-text")); tr.append(reviewCell);
    tr.append(text("td", expired ? "EXPIRED" : !fresh ? "STALE REPORT" : reviewDue ? "REVIEW DUE" : "WITHIN WINDOW", expired || !fresh ? "expired" : ""));
    el("horizons").append(tr);
    h.blocks.forEach(b => allBlocks.add(b));
    const card = text("article", "", "panel horizon-card"); card.append(text("h3", name + " / " + h.action));
    card.append(text("p", "Timeframes: " + (h.supporting_timeframes || []).join(" / ")));
    card.append(list(h.reasons));
    if(h.blocks.length) { card.append(text("p", "Entry blockers", "blocked")); card.append(list(h.blocks)); }
    if(h.action === "BUY" || h.action === "SELL") {
      actionable = true;
      card.append(text("p", fresh && !expired && !reviewDue ? "Advisory levels / not an executed trade" : "Historical levels / refresh required", "blocked"));
      const dl = document.createElement("dl"), levels = h.levels;
      [["Entry zone", levels.entry_zone.map(v => fmt(v)).join(" - ")], ["Stop loss", fmt(levels.sl)], ["TP1 / TP2 / TP3", [levels.tp1, levels.tp2, levels.tp3].map(v => fmt(v)).join(" / ")]].forEach(([label,value]) => {
        const row = document.createElement("div"); row.append(text("dt",label), text("dd",value)); dl.append(row);
      }); card.append(dl);
    }
    el("details").append(card);
  });
  el("why-title").textContent = actionable ? "ENTRY CONDITIONS BY HORIZON" : "WHY THERE IS NO ENTRY";
  el("blocks").replaceChildren(...Array.from(allBlocks, b => text("li", b)));
  if(!allBlocks.size) el("blocks").append(text("li", actionable ? "No explicit entry blockers in this report. See each horizon's evidence and validity." : "The report provides no explicit blocker. The advisor decision remains WAIT."));
  const biases = new Set(names.map(n => r.horizons[n].bias));
  el("bias-note").textContent = !actionable && biases.size === 1 && !biases.has("WAIT") ? `Trend bias is ${[...biases][0]}, but entry conditions are not met. Do not chase the move.` : "After a validity window expires, the advisory must be recalculated.";
  el("timeframes").replaceChildren();
  Object.entries(r.views || {}).forEach(([name,v]) => { const tr = document.createElement("tr"); [name, v.direction, fmt(v.strength,3), fmt(v.atr,3), fmt(v.last_close)].forEach(s => tr.append(text("td",s))); el("timeframes").append(tr); });
  const c = r.verified_context || {};
  el("context").replaceChildren();
  [["Data status",c.status], ["Trend / regime",`${c.trend_direction || "--"} / ${c.trend_regime || "--"}`], ["Relative tick volume",fmt(c.relative_tick_volume)], ["Rolling VWAP",fmt(c.rolling_vwap)], ["ADX M5",fmt(c.adx_m5)], ["Liquidity regime",c.liquidity_regime]].forEach(([key,value]) => {
    const row = document.createElement("div"); row.append(text("dt",key), text("dd",value ?? "--")); el("context").append(row);
  });
  el("proxy-note").textContent = c.proxy_disclaimer || "Context is taken from the same Advisor 1 report.";
}
async function poll() {
  try {
    const response = await fetch("/api/advisor", {cache:"no-store", signal:AbortSignal.timeout(5000)});
    if(!response.ok) throw new Error("HTTP " + response.status);
    state = await response.json(); receivedAt = performance.now();
  } catch(error) {
    if(state) { state.state = "disconnected"; state.message = "Dashboard connection lost. Values below are the last received analysis."; }
    else { state = {state:"disconnected", message:"Cannot connect to the dashboard. Keep its PowerShell process running.", server_time:Date.now()/1000}; receivedAt = performance.now(); }
  }
  render(); setTimeout(poll, 2000);
}
setInterval(render,1000); poll();
