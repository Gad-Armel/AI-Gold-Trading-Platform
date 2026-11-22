"""Main-bot data health and advisor isolation. Does not modify Advisor 1."""
import math
from datetime import datetime, timezone
from config import gold_consensus_settings as settings


def market_health(snapshot, terminal, *, now):
    stamp = float(snapshot.tick_time_msc)/1000-settings.MT5_SERVER_UTC_OFFSET_SECONDS
    age = now-stamp
    bid,ask = float(snapshot.bid),float(snapshot.ask)
    connected = terminal is not None and bool(getattr(terminal,'connected',False))
    reasons=[]
    if not connected:
        reasons.append('MT5 terminal is disconnected or connection status unavailable.')
    if not all(math.isfinite(v) for v in (stamp,age,bid,ask)) or bid <= 0 or ask < bid:
        reasons.append('MT5 quote is malformed.')
    elif age < -settings.MT5_QUOTE_FUTURE_TOLERANCE_SECONDS:
        reasons.append('MT5 quote is future-dated under the configured broker UTC offset.')
    elif age > settings.ENTRY_MAX_QUOTE_AGE_SECONDS:
        reasons.append(f'No fresh XAUUSD quote: last broker tick is {age:.1f}s old. Check feed connection and symbol session.')
    return dict(available=not reasons,terminal_connected=connected,
                quote_age_seconds=round(age,3) if math.isfinite(age) else None,
                entry_blocks=reasons,reason=reasons[0] if reasons else 'Fresh executable quote',
                observed_at=datetime.fromtimestamp(now,timezone.utc).isoformat())


def isolated_advisor(name, build, errors):
    """An advisor failure cannot shut down quote protection or invent a signal."""
    try:
        report=build()
        if not isinstance(report,dict):
            raise TypeError('Advisor did not return a report')
        errors.pop(name,None)
        return report
    except Exception as exc:
        errors[name]=f'{type(exc).__name__}: {exc}'
        return dict(available=False,error=errors[name],generated_at=datetime.now(timezone.utc).isoformat(),horizons={})
