//+------------------------------------------------------------------+
//|                                                 SignalEngine.mqh |
//|                                  Copyright 2026, Institutional Algo Team |
//|                             Multi-Strategy Quantitative Signal Engine |
//+------------------------------------------------------------------+
#property copyright "Copyright 2026, Institutional Algo Team"
#property link      "https://www.mql5.com"
#property strict

#include "MarketAnalyzer.mqh"
#include "TradeLogger.mqh"

enum ENUM_TRADING_MODE
{
   MODE_BALANCED   = 0, // High-confluence pullback & trend continuation
   MODE_AGGRESSIVE = 1  // Responsive momentum breakouts & micro-range scalping
};

enum ENUM_SIGNAL_TYPE
{
   SIGNAL_NONE = 0,
   SIGNAL_BUY  = 1,
   SIGNAL_SELL = -1
};

struct MarketSignal
{
   ENUM_SIGNAL_TYPE   type;
   ENUM_MARKET_REGIME regime;
   double             entry_price;
   double             stop_loss;
   double             take_profit;
   double             atr_value;
   double             confidence; // 0.0 to 100.0%
   string             reason;
   datetime           timestamp;
   bool               ai_confirmed;
};

class CSignalEngine
{
private:
   CTradeLogger*      m_logger;
   CMarketAnalyzer*   m_analyzer;
   ENUM_TRADING_MODE  m_mode;
   double             m_min_confidence;

   // Price Action thresholds
   double             m_pinbar_wick_ratio;
   double             m_pinbar_body_ratio;

   // Optional AI Bridge Settings
   bool               m_use_ai_bridge;
   string             m_ai_bridge_file;
   int                m_ai_max_age_sec;
   datetime           m_last_ai_check;
   ENUM_SIGNAL_TYPE   m_cached_ai_signal;
   double             m_cached_ai_conf;
   bool               m_cached_ai_valid;

public:
   CSignalEngine()
   {
      m_logger            = NULL;
      m_analyzer          = NULL;
      m_mode              = MODE_BALANCED;
      m_min_confidence    = 65.0;
      m_pinbar_wick_ratio = 0.55;
      m_pinbar_body_ratio = 0.35;
      m_use_ai_bridge     = false;
      m_ai_bridge_file    = "xauusd_ai_signals.json";
      m_ai_max_age_sec    = 30;
      m_last_ai_check     = 0;
      m_cached_ai_signal  = SIGNAL_NONE;
      m_cached_ai_conf    = 0.0;
      m_cached_ai_valid   = false;
   }

   void Init(CTradeLogger* logger, 
             CMarketAnalyzer* analyzer, 
             const ENUM_TRADING_MODE mode, 
             const double min_confidence = 65.0,
             const bool use_ai_bridge = false,
             const string ai_bridge_file = "xauusd_ai_signals.json",
             const int ai_max_age_sec = 30)
   {
      m_logger         = logger;
      m_analyzer       = analyzer;
      m_mode           = mode;
      m_min_confidence = min_confidence;
      m_use_ai_bridge  = use_ai_bridge;
      m_ai_bridge_file = ai_bridge_file;
      m_ai_max_age_sec = ai_max_age_sec;
   }

   void SetMode(const ENUM_TRADING_MODE mode) { m_mode = mode; }
   ENUM_TRADING_MODE GetMode() const { return m_mode; }

   //+------------------------------------------------------------------+
   //| Ingest External AI Market Intelligence Bridge (Non-Blocking)     |
   //+------------------------------------------------------------------+
   bool IngestAIIntelligence()
   {
      if(!m_use_ai_bridge)
      {
         m_cached_ai_valid = false;
         return false;
      }

      // Check at most once every 3 seconds to preserve CPU
      if(TimeCurrent() - m_last_ai_check < 3)
      {
         return m_cached_ai_valid;
      }
      m_last_ai_check = TimeCurrent();

      int handle = FileOpen(m_ai_bridge_file, FILE_READ|FILE_TXT|FILE_SHARE_READ|FILE_ANSI);
      if(handle == INVALID_HANDLE)
      {
         m_cached_ai_valid = false;
         return false;
      }

      string content = "";
      while(!FileIsEnding(handle))
      {
         content += FileReadString(handle);
      }
      FileClose(handle);

      if(StringLen(content) < 15)
      {
         m_cached_ai_valid = false;
         return false;
      }

      // Parse JSON fields
      m_cached_ai_signal = SIGNAL_NONE;
      m_cached_ai_conf   = 0.0;

      if(StringFind(content, "\"BUY\"") >= 0 || StringFind(content, "\"signal\":\"BUY\"") >= 0)
         m_cached_ai_signal = SIGNAL_BUY;
      else if(StringFind(content, "\"SELL\"") >= 0 || StringFind(content, "\"signal\":\"SELL\"") >= 0)
         m_cached_ai_signal = SIGNAL_SELL;

      int conf_pos = StringFind(content, "\"confidence\":");
      if(conf_pos >= 0)
      {
         string sub = StringSubstr(content, conf_pos + 13, 8);
         double conf_val = StringToDouble(sub);
         if(conf_val <= 1.0) conf_val *= 100.0; // Convert 0.78 to 78.0%
         m_cached_ai_conf = conf_val;
      }

      m_cached_ai_valid = (m_cached_ai_signal != SIGNAL_NONE);
      return m_cached_ai_valid;
   }

   //+------------------------------------------------------------------+
   //| Price Action Pattern Detection: Pin Bar (Rejection Wick)         |
   //+------------------------------------------------------------------+
   void DetectPinBar(const MqlRates &rates[], const int idx, bool &bull_pin, bool &bear_pin)
   {
      bull_pin = false;
      bear_pin = false;

      double high  = rates[idx].high;
      double low   = rates[idx].low;
      double open  = rates[idx].open;
      double close = rates[idx].close;
      double range = high - low;

      if(range <= 0.0) return;

      double body        = MathAbs(close - open);
      double upper_wick  = high - MathMax(open, close);
      double lower_wick  = MathMin(open, close) - low;

      if((lower_wick / range >= m_pinbar_wick_ratio) && (body / range <= m_pinbar_body_ratio) && (upper_wick / range <= 0.25))
      {
         bull_pin = true;
      }

      if((upper_wick / range >= m_pinbar_wick_ratio) && (body / range <= m_pinbar_body_ratio) && (lower_wick / range <= 0.25))
      {
         bear_pin = true;
      }
   }

   //+------------------------------------------------------------------+
   //| Price Action Pattern Detection: Engulfing Candle                 |
   //+------------------------------------------------------------------+
   void DetectEngulfing(const MqlRates &rates[], const int idx, bool &bull_engulf, bool &bear_engulf)
   {
      bull_engulf = false;
      bear_engulf = false;

      double open_curr  = rates[idx].open;
      double close_curr = rates[idx].close;
      double open_prev  = rates[idx+1].open;
      double close_prev = rates[idx+1].close;

      if(close_prev < open_prev && close_curr > open_curr)
      {
         if(open_curr <= close_prev && close_curr >= open_prev)
            bull_engulf = true;
      }

      if(close_prev > open_prev && close_curr < open_curr)
      {
         if(open_curr >= close_prev && close_curr <= open_prev)
            bear_engulf = true;
      }
   }

   //+------------------------------------------------------------------+
   //| Price Action: Micro Swing Breakout                               |
   //+------------------------------------------------------------------+
   void DetectMicroBreakout(const MqlRates &rates[], const int count, const double current_price, bool &bull_break, bool &bear_break)
   {
      bull_break = false;
      bear_break = false;

      double highest = -DBL_MAX;
      double lowest  = DBL_MAX;

      for(int i = 1; i <= count && i < ArraySize(rates); i++)
      {
         if(rates[i].high > highest) highest = rates[i].high;
         if(rates[i].low < lowest)   lowest  = rates[i].low;
      }

      if(current_price > highest) bull_break = true;
      if(current_price < lowest)  bear_break = true;
   }

   //+------------------------------------------------------------------+
   //| Evaluate Market for Trading Signals                              |
   //+------------------------------------------------------------------+
   MarketSignal EvaluateSignal(const MqlTick &tick)
   {
      MarketSignal sig;
      sig.type        = SIGNAL_NONE;
      sig.regime      = REGIME_UNKNOWN;
      sig.entry_price = 0.0;
      sig.stop_loss   = 0.0;
      sig.take_profit = 0.0;
      sig.atr_value   = 0.0;
      sig.confidence  = 0.0;
      sig.reason      = "NONE";
      sig.timestamp   = TimeCurrent();
      sig.ai_confirmed= false;

      if(m_analyzer == NULL) return sig;

      ENUM_MARKET_REGIME regime = m_analyzer.GetRegime();
      sig.regime = regime;

      if(regime == REGIME_ADVERSE_SPREAD)
      {
         sig.reason = "FILTER_ADVERSE_SPREAD";
         return sig;
      }
      if(regime == REGIME_HIGH_VOLATILITY_EXPANSION)
      {
         sig.reason = "FILTER_VOLATILITY_SHOCK";
         return sig;
      }

      MqlRates m1_rates[];
      MqlRates m5_rates[];
      m_analyzer.GetMicroRates(m1_rates);
      m_analyzer.GetMacroRates(m5_rates);

      if(ArraySize(m1_rates) < 5 || ArraySize(m5_rates) < 5)
      {
         sig.reason = "INSUFFICIENT_BAR_DATA";
         return sig;
      }

      double atr_m1 = m_analyzer.GetATR_Micro(0);
      double atr_m5 = m_analyzer.GetATR_Macro(0);
      sig.atr_value = (m_mode == MODE_BALANCED) ? atr_m5 : atr_m1;

      if(sig.atr_value <= 0.0)
      {
         sig.reason = "INVALID_ATR";
         return sig;
      }

      // Check Price Action on M1 closed bar (index 1)
      bool bull_pin = false, bear_pin = false;
      bool bull_engulf = false, bear_engulf = false;
      bool bull_break = false, bear_break = false;

      DetectPinBar(m1_rates, 1, bull_pin, bear_pin);
      DetectEngulfing(m1_rates, 1, bull_engulf, bear_engulf);
      DetectMicroBreakout(m1_rates, 5, tick.bid, bull_break, bear_break);

      double rsi_m1 = m_analyzer.GetRSI_Micro(0);
      double rsi_m5 = m_analyzer.GetRSI_Macro(0);
      double mom_m1 = m_analyzer.GetMom_Micro(0);

      // Ingest AI Bridge if enabled
      bool has_ai = IngestAIIntelligence();

      //------------------------------------------------------------------
      // STRATEGY 1: BALANCED MODE (Institutional Trend Continuation)
      //------------------------------------------------------------------
      if(m_mode == MODE_BALANCED)
      {
         // BUY LOGIC
         if(regime == REGIME_STRONG_BULL_TREND || regime == REGIME_MODERATE_BULL_TREND)
         {
            double ema_micro_slow = m_analyzer.GetEMAMicroSlow(0);
            double ema_micro_fast = m_analyzer.GetEMAMicroFast(0);

            bool pullback_held = (m1_rates[1].low <= ema_micro_slow || m1_rates[1].close <= ema_micro_fast) && (m1_rates[0].close >= ema_micro_fast);
            bool price_action_ok = bull_pin || bull_engulf || bull_break;
            bool rsi_ok = (rsi_m1 >= 42.0 && rsi_m1 <= 64.0 && rsi_m5 > 50.0);
            bool momentum_ok = (mom_m1 >= 100.02);

            double score = 0.0;
            if(regime == REGIME_STRONG_BULL_TREND) score += 30.0; else score += 20.0;
            if(pullback_held) score += 25.0;
            if(price_action_ok) score += 25.0;
            if(rsi_ok) score += 10.0;
            if(momentum_ok) score += 10.0;

            // AI Confluence Booster
            if(has_ai && m_cached_ai_signal == SIGNAL_BUY && m_cached_ai_conf >= 60.0)
            {
               score += 15.0;
               sig.ai_confirmed = true;
            }

            if(score >= m_min_confidence && pullback_held && price_action_ok)
            {
               sig.type        = SIGNAL_BUY;
               sig.confidence  = score;
               sig.entry_price = tick.ask;
               double swing_low = MathMin(m1_rates[1].low, m1_rates[2].low);
               sig.stop_loss   = MathMin(tick.ask - (1.5 * atr_m5), swing_low - (0.3 * atr_m1));
               sig.take_profit = tick.ask + (2.5 * atr_m5);
               sig.reason      = StringFormat("BALANCED_BULL_PULLBACK (Conf:%.0f%%%s)", score, sig.ai_confirmed?"+AI":"");
               return sig;
            }
         }

         // SELL LOGIC
         if(regime == REGIME_STRONG_BEAR_TREND || regime == REGIME_MODERATE_BEAR_TREND)
         {
            double ema_micro_slow = m_analyzer.GetEMAMicroSlow(0);
            double ema_micro_fast = m_analyzer.GetEMAMicroFast(0);

            bool pullback_held = (m1_rates[1].high >= ema_micro_slow || m1_rates[1].close >= ema_micro_fast) && (m1_rates[0].close <= ema_micro_fast);
            bool price_action_ok = bear_pin || bear_engulf || bear_break;
            bool rsi_ok = (rsi_m1 <= 58.0 && rsi_m1 >= 36.0 && rsi_m5 < 50.0);
            bool momentum_ok = (mom_m1 <= 99.98);

            double score = 0.0;
            if(regime == REGIME_STRONG_BEAR_TREND) score += 30.0; else score += 20.0;
            if(pullback_held) score += 25.0;
            if(price_action_ok) score += 25.0;
            if(rsi_ok) score += 10.0;
            if(momentum_ok) score += 10.0;

            // AI Confluence Booster
            if(has_ai && m_cached_ai_signal == SIGNAL_SELL && m_cached_ai_conf >= 60.0)
            {
               score += 15.0;
               sig.ai_confirmed = true;
            }

            if(score >= m_min_confidence && pullback_held && price_action_ok)
            {
               sig.type        = SIGNAL_SELL;
               sig.confidence  = score;
               sig.entry_price = tick.bid;
               double swing_high = MathMax(m1_rates[1].high, m1_rates[2].high);
               sig.stop_loss   = MathMax(tick.bid + (1.5 * atr_m5), swing_high + (0.3 * atr_m1));
               sig.take_profit = tick.bid - (2.5 * atr_m5);
               sig.reason      = StringFormat("BALANCED_BEAR_PULLBACK (Conf:%.0f%%%s)", score, sig.ai_confirmed?"+AI":"");
               return sig;
            }
         }
      }

      //------------------------------------------------------------------
      // STRATEGY 2: AGGRESSIVE MODE (Momentum Scalp & Range Mean Reversion)
      //------------------------------------------------------------------
      else if(m_mode == MODE_AGGRESSIVE)
      {
         if(regime == REGIME_STRONG_BULL_TREND || regime == REGIME_MODERATE_BULL_TREND)
         {
            double ema_fast_curr = m_analyzer.GetEMAMicroFast(0);
            double ema_slow_curr = m_analyzer.GetEMAMicroSlow(0);

            bool momentum_surge = (mom_m1 >= 100.08) && (rsi_m1 > 52.0 && rsi_m1 < 75.0);
            bool fast_cross_or_bounce = (ema_fast_curr > ema_slow_curr) && (tick.ask > ema_fast_curr);

            if((momentum_surge && bull_break) || (fast_cross_or_bounce && bull_pin))
            {
               sig.type        = SIGNAL_BUY;
               sig.confidence  = 75.0;
               if(has_ai && m_cached_ai_signal == SIGNAL_BUY) { sig.confidence += 15.0; sig.ai_confirmed = true; }
               sig.entry_price = tick.ask;
               sig.stop_loss   = tick.ask - (1.2 * atr_m1);
               sig.take_profit = tick.ask + (2.0 * atr_m1);
               sig.reason      = "AGGRESSIVE_MOMENTUM_BULL_SCALP";
               return sig;
            }
         }
         else if(regime == REGIME_STRONG_BEAR_TREND || regime == REGIME_MODERATE_BEAR_TREND)
         {
            double ema_fast_curr = m_analyzer.GetEMAMicroFast(0);
            double ema_slow_curr = m_analyzer.GetEMAMicroSlow(0);

            bool momentum_surge = (mom_m1 <= 99.92) && (rsi_m1 < 48.0 && rsi_m1 > 25.0);
            bool fast_cross_or_bounce = (ema_fast_curr < ema_slow_curr) && (tick.bid < ema_fast_curr);

            if((momentum_surge && bear_break) || (fast_cross_or_bounce && bear_pin))
            {
               sig.type        = SIGNAL_SELL;
               sig.confidence  = 75.0;
               if(has_ai && m_cached_ai_signal == SIGNAL_SELL) { sig.confidence += 15.0; sig.ai_confirmed = true; }
               sig.entry_price = tick.bid;
               sig.stop_loss   = tick.bid + (1.2 * atr_m1);
               sig.take_profit = tick.bid - (2.0 * atr_m1);
               sig.reason      = "AGGRESSIVE_MOMENTUM_BEAR_SCALP";
               return sig;
            }
         }
         else if(regime == REGIME_RANGING_CONSOLIDATION)
         {
            if(rsi_m1 < 30.0 && bull_pin)
            {
               sig.type        = SIGNAL_BUY;
               sig.confidence  = 65.0;
               sig.entry_price = tick.ask;
               sig.stop_loss   = tick.ask - (1.0 * atr_m1);
               sig.take_profit = tick.ask + (1.5 * atr_m1);
               sig.reason      = "AGGRESSIVE_RANGE_MEAN_REV_BUY";
               return sig;
            }
            else if(rsi_m1 > 70.0 && bear_pin)
            {
               sig.type        = SIGNAL_SELL;
               sig.confidence  = 65.0;
               sig.entry_price = tick.bid;
               sig.stop_loss   = tick.bid + (1.0 * atr_m1);
               sig.take_profit = tick.bid - (1.5 * atr_m1);
               sig.reason      = "AGGRESSIVE_RANGE_MEAN_REV_SELL";
               return sig;
            }
         }
      }

      sig.reason = "NO_CONFLUENCE";
      return sig;
   }
};
