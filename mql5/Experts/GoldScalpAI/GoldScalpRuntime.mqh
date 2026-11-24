#ifndef GOLD_SCALP_RUNTIME
#define GOLD_SCALP_RUNTIME
void SaveControls()
  {
   if(MQLInfoInteger(MQL_TESTER) || !owns_lock || prefix=="")return;
   GlobalVariableSet(prefix+"PAUSED",paused?1:0);GlobalVariableSet(prefix+"CLOSE_ALL",close_all_requested?1:0);GlobalVariablesFlush();
  }
void ProtectAccount()
  {
   double equity=AccountInfoDouble(ACCOUNT_EQUITY);
   bool capital_stable=Stats.capital>0 && MathAbs(AccountInfoDouble(ACCOUNT_BALANCE)+AccountInfoDouble(ACCOUNT_CREDIT)-Stats.capital)<.001;
   if(capital_stable)Safety.Observe(equity); // funding is reconciled before moving the high-water mark
   if(capital_stable && Safety.reference>0)
     {
      if(DailyEquityLossPercent>0 && GoldEquityBreached(Safety.reference,equity,DailyEquityLossPercent))Safety.Trip(ServerNow(),"Equity journaliere : seuil -"+DoubleToString(DailyEquityLossPercent,1)+"%");
      if(Stats.ready && Stats.budget_net+FloatingOwned()<=-MathMin(50.,RollingLossLimitUSD))Safety.LossTrip();
     }
   if(Safety.Locked(ServerNow())){Requests.CancelEntryRetries();DrainOwnedForSafety();}
  }
#include "GoldScalpControls.mqh"
bool EntryEnvironment(const MqlTick &q)
  {
   if(!ValidQuote(q)){status="Cotation absente ou perimee";return false;}
   if(paused || close_all_requested){status="Pause entrees / liquidation compte";return false;}
   if(Safety.Locked(ServerNow())){status=Safety.reason;return false;}
   if(ServerNow()<Stats.budget_start){status="Starting new loss session";return false;}
   if(!ExposureReady()){status="Synchronisation historique / solde";return false;}
   if(!Market.Fresh(TimeCurrent())){status="Attente indicateurs M1/M5/M15/H1";return false;}
   if(!cached_session)
     {
      int gate_bucket=GoldSessionBucket(GoldUTCNow());MqlDateTime gate_utc;TimeToStruct(GoldUTCNow(),gate_utc);
      if(GoldSessionCloseDue(BrokerSessionState.scheduled_open,BrokerSessionState.active_close,ServerNow()))status="Broker close within five minutes; new entries disabled";
      else if(!ExpertScalpMode)status="Hors session UTC ou marche ferme";
      else if(gate_bucket==0 && BlockAsiaSession)status="SCALP: Asia entries disabled by input";
      else if(!GoldScalpWindowAllowed(gate_utc.hour,ScalpEntryStartUTC,ScalpEntryEndUTC))status="SCALP: outside entry window "+(string)ScalpEntryStartUTC+"-"+(string)ScalpEntryEndUTC+" UTC";
      else if(!GoldUnifiedScheduleAllowed(gate_utc.hour,UnifiedScheduleMode,UnifiedBlockedStartUTC,UnifiedBlockedEndUTC))status="Dashboard UTC blackout: "+(string)UnifiedBlockedStartUTC+":00-"+(string)UnifiedBlockedEndUTC+":00";
      else status="SCALP: broker closed";
      return false;
     }
   if(!NewsFresh()){status="Filtre news : flux absent/perime";return false;}
   if(cached_news_active){status="Filtre news : annonce USD majeure";return false;}
   if(TimeCurrent()<loss_pause_until){status="Loss cooldown: "+(string)(loss_pause_until-TimeCurrent())+" s remaining | streak "+(string)loss_streak;return false;}
   if(entries_hour>=MaxEntriesPerHour){status="Hourly entry cap: "+(string)entries_hour+" / "+(string)MaxEntriesPerHour;return false;}
   double spread=q.ask-q.bid;
   if(spread>MaxSpreadPrice || spread/atr>MaximumSpreadATR || !relative_spread_ok || spread>spread_before*SpreadAverageMultiplier+1e-9)
     {status=SpreadWindow.Count()<50?"Initialisation spread : 50 observations":"Filtre spread absolu / glissant actif";return false;}
   if(!volatility_ok){status="Filtre volatilite / volume relatif actif";return false;}
   return true;
  }
string GoldFlowDiagnostic(const string label,const GoldFlowRead &flow)
  {
   return label+" "+(flow.ready?"ready":"not-ready")+" n="+(string)flow.count+
      " span="+DoubleToString(flow.seconds,1)+"s age="+(string)flow.age_milliseconds+"ms"+
      " p="+DoubleToString(flow.pressure,2)+" eff="+DoubleToString(flow.efficiency,2)+
      " move="+DoubleToString(flow.move,3);
  }
bool SignalAllows(const int side,const MqlTick &q,string &reason)
  {
   signal_grace_eligible=false;
   if(ExpertScalpMode)
     {
      scalp_threshold=MinimumScalpScore+SessionAdjustment();scalp_score=0;acceleration_bonus=0;macro_bonus=0;
      trend_entry_lane=false;
      bool impulse=GoldScalpImpulse(side,last_fast,last_slow,q.ask-q.bid,FrequentEntryMode);
      bool continuation=UseTrendContinuation && GoldTrendScalpImpulse(side,last_fast,last_slow,last_context,q.ask-q.bid,Market.direction[0],Market.direction[1]);
      if(q.time_msc<flow_snapshot_msc || q.time_msc-flow_snapshot_msc>1000 || (!impulse && !continuation))
        {reason="SCALP: waiting for 3/8 s impulse or aligned 20 s continuation | "+
           GoldFlowDiagnostic("3s",last_fast)+" | "+GoldFlowDiagnostic("8s",last_slow)+" | "+GoldFlowDiagnostic("20s",last_context);return false;}
      trend_entry_lane=!impulse && continuation;
      if(UseCounterflowGuard && GoldCounterflowTrap(side,last_slow,last_context,q.ask-q.bid,atr))
        {reason="SCALP: brief bounce against 20 s flow; waiting for an 8 s reversal";return false;}
      if(trend_entry_lane)scalp_threshold+=4; // slower context needs stronger total evidence
      GoldScalpEvidence evidence={};evidence.side=side;
      evidence.fast_pressure=trend_entry_lane?last_context.pressure:last_fast.pressure;evidence.slow_pressure=last_slow.pressure;
      evidence.efficiency=trend_entry_lane?last_context.efficiency:last_fast.efficiency;evidence.slow_efficiency=last_slow.efficiency;
      evidence.m1=Market.direction[0];evidence.m5=Market.direction[1];evidence.m15=Market.direction[2];evidence.h1=Market.direction[3];
      evidence.rvol=Market.rvol;evidence.rejected_candle=side>0?Market.shape.reject_buy:Market.shape.reject_sell;
      bool fresh=Advisor1.Fresh(GoldUTCNow(),_Symbol,Advisor1MaxAgeSeconds);
      if(fresh && Advisor1.score>=60)evidence.advisor=Advisor1.action=="BUY"?1:Advisor1.action=="SELL"?-1:0;
      acceleration_bonus=UseImpulseAcceleration?GoldAccelerationBonus(side,last_fast.velocity,last_slow.velocity,q.ask-q.bid):0;
      macro_bonus=Macro.Evidence(side,ServerNow(),(q.bid+q.ask)*.5,q.ask-q.bid);
      intelligence_adjustment=UseMarketIntelligence?Intelligence.Adjustment(side):0;
      if(UseMarketIntelligence && IntelligenceVetoAbnormal && Intelligence.ready && Intelligence.veto)
        {reason="SCALP: intelligence abnormal-volatility veto";return false;}
      scalp_score=GoldClamp(GoldScalpScore(evidence)+acceleration_bonus+macro_bonus+intelligence_adjustment,0,100);
      if((side>0 && bar_high>Market.previous_high && q.bid<Market.previous_high && bar_high-q.bid>=.35*atr) ||
         (side<0 && bar_low<Market.previous_low && q.bid>Market.previous_low && q.bid-bar_low>=.35*atr))
        {reason="SCALP: live failed breakout / liquidity sweep";return false;}
      if(MathAbs((q.bid+q.ask)*.5-ema_fast)>1.8*atr){reason="SCALP: extended move, waiting for pullback";return false;}
      if(Advisor1Mode==GOLD_ADVISOR_REQUIRED && !Advisor1.Allows(side,GoldUTCNow(),_Symbol,Advisor1MaxAgeSeconds))
        {reason="Advisor 1: required approval unavailable";return false;}
      if(UseLearnedVeto && (!Learner.FilterReady() || (side>0?last_prediction<.55:last_prediction>.45)))
        {reason="Statistical veto / insufficient validation";return false;}
      // Grace applies only to a small score dip after all structural and feed
      // checks have passed; it cannot bridge a failed breakout or a hard veto.
      signal_grace_eligible=scalp_score>=scalp_threshold-4;
      if(scalp_score<scalp_threshold){reason="SCALP: evidence "+DoubleToString(scalp_score,1)+" / required "+DoubleToString(scalp_threshold,1);return false;}
      return true;
     }
   if(side==0 || q.time_msc-flow_snapshot_msc>1000 || !last_fast.ready || !last_slow.ready || last_fast.direction!=side || last_slow.direction!=side)
     {reason="Attente confirmation du flux 6/12 s";return false;}
   if(Market.direction[0]!=side || !GoldAligned(side,Market.direction[1],Market.direction[2],Market.direction[3]) || side*(ema_fast-ema_slow)<=.08*atr)
     {reason="M1/M5/M15/H1 non alignes";return false;}
   if((side>0 && Market.shape.reject_buy) || (side<0 && Market.shape.reject_sell))
     {reason="Rejet de meche / faux breakout cloture";return false;}
   if((side>0 && bar_high>Market.previous_high && q.bid<Market.previous_high && bar_high-q.bid>=.25*atr) ||
      (side<0 && bar_low<Market.previous_low && q.bid>Market.previous_low && q.bid-bar_low>=.25*atr))
     {reason="Balayage de liquidite intrabougie";return false;}
   if(MathAbs((q.bid+q.ask)*.5-ema_fast)>1.2*atr){reason="Prix trop etendu / entree tardive";return false;}
   datetime utc=GoldUTCNow();
   if(Advisor1Mode==GOLD_ADVISOR_REQUIRED && !Advisor1.Allows(side,utc,_Symbol,Advisor1MaxAgeSeconds))
     {reason="Advisor 1 : attente accord SCALP frais";return false;}
   if(Advisor1Mode==GOLD_ADVISOR_REQUIRED && MathAbs((q.bid+q.ask-Advisor1.bid-Advisor1.ask)*.5)>.75*atr)
     {reason="Prix trop eloigne de la reference Advisor 1";return false;}
   if(UseLearnedVeto && (!Learner.FilterReady() || (side>0?last_prediction<.55:last_prediction>.45)))
     {reason="Veto statistique / validation insuffisante";return false;}
   return true;
  }
void ProcessTick(const bool service_account_safety=true)
  {
   if(service_account_safety){ProtectAccount();if(close_all_requested)DrainAccountForCloseAll();}
   MqlTick q;if(!SymbolInfoTick(_Symbol,q) || !ValidQuote(q)){EntryConfirmation.Reset();signal_side=0;signal_since=0;status="Cotation absente ou perimee";return;}
   if(q.time_msc<last_quote_msc || (q.time_msc==last_quote_msc && q.bid==last_bid && q.ask==last_ask))return;
   int previous_side=signal_side;datetime previous_since=signal_since;long previous_since_msc=signal_since_msc;
   long gap=q.time_msc-last_quote_msc;
   if(last_quote_msc>0 && gap>2000){EntryConfirmation.Reset();previous_side=0;previous_since=0;previous_since_msc=0;Rotation.Clear();for(int i=0;i<ArraySize(managed);i++){managed[i].adverse_since=0;managed[i].micro_adverse_since=0;}}
   if(last_quote_msc>0 && gap>8000)SpreadWindow.Reset();
   signal_side=0;signal_since=0;signal_since_msc=0;last_quote_msc=q.time_msc;last_bid=q.bid;last_ask=q.ask;quote_count++;
   double mid=(q.bid+q.ask)*.5,spread=q.ask-q.bid;
   if(prior_mid>0 && GoldShock(prior_mid,mid,atr,spread,ShockATRMultiple) && PositionsTotal()>0)
     {Safety.Trip(ServerNow(),"Mouvement anormal : protection compte");DrainOwnedForSafety();}
   prior_mid=mid;
   datetime current=(datetime)(q.time_msc/60000*60);
   if(current!=live_bar){live_bar=current;bar_high=q.bid;bar_low=q.bid;}
   else {bar_high=MathMax(bar_high,q.bid);bar_low=MathMin(bar_low,q.bid);}
   live_atr=GoldLiveATR(atr,ATRPeriod,bar_high,bar_low,bar_close);
   spread_before=SpreadWindow.Mean();relative_spread_ok=SpreadWindow.Allows(spread,SpreadAverageMultiplier);SpreadWindow.Add(spread);
   if(Flow.Add(q)){last_micro=Flow.Read(q.time_msc,1);last_fast=Flow.Read(q.time_msc,ExpertScalpMode?3:6);last_slow=Flow.Read(q.time_msc,ExpertScalpMode?8:12);last_context=Flow.Read(q.time_msc,20);flow_snapshot_msc=q.time_msc;}
   // Safety and exits run even during pause, spread/news blocks and indicator warm-up.
   if(!Safety.Locked(ServerNow()) && !close_all_requested)ManagePositions(q,last_fast,last_slow);
   if(Market.Fresh(TimeCurrent()) && last_fast.ready && last_slow.ready)
     {
      double x[GOLD_FEATURES];x[0]=last_fast.pressure;x[1]=last_slow.pressure;x[2]=(ema_fast-ema_slow)/atr;
      x[3]=(bar_close-ema_slow)/atr;x[4]=spread/atr;
      Learner.Observe(q.time_msc,mid,x);last_prediction=Learner.Predict(x);
     }
   // Analyze continuously, including during a safety pause. This does not arm
   // persistence or submit orders: every execution gate remains below.
   int side=last_fast.direction!=0?last_fast.direction:ExpertScalpMode && FrequentEntryMode && last_fast.ready && last_fast.efficiency>=.30 && MathAbs(last_fast.pressure)>=.20?(last_fast.pressure>0?1:-1):ExpertScalpMode && UseTrendContinuation?last_context.direction:0;bool candidate=false;
   scalp_analysis="Waiting for fresh market indicators";scalp_score=0;acceleration_bonus=0;macro_bonus=0;
   if(Market.Fresh(TimeCurrent()))
     {
      scalp_analysis="Candidate impulse: awaiting persistence and execution checks";
      candidate=SignalAllows(side,q,scalp_analysis);
     }
   scalp_analysis_msc=q.time_msc;
   if(!EntryEnvironment(q)){EntryConfirmation.Reset();return;}
   bool coherent=signal_grace_eligible && side!=0 && last_fast.ready && last_slow.ready && side*last_fast.pressure>=-.10 && side*last_slow.pressure>=.10;
   bool grace_ready=false;
   if(ExpertScalpMode && UseConfirmationGrace)
     {
      // Only distinct sampled quotes count, so repeated OnTick calls cannot
      // fabricate confirmation. The latest sample must still pass every signal filter.
      grace_ready=EntryConfirmation.Observe(flow_snapshot_msc,side,candidate,coherent,ConfirmationSeconds*1000,FrequentEntryMode?750:250,FrequentEntryMode?2:4);
     }
   if(!candidate){status=scalp_analysis;return;}
   signal_side=side;signal_since=previous_side==side?previous_since:TimeCurrent();
   signal_since_msc=previous_side==side && previous_since_msc>0?previous_since_msc:q.time_msc;
   bool strong=GoldStrongScalpSignal(side,scalp_score,scalp_threshold,last_micro);
   int rapid_delay=(int)MathMax(RapidRearmMilliseconds,MathMin(3000,2*ack_latency_ms));
   bool rapid=ExpertScalpMode && UseRapidRotation && Rotation.Ready(side,ExecutionClock(),q.time_msc,rapid_delay,
      PositionsTotal()==0 && OrdersTotal()==0,Requests.EntryBlocked(),ExposureReady(),strong,UseRapidContinuation);
   long confirm_since=rapid?MathMax(signal_since_msc,Rotation.confirmed_quote):signal_since_msc;
   bool confirmed=rapid?q.time_msc-confirm_since>=rapid_delay:ExpertScalpMode && UseConfirmationGrace?grace_ready:q.time_msc-confirm_since>=ConfirmationSeconds*1000;
   if(!confirmed){status=rapid?"SCALP: rapid reversal re-arming":"Confirmation flux + ATR en cours";return;}
   if(!CanExecute()){status="Signal valide / observation (ordres desactives)";return;}
   if(Requests.EntryBlocked()){status=Requests.uncertain_entry?"Entree incertaine : reconciliation requise":"Requete en cours / reservation active";return;}
   int entry_wait=MinimumEntrySeconds+(ExpertScalpMode && SessionAdjustment()>0?12:0);
   int submit_wait=ExpertScalpMode && FrequentEntryMode?1:2;
   if(!rapid && (TimeCurrent()-MathMax(last_entry,last_exit)<entry_wait || TimeCurrent()-last_submit<submit_wait)){status="Temporisation anti-surtrading";return;}
   if(ExpertScalpMode && PositionsTotal()>=3 && !strong){EntryConfirmation.Reset();status="Fourth/fifth entry requires stronger evidence and aligned fresh micro-flow";return;}
   double sl=0,tp=0;if(!EntryRisk(side,q,sl,tp,status)){EntryConfirmation.Reset();signal_side=0;signal_since=0;return;}
   MqlTradeRequest req={};req.action=TRADE_ACTION_DEAL;req.symbol=_Symbol;req.magic=Magic;req.volume=FIXED_LOT;
   req.type=side>0?ORDER_TYPE_BUY:ORDER_TYPE_SELL;req.price=side>0?q.ask:q.bid;req.sl=sl;req.tp=tp;
   req.deviation=(ulong)MathCeil(DynamicSlip()/SymbolInfoDouble(_Symbol,SYMBOL_POINT));req.type_filling=GoldFillFor(_Symbol);req.comment=ExpertScalpMode?"ScalperExpert326:S"+(string)session_bucket:"GoldScalpAI2";
   if(Submit(req,rapid?"SCALP: confirmed profitable-exit re-entry":"Entree"))
     {
      // One decision record per submitted entry, never a tick-history scan.
      string detail=StringFormat("v3.29 side=%d score=%.1f threshold=%.1f intelligence=%s/%d spread=%.3f atr=%.3f flow3=%.3f flow8=%.3f flow20=%.3f rolling_remaining=%.2f",side,scalp_score,scalp_threshold,Intelligence.Label(),intelligence_adjustment,q.ask-q.bid,atr,last_fast.pressure,last_slow.pressure,last_context.pressure,GoldRollingRiskRemaining(RollingLossLimitUSD,Stats.budget_net));
      GoldTelemetryEvent("entry_context",detail);Print("SCALP_ENTRY_CONTEXT ",detail);
      EntryConfirmation.Reset();Rotation.Clear();signal_since=0;signal_since_msc=0;signal_side=0;status="Requete envoyee : attente execution";
     }
  }
string SideLabel(const int side){return side>0?"HAUSSE":side<0?"BAISSE":"NEUTRE";}
void RenderDashboard()
  {
   GoldDashboardData d={};datetime now=ServerNow();bool fresh=Market.Fresh(now);
   d.mode=MQLInfoInteger(MQL_TESTER)?"TESTEUR":CanExecute()?"DEMO / EXECUTION":"OBSERVATION";
   bool quote_fresh=last_quote_msc>0 && (long)now*1000-last_quote_msc<=2000;
   d.paused=paused;d.locked=Safety.Locked(now);d.status=d.locked?Safety.reason:quote_fresh?status:"Flux de cotations perime / en attente";
   d.win_rate=Stats.ready && Stats.closed>0?DoubleToString(Stats.WinRate(),1)+"% / "+(string)Stats.closed:"-- / 0";
   d.profit_factor=Stats.ready?Stats.ProfitFactor():"--";d.pnl_day=Stats.ready?DoubleToString(Stats.day_net,2)+" USD":"--";
   d.pnl_week=Stats.ready?DoubleToString(Stats.week_net,2)+" USD":"--";
   d.equity="Equity compte "+DoubleToString(AccountInfoDouble(ACCOUNT_EQUITY),2)+" USD | flottant EA "+DoubleToString(FloatingOwned(),2);
   d.drawdown="DD actuel "+DoubleToString(Safety.current_drawdown,2)+"% / max "+DoubleToString(Safety.max_drawdown,2)+"%";
   double spread=last_ask-last_bid;
   d.spread=DoubleToString(spread,3)+" / max "+DoubleToString(MaxSpreadPrice,3)+" | moy100 "+DoubleToString(spread_before,3);
   d.spread_state=!quote_fresh || !relative_spread_ok || spread>MaxSpreadPrice?2:spread>=.8*MaxSpreadPrice?1:0;
   d.atr=fresh?DoubleToString(live_atr,3):"PERIME";d.volume=DoubleToString(Market.rvol,2)+"x "+(volatility_ok?"OK":"BLOQUE");
   d.candle_seconds=60-(int)(now%60);d.flow=last_fast.ready && quote_fresh?"flux "+SideLabel(last_fast.direction):"flux en chauffe/perime";
   d.mtf="M1 "+(string)Market.direction[0]+" | M5 "+(string)Market.direction[1]+" | M15 "+(string)Market.direction[2]+" | H1 "+(string)Market.direction[3]+" (+1/-1/0)";
   d.session=ExpertScalpMode?(cached_session?"OPEN | ":"CLOSED | ")+GoldSessionName(session_bucket)+" | broker XAUUSD hours"+(BlockAsiaSession?" | Asia gate enabled":""):
             (cached_session?"OUVERTE | ":"FERMEE | ")+(string)SessionStartUTC+":00-"+(string)SessionEndUTC+":00 UTC";
   d.news=!UseNativeNews?"DESACTIVE":MQLInfoInteger(MQL_TESTER)?TesterWithoutNews?"TEST SANS NEWS":"TEST BLOQUE":!NewsFresh()?"ABSENT / PERIME":cached_news_active?"BLOQUE / USD":"OK / calendrier natif";
   datetime utc=GoldUTCNow();bool advisor_fresh=Advisor1.Fresh(utc,_Symbol,Advisor1MaxAgeSeconds);
   d.advisor=(Advisor1Mode==GOLD_ADVISOR_REQUIRED?"REQUIS / ":"REFERENCE / ")+(advisor_fresh?Advisor1.action+" "+DoubleToString(Advisor1.score,0)+"/100":"ABSENT / PERIME");
   d.risk=Safety.loss_locked?"Loss limit reached | manual session reset required":d.locked?"SECURITE jusqu'au "+TimeToString(Safety.locked_until,TIME_DATE|TIME_MINUTES):"0.01 fixed | max "+(string)MaxPositions+" | loss limit $"+DoubleToString(RollingLossLimitUSD,2)+(DailyEquityLossPercent==0?" | daily equity pause disabled":" | equity -"+DoubleToString(DailyEquityLossPercent,1)+"%");
   double mean=tick_calls>0?(double)total_tick_us/tick_calls:0;
   d.execution=last_execution+" | tick us p50/p95/p99 "+DoubleToString(GoldTickLatencyPercentile(.50),0)+"/"+DoubleToString(GoldTickLatencyPercentile(.95),0)+"/"+DoubleToString(GoldTickLatencyPercentile(.99),0)+" | mean "+DoubleToString(mean,0)+" | max "+(string)max_tick_us;
   d.learning="Modele "+(UseLearnedVeto?"VETO":"OBSERVATION")+" | n="+(string)Learner.Samples()+" | Brier "+DoubleToString(Learner.Brier(),3);
   if(ExpertScalpMode)d.learning="Scalper Expert | evidence "+DoubleToString(scalp_score,1)+" / "+DoubleToString(scalp_threshold,1)+
      " | "+Intelligence.Label()+" "+(string)intelligence_adjustment+" | session outcomes "+(string)(session_bucket<4?Stats.session_count[session_bucket]:0)+" | score adjustment "+DoubleToString(SessionAdjustment(),0);
   Dashboard.Render(d);
   GoldPublishTelemetry(d);
  }
bool InputsValid()
  {
   return RapidRearmMilliseconds>=250 && RapidRearmMilliseconds<=3000 && MinimumScalpScore>=50 && MinimumScalpScore<=90 && ProfitGivebackFraction>=.15 && ProfitGivebackFraction<=.60 && MinimumProfitArmUSD>=.10 &&
      Magic>0 && MaxPositions>=1 && MaxPositions<=3 && RiskPerTradeUSD>0 && RiskPerTradeUSD<=2 &&
      MaxAggregateRiskUSD>0 && MaxAggregateRiskUSD<=5 && RollingLossLimitUSD>0 && RollingLossLimitUSD<=5 && DailyEquityLossPercent>=0 && DailyEquityLossPercent<=3 &&
      MaxSpreadPrice>0 && SpreadAverageMultiplier>=1 && SpreadAverageMultiplier<=3 && SlippageAllowancePrice>=0 && MaximumSlippagePrice>=SlippageAllowancePrice && MaximumSlippagePrice<=.5 &&
      RoundTripCommissionUSD>=0 && ATRPeriod>=2 && FastEMA>=2 && SlowEMA>FastEMA && StopATR>0 && TargetATR>0 &&
      MaximumSpreadATR>0 && MaximumCostFraction>0 && MaximumCostFraction<=.5 && MaximumBarExpansion>0 && MinimumRelativeVolume>0 && MaximumRelativeVolume>=MinimumRelativeVolume &&
      ConfirmationSeconds>=1 && MinimumEntrySeconds>=1 && MaxEntriesPerHour>=1 && LossStreakLimit>=1 && LossCooldownMinutes>=1 &&
      BreakevenArmR>0 && TrailArmR>0 && TrailGivebackR>0 && ReversalConfirmationSeconds>=1 && MaxHoldMinutes>=1 && ShockATRMultiple>=1 &&
      MathAbs(ServerUTCOffsetMinutes)<=840 && SessionStartUTC>=0 && SessionStartUTC<=23 && SessionEndUTC>=0 && SessionEndUTC<=23 && SessionStartUTC!=SessionEndUTC &&
      ((ScalpEntryStartUTC==-1 && ScalpEntryEndUTC==-1) || (ScalpEntryStartUTC>=0 && ScalpEntryStartUTC<=23 && ScalpEntryEndUTC>=0 && ScalpEntryEndUTC<=23 && ScalpEntryStartUTC!=ScalpEntryEndUTC)) &&
      NewsMinutesBefore>=0 && NewsMinutesBefore<=60 && NewsMinutesAfter>=0 && NewsMinutesAfter<=60 && Advisor1MaxAgeSeconds>=5 && Advisor1MaxAgeSeconds<=300;
  }
int OnInit()
  {
   if(!InputsValid() || StringFind(_Symbol,"XAUUSD")!=0 || AccountInfoString(ACCOUNT_CURRENCY)!="USD")return INIT_PARAMETERS_INCORRECT;
   if(!MQLInfoInteger(MQL_TESTER) && AccountInfoInteger(ACCOUNT_TRADE_MODE)!=ACCOUNT_TRADE_MODE_DEMO){Print("REAL ACCOUNT EXECUTION DISABLED");return INIT_FAILED;}
   if(AccountInfoInteger(ACCOUNT_MARGIN_MODE)!=ACCOUNT_MARGIN_MODE_RETAIL_HEDGING){Print("USD hedging account required");return INIT_FAILED;}
   if(SymbolInfoDouble(_Symbol,SYMBOL_TRADE_TICK_SIZE)<=0 || !GoldVolumeValid(FIXED_LOT,SymbolInfoDouble(_Symbol,SYMBOL_VOLUME_MIN),SymbolInfoDouble(_Symbol,SYMBOL_VOLUME_MAX),SymbolInfoDouble(_Symbol,SYMBOL_VOLUME_STEP)))return INIT_FAILED;
   prefix="GS_"+(string)AccountInfoInteger(ACCOUNT_LOGIN)+"_"+(string)Magic+"_";
   if(StringLen(prefix)>43)return INIT_PARAMETERS_INCORRECT;
   uint server_hash=2166136261;string server=AccountInfoString(ACCOUNT_SERVER);
   for(int i=0;i<StringLen(server);i++){server_hash^=(uint)StringGetCharacter(server,i);server_hash*=16777619;}
   safety_key="GS_ACCOUNT_"+(string)server_hash+"_"+(string)AccountInfoInteger(ACCOUNT_LOGIN)+"_";
   lock_name=prefix+"LOCK";lock_owner=(double)ChartID();
   if(!MQLInfoInteger(MQL_TESTER))
     {
      string account_lock=safety_key+"LOCK";
      if(!AccountLease.Acquire("GoldScalp\\"+account_lock+".lease"))
        {Print("Account startup lease unavailable: another EA is running, or common-file access failed. Error ",GetLastError());return INIT_FAILED;}
      if(!GoldClaimLegacyLock(account_lock,ChartID())){Print("Another active chart owns this account; startup refused");return INIT_FAILED;}
      owns_account_lock=true;
      if(!GoldClaimLegacyLock(lock_name,ChartID())){Print("Instance lock held by an active chart");return INIT_FAILED;}
   owns_lock=true;
      paused=GlobalVariableCheck(prefix+"PAUSED") && GlobalVariableGet(prefix+"PAUSED")>0;
      close_all_requested=GlobalVariableCheck(prefix+"CLOSE_ALL") && GlobalVariableGet(prefix+"CLOSE_ALL")>0;
      Requests.uncertain_entry=GlobalVariableCheck(prefix+"AMBIGUOUS") && GlobalVariableGet(prefix+"AMBIGUOUS")>0;ambiguity_persisted=Requests.uncertain_entry;
     }
   if(!MQLInfoInteger(MQL_TESTER) && GlobalVariableCheck(prefix+"BUDGET_START"))Stats.budget_start=(datetime)GlobalVariableGet(prefix+"BUDGET_START");
   Safety.Init(safety_key,!MQLInfoInteger(MQL_TESTER),AccountInfoDouble(ACCOUNT_EQUITY));
   control_instance=(string)ChartID()+"_"+(string)(long)GoldUTCNow()+"_"+(string)GetTickCount64();
   if(!Market.Init(_Symbol,ATRPeriod,FastEMA,SlowEMA))return INIT_FAILED;
   Dashboard.Create(prefix+"UI_",ShowDashboard && !BrowserDashboardOnly && (!MQLInfoInteger(MQL_TESTER) || MQLInfoInteger(MQL_VISUAL_MODE)));
   if(!EventSetMillisecondTimer(250))return INIT_FAILED;
   UnifiedReadConfig();
   GoldRefreshBrokerSessionState(ServerNow());
   RefreshHistory();RefreshIndicators();RefreshNews();
   startup_complete=true;
   Print("Scalper Expert 3.29 | causal intelligence + frequent XAUUSD scalping | 0.01 lot | <=3 positions | demo/tester only");
   if(MQLInfoInteger(MQL_TESTER))Print("TEST POLICY: news bypass=",TesterWithoutNews," Advisor1 mode=",EnumToString(Advisor1Mode),"; a missing required point-in-time Advisor1 snapshot blocks entries.");
   return INIT_SUCCEEDED;
  }
void OnTick()
  {
   ulong began=GetMicrosecondCount();ProcessTick();ulong elapsed=GetMicrosecondCount()-began;
   tick_calls++;total_tick_us+=elapsed;max_tick_us=MathMax(max_tick_us,elapsed);GoldRecordTickLatency(elapsed);
  }
void OnTimer()
  {
   datetime now=ServerNow();
   UnifiedReadConfig();
   PollBrowserControls();
   // No synchronous calendar calls, CopyTicks scans or GUI painting in OnTick.
   if(now!=last_slow_timer)
     {
      GoldRefreshBrokerSessionState(now);
      last_slow_timer=now;RefreshHistory();RefreshIndicators();RefreshNews();PruneClosedState();PersistManagedPeaks();
      session_bucket=GoldSessionBucket(GoldUTCNow());scalp_threshold=MinimumScalpScore+SessionAdjustment()+(trend_entry_lane?4:0);
      cached_session=EntrySession();volatility_ok=Market.ready && Market.range/Market.atr<=MaximumBarExpansion && Market.rvol>=MinimumRelativeVolume && Market.rvol<=MaximumRelativeVolume;
      if(MQLInfoInteger(MQL_TESTER))
        {
         if(Advisor1ReplayFile!="")Advisor1.Replay(Advisor1ReplayFile,now-ServerUTCOffsetMinutes*60);
         // A live Common/Files report is deliberately never read by a backtest.
        }
      else Advisor1.Load(Advisor1File);
      MqlTick q;double value=0,step=SymbolInfoDouble(_Symbol,SYMBOL_TRADE_TICK_SIZE);
      if(SymbolInfoTick(_Symbol,q) && step>0 && OrderCalcProfit(ORDER_TYPE_BUY,_Symbol,FIXED_LOT,q.ask,q.ask+step,value))money_per_price=MathAbs(value/step);
     }
   // Poll the broker quote as a fallback when chart tick events are delayed.
   // ProcessTick rejects stale quotes and duplicate timestamps/prices.
   ProtectAccount();if(close_all_requested)DrainAccountForCloseAll();
   GoldServiceScheduledSessionClose(now);
   ProcessTick(false);
   if(cached_news_active && CloseBeforeNews)CloseOwned("Fenetre annonces USD");
   ServiceRequests();
   if(now!=last_dashboard){last_dashboard=now;RenderDashboard();}
   if(now-last_safety_save>=60){last_safety_save=now;Safety.Save();}
  }
void OnChartEvent(const int id,const long &lparam,const double &dparam,const string &sparam)
  {
   if(id==CHARTEVENT_CHART_CHANGE){Dashboard.Destroy();Dashboard.Create(prefix+"UI_",ShowDashboard && !BrowserDashboardOnly);RenderDashboard();return;}
   if(id!=CHARTEVENT_OBJECT_CLICK)return;int action=Dashboard.Action(sparam);
   if(action==1)
     {
      if(!GoldControlTransition(paused?"resume":"pause",Safety.Locked(ServerNow()),CanExecute(),paused,close_all_requested))status="Reprise interdite : securite / liquidation";
      else {EntryConfirmation.Reset();Rotation.Clear();Requests.CancelEntryRetries();signal_side=0;signal_since=0;signal_since_msc=0;SaveControls();}
     }
   if(action==2)
     {
      if(!CanExecute())status="Close All indisponible : ordres demo desactives";
      else {paused=true;close_all_requested=true;EntryConfirmation.Reset();Rotation.Clear();Requests.CancelEntryRetries();SaveControls();DrainAccountForCloseAll();}
     }
   RenderDashboard();
  }
void OnTradeTransaction(const MqlTradeTransaction &trans,const MqlTradeRequest &request,const MqlTradeResult &result)
  {
   history_dirty=true; // one flag only; history reconstruction belongs to timer
   if(trans.type==TRADE_TRANSACTION_DEAL_ADD)
     {
      // Callbacks may arrive in either order. A deal can reveal the broker order
      // before the request acknowledgement, including a partial close.
      bool owned_entry=false;
      if(trans.symbol==_Symbol && HistoryDealSelect(trans.deal))
        {
         owned_entry=(ulong)HistoryDealGetInteger(trans.deal,DEAL_MAGIC)==Magic && HistoryDealGetInteger(trans.deal,DEAL_ENTRY)==DEAL_ENTRY_IN;
         long entry_kind=HistoryDealGetInteger(trans.deal,DEAL_ENTRY);
         if(entry_kind==DEAL_ENTRY_OUT || entry_kind==DEAL_ENTRY_OUT_BY)
           {
            double net=HistoryDealGetDouble(trans.deal,DEAL_PROFIT)+HistoryDealGetDouble(trans.deal,DEAL_SWAP)+HistoryDealGetDouble(trans.deal,DEAL_COMMISSION)+HistoryDealGetDouble(trans.deal,DEAL_FEE)-RoundTripCommissionUSD;
            if(net>0)
              {
               if(ExpertScalpMode && UseRapidRotation && !paused && !close_all_requested && !Safety.Locked(ServerNow()) &&
                  (ulong)HistoryDealGetInteger(trans.deal,DEAL_MAGIC)==Magic && Rotation.ticket!=trans.position)
                  Rotation.Intent(trans.position,HistoryDealGetInteger(trans.deal,DEAL_TYPE)==DEAL_TYPE_BUY?-1:1);
               Rotation.Confirm(trans.position,ExecutionClock(),last_quote_msc);
              }
            else if(Rotation.ticket==trans.position)Rotation.Clear();
           }
        }
      for(int i=0;i<16;i++)if(Requests.items[i].state!=GOLD_REQUEST_FREE && Requests.items[i].request.action==TRADE_ACTION_DEAL &&
         ((Requests.items[i].request.position>0 && Requests.items[i].request.position==trans.position) || (owned_entry && Requests.items[i].request.position==0)))
         Requests.items[i].broker_order=trans.order;
     }
   if(trans.type==TRADE_TRANSACTION_REQUEST)
     {
      int slot=Requests.Find(result.request_id);if(slot<0)return;
      if(result.order>0)Requests.items[slot].broker_order=result.order;
      bool entry=Requests.items[slot].request.action==TRADE_ACTION_DEAL && Requests.items[slot].request.position==0;
      bool was_unknown=Requests.items[slot].state==GOLD_REQUEST_UNKNOWN;
      bool done=result.retcode==TRADE_RETCODE_DONE || result.retcode==TRADE_RETCODE_DONE_PARTIAL;
      if(result.retcode!=TRADE_RETCODE_PLACED)
        {
         double elapsed=(double)(ExecutionClock()-Requests.items[slot].sent_ms);
         ack_latency_ms=ack_samples==0?elapsed:.8*ack_latency_ms+.2*elapsed;ack_samples++;ack_latency_max_ms=MathMax(ack_latency_max_ms,elapsed);
         // Some brokers omit callback request.price. Use the reserved request,
         // correlated by request_id, rather than subtracting zero from the fill.
         MqlTradeRequest original=Requests.items[slot].request;
         if(done && original.action==TRADE_ACTION_DEAL)
           {
            last_fill_slippage=GoldSignedFillSlippage(original.price,result.price,original.type==ORDER_TYPE_BUY,fill_slippage_valid);
           }
        }
      if(done){filled++;if(entry)last_entry=TimeCurrent();else if(request.action==TRADE_ACTION_DEAL)last_exit=TimeCurrent();}
      else if(result.retcode!=TRADE_RETCODE_PLACED)rejections++;
      last_execution="Retour courtier "+(string)result.retcode;
      GoldTelemetryEvent("broker",last_execution+" | "+result.comment);
      Requests.Response(slot,result.retcode,ExecutionClock());
      if(entry && was_unknown && Requests.items[slot].state==GOLD_REQUEST_FREE)
        {Requests.uncertain_entry=false;ambiguity_persisted=false;if(!MQLInfoInteger(MQL_TESTER))GlobalVariableDel(prefix+"AMBIGUOUS");}
      PersistAmbiguity();
     }
  }
double OnTester()
  {
   PrintFormat("VALIDATION_SUMMARY quotes=%I64u requests=%I64u completed=%I64u rejected=%I64u retries=%I64u tick_us_mean=%.1f tick_us_max=%I64u",quote_count,attempts,filled,rejections,retry_count,tick_calls>0?(double)total_tick_us/tick_calls:0,max_tick_us);
   double trades=TesterStatistics(STAT_TRADES),profit=TesterStatistics(STAT_PROFIT),drawdown=TesterStatistics(STAT_EQUITY_DD);
   return trades>=30?profit/MathMax(1.,drawdown):-1e6;
  }
void OnDeinit(const int reason)
  {
   if(!startup_complete)
     {
      EventKillTimer();Market.Release();Advisor1.CloseReplay();Dashboard.Destroy();
      if(owns_lock)GlobalVariableSetOnCondition(lock_name,0,lock_owner);
      if(owns_account_lock)GlobalVariableSetOnCondition(safety_key+"LOCK",0,lock_owner);
      AccountLease.Release();return;
     }
   GoldDashboardData final_state={};final_state.status="EA stopped / deinit "+(string)reason;
   GoldPublishTelemetry(final_state,true);
   EventKillTimer();PersistManagedPeaks();Market.Release();Advisor1.CloseReplay();Dashboard.Destroy();Safety.Save();SaveControls();
   if(!MQLInfoInteger(MQL_TESTER) && owns_lock)GlobalVariableSetOnCondition(lock_name,0,lock_owner);
   if(!MQLInfoInteger(MQL_TESTER) && owns_account_lock)GlobalVariableSetOnCondition(safety_key+"LOCK",0,lock_owner);
   AccountLease.Release();
   // Broker stops remain active. Session resets require an explicit acknowledged command.
  }
#endif
