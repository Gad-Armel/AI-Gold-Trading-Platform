from __future__ import annotations

"""Read-only end-to-end health check for both advisors and their consensus."""

import json

import MetaTrader5 as mt5

from config import gold_consensus_settings as settings
from config.free_data_settings import HTTP_TIMEOUT_SECONDS, TWELVE_DATA_API_KEY
from services.execution.mt5_connector import connect_mt5, disconnect_mt5
from services.market_data.scalping_snapshot import get_scalping_snapshot
from services.market_data.twelve_data_gold import TwelveDataError, fetch_twelve_data_snapshot
from services.research.gold_advisory import build_gold_advisory
from services.research.gold_advisory_consensus import build_gold_advisory_consensus
from services.research.gold_advisory_v2 import build_gold_advisory_v2
from services.research.gold_advisory_v3 import build_gold_advisory_v3


def main() -> int:
    if not TWELVE_DATA_API_KEY:
        print("BLOCKED: TWELVE_DATA_API_KEY is missing from .env.")
        return 1
    if not connect_mt5():
        return 1
    try:
        mt5_report = build_gold_advisory(get_scalping_snapshot(settings.SYMBOL))
        tick_report = build_gold_advisory_v3(mt5, settings.SYMBOL)
        api_report = build_gold_advisory_v2(
            fetch_twelve_data_snapshot(TWELVE_DATA_API_KEY, timeout=HTTP_TIMEOUT_SECONDS)
        )
        consensus = build_gold_advisory_consensus(
            mt5_report,
            api_report,
            tick_report,
            minimum_evidence=settings.MINIMUM_EVIDENCE,
            minimum_individual_evidence=settings.MINIMUM_INDIVIDUAL_EVIDENCE,
            lone_direction_evidence=settings.LONE_DIRECTION_EVIDENCE,
            maximum_mt5_age_seconds=settings.MT5_MAX_AGE_SECONDS,
            maximum_api_age_seconds=settings.API_MAX_AGE_SECONDS,
            maximum_tick_age_seconds=settings.V3_MAX_AGE_SECONDS,
            maximum_api_bar_age_seconds=settings.API_MAX_BAR_AGE_SECONDS,
            maximum_feed_price_difference_usd=settings.MAX_FEED_PRICE_DIFFERENCE_USD,
        )
        account = mt5.account_info()
        hedging_mode = int(getattr(mt5, "ACCOUNT_MARGIN_MODE_RETAIL_HEDGING", 2))
        summary = {
            "status": "PASS",
            "orders_sent": False,
            "account": {
                "trade_mode": getattr(account, "trade_mode", None),
                "margin_mode": getattr(account, "margin_mode", None),
                "hedging_required": hedging_mode,
                "hedging": account is not None and int(getattr(account, "margin_mode", -1)) == hedging_mode,
            },
            "mt5_advisor": {
                "generated_at": mt5_report.get("generated_at"),
                "overall": mt5_report.get("overall"),
            },
            "api_advisor": {
                "generated_at": api_report.get("generated_at"),
                "overall": api_report.get("overall"),
                "data_source": api_report.get("data_source"),
            },
            "tick_advisor_v3": {
                "generated_at": tick_report.get("generated_at"),
                "overall": tick_report.get("overall"),
                "tick_count": tick_report.get("tick_count"),
                "latest_tick_age_seconds": tick_report.get("latest_tick_age_seconds"),
                "market_depth_available": bool(tick_report.get("market_depth", {}).get("available")),
                "data_source": tick_report.get("data_source"),
            },
            "consensus": {
                "direction": consensus.get("direction"),
                "allowed": consensus.get("allowed"),
                "evidence": consensus.get("evidence"),
                "blocks": consensus.get("blocks", []),
            },
        }
        print(json.dumps(summary, indent=2))
        return 0
    except TwelveDataError as error:
        print(json.dumps({
            "status": "PARTIAL", "orders_sent": False,
            "twelve_data_error": str(error),
            "tick_advisor_v3": {
                "generated_at": tick_report.get("generated_at") if "tick_report" in locals() else None,
                "overall": tick_report.get("overall") if "tick_report" in locals() else None,
                "tick_count": tick_report.get("tick_count") if "tick_report" in locals() else None,
                "latest_tick_age_seconds": tick_report.get("latest_tick_age_seconds") if "tick_report" in locals() else None,
                "market_depth": tick_report.get("market_depth") if "tick_report" in locals() else None,
            },
        }, indent=2))
        return 1
    except Exception as error:
        print(f"BLOCKED: consensus health check failed: {type(error).__name__}: {error}")
        return 1
    finally:
        disconnect_mt5()


if __name__ == "__main__":
    raise SystemExit(main())
