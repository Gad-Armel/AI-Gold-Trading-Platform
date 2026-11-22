"""Read-only prospective forecast observer. It has no order-sending functions."""
import argparse
import hashlib
import json
import math
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
import joblib
import MetaTrader5 as mt5
import pandas as pd

PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from config import gold_consensus_settings as settings
from services.market_data.gold_broker_clock import quote_age
from services.utils.atomic_json import atomic_write_json
from benchmark_gold_entry_patterns import ROOT, dataset
from research_gold_bidirectional import entry_features


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--minutes', type=float, default=30)
    args = parser.parse_args()
    manifest = json.loads((ROOT/'bidirectional_5m_observation.json').read_text())
    path = ROOT/'bidirectional_5m_observation.joblib'
    if hashlib.sha256(path.read_bytes()).hexdigest() != manifest['model_sha256']:
        raise RuntimeError('Research model does not match frozen manifest')
    frozen = joblib.load(path)
    frames = {name: pd.read_csv(ROOT/'broker_bars'/(name+'.csv')) for name in ('M1', 'M5', 'M15')}
    output = ROOT/'prospective'/datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    output.mkdir(parents=True, exist_ok=True)
    print(str(output), flush=True)
    if not mt5.initialize():
        raise RuntimeError(mt5.last_error())
    position, trades, signal = None, [], {}
    last_bar, cooldown, last_save = None, 0., 0.
    started = time.monotonic()
    try:
        account = mt5.account_info()
        if account is None or account.trade_mode != mt5.ACCOUNT_TRADE_MODE_DEMO:
            raise RuntimeError('Observer requires connected demo terminal')
        while time.monotonic()-started <= args.minutes*60:
            now = time.time()
            stamp = datetime.fromtimestamp(now, timezone.utc).isoformat()
            tick = mt5.symbol_info_tick('XAUUSD')
            error = None
            floating = None
            try:
                if tick is None:
                    raise RuntimeError('No broker quote')
                bid, ask = float(tick.bid), float(tick.ask)
                age = quote_age(float(tick.time_msc)/1000)
                valid = all(math.isfinite(v) for v in (bid, ask, age)) and 0 < bid <= ask
                if position and valid and age <= settings.EXIT_MAX_FEED_AGE_SECONDS:
                    sign = position['sign']
                    floating = sign*((bid if sign==1 else ask)-position['entry'])-.05
                    stopped = sign*((bid if sign==1 else ask)-position['stop'])<=0
                    if stopped or now-position['opened_epoch'] >= manifest['horizon_seconds']:
                        trade = dict(position, closed_at=stamp, profit=round(floating, 4),
                                     reason='SHADOW_STOP' if stopped else 'SHADOW_TIME_EXIT')
                        trades.append(trade)
                        with (output/'trades.jsonl').open('a') as handle:
                            handle.write(json.dumps(trade)+'\n')
                        position, floating, cooldown = None, None, now+180
                newest = mt5.copy_rates_from_pos('XAUUSD', mt5.TIMEFRAME_M1, 1, 1)
                if newest is None or not len(newest):
                    raise RuntimeError('No closed M1 candle')
                bar = int(newest[0]['time'])
                if bar != last_bar:
                    broker_now = now+settings.MT5_SERVER_UTC_OFFSET_SECONDS
                    for name, timeframe, seconds in [('M1', mt5.TIMEFRAME_M1, 60),
                            ('M5', mt5.TIMEFRAME_M5, 300), ('M15', mt5.TIMEFRAME_M15, 900)]:
                        rates = mt5.copy_rates_from_pos('XAUUSD', timeframe, 1, 2000)
                        if rates is None or not len(rates):
                            raise RuntimeError(f'{name} unavailable')
                        joined = pd.concat([frames[name], pd.DataFrame(rates)], ignore_index=True)
                        frames[name] = joined[joined.time+seconds<=broker_now].sort_values('time').drop_duplicates('time', keep='last').reset_index(drop=True)
                    data = dataset(frames, include_latest=True)
                    row = data.iloc[-1]
                    if broker_now-row.available > 90:
                        raise RuntimeError('Completed-candle features are stale')
                    features = entry_features(data).iloc[[-1]][frozen['feature_columns']]
                    buy = float(frozen['models'][1].predict(features)[0])
                    sell = float(frozen['models'][-1].predict(features)[0])
                    any_signal = bool((features[['m1_bias', 'm5_bias', 'm15_bias']] != 0).any(axis=1).iloc[0])
                    eligible = any_signal and max(buy, sell)>=manifest['threshold'] and abs(buy-sell)>=manifest['minimum_forecast_gap']
                    signal = dict(observed_at=datetime.now(timezone.utc).isoformat(), bar_available_broker_epoch=float(row.available),
                        buy_expected_usd=buy, sell_expected_usd=sell,
                        direction=('BUY' if buy>sell else 'SELL') if eligible else 'WAIT',
                        role='RESEARCH_OBSERVATION_ONLY', live_approved=False,
                        features=features.iloc[0].to_dict())
                    with (output/'signals.jsonl').open('a') as handle:
                        handle.write(json.dumps(signal)+'\n')
                    last_bar = bar
                # Analysis may take time: hypothetical fills use a new quote
                # obtained after the forecast exists, never the pre-analysis quote.
                entry_tick = mt5.symbol_info_tick('XAUUSD')
                entry_now = time.time()
                entry_bid = float(entry_tick.bid) if entry_tick else float('nan')
                entry_ask = float(entry_tick.ask) if entry_tick else float('nan')
                entry_age = quote_age(float(entry_tick.time_msc)/1000) if entry_tick else float('inf')
                entry_valid = all(math.isfinite(v) for v in (entry_bid, entry_ask, entry_age)) and 0 < entry_bid <= entry_ask
                if (position is None and entry_now>=cooldown and signal.get('direction') in ('BUY', 'SELL')
                        and entry_now-datetime.fromisoformat(signal['observed_at']).timestamp() < 90
                        and entry_valid and entry_age<=settings.ENTRY_MAX_QUOTE_AGE_SECONDS and entry_ask-entry_bid<=.50):
                    sign = 1 if signal['direction']=='BUY' else -1
                    entry = (entry_ask if sign==1 else entry_bid)+sign*.05
                    position = dict(direction=signal['direction'], sign=sign, entry=entry,
                        stop=entry-sign*5, volume=.01, opened_epoch=entry_now,
                        opened_at=datetime.fromtimestamp(entry_now, timezone.utc).isoformat(),
                        forecast=signal, simulated=True)
                    cooldown = now+30
            except Exception as exc:
                error = f'{type(exc).__name__}: {exc}'
            if now-last_save >= 10:
                summary = dict(updated_at=datetime.now(timezone.utc).isoformat(), status='OBSERVING', role='NO_BROKER_ORDERS',
                    policy=manifest['policy'], signal=signal, position=position,
                    closed_trades=len(trades), realized=sum(t['profit'] for t in trades),
                    floating=floating, error=error, model_sha256=manifest['model_sha256'])
                atomic_write_json(output/'status.json', summary, indent=2)
                last_save = now
            time.sleep(2)
        summary.update(status='COMPLETED', ended_at=datetime.now(timezone.utc).isoformat())
        atomic_write_json(output/'status.json', summary, indent=2)
    finally:
        mt5.shutdown()


if __name__ == '__main__':
    main()
