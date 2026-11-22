#ifndef GOLD_SCALP_EXECUTION
#define GOLD_SCALP_EXECUTION
enum GOLD_REQUEST_STATE { GOLD_REQUEST_FREE=0,GOLD_REQUEST_WAIT,GOLD_REQUEST_RETRY,GOLD_REQUEST_UNKNOWN };
bool GoldRetryable(const uint code)
  {return code==TRADE_RETCODE_REQUOTE || code==TRADE_RETCODE_PRICE_CHANGED || code==TRADE_RETCODE_PRICE_OFF;}
bool GoldAmbiguous(const uint code)
  {return code==TRADE_RETCODE_TIMEOUT || code==TRADE_RETCODE_CONNECTION || code==TRADE_RETCODE_PLACED || code==0;}
struct GoldRequest
  {
   MqlTradeRequest request;
   GOLD_REQUEST_STATE state;
   uint request_id;
   ulong broker_order;
   int retries;
   ulong sent_ms,due_ms,created_ms;
   string reason;
  };
// One reservation per ticket and one for new entries; callbacks are correlated
// by request_id, never by arrival order. No Sleep, spin loop or blind refill.
class CGoldRequests
  {
private:
   ulong cooldown_ticket[32],cooldown_time[32];
   ENUM_TRADE_REQUEST_ACTIONS cooldown_action[32];
   int cooldown_next;
public:
   GoldRequest items[16];
   bool uncertain_entry;
   CGoldRequests(){uncertain_entry=false;cooldown_next=0;ArrayInitialize(cooldown_ticket,0);ArrayInitialize(cooldown_time,0);for(int i=0;i<16;i++)Clear(i);}
   void Clear(const int i){ZeroMemory(items[i]);items[i].state=GOLD_REQUEST_FREE;}
   bool EntryBlocked()
     {
      if(uncertain_entry)return true;
      for(int i=0;i<16;i++)if(items[i].state!=GOLD_REQUEST_FREE && items[i].request.action==TRADE_ACTION_DEAL && items[i].request.position==0)return true;
      return false;
     }
   int ForTicket(const ulong ticket)
     {for(int i=0;i<16;i++)if(items[i].state!=GOLD_REQUEST_FREE && (items[i].request.position==ticket || items[i].request.order==ticket))return i;return -1;}
   int Reserve(const MqlTradeRequest &request,const ulong now,const string reason)
     {
      bool entry=request.action==TRADE_ACTION_DEAL && request.position==0;
      if(entry && EntryBlocked())return -1;
      ulong ticket=request.position>0?request.position:request.order;
      if(ticket>0 && ForTicket(ticket)>=0)return -1;
      if(ticket>0)
        {
         for(int i=0;i<32;i++)if(cooldown_ticket[i]==ticket && cooldown_action[i]==request.action && now-cooldown_time[i]<500)return -1;
         cooldown_ticket[cooldown_next]=ticket;cooldown_action[cooldown_next]=request.action;cooldown_time[cooldown_next]=now;cooldown_next=(cooldown_next+1)%32;
        }
      for(int i=0;i<16;i++)if(items[i].state==GOLD_REQUEST_FREE)
        {Clear(i);items[i].request=request;items[i].state=GOLD_REQUEST_WAIT;items[i].created_ms=now;items[i].sent_ms=now;items[i].reason=reason;return i;}
      return -1;
     }
   int Find(const uint id)
     {if(id==0)return -1;for(int i=0;i<16;i++)if(items[i].state!=GOLD_REQUEST_FREE && items[i].request_id==id)return i;return -1;}
   void Response(const int i,const uint code,const ulong now)
     {
      if(i<0 || i>=16)return;
      if(code==TRADE_RETCODE_PLACED){items[i].state=GOLD_REQUEST_WAIT;return;}
      if(code==TRADE_RETCODE_DONE || code==TRADE_RETCODE_DONE_PARTIAL || code==TRADE_RETCODE_NO_CHANGES){Clear(i);return;}
      if(GoldRetryable(code) && items[i].retries<2 && now-items[i].created_ms<=3000)
        {items[i].retries++;items[i].due_ms=now+(ulong)(150*items[i].retries);items[i].state=GOLD_REQUEST_RETRY;return;}
      if(GoldAmbiguous(code))
        {items[i].state=GOLD_REQUEST_UNKNOWN;if(items[i].request.action==TRADE_ACTION_DEAL && items[i].request.position==0)uncertain_entry=true;return;}
      Clear(i);
     }
   void Expire(const ulong now)
     {
      for(int i=0;i<16;i++)
        {
         if(items[i].state==GOLD_REQUEST_WAIT && now-items[i].sent_ms>=8000)Response(i,TRADE_RETCODE_TIMEOUT,now);
         if(items[i].state==GOLD_REQUEST_RETRY && now-items[i].created_ms>3000)Clear(i);
        }
     }
   void CancelEntryRetries()
     {for(int i=0;i<16;i++)if(items[i].state==GOLD_REQUEST_RETRY && items[i].request.action==TRADE_ACTION_DEAL && items[i].request.position==0)Clear(i);}
  };
#endif
