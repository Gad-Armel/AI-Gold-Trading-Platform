"""Read-only actual-terminal comparison of USD protective stop preparation."""
import json
from datetime import datetime, timezone
from pathlib import Path
import statistics
import sys
import time
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from services.execution import scalp_profit_calculator as old
from services.execution.gold_consensus_demo_broker import _money_stop_price, _planned_risk_block


def main():
    import MetaTrader5 as mt5
    if not mt5.initialize():
        raise RuntimeError(mt5.last_error())
    try:
        account = mt5.account_info()
        assert account and account.trade_mode == mt5.ACCOUNT_TRADE_MODE_DEMO
        info, tick = mt5.symbol_info('XAUUSD'), mt5.symbol_info_tick('XAUUSD')
        results = {}
        for side in ('BUY', 'SELL'):
            price = tick.ask if side == 'BUY' else tick.bid
            for method in ('previous', 'broker_grid'):
                samples, stops, calls = [], [], []
                for _ in range(25):
                    with patch.object(mt5, 'order_calc_profit', wraps=mt5.order_calc_profit) as calc:
                        start = time.perf_counter()
                        stop = (old.find_price_for_profit(symbol='XAUUSD', direction=side,
                            entry_price=price, lot_size=.01, contract_size=info.trade_contract_size,
                            target_profit_usd=-5, point=info.point)[0] if method == 'previous' else
                            _money_stop_price(mt5, info, side, .01, price, 5))
                        rejected = _planned_risk_block(mt5, side, .01, price, stop)
                        samples.append((time.perf_counter()-start)*1000)
                        stops.append(stop)
                        calls.append(calc.call_count)
                    if method == 'broker_grid' and rejected:
                        raise RuntimeError(rejected)
                results[side+'_'+method] = dict(median_ms=statistics.median(samples),
                    p95_ms=sorted(samples)[23], mean_calls=statistics.mean(calls),
                    stop=stops[-1], rejected_by_final_risk_check=bool(rejected))
        report = dict(created_at=datetime.now(timezone.utc).isoformat(), measured_terminal=True,
            broker_symbol={name:getattr(info,name) for name in
                           ('point','digits','trade_tick_size','trade_contract_size','trade_stops_level','volume_min','volume_step')},
            results=results, note='Read-only calculator latency; not order latency or measured profit improvement.')
        target = ROOT/'data/research/blueprint_review_20261009/stop_preparation_benchmark.json'
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(report, indent=2))
        print(json.dumps(report, indent=2))
    finally:
        mt5.shutdown()


if __name__ == '__main__':
    main()
