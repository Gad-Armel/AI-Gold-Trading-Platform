//+------------------------------------------------------------------+
//|                                               MarketAnalyzer.mqh |
//|                                  Copyright 2026, Institutional Algo Team |
//|              Ultimate Market Structure, Regime & Liquidity Engine |
//+------------------------------------------------------------------+
#property copyright "Copyright 2026, Institutional Algo Team"
#property link      "https://www.mql5.com"
#property strict

#include "TradeLogger.mqh"

enum ENUM_MARKET_REGIME
{
   REGIME_UNKNOWN                  = 0,
   REGIME_STRONG_BULL_TREND        = 1,
   REGIME_MODERATE_BULL_TREND      = 2,
   REGIME_STRONG_BEAR_TREND        = 3,
   REGIME_MODERATE_BEAR_TREND      = 4,
   REGIME_RANGING_CONSOLIDATION    = 5,
   REGIME_HIGH_VOLATILITY_EXPANSION= 6,
   REGIME_ADVERSE_SPREAD           = 7
};

enum ENUM_STRUCTURE_EVENT
{
   STRUCT_NONE          = 0,
   STRUCT_BOS_BULL      = 1,  // Break of Structure Bullish
   STRUCT_BOS_BEAR      = 2,  // Break of Structure Bearish
   STRUCT_CHOCH_BULL    = 3,  // Change of Character Bullish
   STRUCT_CHOCH_BEAR    = 4   // Change of Character Bearish
};

//+------------------------------------------------------------------+
//| Circular Buffer for Rolling Spread Statistics                     |
//+------------------------------------------------------------------+
class CSpreadRollingWindow
{
private:
   double m_values[50];
   double m_sum;
   int    m_next;
   int    m_count;
public:
   CSpreadRollingWindow() { Reset(); }
   void Reset() { m_sum = 0.0; m_next = 0; m_count = 0; ArrayInitialize(m_values, 0.0); }
   int Count() const { return m_count; }
   double Mean() const { return (m_count > 0) ? (m_sum / m_count) : 0.0; }
   
   void Add(const double spread)
   {
      if(spread < 0.0) return;
      if(m_count == 50) m_sum -= m_values[m_next]; else m_count++;
      m_values[m_next] = spread;
      m_sum += spread;
      m_next = (m_next + 1) % 50;
   }
   
   bool IsSpreadElevated(const double current_spread, const double multiplier) const
   {
      if(m_count < 20) return false;
      double mean = Mean();
      return (mean > 0.0 && current_spread > (mean * multiplier));
   }
};

class CMarketAnalyzer
{
private:
   CTradeLogger*        m_logger;
   string               m_symbol;
   ENUM_TIMEFRAMES      m_tf_micro;
   ENUM_TIMEFRAMES      m_tf_macro;

   // Indicator Handles
   int                  m_h_ema_macro_base;  // M5 EMA 200
   int                  m_h_ema_macro_trend; // M5 EMA 50
   int                  m_h_ema_micro_fast;  // M1 EMA 9
   int                  m_h_ema_micro_slow;  // M1 EMA 21
   int                  m_h_rsi_micro;       // M1 RSI 14
   int                  m_h_rsi_macro;       // M5 RSI 14
   int                  m_h_atr_micro;       // M1 ATR 14
   int                  m_h_atr_macro;       // M5 ATR 14
   int                  m_h_mom_micro;       // M1 Momentum 14

   // Dynamic Buffer Values (Series indexed: 0 = current, 1 = previous)
   double               m_val_ema_macro_base[];
   double               m_val_ema_macro_trend[];
   double               m_val_ema_micro_fast[];
   double               m_val_ema_micro_slow[];
   double               m_val_rsi_micro[];
   double               m_val_rsi_macro[];
   double               m_val_atr_micro[];
   double               m_val_atr_macro[];
   double               m_val_mom_micro[];

   // Dynamic Rates Arrays
   MqlRates             m_rates_micro[];
   MqlRates             m_rates_macro[];
   MqlTick              m_last_tick;

   // Rolling Spread Window
   CSpreadRollingWindow m_spread_window;
   double               m_spread_multiplier;

   // Market state & Structure
   ENUM_MARKET_REGIME   m_current_regime;
   ENUM_STRUCTURE_EVENT m_last_structure_event;
   double               m_current_spread_pts;
   double               m_max_spread_pts;
   double               m_volatility_expansion_ratio;
   datetime             m_last_analysis_time;
   ulong                m_last_analysis_microsecond;

   // Fair Value Gaps (FVG)
   bool                 m_has_bullish_fvg;
   double               m_fvg_bull_top;
   double               m_fvg_bull_bottom;
   bool                 m_has_bearish_fvg;
   double               m_fvg_bear_top;
   double               m_fvg_bear_bottom;

   // Liquidity Sweeps / Traps
   bool                 m_sweep_buy_trap;
   bool                 m_sweep_sell_trap;

   // Symbol specifications
   double               m_point;
   int                  m_digits;
   double               m_tick_size;
   double               m_tick_value;
   double               m_lot_min;
   double               m_lot_max;
   double               m_lot_step;
   int                  m_stops_level;
   int                  m_freeze_level;

public:
   CMarketAnalyzer()
   {
      m_logger                   = NULL;
      m_symbol                   = "";
      m_tf_micro                 = PERIOD_M1;
      m_tf_macro                 = PERIOD_M5;
      m_h_ema_macro_base         = INVALID_HANDLE;
      m_h_ema_macro_trend        = INVALID_HANDLE;
      m_h_ema_micro_fast         = INVALID_HANDLE;
      m_h_ema_micro_slow         = INVALID_HANDLE;
      m_h_rsi_micro              = INVALID_HANDLE;
      m_h_rsi_macro              = INVALID_HANDLE;
      m_h_atr_micro              = INVALID_HANDLE;
      m_h_atr_macro              = INVALID_HANDLE;
      m_h_mom_micro              = INVALID_HANDLE;
      m_current_regime           = REGIME_UNKNOWN;
      m_last_structure_event     = STRUCT_NONE;
      m_current_spread_pts       = 0.0;
      m_max_spread_pts           = 40.0;
      m_spread_multiplier        = 1.8;
      m_volatility_expansion_ratio= 1.0;
      m_last_analysis_time       = 0;
      m_last_analysis_microsecond= 0;

      m_has_bullish_fvg          = false;
      m_fvg_bull_top             = 0.0;
      m_fvg_bull_bottom          = 0.0;
      m_has_bearish_fvg          = false;
      m_fvg_bear_top             = 0.0;
      m_fvg_bear_bottom          = 0.0;

      m_sweep_buy_trap           = false;
      m_sweep_sell_trap          = false;

      ArraySetAsSeries(m_rates_micro, true);
      ArraySetAsSeries(m_rates_macro, true);
      ArraySetAsSeries(m_val_ema_macro_base, true);
      ArraySetAsSeries(m_val_ema_macro_trend, true);
      ArraySetAsSeries(m_val_ema_micro_fast, true);
      ArraySetAsSeries(m_val_ema_micro_slow, true);
      ArraySetAsSeries(m_val_rsi_micro, true);
      ArraySetAsSeries(m_val_rsi_macro, true);
      ArraySetAsSeries(m_val_atr_micro, true);
      ArraySetAsSeries(m_val_atr_macro, true);
      ArraySetAsSeries(m_val_mom_micro, true);
   }

   ~CMarketAnalyzer()
   {
      ReleaseIndicators();
   }

   void ReleaseIndicators()
   {
      if(m_h_ema_macro_base  != INVALID_HANDLE) { IndicatorRelease(m_h_ema_macro_base);  m_h_ema_macro_base  = INVALID_HANDLE; }
      if(m_h_ema_macro_trend != INVALID_HANDLE) { IndicatorRelease(m_h_ema_macro_trend); m_h_ema_macro_trend = INVALID_HANDLE; }
      if(m_h_ema_micro_fast  != INVALID_HANDLE) { IndicatorRelease(m_h_ema_micro_fast);  m_h_ema_micro_fast  = INVALID_HANDLE; }
      if(m_h_ema_micro_slow  != INVALID_HANDLE) { IndicatorRelease(m_h_ema_micro_slow);  m_h_ema_micro_slow  = INVALID_HANDLE; }
      if(m_h_rsi_micro       != INVALID_HANDLE) { IndicatorRelease(m_h_rsi_micro);       m_h_rsi_micro       = INVALID_HANDLE; }
      if(m_h_rsi_macro       != INVALID_HANDLE) { IndicatorRelease(m_h_rsi_macro);       m_h_rsi_macro       = INVALID_HANDLE; }
      if(m_h_atr_micro       != INVALID_HANDLE) { IndicatorRelease(m_h_atr_micro);       m_h_atr_micro       = INVALID_HANDLE; }
      if(m_h_atr_macro       != INVALID_HANDLE) { IndicatorRelease(m_h_atr_macro);       m_h_atr_macro       = INVALID_HANDLE; }
      if(m_h_mom_micro       != INVALID_HANDLE) { IndicatorRelease(m_h_mom_micro);       m_h_mom_micro       = INVALID_HANDLE; }
   }

   //+------------------------------------------------------------------+
   //| Auto-detect Exness XAUUSD Broker Suffix and Select Symbol        |
   //+------------------------------------------------------------------+
   bool ResolveAndInitSymbol(const string requested_symbol, CTradeLogger* logger)
   {
      m_logger = logger;
      string candidate = requested_symbol;
      StringTrimLeft(candidate);
      StringTrimRight(candidate);

      if(candidate == "" || candidate == "AUTO" || candidate == "auto")
      {
         string chart_sym = _Symbol;
         string chart_upper = chart_sym;
         StringToUpper(chart_upper);

         if(StringFind(chart_upper, "XAU") >= 0 || StringFind(chart_upper, "GOLD") >= 0)
         {
            candidate = chart_sym;
         }
         else
         {
            candidate = SearchGoldSymbol(false);
            if(candidate == "") candidate = SearchGoldSymbol(true);
         }
      }

      if(candidate == "")
      {
         if(m_logger != NULL) m_logger.Error("Failed to auto-detect XAUUSD symbol with broker suffix!");
         return false;
      }

      if(!SymbolSelect(candidate, true))
      {
         if(m_logger != NULL) m_logger.Error(StringFormat("SymbolSelect failed for resolved symbol: %s", candidate));
         return false;
      }

      long trade_mode = SymbolInfoInteger(candidate, SYMBOL_TRADE_MODE);
      if(trade_mode == SYMBOL_TRADE_MODE_DISABLED)
      {
         if(m_logger != NULL) m_logger.Error(StringFormat("Trading is DISABLED on symbol: %s", candidate));
         return false;
      }

      m_symbol       = candidate;
      m_point        = SymbolInfoDouble(m_symbol, SYMBOL_POINT);
      m_digits       = (int)SymbolInfoInteger(m_symbol, SYMBOL_DIGITS);
      m_tick_size    = SymbolInfoDouble(m_symbol, SYMBOL_TRADE_TICK_SIZE);
      m_tick_value   = SymbolInfoDouble(m_symbol, SYMBOL_TRADE_TICK_VALUE);
      m_lot_min      = SymbolInfoDouble(m_symbol, SYMBOL_VOLUME_MIN);
      m_lot_max      = SymbolInfoDouble(m_symbol, SYMBOL_VOLUME_MAX);
      m_lot_step     = SymbolInfoDouble(m_symbol, SYMBOL_VOLUME_STEP);
      m_stops_level  = (int)SymbolInfoInteger(m_symbol, SYMBOL_TRADE_STOPS_LEVEL);
      m_freeze_level = (int)SymbolInfoInteger(m_symbol, SYMBOL_TRADE_FREEZE_LEVEL);

      if(m_logger != NULL)
      {
         m_logger.Info(StringFormat("Successfully resolved XAUUSD symbol: '%s' | Digits: %d | Point: %.5f | TickSize: %.5f | TickVal: %.2f | LotStep: %.2f",
                                    m_symbol, m_digits, m_point, m_tick_size, m_tick_value, m_lot_step));
      }

      return true;
   }

   string SearchGoldSymbol(const bool search_all)
   {
      int total = SymbolsTotal(search_all);
      string preferred_names[] = {
         "XAUUSD", "XAUUSDm", "XAUUSD.r", "XAUUSDz", "XAUUSDc", "GOLD", "GOLDm", "XAUUSD.", "XAUUSD_", "XAUUSD.s"
      };

      for(int p = 0; p < ArraySize(preferred_names); p++)
      {
         for(int i = 0; i < total; i++)
         {
            string name = SymbolName(i, search_all);
            if(name == preferred_names[p]) return name;
         }
      }

      for(int i = 0; i < total; i++)
      {
         string name = SymbolName(i, search_all);
         string upper = name;
         StringToUpper(upper);
         if((StringFind(upper, "XAU") >= 0 && StringFind(upper, "USD") >= 0) || StringFind(upper, "GOLD") >= 0)
         {
            return name;
         }
      }
      return "";
   }

   //+------------------------------------------------------------------+
   //| Initialize Indicator Handles                                     |
   //+------------------------------------------------------------------+
   bool InitIndicators(const ENUM_TIMEFRAMES tf_micro,
                       const ENUM_TIMEFRAMES tf_macro,
                       const int ema_macro_base_period   = 200,
                       const int ema_macro_trend_period  = 50,
                       const int ema_micro_fast_period   = 9,
                       const int ema_micro_slow_period   = 21,
                       const int rsi_period              = 14,
                       const int atr_period              = 14,
                       const int mom_period              = 14,
                       const double max_spread_pts       = 40.0,
                       const double spread_mult          = 1.8)
   {
      m_tf_micro          = tf_micro;
      m_tf_macro          = tf_macro;
      m_max_spread_pts    = max_spread_pts;
      m_spread_multiplier = spread_mult;

      ReleaseIndicators();

      m_h_ema_macro_base  = iMA(m_symbol, m_tf_macro, ema_macro_base_period, 0, MODE_EMA, PRICE_CLOSE);
      m_h_ema_macro_trend = iMA(m_symbol, m_tf_macro, ema_macro_trend_period, 0, MODE_EMA, PRICE_CLOSE);
      m_h_ema_micro_fast  = iMA(m_symbol, m_tf_micro, ema_micro_fast_period, 0, MODE_EMA, PRICE_CLOSE);
      m_h_ema_micro_slow  = iMA(m_symbol, m_tf_micro, ema_micro_slow_period, 0, MODE_EMA, PRICE_CLOSE);
      m_h_rsi_micro       = iRSI(m_symbol, m_tf_micro, rsi_period, PRICE_CLOSE);
      m_h_rsi_macro       = iRSI(m_symbol, m_tf_macro, rsi_period, PRICE_CLOSE);
      m_h_atr_micro       = iATR(m_symbol, m_tf_micro, atr_period);
      m_h_atr_macro       = iATR(m_symbol, m_tf_macro, atr_period);
      m_h_mom_micro       = iMomentum(m_symbol, m_tf_micro, mom_period, PRICE_CLOSE);

      if(m_h_ema_macro_base == INVALID_HANDLE || m_h_ema_macro_trend == INVALID_HANDLE ||
         m_h_ema_micro_fast == INVALID_HANDLE || m_h_ema_micro_slow  == INVALID_HANDLE ||
         m_h_rsi_micro      == INVALID_HANDLE || m_h_rsi_macro       == INVALID_HANDLE ||
         m_h_atr_micro      == INVALID_HANDLE || m_h_atr_macro       == INVALID_HANDLE ||
         m_h_mom_micro      == INVALID_HANDLE)
      {
         if(m_logger != NULL)
            m_logger.Error(StringFormat("Failed to create indicator handles on %s! Error: %d", m_symbol, GetLastError()));
         return false;
      }

      if(m_logger != NULL) m_logger.Info("All multi-timeframe indicator handles created successfully.");
      return true;
   }

   //+------------------------------------------------------------------+
   //| Fast Tick Update, Structure Analysis & Regime Classification    |
   //+------------------------------------------------------------------+
   bool Update(const MqlTick &tick)
   {
      m_last_tick = tick;
      
      if(m_point > 0.0)
         m_current_spread_pts = (m_last_tick.ask - m_last_tick.bid) / m_point;
      else
         m_current_spread_pts = 0.0;

      // Update rolling spread window
      m_spread_window.Add(m_current_spread_pts);

      // Copy recent rates (6 bars)
      if(CopyRates(m_symbol, m_tf_micro, 0, 6, m_rates_micro) < 6) return false;
      if(CopyRates(m_symbol, m_tf_macro, 0, 6, m_rates_macro) < 6) return false;

      // Copy indicator buffers (latest 3 bars)
      if(CopyBuffer(m_h_ema_macro_base,  0, 0, 3, m_val_ema_macro_base)  < 3) return false;
      if(CopyBuffer(m_h_ema_macro_trend, 0, 0, 3, m_val_ema_macro_trend) < 3) return false;
      if(CopyBuffer(m_h_ema_micro_fast,  0, 0, 3, m_val_ema_micro_fast)  < 3) return false;
      if(CopyBuffer(m_h_ema_micro_slow,  0, 0, 3, m_val_ema_micro_slow)  < 3) return false;
      if(CopyBuffer(m_h_rsi_micro,       0, 0, 3, m_val_rsi_micro)       < 3) return false;
      if(CopyBuffer(m_h_rsi_macro,       0, 0, 3, m_val_rsi_macro)       < 3) return false;
      if(CopyBuffer(m_h_atr_micro,       0, 0, 3, m_val_atr_micro)       < 3) return false;
      if(CopyBuffer(m_h_atr_macro,       0, 0, 3, m_val_atr_macro)       < 3) return false;
      if(CopyBuffer(m_h_mom_micro,       0, 0, 3, m_val_mom_micro)       < 3) return false;

      // Advanced Structure Analyses
      AnalyzeFairValueGaps();
      AnalyzeLiquiditySweeps();
      AnalyzeMarketStructureEvents();
      ClassifyRegime();

      m_last_analysis_time = TimeCurrent();
      m_last_analysis_microsecond = GetMicrosecondCount();

      return true;
   }

   //+------------------------------------------------------------------+
   //| Fair Value Gap (FVG / 3-Bar Imbalance) Detection                 |
   //+------------------------------------------------------------------+
   void AnalyzeFairValueGaps()
   {
      m_has_bullish_fvg = false;
      m_has_bearish_fvg = false;

      double min_gap_dist = 1.0 * m_val_atr_micro[0] * 0.4; // At least 40% of M1 ATR

      // Bullish FVG on closed bars: Low of bar 1 is higher than High of bar 3
      if(m_rates_micro[1].low > (m_rates_micro[3].high + min_gap_dist))
      {
         m_has_bullish_fvg = true;
         m_fvg_bull_top    = m_rates_micro[1].low;
         m_fvg_bull_bottom = m_rates_micro[3].high;
      }

      // Bearish FVG on closed bars: High of bar 1 is lower than Low of bar 3
      if(m_rates_micro[1].high < (m_rates_micro[3].low - min_gap_dist))
      {
         m_has_bearish_fvg = true;
         m_fvg_bear_top    = m_rates_micro[3].low;
         m_fvg_bear_bottom = m_rates_micro[1].high;
      }
   }

   //+------------------------------------------------------------------+
   //| Liquidity Sweep / False Breakout Trap Detection                  |
   //+------------------------------------------------------------------+
   void AnalyzeLiquiditySweeps()
   {
      m_sweep_buy_trap  = false;
      m_sweep_sell_trap = false;

      double prior_high = MathMax(m_rates_micro[2].high, m_rates_micro[3].high);
      double prior_low  = MathMin(m_rates_micro[2].low,  m_rates_micro[3].low);

      double range_1 = m_rates_micro[1].high - m_rates_micro[1].low;
      if(range_1 > 0.0)
      {
         double upper_wick = (m_rates_micro[1].high - MathMax(m_rates_micro[1].open, m_rates_micro[1].close)) / range_1;
         double lower_wick = (MathMin(m_rates_micro[1].open, m_rates_micro[1].close) - m_rates_micro[1].low) / range_1;

         // Swept prior high but failed to close above (rejection trap)
         if(m_rates_micro[1].high > prior_high && m_rates_micro[1].close < prior_high && upper_wick >= 0.35)
         {
            m_sweep_buy_trap = true;
         }

         // Swept prior low but failed to close below (rejection trap)
         if(m_rates_micro[1].low < prior_low && m_rates_micro[1].close > prior_low && lower_wick >= 0.35)
         {
            m_sweep_sell_trap = true;
         }
      }
   }

   //+------------------------------------------------------------------+
   //| Market Structure Events (BOS & CHoCH)                            |
   //+------------------------------------------------------------------+
   void AnalyzeMarketStructureEvents()
   {
      m_last_structure_event = STRUCT_NONE;

      double swing_high = MathMax(m_rates_macro[2].high, m_rates_macro[3].high);
      double swing_low  = MathMin(m_rates_macro[2].low,  m_rates_macro[3].low);
      double close_now  = m_rates_macro[0].close;

      double ema_trend = m_val_ema_macro_trend[0];
      double ema_base  = m_val_ema_macro_base[0];

      if(close_now > swing_high)
      {
         if(ema_trend > ema_base)
            m_last_structure_event = STRUCT_BOS_BULL;
         else
            m_last_structure_event = STRUCT_CHOCH_BULL;
      }
      else if(close_now < swing_low)
      {
         if(ema_trend < ema_base)
            m_last_structure_event = STRUCT_BOS_BEAR;
         else
            m_last_structure_event = STRUCT_CHOCH_BEAR;
      }
   }

   //+------------------------------------------------------------------+
   //| Institutional Multi-Timeframe Regime Detection Logic             |
   //+------------------------------------------------------------------+
   void ClassifyRegime()
   {
      // 1. Absolute & Rolling Spread Check
      if(m_current_spread_pts > m_max_spread_pts || m_spread_window.IsSpreadElevated(m_current_spread_pts, m_spread_multiplier))
      {
         m_current_regime = REGIME_ADVERSE_SPREAD;
         return;
      }

      // 2. Volatility Shock Check
      if(m_val_atr_macro[0] > 0.0)
         m_volatility_expansion_ratio = m_val_atr_micro[0] / (m_val_atr_macro[0] / 2.0);
      else
         m_volatility_expansion_ratio = 1.0;

      if(m_volatility_expansion_ratio > 1.85)
      {
         m_current_regime = REGIME_HIGH_VOLATILITY_EXPANSION;
         return;
      }

      // 3. Trend Alignment Check
      double close_macro = m_rates_macro[0].close;
      double ema_trend   = m_val_ema_macro_trend[0]; // M5 EMA 50
      double ema_base    = m_val_ema_macro_base[0];  // M5 EMA 200
      double slope_trend = m_val_ema_macro_trend[0] - m_val_ema_macro_trend[2];

      double close_micro = m_rates_micro[0].close;
      double ema_fast    = m_val_ema_micro_fast[0];   // M1 EMA 9
      double ema_slow    = m_val_ema_micro_slow[0];   // M1 EMA 21
      double rsi_macro   = m_val_rsi_macro[0];
      double rsi_micro   = m_val_rsi_micro[0];

      if(close_macro > ema_trend && ema_trend > ema_base && slope_trend > 0.0 && rsi_macro > 54.0)
      {
         if(ema_fast > ema_slow && close_micro > ema_fast && rsi_micro > 50.0)
            m_current_regime = REGIME_STRONG_BULL_TREND;
         else
            m_current_regime = REGIME_MODERATE_BULL_TREND;
         return;
      }

      if(close_macro < ema_trend && ema_trend < ema_base && slope_trend < 0.0 && rsi_macro < 46.0)
      {
         if(ema_fast < ema_slow && close_micro < ema_fast && rsi_micro < 50.0)
            m_current_regime = REGIME_STRONG_BEAR_TREND;
         else
            m_current_regime = REGIME_MODERATE_BEAR_TREND;
         return;
      }

      // 4. Ranging Consolidation
      double dist_ema = MathAbs(ema_trend - ema_base);
      if(dist_ema < (m_val_atr_macro[0] * 0.8) && rsi_macro >= 42.0 && rsi_macro <= 58.0)
      {
         m_current_regime = REGIME_RANGING_CONSOLIDATION;
         return;
      }

      if(close_macro > ema_trend)
         m_current_regime = REGIME_MODERATE_BULL_TREND;
      else if(close_macro < ema_trend)
         m_current_regime = REGIME_MODERATE_BEAR_TREND;
      else
         m_current_regime = REGIME_RANGING_CONSOLIDATION;
   }

   // Getters
   string             GetSymbol()                  const { return m_symbol; }
   ENUM_MARKET_REGIME GetRegime()                  const { return m_current_regime; }
   ENUM_STRUCTURE_EVENT GetStructureEvent()        const { return m_last_structure_event; }
   double             GetSpreadPts()               const { return m_current_spread_pts; }
   double             GetRollingMeanSpread()       const { return m_spread_window.Mean(); }
   double             GetPoint()                   const { return m_point; }
   int                GetDigits()                  const { return m_digits; }
   double             GetTickSize()                const { return m_tick_size; }
   double             GetTickValue()               const { return m_tick_value; }
   double             GetLotMin()                  const { return m_lot_min; }
   double             GetLotMax()                  const { return m_lot_max; }
   double             GetLotStep()                 const { return m_lot_step; }
   int                GetStopsLevel()              const { return m_stops_level; }
   int                GetFreezeLevel()             const { return m_freeze_level; }

   bool               HasBullishFVG()              const { return m_has_bullish_fvg; }
   bool               HasBearishFVG()              const { return m_has_bearish_fvg; }
   bool               IsBuyTrapSweep()             const { return m_sweep_buy_trap; }
   bool               IsSellTrapSweep()            const { return m_sweep_sell_trap; }
   
   double             GetATR_Micro(const int shift=0) const { return m_val_atr_micro[shift]; }
   double             GetATR_Macro(const int shift=0) const { return m_val_atr_macro[shift]; }
   double             GetRSI_Micro(const int shift=0) const { return m_val_rsi_micro[shift]; }
   double             GetRSI_Macro(const int shift=0) const { return m_val_rsi_macro[shift]; }
   double             GetMom_Micro(const int shift=0) const { return m_val_mom_micro[shift]; }
   double             GetEMAMacroTrend(const int shift=0) const { return m_val_ema_macro_trend[shift]; }
   double             GetEMAMacroBase(const int shift=0)  const { return m_val_ema_macro_base[shift]; }
   double             GetEMAMicroFast(const int shift=0)  const { return m_val_ema_micro_fast[shift]; }
   double             GetEMAMicroSlow(const int shift=0)  const { return m_val_ema_micro_slow[shift]; }

   void GetMicroRates(MqlRates &rates[]) const { ArrayCopy(rates, m_rates_micro); }
   void GetMacroRates(MqlRates &rates[]) const { ArrayCopy(rates, m_rates_macro); }

   string GetRegimeName() const
   {
      switch(m_current_regime)
      {
         case REGIME_STRONG_BULL_TREND:         return "STRONG_BULL_TREND";
         case REGIME_MODERATE_BULL_TREND:       return "MODERATE_BULL_TREND";
         case REGIME_STRONG_BEAR_TREND:         return "STRONG_BEAR_TREND";
         case REGIME_MODERATE_BEAR_TREND:       return "MODERATE_BEAR_TREND";
         case REGIME_RANGING_CONSOLIDATION:     return "RANGING_CONSOLIDATION";
         case REGIME_HIGH_VOLATILITY_EXPANSION: return "HIGH_VOLATILITY_EXPANSION";
         case REGIME_ADVERSE_SPREAD:            return "ADVERSE_SPREAD_BLOCKED";
         default:                               return "UNKNOWN";
      }
   }

   string GetStructureEventName() const
   {
      switch(m_last_structure_event)
      {
         case STRUCT_BOS_BULL:   return "BOS_BULL";
         case STRUCT_BOS_BEAR:   return "BOS_BEAR";
         case STRUCT_CHOCH_BULL: return "CHOCH_BULL";
         case STRUCT_CHOCH_BEAR: return "CHOCH_BEAR";
         default:                return "STRUCTURE_ALIGNED";
      }
   }
};
