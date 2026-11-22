"""
Multi-Timeframe Market Structure Engine for XAUUSD.
Detects Swing Highs/Lows, Break of Structure (BOS), Change of Character (CHoCH),
Fair Value Gaps (FVG), Liquidity Sweeps, and Multi-Timeframe Alignment.
"""

from typing import Dict, List, Tuple, Any, Optional
import numpy as np
import pandas as pd


class MarketStructureAnalyzer:
    """
    Computes algorithmic market structure across M1, M5, M15, and H1 timeframes.
    Strictly causal: swing pivots are confirmed only after N subsequent bars close,
    preventing look-ahead bias in live/backtest analysis.
    """

    def __init__(self, pivot_order: int = 5, fvg_threshold_points: float = 15.0):
        self.pivot_order = pivot_order
        self.fvg_threshold = fvg_threshold_points

    def detect_swing_points(self, df: pd.DataFrame) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
        """
        Detects fractal swing highs and swing lows.
        A bar at index `i` is a confirmed swing high if its high is >= the highs of `order` bars
        before and `order` bars after.
        """
        highs = df['high'].values
        lows = df['low'].values
        times = df['time'].values
        n = len(df)
        k = self.pivot_order

        swing_highs = []
        swing_lows = []

        for i in range(k, n - k):
            # Check swing high
            if np.all(highs[i] >= highs[i - k:i]) and np.all(highs[i] >= highs[i + 1:i + k + 1]):
                swing_highs.append({
                    "index": i,
                    "time": str(times[i]),
                    "price": float(highs[i]),
                    "confirmed_at_index": i + k
                })

            # Check swing low
            if np.all(lows[i] <= lows[i - k:i]) and np.all(lows[i] <= lows[i + 1:i + k + 1]):
                swing_lows.append({
                    "index": i,
                    "time": str(times[i]),
                    "price": float(lows[i]),
                    "confirmed_at_index": i + k
                })

        return swing_highs, swing_lows

    def detect_fair_value_gaps(self, df: pd.DataFrame, point_value: float = 0.01) -> List[Dict[str, Any]]:
        """
        Detects Fair Value Gaps (FVG / 3-bar imbalance):
        - Bullish FVG: Bar(i).low > Bar(i-2).high by at least fvg_threshold points.
        - Bearish FVG: Bar(i).high < Bar(i-2).low by at least fvg_threshold points.
        """
        fvgs = []
        n = len(df)
        if n < 3:
            return fvgs

        highs = df['high'].values
        lows = df['low'].values
        times = df['time'].values

        min_gap_dist = self.fvg_threshold * point_value

        for i in range(2, n):
            # Bullish FVG
            if lows[i] > highs[i - 2] + min_gap_dist:
                fvgs.append({
                    "type": "BULLISH_FVG",
                    "top": float(lows[i]),
                    "bottom": float(highs[i - 2]),
                    "gap_size_points": round((lows[i] - highs[i - 2]) / point_value, 1),
                    "created_at_index": i,
                    "time": str(times[i]),
                    "mitigated": False
                })
            # Bearish FVG
            elif highs[i] < lows[i - 2] - min_gap_dist:
                fvgs.append({
                    "type": "BEARISH_FVG",
                    "top": float(lows[i - 2]),
                    "bottom": float(highs[i]),
                    "gap_size_points": round((lows[i - 2] - highs[i]) / point_value, 1),
                    "created_at_index": i,
                    "time": str(times[i]),
                    "mitigated": False
                })

        # Check for subsequent mitigation (test if price later retraces into gap)
        for fvg in fvgs:
            c_idx = fvg["created_at_index"]
            if fvg["type"] == "BULLISH_FVG":
                subseq_lows = lows[c_idx + 1:]
                if len(subseq_lows) > 0 and np.any(subseq_lows <= fvg["bottom"]):
                    fvg["mitigated"] = True
            else:
                subseq_highs = highs[c_idx + 1:]
                if len(subseq_highs) > 0 and np.any(subseq_highs >= fvg["top"]):
                    fvg["mitigated"] = True

        return fvgs

    def detect_bos_and_choch(self, df: pd.DataFrame) -> Dict[str, Any]:
        """
        Evaluates recent Break of Structure (BOS) and Change of Character (CHoCH).
        - BOS occurs when price closes beyond the most recent confirmed swing point in the direction of trend.
        - CHoCH occurs when price breaks the swing point opposite to the established trend.
        """
        swing_highs, swing_lows = self.detect_swing_points(df)
        closes = df['close'].values
        n = len(df)

        current_trend = "NEUTRAL"
        last_event = "NONE"
        last_event_bar = 0
        last_event_price = 0.0

        # Merge swings chronologically
        events = []
        for sh in swing_highs:
            events.append({"type": "HIGH", **sh})
        for sl in swing_lows:
            events.append({"type": "LOW", **sl})
        events.sort(key=lambda x: x["index"])

        if len(events) >= 3:
            # Determine initial trend sequence
            last_two_highs = [e for e in events if e["type"] == "HIGH"][-3:]
            last_two_lows = [e for e in events if e["type"] == "LOW"][-3:]

            higher_highs = len(last_two_highs) >= 2 and last_two_highs[-1]["price"] > last_two_highs[-2]["price"]
            higher_lows = len(last_two_lows) >= 2 and last_two_lows[-1]["price"] > last_two_lows[-2]["price"]
            lower_highs = len(last_two_highs) >= 2 and last_two_highs[-1]["price"] < last_two_highs[-2]["price"]
            lower_lows = len(last_two_lows) >= 2 and last_two_lows[-1]["price"] < last_two_lows[-2]["price"]

            if higher_highs and higher_lows:
                current_trend = "BULLISH"
            elif lower_highs and lower_lows:
                current_trend = "BEARISH"
            else:
                current_trend = "RANGING"

            # Check latest bar relative to active swings
            latest_close = closes[-1]
            latest_high_swing = last_two_highs[-1]["price"] if last_two_highs else None
            latest_low_swing = last_two_lows[-1]["price"] if last_two_lows else None

            if latest_high_swing is not None and latest_close > latest_high_swing:
                if current_trend == "BULLISH":
                    last_event = "BOS_BULLISH"
                else:
                    last_event = "CHOCH_BULLISH"
                last_event_price = latest_high_swing
                last_event_bar = n - 1
            elif latest_low_swing is not None and latest_close < latest_low_swing:
                if current_trend == "BEARISH":
                    last_event = "BOS_BEARISH"
                else:
                    last_event = "CHOCH_BEARISH"
                last_event_price = latest_low_swing
                last_event_bar = n - 1

        return {
            "trend": current_trend,
            "last_event": last_event,
            "last_event_price": float(last_event_price),
            "swing_highs_count": len(swing_highs),
            "swing_lows_count": len(swing_lows),
            "recent_swing_high": swing_highs[-1]["price"] if swing_highs else None,
            "recent_swing_low": swing_lows[-1]["price"] if swing_lows else None,
        }

    def analyze_multi_timeframe(self, mtf_candles: Dict[str, pd.DataFrame]) -> Dict[str, Any]:
        """
        Aggregates structure across M1, M5, M15, H1 timeframes and calculates alignment score.
        Alignment Score: +1.0 (Full Bullish Confluence), -1.0 (Full Bearish Confluence), 0.0 (Conflicted).
        """
        report = {}
        trend_weights = {"H1": 0.40, "M15": 0.30, "M5": 0.20, "M1": 0.10}
        confluence_score = 0.0

        for tf, df in mtf_candles.items():
            if df.empty or len(df) < (self.pivot_order * 2 + 10):
                continue

            struct = self.detect_bos_and_choch(df)
            fvgs = self.detect_fair_value_gaps(df)
            unmitigated_fvgs = [f for f in fvgs if not f["mitigated"]]

            report[tf] = {
                "trend": struct["trend"],
                "last_event": struct["last_event"],
                "recent_swing_high": struct["recent_swing_high"],
                "recent_swing_low": struct["recent_swing_low"],
                "unmitigated_fvgs": len(unmitigated_fvgs),
                "latest_unmitigated_fvg": unmitigated_fvgs[-1] if unmitigated_fvgs else None
            }

            # Weight direction
            w = trend_weights.get(tf, 0.25)
            if struct["trend"] == "BULLISH":
                confluence_score += w
            elif struct["trend"] == "BEARISH":
                confluence_score -= w

        report["multi_timeframe_alignment_score"] = round(confluence_score, 2)
        if confluence_score >= 0.50:
            report["confluence_bias"] = "STRONG_BULLISH"
        elif confluence_score <= -0.50:
            report["confluence_bias"] = "STRONG_BEARISH"
        elif abs(confluence_score) < 0.20:
            report["confluence_bias"] = "CHOPPY_NEUTRAL"
        else:
            report["confluence_bias"] = "MODERATE_" + ("BULLISH" if confluence_score > 0 else "BEARISH")

        return report
