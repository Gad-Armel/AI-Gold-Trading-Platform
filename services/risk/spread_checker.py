from services.market_data.price_service import get_current_price


def is_spread_safe(symbol, max_spread):

    price = get_current_price(symbol)

    if price is None:
        return False

    if price["spread"] <= max_spread:
        return True

    return False