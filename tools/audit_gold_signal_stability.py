"""Read-only cache parity and indicator warm-up sensitivity; not a backtest."""
import argparse
from dataclasses import replace
from datetime import datetime, timezone
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from services.research.gold_advisory import build_gold_advisory
from services.research.gold_main_candle_signal import MainCandleSignal


def audit_snapshot(snapshot):
    reference = build_gold_advisory(snapshot)
    cached = MainCandleSignal().build(snapshot)
    parity = {name: {key: reference['horizons'][name][key] == cached['horizons'][name][key]
                     for key in ('bias', 'directional_score', 'levels', 'votes')}
              for name in ('SCALP', 'INTRADAY', 'SWING')}
    windows = {}
    for count in (64, 128, 256):
        candidate = replace(snapshot, candles={name: frame.tail(count).copy()
                            for name, frame in snapshot.candles.items()})
        report = build_gold_advisory(candidate)
        windows[str(count)] = {name: dict(bias=item['bias'], score=item['directional_score'],
            score_change=round(item['directional_score']-reference['horizons'][name]['directional_score'], 6),
            same_bias=item['bias'] == reference['horizons'][name]['bias'])
            for name, item in report['horizons'].items()}
    return dict(as_of=datetime.now(timezone.utc).isoformat(), read_only=True,
                cache_parity=parity, warmup_windows=windows,
                warmup_source_rows={str(count): {name: min(count, len(frame))
                    for name, frame in snapshot.candles.items()} for count in (64, 128, 256)},
                source_rows={name: len(frame) for name, frame in snapshot.candles.items()},
                limitations=['Single snapshot diagnostic, not a performance or full lookahead audit.',
                             'Warm-up sensitivity is reported; no model is promoted or retuned.',
                             'Framework methods are adapted, not a run of Freqtrade on MT5.'])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    import MetaTrader5 as mt5
    from services.market_data.scalping_snapshot import get_scalping_snapshot
    if not mt5.initialize(timeout=10000):
        raise RuntimeError(str(mt5.last_error()))
    try:
        account = mt5.account_info()
        if account is None or account.trade_mode != mt5.ACCOUNT_TRADE_MODE_DEMO:
            raise RuntimeError('Verified demo account required')
        result = audit_snapshot(get_scalping_snapshot('XAUUSD'))
    finally:
        mt5.shutdown()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2), encoding='utf-8')
    print(json.dumps(result, indent=2))
    if not all(all(checks.values()) for checks in result['cache_parity'].values()):
        raise RuntimeError('Cache parity failed; inspect evidence before deployment')


if __name__ == '__main__':
    main()
