import json
import os
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Mapping
from datetime import datetime
from typing import Any

from config import settings


DATETIME_FORMAT = "%Y-%m-%d %H:%M:%S"


# ======================================================================
# CONFIGURATION HELPERS
# ======================================================================

def _get_api_key() -> str:
    """
    Gets the FMP API key.

    The settings value is checked first for compatibility.
    The environment variable is used when settings.FMP_API_KEY is blank.
    """

    settings_key = str(
        getattr(settings, "FMP_API_KEY", "") or ""
    ).strip()

    environment_key = str(
        os.getenv("FMP_API_KEY", "") or ""
    ).strip()

    return settings_key or environment_key


def _get_context_file_path() -> str:
    return str(
        getattr(
            settings,
            "FMP_MARKET_CONTEXT_FILE",
            "data/fmp_market_context.json",
        )
    )


def _get_refresh_hours() -> int:
    try:
        refresh_hours = int(
            getattr(
                settings,
                "FMP_MARKET_CONTEXT_REFRESH_HOURS",
                3,
            )
        )
    except (TypeError, ValueError):
        refresh_hours = 3

    return max(1, refresh_hours)


def _get_timeout_seconds() -> int:
    try:
        timeout_seconds = int(
            getattr(
                settings,
                "FMP_MARKET_CONTEXT_TIMEOUT_SECONDS",
                20,
            )
        )
    except (TypeError, ValueError):
        timeout_seconds = 20

    return max(1, timeout_seconds)


def _forex_news_enabled() -> bool:
    return bool(
        getattr(
            settings,
            "ENABLE_FMP_FOREX_NEWS",
            False,
        )
    )


# ======================================================================
# CACHE MANAGEMENT
# ======================================================================

def _ensure_folder_for_file(file_path: str) -> None:
    folder = os.path.dirname(file_path)

    if folder:
        os.makedirs(folder, exist_ok=True)


def _load_context_cache() -> dict[str, Any]:
    file_path = _get_context_file_path()

    if not os.path.exists(file_path):
        return {}

    try:
        with open(file_path, "r", encoding="utf-8") as file:
            data = json.load(file)

        if isinstance(data, dict):
            return data

        return {}

    except (OSError, json.JSONDecodeError, TypeError):
        return {}


def _save_context_cache(data: dict[str, Any]) -> str:
    file_path = _get_context_file_path()

    _ensure_folder_for_file(file_path)

    with open(file_path, "w", encoding="utf-8") as file:
        json.dump(
            data,
            file,
            indent=4,
            default=str,
        )

    return file_path


def _should_refresh(force: bool = False) -> bool:
    if force:
        return True

    cache = _load_context_cache()
    last_refresh = cache.get("last_refresh")

    if not last_refresh:
        return True

    try:
        last_refresh_time = datetime.fromisoformat(
            str(last_refresh)
        )
    except (TypeError, ValueError):
        return True

    current_time = datetime.now().astimezone()

    # Support older cache files that used timezone-naive timestamps.
    if last_refresh_time.tzinfo is None:
        last_refresh_time = last_refresh_time.replace(
            tzinfo=current_time.tzinfo
        )

    cache_age_seconds = (
        current_time - last_refresh_time
    ).total_seconds()

    refresh_seconds = _get_refresh_hours() * 3600

    return cache_age_seconds >= refresh_seconds


# ======================================================================
# HTTP HELPERS
# ======================================================================

def _fetch_json(url: str) -> Any:
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": "AI-Trading-Platform/1.0",
            "Accept": "application/json",
        },
    )

    with urllib.request.urlopen(
        request,
        timeout=_get_timeout_seconds(),
    ) as response:
        raw_data = response.read().decode("utf-8")

    return json.loads(raw_data)


def _build_url(
    endpoint: str,
    params: Mapping[str, Any],
) -> str:
    query_parameters = dict(params)
    query_parameters["apikey"] = _get_api_key()

    query = urllib.parse.urlencode(query_parameters)
    clean_endpoint = endpoint.lstrip("/")

    return (
        "https://financialmodelingprep.com/stable/"
        f"{clean_endpoint}?{query}"
    )


def _extract_api_error(data: Any) -> str | None:
    if not isinstance(data, dict):
        return None

    possible_error = (
        data.get("Error Message")
        or data.get("error")
        or data.get("message")
    )

    if possible_error:
        return str(possible_error)

    return None


# ======================================================================
# FMP GOLD QUOTE
# ======================================================================

def fetch_gold_quote() -> dict[str, Any]:
    api_key = _get_api_key()

    if not api_key:
        return {
            "success": False,
            "message": "FMP API key missing.",
            "data": None,
        }

    symbol = str(
        getattr(
            settings,
            "FMP_GOLD_SYMBOL",
            "GCUSD",
        )
        or "GCUSD"
    ).upper()

    url = _build_url(
        "quote-short",
        {
            "symbol": symbol,
        },
    )

    try:
        data = _fetch_json(url)
        api_error = _extract_api_error(data)

        if api_error:
            return {
                "success": False,
                "message": api_error,
                "data": None,
            }

        if isinstance(data, list) and data:
            quote = data[0]

        elif isinstance(data, dict):
            quote = data

        else:
            quote = None

        if not isinstance(quote, dict) or not quote:
            return {
                "success": False,
                "message": "No gold quote returned.",
                "data": None,
            }

        if quote.get("price") is None:
            return {
                "success": False,
                "message": "Gold quote did not contain a price.",
                "data": None,
            }

        return {
            "success": True,
            "message": "Gold quote fetched.",
            "data": quote,
        }

    except urllib.error.HTTPError as error:
        return {
            "success": False,
            "message": (
                "Gold quote fetch failed: "
                f"HTTP {error.code} {error.reason}"
            ),
            "data": None,
        }

    except urllib.error.URLError as error:
        return {
            "success": False,
            "message": (
                "Gold quote fetch failed: "
                f"{error.reason}"
            ),
            "data": None,
        }

    except (
        json.JSONDecodeError,
        OSError,
        TypeError,
        ValueError,
    ) as error:
        return {
            "success": False,
            "message": f"Gold quote fetch failed: {error}",
            "data": None,
        }


# ======================================================================
# OPTIONAL FMP FOREX NEWS
# ======================================================================

def fetch_forex_news() -> dict[str, Any]:
    """
    Retained for compatibility with existing modules.

    The paid FMP Forex News endpoint is never called unless
    ENABLE_FMP_FOREX_NEWS is explicitly set to True.
    """

    if not _forex_news_enabled():
        return {
            "success": False,
            "skipped": True,
            "message": (
                "FMP forex news disabled to save API calls."
            ),
            "data": [],
        }

    api_key = _get_api_key()

    if not api_key:
        return {
            "success": False,
            "skipped": True,
            "message": "FMP API key missing.",
            "data": [],
        }

    try:
        limit = int(
            getattr(
                settings,
                "FMP_FOREX_NEWS_LIMIT",
                10,
            )
        )
    except (TypeError, ValueError):
        limit = 10

    limit = max(1, limit)

    url = _build_url(
        "news/forex-latest",
        {
            "page": 0,
            "limit": limit,
        },
    )

    try:
        data = _fetch_json(url)
        api_error = _extract_api_error(data)

        if api_error:
            return {
                "success": False,
                "skipped": False,
                "message": api_error,
                "data": [],
            }

        if not isinstance(data, list):
            return {
                "success": False,
                "skipped": False,
                "message": (
                    "Unexpected forex news response format."
                ),
                "data": [],
            }

        return {
            "success": True,
            "skipped": False,
            "message": "Forex news fetched.",
            "data": data[:limit],
        }

    except urllib.error.HTTPError as error:
        return {
            "success": False,
            "skipped": False,
            "message": (
                "Forex news fetch failed: "
                f"HTTP {error.code} {error.reason}"
            ),
            "data": [],
        }

    except urllib.error.URLError as error:
        return {
            "success": False,
            "skipped": False,
            "message": (
                "Forex news fetch failed: "
                f"{error.reason}"
            ),
            "data": [],
        }

    except (
        json.JSONDecodeError,
        OSError,
        TypeError,
        ValueError,
    ) as error:
        return {
            "success": False,
            "skipped": False,
            "message": f"Forex news fetch failed: {error}",
            "data": [],
        }


# ======================================================================
# NEWS RISK SCANNING
# ======================================================================

def _headline_text(news_items: list[Any]) -> str:
    parts: list[str] = []

    for item in news_items:
        if not isinstance(item, dict):
            continue

        parts.append(str(item.get("title", "")))
        parts.append(str(item.get("text", "")))
        parts.append(str(item.get("site", "")))

    return " ".join(parts).lower()


def _detect_high_risk_news(
    news_items: list[Any],
) -> dict[str, Any]:
    news_text = _headline_text(news_items)

    keywords = getattr(
        settings,
        "FMP_HIGH_RISK_NEWS_KEYWORDS",
        [],
    )

    matched_keywords: list[str] = []

    for keyword in keywords:
        clean_keyword = str(keyword).lower().strip()

        if clean_keyword and clean_keyword in news_text:
            matched_keywords.append(str(keyword))

    return {
        "high_risk_news_detected": bool(
            matched_keywords
        ),
        "matched_keywords": matched_keywords,
    }


# ======================================================================
# API USAGE ESTIMATE
# ======================================================================

def _estimated_calls_per_day(
    forex_news_enabled: bool,
) -> float:
    calls_per_refresh = 1

    if forex_news_enabled:
        calls_per_refresh += 1

    estimate = (
        24 / _get_refresh_hours()
    ) * calls_per_refresh

    return round(estimate, 2)


# ======================================================================
# BUILD FMP MARKET CONTEXT
# ======================================================================

def build_fmp_market_context(
    force: bool = False,
) -> dict[str, Any]:
    """
    Builds the FMP market context.

    Normal Phase 37 behavior:
    - one GCUSD quote request;
    - no Forex News request;
    - cache refresh every three hours;
    - approximately eight API calls per day.
    """

    if not bool(
        getattr(
            settings,
            "ENABLE_FMP_MARKET_CONTEXT",
            True,
        )
    ):
        return {
            "success": True,
            "skipped": True,
            "cache_hit": False,
            "message": "FMP market context disabled.",
            "calls_used": 0,
            "estimated_calls_per_day": 0,
        }

    # Return cached data without using another API call.
    if not _should_refresh(force=force):
        cache = _load_context_cache()
        cached_result = dict(cache)

        cached_result["cached_calls_used"] = cache.get(
            "calls_used",
            0,
        )

        # No API call was made during this cycle.
        cached_result["calls_used"] = 0
        cached_result["skipped"] = True
        cached_result["cache_hit"] = True
        cached_result["message"] = (
            "FMP market context cache still fresh."
        )

        return cached_result

    api_key_present = bool(_get_api_key())
    forex_news_enabled = _forex_news_enabled()

    # Phase 37 always requests the gold quote.
    gold_result = fetch_gold_quote()

    # Count an attempted HTTP request only when an API key exists.
    calls_used = 1 if api_key_present else 0

    if forex_news_enabled:
        news_result = fetch_forex_news()

        if api_key_present:
            calls_used += 1

    else:
        news_result = {
            "success": False,
            "skipped": True,
            "message": (
                "FMP forex news disabled to save API calls."
            ),
            "data": [],
        }

    news_items = news_result.get("data", [])

    if not isinstance(news_items, list):
        news_items = []

    risk_scan = _detect_high_risk_news(news_items)

    gold_success = bool(
        gold_result.get("success")
    )

    news_success = bool(
        news_result.get("success")
    )

    overall_success = (
        gold_success
        or (
            forex_news_enabled
            and news_success
        )
    )

    current_time = datetime.now().astimezone()

    context: dict[str, Any] = {
        "success": overall_success,
        "skipped": False,
        "cache_hit": False,
        "message": (
            "FMP market context refreshed."
            if overall_success
            else "FMP market context refresh failed."
        ),
        "last_refresh": current_time.isoformat(),
        "generated_at": current_time.strftime(
            DATETIME_FORMAT
        ),
        "provider": "FMP",
        "calls_used": calls_used,
        "estimated_calls_per_day": (
            _estimated_calls_per_day(
                forex_news_enabled
            )
        ),
        "refresh_hours": _get_refresh_hours(),

        "gold_quote_success": gold_success,
        "gold_quote_message": gold_result.get(
            "message"
        ),
        "gold_quote": gold_result.get("data"),

        "forex_news_enabled": forex_news_enabled,
        "forex_news_success": news_success,
        "forex_news_message": news_result.get(
            "message"
        ),
        "forex_news_count": len(news_items),
        "forex_news": news_items,

        "high_risk_news_detected": risk_scan[
            "high_risk_news_detected"
        ],
        "matched_news_keywords": risk_scan[
            "matched_keywords"
        ],
    }

    try:
        context["file_path"] = _save_context_cache(
            context
        )
        context["cache_save_success"] = True

    except OSError as error:
        # The bot can continue safely even if the cache cannot be saved.
        context["file_path"] = _get_context_file_path()
        context["cache_save_success"] = False
        context["cache_save_error"] = str(error)

    return context


# ======================================================================
# AI CONFIDENCE ADJUSTMENT
# ======================================================================

def apply_fmp_context_to_ai(
    ai_result: Any,
    fmp_context: Mapping[str, Any] | None,
) -> Any:
    """
    Conservatively adjusts AI confidence.

    This function:
    - never changes BUY to SELL;
    - never changes SELL to BUY;
    - never forces a trade;
    - only applies a small configured confidence adjustment.
    """

    if ai_result is None:
        ai_result = {}

    if not isinstance(ai_result, dict):
        return ai_result

    if not fmp_context or not bool(
        fmp_context.get("success")
    ):
        ai_result["fmp_context_applied"] = False
        ai_result["fmp_context_reason"] = (
            "No usable FMP context."
        )

        return ai_result

    try:
        confidence = float(
            ai_result.get("confidence", 0.0)
            or 0.0
        )
    except (TypeError, ValueError):
        confidence = 0.0

    try:
        bonus = float(
            getattr(
                settings,
                "FMP_CONTEXT_CONFIDENCE_BONUS",
                0.03,
            )
        )
    except (TypeError, ValueError):
        bonus = 0.03

    try:
        penalty = float(
            getattr(
                settings,
                "FMP_CONTEXT_CONFIDENCE_PENALTY",
                0.05,
            )
        )
    except (TypeError, ValueError):
        penalty = 0.05

    high_risk_news = bool(
        fmp_context.get(
            "high_risk_news_detected",
            False,
        )
    )

    gold_quote_success = bool(
        fmp_context.get(
            "gold_quote_success",
            False,
        )
    )

    adjustment = 0.0
    reasons: list[str] = []

    ai_action = str(
        ai_result.get("ai_action", ai_result.get("action", "")) or ""
    ).strip().upper()
    ai_can_trade = bool(
        ai_result.get("can_trade", ai_result.get("trade_allowed", False))
    )
    directional_confirmation = (
        ai_can_trade
        and ai_action in {"CONFIRMED_BUY", "CONFIRMED_SELL", "BUY", "SELL"}
    )

    if gold_quote_success and directional_confirmation:
        adjustment += bonus
        reasons.append("FMP gold quote confirmed a directional AI setup.")
    elif gold_quote_success:
        reasons.append("FMP gold quote available; no confidence bonus applied to NO_TRADE.")

    if high_risk_news:
        adjustment -= penalty
        reasons.append(
            "FMP forex news detected high-risk "
            "macro keywords."
        )

    adjusted_confidence = max(
        0.0,
        min(
            1.0,
            confidence + adjustment,
        ),
    )

    ai_result["confidence"] = adjusted_confidence
    ai_result["fmp_context_applied"] = True
    ai_result["fmp_context_adjustment"] = round(
        adjustment,
        4,
    )

    ai_result["fmp_context_reason"] = (
        " ".join(reasons)
        if reasons
        else "FMP context checked."
    )

    ai_result["fmp_high_risk_news_detected"] = (
        high_risk_news
    )

    ai_result["fmp_matched_news_keywords"] = (
        fmp_context.get(
            "matched_news_keywords",
            [],
        )
    )

    ai_result["fmp_gold_quote"] = (
        fmp_context.get("gold_quote")
    )

    return ai_result


# ======================================================================
# FLEXIBLE OBJECT / DICTIONARY READER
# ======================================================================

def _read_value(
    source: Any,
    field_name: str,
    default: Any = None,
) -> Any:
    if source is None:
        return default

    if isinstance(source, Mapping):
        return source.get(
            field_name,
            default,
        )

    return getattr(
        source,
        field_name,
        default,
    )


# ======================================================================
# FMP / MT5 PRICE COMPARISON
# ======================================================================

def compare_fmp_gold_to_snapshot(
    fmp_context: Mapping[str, Any] | None,
    snapshot: Any,
) -> dict[str, Any]:
    """
    Compares the FMP GCUSD quote with the MT5 XAUUSD midpoint.

    This is an informational external price-feed check only.
    It does not place, approve, reject, or modify a trade.
    """

    if not fmp_context or not bool(
        fmp_context.get("gold_quote_success")
    ):
        return {
            "success": False,
            "price_confirmed": False,
            "message": "No usable FMP gold quote.",
        }

    gold_quote = fmp_context.get(
        "gold_quote",
        {},
    )

    try:
        fmp_price = float(
            _read_value(
                gold_quote,
                "price",
            )
        )
    except (TypeError, ValueError):
        return {
            "success": False,
            "price_confirmed": False,
            "message": (
                "FMP gold price missing or invalid."
            ),
        }

    # Supports both:
    # snapshot.price.bid / snapshot.price.ask
    # snapshot["price"]["bid"] / snapshot["price"]["ask"]
    price_data = _read_value(
        snapshot,
        "price",
        None,
    )

    # Also supports snapshots with bid and ask directly.
    if price_data is None:
        price_data = snapshot

    bid = _read_value(
        price_data,
        "bid",
    )

    ask = _read_value(
        price_data,
        "ask",
    )

    try:
        bid_value = float(bid)
        ask_value = float(ask)

    except (TypeError, ValueError):
        return {
            "success": False,
            "price_confirmed": False,
            "fmp_price": fmp_price,
            "message": (
                "MT5 snapshot bid/ask missing or invalid."
            ),
        }

    if bid_value <= 0 or ask_value <= 0:
        return {
            "success": False,
            "price_confirmed": False,
            "fmp_price": fmp_price,
            "message": (
                "MT5 snapshot bid/ask must be positive."
            ),
        }

    mt5_mid_price = (
        bid_value + ask_value
    ) / 2

    difference = abs(
        fmp_price - mt5_mid_price
    )

    try:
        maximum_difference = float(
            getattr(
                settings,
                "FMP_PRICE_CONFIRMATION_MAX_DIFF_USD",
                25.00,
            )
        )
    except (TypeError, ValueError):
        maximum_difference = 25.00

    maximum_difference = max(
        0.0,
        maximum_difference,
    )

    price_confirmed = (
        difference <= maximum_difference
    )

    return {
        "success": True,
        "price_confirmed": price_confirmed,
        "fmp_price": round(fmp_price, 4),
        "mt5_bid": round(bid_value, 4),
        "mt5_ask": round(ask_value, 4),
        "mt5_mid_price": round(
            mt5_mid_price,
            4,
        ),
        "difference_usd": round(
            difference,
            4,
        ),
        "max_allowed_difference_usd": (
            maximum_difference
        ),
        "message": (
            "FMP and MT5 gold prices agree."
            if price_confirmed
            else (
                "FMP and MT5 gold prices differ "
                "too much."
            )
        ),
    }