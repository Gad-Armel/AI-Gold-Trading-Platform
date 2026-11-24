"""Prospective paper-only observation of a fixed gold strategy; no order API."""
import argparse
from datetime import datetime, timezone
import json
import hashlib
from pathlib import Path
import sys
import time
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from config import gold_consensus_settings as settings
from services.research.gold_tick_history import TickHistoryBuffer
from services.research.gold_regime_scalper import RegimeScalper
from services.research.gold_causal_replay import replay, ReplayConfig
from services.research.gold_s30_execution import account_fingerprint
from services.utils.atomic_json import atomic_write_json


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--minutes', type=float, default=30.)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--strategy', choices=('regime', 'orbit'), default='regime')
    args = parser.parse_args()
    if not 0 < args.minutes <= 120:
        parser.error('--minutes must be in (0,120]')
    import MetaTrader5 as mt5
    if (args.output/'decisions.jsonl').exists():
        raise RuntimeError('Choose a new output folder; prospective trials must not be mixed')
    if not mt5.initialize(timeout=10000):
        raise RuntimeError('MT5 initialization failed')
    args.output.mkdir(parents=True, exist_ok=True)
    start = time.time()
    started_monotonic = time.monotonic()
    history, strategy = TickHistoryBuffer(), RegimeScalper()
    period = 5
    replay_config = ReplayConfig(latency=.35, round_trip_cost=.3)
    strategy_name = 'REGIME_PULLBACK_V1'
    if args.strategy == 'orbit':
        from services.research.gold_orbit_research import OrbitScalper
        strategy = OrbitScalper()
        period = 60
        strategy_name = 'ORBIT_M1_M15_RESEARCH_V1'
        replay_config = ReplayConfig(latency=.35, round_trip_cost=.3, maximum_hold=900.,
            trailing_arm_r=1.2, trailing_gap_r=.5, maximum_entry_risk=10., breakeven_arm_r=.8)
    collected, decisions, processed, candles = [], [], set(), {}
    last_candles = last_report = -float('inf')
    last_feature, errors = None, []
    try:
        account = mt5.account_info()
        if account is None or account.trade_mode != mt5.ACCOUNT_TRADE_MODE_DEMO or account.currency != 'USD':
            raise RuntimeError('Connected USD demo required for observation')
        fingerprint = account_fingerprint(account)
        atomic_write_json(str(args.output/'protocol.json'), dict(
            started_at=datetime.fromtimestamp(start, timezone.utc).isoformat(),
            account_fingerprint=fingerprint, execution_enabled=False,
            strategy=strategy_name, latency_seconds=.35, round_trip_cost_price=.3,
            source_sha256=hashlib.sha256((ROOT/'services/research'/(
                'gold_orbit_research.py' if args.strategy == 'orbit' else 'gold_regime_scalper.py')).read_bytes()).hexdigest(),
            changes_during_trial_allowed=False, automatic_promotion_allowed=False), indent=2)
        while time.monotonic()-started_monotonic <= args.minutes*60:
            now = time.time()
            current = mt5.account_info()
            if current is None or account_fingerprint(current) != fingerprint:
                raise RuntimeError('Account identity changed; observation stopped')
            try:
                frame, health = history.refresh(mt5, 'XAUUSD', datetime.now(timezone.utc))
                lower = max(start, collected[-1]['timestamp']-1) if collected else start
                fresh = frame[(frame.timestamp >= lower) & (frame.timestamp <= now)]
                for row in fresh[['timestamp', 'bid', 'ask']].to_dict('records'):
                    key = tuple(row[column] for column in ('timestamp', 'bid', 'ask'))
                    if key not in processed:
                        processed.add(key)
                        collected.append(row)
                if now-last_candles >= 2:
                    frames = [('M1', mt5.TIMEFRAME_M1), ('M5', mt5.TIMEFRAME_M5)]
                    if args.strategy == 'orbit':
                        frames.append(('M15', mt5.TIMEFRAME_M15))
                    for name, timeframe in frames:
                        rates = mt5.copy_rates_from_pos('XAUUSD', timeframe, 0, 400)
                        if rates is None:
                            raise RuntimeError(f'{name} unavailable')
                        candles[name] = pd.DataFrame(rates)
                    last_candles = now
                tick = mt5.symbol_info_tick('XAUUSD')
                if tick is None or not health.get('available'):
                    raise RuntimeError(health.get('error') or 'Quote unavailable')
                signal = strategy.assess(frame, candles, now=now, bid=float(tick.bid), ask=float(tick.ask),
                    offset=settings.MT5_SERVER_UTC_OFFSET_SECONDS)
                feature = strategy.row
                if feature is not None and feature['feature_epoch'] != last_feature:
                    last_feature = feature['feature_epoch']
                    candidate = dict(feature_epoch=now, valid_until_epoch=last_feature+period,
                        direction=signal['bias'], stop=float(signal.get('levels', {}).get('sl', feature.get('stop', 0.))),
                        setup=feature['setup'], trend_sign=int(feature['trend_sign']) if pd.notna(feature['trend_sign']) else 0)
                    decisions.append(candidate)
                    with (args.output/'decisions.jsonl').open('a', encoding='utf-8') as handle:
                        handle.write(json.dumps(dict(observed_at=now, signal=signal), allow_nan=False)+'\n')
                if now-last_report >= 30 and collected:
                    ticks = pd.DataFrame(collected).sort_values('timestamp', kind='stable')
                    result = replay(ticks, decisions, start=start, end=now,
                        config=replay_config)
                    report = dict(started_at=datetime.fromtimestamp(start, timezone.utc).isoformat(),
                        observed_at=datetime.now(timezone.utc).isoformat(), read_only=True,
                        execution_enabled=False, strategy=strategy_name,
                        duration_seconds=now-start, ticks=len(ticks), decisions=len(decisions),
                        last_signal=signal, paper_result=result, errors=errors[-10:],
                        limitations=['Paper reconstruction with assumed 350 ms latency and .30 round-trip costs.',
                                     'Not broker execution; no order rejection or queue model.',
                                     'No automatic strategy promotion or parameter changes.'])
                    atomic_write_json(str(args.output/'latest.json'), report, indent=2)
                    ticks.to_parquet(args.output/'ticks.parquet', index=False)
                    print(report['observed_at'], result['summary'], flush=True)
                    last_report = now
            except (ValueError, KeyError, RuntimeError) as error:
                errors.append(dict(at=now, message=str(error)))
            time.sleep(.5)
    finally:
        mt5.shutdown()
        latest = args.output/'latest.json'
        if latest.exists():
            report = json.loads(latest.read_text(encoding='utf-8'))
            report['completed_at'] = datetime.now(timezone.utc).isoformat()
            report['completed'] = time.monotonic()-started_monotonic >= args.minutes*60
            report['errors'] = errors[-10:]
            atomic_write_json(str(latest), report, indent=2)


if __name__ == '__main__':
    main()
