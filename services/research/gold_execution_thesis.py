"""Causal executable-quote trigger. No fitted model or calibrated probability."""
import math
from statistics import median


def execution_thesis(ticks, *, now, direction, atr, commission, slippage):
    result = dict(available=False, allowed=False, direction=direction, policy='EXECUTABLE_EVENT_V1',
                  setup_id=None, blocks=[], calibrated_probability=None)
    if direction not in ('BUY', 'SELL'):
        return dict(result, blocks=['A strong directional context is required.'])
    values = (now, atr, commission, slippage)
    if not all(not isinstance(v, bool) and isinstance(v, (int,float)) and math.isfinite(v) for v in values) or atr <= 0 or min(commission,slippage) < 0:
        return dict(result, blocks=['Explicit finite volatility and execution costs required.'])
    if hasattr(ticks, 'to_dict'):
        ticks = ticks[(ticks.timestamp >= now-40) & (ticks.timestamp <= now)].to_dict('records')
    rows = []
    try:
        for row in ticks:
            t,b,a = (float(row[k]) for k in ('timestamp','bid','ask'))
            if not all(math.isfinite(v) for v in (t,b,a)) or b <= 0 or a < b:
                return dict(result, blocks=['Invalid executable tick.'])
            if now-40 <= t <= now:
                rows.append((t,b,a))
    except (TypeError,ValueError,KeyError):
        return dict(result, blocks=['Malformed tick history.'])
    rows = sorted(set(rows))
    if not rows or now-rows[-1][0] > 2:
        return dict(result, blocks=['Fresh executable tick required.'])
    end = math.floor(now/5)*5
    bars = []
    for start in range(end-30,end,5):
        group = [r for r in rows if start <= r[0] < start+5]
        edges = [start]+[r[0] for r in group]+[start+5]
        if len(group) < 2 or max(b-a for a,b in zip(edges,edges[1:])) > 2.5:
            return dict(result, blocks=['Continuous completed S5 structure is required.'])
        mids = [(r[1]+r[2])/2 for r in group]
        bars.append(dict(time=start, open=mids[0], close=mids[-1], high=max(mids), low=min(mids)))
    recent = [r for r in rows if r[0] >= now-3]
    longer = [r for r in rows if r[0] >= now-12]
    edges = [now-12]+[r[0] for r in longer]+[now]
    if len(recent)<4 or len(longer)<8 or max(b-a for a,b in zip(edges,edges[1:]))>2.5:
        return dict(result, blocks=['Continuous short-horizon quote pressure required.'])
    sign = 1 if direction=='BUY' else -1
    bid,ask = rows[-1][1:]
    spread = ask-bid
    cost = spread+commission+slippage
    mids = [(r[1]+r[2])/2 for r in recent]
    net = sign*(mids[-1]-mids[0])
    path = sum(abs(b-a) for a,b in zip(mids,mids[1:]))
    efficiency = abs(mids[-1]-mids[0])/path if path else 0.
    bid_move,ask_move = (sign*(recent[-1][i]-recent[0][i]) for i in (1,2))
    long_move = sign*((longer[-1][1]+longer[-1][2]-longer[0][1]-longer[0][2])/2)
    all_mids = [(r[1]+r[2])/2 for r in rows if r[0]>=end-30]
    opportunity = max(all_mids)-min(all_mids)
    typical_spread = median(r[2]-r[1] for r in longer)
    last,prev = bars[-1],bars[-2]
    body = sign*(last['close']-last['open'])
    breakout = last['close']>prev['high'] if sign==1 else last['close']<prev['low']
    reclaim = sign*(prev['close']-prev['open'])<0 and sign*(last['close']-prev['open'])>0
    setup = 'S5_PULLBACK_RECLAIM' if reclaim else 'S5_CONTINUATION_BREAK'
    blocks = []
    if body<=0 or not (breakout or reclaim):
        blocks.append('Wait for a fresh S5 break or pullback reclaim.')
    if min(bid_move,ask_move)<=0 or net<=.25*spread or efficiency<.45 or long_move<=0:
        blocks.append('Executable pressure does not confirm the context direction.')
    if opportunity<1.5*cost:
        blocks.append('Recent observable movement is too small relative to dealing costs.')
    if spread>1.5*max(typical_spread,1e-9):
        blocks.append('Current spread is expanding.')
    if sign*((bid+ask)/2-last['close']) > max(last['high']-last['low'],spread):
        blocks.append('Entry is extended beyond the completed setup.')
    reference=ask if sign==1 else bid
    pivot=min(last['low'],prev['low']) if sign==1 else max(last['high'],prev['high'])
    stop=pivot-sign*max(.25*spread,.1*atr)
    risk=sign*(reference-stop)
    if not 0<risk<=5:
        blocks.append('Structural stop exceeds the current trade-risk budget.')
    target=reference+sign*max(2*risk,2*cost)
    return dict(result, available=True, allowed=not blocks, blocks=blocks,
        setup=setup, setup_id=f'{setup}:{prev["time"]}:{last["time"]}:{direction}',
        feature_epoch=end, valid_until_epoch=end+5, quote_efficiency=efficiency,
        bid_move=bid_move,ask_move=ask_move,net_move=net,context_move=long_move,
        observed_range=opportunity, estimated_cost=cost,spread=spread, risk_price=risk,
        levels=dict(sl=stop, tp1=target, tp2=reference+sign*3*risk,tp3=reference+sign*4*risk,
                    entry_reference=reference,entry_zone=[bid,ask],source='EXECUTABLE_EVENT_STRUCTURE'))
