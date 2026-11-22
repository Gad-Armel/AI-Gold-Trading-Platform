"""Read-only display of official-source health and observed dollar transmission."""
import argparse
import json
import time
from services.execution.mt5_connector import connect_mt5, disconnect_mt5
from services.market_data.scalping_snapshot import get_scalping_snapshot
from services.research.background_refresh import BackgroundRefresh
from services.research.gold_cross_market import CrossMarketCollector
from services.research.gold_source_intelligence import SOURCES, fetch_source, source_status


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--interval-seconds', type=float, default=15.)
    parser.add_argument('--max-minutes', type=float, default=0.)
    args = parser.parse_args()
    if not connect_mt5():
        return 1
    import MetaTrader5 as mt5
    background, cross = BackgroundRefresh(), CrossMarketCollector()
    started = time.monotonic()
    try:
        while args.max_minutes <= 0 or time.monotonic()-started < args.max_minutes*60:
            values = {name: background.poll(name, cadence, lambda name=name: fetch_source(name), {})
                      for name, (_, cadence) in SOURCES.items()}
            report = source_status(values, background.errors)
            report['cross_market'] = cross.assess(mt5, get_scalping_snapshot('XAUUSD'))
            print(json.dumps(report, indent=2), flush=True)
            time.sleep(max(2., args.interval_seconds))
    except KeyboardInterrupt:
        pass
    finally:
        background.close()
        disconnect_mt5()
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
