"""Frozen causal quote-event comparison; offline only, no broker connection.

Inputs are UTC-normalized ticks.parquet and m1.parquet. Parameters below are
fixed before reading results. This compares candidate rules, not live source
votes, broker execution or the multiposition bot's adaptive profit-lock exits.
"""
import argparse
from collections import Counter
from dataclasses import asdict
import hashlib
import json
import math
from pathlib import Path
import sys

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from services.research.gold_execution_thesis import execution_thesis
from services.research.gold_causal_replay import replay, ReplayConfig


def utc_seconds(series):
    if pd.api.types.is_numeric_dtype(series):
        return pd.to_numeric(series, errors='raise').astype(float)
    return pd.to_datetime(series, utc=True, errors='raise').astype('int64')/1e9


def load_capture(root):
    ticks = pd.read_parquet(root/'ticks.parquet')
    rate_path = root/'m1.parquet'
    if not rate_path.exists():
        rate_path = root/'M1.parquet'
    rates = pd.read_parquet(rate_path)
    if not {'timestamp', 'bid', 'ask'}.issubset(ticks) or not {'time', 'open', 'high', 'low', 'close'}.issubset(rates):
        raise ValueError('UTC ticks(timestamp,bid,ask) and M1(time,OHLC) required')
    ticks = ticks[['timestamp', 'bid', 'ask']].copy()
    ticks['timestamp'] = utc_seconds(ticks.timestamp)
    rates = rates[['time', 'open', 'high', 'low', 'close']].copy()
    rates['time'] = utc_seconds(rates.time)
    for frame in (ticks, rates):
        if not np.isfinite(frame.to_numpy(dtype=float)).all():
            raise ValueError('Finite numeric timestamps and prices required')
    if ticks.empty or len(rates) < 15 or (ticks.bid <= 0).any() or (ticks.ask < ticks.bid).any():
        raise ValueError('Valid nonempty executable quotes and 15 M1 bars required')
    if ((rates[['open','high','low','close']] <= 0).any().any()
            or (rates.high < rates[['open','close','low']].max(axis=1)).any()
            or (rates.low > rates[['open','close','high']].min(axis=1)).any()):
        raise ValueError('Valid positive M1 OHLC required')
    ticks = ticks.sort_values('timestamp', kind='stable').drop_duplicates()
    rates = rates.sort_values('time', kind='stable')
    if rates.time.duplicated().any():
        raise ValueError('Duplicate M1 bar timestamps are ambiguous')
    if (np.abs(rates.time % 60) > 1e-6).any():
        raise ValueError('M1 open timestamps must be UTC minute-aligned')
    prior = rates.close.shift()
    tr = pd.concat([rates.high-rates.low, (rates.high-prior).abs(), (rates.low-prior).abs()], axis=1).max(axis=1)
    rates['atr'] = tr.rolling(14, min_periods=14).mean()
    rates['continuous'] = rates.time.diff().eq(60).rolling(14, min_periods=14).sum().eq(14)
    rates['available_epoch'] = rates.time+60
    return ticks.reset_index(drop=True), rates.reset_index(drop=True), rate_path


def candidates(ticks, rates, *, start, end):
    stamps = ticks.timestamp.to_numpy(dtype=float)
    bids = ticks.bid.to_numpy(dtype=float)
    asks = ticks.ask.to_numpy(dtype=float)
    rate_stamps = rates.available_epoch.to_numpy(dtype=float)
    policies = dict(one_bar_s5=[], execution_thesis=[])
    block_counts = Counter()
    checked = 0
    # At 250ms after a completed S5 candle; never use its still-forming successor.
    first = math.ceil(start/5)*5
    for close_epoch in range(first, int(end), 5):
        observed = close_epoch+.25
        if observed >= end:
            break
        idx = np.searchsorted(stamps, observed, side='right')
        left = np.searchsorted(stamps, observed-40, side='left')
        ri = np.searchsorted(rate_stamps, observed, side='right')-1
        if ri < 0 or idx <= left or not rates.continuous.iloc[ri]:
            block_counts['missing_warmup_or_continuous_M1'] += 1
            continue
        atr = float(rates.atr.iloc[ri])
        if not math.isfinite(atr) or atr <= 0 or observed-rate_stamps[ri] > 65:
            block_counts['stale_or_invalid_completed_M1_ATR'] += 1
            continue
        recent = ticks.iloc[left:idx]
        bars = []
        for begin in (close_epoch-10, close_epoch-5):
            a = np.searchsorted(stamps, begin, side='left')
            b = np.searchsorted(stamps, begin+5, side='left')
            boundaries = np.r_[begin, stamps[a:b], begin+5]
            if b-a < 2 or np.diff(boundaries).max() > 2.5:
                bars = []
                break
            mids = (bids[a:b]+asks[a:b])/2
            bars.append(dict(open=float(mids[0]), close=float(mids[-1]),
                             low=float(mids.min()), high=float(mids.max())))
        if len(bars) != 2 or observed-stamps[idx-1] > 2:
            block_counts['incomplete_S5_or_stale_tick'] += 1
            continue
        body = bars[-1]['close']-bars[-1]['open']
        if body == 0:
            block_counts['flat_completed_S5'] += 1
            continue
        checked += 1
        direction, sign = ('BUY', 1) if body > 0 else ('SELL', -1)
        bid, ask = float(bids[idx-1]), float(asks[idx-1])
        spread = ask-bid
        pivot = min(bar['low'] for bar in bars) if sign == 1 else max(bar['high'] for bar in bars)
        stop = pivot-sign*max(.25*spread, .1*atr)
        risk = sign*((ask if sign == 1 else bid)-stop)
        event = dict(feature_epoch=observed, valid_until_epoch=close_epoch+5,
                     direction=direction, stop=stop, atr=atr,
                     setup='ONE_COMPLETED_S5', range_id=f'S5:{close_epoch}')
        if 0 < risk <= 5:
            policies['one_bar_s5'].append(event)
        thesis = execution_thesis(recent, now=observed, direction=direction, atr=atr,
                                  commission=.10, slippage=.20)
        for reason in thesis.get('blocks', []):
            block_counts[reason] += 1
        if thesis.get('allowed'):
            event = dict(event, stop=float(thesis['levels']['sl']), setup=thesis['setup'],
                         range_id=thesis['setup_id'])
            policies['execution_thesis'].append(event)
    return policies, checked, dict(block_counts)


def evaluate(root):
    ticks, rates, rate_path = load_capture(root)
    end = float(ticks.timestamp.iloc[-1])
    start = max(float(ticks.timestamp.iloc[0])+60, end-4*3600)
    if end-start < 120:
        raise ValueError('At least three minutes of tick history required')
    boundary = (start+end)/2
    policies, checked, blocks = candidates(ticks, rates, start=start, end=end)
    config = ReplayConfig(latency=.35, round_trip_cost=.30, maximum_hold=180.,
                          trailing_arm_r=.8, trailing_gap_r=.45, maximum_entry_risk=5.)
    segments = [('first_half', start, boundary), ('second_half', boundary, end)]
    results = []
    for policy, events in policies.items():
        for segment, begin, finish in segments:
            outcome = replay(ticks, events, start=begin, end=finish, config=config)
            results.append(dict(policy=policy, segment=segment, start=begin, end=finish,
                candidate_events=sum(begin <= row['feature_epoch'] < finish for row in events),
                summary=outcome['summary'], rejected=outcome['rejected'],
                censored_positions=outcome['censored_positions'],
                unfilled_requests=outcome['unfilled_requests'], trades=outcome['trades']))
    return dict(role='FROZEN_OFFLINE_SINGLE_POSITION_COMPARISON_NOT_LIVE_BOT_VALIDATION',
        direction_rule='Most recent completed S5 candle close minus open; frozen before evaluation.',
        atr_rule='Mean 14 completed causal M1 true ranges with continuous minute coverage.',
        capture=str(root), tick_count=len(ticks), start=start, end=end, chronological_boundary=boundary,
        source_hashes={str(path.name):hashlib.sha256(path.read_bytes()).hexdigest()
                       for path in (root/'ticks.parquet', rate_path)},
        configuration=asdict(config), entry_evaluation_delay_seconds=.25,
        commission_price=.10, slippage_price=.20, checked_directional_epochs=checked,
        candidate_block_counts=blocks, results=results,
        limitations=[
            'Two frozen candidate policies; no optimization, fitting or best-threshold selection.',
            'Chronological halves are descriptive: no untouched holdout claim after inspection.',
            'Executable bid/ask fills delayed 350ms; .30 assumed additional round-trip costs, not measured.',
            'Single position, no live three-source votes, multiple lots, margin, requotes or dynamic profit-lock parity.',
            'No exit comparison: changing exits alters subsequent filled entries; not identical-entry causal evidence.',
            'Half-boundary open positions censored, not closed at favorable synthetic prices.',
            'Price-unit P/L models 1oz (.01 standard 100oz contract); no profit guarantee or promotion authority.'])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--capture', required=True, type=Path)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    report = evaluate(args.capture)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, allow_nan=False), encoding='utf-8')
    print(json.dumps({key:report[key] for key in ('role','start','end','checked_directional_epochs')}))
    print(json.dumps([dict(policy=row['policy'], segment=row['segment'],
        candidates=row['candidate_events'], **row['summary'], censored=row['censored_positions'])
        for row in report['results']], indent=2))


if __name__ == '__main__':
    main()
