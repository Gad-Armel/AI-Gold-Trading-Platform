"""Quote-only exit pass runs before candle, source and forecast analysis."""
from config import gold_consensus_settings as settings
from services.research.gold_flow_exit import evaluate_flow_exit
from services.research.gold_micro_flow import fast_profit_take


def quote_protection(positions, state, *, horizon, now, quote_time, bid, ask, flow, atr=None, contract_size=100.):
    result=evaluate_flow_exit(positions,state,now=now,quote_time=quote_time,bid=bid,ask=ask,horizon=horizon,atr=atr)
    if result['close'] or not positions or not -settings.MT5_QUOTE_FUTURE_TOLERANCE_SECONDS <= now-quote_time <= settings.ENTRY_MAX_QUOTE_AGE_SECONDS:
        return result
    directions={p['direction'] for p in positions}
    if len(directions)!=1:
        return result
    risk=settings.ADAPTIVE_EXIT_CONFIG[horizon].get('fast_flow_exit_risk')
    if risk is None:
        return result
    exposure=sum(p['volume'] for p in positions)*contract_size
    entry=sum(p['volume']*p['entry_price'] for p in positions)/sum(p['volume'] for p in positions)
    move=bid-entry if positions[0]['direction']=='BUY' else entry-ask
    take,reason=fast_profit_take(flow,move=move,spread=ask-bid,risk_threshold=risk,exposure=exposure)
    return dict(result,close=True,reason=reason) if take else result
