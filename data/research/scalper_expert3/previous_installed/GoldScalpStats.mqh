#ifndef GOLD_SCALP_STATS
#define GOLD_SCALP_STATS
#include "GoldScalpSafety.mqh"
struct GoldOutcome
  {
   double pnl,volume_in,volume_out;
   long closed_msc;
   datetime opened;
  };
datetime GoldDayStart(const datetime when)
  {MqlDateTime d;TimeToStruct(when,d);d.hour=0;d.min=0;d.sec=0;return StructToTime(d);}
class CGoldStats
  {
private:
   ulong known_funding[];
   bool initialized;
   bool NewFunding(const ulong ticket)
     {
      for(int i=0;i<ArraySize(known_funding);i++)if(known_funding[i]==ticket)return false;
      int n=ArraySize(known_funding);ArrayResize(known_funding,n+1);known_funding[n]=ticket;return true;
     }
public:
   bool ready;
   datetime refreshed,last_entry,last_exit,last_loss;
   double net24,day_net,week_net,gross_profit,gross_loss,reference,capital,funding_delta;
   int closed,wins,losses,breakeven,entries_hour,loss_streak;
   CGoldStats(){initialized=false;ready=false;refreshed=0;last_entry=0;last_exit=0;last_loss=0;net24=0;day_net=0;week_net=0;gross_profit=0;gross_loss=0;reference=0;capital=0;funding_delta=0;closed=0;wins=0;losses=0;breakeven=0;entries_hour=0;loss_streak=0;}
   bool Refresh(const string symbol,const ulong magic,const datetime now,const int days)
     {
      ready=false;datetime day=GoldDayStart(now);MqlDateTime d;TimeToStruct(now,d);
      datetime week=day-((d.day_of_week+6)%7)*86400,cutoff=now-days*86400;
      if(!HistorySelect(cutoff-86400,now))return false;
      int count=HistoryDealsTotal();if(count>100000)return false; // bounded work; fail closed on unexpected history volume
      ulong ids[];ArrayResize(ids,count);int n=0;
      for(int i=0;i<count;i++)
        {
         ulong deal=HistoryDealGetTicket(i);
         if(HistoryDealGetString(deal,DEAL_SYMBOL)==symbol && (ulong)HistoryDealGetInteger(deal,DEAL_MAGIC)==magic && HistoryDealGetInteger(deal,DEAL_ENTRY)==DEAL_ENTRY_IN)
           {ulong id=(ulong)HistoryDealGetInteger(deal,DEAL_POSITION_ID);if(id>0)ids[n++]=id;}
        }
      ArrayResize(ids,n);ArraySort(ids);int unique=0;
      for(int i=0;i<n;i++)if(i==0 || ids[i]!=ids[i-1])ids[unique++]=ids[i];
      ArrayResize(ids,unique);GoldOutcome outcomes[];ArrayResize(outcomes,unique);
      for(int i=0;i<unique;i++)ZeroMemory(outcomes[i]);
      net24=0;day_net=0;week_net=0;gross_profit=0;gross_loss=0;closed=0;wins=0;losses=0;breakeven=0;entries_hour=0;loss_streak=0;last_loss=0;funding_delta=0;
      double account_changes=0,funding=0;
      for(int i=0;i<count;i++)
        {
         ulong deal=HistoryDealGetTicket(i);long type=HistoryDealGetInteger(deal,DEAL_TYPE);
         datetime when=(datetime)HistoryDealGetInteger(deal,DEAL_TIME);
         double value=HistoryDealGetDouble(deal,DEAL_PROFIT)+HistoryDealGetDouble(deal,DEAL_COMMISSION)+HistoryDealGetDouble(deal,DEAL_SWAP)+HistoryDealGetDouble(deal,DEAL_FEE);
         if(when>=day){account_changes+=value;if(GoldIsFunding(type))funding+=value;}
         if(GoldIsFunding(type) && NewFunding(deal) && initialized)funding_delta+=value;
         if(type!=DEAL_TYPE_BUY && type!=DEAL_TYPE_SELL)continue;
         ulong id=(ulong)HistoryDealGetInteger(deal,DEAL_POSITION_ID);
         int slot=unique>0?ArrayBsearch(ids,id):-1;if(slot<0 || ids[slot]!=id)continue;
         if(when>=now-86400)net24+=value;if(when>=day)day_net+=value;if(when>=week)week_net+=value;
         outcomes[slot].pnl+=value;long entry=HistoryDealGetInteger(deal,DEAL_ENTRY);
         double volume=HistoryDealGetDouble(deal,DEAL_VOLUME);
         if(entry==DEAL_ENTRY_IN)
           {
            if(outcomes[slot].volume_in==0 && when>=now-3600)entries_hour++;
            outcomes[slot].volume_in+=volume;last_entry=MathMax(last_entry,when);
            if(outcomes[slot].opened==0 || when<outcomes[slot].opened)outcomes[slot].opened=when;
           }
         else if(entry==DEAL_ENTRY_OUT || entry==DEAL_ENTRY_OUT_BY)
           {outcomes[slot].volume_out+=volume;outcomes[slot].closed_msc=MathMax(outcomes[slot].closed_msc,HistoryDealGetInteger(deal,DEAL_TIME_MSC));last_exit=MathMax(last_exit,when);}
        }
      long sorted_closes[];ArrayResize(sorted_closes,unique);int completed=0;
      for(int i=0;i<unique;i++)
        {
         // A partial fill is not a closed trade. Missing original entry => exclude, never invent cost basis.
         if(outcomes[i].volume_in<=0 || outcomes[i].volume_out<outcomes[i].volume_in-1e-8 || outcomes[i].closed_msc/1000<cutoff)continue;
         bool open=false;for(int p=PositionsTotal()-1;p>=0;p--)if(PositionGetTicket(p)>0 && (ulong)PositionGetInteger(POSITION_IDENTIFIER)==ids[i]){open=true;break;}
         if(open)continue;
         closed++;double profit=outcomes[i].pnl;
         if(profit>1e-8){wins++;gross_profit+=profit;}else if(profit<-1e-8){losses++;gross_loss-=profit;}else breakeven++;
         sorted_closes[completed++]=outcomes[i].closed_msc*100000+i;
        }
      ArrayResize(sorted_closes,completed);ArraySort(sorted_closes);
      for(int i=completed-1;i>=0;i--)
        {
         int slot=(int)(sorted_closes[i]%100000);double profit=outcomes[slot].pnl;
         if(profit>1e-8)break;
         if(profit<-1e-8){loss_streak++;last_loss=MathMax(last_loss,(datetime)(outcomes[slot].closed_msc/1000));}
        }
      capital=AccountInfoDouble(ACCOUNT_BALANCE)+AccountInfoDouble(ACCOUNT_CREDIT);
      reference=GoldDailyReference(capital,account_changes,funding);
      refreshed=now;ready=true;initialized=true;return true;
     }
   double WinRate(){return closed>0?100.*wins/closed:0;}
   string ProfitFactor(){return closed==0?"--":gross_loss>1e-8?DoubleToString(gross_profit/gross_loss,2):gross_profit>0?"sans perte":"--";}
  };
#endif
