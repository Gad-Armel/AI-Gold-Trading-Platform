"""Explicit demo-only S30 entry gate; never sends orders."""
from datetime import datetime, timezone
import json
import math
import hashlib
import copy
from pathlib import Path
from dataclasses import replace
from config import gold_consensus_settings as settings

from services.research.gold_s30_shadow import s30_observation


def position_exit_signal(decision, *, confirmed_reversal=None):
    signal = copy.deepcopy(decision)
    signal['exit_thesis_source'] = decision.get('entry_mode', 'DIRECTIONAL_POLICY')
    if confirmed_reversal is not None:
        signal['entry_confirmation_only'] = True
        signal['allowed'] = bool(signal.get('allowed') and confirmed_reversal)
    return signal


def confirmed_fast_reversal(decision, held_direction, state, *, now, entry_blocks,
                            market_available, minimum_seconds=1., position_ids=None,
                            quote_time=None, require_fresh_quotes=False):
    """Only an independently confirmed opposite setup can request a reversal exit."""
    direction = decision.get('direction')
    valid = (market_available and decision.get('allowed') and not entry_blocks
             and direction in ('BUY', 'SELL') and held_direction in ('BUY', 'SELL')
             and direction != held_direction and not decision.get('news_block'))
    valid = bool(valid and not isinstance(now, bool) and isinstance(now, (int, float))
                 and math.isfinite(now) and not isinstance(minimum_seconds, bool)
                 and isinstance(minimum_seconds, (int, float)) and math.isfinite(minimum_seconds)
                 and minimum_seconds >= 0)
    binding = None
    if position_ids is not None:
        if (not isinstance(position_ids, (list, tuple, set)) or not position_ids or
                any(isinstance(ticket, bool) or not isinstance(ticket, int) or ticket <= 0
                    for ticket in position_ids)):
            valid = False
        else:
            binding = tuple(sorted(set(position_ids)))
    if require_fresh_quotes and (isinstance(quote_time, bool) or
            not isinstance(quote_time, (int, float)) or not math.isfinite(quote_time) or quote_time <= 0):
        valid = False
    if not valid:
        state.clear()
        return dict(close=False, reason='No confirmed opposite entry setup')
    signature = (held_direction, direction, decision.get('entry_mode'), binding)
    if state.get('signature') != signature:
        state.clear()
        state.update(signature=signature, since=now)
    if now < state['since']:
        state.clear()
        return dict(close=False, reason='Reversal clock moved backwards; confirmation reset')
    if require_fresh_quotes:
        previous_quote = state.get('last_quote_time')
        if previous_quote is not None and quote_time <= previous_quote:
            return dict(close=False, direction=direction,
                        confirmation_age_seconds=max(0., now-state['since']),
                        reason='Waiting for a distinct newer executable quote')
        state['last_quote_time'] = quote_time
        state['quote_observations'] = state.get('quote_observations', 0)+1
    elapsed = max(0., now-state['since'])
    enough_quotes = not require_fresh_quotes or state['quote_observations'] >= 2
    return dict(close=elapsed >= minimum_seconds and enough_quotes, direction=direction,
                confirmation_age_seconds=elapsed,
                distinct_quote_observations=state.get('quote_observations'),
                reason='Confirmed opposite fast entry setup')


def refresh_fast_snapshot(mt5, history, snapshot, *, now=None):
    now = now or datetime.now(timezone.utc)
    try:
        _, health = history.refresh(mt5, snapshot.symbol, now)
        tick = mt5.symbol_info_tick(snapshot.symbol)
        if tick is None:
            raise ValueError('Latest executable quote unavailable')
        bid, ask = float(tick.bid), float(tick.ask)
        if not all(math.isfinite(value) for value in (bid, ask)) or bid <= 0 or ask < bid:
            raise ValueError('Latest executable quote invalid')
        return replace(snapshot, bid=bid, ask=ask, mid=(bid+ask)/2, spread=ask-bid,
                       tick_time_msc=int(tick.time_msc)), health
    except Exception as error:
        return snapshot, dict(available=False, error=f'Fast input refresh failed: {error}')


def directional_signal(ticks, *, now, bid, ask, atr, period_seconds=30, bar_count=3):
    if isinstance(period_seconds, bool) or period_seconds not in (1, 5, 15, 30):
        raise ValueError('Fast entries support S1, S5, S15 and S30')
    observation = s30_observation(ticks, now=now, period_seconds=period_seconds, bar_count=bar_count)
    timeframe = observation['timeframe']
    bars = observation.get('bars', [])
    direction = observation.get('direction', 'WAIT')
    valid = (observation.get('available') and direction in ('BUY', 'SELL') and
             all(isinstance(value, (int, float)) and math.isfinite(value) for value in (bid, ask, atr))
             and bid > 0 and ask >= bid and atr > 0)
    if not valid:
        return dict(bias='WAIT', evidence=0., source_usable=bool(observation.get('available')), levels={},
                    observation=observation, timeframe=timeframe)
    reference = ask if direction == 'BUY' else bid
    buffer = max(ask-bid, .2*atr)
    stop = min(bar['low'] for bar in bars)-buffer if direction == 'BUY' else max(bar['high'] for bar in bars)+buffer
    distance = abs(reference-stop)
    sign = 1 if direction == 'BUY' else -1
    total_range = sum(bar['high']-bar['low'] for bar in bars)
    evidence = 100*sum(abs(bar['close']-bar['open']) for bar in bars)/total_range if total_range else 0.
    levels = dict(sl=stop, entry_zone=[bid, ask], entry_reference=reference, source=f'{timeframe}_STRUCTURE')
    levels.update({f'tp{index}': reference+sign*distance*multiple
                   for index, multiple in enumerate((1.5, 2., 3.), 1)})
    return dict(bias=direction, evidence=evidence, source_usable=True, levels=levels, timeframe=timeframe,
                observation=observation, valid_until=datetime.fromtimestamp(now+3, timezone.utc).isoformat())


def account_fingerprint(account):
    identity = f'{account.login}|{account.server}|{account.trade_mode}'
    return hashlib.sha256(identity.encode()).hexdigest()


def load_costs(path, *, now, allow_provisional=False, account=None):
    report = json.loads(Path(path).read_text(encoding='utf-8'))
    stamp = datetime.fromisoformat(report['as_of'])
    costs = report['costs']
    provisional = report.get('profile_type') == 'PROVISIONAL_DEMO'
    if provisional:
        if (not allow_provisional or account is None or account.trade_mode != 0 or
                account.currency != 'USD' or report.get('account_fingerprint') != account_fingerprint(account)):
            raise ValueError('Provisional costs require explicit opt-in and the matching USD demo account')
    if stamp.tzinfo is None or now-stamp.timestamp() < 0:
        raise ValueError('S30 cost calibration timestamp must be timezone-aware and not future-dated')
    if (report.get('symbol') != 'XAUUSD' or report.get('currency') != 'USD' or
            report.get('volume') != .01 or not report.get('read_only') or
            (not provisional and (costs.get('available') is not True or costs.get('reconciled_pairs', 0) < 30))):
        raise ValueError('S30 requires reconciled XAUUSD USD demo cost evidence')
    for key in ('commission_price', 'slippage_price'):
        value = costs.get(key)
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value < 0:
            raise ValueError('S30 costs must be explicit finite nonnegative price equivalents')
    age = now-stamp.timestamp()
    if age > 86400:
        raise ValueError('S30 cost calibration is older than 24 hours; refresh broker-specific costs before trading')
    return dict(costs, profile_type='PROVISIONAL_DEMO' if provisional else 'MEASURED',
                calibration_age_seconds=age, calibration_stale=False,
                calibration_expiry_enforced=True)


def entry_check(decision, ticks, *, now, plan, cost_path, period_seconds=30,
                allow_provisional=False, account=None):
    timeframe = f'S{period_seconds}'
    if isinstance(period_seconds, bool) or period_seconds not in (1, 5, 15, 30):
        return ['Unsupported fast timeframe'], {}
    try:
        costs = load_costs(cost_path, now=now, allow_provisional=allow_provisional, account=account)
        observation = s30_observation(ticks, now=now, bar_count=plan['required_bars'],
            commission_price=costs['commission_price'], slippage_price=costs['slippage_price'],
            require_micro_confirmation=settings.FAST_MICRO_CONFIRMATION_REQUIRED, period_seconds=period_seconds,
            require_range_cost_screen=settings.FAST_RANGE_COST_FILTER_ENABLED,
            range_cost_multiple=settings.FAST_RANGE_COST_MULTIPLE,
            micro_window_seconds=settings.FAST_MICRO_WINDOW_SECONDS,
            activity_mode=bool(settings.FAST_DEMO_ACTIVITY_MODE and account is not None
                               and getattr(account, 'trade_mode', None) == 0))
    except (OSError, ValueError, KeyError, TypeError) as error:
        return [f'{timeframe} cost/input gate: {error}'], {}
    fast = observation.get('fast_candidate', {})
    blocks = list(fast.get('blocks', []))
    if not observation.get('available'):
        blocks.append(observation.get('reason', f'{timeframe} unavailable'))
    if observation.get('direction') != decision.get('direction'):
        blocks.append(f'{timeframe} confirmation must agree with the {timeframe} entry direction')
    after = plan['after_epoch']
    if after is not None and (after <= 0 or not observation.get('bars') or
                             observation['bars'][-1]['time']+period_seconds <= after):
        blocks.append(f'{timeframe} addition requires a fresh completed candle after the last entry')
    observation.update(entry_timeframe=f'S{period_seconds}', entry_gate_enabled=True, execution_enabled=True,
                       role='DEMO_ENTRY_CONFIRMATION',
                       cost_calibration=dict(age_seconds=costs.get('calibration_age_seconds'),
                                             profile_type=costs.get('profile_type', 'MEASURED'),
                                             commission_price=costs.get('commission_price'),
                                             slippage_price=costs.get('slippage_price'),
                                             stale=costs.get('calibration_stale'),
                                             expiry_enforced=costs.get('calibration_expiry_enforced')),
                       required_bars=plan['required_bars'], blocks=blocks)
    return blocks, observation
