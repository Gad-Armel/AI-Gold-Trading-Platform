"""
Training & Walk-Forward Validation Script for XAUUSD AI Market Intelligence Engine.
Executes data ingestion, feature generation, regime mapping, purged walk-forward
cross-validation with embargo, baseline benchmarking, and model artifact serialization.
"""

import sys
import os
import argparse
import logging
import json
import pandas as pd

from .config import load_config
from .data_loader import MT5DataLoader
from .market_structure import MarketStructureAnalyzer
from .feature_engineering import FeatureEngineer
from .regime_classifier import RegimeClassifier
from .alpha_model import AlphaOpportunityEvaluator
from .walk_forward_validator import PurgedWalkForwardValidator
from .model_registry import ModelRegistry

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("TrainPipeline")


def run_training_pipeline(bars_count: int = 3500, config_path: str = None) -> dict:
    """Executes full quantitative training and benchmark pipeline."""
    logger.info("Initializing XAUUSD AI Training Pipeline...")
    cfg = load_config(config_path)

    # 1. Ingest Data
    loader = MT5DataLoader(cfg)
    loader.connect()
    logger.info("Ingesting multi-timeframe candle data (%s bars per timeframe)...", bars_count)
    mtf_data = loader.fetch_multi_timeframe_data(count=bars_count)

    # 2. Market Structure Analysis
    struct_analyzer = MarketStructureAnalyzer(
        pivot_order=cfg.market_structure.swing_pivot_order,
        fvg_threshold_points=cfg.market_structure.fvg_threshold_points
    )
    mtf_struct = struct_analyzer.analyze_multi_timeframe(mtf_data)
    logger.info("Multi-Timeframe Structure Bias: %s (Score: %s)",
                mtf_struct.get("confluence_bias"), mtf_struct.get("multi_timeframe_alignment_score"))

    # 3. Feature Engineering with Strict 1-Bar Lag
    engineer = FeatureEngineer(point_value=cfg.point_value)
    logger.info("Engineering multi-timeframe indicators with strict no-lookahead lag...")
    feature_matrix = engineer.build_feature_matrix(mtf_data, primary_tf=cfg.primary_alpha_tf)
    logger.info("Clean Feature Matrix: %d rows x %d columns", len(feature_matrix), len(feature_matrix.columns))

    # 4. Market Regime Classification
    regime_clf = RegimeClassifier(
        adx_trend_threshold=cfg.regime_detection.adx_trend_threshold,
        bb_squeeze_percentile=cfg.regime_detection.bb_squeeze_percentile,
        abnormal_volatility_multiplier=cfg.regime_detection.abnormal_volatility_multiplier,
        abnormal_spread_points=cfg.regime_detection.abnormal_spread_points,
        point_value=cfg.point_value
    )
    feature_matrix = regime_clf.classify_series(feature_matrix)
    regime_dist = feature_matrix['market_regime'].value_counts().to_dict()
    logger.info("Market Regime Distribution: %s", regime_dist)

    # 5. Purged Walk-Forward Cross-Validation & Baseline Benchmarking
    validator = PurgedWalkForwardValidator(
        n_splits=cfg.validation.n_walk_forward_splits,
        embargo_pct=cfg.validation.embargo_pct,
        horizon_bars=cfg.alpha_model.prediction_horizon_bars
    )
    logger.info("Executing Purged Walk-Forward Validation (%d folds, embargo: %.1f%%)...",
                cfg.validation.n_walk_forward_splits, cfg.validation.embargo_pct * 100)
    validation_results = validator.run_benchmark_comparison(feature_matrix)

    # 6. Fit Final Production Model on Full Historical Dataset
    logger.info("Training final calibrated production model on full dataset...")
    feature_cols = [c for c in feature_matrix.columns if c not in [
        'time', 'open', 'high', 'low', 'close', 'tick_volume', 'spread', 'market_regime', 'regime_confidence', 'target_label'
    ]]
    
    final_evaluator = AlphaOpportunityEvaluator(cfg.alpha_model)
    target_series = final_evaluator.generate_triple_barrier_labels(
        feature_matrix,
        horizon_bars=cfg.alpha_model.prediction_horizon_bars,
        pt_atr_mult=cfg.alpha_model.triple_barrier.pt_atr_mult,
        sl_atr_mult=cfg.alpha_model.triple_barrier.sl_atr_mult
    )
    final_evaluator.train(feature_matrix[feature_cols], target_series)

    # 7. Model Versioning & Registry Serialization
    registry = ModelRegistry()
    metadata = {
        "model_type": cfg.alpha_model.model_type,
        "probability_calibration": cfg.alpha_model.probability_calibration,
        "features_count": len(feature_cols),
        "feature_names": feature_cols,
        "bars_trained": len(feature_matrix),
        "primary_timeframe": cfg.primary_alpha_tf
    }
    saved_path = registry.save_model_version(
        model_obj=final_evaluator,
        version_tag="prod_v1",
        metadata=metadata,
        metrics=validation_results["performance_comparison"]
    )
    logger.info("Production model saved successfully to: %s", saved_path)

    # Print summary performance table
    print("\n" + "="*80)
    print("XAUUSD QUANTITATIVE OUT-OF-SAMPLE PERFORMANCE COMPARISON")
    print("="*80)
    comp = validation_results["performance_comparison"]
    print(f"{'Strategy':<36} | {'Return %':<10} | {'Max DD %':<10} | {'Sharpe':<8} | {'Win Rate %':<10} | {'Profit Factor':<12}")
    print("-" * 96)
    for k, strat in comp.items():
        print(f"{strat['name']:<36} | {strat['total_return_pct']:<10.2f} | {strat['max_drawdown_pct']:<10.2f} | {strat['sharpe_ratio']:<8.2f} | {strat['win_rate_pct']:<10.1f} | {strat['profit_factor']:<12.2f}")
    print("="*80 + "\n")

    return {
        "saved_path": saved_path,
        "validation_results": validation_results,
        "mtf_structure": mtf_struct,
        "features_count": len(feature_cols),
        "total_bars": len(feature_matrix)
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Train XAUUSD AI Market Intelligence Engine")
    parser.add_argument("--bars", type=int, default=3000, help="Number of historical bars to load")
    parser.add_argument("--config", type=str, default=None, help="Path to config.yaml")
    args = parser.parse_args()

    run_training_pipeline(bars_count=args.bars, config_path=args.config)
