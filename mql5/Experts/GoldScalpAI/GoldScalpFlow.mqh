#ifndef GOLD_SCALP_FLOW
#define GOLD_SCALP_FLOW
#include "GoldScalpMath.mqh"
#define GOLD_FLOW_CAPACITY 1200
struct GoldFlowRead
  {
   bool ready;
   long age_milliseconds;
   double pressure,efficiency,move,spread,seconds,velocity,observations_per_second;
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
      r.age_milliseconds=-1;
      if(total<=0)return r;
      int last=(next-1+GOLD_FLOW_CAPACITY)%GOLD_FLOW_CAPACITY;
      if(now_msc<stamp[last])return r;
      r.age_milliseconds=now_msc-stamp[last];
      if(r.age_milliseconds>2000)return r;
      if(total<4){r.count=total;return r;}
      int first=last;
      double path=0,maxspread=0,previous=(bid[last]+ask[last])*0.5;
      for(int n=0;n<total;n++)
        {
         int i=(last-n+GOLD_FLOW_CAPACITY)%GOLD_FLOW_CAPACITY;
         long age=stamp[last]-stamp[i];
         // Include one point bracketing the window edge on irregular broker ticks.
         // Do not stretch a window across a multi-second quote outage.
         if(age>seconds*1000+MathMin(1000,seconds*250))break;
         double mid=(bid[i]+ask[i])*0.5;
         if(n>0)path+=MathAbs(previous-mid);
         previous=mid;first=i;r.count++;
         maxspread=MathMax(maxspread,ask[i]-bid[i]);
         if(age>=seconds*1000)break;
        }
      if(r.count<=0)return r;
      r.spread=maxspread;r.seconds=(stamp[last]-stamp[first])/1000.;
      double b=bid[last]-bid[first],a=ask[last]-ask[first];
      double both=(b>0 && a>0)?MathMin(b,a):(b<0 && a<0)?MathMax(b,a):0;
      r.move=((bid[last]+ask[last])-(bid[first]+ask[first]))*.5;
      if(r.seconds>0){r.velocity=r.move/r.seconds;r.observations_per_second=(r.count-1)/r.seconds;}
      r.efficiency=path>0?MathAbs(r.move)/path:0;
      r.pressure=GoldClamp(both/MathMax(2*maxspread,0.02),-1,1);
      if(r.count<(seconds<=2?3:4) || stamp[last]-stamp[first]<seconds*800)return r;
      r.ready=true;
      if(r.efficiency>=.45 && MathAbs(r.pressure)>=.35)r.direction=r.pressure>0?1:-1;
      return r;
     }
  };
#endif
