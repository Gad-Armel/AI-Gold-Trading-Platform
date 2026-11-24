"""DST-aware gold liquidity context; not an authoritative CFD trading calendar."""
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


def market_schedule(now=None):
    now = datetime.now(timezone.utc) if now is None else now
    if now.tzinfo is None:
        raise ValueError('Timezone-aware observation required')
    try:
        local = {name: now.astimezone(ZoneInfo(zone)) for name, zone in (
            ('London', 'Europe/London'), ('New_York', 'America/New_York'), ('Shanghai', 'Asia/Shanghai'))}
    except ZoneInfoNotFoundError:
        return dict(available=False, reason='Timezone database unavailable; no fixed UTC substitution')
    windows = dict(London=(8, 17), New_York=(8, 17))
    active = [name for name, stamp in local.items() if name in windows
              if stamp.weekday() < 5 and windows[name][0] <= stamp.hour < windows[name][1]]
    shanghai = local['Shanghai']
    shanghai_minutes = shanghai.hour*60+shanghai.minute
    sge_day = shanghai.weekday() < 5 and 9*60 <= shanghai_minutes < 15*60+30
    sge_night = ((shanghai.weekday() < 5 and shanghai_minutes >= 20*60)
                 or (1 <= shanghai.weekday() <= 5 and shanghai_minutes < 2*60+30))
    if sge_day or sge_night:
        active.append('Shanghai')
    london, new_york = local['London'], local['New_York']
    auctions = []
    for days in range(8):
        day = london+timedelta(days=days)
        if day.weekday() >= 5:
            continue
        for hour, minute in ((10, 30), (15, 0)):
            stamp = day.replace(hour=hour, minute=minute, second=0, microsecond=0)
            if stamp >= london:
                auctions.append(stamp.astimezone(timezone.utc))
    next_auction = min(auctions)
    ny_minutes = new_york.hour*60+new_york.minute
    rollover_watch = new_york.weekday() < 5 and 16*60+55 <= ny_minutes < 18*60+5
    return dict(available=True, observed_at=now.astimezone(timezone.utc).isoformat(),
        active_centres=active, london_new_york_overlap='London' in active and 'New_York' in active,
        local_times={name: stamp.isoformat() for name, stamp in local.items()},
        sge_regular_session='DAY' if sge_day else 'NIGHT' if sge_night else 'BREAK',
        next_regular_lbma_auction_utc=next_auction.isoformat(),
        minutes_to_regular_auction=round((next_auction-now).total_seconds()/60, 1),
        rollover_watch=rollover_watch, authoritative_broker_hours=False,
        holiday_calendar_verified=False, execution_authority=False,
        note='Centre windows are liquidity heuristics, not exchange opening hours. Auctions exclude holidays only when separately verified; broker permissions and fresh quotes govern entries.')


def broker_entry_permission(info, direction):
    if info is None:
        return dict(success=False, action='SYMBOL_SESSION_BLOCK', message='Broker symbol metadata unavailable.')
    mode = getattr(info, 'trade_mode', None)
    if mode is None:
        return None
    if mode == 4 or (mode == 1 and direction == 'BUY') or (mode == 2 and direction == 'SELL'):
        return None
    return dict(success=False, action='SYMBOL_SESSION_BLOCK',
                message=f'Broker symbol trade mode {mode} does not permit a new {direction} position.')


def execution_plan(decision):
    setup = decision.get('setup_observation', {})
    regime = setup.get('regime', 'UNKNOWN')
    preferred = ('pullback', 'breakout') if regime in ('TREND_UP', 'TREND_DOWN') else (
        ('sweep',) if regime == 'RANGE_OR_TRANSITION' else ())
    return dict(live_strategy='EXECUTABLE_QUOTE_CONTINUATION',
        frequency_policy='FASTEST_COST_AND_RISK_FEASIBLE_NOT_TARGET_TRADE_COUNT',
        market_regime=regime,
        research_candidates=[dict(setup=name, direction=setup.get('candidates', {}).get(name, 'WAIT'),
                                  execution_enabled=False) for name in preferred],
        news_policy='EXISTING_VERIFIED_CALENDAR_FILTERS_UNCHANGED',
        session_policy='CONTEXT_ONLY_BROKER_PERMISSION_AND_QUOTES_AUTHORITATIVE',
        calibrated_probability=None)
