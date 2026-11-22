#ifndef GOLD_SCALP_FLOW
#define GOLD_SCALP_FLOW
#include "GoldScalpMath.mqh"
#define GOLD_FLOW_CAPACITY 1200
struct GoldFlowRead
  {
   bool ready;
   double pressure,efficiency,move,spread;
   int direction,count;
  };
class CGoldFlow
  {
private:
   long stamp[GOLD_FLOW_CAPACITY];
   double bid[GOLD_FLOW_CAPACITY],ask[GOLD_FLOW_CAPACITY];
   int next,total;
public:
   void Reset(){next=0;total=0;}
   CGoldFlow(){Reset();}
   bool Add(const MqlTick &tick)
     {
      if(tick.time_msc<=0 || tick.bid<=0 || tick.ask<tick.bid || !MathIsValidNumber(tick.bid) || !MathIsValidNumber(tick.ask))return false;
      if(total>0)
        {
         int prior=(next-1+GOLD_FLOW_CAPACITY)%GOLD_FLOW_CAPACITY;
         long delta=tick.time_msc-stamp[prior];
         if(delta<=0)return false;
         if(delta>8000)Reset();
         else if(delta<100)return false; // bounded ten observations/sec, no tick-count illusion
        }
      stamp[next]=tick.time_msc;bid[next]=tick.bid;ask[next]=tick.ask;
      next=(next+1)%GOLD_FLOW_CAPACITY;total=MathMin(total+1,GOLD_FLOW_CAPACITY);
      return true;
     }
   GoldFlowRead Read(const long now_msc,const int seconds)
     {
      GoldFlowRead r={};
      if(total<4)return r;
      int last=(next-1+GOLD_FLOW_CAPACITY)%GOLD_FLOW_CAPACITY;
      if(now_msc<stamp[last] || now_msc-stamp[last]>2000)return r;
      int first=last;
      double path=0,maxspread=0,previous=(bid[last]+ask[last])*0.5;
      for(int n=0;n<total;n++)
        {
         int i=(last-n+GOLD_FLOW_CAPACITY)%GOLD_FLOW_CAPACITY;
         if(stamp[last]-stamp[i]>seconds*1000)break;
         double mid=(bid[i]+ask[i])*0.5;
         if(n>0)path+=MathAbs(previous-mid);
         previous=mid;first=i;r.count++;
         maxspread=MathMax(maxspread,ask[i]-bid[i]);
        }
      if(r.count<4 || stamp[last]-stamp[first]<seconds*800)return r;
      r.ready=true;r.spread=maxspread;
      double b=bid[last]-bid[first],a=ask[last]-ask[first];
      double both=(b>0 && a>0)?MathMin(b,a):(b<0 && a<0)?MathMax(b,a):0;
      r.move=((bid[last]+ask[last])-(bid[first]+ask[first]))*.5;
      r.efficiency=path>0?MathAbs(r.move)/path:0;
      r.pressure=GoldClamp(both/MathMax(2*maxspread,0.02),-1,1);
      if(r.efficiency>=.45 && MathAbs(r.pressure)>=.35)r.direction=r.pressure>0?1:-1;
      return r;
     }
  };
#endif
