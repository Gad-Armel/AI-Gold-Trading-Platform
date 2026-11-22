#ifndef GOLD_SCALP_LEARNING
#define GOLD_SCALP_LEARNING
#include "GoldScalpMath.mqh"
// Small causal online logistic model. Observation-only by default. No API.
// Prediction is direction 30s ahead, not a win probability or expected net P/L.
#define GOLD_FEATURES 5
#define GOLD_LABEL_QUEUE 16
struct GoldObservation
  {
   long when;
   double mid,prediction,baseline_prediction,x[GOLD_FEATURES];
  };
class CGoldOnlineModel
  {
private:
   double weights[GOLD_FEATURES],bias,brier,base_brier,base_up;
   GoldObservation queue[GOLD_LABEL_QUEUE];
   int head,count,trained;
   long last_sample,last_observed;
public:
   CGoldOnlineModel()
     {ArrayInitialize(weights,0);bias=0;brier=.25;base_brier=.25;base_up=.5;head=0;count=0;trained=0;last_sample=0;last_observed=0;}
   double Predict(const double &x[])
     {
      double z=bias;
      for(int i=0;i<GOLD_FEATURES;i++)z+=weights[i]*GoldClamp(x[i],-3,3);
      return GoldSigmoid(z);
     }
   void Observe(const long now,const double mid,const double &x[])
     {
      if(now<=last_observed || mid<=0 || !MathIsValidNumber(mid))return;
      // A missing observation interval cannot mature apparently continuous labels.
      if(last_observed>0 && now-last_observed>8000){head=0;count=0;last_sample=0;}
      last_observed=now;
      while(count>0)
        {
         GoldObservation item=queue[head];
         long age=now-item.when;
         if(age<30000)break;
         if(age<=35000)
           {
            double label=mid==item.mid?.5:mid>item.mid?1.:0.;
            // Prequential score uses the prediction stored BEFORE this label existed.
            brier=.99*brier+.01*MathPow(item.prediction-label,2);
            base_brier=.99*base_brier+.01*MathPow(item.baseline_prediction-label,2);
            base_up=.99*base_up+.01*label;
            double z=bias;
            for(int k=0;k<GOLD_FEATURES;k++)z+=weights[k]*item.x[k];
            double error=GoldSigmoid(z)-label;
            double rate=.01/MathSqrt(1.+trained/1000.);
            bias=GoldClamp(bias-rate*error,-3,3);
            for(int k=0;k<GOLD_FEATURES;k++)weights[k]=GoldClamp(weights[k]*(1-rate*.001)-rate*error*item.x[k],-3,3);
            trained++;
           }
         head=(head+1)%GOLD_LABEL_QUEUE;count--;
        }
      if(now-last_sample<5000 || count>=GOLD_LABEL_QUEUE)return;
      int slot=(head+count)%GOLD_LABEL_QUEUE;
      queue[slot].when=now;queue[slot].mid=mid;queue[slot].prediction=Predict(x);
      queue[slot].baseline_prediction=base_up;
      for(int k=0;k<GOLD_FEATURES;k++)queue[slot].x[k]=GoldClamp(x[k],-3,3);
      count++;last_sample=now;
     }
   int Samples(){return trained;}
   double Brier(){return brier;}
   bool FilterReady(){return trained>=2000 && brier<base_brier*.98;}
  };
#endif
