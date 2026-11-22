#property copyright "Local XAUUSD research project"
#property version   "3.29"
#property strict
#property description "Native XAUUSD scalper: fixed 0.01 lot, <=3 positions, adaptive exits, resilient free news feed."
#include "GoldScalpMath.mqh"
#include "GoldScalpLatency.mqh"
#include "GoldScalpInstance.mqh"
#include "GoldScalpFlow.mqh"
#include "GoldScalpExpert.mqh"
#include "GoldScalpRotation.mqh"
#include "GoldScalpEntry.mqh"
#include "GoldScalpLearning.mqh"
#include "GoldScalpExit.mqh"
#include "GoldScalpMarket.mqh"
#include "GoldScalpIntelligence.mqh"
#include "GoldScalpSafety.mqh"
#include "GoldScalpStats.mqh"
#include "GoldScalpExecution.mqh"
#include "GoldScalpDashboard.mqh"
#include "GoldScalpFeeds.mqh"
#include "GoldScalpMacro.mqh"

input group "Execution and fixed user limits"
input bool EnableDemoOrders=false;
input ulong Magic=92563101;
input int MaxPositions=3;
input double RiskPerTradeUSD=2.0;
input double MaxAggregateRiskUSD=4.0;
input double RollingLossLimitUSD=5.0;
input double MaxSpreadPrice=0.60;
input double SlippageAllowancePrice=0.05;
input double RoundTripCommissionUSD=0.10;
input bool BlockOtherStrategies=true;
input bool AsyncExecution=true;
input double MaximumSlippagePrice=0.10;
input double DailyEquityLossPercent=3.0; // zero disables daily equity pause
input double ShockATRMultiple=2.0;
input double SpreadAverageMultiplier=1.8;
input group "Scalper Expert: tick-led decisions"
input bool ExpertScalpMode=true;
input bool FrequentEntryMode=true;
input double MinimumScalpScore=50;
input double ProfitGivebackFraction=0.333333;
input double MinimumProfitArmUSD=0.35;
input bool AdaptiveSessions=true;
input bool UseRapidRotation=true;
input bool UseRapidContinuation=true;
input bool UseTrendContinuation=true;
input int RapidRearmMilliseconds=250;
input bool UseImpulseAcceleration=true;
input bool UseConfirmationGrace=true;
input bool UseCounterflowGuard=true;
input group "Causal market intelligence"
input bool UseMarketIntelligence=true;
input bool IntelligenceVetoAbnormal=true;
input group "Native indicators and entry quality"
input int ATRPeriod=14;
input int FastEMA=9;
input int SlowEMA=21;
input double StopATR=0.65;
input double TargetATR=1.60;
input double MaximumSpreadATR=0.50;
input double MaximumCostFraction=0.45;
input double MaximumBarExpansion=2.5;
input double MinimumRelativeVolume=0.35;
input double MaximumRelativeVolume=6.0;
input int ConfirmationSeconds=1;
input int MinimumEntrySeconds=1;
input int MaxEntriesPerHour=60;
input int LossStreakLimit=3;
input int LossCooldownMinutes=1;
input group "Independent adaptive exits"
input bool UseBrokerTakeProfit=false;
input double BreakevenArmR=0.60;
input double TrailArmR=0.40;
input double TrailGivebackR=0.35;
input int ReversalConfirmationSeconds=2;
input int MaxHoldMinutes=20;
input group "Sessions and native economic calendar"
input int ServerUTCOffsetMinutes=180;
input int SessionStartUTC=13; // applied only when ExpertScalpMode=false
input int SessionEndUTC=16; // applied only when ExpertScalpMode=false
input bool BlockAsiaSession=false; // Optional entry restriction; disabled for broker-open full-time scalping
input int ScalpEntryStartUTC=-1; // optional extra scalp entry window (both -1 disables; for pre-registered V2 tests)
input int ScalpEntryEndUTC=-1;
input bool UseNativeNews=true;
input bool TesterWithoutNews=true;
input int NewsMinutesBefore=10;
input int NewsMinutesAfter=5;
input bool CloseBeforeNews=true;
input group "Causal experimental learning"
input bool UseLearnedVeto=false;
input group "Protected Advisor 1 and dashboard"
input GOLD_ADVISOR_MODE Advisor1Mode=GOLD_ADVISOR_REFERENCE;
input string Advisor1File="GoldScalp\\advisor1.csv";
input string Advisor1ReplayFile="";
input int Advisor1MaxAgeSeconds=90;
input bool ShowDashboard=false;
input bool BrowserDashboardOnly=true;
input bool ExportWebDashboard=true;
input bool AllowBrowserControls=true;

const double FIXED_LOT=0.01;
CGoldInstanceLease AccountLease;
bool startup_complete=false;
CGoldFlow Flow;
CGoldRotation Rotation;
CGoldEntryConfirmation EntryConfirmation;
CGoldOnlineModel Learner;
CGoldMarket Market;
CGoldScalpIntelligence Intelligence;
CGoldSpreadWindow SpreadWindow;
CGoldSafety Safety;
CGoldStats Stats;
CGoldRequests Requests;
CGoldDashboard Dashboard;
CGoldAdvisorReference Advisor1;
CGoldNewsCache News;
CGoldMacro Macro;
double macro_bonus=0;
double atr=0,ema_fast=0,ema_slow=0,trend=0,bar_range=0,bar_close=0;
datetime indicator_bar=0,last_entry=0,last_exit=0,last_history=0,last_news=0;
datetime news_start=0,news_end=0,loss_pause_until=0;
datetime news_starts[],news_ends[];
double realized24=0;
bool history_ok=false,news_ok=false,risk_latched=false,request_pending=false;
datetime pending_until=0,signal_since=0,last_submit=0;
int signal_side=0,entries_hour=0,loss_streak=0;
string status="Starting",lock_name="",prefix="";
double lock_owner=0;
double last_prediction=.5;
ulong attempts=0,filled=0,rejections=0,quote_count=0;
long last_quote_msc=0;
struct GoldPositionState
  {
   ulong id;
   double peak,risk,net_peak;
   datetime adverse_since,last_modify,last_close;
   ulong last_modify_ms;
   long micro_adverse_since;
  };
GoldPositionState managed[];
bool paused=false,close_all_requested=false,relative_spread_ok=false,history_dirty=true;
bool ambiguity_persisted=false,owns_lock=false,owns_account_lock=false;
long flow_snapshot_msc=0;
bool cached_session=false,cached_news_active=false,volatility_ok=false;
double spread_before=0,live_atr=0,bar_high=0,bar_low=0,prior_mid=0,last_bid=0,last_ask=0;
double money_per_price=0;
datetime live_bar=0,last_slow_timer=0,last_dashboard=0,last_safety_save=0;
string safety_key="",last_execution="Aucune requete",advisor_status="En attente";
ulong total_tick_us=0,max_tick_us=0,retry_count=0,tick_calls=0;
GoldFlowRead last_fast,last_slow,last_micro,last_context;
bool trend_entry_lane=false;
bool signal_grace_eligible=false;
long signal_since_msc=0;
double acceleration_bonus=0,ack_latency_ms=0,ack_latency_max_ms=0,last_fill_slippage=0;
int intelligence_adjustment=0;
bool fill_slippage_valid=false;
ulong ack_samples=0;
string control_instance="",control_last_id="",control_result="No browser command";
double scalp_score=0,scalp_threshold=62;
bool UnifiedExecutionEnabled=false;
bool UnifiedConfigLoaded=false;
string UnifiedMode="observe",UnifiedTimeframe="M1";
string UnifiedScheduleMode="all_day";
int UnifiedBlockedStartUTC=-1,UnifiedBlockedEndUTC=-1;
struct GoldBrokerSessionSnapshot
  {
   bool schedule_available,scheduled_open,preclose_active;
   datetime active_open,active_close,next_open,next_close;
   int seconds_to_close;
  };
GoldBrokerSessionSnapshot BrokerSessionState;
string session_close_status="Waiting for broker session schedule";
int session_close_remaining=0;
bool UnifiedReadConfig()
  {
   int file=FileOpen("GoldScalp\\unified_config.csv",FILE_READ|FILE_CSV|FILE_ANSI|FILE_COMMON|FILE_SHARE_READ,';',CP_UTF8);
   UnifiedConfigLoaded=false;UnifiedExecutionEnabled=false;
   UnifiedMode="observe";UnifiedTimeframe="M1";UnifiedScheduleMode="all_day";
   UnifiedBlockedStartUTC=-1;UnifiedBlockedEndUTC=-1;
   if(file==INVALID_HANDLE)return false;
   string fields[9];
   for(int i=0;i<6;i++)
     {
      if(FileIsEnding(file)){FileClose(file);return false;}
      fields[i]=FileReadString(file);
     }
   bool legacy=fields[0]=="GOLD_UNIFIED_V1";
   if(!legacy)
     {
      if(fields[0]!="GOLD_UNIFIED_V2"){FileClose(file);return false;}
      for(int i=6;i<9;i++)
        {
         if(FileIsEnding(file)){FileClose(file);return false;}
         fields[i]=FileReadString(file);
        }
     }
   FileClose(file);
   if(fields[1]!="XAUUSD" ||
      (fields[2]!="observe" && fields[2]!="demo") ||
      (fields[3]!="M1" && fields[3]!="M5") ||
      (fields[4]!="enabled" && fields[4]!="disabled"))return false;
   string schedule_mode="all_day";int blocked_start=-1,blocked_end=-1;
   if(legacy)
     {if(fields[5]!="END")return false;}
   else
     {
      if(fields[8]!="END")return false;
      schedule_mode=fields[5];
      if(schedule_mode=="all_day")
        {if(fields[6]!="-1" || fields[7]!="-1")return false;}
      else if(schedule_mode=="exclude_window")
        {
         long start_value=StringToInteger(fields[6]),end_value=StringToInteger(fields[7]);
         if((string)start_value!=fields[6] || (string)end_value!=fields[7] ||
            start_value<0 || start_value>23 || end_value<0 || end_value>23 || start_value==end_value)return false;
         blocked_start=(int)start_value;blocked_end=(int)end_value;
        }
      else return false;
     }
   UnifiedMode=fields[2];UnifiedTimeframe=fields[3];UnifiedConfigLoaded=true;
   UnifiedExecutionEnabled=(UnifiedMode=="demo" && fields[4]=="enabled");
   UnifiedScheduleMode=schedule_mode;UnifiedBlockedStartUTC=blocked_start;UnifiedBlockedEndUTC=blocked_end;
   return true;
  }
string scalp_analysis="Waiting for fresh market indicators";
long scalp_analysis_msc=0;
int session_bucket=4;
double SessionAdjustment()
  {return AdaptiveSessions && session_bucket<4?GoldSessionAdjustment(Stats.session_count[session_bucket],Stats.session_net[session_bucket],Stats.session_squares[session_bucket]):0;}

datetime ServerNow(){return MQLInfoInteger(MQL_TESTER)?TimeCurrent():TimeTradeServer();}
// Live reports use UTC, independent of the broker's server/DST offset.
// Tester timestamps retain the configured historical server offset.
datetime GoldUTCNow(){return MQLInfoInteger(MQL_TESTER)?TimeCurrent()-ServerUTCOffsetMinutes*60:TimeGMT();}
ulong ExecutionClock(){return MQLInfoInteger(MQL_TESTER)?(ulong)MathMax((long)TimeCurrent()*1000,last_quote_msc):GetTickCount64();}
double DynamicSlip(){return GoldSlippage(last_ask-last_bid,live_atr,SlippageAllowancePrice,MaximumSlippagePrice);}
bool NewsFresh(){return !UseNativeNews || (MQLInfoInteger(MQL_TESTER)?TesterWithoutNews:News.Fresh(TimeTradeServer()));}
bool ExposureReady(){return Stats.ready && !history_dirty && ServerNow()-Stats.refreshed<=35 && MathAbs(AccountInfoDouble(ACCOUNT_BALANCE)+AccountInfoDouble(ACCOUNT_CREDIT)-Stats.capital)<.001;}

bool CanExecute()
  {
   if(MQLInfoInteger(MQL_TESTER))return true;
   return (EnableDemoOrders || UnifiedExecutionEnabled) && AccountInfoInteger(ACCOUNT_TRADE_MODE)==ACCOUNT_TRADE_MODE_DEMO
          && TerminalInfoInteger(TERMINAL_TRADE_ALLOWED) && MQLInfoInteger(MQL_TRADE_ALLOWED)
          && AccountInfoInteger(ACCOUNT_TRADE_ALLOWED) && AccountInfoInteger(ACCOUNT_TRADE_EXPERT);
  }
bool ValidQuote(const MqlTick &q)
  {
   if(q.time_msc<=0 || q.bid<=0 || q.ask<q.bid || !MathIsValidNumber(q.bid) || !MathIsValidNumber(q.ask))return false;
   long age=(long)TimeTradeServer()*1000-q.time_msc;
   return age>=-1000 && age<=2000;
  }
bool OwnSelected(){return GoldSafetyOwnsExposure(PositionGetString(POSITION_SYMBOL),_Symbol,(ulong)PositionGetInteger(POSITION_MAGIC),Magic);}
double RoundPrice(const double p,const bool up)
  {return NormalizeDouble(GoldRound(p,SymbolInfoDouble(_Symbol,SYMBOL_TRADE_TICK_SIZE),up),(int)SymbolInfoInteger(_Symbol,SYMBOL_DIGITS));}
double MinDistance(const bool modification=false)
  {
   long points=SymbolInfoInteger(_Symbol,SYMBOL_TRADE_STOPS_LEVEL);
   if(modification)points=MathMax(points,SymbolInfoInteger(_Symbol,SYMBOL_TRADE_FREEZE_LEVEL));
   return points*SymbolInfoDouble(_Symbol,SYMBOL_POINT)+SymbolInfoDouble(_Symbol,SYMBOL_TRADE_TICK_SIZE);
  }
ENUM_ORDER_TYPE_FILLING FillMode()
  {
   long mask=SymbolInfoInteger(_Symbol,SYMBOL_FILLING_MODE);
   if((mask&SYMBOL_FILLING_FOK)!=0)return ORDER_FILLING_FOK;
   if((mask&SYMBOL_FILLING_IOC)!=0)return ORDER_FILLING_IOC;
   return ORDER_FILLING_RETURN;
  }
#include "GoldScalpTelemetry.mqh"
#include "GoldScalpOrders.mqh"
#include "GoldScalpSession.mqh"
double FloatingOwned()
  {
   double sum=0;
   for(int i=PositionsTotal()-1;i>=0;i--)if(PositionGetTicket(i)>0 && OwnSelected())sum+=PositionGetDouble(POSITION_PROFIT)+PositionGetDouble(POSITION_SWAP);
   return sum;
  }
bool RefreshIndicators()
  {
   bool ok=Market.Refresh(ServerNow());
   if(ok){atr=Market.atr;ema_fast=Market.fast;ema_slow=Market.slow;bar_range=Market.range;bar_close=Market.close;indicator_bar=Market.m1_bar;Intelligence.Refresh(Market,last_ask-last_bid,MaximumBarExpansion);}
   return ok;
  }
bool EntrySession()
  {
   datetime now=ServerNow();MqlDateTime utc;TimeToStruct(GoldUTCNow(),utc);
   bool hours=ExpertScalpMode?GoldBucketEntriesAllowed(GoldSessionBucket(GoldUTCNow()),BlockAsiaSession) && GoldScalpWindowAllowed(utc.hour,ScalpEntryStartUTC,ScalpEntryEndUTC):GoldHourAllowed(utc.hour,SessionStartUTC,SessionEndUTC);
   bool before_close=GoldSessionCloseDue(BrokerSessionState.scheduled_open,BrokerSessionState.active_close,now);
   return hours && GoldUnifiedScheduleAllowed(utc.hour,UnifiedScheduleMode,UnifiedBlockedStartUTC,UnifiedBlockedEndUTC) &&
      BrokerSessionState.schedule_available && BrokerSessionState.scheduled_open && !before_close;
  }
void RefreshNews()
  {
   if(!UseNativeNews){news_ok=true;cached_news_active=false;return;}
   if(MQLInfoInteger(MQL_TESTER)){news_ok=TesterWithoutNews;cached_news_active=false;return;}
   datetime now=ServerNow();if(now-last_news>=5)
     {
      string server=AccountInfoString(ACCOUNT_SERVER);News.Load(GoldNewsFile(server),server);
      bool recent_quote=last_bid>0 && last_ask>=last_bid && last_quote_msc>0 && MathAbs((double)((long)now*1000-last_quote_msc))<=2000;
      Macro.Load(server,now,recent_quote?(last_bid+last_ask)*.5:0);last_news=now;
     }
   news_ok=NewsFresh();cached_news_active=News.Active(now,NewsMinutesBefore,NewsMinutesAfter);
  }
void RefreshHistory()
  {
   datetime now=ServerNow();
   bool capital_stable=MathAbs(AccountInfoDouble(ACCOUNT_BALANCE)+AccountInfoDouble(ACCOUNT_CREDIT)-Stats.capital)<.001;
   if(!history_dirty && capital_stable && now-last_history<30 && GoldDayStart(now)==GoldDayStart(last_history))return;
   last_history=now;history_ok=Stats.Refresh(_Symbol,Magic,now,30,ServerUTCOffsetMinutes);history_dirty=!history_ok;
   if(!history_ok)return;
   realized24=Stats.net24;entries_hour=Stats.entries_hour;last_entry=MathMax(last_entry,Stats.last_entry);last_exit=MathMax(last_exit,Stats.last_exit);
   loss_streak=Stats.loss_streak;loss_pause_until=loss_streak>=LossStreakLimit?Stats.last_loss+LossCooldownMinutes*60:0;
   Safety.reference=Stats.reference;Safety.Funding(Stats.funding_delta);
  }
int StateFor(const ulong id,const double initial_risk)
  {
   for(int i=0;i<ArraySize(managed);i++)if(managed[i].id==id)return i;
   int n=ArraySize(managed);ArrayResize(managed,n+1);
   managed[n].id=id;managed[n].peak=0;managed[n].net_peak=0;managed[n].risk=initial_risk;managed[n].adverse_since=0;managed[n].micro_adverse_since=0;managed[n].last_modify=0;managed[n].last_close=0;managed[n].last_modify_ms=0;
   string key=prefix+(string)id;
   if(!MQLInfoInteger(MQL_TESTER))
     {
      if(GlobalVariableCheck(key+"P"))managed[n].peak=GlobalVariableGet(key+"P");
      if(GlobalVariableCheck(key+"N"))managed[n].net_peak=GlobalVariableGet(key+"N");
      if(GlobalVariableCheck(key+"R"))managed[n].risk=GlobalVariableGet(key+"R");
      GlobalVariableSet(key+"R",managed[n].risk);
     }
   return n;
  }
void PruneClosedState()
  {
   for(int i=ArraySize(managed)-1;i>=0;i--)
     {
      bool open=false;
      for(int p=PositionsTotal()-1;p>=0;p--)if(PositionGetTicket(p)>0 && (ulong)PositionGetInteger(POSITION_IDENTIFIER)==managed[i].id){open=true;break;}
      if(open)continue;
      if(!MQLInfoInteger(MQL_TESTER)){GlobalVariableDel(prefix+(string)managed[i].id+"P");GlobalVariableDel(prefix+(string)managed[i].id+"R");GlobalVariableDel(prefix+(string)managed[i].id+"N");}
      ArrayRemove(managed,i,1);
     }
  }
void PersistManagedPeaks()
  {
   if(MQLInfoInteger(MQL_TESTER) || !owns_lock)return;
   for(int i=0;i<ArraySize(managed);i++)
     {string key=prefix+(string)managed[i].id;GlobalVariableSet(key+"P",managed[i].peak);GlobalVariableSet(key+"N",managed[i].net_peak);}
  }
void ManagePositions(const MqlTick &q,const GoldFlowRead &fast,const GoldFlowRead &slow)
  {
   for(int i=PositionsTotal()-1;i>=0;i--)
     {
      ulong ticket=PositionGetTicket(i);if(ticket==0 || !OwnSelected())continue;
      bool buy=PositionGetInteger(POSITION_TYPE)==POSITION_TYPE_BUY;int sign=buy?1:-1;
      double entry=PositionGetDouble(POSITION_PRICE_OPEN),sl=PositionGetDouble(POSITION_SL),tp=PositionGetDouble(POSITION_TP);
      double volume=PositionGetDouble(POSITION_VOLUME),price=buy?q.bid:q.ask,move=sign*(price-entry),spread=q.ask-q.bid;
      if(MathAbs(volume-FIXED_LOT)>1e-8 || sl<=0){ClosePosition(ticket,"Unexpected volume or missing broker stop");continue;}
      double estimate=0;
      if(!OrderCalcProfit(buy?ORDER_TYPE_BUY:ORDER_TYPE_SELL,_Symbol,volume,entry,sl,estimate))
        {ClosePosition(ticket,"Conversion risque indisponible");continue;}
      if(estimate-RoundTripCommissionUSD < -MathMin(2.,RiskPerTradeUSD)-.01){ClosePosition(ticket,"Filled stop exposure exceeds budget");continue;}
      ulong id=(ulong)PositionGetInteger(POSITION_IDENTIFIER);
      int slot=StateFor(id,MathMax(MathAbs(entry-sl),SymbolInfoDouble(_Symbol,SYMBOL_TRADE_TICK_SIZE)));
      double previous_peak=managed[slot].peak;
      managed[slot].peak=MathMax(previous_peak,move);double peak=managed[slot].peak,risk=managed[slot].risk;
      bool opposing=ExpertScalpMode?(fast.ready && sign*fast.pressure<-.35 && fast.efficiency>=.35):
                    (fast.ready && slow.ready && sign*fast.pressure<-.5 && sign*slow.pressure<-.25 && fast.efficiency>=.5);
      if(opposing){if(managed[slot].adverse_since==0)managed[slot].adverse_since=TimeCurrent();}
      else managed[slot].adverse_since=0;
      double cost_buffer=2*DynamicSlip()+spread+(money_per_price>0?RoundTripCommissionUSD/money_per_price:0);
      double profit=PositionGetDouble(POSITION_PROFIT)+PositionGetDouble(POSITION_SWAP);
      double net=profit-RoundTripCommissionUSD,old_net_peak=managed[slot].net_peak;
      managed[slot].net_peak=MathMax(old_net_peak,net);
      double noise=GoldProfitNoise(live_atr,spread,DynamicSlip(),money_per_price);
      if(ExpertScalpMode)
        {
         // Executable-side P&L is already spread-adjusted; only fees/slippage remain.
         cost_buffer=DynamicSlip()+(money_per_price>0?RoundTripCommissionUSD/money_per_price:0);
         if(GoldProfitGiveback(net,managed[slot].net_peak,ProfitGivebackFraction,noise,MinimumProfitArmUSD))
           {ClosePosition(ticket,"SCALP: protected peak-profit giveback");continue;}
         bool micro_against=last_micro.ready && sign*last_micro.pressure<=-.5 && last_micro.efficiency>=.55;
         if(micro_against){if(managed[slot].micro_adverse_since==0)managed[slot].micro_adverse_since=q.time_msc;}
         else managed[slot].micro_adverse_since=0;
         if(micro_against && (GoldEarlyProfitExit(net,managed[slot].net_peak,noise,sign*last_micro.pressure,last_micro.efficiency,q.time_msc-managed[slot].micro_adverse_since) || GoldMicroTakeOut(net,managed[slot].net_peak,noise,MinimumProfitArmUSD,sign*last_micro.pressure,
            last_micro.efficiency,sign*fast.velocity,sign*slow.velocity,q.time_msc-managed[slot].micro_adverse_since)))
           {ClosePosition(ticket,"SCALP: micro reversal, protect runner");continue;}
         int adverse=managed[slot].adverse_since>0?(int)(TimeCurrent()-managed[slot].adverse_since):0;
         if(opposing && adverse>=ReversalConfirmationSeconds && net>noise)
           {ClosePosition(ticket,"SCALP: confirmed reversal, bank net profit");continue;}
         if(opposing && adverse>=ReversalConfirmationSeconds+1 && slow.ready && sign*slow.pressure<-.25 && move<-MathMax(spread,.2*live_atr))
           {ClosePosition(ticket,"SCALP: impulse failed, cut exposure");continue;}
        }
      GoldExitContext context={};context.move=move;context.peak=peak;context.risk=risk;context.spread=spread;
      context.cost_buffer=cost_buffer;context.profit=profit;context.commission=RoundTripCommissionUSD;
      context.fast_pressure=sign*fast.pressure;context.opposing=opposing;context.fast_ready=fast.ready;
      context.adverse_seconds=managed[slot].adverse_since>0?(int)(TimeCurrent()-managed[slot].adverse_since):0;
      context.held_seconds=(int)(TimeCurrent()-(datetime)PositionGetInteger(POSITION_TIME));
      double be_arm=GoldAdaptiveArm(risk,live_atr,BreakevenArmR,.5,cost_buffer);
      double trail_arm=GoldAdaptiveArm(risk,live_atr,TrailArmR,.35,cost_buffer);
      GOLD_EXIT exit=ExpertScalpMode?GOLD_HOLD:GoldChooseExit(context,trail_arm,TrailGivebackR,be_arm,ReversalConfirmationSeconds,MaxHoldMinutes*60);
      if(ExpertScalpMode && context.held_seconds>=MaxHoldMinutes*60 && net<noise)exit=GOLD_STAGNATION;
      if(exit!=GOLD_HOLD){ClosePosition(ticket,EnumToString(exit));continue;}
      if(ExecutionClock()-managed[slot].last_modify_ms<250)continue;
      double candidate=sl;
      if(ExpertScalpMode && money_per_price>0 && managed[slot].net_peak>=MathMax(MinimumProfitArmUSD,2*noise))
        {
         double retained=GoldRetainedProfit(managed[slot].net_peak,ProfitGivebackFraction,noise);
         double protected_price=entry+sign*(retained+RoundTripCommissionUSD)/money_per_price;
         candidate=buy?MathMax(candidate,protected_price):MathMin(candidate,protected_price);
        }
      if(peak>=be_arm*risk)candidate=buy?MathMax(candidate,entry+cost_buffer):MathMin(candidate,entry-cost_buffer);
      if(peak>=trail_arm*risk && live_atr>0)
        {
         double distance=MathMax(.7*live_atr,MathMax(TrailGivebackR*risk,2.5*spread));
         candidate=buy?MathMax(candidate,price-distance):MathMin(candidate,price+distance);
        }
      candidate=RoundPrice(candidate,!buy);
      double minimum=MinDistance(true),step=SymbolInfoDouble(_Symbol,SYMBOL_TRADE_TICK_SIZE);
      if(sign*(candidate-sl)<MathMax(step,.2*spread) || sign*(price-candidate)<minimum)continue;
      MqlTradeRequest req={};req.action=TRADE_ACTION_SLTP;req.symbol=_Symbol;req.position=ticket;req.magic=Magic;req.sl=candidate;req.tp=tp;
      managed[slot].last_modify_ms=ExecutionClock();Submit(req,"Tighten protective stop");
     }
  }
bool EntryRisk(const int side,const MqlTick &q,double &sl,double &tp,string &reason)
  {
   if(!GoldPositionCapacity(PositionsTotal(),OrdersTotal(),MaxPositions)){reason="Account position/order cap";return false;}
   if(BlockOtherStrategies)
     for(int i=PositionsTotal()-1;i>=0;i--)if(PositionGetTicket(i)>0 && !OwnSelected()){reason="Another strategy/manual position is active";return false;}
   long trade_mode=SymbolInfoInteger(_Symbol,SYMBOL_TRADE_MODE);
   if(trade_mode==SYMBOL_TRADE_MODE_DISABLED || trade_mode==SYMBOL_TRADE_MODE_CLOSEONLY || (side>0 && trade_mode==SYMBOL_TRADE_MODE_SHORTONLY) || (side<0 && trade_mode==SYMBOL_TRADE_MODE_LONGONLY))
     {reason="Sens de trading interdit par le courtier";return false;}
   double price=side>0?q.ask:q.bid,spread=q.ask-q.bid,slip=DynamicSlip();
   double stop=MathMax(StopATR*atr,MinDistance()+spread),target=TargetATR*atr;
   if(ExpertScalpMode)
     {
      double floor_distance=MathMax(.30*atr,MathMax(2*spread,MinDistance()+spread));
      stop=GoldAffordableStop(stop,floor_distance,MathMin(2.,RiskPerTradeUSD)-SymbolInfoDouble(_Symbol,SYMBOL_TRADE_TICK_SIZE)*money_per_price,RoundTripCommissionUSD,slip,money_per_price);
      if(stop<=0){reason="SCALP: structural stop cannot fit fixed-lot risk budget";return false;}
      target=MathMax(.85*atr,MathMin(1.5*atr,MathAbs(last_slow.move)*1.5));
     }
   sl=RoundPrice(price-side*stop,side<0);tp=UseBrokerTakeProfit?RoundPrice(price+side*target,side>0):0;
   double commission_price=money_per_price>0?RoundTripCommissionUSD/money_per_price:0;
   if(money_per_price<=0 || (!ExpertScalpMode && target/stop<1.2) || !GoldCostFits(spread+2*slip+commission_price,target,MaximumCostFraction)){reason="Mouvement insuffisant apres frais";return false;}
   ENUM_ORDER_TYPE type=side>0?ORDER_TYPE_BUY:ORDER_TYPE_SELL;double loss=0,cost=0,margin=0;
   if(!OrderCalcProfit(type,_Symbol,FIXED_LOT,price,sl,loss) || !OrderCalcProfit(type,_Symbol,FIXED_LOT,price,price-side*2*slip,cost))
     {reason="Risk conversion unavailable";return false;}
   double planned=MathAbs(loss)+MathAbs(cost)+RoundTripCommissionUSD;
   if(planned>MathMin(2.,RiskPerTradeUSD)){reason="ATR stop does not fit fixed 0.01 lot / $2 budget";return false;}
   double aggregate=planned;
   for(int i=PositionsTotal()-1;i>=0;i--)
     {
      if(PositionGetTicket(i)==0 || !OwnSelected())continue;
      double existing_sl=PositionGetDouble(POSITION_SL),existing_loss=0;
      if(existing_sl<=0 || MathAbs(PositionGetDouble(POSITION_VOLUME)-FIXED_LOT)>1e-8){reason="Position existante non conforme";return false;}
      bool buy=PositionGetInteger(POSITION_TYPE)==POSITION_TYPE_BUY;
      if(ExpertScalpMode)
        {
         double opened=PositionGetDouble(POSITION_PRICE_OPEN),mark=buy?q.bid:q.ask;
         int existing_side=buy?1:-1;
         if(existing_side!=side || existing_side*(existing_sl-opened)<0 || existing_side*(mark-opened)<MathMax(.25*atr,spread+commission_price))
           {reason="SCALP: add only to protected winning positions; no averaging down";return false;}
        }
      if(!OrderCalcProfit(buy?ORDER_TYPE_BUY:ORDER_TYPE_SELL,_Symbol,PositionGetDouble(POSITION_VOLUME),PositionGetDouble(POSITION_PRICE_OPEN),existing_sl,existing_loss))return false;
      aggregate+=MathMax(0,-existing_loss)+RoundTripCommissionUSD+2*slip*money_per_price;
     }
   if(aggregate>MaxAggregateRiskUSD || !GoldDailyRiskFits(aggregate,AccountInfoDouble(ACCOUNT_EQUITY),Safety.reference,DailyEquityLossPercent))
     {reason="Budget agrege / equity restant insuffisant";return false;}
   double rolling_remaining=GoldRollingRiskRemaining(RollingLossLimitUSD,Stats.budget_net);
   if(!GoldRiskReservationFits(planned,aggregate-planned,rolling_remaining))
     {reason="SCALP: rolling loss budget remaining $"+DoubleToString(rolling_remaining,2)+" < reserved stop risk $"+DoubleToString(aggregate,2);return false;}
   if(!OrderCalcMargin(type,_Symbol,FIXED_LOT,price,margin) || AccountInfoDouble(ACCOUNT_MARGIN_FREE)<margin+planned+2)
     {reason="Insufficient free margin";return false;}
   return true;
  }
#include "GoldScalpRuntime.mqh"
