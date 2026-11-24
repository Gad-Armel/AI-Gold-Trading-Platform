"""Read-only demo capture or exact captured-input replay; never sends orders."""
import argparse
from dataclasses import asdict
from datetime import datetime, timezone
import json
import math
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from config import gold_consensus_settings as settings
from services.research.gold_smc import SmcConfig, SmcStrategy
from services.utils.atomic_json import atomic_write_json


def evaluate(capture, config):
    if capture.get('symbol') != 'XAUUSD':
        raise ValueError('This audit is XAUUSD only')
    return SmcStrategy(config).assess(capture['candles'], now=capture['now'],
        bid=capture['bid'], ask=capture['ask'], offset=capture['offset'])


def capture_demo():
    import MetaTrader5 as mt5
    if not mt5.initialize(timeout=10000):
        raise RuntimeError(f'MT5 unavailable: {mt5.last_error()}')
    try:
        account = mt5.account_info()
        if account is None or account.trade_mode != mt5.ACCOUNT_TRADE_MODE_DEMO:
            raise ValueError('Read-only capture requires a demo account')
        tick = mt5.symbol_info_tick('XAUUSD')
        if tick is None:
            raise ValueError('No XAUUSD quote')
        now = datetime.now(timezone.utc).timestamp()
        stamp = float(tick.time_msc)/1000-settings.MT5_SERVER_UTC_OFFSET_SECONDS
        if not math.isfinite(stamp) or not -5 <= now-stamp <= 3:
            raise ValueError('Quote stale or clock policy inconsistent; capture aborted')
        candles = {}
        for name, count in (('M1', 180), ('M5', 160), ('M15', 140), ('H1', 120)):
            rows = mt5.copy_rates_from_pos('XAUUSD', getattr(mt5, 'TIMEFRAME_'+name), 0, count)
            if rows is None:
                raise ValueError(f'{name} history unavailable')
            candles[name] = [{key: row[key].item() for key in rows.dtype.names} for row in rows]
        return dict(symbol='XAUUSD', now=now, bid=float(tick.bid), ask=float(tick.ask),
                    offset=settings.MT5_SERVER_UTC_OFFSET_SECONDS, candles=candles,
                    observed_at=datetime.now(timezone.utc).isoformat(), execution_enabled=False)
    finally:
        mt5.shutdown()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument('--capture-demo', action='store_true')
    source.add_argument('--input', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if args.input and args.input.resolve() == args.output.resolve():
        raise ValueError('Input evidence must not be overwritten')
    config = SmcConfig(**settings.SCALP_SMC_CONFIG)
    saved = json.loads(args.input.read_text(encoding='utf-8-sig')) if args.input else None
    capture = saved['capture'] if saved else capture_demo()
    if saved:
        config = SmcConfig(**saved['config'])
    result = evaluate(capture, config)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    atomic_write_json(args.output, dict(capture=capture, config=asdict(config), report=result,
        orders_sent=False, profitability_test=False), indent=2)
    print(json.dumps(dict(output=str(args.output), available=result['available'],
        candidates=len(result['candidates']), reason=result.get('reason'), orders_sent=False)))


if __name__ == '__main__':
    main()
