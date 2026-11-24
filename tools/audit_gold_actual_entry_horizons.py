"""Tick-path outcomes of actual entries with fixed original advisory horizons.

Exit-only diagnostic: never changes orders and never replays changed entries.
"""
from datetime import datetime,timedelta,timezone
import json
from pathlib import Path
import sys
import numpy as np
import MetaTrader5 as mt5

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from config import gold_consensus_settings as settings
from services.market_data.gold_broker_clock import to_broker_time


def outcome(times,bids,asks,opened,entry,direction,horizon):
    sign=1 if direction=='BUY' else -1
    deadline=opened+horizon
    start=np.searchsorted(times,opened,side='left')
    end=np.searchsorted(times,deadline,side='right')-1
    if (not len(times) or start>=len(times) or end<start or deadline>times[-1]
            or times[start]-opened>2 or deadline-times[end]>15):
        return dict(available=False,reason='Incomplete or stale entry/horizon quote coverage')
    path=bids[start:end+1] if sign==1 else asks[start:end+1]
    moves=sign*(path-entry)
    hit=np.flatnonzero(moves<=-5.)
    index=int(hit[0]) if len(hit) else len(path)-1
    # Quote paths can gap beyond the planned $5 stop. Charge the actual first
    # adverse quote plus exit slippage; do not truncate loss to the risk budget.
    profit=float(moves[index])-.05
    stop_time=float(times[start+index]) if len(hit) else None
    gap=max(float(times[start]-opened),float(deadline-times[end]),
            float(np.diff(times[start:end+1]).max()) if end>start else 0.)
    return dict(available=True,profit=round(profit,4),stop_hit=bool(len(hit)),stop_time=stop_time,
        exit_epoch=float(times[start+index]) if len(hit) else deadline,
        peak=round(float(moves.max()),4),trough=round(float(moves.min()),4),maximum_gap_seconds=round(gap,3))


def metrics(rows,key):
    values=[row[key] for row in rows]
    gains=sum(max(0,v) for v in values);losses=-sum(min(0,v) for v in values)
    return dict(trades=len(values),net=round(sum(values),2),
        mean=round(sum(values)/len(values),4) if values else None,
        profit_factor=round(gains/losses,4) if losses else None)


def main():
    now=datetime.now(timezone.utc)
    beginning=now.replace(hour=0,minute=0,second=0,microsecond=0)
    output=ROOT/'data/research/entry_efficiency/actual_entry_horizons'/now.strftime('%Y%m%dT%H%M%SZ')
    output.mkdir(parents=True,exist_ok=True)
    closed={}
    for path in sorted((ROOT/'data/monitoring').glob('*/observations.jsonl')):
        for line in path.open(encoding='utf-8'):
            obs=json.loads(line)
            for name,lane in obs.get('status',{}).get('lanes',{}).items():
                for trade in lane.get('closed_trades',[]):
                    opened=datetime.fromisoformat(trade['opened_at'])
                    if beginning<=opened<=now:
                        closed[str(trade['position_id'])]=dict(trade,horizon=name)
    if not mt5.initialize():
        raise RuntimeError(str(mt5.last_error()))
    try:
        ticks=mt5.copy_ticks_range('XAUUSD',to_broker_time(beginning),to_broker_time(now),mt5.COPY_TICKS_ALL)
        if ticks is None or not len(ticks):
            raise RuntimeError(str(mt5.last_error()))
        times=ticks['time_msc']/1000-settings.MT5_SERVER_UTC_OFFSET_SECONDS
        bids,asks=ticks['bid'],ticks['ask']
        valid=(times>=beginning.timestamp())&(times<=now.timestamp())&np.isfinite(bids)&np.isfinite(asks)&(bids>0)&(asks>=bids)
        times,bids,asks=times[valid],bids[valid],asks[valid]
        order=np.argsort(times,kind='stable')
        times,bids,asks=times[order],bids[order],asks[order]
        np.savez_compressed(output/'ticks.npz',utc_time=times,bid=bids,ask=asks)
    finally:
        mt5.shutdown()
    rows=[]
    split=datetime.fromisoformat('2026-10-08T06:08:30+00:00').timestamp()
    for ticket,trade in sorted(closed.items(),key=lambda item:item[1]['opened_at']):
        opened=datetime.fromisoformat(trade['opened_at']).timestamp()
        horizon={'SCALP':300,'INTRADAY':1800,'SWING':7200}[trade['horizon']]
        result=outcome(times,bids,asks,opened,trade['entry_price'],trade['direction'],horizon)
        rows.append(dict(ticket=ticket,lane=trade['horizon'],opened_at=trade['opened_at'],
            period='EARLY' if opened<split else 'LATER',actual=trade['profit'],
            horizon_seconds=horizon,**result))
    groups=[]
    usable=[row for row in rows if row['available'] and row['maximum_gap_seconds']<=10]
    for period in ('EARLY','LATER','ALL'):
        for lane in ('SCALP','INTRADAY','SWING','ALL'):
            sample=[row for row in usable if (period=='ALL' or row['period']==period)
                    and (lane=='ALL' or row['lane']==lane)]
            groups.append(dict(period=period,lane=lane,actual=metrics(sample,'actual'),
                               fixed_horizon=metrics(sample,'profit')))
    report=dict(captured_at=now.isoformat(),ticks=len(times),rows=rows,groups=groups,
        usable_trades=len(usable),excluded_incomplete=sum(not row['available'] for row in rows),
        excluded_gaps=sum(row['available'] and row['maximum_gap_seconds']>10 for row in rows),
        live_approved=False,limitations=[
            'Same actual historical entries/fills; fixed 5/30/120-minute exits known from advisory horizons.',
            '$5 planned stop, actual executable bid/ask and $.05 exit slippage; adverse gaps charged in full.',
            'Quote ticks may omit broker-server events; paths with gaps over 10 seconds excluded.',
            'No changed re-entry, capacity, margin, adaptive exit or correlated exposure simulation.',
            'Hypothetical holds can overlap; summed label outcomes are not a realizable portfolio return.',
            'Earlier/later periods were previously inspected; this decomposition is not blind policy validation.',
            'Actual closed-trade selection excludes open positions and unobserved trades; no policy promoted.'])
    (output/'report.json').write_text(json.dumps(report,indent=2))
    print(json.dumps(dict(path=str(output),ticks=len(times),groups=groups,
        usable_trades=len(usable),excluded_incomplete=report['excluded_incomplete'],excluded_gaps=report['excluded_gaps']),indent=2))


if __name__=='__main__':
    main()
