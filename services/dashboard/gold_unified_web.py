"""Unified read-only command center for the project's Gold dashboards.

This server only combines existing validated readers. It does not calculate
advisor signals or submit orders.
"""
from __future__ import annotations

import json
import os
import secrets
import time
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

from services.dashboard.gold_advisor_web import read_advisor
from services.dashboard.gold_manual_scalp_web import read_manual_scalp
from services.dashboard.gold_scalp_web import default_feed_directory, read_status
from services.dashboard.gold_consensus_web import read_dashboard_status
from services.dashboard.gold_scalp_controls import ControlMailbox, ControlConflict


ROOT = Path(__file__).resolve().parents[2]
VFINAL_STATUS = ROOT / "vfinal" / "data" / "runtime" / "vfinal_demo_status.json"
CONFIG_PATH = ROOT / "data" / "runtime" / "gold_unified_config.json"
EQUITY_HISTORY: dict[str, list[dict]] = {}
LIVE_ACCOUNT_CACHE: dict[str, object] = {"checked_at": 0.0, "value": {}}


def read_live_mt5_account() -> dict:
    """Small read-only account fallback for the browser dashboard.

    The trading engine remains the only order sender. This reader is cached so
    normal browser refreshes do not add a terminal call on every request.
    """
    now = time.time()
    cached = LIVE_ACCOUNT_CACHE.get("value")
    if now - float(LIVE_ACCOUNT_CACHE.get("checked_at", 0.0)) < 2.0 and isinstance(cached, dict):
        return dict(cached)
    snapshot: dict = {}
    try:
        import MetaTrader5 as mt5
        if mt5.initialize():
            account = mt5.account_info()
            positions = mt5.positions_get(symbol="XAUUSD")
            if account is not None:
                snapshot = {
                    "login": int(getattr(account, "login", 0) or 0),
                    "server": str(getattr(account, "server", "") or ""),
                    "currency": str(getattr(account, "currency", "") or ""),
                    "balance": float(getattr(account, "balance", 0.0) or 0.0),
                    "equity": float(getattr(account, "equity", 0.0) or 0.0),
                    "floating": float(getattr(account, "profit", 0.0) or 0.0),
                    "margin_free": float(getattr(account, "margin_free", 0.0) or 0.0),
                    "position_count": len(positions or ()),
                    "updated_at": datetime.now(timezone.utc).isoformat(),
                }
        mt5.shutdown()
    except Exception:
        snapshot = dict(cached) if isinstance(cached, dict) else {}
    LIVE_ACCOUNT_CACHE["checked_at"] = now
    if snapshot:
        LIVE_ACCOUNT_CACHE["value"] = snapshot
    return snapshot


def _compact_consensus_status(status: dict) -> dict:
    """Keep the browser payload small and limited to live desk information.

    The engine status also contains research experiments and raw evidence trees.
    Those can be several megabytes over time and made the browser request time
    out even though MT5 and the trading loop were healthy.
    """
    keep = ("status", "status_message", "state", "message", "age_seconds", "updated_at", "updated_local", "mode", "cycle",
            "account", "pnl", "positions", "market", "market_health", "tick_history_health",
            "phase_timings_ms", "loop_elapsed_ms", "history_refresh_ms", "previous_status_write_ms",
            "config", "paper_trading", "learned_policy_mode", "account_fingerprint")
    result = {key: status.get(key) for key in keep if key in status}
    lanes = {}
    for name, source in (status.get("lanes") or {}).items():
        if not isinstance(source, dict):
            continue
        raw_decision = dict(source.get("decision") or {})
        decision_keys = ("horizon", "direction", "dominant_bias", "evidence", "entry_threshold",
                         "entry_timeframe", "allowed", "blocks", "reasons", "signal_band",
                         "entry_mode", "levels", "news_block", "news_policy")
        decision = {key: raw_decision.get(key) for key in decision_keys if key in raw_decision}
        raw_exit = dict(source.get("adaptive_exit") or {})
        exit_keys = ("close", "reason", "policy", "profit_r", "peak_r", "giveback_distance",
                     "breakeven_price", "trailing_stop")
        exit_info = {key: raw_exit.get(key) for key in exit_keys if key in raw_exit}
        raw_market = dict(source.get("adaptive_market") or {})
        market_keys = ("available", "reason", "atr", "trend", "momentum", "regime", "bar_id")
        raw_flow = dict(source.get("micro_flow") or {})
        flow_keys = ("available", "reason", "bias", "direction", "pressure", "reversal_risk")
        raw_conscience = dict(source.get("conscience") or {})
        conscience_keys = ("available", "conviction", "coverage", "alignment", "reason")
        lanes[name] = {
            "decision": decision,
            "positions": list(source.get("positions") or []),
            "closed_trades": list(source.get("closed_trades") or [])[:30],
            "exit_policy": source.get("exit_policy"),
            "adaptive_exit": exit_info,
            "adaptive_market": {key: raw_market.get(key) for key in market_keys if key in raw_market},
            "micro_flow": {key: raw_flow.get(key) for key in flow_keys if key in raw_flow},
            "conscience": {key: raw_conscience.get(key) for key in conscience_keys if key in raw_conscience},
            "risk_unit_usd": source.get("risk_unit_usd"),
            "entry_mode": source.get("entry_mode"),
            "exit_frame": source.get("exit_frame"),
            "entry_timing_ready": source.get("entry_timing_ready"),
            "entry_timing_blocks": list(source.get("entry_timing_blocks") or [])[:12],
            "signal_age_seconds": source.get("signal_age_seconds"),
            "signal_age_required_seconds": source.get("signal_age_required_seconds"),
            "max_positions": source.get("max_positions"),
            "entries_last_hour": source.get("entries_last_hour"),
            "consecutive_losses": source.get("consecutive_losses"),
        }
    result["lanes"] = lanes
    return result


def _compact_native_status(native: dict) -> dict:
    """Avoid serving a historical native-EA export as a multi-megabyte API."""
    result = {key: native.get(key) for key in ("state", "message", "source", "sources") if key in native}
    snapshot = dict(native.get("snapshot") or {})
    if not snapshot:
        return result
    keep = ("schema", "version", "strategy", "symbol", "server", "login", "currency", "connected",
            "stopped", "mode", "paused", "locked", "status", "execution", "learning", "account",
            "kpi", "market", "filters", "risk", "controls", "blockers", "events")
    compact = {key: snapshot.get(key) for key in keep if key in snapshot}
    compact["positions"] = list(snapshot.get("positions") or [])[:10]
    compact["deals"] = list(snapshot.get("deals") or [])[:30]
    compact["candles"] = list(snapshot.get("candles") or [])[-120:]
    result["snapshot"] = compact
    return result


def _compact_advisor_status(advisor: dict) -> dict:
    result = {key: advisor.get(key) for key in ("state", "message", "age_seconds") if key in advisor}
    report = advisor.get("report")
    if not isinstance(report, dict):
        result["report"] = None
        return result
    compact = {key: report.get(key) for key in ("generated_at", "symbol", "bid", "ask", "spread", "session",
                                                  "overall", "actionable_horizons") if key in report}
    horizons = {}
    for name, horizon in (report.get("horizons") or {}).items():
        if isinstance(horizon, dict):
            keys = ("action", "bias", "directional_score", "review_at", "valid_until", "valid_for_minutes",
                    "reasons", "blocks", "levels", "supporting_timeframes", "votes")
            horizons[name] = {key: horizon.get(key) for key in keys if key in horizon}
    compact["horizons"] = horizons
    result["report"] = compact
    return result


HTML = r"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Gold Unified Command Center</title>
<style>
:root{color-scheme:dark;--bg:#090b10;--panel:#151922;--panel2:#10141d;--line:#2a3140;--gold:#e7b85a;--text:#edf0f7;--muted:#9ba5b7;--good:#62c994;--warn:#f0b54a;--bad:#ef7a7a}*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--text);font-family:Segoe UI,Arial,sans-serif}.top{position:sticky;top:0;z-index:10;display:flex;align-items:center;justify-content:space-between;padding:14px 20px;background:#0d1017;border-bottom:1px solid var(--line)}.brand{display:flex;gap:12px;align-items:center}.mark{width:38px;height:38px;border:1px solid var(--gold);border-radius:50%;display:grid;place-items:center;color:#171109;background:var(--gold);font-weight:800}.brand strong{font-size:18px}.brand small{display:block;color:var(--muted)}.tabs{display:flex;gap:6px;flex-wrap:wrap}.tabs button{border:1px solid var(--line);background:var(--panel2);color:var(--text);padding:9px 12px;border-radius:8px;cursor:pointer}.tabs button.active{border-color:var(--gold);color:var(--gold)}.tools{display:flex;gap:8px;align-items:center}.tools select,.tools button{border:1px solid var(--line);background:var(--panel);color:var(--text);border-radius:7px;padding:7px}main{max-width:1500px;margin:auto;padding:18px}.view{display:none}.view.active{display:block}.grid{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:12px}.grid3{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:12px}.panel{background:var(--panel);border:1px solid var(--line);border-radius:12px;padding:14px;min-width:0}.panel h2,.panel h3{margin:0 0 10px}.metric{font-size:28px;font-weight:700}.muted{color:var(--muted)}.pill{display:inline-block;padding:4px 8px;border-radius:999px;border:1px solid var(--line);font-size:12px}.live{color:var(--good);border-color:#376a51}.stale,.waiting{color:var(--warn);border-color:#756130}.error,.stopped{color:var(--bad);border-color:#7a4141}.table{width:100%;border-collapse:collapse}.table th,.table td{padding:8px;border-bottom:1px solid var(--line);text-align:left}.table th{color:var(--muted);font-size:12px}.reason{white-space:pre-wrap;color:#d7dbea}.banner{border:1px solid #5a4a27;background:#241d12;border-radius:10px;padding:12px;margin-bottom:12px}.compact .panel{padding:9px}.compact .metric{font-size:22px}pre{white-space:pre-wrap;overflow:auto}.controls{display:flex;gap:8px;flex-wrap:wrap}.controls button{border:1px solid var(--line);background:#1d2230;color:var(--text);border-radius:8px;padding:8px 10px;cursor:pointer}@media(max-width:1000px){.grid,.grid3{grid-template-columns:1fr 1fr}.top{align-items:flex-start}.tabs{justify-content:flex-end}}@media(max-width:650px){.grid,.grid3{grid-template-columns:1fr}.top{display:block}.tools{margin-top:10px}}
.chart-wrap{height:360px}.chart-wrap canvas{width:100%;height:100%;display:block}.position-table{max-height:260px;overflow:auto}.table.negative{color:var(--bad)}.positive{color:var(--good)}.negative{color:var(--bad)}.control-strip{display:flex;gap:8px;flex-wrap:wrap}.control-strip button{border:1px solid var(--line);background:var(--panel2);color:var(--text);padding:8px 10px;border-radius:8px}.control-strip .danger{border-color:#7a4141;color:#ff9c9c}.config-ok{color:var(--good)}.config-blocked{color:var(--warn)}
.schedule-bar{display:flex;align-items:end;gap:12px;flex-wrap:wrap;background:var(--panel2);border:1px solid var(--line);border-radius:10px;padding:10px 12px;margin-bottom:12px}.schedule-bar label{display:grid;gap:4px;color:var(--muted);font-size:12px}.schedule-bar select{border:1px solid var(--line);background:var(--panel);color:var(--text);border-radius:7px;padding:7px}.schedule-bar select:disabled{opacity:.55}
.top{display:grid;grid-template-columns:minmax(230px,auto) minmax(0,1fr);grid-template-areas:"brand tools" "tabs tabs";column-gap:20px;row-gap:12px;padding:16px 24px}.brand{grid-area:brand}.tabs{grid-area:tabs;border-top:1px solid var(--line);padding-top:10px}.tools{grid-area:tools;justify-content:flex-end;flex-wrap:wrap}.tools label{display:grid;gap:4px;font-size:11px}.tools label .muted{white-space:nowrap}main{max-width:1600px;padding:24px}.grid,.grid3{gap:16px}.panel{padding:18px}.metric{font-size:30px;letter-spacing:-.03em}.banner{line-height:1.6}.schedule-bar{padding:14px 16px;margin-bottom:16px;gap:16px}.schedule-bar label{font-size:12px}.session-card{display:grid;grid-template-columns:minmax(160px,.9fr) repeat(3,minmax(0,1fr));align-items:center;gap:14px;border:1px solid var(--line);border-left:4px solid var(--good);background:linear-gradient(110deg,#161c24,#11151d);border-radius:12px;padding:16px 20px;margin:14px 0 18px}.session-card.closed{border-left-color:var(--warn)}.session-card.unknown,.session-card.urgent{border-left-color:var(--bad)}.session-card small{display:block;color:var(--muted);margin-bottom:5px}.session-card strong{display:block;font-size:15px}.session-card h2{margin:0;font-size:18px}.session-card .session-detail{color:var(--muted);font-size:13px;line-height:1.45}.session-card .session-status{color:var(--text)}.position-grid{grid-template-columns:minmax(0,1.2fr) minmax(0,1.2fr) minmax(260px,.8fr)}.advanced-grid details summary{cursor:pointer;font-weight:650;margin-bottom:8px}.advanced-grid details[open] summary{margin-bottom:14px}.advanced-grid pre{max-height:300px}@media(max-width:1050px){.top{grid-template-columns:1fr;grid-template-areas:"brand" "tools" "tabs"}.tools{justify-content:flex-start}.session-card{grid-template-columns:repeat(2,minmax(0,1fr))}.position-grid{grid-template-columns:1fr 1fr}}@media(max-width:650px){.top{display:grid;padding:12px}.tools{justify-content:flex-start}.tools label{min-width:calc(50% - 8px)}main{padding:14px}.session-card,.position-grid{grid-template-columns:1fr}.session-card{gap:10px;padding:14px}.schedule-bar{align-items:stretch}.schedule-bar label{min-width:calc(50% - 8px)}}
/* Aurum Command Center */
:root{--bg:#060a12;--panel:#0e1726;--panel2:#0a1321;--line:rgba(150,178,215,.18);--gold:#ffd27b;--accent:#63ddff;--text:#edf5ff;--muted:#91a2ba;--good:#60e2b0;--warn:#ffd27b;--bad:#ff718b}
body{background:radial-gradient(900px 500px at 78% -12%,rgba(36,111,163,.22),transparent 68%),radial-gradient(700px 520px at -8% 38%,rgba(184,134,46,.12),transparent 70%),var(--bg);background-attachment:fixed}
.top{background:rgba(6,10,18,.84);backdrop-filter:blur(18px);border-bottom-color:var(--line);box-shadow:0 12px 36px rgba(0,0,0,.24)}
.brand strong{letter-spacing:.09em;text-transform:uppercase}.brand small{font-size:10px;letter-spacing:.13em;text-transform:uppercase}
.mark{border:1px solid rgba(255,210,123,.7);box-shadow:0 0 24px rgba(255,210,123,.2)}
.mode-lock{display:inline-flex;align-items:center;gap:7px;padding:7px 10px;border:1px solid rgba(96,226,176,.3);border-radius:999px;background:rgba(96,226,176,.08);color:var(--good);font-size:10px;font-weight:800;letter-spacing:.12em;white-space:nowrap}
.mode-lock:before{content:"";width:6px;height:6px;border-radius:50%;background:currentColor;box-shadow:0 0 10px currentColor}
.tabs{border-color:var(--line)}.tabs button{border-color:transparent;border-radius:999px;background:transparent;color:var(--muted);transition:background .18s ease,color .18s ease,border-color .18s ease}
.tabs button:hover{color:var(--text);background:rgba(255,255,255,.045)}.tabs button.active{border-color:rgba(99,221,255,.24);background:rgba(99,221,255,.09);color:var(--accent)}
.tools select,.tools button,.schedule-bar select{border-color:var(--line);border-radius:9px;background:rgba(12,21,35,.92);transition:border-color .18s ease,box-shadow .18s ease}
.tools select:focus,.tools button:focus-visible,.schedule-bar select:focus{outline:none;border-color:var(--accent);box-shadow:0 0 0 3px rgba(99,221,255,.12)}
.tools button,#apply-config{cursor:pointer}.tools button:hover,#apply-config:hover{border-color:rgba(99,221,255,.45);color:var(--accent)}
main{max-width:1680px;padding:22px clamp(14px,3vw,40px)}
.panel{border-color:var(--line);background:linear-gradient(145deg,rgba(17,29,47,.94),rgba(10,17,29,.94));box-shadow:0 12px 32px rgba(0,0,0,.16);transition:border-color .18s ease,transform .18s ease}
.panel:hover{border-color:rgba(99,221,255,.24);transform:translateY(-1px)}
.panel h2,.panel h3{letter-spacing:.015em}.metric{font-variant-numeric:tabular-nums;letter-spacing:-.04em}
.banner{border-color:var(--line);background:linear-gradient(110deg,rgba(13,26,43,.96),rgba(11,17,29,.94));box-shadow:0 12px 32px rgba(0,0,0,.16);padding:14px 18px}
.status-rail{display:flex;align-items:center;justify-content:space-between;gap:14px;flex-wrap:wrap}.status-main,.status-meta{display:flex;align-items:center;gap:12px;flex-wrap:wrap}.status-meta{color:var(--muted);font-size:12px}.status-market{color:var(--accent);font-weight:700}.status-config{color:var(--muted)}
.config-drawer{margin:0 0 14px;border:1px solid var(--line);border-radius:12px;background:rgba(10,18,31,.82);overflow:hidden}
.config-drawer>summary{display:flex;align-items:center;justify-content:space-between;gap:12px;padding:12px 16px;cursor:pointer;list-style:none;font-size:13px;font-weight:700;letter-spacing:.03em}
.config-drawer>summary::-webkit-details-marker{display:none}.config-drawer>summary:after{content:"+";color:var(--accent);font-size:18px}.config-drawer[open]>summary:after{content:"−"}
.config-drawer .tools{grid-area:auto;justify-content:flex-start;padding:12px 16px;border-bottom:1px solid var(--line)}
.config-drawer .schedule-bar{margin:0;border:0;border-top:1px solid var(--line);border-radius:0;background:transparent}
.top.compact-top{grid-template-columns:1fr;grid-template-areas:"brand" "tabs"}
.static-setting{display:inline-flex;align-items:center;padding:8px 11px;border:1px solid var(--line);border-radius:9px;background:rgba(12,21,35,.7);color:var(--text);font-size:12px;font-weight:700;white-space:nowrap}
.session-card{border-color:var(--line);background:linear-gradient(115deg,rgba(17,31,49,.97),rgba(9,17,29,.96));box-shadow:0 16px 40px rgba(0,0,0,.2)}
.control-strip button{cursor:pointer;transition:border-color .18s ease,color .18s ease,background .18s ease}.control-strip button:hover:not(:disabled){border-color:rgba(99,221,255,.4);color:var(--accent)}button:disabled,select:disabled{cursor:not-allowed;opacity:.55}
.table th{letter-spacing:.08em;text-transform:uppercase}.pill{border-radius:999px}
.session-card.session-unavailable{display:flex;align-items:center;gap:12px;min-height:64px;padding:12px 18px;border-left-color:var(--warn)}
.session-unavailable strong{color:var(--warn)}.session-unavailable span{color:var(--muted);font-size:13px}
.advisor-stack{display:grid;grid-template-columns:1fr;gap:18px}.advisor-horizon{padding:24px;border-left:5px solid var(--warn)}.advisor-horizon.buy{border-left-color:var(--good)}.advisor-horizon.sell{border-left-color:var(--bad)}.advisor-head{display:flex;align-items:center;justify-content:space-between;gap:18px;flex-wrap:wrap}.advisor-name{font-size:24px;font-weight:800;letter-spacing:.08em}.advisor-action{font-size:34px;font-weight:900;letter-spacing:.04em}.confidence-row{display:grid;grid-template-columns:170px 1fr 84px;align-items:center;gap:14px;margin:18px 0}.confidence-track{height:16px;border-radius:999px;background:#1d2a3c;overflow:hidden}.confidence-track i{display:block;height:100%;border-radius:inherit}.confidence-number{text-align:right;font-size:20px;font-weight:800;font-variant-numeric:tabular-nums}.advisor-details{display:grid;grid-template-columns:1fr 1fr;gap:12px;margin-top:14px}.advisor-detail{border:1px solid var(--line);background:rgba(5,12,22,.45);border-radius:10px;padding:12px}.advisor-detail strong{display:block;margin-bottom:5px}.price-levels{display:flex;flex-wrap:wrap;gap:8px;margin-top:14px}.price-level{padding:8px 11px;border:1px solid var(--line);background:rgba(12,23,39,.85);border-radius:8px;font-variant-numeric:tabular-nums}.price-level b{color:var(--accent);margin-right:6px}@media(max-width:700px){.confidence-row{grid-template-columns:1fr}.confidence-number{text-align:left}.advisor-details{grid-template-columns:1fr}.advisor-horizon{padding:16px}.advisor-action{font-size:28px}}
@media(max-width:760px){.top{padding:12px;row-gap:10px}.brand{flex-wrap:wrap}.mode-lock{margin-left:50px}.status-meta{width:100%}.config-drawer>summary{align-items:flex-start}.config-drawer>summary .drawer-note{max-width:70%;text-align:right}}
@media(prefers-reduced-motion:reduce){*,*:before,*:after{scroll-behavior:auto!important;transition:none!important}}
</style>
</head>
<body>
<header class="top"><div class="brand"><div class="mark">Au</div><div><strong>Gold Unified Command Center</strong><small>Native EA · Consensus · Advisor 1 · Manual · V-FINAL</small></div></div><div class="tabs" id="tabs"></div><div class="tools"><label><span class="muted">Instrument</span><select id="instrument"><option value="XAUUSD" selected>XAUUSD</option></select></label><label><span class="muted">Mode</span><select id="trade-mode"><option value="observe">Observe</option><option value="demo" selected>MT5 demo</option></select></label><label><span class="muted">Requested timeframe</span><select id="chart-timeframe"><option value="M1" selected>M1</option><option value="M5">M5</option></select></label><button id="apply-config">Apply selection</button><label><span class="muted">Refresh</span><select id="interval"><option value="1">1s</option><option value="3" selected>3s</option><option value="10">10s</option><option value="30">30s</option></select></label><button id="density">Compact</button></div></header>
<main>
<div class="schedule-bar"><label>New-entry schedule (UTC)<select id="schedule-mode"><option value="all_day">Use EA gates only</option><option value="exclude_window">Exclude one UTC interval</option></select></label><label>Block from<select id="blocked-start-utc"></select></label><label>Until (exclusive)<select id="blocked-end-utc"></select></label><span class="muted">22:00–23:00 blocks the 22nd hour only; risk, news, and broker-session gates still apply.</span></div>
<div class="banner" id="overview">Connecting to local Gold engines…</div>
<section class="view active" id="view-overview"></section>
<section class="view" id="view-native"></section>
<section class="view" id="view-consensus"></section>
<section class="view" id="view-advisor"></section>
<section class="view" id="view-manual"></section>
<section class="view" id="view-vfinal"></section>
<section class="view" id="view-system"></section>
</main>
<script>
const $=id=>document.getElementById(id);
const esc=v=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const num=(v,d=2)=>v===null||v===undefined||Number.isNaN(+v)?'—':Number(v).toFixed(d);
const money=v=>v===null||v===undefined?'—':`${Number(v)>=0?'$':'-$'}${Math.abs(Number(v)).toFixed(2)}`;
const stateClass=s=>['live','running','stale','waiting','error','stopped'].includes(s)?s:'waiting';
let unifiedControlToken="",equityHistory=[],unifiedNative=null;
let appliedConfigSignature="";
document.title='Aurum | Gold Demo Desk';
document.querySelector('.brand strong').textContent='Aurum Gold Desk';
document.querySelector('.brand small').textContent='XAUUSD · MT5 · AI execution';
const tabs=[['overview','Overview'],['native','Main AI'],['consensus','Consensus'],['advisor','Advisor'],['manual','Manual'],['vfinal','V-Final'],['system','System']];
tabs.forEach(([key,label])=>{const b=document.createElement('button');b.textContent=label;b.dataset.view=key;b.onclick=()=>show(key);$('tabs').appendChild(b)});
const instrumentSelect=$('instrument'),instrumentBadge=document.createElement('span');instrumentBadge.className='static-setting';instrumentBadge.textContent='XAUUSD';instrumentSelect.parentElement.replaceWith(instrumentBadge);
const timeframeSelect=$('chart-timeframe'),timeframeBadge=document.createElement('span');timeframeBadge.className='static-setting';timeframeBadge.textContent='Native analysis · M1';timeframeSelect.parentElement.replaceWith(timeframeBadge);
const modeSelect=$('trade-mode');
modeSelect.previousElementSibling.textContent='Execution';
const liveOption=document.createElement('option');liveOption.value='live';liveOption.textContent='Live · locked (separate account)';liveOption.disabled=true;modeSelect.appendChild(liveOption);
const demoBadge=document.createElement('span');demoBadge.className='mode-lock';demoBadge.textContent='DEMO ONLY';document.querySelector('.brand').appendChild(demoBadge);
const scheduleBar=document.querySelector('.schedule-bar');
scheduleBar.querySelector('.muted').textContent='UTC entry block. Weekend hours follow MT5 broker time; the expected Fri 22:00–Sun 23:00 window is not hardcoded.';
const settingsDrawer=document.createElement('details');settingsDrawer.className='config-drawer';
const settingsSummary=document.createElement('summary');settingsSummary.innerHTML='<span>Trading settings</span><span class="drawer-note muted">XAUUSD · demo only · Live locked</span>';
settingsDrawer.appendChild(settingsSummary);settingsDrawer.appendChild(document.querySelector('.tools'));settingsDrawer.appendChild(scheduleBar);
document.querySelector('.top').classList.add('compact-top');
document.querySelector('main').insertBefore(settingsDrawer,$('overview'));
function show(key){document.querySelectorAll('.view').forEach(v=>v.classList.toggle('active',v.id==='view-'+key));document.querySelectorAll('.tabs button').forEach(b=>b.classList.toggle('active',b.dataset.view===key));localStorage.setItem('goldUnifiedView',key)}
function panel(title,body,extra=''){return `<article class="panel ${extra}"><h2>${esc(title)}</h2>${body}</article>`}
function card(label,value,detail='',kind=''){return panel(label,`<div class="metric">${esc(value)}</div><div class="muted">${esc(detail)}</div>`,kind)}
function state(name,s){return `<span class="pill ${stateClass(s.state)}">${esc(name)} · ${esc(s.state||'waiting')}</span>`}
function showJson(v){return `<pre>${esc(JSON.stringify(v,null,2))}</pre>`}
function advisorHorizonCard(name,h){
 const score=Number(h.directional_score),confidence=Number.isFinite(score)?Math.max(0,Math.min(100,score)):0;
 const action=h.action||'WAIT',bias=h.bias||'WAIT',tone=action==='BUY'?'buy':action==='SELL'?'sell':'';
 const levels=h.levels||{},reasons=[...(h.reasons||[]),...(h.blocks||[])];
 const color=action==='BUY'?'var(--good)':action==='SELL'?'var(--bad)':'var(--warn)';
 const entry=Array.isArray(levels.entry_zone)?levels.entry_zone.map(v=>num(v)).join(' – '):num(levels.entry_reference);
 const levelChips=Object.keys(levels).length?`<div class="price-levels"><span class="price-level"><b>ENTRY</b>${entry}</span><span class="price-level"><b>SL</b>${num(levels.sl)}</span><span class="price-level"><b>TP1</b>${num(levels.tp1)}</span><span class="price-level"><b>TP2</b>${num(levels.tp2)}</span><span class="price-level"><b>TP3</b>${num(levels.tp3)}</span></div>`:'<div class="muted" style="margin-top:14px">No actionable price levels for this horizon.</div>';
 return `<article class="panel advisor-horizon ${tone}"><div class="advisor-head"><div><div class="advisor-name">${esc(name)}</div><div class="muted">${esc((h.supporting_timeframes||[]).join(' · ')||'Movement analysis')}</div></div><div class="advisor-action ${tone}">${esc(action)} <span class="muted" style="font-size:16px">${esc(bias)} bias</span></div></div><div class="confidence-row"><strong>CONFIDENCE</strong><div class="confidence-track"><i style="width:${confidence}%;background:${color}"></i></div><div class="confidence-number">${num(confidence,1)}%</div></div><div class="advisor-details"><div class="advisor-detail"><strong>Why</strong>${esc(reasons.join(' · ')||'No additional movement confirmation reported.')}</div><div class="advisor-detail"><strong>Timing</strong><div>Valid until: ${esc(h.valid_until||'—')}</div><div>Next review: ${esc(h.review_at||'—')}</div></div></div>${levelChips}</article>`;
}
function consensusLaneCard(name,lane){
 const decision=lane.decision||{},exit=lane.adaptive_exit||{},flow=lane.micro_flow||{},levels=decision.levels||{};
 const positions=Array.isArray(lane.positions)?lane.positions:[],blocks=[...(decision.blocks||[]),...(lane.entry_timing_blocks||[])];
 const ready=decision.allowed===true&&lane.entry_timing_ready!==false;
 const exitSummary=exit.close===true?'Exit condition triggered':positions.length?'Managing open position':'No open position';
 const exitDetail=[exit.reason,exit.profit_r!=null?`${num(exit.profit_r)}R open`:null,exit.peak_r!=null?`${num(exit.peak_r)}R peak`:null].filter(Boolean).join(' · ');
 const flowDetail=flow.available?`${flow.bias||flow.direction||'Flow available'} · pressure ${num(flow.pressure)} · reversal risk ${num(flow.reversal_risk)}`:(flow.reason||'Tick-flow context unavailable');
 return `<article class="panel consensus-lane"><div class="status-rail"><h2>${esc(name)} · ${esc(decision.dominant_bias||decision.direction||'WAIT')}</h2><span class="pill ${ready?'running':'stale'}">${ready?'Entry conditions met':'Entry blocked / confirming'}</span></div><div class="muted">${esc(lane.entry_mode||decision.entry_mode||'')} · ${esc(decision.entry_timeframe||'M1')} · ${positions.length}/${num(lane.max_positions??decision.source_position_limit??0,0)} positions · ${num(decision.evidence)}/100 evidence</div><div class="grid3" style="margin-top:12px"><div><strong>Entry gate</strong><div>${esc(blocks.length?blocks.join(' · '):ready?'All reported entry gates pass.':'Waiting for stable, confirmed entry conditions.')}</div><div class="muted">Stop ${num(decision.stop_loss??levels.sl)} · TP1 ${num(levels.tp1)} · TP2 ${num(levels.tp2)} · TP3 ${num(levels.tp3)}</div><div class="muted">Signal age ${num(lane.signal_age_seconds,1)}s / ${num(lane.signal_age_required_seconds,1)}s · ${num(lane.strong_advisor_count??decision.strong_advisor_count??0,0)} strong sources</div></div><div><strong>Adaptive exit · ${esc(lane.exit_policy||exit.policy||'reported')}</strong><div>${esc(exitSummary)}</div><div class="muted">${esc(exitDetail||'Exit manager is waiting for a position or a fresh market update.')}</div><div class="muted">Risk unit ${money(lane.risk_unit_usd)} · Exit frame ${esc(lane.exit_frame||'—')}</div></div><div><strong>Fast tick-flow context</strong><div>${esc(flowDetail)}</div><div class="muted">${num(lane.entries_last_hour,0)} entries/hour · ${num(lane.consecutive_losses,0)} consecutive losses</div><div class="muted">Experimental research/read-only signals never override the execution and risk gates.</div></div></div><details><summary>Full ${esc(name)} decision and exit telemetry</summary>${showJson({decision,adaptive_exit:exit,adaptive_market:lane.adaptive_market,micro_flow:flow,conscience:lane.conscience,entry_timing_blocks:lane.entry_timing_blocks,positions})}</details></article>`;
}
function consensusTelemetry(c){
 const health=c.market_health||{},tick=c.tick_history_health||{},market=c.market||{},phases=c.phase_timings_ms||{};
 const phaseRows=Object.entries(phases).sort((a,b)=>Number(b[1])-Number(a[1])).slice(0,8).map(([name,value])=>`<tr><td>${esc(name)}</td><td>${num(value,2)} ms</td></tr>`).join('')||'<tr><td colspan="2" class="muted">No timing samples reported.</td></tr>';
 const providers=c.source_intelligence?.providers||{},providerRows=Object.entries(providers).map(([name,value])=>`<tr><td>${esc(name)}</td><td>${esc(value.status||value.state||'reported')}</td><td>${value.age_seconds==null?'—':`${num(value.age_seconds,0)} s`}</td></tr>`).join('')||'<tr><td colspan="3" class="muted">No provider status reported.</td></tr>';
 return `<div class="grid3" style="margin-top:12px">${panel('Market feed quality',`<div class="metric">${health.terminal_connected===true?'CONNECTED':health.terminal_connected===false?'DISCONNECTED':'UNKNOWN'}</div><div>${esc(health.reason||c.status_message||'Waiting for feed health.')}</div><div class="muted">Broker quote age ${num(market.broker_tick_age_seconds??health.quote_age_seconds,2)}s · spread ${num(market.spread)} · ${esc(market.session||'session unknown')}</div>`)}${panel('Fast-loop telemetry · not co-located HFT',`<div class="metric">${num(c.loop_elapsed_ms,2)} ms</div><div>Cycle processing · tick-history fetch ${num(tick.fetch_ms,2)} ms</div><div class="muted">Latest tick age ${num(tick.latest_tick_age_seconds??market.v3_tick_age_seconds,2)}s · ${num(tick.cached_ticks??market.v3_tick_count,0)} cached ticks</div><div class="muted">Observed retail MT5/API timings only; no HFT or latency guarantee.</div>`)}${panel('Runtime work per cycle',`<table class="table"><thead><tr><th>Stage</th><th>Measured</th></tr></thead><tbody>${phaseRows}</tbody></table><div class="muted">History refresh ${num(c.history_refresh_ms,2)} ms · status write ${num(c.previous_status_write_ms,2)} ms</div><div class="muted">Signal cache ${num(c.candle_signal_cache?.hits,0)} hits / ${num(c.candle_signal_cache?.misses,0)} misses · exit cache ${num(c.exit_context_cache?.hits,0)} / ${num(c.exit_context_cache?.misses,0)}</div>`)}${panel('AI source resources',`<div class="muted">Provider availability and freshness are reported by the running engine.</div><table class="table"><thead><tr><th>Source</th><th>Status</th><th>Age</th></tr></thead><tbody>${providerRows}</tbody></table><div class="muted">${esc(c.advisor_errors&&Object.keys(c.advisor_errors).length?Object.entries(c.advisor_errors).map(([name,error])=>`${name}: ${error}`).join(' · '):'No advisor errors reported.')}</div>`)}${panel('Entry / exit risk gates',`<div><strong>News:</strong> ${esc((c.news_risk?.block_reasons||[]).join(' · ')||'No active news block reported.')}</div><div><strong>Session stop:</strong> ${esc(c.config?.session_loss_stop_enabled===false?'Disabled in engine config':c.config?.max_session_loss_usd==null?'Not reported':money(c.config.max_session_loss_usd))}</div><div><strong>Per-entry risk cap:</strong> ${money(c.config?.max_trade_risk_usd)} · <strong>Position cap:</strong> ${num(c.config?.max_positions_total,0)}</div><div class="muted">These are engine-reported controls; dashboard display does not approve or send trades.</div>`)}${panel('Detailed AI context',`<details><summary>Signals, filters, calendars and research status</summary>${showJson({advisor_sources:c.advisor_source_health,source_intelligence:c.source_intelligence,economic_advisor_v5:c.economic_advisor_v5,macro_context:c.macro_context,free_macro_context:c.free_macro_context,calendar_status:c.calendar_status,official_release_monitor:c.official_release_monitor,background_refresh_errors:c.background_refresh_errors,adaptive_state_recovery:c.adaptive_state_recovery})}</details>`)}</div>`;
}
function chartCanvas(id,bars,positions){
 const c=document.getElementById(id);if(!c)return;
 const rect=c.getBoundingClientRect();const dpr=window.devicePixelRatio||1;
 c.width=Math.round(rect.width*dpr);c.height=Math.round(rect.height*dpr);
 const ctx=c.getContext('2d');ctx.scale(dpr,dpr);const w=rect.width,h=rect.height;
 ctx.clearRect(0,0,w,h);ctx.fillStyle='#151922';ctx.fillRect(0,0,w,h);
 if(!bars||!bars.length){ctx.fillStyle='#9ba5b7';ctx.textAlign='center';ctx.fillText('Waiting for MT5 XAUUSD candles',w/2,h/2);return}
 const left=12,right=w-70,top=18,bottom=h-28,subset=bars.slice(-160);
 let lo=Math.min(...subset.map(x=>x.low)),hi=Math.max(...subset.map(x=>x.high));const pad=Math.max((hi-lo)*.08,.1);lo-=pad;hi+=pad;
 const y=v=>bottom-(v-lo)/(hi-lo)*(bottom-top),step=(right-left)/subset.length;
 ctx.font='10px Segoe UI';ctx.textAlign='right';
 for(let i=0;i<5;i++){const v=lo+(hi-lo)*i/4,py=y(v);ctx.strokeStyle='#29303d';ctx.beginPath();ctx.moveTo(left,py);ctx.lineTo(right,py);ctx.stroke();ctx.fillStyle='#9ba5b7';ctx.fillText(v.toFixed(2),w-5,py+3)}
 subset.forEach((b,i)=>{const x=left+(i+.5)*step,color=b.close>=b.open?'#62c994':'#ef7a7a';ctx.strokeStyle=color;ctx.fillStyle=color;ctx.beginPath();ctx.moveTo(x,y(b.high));ctx.lineTo(x,y(b.low));ctx.stroke();const bw=Math.max(1,step*.68);ctx.fillRect(x-bw/2,Math.min(y(b.open),y(b.close)),bw,Math.max(1,Math.abs(y(b.open)-y(b.close))))});
 (positions||[]).forEach(p=>{if(typeof p.open==='number'){const py=y(p.open);ctx.strokeStyle=p.side==='BUY'?'#62c994':'#ef7a7a';ctx.setLineDash([4,3]);ctx.beginPath();ctx.moveTo(left,py);ctx.lineTo(right,py);ctx.stroke();ctx.setLineDash([])}});
}
function equityChart(id,history){
 const c=document.getElementById(id);if(!c)return;const rect=c.getBoundingClientRect(),dpr=window.devicePixelRatio||1;c.width=rect.width*dpr;c.height=rect.height*dpr;
 const ctx=c.getContext('2d');ctx.scale(dpr,dpr);const w=rect.width,h=rect.height;ctx.clearRect(0,0,w,h);ctx.fillStyle='#151922';ctx.fillRect(0,0,w,h);
 if(!history||history.length<2){ctx.fillStyle='#9ba5b7';ctx.textAlign='center';ctx.fillText('Waiting for live equity samples',w/2,h/2);return}
 let lo=Math.min(...history.map(x=>x.equity)),hi=Math.max(...history.map(x=>x.equity)),pad=Math.max((hi-lo)*.15,.1);lo-=pad;hi+=pad;
 const t0=history[0].time,t1=history.at(-1).time,x=v=>25+(v-t0)/Math.max(1,t1-t0)*(w-55),y=v=>h-28-(v-lo)/(hi-lo)*(h-55);
 ctx.strokeStyle='#e7b85a';ctx.lineWidth=2;ctx.beginPath();history.forEach((p,i)=>i?ctx.lineTo(x(p.time),y(p.equity)):ctx.moveTo(x(p.time),y(p.equity)));ctx.stroke();
 ctx.fillStyle='#edf0f7';ctx.textAlign='left';ctx.fillText(money(history.at(-1).equity),10,18);
}
function positionsRows(items){if(!items||!items.length)return'<tr><td colspan="7" class="muted">No open positions.</td></tr>';return items.map(p=>`<tr><td>${esc(p.ticket)}</td><td>${esc(p.symbol||p.owner||'XAUUSD')}</td><td>${esc(p.side||p.direction||'—')}</td><td>${num(p.volume)}</td><td>${num(p.open)}</td><td>${num(p.current)}</td><td>${money(p.pnl)}</td></tr>`).join('')}
function dealRows(items){if(!items||!items.length)return'<tr><td colspan="7" class="muted">No recent closed executions.</td></tr>';return items.slice(0,30).map(d=>`<tr><td>${esc(d.time)}</td><td>${esc(d.ticket)}</td><td>${esc(d.symbol)}</td><td>${esc(d.entry||d.side)}</td><td>${num(d.volume)}</td><td>${num(d.price)}</td><td>${money(d.net)}</td></tr>`).join('')}
function formatDuration(seconds){
 if(typeof seconds!=='number'||seconds<0)return'—';
 const days=Math.floor(seconds/86400),hours=Math.floor(seconds%86400/3600),minutes=Math.floor(seconds%3600/60),remaining=seconds%60;
 return `${days?`${days}d `:''}${hours?`${hours}h `:''}${minutes}m ${remaining}s`;
}
function sessionCard(session){
 const available=session.schedule_available===true,open=available&&session.scheduled_open===true;
 if(!available)return `<section class="session-card unknown session-unavailable"><strong>Broker hours unavailable</strong><span>Connect the MT5 demo EA to load its XAUUSD schedule.</span></section>`;
 const state=available?(open?'Scheduled open':'Scheduled closed'):'Schedule unavailable';
 const cls=!available?'unknown':session.preclose_active?'urgent':open?'':'closed';
 const nextClose=open?session.active_close:session.next_close;
 const countdown=session.seconds_to_close>=0?formatDuration(session.seconds_to_close):'—';
 const closeLabel=open?'Current session closes':'Next scheduled close';
 const openLabel=open?'Following open':'Next scheduled open';
 return `<section class="session-card ${cls}"><div><small>MT5 broker schedule · server time</small><h2>${state}</h2></div><div class="session-detail">${closeLabel}<strong>${esc(nextClose||'Unavailable')}</strong><span>${open?'Close in':'Next close in'} ${esc(countdown)}</span></div><div class="session-detail">${openLabel}<strong>${esc(session.next_open||'Unavailable')}</strong><span>Scheduled broker hours; holidays or unscheduled changes may differ.</span></div><div class="session-detail session-status"><strong>${esc(session.closeout_status||'Waiting for current EA session data')}</strong><span>${num(session.xauusd_positions_remaining,0)} positions on attached XAUUSD symbol · close-out target: 5 min before close</span></div></section>`;
}
function render(data){
 const native=data.native||{}, consensus=data.consensus||{}, advisor=data.advisor||{}, manual=data.manual||{}, vfinal=data.vfinal||{};
 const ns=native.snapshot||{};
 // The main engine is authoritative. Old native-EA exports are reference only.
 if(data.main_account?.equity!=null)ns.account=data.main_account;
 if((!Array.isArray(ns.positions)||!ns.positions.length)&&Array.isArray(consensus.positions)){
  ns.positions=consensus.positions.map(p=>({...p,symbol:p.symbol||'XAUUSD',side:p.side||p.direction,
   open:p.open??p.entry_price,current:p.current??p.current_price,pnl:p.pnl??p.profit}));
 }
 if(!ns.market&&consensus.market)ns.market=consensus.market;
 const config=data.config||{},configSignature=JSON.stringify(config);
 if(configSignature!==appliedConfigSignature){
  $('trade-mode').value=config.mode||'observe';
  $('schedule-mode').value=config.schedule_mode||'all_day';$('blocked-start-utc').value=String(config.schedule_mode==='exclude_window'?config.blocked_start_utc:22);$('blocked-end-utc').value=String(config.schedule_mode==='exclude_window'?config.blocked_end_utc:23);updateScheduleInputs();
  appliedConfigSignature=configSignature;
 }
 const eaConfig=ns.unified_config||{};
 const eaConfigMatches=native.state==='live'&&eaConfig.loaded&&eaConfig.mode===config.mode&&eaConfig.timeframe===config.timeframe&&eaConfig.execution_enabled===config.execution_enabled&&eaConfig.schedule_mode===(config.schedule_mode||'all_day')&&eaConfig.blocked_start_utc===(config.blocked_start_utc??-1)&&eaConfig.blocked_end_utc===(config.blocked_end_utc??-1);
 const configDetail=eaConfigMatches?'EA confirmed selection':config.bridge_write_state==='written'&&native.state==='live'?'Waiting for EA to confirm selection':config.bridge_write_state==='written'?'Waiting for a live EA snapshot':'Selection not delivered to MT5';
 const scheduleText=config.schedule_mode==='exclude_window'?`Blocks ${String(config.blocked_start_utc).padStart(2,'0')}:00–${String(config.blocked_end_utc).padStart(2,'0')}:00 UTC`:'EA gates only; no extra time block';
 const session=ns.market_session||{},marketStatus=consensus.state==='running'?'Main AI connected to MT5':!session.schedule_available?'Broker schedule unavailable':'Market status reported';
 const mainLane=consensus.lanes?.SCALP||{},mainDecision=mainLane.decision||{};
 $('overview').innerHTML=`<div class="status-rail"><div class="status-main">${state('Main AI',consensus)}<span class="status-market">${esc(marketStatus)}</span></div><div class="status-meta"><span class="status-config">${esc(consensus.message||'Waiting for main AI heartbeat')}</span><span>${esc(scheduleText)}</span><span>Updated ${new Date(data.server_time*1000).toLocaleTimeString()}</span></div></div>`;
 $('view-overview').innerHTML=`<div class="grid">${card('Main AI',consensus.state||'waiting',consensus.message||'',stateClass(consensus.state))}${card('MT5 demo account',ns.account?.equity!=null?money(ns.account.equity):'—',ns.account?.balance!=null?'Balance '+money(ns.account.balance):'Waiting for MT5 account')}${card('Advisor 1',advisor.report?.overall||'WAIT',advisor.message||'',stateClass(advisor.state))}${card('Open positions',consensus.positions?.length??0,`${num(mainLane.max_positions??3,0)} maximum at 0.01 lot`)}</div><div class="grid3" style="margin-top:12px">${panel('Main AI decision',`<div class="metric">${esc(mainDecision.direction||'WAIT')}</div><div class="reason">${esc((mainDecision.blocks||[]).join(' · ')||mainLane.status||'Monitoring XAUUSD tick flow.')}</div><div class="muted">Evidence ${num(mainDecision.evidence)}/100 · ${esc(mainDecision.dominant_bias||'WAIT')} bias</div>`)}${panel('Live P/L',`<div class="metric">${money(consensus.pnl?.total)}</div><div class="muted">Realized ${money(consensus.pnl?.realized)} · Floating ${money(consensus.pnl?.floating)}</div>`)}${panel('Advisor 1',advisor.report?`<div class="metric">${esc(advisor.report.overall||'WAIT')}</div><div class="reason">${esc(advisor.report.horizons?.SCALP?.reasons?.join(' · ')||advisor.message)}</div>`:`<div class="muted">${esc(advisor.message||'Waiting for Advisor 1.')}</div>`)}</div>`;
 const ca=ns.account||{}, cm=ns.market||{}, ck=ns.kpi||{};
 unifiedControlToken=data.control_token||"";equityHistory=data.equity_history||[];unifiedNative={...ns,source:native.source};
 const controls=ns.controls||{}, enabled=native.state==='live'&&controls.enabled&&!!unifiedControlToken;
 $('view-native').innerHTML=`<div class="grid">${card('Symbol',cm.symbol||'XAUUSD',cm.timeframe||'M1')}${card('Bid',cm.bid!=null?num(cm.bid):'—',cm.ask!=null?'Ask '+num(cm.ask):'')}${card('Equity',ca.equity!=null?money(ca.equity):'—',ca.balance!=null?'Balance '+money(ca.balance):'')}${card('Positions',ns.positions?.length??0,ns.risk?.message||native.message||'')}</div><div class="control-strip" style="margin-top:12px"><button data-native-action="pause" ${enabled?'':'disabled'}>Pause entries</button><button data-native-action="resume" ${enabled?'':'disabled'}>Resume entries</button><button data-native-action="reset_session" ${enabled&&controls.can_reset?'':'disabled'}>Reset session</button><button class="danger" data-native-action="close_all" ${enabled&&controls.can_execute?'':'disabled'}>Close All account</button><span class="muted">${esc(native.message||'Waiting for EA')}</span></div><div class="grid3" style="margin-top:12px"><article class="panel" style="grid-column:span 2"><h2>Live XAUUSD chart</h2><div class="chart-wrap"><canvas id="live-chart"></canvas></div></article>${panel('Execution',`<div class="reason">${esc(ns.execution?.message||ns.status||native.message||'Waiting')}</div>`)}</div><div class="grid" style="margin-top:12px">${card('Balance',ca.balance!=null?money(ca.balance):'—','Account balance')}${card('Floating P/L',ca.floating!=null?money(ca.floating):'—','Includes open position floating P/L')}${card('Free margin',ca.margin_free!=null?money(ca.margin_free):'—','Broker free margin')}${card('Win rate',ns.kpi?.win_rate||'—','30-day closed EA positions')}</div><div class="grid3" style="margin-top:12px"><article class="panel"><h2>Open positions</h2><div class="position-table"><table class="table"><thead><tr><th>Ticket</th><th>Symbol</th><th>Side</th><th>Lots</th><th>Entry</th><th>Current</th><th>P/L</th></tr></thead><tbody>${positionsRows(ns.positions||[])}</tbody></table></div></article><article class="panel"><h2>Past executions</h2><div class="position-table"><table class="table"><thead><tr><th>Time</th><th>Ticket</th><th>Symbol</th><th>Side</th><th>Lots</th><th>Price</th><th>Net P/L</th></tr></thead><tbody>${dealRows(ns.deals||[])}</tbody></table></div></article><article class="panel"><h2>Account equity</h2><div class="chart-wrap" style="height:220px"><canvas id="equity-chart"></canvas></div></article></div><div class="grid3" style="margin-top:12px">${panel('Scalp engine',ns.scalp?showJson(ns.scalp):'<div class="muted">No native EA snapshot.</div>')}${panel('Risk',ns.risk?showJson(ns.risk):'<div class="muted">No risk snapshot.</div>')}${panel('Decision / activity',showJson({filters:ns.filters,blockers:ns.blockers,events:ns.events,learning:ns.learning}))}</div>`;
 setTimeout(()=>{chartCanvas('live-chart',unifiedNative.candles||[],unifiedNative.positions||[]);equityChart('equity-chart',equityHistory||[]);document.querySelectorAll('[data-native-action]').forEach(button=>button.onclick=()=>sendNativeAction(button.dataset.nativeAction));},0);
 const nativeView=$('view-native'),nativeGrids=nativeView.querySelectorAll('.grid3');
 if(nativeGrids.length>1)nativeGrids[1].classList.add('position-grid');
 if(nativeGrids.length>2)nativeGrids[2].classList.add('advanced-grid');
 if(nativeGrids.length>2){
  Array.from(nativeGrids[2].children).forEach(article=>{
   const heading=article.querySelector('h2');if(!heading)return;
   const details=document.createElement('details');details.className='panel';
   const summary=document.createElement('summary');summary.textContent=heading.textContent;
   const contents=Array.from(article.children).filter(child=>child!==heading);
   details.appendChild(summary);contents.forEach(child=>details.appendChild(child));
   article.replaceWith(details);
  });
 }
 $('view-consensus').innerHTML=consensus.status?`<div class="grid">${card('Engine',consensus.state||'waiting',consensus.message||'')}${card('Mode / P&L',consensus.paper_trading?'PAPER':String(consensus.mode||'DEMO').toUpperCase(),consensus.pnl?.total!=null?`Total ${money(consensus.pnl.total)} · Realized ${money(consensus.pnl.realized)} · Floating ${money(consensus.pnl.floating)}`:'P&L not reported')}${card('Positions',consensus.positions?.length??0,consensus.config?.max_positions_total!=null?`${consensus.config.max_positions_total} configured slots`:'')}${card('Last cycle',consensus.cycle??'—',consensus.age_seconds!=null?`Snapshot age ${num(consensus.age_seconds,1)}s · ${esc(consensus.updated_local||consensus.updated_at||'')}`:'No trusted heartbeat')}</div>${consensusTelemetry(consensus)}<div class="grid3" style="margin-top:12px">${['SCALP','INTRADAY','SWING'].filter(name=>consensus.lanes?.[name]).map(name=>consensusLaneCard(name,consensus.lanes[name])).join('')||panel('Lane decisions','No lane decision snapshot is available.')}</div>`:`<div class="panel"><h2>AI consensus waiting</h2><div class="muted">${esc(consensus.message||'No consensus status file.')}</div></div>`;
 const ar=advisor.report;
 $('view-advisor').innerHTML=ar?`<div class="grid">${card('Overall movement',ar.overall,advisor.message||'',stateClass(advisor.state))}${card('Market',ar.symbol||'XAUUSD',`Bid ${num(ar.bid)} · Ask ${num(ar.ask)} · Spread ${num(ar.spread)}`)}${card('Session',ar.session||'—',`Report age ${num(advisor.age_seconds,1)}s`)}${card('Active horizons',(ar.actionable_horizons||[]).join(', ')||'None','Advisor 1 analysis only')}</div><div class="advisor-stack" style="margin-top:16px">${['SCALP','INTRADAY','SWING'].map(name=>advisorHorizonCard(name,ar.horizons?.[name]||{})).join('')}</div>`:`<div class="panel"><h2>Advisor 1</h2><div class="muted">${esc(advisor.message||'Waiting for the protected Advisor 1 report.')}</div></div>`;
 const mr=manual.report;
 $('view-manual').innerHTML=mr?`<div class="grid">${card('Action',mr.action,mr.bias||'')}${card('Evidence',num(mr.directional_evidence_score),`Valid until ${esc(mr.valid_until||'')}`)}${card('Quote',num(mr.quote?.bid),`Ask ${num(mr.quote?.ask)} · Spread ${num(mr.quote?.spread)}`)}${card('Execution','DISABLED','Read-only advisory')}</div><div class="grid3" style="margin-top:12px">${panel('Reasons',`<ul>${(mr.reasons||[]).map(x=>`<li>${esc(x)}</li>`).join('')||'<li>None</li>'}</ul>`)}${panel('Blocks / cautions',`<ul>${(mr.blocks||[]).map(x=>`<li>${esc(x)}</li>`).join('')||'<li>None</li>'}</ul>`)}${panel('Scenario',showJson(mr.scenario_levels||{}))}</div>`:`<div class="panel"><h2>Manual scalp</h2><div class="muted">${esc(manual.message||'Waiting for a read-only manual report.')}</div></div>`;
 $('view-vfinal').innerHTML=vfinal.report?`<div class="grid">${card('Status',vfinal.report.status||vfinal.state||'WAITING',vfinal.message||'')}${card('Signal',vfinal.report.signal?.direction||'WAIT',vfinal.report.signal?.score!=null?`Score ${num(vfinal.report.signal.score)}`:'')}${card('Price',vfinal.report.market?.bid!=null?num(vfinal.report.market.bid):'—',vfinal.report.market?.spread!=null?`Spread ${num(vfinal.report.market.spread)}`:'')}${card('Updated',vfinal.report.updated_at||'—','')}</div><div class="grid3" style="margin-top:12px">${panel('Account',showJson(vfinal.report.account||{}))}${panel('Positions',showJson(vfinal.report.positions||[]))}${panel('Safety / learning',showJson({safety:vfinal.report.safety,learning:vfinal.report.learning,actions:vfinal.report.actions}))}</div>`:`<div class="panel"><h2>V-FINAL</h2><div class="muted">${esc(vfinal.message||'Waiting for V-FINAL status.')}</div></div>`;
 $('view-system').innerHTML=`<div class="grid3">${panel('Local service',`<div class="metric">127.0.0.1:8777</div><div class="muted">Refresh every ${num(data.refresh_seconds||3,0)} seconds</div>`)}${panel('Execution policy',`<span class="mode-lock">DEMO ONLY</span><p class="muted">Observe or MT5 demo. Live is locked until a separate account is configured and explicitly authorized.</p>`)}${panel('Engine status',`${state('Native EA',native)} ${state('Consensus',consensus)} ${state('Advisor 1',advisor)} ${state('Manual',manual)} ${state('V-FINAL',vfinal)}`)}${panel('Advisor report bridge',`<div class="metric">${esc(data.advisor_support?.advisor||'Not running')}</div><div class="muted">Age ${num(data.advisor_support?.report_age_seconds,1)}s · report is analysis only</div>`)}${panel('Fast execution limits',`The desk shows broker-reported tick and loop timing for the fast scalping engine. It does not imply exchange co-location, HFT infrastructure, or guaranteed order latency. Strategy evaluation and MT5 broker execution are separate steps.`)} </div>`;
}
let timer=null,seconds=3;
async function sendNativeAction(action){
 const source=unifiedNative?.source||document.querySelector('#source')?.value||"";
 if(!source||!unifiedControlToken){alert('Waiting for a live native EA account feed.');return}
 const response=await fetch('/api/control',{method:'POST',headers:{'Content-Type':'application/json','X-Gold-Control':unifiedControlToken,'Origin':location.origin},body:JSON.stringify({source,instance:unifiedNative.controls?.instance||"",action})});
 if(!response.ok){alert(await response.text());return}
 const result=await response.json();alert(`${result.action}: ${result.message}`);
}
function updateScheduleInputs(){
 const enabled=$('schedule-mode').value==='exclude_window';
 $('blocked-start-utc').disabled=!enabled;$('blocked-end-utc').disabled=!enabled;
}
const hourOptions=Array.from({length:24},(_,hour)=>`<option value="${hour}">${String(hour).padStart(2,'0')}:00</option>`).join('');
$('blocked-start-utc').innerHTML=hourOptions;$('blocked-end-utc').innerHTML=hourOptions;
$('schedule-mode').onchange=updateScheduleInputs;
async function applySelection(){
 const scheduleMode=$('schedule-mode').value;
 const payload={symbol:'XAUUSD',mode:$('trade-mode').value,timeframe:'M1',execution_enabled:$('trade-mode').value==='demo',schedule_mode:scheduleMode,blocked_start_utc:scheduleMode==='exclude_window'?Number($('blocked-start-utc').value):-1,blocked_end_utc:scheduleMode==='exclude_window'?Number($('blocked-end-utc').value):-1};
 const response=await fetch('/api/config',{method:'POST',headers:{'Content-Type':'application/json','Origin':location.origin},body:JSON.stringify(payload)});
 const body=await response.text();let result={};
 try{result=JSON.parse(body)}catch(_){alert(body||'Could not save the selection.');return}
 if(!response.ok){alert(result.error||'Could not deliver the selection to MT5.');await refresh();return}
 $('overview').dataset.config=JSON.stringify(result);const scheduleSummary=result.schedule_mode==='exclude_window'?`Entries blocked ${String(result.blocked_start_utc).padStart(2,'0')}:00–${String(result.blocked_end_utc).padStart(2,'0')}:00 UTC.`:'No extra entry-time block.';
 alert(`Saved: XAUUSD ${result.mode==='demo'?'demo':'observe'} mode. ${scheduleSummary} The EA must confirm the selection in a live snapshot.`);
 await refresh();
}
$('apply-config').onclick=applySelection;
async function refresh(){try{const r=await fetch('/api/unified?t='+Date.now(),{cache:'no-store'});if(!r.ok)throw Error('HTTP '+r.status);render(await r.json())}catch(e){$('overview').textContent='Unified dashboard connection error: '+e.message}}
function schedule(){clearInterval(timer);seconds=Number($('interval').value)||3;timer=setInterval(refresh,seconds*1000)}
$('interval').onchange=schedule;$('density').onclick=()=>document.body.classList.toggle('compact');
show(localStorage.getItem('goldUnifiedView')||'overview');refresh();schedule();
</script>
</body></html>"""


def read_vfinal_status(path: Path = VFINAL_STATUS) -> dict:
    try:
        report = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(report, dict):
            raise ValueError("Invalid V-FINAL status")
        return {"state": str(report.get("status") or "running").lower(),
                "message": "V-FINAL status loaded.", "report": report}
    except FileNotFoundError:
        return {"state": "waiting", "message": "Waiting for V-FINAL demo status.", "report": None}
    except (OSError, ValueError, TypeError, json.JSONDecodeError) as error:
        return {"state": "error", "message": f"Cannot read V-FINAL status: {error}", "report": None}


def classify_consensus_status(status: dict, now: float | None = None) -> dict:
    result = dict(status)
    state = str(result.get("status", "WAITING")).upper()
    now = time.time() if now is None else now
    if state == "RUNNING":
        try:
            updated = datetime.fromisoformat(str(result["updated_at"]).replace("Z", "+00:00"))
            if updated.tzinfo is None:
                raise ValueError("Consensus heartbeat has no timezone.")
            age = now - updated.astimezone(timezone.utc).timestamp()
        except (KeyError, TypeError, ValueError, OverflowError):
            result.update(state="stale", message="Consensus heartbeat is missing or invalid; cached values are not live.")
            return result
        result["age_seconds"] = round(max(age, 0.0), 1)
        if age < -5.0 or age > 10.0:
            result.update(state="stale", message="Consensus heartbeat is future-dated or older than 10 seconds; cached values are not live.")
        else:
            result.update(state="running", message="Consensus heartbeat is current.")
    elif state in {"STOPPED", "HALTED"}:
        result.update(state="stopped", message="Consensus bot is stopped; values below are its last snapshot.")
    elif state in {"ERROR", "DATA_UNAVAILABLE"}:
        result.update(state="error", message=str(result.get("status_message") or "Consensus bot reported an error."))
    else:
        result.update(state="waiting", message=str(result.get("status_message") or "Waiting for the consensus bot."))
    return result


def read_unified_config() -> dict:
    default = {"symbol": "XAUUSD", "mode": "demo", "timeframe": "M1",
               "execution_enabled": False, "updated_at": None,
               "bridge_write_state": "not_written", "bridge_write_error": None,
               "schedule_mode": "all_day", "blocked_start_utc": -1, "blocked_end_utc": -1}
    try:
        value = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
        if not isinstance(value, dict):
            return default
        return {
            "symbol": "XAUUSD" if value.get("symbol") == "XAUUSD" else "XAUUSD",
            "mode": "demo" if value.get("mode") == "demo" else "observe",
            "timeframe": value.get("timeframe") if value.get("timeframe") in ("M1", "M5") else "M1",
            "execution_enabled": value.get("mode") == "demo" and value.get("execution_enabled") is True,
            "updated_at": value.get("updated_at"),
            "bridge_write_state": value.get("bridge_write_state")
            if value.get("bridge_write_state") in ("written", "failed", "not_written") else "not_written",
            "bridge_write_error": value.get("bridge_write_error")
            if isinstance(value.get("bridge_write_error"), str) else None,
                "schedule_mode": value.get("schedule_mode")
                if value.get("schedule_mode") in ("all_day", "exclude_window") else "all_day",
                "blocked_start_utc": value.get("blocked_start_utc")
                if isinstance(value.get("blocked_start_utc"), int) and not isinstance(value.get("blocked_start_utc"), bool) else -1,
                "blocked_end_utc": value.get("blocked_end_utc")
                if isinstance(value.get("blocked_end_utc"), int) and not isinstance(value.get("blocked_end_utc"), bool) else -1,
        }
    except (FileNotFoundError, OSError, ValueError, TypeError, json.JSONDecodeError):
        return default


class BridgeWriteError(OSError):
    def __init__(self, message: str, config: dict):
        super().__init__(message)
        self.config = config


def _write_config_file(config: dict) -> None:
    CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    temporary = CONFIG_PATH.with_suffix(".tmp")
    temporary.write_text(json.dumps(config, indent=2), encoding="utf-8")
    os.replace(temporary, CONFIG_PATH)


def save_unified_config(payload: dict, feed_directory: Path | None = None) -> dict:
    symbol = payload.get("symbol")
    mode = payload.get("mode")
    timeframe = payload.get("timeframe")
    if symbol != "XAUUSD":
        raise ValueError("Only XAUUSD is available in this release.")
    if mode not in ("observe", "demo"):
        raise ValueError("Trading mode must be observe or demo.")
    if timeframe not in ("M1", "M5"):
        raise ValueError("Timeframe must be M1 or M5.")
    schedule_mode = payload.get("schedule_mode", "all_day")
    if schedule_mode not in ("all_day", "exclude_window"):
        raise ValueError("Schedule must be all_day or exclude_window.")
    if schedule_mode == "exclude_window":
        def parse_hour(value: object) -> int:
            if isinstance(value, bool):
                raise ValueError("UTC blocked-window hours must be integers from 0 to 23.")
            if isinstance(value, int):
                return value
            if isinstance(value, str) and value.isdigit():
                return int(value)
            raise ValueError("UTC blocked-window hours must be integers from 0 to 23.")

        blocked_start = parse_hour(payload.get("blocked_start_utc"))
        blocked_end = parse_hour(payload.get("blocked_end_utc"))
        if not 0 <= blocked_start <= 23 or not 0 <= blocked_end <= 23 or blocked_start == blocked_end:
            raise ValueError("UTC blocked-window hours must differ and be from 0 to 23.")
    else:
        blocked_start = blocked_end = -1
    execution_enabled = mode == "demo" and payload.get("execution_enabled") is True
    config = {
        "symbol": "XAUUSD",
        "mode": mode,
        "timeframe": timeframe,
        "execution_enabled": execution_enabled,
        "schedule_mode": schedule_mode,
        "blocked_start_utc": blocked_start,
        "blocked_end_utc": blocked_end,
        "updated_at": time.time(),
        "bridge_write_state": "not_written",
        "bridge_write_error": None,
    }
    _write_config_file(config)
    try:
        feed = feed_directory or default_feed_directory()
        feed.mkdir(parents=True, exist_ok=True)
        unified_file = feed / "unified_config.csv"
        temporary_file = unified_file.with_suffix(".tmp")
        temporary_file.write_text(
            f"GOLD_UNIFIED_V2;XAUUSD;{mode};{timeframe};{'enabled' if execution_enabled else 'disabled'};"
            f"{schedule_mode};{blocked_start};{blocked_end};END\n",
            encoding="ascii",
        )
        os.replace(temporary_file, unified_file)
    except (OSError, ValueError) as error:
        config["bridge_write_state"] = "failed"
        config["bridge_write_error"] = str(error)
        _write_config_file(config)
        raise BridgeWriteError(f"Could not write the MT5 Common/Files config: {error}", config) from error
    config["bridge_write_state"] = "written"
    _write_config_file(config)
    return read_unified_config()


def build_unified_status(directory: Path) -> dict:
    source = ""
    paths = sorted(directory.glob("dashboard_*.json")) if directory.exists() else []
    if len(paths) == 1:
        source = paths[0].name
    native = read_status(directory, source)
    try:
        consensus = _compact_consensus_status(classify_consensus_status(read_dashboard_status()))
    except (FileNotFoundError, OSError, ValueError, TypeError):
        consensus = {"state": "waiting", "message": "Waiting for consensus status.", "status": "WAITING"}
    advisor = _compact_advisor_status(read_advisor())
    manual = read_manual_scalp()
    vfinal = read_vfinal_status()
    config = read_unified_config()
    native_account = (native.get("snapshot") or {}).get("account") or {}
    consensus_account = consensus.get("account") or {}
    # The consensus engine is the active trading process. Prefer its fresh MT5
    # account snapshot over a possibly old native-EA export.
    consensus_live = consensus.get("state") == "running"
    account = (consensus_account if consensus_live and isinstance(consensus_account.get("equity"), (int, float))
               else native_account)
    account_live = (native.get("state") == "live" or consensus_live)
    account_source = "gold-consensus-main" if account is consensus_account else str(native.get("source") or "native")
    live_account = read_live_mt5_account()
    if isinstance(live_account.get("equity"), (int, float)):
        account, account_live, account_source = live_account, True, "mt5-read-only-account"
    if account_live and isinstance(account.get("equity"), (int, float)):
        source_key = account_source
        history = EQUITY_HISTORY.setdefault(source_key, [])
        point = {"time": time.time(), "equity": float(account["equity"]),
                 "balance": float(account.get("balance", 0)),
                 "floating": float(account.get("floating", 0))}
        if not history or abs(history[-1]["equity"] - point["equity"]) > 1e-9:
            history.append(point)
        if len(history) > 500:
            del history[:-500]
    return {
        "server_time": time.time(),
        "refresh_seconds": 3,
        "config": config,
        "equity_history": EQUITY_HISTORY.get(account_source, [])[-500:],
        "main_account": account,
        "sources": {
            "native": str(directory),
            "consensus": "data/runtime/gold_consensus_status.json",
            "advisor": str(Path("data/runtime/gold_advisory.json")),
            "manual": str(Path("data/runtime/gold_manual_scalp_advisory.json")),
            "vfinal": str(VFINAL_STATUS),
        },
        "native": _compact_native_status(native),
        "consensus": consensus,
        "advisor": advisor,
        "manual": manual,
        "vfinal": vfinal,
    }


class UnifiedDashboardServer(ThreadingHTTPServer):
    allow_reuse_address = False


def create_unified_server(feed_directory: Path | None = None, port: int = 8777) -> ThreadingHTTPServer:
    directory = feed_directory or default_feed_directory()
    directory.mkdir(parents=True, exist_ok=True)
    mailbox = ControlMailbox(directory)
    control_token = secrets.token_urlsafe(32)

    class Handler(BaseHTTPRequestHandler):
        def setup(self) -> None:
            super().setup()
            self.connection.settimeout(3)

        def reply(self, code: int, body: bytes, content_type: str) -> None:
            self.send_response(code)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Content-Security-Policy", "default-src 'self'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; connect-src 'self'; img-src 'self'; frame-ancestors 'none'")
            self.end_headers()
            try:
                self.wfile.write(body)
            except (BrokenPipeError, ConnectionResetError):
                pass

        def do_GET(self) -> None:
            port = self.server.server_address[1]
            if self.headers.get("Host", "") not in {f"127.0.0.1:{port}", f"localhost:{port}"}:
                self.reply(403, b"Local access only", "text/plain")
                return
            path = urlsplit(self.path).path
            if path == "/":
                self.reply(200, HTML.encode("utf-8"), "text/html; charset=utf-8")
                return
            if path == "/api/unified":
                status = build_unified_status(directory)
                status["control_token"] = control_token
                support = getattr(self.server, "advisor_support", None)
                if support is not None:
                    status["advisor_support"] = dict(support.health)
                payload = json.dumps(status, allow_nan=False).encode("utf-8")
                self.reply(200, payload, "application/json")
                return
            if path == "/api/config":
                self.reply(200, json.dumps(read_unified_config()).encode("utf-8"), "application/json")
                return
            if path == "/health":
                self.reply(200, b'{"ok":true,"dashboard":"aurum-gold-unified"}', "application/json")
                return
            self.reply(404, b"Not found", "text/plain")

        def do_POST(self) -> None:
            port = self.server.server_address[1]
            host = self.headers.get("Host", "")
            if host not in {f"127.0.0.1:{port}", f"localhost:{port}"}:
                self.reply(403, b"Local access only", "text/plain")
                return
            origin = self.headers.get("Origin")
            if origin != "http://" + host:
                self.reply(403, b"Invalid origin", "text/plain")
                return
            path = urlsplit(self.path).path
            try:
                size = int(self.headers.get("Content-Length", "0"))
                if size <= 0 or size > 2048:
                    raise ValueError("Invalid request size")
                if self.headers.get("Content-Type", "").split(";")[0] != "application/json":
                    raise ValueError("JSON required")
                payload = json.loads(self.rfile.read(size))
                if not isinstance(payload, dict):
                    raise ValueError("JSON object required")
                if path == "/api/config":
                    saved = save_unified_config(payload, directory)
                    self.reply(200, json.dumps(saved).encode("utf-8"), "application/json")
                    return
                if path == "/api/control":
                    token = self.headers.get("X-Gold-Control", "")
                    if not secrets.compare_digest(token, control_token):
                        self.reply(403, b"Invalid control token", "text/plain")
                        return
                    source = payload.get("source")
                    status = read_status(directory, source)
                    result = mailbox.enqueue(payload, status)
                    self.reply(202, json.dumps(result).encode("utf-8"), "application/json")
                    return
                self.reply(404, b"Not found", "text/plain")
            except ControlConflict as error:
                self.reply(409, str(error).encode("utf-8"), "text/plain")
            except BridgeWriteError as error:
                body = json.dumps({"error": str(error), "config": error.config}).encode("utf-8")
                self.reply(503, body, "application/json")
            except (OSError, ValueError, TypeError, RecursionError) as error:
                self.reply(400, str(error).encode("utf-8"), "text/plain")

        def log_message(self, *args: object) -> None:
            return

    server = UnifiedDashboardServer(("127.0.0.1", int(port)), Handler)
    return server
