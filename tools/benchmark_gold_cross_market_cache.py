"""Paired read-only benchmark of completed-bar transmission reuse."""
from copy import deepcopy
import json
from pathlib import Path
import statistics
import sys
import time
from types import SimpleNamespace
import MetaTrader5 as mt5

PROJECT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(PROJECT))
from services.market_data.scalping_snapshot import get_scalping_snapshot
from services.research.gold_cross_market import CrossMarketCollector,PAIRS


def main():
    if not mt5.initialize():
        raise RuntimeError(str(mt5.last_error()))
    try:
        snapshot=get_scalping_snapshot('XAUUSD')
        frames={name:mt5.copy_rates_from_pos(name,mt5.TIMEFRAME_M5,0,160) for name in PAIRS}
        ticks={name:mt5.symbol_info_tick(name) for name in PAIRS}
        infos={name:mt5.symbol_info(name) for name in PAIRS}
        if any(value is None for value in [*frames.values(),*ticks.values(),*infos.values()]):
            raise RuntimeError('Missing cross-market snapshot')
        frozen=SimpleNamespace(TIMEFRAME_M5=mt5.TIMEFRAME_M5,
            symbol_info=lambda name:infos[name],symbol_info_tick=lambda name:ticks[name],
            copy_rates_from_pos=lambda name,*args:frames[name])
        # Tick timestamps are frozen solely for a paired calculation benchmark.
        # The collector's live quote checks are separately covered by tests.
        from unittest.mock import patch
        cached=CrossMarketCollector()
        values={'fresh':[],'cached':[]}
        with patch('services.research.gold_cross_market.quote_age',return_value=0):
            expected=deepcopy(cached.assess(frozen,snapshot))
            if not expected.get('available'):
                raise RuntimeError(expected.get('reason'))
            for i in range(50):
                for mode in (('fresh','cached') if i%2==0 else ('cached','fresh')):
                    if mode=='fresh':
                        cached.signature=None
                    started=time.perf_counter()
                    result=cached.assess(frozen,snapshot)
                    values[mode].append((time.perf_counter()-started)*1000)
                    assert result==expected, 'Output parity failed'
        summary={name:dict(median_ms=statistics.median(v),samples=len(v)) for name,v in values.items()}
        report=dict(results=summary,output_parity=True,
            reduction_percent=100*(1-summary['cached']['median_ms']/summary['fresh']['median_ms']),
            limitations=['Frozen read-only broker snapshot; quote freshness patched for paired timing only.',
                         'Alternating sequence reduces ordering bias; wall time still includes CPU contention.',
                         'Component computation benefit does not establish entry accuracy or profitability.'])
        (PROJECT/'data/research/entry_efficiency/cross_market_cache_latency.json').write_text(json.dumps(report,indent=2))
        print(json.dumps(report,indent=2))
    finally:
        mt5.shutdown()


if __name__=='__main__':
    main()
