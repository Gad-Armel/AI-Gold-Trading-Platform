#ifndef GOLD_SCALP_ENTRY
#define GOLD_SCALP_ENTRY
#include "GoldScalpFlow.mqh"
// Causal confirmation with a bounded neutral gap. No grace for a reversal,
// execution block, stale quote, direction change, or a currently weak entry.
class CGoldEntryConfirmation
  {
public:
   long started,last_seen,last_good;
   int side,qualified;
   bool weakened;
   CGoldEntryConfirmation(){Reset();}
   void Reset(){started=0;last_seen=0;last_good=0;side=0;qualified=0;weakened=false;}
   bool Observe(const long now,const int direction,const bool candidate,const bool coherent,const int required_ms,const int grace_ms,const int minimum_quotes=4)
     {
      if(now<=0 || direction==0 || !coherent){Reset();return false;}
      if(last_seen>0 && (now<last_seen || now-last_seen>1500 || direction!=side))Reset();
      if(now==last_seen)return false; // one observation per sampled quote
      last_seen=now;
      if(!candidate)
        {
         weakened=true;
         if(last_good==0 || now-last_good>grace_ms)Reset();
         return false;
        }
      if(last_good==0 || (weakened && now-last_good>grace_ms)){started=now;qualified=0;}
      weakened=false;side=direction;last_good=now;qualified++;
      return qualified>=MathMax(2,minimum_quotes) && now-started>=required_ms;
     }
  };
bool GoldCounterflowTrap(const int side,const GoldFlowRead &slow,const GoldFlowRead &context,const double spread,const double volatility)
  {
   return side!=0 && slow.ready && context.ready && context.direction==-side && context.efficiency>=.45 &&
      side*context.move<=-MathMax(3*spread,.30*volatility) && side*slow.pressure<.5;
  }
double GoldRollingRiskRemaining(const double limit,const double realized)
  {return MathMax(0,MathMin(50.,limit)+realized);}
bool GoldRiskReservationFits(const double planned,const double reserved,const double remaining)
  {return MathIsValidNumber(planned) && MathIsValidNumber(reserved) && MathIsValidNumber(remaining) && planned>0 && reserved>=0 && remaining>0 && planned+reserved<=remaining+1e-8;}
#endif
