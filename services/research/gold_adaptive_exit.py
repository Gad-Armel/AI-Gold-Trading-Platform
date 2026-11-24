"""Causal, volatility-aware position management; scores are not probabilities."""
from __future__ import annotations
import math
from typing import Any

import pandas as pd
from config import gold_consensus_settings as settings
from services.research.gold_profit_lock import bind_exit_positions, profit_lock_exit

FRAME_SECONDS = {'M1': 60, 'M5': 300, 'M15': 900, 'H1': 3600, 'H4': 14400}
# Fallback only: the live frame comes from each lane's "exit_frame" setting.
FRAMES = {'SCALP': ('M5', 300), 'INTRADAY': ('M15', 900), 'SWING': ('H1', 3600)}


def exit_frame(horizon: str) -> tuple[str, int]:
    """The candle frame a lane manages positions on.

    SCALP runs on M1. An M5 bar only re-evaluates every five minutes, which is
    slower than the trade it is supposed to be managing; a scalper needs a
    substrate it can actually react on, and M1 also lets the post-exit
    re-entry gate clear within a minute instead of five.
    """
    lane = dict(settings.HORIZON_LANES.get(horizon, {}) or {})
    name = str(lane.get('exit_frame') or FRAMES.get(horizon, ('M5', 300))[0]).upper()
    if name not in FRAME_SECONDS:
        name = FRAMES.get(horizon, ('M5', 300))[0]
    return name, FRAME_SECONDS[name]


def market_exit_context(snapshot: Any, horizon: str, *, now_utc: Any = None) -> dict:
    """Use only completed bars and reject stale, malformed or future observations."""
    name, seconds = exit_frame(horizon)
    frame = pd.DataFrame(snapshot.candles.get(name)).copy()
    if len(frame) < 30 or not {'time','open','high','low','close'}.issubset(frame.columns):
        return {'available': False, 'reason': 'Insufficient completed candles'}
    raw_time = frame.time
    stamps = pd.to_datetime(raw_time, unit='s', utc=True) if pd.api.types.is_numeric_dtype(raw_time) else pd.to_datetime(raw_time, utc=True)
    now = (pd.Timestamp(now_utc)+pd.Timedelta(seconds=settings.MT5_SERVER_UTC_OFFSET_SECONDS)
           if now_utc is not None else pd.Timestamp(snapshot.timestamp))
    now = now.tz_localize('UTC') if now.tzinfo is None else now.tz_convert('UTC')
    frame = frame.assign(stamp=stamps).sort_values('stamp').drop_duplicates('stamp')
    frame = frame[frame.stamp + pd.Timedelta(seconds=seconds) <= now]
    if len(frame) < 28 or (now-frame.stamp.iloc[-1]).total_seconds() > seconds*3:
        return {'available': False, 'reason': 'Stale completed candles'}
    values = frame[['open','high','low','close']].apply(pd.to_numeric, errors='coerce')
    if not values.apply(lambda column: column.map(lambda v: math.isfinite(v) and v > 0)).all().all():
        return {'available': False, 'reason': 'Invalid candle prices'}
    if ((values.high < values[['open','close','low']].max(axis=1)) | (values.low > values[['open','close','high']].min(axis=1))).any():
        return {'available': False, 'reason': 'Invalid candle ranges'}
    close = values.close
    tr = pd.concat([values.high-values.low,(values.high-close.shift()).abs(),(values.low-close.shift()).abs()],axis=1).max(axis=1)
    atr = float(tr.ewm(alpha=1/14,adjust=False).mean().iloc[-1])
    if atr <= 0:
        return {'available': False, 'reason': 'Zero volatility'}
    fast = close.ewm(span=12,adjust=False).mean()
    slow = close.ewm(span=26,adjust=False).mean()
    previous_low = float(values.low.iloc[-6:-1].min())
    previous_high = float(values.high.iloc[-6:-1].max())
    # Observable candle patterns, not evidence of institutional orders or alpha.
    bullish_gap = max(0.0, float(values.low.iloc[-1]-values.high.iloc[-3]))
    bearish_gap = max(0.0, float(values.low.iloc[-3]-values.high.iloc[-1]))
    path = float(close.diff().abs().iloc[-20:].sum())
    efficiency = abs(float(close.iloc[-1]-close.iloc[-21]))/path if path > 0 else 0.0
    trend = float((fast.iloc[-1]-slow.iloc[-1])/atr)
    prior_atr = float(tr.ewm(alpha=1/14,adjust=False).mean().iloc[-2])
    expansion = float(tr.iloc[-1])/prior_atr if prior_atr > 0 else 0.0
    regime = ('VOLATILITY_EXPANSION' if expansion >= 2.0 else
              'TREND_UP' if trend > .25 and efficiency >= .30 else
              'TREND_DOWN' if trend < -.25 and efficiency >= .30 else 'RANGE_OR_UNCLEAR')
    return dict(available=True, horizon=horizon,
        bar_id=(frame.stamp.iloc[-1]-pd.Timedelta(seconds=settings.MT5_SERVER_UTC_OFFSET_SECONDS)).isoformat(),
        broker_utc_offset_seconds=settings.MT5_SERVER_UTC_OFFSET_SECONDS, atr=atr,
        close=float(close.iloc[-1]), previous_low=previous_low,
        previous_high=previous_high, trend=trend,
        structure_research=dict(role='RESEARCH_ONLY',version=1,
            bullish_gap_atr=bullish_gap/atr,bearish_gap_atr=bearish_gap/atr,
            downside_sweep=bool(values.low.iloc[-1] < previous_low < close.iloc[-1]),
            upside_sweep=bool(values.high.iloc[-1] > previous_high > close.iloc[-1]),
            directional_efficiency=efficiency,true_range_expansion=expansion,regime=regime),
        momentum=float((close.iloc[-1]-close.iloc[-4])/atr))


def risk_price_distance(risk_usd: float, volume: float, contract_size: float) -> float:
    """Convert a lane's money stop into the price distance that realises it.

    This is the position's risk unit R. Anchoring exits to R instead of to an
    ATR multiple keeps them meaningful as gold repriced from ~$2,000 to
    ~$4,270, and makes it structurally impossible to configure a profit trail
    that arms beyond the risk actually budgeted for the trade.
    """
    exposure = float(volume)*float(contract_size)
    if not math.isfinite(exposure) or exposure <= 0 or not math.isfinite(float(risk_usd)) or float(risk_usd) <= 0:
        return 0.0
    return float(risk_usd)/exposure


def evaluate_adaptive_exit(decision: dict, positions: list[dict], context: dict,
                           state: dict, *, now: float, bid: float, ask: float,
                           feed_age: float, config: dict, risk_usd: float,
                           contract_size: float = 100.0,
                           conscience: dict | None = None,
                           micro_flow: dict | None = None) -> dict:
    """State is lane-local. Broker stops and session loss limits remain independent.

    ``feed_age`` is the age of the broker's last tick, NOT the time since the
    quote last changed: a quiet market still has an executable price, and
    gating protection on quietness disarmed this function during exactly the
    slow adverse drifts it exists to catch.
    """
    from services.research.gold_position_conscience import conviction_collapse, giveback_scale
    from services.research.gold_micro_flow import fast_profit_take

    result = {'close': False, 'reason': 'Position thesis remains valid', 'policy': 'ADAPTIVE_R_V2'}
    if not positions:
        state.clear()
        return result
    if decision.get('news_block') and decision.get('news_policy') == 'CLOSE_AND_BLOCK':
        return {**result, 'close': True, 'reason': 'High-impact news protection'}
    ceiling = float(settings.EXIT_MAX_FEED_AGE_SECONDS)
    if (not context.get('available') or not all(math.isfinite(v) for v in (bid,ask,feed_age))
            or bid <= 0 or ask < bid or feed_age < 0 or feed_age > ceiling):
        if state:
            state['adverse_since'] = None
        return {**result, 'reason': 'Adaptive exit unavailable: stale or invalid market data'}
    bind_exit_positions(positions, state, now=now, bid=bid, ask=ask)
    signature = state['position_signature']
    directions = {p['direction'] for p in positions}
    if len(directions) != 1:
        return {**result, 'close': True, 'reason': 'Mixed lane directions'}
    sign = 1 if positions[0]['direction'] == 'BUY' else -1
    price = bid if sign == 1 else ask
    volume = sum(p['volume'] for p in positions)
    entry = sum(p['entry_price']*p['volume'] for p in positions)/volume
    # ``move`` is measured against the executable exit side, so the entry
    # spread is already deducted: move == 0 is true breakeven, not gross.
    move = sign*(price-entry)
    atr = context['atr']
    spread = max(0.0, ask-bid)
    state['peak_move'] = max(state.get('peak_move',move),move)
    state['trough_move'] = min(state.get('trough_move',move),move)
    risk = risk_price_distance(risk_usd, volume, contract_size)
    # Bind R to the initial observed protective stop, capped by the entry budget.
    # Never move the reference when a stop is subsequently tightened.
    if 'initial_risk_price' not in state:
        distances = [sign*(float(p['entry_price'])-float(p.get('sl', 0))) for p in positions]
        if all(math.isfinite(d) and d > 0 and float(p.get('sl', 0)) > 0 for d,p in zip(distances,positions)):
            actual = sum(d*p['volume'] for d,p in zip(distances, positions))/volume
            risk = min(risk, actual) if risk > 0 else actual
        state['initial_risk_price'] = risk
    risk = state['initial_risk_price']
    conscience = conscience or {}
    scale = giveback_scale(conscience)
    profit_r = move/risk if risk > 0 else 0.0
    peak_r = state['peak_move']/risk if risk > 0 else 0.0
    if risk > 0:
        arm = float(config.get('trail_arm_r',0.40))*risk
        giveback = max(float(config.get('trail_giveback_r',0.35))*risk*scale,
                       float(settings.ADAPTIVE_GIVEBACK_SPREAD_FLOOR)*spread,
                       float(settings.ADAPTIVE_GIVEBACK_ATR_FLOOR)*atr)
        breakeven_arm = float(config.get('breakeven_arm_r',0.60))*risk
    else:
        arm = giveback = breakeven_arm = float('inf')
    weakening = sign*context['momentum'] < 0
    supported = float(conscience.get('conviction', 0.5)) > 0.5 if conscience.get('available') else False
    structural = (context['close'] < context['previous_low'] if sign == 1 else context['close'] > context['previous_high'])
    reversal = bool(decision.get('allowed') and decision.get('direction') in {'BUY','SELL'}
                    and decision['direction'] != positions[0]['direction'])
    neutral_sources = [item for item in decision.get('contributors', [])
                       if item.get('source_usable') and item.get('bias') == 'WAIT']
    entry_mode = decision.get('entry_mode')
    fast_primary = entry_mode in ('S1_PRIMARY', 'S5_PRIMARY', 'S15_PRIMARY', 'S30_PRIMARY')
    primary_name = entry_mode.removesuffix('_PRIMARY')+'_TICKS' if fast_primary else None
    neutral_confirmed = (any(item.get('advisor') == primary_name for item in neutral_sources)
                         if fast_primary else len(neutral_sources) >= 2)
    neutral_thesis_lost = bool(
        (fast_primary or decision.get('continuous_directional_entries'))
        and decision.get('dominant_bias') == 'WAIT'
        and neutral_confirmed
        and not decision.get('entry_confirmation_only')
        and sign*context['momentum'] < 0
        and move < -max(2*spread, .1*atr))
    adverse = reversal or neutral_thesis_lost or (structural and sign*context['trend'] < 0)
    if adverse:
        if state.get('adverse_since') is None: state['adverse_since'] = now
    else:
        state['adverse_since'] = None
    telemetry = {'peak_move':state['peak_move'], 'trough_move':state['trough_move'], 'atr':atr,
                 'risk_price':risk, 'profit_r':profit_r, 'peak_r':peak_r,
                 'giveback_distance':giveback, 'giveback_scale':scale,
                 'trail_armed':bool(state['peak_move'] >= arm),
                 'breakeven_armed':bool(state.get('breakeven_armed'))}
    if adverse and now-state['adverse_since'] >= float(config.get('exit_confirmation_seconds',15)):
        return {**result, **telemetry, 'close': True,
                'reason': ('Confirmed neutral directional thesis with opposing momentum; cutting unsupported loss'
                           if neutral_thesis_lost else 'Confirmed market thesis invalidation')}
    # A trade that has paid for itself may not be handed back. The exit-side
    # spread is already inside ``move``; this buffer covers slippage beyond it.
    if state['peak_move'] >= breakeven_arm:
        state['breakeven_armed'] = True
        telemetry['breakeven_armed'] = True
    buffer = max(0.0, (float(settings.ADAPTIVE_ROUND_TRIP_COST_SPREADS)-1.0)*spread)
    if state.get('breakeven_armed') and move <= buffer:
        return {**result, **telemetry, 'close': True,
                'reason': 'Protected winner returned to breakeven; banking it rather than risking the stop'}
    # Take the money the moment flow turns, at any size of gain that clears the
    # round trip -- without waiting for the giveback trail or for the slower
    # confirmed-reversal closer. Below the cost floor this does not fire as a
    # profit take: a gain smaller than the round trip is a loss in green ink.
    fast_risk = config.get('fast_flow_exit_risk')
    if fast_risk is not None and micro_flow and micro_flow.get('available'):
        observed = micro_flow.get('reversal_risk')
        floor = max(float(settings.SCALP_MIN_PROFIT_TAKE_SPREADS)*spread,
                    float(settings.SCALP_MIN_PROFIT_TAKE_USD)/(volume*contract_size))
        telemetry['flow_reversal_risk'] = observed
        telemetry['profit_take_floor'] = floor
        take, take_reason = fast_profit_take(micro_flow, move=move, spread=spread,
                                            risk_threshold=fast_risk, exposure=volume*contract_size)
        if take:
            return {**result, **telemetry, 'close': True, 'reason': take_reason}
    # Give back the configured share of R -- unless every source still supports
    # the trade and momentum has not turned, in which case let the winner run.
    if state['peak_move'] >= arm and state['peak_move']-move >= giveback and (weakening or not supported):
        return {**result, **telemetry, 'close': True,
                'close_tickets': [int(p['ticket']) for p in positions],
                'reason': f'Profit giveback of {giveback:.2f} from peak with support fading'}
    if state['peak_move'] >= breakeven_arm:
        lock = profit_lock_exit(positions, state, now=now, bid=bid, ask=ask,
                                feed_age=feed_age, config=config, contract_size=contract_size)
        if lock['close']:
            return {**result, **telemetry, **lock}
    collapsed, collapse_reason = conviction_collapse(
        conscience, state.setdefault('conscience_state', {}), now=now, profit_r=profit_r,
        horizon=str(context.get('horizon') or decision.get('horizon') or ''),
        position_signature=tuple(map(tuple, signature)))
    if collapsed:
        return {**result, **telemetry, 'close': True, 'reason': collapse_reason}
    if now-state['started'] >= float(config.get('stagnation_seconds',7200)) and move < 0.25*atr and sign*context['trend'] <= 0:
        return {**result, **telemetry, 'close': True, 'reason': 'Stagnant position without trend support'}
    return {**result, **telemetry}
