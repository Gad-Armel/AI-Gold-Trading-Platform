# XAUUSD AI Market Intelligence Engine

An institutional-grade quantitative research, machine learning, and multi-timeframe market intelligence system dedicated to **XAUUSD (Gold)** trading with **MetaTrader 5**.

---

## 1. Executive Summary & Design Philosophy

The **XAUUSD AI Market Intelligence Engine** operates as an asynchronous, advisory intelligence provider for algorithmic execution systems. It bridges high-dimensional statistical machine learning with low-latency MetaTrader 5 execution via:
1. **Asynchronous File-Based IPC Bridge** (`xauusd_ai_signals.json` via atomic rename)
2. **Local Low-Latency REST API Bridge** (`GET /api/v1/market-intelligence` via MT5 `WebRequest`)

### Critical Operational Guarantees
- **No Direct Trade Execution**: The AI Engine **never** opens, modifies, or closes trades directly.
- **Native RiskManager Supremacy**: The MT5 Expert Advisor's native `RiskManager` holds absolute authority over account risk %, lot sizing, margin limits, and order placement.
- **Fail-Safe Offline Autonomy**: If the Python AI service is disconnected, lagging, or unreachable, the MT5 EA automatically falls back to its independent native Donchian/EMA breakout strategy without interruption or capital risk.
- **Zero Look-Ahead Bias**: All features are strictly calculated on closed historical bars and shifted forward by at least 1 bar (`shift(1)`). Cross-validation utilizes **Purged Walk-Forward TimeSeriesSplit with Embargo**.

---

## 2. Quantitative Architecture

```
[MetaTrader 5 Terminal / Feed]
             │
             ▼
   [MT5DataLoader] ─── (Real MT5 API or High-Fidelity Merton Jump Diffusion Simulator)
             │
   ┌─────────┴───────────────────────────────┐
   │                                         │
   ▼                                         ▼
[MarketStructureAnalyzer]           [FeatureEngineer]
• M1, M5, M15, H1 Swings             • EMA Ribbons (8/21/55/200)
• Break of Structure (BOS)          • Volatility (ATR, Parkinson, BBW)
• Change of Character (CHoCH)       • Momentum (RSI, ROC, MACD)
• Fair Value Gaps (FVG)              • Price Action & Candle Wicks
• Liquidity Sweeps                  • STRICT shift(1) Anti-Leakage
   │                                         │
   └─────────┬───────────────────────────────┘
             │
             ▼
    [RegimeClassifier]
    • TRENDING_BULL / TRENDING_BEAR
    • RANGING_MEAN_REVERT
    • BREAKOUT_EXPANSION
    • ABNORMAL_VOLATILITY (Forced Trade Veto)
             │
             ▼
  [AlphaOpportunityEvaluator]
  • Triple-Barrier Labeling (Profit Target, Stop Loss, Horizon)
  • Calibrated Ensemble (HistGradientBoosting / Random Forest)
  • Output: BUY / SELL / NO_TRADE + Calibrated Probability
             │
             ▼
      [RiskEstimator]
      • Expected Volatility in Points ($0.01 = 1 pt)
      • Dynamic SL/TP Bounds & Risk-Reward Ratio
      • Explicit `ea_override_permitted: false` Flag
             │
             ▼
 ┌───────────────────────┐
 │ Communication Bridges │
 ├───────────────────────┤
 │ 1. Atomic File IPC    │ ───► MQL5/Files/xauusd_ai_signals.json
 │ 2. Local REST API     │ ───► http://127.0.0.1:8000/api/v1/...
 └───────────────────────┘
             │
             ▼
 [MT5 Expert Advisor (XAUUSD_AI_Sentinel.mq5)]
  ├── Reads signals + verifies data freshness (< 20s)
  ├── Enforces Native Account Risk % & Lot Sizing
  └── Falls back to Native Donchian/EMA Strategy if offline
```

---

## 3. Market Regimes & Alpha Strategy

| Market Regime | Detection Conditions | Strategy Orientation |
| :--- | :--- | :--- |
| `TRENDING_BULL` | EMA 8 > 21 > 55, Distance to 200 EMA > +0.15%, RSI > 52 | Momentum Trend-Following Buy |
| `TRENDING_BEAR` | EMA 8 < 21 < 55, Distance to 200 EMA < -0.15%, RSI < 48 | Momentum Trend-Following Sell |
| `RANGING_MEAN_REVERT` | BB Bandwidth in lowest 20th percentile, ADX < 20, Neutral Swings | Boundary Mean Reversion |
| `BREAKOUT_EXPANSION` | ATR > 1.4x rolling median, BBW > 1.5x median, ROC > 0.45% | Volatility Breakout Continuation |
| `ABNORMAL_VOLATILITY` | ATR > 2.8x median, Spread > 60 pts, or flash surge | **MANDATORY NO_TRADE / VETO** |

---

## 4. Anti-Leakage & Validation Methodology

1. **Causal Indicator Lag**:
   Every indicator calculated at bar $t$ reflects closed information from bar $t-1$ or earlier. The unclosed bar is never passed to the inference pipeline.
2. **Purged Walk-Forward TimeSeriesSplit**:
   When training, labels are generated using a forward horizon of $H$ bars. Any training sample within $H$ bars of the test partition is **purged** to eliminate overlap.
3. **Embargo Buffer**:
   An embargo period (2% of samples) immediately follows test partitions before subsequent training folds to prevent autoregressive serial correlation leakage.
4. **Scaler Isolation**:
   Feature scalers (`StandardScaler`) are fit strictly on training fold data and applied to test fold data.

---

## 5. Directory Structure

```
python_engine/
├── __init__.py
├── config.py                 # Dataclasses & config parser
├── config.yaml               # Engine parameters
├── data_loader.py            # MT5 connector & Gold market simulator
├── market_structure.py       # Multi-timeframe swings, BOS, CHoCH, FVGs
├── feature_engineering.py    # Lagged multi-timeframe indicators
├── regime_classifier.py      # 5-state statistical regime detector
├── alpha_model.py            # Calibrated opportunity evaluator
├── risk_estimator.py         # Dynamic SL/TP and volatility bounds
├── walk_forward_validator.py # Purged walk-forward CV vs 3 baselines
├── model_registry.py         # Model artifacts & prediction audit logger
├── file_bridge.py            # Atomic file IPC writer
├── api_bridge.py             # Local HTTP REST server
├── train.py                  # Standalone training script
├── inference.py              # Real-time daemon
├── requirements.txt          # Python dependencies
├── README.md                 # Complete documentation
└── mql5/
    └── XAUUSD_AI_Sentinel.mq5 # Expert Advisor source
```

---

## 6. Installation & Quick Start

### Step 1: Install Dependencies
```bash
cd python_engine
pip install -r requirements.txt
```

### Step 2: Configure MT5 Terminal
Edit `python_engine/config.yaml`:
```yaml
symbol: "XAUUSD"
mt5:
  enabled: true
  login: 12345678       # Your MT5 account number
  password: "your_password"
  server: "YourBroker-Server"
```
*Note: On Linux or macOS, the engine automatically runs in simulated Gold mode with empirical Merton Jump Diffusion dynamics.*

### Step 3: Run Purged Walk-Forward Cross-Validation
```bash
python -m python_engine.train --bars 3500
```

### Step 4: Launch Real-Time Inference Daemon
```bash
python -m python_engine.inference --interval 5
```

### Step 5: Setup MetaTrader 5 Expert Advisor
1. Copy `python_engine/mql5/XAUUSD_AI_Sentinel.mq5` into your MT5 `MQL5/Experts/` folder.
2. Compile in MetaEditor (press `F7`).
3. Attach `XAUUSD_AI_Sentinel` to a `XAUUSD` `M1` or `M15` chart.
4. If using REST API mode, add `http://127.0.0.1:8000` to MT5 `Tools -> Options -> Expert Advisors -> Allow WebRequest for listed URL`.
5. Enable **Algo Trading** in MT5.

---

## 7. Performance Disclosures

Past performance, simulated backtests, and out-of-sample metrics do not guarantee future profitability. Market conditions, slippage, liquidity gaps, and macroeconomic announcements can significantly affect real execution. The AI Engine is strictly a mathematical decision-support system.
