"""Explicit broker clock conversion; never disguise a future quote as fresh."""
from datetime import datetime, timedelta, timezone
from config import gold_consensus_settings as settings


def to_broker_time(utc_time: datetime) -> datetime:
    if utc_time.tzinfo is None:
        raise ValueError('UTC-aware datetime required')
    return utc_time.astimezone(timezone.utc) + timedelta(seconds=settings.MT5_SERVER_UTC_OFFSET_SECONDS)


def broker_epoch_to_utc(seconds: float) -> datetime:
    return datetime.fromtimestamp(seconds-settings.MT5_SERVER_UTC_OFFSET_SECONDS, timezone.utc)


def quote_age(seconds: float) -> float:
    age = (datetime.now(timezone.utc)-broker_epoch_to_utc(seconds)).total_seconds()
    return max(0.0, age) if age >= -settings.MT5_QUOTE_FUTURE_TOLERANCE_SECONDS else float('inf')
