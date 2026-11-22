#ifndef GOLD_SCALP_MARKET
#define GOLD_SCALP_MARKET
#include "GoldScalpMath.mqh"
// Constant-time spread baseline. The candidate quote is tested BEFORE insertion.
class CGoldSpreadWindow
  {
private:
   double values[100],sum;
   int next,count;
public:
   CGoldSpreadWindow(){Reset();}
   void Reset(){sum=0;next=0;count=0;ArrayInitialize(values,0);}
   int Count(){return count;}
   double Mean(){return count>0?sum/count:0;}
   bool Allows(const double spread,const double multiplier)
     {return count==100 && spread>=0 && Mean()>0 && spread<=Mean()*multiplier+1e-9;}
   void Add(const double spread)
     {
      if(spread<0 || !MathIsValidNumber(spread))return;
      if(count==100)sum-=values[next];else count++;
      values[next]=spread;sum+=spread;next=(next+1)%100;
     }
  };
struct GoldCandleShape
  {
   double range,upper,lower,body,close_location;
   bool reject_buy,reject_sell;
  };
GoldCandleShape GoldShape(const MqlRates &bar,const double prior_high,const double prior_low)
  {
   GoldCandleShape c={};c.range=bar.high-bar.low;
   if(c.range<=0){c.reject_buy=true;c.reject_sell=true;return c;}
   c.upper=(bar.high-MathMax(bar.open,bar.close))/c.range;
   c.lower=(MathMin(bar.open,bar.close)-bar.low)/c.range;
   c.body=MathAbs(bar.close-bar.open)/c.range;c.close_location=(bar.close-bar.low)/c.range;
   c.reject_buy=(bar.high>prior_high && bar.close<prior_high && c.upper>=.35) || (c.upper>=.55 && c.close_location<.55);
   c.reject_sell=(bar.low<prior_low && bar.close>prior_low && c.lower>=.35) || (c.lower>=.55 && c.close_location>.45);
   return c;
  }
int GoldTrendSide(const double fast,const double slow,const double close)
  {return fast>slow && close>slow?1:fast<slow && close<slow?-1:0;}
bool GoldAligned(const int side,const int m5,const int m15,const int h1)
  {return side!=0 && side==m5 && side==m15 && side==h1;}
double GoldLiveATR(const double completed,const int period,const double high,const double low,const double previous_close)
  {
   if(completed<=0 || period<2 || high<low)return completed;
   double tr=MathMax(high-low,MathMax(MathAbs(high-previous_close),MathAbs(low-previous_close)));
   return MathMax(completed*.5,(completed*(period-1)+tr)/period);
  }
double GoldSlippage(const double spread,const double volatility,const double minimum,const double maximum)
  {return GoldClamp(MathMax(spread*.20,volatility*.015),minimum,maximum);}
bool GoldShock(const double before,const double after,const double volatility,const double spread,const double multiple)
  {return before>0 && after>0 && volatility>0 && MathAbs(after-before)>=MathMax(volatility*multiple,spread*8.);}
double GoldAdaptiveArm(const double risk,const double volatility,const double configured,const double factor,const double costs)
  {return risk>0?MathMax(costs/risk,MathMin(configured,factor*volatility/risk)):configured;}

// All terminal indicator/history calls in this class belong to the timer lane.
class CGoldMarket
  {
private:
   int atr_handle,fast_handle[4],slow_handle[4],atr_period,warmup;
   ENUM_TIMEFRAMES frames[4];
   datetime bars[4];
   string symbol;
public:
   bool ready;
   double atr,fast,slow,close,range,rvol,previous_high,previous_low;
   int direction[4];
   datetime m1_bar,refreshed;
   GoldCandleShape shape;
   CGoldMarket()
     {atr_handle=INVALID_HANDLE;ArrayInitialize(fast_handle,INVALID_HANDLE);ArrayInitialize(slow_handle,INVALID_HANDLE);ArrayInitialize(bars,0);ArrayInitialize(direction,0);ready=false;atr=0;fast=0;slow=0;close=0;range=0;rvol=0;m1_bar=0;refreshed=0;}
   bool Init(const string name,const int period,const int fast_period,const int slow_period)
     {
      symbol=name;atr_period=period;warmup=slow_period*3;frames[0]=PERIOD_M1;frames[1]=PERIOD_M5;frames[2]=PERIOD_M15;frames[3]=PERIOD_H1;
      atr_handle=iATR(symbol,PERIOD_M1,period);if(atr_handle==INVALID_HANDLE)return false;
      for(int i=0;i<4;i++)
        {
         fast_handle[i]=iMA(symbol,frames[i],fast_period,0,MODE_EMA,PRICE_CLOSE);
         slow_handle[i]=iMA(symbol,frames[i],slow_period,0,MODE_EMA,PRICE_CLOSE);
         if(fast_handle[i]==INVALID_HANDLE || slow_handle[i]==INVALID_HANDLE)return false;
        }
      return true;
     }
   bool Refresh(const datetime now)
     {
      ready=false;
      for(int i=0;i<4;i++)
        {
         datetime current=iTime(symbol,frames[i],0);
         if(current<=0 || now-current>PeriodSeconds(frames[i])+30 || now<current)return false;
         if(current==bars[i])continue;
         if(BarsCalculated(fast_handle[i])<warmup || BarsCalculated(slow_handle[i])<warmup || BarsCalculated(atr_handle)<atr_period+3)return false;
         double f[1],s[1];MqlRates completed[1];
         if(CopyBuffer(fast_handle[i],0,1,1,f)!=1 || CopyBuffer(slow_handle[i],0,1,1,s)!=1 || CopyRates(symbol,frames[i],1,1,completed)!=1)return false;
         if(!MathIsValidNumber(f[0]) || !MathIsValidNumber(s[0]) || f[0]<=0 || s[0]<=0)return false;
         direction[i]=GoldTrendSide(f[0],s[0],completed[0].close);
         if(i==0)
           {
            MqlRates history[21];double a[1];
            if(CopyRates(symbol,PERIOD_M1,1,21,history)!=21 || CopyBuffer(atr_handle,0,1,1,a)!=1 || a[0]<=0 || !MathIsValidNumber(a[0]))return false;
            double average=0;previous_high=history[0].high;previous_low=history[0].low;
            for(int j=0;j<20;j++)
              {average+=(double)history[j].tick_volume;previous_high=MathMax(previous_high,history[j].high);previous_low=MathMin(previous_low,history[j].low);}
            average/=20.;rvol=average>0?(double)history[20].tick_volume/average:0;
            shape=GoldShape(history[20],previous_high,previous_low);
            fast=f[0];slow=s[0];close=history[20].close;range=shape.range;atr=a[0];m1_bar=current;
           }
         bars[i]=current;
        }
      refreshed=now;ready=true;return true;
     }
   bool Fresh(const datetime now){return ready && now>=refreshed && now-refreshed<=3 && now>=m1_bar && now-m1_bar<90;}
   void Release()
     {
      if(atr_handle!=INVALID_HANDLE)IndicatorRelease(atr_handle);
      for(int i=0;i<4;i++){if(fast_handle[i]!=INVALID_HANDLE)IndicatorRelease(fast_handle[i]);if(slow_handle[i]!=INVALID_HANDLE)IndicatorRelease(slow_handle[i]);}
     }
  };
#endif
