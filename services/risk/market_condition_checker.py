from config.settings import MAX_SPREAD
from models.market_state import MarketSnapshot, MarketConditionState
from services.risk.spread_checker import is_spread_safe


REQUIRED_TIMEFRAMES = ["M1", "M5", "M15", "H1"]


def _is_price_valid(price) -> bool:
    """
    Checks if price data exists.
    Works with simple price values, dictionaries, or MT5-style objects.
    """

    if price is None:
        return False

    if isinstance(price, (int, float)):
        return price > 0

    if isinstance(price, dict):
        bid = price.get("bid")
        ask = price.get("ask")

        if bid is not None and ask is not None:
            return bid > 0 and ask > 0

        value = price.get("price")
        if value is not None:
            return value > 0

    if hasattr(price, "bid") and hasattr(price, "ask"):
        return price.bid > 0 and price.ask > 0

    return True


def _are_candles_loaded(candles: dict) -> bool:
    """
    Checks that all required timeframe candles are available.
    """

    if not candles:
        return False

    for timeframe in REQUIRED_TIMEFRAMES:
        data = candles.get(timeframe)

        if data is None:
            return False

        try:
            if len(data) == 0:
                return False
        except TypeError:
            return False

    return True


def _is_session_active(snapshot: MarketSnapshot) -> bool:
    """
    Checks if the market is inside one of our allowed trading sessions.
    """

    if snapshot.session is None:
        return False

    if snapshot.session.primary_session == "Off Session":
        return False

    return True


def check_market_conditions(snapshot: MarketSnapshot) -> MarketConditionState:
    """
    Main market safety filter.

    This function decides whether the system is allowed to continue
    toward AI analysis and trading logic.
    """

    reasons = []

    price_valid = _is_price_valid(snapshot.price)
    candles_loaded = _are_candles_loaded(snapshot.candles)
    session_active = _is_session_active(snapshot)

    try:
        spread_safe = is_spread_safe(snapshot.symbol, MAX_SPREAD)
    except Exception as error:
        spread_safe = False
        reasons.append(f"Spread check failed: {error}")

    if not price_valid:
        reasons.append("Price data is invalid.")

    if not candles_loaded:
        reasons.append("Candles are missing or empty.")

    if not spread_safe:
        reasons.append("Spread is too high.")

    if not session_active:
        reasons.append("No active trading session.")

    trade_allowed = (
        price_valid
        and candles_loaded
        and spread_safe
        and session_active
    )

    if trade_allowed:
        reasons.append("Market conditions are safe.")

    return MarketConditionState(
        price_valid=price_valid,
        candles_loaded=candles_loaded,
        spread_safe=spread_safe,
        session_active=session_active,
        trade_allowed=trade_allowed,
        reasons=reasons,
    )