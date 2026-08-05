from __future__ import annotations

import time
from collections import defaultdict, deque
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

try:
    import MetaTrader5 as mt5
except ImportError:  # Allows offline validation on non-Windows build hosts.
    mt5 = None

from config import scalping_settings


@dataclass
class VerifiedIntermarketSymbol:
    role: str
    symbol: str
    verified: bool
    reason: str = ""


@dataclass
class IntermarketTickContext:
    status: str
    generated_at: str
    resolved_symbols: dict[str, str] = field(default_factory=dict)
    values: dict[str, float] = field(default_factory=dict)
    returns: dict[str, dict[str, float]] = field(default_factory=dict)
    gold_bias: str = "NEUTRAL"
    pressure_score: float = 0.0
    reasons: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "generated_at": self.generated_at,
            "resolved_symbols": dict(self.resolved_symbols),
            "values": dict(self.values),
            "returns": {key: dict(value) for key, value in self.returns.items()},
            "gold_bias": self.gold_bias,
            "pressure_score": self.pressure_score,
            "reasons": list(self.reasons),
        }


class IntermarketSymbolTracker:
    """Resolve broker-specific proxy symbols and track short percentage returns."""

    def __init__(self) -> None:
        self._resolved: dict[str, VerifiedIntermarketSymbol] = {}
        self._last_resolution = 0.0
        self._samples: dict[str, deque[tuple[float, float]]] = defaultdict(
            lambda: deque(maxlen=10000)
        )

    @staticmethod
    def _candidates() -> dict[str, tuple[str, ...]]:
        return {
            "dxy": tuple(scalping_settings.SCALPING_DXY_SYMBOL_CANDIDATES),
            "us10y": tuple(scalping_settings.SCALPING_US10Y_SYMBOL_CANDIDATES),
            "tnote": tuple(scalping_settings.SCALPING_TNOTE_SYMBOL_CANDIDATES),
            "vix": tuple(scalping_settings.SCALPING_VIX_SYMBOL_CANDIDATES),
        }

    @staticmethod
    def _verified_tick(symbol: str) -> tuple[bool, float, str]:
        if mt5 is None:
            return False, 0.0, "MetaTrader5 package unavailable"
        info = mt5.symbol_info(symbol)
        if info is None:
            return False, 0.0, "symbol_info unavailable"
        if not bool(getattr(info, "visible", False)):
            try:
                mt5.symbol_select(symbol, True)
            except Exception:
                pass
        tick = mt5.symbol_info_tick(symbol)
        if tick is None:
            return False, 0.0, "symbol_info_tick unavailable"
        bid = float(getattr(tick, "bid", 0.0) or 0.0)
        ask = float(getattr(tick, "ask", 0.0) or 0.0)
        last = float(getattr(tick, "last", 0.0) or 0.0)
        value = (bid + ask) / 2.0 if bid > 0 and ask > 0 else last
        if value <= 0:
            return False, 0.0, "no positive quote"
        return True, value, "verified MT5 quote"

    @staticmethod
    def _symbol_matches_candidate(symbol: str, candidate: str) -> bool:
        """Reject accidental substring matches such as AZN for ZN or SVIX for VIX."""
        symbol_upper = str(symbol or "").strip().upper()
        candidate_upper = str(candidate or "").strip().upper()
        if not symbol_upper or not candidate_upper:
            return False
        if symbol_upper == candidate_upper:
            return True
        # Accept only explicit broker suffix conventions. Arbitrary leading or
        # trailing letters are not accepted because they can represent a wholly
        # unrelated equity or ETF.
        allowed_suffixes = (".CASH", "_CASH", "-CASH", ".SPOT", "_SPOT", "-SPOT", ".M", "_M", "-M", ".I", "_I", "-I", ".PRO", "_PRO", "-PRO")
        return any(symbol_upper == candidate_upper + suffix for suffix in allowed_suffixes)

    @staticmethod
    def _expanded_candidates(candidates: tuple[str, ...]) -> list[str]:
        names: list[str] = []
        for candidate in candidates:
            if candidate not in names:
                names.append(candidate)
            try:
                matches = mt5.symbols_get(group=f"*{candidate}*") or () if mt5 is not None else ()
            except Exception:
                matches = ()
            discovered = sorted(
                {str(getattr(item, "name", "") or "") for item in matches},
                key=lambda value: (len(value), value),
            )
            for name in discovered:
                if (
                    name
                    and IntermarketSymbolTracker._symbol_matches_candidate(name, candidate)
                    and name not in names
                ):
                    names.append(name)
        return names

    def _resolve_if_due(self) -> None:
        refresh = max(30.0, float(scalping_settings.SCALPING_INTERMARKET_REFRESH_SECONDS))
        now = time.monotonic()
        if self._resolved and now - self._last_resolution < refresh:
            return
        self._last_resolution = now
        self._resolved = {}
        for role, candidates in self._candidates().items():
            chosen = VerifiedIntermarketSymbol(role, "", False, "No candidate verified")
            for symbol in self._expanded_candidates(candidates):
                ok, _, reason = self._verified_tick(symbol)
                if ok:
                    chosen = VerifiedIntermarketSymbol(role, symbol, True, reason)
                    break
            self._resolved[role] = chosen

    @staticmethod
    def _return_at(samples: deque[tuple[float, float]], now_msc: float, seconds: float) -> float:
        if not samples:
            return 0.0
        latest = samples[-1][1]
        target = now_msc - seconds * 1000.0
        previous = None
        for stamp, value in reversed(samples):
            if stamp <= target:
                previous = value
                break
        if previous is None:
            previous = samples[0][1]
        return (latest / previous - 1.0) if previous > 0 else 0.0

    def snapshot(self) -> IntermarketTickContext:
        if not bool(scalping_settings.SCALPING_DIRECT_INTERMARKET_ENABLED):
            return IntermarketTickContext(
                status="DISABLED",
                generated_at=datetime.now(timezone.utc).isoformat(),
            )
        self._resolve_if_due()
        now_msc = time.time() * 1000.0
        values: dict[str, float] = {}
        returns: dict[str, dict[str, float]] = {}
        resolved: dict[str, str] = {}
        reasons: list[str] = []
        windows = tuple(scalping_settings.SCALPING_INTERMARKET_RETURN_WINDOWS_SECONDS)

        for role, record in self._resolved.items():
            if not record.verified or not record.symbol:
                continue
            ok, value, reason = self._verified_tick(record.symbol)
            if not ok:
                reasons.append(f"{role}:{record.symbol} unavailable ({reason})")
                continue
            resolved[role] = record.symbol
            values[role] = value
            samples = self._samples[role]
            samples.append((now_msc, value))
            cutoff = now_msc - 60_000.0
            while samples and samples[0][0] < cutoff:
                samples.popleft()
            returns[role] = {
                f"{int(seconds)}s": round(self._return_at(samples, now_msc, float(seconds)), 10)
                for seconds in windows
            }

        # Five-second returns provide context; they never generate a trade.
        minimum = max(1e-9, float(scalping_settings.SCALPING_INTERMARKET_MIN_RETURN_ABS))
        signed_components: list[float] = []
        dxy_ret = returns.get("dxy", {}).get("5s", 0.0)
        yield_ret = returns.get("us10y", {}).get("5s", 0.0)
        note_ret = returns.get("tnote", {}).get("5s", 0.0)
        if abs(dxy_ret) >= minimum:
            signed_components.append(-max(-1.0, min(1.0, dxy_ret / (minimum * 5.0))))
            reasons.append(f"DXY 5s return={dxy_ret:+.6%}")
        if abs(yield_ret) >= minimum:
            signed_components.append(-max(-1.0, min(1.0, yield_ret / (minimum * 5.0))))
            reasons.append(f"US10Y 5s return={yield_ret:+.6%}")
        if abs(note_ret) >= minimum:
            signed_components.append(max(-1.0, min(1.0, note_ret / (minimum * 5.0))))
            reasons.append(f"T-note 5s return={note_ret:+.6%}")

        pressure = sum(signed_components) / len(signed_components) if signed_components else 0.0
        bias = "BUY" if pressure >= 0.25 else "SELL" if pressure <= -0.25 else "NEUTRAL"
        status = "ACTIVE" if resolved else "NO_VERIFIED_SYMBOLS"
        return IntermarketTickContext(
            status=status,
            generated_at=datetime.now(timezone.utc).isoformat(),
            resolved_symbols=resolved,
            values=values,
            returns=returns,
            gold_bias=bias,
            pressure_score=round(pressure, 6),
            reasons=reasons,
        )


_TRACKER = IntermarketSymbolTracker()


def get_direct_intermarket_context() -> dict[str, Any]:
    return _TRACKER.snapshot().to_dict()
