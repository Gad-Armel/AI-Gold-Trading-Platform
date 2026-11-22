#ifndef GOLD_SCALP_INTELLIGENCE
#define GOLD_SCALP_INTELLIGENCE
#include "GoldScalpMath.mqh"
#include "GoldScalpMarket.mqh"

// Execution-safe subset of the intelligence research: regime, MTF confluence
// and abnormal-volatility detection. It only uses completed M1/M5/M15/H1 data
// already refreshed in the timer lane; OnTick never does I/O or history scans.
enum GOLD_INTELLIGENCE_REGIME
  {
   GOLD_INTEL_WARMING=0,
   GOLD_INTEL_TREND_BULL,
   GOLD_INTEL_TREND_BEAR,
   GOLD_INTEL_BREAKOUT_BULL,
   GOLD_INTEL_BREAKOUT_BEAR,
   GOLD_INTEL_RANGE,
   GOLD_INTEL_ABNORMAL
  };

string GoldIntelligenceRegimeLabel(const GOLD_INTELLIGENCE_REGIME regime)
  {
   switch(regime)
     {
      case GOLD_INTEL_TREND_BULL:return "TREND BULL";
      case GOLD_INTEL_TREND_BEAR:return "TREND BEAR";
      case GOLD_INTEL_BREAKOUT_BULL:return "BREAKOUT BULL";
      case GOLD_INTEL_BREAKOUT_BEAR:return "BREAKOUT BEAR";
      case GOLD_INTEL_RANGE:return "RANGE";
      case GOLD_INTEL_ABNORMAL:return "ABNORMAL VOL";
     }
   return "WARMING";
  }

int GoldIntelligenceAlignment(const int side,const int &directions[])
  {
   if(side==0)return 0;
   int aligned=0;
   for(int i=0;i<4;i++)if(directions[i]==side)aligned++;
   return aligned;
  }

int GoldIntelligenceAdjustment(const int side,const int &directions[],const GOLD_INTELLIGENCE_REGIME regime)
  {
   if(side==0)return 0;
   if(regime==GOLD_INTEL_ABNORMAL)return -100;
   int aligned=GoldIntelligenceAlignment(side,directions);
   int higher=(directions[2]==side?1:0)+(directions[3]==side?1:0);
   if(aligned==4)return 6;
   if(aligned>=3 && directions[0]==side && directions[1]==side)return 3;
   if(higher==0 && (directions[2]==-side || directions[3]==-side))return -6;
   if(regime==GOLD_INTEL_RANGE)return -2;
   return 0;
  }

class CGoldScalpIntelligence
  {
public:
   bool ready,veto;
   GOLD_INTELLIGENCE_REGIME regime;
   double volatility_ratio;
   int directions[4];
   datetime refreshed;
   CGoldScalpIntelligence(){Reset();}
   void Reset()
     {
      ready=false;veto=false;regime=GOLD_INTEL_WARMING;volatility_ratio=0;ArrayInitialize(directions,0);refreshed=0;
     }
   void Refresh(const CGoldMarket &market,const double spread,const double maximum_bar_expansion)
     {
      if(!market.ready || market.atr<=0 || market.atr_reference<=0 || maximum_bar_expansion<=0){Reset();return;}
      for(int i=0;i<4;i++)directions[i]=market.direction[i];
      volatility_ratio=market.atr/market.atr_reference;
      int bull=GoldIntelligenceAlignment(1,directions),bear=GoldIntelligenceAlignment(-1,directions);
      bool expansion=market.range>=1.4*market.atr;
      veto=volatility_ratio>=2.8 || market.range>=maximum_bar_expansion*market.atr || spread>MathMax(.60,3.0*market.atr);
      if(veto)regime=GOLD_INTEL_ABNORMAL;
      else if(expansion && directions[0]==1 && directions[1]==1)regime=GOLD_INTEL_BREAKOUT_BULL;
      else if(expansion && directions[0]==-1 && directions[1]==-1)regime=GOLD_INTEL_BREAKOUT_BEAR;
      else if(bull>=3)regime=GOLD_INTEL_TREND_BULL;
      else if(bear>=3)regime=GOLD_INTEL_TREND_BEAR;
      else regime=GOLD_INTEL_RANGE;
      ready=true;refreshed=market.refreshed;
     }
   int Adjustment(const int side)const{return ready?GoldIntelligenceAdjustment(side,directions,regime):0;}
   string Label()const{return GoldIntelligenceRegimeLabel(regime);}
  };
#endif
