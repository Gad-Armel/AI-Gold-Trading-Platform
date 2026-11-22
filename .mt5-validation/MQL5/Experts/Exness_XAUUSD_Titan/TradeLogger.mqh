//+------------------------------------------------------------------+
//|                                                  TradeLogger.mqh |
//|                                  Copyright 2026, Institutional Algo Team |
//|                                      High-Performance MT5 Logging Engine |
//+------------------------------------------------------------------+
#property copyright "Copyright 2026, Institutional Algo Team"
#property link      "https://www.mql5.com"
#property strict

enum ENUM_LOG_LEVEL
{
   LOG_LEVEL_DEBUG   = 0,
   LOG_LEVEL_INFO    = 1,
   LOG_LEVEL_TRADE   = 2,
   LOG_LEVEL_WARN    = 3,
   LOG_LEVEL_ERROR   = 4,
   LOG_LEVEL_NONE    = 5
};

class CTradeLogger
{
private:
   string            m_prefix;
   ENUM_LOG_LEVEL    m_min_level;
   bool              m_file_logging;
   int               m_file_handle;
   string            m_symbol;
   ulong             m_magic;

   string LevelToString(const ENUM_LOG_LEVEL level)
   {
      switch(level)
      {
         case LOG_LEVEL_DEBUG: return "DEBUG";
         case LOG_LEVEL_INFO:  return "INFO";
         case LOG_LEVEL_TRADE: return "TRADE";
         case LOG_LEVEL_WARN:  return "WARN";
         case LOG_LEVEL_ERROR: return "ERROR";
         default:              return "LOG";
      }
   }

public:
   CTradeLogger()
   {
      m_prefix       = "[TITAN-XAUUSD]";
      m_min_level    = LOG_LEVEL_INFO;
      m_file_logging = false;
      m_file_handle  = INVALID_HANDLE;
      m_symbol       = "";
      m_magic        = 0;
   }

   ~CTradeLogger()
   {
      CloseLogFile();
   }

   void Init(const string prefix, const string symbol, const ulong magic, const ENUM_LOG_LEVEL min_level, const bool file_log = false)
   {
      m_prefix       = prefix;
      m_symbol       = symbol;
      m_magic        = magic;
      m_min_level    = min_level;
      m_file_logging = file_log;

      if(m_file_logging)
      {
         string filename = StringFormat("Titan_Logs\\%s_%d_%s.log", 
                                        m_symbol, 
                                        m_magic, 
                                        TimeToString(TimeCurrent(), TIME_DATE));
         m_file_handle = FileOpen(filename, FILE_WRITE|FILE_READ|FILE_TXT|FILE_ANSI);
         if(m_file_handle != INVALID_HANDLE)
         {
            FileSeek(m_file_handle, 0, SEEK_END);
            FileWriteString(m_file_handle, StringFormat("=== SESSION START %s ===\r\n", TimeToString(TimeCurrent(), TIME_DATE|TIME_SECONDS)));
         }
      }
   }

   void CloseLogFile()
   {
      if(m_file_handle != INVALID_HANDLE)
      {
         FileWriteString(m_file_handle, StringFormat("=== SESSION END %s ===\r\n", TimeToString(TimeCurrent(), TIME_DATE|TIME_SECONDS)));
         FileClose(m_file_handle);
         m_file_handle = INVALID_HANDLE;
      }
   }

   void Log(const ENUM_LOG_LEVEL level, const string message)
   {
      if(level < m_min_level)
         return;

      string formatted = StringFormat("%s [%s] [%s] %s", 
                                      m_prefix, 
                                      LevelToString(level), 
                                      TimeToString(TimeCurrent(), TIME_MINUTES|TIME_SECONDS), 
                                      message);

      Print(formatted);

      if(m_file_logging && m_file_handle != INVALID_HANDLE)
      {
         FileWriteString(m_file_handle, formatted + "\r\n");
         FileFlush(m_file_handle);
      }
   }

   void Info(const string msg)  { Log(LOG_LEVEL_INFO, msg); }
   void Debug(const string msg) { Log(LOG_LEVEL_DEBUG, msg); }
   void Trade(const string msg) { Log(LOG_LEVEL_TRADE, msg); }
   void Warn(const string msg)  { Log(LOG_LEVEL_WARN, msg); }
   void Error(const string msg) { Log(LOG_LEVEL_ERROR, msg); }

   void UpdateDashboard(const string mode_name,
                        const string resolved_symbol,
                        const string regime_name,
                        const double current_spread_pts,
                        const double max_spread_pts,
                        const double atr_m1,
                        const double atr_m5,
                        const double daily_pnl,
                        const double daily_drawdown_pct,
                        const double max_dd_pct,
                        const int consecutive_losses,
                        const int max_consecutive_losses,
                        const int open_positions_count,
                        const int max_positions,
                        const double total_exposure_lots,
                        const string engine_status,
                        const bool is_cooldown,
                        const datetime cooldown_until)
   {
      string spread_status = (current_spread_pts <= max_spread_pts) ? "NORMAL [OK]" : "ELEVATED [BLOCKED]";
      string streak_status = StringFormat("%d / %d", consecutive_losses, max_consecutive_losses);
      
      string cooldown_text = "NONE";
      if(is_cooldown)
      {
         int remaining_sec = (int)MathMax(0, (long)(cooldown_until - TimeCurrent()));
         cooldown_text = StringFormat("ACTIVE (%d sec remaining)", remaining_sec);
      }

      string hud = "";
      hud += "========================================================\n";
      hud += "           EXNESS XAUUSD TITAN QUANT EA                \n";
      hud += "========================================================\n";
      hud += StringFormat(" Engine Mode       : %s\n", mode_name);
      hud += StringFormat(" Target Symbol     : %s (Broker Suffix Resolved)\n", resolved_symbol);
      hud += StringFormat(" Market Regime     : %s\n", regime_name);
      hud += StringFormat(" Engine Status     : %s\n", engine_status);
      hud += "--------------------------------------------------------\n";
      hud += StringFormat(" Spread            : %.1f pts (Max: %.1f) - %s\n", current_spread_pts, max_spread_pts, spread_status);
      hud += StringFormat(" ATR (M1 / M5)     : %.2f / %.2f\n", atr_m1, atr_m5);
      hud += "--------------------------------------------------------\n";
      hud += StringFormat(" Daily Net P&L     : $%.2f\n", daily_pnl);
      hud += StringFormat(" Daily Drawdown    : %.2f%% (Max: %.2f%%)\n", daily_drawdown_pct, max_dd_pct);
      hud += StringFormat(" Consecutive Losses: %s\n", streak_status);
      hud += StringFormat(" Cooldown Status   : %s\n", cooldown_text);
      hud += "--------------------------------------------------------\n";
      hud += StringFormat(" Active Positions  : %d / %d\n", open_positions_count, max_positions);
      hud += StringFormat(" Total Net Exposure: %.2f Lots\n", total_exposure_lots);
      hud += "========================================================\n";
      hud += StringFormat(" Server Time       : %s\n", TimeToString(TimeCurrent(), TIME_DATE|TIME_SECONDS));
      hud += "========================================================";

      Comment(hud);
   }

   void ClearDashboard()
   {
      Comment("");
   }
};
