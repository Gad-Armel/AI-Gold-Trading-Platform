#ifndef GOLD_SCALP_LATENCY
#define GOLD_SCALP_LATENCY
#include "GoldScalpMath.mqh"
#define GOLD_TICK_LATENCY_CAPACITY 512
ulong gold_tick_latency_us[GOLD_TICK_LATENCY_CAPACITY];
int gold_tick_latency_next=0,gold_tick_latency_count=0;
void GoldRecordTickLatency(const ulong elapsed)
  {
   gold_tick_latency_us[gold_tick_latency_next]=elapsed;
   gold_tick_latency_next=(gold_tick_latency_next+1)%GOLD_TICK_LATENCY_CAPACITY;
   gold_tick_latency_count=MathMin(gold_tick_latency_count+1,GOLD_TICK_LATENCY_CAPACITY);
  }
double GoldTickLatencyPercentile(const double fraction)
  {
   if(gold_tick_latency_count<=0)return 0;
   ulong sorted[];ArrayResize(sorted,gold_tick_latency_count);
   for(int i=0;i<gold_tick_latency_count;i++)sorted[i]=gold_tick_latency_us[i];
   ArraySort(sorted);
   int index=(int)MathMax(0,MathMin(gold_tick_latency_count-1,MathCeil(gold_tick_latency_count*GoldClamp(fraction,0,1))-1));
   return (double)sorted[index];
  }
#endif
