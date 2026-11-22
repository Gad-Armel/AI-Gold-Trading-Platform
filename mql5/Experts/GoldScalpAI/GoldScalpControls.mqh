#ifndef GOLD_SCALP_CONTROLS
#define GOLD_SCALP_CONTROLS
#include "GoldScalpControlWire.mqh"
bool CanResetSession()
  {
   if(!TerminalInfoInteger(TERMINAL_CONNECTED) || !CanExecute() || !ExposureReady() || close_all_requested || PositionsTotal()!=0 || OrdersTotal()!=0 || Requests.uncertain_entry)return false;
   for(int i=0;i<16;i++)if(Requests.items[i].state!=GOLD_REQUEST_FREE)return false;
   return true;
  }
void PollBrowserControls()
  {
   if(!AllowBrowserControls || MQLInfoInteger(MQL_TESTER) || !owns_account_lock)return;
   string path="GoldScalp\\control_"+safety_key+(string)Magic+".csv";
   if(!FileIsExist(path,FILE_COMMON))return;
   int handle=FileOpen(path,FILE_READ|FILE_CSV|FILE_ANSI|FILE_COMMON,';',CP_UTF8);if(handle==INVALID_HANDLE)return;
   string fields[];bool size_ok=GoldReadControl(handle,fields);
   FileClose(handle);FileDelete(path,FILE_COMMON);
   if(!size_ok || !GoldControlValid(fields,control_instance,control_last_id,GoldUTCNow()))
     {GoldTelemetryEvent("control","Rejected stale or invalid browser command");return;}
   control_last_id=fields[2];string action=fields[5];control_result="rejected";
   if(action=="reset_session")
     {
      if(!CanResetSession())control_result="rejected: reset requires reconciled flat account and no pending requests";
      else
        {
         Stats.budget_start=ServerNow()+1;
         GlobalVariableSet(prefix+"BUDGET_START",(double)Stats.budget_start);GlobalVariablesFlush();
         Safety.ResetSession();Stats.budget_net=0;Stats.loss_streak=0;loss_streak=0;loss_pause_until=0;
         paused=false;history_dirty=true;EntryConfirmation.Reset();Rotation.Clear();Requests.CancelEntryRetries();
         signal_side=0;signal_since=0;signal_since_msc=0;SaveControls();
         control_result="applied: new $50 loss session; counters reset; history preserved; entries resumed";
        }
      GoldTelemetryEvent("control",action+" | "+control_result);status=control_result;return;
     }
   if(!GoldControlTransition(action,Safety.Locked(ServerNow()),CanExecute(),paused,close_all_requested))
      control_result="rejected: safety lock, liquidation or execution disabled";
   else
     {
      EntryConfirmation.Reset();Rotation.Clear();Requests.CancelEntryRetries();signal_side=0;signal_since=0;signal_since_msc=0;SaveControls();
      control_result=action=="pause"?"applied: entries paused; exits remain active":action=="resume"?"applied: entries resumed subject to normal checks":"accepted: closing account positions/orders; entries paused";
      if(action=="close_all")DrainAccountForCloseAll();
     }
   GoldTelemetryEvent("control",action+" | "+control_result);status=control_result;
  }
#endif
