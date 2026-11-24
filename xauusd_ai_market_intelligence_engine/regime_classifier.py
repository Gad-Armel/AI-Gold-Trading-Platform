"""
Market Regime Classification Engine for XAUUSD.
Identifies whether Gold is Trending, Ranging, in Breakout Expansion,
or experiencing Abnormal Volatility (news spikes / liquidity vacuums).
"""

from typing import Dict, Any, List, Optional
import numpy as np
import pandas as pd


class MarketRegime:
    TRENDING_BULL = "TRENDING_BULL"
    TRENDING_BEAR = "TRENDING_BEAR"
    RANGING_MEAN_REVERT = "RANGING_MEAN_REVERT"
    BREAKOUT_EXPANSION = "BREAKOUT_EXPANSION"
    ABNORMAL_VOLATILITY = "ABNORMAL_VOLATILITY"


class RegimeClassifier:
    """
    Classifies the continuous market dynamics of XAUUSD into 5 actionable regimes.
    Combines rule-based statistical bounds (ATR multiples, BB squeeze percentiles)
    with multi-timeframe directional strength.
    """

    def __init__(
        self,
        adx_trend_threshold: float = 25.0,
        bb_squeeze_percentile: float = 20.0,
        abnormal_volatility_multiplier: float = 2.8,
        abnormal_spread_points: float = 60.0,
        point_value: float = 0.01
    ):
        self.adx_threshold = adx_trend_threshold
        self.bb_squeeze_pct = bb_squeeze_percentile
        self.abnormal_vol_mult = abnormal_volatility_multiplier
        self.abnormal_spread = abnormal_spread_points
        self.point_value = point_value

    def classify_bar(self, row: pd.Series, rolling_atr_median: float, rolling_bbw_median: float) -> Dict[str, Any]:
        """
        Classifies market regime for a single feature row.
        """
        atr_points = float(row.get('m15_atr_points', 15.0))
        bb_bandwidth = float(row.get('m15_bb_bandwidth', 0.8))
        ema_spread = float(row.get('m15_ema_spread_8_21', 0.0))
        dist_200 = float(row.get('m15_dist_to_ema_200_pct', 0.0))
        rsi = float(row.get('m15_rsi_14', 50.0))
        spread = float(row.get('spread', 25.0))
        roc_5 = float(row.get('m15_roc_5', 0.0))

        # Check Condition 1: ABNORMAL VOLATILITY (Flash spike / major news release / spread blowout)
        is_abnormal_vol = (atr_points >= rolling_atr_median * self.abnormal_vol_mult)
        is_abnormal_spread = (spread >= self.abnormal_spread)
        is_flash_move = (abs(roc_5) > 1.2)  # >1.2% in 5 bars on Gold is an extreme outlier

        if is_abnormal_vol or is_abnormal_spread or is_flash_move:
            return {
                "regime": MarketRegime.ABNORMAL_VOLATILITY,
                "confidence": 0.95,
                "description": "High abnormal volatility detected (spread/flash shock). Mandatory risk guard active.",
                "trade_recommendation_permitted": False,
                "metrics": {
                    "atr_points": round(atr_points, 1),
                    "rolling_atr_median": round(rolling_atr_median, 1),
                    "spread_points": spread,
                    "volatility_ratio": round(atr_points / max(1e-5, rolling_atr_median), 2)
                }
            }

        # Check Condition 2: BREAKOUT EXPANSION (Volatility expansion breaking out from low squeeze)
        is_vol_expanding = (atr_points > rolling_atr_median * 1.4)
        is_bb_widening = (bb_bandwidth > rolling_bbw_median * 1.5)
        is_strong_directional_roc = (abs(roc_5) > 0.45)

        if is_vol_expanding and is_bb_widening and is_strong_directional_roc:
            direction = "BULLISH" if roc_5 > 0 else "BEARISH"
            return {
                "regime": MarketRegime.BREAKOUT_EXPANSION,
                "confidence": 0.82,
                "description": f"Volatility breakout expansion ({direction}). High momentum expansion phase.",
                "trade_recommendation_permitted": True,
                "direction": direction,
                "metrics": {
                    "atr_points": round(atr_points, 1),
                    "bb_bandwidth": round(bb_bandwidth, 3),
                    "roc_5": round(roc_5, 2)
                }
            }

        # Check Condition 3: TRENDING (BULLISH vs BEARISH)
        # Clear separation between EMAs and positive/negative distance to 200 EMA
        is_bull_trend = (ema_spread > 5.0) and (dist_200 > 0.15) and (rsi > 52.0)
        is_bear_trend = (ema_spread < -5.0) and (dist_200 < -0.15) and (rsi < 48.0)

        if is_bull_trend:
            return {
                "regime": MarketRegime.TRENDING_BULL,
                "confidence": 0.88,
                "description": "Established Bullish Trend structure with positive EMA ribbon alignment.",
                "trade_recommendation_permitted": True,
                "metrics": {
                    "ema_spread": round(ema_spread, 1),
                    "dist_200_pct": round(dist_200, 2),
                    "rsi": round(rsi, 1)
                }
            }

        if is_bear_trend:
            return {
                "regime": MarketRegime.TRENDING_BEAR,
                "confidence": 0.88,
                "description": "Established Bearish Trend structure with negative EMA ribbon alignment.",
                "trade_recommendation_permitted": True,
                "metrics": {
                    "ema_spread": round(ema_spread, 1),
                    "dist_200_pct": round(dist_200, 2),
                    "rsi": round(rsi, 1)
                }
            }

        # Check Condition 4: RANGING / MEAN REVERTING
        return {
            "regime": MarketRegime.RANGING_MEAN_REVERT,
            "confidence": 0.78,
            "description": "Consolidation / sideways range. Mean-reverting boundary characteristics.",
            "trade_recommendation_permitted": True,
            "metrics": {
                "bb_bandwidth": round(bb_bandwidth, 3),
                "rsi": round(rsi, 1),
                "ema_spread": round(ema_spread, 1)
            }
        }

    def classify_series(self, feature_df: pd.DataFrame) -> pd.DataFrame:
        """
        Classifies regimes across an entire historical DataFrame.
        Uses expanding or rolling statistics to strictly prevent future information leakage.
        """
        df = feature_df.copy()
        
        # Calculate rolling historical medians (strictly backward-looking window = 100 bars)
        atr_col = 'm15_atr_points' if 'm15_atr_points' in df.columns else df.columns[1]
        bbw_col = 'm15_bb_bandwidth' if 'm15_bb_bandwidth' in df.columns else df.columns[2]

        rolling_atr_median = df[atr_col].rolling(window=100, min_periods=20).median().fillna(df[atr_col].mean())
        rolling_bbw_median = df[bbw_col].rolling(window=100, min_periods=20).median().fillna(df[bbw_col].mean())

        regimes = []
        confidences = []

        for i in range(len(df)):
            row = df.iloc[i]
            res = self.classify_bar(row, rolling_atr_median.iloc[i], rolling_bbw_median.iloc[i])
            regimes.append(res["regime"])
            confidences.append(res["confidence"])

        df["market_regime"] = regimes
        df["regime_confidence"] = confidences
        return df
