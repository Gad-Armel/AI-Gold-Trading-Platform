"""Read-only parity check of the main candle cache against live MT5 analysis."""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import MetaTrader5 as mt5
from services.market_data.scalping_snapshot import get_scalping_snapshot
from services.research.gold_advisory import build_gold_advisory
from services.research.gold_main_candle_signal import MainCandleSignal


def main():
    if not mt5.initialize():
        raise RuntimeError(mt5.last_error())
    try:
        snapshot = get_scalping_snapshot('XAUUSD')
        original = build_gold_advisory(snapshot)
        cache = MainCandleSignal()
        cache.build(snapshot)
        cached = cache.build(snapshot)
        result = {}
        for name in ('SCALP', 'INTRADAY', 'SWING'):
            expected, actual = original['horizons'][name], cached['horizons'][name]
            checks = {key: expected[key] == actual[key] for key in
                      ('bias', 'directional_score', 'levels', 'votes')}
            result[name] = dict(bias=expected['bias'], score=expected['directional_score'], checks=checks)
            if not all(checks.values()):
                raise AssertionError(result)
        print(json.dumps(result))
    finally:
        mt5.shutdown()


if __name__ == '__main__':
    main()
