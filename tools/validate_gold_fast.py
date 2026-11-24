"""Read-only demo cost calibration and chronological S30/M1 pattern screening."""
import argparse
from bisect import bisect_left, bisect_right
from datetime import datetime, timedelta, timezone
import json
import math
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from config import gold_consensus_settings as settings
from services.market_data.gold_broker_clock import to_broker_time
from services.research.gold_s30_shadow import s30_observation
from services.utils.atomic_json import atomic_write_json


def percentile(values, fraction=.95):
    return sorted(values)[max(0, math.ceil(len(values)*fraction)-1)] if values else None


def calibrate(deals, journal, contract, *, minimum=30):
    requests = {}
    for row in journal:
        if row.get('success') and row.get('record_type') in {'HORIZON_OPEN', 'CLOSE'}:
            requests[int(row.get('deal') or 0)] = row
    groups = {}
    for deal in deals:
        if deal['symbol'] == settings.SYMBOL and deal['magic'] == 631011:
            groups.setdefault(deal['position_id'], []).append(deal)
    fees, slips, latencies = [], [], []
    for group in groups.values():
        entries = [deal for deal in group if deal['entry'] == 0]
        exits = [deal for deal in group if deal['entry'] == 1]
        if len(group) != 2 or len(entries) != 1 or len(exits) != 1:
            continue
        opened, closed = entries[0], exits[0]
        if opened['type'] not in (0, 1) or closed['type'] != 1-opened['type']:
            continue
        if any(abs(deal['volume']-.01) > 1e-8 or deal.get('swap', 0) != 0 for deal in group):
            continue
        expected = (1 if opened['type'] == 0 else -1)*(closed['price']-opened['price'])*contract*.01
        if abs(expected-closed['profit']) > .02:
            continue
        pair_slip, pair_latency = [], []
        for deal in (opened, closed):
            request = requests.get(deal['ticket'], {})
            price = request.get('entry_price') if deal['entry'] == 0 else request.get('requested_price')
            latency = request.get('execution_metrics', {}).get('order_send_elapsed_ms')
            if not isinstance(price, (int, float)) or not math.isfinite(price) or price <= 0:
                break
            if not isinstance(latency, (int, float)) or not math.isfinite(latency) or latency < 0:
                break
            pair_slip.append(max(0., (1 if deal['type'] == 0 else -1)*(deal['price']-price)))
            pair_latency.append(latency)
        if len(pair_slip) != 2:
            continue
        fees.append(sum(max(0., -deal.get('commission', 0)-deal.get('fee', 0)) for deal in group)/(contract*.01))
        slips.append(sum(pair_slip))
        latencies.extend(pair_latency)
    ready = len(fees) >= minimum
    return dict(available=ready, reconciled_pairs=len(fees), minimum_pairs=minimum,
                commission_price=percentile(fees) if ready else None,
                slippage_price=percentile(slips) if ready else None,
                order_send_p95_ms=percentile(latencies),
                reason='Historical demo p95 estimates, not guaranteed future costs' if ready else
                       'Insufficient matched complete demo fills; costs remain unknown')


def m1_direction(ticks, now):
    end = int(now//60)*60
    bodies = []
    for start in range(end-180, end, 60):
        group = [tick for tick in ticks if start <= tick['timestamp'] < start+60]
        bounds = [start]+[tick['timestamp'] for tick in group]+[start+60]
        if len(group) < 2 or max(right-left for left, right in zip(bounds, bounds[1:])) > 5:
            return 'WAIT', end
        bodies.append((group[-1]['bid']+group[-1]['ask']-group[0]['bid']-group[0]['ask'])/2)
    return ('BUY' if all(body > 0 for body in bodies) else
            'SELL' if all(body < 0 for body in bodies) else 'WAIT'), end


def screen(ticks, costs, *, latency_seconds=1.):
    results = dict(S30=[], M1_PATTERN_BENCHMARK=[])
    if not costs['available']:
        return dict(available=False, reason=costs['reason'], execution_enabled=False)
    stamps = [tick['timestamp'] for tick in ticks]
    seen = {name: set() for name in results}
    blockers = {}
    pattern_cycles = 0
    for now in range(math.ceil(stamps[0]+240), math.floor(stamps[-1]-61)):
        window = ticks[bisect_left(stamps, now-240):bisect_right(stamps, now)]
        if not window:
            continue
        observation = s30_observation(window, now=now, commission_price=costs['commission_price'],
                                      slippage_price=costs['slippage_price'])
        fast = observation.get('fast_candidate', {})
        pattern_cycles += bool(fast.get('pattern_ready'))
        for reason in fast.get('blocks', []) or ([observation['reason']] if not observation.get('available') else []):
            blockers[reason] = blockers.get(reason, 0)+1
        direction, end = m1_direction(window, now)
        candidates = dict(S30=(fast.get('direction', 'WAIT'), fast.get('setup_id'),
                               fast.get('research_candidate', False)),
                          M1_PATTERN_BENCHMARK=(direction, f'{end}:{direction}', direction != 'WAIT'))
        for name, (bias, identity, allowed) in candidates.items():
            if not allowed or identity in seen[name]:
                continue
            seen[name].add(identity)
            entry_index = bisect_left(stamps, now+latency_seconds)
            exit_index = bisect_left(stamps, now+latency_seconds+60)
            if exit_index >= len(ticks):
                continue
            entry, exit_tick = ticks[entry_index], ticks[exit_index]
            if entry['timestamp']-now-latency_seconds > 3 or exit_tick['timestamp']-now-latency_seconds-60 > 3:
                continue
            gross = exit_tick['bid']-entry['ask'] if bias == 'BUY' else entry['bid']-exit_tick['ask']
            net = gross-costs['commission_price']-costs['slippage_price']
            results[name].append(dict(decision_epoch=now, direction=bias, setup_id=identity,
                                      entry_epoch=entry['timestamp'], exit_epoch=exit_tick['timestamp'],
                                      net_price=net))
    summary = {}
    for name, trades in results.items():
        values = [trade['net_price'] for trade in trades]
        summary[name] = dict(candidates=len(values), net_price_sum=sum(values),
                             mean_net_price=sum(values)/len(values) if values else None,
                             wins=sum(value > 0 for value in values),
                             extra_cost_stress={str(extra): sum(value-extra for value in values)
                                                for extra in (.1, .25, .5)})
    return dict(available=True, execution_enabled=False, horizon_seconds=60,
                pattern_ready_cycles=pattern_cycles, blocker_cycles=blockers,
                latency_seconds=latency_seconds, summary=summary, observations=results,
                limitations=['Pattern-only screen, not production Advisor 1 or dynamic exit backtest.',
                    'Overlapping markouts are correlated and do not enforce portfolio capacity.',
                    'Historical cost calibration is not a chronological out-of-sample validation.',
                    'Bid/ask includes spread once; net_price subtracts estimated fees and slippage once.',
                    'No entry, position sizing or news-filter activation is authorized by this screen.'])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--hours', type=float, default=2.)
    args = parser.parse_args()
    if not 0 < args.hours <= 24:
        parser.error('--hours must be in (0, 24]')
    import MetaTrader5 as mt5
    if not mt5.initialize(timeout=10000):
        raise RuntimeError('MT5 initialization failed')
    try:
        account, info = mt5.account_info(), mt5.symbol_info(settings.SYMBOL)
        if account is None or account.trade_mode != mt5.ACCOUNT_TRADE_MODE_DEMO or account.currency != 'USD':
            raise RuntimeError('Verified USD demo required')
        if info is None or not info.trade_contract_size > 0:
            raise RuntimeError('Valid contract size required')
        now = datetime.now(timezone.utc)
        history = mt5.history_deals_get(to_broker_time(now-timedelta(days=14)), to_broker_time(now))
        rows = mt5.copy_ticks_range(settings.SYMBOL, to_broker_time(now-timedelta(hours=args.hours)),
                                   to_broker_time(now), mt5.COPY_TICKS_ALL)
        if history is None or rows is None or len(rows) == 0:
            raise RuntimeError('Broker history unavailable')
        journal = []
        with (ROOT/settings.JOURNAL_PATH).open(encoding='utf-8') as handle:
            for line in handle:
                try:
                    journal.append(json.loads(line))
                except ValueError:
                    pass
        costs = calibrate([deal._asdict() for deal in history], journal, float(info.trade_contract_size))
        ticks = []
        for row in rows:
            stamp = float(row['time_msc'])/1000-settings.MT5_SERVER_UTC_OFFSET_SECONDS
            bid, ask = float(row['bid']), float(row['ask'])
            if all(math.isfinite(value) for value in (stamp, bid, ask)) and bid > 0 and ask >= bid and stamp <= now.timestamp():
                ticks.append(dict(timestamp=stamp, bid=bid, ask=ask))
        ticks.sort(key=lambda tick: tick['timestamp'])
        if not ticks:
            raise RuntimeError('No usable historical quotes')
        latency = max(1., (costs['order_send_p95_ms'] or 0)/1000)
        report = dict(as_of=now.isoformat(), read_only=True, symbol=settings.SYMBOL,
                      currency=account.currency, volume=.01, ticks=len(ticks), costs=costs,
                      screening=screen(ticks, costs, latency_seconds=latency),
                      activation_allowed=False, decision='KEEP_FAST_SHADOW_ONLY')
        args.output.parent.mkdir(parents=True, exist_ok=True)
        atomic_write_json(str(args.output), report, indent=2)
        print(json.dumps({key: value if key != 'screening' else
                          {name: item for name, item in value.items() if name != 'observations'}
                          for key, value in report.items()}, indent=2))
    finally:
        mt5.shutdown()


if __name__ == '__main__':
    main()
