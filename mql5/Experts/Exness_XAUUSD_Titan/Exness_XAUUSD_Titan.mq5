//+------------------------------------------------------------------+
//|                                         Exness_XAUUSD_Titan.mq5 |
//|                                  Copyright 2026, Institutional Algo Team |
//|                             Ultimate Institutional MT5 Gold EA    |
//+------------------------------------------------------------------+
#property copyright   "Copyright 2026, Institutional Algo Team"
#property link        "https://www.mql5.com"
#property version     "2.00"
#property description "Ultimate Institutional Expert Advisor for XAUUSD on Exness."
#property description "Combines broker suffix resolution, market structure (BOS/CHOCH), Fair Value Gaps, persistent risk, and optional AI intelligence."

#include "TradeLogger.mqh"
#include "MarketAnalyzer.mqh"
#include "SignalEngine.mqh"
#include "RiskManager.mqh"
#include "ExecutionEngine.mqh"
#include "PositionManager.mqh"

//--- Inputs Group: Broker & Symbol Configuration
input group "=== Broker & Symbol Configuration ==="
input string            InpSymbol                 = "AUTO";          // Target Symbol ("AUTO" for Exness suffix search)
input ulong             InpMagicNumber            = 778899;          // EA Magic Number
input string            InpTradeComment           = "TITAN_ULTIMATE";// Base Order Comment

//--- Inputs Group: Strategy & Operational Mode
input group "=== Strategy & Operational Mode ==="
input ENUM_TRADING_MODE InpTradingMode            = MODE_BALANCED;   // Operational Mode (Balanced / Aggressive)
input ENUM_TIMEFRAMES   InpMicroTF                = PERIOD_M1;       // Micro Timeframe (Entries)
input ENUM_TIMEFRAMES   InpMacroTF                = PERIOD_M5;       // Macro Timeframe (Structure & Regime)
input double            InpMinConfidence          = 65.0;            // Minimum Signal Confidence (0-100%)

//--- Inputs Group: Session & Rollover Controls
input group "=== Institutional Session & Hours ==="
input bool              InpUseSessionFilter       = true;            // Enable Session Hours Filter
input int               InpStartHourGMT           = 1;               // Trading Start Hour (GMT, 0-23)
input int               InpEndHourGMT             = 22;              // Trading End Hour (GMT, 0-23)
input bool              InpBlockRollover          = true;            // Block During Rollover (21:55 - 23:05 GMT)

//--- Inputs Group: Optional AI Market Intelligence Bridge
input group "=== Optional AI Market Intelligence Bridge ==="
input bool              InpUseAIBridge            = false;           // Ingest Python AI Intelligence (MQL5/Files)
input string            InpAIBridgeFile           = "xauusd_ai_signals.json"; // AI Bridge File Name
input int               InpAIMaxAgeSec            = 30;              // Max AI Signal Freshness (Seconds)

//--- Inputs Group: Technical Indicators & Structure
input group "=== Technical Indicators & Structure ==="
input int               InpMacroEMABase           = 200;             // Macro Baseline EMA Period (M5)
input int               InpMacroEMATrend          = 50;              // Macro Trend EMA Period (M5)
input int               InpMicroEMAFast           = 9;               // Micro Fast EMA Period (M1)
input int               InpMicroEMASlow           = 21;              // Micro Slow EMA Period (M1)
input int               InpRSIPeriod              = 14;              // RSI Period
input int               InpATRPeriod              = 14;              // ATR Period
input int               InpMomentumPeriod         = 14;              // Momentum Period

//--- Inputs Group: Risk Management & Capital Bounds
input group "=== Risk Management & Capital Bounds ==="
input ENUM_RISK_MODE    InpRiskMode               = RISK_MODE_PERCENT_EQUITY; // Capital Allocation Mode
input double            InpRiskPercent            = 1.0;             // Risk Per Trade (% of Equity/Balance)
input double            InpFixedLot               = 0.01;            // Fixed Lot Size (if Fixed Mode)
input double            InpMaxDailyDrawdown       = 3.0;             // Max Daily Drawdown (% of Day Baseline)
input bool              InpCloseAllOnDailyDD      = true;            // Emergency Liquidation on Daily DD Breach
input int               InpMaxConcurrentPos       = 2;               // Max Concurrent Positions
input double            InpMaxExposureLots        = 0.20;            // Max Total Active Exposure (Lots)
input int               InpMaxConsecutiveLosses   = 3;               // Max Loss Streak before Cooldown
input int               InpStreakCooldownMin      = 60;              // Loss Streak Cooldown (Minutes)
input bool              InpPersistRiskState       = true;            // Persist Risk State across MT5 Restarts

//--- Inputs Group: Execution & Protection
input group "=== Execution & Spread Protection ==="
input double            InpMaxSpreadPoints        = 35.0;            // Max Absolute Spread Allowed (Points)
input double            InpSpreadAverageMult      = 1.8;             // Rolling Spread Spike Multiplier
input int               InpMaxSlippagePoints      = 30;              // Max Slippage Tolerance (Points)
input int               InpMaxOrderRetries        = 3;               // Max Routing Retries
input int               InpTickThrottleMs         = 100;             // OnTick Processing Throttle (Milliseconds)

//--- Inputs Group: Active Position Lifecycle
input group "=== Position Lifecycle & Exit Logic ==="
input bool              InpEnableBreakEven        = true;            // Enable Break-Even Engine
input double            InpBETriggerATR           = 1.0;             // Break-Even Trigger (ATR Multiple)
input double            InpBELockPoints           = 10.0;            // Break-Even Lock Profit (Points)
input bool              InpEnableTrailing         = true;            // Enable Adaptive Trailing Stop
input double            InpTrailDistATR           = 1.3;             // Trailing Distance (ATR Multiple)
input double            InpTrailStepATR           = 0.3;             // Trailing Step (ATR Multiple)
input bool              InpEnablePartialClose     = true;            // Enable Partial Scale-Out
input double            InpPartialTriggerATR      = 1.5;             // Partial Close Trigger (ATR Multiple)
input double            InpPartialClosePct        = 50.0;            // Partial Close Ratio (%)

//--- Inputs Group: Telemetry & Interface
input group "=== Telemetry & Diagnostics ==="
input bool              InpShowDashboard          = true;            // Display On-Chart HUD
input ENUM_LOG_LEVEL    InpLogLevel               = LOG_LEVEL_INFO;  // Minimum Telemetry Log Level
input bool              InpEnableFileLog          = false;           // Write Telemetry to File

//--- Global Engine Modules
CTradeLogger            g_logger;
CMarketAnalyzer         g_analyzer;
CSignalEngine           g_signal_engine;
CRiskManager            g_risk_manager;
CExecutionEngine        g_execution_engine;
CPositionManager        g_position_manager;

//--- State variables
string                  g_active_symbol           = "";
ulong                   g_last_tick_timestamp_ms  = 0;

//+------------------------------------------------------------------+
//| Expert initialization function                                   |
//+------------------------------------------------------------------+
int OnInit()
{
   // 1. Initialize Logger
   g_logger.Init("[TITAN-ULTIMATE]", _Symbol, InpMagicNumber, InpLogLevel, InpEnableFileLog);
   g_logger.Info("Starting initialization of Exness XAUUSD Titan Ultimate Expert Advisor...");

   // 2. Resolve Symbol & Detect Broker Suffix
   if(!g_analyzer.ResolveAndInitSymbol(InpSymbol, &g_logger))
   {
      g_logger.Error("Initialization aborted: Unable to resolve valid tradeable Gold symbol!");
      return INIT_FAILED;
   }
   g_active_symbol = g_analyzer.GetSymbol();

   // 3. Initialize Multi-Timeframe Technical Indicators & Rolling Spread
   if(!g_analyzer.InitIndicators(InpMicroTF, InpMacroTF, 
                                 InpMacroEMABase, InpMacroEMATrend, 
                                 InpMicroEMAFast, InpMicroEMASlow, 
                                 InpRSIPeriod, InpATRPeriod, InpMomentumPeriod, 
                                 InpMaxSpreadPoints, InpSpreadAverageMult))
   {
      g_logger.Error("Initialization aborted: Failed to initialize indicator subsystem!");
      return INIT_FAILED;
   }

   // 4. Initialize Signal Engine (with Market Structure, Sessions, and optional AI Bridge)
   g_signal_engine.Init(&g_logger, &g_analyzer, InpTradingMode, InpMinConfidence, 
                        InpUseSessionFilter, InpStartHourGMT, InpEndHourGMT, InpBlockRollover,
                        InpUseAIBridge, InpAIBridgeFile, InpAIMaxAgeSec);

   // 5. Initialize Execution Engine
   g_execution_engine.Init(&g_logger, g_active_symbol, InpMagicNumber, InpMaxSlippagePoints, InpMaxSpreadPoints, InpMaxOrderRetries);

   // 6. Initialize Risk Manager with Persistent Memory
   g_risk_manager.Init(&g_logger, g_active_symbol, InpMagicNumber, InpRiskMode, 
                       InpRiskPercent, InpFixedLot, InpMaxDailyDrawdown, 
                       InpCloseAllOnDailyDD, InpMaxConcurrentPos, InpMaxExposureLots, 
                       InpMaxConsecutiveLosses, InpStreakCooldownMin, InpPersistRiskState);

   // 7. Initialize Position Lifecycle Manager
   g_position_manager.Init(&g_logger, &g_execution_engine, &g_analyzer, g_active_symbol, InpMagicNumber,
                           InpEnableBreakEven, InpBETriggerATR, InpBELockPoints,
                           InpEnableTrailing, InpTrailDistATR, InpTrailStepATR,
                           InpEnablePartialClose, InpPartialTriggerATR, InpPartialClosePct);

   g_logger.Info(StringFormat("Initialization complete. Operational on %s | Mode: %s | AI Bridge: %s | Persistent State: %s",
                              g_active_symbol, (InpTradingMode == MODE_BALANCED ? "BALANCED" : "AGGRESSIVE"),
                              (InpUseAIBridge ? "ENABLED" : "DISABLED (100% Native)"),
                              (InpPersistRiskState ? "ON" : "OFF")));

   return INIT_SUCCEEDED;
}

//+------------------------------------------------------------------+
//| Expert deinitialization function                                 |
//+------------------------------------------------------------------+
void OnDeinit(const int reason)
{
   g_logger.ClearDashboard();
   g_logger.Info(StringFormat("Expert Advisor shutting down. Reason code: %d", reason));
}

//+------------------------------------------------------------------+
//| Expert tick function                                             |
//+------------------------------------------------------------------+
void OnTick()
{
   // 1. Tick Throttling to prevent thread lockup during peak volatility
   ulong current_ms = GetTickCount64();
   if(current_ms - g_last_tick_timestamp_ms < (ulong)InpTickThrottleMs)
      return;
   g_last_tick_timestamp_ms = current_ms;

   // 2. Fetch Latest Quote
   MqlTick tick;
   if(!SymbolInfoTick(g_active_symbol, tick))
      return;

   // 3. Risk State & Maximum Drawdown Verification
   bool emergency_shutdown = false;
   bool risk_allowed = g_risk_manager.CheckRiskState(emergency_shutdown);

   if(emergency_shutdown)
   {
      int closed = g_execution_engine.CloseAllPositions("EMERGENCY_DAILY_DRAWDOWN_BREACH");
      g_logger.Error(StringFormat("EMERGENCY SHUTDOWN TRIGGERED: Liquidated %d active positions!", closed));
   }

   // 4. Update Market Analyzer (Rates, Buffers, Regimes, FVG, Structure)
   if(!g_analyzer.Update(tick))
      return;

   // 5. Position Lifecycle Management (Break-Even, Trailing Stop, Partial Scale-Out)
   int open_positions_count = 0;
   double total_exposure_lots = 0.0;
   g_position_manager.ManagePositions(tick, open_positions_count, total_exposure_lots);

   // 6. Signal Evaluation & New Order Routing
   if(risk_allowed && open_positions_count < InpMaxConcurrentPos)
   {
      MarketSignal signal = g_signal_engine.EvaluateSignal(tick);

      if(signal.type == SIGNAL_BUY || signal.type == SIGNAL_SELL)
      {
         double lot_size = g_risk_manager.CalculateLotSize(signal.entry_price, signal.stop_loss);

         if(g_risk_manager.CanOpenNewPosition(open_positions_count, total_exposure_lots, lot_size))
         {
            ENUM_ORDER_TYPE order_type = (signal.type == SIGNAL_BUY) ? ORDER_TYPE_BUY : ORDER_TYPE_SELL;
            string order_comment = StringFormat("%s_%s", InpTradeComment, signal.reason);

            ulong deal_ticket = 0;
            if(g_execution_engine.SendMarketOrder(order_type, lot_size, signal.stop_loss, signal.take_profit, order_comment, deal_ticket))
            {
               g_logger.Trade(StringFormat("ORDER EXECUTED: %s %.2f lots | SL: %.2f | TP: %.2f | Reason: %s",
                                           (order_type == ORDER_TYPE_BUY ? "BUY" : "SELL"),
                                           lot_size, signal.stop_loss, signal.take_profit, signal.reason));
            }
         }
      }
   }

   // 7. Update On-Chart HUD Telemetry
   if(InpShowDashboard)
   {
      double starting_equity = g_risk_manager.GetDailyStartEquity();
      double current_equity  = AccountInfoDouble(ACCOUNT_EQUITY);
      double daily_dd_pct    = (starting_equity > 0.0) ? MathMax(0.0, (starting_equity - current_equity) / starting_equity * 100.0) : 0.0;
      double daily_pnl       = g_risk_manager.GetDailyRealizedPnL() + (current_equity - AccountInfoDouble(ACCOUNT_BALANCE));

      string status_str = "ACTIVE_NORMAL";
      if(emergency_shutdown || g_risk_manager.IsDailyDrawdownBreached())
         status_str = "HALTED_DAILY_DD_LIMIT";
      else if(g_risk_manager.IsCooldownActive())
         status_str = "COOLDOWN_ACTIVE";
      else if(g_analyzer.GetRegime() == REGIME_ADVERSE_SPREAD)
         status_str = "PAUSED_SPREAD_EXCEEDED";

      string fvg_str = "CLEAN";
      if(g_analyzer.HasBullishFVG()) fvg_str = "BULL_FVG";
      else if(g_analyzer.HasBearishFVG()) fvg_str = "BEAR_FVG";

      g_logger.UpdateDashboard((InpTradingMode == MODE_BALANCED ? "BALANCED" : "AGGRESSIVE"),
                               g_active_symbol,
                               g_analyzer.GetRegimeName(),
                               g_analyzer.GetStructureEventName(),
                               fvg_str,
                               g_analyzer.GetSpreadPts(),
                               g_analyzer.GetRollingMeanSpread(),
                               InpMaxSpreadPoints,
                               g_analyzer.GetATR_Micro(0),
                               g_analyzer.GetATR_Macro(0),
                               daily_pnl,
                               daily_dd_pct,
                               InpMaxDailyDrawdown,
                               g_risk_manager.GetConsecutiveLosses(),
                               g_risk_manager.GetMaxConsecutiveLosses(),
                               open_positions_count,
                               InpMaxConcurrentPos,
                               total_exposure_lots,
                               status_str,
                               g_risk_manager.IsCooldownActive(),
                               g_risk_manager.GetCooldownUntil(),
                               InpUseAIBridge);
   }
}

//+------------------------------------------------------------------+
//| Trade transaction event handler                                  |
//+------------------------------------------------------------------+
void OnTradeTransaction(const MqlTradeTransaction &trans,
                        const MqlTradeRequest &request,
                        const MqlTradeResult &result)
{
   if(trans.type == TRADE_TRANSACTION_DEAL_ADD)
   {
      g_risk_manager.CalculateLossStreak();
   }
}
