#ifndef GOLD_SCALP_SAFETY
#define GOLD_SCALP_SAFETY
// Stateless helpers are exercised with deposits, withdrawals and boundary cases.
double GoldDailyReference(const double capital,const double all_day_changes,const double funding)
  {return capital-all_day_changes+funding;}
double GoldDrawdown(const double peak,const double equity)
  {return peak>0?MathMax(0.,100.*(peak-equity)/peak):0.;}
bool GoldEquityBreached(const double reference,const double equity,const double percent)
  {return percent>0 && reference>0 && equity>=0 && equity<=reference*(1.-percent/100.)+1e-8;}
bool GoldIsFunding(const long type)
  {return type==DEAL_TYPE_BALANCE || type==DEAL_TYPE_CREDIT || type==DEAL_TYPE_BONUS || type==DEAL_TYPE_CORRECTION;}
bool GoldSafetyOwnsExposure(const string symbol,const string target_symbol,const ulong magic,const ulong target_magic)
  {return symbol==target_symbol && magic==target_magic;}
class CGoldSafety
  {
private:
   string key;
   bool persist;
public:
   bool loss_locked;
   datetime locked_until;
   double reference,peak,max_drawdown,current_drawdown;
   string reason;
   CGoldSafety(){loss_locked=false;locked_until=0;reference=0;peak=0;max_drawdown=0;current_drawdown=0;persist=false;reason="";}
   void Init(const string account_key,const bool persistent,const double equity)
     {
      key=account_key;persist=persistent;peak=equity;
      if(persist && GlobalVariableCheck(key+"LOSS_LOCK"))loss_locked=GlobalVariableGet(key+"LOSS_LOCK")>0;
      if(!persist)return;
      if(GlobalVariableCheck(key+"UNTIL"))locked_until=(datetime)GlobalVariableGet(key+"UNTIL");
      if(GlobalVariableCheck(key+"PEAK"))peak=MathMax(equity,GlobalVariableGet(key+"PEAK"));
      // Funding/trades while offline cannot reconstruct an unobserved equity path.
      // Start a new current-DD segment if capital changed; retain the observed max.
      if(GlobalVariableCheck(key+"CAPITAL") && MathAbs(GlobalVariableGet(key+"CAPITAL")-AccountInfoDouble(ACCOUNT_BALANCE)-AccountInfoDouble(ACCOUNT_CREDIT))>.001)peak=equity;
      if(GlobalVariableCheck(key+"MAXDD"))max_drawdown=GlobalVariableGet(key+"MAXDD");
      if(locked_until>0)reason="Protection compte memorisee";
      if(loss_locked)reason="Loss limit reached: reset session to restart";
     }
   bool Locked(const datetime now){return loss_locked || now<locked_until;}
   void Trip(const datetime now,const string why)
     {
      // Do not slide the end time on every tick while already locked.
      if(!Locked(now)){locked_until=now+86400;reason=why;Save();}
     }
   void LossTrip(){if(loss_locked)return;loss_locked=true;reason="$50 loss limit: reset session to restart";Save();}
   void ResetSession(){loss_locked=false;locked_until=0;reason="";Save();}
   void Funding(const double amount){peak=MathMax(0.,peak+amount);}
   void Observe(const double equity)
     {peak=MathMax(peak,equity);current_drawdown=GoldDrawdown(peak,equity);max_drawdown=MathMax(max_drawdown,current_drawdown);}
   void Save()
     {if(persist){GlobalVariableSet(key+"LOSS_LOCK",loss_locked?1:0);GlobalVariableSet(key+"UNTIL",(double)locked_until);GlobalVariableSet(key+"PEAK",peak);GlobalVariableSet(key+"MAXDD",max_drawdown);GlobalVariableSet(key+"CAPITAL",AccountInfoDouble(ACCOUNT_BALANCE)+AccountInfoDouble(ACCOUNT_CREDIT));GlobalVariablesFlush();}}
  };
#endif
