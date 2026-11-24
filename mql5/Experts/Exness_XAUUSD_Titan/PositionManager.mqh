//+------------------------------------------------------------------+
//|                                              PositionManager.mqh |
//|                                  Copyright 2026, Institutional Algo Team |
//|                             Active Position Lifecycle & Trade Management |
//+------------------------------------------------------------------+
#property copyright "Copyright 2026, Institutional Algo Team"
#property link      "https://www.mql5.com"
#property strict

#include "TradeLogger.mqh"
#include "ExecutionEngine.mqh"
#include "MarketAnalyzer.mqh"

class CPositionManager
{
private:
   CTradeLogger*     m_logger;
   CExecutionEngine* m_execution;
   CMarketAnalyzer*  m_analyzer;
   string            m_symbol;
   ulong             m_magic;

   // Lifecycle Parameters
   bool              m_enable_be;
   double            m_be_trigger_atr_mult;  // e.g. 1.0x ATR profit triggers BE
   double            m_be_lock_points;       // e.g. 10 points profit locked ($0.10)
   bool              m_enable_trailing;
   double            m_trail_dist_atr_mult;  // e.g. 1.2x ATR
   double            m_trail_step_atr_mult;  // e.g. 0.3x ATR
   bool              m_enable_partial;
   double            m_partial_trigger_atr_mult; // e.g. 1.5x ATR
   double            m_partial_close_pct;    // e.g. 50%

   // Tracking partial closes
   ulong             m_partially_closed[];

   bool IsPartiallyClosed(const ulong ticket)
   {
      for(int i = 0; i < ArraySize(m_partially_closed); i++)
      {
         if(m_partially_closed[i] == ticket)
            return true;
      }
      return false;
   }

   void MarkPartiallyClosed(const ulong ticket)
   {
      if(IsPartiallyClosed(ticket)) return;
      int sz = ArraySize(m_partially_closed);
      ArrayResize(m_partially_closed, sz + 1);
      m_partially_closed[sz] = ticket;
   }

   void CleanupClosedTickets()
   {
      for(int i = ArraySize(m_partially_closed) - 1; i >= 0; i--)
      {
         ulong ticket = m_partially_closed[i];
         if(!PositionSelectByTicket(ticket))
         {
            // Position no longer open, remove from tracking array
            for(int j = i; j < ArraySize(m_partially_closed) - 1; j++)
            {
               m_partially_closed[j] = m_partially_closed[j + 1];
            }
            ArrayResize(m_partially_closed, ArraySize(m_partially_closed) - 1);
         }
      }
   }

public:
   CPositionManager()
   {
      m_logger                   = NULL;
      m_execution                = NULL;
      m_analyzer                 = NULL;
      m_symbol                   = "";
      m_magic                    = 0;
      m_enable_be                = true;
      m_be_trigger_atr_mult      = 1.0;
      m_be_lock_points           = 10.0;
      m_enable_trailing          = true;
      m_trail_dist_atr_mult      = 1.3;
      m_trail_step_atr_mult      = 0.3;
      m_enable_partial           = true;
      m_partial_trigger_atr_mult = 1.5;
      m_partial_close_pct        = 50.0;
      ArrayResize(m_partially_closed, 0);
   }

   void Init(CTradeLogger* logger,
             CExecutionEngine* execution,
             CMarketAnalyzer* analyzer,
             const string symbol,
             const ulong magic,
             const bool enable_be,
             const double be_trigger_atr,
             const double be_lock_pts,
             const bool enable_trailing,
             const double trail_dist_atr,
             const double trail_step_atr,
             const bool enable_partial,
             const double partial_trigger_atr,
             const double partial_pct)
   {
      m_logger                   = logger;
      m_execution                = execution;
      m_analyzer                 = analyzer;
      m_symbol                   = symbol;
      m_magic                    = magic;
      m_enable_be                = enable_be;
      m_be_trigger_atr_mult      = be_trigger_atr;
      m_be_lock_points           = be_lock_pts;
      m_enable_trailing          = enable_trailing;
      m_trail_dist_atr_mult      = trail_dist_atr;
      m_trail_step_atr_mult      = trail_step_atr;
      m_enable_partial           = enable_partial;
      m_partial_trigger_atr_mult = partial_trigger_atr;
      m_partial_close_pct        = partial_pct;
   }

   //+------------------------------------------------------------------+
   //| Inspect and Manage All Open Positions                            |
   //+------------------------------------------------------------------+
   void ManagePositions(const MqlTick &tick, int &out_open_count, double &out_total_lots)
   {
      out_open_count = 0;
      out_total_lots = 0.0;

      CleanupClosedTickets();

      double point  = SymbolInfoDouble(m_symbol, SYMBOL_POINT);
      int digits    = (int)SymbolInfoInteger(m_symbol, SYMBOL_DIGITS);
      double atr_m1 = (m_analyzer != NULL) ? m_analyzer.GetATR_Micro(0) : 1.5;
      double atr_m5 = (m_analyzer != NULL) ? m_analyzer.GetATR_Macro(0) : 3.0;
      double ref_atr = (atr_m5 > 0.0) ? atr_m5 : atr_m1;

      for(int i = PositionsTotal() - 1; i >= 0; i--)
      {
         ulong ticket = PositionGetTicket(i);
         if(ticket == 0) continue;

         if(PositionGetString(POSITION_SYMBOL) != m_symbol || PositionGetInteger(POSITION_MAGIC) != (long)m_magic)
            continue;

         out_open_count++;
         double volume      = PositionGetDouble(POSITION_VOLUME);
         out_total_lots    += volume;

         ENUM_POSITION_TYPE type = (ENUM_POSITION_TYPE)PositionGetInteger(POSITION_TYPE);
         double open_price       = PositionGetDouble(POSITION_PRICE_OPEN);
         double curr_sl          = PositionGetDouble(POSITION_SL);
         double curr_tp          = PositionGetDouble(POSITION_TP);

         //------------------------------------------------------------------
         // 1. PARTIAL CLOSING (Scale Out)
         //------------------------------------------------------------------
         if(m_enable_partial && !IsPartiallyClosed(ticket) && m_execution != NULL)
         {
            double trigger_dist = m_partial_trigger_atr_mult * ref_atr;
            bool hit_partial = false;

            if(type == POSITION_TYPE_BUY && (tick.bid - open_price) >= trigger_dist)
               hit_partial = true;
            else if(type == POSITION_TYPE_SELL && (open_price - tick.ask) >= trigger_dist)
               hit_partial = true;

            if(hit_partial)
            {
               double lot_step = SymbolInfoDouble(m_symbol, SYMBOL_VOLUME_STEP);
               double close_vol = MathFloor((volume * (m_partial_close_pct / 100.0)) / lot_step) * lot_step;
               close_vol = NormalizeDouble(close_vol, 2);

               if(m_execution.ClosePartial(ticket, close_vol, "PROFIT_TARGET_1"))
               {
                  MarkPartiallyClosed(ticket);
                  // Immediately advance stop-loss to Break-Even upon partial close
                  double be_sl = (type == POSITION_TYPE_BUY) ? (open_price + (m_be_lock_points * point)) : (open_price - (m_be_lock_points * point));
                  m_execution.ModifyPositionStops(ticket, be_sl, curr_tp);
                  continue; // Continue to next position
               }
            }
         }

         //------------------------------------------------------------------
         // 2. BREAK-EVEN ENGINE
         //------------------------------------------------------------------
         if(m_enable_be && m_execution != NULL)
         {
            double be_trigger_dist = m_be_trigger_atr_mult * ref_atr;
            double lock_dist = m_be_lock_points * point;

            if(type == POSITION_TYPE_BUY)
            {
               if((tick.bid - open_price) >= be_trigger_dist)
               {
                  double desired_sl = NormalizeDouble(open_price + lock_dist, digits);
                  if(curr_sl < desired_sl)
                  {
                     m_execution.ModifyPositionStops(ticket, desired_sl, curr_tp);
                     curr_sl = desired_sl;
                  }
               }
            }
            else // POSITION_TYPE_SELL
            {
               if((open_price - tick.ask) >= be_trigger_dist)
               {
                  double desired_sl = NormalizeDouble(open_price - lock_dist, digits);
                  if(curr_sl == 0.0 || curr_sl > desired_sl)
                  {
                     m_execution.ModifyPositionStops(ticket, desired_sl, curr_tp);
                     curr_sl = desired_sl;
                  }
               }
            }
         }

         //------------------------------------------------------------------
         // 3. ADAPTIVE TRAILING STOP
         //------------------------------------------------------------------
         if(m_enable_trailing && m_execution != NULL)
         {
            double trail_dist = NormalizeDouble(m_trail_dist_atr_mult * ref_atr, digits);
            double trail_step = NormalizeDouble(m_trail_step_atr_mult * ref_atr, digits);

            if(type == POSITION_TYPE_BUY)
            {
               double candidate_sl = NormalizeDouble(tick.bid - trail_dist, digits);
               // Only trail once candidate SL is above open price (profit territory) and exceeds step
               if(candidate_sl > open_price && (candidate_sl - curr_sl) >= trail_step)
               {
                  m_execution.ModifyPositionStops(ticket, candidate_sl, curr_tp);
               }
            }
            else // POSITION_TYPE_SELL
            {
               double candidate_sl = NormalizeDouble(tick.ask + trail_dist, digits);
               // Only trail once candidate SL is below open price and below current SL by step
               if(candidate_sl < open_price && (curr_sl == 0.0 || (curr_sl - candidate_sl) >= trail_step))
               {
                  m_execution.ModifyPositionStops(ticket, candidate_sl, curr_tp);
               }
            }
         }
      }
   }
};
