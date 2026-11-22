#ifndef GOLD_SCALP_ORDERS
#define GOLD_SCALP_ORDERS
// Included after EA state declarations. No waits or retry loops in this lane.
ENUM_ORDER_TYPE_FILLING GoldFillFor(const string symbol)
  {
   long mask=SymbolInfoInteger(symbol,SYMBOL_FILLING_MODE);
   if((mask&SYMBOL_FILLING_FOK)!=0)return ORDER_FILLING_FOK;
   if((mask&SYMBOL_FILLING_IOC)!=0)return ORDER_FILLING_IOC;
   long execution=SymbolInfoInteger(symbol,SYMBOL_TRADE_EXEMODE);
   if(execution==SYMBOL_TRADE_EXECUTION_INSTANT || execution==SYMBOL_TRADE_EXECUTION_REQUEST)return ORDER_FILLING_FOK;
   return ORDER_FILLING_RETURN;
  }
void PersistAmbiguity()
  {if(Requests.uncertain_entry && !ambiguity_persisted && !MQLInfoInteger(MQL_TESTER)){GlobalVariableSet(prefix+"AMBIGUOUS",1);GlobalVariablesFlush();ambiguity_persisted=true;}}
bool SendReserved(const int slot)
  {
   if(slot<0 || !CanExecute())return false;
   MqlTradeRequest req=Requests.items[slot].request;MqlTradeCheckResult check={};MqlTradeResult result={};
   bool entry=req.action==TRADE_ACTION_DEAL && req.position==0;
   if(entry && (paused || Safety.Locked(ServerNow()) || close_all_requested || !GoldPositionCapacity(PositionsTotal(),OrdersTotal(),MaxPositions)))
     {Requests.Clear(slot);return false;}
   if(!OrderCheck(req,check))
     {rejections++;last_execution="Check refuse "+(string)check.retcode;Print(last_execution," ",check.comment);Requests.Clear(slot);last_submit=TimeCurrent();return false;}
   Requests.items[slot].state=GOLD_REQUEST_WAIT;Requests.items[slot].sent_ms=ExecutionClock();
   attempts++;last_submit=TimeCurrent();bool sent=AsyncExecution?OrderSendAsync(req,result):OrderSend(req,result);
   Requests.items[slot].request_id=result.request_id;
   Requests.items[slot].broker_order=result.order;
   last_execution=(AsyncExecution?"Envoi async ":"Envoi ")+(string)result.retcode;
   if(sent && AsyncExecution && result.retcode==TRADE_RETCODE_PLACED)return true;
   if(result.retcode==TRADE_RETCODE_DONE || result.retcode==TRADE_RETCODE_DONE_PARTIAL)
     {
      filled++;if(entry)last_entry=TimeCurrent();history_dirty=true;
      if(req.action==TRADE_ACTION_DEAL)last_fill_slippage=GoldSignedFillSlippage(req.price,result.price,req.type==ORDER_TYPE_BUY,fill_slippage_valid);
     }
   else {rejections++;Print("ORDER_RESULT ",result.retcode," ",result.comment);}
   Requests.Response(slot,result.retcode,ExecutionClock());PersistAmbiguity();return sent;
  }
bool Submit(MqlTradeRequest &request,const string why)
  {
   if(!CanExecute())return false;
   int slot=Requests.Reserve(request,ExecutionClock(),why);if(slot<0)return false;
   GoldTelemetryEvent("request",why+" | "+request.symbol+" | position "+(string)request.position);
   return SendReserved(slot);
  }
bool BuildClose(const ulong ticket,const bool account_wide,MqlTradeRequest &request)
  {
   if(!PositionSelectByTicket(ticket) || (!account_wide && !OwnSelected()))return false;
   string symbol=PositionGetString(POSITION_SYMBOL);MqlTick q;
   if(!SymbolInfoTick(symbol,q) || !ValidQuote(q))return false;
   bool buy=PositionGetInteger(POSITION_TYPE)==POSITION_TYPE_BUY;
   ZeroMemory(request);request.action=TRADE_ACTION_DEAL;request.position=ticket;request.symbol=symbol;
   request.magic=Magic;request.volume=PositionGetDouble(POSITION_VOLUME);
   request.type=buy?ORDER_TYPE_SELL:ORDER_TYPE_BUY;request.price=buy?q.bid:q.ask;
   double point=SymbolInfoDouble(symbol,SYMBOL_POINT);if(point<=0)return false;
   double slip=symbol==_Symbol?DynamicSlip():MathMin(100*point,MathMax(point,(q.ask-q.bid)*.5));
   request.deviation=(ulong)MathCeil(slip/point);request.type_filling=GoldFillFor(symbol);request.comment="GoldSafetyExit";return true;
  }
bool ClosePosition(const ulong ticket,const string why)
  {
   if(Requests.ForTicket(ticket)>=0)return false;
   MqlTradeRequest request={};if(!BuildClose(ticket,false,request))return false;
   bool rotate=ExpertScalpMode && UseRapidRotation && StringFind(why,"SCALP:")==0 && StringFind(why,"cut exposure")<0;
   // Set intent before sending: a synchronous completion can be followed by a deal callback.
   if(rotate)Rotation.Intent(ticket,request.type==ORDER_TYPE_SELL?1:-1);
   bool sent=Submit(request,why);if(!sent && rotate)Rotation.Clear();return sent;
  }
void CloseOwned(const string why)
  {for(int i=PositionsTotal()-1;i>=0;i--){ulong ticket=PositionGetTicket(i);if(ticket>0 && OwnSelected())ClosePosition(ticket,why);}}
void DrainOwnedForSafety()
  {
   Requests.CancelEntryRetries();if(!CanExecute())return;
   int sent=0;
   for(int i=OrdersTotal()-1;i>=0 && sent<4;i--)
     {
      ulong ticket=OrderGetTicket(i);
      if(ticket==0 || !GoldSafetyOwnsExposure(OrderGetString(ORDER_SYMBOL),_Symbol,(ulong)OrderGetInteger(ORDER_MAGIC),Magic) || Requests.ForTicket(ticket)>=0)continue;
      MqlTradeRequest req={};req.action=TRADE_ACTION_REMOVE;req.order=ticket;req.symbol=_Symbol;req.magic=Magic;
      if(Submit(req,"Annulation urgence EA XAUUSD"))sent++;
     }
   for(int i=PositionsTotal()-1;i>=0 && sent<8;i--)
     {
      ulong ticket=PositionGetTicket(i);if(ticket==0 || !OwnSelected() || Requests.ForTicket(ticket)>=0)continue;
      MqlTradeRequest req={};if(BuildClose(ticket,false,req) && Submit(req,"Fermeture urgence EA XAUUSD"))sent++;
     }
  }
void DrainAccountForCloseAll()
  {
   Requests.CancelEntryRetries();if(!CanExecute())return;
   // Pending orders are removed first. Up to sixteen in-flight requests bound memory/work.
   int sent=0;
   for(int i=OrdersTotal()-1;i>=0 && sent<4;i--)
     {
      ulong ticket=OrderGetTicket(i);if(ticket==0 || Requests.ForTicket(ticket)>=0)continue;
      MqlTradeRequest req={};req.action=TRADE_ACTION_REMOVE;req.order=ticket;req.magic=Magic;
      if(Submit(req,"Annulation urgence compte"))sent++;
     }
   for(int i=PositionsTotal()-1;i>=0 && sent<8;i--)
     {
      ulong ticket=PositionGetTicket(i);if(ticket==0 || Requests.ForTicket(ticket)>=0)continue;
      MqlTradeRequest req={};if(BuildClose(ticket,true,req) && Submit(req,"Fermeture urgence compte"))sent++;
     }
   static datetime flat_since=0;
   if(PositionsTotal()==0 && OrdersTotal()==0 && !Requests.EntryBlocked() && ExposureReady())
     {
      if(flat_since==0)flat_since=TimeCurrent();
      if(close_all_requested && TimeCurrent()-flat_since>=5)
        {
         close_all_requested=false;SaveControls();
         if(StringFind(control_result,"accepted: closing")==0)
            control_result="completed: account flat; entries remain paused";
        }
     }
   else flat_since=0;
  }
void ServiceRequests()
  {
   ulong now=ExecutionClock();Requests.Expire(now);PersistAmbiguity();
   for(int i=0;i<16;i++)
     {
      GoldRequest item=Requests.items[i];if(item.state==GOLD_REQUEST_FREE)continue;
      bool entry=item.request.action==TRADE_ACTION_DEAL && item.request.position==0;
      if(item.request.action==TRADE_ACTION_DEAL && item.broker_order>0 && HistoryOrderSelect(item.broker_order))
        {
         long state=HistoryOrderGetInteger(item.broker_order,ORDER_STATE);
         if(state==ORDER_STATE_FILLED || state==ORDER_STATE_CANCELED || state==ORDER_STATE_REJECTED || state==ORDER_STATE_EXPIRED)
           {
            if(entry)
              {
               if(state==ORDER_STATE_FILLED)last_entry=TimeCurrent();Requests.uncertain_entry=false;
               ambiguity_persisted=false;if(!MQLInfoInteger(MQL_TESTER))GlobalVariableDel(prefix+"AMBIGUOUS");
              }
            Requests.Clear(i);history_dirty=true;continue;
           }
        }
      if(item.state==GOLD_REQUEST_UNKNOWN)
        {
         // An uncertain entry is never repeated. Ticket-specific closes are only
         // unlocked once the terminal confirms that the target no longer exists.
         if(!entry && ((item.request.position>0 && !PositionSelectByTicket(item.request.position)) ||
            (item.request.order>0 && !OrderSelect(item.request.order))))Requests.Clear(i);
         continue;
        }
      if(item.state!=GOLD_REQUEST_RETRY || now<item.due_ms)continue;
      MqlTradeRequest fresh=item.request;
      if(entry)
        {
         MqlTick q;int side=fresh.type==ORDER_TYPE_BUY?1:-1;string reason;
         if(!SymbolInfoTick(_Symbol,q) || !EntryEnvironment(q) || !SignalAllows(side,q,reason) || !EntryRisk(side,q,fresh.sl,fresh.tp,reason))
           {Requests.Clear(i);continue;}
         fresh.price=side>0?q.ask:q.bid;fresh.deviation=(ulong)MathCeil(DynamicSlip()/SymbolInfoDouble(_Symbol,SYMBOL_POINT));
        }
      else if(fresh.action==TRADE_ACTION_DEAL)
        {if(!BuildClose(fresh.position,close_all_requested,fresh)){Requests.Clear(i);continue;}}
      else if(fresh.action==TRADE_ACTION_SLTP)
        {Requests.Clear(i);continue;} // recalculate trailing on next tick, never resend obsolete levels
      else if(fresh.action==TRADE_ACTION_REMOVE && !OrderSelect(fresh.order)){Requests.Clear(i);continue;}
      Requests.items[i].request=fresh;retry_count++;SendReserved(i);
     }
  }
#endif
