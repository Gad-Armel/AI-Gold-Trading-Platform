#ifndef GOLD_SCALP_SESSION
#define GOLD_SCALP_SESSION
bool GoldBuildBrokerSessionState(const datetime now,GoldBrokerSessionSnapshot &state)
  {
   ZeroMemory(state);
   if(now<=0)return false;
   MqlDateTime today;TimeToStruct(now,today);
   MqlDateTime midnight=today;midnight.hour=0;midnight.min=0;midnight.sec=0;
   datetime day_start=StructToTime(midnight);
   datetime opens[100],closes[100];int count=0;
   for(int day_offset=-1;day_offset<=8;day_offset++)
     {
      int weekday=(today.day_of_week+day_offset+14)%7;
      ENUM_DAY_OF_WEEK day=(ENUM_DAY_OF_WEEK)weekday;
      datetime base=(datetime)((long)day_start+(long)day_offset*86400);
      for(uint session=0;session<10;session++)
        {
         datetime from,to;
         if(!SymbolInfoSessionTrade(_Symbol,day,session,from,to))break;
         int first=(int)((long)from%86400),last=(int)((long)to%86400);
         if(first<0)first+=86400;if(last<0)last+=86400;
         datetime opening=base+first,closing=base+last;
         if(first==last){opening=base;closing=base+86400;}
         else if(last<first)closing+=86400;
         if(closing<=opening || count>=100)continue;
         opens[count]=opening;closes[count]=closing;count++;
        }
     }
   if(count==0)return false;
   for(int i=1;i<count;i++)
     {
      datetime key_open=opens[i],key_close=closes[i];int j=i-1;
      while(j>=0 && opens[j]>key_open)
        {opens[j+1]=opens[j];closes[j+1]=closes[j];j--;}
      opens[j+1]=key_open;closes[j+1]=key_close;
     }
   datetime merged_opens[100],merged_closes[100];int merged=0;
   for(int i=0;i<count;i++)
     {
      if(merged>0 && opens[i]<=merged_closes[merged-1])
        {if(closes[i]>merged_closes[merged-1])merged_closes[merged-1]=closes[i];}
      else {merged_opens[merged]=opens[i];merged_closes[merged]=closes[i];merged++;}
     }
   state.schedule_available=true;
   for(int i=0;i<merged;i++)
     {
      if(now>=merged_opens[i] && now<merged_closes[i])
        {
         if(!state.scheduled_open || merged_closes[i]<state.active_close)
           {state.scheduled_open=true;state.active_open=merged_opens[i];state.active_close=merged_closes[i];}
        }
      if(merged_opens[i]>now && (state.next_open==0 || merged_opens[i]<state.next_open))
        {state.next_open=merged_opens[i];state.next_close=merged_closes[i];}
     }
   if(state.scheduled_open)state.seconds_to_close=(int)(state.active_close-now);
   else if(state.next_close>now)state.seconds_to_close=(int)(state.next_close-now);
   else state.seconds_to_close=-1;
   state.preclose_active=GoldSessionCloseDue(state.scheduled_open,state.active_close,now);
   return true;
  }
void GoldRefreshBrokerSessionState(const datetime now)
  {
   if(!GoldBuildBrokerSessionState(now,BrokerSessionState))
     {
      session_close_status="Broker trading schedule unavailable; pre-close cannot be planned";
      return;
     }
   BrokerSessionState.preclose_active=GoldSessionCloseDue(BrokerSessionState.scheduled_open,BrokerSessionState.active_close,now);
  }
int GoldCountAttachedXauusdPositions()
  {
   int count=0;
   for(int i=PositionsTotal()-1;i>=0;i--)
     {
      if(PositionGetTicket(i)==0)continue;
      if(GoldSessionPositionTarget(PositionGetString(POSITION_SYMBOL),_Symbol))count++;
     }
   return count;
  }
bool GoldHasOverdueAttachedXauusdPosition()
  {
   if(!BrokerSessionState.scheduled_open || BrokerSessionState.active_open<=0)return false;
   for(int i=PositionsTotal()-1;i>=0;i--)
     {
      if(PositionGetTicket(i)==0 || !GoldSessionPositionTarget(PositionGetString(POSITION_SYMBOL),_Symbol))continue;
      datetime opened=(datetime)PositionGetInteger(POSITION_TIME);
      if(opened<=0 || opened<BrokerSessionState.active_open)return true;
     }
   return false;
  }
void GoldCloseAttachedXauusdPositions(const string reason)
  {
   int attempted=0,unbuildable=0,pending=0;
   for(int i=PositionsTotal()-1;i>=0;i--)
     {
      ulong ticket=PositionGetTicket(i);
      if(ticket==0 || !GoldSessionPositionTarget(PositionGetString(POSITION_SYMBOL),_Symbol))continue;
      if(Requests.ForTicket(ticket)>=0){pending++;continue;}
      MqlTradeRequest request={};
      if(!BuildClose(ticket,true,request)){unbuildable++;continue;}
      if(Submit(request,reason))attempted++;
      else unbuildable++;
     }
   session_close_remaining=GoldCountAttachedXauusdPositions();
   if(session_close_remaining==0)
      session_close_status="All attached-symbol XAUUSD positions are flat";
   else if(attempted>0)
      session_close_status="Close requests sent; awaiting fills ("+(string)session_close_remaining+" remain)";
   else if(pending>0)
      session_close_status="Waiting for close request acknowledgement ("+(string)session_close_remaining+" remain)";
   else if(unbuildable>0)
      session_close_status="Close unavailable: quote or MT5 trade permission ("+(string)session_close_remaining+" remain)";
   else
      session_close_status="Close not confirmed ("+(string)session_close_remaining+" remain)";
  }
void GoldServiceScheduledSessionClose(const datetime now)
  {
   session_close_remaining=GoldCountAttachedXauusdPositions();
   if(!BrokerSessionState.schedule_available)
     {
      session_close_status="Broker trading schedule unavailable; pre-close cannot be planned";
      return;
     }
   if(!BrokerSessionState.scheduled_open)
     {
      session_close_status=session_close_remaining>0
         ?"XAUUSD position remains during scheduled closure; retry at next open"
         :"Scheduled market closed";
      return;
     }
   bool preclose=GoldSessionCloseDue(true,BrokerSessionState.active_close,now);
   bool overdue=GoldHasOverdueAttachedXauusdPosition();
   if(!preclose && !overdue)
     {
      session_close_status=session_close_remaining>0
         ?"XAUUSD positions open; scheduled close is monitored"
         :"No XAUUSD position requires a session close";
      return;
     }
   if(session_close_remaining==0)
     {
      session_close_status=overdue
         ?"Overdue XAUUSD session exposure is flat"
         :"XAUUSD positions are flat before scheduled close";
      return;
     }
   if(!CanExecute())
     {
      session_close_status="Pre-close due but MT5 demo execution or trade permission is disabled";
      return;
     }
   GoldCloseAttachedXauusdPositions(overdue
      ?"Overdue XAUUSD exposure; flattening after broker reopen"
      :"Broker session closes within five minutes; flattening XAUUSD");
  }
#endif
