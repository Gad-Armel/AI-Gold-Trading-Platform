"""
Feature Engineering Engine for XAUUSD Market Intelligence.
Computes Momentum, Volatility, ATR, RSI, EMA Ribbons, Parkinson Volatility,
and Price Action ratios with strict causal shifting to prevent look-ahead bias.
"""

from typing import Dict, List, Optional, Tuple
import numpy as np
import pandas as pd


class FeatureEngineer:
    """
    Computes mathematical and statistical features across multi-timeframe candles.
    Enforces Strict No-Lookahead Discipline:
    All features derived from bar [t] are shifted by 1 position (.shift(1)) so
    inference at bar [t+1] uses strictly closed past data.
    """

    def __init__(self, point_value: float = 0.01):
        self.point_value = point_value

    def compute_indicators(self, df: pd.DataFrame, prefix: str = "") -> pd.DataFrame:
        """
        Calculates full suite of technical, statistical and price-action indicators on a single timeframe.
        """
        res = df.copy()
        p = f"{prefix}_" if prefix else ""

        close = res['close']
        high = res['high']
        low = res['low']
        open_ = res['open']
        volume = res['tick_volume']

        # ----------------------------------------------------
        # 1. Exponential Moving Averages (EMA Ribbon)
        # ----------------------------------------------------
        res[f"{p}ema_8"] = close.ewm(span=8, adjust=False).mean()
        res[f"{p}ema_21"] = close.ewm(span=21, adjust=False).mean()
        res[f"{p}ema_55"] = close.ewm(span=55, adjust=False).mean()
        res[f"{p}ema_200"] = close.ewm(span=200, adjust=False).mean()

        # Ribbon spreads and slope
        res[f"{p}ema_spread_8_21"] = (res[f"{p}ema_8"] - res[f"{p}ema_21"]) / self.point_value
        res[f"{p}ema_spread_21_55"] = (res[f"{p}ema_21"] - res[f"{p}ema_55"]) / self.point_value
        res[f"{p}dist_to_ema_200_pct"] = (close - res[f"{p}ema_200"]) / res[f"{p}ema_200"] * 100.0
        res[f"{p}ema_21_slope"] = (res[f"{p}ema_21"] - res[f"{p}ema_21"].shift(3)) / self.point_value

        # ----------------------------------------------------
        # 2. Volatility & ATR (Average True Range)
        # ----------------------------------------------------
        prev_close = close.shift(1)
        tr1 = high - low
        tr2 = (high - prev_close).abs()
        tr3 = (low - prev_close).abs()
        true_range = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)

        res[f"{p}tr"] = true_range
        res[f"{p}atr_14"] = true_range.ewm(span=14, adjust=False).mean()
        res[f"{p}atr_points"] = res[f"{p}atr_14"] / self.point_value
        res[f"{p}natr_pct"] = (res[f"{p}atr_14"] / close) * 100.0

        # Bollinger Bands (20, 2 std)
        sma_20 = close.rolling(window=20).mean()
        std_20 = close.rolling(window=20).std(ddof=0)
        upper_bb = sma_20 + 2.0 * std_20
        lower_bb = sma_20 - 2.0 * std_20
        res[f"{p}bb_bandwidth"] = (upper_bb - lower_bb) / sma_20 * 100.0
        # %B position
        bb_denom = (upper_bb - lower_bb).replace(0, np.nan)
        res[f"{p}bb_pct_b"] = (close - lower_bb) / bb_denom

        # Parkinson Volatility (High-Low extreme value estimator)
        hl_ratio = np.log(high / low.replace(0, np.nan))
        res[f"{p}parkinson_vol_14"] = np.sqrt((hl_ratio ** 2).rolling(window=14).sum() / (4.0 * np.log(2.0) * 14)) * 100.0

        # ----------------------------------------------------
        # 3. Momentum & Relative Strength Index (RSI)
        # ----------------------------------------------------
        delta = close.diff()
        gain = delta.where(delta > 0, 0.0)
        loss = -delta.where(delta < 0, 0.0)
        avg_gain = gain.ewm(alpha=1/14, min_periods=14, adjust=False).mean()
        avg_loss = loss.ewm(alpha=1/14, min_periods=14, adjust=False).mean()
        rs = avg_gain / avg_loss.replace(0, np.nan)
        res[f"{p}rsi_14"] = 100.0 - (100.0 / (1.0 + rs))

        # Rate of Change (ROC)
        res[f"{p}roc_5"] = (close - close.shift(5)) / close.shift(5) * 100.0
        res[f"{p}roc_20"] = (close - close.shift(20)) / close.shift(20) * 100.0

        # MACD (12, 26, 9)
        ema_12 = close.ewm(span=12, adjust=False).mean()
        ema_26 = close.ewm(span=26, adjust=False).mean()
        macd_line = ema_12 - ema_26
        macd_signal = macd_line.ewm(span=9, adjust=False).mean()
        res[f"{p}macd_diff"] = (macd_line - macd_signal) / self.point_value

        # ----------------------------------------------------
        # 4. Price Action & Candle Geometry
        # ----------------------------------------------------
        body_size = (close - open_).abs()
        candle_range = (high - low).replace(0, np.nan)
        upper_wick = high - np.maximum(close, open_)
        lower_wick = np.minimum(close, open_) - low

        res[f"{p}body_to_range_ratio"] = body_size / candle_range
        res[f"{p}upper_wick_ratio"] = upper_wick / candle_range
        res[f"{p}lower_wick_ratio"] = lower_wick / candle_range

        # Pin-bar signatures (wick >= 60% of total range)
        res[f"{p}bullish_pinbar"] = ((lower_wick / candle_range >= 0.60) & (body_size / candle_range <= 0.30)).astype(int)
        res[f"{p}bearish_pinbar"] = ((upper_wick / candle_range >= 0.60) & (body_size / candle_range <= 0.30)).astype(int)

        # ----------------------------------------------------
        # 5. Volume Flow / Tick Pressure
        # ----------------------------------------------------
        vol_sma_20 = volume.rolling(window=20).mean().replace(0, np.nan)
        res[f"{p}volume_ratio"] = volume / vol_sma_20

        return res

    def build_feature_matrix(self, mtf_candles: Dict[str, pd.DataFrame], primary_tf: str = "M15") -> pd.DataFrame:
        """
        Builds the unified feature matrix aligned to the primary decision timeframe.
        Merges higher and lower timeframe features via backward forward-fill (asof join)
        and applies a STRICT lag of 1 period to prevent look-ahead bias.
        """
        if primary_tf not in mtf_candles:
            raise ValueError(f"Primary timeframe {primary_tf} not found in provided candle data.")

        # Compute indicators for primary timeframe
        base_df = self.compute_indicators(mtf_candles[primary_tf], prefix=primary_tf.lower())
        base_df.set_index('time', inplace=False)

        # Process higher/lower timeframes and merge
        merged = base_df.copy()
        merged['merge_time'] = merged['time']

        for tf, df in mtf_candles.items():
            if tf == primary_tf or df.empty:
                continue

            ind_df = self.compute_indicators(df, prefix=tf.lower())
            # Select key summary indicators to keep feature dimension clean & non-collinear
            prefix = tf.lower()
            cols_to_pull = [
                'time',
                f"{prefix}_ema_spread_8_21",
                f"{prefix}_dist_to_ema_200_pct",
                f"{prefix}_atr_points",
                f"{prefix}_rsi_14",
                f"{prefix}_roc_20",
                f"{prefix}_bb_bandwidth"
            ]
            cols_exist = [c for c in cols_to_pull if c in ind_df.columns]
            tf_subset = ind_df[cols_exist].copy()

            # Merge asof (matches latest available historical bar without peeking forward)
            merged = pd.merge_asof(
                merged.sort_values('merge_time'),
                tf_subset.sort_values('time'),
                left_on='merge_time',
                right_on='time',
                direction='backward',
                suffixes=('', f'_{prefix}_merge')
            )

        # Drop temporary merge timestamps
        drop_cols = [c for c in merged.columns if '_merge' in c or c == 'merge_time']
        merged.drop(columns=drop_cols, inplace=True, errors='ignore')

        # ------------------------------------------------------------------
        # STRICT NO-LOOKAHEAD ENFORCEMENT:
        # Separate OHLCV prices from features.
        # Shift all predictive indicators by 1 bar forward.
        # ------------------------------------------------------------------
        price_cols = ['time', 'open', 'high', 'low', 'close', 'tick_volume', 'spread']
        feat_cols = [c for c in merged.columns if c not in price_cols]

        # Shift all feature columns by 1 bar:
        # Bar [t] will hold indicators calculated from Bar [t-1] and earlier.
        merged[feat_cols] = merged[feat_cols].shift(1)

        # Drop warmup rows with NaN from rolling calculations and shifting
        clean_matrix = merged.dropna().reset_index(drop=True)
        return clean_matrix
