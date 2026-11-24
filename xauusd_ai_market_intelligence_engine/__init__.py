"""
XAUUSD AI Market Intelligence Engine
====================================
Quantitative machine learning engine for MetaTrader 5 XAUUSD (Gold) trading.
"""

from .config import AppConfig, load_config
from .data_loader import MT5DataLoader
from .market_structure import MarketStructureAnalyzer
from .feature_engineering import FeatureEngineer
from .regime_classifier import RegimeClassifier, MarketRegime
from .alpha_model import AlphaOpportunityEvaluator
from .risk_estimator import RiskEstimator
from .walk_forward_validator import PurgedWalkForwardValidator
from .model_registry import ModelRegistry
from .file_bridge import MT5FileBridge
from .api_bridge import MT5APIBridgeServer

__version__ = "1.0.0"
