#ifndef GOLD_SCALP_REPLAY_DIAGNOSTIC
#define GOLD_SCALP_REPLAY_DIAGNOSTIC
#include "GoldScalpExpert.mqh"
// Optional real broker tick diagnostic. No orders, no synthetic profitability.
// Isolates flow availability; does not pretend to replay news, ATR or account risk.
void GoldReplayDiagnostic()
  {
   int file=FileOpen("scalp_ticks.csv",FILE_READ|FILE_CSV|FILE_ANSI,';');
   if(file==INVALID_HANDLE){Print("SCALP_REPLAY: no optional tick fixture");return;}
   CGoldFlow replay;int rows=0,impulses=0,strong=0,old_agreement=0;long first=0,last=0;
   while(!FileIsEnding(file) && rows<2000000)
     {
      MqlTick q={};q.time_msc=(long)StringToInteger(FileReadString(file));q.bid=StringToDouble(FileReadString(file));q.ask=StringToDouble(FileReadString(file));
      if(q.time_msc<=0 || q.bid<=0 || q.ask<q.bid)continue;
      rows++;if(first==0)first=q.time_msc;last=q.time_msc;
      if(!replay.Add(q))continue;
      GoldFlowRead f=replay.Read(q.time_msc,3),s=replay.Read(q.time_msc,8);
      if(GoldScalpImpulse(f.direction,f,s,q.ask-q.bid))
        {
         impulses++;GoldScalpEvidence e={};e.side=f.direction;e.fast_pressure=f.pressure;e.slow_pressure=s.pressure;e.efficiency=f.efficiency;e.slow_efficiency=s.efficiency;e.rvol=1;
         if(GoldScalpScore(e)>=62)strong++;
        }
      f=replay.Read(q.time_msc,6);s=replay.Read(q.time_msc,12);
      if(f.ready && s.ready && f.direction!=0 && f.direction==s.direction)old_agreement++;
     }
   FileClose(file);
   PrintFormat("SCALP_REPLAY rows=%d span_hours=%.2f new_raw_impulses=%d neutral_context_score62=%d old_raw_agreement=%d (overlapping tick observations, not trades or a profit backtest)",rows,(last-first)/3600000.,impulses,strong,old_agreement);
  }
#endif
