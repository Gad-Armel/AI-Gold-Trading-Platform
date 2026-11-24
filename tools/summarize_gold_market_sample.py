"""Describe the captured broker market, not a web quote or a forecast."""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import numpy as np
import pandas as pd


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--capture', type=Path, default=Path('data/research/strategy_20261021/capture'))
    parser.add_argument('--output', type=Path, default=Path('data/research/strategy_20261021/market_sample.json'))
    args = parser.parse_args()
    ticks = pd.read_parquet(args.capture/'ticks.parquet').sort_values('timestamp', kind='stable')
    ticks['mid'] = (ticks.bid+ticks.ask)/2
    ticks['spread'] = ticks.ask-ticks.bid
    ticks['utc'] = pd.to_datetime(ticks.timestamp, unit='s', utc=True)
    day = ticks.utc.iloc[-1].floor('D')
    today = ticks[ticks.utc >= day]
    segments = {}
    for name, start_hour, end_hour in (('UTC_TODAY', 0, 24), ('ASIA_UTC_00_07', 0, 7),
                                      ('LONDON_UTC_07_12', 7, 12)):
        sample = today[(today.utc.dt.hour >= start_hour) & (today.utc.dt.hour < end_hour)]
        if sample.empty:
            continue
        segments[name] = dict(ticks=len(sample), first=sample.utc.iloc[0].isoformat(),
            last=sample.utc.iloc[-1].isoformat(), midpoint_open=float(sample.mid.iloc[0]),
            midpoint_high=float(sample.mid.max()), midpoint_low=float(sample.mid.min()),
            midpoint_last=float(sample.mid.iloc[-1]), midpoint_change=float(sample.mid.iloc[-1]-sample.mid.iloc[0]),
            spread_median=float(sample.spread.median()), spread_p95=float(sample.spread.quantile(.95)))
    moves = ticks.mid.diff().round(8)
    moving = ticks.loc[moves.ne(0) & moves.notna(), ['timestamp', 'mid', 'spread']].copy()
    moving['sign'] = np.sign(moves.loc[moving.index])
    moving['run'] = moving.sign.ne(moving.sign.shift()).cumsum()
    moving['ordinal'] = moving.groupby('run').cumcount()+1
    second = moving[moving.ordinal == 2].set_index('run')
    fifth = moving[moving.ordinal == 5].set_index('run')
    joined = second.join(fifth[['mid', 'timestamp']], how='inner', rsuffix='_fifth')
    drift = (joined.mid_fifth-joined.mid)*joined.sign
    quote_seconds = ticks.timestamp.diff().dropna()
    report = dict(read_only=True, created_at=datetime.now(timezone.utc).isoformat(),
        source='MetaQuotes demo XAUUSD executable bid/ask history, not consolidated gold market',
        segments=segments, tick_run_diagnostic=dict(
            runs_reaching_second=len(second), runs_reaching_fifth=len(fifth),
            conditional_fifth_fraction=len(joined)/len(second) if len(second) else None,
            second_to_fifth_midpoint_gain_median=float(drift.median()) if len(drift) else None,
            second_to_fifth_midpoint_gain_p90=float(drift.quantile(.9)) if len(drift) else None,
            second_to_fifth_seconds_median=float((joined.timestamp_fifth-joined.timestamp).median()) if len(joined) else None,
            limitations=['Conditional on reaching five ticks: excludes failed shorter runs and is optimistically selected.',
                         'Midpoint drift is not executable net P/L; spread, latency and fees remain to be paid.']),
        quote_interarrival_median_seconds=float(quote_seconds.median()),
        quote_interarrival_p95_seconds=float(quote_seconds.quantile(.95)),
        limitations=['One demo broker, incomplete current day and no centralized order book.',
                     'Session names are descriptive UTC windows for this October sample, not universal session calendars.',
                     'No claim about causality, tomorrow, or a statistically reliable trading edge.'])
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, allow_nan=False), encoding='utf-8')
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
