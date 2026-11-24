from __future__ import annotations

"""Local dashboard for the three-horizon demo bot."""

import json
import math
import gzip
import os
import threading
import time
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse
from urllib.request import urlopen

from services.dashboard.gold_horizon_history import reset_history
from services.dashboard.gold_loss_reset import reset_loss_baseline
from services.dashboard.gold_dual_reset import reset_both_displays
from config import gold_inverse_settings as inverse_settings
from services.dashboard.gold_main_display_reset import reset_main_display, apply_main_display_reset

STATUS_PATH = Path("data/runtime/gold_consensus_status.json")
INVERSE_STATUS_PATH = Path('data/runtime/gold_inverse_status.json')


def _read_status_json(path):
    for attempt in range(3):
        try:
            try:
                return json.loads(path.read_text(encoding='utf-8'))
            except (UnicodeDecodeError, TypeError):
                return json.loads(path.read_bytes())
        except (PermissionError, FileNotFoundError):
            if attempt == 2:
                raise
            time.sleep(.01*(attempt+1))


def read_dashboard_status(*, now=None):
    now = time.time() if now is None else now
    status = _read_status_json(STATUS_PATH)
    if not isinstance(status, dict):
        raise ValueError('Invalid main status')
    if 'lanes' not in status and not status.get('account_fingerprint'):
        return status
    inverse = dict(available=False, fresh=False, state='UNAVAILABLE', reason='Inverse status unavailable')
    try:
        payload = _read_status_json(INVERSE_STATUS_PATH)
        if not isinstance(payload, dict):
            raise ValueError('Invalid inverse status')
        if (not status.get('account_fingerprint') or
                payload.get('account_fingerprint') != status['account_fingerprint'] or
                payload.get('demo_only') is not True or payload.get('protocol') != 1):
            raise ValueError('Inverse account/status mismatch')
        age = now-float(payload['heartbeat_epoch'])
        if not math.isfinite(age) or age < 0:
            raise ValueError('Inverse status is future-dated')
        inverse = dict(payload, available=True, fresh=age <= 15, age_seconds=age)
        if age > 15:
            inverse['state'] = 'STALE'
    except (OSError, ValueError, KeyError, TypeError):
        pass
    status['inverse'] = inverse
    report = inverse.get('trading', {})
    main_display = report.get('main_display', {})
    if (inverse_settings.EXECUTOR_ENABLED and inverse.get('fresh')
            and inverse.get('state') == 'RUNNING' and report.get('available')
            and main_display.get('pnl', {}).get('available')):
        status['execution_pnl'] = status.get('pnl', {})
        status['pnl'] = main_display['pnl']
        status['lanes']['SCALP']['closed_trades'] = main_display.get('closed_trades', [])
        status['display_scope'] = report.get('scope')
    else:
        status['display_scope'] = 'MT5 demo broker P/L since ' + str(status.get('loss_baseline_at', 'session start'))
    if not inverse_settings.EXECUTOR_ENABLED:
        status = apply_main_display_reset(status)
    try:
        validation = _read_status_json(Path('data/runtime/gold_strategy_validation.json'))
        if validation.get('account_fingerprint') == status.get('account_fingerprint'):
            status['strategy_validation'] = validation
    except (OSError, ValueError, TypeError, AttributeError):
        pass
    return status

HTML = r'''<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Gold Consensus Command Center</title>
<style>
:root{--bg:#070b12;--panel:#111925;--panel2:#0c131e;--line:#273447;--text:#edf4fc;--muted:#91a1b6;--buy:#2ee6a6;--sell:#ff667d;--wait:#ffc857;--blue:#67a8ff;--purple:#b493ff}
*{box-sizing:border-box}body{margin:0;background:radial-gradient(circle at 45% -10%,#1b2d49 0,#070b12 38%);color:var(--text);font:14px Inter,Segoe UI,Arial,sans-serif}.wrap{max-width:1720px;margin:auto;padding:18px}.top,.row{display:flex;justify-content:space-between;align-items:center;gap:12px}.top{flex-wrap:wrap}.title{font-size:27px;font-weight:900}.muted,.small{color:var(--muted)}.small{font-size:12px}.badges{display:flex;flex-wrap:wrap;gap:7px}.badge,.pill{padding:6px 10px;border:1px solid var(--line);border-radius:999px;background:#0b121c}.grid3{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:12px}.grid4{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:12px}.two{display:grid;grid-template-columns:1.15fr .85fr;gap:12px}.card{background:linear-gradient(180deg,#131c29f7,#0b121cf7);border:1px solid var(--line);border-radius:15px;padding:15px;box-shadow:0 12px 34px #0005}.section{margin-top:13px}.label{font-size:10px;letter-spacing:.13em;text-transform:uppercase;color:var(--muted)}.metric{font-size:27px;font-weight:900}.buy{color:var(--buy)}.sell{color:var(--sell)}.wait{color:var(--wait)}.ok{color:var(--buy)}.danger{color:var(--sell)}.lane{border-top:3px solid var(--wait)}.lane.scalp{border-top-color:var(--buy)}.lane.intraday{border-top-color:var(--blue)}.lane.swing{border-top-color:var(--purple)}.lane h2,.card h2{margin:0 0 8px}.decision{font-size:29px;font-weight:900}.bar{height:7px;background:#202c3c;border-radius:10px;overflow:hidden;margin:8px 0 12px}.bar i{display:block;height:100%;background:currentColor}.kv{display:grid;grid-template-columns:repeat(2,1fr);gap:7px}.kv>div,.advisor,.position{background:var(--panel2);border:1px solid #1d2938;border-radius:9px;padding:9px}.kv b{display:block;margin-top:3px}.reason{border-left:3px solid var(--wait);background:#0a111a;padding:9px;border-radius:7px;line-height:1.4;margin-top:10px}.advisors{display:grid;grid-template-columns:repeat(3,1fr);gap:7px}.advisor .bias{font-size:17px;font-weight:850}.table{width:100%;border-collapse:collapse}.table th,.table td{padding:8px;border-bottom:1px solid var(--line);text-align:left;font-size:12px}.table th{font-size:10px;color:var(--muted);text-transform:uppercase}.scroll{overflow:auto;max-height:430px}.position{margin:7px 0}.button{cursor:pointer;border:1px solid #3a4d66;background:#172438;color:var(--text);padding:7px 10px;border-radius:8px}.button:hover{border-color:var(--blue)}.footer{margin:15px 2px;color:var(--muted);font-size:11px}.empty{padding:12px;color:var(--muted)}
@media(max-width:1100px){.grid4{grid-template-columns:repeat(2,1fr)}.grid3,.two{grid-template-columns:1fr}}@media(max-width:650px){.grid4,.advisors{grid-template-columns:1fr}.wrap{padding:9px}.title{font-size:21px}}
</style></head><body><div class="wrap">
<div class="top"><div><div class="title">Gold Scalping Command Center</div><div class="muted">Gold SCALP trading: up to 4 positions; three combined positions maximum. INTRADAY and SWING: analysis only.</div></div><div id="badges" class="badges"></div></div>
<div id="app" class="section"><div class="card">Connecting to bot...</div></div>
<div id="connection-warning" class="section" role="status" aria-live="polite"></div>
<div class="section"><a class="button" href="/advisor" target="_blank" rel="noopener">Open Advisor 1 analysis</a></div>
<div class="footer">Auto-refresh: 2 seconds. Display resets never delete MT5 trade records. Live-account trading cannot be enabled here.</div>
</div><script>
const $=id=>document.getElementById(id),num=(v,d=2)=>Number(v??0).toFixed(d),cap=v=>String(v||'WAIT').toUpperCase();
const esc=s=>String(s??'').replace(/[&<>"']/g,m=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[m]));
const tone=v=>cap(v)==='BUY'?'buy':cap(v)==='SELL'?'sell':'wait';
const money=x=>Number(x)<0?'-$'+Math.abs(Number(x)).toFixed(2):'$'+Number(x??0).toFixed(2);
const local=t=>{if(!t)return '-';let d=new Date(t);return isNaN(d)?'-':d.toLocaleString([],{dateStyle:'medium',timeStyle:'medium'})};
const badge=(s,c='')=>`<span class="badge ${c}">${esc(s)}</span>`;
function feedHealth(x){const h=x.market_health||{},t=x.tick_history_health||{};
 return `<div class="card section"><b>Market data:</b> ${esc(h.reason||x.status_message||'Waiting for status')}`
 +`<div class="small">Terminal: ${h.terminal_connected===true?'connected':h.terminal_connected===false?'disconnected':'unknown'} | Broker tick age: ${h.quote_age_seconds==null?'unknown':num(h.quote_age_seconds,1)+'s'}`
 +` | Loop: ${x.loop_elapsed_ms==null?'-':num(x.loop_elapsed_ms,0)+'ms'} | Tick fetch: ${t.fetch_ms==null?'-':num(t.fetch_ms,1)+'ms'}</div>`
 +`${t.error?'<div class="reason">'+esc(t.error)+'</div>':''}`
 +`${Object.keys(x.advisor_errors||{}).length?'<div class="reason">'+Object.entries(x.advisor_errors).map(([k,v])=>esc(k)+': '+esc(v)).join('<br>')+'</div>':''}</div>`}
function conscienceLine(lane){const x=lane?.adaptive_exit||{},c=x.conscience||{},f=lane?.micro_flow||{};
 const flow=`<div class="small section"><b>Quote flow:</b> ${f.available?esc(f.bias)+' | pressure '+num(f.pressure,2)+(f.reversal_risk==null?'':' | reversal strength '+num(f.reversal_risk,2)):esc(f.reason||'Warming up')}`
  +`<br>Entries/hour: ${num(lane?.entries_last_hour||0,0)} | Loss streak: ${num(lane?.consecutive_losses||0,0)}`
  +`${lane?.execution_history_available===false?' | Waiting for execution history':''}</div>`;
 if(!c.available)return flow;
 const conv=Number(c.conviction||0),tone_=conv>=.6?'buy':conv<=.35?'sell':'wait';
 const held=x.profit_r==null?'-':`${Number(x.profit_r)>=0?'+':''}${Number(x.profit_r).toFixed(2)}R`;
 const give=x.giveback_distance==null?'-':`${Number(x.giveback_distance).toFixed(2)} (x${Number(x.giveback_scale||1).toFixed(2)})`;
 const worry=(c.leading_concerns||[]).map(t=>esc(t)).join('<br>');
 return flow+`<div class="small section"><b>Conscience:</b> <span class="${tone_}">${num(conv,2)}</span>`
  +` conviction from ${num(100*Number(c.coverage||0),0)}% source coverage · held ${esc(held)}`
  +` · giveback ${esc(give)}${x.breakeven_armed?' · breakeven protected':''}`
  +(worry?`<div class="reason">${worry}</div>`:'')+`</div>`}
function advisorCards(d){let map={};for(let a of(d?.contributors||[]))map[a.advisor]=a;return [['MT5 Candles','MT5_CANDLES'],['API Candles','API_CANDLES'],['V3 MT5 Tick Flow','MT5_TICK_FLOW']].map(([label,key])=>{let a=map[key]||{},b=cap(a.bias),usable=a.source_usable!==false;return `<div class="advisor"><div class="label">${label}</div><div class="row"><span class="bias ${tone(b)}">${esc(b)}</span><b>${num(a.evidence)}/100</b></div><div class="small">${usable?'usable':'unavailable / stale'}</div></div>`}).join('')}
function laneCard(name,lane){let d=lane?.decision||{},dir=cap(d.direction||d.dominant_bias),ev=d.evidence||0,pos=lane.positions||[],lv=d.levels||{},ready=!!d.allowed&&lane.entry_timing_ready!==false,status=!d.allowed?'ENTRY BLOCKED':ready?'ENTRY READY':'CONFIRMING';let reason=(d.blocks||[])[0]||(lane.entry_timing_blocks||[])[0]||lane.status||'No block';let stop=lane.stop_mode==='INDIVIDUAL'?`Individual ${money(lane.individual_stop_loss_usd)} / position`:`Cumulative ${money(lane.cumulative_stop_loss_usd)}`;let econ=d.economic_advisor||{},last=lane.last_execution||{};return `<div class="card lane ${name.toLowerCase()}"><div class="row"><div><h2>${name}</h2><div class="small">${stop} · ${pos.length}/${lane.max_positions||2} open</div></div><span class="pill ${ready?'ok':'wait'}">${status}</span></div><div class="row"><span class="decision ${tone(dir)}">${dir}</span><span class="metric">${num(ev)}<small class="small">/100</small></span></div><div class="bar ${tone(dir)}"><i style="width:${Math.max(0,Math.min(100,ev))}%"></i></div><div class="kv"><div><span class="label">Signal stable</span><b>${num(lane.signal_age_seconds,1)}s / ${num(lane.signal_age_required_seconds,1)}s</b></div><div><span class="label">Strong sources</span><b>${d.strong_advisor_count||0} / 3</b></div><div><span class="label">Possible TP1 / TP2 / TP3</span><b>${num(lv.tp1)} / ${num(lv.tp2)} / ${num(lv.tp3)}</b></div><div><span class="label">Analysis SL</span><b>${num(d.stop_loss??lv.sl)}</b></div><div><span class="label">Analysis time (local)</span><b>${local(window.STATE?.updated_at)}</b></div><div><span class="label">Valid until (local)</span><b>${local(d.valid_until)}</b></div><div><span class="label">Combined lane P/L</span><b class="${Number(lane.floating_profit?.profit||0)>=0?'buy':'sell'}">${money(lane.floating_profit?.profit)}</b></div><div><span class="label">Economic V5</span><b class="${tone(econ.bias)}">${cap(econ.bias||'NEUTRAL')} ${num(Math.abs(econ.score||0),2)} · Q ${num(econ.quality||0,2)}</b></div></div><div class="reason"><b>${ready?'ENTRY CONDITIONS MET':'WHY NOT ENTERING'}</b><br>${esc(reason)}</div>${learnedCard(d)}<div class="small section"><b>Last execution:</b> ${esc(last.action||'-')} · ${esc(last.message||'No attempt yet.')}</div><div class="small section"><b>Exit management:</b> ${esc(lane.exit_policy||"legacy")} ? ${esc(lane.adaptive_exit?.reason||"Monitoring market thesis")}</div>${conscienceLine(lane)}<div class="label section">Advisor contribution</div><div class="advisors">${advisorCards(d)}</div></div>`}
function sourceCard(s){const x=s.source_intelligence||{},c=x.cross_market||{},f=x.funding||{};return `<div class="card section"><h2>Source intelligence</h2><div class="small">Currency policy: ${esc(x.cross_market_policy||'observe')} · Observation is not a validated prediction.</div><div class="reason">${esc(c.reason||'Cross-market data pending')}<br>Gold context: ${esc(c.gold_bias||'UNAVAILABLE')} · Dollar pressure ${num(c.dollar_pressure_z,2)} · Recent gold/dollar correlation ${num(c.prior_gold_dollar_correlation,2)}</div><table class="table"><tr><th>Official provider</th><th>Status</th><th>Retrieval age</th></tr>${Object.entries(x.providers||{}).map(([name,p])=>`<tr><td>${esc(name)}</td><td>${esc(p.status)} ${esc(p.error||'')}</td><td>${p.age_seconds==null?'unavailable':num(p.age_seconds,0)+'s'}</td></tr>`).join('')}</table><div class="small section">${f.effective_date?`Funding observation ${esc(f.effective_date)} · SOFR–EFFR ${num(f.sofr_minus_effr_bps,2)} bp · Daily context only`:'Funding observation unavailable'}</div></div>`}
function learnedCard(d){const a=d.learned_policy;if(!a)return '';return `<div class="reason"><b>Experimental learned forecast</b><br>${a.available?`Buy edge ${money(a.edge_usd?.BUY)} · Sell edge ${money(a.edge_usd?.SELL)}<br>Minimum entry edge ${money(a.minimum_edge_usd)} · ${a.forecast_bars} completed bars ahead<br>Historical validation PF ${num(a.validation?.profit_factor,2)} · Not approved for live trading`:esc(a.reason||'Unavailable')}</div>`}
function profitProtection(p){if(p.peak_profit_usd==null)return '';return `<div class="small">Peak P/L ${money(p.peak_profit_usd)} · ${p.profit_lock_armed?`Protect at ${money(p.profit_lock_trigger_usd)}`:`Profit protection arms at ${money(p.profit_lock_arm_usd)}`}</div>`}
function positions(items){if(!items.length)return '<div class="empty">No controlled positions open.</div>';return items.map(p=>`<div class="position"><div class="row"><b class="${tone(p.direction)}">${esc(p.horizon)} ${esc(p.direction)} #${esc(p.ticket)}</b><b class="${Number(p.profit)>=0?'buy':'sell'}">${money(p.profit)}</b></div><div class="small">${p.volume} lot · Entry ${num(p.entry_price)} · Current ${num(p.current_price)} · SL ${num(p.sl)}</div>${profitProtection(p)}</div>`).join('')}
function history(name,lane){let rows=(lane.closed_trades||[]).map(t=>`<tr><td>${local(t.closed_at||t.close_time)}</td><td class="${tone(t.direction)}">${esc(t.direction)}</td><td>${num(t.volume)}</td><td>${money(t.profit)}</td></tr>`).join('');return `<div class="card"><div class="row"><div><h2>${name}: Latest 30 closed trades</h2><div class="small">Rolling display; trading continues after 30.</div></div><button class="button" onclick="resetHistory('${name}')">Reset history</button></div><div class="scroll"><table class="table"><tr><th>Closed (local)</th><th>Side</th><th>Lot</th><th>Net P/L</th></tr>${rows||'<tr><td colspan="4" class="empty">No closed trades since reset.</td></tr>'}</table></div></div>`}
async function post(url){let r=await fetch(url,{method:'POST'});if(!r.ok)throw Error(await r.text());await refresh()}
async function resetHistory(lane){if(confirm(`Reset ${lane} displayed history? MT5 records remain intact.`))await post('/api/reset-history?lane='+encodeURIComponent(lane))}
async function resetLoss(){if(confirm('Reset the rolling 24h P/L circuit-breaker baseline?'))await post('/api/reset-loss')}
async function refresh(){try{let r=await fetch('/api/status?t='+Date.now(),{cache:'no-store'}),x=await r.json();window.STATE=x;let m=x.market||{},p=x.pnl||{},l=x.lanes||{},econ=x.economic_advisor_v5||{};$('badges').innerHTML=badge(x.status||'WAITING',x.status==='RUNNING'?'ok':'wait')+badge(x.paper_trading?'PAPER '+cap(x.learned_policy_mode):cap(x.mode||'DEMO'),'ok')+badge(`${m.symbol||'XAUUSD'} · ${m.session||'-'}`)+badge(`Cycle ${x.cycle||0}`)+badge(`Updated ${local(x.updated_at)}`);$('app').innerHTML=`${feedHealth(x)}<div class="grid4"><div class="card"><div class="label">Executable market</div><div class="metric">${num(m.bid)} <small class="small">bid</small></div><div class="small">Ask ${num(m.ask)} · Spread ${num(m.spread)}</div></div><div class="card"><div class="label">${x.paper_trading?"Paper account P/L":"Session P/L"}</div><div class="metric ${Number(p.total)>=0?'buy':'sell'}">${money(p.total)}</div><div class="small">Realized ${money(p.realized)} · Floating ${money(p.floating)}</div>${x.paper_trading?`<div class="small">Balance ${money(p.balance)} · Equity ${money(p.equity)}<br>Drawdown ${money(p.max_drawdown_usd)}</div>`:""}</div><div class="card"><div class="label">Data freshness</div><div>API bar: <b>${m.api_bar_age_seconds==null?'unavailable':num(m.api_bar_age_seconds,1)+'s'}</b></div><div>Tick: <b>${num(m.v3_tick_age_seconds,1)}s</b> · ${m.v3_tick_count||0} samples</div></div><div class="card"><div class="row"><div><div class="label">Risk controls</div><b>DEMO ONLY</b><div class="small">${x.positions?.length||0} / ${x.config?.max_positions_total||3} positions total | 0.01 lot each</div><div class="small">Budget ${money(x.config?.starting_capital_usd??100)} | SL ${money(x.config?.max_trade_risk_usd??5)} per position · Session loss stop ${x.config?.session_loss_stop_enabled===false?'off':money(x.config?.max_session_loss_usd??5)}</div></div><button class="button" onclick="resetLoss()">Reset 24h P/L baseline</button></div><div class="small section">Baseline: ${local(x.loss_baseline_at)}</div></div></div><div class="grid3 section">${laneCard('SCALP',l.SCALP||{})}${laneCard('INTRADAY',l.INTRADAY||{})}${laneCard('SWING',l.SWING||{})}</div><div class="two section"><div class="card"><h2>${x.paper_trading?"Simulated positions":"Live demo positions"}</h2>${positions(x.positions||[])}</div><div class="card"><h2>Economic context</h2><div class="small">V5 is context/veto only; it never sends orders.</div><table class="table"><tr><th>Horizon</th><th>Bias</th><th>Score</th><th>Quality</th></tr>${Object.entries(econ.horizons||{}).map(([k,v])=>`<tr><td>${k}</td><td class="${tone(v.bias)}">${cap(v.bias||'NEUTRAL')}</td><td>${num(v.score)}</td><td>${num(v.quality)}</td></tr>`).join('')}</table><div class="reason">${esc((x.news_risk?.block_reasons||[])[0]||'No active high-impact release block.')}</div></div></div>${sourceCard(x)}<div class="grid3 section">${history('SCALP',l.SCALP||{})}${history('INTRADAY',l.INTRADAY||{})}${history('SWING',l.SWING||{})}</div>`}catch(e){$('app').innerHTML=`<div class="card"><h2>Waiting for bot status...</h2><div class="small">${esc(e.message)}</div></div>`}}
refresh();setInterval(refresh,2000);
</script></body></html>'''

HTML = HTML.replace("let stop=lane.stop_mode==='INDIVIDUAL'?",
    "let stop=lane.stop_mode==='ANALYSIS'?'Candle-based stop / position':lane.stop_mode==='INDIVIDUAL'?")
HTML = HTML.replace('SL ${money(x.config?.max_trade_risk_usd??5)} per position',
    "${l.SCALP?.stop_mode==='ANALYSIS'?'Candle-based SL':`SL ${money(x.config?.max_trade_risk_usd??5)} per position`}")
HTML = HTML.replace('SCALP trading: up to 3 positions. INTRADAY and SWING: analysis only.',
    'SCALP trading: up to 3 positions. Higher-timeframe context analysed in the background.')
for hidden_lane in ('INTRADAY', 'SWING'):
    HTML = HTML.replace("${laneCard('" + hidden_lane + "',l." + hidden_lane + "||{})}", '')
    HTML = HTML.replace("${history('" + hidden_lane + "',l." + hidden_lane + "||{})}", '')
HTML = HTML.replace('Object.entries(econ.horizons||{}).map',
    "Object.entries(econ.horizons||{}).filter(([name])=>name==='SCALP').map")
HTML = HTML.replace('class="grid3 section"', 'class="section"')
HTML = HTML.replace('${esc(p.horizon)} ${esc(p.direction)}',
    "${p.horizon==='SCALP'?'SCALP':'Position'} ${esc(p.direction)}")
HTML = HTML.replace(
    "async function refresh(){try{let r=await fetch('/api/status?t='+Date.now(),{cache:'no-store'}),x=await r.json();window.STATE=x;",
    "let refreshPending=false,lastDashboardHtml='';async function refresh(){if(refreshPending)return;refreshPending=true;"
    "const controller=new AbortController(),deadline=setTimeout(()=>controller.abort(),8000);try{"
    "let r=await fetch('/api/status?t='+Date.now(),{cache:'no-store',signal:controller.signal});"
    "if(!r.ok)throw Error('Status API HTTP '+r.status);let x=await r.json();"
    "if(!x||typeof x!=='object'||Array.isArray(x)||!x.status)throw Error('Invalid status response');"
    "window.STATE=x;$('connection-warning').innerHTML='';")
HTML = HTML.replace(
    "}catch(e){$('app').innerHTML=`<div class=\"card\"><h2>Waiting for bot status...</h2><div class=\"small\">${esc(e.message)}</div></div>`}}",
    ";lastDashboardHtml=$('app').innerHTML;}catch(e){"
    "$('badges').innerHTML=badge('DASHBOARD CONNECTION LOST','wait');"
    "$('connection-warning').innerHTML=`<div class=\"card\"><h2>Status connection interrupted — retrying</h2>"
    "<div class=\"small\">${lastDashboardHtml?'Displayed values are cached, NOT live. Last update: '+esc(local(window.STATE?.updated_at))+'. ':''}"
    "Open this dashboard at http://127.0.0.1:8765/ and keep the bot running. ${esc(e.name==='AbortError'?'Status request timed out':e.message)}</div></div>`;"
    "$('app').innerHTML=lastDashboardHtml||'<div class=\"card\">Waiting for the first valid bot status. Retrying automatically.</div>';"
    "}finally{clearTimeout(deadline);refreshPending=false;}}")
HTML = HTML.replace('${learnedCard(d)}',
    '<div class="small section"><b>Entry engine:</b> ${esc(d.entry_mode||"unknown")} '
    '· ${esc(d.entry_timeframe||"M1")} · ${ready?"ALL ENTRY CHECKS PASSED":"NOT AUTHORIZED TO OPEN"}'
    '${d.advisor1_context?`<br>Advisor 1: ${esc(d.advisor1_context.direction)} '
    '${num(d.advisor1_context.evidence)}/100 — CONTEXT ONLY, not an order instruction`:""}</div>${learnedCard(d)}')
HTML = HTML.replace('refresh();setInterval(refresh,2000);',
    'async function pollDashboard(){await refresh();setTimeout(pollDashboard,2000)}pollDashboard();')
HTML = HTML.replace('${learnedCard(d)}',
    '${d.regime_research?`<div class="small section"><b>Strategy research (NO ORDERS):</b> '
    '${esc(d.regime_research.strategy)} / ${esc(d.regime_research.bias)}'
    '<br>${esc((d.regime_research.blocks||[]).join("; ")||"Candidate found; forward validation only")}'
    '<br>Historical test: no positive expectancy demonstrated after costs.</div>`:""}${learnedCard(d)}')
HTML = HTML.replace('${learnedCard(d)}',
    '${d.market_schedule?.available?`<div class="small section"><b>Gold liquidity context:</b> '
    '${esc((d.market_schedule.active_centres||[]).join(" / ")||"Outside modelled centre windows")}'
    '${d.market_schedule.london_new_york_overlap?" · London/New York overlap":""}'
    '<br>Next regular London gold auction: ${esc(local(d.market_schedule.next_regular_lbma_auction_utc))}'
    '${d.market_schedule.rollover_watch?"<br>Rollover watch: verify broker spread and permissions":""}'
    '<br>Context only; broker hours and holidays are not inferred from these windows.</div>`:""}${learnedCard(d)}')
HTML = HTML.replace('${feedHealth(x)}',
    '${x.config?.research_entry_hold?`<div class="card section"><h2>Research hold: NEW ENTRIES PAUSED</h2>'
    '<div class="small">The bot is connected. Existing position exits and broker stops remain active. '
    'The tested strategies did not establish positive expectancy after costs; this is not a launch failure.</div></div>`:""}'
    '${feedHealth(x)}')
HTML = HTML.replace('${learnedCard(d)}',
    '${d.orbit_research?.available?`<div class="small section"><b>ORBIT paper observer:</b> '
    '${esc(d.orbit_research.observer_state)} / ${esc(d.orbit_research.last_signal?.bias||"WAIT")}'
    '<br>${esc((d.orbit_research.last_signal?.blocks||[]).join("; "))}'
    '<br>${d.orbit_research.paper_summary?.trades||0} simulated closes, '
    'net ${num(d.orbit_research.paper_summary?.net_price)} price units. NO BROKER ORDERS.</div>`:""}${learnedCard(d)}')


HTML = HTML.replace('${learnedCard(d)}',
    '${d.multi_engine_research?.available?`<div class="small section"><b>A/B/C research - NO ORDERS:</b> '
    '${esc(d.multi_engine_research.evaluation)}'
    '${Object.entries(d.multi_engine_research.engines||{}).map(([engine,result])=>'
    '`<br>${esc(engine)}: ${esc(result.score?.state||"WAIT")} / ${result.summary?.trades||0} paper closes / '
    'net ${num(result.summary?.net_price)} price units`).join("")}'
    '<br>Paper scores never authorize broker entries.</div>`:""}${learnedCard(d)}')

HTML = HTML.replace('${learnedCard(d)}',
    '${d.trigger_funnel?`<div class="small section"><b>Unique-setup funnel:</b> '
    '${num(d.trigger_funnel.window_unique_setups,0)} candidates; '
    '${num(d.trigger_funnel.request_attempts,0)} requests; '
    '${num(d.trigger_funnel.reported_done_setups,0)} reported DONE. '
    'Local blocks are not broker rejections; no acceptance quota.</div>`:""}'
    '${d.graded_trigger?.available?`<div class="small section"><b>Graded research — NO ORDERS:</b> '
    '${esc(d.graded_trigger.suggested_tier)} · heuristic ${num(d.graded_trigger.heuristic_score)}/100. '
    'Fixed lot unchanged; no trained probability.</div>`:""}${learnedCard(d)}')


HTML = HTML.replace('function feedHealth(x){', r'''
function botPositions(items){return (items||[]).map(p=>`<div class="position"><div class="row"><b class="${tone(p.direction)}">${esc(p.direction)} #${esc(p.ticket)}</b><b>${money(p.profit)}</b></div><div class="small">${num(p.volume)} lot · Entry ${num(p.entry_price)} · Current ${num(p.current_price)} · SL ${num(p.sl)}${p.source_position_id?'<br>Linked main #'+esc(p.source_position_id):''}</div></div>`).join('')||'<div class="empty">No positions open.</div>'}
function bothBots(x){const inv=x.inverse||{},tr=inv.trading||{},p=x.pnl||{},ip=tr.pnl||{},live=inv.fresh&&inv.state==='RUNNING',known=tr.available&&ip.available!==false;
 const rows=(tr.closed_trades||[]).map(t=>`<tr><td>${local(t.closed_at)}</td><td>${esc(t.direction)} #${esc(t.position_id)}</td><td>${money(t.profit)}</td></tr>`).join('');
 return `<div class="two section"><div class="card"><div class="row"><h2>Main demo bot</h2>${badge(x.status||'UNKNOWN')}</div><div class="metric">${money(p.total)}</div><div class="small">Main session/dashboard baseline · Realized ${money(p.realized)} · Floating ${money(p.floating)}</div><div class="label section">Main positions · ${x.positions?.length||0} / ${x.lanes?.SCALP?.max_positions||2}</div>${botPositions(x.positions||[])}</div><div class="card"><div class="row"><h2>Inverse demo bot</h2>${badge(inv.state||'UNAVAILABLE',live?'ok':'wait')}</div>${known?`<div class="metric">${money(ip.total)}</div><div class="small">Realized closed ${money(ip.realized)} · Open net ${money(ip.floating)}<br>${esc(tr.scope)}</div>`:'<div class="empty">Inverse P/L unavailable: '+esc(tr.reason||inv.reason||'Waiting for broker reporting')+'</div>'}${!live?'<div class="reason">Inverse values are not live; check executor status.</div>':''}<div class="small">Heartbeat age ${inv.age_seconds==null?'-':num(inv.age_seconds,1)+'s'} · Broker report ${local(tr.updated_at)} · Pending ${inv.detail?.pending_inverse_orders??'unknown'}</div>${inv.error?'<div class="reason">'+esc(inv.error)+'</div>':''}<div class="label section">Inverse positions · ${tr.positions?.length||0} / 2</div>${botPositions(tr.positions||[])}<h3>Inverse: latest 30 closed trades</h3><div class="scroll"><table class="table"><tr><th>Closed (local)</th><th>Side / ticket</th><th>Net P/L</th></tr>${rows||'<tr><td colspan="3">No closed inverse trades reported.</td></tr>'}</table></div></div></div>`}
function pairedCard(x){const tr=x.inverse?.trading||{},p=tr.paired||{};return `<h2>Matched-pair experiment</h2>${p.available&&tr.available?`<div class="metric">${money(p.combined_net)}</div><div>Main ${money(p.main_net)} + Inverse ${money(p.inverse_net)}</div><div class="small">${num(p.linked_sources,0)} linked source positions · ${esc(p.scope)}</div>`:'<div class="empty">Matched-pair P/L unavailable.</div>'}<div class="small section">Do not add the main session figure to inverse history: their baselines differ. Pairs include costs; opposite trades are not guaranteed to cancel losses.</div>`}
function feedHealth(x){''')
HTML = HTML.replace('${feedHealth(x)}', '${bothBots(x)}${feedHealth(x)}')
HTML = HTML.replace('"Session P/L"', '"Main session P/L"')
HTML = HTML.replace('${x.positions?.length||0} / ${x.config?.max_positions_total||3} positions total',
    '${x.positions?.length||0} main + ${x.inverse?.fresh&&x.inverse?.trading?.available?x.inverse.trading.positions.length:"?"} inverse / ${x.config?.max_positions_total||3} combined slots')
HTML = HTML.replace('<h2>${x.paper_trading?"Simulated positions":"Live demo positions"}</h2>${positions(x.positions||[])}',
    '${pairedCard(x)}')
HTML = HTML.replace('SCALP trading: up to 3 positions. Higher-timeframe context analysed in the background.',
    'Main + inverse DEMO executors · 0.01 lot · up to 4 positions combined. Advisor1 remains analysis only.')
HTML = HTML.replace('<h2>Matched-pair experiment</h2>${p.available',
    '<h2>Matched-pair experiment</h2>${!x.inverse?.fresh||x.inverse?.state!=="RUNNING"?'
    '\'<div class="reason">Inverse reporting is stopped or stale; these are cached results, not live totals.</div>\':""}${p.available')
HTML = HTML.replace('<div id="app"', '<div class="section"><button class="button" onclick="resetBothDisplays()">Reset BOTH bots: P/L + history</button><span class="small"> Display only; open trades and risk limits unchanged.</span></div><div id="app"')
HTML = HTML.replace('function botPositions(items){',
    'async function resetBothDisplays(){if(confirm("Reset BOTH displayed profit/loss and closed histories? Open positions, MT5 records and risk controls stay unchanged."))await post("/api/reset-both-displays")}\nfunction botPositions(items){')
HTML = HTML.replace('Main session/dashboard baseline', '${esc(x.display_scope||"Main session/dashboard baseline")}')
HTML = HTML.replace('"Main session P/L"', '"Main displayed P/L"')
HTML = HTML.replace('<div class="metric">${money(p.total)}</div>', '<div class="metric ${Number(p.total)>=0?"buy":"sell"}">${money(p.total)}</div>')
HTML = HTML.replace('<div class="metric">${money(ip.total)}</div>', '<div class="metric ${Number(ip.total)>=0?"buy":"sell"}">${money(ip.total)}</div>')
HTML = HTML.replace('<div class="metric">${money(p.combined_net)}</div>', '<div class="metric ${Number(p.combined_net)>=0?"buy":"sell"}">${money(p.combined_net)}</div>')
HTML = HTML.replace('<td>${money(t.profit)}</td>', '<td class="${Number(t.profit)>=0?"buy":"sell"}">${money(t.profit)}</td>')
HTML = HTML.replace('<b>${money(p.profit)}</b>', '<b class="${Number(p.profit)>=0?"buy":"sell"}">${money(p.profit)}</b>')
HTML = HTML.replace('Do not add the main session figure to inverse history: their baselines differ.',
    'The shared reset clears displayed P/L and histories for both bots and matched pairs. MT5 records and risk controls are retained.')
HTML = HTML.replace('''<button class="button" onclick="resetHistory('${name}')">Reset history</button>''', '')
HTML = HTML.replace('Realized closed ${money(ip.realized)} · Open net ${money(ip.floating)}',
    'Realized closed <span class="${Number(ip.realized)>=0?"buy":"sell"}">${money(ip.realized)}</span> · '
    'Floating change <span class="${Number(ip.floating)>=0?"buy":"sell"}">${money(ip.floating)}</span>')
HTML = HTML.replace('Realized ${money(p.realized)} · Floating ${money(p.floating)}',
    'Realized <span class="${Number(p.realized)>=0?"buy":"sell"}">${money(p.realized)}</span> · '
    'Floating change <span class="${Number(p.floating)>=0?"buy":"sell"}">${money(p.floating)}</span>')


HTML = HTML.replace('<span class="label">Strong sources</span><b>${d.strong_advisor_count||0} / 3</b>',
    '<span class="label">Agreeing strong sources (75+/100)</span><b>${d.strong_advisor_count||0} / 3</b>'
    '${d.entry_mode==="THREE_SOURCE_VOTE"?`<div class="small">Position allowance: '
    '${d.source_position_limit??0} · Open: ${pos.length}<br>'
    '1 source = 1 position · 2 = 2 · 3 = 3 (risk checks apply)</div>`:""}')
HTML = HTML.replace('Advisor 1: ${esc(d.advisor1_context.direction)}',
    'Legacy context: ${esc(d.advisor1_context.direction)}')
HTML = HTML.replace(' · ${pos.length}/${lane.max_positions||2} open',
    ' · ${pos.length}/${d.source_position_limit??lane.max_positions??2} open / permitted')

# Main-only display; inverse records remain on disk for audit/history.
from config import gold_inverse_settings as inverse_settings
if not inverse_settings.EXECUTOR_ENABLED:
    import re
    HTML = HTML.replace('/api/reset-both-displays', '/api/reset-main-display')
    HTML = re.sub(r'function bothBots\(x\).*?function feedHealth\(x\)\{',
        'function bothBots(x){const ps=x.positions||[],last=x.lanes?.SCALP?.last_execution||{};'
        'return `<div class="card section"><div class="row"><h2>Main bot: live positions (${ps.length})</h2>'
        '<span class="small">Updated ${local(x.updated_at)}</span></div>${botPositions(ps)}'
        '<div class="small section">Last action: ${esc(last.action||"None")} · ${esc(last.message||"Waiting")}'
        '<br>Closed trades move to SCALP history below.</div></div>`}\n'
        'function pairedCard(x){return `<h2>Main demo positions</h2>${botPositions(x.positions||[])}`}\n'
        'function feedHealth(x){', HTML, flags=re.S)
    HTML = HTML.replace('Main + inverse DEMO executors', 'Main DEMO executor')
    HTML = HTML.replace('Reset BOTH bots: P/L + history', 'Reset displayed P/L + history')
    HTML = HTML.replace('Reset BOTH displayed profit/loss and closed histories?',
                        'Reset displayed profit/loss and closed history?')
    HTML = re.sub(r'\$\{x.positions\?\.length\|\|0\} main \+ .*?combined slots',
                  '${x.positions?.length||0} / ${x.config?.max_positions_total||3} positions', HTML)


HTML = HTML.replace('function feedHealth(x){',
    'function strategyValidation(x){const v=x.strategy_validation;if(!v)return "";'
    'return `<div class="card section"><b>Strategy validation: ${esc(v.state)}</b>'
    '<div class="reason">${esc(v.reason)}</div>'
    '<div class="small">Candidate model: ${esc(v.model_role)} · '
    'Historical test window: ${esc(v.historical_capture)}</div></div>`}\nfunction feedHealth(x){')
HTML = HTML.replace('${feedHealth(x)}', '${strategyValidation(x)}${feedHealth(x)}')


class DashboardHandler(BaseHTTPRequestHandler):
    def _send(self, body: bytes, content_type: str = "application/json", status: int = 200) -> None:
        compressed = False
        for encoding in self.headers.get('Accept-Encoding', '').split(','):
            parts = [part.strip() for part in encoding.split(';')]
            if parts[0].lower() != 'gzip':
                continue
            quality = 1.0
            try:
                for parameter in parts[1:]:
                    if parameter.startswith('q='):
                        quality = float(parameter[2:])
            except ValueError:
                quality = 0.0
            if quality > 0 and len(body) >= 1024:
                body = gzip.compress(body, mtime=0)
                compressed = True
            break
        self.send_response(status)
        self.send_header("Content-Type", f"{content_type}; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        self.send_header('Vary', 'Accept-Encoding')
        if compressed:
            self.send_header('Content-Encoding', 'gzip')
        self.send_header("Access-Control-Allow-Origin", "http://127.0.0.1")
        self.end_headers()
        try:
            self.wfile.write(body)
        except (BrokenPipeError, ConnectionResetError):
            return

    def do_GET(self) -> None:
        path = urlparse(self.path).path
        if path == "/":
            self._send(HTML.encode("utf-8"), "text/html")
        elif path == "/api/advisor":
            from services.dashboard.gold_advisor_web import read_advisor
            self._send(json.dumps(read_advisor()).encode("utf-8"))
        elif path in {"/advisor", "/advisor/", "/advisor.js", "/advisor.css", "/style.css"}:
            asset = "advisor.html" if path in {"/advisor", "/advisor/"} else path[1:]
            content_type = "text/html" if asset.endswith(".html") else "text/javascript" if asset.endswith(".js") else "text/css"
            self._send((Path(__file__).parent / "gold_scalp_assets" / asset).read_bytes(), content_type)
        elif path in {"/api/status", "/status"}:
            try:
                self._send(json.dumps(read_dashboard_status()).encode('utf-8'))
            except FileNotFoundError:
                self._send(b'{"status":"WAITING","status_message":"Bot has not written status yet."}')
            except OSError:
                self._send(b'{"error":"Status file temporarily unavailable; retry."}', status=503)
            except (ValueError, TypeError):
                self._send(b'{"error":"Status data temporarily invalid; retry."}', status=503)
        elif path == "/health":
            self._send(b'{"ok":true}')
        else:
            self._send(b'{"error":"not found"}', status=404)

    def do_POST(self) -> None:
        parsed = urlparse(self.path)
        try:
            if parsed.path == "/api/reset-history":
                lane = parse_qs(parsed.query).get("lane", [""])[0]
                payload = reset_history(lane)
            elif parsed.path == '/api/reset-both-displays':
                payload = reset_both_displays(read_dashboard_status())
            elif parsed.path == '/api/reset-main-display':
                payload = reset_main_display(read_dashboard_status())
            elif parsed.path == "/api/reset-loss":
                payload = reset_loss_baseline()
            else:
                self._send(b'{"error":"not found"}', status=404)
                return
            self._send(json.dumps(payload).encode("utf-8"))
        except ValueError as error:
            self._send(json.dumps({"error": str(error)}).encode("utf-8"), status=400)
        except OSError as error:
            self._send(json.dumps({"error": str(error)}).encode("utf-8"), status=500)

    def log_message(self, *_args: object) -> None:
        return


def open_dashboard_url(port: int = 8765) -> str:
    url = f"http://127.0.0.1:{int(port)}/?run={int(time.time() * 1000)}"
    if os.name == "nt" and hasattr(os, "startfile"):
        try:
            os.startfile(url)  # type: ignore[attr-defined]
            return url
        except OSError:
            pass
    webbrowser.open(url, new=0, autoraise=True)
    return url


def start_dashboard_server(host: str = "127.0.0.1", port: int = 8765,
                           open_browser: bool = True) -> tuple[ThreadingHTTPServer, str]:
    server = ThreadingHTTPServer((host, int(port)), DashboardHandler)
    threading.Thread(target=server.serve_forever, daemon=True, name="gold-dashboard").start()
    actual_port = int(server.server_address[1])
    base_url = f"http://{host}:{actual_port}"
    deadline = time.monotonic() + 3.0
    while time.monotonic() < deadline:
        try:
            with urlopen(base_url + "/health", timeout=0.5) as response:
                if response.status == 200:
                    break
        except Exception:
            time.sleep(0.05)
    else:
        server.shutdown()
        server.server_close()
        raise OSError("Dashboard HTTP server did not become ready.")
    if open_browser:
        open_dashboard_url(actual_port)
    return server, base_url
