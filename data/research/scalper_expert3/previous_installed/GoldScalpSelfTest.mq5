#property strict
#property version "2.00"
#include "GoldScalpMath.mqh"
#include "GoldScalpFlow.mqh"
#include "GoldScalpLearning.mqh"
#include "GoldScalpExit.mqh"
#include "GoldScalpMarket.mqh"
#include "GoldScalpSafety.mqh"
#include "GoldScalpExecution.mqh"
#include "GoldScalpFeeds.mqh"
#include "GoldScalpWire.mqh"
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
   for(int i=0;i<99;i++)spread.Add(.2);
   Check(!spread.Allows(.2,1.5),"spread gate waits for one hundred observations");
   spread.Add(.2);Check(spread.Allows(.3,1.5),"spread equality boundary is allowed");
   Check(!spread.Allows(.301,1.5),"candidate spike tested against prior baseline");
   spread.Add(2.);Check(MathAbs(spread.Mean()-.218)<1e-8,"spread rolling sum replaces one sample");
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
   PrintFormat("GOLD_SELF_TEST checks=%d failures=%d",checks,failures);
   return failures==0?INIT_SUCCEEDED:INIT_FAILED;
  }
void OnTick(){}
double OnTester(){return failures==0?checks:-failures;}
