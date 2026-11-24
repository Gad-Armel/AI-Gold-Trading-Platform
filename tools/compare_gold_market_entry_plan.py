"""Frozen entry-plan associations at actual entry timestamps, not a new backtest.

Kept/rejected rows retain their ORIGINAL observed trade outcomes. Proposed
structural stops and different entries/exits are not replayed by this tool.
"""
import argparse
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import sys

import numpy as np
import pandas as pd

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from tools.audit_gold_market_decisions import load_capture,Quotes,epoch


def causal_context(m1, opened, quotes):
    """Latest completed M1 context; never include a forming/future candle."""
    unavailable=dict(available=False,reason='Causal M1 or executable quote unavailable')
    if m1 is None or m1.empty:
        return unavailable
    bars=m1[m1.time+60<=opened].sort_values('time').tail(200)
    i=quotes.quote_before(opened)
    if i is None or len(bars)<30 or opened-float(bars.time.iloc[-1])-60>65:
        return unavailable
    if not np.all(np.diff(bars.time.tail(14).to_numpy())==60):
        return dict(available=False,reason='Discontinuous latest14 completed M1 bars')
    close=bars.close.astype(float)
    tr=pd.concat([bars.high-bars.low,(bars.high-close.shift()).abs(),
                  (bars.low-close.shift()).abs()],axis=1).max(axis=1)
    atr=float(tr.ewm(alpha=1/14,adjust=False).mean().iloc[-1])
    if not math.isfinite(atr) or atr<=0:
        return dict(available=False,reason='Invalid causal M1 volatility')
    fast=close.ewm(span=12,adjust=False).mean()
    slow=close.ewm(span=26,adjust=False).mean()
    return dict(available=True,atr=atr,
        bar_id=datetime.fromtimestamp(float(bars.time.iloc[-1]),timezone.utc).isoformat(),
        close=float(close.iloc[-1]),previous_low=float(bars.low.iloc[-6:-1].min()),
        previous_high=float(bars.high.iloc[-6:-1].max()),
        trend=float((fast.iloc[-1]-slow.iloc[-1])/atr),
        momentum=float((close.iloc[-1]-close.iloc[-4])/atr),
        bid=float(quotes.bid[i]),ask=float(quotes.ask[i]),
        atr_definition='EWMA alpha1/14 over at most200 completed consecutive M1 true ranges')


def summary(rows):
    values=[r['original_net_usd'] for r in rows]
    wins=[v for v in values if v>0]
    losses=[v for v in values if v<0]
    return dict(trades=len(values),original_net_usd=round(sum(values),6),wins=len(wins),losses=len(losses),
        original_average_net_usd=sum(values)/len(values) if values else None,
        original_profit_factor=sum(wins)/-sum(losses) if losses else None)


def evaluate(audit,ticks,m1):
    from services.research.gold_market_entry_plan import market_entry_plan
    quotes=Quotes(ticks)
    ordered=ticks.sort_values('timestamp',kind='stable').drop_duplicates().reset_index(drop=True)
    stamps=ordered.timestamp.to_numpy(dtype=float)
    rows=[]
    for trade in sorted(audit['closed_positions'],key=lambda r:epoch(r['opened_utc'])):
        opened=epoch(trade['opened_utc'])
        first=int(np.searchsorted(stamps,opened-120.,side='left'))
        last=int(np.searchsorted(stamps,opened,side='right'))
        prefix=ordered.iloc[first:last]
        context=causal_context(m1,opened,quotes)
        plan=market_entry_plan(prefix,context,now=opened,direction=trade['direction'],
                               commission=.10,slippage=.20,maximum_risk=5.)
        stop=plan.get('levels',{}).get('sl')
        reference=(context.get('ask') if trade['direction']=='BUY' else context.get('bid'))
        proposed_risk=(float(reference)-float(stop))*(1 if trade['direction']=='BUY' else -1) if stop is not None and reference is not None else None
        rows.append(dict(position_id=int(trade['position_id']),opened_utc=trade['opened_utc'],
            closed_utc=trade['closed_utc'],direction=trade['direction'],
            original_net_usd=float(trade['net']),original_initial_stop_distance=trade.get('initial_stop_distance'),
            original_exit_reason=trade.get('exit_reason',trade.get('close_comment')),
            plan_allows_entry=bool(plan['allowed']),plan_blocks=plan.get('blocks',[]),
            context_available=bool(context.get('available')),context_reason=context.get('reason'),
            causal_m1_bar_id=context.get('bar_id'),causal_atr=context.get('atr'),
            candidate_setup_id=plan.get('setup_id'),proposed_stop=stop,proposed_risk_price=proposed_risk))
    if rows:
        opened=[epoch(r['opened_utc']) for r in rows]
        midpoint=len(rows)//2
        boundary=(opened[max(0,midpoint-1)]+opened[midpoint])/2
    else:
        boundary=None
    results=[]
    for label in ('all','first_half','second_half'):
        selected=rows if label=='all' else rows[:len(rows)//2] if label=='first_half' else rows[len(rows)//2:]
        results.append(dict(segment=label,
            original=summary(selected),
            kept_original_outcomes=summary([r for r in selected if r['plan_allows_entry']]),
            rejected_original_outcomes=summary([r for r in selected if not r['plan_allows_entry']]),
            unavailable_context=summary([r for r in selected if not r['context_available']])))
    return dict(role='RETROSPECTIVE_ACTUAL_ENTRY_FILTER_ASSOCIATIONS_NOT_NEW_STRATEGY_PNL',
        fixed_parameters=dict(commission_price=.10,slippage_price=.20,maximum_risk_price=5.),
        chronological_boundary_utc=datetime.fromtimestamp(boundary,timezone.utc).isoformat() if boundary is not None else None,
        chronological_split_rule='First half of entry-time-ordered positions versus remaining positions; not time-duration halves.',
        results=results,rows=rows,
        block_counts=dict(Counter(b for row in rows for b in row['plan_blocks'])),
        limitations=[
            'Kept/rejected P/L is ORIGINAL broker outcome under original stops/exits, not hypothetical P/L of proposed stops.',
            'Different entry timing, lower turnover, overlap, slot availability and equity paths are not replayed.',
            'No parameter search, threshold fitting or positive expectancy/profitability claim.',
            'Chronological halves are descriptive, not an untouched holdout after prior inspection.',
            'Causal ATR is EWMA14 on at most200 completed M1 bars; live cache initialization may differ slightly.',
            'Only captured quotes at/before entry are supplied. Missing quote/context causes conservative rejection and is reported.',
            'Unavailable feed history cannot establish a specific historical market cause.',
            'Source-vote authenticity, news, order-book data and broker execution conditions are not re-created by this association tool.'])


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--audit',required=True,type=Path)
    parser.add_argument('--capture',required=True,type=Path)
    parser.add_argument('--output',required=True,type=Path)
    args=parser.parse_args()
    audit=json.loads(args.audit.read_text(encoding='utf-8'))
    metadata,ticks,frames=load_capture(args.capture)
    if audit.get('account_fingerprint') and metadata.get('account_fingerprint') and audit['account_fingerprint']!=metadata['account_fingerprint']:
        raise ValueError('Audit and capture account mismatch')
    report=evaluate(audit,ticks,frames['M1'])
    from services.research import gold_market_entry_plan as helper
    helper_path=Path(helper.__file__)
    paths=[args.audit,args.capture/'metadata.json',args.capture/'ticks.parquet',helper_path]
    if (args.capture/'M1.parquet').exists():
        paths.append(args.capture/'M1.parquet')
    report.update(account_fingerprint=metadata.get('account_fingerprint'),
        account_identity_verified=bool(audit.get('account_fingerprint') and metadata.get('account_fingerprint')),
        input_audit=str(args.audit),input_capture=str(args.capture),
        source_hashes={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in paths})
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(report,indent=2,allow_nan=False),encoding='utf-8')
    print(json.dumps(dict(results=report['results'],block_counts=report['block_counts']),indent=2))


if __name__=='__main__':
    main()
