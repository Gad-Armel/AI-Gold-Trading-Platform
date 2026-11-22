"""Experimental learned filter and continuation forecast; never a risk override."""
from pathlib import Path
import math
import numpy as np
import pandas as pd

FRAMES = {'SCALP': ('M5', 300), 'INTRADAY': ('M15', 900), 'SWING': ('H1', 3600)}
FEATURES = ['trend', 'momentum', 'distance', 'atr', 'range_atr',
            'volatility_ratio', 'efficiency', 'gap_up', 'gap_down']
VERSION = 1


def feature_frame(frame):
    """Finite trailing windows: identical training/live inputs, no future bars."""
    p = frame[['open', 'high', 'low', 'close']].astype(float)
    c = p.close
    tr = pd.concat([p.high-p.low, (p.high-c.shift()).abs(),
                    (p.low-c.shift()).abs()], axis=1).max(axis=1)
    atr = tr.rolling(14).mean().replace(0, np.nan)
    fast, slow = c.rolling(12).mean(), c.rolling(26).mean()
    out = pd.DataFrame(index=frame.index)
    out['trend'] = (fast-slow)/atr
    out['momentum'] = c.diff(3)/atr
    out['distance'] = (c-fast)/atr
    out['atr'] = atr
    out['range_atr'] = (p.high-p.low)/atr
    out['volatility_ratio'] = atr/tr.rolling(60).mean().replace(0, np.nan)
    out['efficiency'] = c.diff(20).abs()/c.diff().abs().rolling(20).sum().replace(0, np.nan)
    out['gap_up'] = (p.low-p.high.shift(2)).clip(lower=0)/atr
    out['gap_down'] = (p.low.shift(2)-p.high).clip(lower=0)/atr
    return out[FEATURES].replace([np.inf, -np.inf], np.nan)


class GoldLearnedPolicy:
    def __init__(self, root='data/research/gold_ai'):
        # Only locally trained artifacts should be loaded: joblib is executable pickle.
        import joblib
        self.models = {}
        self.cache = {}
        for lane, (frame, _) in FRAMES.items():
            path = Path(root)/f'{frame}.joblib'
            if not path.exists():
                raise ValueError(f'Missing {path}; run python tools/train_gold_ai.py first')
            artifact = joblib.load(path)
            if (artifact.get('version') != VERSION or artifact.get('features') != FEATURES
                    or artifact.get('frame') != frame or artifact.get('symbol') != 'XAUUSD'
                    or artifact.get('lot_size') != .01 or artifact.get('contract_size') != 100):
                raise ValueError(f'Incompatible learned artifact: {path}')
            self.models[lane] = artifact

    def assess(self, snapshot, lane, context):
        if not context.get('available'):
            return dict(available=False, reason='Completed candle context unavailable')
        name, seconds = FRAMES[lane]
        frame = pd.DataFrame(snapshot.candles.get(name)).copy()
        if 'time' not in frame:
            return dict(available=False, reason='Candle timestamps unavailable')
        times = pd.to_datetime(frame.time, unit='s', utc=True) if pd.api.types.is_numeric_dtype(frame.time) else pd.to_datetime(frame.time, utc=True)
        now = pd.Timestamp(snapshot.timestamp)
        now = now.tz_localize('UTC') if now.tzinfo is None else now.tz_convert('UTC')
        frame = frame.assign(stamp=times).sort_values('stamp').drop_duplicates('stamp')
        frame = frame[frame.stamp+pd.Timedelta(seconds=seconds) <= now]
        if len(frame) < 61:
            return dict(available=False, reason='Learned policy needs 61 completed candles')
        artifact = self.models[lane]
        if (frame.stamp.iloc[-1].timestamp() <= artifact['training_last_bar']
                or (now-frame.stamp.iloc[-1]).total_seconds() > seconds*3):
            return dict(available=False, reason='Stale candles or observations overlap model training')
        x = feature_frame(frame.tail(80)).iloc[[-1]]
        if not np.isfinite(x.to_numpy()).all():
            return dict(available=False, reason='Invalid learned features')
        # Cache only candle forecasts, never the changing executable quote/cost.
        from config import gold_consensus_settings as settings
        forecast_bar = (frame.stamp.iloc[-1]-pd.Timedelta(seconds=settings.MT5_SERVER_UTC_OFFSET_SECONDS)).isoformat()
        key = (forecast_bar, tuple(x.iloc[0]))
        if self.cache.get(lane, {}).get('key') != key:
            prediction = float(artifact['model'].predict(x)[0])
            self.cache[lane] = dict(key=key, prediction=prediction)
        prediction = self.cache[lane]['prediction']
        bid, ask = float(snapshot.bid), float(snapshot.ask)
        if not all(math.isfinite(v) for v in (prediction, bid, ask)) or bid <= 0 or ask < bid:
            return dict(available=False, reason='Invalid forecast or executable quote')
        # Forecast is future bid close minus last completed bid close. Re-anchor
        # at today's executable price so an already-realized move is not alpha.
        future_bid = float(frame.close.iloc[-1])+prediction
        cost = float(artifact['round_trip_slippage_usd'])
        edge = {'BUY': future_bid-ask-cost, 'SELL': bid-future_bid-(ask-bid)-cost}
        return dict(available=True, role='EXPERIMENTAL', model_id=artifact['model_id'],
                    bar_id=forecast_bar, forecast_bars=artifact['forecast_bars'],
                    edge_usd=edge, continuation_usd={'BUY': future_bid-bid,
                    'SELL': bid-future_bid}, minimum_edge_usd=artifact['minimum_edge_usd'],
                    validation=artifact['validation'], live_approved=False)


def apply_entry_filter(decision, assessment):
    """May veto a consensus entry. Cannot create permission or change sizing."""
    decision['learned_policy'] = assessment
    direction = decision.get('direction')
    if not assessment.get('available'):
        decision['allowed'] = False
        decision.setdefault('blocks', []).append('Learned filter unavailable: '+assessment.get('reason', 'unknown'))
    elif direction in ('BUY', 'SELL') and assessment['edge_usd'][direction] < assessment['minimum_edge_usd']:
        decision['allowed'] = False
        decision.setdefault('blocks', []).append('Learned expected return does not cover costs and entry margin.')


def learned_exit(assessment, positions, state, feed_age):
    """Two distinct completed adverse forecasts; never counts repeated ticks.

    ``feed_age`` is broker tick age, so a quiet market does not disarm the
    check; only a stale or future-dated feed does.
    """
    from config import gold_consensus_settings as settings
    if (not positions or not assessment.get('available') or not math.isfinite(feed_age)
            or not 0 <= feed_age <= float(settings.EXIT_MAX_FEED_AGE_SECONDS)):
        state.clear()
        return False
    signature = tuple(sorted(p['ticket'] for p in positions))
    direction = positions[0]['direction']
    if state.get('signature') != signature:
        state.clear()
        state.update(signature=signature, count=0)
    if state.get('bar') != assessment['bar_id']:
        adverse = assessment['continuation_usd'][direction] < -max(.20, assessment['minimum_edge_usd'])
        state['count'] = state['count']+1 if adverse else 0
        state['bar'] = assessment['bar_id']
    return state['count'] >= 2
