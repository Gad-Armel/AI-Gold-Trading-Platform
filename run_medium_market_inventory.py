from __future__ import annotations

"""Inventory broker symbols relevant to XAUUSD medium-horizon research."""

import json

import MetaTrader5 as mt5

from services.execution.mt5_connector import connect_mt5, disconnect_mt5


QUERIES = (
    "DXY", "USDX", "USDINDEX", "US10Y", "UST10Y", "TNOTE", "VIX",
    "XAGUSD", "EURUSD", "GBPUSD", "USDJPY", "USDCHF",
    "US500", "SPX500", "SP500", "USTEC", "NAS100",
    "USOIL", "WTI", "BRENT",
)


def main() -> int:
    if not connect_mt5():
        return 1
    try:
        result = {}
        for query in QUERIES:
            matches = mt5.symbols_get(group=f"*{query}*") or ()
            rows = []
            for item in matches:
                name = str(getattr(item, "name", "") or "")
                if not name:
                    continue
                mt5.symbol_select(name, True)
                rates = mt5.copy_rates_from_pos(name, mt5.TIMEFRAME_H1, 0, 5)
                tick = mt5.symbol_info_tick(name)
                rows.append({
                    "name": name,
                    "description": str(getattr(item, "description", "") or ""),
                    "path": str(getattr(item, "path", "") or ""),
                    "currency_base": str(getattr(item, "currency_base", "") or ""),
                    "currency_profit": str(getattr(item, "currency_profit", "") or ""),
                    "h1_bars_available": int(len(rates)) if rates is not None else 0,
                    "positive_quote": bool(
                        tick is not None
                        and max(float(getattr(tick, "bid", 0.0) or 0.0), float(getattr(tick, "last", 0.0) or 0.0)) > 0
                    ),
                })
            result[query] = rows
        print(json.dumps(result, indent=2))
        return 0
    finally:
        disconnect_mt5()


if __name__ == "__main__":
    raise SystemExit(main())
