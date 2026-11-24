import json
import os
import re
import urllib.parse
import urllib.request

from datetime import datetime, timedelta, timezone
from html import unescape
from typing import Any

try:
    from zoneinfo import ZoneInfo
except Exception:
    ZoneInfo = None

from config import settings

from services.risk.economic_event_manager import (
    load_events,
    save_events,
)


AUTO_SOURCE_FMP = "AUTO_FMP"
AUTO_SOURCE_FREE = "AUTO_FREE_FALLBACK"

DATETIME_FORMAT = "%Y-%m-%d %H:%M:%S"


# Official Federal Reserve FOMC decision dates.  The decision is normally
# released at 2:00 p.m. U.S. Eastern on the second meeting day.  These dates
# are sourced from the Federal Reserve meeting calendar and are deliberately
# explicit so an unavailable webpage can never degrade into "every Wednesday".
OFFICIAL_FOMC_DECISION_DATES = {
    2025: [(1, 29), (3, 19), (5, 7), (6, 18), (7, 30), (9, 17), (10, 29), (12, 10)],
    2026: [(1, 28), (3, 18), (4, 29), (6, 17), (7, 29), (9, 16), (10, 28), (12, 9)],
    2027: [(1, 27), (3, 17), (4, 28), (6, 9), (7, 28), (9, 15), (10, 27), (12, 8)],
}


# ======================================================================
# BASIC HELPERS
# ======================================================================

def _safe_int(
    value: Any,
    default: int,
    minimum: int | None = None,
) -> int:
    try:
        result = int(value)
    except (TypeError, ValueError):
        result = default

    if minimum is not None:
        result = max(minimum, result)

    return result


def _safe_bool(
    value: Any,
    default: bool = False,
) -> bool:
    if isinstance(value, bool):
        return value

    if isinstance(value, str):
        normalized = value.strip().lower()

        if normalized in {
            "true",
            "yes",
            "1",
            "enabled",
            "active",
        }:
            return True

        if normalized in {
            "false",
            "no",
            "0",
            "disabled",
            "inactive",
        }:
            return False

    if value is None:
        return default

    return bool(value)


def _fmp_calendar_enabled() -> bool:
    """
    The FMP economic calendar is disabled by default.

    FMP gold quotes remain controlled separately by the Phase 37
    market-context service.

    To try the FMP economic calendar again in the future, explicitly add:

        ENABLE_FMP_ECONOMIC_CALENDAR = True

    to config/settings.py.
    """

    return _safe_bool(
        getattr(
            settings,
            "ENABLE_FMP_ECONOMIC_CALENDAR",
            False,
        ),
        default=False,
    )


def _free_calendar_enabled() -> bool:
    return _safe_bool(
        getattr(
            settings,
            "ENABLE_FREE_CALENDAR_FALLBACK",
            True,
        ),
        default=True,
    )


def _get_api_key() -> str:
    settings_key = str(
        getattr(
            settings,
            "FMP_API_KEY",
            "",
        )
        or ""
    ).strip()

    environment_key = str(
        os.getenv(
            "FMP_API_KEY",
            "",
        )
        or ""
    ).strip()

    return settings_key or environment_key


# ======================================================================
# SYNC METADATA
# ======================================================================

def _get_sync_file_path() -> str:
    return str(
        getattr(
            settings,
            "AUTO_ECONOMIC_CALENDAR_SYNC_FILE",
            "data/economic_calendar_sync.json",
        )
    )


def _ensure_folder_for_file(
    file_path: str,
) -> None:
    folder = os.path.dirname(file_path)

    if folder:
        os.makedirs(
            folder,
            exist_ok=True,
        )


def _load_sync_metadata() -> dict[str, Any]:
    file_path = _get_sync_file_path()

    if not os.path.exists(file_path):
        return {}

    try:
        with open(
            file_path,
            "r",
            encoding="utf-8",
        ) as file:
            metadata = json.load(file)

        if isinstance(metadata, dict):
            return metadata

    except Exception:
        pass

    return {}


def _save_sync_metadata(
    metadata: dict[str, Any],
) -> str:
    """
    Saves metadata atomically to reduce corruption risk.
    """

    file_path = _get_sync_file_path()
    temporary_path = f"{file_path}.tmp"

    _ensure_folder_for_file(
        file_path
    )

    with open(
        temporary_path,
        "w",
        encoding="utf-8",
    ) as file:
        json.dump(
            metadata,
            file,
            indent=4,
            default=str,
        )

    os.replace(
        temporary_path,
        file_path,
    )

    return file_path


def _should_sync(
    force: bool = False,
) -> bool:
    if force:
        return True

    refresh_hours = _safe_int(
        getattr(
            settings,
            "AUTO_ECONOMIC_CALENDAR_REFRESH_HOURS",
            3,
        ),
        default=3,
        minimum=1,
    )

    metadata = _load_sync_metadata()
    last_sync = metadata.get("last_sync")

    if not last_sync:
        return True

    try:
        last_sync_datetime = datetime.fromisoformat(
            str(last_sync)
        )
    except (TypeError, ValueError):
        return True

    age = datetime.now() - last_sync_datetime

    return (
        age.total_seconds()
        >= refresh_hours * 3600
    )


# ======================================================================
# TARGET EVENT FILTERS
# ======================================================================

def _get_keywords() -> list[str]:
    configured = getattr(
        settings,
        "AUTO_ECONOMIC_CALENDAR_KEYWORDS",
        [
            "CPI",
            "NFP",
            "FOMC",
            "Federal Reserve",
            "Core PCE",
            "Unemployment Rate",
            "Retail Sales",
        ],
    )

    if isinstance(
        configured,
        (list, tuple, set),
    ):
        return [
            str(keyword)
            for keyword in configured
            if str(keyword).strip()
        ]

    return [
        "CPI",
        "NFP",
        "FOMC",
        "Federal Reserve",
        "Core PCE",
        "Unemployment Rate",
        "Retail Sales",
    ]


def _matches_target_keywords(
    event: dict[str, Any],
) -> bool:
    text_parts = [
        str(event.get("event", "")),
        str(event.get("Event", "")),
        str(event.get("title", "")),
        str(event.get("name", "")),
        str(event.get("category", "")),
        str(event.get("Category", "")),
    ]

    event_text = " ".join(
        text_parts
    ).lower()

    return any(
        str(keyword).lower() in event_text
        for keyword in _get_keywords()
    )


def _matches_usd_event(
    event: dict[str, Any],
) -> bool:
    target_currency = str(
        getattr(
            settings,
            "AUTO_ECONOMIC_CALENDAR_CURRENCY",
            "USD",
        )
        or "USD"
    ).upper()

    currency = str(
        event.get("currency")
        or event.get("Currency")
        or ""
    ).upper()

    country = str(
        event.get("country")
        or event.get("Country")
        or ""
    ).upper()

    if currency == target_currency:
        return True

    return country in {
        "US",
        "USA",
        "UNITED STATES",
        "UNITED STATES OF AMERICA",
    }


def _normalize_impact(
    event: dict[str, Any],
) -> str:
    impact = str(
        event.get("impact")
        or event.get("Impact")
        or event.get("importance")
        or event.get("Importance")
        or ""
    ).upper()

    if impact in {
        "HIGH",
        "3",
        "IMPORTANT",
    }:
        return "HIGH"

    if impact in {
        "MEDIUM",
        "2",
        "MODERATE",
    }:
        return "MEDIUM"

    if impact in {
        "LOW",
        "1",
    }:
        return "LOW"

    # Unknown economic events are treated conservatively.
    return "HIGH"


# ======================================================================
# OPTIONAL FMP CALENDAR
# ======================================================================

def _parse_fmp_datetime(
    date_value: Any,
) -> datetime | None:
    if not date_value:
        return None

    raw_value = str(
        date_value
    ).strip()

    try:
        normalized = raw_value.replace(
            "Z",
            "+00:00",
        )

        parsed = datetime.fromisoformat(
            normalized
        )

        if parsed.tzinfo is None:
            parsed = parsed.replace(
                tzinfo=timezone.utc
            )

        local_datetime = parsed.astimezone()

        return local_datetime.replace(
            tzinfo=None
        )

    except Exception:
        pass

    formats = [
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%dT%H:%M:%S",
        "%Y-%m-%d",
    ]

    for date_format in formats:
        try:
            if date_format == "%Y-%m-%d":
                parsed = datetime.strptime(
                    raw_value[:10],
                    "%Y-%m-%d",
                )
            else:
                parsed = datetime.strptime(
                    raw_value[:19],
                    date_format,
                )

            parsed = parsed.replace(
                tzinfo=timezone.utc
            )

            local_datetime = parsed.astimezone()

            return local_datetime.replace(
                tzinfo=None
            )

        except Exception:
            continue

    return None


def _build_fmp_url() -> str:
    api_key = _get_api_key()

    days_ahead = _safe_int(
        getattr(
            settings,
            "AUTO_ECONOMIC_CALENDAR_DAYS_AHEAD",
            14,
        ),
        default=14,
        minimum=1,
    )

    start_date = datetime.now().strftime(
        "%Y-%m-%d"
    )

    end_date = (
        datetime.now()
        + timedelta(days=days_ahead)
    ).strftime("%Y-%m-%d")

    parameters = urllib.parse.urlencode(
        {
            "from": start_date,
            "to": end_date,
            "apikey": api_key,
        }
    )

    return (
        "https://financialmodelingprep.com/"
        f"stable/economic-calendar?{parameters}"
    )


def fetch_fmp_calendar() -> dict[str, Any]:
    """
    Fetches the FMP economic calendar only when explicitly enabled.

    Default behavior:
        ENABLE_FMP_ECONOMIC_CALENDAR = False

    Therefore the bot makes no FMP calendar request and avoids the
    blocked 403 endpoint.
    """

    if not _fmp_calendar_enabled():
        return {
            "success": False,
            "skipped": True,
            "message": (
                "FMP economic calendar disabled. "
                "Free calendar will be used directly."
            ),
            "raw_events": [],
            "provider": "FMP",
            "api_call_made": False,
        }

    api_key = _get_api_key()

    if not api_key:
        return {
            "success": False,
            "skipped": True,
            "message": (
                "FMP API key missing. "
                "Free calendar will be used."
            ),
            "raw_events": [],
            "provider": "FMP",
            "api_call_made": False,
        }

    timeout_seconds = _safe_int(
        getattr(
            settings,
            "AUTO_ECONOMIC_CALENDAR_TIMEOUT_SECONDS",
            20,
        ),
        default=20,
        minimum=1,
    )

    try:
        request = urllib.request.Request(
            _build_fmp_url(),
            headers={
                "User-Agent": (
                    "AI-Trading-Platform/1.0"
                ),
            },
        )

        with urllib.request.urlopen(
            request,
            timeout=timeout_seconds,
        ) as response:
            raw_data = response.read().decode(
                "utf-8"
            )

        data = json.loads(
            raw_data
        )

        if isinstance(data, dict):
            possible_error = (
                data.get("Error Message")
                or data.get("error")
                or data.get("message")
            )

            if possible_error:
                return {
                    "success": False,
                    "skipped": False,
                    "message": (
                        "FMP calendar response error: "
                        f"{possible_error}"
                    ),
                    "raw_events": [],
                    "provider": "FMP",
                    "api_call_made": True,
                }

        if not isinstance(data, list):
            return {
                "success": False,
                "skipped": False,
                "message": (
                    "Unexpected FMP calendar "
                    "response format."
                ),
                "raw_events": [],
                "provider": "FMP",
                "api_call_made": True,
            }

        return {
            "success": True,
            "skipped": False,
            "message": (
                "FMP economic calendar fetched."
            ),
            "raw_events": data,
            "provider": "FMP",
            "api_call_made": True,
        }

    except Exception as error:
        return {
            "success": False,
            "skipped": False,
            "message": (
                f"FMP calendar fetch failed: {error}"
            ),
            "raw_events": [],
            "provider": "FMP",
            "api_call_made": True,
        }


def _convert_fmp_event_to_internal(
    event: dict[str, Any],
) -> dict[str, Any] | None:
    raw_date = (
        event.get("date")
        or event.get("Date")
        or event.get("datetime")
        or event.get("time")
    )

    event_time = _parse_fmp_datetime(
        raw_date
    )

    if event_time is None:
        return None

    event_name = str(
        event.get("event")
        or event.get("Event")
        or event.get("title")
        or event.get("name")
        or "USD Economic Event"
    ).strip()

    category = str(
        event.get("category")
        or event.get("Category")
        or ""
    ).strip()

    title_parts = []

    if event_name:
        title_parts.append(
            event_name
        )

    if (
        category
        and category.lower()
        not in event_name.lower()
    ):
        title_parts.append(
            category
        )

    title = (
        " - ".join(title_parts)
        or "USD Economic Event"
    )

    external_id = (
        event.get("id")
        or event.get("calendarId")
        or event.get("CalendarId")
        or (
            "FMP:"
            f"{title}:"
            f"{event_time.strftime(DATETIME_FORMAT)}"
        )
    )

    currency = str(
        getattr(
            settings,
            "AUTO_ECONOMIC_CALENDAR_CURRENCY",
            "USD",
        )
        or "USD"
    ).upper()

    return {
        "title": title,
        "currency": currency,
        "impact": _normalize_impact(event),
        "event_time": event_time.strftime(
            DATETIME_FORMAT
        ),
        "enabled": True,
        "source": AUTO_SOURCE_FMP,
        "provider": "Financial Modeling Prep",
        "external_id": f"FMP:{external_id}",
        "country": (
            event.get("country")
            or event.get("Country")
            or "US"
        ),
        "category": category,
        "utc_time": str(raw_date),
        "actual": event.get("actual", event.get("Actual")),
        "forecast": event.get("estimate", event.get("Estimate", event.get("forecast"))),
        "previous": event.get("previous", event.get("Previous")),
        "calendar_confidence": "PROVIDER_VERIFIED",
        "source_detail": "fmp_economic_calendar",
    }


def _convert_fmp_events(
    raw_events: list[Any],
) -> list[dict[str, Any]]:
    converted_events: list[
        dict[str, Any]
    ] = []

    seen_ids: set[str] = set()

    for raw_event in raw_events:
        if not isinstance(
            raw_event,
            dict,
        ):
            continue

        if not _matches_usd_event(
            raw_event
        ):
            continue

        if not _matches_target_keywords(
            raw_event
        ):
            continue

        converted = (
            _convert_fmp_event_to_internal(
                raw_event
            )
        )

        if converted is None:
            continue

        external_id = str(
            converted.get(
                "external_id",
                "",
            )
        )

        if external_id in seen_ids:
            continue

        seen_ids.add(
            external_id
        )

        converted_events.append(
            converted
        )

    return converted_events


# ======================================================================
# FREE OFFICIAL AND CONSERVATIVE CALENDAR
# ======================================================================

def _fetch_url_text(
    url: str,
) -> str:
    timeout_seconds = _safe_int(
        getattr(
            settings,
            "FREE_CALENDAR_TIMEOUT_SECONDS",
            20,
        ),
        default=20,
        minimum=1,
    )

    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": (
                "AI-Trading-Platform/1.0"
            ),
        },
    )

    with urllib.request.urlopen(
        request,
        timeout=timeout_seconds,
    ) as response:
        return response.read().decode(
            "utf-8",
            errors="ignore",
        )


def _html_to_text(
    html: str,
) -> str:
    text = re.sub(
        r"<script.*?</script>",
        " ",
        html,
        flags=re.I | re.S,
    )

    text = re.sub(
        r"<style.*?</style>",
        " ",
        text,
        flags=re.I | re.S,
    )

    text = re.sub(
        r"<[^>]+>",
        "\n",
        text,
    )

    text = unescape(
        text
    )

    lines = [
        line.strip()
        for line in text.splitlines()
        if line.strip()
    ]

    return "\n".join(
        lines
    )


def _local_from_eastern(
    year: int,
    month: int,
    day: int,
    hour: int,
    minute: int,
) -> datetime:
    """
    Converts U.S. Eastern release time to the computer's local time.
    """

    try:
        if ZoneInfo is None:
            raise RuntimeError(
                "ZoneInfo unavailable."
            )

        timezone_name = str(
            getattr(
                settings,
                "FREE_CALENDAR_TIMEZONE",
                "America/New_York",
            )
        )

        eastern_timezone = ZoneInfo(
            timezone_name
        )

        eastern_datetime = datetime(
            year,
            month,
            day,
            hour,
            minute,
            tzinfo=eastern_timezone,
        )

        local_datetime = (
            eastern_datetime.astimezone()
        )

        return local_datetime.replace(
            tzinfo=None
        )

    except Exception:
        return datetime(
            year,
            month,
            day,
            hour,
            minute,
        )


def _make_free_event(
    title: str,
    event_time: datetime,
    category: str = "Free Fallback",
    source_detail: str = "conservative",
    impact: str = "HIGH",
    calendar_confidence: str = "VERIFIED",
    provider: str = "Free Official/Conservative Fallback",
) -> dict[str, Any]:
    return {
        "title": title,
        "currency": "USD",
        "impact": str(impact).upper(),
        "event_time": event_time.strftime(
            DATETIME_FORMAT
        ),
        "enabled": True,
        "source": AUTO_SOURCE_FREE,
        "provider": provider,
        "external_id": (
            f"FREE:{title}:"
            f"{event_time.strftime(DATETIME_FORMAT)}"
        ),
        "country": "US",
        "category": category,
        "source_detail": source_detail,
        "calendar_confidence": str(calendar_confidence).upper(),
    }


def _month_number(
    month_name: str,
) -> int | None:
    months = {
        "january": 1,
        "jan": 1,
        "february": 2,
        "feb": 2,
        "march": 3,
        "mar": 3,
        "april": 4,
        "apr": 4,
        "may": 5,
        "june": 6,
        "jun": 6,
        "july": 7,
        "jul": 7,
        "august": 8,
        "aug": 8,
        "september": 9,
        "sep": 9,
        "sept": 9,
        "october": 10,
        "oct": 10,
        "november": 11,
        "nov": 11,
        "december": 12,
        "dec": 12,
    }

    clean_name = (
        str(month_name)
        .lower()
        .replace(".", "")
        .strip()
    )

    return months.get(
        clean_name
    )


def _parse_bls_current_year_schedule() -> list[
    dict[str, Any]
]:
    """
    Attempts to read the official BLS release schedule.

    Conservative fallback events are still generated when this parser
    cannot retrieve or recognize an event.
    """

    events: list[
        dict[str, Any]
    ] = []

    url = (
        "https://www.bls.gov/schedule/"
        "news_release/current_year.asp"
    )

    try:
        text = _html_to_text(
            _fetch_url_text(url)
        )
    except Exception:
        return events

    pattern = re.compile(
        r"(Monday|Tuesday|Wednesday|Thursday|Friday|"
        r"Saturday|Sunday)\s*,?\s+"
        r"([A-Za-z]+)\s+(\d{1,2}),\s+(\d{4})\s+"
        r"(\d{1,2}:\d{2})\s*(AM|PM)\s+"
        r"(.+?)(?=(Monday|Tuesday|Wednesday|Thursday|"
        r"Friday|Saturday|Sunday)\s*,?\s+[A-Za-z]+|\Z)",
        flags=re.I | re.S,
    )

    for match in pattern.finditer(
        text
    ):
        month_name = match.group(2)
        day = int(match.group(3))
        year = int(match.group(4))
        time_part = match.group(5)
        am_pm = match.group(6).upper()

        release_name = " ".join(
            match.group(7).split()
        )

        month = _month_number(
            month_name
        )

        if not month:
            continue

        try:
            hour, minute = [
                int(part)
                for part in time_part.split(":")
            ]

            if (
                am_pm == "PM"
                and hour != 12
            ):
                hour += 12

            if (
                am_pm == "AM"
                and hour == 12
            ):
                hour = 0

            event_time = _local_from_eastern(
                year,
                month,
                day,
                hour,
                minute,
            )

        except Exception:
            continue

        release_lower = (
            release_name.lower()
        )

        if (
            "consumer price index"
            in release_lower
        ):
            events.append(
                _make_free_event(
                    title=(
                        f"CPI - {release_name}"
                    ),
                    event_time=event_time,
                    category="CPI",
                    source_detail=(
                        "official_bls_schedule"
                    ),
                )
            )

        if (
            "employment situation"
            in release_lower
        ):
            events.append(
                _make_free_event(
                    title=(
                        "NFP / Unemployment Rate - "
                        f"{release_name}"
                    ),
                    event_time=event_time,
                    category=(
                        "Employment Situation"
                    ),
                    source_detail=(
                        "official_bls_schedule"
                    ),
                )
            )

    return events


def _is_business_day(
    date_value: datetime,
) -> bool:
    return date_value.weekday() < 5


def _first_friday(
    year: int,
    month: int,
) -> datetime:
    current = datetime(
        year,
        month,
        1,
    )

    while current.weekday() != 4:
        current += timedelta(days=1)

    return current


def _last_business_day(
    year: int,
    month: int,
) -> datetime:
    if month == 12:
        current = (
            datetime(
                year + 1,
                1,
                1,
            )
            - timedelta(days=1)
        )
    else:
        current = (
            datetime(
                year,
                month + 1,
                1,
            )
            - timedelta(days=1)
        )

    while not _is_business_day(
        current
    ):
        current -= timedelta(days=1)

    return current


def _date_range_days(
    days_ahead: int,
):
    today = datetime.now().date()

    for offset in range(
        days_ahead + 1
    ):
        yield today + timedelta(
            days=offset
        )


def _generate_official_fomc_events() -> list[dict[str, Any]]:
    """Build verified FOMC decision events from the official Fed schedule."""

    events: list[dict[str, Any]] = []
    now = datetime.now()
    days_ahead = _safe_int(
        getattr(settings, "FREE_CALENDAR_FALLBACK_DAYS_AHEAD", 14),
        default=14,
        minimum=1,
    )
    earliest = now - timedelta(hours=2)
    final_date = now.date() + timedelta(days=days_ahead)
    latest = datetime.combine(final_date, datetime.max.time()).replace(microsecond=0)

    for year, dates in OFFICIAL_FOMC_DECISION_DATES.items():
        for month, day in dates:
            event_time = _local_from_eastern(year, month, day, 14, 0)
            if event_time < earliest or event_time > latest:
                continue
            events.append(
                _make_free_event(
                    title=(
                        "FOMC / Fed Interest Rate Decision "
                        "- Official Federal Reserve Schedule"
                    ),
                    event_time=event_time,
                    category="FOMC",
                    source_detail="official_federal_reserve_schedule",
                    impact="HIGH",
                    calendar_confidence="VERIFIED",
                    provider="Federal Reserve",
                )
            )

    return events


def _generate_conservative_fallback_events() -> list[
    dict[str, Any]
]:
    """
    Creates conservative USD watch windows.

    These dates are estimates, not verified release times. They are stored as
    MEDIUM/watch-only records and do not hard-block trading by default.
    """

    events: list[
        dict[str, Any]
    ] = []

    days_ahead = _safe_int(
        getattr(
            settings,
            "FREE_CALENDAR_FALLBACK_DAYS_AHEAD",
            14,
        ),
        default=14,
        minimum=1,
    )

    for date_value in _date_range_days(
        days_ahead
    ):
        year = date_value.year
        month = date_value.month
        day = date_value.day

        current_datetime = datetime(
            year,
            month,
            day,
        )

        # Employment Situation / NFP.
        first_friday = _first_friday(
            year,
            month,
        ).date()

        if date_value == first_friday:
            events.append(
                _make_free_event(
                    title=(
                        "NFP / Unemployment Rate "
                        "- Conservative Watch"
                    ),
                    event_time=_local_from_eastern(
                        year,
                        month,
                        day,
                        8,
                        30,
                    ),
                    category=(
                        "Employment Situation"
                    ),
                    source_detail=(
                        "conservative_first_friday"
                    ),
                    impact="MEDIUM",
                    calendar_confidence="ESTIMATED",
                )
            )

        # CPI conservative window.
        if (
            10 <= day <= 15
            and _is_business_day(
                current_datetime
            )
        ):
            events.append(
                _make_free_event(
                    title=(
                        "CPI - Conservative Watch"
                    ),
                    event_time=_local_from_eastern(
                        year,
                        month,
                        day,
                        8,
                        30,
                    ),
                    category="CPI",
                    source_detail=(
                        "conservative_mid_month"
                    ),
                    impact="MEDIUM",
                    calendar_confidence="ESTIMATED",
                )
            )

        # Retail sales conservative window.
        if (
            14 <= day <= 17
            and _is_business_day(
                current_datetime
            )
        ):
            events.append(
                _make_free_event(
                    title=(
                        "Retail Sales "
                        "- Conservative Watch"
                    ),
                    event_time=_local_from_eastern(
                        year,
                        month,
                        day,
                        8,
                        30,
                    ),
                    category="Retail Sales",
                    source_detail=(
                        "conservative_mid_month"
                    ),
                    impact="MEDIUM",
                    calendar_confidence="ESTIMATED",
                )
            )


        # Core PCE conservative window.
        last_business_day = (
            _last_business_day(
                year,
                month,
            ).date()
        )

        if date_value == last_business_day:
            events.append(
                _make_free_event(
                    title=(
                        "Core PCE / PCE Price Index "
                        "- Conservative Watch"
                    ),
                    event_time=_local_from_eastern(
                        year,
                        month,
                        day,
                        8,
                        30,
                    ),
                    category="Core PCE",
                    source_detail=(
                        "conservative_last_business_day"
                    ),
                    impact="MEDIUM",
                    calendar_confidence="ESTIMATED",
                )
            )

    return events


def fetch_free_official_calendar() -> dict[str, Any]:
    """
    Builds the free calendar from:
    - the official BLS release schedule when available;
    - non-blocking conservative watch windows when enabled.
    """

    events: list[
        dict[str, Any]
    ] = []

    official_bls_events = (
        _parse_bls_current_year_schedule()
    )

    official_fomc_events = _generate_official_fomc_events()

    events.extend(
        official_bls_events
    )
    events.extend(
        official_fomc_events
    )

    use_conservative_estimates = _safe_bool(
        getattr(
            settings,
            "FREE_CALENDAR_USE_CONSERVATIVE_ESTIMATES",
            True,
        ),
        default=True,
    )

    if use_conservative_estimates:
        events.extend(
            _generate_conservative_fallback_events()
        )

    unique_events: list[
        dict[str, Any]
    ] = []

    seen: set[
        tuple[Any, Any, Any]
    ] = set()

    now = datetime.now()

    days_ahead = _safe_int(
        getattr(
            settings,
            "FREE_CALENDAR_FALLBACK_DAYS_AHEAD",
            14,
        ),
        default=14,
        minimum=1,
    )

    final_date = now.date() + timedelta(days=days_ahead)
    maximum_time = datetime.combine(
        final_date,
        datetime.max.time(),
    ).replace(microsecond=0)

    for event in events:
        try:
            event_time = datetime.strptime(
                event["event_time"],
                DATETIME_FORMAT,
            )
        except Exception:
            continue

        if (
            event_time
            < now - timedelta(hours=2)
        ):
            continue

        if event_time > maximum_time:
            continue

        key = (
            event.get("title"),
            event.get("event_time"),
            event.get("category"),
        )

        if key in seen:
            continue

        seen.add(
            key
        )

        unique_events.append(
            event
        )

    return {
        "success": True,
        "skipped": False,
        "message": (
            "Free official/conservative "
            "calendar sync complete."
        ),
        "raw_events": unique_events,
        "provider": "FREE_FALLBACK",
        "official_bls_events": len(
            official_bls_events
        ),
        "official_fomc_events": len(
            official_fomc_events
        ),
        "total_free_events": len(
            unique_events
        ),
    }


# ======================================================================
# EVENT SYNCHRONIZATION
# ======================================================================

def _remove_old_auto_events(
    events: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    auto_sources = {
        AUTO_SOURCE_FMP,
        AUTO_SOURCE_FREE,
        "AUTO_TRADING_ECONOMICS",
    }

    return [
        event
        for event in events
        if event.get("source")
        not in auto_sources
    ]


def _sync_with_events(
    auto_events: list[dict[str, Any]],
    provider_name: str,
    fetch_message: str,
    *,
    fmp_calendar_enabled: bool,
    fmp_api_call_made: bool,
) -> dict[str, Any]:
    existing_events = load_events()

    manual_events = _remove_old_auto_events(
        existing_events
    )

    final_events = (
        manual_events
        + auto_events
    )

    save_events(
        final_events
    )

    now = datetime.now().isoformat()

    refresh_hours = _safe_int(
        getattr(
            settings,
            "AUTO_ECONOMIC_CALENDAR_REFRESH_HOURS",
            3,
        ),
        default=3,
        minimum=1,
    )

    metadata = {
        "last_sync": now,
        "last_attempt": now,
        "last_success": True,
        "last_message": fetch_message,
        "last_added_events": len(
            auto_events
        ),
        "total_events": len(
            final_events
        ),
        "provider": provider_name,
        "refresh_hours": refresh_hours,
        "fmp_calendar_enabled": (
            fmp_calendar_enabled
        ),
        "fmp_api_call_made": (
            fmp_api_call_made
        ),
    }

    sync_file = _save_sync_metadata(
        metadata
    )

    return {
        "success": True,
        "skipped": False,
        "message": fetch_message,
        "provider": provider_name,
        "added_events": len(
            auto_events
        ),
        "total_events": len(
            final_events
        ),
        "sync_file": sync_file,
        "fmp_calendar_enabled": (
            fmp_calendar_enabled
        ),
        "fmp_api_call_made": (
            fmp_api_call_made
        ),
    }


def _save_failed_sync(
    message: str,
    provider: str = "NONE",
) -> None:
    metadata = {
        "last_attempt": datetime.now().isoformat(),
        "last_success": False,
        "last_message": message,
        "last_added_events": 0,
        "provider": provider,
        "fmp_calendar_enabled": (
            _fmp_calendar_enabled()
        ),
    }

    _save_sync_metadata(
        metadata
    )


# ======================================================================
# MAIN CALENDAR SYNCHRONIZATION
# ======================================================================

def sync_auto_economic_calendar(
    force: bool = False,
    *,
    free_only: bool = False,
) -> dict[str, Any]:
    """
    Synchronizes economic events.

    Default provider order:

        Free official/verified calendar

    The FMP economic calendar is not called unless
    ENABLE_FMP_ECONOMIC_CALENDAR=True is explicitly configured.
    """

    if type(free_only) is not bool:
        raise ValueError('free_only must be a boolean')
    fmp_enabled = _fmp_calendar_enabled() and not free_only
    if free_only and _load_sync_metadata().get('fmp_calendar_enabled'):
        force = True
    auto_calendar_enabled = _safe_bool(
        getattr(
            settings,
            "ENABLE_AUTO_ECONOMIC_CALENDAR",
            True,
        ),
        default=True,
    )

    if not auto_calendar_enabled:
        return {
            "success": True,
            "skipped": True,
            "message": (
                "Auto economic calendar disabled."
            ),
            "provider": "DISABLED",
            "added_events": 0,
            "total_events": len(
                load_events()
            ),
            "fmp_calendar_enabled": (
                fmp_enabled
            ),
            "fmp_api_call_made": False,
        }

    if not _should_sync(
        force=force
    ):
        metadata = _load_sync_metadata()

        return {
            "success": True,
            "skipped": True,
            "message": (
                "Auto economic calendar already fresh."
            ),
            "provider": metadata.get(
                "provider",
                "UNKNOWN",
            ),
            "added_events": metadata.get(
                "last_added_events",
                0,
            ),
            "total_events": len(
                load_events()
            ),
            "last_sync": metadata.get(
                "last_sync"
            ),
            "fmp_calendar_enabled": (
                metadata.get(
                    "fmp_calendar_enabled",
                    fmp_enabled,
                )
            ),
            "fmp_api_call_made": False,
        }

    # ==================================================================
    # OPTIONAL FMP PATH
    # ==================================================================

    if fmp_enabled:
        fmp_result = fetch_fmp_calendar()

        if fmp_result.get(
            "success",
            False,
        ):
            auto_events = _convert_fmp_events(
                fmp_result.get(
                    "raw_events",
                    [],
                )
            )

            return _sync_with_events(
                auto_events=auto_events,
                provider_name="FMP",
                fetch_message=(
                    "FMP auto calendar sync complete."
                ),
                fmp_calendar_enabled=True,
                fmp_api_call_made=True,
            )

        if _free_calendar_enabled():
            free_result = (
                fetch_free_official_calendar()
            )

            if not free_result.get(
                "success",
                False,
            ):
                failure_message = (
                    "FMP and free calendar both failed. "
                    f"FMP: {fmp_result.get('message')}. "
                    f"Free: {free_result.get('message')}."
                )

                _save_failed_sync(
                    failure_message
                )

                return {
                    "success": False,
                    "skipped": False,
                    "message": failure_message,
                    "provider": "NONE",
                    "added_events": 0,
                    "total_events": len(
                        load_events()
                    ),
                    "fmp_calendar_enabled": True,
                    "fmp_api_call_made": (
                        fmp_result.get(
                            "api_call_made",
                            False,
                        )
                    ),
                }

            result = _sync_with_events(
                auto_events=free_result.get(
                    "raw_events",
                    [],
                ),
                provider_name="FREE_FALLBACK",
                fetch_message=(
                    "Free calendar sync complete after "
                    "the optional FMP calendar failed."
                ),
                fmp_calendar_enabled=True,
                fmp_api_call_made=(
                    fmp_result.get(
                        "api_call_made",
                        False,
                    )
                ),
            )

            result["fmp_message"] = (
                fmp_result.get("message")
            )

            return result

        failure_message = str(
            fmp_result.get(
                "message",
                "FMP calendar failed.",
            )
        )

        _save_failed_sync(
            failure_message,
            provider="FMP",
        )

        return {
            "success": False,
            "skipped": fmp_result.get(
                "skipped",
                False,
            ),
            "message": failure_message,
            "provider": "FMP",
            "added_events": 0,
            "total_events": len(
                load_events()
            ),
            "fmp_calendar_enabled": True,
            "fmp_api_call_made": (
                fmp_result.get(
                    "api_call_made",
                    False,
                )
            ),
        }

    # ==================================================================
    # DEFAULT FREE-ONLY PATH — NO FMP REQUEST
    # ==================================================================

    if not _free_calendar_enabled():
        failure_message = (
            "No economic-calendar provider is enabled. "
            "FMP calendar is disabled and free calendar "
            "fallback is disabled."
        )

        _save_failed_sync(
            failure_message
        )

        return {
            "success": False,
            "skipped": True,
            "message": failure_message,
            "provider": "NONE",
            "added_events": 0,
            "total_events": len(
                load_events()
            ),
            "fmp_calendar_enabled": False,
            "fmp_api_call_made": False,
        }

    free_result = (
        fetch_free_official_calendar()
    )

    if not free_result.get(
        "success",
        False,
    ):
        failure_message = str(
            free_result.get(
                "message",
                "Free calendar sync failed.",
            )
        )

        _save_failed_sync(
            failure_message,
            provider="FREE_FALLBACK",
        )

        return {
            "success": False,
            "skipped": False,
            "message": failure_message,
            "provider": "FREE_FALLBACK",
            "added_events": 0,
            "total_events": len(
                load_events()
            ),
            "fmp_calendar_enabled": False,
            "fmp_api_call_made": False,
        }

    return _sync_with_events(
        auto_events=free_result.get(
            "raw_events",
            [],
        ),
        provider_name="FREE_FALLBACK",
        fetch_message=(
            "Free official/verified calendar sync complete. "
            "FMP economic calendar disabled; no FMP calendar "
            "API call was made."
        ),
        fmp_calendar_enabled=False,
        fmp_api_call_made=False,
    )


def sync_auto_economic_calendar_if_needed(*, free_only: bool = False) -> dict[str, Any]:
    return sync_auto_economic_calendar(
        force=False, free_only=free_only
    )


# ======================================================================
# BACKWARD-COMPATIBLE FUNCTION NAMES
# ======================================================================

def fetch_trading_economics_calendar() -> dict[str, Any]:
    """
    Backward-compatible name retained for older imports.

    It no longer calls Trading Economics. It delegates to the optional
    FMP calendar function, which is disabled by default.
    """

    return fetch_fmp_calendar()


def fetch_free_calendar_fallback() -> dict[str, Any]:
    return fetch_free_official_calendar()
