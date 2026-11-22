"""
Configuration Loader and Data Contracts for XAUUSD AI Market Intelligence Engine.
"""

from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional
import os
import yaml


@dataclass
class MT5Config:
    enabled: bool = True
    path: str = ""
    login: int = 0
    password: str = ""
    server: str = ""
    timeout_ms: int = 60000
    historical_bars_load: int = 5000


@dataclass
class MarketStructureConfig:
    swing_pivot_order: int = 5
    fvg_threshold_points: float = 15.0
    liquidity_sweep_lookback: int = 50


@dataclass
class RegimeConfig:
    adx_trend_threshold: float = 25.0
    bb_squeeze_percentile: float = 20.0
    abnormal_volatility_multiplier: float = 2.8
    abnormal_spread_points: float = 60.0


@dataclass
class TripleBarrierConfig:
    pt_atr_mult: float = 2.0
    sl_atr_mult: float = 1.5
    max_holding_bars: int = 12


@dataclass
class AlphaModelConfig:
    prediction_horizon_bars: int = 8
    min_confidence_threshold: float = 0.65
    triple_barrier: TripleBarrierConfig = field(default_factory=TripleBarrierConfig)
    model_type: str = "HistGradientBoosting"
    probability_calibration: str = "isotonic"


@dataclass
class RiskEstimationConfig:
    atr_period: int = 14
    risk_reward_ratio_target: float = 1.5
    max_recommended_sl_points: float = 180.0
    min_recommended_sl_points: float = 30.0


@dataclass
class ValidationConfig:
    n_walk_forward_splits: int = 5
    train_window_bars: int = 2500
    test_window_bars: int = 500
    embargo_pct: float = 0.02


@dataclass
class BridgeConfig:
    mode: str = "both"
    file_path: str = "MQL5/Files/xauusd_ai_signals.json"
    api_host: str = "127.0.0.1"
    api_port: int = 8000
    heartbeat_interval_sec: int = 5
    stale_data_timeout_sec: int = 20


@dataclass
class AppConfig:
    symbol: str = "XAUUSD"
    point_value: float = 0.01
    lot_size: float = 100.0
    execution_tf: str = "M1"
    structure_tfs: List[str] = field(default_factory=lambda: ["M1", "M5", "M15", "H1"])
    primary_alpha_tf: str = "M15"
    mt5: MT5Config = field(default_factory=MT5Config)
    market_structure: MarketStructureConfig = field(default_factory=MarketStructureConfig)
    regime_detection: RegimeConfig = field(default_factory=RegimeConfig)
    alpha_model: AlphaModelConfig = field(default_factory=AlphaModelConfig)
    risk_estimation: RiskEstimationConfig = field(default_factory=RiskEstimationConfig)
    validation: ValidationConfig = field(default_factory=ValidationConfig)
    bridge: BridgeConfig = field(default_factory=BridgeConfig)


def load_config(config_path: Optional[str] = None) -> AppConfig:
    """Load configuration from YAML file or return robust defaults."""
    if config_path is None:
        base_dir = os.path.dirname(os.path.abspath(__file__))
        config_path = os.path.join(base_dir, "config.yaml")

    if not os.path.exists(config_path):
        return AppConfig()

    try:
        with open(config_path, "r", encoding="utf-8") as f:
            raw_cfg = yaml.safe_load(f) or {}

        mt5_cfg = MT5Config(**raw_cfg.get("mt5", {}))
        ms_cfg = MarketStructureConfig(**raw_cfg.get("market_structure", {}))
        reg_cfg = RegimeConfig(**raw_cfg.get("regime_detection", {}))
        
        alpha_raw = raw_cfg.get("alpha_model", {})
        tb_raw = alpha_raw.pop("triple_barrier", {})
        tb_cfg = TripleBarrierConfig(**tb_raw)
        alpha_cfg = AlphaModelConfig(triple_barrier=tb_cfg, **alpha_raw)
        
        risk_cfg = RiskEstimationConfig(**raw_cfg.get("risk_estimation", {}))
        val_cfg = ValidationConfig(**raw_cfg.get("validation", {}))
        bridge_cfg = BridgeConfig(**raw_cfg.get("bridge", {}))

        tf_raw = raw_cfg.get("timeframes", {})

        return AppConfig(
            symbol=raw_cfg.get("symbol", "XAUUSD"),
            point_value=raw_cfg.get("point_value", 0.01),
            lot_size=raw_cfg.get("lot_size", 100.0),
            execution_tf=tf_raw.get("execution_tf", "M1"),
            structure_tfs=tf_raw.get("structure_tfs", ["M1", "M5", "M15", "H1"]),
            primary_alpha_tf=tf_raw.get("primary_alpha_tf", "M15"),
            mt5=mt5_cfg,
            market_structure=ms_cfg,
            regime_detection=reg_cfg,
            alpha_model=alpha_cfg,
            risk_estimation=risk_cfg,
            validation=val_cfg,
            bridge=bridge_cfg
        )
    except Exception as e:
        print(f"[Config] Warning: Failed to parse {config_path} ({e}), using default configuration.")
        return AppConfig()
