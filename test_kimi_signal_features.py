from __future__ import annotations

import pandas as pd

from services.analysis.atome_factor_model import _direction_score, _indicators, _prepare
from services.research.v6_outcome_quality import research_outcome_eligible


def _frame(closes: list[float]) -> pd.DataFrame:
    rows = []
    for index, close in enumerate(closes):
        open_price = closes[index - 1] if index else close
        rows.append(
            {
                "time": pd.Timestamp("2026-01-01", tz="UTC") + pd.Timedelta(minutes=index),
                "open": open_price,
                "high": max(open_price, close) + 0.02,
                "low": min(open_price, close) - 0.02,
                "close": close,
                "tick_volume": 100,
            }
        )
    return pd.DataFrame(rows)


def test_prepare_excludes_forming_candle() -> None:
    frame = _frame([100.0] * 60)
    frame.loc[59, "close"] = 999.0
    closed, diagnostic = _prepare(frame, "M1")
    assert len(closed) == 59
    assert float(closed.iloc[-1]["close"]) == 100.0
    assert diagnostic["closed_bars_used"] == 59


def test_bullish_engulfing_adds_price_action_evidence() -> None:
    frame = _frame([100.0 + index * 0.01 for index in range(58)] + [100.80, 100.65])
    frame.loc[58, ["open", "close", "high", "low"]] = [100.85, 100.70, 100.87, 100.68]
    frame.loc[59, ["open", "close", "high", "low"]] = [100.68, 100.90, 100.92, 100.66]
    metrics = _indicators(frame)
    assert metrics["bullish_engulfing"] is True
    score = _direction_score("BUY", metrics, metrics, metrics)
    assert score["components"]["price_action"] == 10.0


def test_closed_candle_squeeze_breakout_is_detected() -> None:
    # A volatile baseline followed by a tight 30-bar compression makes the
    # previous band materially narrower than its rolling width baseline.
    closes = [100.0 + (0.50 if index % 2 else -0.50) for index in range(50)]
    closes += [100.0 + (0.01 if index % 2 else -0.01) for index in range(30)]
    closes += [100.50]
    metrics = _indicators(_frame(closes))
    assert metrics["bb_width_ratio"] <= 0.80
    assert metrics["bullish_band_expansion"] is True
    assert metrics["bearish_band_expansion"] is False


def test_unmonitored_legacy_outcome_is_not_research_eligible() -> None:
    assert research_outcome_eligible({"feed_pause_seconds_ignored": 1_008_461.898}) is False
    assert research_outcome_eligible({"feed_pause_seconds_ignored": 2.0}) is True


if __name__ == "__main__":
    test_prepare_excludes_forming_candle()
    test_bullish_engulfing_adds_price_action_evidence()
    test_closed_candle_squeeze_breakout_is_detected()
    test_unmonitored_legacy_outcome_is_not_research_eligible()
    print("KIMI-inspired closed-candle feature tests passed.")
