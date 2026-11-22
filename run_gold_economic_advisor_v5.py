from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone

from services.market_data.free_macro_context import build_free_macro_context
from services.news.unified_news_intelligence import build_unified_news_context
from services.research.gold_economic_advisor_v5 import build_gold_economic_advisor_v5
from services.risk.news_event_filter import assess_news_event_risk


def main() -> int:
    parser = argparse.ArgumentParser(description="Read-only XAUUSD Economic Advisor V5")
    parser.add_argument("--session", default="London", choices=("Asian", "London", "New York"))
    parser.add_argument("--institutional", default="data/context/gold_institutional_context.json")
    parser.add_argument("--refresh-macro", action="store_true", help="Ignore the one-hour FRED cache.")
    args = parser.parse_args()
    now = datetime.now(timezone.utc)
    news_risk = assess_news_event_risk("XAUUSD", datetime.now())
    news = build_unified_news_context(args.session, news_risk, now)
    macro = build_free_macro_context(max_cache_age_seconds=0.0 if args.refresh_macro else 3600.0)
    report = build_gold_economic_advisor_v5(news, macro, institutional_path=args.institutional, now=now)
    print(json.dumps(report, indent=2, ensure_ascii=False, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
