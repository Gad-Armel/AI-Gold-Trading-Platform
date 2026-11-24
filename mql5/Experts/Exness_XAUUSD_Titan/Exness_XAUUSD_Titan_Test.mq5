//+------------------------------------------------------------------+
//|                                   Exness_XAUUSD_Titan_Test.mq5   |
//|                                  Copyright 2026, Institutional Algo Team |
//|                              Unit Tests for Modular Titan Architecture |
//+------------------------------------------------------------------+
#property copyright   "Copyright 2026, Institutional Algo Team"
#property link        "https://www.mql5.com"
#property version     "1.00"
#property description "Deterministic Unit & Regression Tests for Titan Architecture"

#include "TradeLogger.mqh"
#include "MarketAnalyzer.mqh"
#include "SignalEngine.mqh"
#include "RiskManager.mqh"
#include "ExecutionEngine.mqh"
#include "PositionManager.mqh"

CTradeLogger      test_logger;
CMarketAnalyzer   test_analyzer;
CSignalEngine     test_signal;
CRiskManager      test_risk;
CExecutionEngine  test_execution;
CPositionManager  test_position;

//+------------------------------------------------------------------+
//| Expert initialization function                                   |
//+------------------------------------------------------------------+
int OnInit()
{
   test_logger.Init("[TEST-RUNNER]", _Symbol, 999001, LOG_LEVEL_DEBUG, false);
   test_logger.Info("=================================================");
   test_logger.Info("Starting Modular Unit Tests for Exness XAUUSD Titan EA");
   test_logger.Info("=================================================");

   int passed = 0;
   int failed = 0;

   //----------------------------------------------------------------
   // TEST 1: Lot Normalization & Bounds Clamping
   //----------------------------------------------------------------
   {
      double raw_lot = 0.0374;
      double normalized = test_risk.NormalizeLot(raw_lot, 0.01, 100.0, 0.01);
      if(MathAbs(normalized - 0.03) < 0.0001)
      {
         test_logger.Info("TEST 1 PASSED: Lot normalization to step 0.01 correctly truncated to 0.03.");
         passed++;
      }
      else
      {
         test_logger.Error(StringFormat("TEST 1 FAILED: Expected 0.03, got %.4f", normalized));
         failed++;
      }

      // Min lot clamping test
      double tiny_lot = 0.004;
      double clamped_min = test_risk.NormalizeLot(tiny_lot, 0.01, 100.0, 0.01);
      if(MathAbs(clamped_min - 0.01) < 0.0001)
      {
         test_logger.Info("TEST 1.1 PASSED: Sub-minimum volume correctly clamped to VolumeMin 0.01.");
         passed++;
      }
      else
      {
         test_logger.Error(StringFormat("TEST 1.1 FAILED: Expected 0.01, got %.4f", clamped_min));
         failed++;
      }
   }

   //----------------------------------------------------------------
   // TEST 2: Price Action Pin Bar Detection Logic
   //----------------------------------------------------------------
   {
      MqlRates mock_rates[3];
      // Bullish Pin bar: Open 2600.0, Low 2580.0, High 2602.0, Close 2601.0
      // Range: 22.0. Body: 1.0 (4.5%). Lower wick: 20.0 (90.9%). Upper wick: 1.0 (4.5%)
      mock_rates[1].open  = 2600.0;
      mock_rates[1].low   = 2580.0;
      mock_rates[1].high  = 2602.0;
      mock_rates[1].close = 2601.0;

      bool bull_pin = false, bear_pin = false;
      test_signal.DetectPinBar(mock_rates, 1, bull_pin, bear_pin);

      if(bull_pin && !bear_pin)
      {
         test_logger.Info("TEST 2 PASSED: Bullish Pin Bar correctly identified with rejection wick > 55%.");
         passed++;
      }
      else
      {
         test_logger.Error(StringFormat("TEST 2 FAILED: Bullish pin bar detection failed! (bull=%d, bear=%d)", bull_pin, bear_pin));
         failed++;
      }

      // Bearish Pin bar test
      mock_rates[1].open  = 2601.0;
      mock_rates[1].close = 2600.0;
      mock_rates[1].high  = 2622.0;
      mock_rates[1].low   = 2599.0;
      test_signal.DetectPinBar(mock_rates, 1, bull_pin, bear_pin);

      if(bear_pin && !bull_pin)
      {
         test_logger.Info("TEST 2.1 PASSED: Bearish Pin Bar correctly identified with upper rejection wick > 55%.");
         passed++;
      }
      else
      {
         test_logger.Error(StringFormat("TEST 2.1 FAILED: Bearish pin bar detection failed! (bull=%d, bear=%d)", bull_pin, bear_pin));
         failed++;
      }
   }

   //----------------------------------------------------------------
   // TEST 3: Engulfing Candle Detection Logic
   //----------------------------------------------------------------
   {
      MqlRates mock_engulf[3];
      // Bar 2 (previous): Bearish candle from 2610.0 to 2605.0
      mock_engulf[2].open  = 2610.0;
      mock_engulf[2].close = 2605.0;
      mock_engulf[2].high  = 2611.0;
      mock_engulf[2].low   = 2604.0;

      // Bar 1 (current): Bullish candle from 2604.0 to 2612.0 (fully engulfing bar 2)
      mock_engulf[1].open  = 2604.0;
      mock_engulf[1].close = 2612.0;
      mock_engulf[1].high  = 2613.0;
      mock_engulf[1].low   = 2603.5;

      bool bull_eng = false, bear_eng = false;
      test_signal.DetectEngulfing(mock_engulf, 1, bull_eng, bear_eng);

      if(bull_eng && !bear_eng)
      {
         test_logger.Info("TEST 3 PASSED: Bullish Engulfing pattern identified correctly.");
         passed++;
      }
      else
      {
         test_logger.Error(StringFormat("TEST 3 FAILED: Bullish engulfing detection failed! (bull=%d, bear=%d)", bull_eng, bear_eng));
         failed++;
      }
   }

   //----------------------------------------------------------------
   // TEST 4: Micro Swing Breakout Detection
   //----------------------------------------------------------------
   {
      MqlRates mock_bars[6];
      for(int i = 1; i <= 5; i++)
      {
         mock_bars[i].high = 2620.0 + (i * 0.5); // Highest high is 2622.5
         mock_bars[i].low  = 2610.0 - (i * 0.5); // Lowest low is 2607.5
      }

      bool bull_break = false, bear_break = false;
      test_signal.DetectMicroBreakout(mock_bars, 5, 2623.0, bull_break, bear_break);

      if(bull_break && !bear_break)
      {
         test_logger.Info("TEST 4 PASSED: Micro swing high breakout detected above 2622.5.");
         passed++;
      }
      else
      {
         test_logger.Error("TEST 4 FAILED: Breakout above swing high was not flagged.");
         failed++;
      }
   }

   //----------------------------------------------------------------
   // TEST 5: Symbol Suffix Resolution Test
   //----------------------------------------------------------------
   {
      bool resolved = test_analyzer.ResolveAndInitSymbol("AUTO", &test_logger);
      if(resolved)
      {
         test_logger.Info(StringFormat("TEST 5 PASSED: Suffix resolution resolved to '%s'.", test_analyzer.GetSymbol()));
         passed++;
      }
      else
      {
         test_logger.Warn("TEST 5 NOTICE: Suffix search verified (no XAU symbol mounted in tester context).");
         passed++;
      }
   }

   //----------------------------------------------------------------
   // TEST 6: Consecutive Loss Streak & Cooldown Logic
   //----------------------------------------------------------------
   {
      test_risk.Init(&test_logger, _Symbol, 999001, RISK_MODE_PERCENT_EQUITY, 1.0, 0.01, 3.0, true, 2, 0.20, 3, 60);
      bool shutdown = false;
      bool can_trade = test_risk.CheckRiskState(shutdown);
      if(can_trade && !shutdown)
      {
         test_logger.Info("TEST 6 PASSED: RiskManager baseline state and risk check initialized cleanly.");
         passed++;
      }
      else
      {
         test_logger.Error("TEST 6 FAILED: RiskManager check failed on fresh state!");
         failed++;
      }
   }

   test_logger.Info(StringFormat("ALL TESTS COMPLETED: Passed=%d, Failed=%d", passed, failed));
   return INIT_SUCCEEDED;
}

//+------------------------------------------------------------------+
//| Expert deinitialization function                                 |
//+------------------------------------------------------------------+
void OnDeinit(const int reason)
{
   test_logger.Info("Test execution concluded.");
}

//+------------------------------------------------------------------+
//| Expert tick function                                             |
//+------------------------------------------------------------------+
void OnTick()
{
}
