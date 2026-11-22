"""Observed currency transmission, not a dollar index or validated prediction."""
import math
import time
from copy import deepcopy
import numpy as np
import pandas as pd
from config import gold_consensus_settings as settings
from services.market_data.gold_broker_clock import quote_age

PAIRS = {'EURUSD': ('EUR', 'USD'), 'USDJPY': ('USD', 'JPY')}


def aligned_returns(frames):
    series = []
    for name in ('XAUUSD', *PAIRS):
        frame = pd.DataFrame(frames[name]).copy()
        stamps = pd.to_datetime(frame.time, unit='s', utc=True) if pd.api.types.is_numeric_dtype(frame.time) else pd.to_datetime(frame.time, utc=True)
        values = pd.Series(pd.to_numeric(frame.close, errors='coerce').to_numpy(), index=stamps)
        values = values[~values.index.duplicated(keep='last')].sort_index()
        returns = np.log(values.where(values > 0)).diff()
        # Neither a weekend gap nor a missing candle is a five-minute return.
        returns[values.index.to_series().diff() != pd.Timedelta(minutes=5)] = np.nan
        series.append(returns.rename(name))
    return pd.concat(series, axis=1).replace([np.inf, -np.inf], np.nan).dropna()


def transmission(frames):
    returns = aligned_returns(frames)
    if len(returns) < 100:
        return dict(available=False, reason='Insufficient aligned completed currency and gold history')
    for frame in frames.values():
        raw = pd.DataFrame(frame).time
        last = pd.to_datetime(raw, unit='s', utc=True).max() if pd.api.types.is_numeric_dtype(raw) else pd.to_datetime(raw, utc=True).max()
        if returns.index[-1] != last:
            return dict(available=False, reason='Latest completed cross-market candle cannot be aligned')
    recent = returns.tail(99)
    if (recent.index.to_series().diff().iloc[-2:] != pd.Timedelta(minutes=5)).any():
        return dict(available=False, reason='Recent cross-market candle gap')
    past = recent.iloc[:-3]
    sigma = past.std()
    if not np.isfinite(sigma).all() or (sigma <= 0).any():
        return dict(available=False, reason='Invalid cross-market volatility')
    z = recent.iloc[-3:].sum()/(sigma*np.sqrt(3))
    dollar = (-past.EURUSD/sigma.EURUSD + past.USDJPY/sigma.USDJPY)/2
    corr = float(past.XAUUSD.corr(dollar))
    pressure = float((-z.EURUSD+z.USDJPY)/2)
    agreement = (-z.EURUSD > .5 and z.USDJPY > .5) or (-z.EURUSD < -.5 and z.USDJPY < -.5)
    if not math.isfinite(corr):
        return dict(available=False, reason='Undefined dollar/gold relationship')
    directional = bool(agreement and abs(pressure) >= 1 and corr <= -.15)
    return dict(available=True, role='EXPERIMENTAL_TRANSMISSION_CONTEXT',
        independent_source_families=1, is_dollar_index=False,
        bar_id=recent.index[-1].isoformat(), dollar_pressure_z=pressure,
        gold_move_z=float(z.XAUUSD), prior_gold_dollar_correlation=corr,
        currency_agreement=bool(agreement),
        gold_bias=('SELL' if pressure > 0 else 'BUY') if directional else 'NEUTRAL',
        reason='Observed dollar pressure with local gold relationship' if directional else 'Dollar relationship is weak or conflicting')


class CrossMarketCollector:
    def __init__(self):
        self.frames = {}
        self.last_fetch = -float('inf')
        self.signature = None
        self.cached_transmission = None
        self.cache_hits = self.cache_misses = 0

    def assess(self, mt5, snapshot):
        try:
            for name, (base, quote) in PAIRS.items():
                info, tick = mt5.symbol_info(name), mt5.symbol_info_tick(name)
                if (info is None or info.currency_base != base or info.currency_profit != quote
                        or tick is None or quote_age(float(tick.time_msc)/1000) > 5
                        or not all(math.isfinite(float(v)) for v in (tick.bid, tick.ask))
                        or tick.bid <= 0 or tick.ask < tick.bid):
                    return dict(available=False, reason=f'{name} missing, stale or wrong instrument identity')
            if time.monotonic()-self.last_fetch >= 15:
                collected = {}
                for name in PAIRS:
                    rates = mt5.copy_rates_from_pos(name, mt5.TIMEFRAME_M5, 0, 160)
                    if rates is None:
                        return dict(available=False, reason=f'{name} history unavailable')
                    collected[name] = pd.DataFrame(rates)
                self.frames, self.last_fetch = collected, time.monotonic()
            frames = dict(self.frames, XAUUSD=pd.DataFrame(snapshot.candles['M5']))
            now = pd.Timestamp(snapshot.timestamp)
            now = now.tz_localize('UTC') if now.tzinfo is None else now.tz_convert('UTC')
            for name, frame in frames.items():
                stamps = pd.to_datetime(frame.time, unit='s', utc=True) if pd.api.types.is_numeric_dtype(frame.time) else pd.to_datetime(frame.time, utc=True)
                frames[name] = frame[stamps+pd.Timedelta(minutes=5) <= now]
            # Transmission depends only on completed close/time observations.
            # Quote identity/freshness above and bar-age checks below still run
            # every call. Hash all relevant history so broker revisions and new
            # completions cannot reuse an obsolete directional result.
            signature = tuple((name, len(frame), pd.util.hash_pandas_object(
                frame[['time', 'close']], index=False).values.tobytes())
                for name, frame in sorted(frames.items()))
            if signature == self.signature:
                result = deepcopy(self.cached_transmission)
                self.cache_hits += 1
            else:
                result = transmission(frames)
                self.signature, self.cached_transmission = signature, deepcopy(result)
                self.cache_misses += 1
            if result.get('available'):
                age = (now-pd.Timestamp(result['bar_id'])).total_seconds()
                if not 300 <= age <= 660:
                    return dict(available=False, reason='Aligned completed candles are stale')
                result['bar_id'] = (pd.Timestamp(result['bar_id'])-pd.Timedelta(seconds=settings.MT5_SERVER_UTC_OFFSET_SECONDS)).isoformat()
            return result
        except (ValueError, TypeError, KeyError, AttributeError):
            return dict(available=False, reason='Cross-market data validation failed')


def protective_exit(context, positions, gold_context, state, age):
    """Experimental: require dollar contradiction AND actual gold deterioration.

    ``age`` is broker tick age. A quiet quote is not a broken feed, so the
    ceiling is the exit-side allowance rather than the tight entry one.
    """
    if (not positions or not context.get('available') or not gold_context.get('available')
            or not math.isfinite(age) or not 0 <= age <= float(settings.EXIT_MAX_FEED_AGE_SECONDS)):
        state.clear()
        return False
    signature = tuple(sorted((p['ticket'], p['direction']) for p in positions))
    if state.get('signature') != signature:
        state.clear()
        state.update(signature=signature, count=0)
    direction = positions[0]['direction']
    sign = 1 if direction == 'BUY' else -1
    if state.get('bar') != context['bar_id']:
        adverse = (context['gold_bias'] in ('BUY', 'SELL') and context['gold_bias'] != direction
                   and sign*context['gold_move_z'] < -.5 and sign*gold_context['momentum'] < 0)
        state['count'] = state['count']+1 if adverse else 0
        state['bar'] = context['bar_id']
    return state['count'] >= 2
