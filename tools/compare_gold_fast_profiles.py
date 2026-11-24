"""Read-only comparison of two frozen fast-entry profiles; never sends orders."""
import argparse
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import numpy as np
import pandas as pd
from config import gold_consensus_settings as settings
from services.market_data.gold_broker_clock import to_broker_time
from services.research.gold_s30_shadow import s30_observation
from services.research.gold_tick_markout import executable_markout, validate_ticks
from services.utils.atomic_json import atomic_write_json


def main():
    import MetaTrader5 as mt5
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', required=True)
    args = parser.parse_args()
    root = Path(args.output)
    root.mkdir(parents=True, exist_ok=True)
    end = datetime.now(timezone.utc)
    start = end-timedelta(minutes=30)
    if not mt5.initialize(timeout=10000):
        raise RuntimeError(mt5.last_error())
    try:
        account = mt5.account_info()
        if account is None or account.trade_mode != 0:
            raise RuntimeError('Demo account required')
        raw = mt5.copy_ticks_range('XAUUSD', to_broker_time(start), to_broker_time(end), mt5.COPY_TICKS_ALL)
        if raw is None or len(raw) == 0:
            raise RuntimeError('Broker tick history unavailable')
        ticks = pd.DataFrame(dict(timestamp=raw['time_msc']/1000-settings.MT5_SERVER_UTC_OFFSET_SECONDS,
                                  bid=raw['bid'], ask=raw['ask']))
        ticks = validate_ticks(ticks)
    finally:
        mt5.shutdown()
    np.savez_compressed(root/'ticks.npz', timestamp=ticks.timestamp.to_numpy(),
                        bid=ticks.bid.to_numpy(), ask=ticks.ask.to_numpy())
    rows = []
    for name, count, multiple in (('control', 3, 3.), ('aggressive_demo', 2, 1.5)):
        for period in (5, 15, 30):
            marks, checked, passed = [], 0, 0
            for epoch in range(int(start.timestamp())+120, int(end.timestamp())-31, period):
                lower = ticks.timestamp.searchsorted(epoch-150)
                upper = ticks.timestamp.searchsorted(epoch, side='right')
                observation = s30_observation(ticks.iloc[lower:upper], now=epoch,
                    period_seconds=period, bar_count=count, range_cost_multiple=multiple,
                    commission_price=.1, slippage_price=.2)
                checked += 1
                if (not observation.get('available') or observation.get('direction') not in ('BUY', 'SELL')
                        or observation.get('fast_candidate', {}).get('blocks')):
                    continue
                passed += 1
                mark = executable_markout(ticks, epoch, observation['direction'], horizon_seconds=15,
                    latency_seconds=.25, commission_price=.1, slippage_price=.2)
                if mark:
                    marks.append(mark['main_net_price'])
            rows.append(dict(profile=name, timeframe=f'S{period}', checked=checked,
                eligible_quote_patterns=passed, labelled_observations=len(marks),
                mean_net_price=sum(marks)/len(marks) if marks else None,
                positive_fraction=sum(value > 0 for value in marks)/len(marks) if marks else None))
    report = dict(start_utc=start.isoformat(), end_utc=end.isoformat(), ticks=len(ticks),
        role='FROZEN_PROFILE_OPPORTUNITY_COMPARISON_NOT_STRATEGY_BACKTEST', results=rows,
        notes=['Overlapping observations, no margin/capacity/persistence or adaptive-exit replay.',
               'Two profiles frozen before comparison; no parameter optimizer.',
               'Assumed costs are round-trip price equivalents; not measured fill guarantees.',
               'Higher candidate count does not establish accuracy or profitability.'])
    atomic_write_json(root/'report.json', report)
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
