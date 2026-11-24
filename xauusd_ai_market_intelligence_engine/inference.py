"""
Live Real-Time Inference Daemon for XAUUSD Market Intelligence Engine.
Polls live MT5 ticks/candles, evaluates multi-timeframe structures, predicts
market regime & trade opportunity, estimates risk bounds, and broadcasts
structured intelligence via File and REST API bridges.
"""

import sys
import os
import time
import argparse
import logging
from datetime import datetime, timezone
import pandas as pd

from .config import load_config, AppConfig
from .data_loader import MT5DataLoader
from .market_structure import MarketStructureAnalyzer
from .feature_engineering import FeatureEngineer
from .regime_classifier import RegimeClassifier
from .alpha_model import AlphaOpportunityEvaluator
from .risk_estimator import RiskEstimator
from .file_bridge import MT5FileBridge
from .api_bridge import MT5APIBridgeServer, update_intelligence_state
from .model_registry import ModelRegistry

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("InferenceDaemon")


class MarketIntelligenceDaemon:
    """
    Continuous or one-shot inference engine coordinating data ingestion,
    feature extraction, regime mapping, model inference, and bridge publishing.
    """

    def __init__(self, config: AppConfig):
        self.config = config
        self.loader = MT5DataLoader(config)
        self.struct_analyzer = MarketStructureAnalyzer(
            pivot_order=config.market_structure.swing_pivot_order,
            fvg_threshold_points=config.market_structure.fvg_threshold_points
        )
        self.engineer = FeatureEngineer(point_value=config.point_value)
        self.regime_clf = RegimeClassifier(
            adx_trend_threshold=config.regime_detection.adx_trend_threshold,
            bb_squeeze_percentile=config.regime_detection.bb_squeeze_percentile,
            abnormal_volatility_multiplier=config.regime_detection.abnormal_volatility_multiplier,
            abnormal_spread_points=config.regime_detection.abnormal_spread_points,
            point_value=config.point_value
        )
        self.alpha_model = AlphaOpportunityEvaluator(config.alpha_model)
        self.risk_estimator = RiskEstimator(config.risk_estimation, point_value=config.point_value)
        self.file_bridge = MT5FileBridge(target_filepath=config.bridge.file_path)
        self.api_server = MT5APIBridgeServer(host=config.bridge.api_host, port=config.bridge.api_port)
        self.registry = ModelRegistry()
        self.is_running = False

    def warm_up(self, bars_history: int = 1500):
        """Pre-fetches history and trains initial opportunity model if needed."""
        logger.info("Warming up inference daemon with %d historical bars...", bars_history)
        self.loader.connect()
        mtf_data = self.loader.fetch_multi_timeframe_data(count=bars_history)
        feature_matrix = self.engineer.build_feature_matrix(mtf_data, primary_tf=self.config.primary_alpha_tf)
        feature_matrix = self.regime_clf.classify_series(feature_matrix)

        feature_cols = [c for c in feature_matrix.columns if c not in [
            'time', 'open', 'high', 'low', 'close', 'tick_volume', 'spread', 'market_regime', 'regime_confidence', 'target_label'
        ]]

        labels = self.alpha_model.generate_triple_barrier_labels(
            feature_matrix,
            horizon_bars=self.config.alpha_model.prediction_horizon_bars,
            pt_atr_mult=self.config.alpha_model.triple_barrier.pt_atr_mult,
            sl_atr_mult=self.config.alpha_model.triple_barrier.sl_atr_mult
        )
        self.alpha_model.train(feature_matrix[feature_cols], labels)
        logger.info("Warm-up complete. Model calibrated across %d samples.", len(feature_matrix))

    def evaluate_cycle(self) -> dict:
        """Executes a single end-to-end intelligence cycle."""
        # 1. Fetch latest multi-timeframe candles & current tick
        mtf_data = self.loader.fetch_multi_timeframe_data(count=300)
        tick = self.loader.get_latest_tick()
        current_bid = tick["bid"]
        current_ask = tick["ask"]
        spread_pts = tick["spread_points"]
        current_price = round((current_bid + current_ask) / 2.0, 2)

        # 2. Market Structure
        struct_report = self.struct_analyzer.analyze_multi_timeframe(mtf_data)

        # 3. Features
        feature_matrix = self.engineer.build_feature_matrix(mtf_data, primary_tf=self.config.primary_alpha_tf)
        latest_row = feature_matrix.iloc[-1]

        # 4. Regime
        atr_col = f"{self.config.primary_alpha_tf.lower()}_atr_points"
        bbw_col = f"{self.config.primary_alpha_tf.lower()}_bb_bandwidth"
        rolling_atr = feature_matrix[atr_col].tail(50).median() if atr_col in feature_matrix else 20.0
        rolling_bbw = feature_matrix[bbw_col].tail(50).median() if bbw_col in feature_matrix else 0.8

        regime_info = self.regime_clf.classify_bar(latest_row, rolling_atr, rolling_bbw)
        current_regime = regime_info["regime"]

        # 5. Opportunity Recommendation
        opp = self.alpha_model.predict_opportunity(latest_row, market_regime=current_regime)
        signal = opp["recommendation"]
        confidence = opp["confidence"]

        # 6. Risk Parameters (Advisory Only)
        atr_pts = float(latest_row.get(atr_col, 20.0))
        risk_params = self.risk_estimator.estimate_risk_parameters(
            current_price=current_price,
            recommendation=signal,
            atr_points=atr_pts,
            market_regime=current_regime,
            spread_points=spread_pts
        )

        # 7. Assemble Structured Intelligence Payload
        payload = {
            "symbol": self.config.symbol,
            "timestamp_utc": datetime.now(timezone.utc).isoformat(),
            "tick": {
                "bid": current_bid,
                "ask": current_ask,
                "spread_points": spread_pts
            },
            "signal": signal,
            "confidence": confidence,
            "regime": current_regime,
            "regime_details": regime_info,
            "multi_timeframe_structure": struct_report,
            "probabilities": opp["probabilities"],
            "decision_reason": opp["reason"],
            **risk_params,
            "model_version": "XAUUSD_AI_v1.0_PROD",
            "heartbeat": int(time.time()),
            "service_available": True
        }

        # 8. Broadcast to IPC File Bridge & API Server
        if self.config.bridge.mode in ["file", "both"]:
            self.file_bridge.publish_intelligence(payload)

        if self.config.bridge.mode in ["api", "both"]:
            update_intelligence_state(payload)

        # 9. Audit Log
        self.registry.log_live_prediction(payload)

        return payload

    def run_daemon(self, interval_sec: int = 5):
        """Runs the daemon loop."""
        self.warm_up()
        if self.config.bridge.mode in ["api", "both"]:
            self.api_server.start()

        self.is_running = True
        logger.info("Starting live inference loop (poll every %d seconds)...", interval_sec)

        try:
            while self.is_running:
                payload = self.evaluate_cycle()
                logger.info("Intelligence Broadcast: %s | Conf: %.1f%% | Regime: %s | SL: %.1f pts | TP: %.1f pts",
                            payload["signal"], payload["confidence"] * 100, payload["regime"],
                            payload["recommended_sl_distance_points"], payload["recommended_tp_distance_points"])
                time.sleep(interval_sec)
        except KeyboardInterrupt:
            logger.info("Daemon interrupted by user.")
        finally:
            self.stop()

    def stop(self):
        self.is_running = False
        self.api_server.stop()
        self.loader.disconnect()
        logger.info("Inference daemon halted.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run Live XAUUSD Market Intelligence Daemon")
    parser.add_argument("--interval", type=int, default=5, help="Polling interval in seconds")
    parser.add_argument("--config", type=str, default=None, help="Path to config.yaml")
    args = parser.parse_args()

    cfg = load_config(args.config)
    daemon = MarketIntelligenceDaemon(cfg)
    daemon.run_daemon(interval_sec=args.interval)
