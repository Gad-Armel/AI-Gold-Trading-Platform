from config.settings import SYMBOL

from services.execution.mt5_connector import get_account_info
from services.market_data.price_service import get_current_price
from services.market_data.candle_service import get_candles


def _get(obj, key, default=None):
    if obj is None:
        return default

    if isinstance(obj, dict):
        return obj.get(key, default)

    return getattr(obj, key, default)


def _check_account():
    try:
        account = get_account_info()

        if account is None:
            return False, "MT5 account info not available."

        login = _get(account, "login")
        balance = _get(account, "balance")

        return True, f"MT5 account connected. Login={login}, Balance={balance}"

    except Exception as error:
        return False, f"MT5 account check failed: {error}"


def _check_price(symbol):
    try:
        price = get_current_price(symbol)

        if price is None:
            return False, f"No price returned for {symbol}."

        bid = _get(price, "bid")
        ask = _get(price, "ask")

        if bid is None or ask is None:
            return False, f"Invalid price data for {symbol}: {price}"

        return True, f"Price feed OK for {symbol}. Bid={bid}, Ask={ask}"

    except Exception as error:
        return False, f"Price check failed for {symbol}: {error}"


def _check_candles(symbol):
    try:
        candles = get_candles(symbol, timeframe_name="M1", count=50)

        if candles is None:
            return False, f"No candles returned for {symbol}."

        if len(candles) < 20:
            return False, f"Not enough M1 candles for {symbol}. Count={len(candles)}"

        return True, f"Candles OK for {symbol}. M1 count={len(candles)}"

    except Exception as error:
        return False, f"Candle check failed for {symbol}: {error}"


def run_health_check(symbol=SYMBOL):
    checks = []

    account_ok, account_message = _check_account()
    checks.append(("MT5 Account", account_ok, account_message))

    price_ok, price_message = _check_price(symbol)
    checks.append(("Price Feed", price_ok, price_message))

    candles_ok, candles_message = _check_candles(symbol)
    checks.append(("Candles", candles_ok, candles_message))

    passed = all(check[1] for check in checks)

    return {
        "passed": passed,
        "checks": checks,
    }


def print_health_check_report(symbol=SYMBOL):
    result = run_health_check(symbol)

    print("")
    print("=" * 70)
    print("BOT HEALTH CHECK REPORT")
    print("=" * 70)

    for name, passed, message in result["checks"]:
        status = "PASS" if passed else "FAIL"
        print(f"{name}: {status}")
        print(f"  {message}")

    print("-" * 70)

    if result["passed"]:
        print("Health Status: PASSED")
    else:
        print("Health Status: FAILED")

    print("=" * 70)
    print("")

    return result