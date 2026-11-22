"""
Machine Learning Opportunity Evaluator & Calibrated Alpha Model for XAUUSD.
Uses Triple-Barrier labeling, HistGradientBoosting / Random Forest ensembles,
and Probability Calibration to issue BUY, SELL, or NO_TRADE recommendations.
"""

from typing import Dict, Any, List, Optional, Tuple
import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingClassifier, RandomForestClassifier
from sklearn.calibration import CalibratedClassifierCV
from sklearn.preprocessing import StandardScaler
from sklearn.metrics import classification_report, brier_score_loss, log_loss
import joblib

from .config import AlphaModelConfig


class AlphaOpportunityEvaluator:
    """
    Evaluates forward trade opportunities on XAUUSD.
    Labels bars using the Marcos Lopez de Prado Triple-Barrier Method:
    - Upper Barrier: Profit Target = entry + (pt_mult * ATR)
    - Lower Barrier: Stop Loss = entry - (sl_mult * ATR)
    - Vertical Barrier: Max holding horizon in bars
    """

    CLASS_LABELS = {0: "NO_TRADE", 1: "BUY", 2: "SELL"}
    INVERSE_LABELS = {"NO_TRADE": 0, "BUY": 1, "SELL": 2}

    def __init__(self, config: Optional[AlphaModelConfig] = None):
        self.config = config or AlphaModelConfig()
        self.scaler = StandardScaler()
        self.base_model = None
        self.calibrated_model = None
        self.feature_names: List[str] = []
        self.is_trained = False

    def generate_triple_barrier_labels(
        self,
        df: pd.DataFrame,
        horizon_bars: int = 8,
        pt_atr_mult: float = 2.0,
        sl_atr_mult: float = 1.5,
        atr_col: str = "m15_atr_points",
        point_value: float = 0.01
    ) -> pd.Series:
        """
        Applies causal triple-barrier labeling on historical dataframe.
        Returns Series of integers: 1 (BUY edge), 2 (SELL edge), 0 (Neutral / NO_TRADE).
        """
        n = len(df)
        labels = np.zeros(n, dtype=int)
        closes = df['close'].values
        highs = df['high'].values
        lows = df['low'].values
        atrs = (df[atr_col].values * point_value) if atr_col in df.columns else (closes * 0.003)

        for i in range(n - horizon_bars):
            entry_p = closes[i]
            bar_atr = max(atrs[i], entry_p * 0.001)

            pt_dist = pt_atr_mult * bar_atr
            sl_dist = sl_atr_mult * bar_atr

            # Barrier levels for Long and Short
            long_pt = entry_p + pt_dist
            long_sl = entry_p - sl_dist

            short_pt = entry_p - pt_dist
            short_sl = entry_p + sl_dist

            long_hit_pt = False
            long_hit_sl = False
            short_hit_pt = False
            short_hit_sl = False

            # Scan path through the vertical barrier
            for step in range(1, horizon_bars + 1):
                idx = i + step
                bar_h = highs[idx]
                bar_l = lows[idx]

                # Long check
                if bar_h >= long_pt and not long_hit_sl:
                    long_hit_pt = True
                    break
                if bar_l <= long_sl:
                    long_hit_sl = True

                # Short check
                if bar_l <= short_pt and not short_hit_sl:
                    short_hit_pt = True
                    break
                if bar_h >= short_sl:
                    short_hit_sl = True

            if long_hit_pt and not long_hit_sl:
                labels[i] = 1  # BUY edge
            elif short_hit_pt and not short_hit_sl:
                labels[i] = 2  # SELL edge
            else:
                labels[i] = 0  # NO_TRADE / Churn

        return pd.Series(labels, index=df.index, name="target_label")

    def train(self, X_train: pd.DataFrame, y_train: pd.Series) -> Dict[str, Any]:
        """
        Fits base gradient boosting ensemble and applies probability calibration (isotonic or sigmoid).
        Strictly fits scaler ONLY on X_train.
        """
        self.feature_names = list(X_train.columns)
        X_scaled = self.scaler.fit_transform(X_train)

        # Base tree ensemble
        if self.config.model_type == "RandomForest":
            base = RandomForestClassifier(
                n_estimators=120,
                max_depth=6,
                min_samples_split=20,
                random_state=42,
                class_weight='balanced',
                n_jobs=-1
            )
        else:
            base = HistGradientBoostingClassifier(
                max_iter=100,
                max_depth=5,
                min_samples_leaf=15,
                l2_regularization=1.5,
                random_state=42,
                class_weight='balanced'
            )

        # Wrap in probability calibration
        cal_method = self.config.probability_calibration if self.config.probability_calibration in ["isotonic", "sigmoid"] else "sigmoid"
        self.calibrated_model = CalibratedClassifierCV(estimator=base, method=cal_method, cv=3)
        self.calibrated_model.fit(X_scaled, y_train)
        self.is_trained = True

        # Train set diagnostics
        train_probs = self.calibrated_model.predict_proba(X_scaled)
        train_preds = self.calibrated_model.predict(X_scaled)

        return {
            "status": "success",
            "model_type": self.config.model_type,
            "calibration": cal_method,
            "features_count": len(self.feature_names),
            "samples_count": len(X_train),
            "classes": [self.CLASS_LABELS.get(c, str(c)) for c in self.calibrated_model.classes_]
        }

    def predict_opportunity(self, feature_row: pd.Series, market_regime: str = "TRENDING_BULL") -> Dict[str, Any]:
        """
        Generates calibrated recommendation (BUY, SELL, or NO_TRADE) for a single live observation.
        Rejects trades if:
        1. Market Regime is ABNORMAL_VOLATILITY (safety filter)
        2. Maximum calibrated class probability is below min_confidence_threshold
        3. Model is uninitialized
        """
        if not self.is_trained or self.calibrated_model is None:
            return {
                "recommendation": "NO_TRADE",
                "confidence": 0.0,
                "reason": "Model not trained or calibrator unavailable",
                "probabilities": {"NO_TRADE": 1.0, "BUY": 0.0, "SELL": 0.0}
            }

        # Safety Guard 1: Abnormal Volatility regime vetoes trade signals
        if market_regime == "ABNORMAL_VOLATILITY":
            return {
                "recommendation": "NO_TRADE",
                "confidence": 0.95,
                "reason": "Abnormal volatility regime active. Risk manager prohibition.",
                "probabilities": {"NO_TRADE": 1.0, "BUY": 0.0, "SELL": 0.0}
            }

        # Align features
        feats = []
        for f in self.feature_names:
            feats.append(float(feature_row.get(f, 0.0)))
        
        X_vec = np.array(feats).reshape(1, -1)
        # Handle nan/inf
        X_vec = np.nan_to_num(X_vec, nan=0.0, posinf=1.0, neginf=-1.0)
        X_scaled = self.scaler.transform(X_vec)

        probs = self.calibrated_model.predict_proba(X_scaled)[0]
        classes = self.calibrated_model.classes_

        prob_map = {self.CLASS_LABELS.get(c, "UNKNOWN"): float(p) for c, p in zip(classes, probs)}
        
        buy_prob = prob_map.get("BUY", 0.0)
        sell_prob = prob_map.get("SELL", 0.0)
        no_trade_prob = prob_map.get("NO_TRADE", 0.0)

        # Regimes directional synergy check
        if market_regime == "TRENDING_BEAR" and buy_prob > sell_prob:
            # Discount counter-trend signals in strong trending regimes
            buy_prob *= 0.80
        elif market_regime == "TRENDING_BULL" and sell_prob > buy_prob:
            sell_prob *= 0.80

        threshold = self.config.min_confidence_threshold

        if buy_prob > threshold and buy_prob > sell_prob:
            rec = "BUY"
            conf = buy_prob
            reason = f"Calibrated Buy Probability ({buy_prob:.1%}) exceeds threshold ({threshold:.1%})"
        elif sell_prob > threshold and sell_prob > buy_prob:
            rec = "SELL"
            conf = sell_prob
            reason = f"Calibrated Sell Probability ({sell_prob:.1%}) exceeds threshold ({threshold:.1%})"
        else:
            rec = "NO_TRADE"
            conf = max(no_trade_prob, 1.0 - max(buy_prob, sell_prob))
            reason = f"No direction meets minimum confidence threshold ({threshold:.1%}). Edge uncertain."

        return {
            "recommendation": rec,
            "confidence": round(conf, 4),
            "reason": reason,
            "probabilities": {
                "BUY": round(buy_prob, 4),
                "SELL": round(sell_prob, 4),
                "NO_TRADE": round(no_trade_prob, 4)
            }
        }
