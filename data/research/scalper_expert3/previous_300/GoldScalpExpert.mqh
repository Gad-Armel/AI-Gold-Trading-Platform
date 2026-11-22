#ifndef GOLD_SCALP_EXPERT
#define GOLD_SCALP_EXPERT
#include "GoldScalpMath.mqh"
#include "GoldScalpFlow.mqh"
// Pure causal helpers. Evidence scores are NOT calibrated win probabilities.
struct GoldScalpEvidence
  {
   int side,m1,m5,m15,h1,advisor;
   double fast_pressure,slow_pressure,efficiency,slow_efficiency,rvol;
   bool rejected_candle;
  };
double GoldScalpScore(const GoldScalpEvidence &c)
  {
   if(c.side==0)return 0;
   double score=35*GoldClamp(c.side*c.fast_pressure,0,1)+20*GoldClamp(c.side*c.slow_pressure,0,1);
   score+=15*GoldClamp(c.efficiency,0,1)+5*GoldClamp(c.slow_efficiency,0,1);
   score+=c.m1==c.side?8:c.m1==-c.side?-4:0;
   score+=c.m5==c.side?5:c.m5==-c.side?-3:0;
   score+=c.m15==c.side?3:c.m15==-c.side?-2:0;
   score+=c.h1==c.side?2:c.h1==-c.side?-1:0;
   score+=c.advisor==c.side?4:c.advisor==-c.side?-6:0;
   score+=5*GoldClamp(c.rvol/1.5,0,1);
   if(c.rejected_candle)score-=8;
   return GoldClamp(score,0,100);
  }
bool GoldScalpImpulse(const int side,const GoldFlowRead &fast,const GoldFlowRead &slow,const double spread)
  {
   return side!=0 && fast.ready && slow.ready && fast.direction==side &&
          side*slow.pressure>=.15 && fast.efficiency>=.35 && slow.efficiency>=.20 &&
          side*fast.move>=MathMax(.03,.60*spread);
  }
int GoldSessionBucket(const datetime utc)
  {
   MqlDateTime t;TimeToStruct(utc,t);
   if(t.hour<7)return 0;if(t.hour<12)return 1;if(t.hour<16)return 2;if(t.hour<21)return 3;
   return t.hour>=23?0:4; // no new entries during 21:00-23:00 UTC rollover
  }
string GoldSessionName(const int bucket)
  {return bucket==0?"ASIA":bucket==1?"LONDON":bucket==2?"OVERLAP":bucket==3?"NEW YORK":"ROLLOVER";}
int GoldRecordedSession(const string note)
  {
   string tag="ScalperExpert3:S";int at=StringLen(tag);
   if(StringFind(note,tag)!=0 || StringLen(note)!=at+1)return -1;
   ushort digit=StringGetCharacter(note,at);
   return digit>='0' && digit<='3'?(int)(digit-'0'):-1;
  }
double GoldSessionAdjustment(const int samples,const double sum,const double square_sum)
  {
   if(samples<20)return 0;
   double mean=sum/samples,variance=MathMax(0,(square_sum-sum*sum/samples)/(samples-1));
   double uncertainty=1.64*MathSqrt(variance/samples);
   if(mean-uncertainty>.03)return -4;
   if(mean+uncertainty<-.03)return 8;
   return 0;
  }
// Net P&L includes the bid/ask crossing. Never subtract spread twice.
double GoldProfitNoise(const double volatility,const double spread,const double slip,const double cash_per_price)
  {return MathMax(.05,MathMax(.12*volatility,MathMax(.35*spread,2*slip))*cash_per_price);}
double GoldRetainedProfit(const double peak_net,const double fraction,const double noise)
  {return MathMax(0,peak_net-MathMax(peak_net*fraction,noise));}
bool GoldProfitGiveback(const double net,const double peak_net,const double fraction,const double noise,const double minimum_arm)
  {return peak_net>=MathMax(minimum_arm,2*noise) && net<=GoldRetainedProfit(peak_net,fraction,noise);}
double GoldAffordableStop(const double desired,const double floor_distance,const double risk_budget,
                          const double commission,const double slip,const double cash_per_price)
  {
   if(cash_per_price<=0 || risk_budget<=commission)return 0;
   double affordable=(risk_budget-commission)/cash_per_price-2*slip;
   if(affordable<floor_distance)return 0;
   return MathMin(MathMax(desired,floor_distance),affordable);
  }
#endif
