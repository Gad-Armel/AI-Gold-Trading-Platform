from __future__ import annotations

"""Independent evidence policies for SCALP, INTRADAY and SWING demo lanes."""

from typing import Any
import math

from config import gold_consensus_settings as settings

DIRECTIONS = {"BUY", "SELL"}


def flow_primary_levels(direction: str, reference: float, atr: float) -> dict[str, Any]:
    """Derive SCALP levels from ATR at the live executable price.

    A flow-primary lane cannot borrow levels from an agreeing candle advisor:
    across 2,420 recorded cycles, no candle advisor agreed with the tick
    advisor in 88% of strong-flow moments. That disagreement is the normal
    condition for fast flow against slower structure, not a reason to stand
    down, so the levels are built from volatility instead.
    """
    if direction not in DIRECTIONS or not all(math.isfinite(x) and x > 0 for x in (atr, reference)):
        return {}
    target_distance = float(settings.SCALP_LEVEL_TARGET_ATR) * atr
    stop_distance = float(settings.SCALP_LEVEL_STOP_ATR) * atr
    sign = 1.0 if direction == "BUY" else -1.0
    return {
        "tp1": round(reference + sign * target_distance, 3),
        "tp2": round(reference + sign * target_distance * 1.6, 3),
        "tp3": round(reference + sign * target_distance * 2.4, 3),
        "sl": round(reference - sign * stop_distance, 3),
        "entry_zone": sorted([round(reference - 0.15 * atr, 3), round(reference + 0.15 * atr, 3)]),
        "source": "SCALP_FLOW_ATR",
        "entry_reference": reference,
    }


def _flow_primary_decision(contributors: list[dict[str, Any]], config: dict[str, Any],
                           atr: float, reference: float) -> dict[str, Any]:
    """Tick flow decides direction and timing against its own evidence scale.

    The three advisors do not share a scale (directional medians 75 / 75 / 54),
    so applying one threshold to all of them silently made the tick advisor --
    which this lane weights at 60% -- almost never qualify. Here it is judged
    on its own distribution and the slower advisors keep a veto.
    """
    by_name = {str(item["advisor"]): item for item in contributors}
    flow = by_name.get("MT5_TICK_FLOW", {})
    blocks: list[str] = []
    reasons: list[str] = []
    continuous = settings.CONTINUOUS_DIRECTIONAL_ENTRIES
    bar = float(settings.VERY_WEAK_EVIDENCE if continuous else settings.SCALP_FLOW_ENTRY_EVIDENCE)
    usable = bool(flow.get("source_usable"))
    bias = str(flow.get("bias", "WAIT")).upper()
    evidence = float(flow.get("evidence", 0.0) or 0.0)
    if not usable:
        blocks.append("MT5_TICK_FLOW is unusable; SCALP has no flow authority.")
    elif bias not in DIRECTIONS:
        blocks.append("MT5_TICK_FLOW has no directional read.")
    elif evidence < bar:
        blocks.append(f"MT5_TICK_FLOW evidence {evidence:.1f} is below the flow bar {bar:.1f}.")
    veto = float(settings.SCALP_OPPOSING_VETO_EVIDENCE)
    opposing = [item for name, item in by_name.items()
                if name != "MT5_TICK_FLOW" and item.get("source_usable")
                and str(item.get("bias")).upper() in DIRECTIONS
                and str(item.get("bias")).upper() != bias
                and float(item.get("evidence", 0.0) or 0.0) >= veto]
    if bias in DIRECTIONS and opposing and not continuous:
        names = ", ".join(sorted(str(item["advisor"]) for item in opposing))
        blocks.append(f"Slower structure opposes the flow at or above {veto:.1f}: {names}.")
    agreeing = [item for name, item in by_name.items()
                if name != "MT5_TICK_FLOW" and item.get("source_usable")
                and str(item.get("bias")).upper() == bias]
    if bias in DIRECTIONS and agreeing:
        reasons.append("Slower structure agrees with the flow: "
                       + ", ".join(sorted(str(item["advisor"]) for item in agreeing)) + ".")
    levels = flow_primary_levels(bias, reference, atr) if bias in DIRECTIONS else {}
    if bias in DIRECTIONS and not levels:
        blocks.append("SCALP volatility levels are unavailable.")
    return {"dominant": bias if usable else "WAIT", "evidence": evidence, "blocks": blocks,
            "reasons": reasons, "levels": levels,
            "strong_supporters": [flow] if (usable and bias in DIRECTIONS and evidence >= bar) else []}


def build_horizon_decisions(consensus: dict[str, Any], news_risk: dict[str, Any] | None = None,
                            macro_context: dict[str, Any] | None = None,
                            economic_advisor: dict[str, Any] | None = None,
                            market_context: dict[str, dict[str, Any]] | None = None,
                            scalp_signal: dict[str, Any] | None = None) -> dict[str, dict[str, Any]]:
    news_risk = news_risk or {"allowed": True, "active_events": [], "block_reasons": []}
    market_context = market_context or {}
    macro_context = macro_context or {}
    economic_advisor = economic_advisor or {}
    source_blocks = dict(consensus.get("source_blocks", {}) or {})
    decisions: dict[str, dict[str, Any]] = {}
    for horizon, config in settings.HORIZON_LANES.items():
        fast_frame = str((scalp_signal or {}).get('timeframe', 'S30'))
        if scalp_signal is not None and fast_frame not in ('S30', 'S15', 'S5', 'S1'):
            raise ValueError('Unsupported fast entry timeframe')
        source = dict(consensus.get("horizons", {}).get(horizon, {}) or {})
        advisors = dict(source.get("advisors", {}) or {})
        weights = dict(config["advisor_weights"])
        if horizon == 'SCALP' and scalp_signal is not None:
            advisors[f'{fast_frame}_TICKS'] = scalp_signal
            weights[f'{fast_frame}_TICKS'] = 1.
        directional_weight = {"BUY": 0.0, "SELL": 0.0}
        evidence_weight = {"BUY": 0.0, "SELL": 0.0}
        contributors: list[dict[str, Any]] = []
        for advisor, weight in weights.items():
            item = dict(advisors.get(advisor, {}) or {})
            bias = str(item.get("bias", "WAIT")).upper()
            evidence = max(0.0, min(100.0, float(item.get("evidence", 0.0) or 0.0)))
            raw_evidence = float(item.get('evidence', 0.0) or 0.0)
            source_usable = bool(item.get("source_usable", True)) and math.isfinite(raw_evidence)
            if bias in DIRECTIONS and source_usable:
                directional_weight[bias] += float(weight)
                evidence_weight[bias] += float(weight) * evidence
            contributors.append({"advisor": advisor, "weight": float(weight), "bias": bias,
                                 "evidence": round(evidence, 2), "action": item.get("action", "WAIT"),
                                 "valid_until": item.get('valid_until'),
                                 "validity_reason": item.get('validity_reason',''),
                                 "source_usable": source_usable})
        continuous = settings.CONTINUOUS_DIRECTIONAL_ENTRIES
        threshold = float(settings.VERY_WEAK_EVIDENCE if continuous else config["entry_evidence"])
        strong = {direction: [item for item in contributors
                              if item["source_usable"] and item["bias"] == direction
                              and item["evidence"] >= threshold]
                  for direction in DIRECTIONS}
        strong_dominant = ("BUY" if len(strong["BUY"]) >= 2 and len(strong["BUY"]) > len(strong["SELL"])
                           else "SELL" if len(strong["SELL"]) >= 2 and len(strong["SELL"]) > len(strong["BUY"])
                           else "WAIT")
        weighted_dominant = "BUY" if directional_weight["BUY"] > directional_weight["SELL"] else (
            "SELL" if directional_weight["SELL"] > directional_weight["BUY"] else "WAIT"
        )
        dominant = weighted_dominant if continuous else (strong_dominant if strong_dominant in DIRECTIONS else weighted_dominant)
        directional_supporters = [item for item in contributors if item["bias"] == dominant]
        support_weight = directional_weight.get(dominant, 0.0)
        strong_supporters = strong.get(dominant, [])
        strong_advisor_names = {str(item["advisor"]) for item in strong_supporters}
        required_sources = () if continuous else tuple(str(item) for item in config.get("required_strong_advisors", ()))
        missing_required_sources = [item for item in required_sources if item not in strong_advisor_names]
        strong_weight = sum(float(item["weight"]) for item in strong_supporters)
        evidence = (sum(float(item["weight"]) * float(item["evidence"]) for item in strong_supporters) / strong_weight
                    if strong_weight > 0 else evidence_weight.get(dominant, 0.0) / support_weight
                    if support_weight > 0 else 0.0)
        blocks: list[str] = []
        reasons: list[str] = []
        entry_mode = str(config.get("entry_mode", "CONSENSUS_2_OF_3")).upper()
        s30_primary = horizon == 'SCALP' and scalp_signal is not None
        if s30_primary:
            entry_mode = f'{fast_frame}_PRIMARY'
        advisor1_primary = entry_mode in {"ADVISOR1_PRIMARY", "S30_PRIMARY", "S15_PRIMARY", "S5_PRIMARY", "S1_PRIMARY"}
        flow_primary = entry_mode in {"FLOW_PRIMARY", "ADVISOR1_PRIMARY", "S30_PRIMARY", "S15_PRIMARY", "S5_PRIMARY", "S1_PRIMARY"}
        primary_source = f'{fast_frame}_TICKS' if s30_primary else 'MT5_CANDLES' if advisor1_primary else 'MT5_TICK_FLOW'
        if flow_primary:
            context = dict(market_context.get(horizon, {}) or {})
            flow_bias = str(advisors.get(primary_source, {}).get('bias', '')).upper()
            reference = context.get('ask' if flow_bias == 'BUY' else 'bid', 0.0)
            if advisor1_primary:
                primary = next(item for item in contributors if item['advisor'] == primary_source)
                primary_blocks = []
                if not primary['source_usable']:
                    primary_blocks.append(f'{fast_frame} tick signal is unavailable or stale.' if s30_primary else
                                          'Advisor 1 SCALP candle signal is unavailable or stale.')
                if flow_bias not in DIRECTIONS or primary['evidence'] < threshold:
                    primary_blocks.append(f'{fast_frame} has no usable direction above the evidence threshold.' if s30_primary else
                                          'Advisor 1 SCALP has no usable direction at or above 15/100.')
                primary_levels = dict(advisors.get(primary_source, {}).get('levels', {}) or {})
                primary_levels.update(entry_reference=float(reference or 0), source=f'{fast_frame}_STRUCTURE' if s30_primary else 'ADVISOR1_SCALP')
                flow_result = dict(dominant=flow_bias if primary['source_usable'] else 'WAIT',
                    evidence=primary['evidence'], blocks=primary_blocks,
                    reasons=[f'{fast_frame} determines entry direction; Advisor 1 is context only.' if s30_primary else
                             'Advisor 1 SCALP candles determine direction and evidence; tick flow is context.'],
                    levels=primary_levels,
                    strong_supporters=[primary] if not primary_blocks else [])
            else:
                flow_result = _flow_primary_decision(
                    contributors, config, float(context.get("atr", 0.0) or 0.0) if context.get('available') else 0.0,
                    float(reference or 0.0))
            dominant = flow_result["dominant"]
            evidence = flow_result["evidence"]
            strong_supporters = flow_result["strong_supporters"]
            strong_advisor_names = {str(item["advisor"]) for item in strong_supporters}
            directional_supporters = [item for item in contributors if item["bias"] == dominant]
            support_weight = directional_weight.get(dominant, 0.0)
            blocks.extend(flow_result["blocks"])
            reasons.extend(flow_result["reasons"])
            # The tick advisor's own source blocks still apply.
            blocks.extend(str(item) for item in source_blocks.get(primary_source, []) or [])
        else:
            if continuous and (dominant not in DIRECTIONS or not strong_supporters):
                blocks.append(f"No usable directional evidence at or above {threshold:.1f}/100.")
            elif not continuous and strong_dominant not in DIRECTIONS:
                blocks.append(f"Fewer than 2 of 3 advisors have the same BIAS at or above {threshold:.1f}/100.")
            if dominant in DIRECTIONS and missing_required_sources:
                blocks.append(
                    "Required strong source(s) missing for this horizon: "
                    + ", ".join(missing_required_sources) + "."
                )
            for required_source in required_sources:
                blocks.extend(str(item) for item in source_blocks.get(required_source, []) or [])
        news_block = not bool(news_risk.get("allowed", True))
        if news_block:
            blocks.extend(str(item) for item in news_risk.get("block_reasons", []) or ["High-impact news window."])
        if flow_primary:
            matching_levels = [flow_result["levels"]] if flow_result["levels"] else []
        else:
            matching_levels = [dict(advisors.get(item["advisor"], {}).get("levels", {}) or {})
                               for item in strong_supporters]
        matching_levels = [item for item in matching_levels if item]
        levels: dict[str, Any] = {}
        for key in ("sl", "tp1", "tp2", "tp3"):
            values = [float(item[key]) for item in matching_levels if item.get(key) is not None]
            if values:
                levels[key] = round(sum(values) / len(values), 3)
        zones = [item["entry_zone"] for item in matching_levels if len(item.get("entry_zone", [])) == 2]
        if zones:
            levels["entry_zone"] = [round(sum(float(zone[index]) for zone in zones) / len(zones), 3)
                                    for index in (0, 1)]
        if flow_primary and flow_result['levels']:
            levels.update(entry_reference=flow_result['levels']['entry_reference'],
                          source=f'{fast_frame}_STRUCTURE' if s30_primary else 'ADVISOR1_SCALP' if advisor1_primary else 'SCALP_FLOW_ATR')
        target_key = str(config["preferred_target"])
        target = levels.get(target_key)
        stop = levels.get("sl")
        if dominant in DIRECTIONS and (target is None or stop is None):
            blocks.append("ATR-derived entry/exit levels are unavailable.")
        macro_bias = str(macro_context.get("directional_bias", "NEUTRAL")).upper()
        if horizon == "SWING" and macro_bias in DIRECTIONS:
            reasons.append(f"Verified macro-surprise context is {macro_bias}; context only, not an entry authority.")
        inverse_threshold = float(getattr(settings, "SCALP_INVERSE_BELOW_EVIDENCE", 78.5))
        inverse_active = (bool(getattr(settings, "SCALP_WEAK_BIAS_INVERSION_ENABLED", False))
                          and horizon == "SCALP" and dominant in DIRECTIONS
                          and len(directional_supporters) >= 2 and evidence < inverse_threshold)
        execution_direction = ({"BUY": "SELL", "SELL": "BUY"}[dominant]
                               if inverse_active else dominant)
        if inverse_active:
            blocks = [item for item in blocks if not item.startswith("Fewer than 2 of 3 advisors")]
            reasons.append(f"SCALP weak-BIAS inversion: {dominant} at {evidence:.1f}/100 executes {execution_direction}.")
            zone = levels.get("entry_zone", [])
            if len(zone) == 2 and target is not None and stop is not None:
                reference = (float(zone[0]) + float(zone[1])) / 2.0
                target_distance, stop_distance = abs(float(target) - reference), abs(reference - float(stop))
                target = round(reference - target_distance, 3) if execution_direction == "SELL" else round(reference + target_distance, 3)
                stop = round(reference + stop_distance, 3) if execution_direction == "SELL" else round(reference - stop_distance, 3)
        economic = dict(economic_advisor.get("horizons", {}).get(horizon, {}) or {})
        economic_bias = str(economic.get("bias", "NEUTRAL")).upper()
        economic_quality = float(economic.get("quality", 0.0) or 0.0)
        economic_strength = abs(float(economic.get("score", 0.0) or 0.0))
        economic_conflict = bool(
            dominant in DIRECTIONS and economic_bias in DIRECTIONS and economic_bias != dominant
            and economic_quality >= 0.70 and economic_strength >= 0.55
        )
        # Slow macro/institutional context is relevant to INTRADAY/SWING, but
        # cannot authorize a trade or override fresh market data. A high-quality
        # contradiction blocks a new entry until the technical picture resolves.
        if horizon in {"INTRADAY", "SWING"} and economic_conflict and not continuous:
            blocks.append(f"Economic V5 strongly opposes {dominant} ({economic_bias}, score {economic_strength:.2f}).")
        elif economic_bias == dominant and economic_quality >= 0.50:
            reasons.append(f"Economic V5 confirms {dominant}; confirmation only, not entry authority.")
        allowed = execution_direction in DIRECTIONS and not blocks
        if flow_primary:
            # Judged on the tick advisor's own scale, where the directional
            # median is 54 and 91.5 is the observed maximum.
            flow_bar = threshold if advisor1_primary or continuous else float(settings.SCALP_FLOW_ENTRY_EVIDENCE)
            signal_band = (("STRONG" if evidence >= 75 else "DEVELOPING" if evidence >= 50
                            else "WEAK" if evidence >= 15 else "VERY_WEAK") if advisor1_primary else
                          "STRONG" if strong_supporters and evidence >= flow_bar + 12.0
                           else "DEVELOPING" if strong_supporters
                           else "WEAK" if evidence >= 15.0 else "VERY_WEAK")
            required_strong_count = 1
        else:
            signal_band = ("STRONG" if len(strong_supporters) >= 2
                           else "DEVELOPING" if evidence >= 75.0
                           else "WEAK" if evidence >= 15.0 else "VERY_WEAK")
            required_strong_count = 1 if continuous else 2
        contrarian_watch = (not flow_primary and dominant in DIRECTIONS
                            and 15.0 <= evidence < 75.0 and not inverse_active)
        if s30_primary and not scalp_signal.get('source_usable'):
            input_reason = scalp_signal.get('observation', {}).get('reason')
            if input_reason:
                blocks.insert(0, f'Fast signal input unavailable: {input_reason}')
        decisions[horizon] = {
            "horizon": horizon, "direction": execution_direction if allowed else "WAIT", "dominant_bias": dominant,
            "evidence": round(evidence, 2), "entry_threshold": threshold if continuous or advisor1_primary else float(settings.SCALP_FLOW_ENTRY_EVIDENCE if flow_primary else config["entry_evidence"]),
            "evidence_type": "HEURISTIC_STRENGTH", "calibrated_probability": None,
            "exit_threshold": threshold if continuous else float(config["exit_evidence"]), "support_weight": round(support_weight, 3),
            "strong_advisor_count": len(strong_supporters),
            "required_strong_advisor_count": required_strong_count,
            "entry_mode": entry_mode,
            "required_strong_advisors": [primary_source] if flow_primary else list(required_sources),
            "strong_advisors": sorted(strong_advisor_names),
            "allowed": allowed, "blocks": blocks, "reasons": reasons,
            "signal_band": signal_band, "contrarian_watch": contrarian_watch,
            "inverse_active": inverse_active, "inverse_threshold": inverse_threshold if horizon == "SCALP" else None,
            "contrarian_direction": ({"BUY": "SELL", "SELL": "BUY"}.get(dominant, "WAIT")
                                      if contrarian_watch or inverse_active else "WAIT"),
            "contributors": contributors, "levels": levels, "entry_reference": levels.get("entry_reference"),
            "economic_advisor": economic, "economic_conflict": economic_conflict,
            "take_profit": target, "stop_loss": stop, "target_name": target_key.upper(),
            "valid_until": min((str(advisors.get(item["advisor"], {}).get("valid_until")) for item in strong_supporters
                                if advisors.get(item["advisor"], {}).get("valid_until")),
                               default=source.get("valid_until")), "news_block": news_block,
            "news_policy": config["news_policy"], "macro_context": macro_context if horizon == "SWING" else {},
            "data_roles": {
                "SCALP": (f"{fast_frame} ticks determine entry bias and structural levels; Advisor 1 is exit context only." if s30_primary else
                          "Advisor 1 M1/M5/M15 candles determine entry bias, evidence and levels; tick flow manages exits."
                          if advisor1_primary else "MT5 tick flow primary; MT5 candles structure; API candles low-weight sanity check."),
                "INTRADAY": "MT5 and independent API candles primary; MT5 tick flow entry timing.",
                "SWING": "MT5/API H1-H4 structure primary; official macro/CFTC context is slow and non-authorizing.",
            }[horizon],
        }
    all_very_weak = all(item['evidence'] < settings.VERY_WEAK_EVIDENCE for item in decisions.values())
    for item in decisions.values():
        item['all_lanes_very_weak'] = all_very_weak
        item['continuous_directional_entries'] = continuous
        if continuous and all_very_weak:
            item['allowed'] = False
            item['direction'] = 'WAIT'
            item['blocks'].append('All three lanes are very weak (below 15/100); new entries paused.')
    from services.research.gold_scalp_context import scalp_context
    decisions['SCALP']['higher_timeframe_context'] = scalp_context(decisions)
    for name, item in decisions.items():
        item['execution_enabled'] = bool(settings.HORIZON_LANES[name].get('trade_enabled', True))
        item['role'] = 'TRADING' if item['execution_enabled'] else 'SCALP_CONTEXT_ONLY'
    return decisions


def evaluate_entry_timing(
    decision: dict[str, Any],
    *,
    open_position_count: int,
    signal_age_seconds: float,
    seconds_since_last_entry: float,
    lane_config: dict[str, Any],
) -> tuple[bool, list[str]]:
    """Apply time persistence and stricter pyramiding rules to one lane.

    The same unchanged snapshot can be evaluated many times by the fast loop;
    elapsed-time persistence prevents those repeated evaluations from being
    mistaken for independent confirmations.
    """
    reasons: list[str] = []
    if not bool(decision.get("allowed", False)):
        reasons.append("The directional policy has not authorized an entry.")
    required_age = float(lane_config.get("minimum_signal_seconds", 0.0) or 0.0)
    if not lane_config.get('trade_enabled', True):
        reasons.append('Analysis only: new positions are disabled for this horizon.')
    if float(signal_age_seconds) < required_age:
        reasons.append(
            f"Signal persistence is {max(0.0, signal_age_seconds):.1f}s; {required_age:.1f}s required."
        )
    if int(open_position_count) > 0:
        add_evidence = float(lane_config.get("add_position_evidence", 100.0) or 100.0)
        if decision.get('entry_mode') == 'THREE_SOURCE_VOTE':
            add_evidence = float(decision.get('source_vote_threshold', 75.))
        elif decision.get('horizon') == 'SCALP':
            adjustment = float(decision.get('higher_timeframe_context', {}).get('addition_threshold_adjustment', 0) or 0)
            if math.isfinite(adjustment):
                add_evidence += max(-5., min(5., adjustment))
        evidence = float(decision.get("evidence", 0.0) or 0.0)
        if evidence < add_evidence:
            reasons.append(f"Adding a position requires evidence >= {add_evidence:.1f}/100.")
        add_spacing = float(lane_config.get("add_position_spacing_seconds", 0.0) or 0.0)
        if float(seconds_since_last_entry) < add_spacing:
            reasons.append(
                f"Position-add spacing is {max(0.0, seconds_since_last_entry):.1f}s; {add_spacing:.1f}s required."
            )
    return not reasons, reasons


def should_close_horizon(decision: dict[str, Any], position_direction: str) -> tuple[bool, str]:
    if decision.get("news_block") and decision.get("news_policy") == "CLOSE_AND_BLOCK":
        return True, "high-impact news protection"
    dominant = str(decision.get("dominant_bias", "WAIT"))
    desired = str(decision.get("direction", "WAIT")) if decision.get("allowed") else dominant
    evidence = float(decision.get("evidence", 0.0) or 0.0)
    if desired in DIRECTIONS and desired != position_direction:
        return True, f"execution direction changed to {desired}"
    if decision.get("inverse_active") and desired == position_direction:
        return False, "SCALP inverse thesis remains active"
    if dominant not in DIRECTIONS or evidence < float(decision.get("exit_threshold", 0.0)):
        return True, f"evidence weakened to {evidence:.1f}"
    return False, "position thesis remains valid"
