"""Main-only cache of Advisor 1's candle signal; Advisor 1 is unchanged.

Only bias, strength and ATR depend on completed candles. Execution prices,
levels and timestamps are rebuilt each loop. Quote-dependent advisory ACTION
is intentionally not cached or used as an entry authority.
"""
from datetime import datetime, timedelta, timezone
import pandas as pd
import numpy as np
from services.research.gold_advisory import HORIZONS, _closed, _levels, build_gold_advisory
from services.research.gold_scalp_setups import latest_observation
from config import gold_consensus_settings as settings


def signature_frame(snapshot, name):
    """Avoid renormalizing already valid, ordered numeric broker candles.

    Unusual inputs still use Advisor 1's canonical cleanup. This only prepares
    cache fingerprints; the actual signal calculation is unchanged.
    """
    raw=snapshot.candles.get(name) if isinstance(snapshot.candles,dict) else None
    columns=('open','high','low','close')
    if isinstance(raw,pd.DataFrame) and not raw.empty and {'time',*columns}.issubset(raw.columns):
        try:
            if (all(pd.api.types.is_numeric_dtype(raw[key]) for key in columns)
                    and raw.time.notna().all() and raw.time.is_unique
                    and raw.time.is_monotonic_increasing
                    and np.isfinite(raw[list(columns)].to_numpy(copy=False)).all()):
                return raw.iloc[:-1]
        except (TypeError,ValueError):
            pass
    return _closed(snapshot,name)


class MainCandleSignal:
    def __init__(self):
        self.signature = None
        self.report = None
        self.hits = 0
        self.misses = 0
        self.setup = {}

    def build(self, snapshot):
        now = snapshot.system_timestamp or datetime.now(timezone.utc)
        if now.tzinfo is None:
            now = now.replace(tzinfo=timezone.utc)
        signature = []
        for name in ('M1', 'M5', 'M15', 'H1', 'H4'):
            closed = signature_frame(snapshot, name)
            fingerprint = (pd.util.hash_pandas_object(
                closed[['time', 'open', 'high', 'low', 'close']], index=False).values.tobytes()
                if not closed.empty else b'')
            signature.append((name, len(closed), fingerprint))
        signature = tuple(signature)
        if signature != self.signature:
            report = build_gold_advisory(snapshot)
            self.report = report
            self.setup = latest_observation(snapshot.candles.get('M1'), snapshot.candles.get('M5'),
                broker_offset_seconds=settings.MT5_SERVER_UTC_OFFSET_SECONDS, now=now.timestamp())
            self.signature = signature
            self.misses += 1
        else:
            self.hits += 1
        setup = dict(self.setup)
        if setup.get('available') and now.timestamp()-setup['feature_epoch'] >= 120:
            setup.update(available=False, reason='Cached completed setup candles are stale')
        horizons = {}
        for name, config in HORIZONS.items():
            item = dict(self.report['horizons'][name])
            direction = item['bias']
            atr = float(self.report['views'][config['anchor']].get('atr', 0))
            item['levels'] = (_levels(snapshot, direction, atr, config)
                              if direction in ('BUY', 'SELL') and atr > 0 else {})
            item['review_at'] = (now+timedelta(minutes=max(1, int(config['minutes']/3)))).isoformat()
            item['valid_until'] = (now+timedelta(minutes=config['minutes'])).isoformat()
            item['action'] = 'WAIT'
            item['blocks'] = []
            horizons[name] = item
        return dict(generated_at=now.isoformat(), symbol=snapshot.symbol,
                    bid=snapshot.bid, ask=snapshot.ask, spread=round(snapshot.spread, 6),
                    session=snapshot.session, horizons=horizons, signal_only=True,
                    cache_hits=self.hits, cache_misses=self.misses,
                    execution_enabled=False, orders_sent=False, setup_observation=setup)
