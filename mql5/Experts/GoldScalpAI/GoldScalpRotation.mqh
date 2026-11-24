#ifndef GOLD_SCALP_ROTATION
#define GOLD_SCALP_ROTATION
#include "GoldScalpMath.mqh"
// Re-arming can shorten only after a broker-confirmed exit and flat account.
class CGoldRotation
  {
public:
   ulong ticket,confirmed_ms;
   long confirmed_quote;
   int exited_side;
   bool confirmed;
   CGoldRotation(){Clear();}
   void Clear(){ticket=0;confirmed_ms=0;confirmed_quote=0;exited_side=0;confirmed=false;}
   void Intent(const ulong target,const int side)
     {ticket=target;exited_side=side;confirmed=false;confirmed_ms=0;confirmed_quote=0;}
   void Confirm(const ulong target,const ulong now,const long quote)
     {if(target==ticket && ticket>0){confirmed=true;confirmed_ms=now;confirmed_quote=quote;}}
   bool Ready(const int side,const ulong now,const long quote,const int rearm_ms,
              const bool flat,const bool pending,const bool reconciled,const bool strong,const bool continuation=false)
     {
      return confirmed && side!=0 && (side==-exited_side || (continuation && side==exited_side)) && flat && !pending && reconciled && strong &&
             now>=confirmed_ms && now-confirmed_ms>=(ulong)rearm_ms && now-confirmed_ms<=10000 && quote>confirmed_quote;
     }
  };
double GoldAccelerationBonus(const int side,const double fast_velocity,const double slow_velocity,const double spread)
  {
   if(side==0 || spread<=0)return 0;
   return 4*GoldClamp(side*(fast_velocity-slow_velocity)/MathMax(spread,.02),-1,1);
  }
bool GoldEarlyProfitExit(const double net,const double peak,const double noise,const double pressure,const double efficiency,const long adverse_ms)
  {
   // Before the percentage trail arms: bank a net winner after a persistent
   // opposing move and a retreat larger than quote/execution noise.
   return net>noise && peak>=2*noise && peak-net>=noise && pressure<=-.5 && efficiency>=.55 && adverse_ms>=500;
  }
bool GoldMicroTakeOut(const double net,const double peak,const double noise,const double arm,
                     const double pressure,const double efficiency,const double fast_velocity,const double slow_velocity,const long adverse_ms)
  {
   return peak>=MathMax(arm,2*noise) && net>noise && peak-net>=noise && pressure<=-.5 && efficiency>=.55 &&
          fast_velocity<.5*MathMax(0,slow_velocity) && adverse_ms>=750;
  }
#endif
