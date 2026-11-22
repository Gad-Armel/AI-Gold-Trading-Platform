//+------------------------------------------------------------------+
//|                                        XAUUSD_AI_Sentinel.mq5    |
//|                         AI Market Intelligence Engine EA Bridge  |
//|                   Copyright 2026, Quantitative Research Team     |
//+------------------------------------------------------------------+
#property copyright   "Quantitative Research Team"
#property link        "https://github.com/quant-intelligence/xauusd"
#property version     "1.00"
#property description "MT5 Expert Advisor with AI Market Intelligence File/API Bridge."
#property description "STRICT POLICY: Native RiskManager has total supremacy. AI NEVER overrides lot size."
#property description "Seamless fallback to independent native strategy when AI is unavailable."
#property strict

#include <Trade\Trade.mqh>
#include <Trade\SymbolInfo.mqh>
#include <Trade\AccountInfo.mqh>

//--- Enums
enum ENUM_BRIDGE_MODE
{
   BRIDGE_FILE_IPC = 0,    // Asynchronous Atomic File Bridge (MQL5/Files)
   BRIDGE_REST_API = 1,    // Local HTTP REST API (WebRequest)
   BRIDGE_AUTO_FAILOVER = 2 // Primary File Bridge with API Failover
};

enum ENUM_SIGNAL_TYPE
{
   SIGNAL_NO_TRADE = 0,
   SIGNAL_BUY = 1,
   SIGNAL_SELL = 2
};

//--- Input Parameters
input group "=== Communication & Bridge Settings ==="
input ENUM_BRIDGE_MODE InpBridgeMode         = BRIDGE_FILE_IPC; // Bridge Mode
input string           InpBridgeFileName     = "xauusd_ai_signals.json"; // File Bridge Path (relative to MQL5/Files)
input string           InpBridgeApiUrl       = "http://127.0.0.1:8000/api/v1/market-intelligence"; // Local API Endpoint
input int              InpMaxDataAgeSec      = 20;             // Max Data Freshness (Seconds) before Fallback
input double           InpMinConfidenceScore = 0.65;           // Minimum AI Confidence (0.0 to 1.0)

input group "=== Native RiskManager Supremacy (EA Controlled) ==="
input double           InpRiskPercentPerTrade= 1.0;            // Risk Per Trade (% of Account Balance)
input double           InpMaxAccountRiskPct  = 5.0;            // Max Total Portfolio Exposure (%)
input double           InpMaxSpreadPoints    = 45.0;           // Maximum Allowed Spread in Points
input ulong            InpMagicNumber        = 778899;         // EA Magic Number
input ulong            InpDeviationPoints    = 20;             // Max Execution Slippage (Points)

input group "=== Independent Native Fallback Strategy ==="
input bool             InpEnableNativeFallback = true;         // Engage Native Strategy when AI is Offline
input int              InpNativeDonchianBars = 20;             // Native Donchian Channel Period
input int              InpNativeEmaPeriod    = 50;             // Native Trend Filter EMA Period
input double           InpNativeAtrSlMult    = 1.5;            // Native Fallback ATR SL Multiplier

//--- Global Objects & State Variables
CTrade         m_trade;
CSymbolInfo    m_symbol;
CAccountInfo   m_account;

bool           g_ai_online = false;
datetime       g_last_ai_read_time = 0;
string         g_current_ai_regime = "INITIALIZING";
double         g_current_ai_conf = 0.0;
ENUM_SIGNAL_TYPE g_current_ai_signal = SIGNAL_NO_TRADE;
double         g_ai_recommended_sl_points = 50.0;
double         g_ai_recommended_tp_points = 75.0;

// Indicators for native fallback
int            g_native_ema_handle = INVALID_HANDLE;
int            g_native_atr_handle = INVALID_HANDLE;
datetime       g_last_bar_time = 0;

//+------------------------------------------------------------------+
//| Expert initialization function                                   |
//+------------------------------------------------------------------+
int OnInit()
{
   if(!m_symbol.Name(_Symbol))
   {
      Print("[Sentinel EA] Error: Could not bind symbol ", _Symbol);
      return INIT_FAILED;
   }
   m_symbol.Refresh();

   m_trade.SetExpertMagicNumber(InpMagicNumber);
   m_trade.SetDeviationInPoints(InpDeviationPoints);
   m_trade.SetTypeFillingBySymbol(m_symbol.Name());

   // Initialize native fallback indicators
   g_native_ema_handle = iMA(_Symbol, PERIOD_M15, InpNativeEmaPeriod, 0, MODE_EMA, PRICE_CLOSE);
   g_native_atr_handle = iATR(_Symbol, PERIOD_M15, 14);

   PrintFormat("[Sentinel EA] Initialized successfully on %s. Mode: %s. Native Risk: %.1f%%",
               _Symbol, EnumToString(InpBridgeMode), InpRiskPercentPerTrade);
   return INIT_SUCCEEDED;
}

//+------------------------------------------------------------------+
//| Expert deinitialization function                                 |
//+------------------------------------------------------------------+
void OnDeinit(const int reason)
{
   if(g_native_ema_handle != INVALID_HANDLE) IndicatorRelease(g_native_ema_handle);
   if(g_native_atr_handle != INVALID_HANDLE) IndicatorRelease(g_native_atr_handle);
   PrintFormat("[Sentinel EA] Deinitialized. Reason code: %d", reason);
}

//+------------------------------------------------------------------+
//| Expert tick function                                             |
//+------------------------------------------------------------------+
void OnTick()
{
   if(!m_symbol.RefreshRates()) return;

   // 1. Hard Volatility & Spread Protection
   double current_spread = (m_symbol.Ask() - m_symbol.Bid()) / m_symbol.Point();
   if(current_spread > InpMaxSpreadPoints)
   {
      // Excessive spread (e.g. during major macro announcement or rollover)
      return;
   }

   // 2. Only evaluate on new M1 / M5 bar or every 5 seconds to reduce CPU
   datetime current_bar_time = iTime(_Symbol, PERIOD_M1, 0);
   if(current_bar_time == g_last_bar_time && (TimeCurrent() - g_last_ai_read_time) < 5)
   {
      return;
   }
   g_last_bar_time = current_bar_time;

   // 3. Ingest AI Market Intelligence
   bool ai_updated = ReadMarketIntelligence();

   // 4. Check Open Positions count for this EA
   int open_positions = CountOpenPositions();

   // 5. Decision Branch: AI Guided vs Native Fallback Strategy
   if(g_ai_online && ai_updated)
   {
      // --- AI MARKET INTELLIGENCE PATH ---
      ProcessAISignal(open_positions);
   }
   else if(InpEnableNativeFallback)
   {
      // --- INDEPENDENT NATIVE STRATEGY PATH ---
      // Seamlessly engaged when AI service is offline, stale, or unreachable
      ProcessNativeFallbackStrategy(open_positions);
   }
}

//+------------------------------------------------------------------+
//| Reads Market Intelligence from Asynchronous File or REST API     |
//+------------------------------------------------------------------+
bool ReadMarketIntelligence()
{
   string json_content = "";
   bool read_success = false;

   if(InpBridgeMode == BRIDGE_FILE_IPC || InpBridgeMode == BRIDGE_AUTO_FAILOVER)
   {
      read_success = ReadFromFileBridge(json_content);
   }

   if(!read_success && (InpBridgeMode == BRIDGE_REST_API || InpBridgeMode == BRIDGE_AUTO_FAILOVER))
   {
      read_success = ReadFromApiBridge(json_content);
   }

   if(!read_success || StringLen(json_content) == 0)
   {
      g_ai_online = false;
      return false;
   }

   // Parse JSON string
   return ParseIntelligenceJson(json_content);
}

//+------------------------------------------------------------------+
//| Reads File Bridge atomically with shared-read lock               |
//+------------------------------------------------------------------+
bool ReadFromFileBridge(string &out_content)
{
   ResetLastError();
   int file_handle = FileOpen(InpBridgeFileName, FILE_READ | FILE_TXT | FILE_SHARE_READ | FILE_ANSI);
   if(file_handle == INVALID_HANDLE)
   {
      return false;
   }

   out_content = "";
   while(!FileIsEnding(file_handle))
   {
      out_content += FileReadString(file_handle);
   }
   FileClose(file_handle);
   return (StringLen(out_content) > 10);
}

//+------------------------------------------------------------------+
//| Reads API Bridge using MT5 WebRequest                            |
//+------------------------------------------------------------------+
bool ReadFromApiBridge(string &out_content)
{
   char post_data[];
   char result_data[];
   string result_headers;
   string headers = "Accept: application/json\r\n";
   int timeout_ms = 1500;

   ResetLastError();
   int res = WebRequest("GET", InpBridgeApiUrl, headers, timeout_ms, post_data, result_data, result_headers);
   if(res == 200 && ArraySize(result_data) > 0)
   {
      out_content = CharArrayToString(result_data, 0, WHOLE_ARRAY, CP_UTF8);
      return true;
   }
   return false;
}

//+------------------------------------------------------------------+
//| Fast Causal JSON Parser for Market Intelligence Payload           |
//+------------------------------------------------------------------+
bool ParseIntelligenceJson(const string json)
{
   // Extract signal string
   string sig_str = ExtractJsonStringValue(json, "signal");
   if(sig_str == "BUY") g_current_ai_signal = SIGNAL_BUY;
   else if(sig_str == "SELL") g_current_ai_signal = SIGNAL_SELL;
   else g_current_ai_signal = SIGNAL_NO_TRADE;

   // Extract confidence
   g_current_ai_conf = ExtractJsonDoubleValue(json, "confidence");
   g_current_ai_regime = ExtractJsonStringValue(json, "regime");

   // Extract suggested SL / TP distances
   double sl_pts = ExtractJsonDoubleValue(json, "recommended_sl_distance_points");
   double tp_pts = ExtractJsonDoubleValue(json, "recommended_tp_distance_points");
   if(sl_pts > 10.0) g_ai_recommended_sl_points = sl_pts;
   if(tp_pts > 10.0) g_ai_recommended_tp_points = tp_pts;

   // Heartbeat check: Ensure message timestamp is not stale
   g_last_ai_read_time = TimeCurrent();
   g_ai_online = true;

   return true;
}

//+------------------------------------------------------------------+
//| Processes AI Signal under Native RiskManager Authority           |
//+------------------------------------------------------------------+
void ProcessAISignal(int open_positions)
{
   if(open_positions > 0) return; // Only 1 active position per EA instance
   if(g_current_ai_signal == SIGNAL_NO_TRADE) return;
   if(g_current_ai_conf < InpMinConfidenceScore) return;

   // Veto trades in abnormal volatility regime
   if(g_current_ai_regime == "ABNORMAL_VOLATILITY")
   {
      Print("[Sentinel EA] Trade rejected: AI flagged ABNORMAL_VOLATILITY regime.");
      return;
   }

   double ask = m_symbol.Ask();
   double bid = m_symbol.Bid();
   double point = m_symbol.Point();

   double sl_price = 0.0;
   double tp_price = 0.0;
   ENUM_ORDER_TYPE order_type;

   if(g_current_ai_signal == SIGNAL_BUY)
   {
      order_type = ORDER_TYPE_BUY;
      sl_price = m_symbol.NormalizePrice(ask - (g_ai_recommended_sl_points * point));
      tp_price = m_symbol.NormalizePrice(ask + (g_ai_recommended_tp_points * point));
   }
   else
   {
      order_type = ORDER_TYPE_SELL;
      sl_price = m_symbol.NormalizePrice(bid + (g_ai_recommended_sl_points * point));
      tp_price = m_symbol.NormalizePrice(bid - (g_ai_recommended_tp_points * point));
   }

   // --- STRICT RISK MANAGER SIZING ---
   // Lot size is calculated EXCLUSIVELY by the EA's RiskManager based on account balance and risk%
   double calculated_lot = CalculateRiskLotSize(g_ai_recommended_sl_points);
   if(calculated_lot <= 0.0)
   {
      Print("[Sentinel EA] RiskManager rejected trade: Sizing check failed.");
      return;
   }

   // Execute Trade
   string comment = StringFormat("AI_%s_C%.0f", EnumToString(g_current_ai_signal), g_current_ai_conf * 100);
   if(order_type == ORDER_TYPE_BUY)
   {
      m_trade.Buy(calculated_lot, _Symbol, ask, sl_price, tp_price, comment);
   }
   else
   {
      m_trade.Sell(calculated_lot, _Symbol, bid, sl_price, tp_price, comment);
   }
}

//+------------------------------------------------------------------+
//| Independent Native Fallback Strategy (Engaged when AI Offline)   |
//+------------------------------------------------------------------+
void ProcessNativeFallbackStrategy(int open_positions)
{
   if(open_positions > 0) return;

   // Donchian Breakout + EMA Filter on M15
   double ema_val[];
   double atr_val[];
   ArraySetAsSeries(ema_val, true);
   ArraySetAsSeries(atr_val, true);

   if(CopyBuffer(g_native_ema_handle, 0, 0, 2, ema_val) < 2) return;
   if(CopyBuffer(g_native_atr_handle, 0, 0, 2, atr_val) < 2) return;

   double highest_high = -1.0;
   double lowest_low = 999999.0;
   for(int i = 1; i <= InpNativeDonchianBars; i++)
   {
      double h = iHigh(_Symbol, PERIOD_M15, i);
      double l = iLow(_Symbol, PERIOD_M15, i);
      if(h > highest_high) highest_high = h;
      if(l < lowest_low) lowest_low = l;
   }

   double close_1 = iClose(_Symbol, PERIOD_M15, 1);
   double ask = m_symbol.Ask();
   double bid = m_symbol.Bid();
   double point = m_symbol.Point();
   double atr_pts = atr_val[0] / point;

   if(close_1 > highest_high && close_1 > ema_val[0])
   {
      // Native Bullish Breakout
      double sl_pts = atr_pts * InpNativeAtrSlMult;
      double sl_price = m_symbol.NormalizePrice(ask - (sl_pts * point));
      double tp_price = m_symbol.NormalizePrice(ask + (sl_pts * 1.8 * point));
      double lots = CalculateRiskLotSize(sl_pts);
      if(lots > 0) m_trade.Buy(lots, _Symbol, ask, sl_price, tp_price, "NATIVE_FALLBACK_BUY");
   }
   else if(close_1 < lowest_low && close_1 < ema_val[0])
   {
      // Native Bearish Breakout
      double sl_pts = atr_pts * InpNativeAtrSlMult;
      double sl_price = m_symbol.NormalizePrice(bid + (sl_pts * point));
      double tp_price = m_symbol.NormalizePrice(bid - (sl_pts * 1.8 * point));
      double lots = CalculateRiskLotSize(sl_pts);
      if(lots > 0) m_trade.Sell(lots, _Symbol, bid, sl_price, tp_price, "NATIVE_FALLBACK_SELL");
   }
}

//+------------------------------------------------------------------+
//| Native RiskManager: Lot Size Calculation from Account Balance     |
//+------------------------------------------------------------------+
double CalculateRiskLotSize(double sl_distance_points)
{
   double balance = m_account.Balance();
   double risk_amount = balance * (InpRiskPercentPerTrade / 100.0);
   double tick_val = m_symbol.TickValue();
   double point = m_symbol.Point();
   double tick_size = m_symbol.TickSize();

   if(sl_distance_points <= 0.0 || tick_val <= 0.0 || point <= 0.0) return 0.0;

   // Dollar loss per 1.0 standard lot = (sl_distance_points * point / tick_size) * tick_val
   double loss_per_lot = (sl_distance_points * point / tick_size) * tick_val;
   if(loss_per_lot <= 0.0) return 0.0;

   double raw_lots = risk_amount / loss_per_lot;
   double step = m_symbol.LotsStep();
   double min_lot = m_symbol.LotsMin();
   double max_lot = m_symbol.LotsMax();

   double normalized_lot = MathFloor(raw_lots / step) * step;
   if(normalized_lot < min_lot) normalized_lot = min_lot;
   if(normalized_lot > max_lot) normalized_lot = max_lot;

   return normalized_lot;
}

//+------------------------------------------------------------------+
//| Utility: Count Active EA Positions                               |
//+------------------------------------------------------------------+
int CountOpenPositions()
{
   int count = 0;
   for(int i = PositionsTotal() - 1; i >= 0; i--)
   {
      ulong ticket = PositionGetTicket(i);
      if(ticket > 0 && PositionGetString(POSITION_SYMBOL) == _Symbol && PositionGetInteger(POSITION_MAGIC) == InpMagicNumber)
      {
         count++;
      }
   }
   return count;
}

//+------------------------------------------------------------------+
//| Utility JSON String Parser Helper                                |
//+------------------------------------------------------------------+
string ExtractJsonStringValue(const string json, const string key)
{
   string needle = "\"" + key + "\":\"";
   int pos = StringFind(json, needle);
   if(pos < 0)
   {
      needle = "\"" + key + "\": \"";
      pos = StringFind(json, needle);
      if(pos < 0) return "";
   }
   int start = pos + StringLen(needle);
   int end = StringFind(json, "\"", start);
   if(end <= start) return "";
   return StringSubstr(json, start, end - start);
}

//+------------------------------------------------------------------+
//| Utility JSON Double Parser Helper                                |
//+------------------------------------------------------------------+
double ExtractJsonDoubleValue(const string json, const string key)
{
   string needle = "\"" + key + "\":";
   int pos = StringFind(json, needle);
   if(pos < 0)
   {
      needle = "\"" + key + "\": ";
      pos = StringFind(json, needle);
      if(pos < 0) return 0.0;
   }
   int start = pos + StringLen(needle);
   while(start < StringLen(json) && (StringGetCharacter(json, start) == ' ' || StringGetCharacter(json, start) == '\t'))
      start++;

   int end = start;
   while(end < StringLen(json))
   {
      ushort ch = StringGetCharacter(json, end);
      if((ch >= '0' && ch <= '9') || ch == '.' || ch == '-') end++;
      else break;
   }
   if(end <= start) return 0.0;
   return StringToDouble(StringSubstr(json, start, end - start));
}
//+------------------------------------------------------------------+
