from __future__ import annotations

from typing import Any

from config import scalping_settings
from models.scalping_state import ScalpSignalState


def _float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _normalize_direction(value: Any) -> str:
    """Map all internal market labels to BUY/SELL/NEUTRAL."""
    text = str(value or "NEUTRAL").strip().upper().replace("-", "_").replace(" ", "_")
    buy_labels = {"BUY", "BULL", "BULLISH", "LONG", "UP", "UPTREND", "RISING"}
    sell_labels = {"SELL", "BEAR", "BEARISH", "SHORT", "DOWN", "DOWNTREND", "FALLING"}
    if text in buy_labels:
        return "BUY"
    if text in sell_labels:
        return "SELL"
    return "NEUTRAL"


_SOFT_STRATEGY_PREFIXES = (
    "Regime-playbook quality gate failed:",
    "Unified score is below minimum:",
    "BUY and SELL unified scores are too close:",
    "Only ",
    "The required entry-trigger family is missing",
    "The required directional-context family is missing",
    "No breakout, pullback/reclaim, candle rejection, or structure entry trigger exists",
    "Market regime is unresolved or conflicting:",
)


def _split_signal_blocks(signal: ScalpSignalState) -> tuple[list[str], list[str]]:
    """Split strategy diagnostics from operational safety blocks.

    V5.0.5 preserves the explicit score-margin candidate while separating normal
    discretionary context from hard execution and anti-chasing protection. A
    score lead can trade without a complete V4 playbook, but cannot chase an
    extreme VWAP displacement or ignore a clearly opposite short-term tape.

    News, spread, stale/missing data, provider failures and other operational
    errors are hard blocks and can never be bypassed.
    """
    soft: list[str] = []
    hard: list[str] = []
    for reason in signal.block_reasons:
        text = str(reason).strip()
        if any(text.startswith(prefix) for prefix in _SOFT_STRATEGY_PREFIXES):
            soft.append(text)
        else:
            hard.append(text)
    return soft, hard


def _score_margin_checks(signal: ScalpSignalState, candidate: str) -> tuple[dict[str, bool], list[str]]:
    metrics = _dict(signal.metrics)
    diagnostics = _dict(metrics.get("score_diagnostics"))
    direct = _dict(diagnostics.get("direct_score_decision"))
    candidate = _normalize_direction(candidate)
    margin = _float(direct.get("margin", diagnostics.get("direction_margin", 0.0)))
    winner_score = _float(direct.get("winner_score", signal.score))

    score_runtime_enabled = bool(
        scalping_settings.SCALPING_PAPER_ONLY
        or (
            getattr(scalping_settings, "SCALPING_DEMO_EXECUTION_ENABLED", False)
            and not getattr(scalping_settings, "SCALPING_REAL_ACCOUNT_EXECUTION_ENABLED", False)
        )
    )
    checks = {
        "score_runtime_enabled": score_runtime_enabled,
        "score_winner_valid": bool(direct.get("passed", False)) and candidate in {"BUY", "SELL"},
        "score_margin": margin + 1e-9 >= float(
            scalping_settings.SCALPING_SCORE_MARGIN_ENTRY_MIN_DIFFERENCE
        ),
        "winner_score_floor": winner_score + 1e-9 >= float(
            scalping_settings.SCALPING_DIRECT_SCORE_MIN_WINNER_SCORE
        ),
    }
    failed = [name for name, passed in checks.items() if not passed]
    return checks, failed


def _advisory_context_checks(signal: ScalpSignalState, candidate: str) -> dict[str, bool]:
    """Retain V5.0.3 context checks as diagnostics, not paper entry vetoes."""
    metrics = _dict(signal.metrics)
    diagnostics = _dict(metrics.get("score_diagnostics"))
    quality = _dict(diagnostics.get("entry_quality_decision"))
    regime = _dict(metrics.get("regime"))
    structure = _dict(metrics.get("structure"))
    mtf = _dict(metrics.get("multi_timeframe_alignment"))
    verified = _dict(metrics.get("verified_context"))
    m1 = _dict(metrics.get("M1"))
    zones = _dict(metrics.get("zones"))

    candidate = _normalize_direction(candidate)
    opposite = "SELL" if candidate == "BUY" else "BUY"
    regime_direction = _normalize_direction(regime.get("direction", "NEUTRAL"))
    structure_direction = _normalize_direction(structure.get("direction", "NEUTRAL"))
    mtf_direction = _normalize_direction(mtf.get("dominant_direction", "NEUTRAL"))
    verified_trend_direction = _normalize_direction(verified.get("trend_direction", "NEUTRAL"))
    vwap = abs(_float(verified.get("vwap_distance_atr")))
    ema = abs(_float(m1.get("distance_fast_atr_ratio")))
    bad_location = (
        candidate == "BUY" and bool(zones.get("near_resistance", False))
    ) or (
        candidate == "SELL" and bool(zones.get("near_support", False))
    )

    return {
        "promotion_context_support": int(_float(quality.get("support_votes", 0)))
        >= int(scalping_settings.SCALPING_META_PROMOTION_MIN_CONTEXT_SUPPORT),
        "promotion_context_opposition": int(_float(quality.get("opposition_votes", 0)))
        <= int(scalping_settings.SCALPING_META_PROMOTION_MAX_CONTEXT_OPPOSITION),
        "promotion_regime": regime_direction in {candidate, "NEUTRAL"}
        and str(regime.get("mode", "NO_TRADE")).upper() in {"TREND", "BREAKOUT", "REVERSAL"},
        "promotion_structure": structure_direction in {candidate, "NEUTRAL"},
        "promotion_mtf": mtf_direction in {candidate, "NEUTRAL"},
        "promotion_adx": _float(verified.get("adx_m5"))
        >= float(scalping_settings.SCALPING_META_PROMOTION_MIN_ADX)
        and verified_trend_direction in {candidate, "NEUTRAL"},
        "promotion_relative_volume": _float(verified.get("relative_tick_volume"))
        >= float(scalping_settings.SCALPING_META_PROMOTION_MIN_RELATIVE_VOLUME),
        "promotion_vwap": vwap <= float(scalping_settings.SCALPING_META_PROMOTION_MAX_VWAP_ATR),
        "promotion_ema": ema <= float(scalping_settings.SCALPING_META_PROMOTION_MAX_EMA_ATR),
        "promotion_location": not bad_location,
        "promotion_no_explicit_opposite_regime": regime_direction != opposite,
    }


def _score_margin_quality_checks(
    signal: ScalpSignalState,
    candidate: str,
    micro: dict[str, Any],
) -> tuple[dict[str, bool], dict[str, Any]]:
    """Apply only the quality checks that protect score-margin paper entries.

    The five-point margin remains the candidate selector. These checks prevent
    the selector from chasing an already exhausted move or entering with almost
    no participation. They intentionally do not require a full named playbook.
    """
    metrics = _dict(signal.metrics)
    diagnostics = _dict(metrics.get("score_diagnostics"))
    direct = _dict(diagnostics.get("direct_score_decision"))
    quality = _dict(diagnostics.get("entry_quality_decision"))
    regime = _dict(metrics.get("regime"))
    structure = _dict(metrics.get("structure"))
    mtf = _dict(metrics.get("multi_timeframe_alignment"))
    trend = _dict(metrics.get("trend_confirmation"))
    verified = _dict(metrics.get("verified_context"))
    factor = _dict(metrics.get("factor_model"))
    playbook = _dict(metrics.get("playbook"))
    zones = _dict(metrics.get("zones"))

    candidate = _normalize_direction(candidate)
    opposite = "SELL" if candidate == "BUY" else "BUY"
    winner_score = _float(direct.get("winner_score", signal.score))
    score_margin = _float(direct.get("margin", diagnostics.get("direction_margin", 0.0)))
    vwap_atr = abs(_float(verified.get("vwap_distance_atr")))
    relative_volume = _float(verified.get("relative_tick_volume"))

    context_directions = {
        "regime": _normalize_direction(regime.get("direction")),
        "structure": _normalize_direction(structure.get("direction")),
        "multi_timeframe": _normalize_direction(mtf.get("dominant_direction")),
        "trend20": _normalize_direction(trend.get("trend_direction")),
        "verified_adx": _normalize_direction(verified.get("trend_direction")),
        "factor_model": _normalize_direction(factor.get("preferred_direction")),
    }
    support_sources = [name for name, direction in context_directions.items() if direction == candidate]
    opposition_sources = [name for name, direction in context_directions.items() if direction == opposite]

    trigger_directions = {
        "three_candle_confirmation": _normalize_direction(trend.get("confirmation_direction")),
        "three_closed": _normalize_direction(playbook.get("three_closed_direction")),
        "closed_pressure": _normalize_direction(playbook.get("three_closed_pressure_direction")),
        "trend_pullback": _normalize_direction(playbook.get("trend_pullback_direction")),
        "breakout_retest": _normalize_direction(playbook.get("breakout_retest_direction")),
        "range_rejection": _normalize_direction(playbook.get("range_rejection_direction")),
        "micro_break": _normalize_direction(quality.get("micro_break_direction")),
    }
    trigger_sources = [name for name, direction in trigger_directions.items() if direction == candidate]
    directional_trigger = bool(trigger_sources)

    near_bad_location = bool(
        (candidate == "BUY" and zones.get("near_resistance", False))
        or (candidate == "SELL" and zones.get("near_support", False))
    )
    extended = vwap_atr > float(scalping_settings.SCALPING_SCORE_MARGIN_EXTENDED_VWAP_ATR)
    micro_direction = _normalize_direction(micro.get("direction"))
    micro_confidence = _float(micro.get("confidence"))
    same_direction_micro = bool(
        micro_direction == candidate
        and micro_confidence + 1e-9 >= float(
            scalping_settings.SCALPING_SCORE_MARGIN_EXTENDED_MIN_MICRO_CONFIDENCE
        )
    )
    strong_micro_override = bool(
        getattr(
            scalping_settings,
            "SCALPING_SCORE_MARGIN_EXTENDED_ALLOW_STRONG_MICRO_OVERRIDE",
            False,
        )
        and micro_direction == candidate
        and micro_confidence + 1e-9
        >= float(
            getattr(
                scalping_settings,
                "SCALPING_SCORE_MARGIN_EXTENDED_OVERRIDE_MIN_MICRO_CONFIDENCE",
                1.0,
            )
        )
        and winner_score + 1e-9
        >= float(
            getattr(
                scalping_settings,
                "SCALPING_SCORE_MARGIN_EXTENDED_OVERRIDE_MIN_WINNER_SCORE",
                100.0,
            )
        )
        and score_margin + 1e-9
        >= float(
            getattr(
                scalping_settings,
                "SCALPING_SCORE_MARGIN_EXTENDED_OVERRIDE_MIN_MARGIN",
                100.0,
            )
        )
    )

    checks = {
        "score_margin_winner_quality": winner_score + 1e-9 >= float(
            scalping_settings.SCALPING_SCORE_MARGIN_MIN_WINNER_SCORE
        ),
        "score_margin_context_alignment": len(support_sources) >= int(
            scalping_settings.SCALPING_SCORE_MARGIN_MIN_CONTEXT_ALIGNMENT
        ),
        "score_margin_context_opposition": len(opposition_sources) <= int(
            scalping_settings.SCALPING_SCORE_MARGIN_MAX_CONTEXT_OPPOSITION
        ),
        "score_margin_relative_volume": relative_volume + 1e-9 >= float(
            scalping_settings.SCALPING_SCORE_MARGIN_MIN_RELATIVE_VOLUME
        ),
        "score_margin_vwap_sanity": vwap_atr <= float(
            scalping_settings.SCALPING_SCORE_MARGIN_MAX_ABS_VWAP_ATR
        ) + 1e-9,
        "score_margin_location": (not near_bad_location) or directional_trigger,
        "score_margin_extended_trigger": (
            not extended
            or not bool(scalping_settings.SCALPING_SCORE_MARGIN_EXTENDED_REQUIRE_TRIGGER)
            or directional_trigger
            or strong_micro_override
        ),
        "score_margin_extended_micro": (
            not extended
            or not bool(
                scalping_settings.SCALPING_SCORE_MARGIN_EXTENDED_REQUIRE_MICRO_CONFIRMATION
            )
            or same_direction_micro
        ),
    }
    details = {
        "winner_score": winner_score,
        "vwap_distance_atr": vwap_atr,
        "relative_volume": relative_volume,
        "extended": extended,
        "near_bad_location": near_bad_location,
        "support_sources": support_sources,
        "opposition_sources": opposition_sources,
        "trigger_sources": trigger_sources,
        "micro_direction": micro_direction,
        "micro_confidence": micro_confidence,
        "score_margin": score_margin,
        "strong_micro_override": strong_micro_override,
    }
    return checks, details


def evaluate_meta_controller(
    signal: ScalpSignalState,
    agents: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    technical = agents.get("technical", {})
    micro = agents.get("microstructure", {})
    intermarket = agents.get("intermarket", {})
    news = agents.get("news", {})
    execution = agents.get("execution", {})

    candidate = _normalize_direction(technical.get("direction", "NEUTRAL"))
    opposite = "SELL" if candidate == "BUY" else "BUY"
    block_reasons: list[str] = []
    advisory_warnings: list[str] = []
    checks: dict[str, bool] = {}

    native_allowed = bool(signal.allowed) and candidate in {"BUY", "SELL"}
    soft_blocks, hard_blocks = _split_signal_blocks(signal)
    margin_checks, margin_failed = _score_margin_checks(signal, candidate)
    quality_checks, quality_details = _score_margin_quality_checks(signal, candidate, micro)
    quality_failed = [name for name, passed in quality_checks.items() if not passed]
    score_margin_enabled = bool(
        scalping_settings.SCALPING_SCORE_MARGIN_ENTRY_ENABLED
    )
    score_margin_authorized = bool(
        score_margin_enabled
        and not native_allowed
        and not hard_blocks
        and all(margin_checks.values())
        and all(quality_checks.values())
    )

    advisory_context = _advisory_context_checks(signal, candidate)
    advisory_failed = [name for name, passed in advisory_context.items() if not passed]
    if soft_blocks:
        advisory_warnings.extend(soft_blocks)
    if advisory_failed:
        advisory_warnings.append(
            "Non-blocking score-margin context warnings: " + ", ".join(advisory_failed) + "."
        )

    checks["technical_candidate_authorized"] = native_allowed or score_margin_authorized
    if not checks["technical_candidate_authorized"]:
        if hard_blocks:
            block_reasons.extend(hard_blocks)
        elif margin_failed:
            block_reasons.append(
                "Score-margin candidate failed: " + ", ".join(margin_failed) + "."
            )
        elif quality_failed:
            detail_parts = []
            if "score_margin_vwap_sanity" in quality_failed:
                detail_parts.append(
                    f"VWAP distance {quality_details['vwap_distance_atr']:.2f} ATR exceeds "
                    f"{float(scalping_settings.SCALPING_SCORE_MARGIN_MAX_ABS_VWAP_ATR):.2f} ATR"
                )
            if "score_margin_relative_volume" in quality_failed:
                detail_parts.append(
                    f"relative volume {quality_details['relative_volume']:.2f} is below "
                    f"{float(scalping_settings.SCALPING_SCORE_MARGIN_MIN_RELATIVE_VOLUME):.2f}"
                )
            if "score_margin_extended_trigger" in quality_failed:
                detail_parts.append("extended price has no same-direction closed-candle trigger")
            if "score_margin_extended_micro" in quality_failed:
                detail_parts.append(
                    "extended price lacks same-direction tick confirmation "
                    f"({quality_details['micro_direction']}/{quality_details['micro_confidence']:.2f})"
                )
            block_reasons.append(
                "Score-margin quality protection blocked entry: "
                + ", ".join(detail_parts or quality_failed)
                + "."
            )
        else:
            block_reasons.append("No native or score-margin technical candidate exists.")

    checks["news_safe"] = bool(news.get("safe", False))
    if not checks["news_safe"]:
        block_reasons.append(str(news.get("reason", "Economic-event risk blocked entry.")))

    checks["execution_economics_acceptable"] = bool(execution.get("safe", False))
    if not checks["execution_economics_acceptable"]:
        block_reasons.append(str(execution.get("reason", "Execution economics rejected entry.")))

    micro_direction = _normalize_direction(micro.get("direction", "NEUTRAL"))
    micro_quality = _float(micro.get("data_quality"))
    micro_confidence = _float(micro.get("confidence"))
    minimum_quality = float(scalping_settings.SCALPING_MICROSTRUCTURE_MIN_DATA_QUALITY)
    micro_ready = micro_quality >= minimum_quality
    checks["microstructure_data_ready"] = (
        micro_ready
        or not bool(scalping_settings.SCALPING_SCORE_MARGIN_REQUIRE_MICRO_DATA)
        or native_allowed
    )
    if not micro_ready:
        advisory_warnings.append(str(micro.get("reason", "Tick microstructure is warming up.")))

    strong_micro_threshold = float(
        scalping_settings.SCALPING_SCORE_MARGIN_STRONG_OPPOSITION_CONFIDENCE
    )
    strong_micro_opposition = bool(
        candidate in {"BUY", "SELL"}
        and micro_direction == opposite
        and micro_confidence + 1e-9 >= strong_micro_threshold
    )
    checks["no_strong_microstructure_opposition"] = not strong_micro_opposition
    if strong_micro_opposition:
        block_reasons.append(
            f"Strong tick opposition: technical={candidate}, microstructure={micro_direction}, "
            f"confidence={micro_confidence:.2f} >= {strong_micro_threshold:.2f}."
        )
    elif micro_direction == opposite:
        advisory_warnings.append(
            f"Weak opposite tick pressure ignored in controlled score-margin mode: "
            f"{micro_direction}/{micro_confidence:.2f}."
        )
    elif micro_direction == "NEUTRAL":
        advisory_warnings.append("Neutral tick pressure did not veto the controlled score-margin entry.")

    intermarket_direction = _normalize_direction(intermarket.get("direction", "NEUTRAL"))
    intermarket_pressure = abs(_float(intermarket.get("pressure_score")))
    threshold = float(scalping_settings.SCALPING_INTERMARKET_STRONG_OPPOSITION_THRESHOLD)
    strong_intermarket_opposition = bool(
        candidate in {"BUY", "SELL"}
        and intermarket_direction == opposite
        and intermarket_pressure + 1e-9 >= threshold
    )
    checks["no_strong_intermarket_opposition"] = not strong_intermarket_opposition
    if strong_intermarket_opposition:
        block_reasons.append(
            f"Strong intermarket opposition: {intermarket_direction} pressure "
            f"{intermarket_pressure:.2f} against {candidate}."
        )

    technical_confidence = _float(technical.get("confidence"))
    execution_confidence = _float(execution.get("confidence"))
    confidence = (
        technical_confidence * 0.50
        + micro_confidence * 0.25
        + execution_confidence * 0.25
    )
    confidence_floor_passed = confidence >= float(scalping_settings.SCALPING_META_MIN_CONFIDENCE)
    checks["meta_confidence_diagnostic_only"] = True
    if not confidence_floor_passed:
        advisory_warnings.append(
            f"Meta confidence {confidence:.2f} is below diagnostic floor "
            f"{float(scalping_settings.SCALPING_META_MIN_CONFIDENCE):.2f}; "
            "it does not veto controlled score-margin entries."
        )

    enabled = bool(scalping_settings.SCALPING_META_CONTROLLER_ENABLED)
    allowed = bool(signal.allowed) if not enabled else all(checks.values())
    if native_allowed and allowed:
        entry_mode = "NATIVE_PLAYBOOK"
    elif score_margin_authorized and allowed:
        entry_mode = "SCORE_MARGIN_PAPER" if scalping_settings.SCALPING_PAPER_ONLY else "SCORE_MARGIN_DEMO"
    else:
        entry_mode = "WAIT"

    return {
        "enabled": enabled,
        "allowed": allowed,
        "direction": candidate if allowed else "WAIT",
        "entry_mode": entry_mode,
        "native_playbook_allowed": native_allowed,
        "score_margin_authorized": score_margin_authorized,
        "candidate_promoted": bool(allowed and score_margin_authorized),
        "confidence": round(confidence, 6),
        "confidence_floor_passed": confidence_floor_passed,
        "checks": checks,
        # Backward-compatible key retained for reports/tests. These are now
        # diagnostics except for the explicit score-margin checks.
        "promotion_checks": {**margin_checks, **quality_checks, **advisory_context},
        "promotion_failed_gates": margin_failed + quality_failed,
        "score_margin_quality_checks": quality_checks,
        "score_margin_quality_details": quality_details,
        "advisory_context_checks": advisory_context,
        "advisory_failed_gates": advisory_failed,
        "soft_strategy_blocks": soft_blocks,
        "hard_signal_blocks": hard_blocks,
        "advisory_warnings": list(dict.fromkeys(advisory_warnings)),
        "block_reasons": list(dict.fromkeys(block_reasons)),
        "reason": (
            "Native technical playbook passed all operational safety gates."
            if allowed and native_allowed
            else (
                f"Quality-aware paper score-margin entry accepted: {candidate} leads by at least "
                f"{float(scalping_settings.SCALPING_SCORE_MARGIN_ENTRY_MIN_DIFFERENCE):.1f} points "
                "and passed anti-chasing protections."
            )
            if allowed and score_margin_authorized
            else " | ".join(list(dict.fromkeys(block_reasons)))
        ),
    }


def apply_meta_controller_to_signal(
    signal: ScalpSignalState,
    meta: dict[str, Any],
    *,
    microstructure: dict[str, Any],
    agents: dict[str, dict[str, Any]],
    direct_intermarket: dict[str, Any],
) -> ScalpSignalState:
    if not isinstance(signal.metrics, dict):
        signal.metrics = {}
    signal.metrics["microstructure"] = microstructure
    signal.metrics["agents"] = agents
    signal.metrics["meta_controller"] = meta
    signal.metrics["direct_intermarket_context"] = direct_intermarket

    if bool(meta.get("enabled", False)) and not bool(meta.get("allowed", False)):
        signal.allowed = False
        signal.action = "WAIT"
        for reason in meta.get("block_reasons", []):
            text = str(reason)
            if text and text not in signal.block_reasons:
                signal.block_reasons.append(text)
    elif bool(meta.get("allowed", False)):
        direction = str(meta.get("direction", signal.direction))
        signal.allowed = direction in {"BUY", "SELL"}
        signal.action = direction if signal.allowed else "WAIT"
        signal.direction = direction if signal.allowed else signal.direction
        if bool(meta.get("candidate_promoted", False)):
            signal.pattern = "SCORE_MARGIN_PAPER" if scalping_settings.SCALPING_PAPER_ONLY else "SCORE_MARGIN_DEMO"
            signal.block_reasons = []
            candidate = _dict(signal.metrics.get("technical_candidate"))
            if candidate.get("signal_key"):
                base_key = str(candidate["signal_key"])
                mode_key = "SCORE_MARGIN_PAPER" if scalping_settings.SCALPING_PAPER_ONLY else "SCORE_MARGIN_DEMO"
                signal.signal_key = base_key.replace(
                    "|DIRECT_SCORE|", f"|{mode_key}|"
                ).replace(
                    "|TICK_CONFIRMED_CONTINUATION|", f"|{mode_key}|"
                ).replace(
                    "|SCORE_MARGIN_PAPER|", f"|{mode_key}|"
                )
        message = str(meta.get("reason", ""))
        if message and message not in signal.reasons:
            signal.reasons.append(message)
    return signal
