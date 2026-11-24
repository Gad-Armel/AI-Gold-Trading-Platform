"""Paired read-only timing of main-only candle fingerprint preparation."""
import json
from pathlib import Path
import statistics
import sys
import time
from unittest.mock import patch
import MetaTrader5 as mt5

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from services.market_data.scalping_snapshot import get_scalping_snapshot
from services.research.gold_advisory import _closed
from services.research.gold_main_candle_signal import MainCandleSignal


def main():
    if not mt5.initialize():
        raise RuntimeError(str(mt5.last_error()))
    try:
        snapshot=get_scalping_snapshot('XAUUSD')
    finally:
        mt5.shutdown()
    caches={name:MainCandleSignal() for name in ('canonical','validated_fast_path')}
    values={name:[] for name in caches}
    for cache in caches.values():
        cache.build(snapshot)
    for i in range(50):
        results={}
        for name in (list(caches) if i%2==0 else list(caches)[::-1]):
            if name=='canonical':
                with patch('services.research.gold_main_candle_signal.signature_frame',_closed):
                    started=time.perf_counter()
                    results[name]=caches[name].build(snapshot)
                    elapsed=(time.perf_counter()-started)*1000
            else:
                started=time.perf_counter()
                results[name]=caches[name].build(snapshot)
                elapsed=(time.perf_counter()-started)*1000
            values[name].append(elapsed)
        assert results['canonical']==results['validated_fast_path'], 'Signal output parity failed'
    summary={name:dict(median_ms=statistics.median(v),samples=len(v)) for name,v in values.items()}
    report=dict(results=summary,output_parity=True,
        reduction_percent=100*(1-summary['validated_fast_path']['median_ms']/summary['canonical']['median_ms']),
        limitations=['Same frozen broker snapshot, alternating order, warm cache in both cases.',
                     'Only validated numeric ordered frames use fast path; other inputs use canonical cleanup.',
                     'No changed signal algorithm, historical outcome selection or orders.',
                     'Component benchmark cannot establish whole-loop speed or trade profitability.'])
    (ROOT/'data/research/entry_efficiency/main_candle_signature_latency.json').write_text(json.dumps(report,indent=2))
    print(json.dumps(report,indent=2))


if __name__=='__main__':
    main()
