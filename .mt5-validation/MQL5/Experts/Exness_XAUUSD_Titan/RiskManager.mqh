//+------------------------------------------------------------------+
//|                                                  RiskManager.mqh |
//|                                  Copyright 2026, Institutional Algo Team |
//|                             Institutional Risk & Capital Preservation |
//+------------------------------------------------------------------+
#property copyright "Copyright 2026, Institutional Algo Team"
#property link      "https://www.mql5.com"
#property strict

#include "TradeLogger.mqh"

enum ENUM_RISK_MODE
{
   RISK_MODE_PERCENT_EQUITY = 0,
   RISK_MODE_PERCENT_BALANCE= 1,
   RISK_MODE_FIXED_LOT      = 2
};

class CRiskManager
{
private:
   CTradeLogger*     m_logger;
   string            m_symbol;
   ulong             m_magic;

   // Risk Parameters
   ENUM_RISK_MODE    m_risk_mode;
   double            m_risk_percent_per_trade; // e.g. 1.0%
   double            m_fixed_lot_size;         // e.g. 0.01
   double            m_max_daily_drawdown_pct; // e.g. 3.0%
   bool              m_close_all_on_daily_dd;  // Close all positions on daily breach
   int               m_max_concurrent_pos;     // e.g. 2
   double            m_max_total_exposure_lots;// e.g. 0.50
   int               m_max_consecutive_losses; // e.g. 3
   int               m_streak_cooldown_min;    // e.g. 60 minutes

   // State tracking
   double            m_daily_start_equity;
   datetime          m_current_day;
   bool              m_daily_dd_breached;
   datetime          m_cooldown_until;
   int               m_consecutive_losses;
   double            m_daily_realized_pnl;

public:
   CRiskManager()
   {
      m_logger                  = NULL;
      m_symbol                  = "";
      m_magic                   = 0;
      m_risk_mode               = RISK_MODE_PERCENT_EQUITY;
      m_risk_percent_per_trade  = 1.0;
      m_fixed_lot_size          = 0.01;
      m_max_daily_drawdown_pct  = 3.0;
      m_close_all_on_daily_dd   = true;
      m_max_concurrent_pos      = 2;
      m_max_total_exposure_lots = 0.20;
      m_max_consecutive_losses  = 3;
      m_streak_cooldown_min     = 60;
      m_daily_start_equity      = 0.0;
      m_current_day             = 0;
      m_daily_dd_breached       = false;
      m_cooldown_until          = 0;
      m_consecutive_losses      = 0;
      m_daily_realized_pnl      = 0.0;
   }

   void Init(CTradeLogger* logger,
             const string symbol,
             const ulong magic,
             const ENUM_RISK_MODE risk_mode,
             const double risk_pct,
             const double fixed_lot,
             const double max_daily_dd,
             const bool close_all_on_dd,
             const int max_positions,
             const double max_exposure,
             const int max_loss_streak,
             const int streak_cooldown_minutes)
   {
      m_logger                  = logger;
      m_symbol                  = symbol;
      m_magic                   = magic;
      m_risk_mode               = risk_mode;
      m_risk_percent_per_trade  = risk_pct;
      m_fixed_lot_size          = fixed_lot;
      m_max_daily_drawdown_pct  = max_daily_dd;
      m_close_all_on_daily_dd   = close_all_on_dd;
      m_max_concurrent_pos      = max_positions;
      m_max_total_exposure_lots = max_exposure;
      m_max_consecutive_losses  = max_loss_streak;
      m_streak_cooldown_min     = streak_cooldown_minutes;

      SyncDailyState();
      CalculateLossStreak();
   }

   //+------------------------------------------------------------------+
   //| Synchronize Daily Starting Equity at midnight                    |
   //+------------------------------------------------------------------+
   void SyncDailyState()
   {
      MqlDateTime dt;
      TimeToStruct(TimeCurrent(), dt);
      datetime today_midnight = StringToTime(StringFormat("%04d.%02d.%02d 00:00", dt.year, dt.mon, dt.day));

      if(m_current_day != today_midnight)
      {
         m_current_day        = today_midnight;
         m_daily_start_equity = AccountInfoDouble(ACCOUNT_EQUITY);
         m_daily_dd_breached  = false;
         m_daily_realized_pnl = 0.0;

         if(m_logger != NULL)
         {
            m_logger.Info(StringFormat("New trading day initialized. Baseline Equity: $%.2f | Max Daily DD Limit: %.2f%% ($%.2f)",
                                       m_daily_start_equity, 
                                       m_max_daily_drawdown_pct, 
                                       m_daily_start_equity * (m_max_daily_drawdown_pct / 100.0)));
         }
      }
   }

   //+------------------------------------------------------------------+
   //| Calculate Consecutive Losses for current day                     |
   //+------------------------------------------------------------------+
   void CalculateLossStreak()
   {
      datetime from_time = m_current_day;
      datetime to_time   = TimeCurrent() + 60;

      if(!HistorySelect(from_time, to_time))
         return;

      int total_deals = HistoryDealsTotal();
      m_consecutive_losses = 0;
      m_daily_realized_pnl = 0.0;

      // Scan deals backwards to count the active loss streak
      bool streak_active = true;

      for(int i = total_deals - 1; i >= 0; i--)
      {
         ulong deal_ticket = HistoryDealGetTicket(i);
         if(deal_ticket == 0) continue;

         long deal_magic = HistoryDealGetInteger(deal_ticket, DEAL_MAGIC);
         if(deal_magic != (long)m_magic) continue;

         ENUM_DEAL_ENTRY entry = (ENUM_DEAL_ENTRY)HistoryDealGetInteger(deal_ticket, DEAL_ENTRY);
         if(entry != DEAL_ENTRY_OUT && entry != DEAL_ENTRY_INOUT) continue;

         double profit = HistoryDealGetDouble(deal_ticket, DEAL_PROFIT) +
                         HistoryDealGetDouble(deal_ticket, DEAL_SWAP) +
                         HistoryDealGetDouble(deal_ticket, DEAL_COMMISSION);

         m_daily_realized_pnl += profit;

         if(streak_active)
         {
            if(profit < -0.01) // Losing trade
            {
               m_consecutive_losses++;
            }
            else if(profit > 0.01) // Winning trade breaks the streak
            {
               streak_active = false;
            }
         }
      }

      // Check if streak triggers cooldown
      if(m_consecutive_losses >= m_max_consecutive_losses && m_streak_cooldown_min > 0)
      {
         datetime cooldown_target = TimeCurrent() + (m_streak_cooldown_min * 60);
         if(cooldown_target > m_cooldown_until)
         {
            m_cooldown_until = cooldown_target;
            if(m_logger != NULL)
            {
               m_logger.Warn(StringFormat("Consecutive loss limit reached (%d losses)! Trading cooled down until: %s",
                                          m_consecutive_losses, TimeToString(m_cooldown_until, TIME_MINUTES|TIME_SECONDS)));
            }
         }
      }
   }

   //+------------------------------------------------------------------+
   //| Drawdown and Risk Monitoring Check                               |
   //+------------------------------------------------------------------+
   bool CheckRiskState(bool &emergency_shutdown_required)
   {
      emergency_shutdown_required = false;
      SyncDailyState();

      double current_equity = AccountInfoDouble(ACCOUNT_EQUITY);
      if(m_daily_start_equity <= 0.0)
         m_daily_start_equity = current_equity;

      // Daily Drawdown calculation:
      double dd_amount = m_daily_start_equity - current_equity;
      double dd_pct    = (dd_amount / m_daily_start_equity) * 100.0;

      if(dd_pct >= m_max_daily_drawdown_pct)
      {
         if(!m_daily_dd_breached)
         {
            m_daily_dd_breached = true;
            if(m_logger != NULL)
            {
               m_logger.Error(StringFormat("MAX DAILY DRAWDOWN BREACHED! Current DD: %.2f%% >= Max Allowed: %.2f%%. Daily baseline: $%.2f | Equity: $%.2f",
                                           dd_pct, m_max_daily_drawdown_pct, m_daily_start_equity, current_equity));
            }
         }

         if(m_close_all_on_daily_dd)
            emergency_shutdown_required = true;

         return false; // Trading blocked
      }

      // Cooldown timer check
      if(TimeCurrent() < m_cooldown_until)
         return false;

      return true;
   }

   //+------------------------------------------------------------------+
   //| Dynamic Lot Sizing Calculation                                   |
   //+------------------------------------------------------------------+
   double CalculateLotSize(const double entry_price, const double stop_loss_price)
   {
      double lot_step = SymbolInfoDouble(m_symbol, SYMBOL_VOLUME_STEP);
      double lot_min  = SymbolInfoDouble(m_symbol, SYMBOL_VOLUME_MIN);
      double lot_max  = SymbolInfoDouble(m_symbol, SYMBOL_VOLUME_MAX);
      double point    = SymbolInfoDouble(m_symbol, SYMBOL_POINT);
      double tick_sz  = SymbolInfoDouble(m_symbol, SYMBOL_TRADE_TICK_SIZE);
      double tick_val = SymbolInfoDouble(m_symbol, SYMBOL_TRADE_TICK_VALUE);

      if(m_risk_mode == RISK_MODE_FIXED_LOT)
      {
         return NormalizeLot(m_fixed_lot_size, lot_min, lot_max, lot_step);
      }

      double sl_distance_price = MathAbs(entry_price - stop_loss_price);
      if(sl_distance_price <= 0.0 || point <= 0.0 || tick_sz <= 0.0 || tick_val <= 0.0)
      {
         return NormalizeLot(m_fixed_lot_size, lot_min, lot_max, lot_step);
      }

      double capital = (m_risk_mode == RISK_MODE_PERCENT_EQUITY) ? AccountInfoDouble(ACCOUNT_EQUITY) : AccountInfoDouble(ACCOUNT_BALANCE);
      double risk_capital = capital * (m_risk_percent_per_trade / 100.0);

      // Value of 1 point per 1.0 standard lot
      double points = sl_distance_price / point;
      double value_per_point = tick_val / (tick_sz / point);

      if(points * value_per_point <= 0.0)
         return NormalizeLot(lot_min, lot_min, lot_max, lot_step);

      double calculated_lots = risk_capital / (points * value_per_point);

      // Margin verification check
      double free_margin = AccountInfoDouble(ACCOUNT_MARGIN_FREE);
      double required_margin = 0.0;
      if(OrderCalcMargin(ORDER_TYPE_BUY, m_symbol, calculated_lots, entry_price, required_margin))
      {
         if(required_margin > free_margin * 0.70) // Do not consume more than 70% free margin on a single trade
         {
            double safe_ratio = (free_margin * 0.70) / required_margin;
            calculated_lots   = calculated_lots * safe_ratio;
            if(m_logger != NULL)
               m_logger.Warn(StringFormat("Lot scaled down due to margin constraints. Adjusted: %.2f Lots", calculated_lots));
         }
      }

      return NormalizeLot(calculated_lots, lot_min, lot_max, lot_step);
   }

   //+------------------------------------------------------------------+
   //| Normalize Lot to broker requirements                             |
   //+------------------------------------------------------------------+
   double NormalizeLot(const double raw_lot, const double min_lot, const double max_lot, const double step_lot)
   {
      if(step_lot <= 0.0) return min_lot;

      double steps = MathFloor(raw_lot / step_lot);
      double normalized = steps * step_lot;

      if(normalized < min_lot) normalized = min_lot;
      if(normalized > max_lot) normalized = max_lot;

      // Digits precision based on step
      int digits = 2;
      if(step_lot == 1.0)        digits = 0;
      else if(step_lot == 0.1)   digits = 1;
      else if(step_lot == 0.01)  digits = 2;
      else if(step_lot == 0.001) digits = 3;

      return NormalizeDouble(normalized, digits);
   }

   //+------------------------------------------------------------------+
   //| Concurrency & Exposure Checks                                    |
   //+------------------------------------------------------------------+
   bool CanOpenNewPosition(const int current_open_positions, const double current_exposure_lots, const double candidate_lot)
   {
      if(m_daily_dd_breached)
      {
         if(m_logger != NULL) m_logger.Warn("New trade blocked: Daily drawdown limit is active.");
         return false;
      }

      if(TimeCurrent() < m_cooldown_until)
      {
         if(m_logger != NULL) m_logger.Warn(StringFormat("New trade blocked: Consecutive loss cooldown active until %s.", TimeToString(m_cooldown_until)));
         return false;
      }

      if(current_open_positions >= m_max_concurrent_pos)
      {
         if(m_logger != NULL) m_logger.Warn(StringFormat("New trade blocked: Max concurrent positions reached (%d/%d).", current_open_positions, m_max_concurrent_pos));
         return false;
      }

      if(current_exposure_lots + candidate_lot > m_max_total_exposure_lots)
      {
         if(m_logger != NULL) m_logger.Warn(StringFormat("New trade blocked: Max exposure exceeded (Current: %.2f + New: %.2f > Max: %.2f).", 
                                                        current_exposure_lots, candidate_lot, m_max_total_exposure_lots));
         return false;
      }

      return true;
   }

   // Getters for Dashboard
   double   GetDailyStartEquity()      const { return m_daily_start_equity; }
   double   GetDailyRealizedPnL()      const { return m_daily_realized_pnl; }
   bool     IsDailyDrawdownBreached()   const { return m_daily_dd_breached; }
   int      GetConsecutiveLosses()     const { return m_consecutive_losses; }
   int      GetMaxConsecutiveLosses()  const { return m_max_consecutive_losses; }
   double   GetMaxDailyDrawdownPct()   const { return m_max_daily_drawdown_pct; }
   int      GetMaxConcurrentPositions()const { return m_max_concurrent_pos; }
   bool     IsCooldownActive()         const { return TimeCurrent() < m_cooldown_until; }
   datetime GetCooldownUntil()         const { return m_cooldown_until; }
};
