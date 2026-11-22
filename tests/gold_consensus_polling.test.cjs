const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');

const html = fs.readFileSync(0, 'utf8');
const source = html.match(/<script>([\s\S]*?)<\/script>/)[1].replace('pollDashboard();', '');
const elements = new Map();
const document = {getElementById(id) {
  if (!elements.has(id)) elements.set(id, {innerHTML: ''});
  return elements.get(id);
}};
let nextFetch;
let calls = 0;
const context = vm.createContext({document, window: {}, AbortController, console,
  setTimeout() { return 1; }, clearTimeout() {},
  fetch(...args) { calls += 1; return nextFetch(...args); }});
vm.runInContext(source, context);
const snapshot = cycle => ({status: 'RUNNING', mode: 'demo', cycle,
  updated_at: '2026-10-20T00:20:00Z', lanes: {}, positions: []});
const response = cycle => ({ok: true, json: async () => snapshot(cycle)});

async function run() {
  nextFetch = async () => response(1);
  await context.refresh();
  const original = document.getElementById('app').innerHTML;
  assert.match(original, /Executable market/);
  assert.equal(context.window.STATE.cycle, 1);

  nextFetch = async () => { throw new TypeError('Failed to fetch'); };
  await context.refresh();
  assert.equal(document.getElementById('app').innerHTML, original);
  assert.match(document.getElementById('connection-warning').innerHTML, /NOT live/);
  assert.match(document.getElementById('badges').innerHTML, /CONNECTION LOST/);

  nextFetch = async () => response(2);
  await context.refresh();
  assert.equal(document.getElementById('connection-warning').innerHTML, '');
  assert.equal(context.window.STATE.cycle, 2);

  nextFetch = async () => ({ok: false, status: 503});
  await context.refresh();
  assert.match(document.getElementById('connection-warning').innerHTML, /HTTP 503/);
  assert.equal(context.window.STATE.cycle, 2);

  let resolveFetch;
  nextFetch = () => new Promise(resolve => { resolveFetch = resolve; });
  const before = calls;
  const pending = context.refresh();
  await context.refresh();
  assert.equal(calls, before+1);
  resolveFetch(response(3));
  await pending;
  assert.equal(context.window.STATE.cycle, 3);
  assert.equal(document.getElementById('connection-warning').innerHTML, '');
  nextFetch = async () => ({ok: true, json: async () => ({...snapshot(4),
    positions: [{ticket: 12345, direction: 'BUY', volume: .01, entry_price: 4000, current_price: 4001, sl: 3998, profit: 1}],
    inverse: {state: 'RUNNING', fresh: true, age_seconds: 1, detail: {pending_inverse_orders: 0},
      trading: {available: true, pnl: {realized: .87, floating: 0, total: .87},
        closed_trades: [{closed_at: '2026-10-23T06:00:00Z', direction: 'SELL', position_id: 20, profit: -2.5}],
        positions: [{ticket: 20, source_position_id: 10, direction: 'SELL', volume: .01, entry_price: 4000, current_price: 3999, sl: 4002, profit: 1}],
        paired: {available: true, main_net: -1.74, inverse_net: .87, combined_net: -.87, linked_sources: 1}}}})});
  await context.refresh();
  const dual = document.getElementById('app').innerHTML;
  if (html.includes('Main bot: live positions')) {
    assert.match(dual, /Main bot: live positions \(1\)/);
    assert.match(dual, /BUY #12345/);
    assert.doesNotMatch(dual, /Inverse demo bot/);
    assert.doesNotMatch(dual, /Matched-pair experiment/);
    assert.match(html, /Reset displayed P\/L \+ history/);
  } else {
  assert.match(dual, /Main demo bot/);
  assert.match(dual, /Inverse demo bot/);
  assert.match(dual, /Linked main #10/);
  assert.match(dual, /Matched-pair experiment/);
  assert.match(dual, /-\$0\.87/);
  assert.match(dual, /class="sell">-\$2\.50/);
  assert.match(html, /Reset BOTH bots: P\/L \+ history/);
  }
  nextFetch = async () => ({ok:true,json:async()=>({...snapshot(5),strategy_validation:{
    state:'FAILED_AFTER_COST_REPLAY',reason:'Entries paused after negative tests',model_role:'SHADOW_ONLY',
    historical_capture:'Frozen previous session'}})});
  await context.refresh();
  assert.match(document.getElementById('app').innerHTML,/FAILED_AFTER_COST_REPLAY/);
  assert.match(document.getElementById('app').innerHTML,/Entries paused after negative tests/);
  console.log('PASS: initial render, offline cache/stale warning, recovery, HTTP failure, no overlapping polling');
}
run().catch(error => { console.error(error); process.exitCode = 1; });
