"""
Risk Estimation & Volatility Forecaster for XAUUSD.
Computes expected forward volatility, dynamic SL/TP point distances,
Risk-to-Reward parameters, and strictly enforces non-execution advisory limits.
"""

from typing import Dict, Any, Optional
import numpy as np
import pandas as pd

from .config import RiskEstimationConfig


class RiskEstimator:
    """
    Computes quantitative risk bounds for XAUUSD trade setups.
    
    CRITICAL ARCHITECTURAL CONTRACT:
    The AI engine acts exclusively as a Market Intelligence Advisor.
    It NEVER executes trades directly, NEVER overrides the EA's RiskManager,
    and NEVER calculates or alters position lot sizing.
    All bounds are strictly advisory reference points for the Expert Advisor.
    """

    def __init__(self, config: Optional[RiskEstimationConfig] = None, point_value: float = 0.01):
        self.config = config or RiskEstimationConfig()
        self.point_value = point_value

    def estimate_risk_parameters(
        self,
        current_price: float,
        recommendation: str,
        atr_points: float,
        market_regime: str,
        spread_points: float = 25.0,
        recent_swing_high: Optional[float] = None,
        recent_swing_low: Optional[float] = None
    ) -> Dict[str, Any]:
        """
        Calculates suggested Stop Loss and Take Profit distances in points.
        Adapts multipliers according to the active market regime.
        """
        # Regime-dependent multiplier calibration
        if market_regime == "BREAKOUT_EXPANSION":
            sl_atr_mult = 1.8  # Wider cushion to avoid getting wicked out in high momentum
            tp_atr_mult = 2.8  # Allow profits to run on breakout
        elif market_regime == "RANGING_MEAN_REVERT":
            sl_atr_mult = 1.3  # Tighter stop outside range boundary
            tp_atr_mult = 1.8  # Take profit at opposing boundary
        else:  # TRENDING or DEFAULT
            sl_atr_mult = 1.5
            tp_atr_mult = 2.25

        base_sl_dist_points = atr_points * sl_atr_mult
        # Clamp to configured safety limits
        clamped_sl_points = max(
            self.config.min_recommended_sl_points,
            min(self.config.max_recommended_sl_points, base_sl_dist_points)
        )
        # Add spread buffer to stop loss distance
        clamped_sl_points += spread_points

        # Calculate target TP based on target Risk/Reward
        target_rr = max(self.config.risk_reward_ratio_target, tp_atr_mult / sl_atr_mult)
        clamped_tp_points = clamped_sl_points * target_rr

        # Price absolute levels (Reference only)
        if recommendation == "BUY":
            suggested_sl_price = round(current_price - (clamped_sl_points * self.point_value), 2)
            suggested_tp_price = round(current_price + (clamped_tp_points * self.point_value), 2)
        elif recommendation == "SELL":
            suggested_sl_price = round(current_price + (clamped_sl_points * self.point_value), 2)
            suggested_tp_price = round(current_price - (clamped_tp_points * self.point_value), 2)
        else:  # NO_TRADE
            suggested_sl_price = None
            suggested_tp_price = None

        # Volatility Risk Score (1 to 10 scale)
        # Normal Gold ATR on M15 is ~15-25 points ($1.50 - $2.50)
        norm_vol_ratio = atr_points / 20.0
        spread_penalty = max(0.0, (spread_points - 25.0) / 10.0)
        raw_risk_score = (norm_vol_ratio * 4.5) + (spread_penalty * 2.0)
        if market_regime == "ABNORMAL_VOLATILITY":
            raw_risk_score = 9.8
        risk_score = round(float(np.clip(raw_risk_score, 1.0, 10.0)), 1)

        return {
            "advisory_mode_only": True,
            "ea_override_permitted": False,
            "execution_authority": "MT5_EA_RISK_MANAGER",
            "expected_volatility_points": round(atr_points, 1),
            "expected_volatility_usd_oz": round(atr_points * self.point_value, 2),
            "recommended_sl_distance_points": round(clamped_sl_points, 1),
            "recommended_tp_distance_points": round(clamped_tp_points, 1),
            "suggested_sl_price": suggested_sl_price,
            "suggested_tp_price": suggested_tp_price,
            "risk_reward_ratio": round(target_rr, 2),
            "market_risk_score_10": risk_score,
            "spread_points": spread_points,
            "disclaimer": "All levels are mathematical intelligence references. The EA RiskManager has sole authority over trade placement, sizing, and risk parameters."
        }
