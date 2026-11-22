"""Graded, continuously-updated read of the executable quote stream.

`gold_flow_exit` answers one question — "has a reversal been *confirmed* long
enough to close?" — and deliberately waits out a confirmation window before it
says yes. That is right for a protective stop and too slow for a scalper who
wants to bank a small profit the moment flow turns.

This module answers a different question, every loop cycle: *how much* is the
flow turning, right now, as a number between 0 and 1. Nothing here closes a
position on its own. It supplies:

* `reversal_risk` for a held direction, used by the fast profit-take,
* a directional read used to decide re-entry after a scalp exit,
* a source for the position conscience.

It reads only the executable bid/ask the bot already samples. No aggressor
side, no order volume, no inferred depth: those are not available from an MT5
quote stream and are not guessed at here.
"""
from __future__ import annotations

import math
from typing import Any

from config import gold_consensus_settings as settings

DIRECTIONS = {"BUY", "SELL"}


def _finite(*values: Any) -> bool:
    try:
        return all(math.isfinite(float(v)) for v in values)
    except (TypeError, ValueError):
        return False


class MicroFlow:
    """Rolling executable-quote buffer, one instance per symbol.

    State is time-indexed on the broker clock, so a repeated or out-of-order
    quote can never advance a window: a stalled feed must not read as calm
    flow, and the same tick seen twice must not read as two observations.
    """

    def __init__(self) -> None:
        self.samples: list[tuple[float, float, float]] = []
        self.last_reason = "No quote observed yet"

    def reset(self) -> None:
        self.samples.clear()

    def observe(self, *, quote_time: float, bid: float, ask: float, now: float) -> bool:
        """Record one quote. Returns False when it is unusable."""
        if (not _finite(quote_time, bid, ask, now) or bid <= 0 or ask < bid
                or not -settings.MT5_QUOTE_FUTURE_TOLERANCE_SECONDS <= now-quote_time <= settings.ENTRY_MAX_QUOTE_AGE_SECONDS):
            self.reset()
            self.last_reason = "Invalid quote"
            return False
        if self.samples:
            previous = self.samples[-1][0]
            if quote_time <= previous:
                self.last_reason = "Repeated or out-of-order quote"
                return False
            if quote_time - previous > float(settings.MICRO_FLOW_MAX_SAMPLE_GAP_SECONDS):
                # A gap means the stream was interrupted; earlier samples no
                # longer describe continuous flow.
                self.samples.clear()
        self.samples.append((float(quote_time), float(bid), float(ask)))
        longest = max(float(w) for w in settings.MICRO_FLOW_WINDOWS_SECONDS)
        cutoff = quote_time - (longest + 5.0)
        self.samples = [s for s in self.samples if s[0] >= cutoff][-int(settings.MICRO_FLOW_MAX_BUFFER):]
        self.last_reason = "Observing"
        return True

    def _window(self, seconds: float) -> dict[str, Any] | None:
        if not self.samples:
            return None
        newest = self.samples[-1][0]
        sample = [s for s in self.samples if newest - s[0] <= seconds]
        if len(sample) < int(settings.MICRO_FLOW_MIN_SAMPLES):
            return None
        span = sample[-1][0] - sample[0][0]
        if span < seconds * .8:
            return None
        mids = [(s[1] + s[2]) / 2.0 for s in sample]
        net = mids[-1] - mids[0]
        path = sum(abs(b - a) for a, b in zip(mids, mids[1:]))
        spreads = [s[2] - s[1] for s in sample]
        median_spread = sorted(spreads)[len(spreads) // 2]
        scale = max(median_spread, 1e-6)
        # Both executable sides must agree on direction: a spread that widens
        # on one side only is a dealing artefact, not flow.
        bid_move = sample[-1][1] - sample[0][1]
        ask_move = sample[-1][2] - sample[0][2]
        both = bid_move if abs(bid_move) < abs(ask_move) else ask_move
        if (bid_move > 0) != (ask_move > 0):
            both = 0.0
        return {
            "seconds": seconds, "samples": len(sample), "span_seconds": span,
            "net_move": net, "velocity_spreads_per_second": (net / scale) / span,
            "efficiency": (abs(net) / path) if path > 0 else 0.0,
            "two_sided_move_spreads": both / scale,
            "median_spread": median_spread,
            "spread_expansion": (spreads[-1] - median_spread) / scale,
        }

    def read(self, direction: str | None = None, *, now: float) -> dict[str, Any]:
        """Multi-window flow read, optionally relative to a held direction."""
        if (not self.samples or not _finite(now)
                or not -settings.MT5_QUOTE_FUTURE_TOLERANCE_SECONDS <= now-self.samples[-1][0] <= settings.ENTRY_MAX_QUOTE_AGE_SECONDS):
            return {'available': False, 'reason': 'No fresh quote-flow observation', 'policy': 'MICRO_FLOW_V2'}
        windows = {}
        for seconds in settings.MICRO_FLOW_WINDOWS_SECONDS:
            measured = self._window(float(seconds))
            if measured is not None:
                windows[str(seconds)] = measured
        # A short window may lead only after the longer context has warmed up.
        if len(windows) < 2:
            return {"available": False, "reason": self.last_reason or "Insufficient quote samples",
                    "policy": "MICRO_FLOW_V1"}
        ordered = [windows[k] for k in sorted(windows, key=float)]
        # Short windows lead, long windows confirm.
        weights = [3.0, 2.0, 1.0][:len(ordered)]
        total = sum(weights)
        pressure = sum(w * math.tanh(x["two_sided_move_spreads"] / 2.0)
                       for w, x in zip(weights, ordered)) / total
        efficiency = sum(w * x["efficiency"] for w, x in zip(weights, ordered)) / total
        fastest = ordered[0]
        slowest = ordered[-1]
        # Acceleration: is the newest window pushing harder than the oldest?
        # Compare rates, not unequal window distances: steady flow must have
        # zero acceleration regardless of which window is longer.
        acceleration = (math.tanh(fastest["two_sided_move_spreads"] / fastest['span_seconds'])
                        - math.tanh(slowest["two_sided_move_spreads"] / slowest['span_seconds']))
        bias = ("BUY" if pressure > 0.15 and efficiency >= 0.35 else
                "SELL" if pressure < -0.15 and efficiency >= 0.35 else "NEUTRAL")
        result = {
            "available": True, "policy": "MICRO_FLOW_V2", "role": "HEURISTIC_FLOW_CONTEXT",
            "observed_at": self.samples[-1][0],
            "pressure": round(pressure, 4), "efficiency": round(efficiency, 4),
            "acceleration": round(acceleration, 4), "bias": bias,
            "median_spread": round(fastest["median_spread"], 5),
            "spread_expansion": round(fastest["spread_expansion"], 4),
            "windows": {k: {kk: (round(vv, 6) if isinstance(vv, float) else vv)
                            for kk, vv in v.items()} for k, v in windows.items()},
            "calibrated_probability": None, "evidence_type": "HEURISTIC_STRENGTH",
        }
        if str(direction).upper() in DIRECTIONS:
            result.update(self._reversal(str(direction).upper(), pressure, efficiency, acceleration))
        return result

    @staticmethod
    def _reversal(direction: str, pressure: float, efficiency: float,
                  acceleration: float) -> dict[str, Any]:
        """Graded risk that flow has turned against the direction held.

        Deliberately continuous rather than a threshold: the caller decides how
        much risk is worth banking a profit for, and that decision differs
        between a position 0.1R up and one 0.8R up.
        """
        sign = 1.0 if direction == "BUY" else -1.0
        against = max(0.0, -sign * pressure)
        # Opposing pressure matters more when the move is clean and speeding up.
        quality = min(1.0, 0.55 + 0.45 * min(1.0, efficiency / 0.6))
        speeding = max(0.0, -sign * acceleration)
        risk = min(1.0, quality * (against + 0.5 * speeding))
        return {"direction": direction, "reversal_risk": round(risk, 4),
                "flow_against": round(against, 4),
                "reversal_detail": (f"{direction} facing {against:.2f} opposing pressure "
                                    f"at {efficiency:.2f} efficiency")}


def fast_profit_take(flow: dict[str, Any], *, move: float, spread: float,
                     risk_threshold: float | None = None, exposure: float = 1.) -> tuple[bool, str]:
    """Bank a small profit when flow turns, but never below the round trip.

    ``move`` is measured against the executable exit side, so the entry spread
    is already deducted and ``move == 0`` is true breakeven. The floor below is
    the additional margin that separates a real gain from a green number that
    cost more to obtain than it returned.
    """
    if not flow.get("available") or flow.get("reversal_risk") is None:
        return False, ""
    if not _finite(move, spread, exposure, flow.get('reversal_risk')) or spread < 0 or exposure <= 0:
        return False, ""
    floor = max(float(settings.SCALP_MIN_PROFIT_TAKE_SPREADS) * max(0.0, spread),
                float(settings.SCALP_MIN_PROFIT_TAKE_USD)/exposure)
    if move < floor:
        return False, ""
    risk = float(flow["reversal_risk"])
    if risk < float(settings.SCALP_REVERSAL_RISK_EXIT if risk_threshold is None else risk_threshold):
        return False, ""
    return True, (f"Flow reversal risk {risk:.2f} while {move:.2f} in profit "
                  f"(floor {floor:.2f}); banking it rather than waiting for a target")
