#property copyright "Local XAUUSD research project"
#property version   "2.02"
#property strict
#property description "Native XAUUSD scalper: fixed 0.01 lot, <=3 positions, adaptive exits, free native inputs."
#include "GoldScalpMath.mqh"
#include "GoldScalpFlow.mqh"
#include "GoldScalpLearning.mqh"
#include "GoldScalpExit.mqh"
#include "GoldScalpMarket.mqh"
#include "GoldScalpSafety.mqh"
#include "GoldScalpStats.mqh"
#include "GoldScalpExecution.mqh"
#include "GoldScalpDashboard.mqh"
#include "GoldScalpFeeds.mqh"

input group "Execution and fixed user limits"
input bool EnableDemoOrders=false;
input ulong Magic=92563101;
input int MaxPositions=3;
input double RiskPerTradeUSD=2.0;
input double MaxAggregateRiskUSD=4.0;
input double RollingLossLimitUSD=5.0;
input double MaxSpreadPrice=0.30;
input double SlippageAllowancePrice=0.05;
input double RoundTripCommissionUSD=0.10;
input bool BlockOtherStrategies=true;
input bool AsyncExecution=true;
input double MaximumSlippagePrice=0.10;
input double DailyEquityLossPercent=3.0;
input double ShockATRMultiple=2.0;
input double SpreadAverageMultiplier=1.5;
input group "Native indicators and entry quality"
input int ATRPeriod=14;
input int FastEMA=9;
input int SlowEMA=21;
input double StopATR=0.80;
input double TargetATR=1.60;
input double MaximumSpreadATR=0.20;
input double MaximumCostFraction=0.25;
input double MaximumBarExpansion=2.5;
input double MinimumRelativeVolume=1.05;
input double MaximumRelativeVolume=6.0;
input int ConfirmationSeconds=3;
input int MinimumEntrySeconds=20;
input int MaxEntriesPerHour=12;
input int LossStreakLimit=3;
input int LossCooldownMinutes=15;
input group "Independent adaptive exits"
input bool UseBrokerTakeProfit=true;
input double BreakevenArmR=0.60;
input double TrailArmR=0.40;
input double TrailGivebackR=0.35;
input int ReversalConfirmationSeconds=2;
input int MaxHoldMinutes=20;
input group "Sessions and native economic calendar"
input int ServerUTCOffsetMinutes=180;
input int SessionStartUTC=13;
input int SessionEndUTC=16;
input bool UseNativeNews=true;
input bool TesterWithoutNews=true;
input int NewsMinutesBefore=10;
input int NewsMinutesAfter=5;
input bool CloseBeforeNews=true;
input group "Causal experimental learning"
input bool UseLearnedVeto=false;
input group "Protected Advisor 1 and dashboard"
input GOLD_ADVISOR_MODE Advisor1Mode=GOLD_ADVISOR_REQUIRED;
input string Advisor1File="GoldScalp\\advisor1.csv";
input string Advisor1ReplayFile="";
input int Advisor1MaxAgeSeconds=90;
input bool ShowDashboard=false;
input bool BrowserDashboardOnly=true;
input bool ExportWebDashboard=true;

const double FIXED_LOT=0.01;
CGoldFlow Flow;
CGoldOnlineModel Learner;
CGoldMarket Market;
CGoldSpreadWindow SpreadWindow;
CGoldSafety Safety;
CGoldStats Stats;
CGoldRequests Requests;
CGoldDashboard Dashboard;
CGoldAdvisorReference Advisor1;
CGoldNewsCache News;
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
   double peak,risk;
   datetime adverse_since,last_modify,last_close;
   ulong last_modify_ms;
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
GoldFlowRead last_fast,last_slow;

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
   return EnableDemoOrders && AccountInfoInteger(ACCOUNT_TRADE_MODE)==ACCOUNT_TRADE_MODE_DEMO
          && TerminalInfoInteger(TERMINAL_TRADE_ALLOWED) && MQLInfoInteger(MQL_TRADE_ALLOWED)
          && AccountInfoInteger(ACCOUNT_TRADE_ALLOWED) && AccountInfoInteger(ACCOUNT_TRADE_EXPERT);
  }
bool ValidQuote(const MqlTick &q)
  {
   if(q.time_msc<=0 || q.bid<=0 || q.ask<q.bid || !MathIsValidNumber(q.bid) || !MathIsValidNumber(q.ask))return false;
   long age=(long)TimeTradeServer()*1000-q.time_msc;
   return age>=-1000 && age<=2000;
  }
bool OwnSelected(){return PositionGetString(POSITION_SYMBOL)==_Symbol && (ulong)PositionGetInteger(POSITION_MAGIC)==Magic;}
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
double FloatingOwned()
  {
   double sum=0;
   for(int i=PositionsTotal()-1;i>=0;i--)if(PositionGetTicket(i)>0 && OwnSelected())sum+=PositionGetDouble(POSITION_PROFIT)+PositionGetDouble(POSITION_SWAP);
   return sum;
  }
bool RefreshIndicators()
  {
   bool ok=Market.Refresh(ServerNow());
   if(ok){atr=Market.atr;ema_fast=Market.fast;ema_slow=Market.slow;bar_range=Market.range;bar_close=Market.close;indicator_bar=Market.m1_bar;}
   return ok;
  }
bool BrokerSession(const datetime now)
  {
   MqlDateTime d;TimeToStruct(now,d);int seconds=d.hour*3600+d.min*60+d.sec;
   for(int previous=0;previous<=1;previous++)
     for(uint session=0;session<10;session++)
       {
        datetime from,to;ENUM_DAY_OF_WEEK day=(ENUM_DAY_OF_WEEK)((d.day_of_week+7-previous)%7);
        if(!SymbolInfoSessionTrade(_Symbol,day,session,from,to))break;
        int first=(int)((long)from%86400),last=(int)((long)to%86400);
        if(first==last && previous==0)return true;
        if(first<last && previous==0 && seconds>=first && seconds<last)return true;
        if(first>last && ((previous==0 && seconds>=first)||(previous==1 && seconds<last)))return true;
       }
   return false;
  }
bool EntrySession()
  {
   datetime now=ServerNow();MqlDateTime utc;TimeToStruct(GoldUTCNow(),utc);
   return utc.day_of_week>=1 && utc.day_of_week<=5 && GoldHourAllowed(utc.hour,SessionStartUTC,SessionEndUTC) && BrokerSession(now);
  }
void RefreshNews()
  {
   if(!UseNativeNews){news_ok=true;cached_news_active=false;return;}
   if(MQLInfoInteger(MQL_TESTER)){news_ok=TesterWithoutNews;cached_news_active=false;return;}
   datetime now=ServerNow();if(now-last_news>=5){News.Load(GoldNewsFile(AccountInfoString(ACCOUNT_SERVER)),AccountInfoString(ACCOUNT_SERVER));last_news=now;}
   news_ok=NewsFresh();cached_news_active=News.Active(now,NewsMinutesBefore,NewsMinutesAfter);
  }
void RefreshHistory()
  {
   datetime now=ServerNow();
   bool capital_stable=MathAbs(AccountInfoDouble(ACCOUNT_BALANCE)+AccountInfoDouble(ACCOUNT_CREDIT)-Stats.capital)<.001;
   if(!history_dirty && capital_stable && now-last_history<30 && GoldDayStart(now)==GoldDayStart(last_history))return;
   last_history=now;history_ok=Stats.Refresh(_Symbol,Magic,now,30);history_dirty=!history_ok;
   if(!history_ok)return;
   realized24=Stats.net24;entries_hour=Stats.entries_hour;last_entry=MathMax(last_entry,Stats.last_entry);last_exit=MathMax(last_exit,Stats.last_exit);
   loss_streak=Stats.loss_streak;if(loss_streak>=LossStreakLimit)loss_pause_until=Stats.last_loss+LossCooldownMinutes*60;
   Safety.reference=Stats.reference;Safety.Funding(Stats.funding_delta);
  }
int StateFor(const ulong id,const double initial_risk)
  {
   for(int i=0;i<ArraySize(managed);i++)if(managed[i].id==id)return i;
   int n=ArraySize(managed);ArrayResize(managed,n+1);
   managed[n].id=id;managed[n].peak=0;managed[n].risk=initial_risk;managed[n].adverse_since=0;managed[n].last_modify=0;managed[n].last_close=0;managed[n].last_modify_ms=0;
   string key=prefix+(string)id;
   if(!MQLInfoInteger(MQL_TESTER))
     {
      if(GlobalVariableCheck(key+"P"))managed[n].peak=GlobalVariableGet(key+"P");
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
      if(!MQLInfoInteger(MQL_TESTER)){GlobalVariableDel(prefix+(string)managed[i].id+"P");GlobalVariableDel(prefix+(string)managed[i].id+"R");}
      ArrayRemove(managed,i,1);
     }
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
      if(!MQLInfoInteger(MQL_TESTER) && peak>previous_peak)GlobalVariableSet(prefix+(string)id+"P",peak);
      bool opposing=fast.ready && slow.ready && sign*fast.pressure<-.5 && sign*slow.pressure<-.25 && fast.efficiency>=.5;
      if(opposing){if(managed[slot].adverse_since==0)managed[slot].adverse_since=TimeCurrent();}
      else managed[slot].adverse_since=0;
      double cost_buffer=2*DynamicSlip()+spread+(money_per_price>0?RoundTripCommissionUSD/money_per_price:0);
      double profit=PositionGetDouble(POSITION_PROFIT)+PositionGetDouble(POSITION_SWAP);
      GoldExitContext context={};context.move=move;context.peak=peak;context.risk=risk;context.spread=spread;
      context.cost_buffer=cost_buffer;context.profit=profit;context.commission=RoundTripCommissionUSD;
      context.fast_pressure=sign*fast.pressure;context.opposing=opposing;context.fast_ready=fast.ready;
      context.adverse_seconds=managed[slot].adverse_since>0?(int)(TimeCurrent()-managed[slot].adverse_since):0;
      context.held_seconds=(int)(TimeCurrent()-(datetime)PositionGetInteger(POSITION_TIME));
      double be_arm=GoldAdaptiveArm(risk,live_atr,BreakevenArmR,.5,cost_buffer);
      double trail_arm=GoldAdaptiveArm(risk,live_atr,TrailArmR,.35,cost_buffer);
      GOLD_EXIT exit=GoldChooseExit(context,trail_arm,TrailGivebackR,be_arm,ReversalConfirmationSeconds,MaxHoldMinutes*60);
      if(exit!=GOLD_HOLD){ClosePosition(ticket,EnumToString(exit));continue;}
      if(ExecutionClock()-managed[slot].last_modify_ms<250)continue;
      double candidate=sl;
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
   if(PositionsTotal()+OrdersTotal()>=MathMin(3,MaxPositions)){reason="Account position/order cap";return false;}
   if(BlockOtherStrategies)
     for(int i=PositionsTotal()-1;i>=0;i--)if(PositionGetTicket(i)>0 && !OwnSelected()){reason="Another strategy/manual position is active";return false;}
   long trade_mode=SymbolInfoInteger(_Symbol,SYMBOL_TRADE_MODE);
   if(trade_mode==SYMBOL_TRADE_MODE_DISABLED || trade_mode==SYMBOL_TRADE_MODE_CLOSEONLY || (side>0 && trade_mode==SYMBOL_TRADE_MODE_SHORTONLY) || (side<0 && trade_mode==SYMBOL_TRADE_MODE_LONGONLY))
     {reason="Sens de trading interdit par le courtier";return false;}
   double price=side>0?q.ask:q.bid,spread=q.ask-q.bid,slip=DynamicSlip();
   double stop=MathMax(StopATR*atr,MinDistance()+spread),target=TargetATR*atr;
   sl=RoundPrice(price-side*stop,side<0);tp=UseBrokerTakeProfit?RoundPrice(price+side*target,side>0):0;
   double commission_price=money_per_price>0?RoundTripCommissionUSD/money_per_price:0;
   if(money_per_price<=0 || target/stop<1.2 || !GoldCostFits(spread+2*slip+commission_price,target,MaximumCostFraction)){reason="Mouvement insuffisant apres frais";return false;}
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
      if(!OrderCalcProfit(buy?ORDER_TYPE_BUY:ORDER_TYPE_SELL,_Symbol,PositionGetDouble(POSITION_VOLUME),PositionGetDouble(POSITION_PRICE_OPEN),existing_sl,existing_loss))return false;
      aggregate+=MathMax(0,-existing_loss)+RoundTripCommissionUSD+2*slip*money_per_price;
     }
   double daily_remaining=AccountInfoDouble(ACCOUNT_EQUITY)-Safety.reference*(1-DailyEquityLossPercent/100.);
   if(aggregate>MaxAggregateRiskUSD || aggregate>daily_remaining){reason="Budget agrege / equity restant insuffisant";return false;}
   if(!OrderCalcMargin(type,_Symbol,FIXED_LOT,price,margin) || AccountInfoDouble(ACCOUNT_MARGIN_FREE)<margin+planned+2)
     {reason="Insufficient free margin";return false;}
   return true;
  }
#include "GoldScalpRuntime.mqh"
