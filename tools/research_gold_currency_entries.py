"""Offline currency-feature challenger; same tick labels, model, splits and gates."""
import os
os.environ.setdefault('OMP_NUM_THREADS', '2')
os.environ.setdefault('OPENBLAS_NUM_THREADS', '1')
from datetime import datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path
import sys
import numpy as np
import pandas as pd
import MetaTrader5 as mt5

PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from config import gold_consensus_settings as settings
from services.market_data.gold_broker_clock import to_broker_time, quote_age
from research_gold_tick_entries import ROOT, main

PAIRS = {'EURUSD': ('EUR', 'USD'), 'USDJPY': ('USD', 'JPY')}
OUTPUT = ROOT / 'currency_challenger'


def currency_features(bars, offset=0):
    frame = pd.DataFrame(bars).sort_values('time').drop_duplicates('time', keep='last')
    stamps = pd.to_numeric(frame.time, errors='coerce')
    close = pd.to_numeric(frame.close, errors='coerce')
    log = np.log(close.where(close > 0))
    one = log.diff().where(stamps.diff() == 60)
    epoch_offset = int(stamps.iloc[0]) if offset == 0 and len(stamps) else int(offset)
    result = pd.DataFrame({'feature_epoch': stamps + 60 - epoch_offset})
    for count in (1, 5, 15):
        continuous = (stamps.diff().rolling(count).min() == 60) & (stamps.diff().rolling(count).max() == 60)
        result['return_' + str(count)] = (log - log.shift(count)).where(continuous) * 10000
    volatility = one.rolling(30, min_periods=30).std()
    result['z_5'] = (result.return_5 / 10000 / (volatility * np.sqrt(5))).where(volatility > 0)
    return result.replace([np.inf, -np.inf], np.nan).dropna().reset_index(drop=True)


def collect():
    OUTPUT.mkdir(parents=True, exist_ok=True)
    manifest = json.loads((ROOT / 'historical_ticks/manifest.json').read_text())
    start = datetime.fromisoformat(manifest['start_utc']) - timedelta(days=1)
    end = datetime.fromisoformat(manifest['end_utc'])
    metadata = {}
    if not mt5.initialize():
        raise RuntimeError(str(mt5.last_error()))
    try:
        for symbol, (base, quote) in PAIRS.items():
            info, tick = mt5.symbol_info(symbol), mt5.symbol_info_tick(symbol)
            if info is None or info.currency_base != base or info.currency_profit != quote or tick is None:
                raise RuntimeError(f'{symbol}: missing or wrong instrument identity')
            age = quote_age(float(tick.time_msc) / 1000)
            if not np.isfinite(age) or age > 15:
                raise RuntimeError(f'{symbol}: cannot validate configured broker clock with fresh quote')
            bars = mt5.copy_rates_range(symbol, mt5.TIMEFRAME_M1, to_broker_time(start), to_broker_time(end))
            if bars is None or not len(bars):
                raise RuntimeError(f'{symbol}: no historical bars: {mt5.last_error()}')
            frame = pd.DataFrame(bars)
            path = OUTPUT / (symbol + '.csv')
            frame.to_csv(path, index=False)
            metadata[symbol] = dict(rows=len(frame), first_broker_epoch=int(frame.time.min()),
                last_broker_epoch=int(frame.time.max()), live_quote_age_seconds=age,
                sha256=hashlib.sha256(path.read_bytes()).hexdigest())
    finally:
        mt5.shutdown()
    (OUTPUT / 'capture.json').write_text(json.dumps(dict(
        captured_at=datetime.now(timezone.utc).isoformat(), requested_start=start.isoformat(),
        requested_end=end.isoformat(), broker_offset_seconds=settings.MT5_SERVER_UTC_OFFSET_SECONDS,
        symbols=metadata, limitations=['Historical revisions and incomplete terminal history are possible.',
            'Broker clock convention verified against current quote; historical offset assumed constant.']), indent=2))


def augment(data):
    original_days = sorted(data.day.unique())
    count = len(data)
    coverage = {}
    for symbol in PAIRS:
        features = currency_features(
            pd.read_csv(OUTPUT / (symbol + '.csv')),
            offset=settings.MT5_SERVER_UTC_OFFSET_SECONDS,
        )
        features = features.rename(columns={key: 'currency_' + symbol.lower() + '_' + key
                                           for key in features if key != 'feature_epoch'})
        columns = [key for key in features if key != 'feature_epoch']
        data = pd.merge_asof(data, features, on='feature_epoch', direction='backward', tolerance=65)
        available = data[columns].notna().all(axis=1)
        data['currency_' + symbol.lower() + '_available'] = available.astype(float)
        coverage[symbol] = data.assign(available=available).groupby('day').available.mean().to_dict()
        data[columns] = data[columns].fillna(0.)
    assert len(data) == count and sorted(data.day.unique()) == original_days
    (OUTPUT / 'coverage.json').write_text(json.dumps(coverage, indent=2))
    return data


if __name__ == '__main__':
    OUTPUT.mkdir(parents=True, exist_ok=True)
    hypothesis = dict(frozen_before_collection=datetime.now(timezone.utc).isoformat(),
        family='COMPLETED_CURRENCY_RETURNS_V1', symbols=list(PAIRS),
        source_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        model_sha256=hashlib.sha256((PROJECT / 'tools/research_gold_tick_entries.py').read_bytes()).hexdigest(),
        design=['Completed M1 currency returns 1/5/15 bars and 30-bar volatility-scaled 5-bar return.',
                'Missing/stale features become zero with explicit availability flags; original rows/days retained.',
                'Same model hyperparameters, threshold grid, chronological splits, labels and acceptance gates.',
                'Middle dates already inspected: exploratory validation, not independent evidence.',
                'Final dates evaluated only if validation qualifies; no model export or execution changes.'],
        live_approved=False)
    (OUTPUT / 'hypothesis.json').write_text(json.dumps(hypothesis, indent=2))
    collect()
    main(augment=augment, filename='currency_tick_entry_assessment.json')
