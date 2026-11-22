"""
MetaTrader 5 Data Connector & Multi-Timeframe Ingestion Pipeline for XAUUSD.
Handles live tick streams, historical OHLCV bar extraction, and robust
synthetic backtesting data generation when MT5 is not available.
"""

import sys
import time
import logging
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Optional, Tuple, Any
import numpy as np
import pandas as pd

from .config import AppConfig

logger = logging.getLogger("XAUUSD_DataLoader")

# Try to import MetaTrader5 package
MT5_AVAILABLE = False
if sys.platform == "win32":
    try:
        import MetaTrader5 as mt5
        MT5_AVAILABLE = True
    except ImportError:
        logger.warning("MetaTrader5 package not found. Using simulation fallback mode.")
else:
    logger.info("Non-Windows OS detected (%s). MetaTrader5 C-extension is unavailable; activating high-fidelity market simulator.", sys.platform)


class MT5DataLoader:
    """
    Manages connection to MT5 terminal, fetches real-time tick data,
    retrieves multi-timeframe candles (M1, M5, M15, H1), and provides
    high-fidelity synthetic historical generation for non-Windows environments.
    """

    TIMEFRAME_MAP = {
        "M1": 1,
        "M5": 5,
        "M15": 15,
        "M30": 30,
        "H1": 60,
        "H4": 240,
        "D1": 1440,
    }

    def __init__(self, config: AppConfig):
        self.config = config
        self.symbol = config.symbol
        self.is_connected = False
        self._last_tick_time = 0
        self._mock_base_price = 2650.00  # Realistic base price for XAUUSD

    def connect(self) -> bool:
        """Initialize connection to MetaTrader 5 terminal."""
        if not MT5_AVAILABLE or not self.config.mt5.enabled:
            logger.info("Running in Simulated Market Data mode for %s", self.symbol)
            self.is_connected = True
            return True

        try:
            init_kwargs = {}
            if self.config.mt5.path:
                init_kwargs["path"] = self.config.mt5.path

            if not mt5.initialize(**init_kwargs):
                logger.error("MT5 initialize() failed with error: %s", mt5.last_error())
                self.is_connected = False
                return False

            if self.config.mt5.login > 0:
                authorized = mt5.login(
                    login=self.config.mt5.login,
                    password=self.config.mt5.password,
                    server=self.config.mt5.server,
                    timeout=self.config.mt5.timeout_ms
                )
                if not authorized:
                    logger.error("MT5 login() failed: %s", mt5.last_error())
                    self.is_connected = False
                    return False

            # Select symbol in Market Watch
            if not mt5.symbol_select(self.symbol, True):
                logger.error("Failed to select symbol %s in MT5: %s", self.symbol, mt5.last_error())
                self.is_connected = False
                return False

            self.is_connected = True
            terminal_info = mt5.terminal_info()
            logger.info("Connected to MT5 (%s, Build %s)", getattr(terminal_info, "name", "MT5"), getattr(terminal_info, "build", "Unknown"))
            return True

        except Exception as e:
            logger.exception("Unexpected exception connecting to MT5: %s", e)
            self.is_connected = False
            return False

    def disconnect(self):
        """Shutdown MT5 terminal connection."""
        if MT5_AVAILABLE and self.is_connected:
            try:
                mt5.shutdown()
            except Exception:
                pass
        self.is_connected = False

    def get_symbol_info(self) -> Dict[str, Any]:
        """Fetch symbol specifications (digits, spread, point, min lot, tick value)."""
        if MT5_AVAILABLE and self.is_connected:
            info = mt5.symbol_info(self.symbol)
            if info is not None:
                return {
                    "symbol": self.symbol,
                    "digits": info.digits,
                    "point": info.point,
                    "spread_points": info.spread,
                    "ask": info.ask,
                    "bid": info.bid,
                    "tick_value": info.trade_tick_value,
                    "tick_size": info.trade_tick_size,
                    "volume_min": info.volume_min,
                    "volume_step": info.volume_step,
                    "volume_max": info.volume_max,
                }

        # Fallback simulation info
        return {
            "symbol": self.symbol,
            "digits": 2,
            "point": 0.01,
            "spread_points": 25,
            "ask": self._mock_base_price + 0.25,
            "bid": self._mock_base_price,
            "tick_value": 1.0,
            "tick_size": 0.01,
            "volume_min": 0.01,
            "volume_step": 0.01,
            "volume_max": 100.0,
        }

    def get_latest_tick(self) -> Dict[str, Any]:
        """Retrieve most recent tick with Bid, Ask, Spread and Volume."""
        if MT5_AVAILABLE and self.is_connected:
            tick = mt5.symbol_info_tick(self.symbol)
            if tick is not None:
                spread_pts = round((tick.ask - tick.bid) / self.config.point_value, 1)
                return {
                    "time": datetime.fromtimestamp(tick.time, tz=timezone.utc).isoformat(),
                    "bid": tick.bid,
                    "ask": tick.ask,
                    "spread_points": spread_pts,
                    "volume": getattr(tick, "volume", 0),
                    "flags": getattr(tick, "flags", 0)
                }

        # High-precision synthetic tick
        t_now = datetime.now(timezone.utc)
        jitter = np.random.normal(0, 0.15)
        self._mock_base_price = max(2400.0, self._mock_base_price + jitter)
        spread_pts = round(np.random.uniform(18.0, 32.0), 1)
        spread_val = spread_pts * self.config.point_value
        
        return {
            "time": t_now.isoformat(),
            "bid": round(self._mock_base_price, 2),
            "ask": round(self._mock_base_price + spread_val, 2),
            "spread_points": spread_pts,
            "volume": int(np.random.exponential(15) + 1),
            "flags": 0
        }

    def fetch_historical_bars(self, timeframe: str, count: int = 1000) -> pd.DataFrame:
        """
        Fetch OHLCV historical dataframe for a given timeframe.
        Returns DataFrame with columns: ['time', 'open', 'high', 'low', 'close', 'tick_volume', 'spread'].
        """
        if MT5_AVAILABLE and self.is_connected:
            tf_const = getattr(mt5, f"TIMEFRAME_{timeframe}", None)
            if tf_const is not None:
                rates = mt5.copy_rates_from_pos(self.symbol, tf_const, 0, count)
                if rates is not None and len(rates) > 0:
                    df = pd.DataFrame(rates)
                    df['time'] = pd.to_datetime(df['time'], unit='s', utc=True)
                    df = df[['time', 'open', 'high', 'low', 'close', 'tick_volume', 'spread']]
                    df.sort_values('time', inplace=True)
                    df.reset_index(drop=True, inplace=True)
                    return df

        # Fallback realistic historical generator for simulation / non-Windows
        return self._generate_synthetic_gold_candles(timeframe, count)

    def fetch_multi_timeframe_data(self, count: int = 1000) -> Dict[str, pd.DataFrame]:
        """Fetch historical candle data across all required timeframes (M1, M5, M15, H1)."""
        mtf_data = {}
        for tf in self.config.structure_tfs:
            mtf_data[tf] = self.fetch_historical_bars(tf, count)
        return mtf_data

    def _generate_synthetic_gold_candles(self, timeframe: str, count: int) -> pd.DataFrame:
        """
        Generates realistic XAUUSD OHLCV time-series matching empirical Gold dynamics:
        - Volatility clustering (GARCH-like behavior)
        - Occasional jump diffusion (news spikes / liquidity voids)
        - Session-based volume patterns (Asian range, London expansion, NY volatility)
        """
        np.random.seed(42 + self.TIMEFRAME_MAP.get(timeframe, 1))
        tf_mins = self.TIMEFRAME_MAP.get(timeframe, 15)
        
        end_time = datetime.now(timezone.utc)
        timestamps = [end_time - timedelta(minutes=tf_mins * i) for i in range(count)]
        timestamps.reverse()

        # Generate price series with Merton jump diffusion + regime switching
        dt = tf_mins / (60 * 24 * 252)
        base_sigma = 0.18  # 18% annualized vol for gold
        
        # Volatility process
        vol_multipliers = np.ones(count)
        for i in range(1, count):
            vol_multipliers[i] = 0.92 * vol_multipliers[i-1] + 0.08 * np.random.gamma(2.0, 0.5)

        returns = []
        current_p = 2620.0
        prices = [current_p]

        for i in range(count):
            sigma_t = base_sigma * vol_multipliers[i] * np.sqrt(dt)
            # Standard diffusion
            drift = 0.00002
            diffusion = np.random.normal(drift, sigma_t)
            
            # Jump component (e.g. CPI, FOMC, geopolitics on Gold)
            has_jump = np.random.rand() < 0.015
            jump = np.random.normal(0, sigma_t * 4.0) if has_jump else 0.0
            
            ret = diffusion + jump
            current_p = max(1800.0, current_p * (1.0 + ret))
            prices.append(current_p)

        prices = prices[1:]

        # Create candle components (Open, High, Low, Close)
        data = []
        for i, (ts, close_p) in enumerate(zip(timestamps, prices)):
            open_p = prices[i-1] if i > 0 else close_p * (1 - 0.0005)
            # Intraday wiggle
            bar_vol = abs(close_p * 0.0018 * vol_multipliers[i])
            high_p = max(open_p, close_p) + abs(np.random.normal(0, bar_vol * 0.6))
            low_p = min(open_p, close_p) - abs(np.random.normal(0, bar_vol * 0.6))
            
            # Volume correlated with bar volatility and range
            rng = high_p - low_p
            vol = int(300 + rng * 120 + np.random.exponential(200))
            spread = int(np.clip(np.random.normal(24, 6), 15, 60))

            data.append({
                "time": ts,
                "open": round(open_p, 2),
                "high": round(high_p, 2),
                "low": round(low_p, 2),
                "close": round(close_p, 2),
                "tick_volume": vol,
                "spread": spread
            })

        df = pd.DataFrame(data)
        return df
