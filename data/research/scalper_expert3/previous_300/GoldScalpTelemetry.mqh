#ifndef GOLD_SCALP_TELEMETRY
#define GOLD_SCALP_TELEMETRY
// Read-only browser telemetry. File/history work runs on the timer, never OnTick.
// Account-specific filenames prevent another terminal silently replacing this feed.
#include "GoldScalpWire.mqh"
string telemetry_events[40];
int telemetry_event_next=0,telemetry_event_count=0;
ulong telemetry_event_sequence=0,telemetry_written_ms=0;
string telemetry_previous_status="",telemetry_deals="[]",telemetry_candles="";
string telemetry_last_payload="";
datetime telemetry_history_at=0,telemetry_candle_bar=0;
bool telemetry_history_ok=false;
void GoldTelemetryEvent(const string kind,const string text)
  {
   if(!ExportWebDashboard || MQLInfoInteger(MQL_TESTER))return;
   telemetry_events[telemetry_event_next]="{\"id\":"+(string)(++telemetry_event_sequence)+",\"time\":"+GoldJson(TimeToString(ServerNow(),TIME_DATE|TIME_SECONDS))+",\"kind\":"+GoldJson(kind)+",\"text\":"+GoldJson(text)+"}";
   telemetry_event_next=(telemetry_event_next+1)%40;telemetry_event_count=MathMin(40,telemetry_event_count+1);
  }
string GoldTelemetryEvents()
  {
   string out="[";
   for(int i=0;i<telemetry_event_count;i++){if(i>0)out+=",";out+=telemetry_events[(telemetry_event_next-1-i+40)%40];}
   return out+"]";
  }
string GoldTelemetryCandles()
  {
   MqlRates current[1];if(CopyRates(_Symbol,PERIOD_M1,0,1,current)!=1)return "[]";
   if(telemetry_candle_bar!=current[0].time)
     {
      MqlRates past[];int count=CopyRates(_Symbol,PERIOD_M1,1,179,past);
      if(count<1)return "["+GoldRateJson(current[0])+"]";
      telemetry_candles="";
      for(int i=0;i<count;i++){if(i>0)telemetry_candles+=",";telemetry_candles+=GoldRateJson(past[i]);}
      telemetry_candle_bar=current[0].time;
     }
   return "["+telemetry_candles+","+GoldRateJson(current[0])+"]";
  }
void GoldTelemetryHistory(const datetime now)
  {
   if(telemetry_history_at>0 && now-telemetry_history_at<10)return;
   telemetry_history_at=now;telemetry_history_ok=HistorySelect(now-7*86400,now);
   if(!telemetry_history_ok){telemetry_deals="[]";return;}
   string out="[";int count=0,total=HistoryDealsTotal();
   // Account executions (not completed-position statistics): cap scan and payload.
   for(int i=total-1;i>=MathMax(0,total-1000) && count<60;i--)
     {
      ulong ticket=HistoryDealGetTicket(i);if(ticket==0)continue;
      long type=HistoryDealGetInteger(ticket,DEAL_TYPE);if(type!=DEAL_TYPE_BUY && type!=DEAL_TYPE_SELL)continue;
      string symbol=HistoryDealGetString(ticket,DEAL_SYMBOL);
      bool owned=symbol==_Symbol && (ulong)HistoryDealGetInteger(ticket,DEAL_MAGIC)==Magic;
      if(count++>0)out+=",";
      double net=HistoryDealGetDouble(ticket,DEAL_PROFIT)+HistoryDealGetDouble(ticket,DEAL_COMMISSION)+HistoryDealGetDouble(ticket,DEAL_SWAP)+HistoryDealGetDouble(ticket,DEAL_FEE);
      out+="{\"ticket\":"+GoldJson((string)ticket)+",\"position\":"+GoldJson((string)HistoryDealGetInteger(ticket,DEAL_POSITION_ID))+
           ",\"time\":"+GoldJson(TimeToString((datetime)HistoryDealGetInteger(ticket,DEAL_TIME),TIME_DATE|TIME_SECONDS))+
           ",\"symbol\":"+GoldJson(symbol)+",\"owned\":"+GoldBool(owned)+",\"side\":"+GoldJson(type==DEAL_TYPE_BUY?"BUY":"SELL")+
           ",\"entry\":"+GoldJson(EnumToString((ENUM_DEAL_ENTRY)HistoryDealGetInteger(ticket,DEAL_ENTRY)))+
           ",\"reason\":"+GoldJson(EnumToString((ENUM_DEAL_REASON)HistoryDealGetInteger(ticket,DEAL_REASON)))+
           ",\"volume\":"+GoldNumber(HistoryDealGetDouble(ticket,DEAL_VOLUME),2)+",\"price\":"+GoldNumber(HistoryDealGetDouble(ticket,DEAL_PRICE))+
           ",\"net\":"+GoldNumber(net,2)+",\"comment\":"+GoldJson(HistoryDealGetString(ticket,DEAL_COMMENT))+"}";
     }
   telemetry_deals=out+"]";
  }
string GoldTelemetryPositions()
  {
   string out="[";int count=0;
   for(int i=0;i<PositionsTotal() && count<100;i++)
     {
      ulong ticket=PositionGetTicket(i);if(ticket==0)continue;
      if(count++>0)out+=",";
      double net_peak=0,profit_floor=0;bool guard_armed=false;
      if(OwnSelected() && ExpertScalpMode)
        {
         ulong id=(ulong)PositionGetInteger(POSITION_IDENTIFIER);
         for(int j=0;j<ArraySize(managed);j++)if(managed[j].id==id)
           {
            net_peak=managed[j].net_peak;double noise=GoldProfitNoise(live_atr,last_ask-last_bid,DynamicSlip(),money_per_price);
            guard_armed=net_peak>=MathMax(MinimumProfitArmUSD,2*noise);
            if(guard_armed)profit_floor=GoldRetainedProfit(net_peak,ProfitGivebackFraction,noise);
            break;
           }
        }
      out+="{\"ticket\":"+GoldJson((string)ticket)+",\"symbol\":"+GoldJson(PositionGetString(POSITION_SYMBOL))+
           ",\"owned\":"+GoldBool(OwnSelected())+",\"side\":"+GoldJson(PositionGetInteger(POSITION_TYPE)==POSITION_TYPE_BUY?"BUY":"SELL")+
           ",\"volume\":"+GoldNumber(PositionGetDouble(POSITION_VOLUME),2)+",\"open\":"+GoldNumber(PositionGetDouble(POSITION_PRICE_OPEN))+
           ",\"current\":"+GoldNumber(PositionGetDouble(POSITION_PRICE_CURRENT))+",\"sl\":"+GoldNumber(PositionGetDouble(POSITION_SL))+
           ",\"tp\":"+GoldNumber(PositionGetDouble(POSITION_TP))+",\"pnl\":"+GoldNumber(PositionGetDouble(POSITION_PROFIT)+PositionGetDouble(POSITION_SWAP),2)+
           ",\"net_peak\":"+GoldNumber(net_peak,2)+",\"profit_floor\":"+GoldNumber(profit_floor,2)+",\"guard_armed\":"+GoldBool(guard_armed)+
           ",\"time\":"+GoldJson(TimeToString((datetime)PositionGetInteger(POSITION_TIME),TIME_DATE|TIME_SECONDS))+"}";
     }
   return out+"]";
  }
void GoldWriteTelemetry(const string text)
  {
   string path="GoldScalp\\dashboard_"+safety_key+(string)Magic+".json",temporary=path+".tmp";
   int file=FileOpen(temporary,FILE_WRITE|FILE_TXT|FILE_ANSI|FILE_COMMON,0,CP_UTF8);
   bool ok=file!=INVALID_HANDLE;
   if(ok){ok=FileWriteString(file,text)>0;FileFlush(file);FileClose(file);}
   if(ok)ok=FileMove(temporary,FILE_COMMON,path,FILE_COMMON|FILE_REWRITE);
   static ulong last_error_ms=0;ulong clock=GetTickCount64();
   if(!ok && (last_error_ms==0 || clock-last_error_ms>60000)){last_error_ms=clock;Print("Web dashboard export failed: ",GetLastError()," ",path);}
  }
string GoldEntryBlockers()
  {
   string items[];int n=0;
   if(!CanExecute()){ArrayResize(items,++n);items[n-1]="Demo order execution disabled";}
   if(paused || close_all_requested){ArrayResize(items,++n);items[n-1]="Entries paused / account liquidation";}
   if(Safety.Locked(ServerNow())){ArrayResize(items,++n);items[n-1]="Account safety lock";}
   if(!cached_session){ArrayResize(items,++n);items[n-1]=ExpertScalpMode?"Broker closed / rollover 21-23 UTC":"Outside "+(string)SessionStartUTC+":00-"+(string)SessionEndUTC+":00 UTC or broker market closed";}
   if(!NewsFresh()){ArrayResize(items,++n);items[n-1]="Native news feed missing or stale";}
   else if(cached_news_active){ArrayResize(items,++n);items[n-1]="High-impact USD news window";}
   if(Advisor1Mode==GOLD_ADVISOR_REQUIRED && !Advisor1.Fresh(GoldUTCNow(),_Symbol,Advisor1MaxAgeSeconds))
     {ArrayResize(items,++n);items[n-1]="Advisor 1 report missing or stale";}
   if(!volatility_ok){ArrayResize(items,++n);items[n-1]="ATR / relative-volume filter";}
   if(!relative_spread_ok || last_ask-last_bid>MaxSpreadPrice){ArrayResize(items,++n);items[n-1]="Spread filter / warm-up";}
   if(!ExpertScalpMode && Market.ready && !GoldAligned(Market.direction[0],Market.direction[1],Market.direction[2],Market.direction[3]))
     {ArrayResize(items,++n);items[n-1]="M1 / M5 / M15 / H1 not aligned";}
   string out="[";for(int i=0;i<n;i++){if(i>0)out+=",";out+=GoldJson(items[i]);}return out+"]";
  }
string GoldScalpTelemetryPolicy()
  {
   string out="{\"enabled\":"+GoldBool(ExpertScalpMode)+",\"score\":"+GoldNumber(scalp_score,1)+",\"threshold\":"+GoldNumber(scalp_threshold,1)+
      ",\"giveback_fraction\":"+GoldNumber(ProfitGivebackFraction,3)+",\"session\":"+GoldJson(GoldSessionName(session_bucket))+",\"sessions\":[";
   for(int i=0;i<4;i++)
     {if(i>0)out+=",";out+="{\"name\":"+GoldJson(GoldSessionName(i))+",\"closed\":"+(string)Stats.session_count[i]+",\"net\":"+GoldNumber(Stats.session_net[i],2)+
        ",\"adjustment\":"+GoldNumber(AdaptiveSessions?GoldSessionAdjustment(Stats.session_count[i],Stats.session_net[i],Stats.session_squares[i]):0,0)+"}";}
   return out+"]}";
  }
void GoldPublishTelemetry(const GoldDashboardData &d,const bool stopped=false)
  {
   if(!ExportWebDashboard || MQLInfoInteger(MQL_TESTER) || !owns_account_lock)return;
   if(stopped)
     {
      // Account changes can trigger OnDeinit after terminal account data changes.
      // Mark the original snapshot stopped instead of mixing two accounts.
      if(telemetry_last_payload=="")return;
      StringReplace(telemetry_last_payload,"\"stopped\":false","\"stopped\":true");
      GoldWriteTelemetry(telemetry_last_payload);return;
     }
   ulong clock=GetTickCount64();if(!stopped && telemetry_written_ms>0 && clock-telemetry_written_ms<950)return;
   telemetry_written_ms=clock;datetime now=ServerNow();
   if(d.status!=telemetry_previous_status){GoldTelemetryEvent("decision",d.status);telemetry_previous_status=d.status;}
   GoldTelemetryHistory(now);
   string text="{\"schema\":1,\"version\":\"3.00\",\"strategy\":\"Scalper Expert\",\"scalp\":"+GoldScalpTelemetryPolicy()+",\"instance\":"+GoldJson(safety_key+(string)Magic)+
      ",\"server_time\":"+GoldJson(TimeToString(now,TIME_DATE|TIME_SECONDS))+",\"symbol\":"+GoldJson(_Symbol)+
      ",\"server\":"+GoldJson(AccountInfoString(ACCOUNT_SERVER))+",\"login\":"+GoldJson((string)AccountInfoInteger(ACCOUNT_LOGIN))+
      ",\"currency\":"+GoldJson(AccountInfoString(ACCOUNT_CURRENCY))+",\"connected\":"+GoldBool(TerminalInfoInteger(TERMINAL_CONNECTED)!=0)+
      ",\"stopped\":"+GoldBool(stopped)+",\"mode\":"+GoldJson(d.mode)+",\"paused\":"+GoldBool(d.paused)+",\"locked\":"+GoldBool(d.locked)+
      ",\"status\":"+GoldJson(d.status)+",\"execution\":"+GoldJson(d.execution)+",\"learning\":"+GoldJson(d.learning)+
      ",\"account\":{\"balance\":"+GoldNumber(AccountInfoDouble(ACCOUNT_BALANCE),2)+",\"equity\":"+GoldNumber(AccountInfoDouble(ACCOUNT_EQUITY),2)+
      ",\"floating\":"+GoldNumber(AccountInfoDouble(ACCOUNT_PROFIT),2)+",\"margin_free\":"+GoldNumber(AccountInfoDouble(ACCOUNT_MARGIN_FREE),2)+
      ",\"position_count\":"+(string)PositionsTotal()+",\"pending_count\":"+(string)OrdersTotal()+"}"+
      ",\"kpi\":{\"win_rate\":"+GoldJson(d.win_rate)+",\"profit_factor\":"+GoldJson(d.profit_factor)+",\"day\":"+GoldJson(d.pnl_day)+
      ",\"week\":"+GoldJson(d.pnl_week)+",\"drawdown\":"+GoldJson(d.drawdown)+",\"ready\":"+GoldBool(Stats.ready)+"}"+
      ",\"market\":{\"bid\":"+GoldNumber(last_bid)+",\"ask\":"+GoldNumber(last_ask)+",\"spread\":"+GoldNumber(last_ask-last_bid)+
      ",\"spread_max\":"+GoldNumber(MaxSpreadPrice)+",\"spread_mean\":"+GoldNumber(spread_before)+",\"spread_state\":"+(string)d.spread_state+
      ",\"quote_age_ms\":"+(string)(last_quote_msc>0?MathMax(0,(long)now*1000-last_quote_msc):-1)+
      ",\"candle_seconds\":"+(string)d.candle_seconds+",\"atr\":"+GoldJson(d.atr)+",\"volume\":"+GoldJson(d.volume)+",\"flow\":"+GoldJson(d.flow)+"}"+
      ",\"filters\":{\"mtf\":"+GoldJson(d.mtf)+",\"session\":"+GoldJson(d.session)+",\"news\":"+GoldJson(d.news)+",\"advisor\":"+GoldJson(d.advisor)+"}"+
      ",\"risk\":{\"text\":"+GoldJson(d.risk)+",\"lot\":0.01,\"max_positions\":"+(string)MaxPositions+
      ",\"per_trade\":"+GoldNumber(RiskPerTradeUSD,2)+",\"aggregate\":"+GoldNumber(MaxAggregateRiskUSD,2)+
      ",\"daily_equity_percent\":"+GoldNumber(DailyEquityLossPercent,1)+",\"locked_until\":"+GoldJson(Safety.Locked(now)?TimeToString(Safety.locked_until,TIME_DATE|TIME_SECONDS):"")+"}"+
      ",\"blockers\":"+GoldEntryBlockers()+",\"positions\":"+GoldTelemetryPositions()+",\"candles\":"+GoldTelemetryCandles()+",\"deals\":"+telemetry_deals+
      ",\"history_ready\":"+GoldBool(telemetry_history_ok)+",\"events\":"+GoldTelemetryEvents()+"}";
   telemetry_last_payload=text;GoldWriteTelemetry(text);
  }
#endif
