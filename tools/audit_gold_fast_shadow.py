"""Capture the XAUUSD fast research screen on demo; never submit orders."""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from config import gold_consensus_settings as settings
from services.research.gold_s30_shadow import s30_observation
from services.research.gold_tick_history import TickHistoryBuffer
from services.utils.atomic_json import atomic_write_json


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--commission-price', type=float)
    parser.add_argument('--slippage-price', type=float)
    parser.add_argument('--period-seconds', type=int, choices=(1, 5, 15, 30), default=30)
    args = parser.parse_args()
    import MetaTrader5 as mt5
    if not mt5.initialize(timeout=10000):
        raise RuntimeError('MT5 initialization failed')
    try:
        account = mt5.account_info()
        terminal = mt5.terminal_info()
        if account is None or account.trade_mode != mt5.ACCOUNT_TRADE_MODE_DEMO:
            raise RuntimeError('Verified demo account required')
        if terminal is None or not terminal.connected:
            raise RuntimeError('Connected terminal required')
        now = datetime.now(timezone.utc)
        ticks, health = TickHistoryBuffer().refresh(mt5, settings.SYMBOL, now)
        report = dict(observed_at=now.isoformat(), read_only=True, symbol=settings.SYMBOL,
                      tick_health=health, observation=s30_observation(
                          ticks, now=now.timestamp(), commission_price=args.commission_price,
                          slippage_price=args.slippage_price, period_seconds=args.period_seconds))
        if not health['available']:
            report['observation'] = dict(available=False, execution_enabled=False,
                                         role='SHADOW_ONLY', reason=health['error'])
        args.output.parent.mkdir(parents=True, exist_ok=True)
        atomic_write_json(str(args.output), report, indent=2)
        print(json.dumps(report, indent=2))
    finally:
        mt5.shutdown()


if __name__ == '__main__':
    main()
