import time
from datetime import datetime, timezone

from models.market_state import MarketState
from services.market_data.price_service import get_current_price


def watch_market(symbol: str, seconds: int = 30) -> MarketState | None:
    print(f"Watching {symbol} for {seconds} seconds...\n")
    start_time = time.time()
    latest_state: MarketState | None = None

    while time.time() - start_time < seconds:
        price = get_current_price(symbol)
        if price is None:
            print("Could not read price")
        else:
            latest_state = MarketState(
                symbol=str(price.get("symbol", symbol)),
                price=price,
                candles={},
                last_update=datetime.now(timezone.utc),
                session=None,
            )
            print(latest_state)
        time.sleep(1)

    return latest_state
