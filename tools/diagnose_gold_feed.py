"""Read-only MT5 quote/history health capture. Never sends trading requests."""
import sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
import json
import time
from datetime import datetime,timezone
from types import SimpleNamespace
import MetaTrader5 as mt5
from services.research.gold_runtime_health import market_health
from services.research.gold_advisory_v3 import build_gold_advisory_v3
from services.research.gold_tick_history import TickHistoryBuffer
from config import gold_consensus_settings as settings


def main():
    if not mt5.initialize():
        raise RuntimeError(f'MT5 initialization failed: {mt5.last_error()}')
    buffer=TickHistoryBuffer();captures=[]
    try:
        for iteration in range(3):
            now=datetime.now(timezone.utc)
            tick=mt5.symbol_info_tick(settings.SYMBOL)
            snapshot=SimpleNamespace(tick_time_msc=getattr(tick,'time_msc',0),
                bid=getattr(tick,'bid',0),ask=getattr(tick,'ask',0))
            health=market_health(snapshot,mt5.terminal_info(),now=now.timestamp())
            report=build_gold_advisory_v3(mt5,settings.SYMBOL,now=now,history=buffer)
            captures.append(dict(health=health,history=report['history_health'],tick_count=report['tick_count'],
                horizons={name:{k:lane[k] for k in ('bias','directional_score','source_usable','blocks')}
                          for name,lane in report['horizons'].items()}))
            if iteration < 2:time.sleep(2)
    finally:
        mt5.shutdown()
    target=ROOT/'data/research/feed_reliability';target.mkdir(parents=True,exist_ok=True)
    (target/'diagnostic.json').write_text(json.dumps(captures,indent=2),encoding='utf-8')
    print(json.dumps(captures,indent=2))


if __name__=='__main__':main()
