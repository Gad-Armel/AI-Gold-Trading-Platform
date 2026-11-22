"""Capture demo quote history and broker metadata for offline research; no orders."""
import argparse
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import sys

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from config import gold_consensus_settings as settings
from services.market_data.gold_broker_clock import to_broker_time
from services.research.gold_s30_execution import account_fingerprint
from services.utils.atomic_json import atomic_write_json


def quote_windows(start, end):
    if start.tzinfo is None or end.tzinfo is None or start >= end:
        raise ValueError('Timezone-aware increasing quote window required')
    cursor = start.replace(microsecond=0)
    request_end = end.replace(microsecond=0)+timedelta(seconds=1)
    while cursor < request_end:
        finish = min(request_end, cursor+timedelta(minutes=30))
        yield cursor, finish
        cursor = finish


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--hours', type=float, default=24)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--end', help='Optional timezone-aware historical end, for reproducible corrected captures')
    parser.add_argument('--terminal-path')
    parser.add_argument('--expected-account-fingerprint')
    args = parser.parse_args()
    if not 0 < args.hours <= 72:
        parser.error('--hours must be in (0,72]')
    import MetaTrader5 as mt5
    if not mt5.initialize(*([args.terminal_path] if args.terminal_path else []), timeout=10000):
        raise RuntimeError('MT5 connection unavailable')
    try:
        account, info, terminal = mt5.account_info(), mt5.symbol_info('XAUUSD'), mt5.terminal_info()
        if account is None or account.trade_mode != mt5.ACCOUNT_TRADE_MODE_DEMO or account.currency != 'USD':
            raise RuntimeError('Verified USD demo required')
        if args.expected_account_fingerprint and account_fingerprint(account)!=args.expected_account_fingerprint:
            raise RuntimeError('Capture account differs from approved demo identity')
        if info is None or terminal is None or not terminal.connected:
            raise RuntimeError('Connected XAUUSD data required')
        captured_at = datetime.now(timezone.utc)
        end = datetime.fromisoformat(args.end).astimezone(timezone.utc) if args.end else captured_at
        if args.end and (datetime.fromisoformat(args.end).tzinfo is None or end > captured_at):
            raise ValueError('Historical end must be timezone-aware and not future-dated')
        start = end-timedelta(hours=args.hours)
        chunks = []
        chunk_metadata = []
        for cursor, finish in quote_windows(start, end):
            rows = mt5.copy_ticks_range('XAUUSD', to_broker_time(cursor), to_broker_time(finish), mt5.COPY_TICKS_ALL)
            if rows is None:
                raise RuntimeError(f'Quote-history chunk failed: {mt5.last_error()}')
            if len(rows):
                frame = pd.DataFrame(rows)
                frame['timestamp'] = frame.time_msc/1000-settings.MT5_SERVER_UTC_OFFSET_SECONDS
                frame = frame[(frame.timestamp >= max(cursor.timestamp(), start.timestamp())) &
                              (frame.timestamp < min(finish.timestamp(), end.timestamp()))]
                chunks.append(frame)
                chunk_metadata.append(dict(start=cursor.isoformat(), end=finish.isoformat(), ticks=len(frame)))
        if not chunks:
            raise RuntimeError('No historical ticks returned')
        ticks = pd.concat(chunks, ignore_index=True).sort_values('timestamp', kind='stable')
        ticks = ticks[np.isfinite(ticks[['timestamp', 'bid', 'ask']]).all(axis=1) &
                      (ticks.bid > 0) & (ticks.ask >= ticks.bid)]
        ticks = ticks.reset_index(drop=True)
        args.output.mkdir(parents=True, exist_ok=True)
        ticks.to_parquet(args.output/'ticks.parquet', index=False)
        rates_summary = {}
        for name, period in [('M1', mt5.TIMEFRAME_M1), ('M5', mt5.TIMEFRAME_M5), ('M15', mt5.TIMEFRAME_M15), ('H1', mt5.TIMEFRAME_H1)]:
            rows = mt5.copy_rates_range('XAUUSD', period, to_broker_time(start-timedelta(hours=24)), to_broker_time(end))
            if rows is not None:
                frame = pd.DataFrame(rows)
                frame.to_parquet(args.output/f'{name}.parquet', index=False)
                rates_summary[name] = len(frame)
        tick = mt5.symbol_info_tick('XAUUSD')
        metadata = dict(captured_at=captured_at.isoformat(), requested_end=end.isoformat(),
            chunk_boundaries='Whole seconds, half-open filtering; no fractional-second request gaps',
            chunks=chunk_metadata, read_only=True, account_fingerprint=account_fingerprint(account),
            symbol='XAUUSD', currency='USD', contract_size=info.trade_contract_size,
            tick_size=info.trade_tick_size, lot_size=.01, broker_offset_seconds=settings.MT5_SERVER_UTC_OFFSET_SECONDS,
            requested_start=start.isoformat(), tick_count=len(ticks), rates=rates_summary,
            first_utc=datetime.fromtimestamp(float(ticks.timestamp.iloc[0]), timezone.utc).isoformat(),
            last_utc=datetime.fromtimestamp(float(ticks.timestamp.iloc[-1]), timezone.utc).isoformat(),
            bid=float(tick.bid) if tick else None, ask=float(tick.ask) if tick else None,
            spread_quantiles={str(quantile):float((ticks.ask-ticks.bid).quantile(quantile)) for quantile in (.5,.9,.99)},
            quote_gaps_over_3_seconds=int((ticks.timestamp.diff()>3).sum()))
        atomic_write_json(str(args.output/'metadata.json'), metadata, indent=2)
        print(json.dumps(metadata, indent=2))
    finally:
        mt5.shutdown()


if __name__ == '__main__':
    main()
