"""Bounded prospective A/B/C paper observer. No order API or automatic activation."""
import argparse
from dataclasses import asdict
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys
import time
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from config import gold_consensus_settings as settings
from services.research.gold_tick_history import TickHistoryBuffer
from services.research.gold_s30_execution import account_fingerprint
from services.research.gold_multiengine_research import MultiEngineResearch
from services.research.gold_engine_paper import evaluate_engines, ABC_REPLAY_CONFIG
from services.utils.atomic_json import atomic_write_json


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--minutes', type=float, default=30.)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if not 0 < args.minutes <= 120:
        parser.error('--minutes must be in (0,120]')
    if args.output.exists() and any(args.output.iterdir()):
        raise RuntimeError('Use a new empty trial directory')
    import MetaTrader5 as mt5
    if not mt5.initialize(timeout=10000):
        raise RuntimeError('MT5 initialization failed')
    args.output.mkdir(parents=True, exist_ok=True)
    started, deadline = time.time(), time.monotonic()+args.minutes*60
    history, strategy = TickHistoryBuffer(), MultiEngineResearch()
    ticks, seen, candles = [], set(), {}
    events = {engine: [] for engine in 'ABC'}
    errors, last_signal = [], {}
    last_feature, last_fetch_boundary = None, None
    last_fetch = last_publish = -float('inf')

    def publish(finished=False, closing=False):
        now = time.time()
        frame = pd.DataFrame(ticks)
        engines = evaluate_engines(frame, events, start=started, end=now) if len(frame) else {}
        report = dict(observed_at=datetime.now(timezone.utc).isoformat(), read_only=True,
            execution_enabled=False, strategy='ABC_REGIME_RESEARCH_V1',
            evaluation='PROSPECTIVE_PAPER', completed=finished,
            observer_state='COMPLETED' if finished else 'STOPPED' if closing else 'RUNNING',
            duration_seconds=now-started, ticks=len(ticks), last_signal=last_signal,
            engines=engines, errors=errors[-10:],
            limitations=['Independent paper paths, not a combined funded account or broker fills.',
                'Assumed 350 ms latency and .30 price-unit round-trip costs plus observed spread.',
                'No news/calendar execution model, no fixed TP, no automatic order authorization.'])
        atomic_write_json(str(args.output/'latest.json'), report, indent=2)
        if len(frame):
            frame.to_parquet(args.output/'ticks.parquet', index=False)
        print(report['observed_at'], {engine: result['summary'] for engine, result in engines.items()}, flush=True)

    try:
        account = mt5.account_info()
        if account is None or account.trade_mode != mt5.ACCOUNT_TRADE_MODE_DEMO or account.currency != 'USD':
            raise RuntimeError('Connected USD demo required')
        identity = account_fingerprint(account)
        atomic_write_json(str(args.output/'protocol.json'), dict(started_at=datetime.now(timezone.utc).isoformat(),
            account_fingerprint=identity, execution_enabled=False, config=asdict(ABC_REPLAY_CONFIG),
            strategy='ABC_REGIME_RESEARCH_V1', source_sha256=hashlib.sha256(
                (ROOT/'services/research/gold_multiengine_research.py').read_bytes()).hexdigest()), indent=2)
        while time.monotonic() < deadline:
            now = time.time()
            current = mt5.account_info()
            if current is None or account_fingerprint(current) != identity:
                raise RuntimeError('Account changed; stopping the paper observer')
            try:
                frame, health = history.refresh(mt5, 'XAUUSD', datetime.now(timezone.utc))
                lower = max(started, ticks[-1]['timestamp']-1) if ticks else started
                recent = frame[(frame.timestamp >= lower) & (frame.timestamp <= now)]
                for row in recent[['timestamp', 'bid', 'ask']].to_dict('records'):
                    key = (row['timestamp'], row['bid'], row['ask'])
                    if key not in seen:
                        seen.add(key)
                        ticks.append(row)
                boundary = int(now//300)
                if boundary != last_fetch_boundary or now-last_fetch >= 30:
                    for name, timeframe, count in (('M1', mt5.TIMEFRAME_M1, 3000),
                            ('M5', mt5.TIMEFRAME_M5, 500), ('M15', mt5.TIMEFRAME_M15, 400)):
                        rates = mt5.copy_rates_from_pos('XAUUSD', timeframe, 1, count)
                        if rates is None:
                            raise RuntimeError(f'Closed {name} history unavailable')
                        candles[name] = pd.DataFrame(rates)
                    last_fetch, last_fetch_boundary = now, boundary
                tick = mt5.symbol_info_tick('XAUUSD')
                if tick is None or not health['available']:
                    raise RuntimeError(health.get('error') or 'No fresh executable quote')
                observed = time.time()
                age = observed-(float(tick.time_msc)/1000-settings.MT5_SERVER_UTC_OFFSET_SECONDS)
                if not -settings.MT5_QUOTE_FUTURE_TOLERANCE_SECONDS <= age <= settings.ENTRY_MAX_QUOTE_AGE_SECONDS:
                    raise RuntimeError('Current quote is stale; do not paper-enter on an old price')
                last_signal = strategy.assess(frame, candles, now=observed, bid=float(tick.bid),
                    ask=float(tick.ask), offset=settings.MT5_SERVER_UTC_OFFSET_SECONDS)
                row = strategy.row
                if row is not None and row['feature_epoch'] != last_feature:
                    last_feature = row['feature_epoch']
                    for engine in 'ABC':
                        candidate = next((item for item in last_signal['candidates'] if item['engine'] == engine), None)
                        event = dict(feature_epoch=observed, direction='WAIT', stop=0., setup=f'ABC_{engine}',
                                     trend_sign=int(row['trend_sign']))
                        if candidate:
                            event.update(candidate, feature_epoch=observed)
                        events[engine].append(event)
                    with (args.output/'decisions.jsonl').open('a', encoding='utf-8') as handle:
                        handle.write(json.dumps(dict(observed_at=observed, signal=last_signal), allow_nan=False)+'\n')
            except (ValueError, KeyError, RuntimeError) as error:
                errors.append(dict(at=now, message=str(error)))
            if time.time()-last_publish >= 30:
                publish()
                last_publish = time.time()
            time.sleep(.5)
    except Exception as error:
        errors.append(dict(at=time.time(), message=f'Observer stopped: {error}'))
        raise
    finally:
        mt5.shutdown()
        publish(finished=time.monotonic() >= deadline, closing=True)


if __name__ == '__main__':
    main()
