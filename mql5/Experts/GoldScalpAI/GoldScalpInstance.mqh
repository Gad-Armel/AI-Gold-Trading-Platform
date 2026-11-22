#ifndef GOLD_SCALP_INSTANCE
#define GOLD_SCALP_INSTANCE
// Exclusive open handles are released by MT5/Windows even after a crash.
// The file itself may remain; its existence does not mean it is locked.
class CGoldInstanceLease
  {
private:
   int handle;
public:
   CGoldInstanceLease(){handle=INVALID_HANDLE;}
   bool Acquire(const string path,const bool common=true)
     {
      if(handle!=INVALID_HANDLE)return false;
      handle=FileOpen(path,FILE_READ|FILE_WRITE|FILE_BIN|(common?FILE_COMMON:0));
      return handle!=INVALID_HANDLE;
     }
   void Release(){if(handle!=INVALID_HANDLE){FileClose(handle);handle=INVALID_HANDLE;}}
  };
bool GoldLegacyOwnerBlocks(const double owner,const long current,const bool chart_exists,const string expert)
  {return owner!=0 && owner!=(double)current && chart_exists && expert!="";}
bool GoldClaimLegacyLock(const string name,const long current)
  {
   if(!GlobalVariableCheck(name) && !GlobalVariableTemp(name))return false;
   double previous=GlobalVariableGet(name);
   if(previous!=0 && previous!=(double)current)
     {
      for(long chart=ChartFirst();chart>=0;chart=ChartNext(chart))
        {
         if((double)chart!=previous)continue;
         string expert;
         if(!ChartGetString(chart,CHART_EXPERT_NAME,expert))return false;
         if(GoldLegacyOwnerBlocks(previous,current,true,expert))return false;
         break;
        }
     }
   // Compare-and-swap also protects migration alongside older EA builds.
   if(!GlobalVariableSetOnCondition(name,(double)current,previous))return false;
   if(previous!=0 && previous!=(double)current)Print("Recovered abandoned startup lock: ",name);
   return true;
  }
#endif
