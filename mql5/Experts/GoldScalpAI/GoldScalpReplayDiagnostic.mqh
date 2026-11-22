#ifndef GOLD_SCALP_REPLAY_DIAGNOSTIC
#define GOLD_SCALP_REPLAY_DIAGNOSTIC
#include "GoldScalpExpert.mqh"
#include "GoldScalpEntry.mqh"
// Optional real broker tick diagnostic. No orders, no synthetic profitability.
// Isolates flow availability; does not pretend to replay news, ATR or account risk.
void GoldReplayDiagnostic()
  {
   int file=FileOpen("scalp_ticks.csv",FILE_READ|FILE_CSV|FILE_ANSI,';');
   if(file==INVALID_HANDLE){Print("SCALP_REPLAY: no optional tick fixture");return;}
   CGoldFlow replay;int rows=0,impulses=0,strong=0,old_agreement=0;long first=0,last=0;
   CGoldEntryConfirmation strict_confirm,grace_confirm;
   int strict_ready=0,grace_ready=0;bool prior_strict=false,prior_grace=false;
   while(!FileIsEnding(file) && rows<2000000)
     {
      MqlTick q={};q.time_msc=(long)StringToInteger(FileReadString(file));q.bid=StringToDouble(FileReadString(file));q.ask=StringToDouble(FileReadString(file));
      if(q.time_msc<=0 || q.bid<=0 || q.ask<q.bid)continue;
      rows++;if(first==0)first=q.time_msc;last=q.time_msc;
      if(!replay.Add(q))continue;
      GoldFlowRead f=replay.Read(q.time_msc,3),s=replay.Read(q.time_msc,8);
      bool qualified=false,coherent=false;
      if(GoldScalpImpulse(f.direction,f,s,q.ask-q.bid))
        {
         impulses++;GoldScalpEvidence e={};e.side=f.direction;e.fast_pressure=f.pressure;e.slow_pressure=s.pressure;e.efficiency=f.efficiency;e.slow_efficiency=s.efficiency;e.rvol=1;
         double score=GoldScalpScore(e);qualified=score>=62;coherent=score>=58;
         if(qualified)strong++;
        }
      bool sr=strict_confirm.Observe(q.time_msc,f.direction,qualified,qualified,1000,0);
      bool gr=grace_confirm.Observe(q.time_msc,f.direction,qualified,coherent,1000,250);
      if(sr && !prior_strict)strict_ready++;if(gr && !prior_grace)grace_ready++;
      prior_strict=sr;prior_grace=gr;
      f=replay.Read(q.time_msc,6);s=replay.Read(q.time_msc,12);
      if(f.ready && s.ready && f.direction!=0 && f.direction==s.direction)old_agreement++;
     }
   FileClose(file);
   PrintFormat("SCALP_REPLAY rows=%d span_hours=%.2f new_raw_impulses=%d neutral_context_score62=%d old_raw_agreement=%d (overlapping tick observations, not trades or a profit backtest)",rows,(last-first)/3600000.,impulses,strong,old_agreement);
   PrintFormat("CONFIRMATION_REPLAY strict_ready_episodes=%d grace_ready_episodes=%d (neutral indicator context, no orders, no profitability claim)",strict_ready,grace_ready);
  }
#endif
