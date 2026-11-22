#ifndef GOLD_SCALP_FEEDS
#define GOLD_SCALP_FEEDS
enum GOLD_ADVISOR_MODE { GOLD_ADVISOR_REFERENCE=0,GOLD_ADVISOR_REQUIRED=1 };
string GoldNewsFile(const string server)
  {
   string name=server;StringReplace(name,"\\","_");StringReplace(name,"/","_");StringReplace(name,":","_");
   return "GoldScalp\\news_"+name+".csv";
  }
bool GoldFreshStamp(const datetime now,const datetime generated,const int ttl)
  {return generated>0 && generated<=now+2 && now-generated<=ttl;}
class CGoldAdvisorReference
  {
private:
   int replay_handle;
   string replay_path,pending[11];
   bool buffered,replay_caught_up;
   datetime replay_now,last_replay_stamp;
public:
   datetime generated,valid_until;
   string symbol,action,bias;
   double score,bid,ask;
   bool loaded;
   CGoldAdvisorReference(){generated=0;valid_until=0;loaded=false;score=0;bid=0;ask=0;action="WAIT";bias="WAIT";replay_handle=INVALID_HANDLE;buffered=false;replay_caught_up=false;replay_now=0;last_replay_stamp=0;}
   void CloseReplay(){if(replay_handle!=INVALID_HANDLE)FileClose(replay_handle);replay_handle=INVALID_HANDLE;buffered=false;}
   bool Parse(const string &fields[])
     {
      loaded=false;
      if(ArraySize(fields)!=11 || fields[0]!="GOLD_ADVISOR1_V1" || fields[10]!="END")return false;
      generated=(datetime)StringToInteger(fields[1]);valid_until=(datetime)StringToInteger(fields[2]);
      symbol=fields[3];action=fields[4];bias=fields[5];score=StringToDouble(fields[6]);bid=StringToDouble(fields[7]);ask=StringToDouble(fields[8]);
      if(fields[9]!="SCALP" || generated<=0 || valid_until<=generated || bid<=0 || ask<bid || !MathIsValidNumber(ask) || score<0 || score>100)return false;
      if(action!="BUY" && action!="SELL" && action!="WAIT")return false;
      if(bias!="BUY" && bias!="SELL" && bias!="WAIT")return false;
      loaded=true;return true;
     }
   bool Load(const string filename)
     {
      loaded=false;int file=FileOpen(filename,FILE_READ|FILE_CSV|FILE_ANSI|FILE_COMMON|FILE_SHARE_READ,';',CP_UTF8);
      if(file==INVALID_HANDLE)return false;
      if(FileSize(file)>4096){FileClose(file);return false;}
      string fields[11];for(int i=0;i<11;i++){if(FileIsEnding(file)){FileClose(file);return false;}fields[i]=FileReadString(file);}
      FileClose(file);return Parse(fields);
     }
   bool Fresh(const datetime utc,const string expected,const int ttl)
     {return loaded && (replay_handle==INVALID_HANDLE || replay_caught_up) && symbol==expected && GoldFreshStamp(utc,generated,ttl) && utc<valid_until;}
   bool Allows(const int side,const datetime utc,const string expected,const int ttl)
     {return Fresh(utc,expected,ttl) && score>=60 && ((side>0 && action=="BUY") || (side<0 && action=="SELL"));}
   bool Replay(const string filename,const datetime utc,const bool common_file=true)
     {
      if(replay_path!=filename || utc<replay_now){CloseReplay();loaded=false;last_replay_stamp=0;}
      replay_path=filename;replay_now=utc;
      replay_caught_up=false;
      if(replay_handle==INVALID_HANDLE)
        {replay_handle=FileOpen(filename,FILE_READ|FILE_CSV|FILE_ANSI|FILE_SHARE_READ|(common_file?FILE_COMMON:0),';',CP_UTF8);if(replay_handle==INVALID_HANDLE){loaded=false;return false;}}
      for(int row=0;row<500;row++)
        {
         if(!buffered)
           {
            if(FileIsEnding(replay_handle)){replay_caught_up=true;return loaded;}
            for(int i=0;i<11;i++){if(FileIsEnding(replay_handle)){loaded=false;return false;}pending[i]=FileReadString(replay_handle);}
            buffered=true;
           }
         datetime stamp=(datetime)StringToInteger(pending[1]);
         if(stamp<last_replay_stamp || stamp<=0){loaded=false;return false;}
         if(stamp>utc){replay_caught_up=true;return loaded;} // keep future row buffered: never expose future direction
         if(!Parse(pending)){loaded=false;return false;}
         last_replay_stamp=stamp;buffered=false;
        }
      return false; // Fresh() remains false until catch-up reaches the current timestamp
     }
  };
class CGoldNewsCache
  {
private:
   datetime times[];
public:
   bool loaded;
   datetime generated,next_event;
   CGoldNewsCache(){loaded=false;generated=0;next_event=0;}
   bool Load(const string filename,const string expected_server,const bool common_file=true)
     {
      loaded=false;int file=FileOpen(filename,FILE_READ|FILE_CSV|FILE_ANSI|FILE_SHARE_READ|(common_file?FILE_COMMON:0),';',CP_UTF8);
      if(file==INVALID_HANDLE)return false;
      if(FileSize(file)>65536){FileClose(file);return false;}
      string version=FileReadString(file),server=FileReadString(file);generated=(datetime)StringToInteger(FileReadString(file));
      int count=(int)StringToInteger(FileReadString(file));
      if(version!="GOLD_NEWS_V1" || server!=expected_server || count<0 || count>512 || generated<=0){FileClose(file);return false;}
      ArrayResize(times,count);
      for(int i=0;i<count;i++)
        {if(FileIsEnding(file)){FileClose(file);return false;}times[i]=(datetime)StringToInteger(FileReadString(file));if(times[i]<=0){FileClose(file);return false;}}
      string end=FileReadString(file);FileClose(file);loaded=end=="END";return loaded;
     }
   bool Fresh(const datetime server_now){return loaded && GoldFreshStamp(server_now,generated,120);}
   bool Active(const datetime now,const int before,const int after)
     {
      next_event=0;bool active=false;
      for(int i=0;i<ArraySize(times);i++)
        {
         if(times[i]>=now && (next_event==0 || times[i]<next_event))next_event=times[i];
         if(now>=times[i]-before*60 && now<=times[i]+after*60)active=true;
        }
      return active;
     }
  };
#endif
