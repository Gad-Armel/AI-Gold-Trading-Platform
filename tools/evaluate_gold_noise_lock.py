"""Offline paired profit-lock comparison on fixed actual entries; never uses MT5."""
import argparse
from collections import Counter
from datetime import datetime, timezone
import json
import math
from pathlib import Path
import sys

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from services.research.gold_profit_lock import profit_lock_exit

HORIZON_SECONDS = 180.
LATENCY_SECONDS = .35
MAX_GAP_SECONDS = 3.
CONTROL = dict(profit_lock_arm_usd=1., profit_lock_retained_fraction=.8)
CHALLENGER = dict(CONTROL, profit_lock_noise_spreads=1., profit_lock_min_retained_usd=.30)


def epoch(value):
    stamp = datetime.fromisoformat(value)
    if stamp.tzinfo is None:
        raise ValueError('Trade timestamps must be timezone-aware')
    return stamp.timestamp()


def summarize(rows):
    nets = [r['net_usd'] for r in rows]
    return dict(trades=len(nets), net_usd=sum(nets),
        wins=sum(v > 0 for v in nets), losses=sum(v < 0 for v in nets),
        mean_net_usd=float(np.mean(nets)) if nets else None,
        mean_hold_seconds=float(np.mean([r['hold_seconds'] for r in rows])) if rows else None,
        exit_reasons=dict(Counter(r['reason'] for r in rows)))


def quote_index(stamps, target):
    idx = int(np.searchsorted(stamps, target, side='left'))
    if idx == len(stamps) or stamps[idx]-target > MAX_GAP_SECONDS:
        return None
    return idx


def scenario(trade, stamps, bids, asks, first, final, *, config, contract_size, cost_usd):
    opened = epoch(trade['opened_utc'])
    sign = 1 if trade['direction'] == 'BUY' else -1
    entry = float(trade['entry_price'])
    exposure = float(trade['volume'])*contract_size
    stop = entry-sign*float(trade['initial_stop_distance'])
    position = dict(ticket=int(trade['position_id']), direction=trade['direction'],
                    entry_price=entry, volume=float(trade['volume']), sl=stop)
    state = {}
    pending_at = None
    decision_at = None
    chosen = None
    reason = None
    for idx in range(first, final+1):
        stamp = float(stamps[idx])
        price = float(bids[idx] if sign == 1 else asks[idx])
        # Broker-side initial SL remains independent of Python decision latency.
        if sign*(price-stop) <= 0:
            chosen, reason = idx, 'INITIAL_BROKER_STOP'
            break
        if pending_at is not None and stamp >= pending_at:
            chosen, reason = idx, 'PROFIT_LOCK'
            break
        if stamp >= opened+HORIZON_SECONDS:
            chosen, reason = idx, 'HORIZON_EXIT'
            break
        if pending_at is None:
            result = profit_lock_exit([position], state, now=stamp,
                bid=float(bids[idx]), ask=float(asks[idx]), feed_age=0.,
                config=config, contract_size=contract_size)
            if result['close']:
                decision_at = stamp
                pending_at = stamp+LATENCY_SECONDS
    if chosen is None:
        chosen, reason = final, 'HORIZON_EXIT'
    fill_time = float(stamps[chosen])
    fill_price = float(bids[chosen] if sign == 1 else asks[chosen])
    gross = sign*(fill_price-entry)*exposure
    return dict(net_usd=gross-cost_usd, gross_exit_side_usd=gross,
        exit_time_utc=datetime.fromtimestamp(fill_time, timezone.utc).isoformat(),
        exit_price=fill_price, hold_seconds=fill_time-opened, reason=reason,
        decision_time_utc=(datetime.fromtimestamp(decision_at, timezone.utc).isoformat()
                           if reason == 'PROFIT_LOCK' and decision_at is not None else None),
        cost_usd=cost_usd, initial_stop_price=stop)


def post_exit_markout(trade, stamps, bids, asks, *, contract_size, cost_usd):
    closed = epoch(trade['closed_utc'])
    first = quote_index(stamps, closed)
    last = quote_index(stamps, closed+15.)
    if first is None or last is None or first > last:
        return dict(available=False, reason='Post-exit quotes unavailable')
    boundaries = np.r_[closed, stamps[first:last+1], closed+15.]
    if len(boundaries) > 1 and float(np.diff(boundaries).max()) > MAX_GAP_SECONDS:
        return dict(available=False, reason='Post-exit quote gap exceeds three seconds')
    sign = 1 if trade['direction'] == 'BUY' else -1
    sides = bids if sign == 1 else asks
    exposure = float(trade['volume'])*contract_size
    return dict(available=True,
        additional_quote_move_usd=sign*float(sides[last]-sides[first])*exposure,
        held_to_plus15_quote_net_usd=sign*(float(sides[last])-float(trade['entry_price']))*exposure-cost_usd,
        quote_at_actual_exit=float(sides[first]), quote_at_plus15=float(sides[last]),
        actual_closed_net_usd=float(trade['net']),
        note='Quote-based markout, not a realizable alternative fill; ignores intervening stop.')


def evaluate(audit, ticks, *, contract_size=100., cost_usd=.30):
    if not math.isfinite(contract_size) or contract_size <= 0 or not math.isfinite(cost_usd) or cost_usd < 0:
        raise ValueError('Finite positive contract size and nonnegative cost required')
    values = ticks[['timestamp', 'bid', 'ask']].astype(float)
    if values.empty or not np.isfinite(values.to_numpy()).all():
        raise ValueError('Nonempty finite tick data required')
    if (values.bid <= 0).any() or (values.ask < values.bid).any():
        raise ValueError('Invalid executable bid/ask data')
    values = values.sort_values('timestamp', kind='stable').reset_index(drop=True)
    stamps, bids, asks = (values[k].to_numpy() for k in ('timestamp', 'bid', 'ask'))
    matched, excluded, markouts = [], Counter(), []
    for trade in audit['closed_positions']:
        try:
            opened = epoch(trade['opened_utc'])
            if trade.get('direction') not in ('BUY', 'SELL'):
                raise ValueError('direction')
            if not all(math.isfinite(float(trade[k])) and float(trade[k]) > 0
                       for k in ('entry_price', 'volume', 'initial_stop_distance', 'position_id')):
                raise ValueError('risk or position')
            # Both variants use the same fully covered 180-second cohort.
            # Extra latency applies to a scheduled horizon close, too.
            if opened < stamps[0] or opened+HORIZON_SECONDS+LATENCY_SECONDS > stamps[-1]:
                excluded['incomplete_horizon_or_outside_capture'] += 1
                continue
            first = quote_index(stamps, opened)
            final = quote_index(stamps, opened+HORIZON_SECONDS+LATENCY_SECONDS)
            if first is None or final is None:
                excluded['stale_boundary'] += 1
                continue
            gaps = np.diff(np.r_[opened, stamps[first:final+1]])
            if len(gaps) and float(gaps.max()) > MAX_GAP_SECONDS:
                excluded['quote_gap_over_three_seconds'] += 1
                continue
            baseline = scenario(trade, stamps, bids, asks, first, final,
                config=CONTROL, contract_size=contract_size, cost_usd=cost_usd)
            challenger = scenario(trade, stamps, bids, asks, first, final,
                config=CHALLENGER, contract_size=contract_size, cost_usd=cost_usd)
            markout = post_exit_markout(trade, stamps, bids, asks,
                contract_size=contract_size, cost_usd=cost_usd)
            markouts.append(markout)
            matched.append(dict(position_id=trade['position_id'], direction=trade['direction'],
                entry_time_utc=trade['opened_utc'], actual_net_usd=trade['net'],
                baseline=baseline, challenger=challenger,
                paired_delta_usd=challenger['net_usd']-baseline['net_usd'], post_exit_15s=markout))
        except (KeyError, TypeError, ValueError):
            excluded['invalid_trade_metadata'] += 1
    deltas = [r['paired_delta_usd'] for r in matched]
    available_markouts = [r for r in markouts if r.get('available')]
    return dict(role='OFFLINE_MATCHED_ENTRY_EXIT_COMPARISON_NOT_FULL_STRATEGY_BACKTEST',
        configuration=dict(control=CONTROL, challenger=CHALLENGER, horizon_seconds=HORIZON_SECONDS,
            decision_fill_latency_seconds=LATENCY_SECONDS, maximum_quote_gap_seconds=MAX_GAP_SECONDS,
            cost_usd_per_trade=cost_usd, contract_size=contract_size),
        input_ticks=len(stamps), input_closed_positions=len(audit['closed_positions']),
        baseline=summarize([r['baseline'] for r in matched]),
        challenger=summarize([r['challenger'] for r in matched]),
        paired=dict(trades=len(deltas), total_delta_usd=sum(deltas),
            mean_delta_usd=float(np.mean(deltas)) if deltas else None,
            improved=sum(d > 1e-8 for d in deltas), worsened=sum(d < -1e-8 for d in deltas),
            unchanged=sum(abs(d) <= 1e-8 for d in deltas)),
        post_actual_exit_15s=dict(available=len(available_markouts),
            mean_additional_quote_move_usd=float(np.mean([r['additional_quote_move_usd']
                for r in available_markouts])) if available_markouts else None),
        excluded=dict(excluded), matched_positions=matched,
        limitations=[
            'Actual recorded entries/fills held fixed: no replacement-entry, sizing or margin replay.',
            'Overlapping positions remain correlated; changing exits changes later live entries.',
            'Initial SL executes at first observed crossed executable quote, no guaranteed stop price.',
            'Profit-lock order fills first available quote >=decision+350ms; broker rejection/queue omitted.',
            'Horizon close uses first quote >=entry+180.35s; gaps above three seconds censor both variants.',
            'Fixed .30 USD additional cost per trade by default; observed entry spread already paid in actual fill.',
            'Both modes retain initial broker stop and omit other adaptive/news/flow exits.',
            'Post-exit markout is hypothetical quoted movement, not profit recoverable by ignoring stops.',
            'Two fixed profiles only, no parameter optimization or profitability guarantee.'])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--capture', type=Path, required=True)
    parser.add_argument('--audit', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--cost-usd', type=float, default=.30,
                        help='Additional assumed round-trip commission/slippage USD per .01-lot trade')
    args = parser.parse_args()
    audit = json.loads(args.audit.read_text(encoding='utf-8'))
    capture = args.capture
    ticks_path = capture/'ticks.parquet' if capture.is_dir() else capture
    metadata_path = ticks_path.parent/'metadata.json'
    metadata = json.loads(metadata_path.read_text(encoding='utf-8')) if metadata_path.exists() else {}
    if audit.get('account_fingerprint') and metadata.get('account_fingerprint'):
        if audit['account_fingerprint'] != metadata['account_fingerprint']:
            raise ValueError('Audit/capture account identity mismatch')
    report = evaluate(audit, pd.read_parquet(ticks_path),
        contract_size=float(metadata.get('contract_size', 100.)), cost_usd=args.cost_usd)
    report.update(capture=str(ticks_path), audit=str(args.audit),
        account_identity_verified=bool(audit.get('account_fingerprint') and metadata.get('account_fingerprint')))
    if not report['account_identity_verified']:
        report['limitations'].append('Audit/capture fingerprints missing: identity consistency not independently established.')
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, allow_nan=False), encoding='utf-8')
    print(json.dumps({k:report[k] for k in ('baseline','challenger','paired','post_actual_exit_15s','excluded')}, indent=2))


if __name__ == '__main__':
    main()
