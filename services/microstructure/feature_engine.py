from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Iterable

import numpy as np
import pandas as pd

from config import scalping_settings


@dataclass
class WindowMicrostructureState:
    window_seconds: float
    tick_count: int = 0
    observed_span_seconds: float = 0.0
    tick_arrival_rate: float = 0.0
    bid_change_rate: float = 0.0
    ask_change_rate: float = 0.0
    mid_velocity: float = 0.0
    mid_acceleration: float = 0.0
    velocity_atr_per_second: float = 0.0
    synthetic_delta: int = 0
    directional_tick_ratio: float = 0.0
    spread_change: float = 0.0
    spread_expansion: float = 0.0
    spread_contraction: float = 0.0
    quote_persistence_ms: float = 0.0
    price_progress_per_tick: float = 0.0
    efficiency_ratio: float = 0.0
    stall_ratio: float = 1.0
    sweep_distance_atr: float = 0.0
    post_sweep_reversal_atr: float = 0.0
    quote_flow_imbalance_proxy: float = 0.0
    arrival_acceleration: float = 0.0
    reversal_ratio: float = 0.0


@dataclass
class MicrostructureFeatureState:
    generated_at_msc: int
    symbol: str
    direction: str
    confidence: float
    data_quality: float
    status: str
    reason: str
    latest_mid: float
    latest_spread: float
    m1_atr: float
    total_recent_ticks: int
    recent_span_seconds: float
    micro_regime: str = "UNKNOWN"
    micro_regime_confidence: float = 0.0
    windows: dict[str, WindowMicrostructureState] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["windows"] = {
            name: asdict(state) for name, state in self.windows.items()
        }
        return payload

    def to_flat_dict(self) -> dict[str, Any]:
        row: dict[str, Any] = {
            "generated_at_msc": self.generated_at_msc,
            "symbol": self.symbol,
            "direction": self.direction,
            "confidence": self.confidence,
            "data_quality": self.data_quality,
            "status": self.status,
            "reason": self.reason,
            "latest_mid": self.latest_mid,
            "latest_spread": self.latest_spread,
            "m1_atr": self.m1_atr,
            "total_recent_ticks": self.total_recent_ticks,
            "recent_span_seconds": self.recent_span_seconds,
            "micro_regime": self.micro_regime,
            "micro_regime_confidence": self.micro_regime_confidence,
        }
        for name, state in self.windows.items():
            prefix = f"w{name}_"
            for key, value in asdict(state).items():
                if key != "window_seconds":
                    row[prefix + key] = value
        return row


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        result = float(value)
        return result if np.isfinite(result) else default
    except (TypeError, ValueError):
        return default


def _normalize_ticks(ticks: Iterable[dict[str, Any]]) -> pd.DataFrame:
    frame = pd.DataFrame.from_records(list(ticks))
    required = {"time_msc", "bid", "ask", "mid", "spread"}
    if frame.empty or not required.issubset(frame.columns):
        return pd.DataFrame(columns=sorted(required))
    for column in required:
        frame[column] = pd.to_numeric(frame[column], errors="coerce")
    frame = frame.dropna(subset=list(required)).sort_values("time_msc")
    frame = frame.drop_duplicates(subset=["time_msc", "bid", "ask"], keep="last")
    return frame.reset_index(drop=True)


def _quote_persistence_ms(frame: pd.DataFrame) -> float:
    if len(frame) < 2:
        return 0.0
    times = frame["time_msc"].to_numpy(dtype=float)
    changed = (
        frame["bid"].diff().fillna(0).ne(0)
        | frame["ask"].diff().fillna(0).ne(0)
    ).to_numpy()
    change_indices = np.flatnonzero(changed)
    boundaries = np.concatenate(([0], change_indices, [len(frame) - 1]))
    durations: list[float] = []
    for start, end in zip(boundaries[:-1], boundaries[1:]):
        if end > start:
            durations.append(max(0.0, times[end] - times[start]))
    return float(np.mean(durations)) if durations else 0.0


def _window_features(
    frame: pd.DataFrame,
    window_seconds: float,
    atr: float,
) -> WindowMicrostructureState:
    latest_msc = float(frame.iloc[-1]["time_msc"])
    lower = latest_msc - float(window_seconds) * 1000.0
    window = frame[frame["time_msc"] >= lower].copy()
    state = WindowMicrostructureState(window_seconds=float(window_seconds))
    state.tick_count = int(len(window))
    if window.empty:
        return state

    span = max(0.0, (float(window.iloc[-1]["time_msc"]) - float(window.iloc[0]["time_msc"])) / 1000.0)
    effective_span = max(span, min(float(window_seconds), 0.001))
    state.observed_span_seconds = round(span, 6)
    state.tick_arrival_rate = round(state.tick_count / effective_span, 6)

    bid_diff = window["bid"].diff().fillna(0.0)
    ask_diff = window["ask"].diff().fillna(0.0)
    mid_diff = window["mid"].diff().fillna(0.0)
    spread_first = _safe_float(window.iloc[0]["spread"])
    spread_last = _safe_float(window.iloc[-1]["spread"])

    state.bid_change_rate = round(float(bid_diff.ne(0).sum()) / effective_span, 6)
    state.ask_change_rate = round(float(ask_diff.ne(0).sum()) / effective_span, 6)

    # Quote-flow imbalance proxy. MT5 top-of-book ticks do not expose queue
    # sizes, so this is deliberately not labelled as true order-flow imbalance.
    # Bid/ask moves upward contribute buying pressure; downward moves contribute
    # selling pressure. The value is normalized to [-1, 1].
    bid_steps = np.sign(bid_diff.to_numpy(dtype=float))
    ask_steps = np.sign(ask_diff.to_numpy(dtype=float))
    quote_events = float(np.abs(bid_steps).sum() + np.abs(ask_steps).sum())
    quote_pressure = float((bid_steps + ask_steps).sum())
    state.quote_flow_imbalance_proxy = round(quote_pressure / quote_events, 6) if quote_events else 0.0

    # Tick-arrival acceleration compares the second half of the observation
    # window with the first. It is normalized so different broker tick rates are
    # comparable and bounded to [-1, 1].
    if len(window) >= 4:
        midpoint_msc = (float(window.iloc[0]["time_msc"]) + float(window.iloc[-1]["time_msc"])) / 2.0
        first_half = window[window["time_msc"] <= midpoint_msc]
        second_half = window[window["time_msc"] > midpoint_msc]
        first_span = max(0.001, (midpoint_msc - float(window.iloc[0]["time_msc"])) / 1000.0)
        second_span = max(0.001, (float(window.iloc[-1]["time_msc"]) - midpoint_msc) / 1000.0)
        first_rate = float(len(first_half)) / first_span
        second_rate = float(len(second_half)) / second_span
        denom = first_rate + second_rate
        state.arrival_acceleration = round((second_rate - first_rate) / denom, 6) if denom > 0 else 0.0

    net_move = _safe_float(window.iloc[-1]["mid"]) - _safe_float(window.iloc[0]["mid"])
    state.mid_velocity = round(net_move / effective_span, 8)
    state.velocity_atr_per_second = round(state.mid_velocity / atr, 8) if atr > 0 else 0.0

    if len(window) >= 4 and span > 0:
        midpoint = len(window) // 2
        first = window.iloc[: midpoint + 1]
        second = window.iloc[midpoint:]
        first_span = max(0.001, (float(first.iloc[-1]["time_msc"]) - float(first.iloc[0]["time_msc"])) / 1000.0)
        second_span = max(0.001, (float(second.iloc[-1]["time_msc"]) - float(second.iloc[0]["time_msc"])) / 1000.0)
        first_velocity = (_safe_float(first.iloc[-1]["mid"]) - _safe_float(first.iloc[0]["mid"])) / first_span
        second_velocity = (_safe_float(second.iloc[-1]["mid"]) - _safe_float(second.iloc[0]["mid"])) / second_span
        state.mid_acceleration = round((second_velocity - first_velocity) / max(0.001, (first_span + second_span) / 2.0), 8)

    signs = np.sign(mid_diff.to_numpy(dtype=float))
    up = int((signs > 0).sum())
    down = int((signs < 0).sum())
    directional = up + down
    state.synthetic_delta = int(up - down)
    state.directional_tick_ratio = round((up - down) / directional, 6) if directional else 0.0

    state.spread_change = round(spread_last - spread_first, 8)
    state.spread_expansion = round(max(0.0, state.spread_change), 8)
    state.spread_contraction = round(max(0.0, -state.spread_change), 8)
    state.quote_persistence_ms = round(_quote_persistence_ms(window), 3)

    absolute_path = float(np.abs(mid_diff.to_numpy(dtype=float)).sum())
    changed_ticks = max(1, directional)
    state.price_progress_per_tick = round(net_move / changed_ticks, 8)
    state.efficiency_ratio = round(abs(net_move) / absolute_path, 6) if absolute_path > 0 else 0.0
    state.stall_ratio = round(float((signs == 0).sum()) / max(1, len(signs)), 6)

    high = _safe_float(window["mid"].max())
    low = _safe_float(window["mid"].min())
    last = _safe_float(window.iloc[-1]["mid"])
    state.sweep_distance_atr = round((high - low) / atr, 6) if atr > 0 else 0.0
    if net_move >= 0:
        reversal = max(0.0, high - last)
    else:
        reversal = max(0.0, last - low)
    state.post_sweep_reversal_atr = round(reversal / atr, 6) if atr > 0 else 0.0
    state.reversal_ratio = round(
        state.post_sweep_reversal_atr / max(state.sweep_distance_atr, 1e-9), 6
    ) if state.sweep_distance_atr > 0 else 0.0
    return state


def build_microstructure_features(
    symbol: str,
    ticks: Iterable[dict[str, Any]],
    *,
    m1_atr: float,
) -> MicrostructureFeatureState:
    frame = _normalize_ticks(ticks)
    atr = max(0.0, _safe_float(m1_atr))
    if frame.empty:
        return MicrostructureFeatureState(
            generated_at_msc=0,
            symbol=symbol,
            direction="NEUTRAL",
            confidence=0.0,
            data_quality=0.0,
            status="NO_TICKS",
            reason="No valid MT5 ticks are available.",
            latest_mid=0.0,
            latest_spread=0.0,
            m1_atr=atr,
            total_recent_ticks=0,
            recent_span_seconds=0.0,
        )

    latest_msc = int(frame.iloc[-1]["time_msc"])
    span = max(0.0, (latest_msc - int(frame.iloc[0]["time_msc"])) / 1000.0)
    windows: dict[str, WindowMicrostructureState] = {}
    configured = tuple(getattr(scalping_settings, "SCALPING_MICROSTRUCTURE_WINDOWS_SECONDS", (1.0, 3.0, 5.0)))
    for seconds in configured:
        name = str(int(seconds)) if float(seconds).is_integer() else str(seconds).replace(".", "p")
        windows[name] = _window_features(frame, float(seconds), atr)

    preferred = windows.get("3") or next(iter(windows.values()))
    minimum_ticks = max(1, int(scalping_settings.SCALPING_MICROSTRUCTURE_MIN_TICKS))
    minimum_span = max(0.001, float(scalping_settings.SCALPING_MICROSTRUCTURE_MIN_SPAN_SECONDS))
    # Readiness is based on the primary 3-second window, not old ticks that may
    # still remain in the 20-second in-memory research buffer.
    tick_quality = min(1.0, preferred.tick_count / minimum_ticks)
    span_quality = min(1.0, preferred.observed_span_seconds / minimum_span)
    atr_quality = 1.0 if atr > 0 else 0.0
    data_quality = round(0.55 * tick_quality + 0.35 * span_quality + 0.10 * atr_quality, 6)

    ratio_threshold = float(scalping_settings.SCALPING_MICROSTRUCTURE_DIRECTIONAL_RATIO_THRESHOLD)
    velocity_threshold = float(scalping_settings.SCALPING_MICROSTRUCTURE_MIN_VELOCITY_ATR_PER_SECOND)
    max_stall = float(scalping_settings.SCALPING_MICROSTRUCTURE_MAX_STALL_RATIO)

    direction = "NEUTRAL"
    evidence = 0.0
    if preferred.stall_ratio <= max_stall:
        buy_ratio = preferred.directional_tick_ratio >= ratio_threshold
        sell_ratio = preferred.directional_tick_ratio <= -ratio_threshold
        buy_velocity = preferred.velocity_atr_per_second >= velocity_threshold
        sell_velocity = preferred.velocity_atr_per_second <= -velocity_threshold
        if buy_ratio and buy_velocity:
            direction = "BUY"
            evidence = min(1.0, abs(preferred.directional_tick_ratio) * 0.65 + min(1.0, abs(preferred.velocity_atr_per_second) / max(velocity_threshold, 1e-9)) * 0.35)
        elif sell_ratio and sell_velocity:
            direction = "SELL"
            evidence = min(1.0, abs(preferred.directional_tick_ratio) * 0.65 + min(1.0, abs(preferred.velocity_atr_per_second) / max(velocity_threshold, 1e-9)) * 0.35)

    confidence = round(evidence * data_quality, 6)

    # A compact micro-regime describes how the tape is moving. It is a model
    # feature only; it never bypasses the hard candidate gate.
    spread_expansion_atr = preferred.spread_expansion / atr if atr > 0 else 0.0
    if preferred.stall_ratio > max_stall:
        micro_regime = "STALLED"
        regime_confidence = min(1.0, preferred.stall_ratio)
    elif (
        preferred.efficiency_ratio >= 0.60
        and abs(preferred.quote_flow_imbalance_proxy) >= 0.20
        and abs(preferred.velocity_atr_per_second) >= velocity_threshold
    ):
        micro_regime = "IMPULSE"
        regime_confidence = min(1.0, 0.40 * preferred.efficiency_ratio + 0.35 * abs(preferred.quote_flow_imbalance_proxy) + 0.25 * min(1.0, abs(preferred.velocity_atr_per_second) / max(velocity_threshold, 1e-9)))
    elif preferred.sweep_distance_atr >= 0.08 and preferred.reversal_ratio >= 0.45:
        micro_regime = "REVERSAL"
        regime_confidence = min(1.0, 0.55 * preferred.reversal_ratio + 0.45 * min(1.0, preferred.sweep_distance_atr / 0.25))
    elif spread_expansion_atr >= 0.05 and preferred.efficiency_ratio < 0.35:
        micro_regime = "DISLOCATED"
        regime_confidence = min(1.0, 0.60 * min(1.0, spread_expansion_atr / 0.15) + 0.40 * (1.0 - preferred.efficiency_ratio))
    else:
        micro_regime = "ROTATION"
        regime_confidence = min(1.0, 0.50 * (1.0 - preferred.efficiency_ratio) + 0.50 * (1.0 - min(1.0, preferred.reversal_ratio)))

    minimum_quality = float(scalping_settings.SCALPING_MICROSTRUCTURE_MIN_DATA_QUALITY)
    if data_quality < minimum_quality:
        status = "WARMING_UP"
        reason = (
            f"Microstructure data quality {data_quality:.2f} is below "
            f"{minimum_quality:.2f}; ticks={len(frame)}, span={span:.2f}s."
        )
        direction = "NEUTRAL"
        confidence = 0.0
    elif direction == "NEUTRAL":
        status = "NEUTRAL"
        reason = (
            f"No directional tick consensus: ratio={preferred.directional_tick_ratio:+.2f}, "
            f"velocity={preferred.velocity_atr_per_second:+.4f} ATR/s, "
            f"stall={preferred.stall_ratio:.2f}."
        )
    else:
        status = "DIRECTIONAL"
        reason = (
            f"{direction} tick pressure: ratio={preferred.directional_tick_ratio:+.2f}, "
            f"velocity={preferred.velocity_atr_per_second:+.4f} ATR/s, "
            f"arrival={preferred.tick_arrival_rate:.1f}/s."
        )

    return MicrostructureFeatureState(
        generated_at_msc=latest_msc,
        symbol=symbol,
        direction=direction,
        confidence=confidence,
        data_quality=data_quality,
        status=status,
        reason=reason,
        latest_mid=_safe_float(frame.iloc[-1]["mid"]),
        latest_spread=_safe_float(frame.iloc[-1]["spread"]),
        m1_atr=atr,
        total_recent_ticks=int(len(frame)),
        recent_span_seconds=round(span, 6),
        micro_regime=micro_regime,
        micro_regime_confidence=round(regime_confidence * data_quality, 6),
        windows=windows,
    )
