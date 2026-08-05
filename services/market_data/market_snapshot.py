from datetime import datetime, timezone

from models.market_state import MarketSnapshot
from services.market_data.price_service import get_current_price
from services.market_data.candle_service import get_candles
from services.market_data.session_service import detect_market_session

def get_market_snapshot(symbol: str) -> MarketSnapshot:
    """
    Builds a complete market snapshot for the selected symbol.

    Includes:
    - current price
    - candles from multiple timeframes
    - current trading session
    """

    price = get_current_price(symbol)

    candles = {
        "M1": get_candles(symbol, "M1", 100),
        "M5": get_candles(symbol, "M5", 100),
        "M15": get_candles(symbol, "M15", 100),
        "H1": get_candles(symbol, "H1", 100),
    }

    current_time = datetime.now(timezone.utc)
    session = detect_market_session(current_time)

    return MarketSnapshot(
        symbol=symbol,
        price=price,
        candles=candles,
        last_update=current_time,
        session=session,
        
    )