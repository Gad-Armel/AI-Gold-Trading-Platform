from datetime import datetime, timezone
from models.market_state import SessionState


SESSION_WINDOWS_UTC = {
    "Asian": (0, 8),
    "London": (7, 16),
    "New York": (13, 22),
}


def _is_hour_in_session(hour: int, start_hour: int, end_hour: int) -> bool:
    """
    Checks if the current UTC hour is inside a session.
    """
    if start_hour < end_hour:
        return start_hour <= hour < end_hour

    return hour >= start_hour or hour < end_hour


def detect_market_session(current_time_utc: datetime | None = None) -> SessionState:
    """
    Detects the active trading session using UTC time.
    """

    if current_time_utc is None:
        current_time_utc = datetime.now(timezone.utc)

    if current_time_utc.tzinfo is None:
        current_time_utc = current_time_utc.replace(tzinfo=timezone.utc)

    current_hour = current_time_utc.hour

    active_sessions = []

    for session_name, hours in SESSION_WINDOWS_UTC.items():
        start_hour, end_hour = hours

        if _is_hour_in_session(current_hour, start_hour, end_hour):
            active_sessions.append(session_name)

    is_asian = "Asian" in active_sessions
    is_london = "London" in active_sessions
    is_new_york = "New York" in active_sessions

    if is_new_york:
        primary_session = "New York"
    elif is_london:
        primary_session = "London"
    elif is_asian:
        primary_session = "Asian"
    else:
        primary_session = "Off Session"

    return SessionState(
        active_sessions=active_sessions,
        primary_session=primary_session,
        is_asian=is_asian,
        is_london=is_london,
        is_new_york=is_new_york,
        utc_time=current_time_utc,
    )