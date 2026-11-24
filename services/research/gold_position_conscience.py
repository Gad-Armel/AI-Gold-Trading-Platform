"""Continuous "am I still right?" scoring for an OPEN position.

Every resource the bot collects -- consensus advisors, completed-candle
structure, executable quote flow, dollar transmission, the learned forecast,
the economic advisor and the news calendar -- already votes on whether to
*enter*. Nothing re-asked the question once a position existed, so a trade held
its original thesis until a money stop or a single specialised detector fired.

This module asks it on every cycle. Each source votes in [-1, +1] relative to
the direction actually held, weighted, and only when that source is genuinely
usable. The result is a conviction in [0, 1] plus the coverage it was computed
from, so thin evidence is never mistaken for confidence.

Deliberate limits, consistent with the project's safety posture:

* Advisory over EXITS only. It never authorizes an entry, never resizes a
  position and never moves or removes a broker stop.
* It may tighten protection at any coverage. It may widen protection only when
  coverage is good, and only inside the configured scale cap.
* Scores are heuristic strengths, not calibrated probabilities.
"""
from __future__ import annotations

import math
from typing import Any

from config import gold_consensus_settings as settings

DIRECTIONS = {"BUY", "SELL"}


def _finite(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _clamp(value: float, low: float = -1.0, high: float = 1.0) -> float:
    return max(low, min(high, value))


def _consensus_vote(decision: dict[str, Any], direction: str) -> tuple[float, str] | None:
    """Agreement of the live advisor consensus with the direction held.

    Scaled between the lane's exit threshold and its entry threshold so the
    vote reads as "how far is this from the bar that authorized it", not as an
    absolute evidence number whose meaning differs per lane.
    """
    dominant = str(decision.get("dominant_bias", "WAIT")).upper()
    evidence = _finite(decision.get("evidence"))
    if evidence is None:
        return None
    exit_threshold = _finite(decision.get("exit_threshold")) or 0.0
    entry_threshold = _finite(decision.get("entry_threshold")) or 100.0
    # A permissive entry floor is not maximum conviction. In continuous mode
    # both thresholds are 15; dividing by their zero span saturated every
    # score above 15 to full support and widened trailing giveback incorrectly.
    if decision.get('continuous_directional_entries'):
        entry_threshold = 100.0
    span = max(1e-9, entry_threshold - exit_threshold)
    strength = _clamp((evidence - exit_threshold) / span, 0.0, 1.0)
    if dominant not in DIRECTIONS:
        # No directional read at all: mildly negative, the thesis is unconfirmed.
        return -0.25, f"Consensus has no directional bias (evidence {evidence:.1f})."
    if dominant == direction:
        return strength, f"Consensus still reads {dominant} at {evidence:.1f}/100."
    return -strength, f"Consensus has turned to {dominant} at {evidence:.1f}/100."


def _structure_vote(context: dict[str, Any], direction: str) -> tuple[float, str] | None:
    """Completed-candle trend and momentum, normalised by ATR upstream."""
    if not context.get("available"):
        return None
    trend = _finite(context.get("trend"))
    momentum = _finite(context.get("momentum"))
    if trend is None or momentum is None:
        return None
    sign = 1.0 if direction == "BUY" else -1.0
    # trend and momentum are already ATR-normalised; 1.0 ATR is a full vote.
    vote = _clamp(0.6 * _clamp(sign * trend) + 0.4 * _clamp(sign * momentum))
    close = _finite(context.get("close"))
    previous_low = _finite(context.get("previous_low"))
    previous_high = _finite(context.get("previous_high"))
    broken = False
    if close is not None and previous_low is not None and previous_high is not None:
        broken = close < previous_low if direction == "BUY" else close > previous_high
    if broken:
        vote = min(vote, -0.5)
    detail = f"Structure trend {sign * trend:+.2f} ATR, momentum {sign * momentum:+.2f} ATR"
    return vote, detail + (" with the prior swing broken against the trade." if broken else ".")


def _flow_vote(flow: dict[str, Any], direction: str) -> tuple[float, str] | None:
    """Executable quote flow: the only source that sees between candles."""
    if not flow or flow.get("close") is None:
        return None
    move = _finite(flow.get("move"))
    threshold = _finite(flow.get("threshold"))
    if move is None or threshold is None or threshold <= 0:
        return None
    if flow.get("close"):
        return -1.0, "Quote flow has confirmed a sustained reversal."
    peak = _finite(flow.get("peak_move"))
    vote = _clamp(move / (2.0 * threshold))
    if peak is not None and peak > threshold:
        giveback = (peak - move) / max(1e-9, peak)
        # Surrendering most of the best price is adverse even while still green.
        vote = min(vote, _clamp(1.0 - 2.0 * giveback))
    return vote, f"Quote flow move {move:+.2f} against a {threshold:.2f} threshold."


def _cross_market_vote(cross: dict[str, Any], direction: str) -> tuple[float, str] | None:
    if not cross or not cross.get("available"):
        return None
    bias = str(cross.get("gold_bias", "NEUTRAL")).upper()
    if bias not in DIRECTIONS:
        return 0.0, "Dollar transmission is neutral."
    pressure = abs(_finite(cross.get("dollar_pressure_z")) or 0.0)
    strength = _clamp(pressure / 2.0, 0.0, 1.0)
    if bias == direction:
        return strength, f"Dollar transmission agrees ({bias}, z {pressure:.2f})."
    return -strength, f"Dollar transmission contradicts the trade ({bias}, z {pressure:.2f})."


def _learned_vote(learned: dict[str, Any], direction: str) -> tuple[float, str] | None:
    if not learned or not learned.get("available"):
        return None
    continuation = dict(learned.get("continuation_usd", {}) or {})
    value = _finite(continuation.get(direction))
    if value is None:
        return None
    minimum = abs(_finite(learned.get("minimum_edge_usd")) or 0.2) or 0.2
    return _clamp(value / (2.0 * minimum)), f"Learned continuation forecast {value:+.2f} USD."


def _economic_vote(economic: dict[str, Any], direction: str) -> tuple[float, str] | None:
    """Slow macro context. Low weight and never decisive on its own."""
    if not economic:
        return None
    bias = str(economic.get("bias", "NEUTRAL")).upper()
    quality = _finite(economic.get("quality"))
    score = _finite(economic.get("score"))
    if quality is None or score is None or quality <= 0.0:
        return None
    strength = _clamp(abs(score) * quality, 0.0, 1.0)
    if bias not in DIRECTIONS:
        return 0.0, "Economic context is neutral."
    if bias == direction:
        return strength, f"Economic context confirms {bias} (quality {quality:.2f})."
    return -strength, f"Economic context opposes the trade ({bias}, quality {quality:.2f})."


def _micro_flow_vote(flow: dict[str, Any], direction: str) -> tuple[float, str] | None:
    """Graded live flow, the fastest source available between candles."""
    if not flow or not flow.get("available"):
        return None
    pressure = _finite(flow.get("pressure"))
    if pressure is None:
        return None
    sign = 1.0 if direction == "BUY" else -1.0
    vote = _clamp(sign * pressure)
    risk = _finite(flow.get("reversal_risk"))
    if risk is not None:
        vote = min(vote, 1.0-2.0*risk)
    # Absence of a reversal is not evidence supporting continuation.
    return vote, f"Live flow pressure {sign * pressure:+.2f}; adverse risk {risk}."


def _regime_vote(context: dict[str, Any], direction: str) -> tuple[float, str] | None:
    """Regime is about whether this is a sane moment to hold, not direction.

    Volatility expansion is scored negative for everyone: spreads widen and
    stops are reached by noise, which is a reason to bank rather than to press.
    """
    research = dict((context or {}).get("structure_research", {}) or {})
    regime = str(research.get("regime", "")).upper()
    if not context.get('available') or regime not in {'VOLATILITY_EXPANSION', 'RANGE_OR_UNCLEAR', 'TREND_UP', 'TREND_DOWN'}:
        return None
    if regime == "VOLATILITY_EXPANSION":
        return -0.6, "Volatility expansion: spreads widen and stops are reached by noise."
    if regime == "RANGE_OR_UNCLEAR":
        return -0.15, "No established regime; continuation is unsupported."
    aligned = (regime == "TREND_UP" and direction == "BUY") or (regime == "TREND_DOWN" and direction == "SELL")
    return (0.8, f"{regime} agrees with the trade.") if aligned else (-0.8, f"{regime} opposes the trade.")


def _news_vote(news_risk: dict[str, Any]) -> tuple[float, str] | None:
    if not news_risk:
        return None
    if not bool(news_risk.get("allowed", True)):
        return -1.0, "A high-impact release window is active."
    active = list(news_risk.get("active_events", []) or [])
    if active:
        return -0.3, f"{len(active)} scheduled event(s) are near."
    return 0.4, "No scheduled high-impact event is near."


def assess_position_conscience(
    *,
    direction: str,
    horizon: str,
    decision: dict[str, Any] | None = None,
    context: dict[str, Any] | None = None,
    flow: dict[str, Any] | None = None,
    cross_market: dict[str, Any] | None = None,
    learned: dict[str, Any] | None = None,
    economic: dict[str, Any] | None = None,
    news_risk: dict[str, Any] | None = None,
    micro_flow: dict[str, Any] | None = None,
    state: dict[str, Any] | None = None,
    now: float | None = None,
) -> dict[str, Any]:
    """Score how well an open position is still supported by every source.

    Returns ``conviction`` in [0, 1] (0.5 is "no net opinion"), the ``coverage``
    of usable weight it was built from, and an auditable per-source breakdown.
    """
    if str(direction).upper() not in DIRECTIONS:
        return {"available": False, "reason": "Conscience requires a held direction.",
                "policy": "CONSCIENCE_V1"}
    direction = str(direction).upper()
    weights = dict(settings.CONSCIENCE_WEIGHTS)
    votes = {
        "consensus": _consensus_vote(dict(decision or {}), direction),
        "structure": _structure_vote(dict(context or {}), direction),
        "quote_flow": _flow_vote(dict(flow or {}), direction),
        "micro_flow": _micro_flow_vote(dict(micro_flow or {}), direction),
        "regime": _regime_vote(dict(context or {}), direction),
        "cross_market": _cross_market_vote(dict(cross_market or {}), direction),
        "learned": _learned_vote(dict(learned or {}), direction),
        "economic": _economic_vote(dict(economic or {}), direction),
        "news": _news_vote(dict(news_risk or {})),
    }
    contributions: list[dict[str, Any]] = []
    weighted_sum = 0.0
    usable_weight = 0.0
    for source, weight in weights.items():
        result = votes.get(source)
        if result is None:
            contributions.append({"source": source, "weight": float(weight),
                                  "usable": False, "vote": None,
                                  "detail": "Source unavailable this cycle."})
            continue
        vote, detail = result
        vote = _clamp(float(vote))
        weighted_sum += float(weight) * vote
        usable_weight += float(weight)
        contributions.append({"source": source, "weight": float(weight), "usable": True,
                              "vote": round(vote, 4), "detail": detail})
    total_weight = sum(float(value) for value in weights.values()) or 1.0
    coverage = usable_weight / total_weight
    if usable_weight <= 0.0:
        return {"available": False, "reason": "No conscience source is usable this cycle.",
                "policy": "CONSCIENCE_V1", "coverage": 0.0, "contributions": contributions}
    raw_alignment = _clamp(weighted_sum / usable_weight)
    # Disagreement between sources is not the same as neutrality. A weighted
    # mean of +1 and -1 looks identical to two sources that both say "nothing
    # is happening", so the spread is measured and used to pull conviction
    # toward neutral rather than letting a coin-flip read as a considered one.
    mean_vote = weighted_sum / usable_weight
    variance = sum(float(item["weight"]) * (float(item["vote"]) - mean_vote) ** 2
                   for item in contributions if item["usable"]) / usable_weight
    dispersion = min(1.0, math.sqrt(max(0.0, variance)))
    alignment = _clamp(raw_alignment * (1.0 - 0.5 * dispersion))
    # Asymmetric memory: react immediately when support falls away, and require
    # persistence before treating a recovery as real. Protection should be
    # quick to arrive and slow to leave.
    smoothed = alignment
    if state is not None and now is not None:
        previous = _finite(state.get("alignment"))
        last_seen = _finite(state.get("updated_at"))
        if (previous is not None and last_seen is not None
                and state.get("direction") == direction and 0 <= now - last_seen <= 30.0):
            smoothed = alignment if alignment < previous else previous + 0.35 * (alignment - previous)
        state.update(alignment=smoothed, updated_at=float(now), direction=direction)
    conviction = (smoothed + 1.0) / 2.0
    adverse = sorted((item for item in contributions
                      if item["usable"] and float(item["vote"]) < -0.25),
                     key=lambda item: float(item["vote"]) * float(item["weight"]))
    return {
        "available": True, "policy": "CONSCIENCE_V2", "role": "EXIT_ADVISORY_ONLY",
        "horizon": str(horizon), "direction": direction,
        "conviction": round(conviction, 4), "alignment": round(smoothed, 4),
        "instant_alignment": round(raw_alignment, 4), "dispersion": round(dispersion, 4),
        "coverage": round(coverage, 4), "usable_sources": int(sum(1 for i in contributions if i["usable"])),
        "contributions": contributions,
        "leading_concerns": [item["detail"] for item in adverse[:3]],
        "calibrated_probability": None, "evidence_type": "HEURISTIC_STRENGTH",
    }


def giveback_scale(conscience: dict[str, Any]) -> float:
    """Multiplier applied to the configured giveback allowance.

    Falling conviction tightens protection immediately. Rising conviction may
    loosen it -- letting a well-supported winner breathe instead of being
    stopped out of a move that every source still agrees with -- but only on
    good coverage and only inside the configured cap.
    """
    minimum = float(settings.ADAPTIVE_GIVEBACK_MIN_SCALE)
    maximum = float(settings.ADAPTIVE_GIVEBACK_MAX_SCALE)
    if not conscience.get("available"):
        return 1.0
    alignment = _finite(conscience.get("alignment"))
    if alignment is None:
        return 1.0
    coverage = _finite(conscience.get("coverage")) or 0.0
    if alignment >= 0.0:
        if coverage < float(settings.CONSCIENCE_MIN_COVERAGE_TO_WIDEN):
            return 1.0
        return min(maximum, 1.0 + alignment * (maximum - 1.0))
    return max(minimum, 1.0 + alignment * (1.0 - minimum))


def conviction_collapse(
    conscience: dict[str, Any],
    state: dict[str, Any],
    *,
    now: float,
    profit_r: float,
    horizon: str,
    position_signature: Any,
) -> tuple[bool, str]:
    """Bank an open profit when support collapses, instead of riding to a stop.

    Requires the collapse to persist, so a single adverse tick or one briefly
    unavailable source cannot flush a position.
    """
    floor = float(settings.CONSCIENCE_EXIT_CONVICTION)
    minimum_profit = float(settings.CONSCIENCE_EXIT_MIN_PROFIT_R)
    required = float(dict(settings.CONSCIENCE_EXIT_CONFIRMATION_SECONDS).get(horizon, 20.0))
    if state.get("signature") != position_signature:
        state.clear()
        state["signature"] = position_signature
    conviction = _finite(conscience.get("conviction")) if conscience.get("available") else None
    if (conviction is None or conviction > floor or not math.isfinite(profit_r)
            or profit_r < minimum_profit):
        state["collapsed_since"] = None
        return False, ""
    if state.get("collapsed_since") is None:
        state["collapsed_since"] = now
    held = now - float(state["collapsed_since"])
    if held < required:
        return False, ""
    return True, (f"Conviction collapsed to {conviction:.2f} for {held:.0f}s while "
                  f"{profit_r:.2f}R in profit; banking the move rather than waiting for a target")
