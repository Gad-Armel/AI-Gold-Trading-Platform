from __future__ import annotations

"""Shared console dashboard for Gold Advisor V1 and V2."""

from datetime import datetime, timezone


def _local_datetime(value: object) -> datetime:
    """Convert an advisory ISO timestamp to the computer's local timezone."""
    parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone()


def _utc_offset_label(value: datetime) -> str:
    offset = value.utcoffset()
    if offset is None:
        return "LOCAL"
    total_minutes = int(offset.total_seconds() // 60)
    sign = "+" if total_minutes >= 0 else "-"
    hours, minutes = divmod(abs(total_minutes), 60)
    return f"UTC{sign}{hours:02d}:{minutes:02d}"


def print_gold_advisory(report: dict) -> None:
    width = 118
    overall = str(report["overall"])
    instruction = "BUY SETUP AVAILABLE" if overall == "BUY" else "SELL SETUP AVAILABLE" if overall == "SELL" else "WAIT - NO ENTRY"
    title = str(report.get("advisor_name", "GOLD MARKET ADVISOR"))
    print("\n" + "=" * width)
    print(title.center(width))
    print("=" * width)
    analyzed_at = _local_datetime(report["generated_at"])
    analyzed_clock = analyzed_at.strftime("%H:%M:%S")
    timezone_label = _utc_offset_label(analyzed_at)
    print(f"Analysis completed (local, {timezone_label}) : {analyzed_at.strftime('%Y-%m-%d %H:%M:%S')}")
    source = report.get("data_source")
    if source:
        print(f"Data source              : {source}")
    if report.get("reference_price_only"):
        print(f"Market     : {report['symbol']} | API reference {report['mid']:.2f} | Spread N/A | Session {report['session']}")
    else:
        print(f"Market     : {report['symbol']} | Bid {report['bid']:.2f} | Ask {report['ask']:.2f} | Spread ${report['spread']:.2f} | Session {report['session']}")
    print(f"DECISION   : {instruction}")
    print("-" * width)
    print(f"{'HORIZON':<12}{'ACTION':<12}{'BIAS':<10}{'EVIDENCE':<14}{'VALID FOR':<12}{'VALID WINDOW (LOCAL)':<25}{'NEXT REVIEW (LOCAL)'}")
    print("-" * width)
    for name in ("SCALP", "INTRADAY", "SWING"):
        item = report["horizons"][name]
        review = _local_datetime(item["review_at"]).strftime("%H:%M:%S")
        expires = _local_datetime(item["valid_until"]).strftime("%H:%M:%S")
        print(f"{name:<12}{item['action']:<12}{item['bias']:<10}{item['directional_score']:>6.1f}/100   {str(item['valid_for_minutes']) + ' min':<12}{analyzed_clock + ' -> ' + expires:<25}{review}")
    actionable = [(name, report["horizons"][name]) for name in ("SCALP", "INTRADAY", "SWING") if report["horizons"][name]["action"] in {"BUY", "SELL"}]
    if actionable:
        print("-" * width)
        print("ACTIONABLE LEVELS")
        for name, item in actionable:
            levels = item["levels"]
            zone = levels["entry_zone"]
            expires = _local_datetime(item["valid_until"]).strftime("%Y-%m-%d %H:%M:%S")
            print(f"\n{name} {item['action']} (expires {expires} local, {timezone_label})")
            print(f"  Entry zone : {zone[0]:.2f} - {zone[1]:.2f}")
            print(f"  Stop loss  : {levels['sl']:.2f}")
            print(f"  Targets    : TP1 {levels['tp1']:.2f} | TP2 {levels['tp2']:.2f} | TP3 {levels['tp3']:.2f}")
    else:
        shared_blocks: list[str] = []
        for name in ("SCALP", "INTRADAY", "SWING"):
            for reason in report["horizons"][name]["blocks"]:
                if reason not in shared_blocks:
                    shared_blocks.append(reason)
        print("-" * width)
        print("WHY THERE IS NO ENTRY")
        for reason in shared_blocks:
            print(f"  - {reason}")
        biases = {report["horizons"][name]["bias"] for name in ("SCALP", "INTRADAY", "SWING")}
        if len(biases) == 1 and "WAIT" not in biases:
            print(f"\n  Trend bias is {next(iter(biases))}, but entry conditions are unsafe. Do not chase the move.")
    print("-" * width)
    print("After the VALID WINDOW expiry, the position advisory is no longer valid and must be recalculated.")
    print("Evidence is directional strength, not a calibrated win probability. No order is sent.")
    print("=" * width)
