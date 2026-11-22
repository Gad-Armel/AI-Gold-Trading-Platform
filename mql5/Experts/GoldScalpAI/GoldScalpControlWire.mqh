#ifndef GOLD_SCALP_CONTROL_WIRE
#define GOLD_SCALP_CONTROL_WIRE
bool GoldReadControl(const int handle,string &fields[])
  {
   ArrayResize(fields,7);
   if(handle==INVALID_HANDLE || FileSize(handle)>512)return false;
   for(int i=0;i<7;i++)fields[i]=FileReadString(handle);
   return FileIsEnding(handle);
  }
bool GoldControlTransition(const string action,const bool locked,const bool executing,bool &paused_state,bool &liquidating)
  {
   if(action=="pause"){paused_state=true;return true;}
   if(action=="resume")
     {if(locked || liquidating)return false;paused_state=false;return true;}
   if(action=="close_all")
     {if(!executing)return false;paused_state=true;liquidating=true;return true;}
   return false;
  }
bool GoldControlValid(const string &fields[],const string instance,const string last_id,const datetime now)
  {
   if(ArraySize(fields)!=7 || fields[0]!="GOLD_CONTROL_V1" || fields[1]!=instance || fields[6]!="END" || fields[2]==last_id || StringLen(fields[2])!=32)return false;
   for(int i=0;i<32;i++){ushort c=StringGetCharacter(fields[2],i);if(!((c>='0' && c<='9') || (c>='a' && c<='f')))return false;}
   long issued=StringToInteger(fields[3]),expires=StringToInteger(fields[4]);
   if((string)issued!=fields[3] || (string)expires!=fields[4] || issued>now+2 || issued<now-10 || expires<now || expires<=issued || expires-issued>10)return false;
   return fields[5]=="reset_session" || fields[5]=="pause" || fields[5]=="resume" || fields[5]=="close_all";
  }
#endif
