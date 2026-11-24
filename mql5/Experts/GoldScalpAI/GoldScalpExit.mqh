#ifndef GOLD_SCALP_EXIT
#define GOLD_SCALP_EXIT
enum GOLD_EXIT { GOLD_HOLD=0,GOLD_TAKE_REVERSAL,GOLD_EXIT_REVERSAL,GOLD_GIVEBACK,GOLD_BANK,GOLD_STAGNATION };
struct GoldExitContext
  {
   double move,peak,risk,spread,cost_buffer,profit,commission,fast_pressure;
   bool opposing,fast_ready;
   int adverse_seconds,held_seconds;
  };
GOLD_EXIT GoldChooseExit(const GoldExitContext &c,const double arm,const double giveback,const double breakeven,
                        const int reversal_seconds,const int max_hold_seconds)
  {
   if(c.opposing && c.move>=MathMax(2*c.spread,c.cost_buffer) && c.profit>c.commission)return GOLD_TAKE_REVERSAL;
   if(c.opposing && c.adverse_seconds>=reversal_seconds)return GOLD_EXIT_REVERSAL;
   if(c.peak>=arm*c.risk && c.peak-c.move>=MathMax(giveback*c.risk,2.5*c.spread) && c.fast_ready && c.fast_pressure<0)return GOLD_GIVEBACK;
   if(c.peak>=breakeven*c.risk && c.peak>c.cost_buffer && c.move<=c.cost_buffer)return GOLD_BANK;
   if(c.held_seconds>=max_hold_seconds && c.move<.25*c.risk)return GOLD_STAGNATION;
   return GOLD_HOLD;
  }
#endif
