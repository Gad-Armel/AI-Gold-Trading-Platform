from __future__ import annotations

"""Dominant-bias consensus for Gold Advisors V1, V2 and V3."""

from datetime import datetime, timezone
import math
from typing import Any


HORIZONS = ("SCALP", "INTRADAY", "SWING")
DIRECTIONS = {"BUY", "SELL"}
ADVISORS = ("MT5_CANDLES", "API_CANDLES", "MT5_TICK_FLOW")


def _utc(value: Any) -> datetime:
    parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _score(value: Any) -> float:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return 0.0
    if not math.isfinite(parsed):
        return 0.0
    return min(100.0, max(0.0, parsed))


def _current_api_bar_age(report: dict[str, Any], checked_at: datetime) -> tuple[float, str]:
    """Age the underlying candle, not just the in-memory report envelope."""
    if report.get('source_bar_time') is not None:
        age=(checked_at-_utc(report['source_bar_time'])).total_seconds()
        if age < -30:
            raise ValueError('API candle timestamp is in the future')
        return max(0.,age),'SOURCE_BAR_TIMESTAMP'
    # Legacy reports only recorded age at generation. Advance that age on
    # every assessment without mutating the provider's cached report.
    age=float(report['source_bar_age_seconds'])
    if not math.isfinite(age) or age<0:
        raise ValueError('Invalid recorded API candle age')
    elapsed=max(0.,(checked_at-_utc(report['generated_at'])).total_seconds())
    return age+elapsed,'REPORT_AGE_PLUS_BAR_AGE'


def build_gold_advisory_consensus(
    mt5_report: dict[str, Any],
    api_report: dict[str, Any],
    tick_report: dict[str, Any],
    *,
    minimum_evidence: float = 85.0,
    minimum_individual_evidence: float = 75.0,
    lone_direction_evidence: float = 90.0,
    now: datetime | None = None,
    maximum_mt5_age_seconds: float = 45.0,
    maximum_api_age_seconds: float = 90.0,
    maximum_tick_age_seconds: float = 10.0,
    maximum_api_bar_age_seconds: float = 180.0,
    maximum_feed_price_difference_usd: float = 5.0,
) -> dict[str, Any]:
    """Confirm horizons from BIAS and evidence; ACTION is display-only.

    Two or three WAIT biases block a horizon. One WAIT bias is neutral when the
    other two biases agree. Otherwise a 2-of-3 BUY/SELL bias with adequate
    supporting evidence confirms the horizon. Two matching confirmed horizons
    determine the final direction. Advisor spread/action blocks do not vote.
    """
    checked_at = _utc(now or datetime.now(timezone.utc))
    reports = dict(zip(ADVISORS, (mt5_report, api_report, tick_report)))
    maximum_ages = {
        "MT5_CANDLES": float(maximum_mt5_age_seconds),
        "API_CANDLES": float(maximum_api_age_seconds),
        "MT5_TICK_FLOW": float(maximum_tick_age_seconds),
    }
    source_checks: dict[str, Any] = {}
    source_blocks: dict[str, list[str]] = {name: [] for name in ADVISORS}
    hard_blocks: list[str] = []
    def block_source(name: str, reason: str) -> None:
        source_blocks[name].append(reason)
        hard_blocks.append(reason)

    for name, report in reports.items():
        if report.get("available") is False:
            block_source(name, f"{name} is unavailable: {report.get('error', 'provider failure')}")
        try:
            generated_at = _utc(report["generated_at"])
            raw_age = (checked_at - generated_at).total_seconds()
            age, future_skew = max(0.0, raw_age), max(0.0, -raw_age)
            fresh = age <= maximum_ages[name] and future_skew <= 30.0
            source_checks[name] = {
                "generated_at": generated_at.isoformat(), "age_seconds": round(age, 3),
                "maximum_age_seconds": maximum_ages[name], "future_skew_seconds": round(future_skew, 3),
                "fresh": fresh,
            }
            if future_skew > 30.0:
                block_source(name, f"{name} timestamp is {future_skew:.1f}s in the future.")
            elif not fresh:
                block_source(name, f"{name} is stale ({age:.1f}s > {maximum_ages[name]:.1f}s).")
        except (KeyError, TypeError, ValueError) as error:
            source_checks[name] = {"fresh": False, "error": str(error)}
            block_source(name, f"{name} timestamp is missing or invalid.")

    try:
        api_bar_age,api_bar_age_basis = _current_api_bar_age(api_report,checked_at)
        if not math.isfinite(api_bar_age) or api_bar_age < 0:
            raise ValueError("invalid bar age")
    except (KeyError, TypeError, ValueError):
        api_bar_age = None
        api_bar_age_basis = 'INVALID_BAR_TIME'
    source_checks.setdefault('API_CANDLES',{}).update(
        bar_age_seconds=round(api_bar_age,3) if api_bar_age is not None else None,
        bar_age_basis=api_bar_age_basis,maximum_bar_age_seconds=float(maximum_api_bar_age_seconds),
        bar_fresh=api_bar_age is not None and api_bar_age<=float(maximum_api_bar_age_seconds))
    if api_bar_age is None:
        block_source("API_CANDLES", "API_CANDLES latest M1 bar age is unavailable.")
    elif api_bar_age > float(maximum_api_bar_age_seconds):
        block_source("API_CANDLES", f"API_CANDLES latest M1 bar is stale ({api_bar_age:.1f}s > {maximum_api_bar_age_seconds:.1f}s).")

    try:
        mt5_mid = (float(mt5_report["bid"]) + float(mt5_report["ask"])) / 2.0
        api_mid = float(api_report["mid"])
        tick_mid = float(tick_report["mid"])
        price_difference = abs(mt5_mid - api_mid)
        if not all(math.isfinite(value) and value > 0 for value in (mt5_mid, api_mid, tick_mid)):
            raise ValueError("invalid reference price")
        if price_difference > float(maximum_feed_price_difference_usd):
            block_source("API_CANDLES", f"Feed price difference ${price_difference:.2f} exceeds ${maximum_feed_price_difference_usd:.2f}.")
        if abs(mt5_mid - tick_mid) > 1.0:
            reason = "V1 and V3 MT5 reference prices are unexpectedly inconsistent."
            block_source("MT5_CANDLES", reason)
            source_blocks["MT5_TICK_FLOW"].append(reason)
    except (KeyError, TypeError, ValueError):
        mt5_mid = api_mid = tick_mid = price_difference = None
        hard_blocks.append("Cross-feed reference prices are missing or invalid.")

    horizon_results: dict[str, Any] = {}
    for horizon in HORIZONS:
        entries: dict[str, dict[str, Any]] = {}
        for advisor, report in reports.items():
            item = dict(report.get("horizons", {}).get(horizon, {}) or {})
            entries[advisor] = {
                "action": str(item.get("action", "WAIT")).upper(),
                "bias": str(item.get("bias", "WAIT")).upper() if str(item.get("bias", "WAIT")).upper() in DIRECTIONS else "WAIT",
                "evidence": _score(item.get("directional_score", 0.0)),
                "blocks": list(item.get("blocks", []) or []),
                "valid_until": item.get("valid_until"),
                "levels": dict(item.get("levels", {}) or {}),
                "source_usable": (bool(source_checks.get(advisor, {}).get("fresh", False))
                                  and item.get('source_usable', True)
                                  and not source_blocks.get(advisor)),
            }
        waits = [name for name, item in entries.items() if item["bias"] == "WAIT"]
        notes: list[str] = []
        for advisor, item in entries.items():
            try:
                if checked_at > _utc(item["valid_until"]):
                    reason=f"{advisor} validity window expired."
                    notes.append(reason)
                    item['source_usable']=False
                    item['validity_reason']=reason
            except (TypeError, ValueError):
                reason=f"{advisor} validity timestamp is missing or invalid."
                notes.append(reason)
                item['source_usable']=False
                item['validity_reason']=reason

        bias_counts = {
            direction: sum(item["bias"] == direction for item in entries.values())
            for direction in DIRECTIONS
        }
        dominant = "BUY" if bias_counts["BUY"] > bias_counts["SELL"] else "SELL" if bias_counts["SELL"] > bias_counts["BUY"] else "WAIT"
        supporters = [item for item in entries.values() if item["bias"] == dominant] if dominant in DIRECTIONS else []
        supporting_scores = [float(item["evidence"]) for item in supporters]
        average = round(sum(supporting_scores) / len(supporting_scores), 2) if supporting_scores else 0.0
        confirmed = False

        if notes:
            pass
        elif len(waits) >= 2:
            notes.append(f"{len(waits)}/3 advisor biases are WAIT; WAIT is effective for this horizon.")
        else:
            if dominant not in DIRECTIONS or bias_counts[dominant] < 2:
                notes.append("No 2-of-3 dominant directional bias.")
            elif average < float(minimum_evidence):
                notes.append(f"Dominant-bias evidence {average:.1f}/100 is below {minimum_evidence:.1f}/100.")
            elif supporting_scores and min(supporting_scores) < float(minimum_individual_evidence):
                notes.append(f"A dominant-bias supporter is below {minimum_individual_evidence:.1f}/100.")
            else:
                confirmed = True
                if waits:
                    notes.append("One WAIT bias treated as neutral; the two matching biases dominate.")
                else:
                    notes.append("Directional bias wins by advisor majority.")

        level_sources = [
            item["levels"] for item in entries.values()
            if dominant in {"BUY", "SELL"} and item["bias"] == dominant and item["levels"]
        ]
        suggested_levels: dict[str, Any] = {}
        if level_sources:
            for key in ("sl", "tp1", "tp2", "tp3"):
                values = [float(level[key]) for level in level_sources if key in level]
                if values and all(math.isfinite(value) for value in values):
                    suggested_levels[key] = round(sum(values) / len(values), 3)
            zones = [level["entry_zone"] for level in level_sources if len(level.get("entry_zone", [])) == 2]
            if zones:
                suggested_levels["entry_zone"] = [
                    round(sum(float(zone[index]) for zone in zones) / len(zones), 3) for index in (0, 1)
                ]
        valid_times = []
        for item in entries.values():
            if item["bias"] == dominant:
                try:
                    valid_times.append(_utc(item["valid_until"]))
                except (TypeError, ValueError):
                    pass
        consensus_valid_until = min(valid_times).isoformat() if dominant in {"BUY", "SELL"} and valid_times else None

        horizon_results[horizon] = {
            "direction": dominant if confirmed else "WAIT", "confirmed": confirmed,
            "dominant_bias": dominant,
            "average_evidence": round(average, 2), "wait_count": len(waits),
            "bias_votes": bias_counts, "advisors": entries, "notes": notes,
            "suggested_levels": suggested_levels, "valid_until": consensus_valid_until,
            # Compatibility fields retained for the existing dashboard while it migrates to three columns.
            "mt5": entries["MT5_CANDLES"], "api": entries["API_CANDLES"], "v3": entries["MT5_TICK_FLOW"],
        }

    confirmed = [horizon_results[name] for name in HORIZONS if horizon_results[name]["confirmed"]]
    buy_horizons = [item for item in confirmed if item["direction"] == "BUY"]
    sell_horizons = [item for item in confirmed if item["direction"] == "SELL"]
    dominant_direction = "BUY" if len(buy_horizons) >= 2 and len(buy_horizons) > len(sell_horizons) else "SELL" if len(sell_horizons) >= 2 and len(sell_horizons) > len(buy_horizons) else "WAIT"
    direction = "WAIT" if hard_blocks else dominant_direction
    winners = buy_horizons if dominant_direction == "BUY" else sell_horizons if dominant_direction == "SELL" else []
    evidence = round(sum(float(item["average_evidence"]) for item in winners) / len(winners), 2) if winners else 0.0
    final_blocks = list(hard_blocks)
    if direction == "WAIT":
        final_blocks.append("No direction dominates at least 2 of the 3 horizons.")

    allowed = direction in DIRECTIONS and not hard_blocks
    return {
        "generated_at": checked_at.isoformat(), "action": direction, "direction": direction,
        "allowed": allowed, "evidence": evidence, "minimum_evidence": float(minimum_evidence),
        "minimum_individual_evidence": float(minimum_individual_evidence),
        "lone_direction_evidence": float(lone_direction_evidence), "horizons": horizon_results,
        "sources": source_checks, "source_blocks": source_blocks,
        "data_blocks": list(hard_blocks), "feed_prices": {"mt5_mid": mt5_mid, "api_mid": api_mid,
        "v3_mid": tick_mid, "difference_usd": price_difference}, "blocks": final_blocks,
        "reason": (
            f"{direction} bias dominates at least two horizons across Advisors V1, V2 and V3."
            if allowed else "Three-advisor dominant-bias confirmation is incomplete."
        ),
    }
