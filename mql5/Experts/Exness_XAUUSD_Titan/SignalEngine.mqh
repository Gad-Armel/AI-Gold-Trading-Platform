//+------------------------------------------------------------------+
//|                                                 SignalEngine.mqh |
//|                                  Copyright 2026, Institutional Algo Team |
//|             Ultimate Quantitative Signal & Market Structure Engine |
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
   bool               fvg_confirmed;
   bool               structure_confirmed;
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

   // Session filter
   bool               m_use_session_filter;
   int                m_start_hour_gmt;
   int                m_end_hour_gmt;
   bool               m_block_rollover;

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
      m_logger             = NULL;
      m_analyzer           = NULL;
      m_mode               = MODE_BALANCED;
      m_min_confidence     = 65.0;
      m_pinbar_wick_ratio  = 0.55;
      m_pinbar_body_ratio  = 0.35;
      m_use_session_filter = true;
      m_start_hour_gmt     = 1;   // 01:00 GMT
      m_end_hour_gmt       = 22;  // 22:00 GMT
      m_block_rollover     = true;// 21:55 - 23:05 GMT
      m_use_ai_bridge      = false;
      m_ai_bridge_file     = "xauusd_ai_signals.json";
      m_ai_max_age_sec     = 30;
      m_last_ai_check      = 0;
      m_cached_ai_signal   = SIGNAL_NONE;
      m_cached_ai_conf     = 0.0;
      m_cached_ai_valid    = false;
   }

   void Init(CTradeLogger* logger, 
             CMarketAnalyzer* analyzer, 
             const ENUM_TRADING_MODE mode, 
             const double min_confidence = 65.0,
             const bool use_session_filter = true,
             const int start_hour_gmt = 1,
             const int end_hour_gmt = 22,
             const bool block_rollover = true,
             const bool use_ai_bridge = false,
             const string ai_bridge_file = "xauusd_ai_signals.json",
             const int ai_max_age_sec = 30)
   {
      m_logger             = logger;
      m_analyzer           = analyzer;
      m_mode               = mode;
      m_min_confidence     = min_confidence;
      m_use_session_filter = use_session_filter;
      m_start_hour_gmt     = start_hour_gmt;
      m_end_hour_gmt       = end_hour_gmt;
      m_block_rollover     = block_rollover;
      m_use_ai_bridge      = use_ai_bridge;
      m_ai_bridge_file     = ai_bridge_file;
      m_ai_max_age_sec     = ai_max_age_sec;
   }

   void SetMode(const ENUM_TRADING_MODE mode) { m_mode = mode; }
   ENUM_TRADING_MODE GetMode() const { return m_mode; }

   //+------------------------------------------------------------------+
   //| Session Time Filter (GMT Rollover & Trading Windows)             |
   //+------------------------------------------------------------------+
   bool IsSessionPermitted(string &veto_reason)
   {
      if(!m_use_session_filter) return true;

      MqlDateTime dt;
      TimeToStruct(TimeGMT(), dt);

      // Block Rollover window: 21:55 to 23:05 GMT
      if(m_block_rollover)
      {
         if((dt.hour == 21 && dt.min >= 55) || (dt.hour == 22) || (dt.hour == 23 && dt.min <= 5))
         {
            veto_reason = "ROLLOVER_SPREAD_EXPANSION_WINDOW";
            return false;
         }
      }

      if(dt.hour < m_start_hour_gmt || dt.hour >= m_end_hour_gmt)
      {
         veto_reason = "OUTSIDE_PERMITTED_SESSION_HOURS";
         return false;
      }

      return true;
   }

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
      while(!FileIsEnding(handle)) content += FileReadString(handle);
      FileClose(handle);

      if(StringLen(content) < 15)
      {
         m_cached_ai_valid = false;
         return false;
      }

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
         if(conf_val <= 1.0) conf_val *= 100.0;
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
         bull_pin = true;

      if((upper_wick / range >= m_pinbar_wick_ratio) && (body / range <= m_pinbar_body_ratio) && (lower_wick / range <= 0.25))
         bear_pin = true;
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
         if(open_curr <= close_prev && close_curr >= open_prev) bull_engulf = true;
      }

      if(close_prev > open_prev && close_curr < open_curr)
      {
         if(open_curr >= close_prev && close_curr <= open_prev) bear_engulf = true;
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
      sig.type               = SIGNAL_NONE;
      sig.regime             = REGIME_UNKNOWN;
      sig.entry_price        = 0.0;
      sig.stop_loss          = 0.0;
      sig.take_profit        = 0.0;
      sig.atr_value          = 0.0;
      sig.confidence         = 0.0;
      sig.reason             = "NONE";
      sig.timestamp          = TimeCurrent();
      sig.ai_confirmed       = false;
      sig.fvg_confirmed      = false;
      sig.structure_confirmed= false;

      if(m_analyzer == NULL) return sig;

      // Session Filter Check
      string session_err = "";
      if(!IsSessionPermitted(session_err))
      {
         sig.reason = "FILTER_" + session_err;
         return sig;
      }

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

      // Check Price Action on M1 closed bar
      bool bull_pin = false, bear_pin = false;
      bool bull_engulf = false, bear_engulf = false;
      bool bull_break = false, bear_break = false;

      DetectPinBar(m1_rates, 1, bull_pin, bear_pin);
      DetectEngulfing(m1_rates, 1, bull_engulf, bear_engulf);
      DetectMicroBreakout(m1_rates, 5, tick.bid, bull_break, bear_break);

      double rsi_m1 = m_analyzer.GetRSI_Micro(0);
      double rsi_m5 = m_analyzer.GetRSI_Macro(0);
      double mom_m1 = m_analyzer.GetMom_Micro(0);

      // Check Liquidity Sweeps / Traps
      bool buy_sweep_trap  = m_analyzer.IsBuyTrapSweep();
      bool sell_sweep_trap = m_analyzer.IsSellTrapSweep();

      // Check Fair Value Gaps (FVG)
      bool has_bull_fvg = m_analyzer.HasBullishFVG();
      bool has_bear_fvg = m_analyzer.HasBearishFVG();

      // Check Market Structure Events (BOS / CHoCH)
      ENUM_STRUCTURE_EVENT struct_evt = m_analyzer.GetStructureEvent();
      bool is_bull_struct = (struct_evt == STRUCT_BOS_BULL || struct_evt == STRUCT_CHOCH_BULL);
      bool is_bear_struct = (struct_evt == STRUCT_BOS_BEAR || struct_evt == STRUCT_CHOCH_BEAR);

      // Ingest AI Bridge if enabled
      bool has_ai = IngestAIIntelligence();

      //------------------------------------------------------------------
      // STRATEGY 1: BALANCED MODE (Institutional Trend Continuation)
      //------------------------------------------------------------------
      if(m_mode == MODE_BALANCED)
      {
         // BUY LOGIC
         if(!buy_sweep_trap && (regime == REGIME_STRONG_BULL_TREND || regime == REGIME_MODERATE_BULL_TREND))
         {
            double ema_micro_slow = m_analyzer.GetEMAMicroSlow(0);
            double ema_micro_fast = m_analyzer.GetEMAMicroFast(0);

            bool pullback_held = (m1_rates[1].low <= ema_micro_slow || m1_rates[1].close <= ema_micro_fast) && (m1_rates[0].close >= ema_micro_fast);
            bool price_action_ok = bull_pin || bull_engulf || bull_break;
            bool rsi_ok = (rsi_m1 >= 42.0 && rsi_m1 <= 64.0 && rsi_m5 > 50.0);
            bool momentum_ok = (mom_m1 >= 100.02);

            double score = 0.0;
            if(regime == REGIME_STRONG_BULL_TREND) score += 25.0; else score += 15.0;
            if(pullback_held) score += 20.0;
            if(price_action_ok) score += 20.0;
            if(rsi_ok) score += 10.0;
            if(momentum_ok) score += 10.0;

            // Institutional Market Structure & FVG Confluence
            if(has_bull_fvg) { score += 10.0; sig.fvg_confirmed = true; }
            if(is_bull_struct) { score += 10.0; sig.structure_confirmed = true; }

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
               sig.reason      = StringFormat("BALANCED_BULL (Conf:%.0f%%%s%s%s)", 
                                              score, sig.fvg_confirmed?"+FVG":"", sig.structure_confirmed?"+BOS":"", sig.ai_confirmed?"+AI":"");
               return sig;
            }
         }

         // SELL LOGIC
         if(!sell_sweep_trap && (regime == REGIME_STRONG_BEAR_TREND || regime == REGIME_MODERATE_BEAR_TREND))
         {
            double ema_micro_slow = m_analyzer.GetEMAMicroSlow(0);
            double ema_micro_fast = m_analyzer.GetEMAMicroFast(0);

            bool pullback_held = (m1_rates[1].high >= ema_micro_slow || m1_rates[1].close <= ema_micro_fast) && (m1_rates[0].close <= ema_micro_fast);
            bool price_action_ok = bear_pin || bear_engulf || bear_break;
            bool rsi_ok = (rsi_m1 <= 58.0 && rsi_m1 >= 36.0 && rsi_m5 < 50.0);
            bool momentum_ok = (mom_m1 <= 99.98);

            double score = 0.0;
            if(regime == REGIME_STRONG_BEAR_TREND) score += 25.0; else score += 15.0;
            if(pullback_held) score += 20.0;
            if(price_action_ok) score += 20.0;
            if(rsi_ok) score += 10.0;
            if(momentum_ok) score += 10.0;

            // Institutional Market Structure & FVG Confluence
            if(has_bear_fvg) { score += 10.0; sig.fvg_confirmed = true; }
            if(is_bear_struct) { score += 10.0; sig.structure_confirmed = true; }

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
               sig.reason      = StringFormat("BALANCED_BEAR (Conf:%.0f%%%s%s%s)", 
                                              score, sig.fvg_confirmed?"+FVG":"", sig.structure_confirmed?"+BOS":"", sig.ai_confirmed?"+AI":"");
               return sig;
            }
         }
      }

      //------------------------------------------------------------------
      // STRATEGY 2: AGGRESSIVE MODE (Momentum Scalp & Range Mean Reversion)
      //------------------------------------------------------------------
      else if(m_mode == MODE_AGGRESSIVE)
      {
         if(!buy_sweep_trap && (regime == REGIME_STRONG_BULL_TREND || regime == REGIME_MODERATE_BULL_TREND))
         {
            double ema_fast_curr = m_analyzer.GetEMAMicroFast(0);
            double ema_slow_curr = m_analyzer.GetEMAMicroSlow(0);

            bool momentum_surge = (mom_m1 >= 100.08) && (rsi_m1 > 52.0 && rsi_m1 < 75.0);
            bool fast_cross_or_bounce = (ema_fast_curr > ema_slow_curr) && (tick.ask > ema_fast_curr);

            if((momentum_surge && bull_break) || (fast_cross_or_bounce && bull_pin) || (has_bull_fvg && bull_break))
            {
               sig.type        = SIGNAL_BUY;
               sig.confidence  = 75.0;
               if(has_bull_fvg) { sig.confidence += 10.0; sig.fvg_confirmed = true; }
               if(has_ai && m_cached_ai_signal == SIGNAL_BUY) { sig.confidence += 15.0; sig.ai_confirmed = true; }
               sig.entry_price = tick.ask;
               sig.stop_loss   = tick.ask - (1.2 * atr_m1);
               sig.take_profit = tick.ask + (2.0 * atr_m1);
               sig.reason      = "AGGRESSIVE_BULL_MOMENTUM";
               return sig;
            }
         }
         else if(!sell_sweep_trap && (regime == REGIME_STRONG_BEAR_TREND || regime == REGIME_MODERATE_BEAR_TREND))
         {
            double ema_fast_curr = m_analyzer.GetEMAMicroFast(0);
            double ema_slow_curr = m_analyzer.GetEMAMicroSlow(0);

            bool momentum_surge = (mom_m1 <= 99.92) && (rsi_m1 < 48.0 && rsi_m1 > 25.0);
            bool fast_cross_or_bounce = (ema_fast_curr < ema_slow_curr) && (tick.bid < ema_fast_curr);

            if((momentum_surge && bear_break) || (fast_cross_or_bounce && bear_pin) || (has_bear_fvg && bear_break))
            {
               sig.type        = SIGNAL_SELL;
               sig.confidence  = 75.0;
               if(has_bear_fvg) { sig.confidence += 10.0; sig.fvg_confirmed = true; }
               if(has_ai && m_cached_ai_signal == SIGNAL_SELL) { sig.confidence += 15.0; sig.ai_confirmed = true; }
               sig.entry_price = tick.bid;
               sig.stop_loss   = tick.bid + (1.2 * atr_m1);
               sig.take_profit = tick.bid - (2.0 * atr_m1);
               sig.reason      = "AGGRESSIVE_BEAR_MOMENTUM";
               return sig;
            }
         }
         else if(regime == REGIME_RANGING_CONSOLIDATION)
         {
            if(rsi_m1 < 30.0 && bull_pin && !buy_sweep_trap)
            {
               sig.type        = SIGNAL_BUY;
               sig.confidence  = 65.0;
               sig.entry_price = tick.ask;
               sig.stop_loss   = tick.ask - (1.0 * atr_m1);
               sig.take_profit = tick.ask + (1.5 * atr_m1);
               sig.reason      = "AGGRESSIVE_RANGE_MEAN_REV_BUY";
               return sig;
            }
            else if(rsi_m1 > 70.0 && bear_pin && !sell_sweep_trap)
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
