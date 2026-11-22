//+------------------------------------------------------------------+
//|                                              ExecutionEngine.mqh |
//|                                  Copyright 2026, Institutional Algo Team |
//|                             Low-Latency Institutional Order Router |
//+------------------------------------------------------------------+
#property copyright "Copyright 2026, Institutional Algo Team"
#property link      "https://www.mql5.com"
#property strict

#include "TradeLogger.mqh"

class CExecutionEngine
{
private:
   CTradeLogger*     m_logger;
   string            m_symbol;
   ulong             m_magic;
   int               m_max_slippage_pts;
   double            m_max_spread_pts;
   int               m_max_retries;
   ENUM_ORDER_TYPE_FILLING m_filling_mode;

   //+------------------------------------------------------------------+
   //| Auto-detect broker compatible filling mode                       |
   //+------------------------------------------------------------------+
   ENUM_ORDER_TYPE_FILLING DetectFillingMode()
   {
      uint filling_flags = (uint)SymbolInfoInteger(m_symbol, SYMBOL_FILLING_MODE);

      // On Exness / ECN: IOC is usually supported, followed by FOK
      if((filling_flags & SYMBOL_FILLING_IOC) != 0)
         return ORDER_FILLING_IOC;
      if((filling_flags & SYMBOL_FILLING_FOK) != 0)
         return ORDER_FILLING_FOK;

      return ORDER_FILLING_RETURN;
   }

public:
   CExecutionEngine()
   {
      m_logger           = NULL;
      m_symbol           = "";
      m_magic            = 0;
      m_max_slippage_pts = 30; // 30 points (3 pips / $0.30 on Gold)
      m_max_spread_pts   = 40.0;
      m_max_retries      = 3;
      m_filling_mode     = ORDER_FILLING_IOC;
   }

   void Init(CTradeLogger* logger, const string symbol, const ulong magic, const int max_slippage, const double max_spread, const int retries = 3)
   {
      m_logger           = logger;
      m_symbol           = symbol;
      m_magic            = magic;
      m_max_slippage_pts = max_slippage;
      m_max_spread_pts   = max_spread;
      m_max_retries      = retries;
      m_filling_mode     = DetectFillingMode();

      if(m_logger != NULL)
      {
         string filling_str = (m_filling_mode == ORDER_FILLING_IOC) ? "IOC" : (m_filling_mode == ORDER_FILLING_FOK ? "FOK" : "RETURN");
         m_logger.Info(StringFormat("ExecutionEngine initialized on %s | Filling Mode: %s | Max Slippage: %d pts | Max Spread: %.1f pts",
                                    m_symbol, filling_str, m_max_slippage_pts, m_max_spread_pts));
      }
   }

   //+------------------------------------------------------------------+
   //| Pre-Trade Validation Checks                                      |
   //+------------------------------------------------------------------+
   bool ValidateEnvironment(string &err_msg)
   {
      if(!TerminalInfoInteger(TERMINAL_TRADE_ALLOWED))
      {
         err_msg = "Automated trading is disabled in Terminal Settings!";
         return false;
      }
      if(!MQLInfoInteger(MQL_TRADE_ALLOWED))
      {
         err_msg = "Algo trading is disabled for this Expert Advisor!";
         return false;
      }
      if(!AccountInfoInteger(ACCOUNT_TRADE_EXPERT))
      {
         err_msg = "Account does not allow Expert Advisor trading!";
         return false;
      }
      return true;
   }

   //+------------------------------------------------------------------+
   //| Execute Market Order (BUY or SELL)                               |
   //+------------------------------------------------------------------+
   bool SendMarketOrder(const ENUM_ORDER_TYPE order_type,
                        const double volume,
                        const double sl,
                        const double tp,
                        const string comment,
                        ulong &out_deal_ticket)
   {
      out_deal_ticket = 0;
      string env_err = "";
      if(!ValidateEnvironment(env_err))
      {
         if(m_logger != NULL) m_logger.Error("Order Rejected: " + env_err);
         return false;
      }

      int digits = (int)SymbolInfoInteger(m_symbol, SYMBOL_DIGITS);
      double point = SymbolInfoDouble(m_symbol, SYMBOL_POINT);
      int stops_level = (int)SymbolInfoInteger(m_symbol, SYMBOL_TRADE_STOPS_LEVEL);

      for(int attempt = 1; attempt <= m_max_retries; attempt++)
      {
         MqlTick tick;
         if(!SymbolInfoTick(m_symbol, tick))
         {
            if(attempt == m_max_retries && m_logger != NULL)
               m_logger.Error(StringFormat("SymbolInfoTick failed on %s (Attempt %d)", m_symbol, attempt));
            continue;
         }

         // Current Spread Check
         double spread_pts = (tick.ask - tick.bid) / point;
         if(spread_pts > m_max_spread_pts)
         {
            if(m_logger != NULL)
               m_logger.Warn(StringFormat("Order aborted: Current spread (%.1f pts) exceeds max allowed (%.1f pts)", spread_pts, m_max_spread_pts));
            return false;
         }

         double price = (order_type == ORDER_TYPE_BUY) ? tick.ask : tick.bid;

         // Normalize Stops & Check Broker Minimum Stop Level
         double norm_sl = (sl > 0.0) ? NormalizeDouble(sl, digits) : 0.0;
         double norm_tp = (tp > 0.0) ? NormalizeDouble(tp, digits) : 0.0;

         if(stops_level > 0)
         {
            double min_stop_dist = stops_level * point;
            if(order_type == ORDER_TYPE_BUY)
            {
               if(norm_sl > 0.0 && (price - norm_sl) < min_stop_dist)
                  norm_sl = NormalizeDouble(price - min_stop_dist, digits);
               if(norm_tp > 0.0 && (norm_tp - price) < min_stop_dist)
                  norm_tp = NormalizeDouble(price + min_stop_dist, digits);
            }
            else
            {
               if(norm_sl > 0.0 && (norm_sl - price) < min_stop_dist)
                  norm_sl = NormalizeDouble(price + min_stop_dist, digits);
               if(norm_tp > 0.0 && (price - norm_tp) < min_stop_dist)
                  norm_tp = NormalizeDouble(price - min_stop_dist, digits);
            }
         }

         MqlTradeRequest request;
         MqlTradeResult  result;
         ZeroMemory(request);
         ZeroMemory(result);

         request.action       = TRADE_ACTION_DEAL;
         request.symbol       = m_symbol;
         request.volume       = volume;
         request.type         = order_type;
         request.price        = price;
         request.sl           = norm_sl;
         request.tp           = norm_tp;
         request.deviation    = m_max_slippage_pts;
         request.type_filling = m_filling_mode;
         request.type_time    = ORDER_TIME_GTC;
         request.magic        = m_magic;
         request.comment      = comment;

         ulong start_micros = GetMicrosecondCount();
         bool success = OrderSend(request, result);
         ulong latency_ms = (GetMicrosecondCount() - start_micros) / 1000;

         if(success && (result.retcode == TRADE_RETCODE_DONE || result.retcode == TRADE_RETCODE_PLACED))
         {
            out_deal_ticket = result.deal;
            if(m_logger != NULL)
            {
               m_logger.Trade(StringFormat("FILL CONFIRMED #%d | %s %.2f lots @ %.2f | SL: %.2f | TP: %.2f | Latency: %d ms | Retcode: %d (%s)",
                                           result.deal, (order_type == ORDER_TYPE_BUY ? "BUY" : "SELL"),
                                           volume, result.price, norm_sl, norm_tp, latency_ms, result.retcode, result.comment));
            }
            return true;
         }
         else
         {
            // Requote or Price Changed: Retry with updated quote
            if(result.retcode == TRADE_RETCODE_REQUOTE || result.retcode == TRADE_RETCODE_PRICE_CHANGED || result.retcode == TRADE_RETCODE_PRICE_OFF)
            {
               if(m_logger != NULL)
                  m_logger.Warn(StringFormat("Requote/Price shift on attempt %d/%d (Retcode: %d). Refreshing prices...", attempt, m_max_retries, result.retcode));
               continue;
            }
            
            // Filling mode fallback retry
            if(result.retcode == TRADE_RETCODE_INVALID_FILL)
            {
               m_filling_mode = (m_filling_mode == ORDER_FILLING_IOC) ? ORDER_FILLING_FOK : ORDER_FILLING_IOC;
               if(m_logger != NULL)
                  m_logger.Warn(StringFormat("Unsupported filling mode! Switched to fallback filling mode, retrying attempt %d...", attempt));
               continue;
            }

            // Fatal error
            if(m_logger != NULL)
            {
               m_logger.Error(StringFormat("OrderSend failed! Retcode: %d (%s) | Attempt: %d | Latency: %d ms",
                                           result.retcode, result.comment, attempt, latency_ms));
            }
            break;
         }
      }

      return false;
   }

   //+------------------------------------------------------------------+
   //| Modify Position SL / TP                                          |
   //+------------------------------------------------------------------+
   bool ModifyPositionStops(const ulong ticket, const double new_sl, const double new_tp)
   {
      if(!PositionSelectByTicket(ticket))
         return false;

      int digits = (int)SymbolInfoInteger(m_symbol, SYMBOL_DIGITS);
      double norm_sl = (new_sl > 0.0) ? NormalizeDouble(new_sl, digits) : 0.0;
      double norm_tp = (new_tp > 0.0) ? NormalizeDouble(new_tp, digits) : 0.0;

      double curr_sl = PositionGetDouble(POSITION_SL);
      double curr_tp = PositionGetDouble(POSITION_TP);

      // Skip redundant calls if difference is negligible
      if(MathAbs(norm_sl - curr_sl) < Point() && MathAbs(norm_tp - curr_tp) < Point())
         return true;

      MqlTradeRequest request;
      MqlTradeResult  result;
      ZeroMemory(request);
      ZeroMemory(result);

      request.action   = TRADE_ACTION_SLTP;
      request.position = ticket;
      request.symbol   = m_symbol;
      request.sl       = norm_sl;
      request.tp       = norm_tp;
      request.magic    = m_magic;

      bool success = OrderSend(request, result);
      if(success && (result.retcode == TRADE_RETCODE_DONE || result.retcode == TRADE_RETCODE_PLACED))
      {
         if(m_logger != NULL)
            m_logger.Info(StringFormat("Stops modified for #%d | New SL: %.2f | New TP: %.2f", ticket, norm_sl, norm_tp));
         return true;
      }
      else
      {
         if(m_logger != NULL)
            m_logger.Warn(StringFormat("Failed to modify stops for #%d! Retcode: %d (%s)", ticket, result.retcode, result.comment));
         return false;
      }
   }

   //+------------------------------------------------------------------+
   //| Close Entire Position by Ticket                                  |
   //+------------------------------------------------------------------+
   bool ClosePosition(const ulong ticket, const string reason)
   {
      if(!PositionSelectByTicket(ticket))
         return false;

      ENUM_POSITION_TYPE pos_type = (ENUM_POSITION_TYPE)PositionGetInteger(POSITION_TYPE);
      double volume = PositionGetDouble(POSITION_VOLUME);
      ENUM_ORDER_TYPE close_type = (pos_type == POSITION_TYPE_BUY) ? ORDER_TYPE_SELL : ORDER_TYPE_BUY;

      MqlTick tick;
      if(!SymbolInfoTick(m_symbol, tick)) return false;
      double close_price = (close_type == ORDER_TYPE_BUY) ? tick.ask : tick.bid;

      MqlTradeRequest request;
      MqlTradeResult  result;
      ZeroMemory(request);
      ZeroMemory(result);

      request.action       = TRADE_ACTION_DEAL;
      request.position     = ticket;
      request.symbol       = m_symbol;
      request.volume       = volume;
      request.type         = close_type;
      request.price        = close_price;
      request.deviation    = m_max_slippage_pts;
      request.type_filling = m_filling_mode;
      request.magic        = m_magic;
      request.comment      = "CLOSE: " + reason;

      bool success = OrderSend(request, result);
      if(success && (result.retcode == TRADE_RETCODE_DONE || result.retcode == TRADE_RETCODE_PLACED))
      {
         if(m_logger != NULL)
            m_logger.Trade(StringFormat("POSITION CLOSED #%d (%.2f lots @ %.2f) | Reason: %s", ticket, volume, result.price, reason));
         return true;
      }
      else
      {
         if(m_logger != NULL)
            m_logger.Error(StringFormat("Failed to close position #%d! Retcode: %d (%s)", ticket, result.retcode, result.comment));
         return false;
      }
   }

   //+------------------------------------------------------------------+
   //| Partial Close Position                                           |
   //+------------------------------------------------------------------+
   bool ClosePartial(const ulong ticket, const double volume_to_close, const string reason)
   {
      if(!PositionSelectByTicket(ticket))
         return false;

      double current_vol = PositionGetDouble(POSITION_VOLUME);
      double lot_step    = SymbolInfoDouble(m_symbol, SYMBOL_VOLUME_STEP);
      double lot_min     = SymbolInfoDouble(m_symbol, SYMBOL_VOLUME_MIN);

      // Verify that partial close volume and remaining volume are valid
      double remainder = current_vol - volume_to_close;
      if(volume_to_close < lot_min || remainder < lot_min)
      {
         if(m_logger != NULL)
            m_logger.Warn(StringFormat("Partial close skipped for #%d: Volume %.2f or Remainder %.2f below MinLot %.2f", 
                                       ticket, volume_to_close, remainder, lot_min));
         return false;
      }

      ENUM_POSITION_TYPE pos_type = (ENUM_POSITION_TYPE)PositionGetInteger(POSITION_TYPE);
      ENUM_ORDER_TYPE close_type = (pos_type == POSITION_TYPE_BUY) ? ORDER_TYPE_SELL : ORDER_TYPE_BUY;

      MqlTick tick;
      if(!SymbolInfoTick(m_symbol, tick)) return false;
      double close_price = (close_type == ORDER_TYPE_BUY) ? tick.ask : tick.bid;

      MqlTradeRequest request;
      MqlTradeResult  result;
      ZeroMemory(request);
      ZeroMemory(result);

      request.action       = TRADE_ACTION_DEAL;
      request.position     = ticket;
      request.symbol       = m_symbol;
      request.volume       = volume_to_close;
      request.type         = close_type;
      request.price        = close_price;
      request.deviation    = m_max_slippage_pts;
      request.type_filling = m_filling_mode;
      request.magic        = m_magic;
      request.comment      = "PARTIAL: " + reason;

      bool success = OrderSend(request, result);
      if(success && (result.retcode == TRADE_RETCODE_DONE || result.retcode == TRADE_RETCODE_PLACED))
      {
         if(m_logger != NULL)
            m_logger.Trade(StringFormat("PARTIAL CLOSE #%d (Closed %.2f of %.2f lots @ %.2f) | Reason: %s", 
                                        ticket, volume_to_close, current_vol, result.price, reason));
         return true;
      }
      else
      {
         if(m_logger != NULL)
            m_logger.Error(StringFormat("Partial close failed for #%d! Retcode: %d (%s)", ticket, result.retcode, result.comment));
         return false;
      }
   }

   //+------------------------------------------------------------------+
   //| Emergency Close All Positions For This EA                        |
   //+------------------------------------------------------------------+
   int CloseAllPositions(const string reason)
   {
      int closed_count = 0;
      for(int i = PositionsTotal() - 1; i >= 0; i--)
      {
         ulong ticket = PositionGetTicket(i);
         if(ticket == 0) continue;

         if(PositionGetString(POSITION_SYMBOL) == m_symbol && PositionGetInteger(POSITION_MAGIC) == (long)m_magic)
         {
            if(ClosePosition(ticket, reason))
               closed_count++;
         }
      }
      return closed_count;
   }
};
