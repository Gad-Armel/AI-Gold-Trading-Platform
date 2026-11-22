"use strict";
const $ = id => document.getElementById(id);
let snapshot = null, selected = "", points = [], lastPoint = "", currentInstance = "", lastResponseAt = 0;
let candleGeometry = null, hoverIndex = -1;
let controlContext = null, pendingControl = null;
let manualReport = null, manualReceivedAt = 0;
const text = (id, value) => { $(id).textContent = value ?? "—"; };
const number = (value, digits = 2) => typeof value === "number" && Number.isFinite(value) ? value.toLocaleString("en-US", {minimumFractionDigits: digits, maximumFractionDigits: digits}) : "—";
const money = value => `${number(value)} ${snapshot?.currency || "USD"}`;
const calendarUnit = value => {
  const parts = String(value || "").replaceAll("CALENDAR_UNIT_", "").replaceAll("CALENDAR_MULTIPLIER_", "").split(" / ");
  const unit = parts[0] === "PERCENT" ? "%" : parts[0] === "NONE" ? "" : (parts[0] || "").toLowerCase().replaceAll("_", " ");
  const scale = parts[1] && parts[1] !== "NONE" ? parts[1].toLowerCase() : "";
  return [scale, unit].filter(Boolean).join(" ") || "units";
};
const tint = (node, value) => { node.classList.remove("positive", "negative"); if (typeof value === "number") node.classList.add(value < 0 ? "negative" : "positive"); };
const badge = (id, label, state = "") => { text(id, label); $(id).className = `pill ${state}`; };
const cell = (row, value, className = "") => { const node = document.createElement("td"); node.textContent = value ?? "—"; node.className = className; row.append(node); return node; };
function ownerCell(row, item) { const node = cell(row, item.ticket); const label = document.createElement("small"); label.textContent = item.owned ? "Scalper Expert / EA" : "Other / manual"; node.append(label); }
function table(id, items, columns, empty, render) {
  const body = $(id), fragment = document.createDocumentFragment();
  for (const item of items) { const row = document.createElement("tr"); render(row, item); fragment.append(row); }
  if (!items.length) { const row = document.createElement("tr"), node = cell(row, empty, "empty"); node.colSpan = columns; fragment.append(row); }
  body.replaceChildren(fragment);
}
function renderPositions(items) {
  text("open-count", items.length);
  table("positions", items, 11, "No open account positions.", (row, p) => {
    ownerCell(row, p); cell(row, p.symbol); cell(row, p.side, p.side === "BUY" ? "positive" : "negative");
    cell(row, number(p.volume)); cell(row, number(p.open)); cell(row, number(p.current));
    cell(row, p.sl > 0 ? number(p.sl) : "None", p.sl > 0 ? "" : "negative"); cell(row, p.tp > 0 ? number(p.tp) : "Dynamic exit");
    tint(cell(row, money(p.pnl)), p.pnl); cell(row, p.owned && snapshot?.scalp?.enabled ? (p.guard_armed ? `Peak ${money(p.net_peak)} / exit floor ${money(p.profit_floor)}` : "Building net profit") : "--"); cell(row, p.time);
  });
}
function renderDeals(items) {
  table("deals", items, 9, snapshot?.history_ready ? "No executions in the available history window." : "Execution history is unavailable.", (row, d) => {
    cell(row, d.time); ownerCell(row, d); cell(row, d.symbol); cell(row, d.side, d.side === "BUY" ? "positive" : "negative");
    cell(row, String(d.entry || "").replace("DEAL_ENTRY_", "")); cell(row, number(d.volume)); cell(row, number(d.price));
    tint(cell(row, money(d.net)), d.net); cell(row, String(d.reason || "").replace("DEAL_REASON_", ""));
  });
  $("export").disabled = !items.length;
}
function renderEvents(items) {
  const fragment = document.createDocumentFragment();
  for (const event of items) {
    const li = document.createElement("li"), when = document.createElement("time"), kind = document.createElement("span"), value = document.createElement("span");
    when.textContent = event.time; kind.className = "tag"; kind.textContent = event.kind; value.textContent = event.text;
    li.append(when, kind, value); fragment.append(li);
  }
  if (!items.length) { const li = document.createElement("li"); li.className = "empty"; li.textContent = "No events received yet."; fragment.append(li); }
  $("events").replaceChildren(fragment);
}
function setManualList(id, items, empty) {
  const list = $(id), fragment = document.createDocumentFragment();
  for (const value of (items || []).slice(0, 20)) {
    const item = document.createElement("li"); item.textContent = String(value).slice(0, 500); fragment.append(item);
  }
  if (!items?.length) { const item = document.createElement("li"); item.className = "empty"; item.textContent = empty; fragment.append(item); }
  list.replaceChildren(fragment);
}
function renderManualScalp(data) {
  manualReport = data; manualReceivedAt = Date.now();
  const report = data.report, state = data.state;
  const live = state === "live" && report;
  const stateLabel = state === "live" ? "FRESH · MANUAL ONLY" : state === "stale" ? "STALE / EXPIRED" : state === "error" ? "REPORT INVALID" : "WAITING FOR REPORT";
  badge("manual-signal-state", stateLabel, live ? "green" : state === "waiting" ? "amber" : "red");
  $("manual-signal-action").textContent = live ? report.action : "WAIT";
  $("manual-signal-action").className = live ? report.action.toLowerCase() : "";
  text("manual-signal-bias", live ? `${report.bias} · XAUUSD` : report?.action ? `Last report: ${report.action} · not current` : data.message);
  text("manual-signal-age", Number.isFinite(data.age_seconds) ? `Report age ${number(data.age_seconds, 1)}s` : "No report age available");
  const reports = report?.reports || {};
  const score = report?.directional_evidence_score;
  text("manual-score", typeof score === "number" ? `${number(score, 1)} / 100` : "—");
  $("manual-score-bar").style.width = `${typeof score === "number" ? Math.max(0, Math.min(100, score)) : 0}%`;
  text("manual-candle", reports.candle_action ? `${reports.candle_action} · ${number(reports.candle_score, 1)}/100` : "—");
  text("manual-tick", reports.tick_action ? `${reports.tick_action} · ${number(reports.tick_score, 1)}/100` : "—");
  text("manual-agreement", reports.candle_action && reports.tick_action
    ? reports.candle_action === reports.tick_action ? "Agree · 2/2" : "Disagree"
    : "—");
  const quote = report?.quote;
  text("manual-quote", quote ? `${number(quote.bid, 2)} / ${number(quote.ask, 2)} · ${number(quote.spread, 3)}` : "—");
  const expiry = report?.valid_until ? Date.parse(report.valid_until) : NaN;
  if (Number.isFinite(expiry)) {
    const remaining = Math.ceil((expiry - (data.server_time * 1000 + Date.now() - manualReceivedAt)) / 1000);
    text("manual-expiry", `${new Date(expiry).toLocaleTimeString()} · ${remaining > 0 && live ? `${remaining}s left` : "expired / not current"}`);
  } else text("manual-expiry", "—");
  const levels = report?.scenario_levels;
  text("manual-rr", typeof report?.scenario_reward_to_risk === "number" ? `${number(report.scenario_reward_to_risk)} : 1 (scenario)` : "—");
  text("manual-entry", levels?.entry_zone ? `${number(levels.entry_zone[0], 2)} – ${number(levels.entry_zone[1], 2)} · ref ${number(levels.entry_reference, 2)}` : "—");
  text("manual-stop", levels ? number(levels.sl, 2) : "—");
  text("manual-targets", levels ? `${number(levels.tp1, 2)} / ${number(levels.tp2, 2)} / ${number(levels.tp3, 2)}` : "—");
  setManualList("manual-reasons", report?.reasons, data.message);
  setManualList("manual-blocks", report?.blocks, state === "live" && report?.action !== "WAIT" ? "No current gates are blocking the advisory. This is not a guarantee." : data.message);
}
async function pollManualScalp() {
  try {
    const response = await fetch("/api/manual-scalp", {cache: "no-store", signal: AbortSignal.timeout(4000)});
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    renderManualScalp(await response.json());
  } catch (error) {
    renderManualScalp({state:"error", message:`Manual scalp report unavailable: ${error.message}`, report:null, age_seconds:null});
  } finally { setTimeout(pollManualScalp, document.hidden ? 3000 : 1000); }
}
function canvasContext(id) {
  const canvas = $(id), rect = canvas.getBoundingClientRect(), scale = window.devicePixelRatio || 1;
  canvas.width = Math.round(rect.width * scale); canvas.height = Math.round(rect.height * scale);
  const ctx = canvas.getContext("2d"); ctx.scale(scale, scale); ctx.font = "10px Segoe UI";
  return {canvas, ctx, w: rect.width, h: rect.height};
}
function blankChart(ctx, w, h, message) { ctx.fillStyle = "#91a0b4"; ctx.textAlign = "center"; ctx.fillText(message, w / 2, h / 2); }
function brokerClock(seconds) { return new Date(seconds * 1000).toISOString().slice(11, 16); }
function drawCandles() {
  const {ctx, w, h} = canvasContext("candles"), bars = (snapshot?.candles || []).slice(-Number($("range").value));
  candleGeometry = null;
  if (!bars.length) { blankChart(ctx, w, h, "Waiting for M1 broker candles"); return; }
  const left = 18, right = w - 78, top = 35, bottom = h - 28;
  let lo = Math.min(...bars.map(b => b.low)), hi = Math.max(...bars.map(b => b.high));
  const padding = Math.max((hi - lo) * .10, .1); lo -= padding; hi += padding;
  const y = value => bottom - (value - lo) / (hi - lo) * (bottom - top), step = (right - left) / bars.length;
  ctx.textAlign = "left";
  for (let i = 0; i <= 4; i++) {
    const value = lo + (hi - lo) * i / 4, py = y(value);
    ctx.strokeStyle = "#24303f"; ctx.beginPath(); ctx.moveTo(left, py); ctx.lineTo(right, py); ctx.stroke();
    ctx.fillStyle = "#91a0b4"; ctx.fillText(number(value), right + 7, py + 3);
  }
  bars.forEach((b, i) => {
    const x = left + (i + .5) * step, color = b.close >= b.open ? "#56d6aa" : "#ff8189";
    ctx.strokeStyle = color; ctx.fillStyle = color; ctx.beginPath(); ctx.moveTo(x, y(b.high)); ctx.lineTo(x, y(b.low)); ctx.stroke();
    ctx.fillRect(x - Math.max(1, step * .62) / 2, Math.min(y(b.open), y(b.close)), Math.max(1, step * .62), Math.max(1, Math.abs(y(b.open) - y(b.close))));
    if (i % Math.max(1, Math.floor(bars.length / 5)) === 0) { ctx.fillStyle = "#91a0b4"; ctx.fillText(brokerClock(b.time), x - 12, h - 9); }
  });
  function level(value, color, label) {
    if (typeof value !== "number" || value < lo || value > hi) return;
    const py = y(value); ctx.strokeStyle = color; ctx.setLineDash([4, 4]); ctx.beginPath(); ctx.moveTo(left, py); ctx.lineTo(right, py); ctx.stroke(); ctx.setLineDash([]);
    ctx.fillStyle = "#131a24"; ctx.fillRect(left, py - 12, Math.min(235, label.length * 6 + 8), 13);
    ctx.fillStyle = color; ctx.fillText(label, left + 3, py - 2);
  }
  for (const p of (snapshot.positions || []).filter(p => p.symbol === snapshot.symbol).slice(0, 10)) {
    level(p.open, "#e4bd72", `${p.side} #${p.ticket} · ${number(p.open)}`);
    if (p.sl > 0) level(p.sl, "#ff8189", `SL #${p.ticket} · ${number(p.sl)}`);
    if (p.tp > 0) level(p.tp, "#56d6aa", `TP #${p.ticket} · ${number(p.tp)}`);
  }
  level(snapshot.market?.bid, "#a4b5cb", `BID ${number(snapshot.market?.bid)}`);
  const index = hoverIndex >= 0 ? Math.min(hoverIndex, bars.length - 1) : bars.length - 1, b = bars[index];
  ctx.fillStyle = "#b5c2d2"; ctx.fillText(`${brokerClock(b.time)}  O ${number(b.open)}  H ${number(b.high)}  L ${number(b.low)}  C ${number(b.close)}`, left, 18);
  if (hoverIndex >= 0) { const x = left + (index + .5) * step; ctx.strokeStyle = "#7e8ea5"; ctx.setLineDash([2, 3]); ctx.beginPath(); ctx.moveTo(x, top); ctx.lineTo(x, bottom); ctx.stroke(); ctx.setLineDash([]); }
  candleGeometry = {left, step, count: bars.length};
}
function drawEquity() {
  const {ctx, w, h} = canvasContext("equity-chart");
  if (!points.length) { blankChart(ctx, w, h, "Equity samples appear when the EA is connected"); return; }
  const values = points.map(p => p.value), min = Math.min(...values), max = Math.max(...values), pad = Math.max((max - min) * .15, .1);
  const x = p => 22 + (p.time - points[0].time) / Math.max(1000, points.at(-1).time - points[0].time) * (w - 105);
  const y = p => h - 30 - (p.value - min + pad) / (max - min + 2 * pad) * (h - 55);
  ctx.strokeStyle = "#e4bd72"; ctx.lineWidth = 1.8; ctx.beginPath();
  points.forEach((p, i) => { if (!i || p.time - points[i - 1].time > 6000) ctx.moveTo(x(p), y(p)); else ctx.lineTo(x(p), y(p)); }); ctx.stroke();
  const last = points.at(-1); ctx.fillStyle = "#e4bd72"; ctx.beginPath(); ctx.arc(x(last), y(last), 3, 0, Math.PI * 2); ctx.fill();
  ctx.fillText(number(last.value), w - 73, y(last) + 3); ctx.fillStyle = "#91a0b4";
  ctx.fillText(new Date(points[0].time).toLocaleTimeString(), 22, h - 9);
}
function clearData() {
  $("macro-panel").hidden = true;
  $("safety-lock").hidden = true;
  controlContext = null; $("pause-trading").disabled = true; $("close-all").disabled = true; $("reset-session").disabled = true;
  snapshot = null; points = []; lastPoint = ""; currentInstance = ""; $("scalp-policy").hidden = true;
  for (const id of ["equity", "balance", "floating", "positions-count", "day", "week", "winrate", "pf", "bid", "ask", "spread", "spread-mean", "volatility", "flow", "mtf", "session", "news", "advisor", "risk-summary", "risk-trade", "risk-total", "margin", "drawdown", "execution", "learning", "candle-time", "clock"]) text(id, "—");
  text("identity", "Native EA dashboard · Local connection · Demo controls"); text("decision", "Waiting for the native EA…");
  badge("mode", "—"); badge("risk-state", "—"); badge("quote-health", "WAITING FOR QUOTES", "amber");
  table("positions", [], 11, "Waiting for position data.", () => {}); table("deals", [], 9, "Waiting for execution history.", () => {});
  text("open-count", "—"); $("export").disabled = true; renderEvents([]); drawCandles(); drawEquity();
}
function render(response) {
  lastResponseAt = Date.now();
  const blockers = [...(response.snapshot?.blockers || [])];
  if (/^REQUIS \/ WAIT\b/.test(response.snapshot?.filters?.advisor || "")) blockers.push("Advisor 1: WAIT (no approved entry signal)");
  $("blocker-panel").hidden = !blockers.length && !response.support;
  text("blocker-heading", blockers.length ? "Entry filters currently blocking:" : response.snapshot ? "No listed environment block. See the live decision for signal and risk checks." : "Feed support");
  $("blocker-panel").className = blockers.length ? "notice" : "notice live";
  $("blockers").replaceChildren(...blockers.map(value => { const item = document.createElement("li"); item.textContent = value; return item; }));
  text("support-health", response.support ? `Advisor 1 transport: ${response.support.advisor}${response.support.report_age_seconds != null ? ' · original report age ' + response.support.report_age_seconds + 's' : ''}` : "");
  const options = response.sources || [], select = $("source");
  if (JSON.stringify(options) !== select.dataset.sources) {
    select.replaceChildren(new Option(options.length ? "Choose an account feed" : "Waiting for an EA feed", ""));
    for (const name of options) select.add(new Option(name.replace("dashboard_GS_ACCOUNT_", "").replace(".json", ""), name));
    select.dataset.sources = JSON.stringify(options);
  }
  if (response.source) selected = response.source; select.value = selected;
  $("notice").className = `notice ${response.state}`; text("notice", response.message);
  badge("heartbeat", response.state.toUpperCase() + (response.age_seconds != null ? ` · ${response.age_seconds}s` : ""), response.state === "live" ? "green" : response.state === "waiting" || response.state === "choose" ? "amber" : "red");
  $("setup").hidden = !!response.snapshot;
  if (!response.snapshot) { clearData(); return; }
  snapshot = response.snapshot;
  const macro = snapshot.macro;
  $("macro-panel").hidden = !macro;
  if (macro) {
    const fresh = response.state === "live" && macro.fresh;
    badge("macro-health", fresh ? "LIVE CALENDAR" : "STALE / UNAVAILABLE", fresh ? "green" : "amber");
    text("macro-context", `USD releases over the previous/next 24 hours. Observed response evidence: ${number(snapshot.scalp?.macro_bonus,1)}. ${macro.observed_response_since ? "Local response observation started " + macro.observed_response_since + " (server time)." : "No recent release response baseline; no directional macro bonus."}`);
    table("macro-events", macro.events || [], 6, "No calendar details available.", (row,e) => {cell(row,e.time);cell(row,e.name);cell(row,e.actual);cell(row,e.forecast);cell(row,e.previous);cell(row,calendarUnit(e.unit));});
  }
  $("safety-lock").hidden = !snapshot.locked;
  if (snapshot.locked) {
    const seconds = snapshot.risk?.lock_remaining_seconds;
    if (snapshot.risk?.manual_reset_required) {
      text("safety-lock", "Loss limit reached. Waiting for a manual loss-session reset after all positions and pending requests are cleared.");
    } else if (response.state === "live" && Number.isFinite(seconds) && seconds > 0) {
      const remaining = Math.max(0, Math.ceil(seconds - (response.age_seconds || 0)));
      const duration = `${Math.floor(remaining/3600)}h ${Math.floor(remaining%3600/60)}m ${remaining%60}s`;
      const ends = new Date(Date.now()+remaining*1000).toLocaleString();
      text("safety-lock", `Protection après pertes : ${duration} restantes. Fin prévue : ${ends} (${Intl.DateTimeFormat().resolvedOptions().timeZone}). Analyse active ; les entrées reprendront automatiquement si les contrôles de sécurité et les signaux le permettent.`);
    } else text("safety-lock", `Protection active au dernier relevé. Échéance MT5 : ${snapshot.risk?.locked_until || "indisponible"}. Attente d'un état à jour pour le compte à rebours.`);
  }
  const controls = snapshot.controls || {};
  const controlReady = response.state === "live" && controls.enabled && response.control_token;
  controlContext = controlReady ? {source:response.source, instance:controls.instance, token:response.control_token} : null;
  $("pause-trading").textContent = snapshot.paused ? "Resume entries" : "Pause entries";
  if (pendingControl) {
    if (pendingControl.source !== response.source || pendingControl.instance !== controls.instance) {
      text("control-feedback", "Account or EA instance changed. Previous command is not considered confirmed."); pendingControl = null;
    } else if (controls.last_id === pendingControl.id) {
      text("control-feedback", "MT5 last command: " + controls.result); pendingControl = null;
    } else if (Date.now()/1000 > pendingControl.expires + 2) {
      text("control-feedback", "Command expired without acknowledgement. Check MT5; no automatic retry was sent."); pendingControl = null;
    }
  } else if (!controlReady) text("control-feedback", "Controls unavailable: require a fresh Scalper Expert 3.10 feed with browser controls enabled.");
  else if (controls.liquidating) text("control-feedback", "MT5 is closing account positions/orders. Entries remain paused.");
  else if (controls.last_id) text("control-feedback", "MT5 last command: " + controls.result);
  else text("control-feedback", "Controls connected to this demo account. No command pending.");
  $("pause-trading").disabled = !controlReady || !!pendingControl || (snapshot.paused && (snapshot.locked || controls.liquidating));
  $("reset-session").disabled = !controlReady || !!pendingControl || controls.can_reset !== true;
  $("close-all").disabled = !controlReady || !controls.can_execute || !!pendingControl || controls.liquidating;
  const a = snapshot.account, k = snapshot.kpi, m = snapshot.market, f = snapshot.filters, r = snapshot.risk;
  text("identity", `${snapshot.symbol} · ${snapshot.server} · Account ${snapshot.login} · EA ${snapshot.version}`);
  text("symbol", `${snapshot.symbol} / M1`); text("clock", `${snapshot.server_time} · server`);
  text("equity", money(a.equity)); text("balance", `Balance ${money(a.balance)}`); text("floating", money(a.floating)); tint($("floating"), a.floating);
  text("positions-count", `${a.position_count} positions / ${r.max_positions} max · ${a.pending_count} pending orders`);
  text("day", k.day); text("week", `This week ${k.week}`); text("winrate", k.win_rate); text("pf", `Profit factor ${k.profit_factor}`);
  text("bid", number(m.bid)); text("ask", `Ask ${number(m.ask)}`); text("candle-time", `Next M1 ${m.candle_seconds}s`);
  const quoteOk = response.state === "live" && m.quote_age_ms >= 0 && m.quote_age_ms <= 2000;
  badge("quote-health", quoteOk ? "LIVE QUOTES" : "QUOTES STALE / UNAVAILABLE", quoteOk ? "green" : "red");
  badge("mode", snapshot.mode || "STOPPED", snapshot.locked ? "red" : snapshot.paused ? "amber" : ""); text("decision", snapshot.status);
  text("spread", `${number(m.spread, 3)} / ${number(m.spread_max, 3)}`); $("spread").className = m.spread_state === 2 ? "negative" : m.spread_state === 1 ? "amber-text" : "positive";
  text("spread-mean", number(m.spread_mean, 3)); text("volatility", `${m.atr} / ${m.volume}`);
  text("flow", m.flow); for (const id of ["mtf", "session", "news", "advisor"]) text(id, f[id]);
  badge("risk-state", response.state !== "live" ? "LAST SNAPSHOT" : snapshot.locked ? "SAFETY LOCK" : snapshot.paused ? "ENTRIES PAUSED" : "MONITORING", response.state !== "live" ? "amber" : snapshot.locked ? "red" : snapshot.paused ? "amber" : "green");
  text("risk-summary", r.text); text("risk-trade", money(r.per_trade)); text("risk-total", money(r.aggregate)); text("margin", money(a.margin_free));
  if (Number.isFinite(r.rolling_remaining)) $("risk-summary").textContent += ` | Loss-session realized (up to 24h) ${money(r.rolling_realized)} | Remaining before stop reservations ${money(r.rolling_remaining)} / limit ${money(r.rolling_limit)} | Loss streak ${r.loss_streak} | Cooldown ${r.cooldown_seconds}s | Entries/hour ${r.entries_hour}/${r.entries_hour_max}`;
  text("drawdown", k.drawdown); text("execution", snapshot.execution); text("learning", snapshot.learning);
  $("scalp-policy").hidden = !snapshot.scalp?.enabled;
  if (snapshot.scalp?.enabled) {
    const policy = snapshot.scalp;
    text("scalp-summary", `Last evaluated evidence ${number(policy.score,1)} / required ${number(policy.threshold,1)} | Active session: ${policy.session} | Peak net-profit giveback: ${number(policy.giveback_fraction*100,0)}% with noise allowance`);
    if (policy.analysis) $("scalp-summary").textContent += ` | ${policy.entry_lane || "Scalp"} | Live signal analysis: ${policy.analysis}`;
    if (Number.isFinite(policy.confirmation_samples)) $("scalp-summary").textContent += ` | Confirmation: ${policy.confirmation_samples} sampled quotes / ${policy.confirmation_age_ms} ms | Neutral grace: ${policy.confirmation_grace ? "250 ms" : "off"} | Counterflow guard: ${policy.counterflow_guard ? "on" : "off"}`;
    text("micro-diagnostics", `State: ${policy.rotation || "SCANNING"} | Quote velocity: ${number(policy.velocity,3)} $/s | Acceleration score: ${number(policy.acceleration_bonus,2)} | ATR / 60-bar range: ${number(policy.atr_ratio,2)}x | Sample rate: ${number(policy.sample_rate,1)}/s (max 10, not exchange volume)`);
    text("execution-diagnostics", policy.ack_samples ? `Broker acknowledgement EWMA: ${number(policy.ack_ewma_ms,0)} ms | Max: ${number(policy.ack_max_ms,0)} ms | Latest signed fill slippage: ${number(policy.fill_slippage,3)} (positive = worse fill)` : "Broker acknowledgement / fill slippage: awaiting executed requests.");
    table("scalp-sessions", policy.sessions || [], 5, "Waiting for session outcomes.", (row, s) => {
      cell(row,s.name); cell(row,s.closed); tint(cell(row,money(s.net)),s.net); cell(row,s.adjustment > 0 ? `+${s.adjustment} (more selective)` : s.adjustment < 0 ? `${s.adjustment} (less selective)` : "0 / unchanged"); cell(row,s.closed < 20 ? `${s.closed}/20 minimum observations` : s.adjustment === 0 ? "Uncertain / neutral" : "Adapting from completed outcomes");
    });
  }
  renderPositions(snapshot.positions); renderDeals(snapshot.deals); renderEvents(snapshot.events);
  if (currentInstance !== snapshot.instance) { points = []; lastPoint = ""; currentInstance = snapshot.instance; }
  if (response.state === "live" && typeof a.equity === "number" && lastPoint !== snapshot.server_time) {
    points.push({time: Date.now(), value: a.equity}); if (points.length > 3600) points.shift(); lastPoint = snapshot.server_time;
  }
  drawCandles(); drawEquity();
}
async function poll() {
  const requestSource = selected, controller = new AbortController(), timeout = setTimeout(() => controller.abort(), 4000);
  try {
    const response = await fetch(`/api/status?source=${encodeURIComponent(requestSource)}`, {cache: "no-store", signal: controller.signal});
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    const data = await response.json(); if (requestSource === selected) render(data);
  } catch (error) {
    $("notice").className = "notice error"; text("notice", `Dashboard connection lost. Displayed values are no longer live. ${error.message}`);
    controlContext = null; $("pause-trading").disabled = true; $("close-all").disabled = true; $("reset-session").disabled = true;
    if (snapshot?.locked) text("safety-lock", "Connexion perdue : échéance de protection non vérifiée. Le dernier compte à rebours n'est plus en direct.");
    badge("heartbeat", "DASHBOARD OFFLINE", "red"); badge("quote-health", "QUOTES UNVERIFIED", "red");
  } finally { clearTimeout(timeout); setTimeout(poll, document.hidden ? 3000 : 1000); }
}
$("source").addEventListener("change", () => { selected = $("source").value; clearData(); badge("heartbeat", "CONNECTING", "amber"); });
$("range").addEventListener("change", drawCandles); window.addEventListener("resize", () => { drawCandles(); drawEquity(); });
$("candles").addEventListener("pointermove", event => { if (!candleGeometry) return; hoverIndex = Math.max(0, Math.min(candleGeometry.count - 1, Math.floor((event.offsetX - candleGeometry.left) / candleGeometry.step))); drawCandles(); });
$("candles").addEventListener("pointerleave", () => { hoverIndex = -1; drawCandles(); });
$("export").addEventListener("click", () => {
  if (!snapshot?.deals.length) return;
  const keys = ["time", "ticket", "position", "symbol", "owned", "side", "entry", "volume", "price", "net", "reason", "comment"];
  const csvCell = value => { let s = String(value ?? ""); if (typeof value === "string" && /^[=+@\-\t\r]/.test(s)) s = "'" + s; return '"' + s.replaceAll('"', '""') + '"'; };
  const csv = [keys.join(","), ...snapshot.deals.map(d => keys.map(k => csvCell(d[k])).join(","))].join("\r\n");
  const url = URL.createObjectURL(new Blob(["\ufeff" + csv], {type: "text/csv;charset=utf-8"})), a = document.createElement("a");
  a.href = url; a.download = "GoldScalp-executions.csv"; a.click(); setTimeout(() => URL.revokeObjectURL(url), 1000);
});
document.addEventListener("visibilitychange", () => { if (!document.hidden && Date.now() - lastResponseAt > 5000) { badge("heartbeat", "RECONNECTING", "amber"); badge("quote-health", "QUOTES UNVERIFIED", "red"); } });
drawCandles(); drawEquity(); poll(); pollManualScalp();

async function sendControl(action) {
  if (!controlContext || pendingControl || !snapshot) return;
  const context = {...controlContext};
  if (action === "reset_session" && !window.confirm(`Start a new $50 loss session on demo account ${snapshot.login}? This clears the loss counter, loss streak and safety pause and resumes entries. Broker trade history and daily results are preserved.`)) return;
  if (action === "close_all" && !window.confirm(`Close ALL positions and cancel ALL pending orders on demo account ${snapshot.login}? This includes manual trades and other symbols. Entries will remain paused.`)) return;
  $("pause-trading").disabled = true; $("close-all").disabled = true; $("reset-session").disabled = true;
  text("control-feedback", "Sending command to the local MT5 mailbox...");
  // Guard against another click while the HTTP response is pending.
  pendingControl = {...context, id:"sending", expires:Date.now()/1000+12};
  try {
    const response = await fetch("/api/control", {method:"POST", headers:{"Content-Type":"application/json", "X-Gold-Control":context.token},
      body:JSON.stringify({source:context.source, instance:context.instance, action}), signal:AbortSignal.timeout(4000)});
    if (!response.ok) throw new Error(await response.text());
    const reply = await response.json(); pendingControl = {...reply, source:context.source, instance:context.instance};
    text("control-feedback", "Queued. Waiting for the native EA acknowledgement...");
  } catch(error) {
    pendingControl = null; text("control-feedback", `Command not confirmed: ${error.message}. No automatic retry.`);
  }
}
$("pause-trading").addEventListener("click", () => sendControl(snapshot?.paused ? "resume" : "pause"));
$("reset-session").addEventListener("click", () => sendControl("reset_session"));
$("close-all").addEventListener("click", () => sendControl("close_all"));
