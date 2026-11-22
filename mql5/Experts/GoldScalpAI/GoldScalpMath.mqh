#ifndef GOLD_SCALP_MATH
#define GOLD_SCALP_MATH
// Pure helpers shared by the EA and its native self-test.
double GoldClamp(const double x,const double lo,const double hi){return MathMax(lo,MathMin(hi,x));}
double GoldRound(const double price,const double step,const bool up)
  {
   if(step<=0 || !MathIsValidNumber(price))return 0;
   return (up?MathCeil(price/step-1e-9):MathFloor(price/step+1e-9))*step;
  }
bool GoldVolumeValid(const double lot,const double minimum,const double maximum,const double step)
  {
   if(step<=0 || lot<minimum-1e-9 || lot>maximum+1e-9)return false;
   return MathAbs(lot/step-MathRound(lot/step))<1e-7;
  }
bool GoldHourAllowed(const int hour,const int start,const int end)
  {
   if(start==end)return false; // explicit empty session, not accidentally 24/7
   return start<end ? hour>=start && hour<end : hour>=start || hour<end;
  }
double GoldSigmoid(const double x){return 1.0/(1.0+MathExp(-GoldClamp(x,-30,30)));}
bool GoldCostFits(const double cost,const double opportunity,const double max_ratio)
  {return cost>=0 && opportunity>0 && cost<=opportunity*max_ratio;}
bool GoldPositionCapacity(const int positions,const int orders,const int limit)
  {return limit>=1 && limit<=5 && positions>=0 && orders>=0 && positions+orders<limit;}
bool GoldDailyRiskFits(const double planned,const double equity,const double reference,const double percent)
  {
   if(!MathIsValidNumber(planned) || !MathIsValidNumber(equity) || !MathIsValidNumber(reference) || !MathIsValidNumber(percent) || planned<0 || equity<=0 || percent<0 || percent>3)return false;
   return percent==0 || (reference>0 && planned<=equity-reference*(1-percent/100.)+1e-8);
  }
#endif
