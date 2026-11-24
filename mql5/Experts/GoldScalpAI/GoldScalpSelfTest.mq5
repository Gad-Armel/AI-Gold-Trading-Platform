#property strict
#property version "2.00"
#property tester_file "scalp_ticks.csv"
#include "GoldScalpMath.mqh"
#include "GoldScalpLatency.mqh"
#include "GoldScalpInstance.mqh"
#include "GoldScalpFlow.mqh"
#include "GoldScalpLearning.mqh"
#include "GoldScalpExit.mqh"
#include "GoldScalpMarket.mqh"
#include "GoldScalpIntelligence.mqh"
#include "GoldScalpSafety.mqh"
#include "GoldScalpStats.mqh"
#include "GoldScalpExecution.mqh"
#include "GoldScalpFeeds.mqh"
#include "GoldScalpWire.mqh"
#include "GoldScalpExpert.mqh"
#include "GoldScalpReplayDiagnostic.mqh"
#include "GoldScalpRotation.mqh"
#include "GoldScalpControlWire.mqh"
#include "GoldScalpMacro.mqh"
#include "../../Services/GoldScalpNewsPublisher.mqh"
#include "GoldScalpEntry.mqh"
int checks=0,failures=0;
void Check(const bool condition,const string name)
  {checks++;if(!condition){failures++;Print("FAIL: ",name);}}
void Feed(CGoldFlow &flow,const int mode)
  {
   for(int i=0;i<=120;i++)
     {
      MqlTick tick={};tick.time_msc=100000+i*100;
      tick.bid=2500+(mode==1?i*.01:mode==2?-i*.01:0);
      tick.ask=tick.bid+.2+(mode==3?i*.01:0);flow.Add(tick);
     }
  }
int OnInit()
  {
   int intel_dirs[]={1,1,1,1};
   Check(GoldIntelligenceAlignment(1,intel_dirs)==4 && GoldIntelligenceAdjustment(1,intel_dirs,GOLD_INTEL_TREND_BULL)==6,"intelligence rewards complete causal MTF alignment");
   int intel_conflict[]={1,1,-1,-1};
   Check(GoldIntelligenceAdjustment(1,intel_conflict,GOLD_INTEL_RANGE)==-6,"intelligence penalizes entries against both higher timeframes");
   Check(GoldIntelligenceAdjustment(1,intel_dirs,GOLD_INTEL_ABNORMAL)==-100,"abnormal-volatility intelligence is a hard veto");
   GoldRecordTickLatency(30);GoldRecordTickLatency(10);GoldRecordTickLatency(20);GoldRecordTickLatency(40);
   Check(GoldTickLatencyPercentile(.50)==20 && GoldTickLatencyPercentile(.95)==40 && GoldTickLatencyPercentile(.99)==40,"tick latency percentiles use bounded sorted samples");
   Check(GoldNewsRetrySeconds(1)==10 && GoldNewsRetrySeconds(2)==20 && GoldNewsRetrySeconds(6)==300,"calendar timeout retry uses bounded exponential backoff");
   Check(GoldNewsRetrySeconds(-1)==5 && GoldNewsRetrySeconds(99)==300,"calendar retry clamps invalid or repeated failure counts");
   Check(GoldNewsFrom(100000)==78400 && GoldNewsTo(100000)==164800,"calendar request window stays bounded around server time");
   Check(GoldSafetyOwnsExposure("XAUUSD","XAUUSD",92563101,92563101),"safety liquidation includes this EA's XAUUSD exposure");
   Check(!GoldSafetyOwnsExposure("EURUSD","XAUUSD",92563101,92563101),"safety liquidation excludes this EA's other symbols");
   Check(!GoldSafetyOwnsExposure("XAUUSD","XAUUSD",92563102,92563101),"safety liquidation excludes other magic numbers");
   Check(GoldPositionCapacity(4,0,5),"fifth position is permitted by account capacity");
   Check(!GoldPositionCapacity(5,0,5) && !GoldPositionCapacity(4,1,5),"positions and pending orders reserve all five slots");
   Check(!GoldPositionCapacity(0,0,6) && !GoldPositionCapacity(-1,0,5),"invalid position limits fail closed");
   Check(GoldDailyRiskFits(4,100,100,0),"disabled daily equity rule permits reserved risk on a flat account");
   Check(GoldDailyRiskFits(4,95,100,0),"disabled daily equity rule does not become a hidden profit-only gate");
   Check(GoldDailyRiskFits(1,98,100,3) && !GoldDailyRiskFits(1.01,98,100,3),"enabled daily risk uses remaining equity allowance");
   Check(!GoldDailyRiskFits(1,100,0,3) && !GoldDailyRiskFits(-1,100,100,0),"invalid daily risk inputs fail closed");
   GoldFlowRead expansion_micro={};expansion_micro.ready=true;expansion_micro.direction=1;expansion_micro.pressure=.5;
   Check(GoldStrongScalpSignal(1,61,55,expansion_micro) && !GoldStrongScalpSignal(1,60.99,55,expansion_micro),"fourth/fifth entry requires six additional evidence points");
   Check(!GoldStrongScalpSignal(-1,80,55,expansion_micro),"strong score cannot replace aligned micro-flow for expanded exposure");
   Check(!GoldLegacyOwnerBlocks(0,100,false,""),"empty legacy lock is claimable");
   Check(!GoldLegacyOwnerBlocks(99,100,false,""),"absent legacy chart is recoverable");
   Check(!GoldLegacyOwnerBlocks(99,100,true,""),"chart without EA cannot retain startup lock");
   Check(GoldLegacyOwnerBlocks(99,100,true,"GoldScalpAI"),"active legacy EA retains ownership");
   Check(!GoldLegacyOwnerBlocks(100,100,true,"GoldScalpAI"),"same chart reinitialization is recoverable under lease");
   CGoldInstanceLease lease_a,lease_b;
   string lease_path="GoldScalpSelfTest_"+(string)ChartID()+".lease";
   Check(lease_a.Acquire(lease_path,false),"first instance acquires exclusive lease");
   Check(!lease_b.Acquire(lease_path,false),"duplicate instance cannot acquire held lease");
   lease_a.Release();
   Check(lease_b.Acquire(lease_path,false),"released lease can be reacquired despite existing file");
   lease_b.Release();FileDelete(lease_path);
   GoldFlowRead frequent_fast={},frequent_slow={};
   frequent_fast.ready=true;frequent_fast.pressure=.21;frequent_fast.efficiency=.31;frequent_fast.move=.13;
   frequent_slow.ready=true;frequent_slow.pressure=.11;frequent_slow.efficiency=.16;
   Check(!GoldScalpImpulse(1,frequent_fast,frequent_slow,.5) && GoldScalpImpulse(1,frequent_fast,frequent_slow,.5,true),"high-frequency mode admits smaller coherent impulse");
   frequent_slow.pressure=.099;Check(!GoldScalpImpulse(1,frequent_fast,frequent_slow,.5,true),"high-frequency mode enforces minimum aligned slow pressure");
   frequent_slow.pressure=.11;frequent_slow.efficiency=.149;Check(!GoldScalpImpulse(1,frequent_fast,frequent_slow,.5,true),"high-frequency mode enforces minimum slow efficiency");
   frequent_slow.efficiency=.16;frequent_fast.move=.124;Check(!GoldScalpImpulse(1,frequent_fast,frequent_slow,.5,true),"high-frequency mode enforces spread-scaled movement floor");
   frequent_fast.move=.13;frequent_fast.efficiency=.10;Check(!GoldScalpImpulse(1,frequent_fast,frequent_slow,.5,true),"frequent mode rejects noisy movement");
   CGoldEntryConfirmation quick;
   Check(!quick.Observe(1000,1,true,true,1000,750,2),"frequent mode cannot enter on one quote");
   Check(!quick.Observe(1500,1,true,true,1000,750,2),"frequent confirmation retains one-second minimum");
   Check(quick.Observe(2000,1,true,true,1000,750,2),"frequent confirmation accepts sustained fresh quotes");
   quick.Reset();quick.Observe(1000,1,true,true,1000,750,2);
   Check(!quick.Observe(3000,1,true,true,1000,750,2),"frequent mode still rejects stale confirmation gaps");
   CGoldEntryConfirmation confirmation;
   Check(!confirmation.Observe(1000,1,true,true,1000,250),"one quote cannot arm a trade");
   confirmation.Observe(1300,1,true,true,1000,250);confirmation.Observe(1600,1,true,true,1000,250);
   Check(confirmation.Observe(2000,1,true,true,1000,250),"four real sparse quotes retain uninterrupted confirmation");
   Check(!confirmation.Observe(2000,1,true,true,1000,250),"duplicate flow snapshot cannot fabricate confirmation");
   Check(!confirmation.Observe(2100,1,false,true,1000,250),"weak current signal cannot enter during grace");
   Check(confirmation.Observe(2200,1,true,true,1000,250),"brief neutral dip preserves mature evidence");
   Check(!confirmation.Observe(2300,-1,true,true,1000,250) && confirmation.started==2300,"direction reversal starts fresh evidence");
   Check(!confirmation.Observe(2400,-1,true,false,1000,250) && confirmation.started==0,"opposing context resets confirmation immediately");
   confirmation.Observe(3000,1,true,true,1000,250);confirmation.Observe(3200,1,true,true,1000,250);
   confirmation.Observe(3400,1,false,true,1000,250);
   Check(!confirmation.Observe(3500,1,true,true,1000,250) && confirmation.started==3500,"neutral interval over 250 ms cannot borrow old evidence");
   Check(!confirmation.Observe(5100,1,true,true,1000,250) && confirmation.started==5100,"quote outage cannot mature persistence");
   Check(!confirmation.Observe(5000,1,true,true,1000,250) && confirmation.started==5000,"backward clock resets evidence");
   confirmation.Reset();Check(confirmation.qualified==0 && confirmation.started==0,"execution blocks clear entry memory");
   Check(MathAbs(GoldRollingRiskRemaining(5,-4.5)-.5)<1e-8,"remaining rolling budget reserves previous realized losses");
   Check(!GoldRiskReservationFits(1.2,0,.5),"entry cannot immediately consume near-exhausted rolling allowance");
   Check(GoldRiskReservationFits(1.2,.8,2),"exact available risk budget accepts existing and new exposure");
   Check(!GoldRiskReservationFits(1.2,.81,2),"existing exposure is reserved before another entry");
   Check(!GoldRiskReservationFits(0,0,1) && !GoldRiskReservationFits(1,-1,1),"invalid risk reservation fails closed");
   Check(GoldRollingRiskRemaining(5,-6)==0 && GoldRollingRiskRemaining(100,-1)==49,"remaining budget is nonnegative and fifty-dollar cap cannot expand");
   Check(MathAbs(GoldRollingRiskRemaining(50,-5.15)-44.85)<1e-8,"old five-dollar breach leaves budget under new limit");
   Check(GoldRollingRiskRemaining(50,-50)==0 && GoldRollingRiskRemaining(50,-49.5)==.5,"fifty-dollar boundary exhausts rolling budget");
   GoldFlowRead bounce={},context_flow={};bounce.ready=true;bounce.pressure=.2;
   context_flow.ready=true;context_flow.direction=-1;context_flow.efficiency=.6;context_flow.move=-1.5;
   Check(GoldCounterflowTrap(1,bounce,context_flow,.3,2),"brief buy bounce against strong falling context is rejected");
   bounce.pressure=.6;Check(!GoldCounterflowTrap(1,bounce,context_flow,.3,2),"sustained eight-second reversal can overcome old direction");
   bounce.pressure=-.2;context_flow.direction=1;context_flow.move=1.5;
   Check(GoldCounterflowTrap(-1,bounce,context_flow,.3,2),"counterflow guard is symmetric for sells");
   context_flow.ready=false;Check(!GoldCounterflowTrap(-1,bounce,context_flow,.3,2),"missing context never invents a directional veto");
   bool slip_valid=false;
   Check(MathAbs(GoldSignedFillSlippage(4000,4000.1,true,slip_valid)-.1)<1e-8 && slip_valid,"buy slippage uses saved positive request price");
   Check(MathAbs(GoldSignedFillSlippage(4000,3999.9,false,slip_valid)-.1)<1e-8 && slip_valid,"sell adverse slippage is positive");
   Check(GoldSignedFillSlippage(0,4000,false,slip_valid)==0 && !slip_valid,"omitted price is unavailable, never four thousand dollars slippage");
   Check(GoldEarlyProfitExit(.16,.28,.10,-.6,.7,500),"small net winner can bank reversal before fixed 0.35 arm");
   Check(!GoldEarlyProfitExit(.16,.28,.10,-.6,.7,499),"early exit needs persistent reversal");
   Check(!GoldEarlyProfitExit(.08,.28,.10,-.6,.7,600),"early micro exit cannot treat sub-noise profit as reliable");
   Check(!GoldEarlyProfitExit(.18,.22,.10,-.6,.7,600),"normal sub-noise pullback holds position");
   Check(GoldReleaseReaction(1,100030,100000,4000,4001,.2)==2,"release context follows observed gold response");
   Check(GoldReleaseReaction(-1,100030,100000,4000,4001,.2)==-2,"opposing response is small contextual penalty");
   Check(GoldReleaseReaction(1,100010,100000,4000,4001,.2)==0,"release observation must mature before influencing score");
   Check(GoldReleaseReaction(1,102000,100000,4000,4001,.2)==0,"release response expires");
   Check(GoldReleaseReaction(1,100030,100000,4000,4000.1,.2)==0,"release noise has no directional effect");
   Check(GoldMacroRelevant("ADP Nonfarm Employment") && GoldMacroRelevant("Core PCE Price Index") && GoldMacroRelevant("GDP q/q"),"requested releases recognized even if not high importance");
   FolderCreate("GoldScalp");string mf=GoldMacroFile("TEST");
   int mh=FileOpen(mf,FILE_WRITE|FILE_TXT|FILE_ANSI,0,CP_UTF8);
   if(mh!=INVALID_HANDLE){FileWriteString(mh,"GOLD_MACRO_V1;TEST;100010;2\n1;100000;Core PCE;2.8;2.7;2.6;PERCENT;POSITIVE\n2;100100;GDP;9.9;3.0;2.0;PERCENT;UNKNOWN\nEND\n");FileClose(mh);}
   CGoldMacro macro;
   Check(macro.Load("TEST",100010,0,false) && macro.observed==0,"calendar arriving before quotes cannot invent a response baseline");
   Check(macro.Load("TEST",100010,4000,false) && macro.Fresh(100010),"native macro file round trips");
   Check(macro.events[1].actual=="NA" && macro.release_id=="1","future actuals are hidden and cannot start reaction tracking");
   Check(macro.Evidence(1,100031,4001,.2)==2 && macro.Evidence(1,100200,4001,.2)==0,"freshness gates release evidence");
   Check(!macro.Load("OTHER",100010,4000,false) && macro.Evidence(1,100031,4001,.2)==0,"missing feed neutralizes stale macro evidence");
   FileDelete(mf);
   CGoldFlow sparse;
   for(int t=0;t<30;t++){MqlTick sq={};sq.time_msc=200000+t*500;sq.bid=4000+t*.1;sq.ask=sq.bid+.2;sparse.Add(sq);}
   GoldFlowRead sparse_micro=sparse.Read(214500,1);
   Check(sparse_micro.ready && sparse_micro.count==3 && sparse_micro.direction==1,"one-second micro flow accepts three genuine half-second quotes");
   CGoldFlow warming;
   for(int t=0;t<4;t++){MqlTick wt={};wt.time_msc=300000+t*100;wt.bid=4000+t*.01;wt.ask=wt.bid+.2;warming.Add(wt);}
   GoldFlowRead warming_read=warming.Read(300300,3);
   Check(!warming_read.ready && warming_read.count==4 && MathAbs(warming_read.seconds-.3)<1e-9 &&
      warming_read.age_milliseconds==0,"warming flow exposes sample span without qualifying an incomplete window");
   GoldFlowRead stale_read=warming.Read(302301,3);
   Check(!stale_read.ready && stale_read.age_milliseconds==2001,"stale-flow diagnostics retain the actual quote age");
   CGoldFlow empty_flow;GoldFlowRead empty_read=empty_flow.Read(300300,3);
   Check(!empty_read.ready && empty_read.age_milliseconds==-1,"empty-flow diagnostics identify unavailable quote age");
   GoldFlowRead tf={},ts={},tc={};tf.ready=true;tf.pressure=.1;ts.ready=true;ts.pressure=.2;ts.efficiency=.5;
   tc.ready=true;tc.direction=1;tc.pressure=.8;tc.efficiency=.6;tc.move=1.0;
   Check(GoldTrendScalpImpulse(1,tf,ts,tc,.3,1,1),"smooth aligned trend may qualify without fast direction flag");
   Check(!GoldTrendScalpImpulse(1,tf,ts,tc,.6,1,1),"continuation movement must exceed two current spreads");
   Check(!GoldTrendScalpImpulse(1,tf,ts,tc,.3,1,-1),"slow continuation lane requires M1 and M5 support");
   tf.pressure=-.3;Check(!GoldTrendScalpImpulse(1,tf,ts,tc,.3,1,1),"opposing current flow prevents chasing old trend");
   tf.pressure=.1;tc.ready=false;Check(!GoldTrendScalpImpulse(1,tf,ts,tc,.3,1,1),"unwarmed context cannot create continuation");
   CGoldRotation rotation;rotation.Intent(17,1);
   Check(!rotation.Ready(-1,2000,100200,750,true,false,true,true),"rotation cannot precede broker exit confirmation");
   rotation.Confirm(18,1000,100000);Check(!rotation.confirmed,"unrelated position exit cannot authorize rotation");
   rotation.Confirm(17,1000,100000);
   Check(!rotation.Ready(-1,1749,100800,750,true,false,true,true),"rotation rearm has a precise millisecond boundary");
   Check(rotation.Ready(-1,1750,100800,750,true,false,true,true),"confirmed flat opposite impulse can use rapid rearm");
   Check(!rotation.Ready(1,2000,101000,750,true,false,true,true),"same-direction re-entry retains normal cooldown");
   Check(rotation.Ready(1,2000,101000,750,true,false,true,true,true),"enabled continuation can rearm same direction after confirmed profitable exit");
   Check(!rotation.Ready(1,2000,101000,750,true,true,true,true,true),"continuation cannot bypass unresolved execution");
   Check(!rotation.Ready(-1,2000,101000,750,false,false,true,true),"remaining positions forbid reversal stacking");
   Check(!rotation.Ready(-1,2000,101000,750,true,true,true,true),"unresolved broker close forbids new entry");
   Check(!rotation.Ready(-1,2000,101000,750,true,false,false,true),"unreconciled exposure forbids rotation");
   Check(!rotation.Ready(-1,2000,101000,750,true,false,true,false),"weak opposite impulse cannot rotate");
   Check(!rotation.Ready(-1,12000,101000,750,true,false,true,true),"rotation authorization expires after ten seconds");
   Check(!rotation.Ready(-1,2000,100000,750,true,false,true,true),"pre-close quote cannot rearm a reversal");
   rotation.Clear();Check(!rotation.confirmed && rotation.ticket==0,"pause and feed gaps clear rotation intent");
   Check(GoldAccelerationBonus(1,.5,.1,.2)==4 && GoldAccelerationBonus(-1,-.5,-.1,.2)==4,"acceleration bonus is symmetric and bounded");
   Check(GoldAccelerationBonus(1,0,.5,.2)==-4 && GoldAccelerationBonus(0,1,0,.2)==0,"deceleration penalizes; no direction gets no bonus");
   Check(GoldMicroTakeOut(.8,1,.1,.35,-.6,.6,0,.2,750),"armed net winner can exit on confirmed decelerating micro-reversal");
   Check(!GoldMicroTakeOut(.8,1,.1,.35,-.6,.6,0,.2,749),"one-tick micro reversal does not close a runner");
   Check(!GoldMicroTakeOut(.8,1,.1,.35,-.6,.6,.3,.2,900),"still accelerating runner is not cut by short opposing noise");
   Check(!GoldMicroTakeOut(.95,1,.1,.35,-.6,.6,0,.2,900),"giveback below price noise does not trigger micro exit");
   bool p=false,l=false;
   Check(GoldControlTransition("pause",false,false,p,l) && p && !l,"browser pause works without enabling trading");
   Check(!GoldControlTransition("resume",true,true,p,l) && p,"browser resume cannot clear risk lock");
   Check(GoldControlTransition("resume",false,true,p,l) && !p,"browser resume changes only entry pause");
   Check(!GoldControlTransition("close_all",false,false,p,l) && !l,"disabled MT5 execution cannot falsely accept close all");
   Check(GoldControlTransition("close_all",false,true,p,l) && p && l,"close all pauses entries and starts liquidation");
   Check(!GoldControlTransition("resume",false,true,p,l) && p && l,"resume cannot interrupt ongoing liquidation");
   string command[7]={"GOLD_CONTROL_V1","instance_1","0123456789abcdef0123456789abcdef","100000","100010","pause","END"};
   Check(GoldControlValid(command,"instance_1","",100005),"account-instance command accepts valid bounded timestamp");
   Check(!GoldControlValid(command,"instance_2","",100005),"another EA instance cannot receive command");
   Check(!GoldControlValid(command,"instance_1",command[2],100005),"duplicate command ID cannot replay");
   Check(!GoldControlValid(command,"instance_1","",100011),"expired command cannot run later");
   Check(!GoldControlValid(command,"instance_1","",99990),"future command cannot run early");
   command[5]="reset_session";Check(GoldControlValid(command,"instance_1","",100005),"session reset uses authenticated expiring protocol");
   command[5]="buy";Check(!GoldControlValid(command,"instance_1","",100005),"browser protocol has no direct entry action");command[5]="pause";
   command[4]="100099";Check(!GoldControlValid(command,"instance_1","",100005),"unbounded command expiry rejected");
   string wire_command="GOLD_CONTROL_V1;instance_1;0123456789abcdef0123456789abcdef;100000;100010;pause;END\n";
   for(int variant=0;variant<2;variant++)
     {
      int cf=FileOpen("control-validation.csv",FILE_WRITE|FILE_TXT|FILE_ANSI,0,CP_UTF8);
      if(cf!=INVALID_HANDLE){FileWriteString(cf,wire_command+(variant==1?"extra;data\n":""));FileClose(cf);}
      cf=FileOpen("control-validation.csv",FILE_READ|FILE_CSV|FILE_ANSI,';',CP_UTF8);
      string parsed[];bool accepted=GoldReadControl(cf,parsed);
      if(cf!=INVALID_HANDLE)FileClose(cf);
      Check(variant==0?accepted && GoldControlValid(parsed,"instance_1","",100005):!accepted,"native control CSV exact-file round trip "+(string)variant);
     }
   FileDelete("control-validation.csv");
   GoldScalpEvidence e={};e.side=1;e.fast_pressure=1;e.slow_pressure=1;e.efficiency=1;e.slow_efficiency=1;e.rvol=1;
   e.m1=-1;e.m5=-1;e.m15=-1;e.h1=-1;
   Check(GoldScalpScore(e)>=62,"strong impulse can qualify against lagging higher timeframes");
   double neutral_advisor=GoldScalpScore(e);e.advisor=-1;
   Check(GoldScalpScore(e)<neutral_advisor,"fresh opposing advisor reduces evidence without unconditional veto");
   e.advisor=0;e.fast_pressure=.35;e.slow_pressure=.15;e.efficiency=.35;e.slow_efficiency=.20;
   Check(GoldScalpScore(e)<62,"weak momentum cannot qualify just because session is open");
   e.side=0;Check(GoldScalpScore(e)==0,"no direction means no scalp score");
   e.side=1;e.fast_pressure=1;e.slow_pressure=1;e.efficiency=1;e.slow_efficiency=1;e.rejected_candle=true;
   Check(GoldScalpScore(e)<62,"rejection candle penalizes a countertrend chase");
   GoldFlowRead f={},s={};f.ready=true;s.ready=true;f.direction=1;f.pressure=.8;f.move=.4;f.efficiency=.6;s.pressure=.5;s.efficiency=.4;
   Check(GoldScalpImpulse(1,f,s,.3),"scalp impulse can qualify without slow direction flag");
   s.pressure=-.4;Check(!GoldScalpImpulse(1,f,s,.3),"opposing slow flow prevents entry churn");
   s.pressure=.5;f.move=.1;Check(!GoldScalpImpulse(1,f,s,.3),"impulse must exceed spread-scaled noise");
   f.move=.4;f.ready=false;Check(!GoldScalpImpulse(1,f,s,.3),"missing fast feed cannot create entry");
   Check(GoldProfitGiveback(.66,1,.333333,.1,.35),"one-third net peak giveback closes winner");
   Check(!GoldProfitGiveback(.8,1,.333333,.1,.35),"small pullback holds the runner");
   Check(!GoldProfitGiveback(.05,.2,.333333,.1,.35),"tiny unarmed profit cannot trigger noise exit");
   Check(!GoldProfitGiveback(.3,.4,.333333,.25,.35),"high-noise market delays arming");
   Check(GoldProfitGiveback(-.1,1,.333333,.1,.35),"gap through retained profit still requests exit");
   Check(MathAbs(GoldRetainedProfit(3,1./3.,.1)-2)<1e-8,"three dollars peak protects two before execution slippage");
   Check(MathAbs(GoldRetainedProfit(.5,1./3.,.2)-.3)<1e-8,"noise floor avoids excessively tight percentage trail");
   Check(GoldSessionAdjustment(19,10,10)==0,"session adaptation waits for twenty completed positions");
   Check(GoldSessionAdjustment(20,20,20)==-4,"consistent positive session modestly reduces entry threshold");
   Check(GoldSessionAdjustment(20,-20,20)==8,"consistent negative session raises threshold");
   Check(GoldSessionAdjustment(20,1,100)==0,"uncertain session outcomes cannot claim an edge");
   Check(GoldSessionBucket(D'2026.09.29 06:59')==0 && GoldSessionBucket(D'2026.09.29 07:00')==1,"Asia to London UTC boundary");
   Check(GoldSessionBucket(D'2026.09.29 12:00')==2 && GoldSessionBucket(D'2026.09.29 16:00')==3,"overlap to NY UTC boundary");
   Check(GoldSessionBucket(D'2026.09.29 21:00')==3 && GoldSessionBucket(D'2026.09.29 23:00')==3 && GoldSessionBucket(D'2026.09.30 00:00')==0,"late hours and Asia retain valid adaptive buckets");
   Check(GoldBucketEntriesAllowed(3,false) && GoldBucketEntriesAllowed(3,true),"late hours allow entries when the broker session is open");
   Check(GoldBucketEntriesAllowed(0,false) && !GoldBucketEntriesAllowed(0,true),"Asia is allowed by default and can be explicitly restricted");
   Check(GoldBucketEntriesAllowed(1,false) && GoldBucketEntriesAllowed(2,false) && GoldBucketEntriesAllowed(3,false),"all non-Asia buckets allow entries");
   Check(!GoldBucketEntriesAllowed(-1,true) && !GoldBucketEntriesAllowed(4,true) && !GoldBucketEntriesAllowed(-1,false),"unknown bucket cannot open entries");
   Check(GoldScalpWindowAllowed(3,-1,-1) && GoldScalpWindowAllowed(20,-1,-1),"disabled scalp window allows every hour");
   Check(GoldScalpWindowAllowed(7,7,16) && GoldScalpWindowAllowed(15,7,16) && !GoldScalpWindowAllowed(6,7,16) && !GoldScalpWindowAllowed(16,7,16),"scalp entry window 07-16 UTC applies exact boundaries");
   Check(GoldUnifiedScheduleAllowed(0,"exclude_window",22,23) && GoldUnifiedScheduleAllowed(21,"exclude_window",22,23) && !GoldUnifiedScheduleAllowed(22,"exclude_window",22,23) && GoldUnifiedScheduleAllowed(23,"exclude_window",22,23),"dashboard schedule excludes 22:00-23:00 UTC only");
   Check(!GoldUnifiedScheduleAllowed(5,"exclude_window",5,5) && !GoldUnifiedScheduleAllowed(24,"all_day",-1,-1),"invalid dashboard schedule fails closed");
   Check(GoldSessionCloseDue(true,1000,700) && !GoldSessionCloseDue(true,1000,699) && !GoldSessionCloseDue(false,1000,700) && !GoldSessionCloseDue(true,1000,1000),"scheduled close window begins exactly five minutes before close");
   Check(GoldSessionPositionTarget("XAUUSD","XAUUSD") && !GoldSessionPositionTarget("EURUSD","XAUUSD") && !GoldSessionPositionTarget("XAUUSD.a","XAUUSD"),"pre-close rule is restricted to the attached XAUUSD symbol");
   for(int b=0;b<4;b++)Check(GoldRecordedSession("ScalperExpert326:S"+(string)b)==b,"order comment retains exact UTC session bucket");
   Check(GoldRecordedSession("ScalperExpert326:Sx")==-1 && GoldRecordedSession("ScalperExpert326:S")==-1 && GoldRecordedSession("ScalperExpert326:S30")==-1 && GoldRecordedSession("ScalperExpert325:S1")==-1 && GoldRecordedSession("ScalperExpert324:S1")==-1 && GoldRecordedSession("ScalperExpert323:S1")==-1,"invalid or old-policy broker comment cannot contaminate session history");
   Check(GoldRecordedSession("ScalperExpert320:S0")==-1,"prior policy results cannot tune current policy's session frequency");
   Check(GoldRecordedSession("ScalperExpert3:S3")==-1,"old policy outcomes remain in account risk but cannot bias current session adaptation");
   Check(MathAbs(GoldAffordableStop(3,.8,2,.1,.05,1)-1.8)<1e-8,"ATR stop capped by fixed-lot dollar risk");
   Check(GoldAffordableStop(3,2,2,.1,.05,1)==0,"unaffordable structural stop rejects trade");
   Check(GoldAffordableStop(1,.5,2,.1,.05,0)==0,"missing money conversion rejects stop sizing");
   datetime wire_stamp=(datetime)1790668800;
   Check(GoldEpoch(wire_stamp)=="1790668800","wire datetime is integer epoch, never formatted date");
   MqlRates wire_rate={};wire_rate.time=wire_stamp;wire_rate.open=4100;wire_rate.high=4102;wire_rate.low=4099;wire_rate.close=4101;wire_rate.tick_volume=7;
   string wire_json=GoldRateJson(wire_rate);
   Check(StringFind(wire_json,"\"time\":1790668800,")==1,"candle JSON emits a valid numeric timestamp");
   Check(GoldJson("a\"b\\c\n")=="\"a\\\"b\\\\c\\u000a\"","wire strings escape quotes slash and control characters");
   datetime wire_events[1];wire_events[0]=wire_stamp+60;
   string wire_news=GoldNewsLine("TEST",wire_stamp,wire_events);
   Check(wire_news=="GOLD_NEWS_V1;TEST;1790668800;1;1790668860;END\r\n","calendar CSV emits numeric epochs");
   // Export the actual native serializer output for a Python JSON-parser regression.
   string wire_dir="GoldScalp\\validation";FolderCreate("GoldScalp");FolderCreate(wire_dir);
   int wire_file=FileOpen(wire_dir+"\\wire-fixture.json",FILE_WRITE|FILE_TXT|FILE_ANSI,0,CP_UTF8);
   Check(wire_file!=INVALID_HANDLE,"native wire fixture opens");
   if(wire_file!=INVALID_HANDLE){FileWriteString(wire_file,wire_json);FileClose(wire_file);}
   wire_file=FileOpen(wire_dir+"\\news-fixture.csv",FILE_WRITE|FILE_TXT|FILE_ANSI,0,CP_UTF8);
   if(wire_file!=INVALID_HANDLE){FileWriteString(wire_file,wire_news);FileClose(wire_file);}
   CGoldNewsCache wire_cache;
   Check(wire_cache.Load(wire_dir+"\\news-fixture.csv","TEST",false) && wire_cache.Fresh(wire_stamp) && wire_cache.Active(wire_stamp,10,5),"calendar serializer round-trips through production freshness and event gates");
   Check(MathAbs(GoldRound(1.023,.01,true)-1.03)<1e-9,"round upward to tick");
   Check(MathAbs(GoldRound(1.023,.01,false)-1.02)<1e-9,"round downward to tick");
   Check(GoldVolumeValid(.01,.01,1.,.01),"fixed lot supported");
   Check(!GoldVolumeValid(.01,.1,1.,.1),"broker minimum cannot round lot upward");
   Check(!GoldVolumeValid(.01,.001,1.,.003),"incompatible volume step rejected");
   Check(GoldHourAllowed(13,13,16) && !GoldHourAllowed(16,13,16),"session right boundary excluded");
   Check(GoldHourAllowed(0,22,3) && !GoldHourAllowed(12,22,3),"overnight session");
   Check(!GoldCostFits(.4,1.,.25) && GoldCostFits(.2,1.,.25),"cost opportunity gate");
   CGoldFlow up,down,widen;Feed(up,1);Feed(down,2);Feed(widen,3);
   GoldFlowRead a=up.Read(112000,12),b=down.Read(112000,12),wide=widen.Read(112000,12);
   Check(a.ready && a.direction==1 && a.efficiency>.99,"rising two-sided executable quotes");
   Check(b.ready && b.direction==-1,"falling two-sided executable quotes");
   Check(wide.ready && wide.direction==0,"ask-only spread widening is not buying flow");
   a=up.Read(115000,12);Check(!a.ready,"stale flow is unusable");
   MqlTick gap={};gap.bid=2502;gap.ask=2502.2;gap.time_msc=130000;up.Add(gap);
   a=up.Read(130000,12);Check(!a.ready,"gap clears warmed flow");
   gap.time_msc=129000;Check(!up.Add(gap),"out-of-order quote rejected");
   gap.time_msc=131000;gap.ask=gap.bid-1;Check(!up.Add(gap),"crossed quote rejected");
   CGoldOnlineModel model;double x[GOLD_FEATURES]={1,1,.3,.2,.1};
   Check(model.Samples()==0 && MathAbs(model.Predict(x)-.5)<1e-9,"untrained prediction neutral");
   for(int i=0;i<30;i++)model.Observe(100000+i*1000,2500+i*.01,x);
   Check(model.Samples()==0,"future labels unavailable before maturity");
   model.Observe(130000,2500.3,x);Check(model.Samples()==1,"label matures causally after 30 seconds");
   Check(model.Predict(x)>.5 && !model.FilterReady(),"learns direction without early activation");
   int before=model.Samples();model.Observe(140000,2501,x);
   Check(model.Samples()==before,"observation outage cannot mature queued labels");
   CGoldOnlineModel flat;
   for(int i=0;i<=30;i++)flat.Observe(100000+i*1000,2500,x);
   Check(flat.Samples()==1 && MathAbs(flat.Predict(x)-.5)<1e-9,"unchanged prices retained as neutral labels");
   GoldExitContext c={};c.risk=1;c.spread=.1;c.cost_buffer=.2;c.commission=.1;c.move=.5;c.peak=.5;c.profit=.4;c.opposing=true;
   Check(GoldChooseExit(c,.4,.35,.6,2,1200)==GOLD_TAKE_REVERSAL,"profitable reversal exits before any TP");
   c.move=-.3;c.profit=-.3;c.peak=0;c.adverse_seconds=1;
   Check(GoldChooseExit(c,.4,.35,.6,2,1200)==GOLD_HOLD,"one adverse second does not churn a losing position");
   c.adverse_seconds=2;
   Check(GoldChooseExit(c,.4,.35,.6,2,1200)==GOLD_EXIT_REVERSAL,"confirmed adverse flow closes a loss before SL");
   c.opposing=false;c.peak=.9;c.move=.5;c.fast_ready=true;c.fast_pressure=-.1;
   Check(GoldChooseExit(c,.4,.35,.6,2,1200)==GOLD_GIVEBACK,"giveback with opposing flow protects excursion");
   c.fast_ready=false;c.move=.1;
   Check(GoldChooseExit(c,.4,.35,.6,2,1200)==GOLD_BANK,"breakeven fallback survives unavailable flow");
   c.peak=0;c.move=-.1;c.held_seconds=1200;
   Check(GoldChooseExit(c,.4,.35,.6,2,1200)==GOLD_STAGNATION,"stagnant trade times out");
   CGoldSpreadWindow spread;
   for(int i=0;i<49;i++)spread.Add(.2);
   Check(!spread.Allows(.2,1.5),"spread gate waits for fifty observations");
   spread.Add(.2);Check(spread.Allows(.3,1.5),"spread equality boundary is allowed");
   Check(!spread.Allows(.301,1.5),"candidate spike tested against prior baseline");
   spread.Add(2.);Check(MathAbs(spread.Mean()-.236)<1e-8,"spread rolling sum replaces one sample");
   for(int i=0;i<100;i++)spread.Add(.1);
   Check(MathAbs(spread.Mean()-.1)<1e-8,"spread ring forgets old spike");
   spread.Reset();Check(spread.Count()==0 && !spread.Allows(.1,1.5),"feed gap resets spread warm-up");
   MqlRates trap={};trap.open=100;trap.high=103;trap.low=99;trap.close=100.5;
   GoldCandleShape shape=GoldShape(trap,102,98);
   Check(shape.reject_buy && !shape.reject_sell,"upper sweep rejected for buys only");
   trap.open=100;trap.high=101;trap.low=97;trap.close=99.5;shape=GoldShape(trap,102,98);
   Check(shape.reject_sell && !shape.reject_buy,"lower sweep rejected for sells only");
   Check(GoldAligned(1,1,1,1) && GoldAligned(-1,-1,-1,-1),"all higher timeframes must agree");
   Check(!GoldAligned(1,1,1,-1) && !GoldAligned(1,1,0,1),"H1 disagreement and neutral M15 veto entry");
   Check(GoldLiveATR(2,14,104,100,100)>2,"live true range increases adaptive volatility");
   Check(MathAbs(GoldSlippage(.3,20,.05,.1)-.1)<1e-8,"dynamic slippage never exceeds cap");
   Check(MathAbs(GoldSlippage(.01,.1,.05,.1)-.05)<1e-8,"dynamic slippage respects minimum");
   Check(GoldShock(2500,2505,2,.2,2) && !GoldShock(2500,2501,2,.2,2),"price shock threshold");
   Check(GoldAdaptiveArm(1,.4,.6,.5,.1)<.6,"breakeven reacts when volatility contracts");
   Check(GoldAdaptiveArm(1,.1,.6,.5,.3)>=.3,"adaptive arming still covers costs");
   Check(MathAbs(GoldDailyReference(150,50,50)-150)<1e-8,"deposit is not trading profit");
   Check(MathAbs(GoldDailyReference(80,-20,-20)-80)<1e-8,"withdrawal is not a trading loss");
   Check(MathAbs(GoldDailyReference(97,-3,0)-100)<1e-8,"realized daily loss retains opening reference");
   Check(GoldEquityBreached(100,97,3) && !GoldEquityBreached(100,97.01,3),"three percent equity boundary");
   Check(!GoldEquityBreached(0,0,3),"invalid capital reference cannot trigger percentage loss");
   Check(!GoldEquityBreached(100,50,0),"zero disables daily equity protection");
   Check(!GoldBudgetIncludes(1000,2000,1500) && GoldBudgetIncludes(1500,2000,1500),"session reset excludes old deals and includes new boundary");
   Check(!GoldBudgetIncludes(1000,90000,0),"loss session retains rolling 24-hour horizon");
   CGoldSafety manual;manual.Init("SELFTEST_MANUAL_",false,100);manual.LossTrip();
   Check(manual.Locked(999999) && manual.loss_locked,"loss stop never auto-resumes");
   manual.ResetSession();Check(!manual.Locked(999999) && !manual.loss_locked,"explicit session reset clears loss stop");
   CGoldSafety safety;safety.Init("TEST_",false,100);safety.Observe(98);
   Check(MathAbs(safety.current_drawdown-2)<1e-8,"current observed equity drawdown");
   safety.Observe(105);safety.Observe(99.75);Check(MathAbs(safety.max_drawdown-5)<1e-8,"maximum drawdown follows equity peak");
   safety.Funding(50);safety.Observe(149.75);Check(safety.max_drawdown>=5 && safety.current_drawdown<5,"funding adjusts high-water mark");
   safety.Trip(100000,"test");Check(safety.Locked(186399) && !safety.Locked(186400),"safety pause lasts exactly 24 hours");
   safety.Trip(100100,"repeat");Check(safety.locked_until==186400,"repeated triggers do not slide pause expiry");
   CGoldRequests requests;MqlTradeRequest request={};request.action=TRADE_ACTION_DEAL;request.volume=.01;
   int slot=requests.Reserve(request,1000,"test");Check(slot>=0 && requests.EntryBlocked(),"in-flight entry reserves a slot");
   Check(requests.Reserve(request,1001,"duplicate")<0,"duplicate entry blocked before broker response");
   requests.Response(slot,TRADE_RETCODE_REQUOTE,1100);
   Check(requests.items[slot].state==GOLD_REQUEST_RETRY && requests.items[slot].due_ms==1250,"requote schedules nonblocking bounded retry");
   requests.Response(slot,TRADE_RETCODE_PRICE_CHANGED,1300);requests.Response(slot,TRADE_RETCODE_REQUOTE,1600);
   Check(!requests.EntryBlocked(),"third rejected attempt ends retry chain");
   slot=requests.Reserve(request,2000,"ambiguous");requests.Response(slot,TRADE_RETCODE_TIMEOUT,2100);
   Check(requests.EntryBlocked() && requests.items[slot].state==GOLD_REQUEST_UNKNOWN,"timeout never authorizes duplicate entry");
   CGoldRequests accepted;slot=accepted.Reserve(request,1000,"accepted");accepted.Response(slot,TRADE_RETCODE_PLACED,1100);
   Check(accepted.items[slot].state==GOLD_REQUEST_WAIT && !accepted.uncertain_entry,"accepted request remains pending rather than failed");
   accepted.items[slot].request_id=42;Check(accepted.Find(42)==slot && accepted.Find(43)<0,"callbacks match request id");
   accepted.Response(slot,TRADE_RETCODE_DONE_PARTIAL,1200);Check(!accepted.EntryBlocked(),"partial entry is never topped up automatically");
   CGoldRequests stalled;slot=stalled.Reserve(request,1000,"stalled");stalled.Expire(9000);
   Check(stalled.uncertain_entry,"missing async acknowledgement latches uncertainty");
   CGoldRequests closes;request.position=777;slot=closes.Reserve(request,1000,"exit");closes.Clear(slot);
   Check(closes.Reserve(request,1100,"exit flood")<0 && closes.Reserve(request,1500,"next exit")>=0,"failed closes cannot flood every tick");
   Check(!GoldRetryable(TRADE_RETCODE_TIMEOUT) && !GoldRetryable(TRADE_RETCODE_INVALID_STOPS),"only definite price rejection is retried");
   CGoldAdvisorReference advisor;string fields[11]={"GOLD_ADVISOR1_V1","100000","100300","XAUUSD","BUY","BUY","80","2500","2500.2","SCALP","END"};
   Check(advisor.Parse(fields) && advisor.Allows(1,100020,"XAUUSD",90),"unchanged Advisor 1 signal can confirm entry");
   Check(!advisor.Allows(-1,100020,"XAUUSD",90),"Advisor 1 disagreement blocks required mode");
   Check(!advisor.Fresh(100091,"XAUUSD",90),"re-copying old reports cannot refresh their timestamp");
   Check(!advisor.Fresh(99990,"XAUUSD",90),"future reference cannot leak into a backtest");
   Check(!advisor.Fresh(100020,"XAUUSD.other",90),"reference must match exact broker symbol");
   fields[10]="BROKEN";Check(!advisor.Parse(fields),"truncated or malformed reference fails closed");
   string replay_name="GoldScalpSelfTest_replay.csv";
   int fixture=FileOpen(replay_name,FILE_WRITE|FILE_CSV|FILE_ANSI,';',CP_UTF8);
   Check(fixture!=INVALID_HANDLE,"local replay fixture opens");
   if(fixture!=INVALID_HANDLE)
     {
      FileWrite(fixture,"GOLD_ADVISOR1_V1",100000,100300,"XAUUSD","BUY","BUY",80,2500,2500.2,"SCALP","END");
      FileWrite(fixture,"GOLD_ADVISOR1_V1",100050,100350,"XAUUSD","SELL","SELL",82,2500,2500.2,"SCALP","END");FileClose(fixture);
      CGoldAdvisorReference replay;
      Check(!replay.Replay(replay_name,99999,false),"replay starts without leaking its first future observation");
      Check(replay.Replay(replay_name,100020,false) && replay.action=="BUY","replay exposes only the most recent available report");
      Check(replay.Replay(replay_name,100060,false) && replay.action=="SELL","replay advances when the next report becomes available");
      Check(replay.Replay(replay_name,100020,false) && replay.action=="BUY","a rewound test resets the replay cursor");
      replay.Replay(replay_name,100400,false);Check(!replay.Fresh(100400,"XAUUSD",90),"end-of-file report expires rather than extending its validity");
      replay.CloseReplay();FileDelete(replay_name);
     }
   fixture=FileOpen(replay_name,FILE_WRITE|FILE_CSV|FILE_ANSI,';',CP_UTF8);
   Check(fixture!=INVALID_HANDLE,"large replay fixture opens");
   if(fixture!=INVALID_HANDLE)
     {
      for(int i=0;i<=500;i++)FileWrite(fixture,"GOLD_ADVISOR1_V1",100000+i,100900,"XAUUSD","BUY","BUY",80,2500,2500.2,"SCALP","END");
      FileClose(fixture);CGoldAdvisorReference bounded;
      Check(!bounded.Replay(replay_name,100500,false) && !bounded.Fresh(100500,"XAUUSD",90),"bounded replay cannot expose a report before catching up");
      Check(bounded.Replay(replay_name,100500,false) && bounded.Fresh(100500,"XAUUSD",90) && bounded.generated==100500,"bounded replay resumes without losing its last valid observation");
      bounded.CloseReplay();FileDelete(replay_name);
     }
   ulong start=GetMicrosecondCount();CGoldSpreadWindow bench;
   for(int i=0;i<100000;i++){bench.Allows(.2,1.5);bench.Add(.2);}
   PrintFormat("MICROBENCH spread_window iterations=100000 elapsed_us=%I64u final_mean=%.3f (synthetic invariant benchmark, not market performance)",GetMicrosecondCount()-start,bench.Mean());
   GoldReplayDiagnostic();
   PrintFormat("GOLD_SELF_TEST checks=%d failures=%d",checks,failures);
   return failures==0?INIT_SUCCEEDED:INIT_FAILED;
  }
void OnTick(){}
double OnTester(){return failures==0?checks:-failures;}
