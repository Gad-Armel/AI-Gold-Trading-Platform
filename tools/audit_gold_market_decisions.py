"""Offline, descriptive market reconstruction for every closed demo position.

Never sends orders or infers a unique cause of a losing trade. Pre-entry
features use quotes at/before the recorded entry and completed candles only.
"""
import argparse
from collections import Counter, defaultdict
from datetime import datetime, timezone
import csv
import hashlib
import json
import math
from pathlib import Path

import numpy as np
import pandas as pd


def epoch(value):
    stamp = datetime.fromisoformat(value)
    if stamp.tzinfo is None:
        raise ValueError('Timezone-aware trade timestamp required')
    return stamp.timestamp()


class Quotes:
    def __init__(self, frame):
        data = frame[['timestamp', 'bid', 'ask']].astype(float)
        if data.empty or not np.isfinite(data.to_numpy()).all() or (data.bid <= 0).any() or (data.ask < data.bid).any():
            raise ValueError('Nonempty finite valid executable quotes required')
        data = data.sort_values('timestamp', kind='stable').drop_duplicates()
        self.time, self.bid, self.ask = (data[k].to_numpy() for k in ('timestamp', 'bid', 'ask'))

    def window(self, start, end, *, gap=3., minimum=2, require_end_coverage=True):
        first = int(np.searchsorted(self.time, start, side='left'))
        last = int(np.searchsorted(self.time, end, side='right'))
        indices = slice(first, last)
        stamps = self.time[indices]
        largest = float(np.diff(np.r_[start, stamps, end]).max()) if len(stamps) else end-start
        covered = self.time[0] <= start and (not require_end_coverage or self.time[-1] >= end)
        return indices, dict(available=bool(covered and len(stamps) >= minimum and largest <= gap),
            quotes=len(stamps), maximum_gap_seconds=largest,
            reason=('Covered observed quote window' if covered and len(stamps) >= minimum and largest <= gap else
                    'Missing, insufficient or discontinuous quote coverage'))

    def quote_before(self, when, *, maximum_age=2.):
        i = int(np.searchsorted(self.time, when, side='right'))-1
        if i < 0 or when-self.time[i] > maximum_age:
            return None
        return i


def completed_context(frame, seconds, opened, sign):
    if frame is None or frame.empty:
        return dict(available=False, reason='Completed candle data unavailable')
    rows = frame[frame.time+seconds <= opened].sort_values('time').tail(20)
    if len(rows) < 6 or opened-(float(rows.time.iloc[-1])+seconds) > seconds+5:
        return dict(available=False, reason='Insufficient or stale completed candles')
    if not np.all(np.diff(rows.time.to_numpy()) == seconds):
        return dict(available=False, reason='Discontinuous completed candle context')
    close = rows.close.astype(float)
    tr = pd.concat([rows.high-rows.low, (rows.high-close.shift()).abs(),
                    (rows.low-close.shift()).abs()], axis=1).max(axis=1)
    atr = float(tr.tail(14).mean())
    net = float(close.iloc[-1]-close.iloc[-6])
    path = float(close.diff().abs().tail(5).sum())
    return dict(available=True, last_completed_close_epoch=float(rows.time.iloc[-1])+seconds,
        direction='BUY' if net > 0 else 'SELL' if net < 0 else 'WAIT',
        signed_five_bar_move_price=sign*net, signed_five_bar_move_atr=sign*net/atr if atr > 0 else None,
        efficiency=abs(net)/path if path else 0., atr_price=atr,
        reason='Five completed close changes; descriptive trend, not a prediction')


def pre_entry_features(quotes, opened, direction, *, entry_price, stop_distance,
                       m1=None, m5=None, assumed_additional_cost=.30):
    sign = 1 if direction == 'BUY' else -1
    result = dict(quote_available=False, pressure={}, m1=completed_context(m1,60,opened,sign),
                  m5=completed_context(m5,300,opened,sign))
    i = quotes.quote_before(opened)
    if i is not None:
        bid, ask = float(quotes.bid[i]), float(quotes.ask[i])
        spread = ask-bid
        executable = bid if sign == 1 else ask
        mark = sign*(executable-entry_price)
        result.update(quote_available=True, quote_epoch=float(quotes.time[i]),
            quote_age_seconds=opened-float(quotes.time[i]), bid=bid, ask=ask, spread_price=spread,
            initial_executable_mark_price=mark,
            estimated_round_trip_cost_price=spread+assumed_additional_cost,
            additional_cost_assumption_price=assumed_additional_cost,
            spread_to_stop=spread/stop_distance if stop_distance and stop_distance>0 else None,
            estimated_cost_to_stop=(spread+assumed_additional_cost)/stop_distance if stop_distance and stop_distance>0 else None,
            remaining_stop_room_price=stop_distance+mark if stop_distance and stop_distance>0 else None)
    for seconds in (3,12,30):
        selected, health = quotes.window(opened-seconds,opened,gap=min(3.,seconds/2),minimum=4,
                                        require_end_coverage=False)
        if health['available']:
            bids,asks = quotes.bid[selected],quotes.ask[selected]
            mids=(bids+asks)/2
            net=float(mids[-1]-mids[0])
            path=float(np.abs(np.diff(mids)).sum())
            health.update(signed_bid_move_price=sign*float(bids[-1]-bids[0]),
                signed_ask_move_price=sign*float(asks[-1]-asks[0]),
                signed_mid_move_price=sign*net, efficiency=abs(net)/path if path else 0.,
                both_sides_opposed=bool(sign*(bids[-1]-bids[0])<0 and sign*(asks[-1]-asks[0])<0))
        result['pressure'][str(seconds)] = health
    return result


def summarize(rows):
    values=[r['net'] for r in rows]
    wins=[v for v in values if v>0]
    losses=[v for v in values if v<0]
    return dict(trades=len(values),wins=len(wins),losses=len(losses),net_usd=round(sum(values),6),
                average_net=sum(values)/len(values) if values else None,
                profit_factor=sum(wins)/-sum(losses) if losses else None)


def evaluate(audit, ticks, m1=None, m5=None, *, contract_size=100., assumed_additional_cost=.30):
    if not math.isfinite(contract_size) or contract_size<=0 or not math.isfinite(assumed_additional_cost) or assumed_additional_cost<0:
        raise ValueError('Finite positive contract and nonnegative cost assumption required')
    quotes=Quotes(ticks)
    rows=[]
    previous=[]
    minute_counts=Counter()
    for trade in sorted(audit['closed_positions'],key=lambda r:epoch(r['opened_utc'])):
        opened,closed=epoch(trade['opened_utc']),epoch(trade['closed_utc'])
        direction=trade['direction']
        if direction not in ('BUY','SELL') or closed<opened:
            raise ValueError('Valid direction and increasing trade times required')
        price,volume,net=(float(trade[k]) for k in ('entry_price','volume','net'))
        if not all(math.isfinite(v) for v in (price,volume,net)) or min(price,volume)<=0:
            raise ValueError('Finite valid trade prices and size required')
        stop=trade.get('initial_stop_distance')
        stop=float(stop) if stop is not None and math.isfinite(float(stop)) and float(stop)>0 else None
        sign=1 if direction=='BUY' else -1
        before=pre_entry_features(quotes,opened,direction,entry_price=price,stop_distance=stop,
            m1=m1,m5=m5,assumed_additional_cost=assumed_additional_cost)
        during_index,during=quotes.window(opened,closed,gap=3.)
        if during['available']:
            executable=quotes.bid[during_index] if sign==1 else quotes.ask[during_index]
            excursions=sign*(executable-price)*volume*contract_size
            during.update(maximum_favorable_gross_usd=float(excursions.max()),
                maximum_adverse_gross_usd=float(excursions.min()),
                peak_r=float(excursions.max()/(stop*volume*contract_size)) if stop else None,
                gross_peak_minus_realized_net_usd=float(excursions.max()-net))
        post_index,post=quotes.window(closed,closed+15,gap=3.)
        if post['available']:
            executable=quotes.bid[post_index] if sign==1 else quotes.ask[post_index]
            post['additional_quoted_move_usd']=sign*float(executable[-1]-executable[0])*volume*contract_size
            post['hypothetical_gross_from_original_entry_usd']=sign*float(executable[-1]-price)*volume*contract_size
        overlap=[p for p in previous if p['opened']<=opened<p['closed'] and p['direction']==direction]
        minute_key=(int(opened//60),direction)
        repeated=minute_counts[minute_key]
        flags=[]
        for seconds,measure in before['pressure'].items():
            if measure.get('both_sides_opposed'):
                flags.append(f'PREENTRY_BID_ASK_OPPOSED_{seconds}S')
        for frame in ('m1','m5'):
            if before[frame].get('available') and before[frame]['signed_five_bar_move_price']<0:
                flags.append(f'COMPLETED_{frame.upper()}_TREND_OPPOSED')
        if before.get('estimated_cost_to_stop') is not None and before['estimated_cost_to_stop']>=.5:
            flags.append('ESTIMATED_COST_AT_LEAST_HALF_STOP_DISTANCE')
        if before.get('spread_to_stop') is not None and before['spread_to_stop']>=.4:
            flags.append('ENTRY_SPREAD_AT_LEAST_40_PERCENT_OF_STOP')
        if overlap:
            flags.append('OVERLAPPING_SAME_DIRECTION_EXPOSURE')
        if repeated:
            flags.append('REPEATED_DIRECTION_WITHIN_SAME_UTC_MINUTE')
        if during.get('available') and net<0 and during['maximum_favorable_gross_usd']<=0:
            flags.append('LOSS_NEVER_OBSERVED_EXECUTABLY_POSITIVE')
        if during.get('available') and net<0 and during['maximum_favorable_gross_usd']>=1.:
            flags.append('LOSS_AFTER_OBSERVED_GROSS_PEAK_AT_LEAST_ONE_USD')
        if not during['available']:
            flags.append('TRADE_PATH_UNASSESSABLE_FROM_CAPTURE')
        if not any(v.get('available') for v in before['pressure'].values()):
            flags.append('PREENTRY_PRESSURE_UNASSESSABLE_FROM_CAPTURE')
        evidence_notes=[]
        if not flags or flags==['TRADE_PATH_UNASSESSABLE_FROM_CAPTURE']:
            evidence_notes.append('No distinctive cause established from available measurements.')
        evidence_notes.append('Flags describe observed conditions, not proven causes or profitable counterfactuals.')
        rows.append(dict(position_id=int(trade['position_id']),opened_utc=trade['opened_utc'],
            closed_utc=trade['closed_utc'],direction=direction,entry_price=price,volume=volume,net=net,
            hold_seconds=closed-opened,initial_stop_distance=stop,
            exit_reason=trade.get('exit_reason') or trade.get('close_comment','UNKNOWN'),
            source_evidence=trade.get('evidence'),strategy=trade.get('timeframe','UNKNOWN'),
            pre_entry=before,during=during,post_exit_15s=post,
            same_direction_positions_already_open=len(overlap),same_minute_prior_direction_entries=repeated,
            source_event_identity_available=bool(trade.get('setup_id')),
            flags=flags,notes=evidence_notes))
        previous.append(dict(opened=opened,closed=closed,direction=direction))
        minute_counts[minute_key]+=1
    flags=sorted({f for row in rows for f in row['flags']})
    return dict(role='DESCRIPTIVE_PER_POSITION_MARKET_AUDIT_NO_ORDER_AUTHORITY',
        summary=summarize(rows),flag_groups={f:summarize([r for r in rows if f in r['flags']]) for f in flags},
        losing_positions=sum(r['net']<0 for r in rows),covered_paths=sum(r['during']['available'] for r in rows),
        quotes=dict(first_utc=datetime.fromtimestamp(quotes.time[0],timezone.utc).isoformat(),
                    last_utc=datetime.fromtimestamp(quotes.time[-1],timezone.utc).isoformat(),count=len(quotes.time)),
        assumed_additional_cost_price=assumed_additional_cost,positions=rows,
        limitations=['No causal blame is assigned: conditions overlap and arise from changed policies.',
            'Pre-entry prices are the latest recorded quotes at/before entry; recorded fill can include slippage.',
            'MFE/MAE are executable-side observed gross extrema, not attainable fills; fees are excluded from extrema.',
            'Post-exit markouts ignore intervening stops and are not realizable alternative profits.',
            'Same-minute repeats do not prove unchanged source evidence; source setup identity is often absent.',
            'Overlapping correlated positions are not independent trials; flag groups overlap.',
            'Missing/stale/discontinuous windows are labelled unassessable; no gap interpolation.'])


def load_capture(root):
    metadata=json.loads((root/'metadata.json').read_text(encoding='utf-8'))
    ticks=pd.read_parquet(root/'ticks.parquet')
    frames={}
    offset=float(metadata.get('broker_offset_seconds',metadata.get('clock_offset',0)))
    for name in ('M1','M5'):
        raw=root/f'{name}.parquet'
        normalized=root/f'{name.lower()}.parquet'
        path=raw if raw.exists() else normalized
        if not path.exists():
            frames[name]=None
            continue
        frame=pd.read_parquet(path)[['time','open','high','low','close']].astype(float)
        # Standard capture tool stores uppercase candle files in broker-clock epochs.
        # Earlier normalized research capture uses lowercase files; do not shift twice.
        if path==raw:
            frame['time']-=offset
        if not np.isfinite(frame.to_numpy()).all() or (frame[['open','high','low','close']]<=0).any().any():
            raise ValueError('Invalid captured candle data')
        if (frame.high<frame[['open','close','low']].max(axis=1)).any() or (frame.low>frame[['open','close','high']].min(axis=1)).any():
            raise ValueError('Invalid captured OHLC ranges')
        if frame.time.duplicated().any():
            raise ValueError('Duplicate candle times')
        frames[name]=frame.sort_values('time')
    return metadata,ticks,frames


def write_outputs(report, root):
    root.mkdir(parents=True,exist_ok=True)
    (root/'report.json').write_text(json.dumps(report,indent=2,allow_nan=False),encoding='utf-8')
    flat=[]
    for row in report['positions']:
        output={k:v for k,v in row.items() if k not in ('pre_entry','during','post_exit_15s','notes','flags')}
        output['flags']=' | '.join(row['flags'])
        for section in ('pre_entry','during','post_exit_15s'):
            output[section]=json.dumps(row[section],sort_keys=True)
        flat.append(output)
    with (root/'positions.csv').open('w',encoding='utf-8',newline='') as handle:
        fields=list(flat[0]) if flat else ['position_id','net','flags']
        writer=csv.DictWriter(handle,fieldnames=fields);writer.writeheader();writer.writerows(flat)
    text=['# Every losing position: observed market evidence','',
          'These are descriptive observations, not proof that a flag caused a loss. Missing windows remain unknown.','']
    for row in report['positions']:
        if row['net']>=0:
            continue
        text.extend([f"## #{row['position_id']} {row['direction']} — net ${row['net']:.2f}",'',
            f"Opened {row['opened_utc']}; closed {row['closed_utc']}; held {row['hold_seconds']:.1f}s.",
            f"Exit: {row['exit_reason']}.",f"Observed flags: {', '.join(row['flags']) or 'None distinctive'}."])
        if row['pre_entry'].get('quote_available'):
            b=row['pre_entry'];text.append(f"Entry spread {b['spread_price']:.4f}; planned stop distance {row['initial_stop_distance']}; estimated cost/stop {b.get('estimated_cost_to_stop')}.")
        for seconds,flow in row['pre_entry']['pressure'].items():
            text.append(f"Before entry ({seconds}s): "+
                (f"signed bid {flow['signed_bid_move_price']:+.4f}, ask {flow['signed_ask_move_price']:+.4f}; efficiency {flow['efficiency']:.3f}." if flow['available'] else flow['reason']+'.'))
        for frame in ('m1','m5'):
            context=row['pre_entry'][frame]
            text.append(f"Completed {frame.upper()} context: "+
                (f"{context['direction']}; signed five-bar change {context['signed_five_bar_move_price']:+.4f}; efficiency {context['efficiency']:.3f}." if context['available'] else context['reason']+'.'))
        text.append(f"Existing same-direction positions at entry: {row['same_direction_positions_already_open']}; prior same-direction entries in that UTC minute: {row['same_minute_prior_direction_entries']}.")
        d=row['during'];text.append((f"Observed executable gross peak ${d['maximum_favorable_gross_usd']:.2f}, trough ${d['maximum_adverse_gross_usd']:.2f}." if d['available'] else 'Trade path: '+d['reason']+'.'))
        text.extend(['No unique cause or successful alternative trade is established.',''])
    (root/'losses.md').write_text('\n'.join(text),encoding='utf-8')


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--audit',type=Path,required=True)
    parser.add_argument('--capture',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--additional-cost-price',type=float,default=.30)
    args=parser.parse_args()
    audit=json.loads(args.audit.read_text(encoding='utf-8'))
    metadata,ticks,frames=load_capture(args.capture)
    if audit.get('account_fingerprint') and metadata.get('account_fingerprint') and audit['account_fingerprint']!=metadata['account_fingerprint']:
        raise ValueError('Audit and quote capture account mismatch')
    report=evaluate(audit,ticks,frames['M1'],frames['M5'],
        contract_size=float(metadata.get('contract_size',100)),assumed_additional_cost=args.additional_cost_price)
    report.update(account_fingerprint=metadata.get('account_fingerprint'),
        identity_verified=bool(audit.get('account_fingerprint') and metadata.get('account_fingerprint')),
        inputs=dict(audit=str(args.audit),capture=str(args.capture)),
        source_hashes={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in
            (args.audit,args.capture/'ticks.parquet',args.capture/'metadata.json')})
    write_outputs(report,args.output)
    print(json.dumps({k:report[k] for k in ('summary','losing_positions','covered_paths','flag_groups')},indent=2))


if __name__=='__main__':
    main()
