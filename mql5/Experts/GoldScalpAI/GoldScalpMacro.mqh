#ifndef GOLD_SCALP_MACRO
#define GOLD_SCALP_MACRO
#include "GoldScalpFeeds.mqh"
#include "GoldScalpWire.mqh"
string GoldMacroFile(const string server){string name=GoldNewsFile(server);StringReplace(name,"news_","macro_");return name;}
string GoldCsvText(string text){StringReplace(text,";",",");StringReplace(text,"\r"," ");StringReplace(text,"\n"," ");return StringSubstr(text,0,180);}
bool GoldMacroRelevant(string name)
  {StringToLower(name);return StringFind(name,"adp")>=0 || StringFind(name,"pce")>=0 || StringFind(name,"consumption expenditure")>=0 || StringFind(name,"gdp")>=0 || StringFind(name,"gross domestic product")>=0;}
double GoldReleaseReaction(const int side,const datetime now,const datetime observed,const double baseline,const double mid,const double spread)
  {
   // Describes observed XAUUSD response, never assumes that higher inflation means buy/sell.
   if(side==0 || observed<=0 || now-observed<20 || now-observed>1800 || baseline<=0 || spread<=0)return 0;
   double move=mid-baseline;if(MathAbs(move)<2*spread)return 0;
   return side*move>0?2:-2;
  }
struct GoldMacroEvent {string id,name,actual,forecast,previous,unit,impact;datetime time;};
class CGoldMacro
  {
public:
   GoldMacroEvent events[];
   datetime generated,observed,release_time;
   double baseline;
   string release_id;
   bool loaded;
   CGoldMacro(){generated=0;observed=0;release_time=0;baseline=0;loaded=false;release_id="";}
   bool Fresh(const datetime now){return loaded && GoldFreshStamp(now,generated,120);}
   bool Load(const string server,const datetime now,const double mid,const bool common=true)
     {
      loaded=false;
      int file=FileOpen(GoldMacroFile(server),FILE_READ|FILE_CSV|FILE_ANSI|FILE_SHARE_READ|(common?FILE_COMMON:0),';',CP_UTF8);
      if(file==INVALID_HANDLE)return false;
      if(FileSize(file)>65536){FileClose(file);return false;}
      string version=FileReadString(file),source=FileReadString(file);generated=(datetime)StringToInteger(FileReadString(file));
      int count=(int)StringToInteger(FileReadString(file));
      if(version!="GOLD_MACRO_V1" || source!=server || count<0 || count>64 || generated<=0){FileClose(file);return false;}
      ArrayResize(events,count);datetime latest=0;string latest_id="";
      for(int i=0;i<count;i++)
        {
         string row[8];for(int j=0;j<8;j++){if(FileIsEnding(file)){FileClose(file);return false;}row[j]=FileReadString(file);if(StringLen(row[j])>180){FileClose(file);return false;}}
         events[i].id=row[0];events[i].time=(datetime)StringToInteger(row[1]);events[i].name=row[2];events[i].actual=row[3];
         events[i].forecast=row[4];events[i].previous=row[5];events[i].unit=row[6];events[i].impact=row[7];
         if(events[i].time<=0){FileClose(file);return false;}
         if(events[i].time>now)events[i].actual="NA";
         if(events[i].actual!="NA" && events[i].time>latest && events[i].time<=now){latest=events[i].time;latest_id=events[i].id;}
        }
      string end=FileReadString(file);bool eof=FileIsEnding(file);FileClose(file);loaded=end=="END" && eof;
      if(Fresh(now) && latest_id!="")
        {
         if(latest_id!=release_id){release_id=latest_id;release_time=latest;observed=0;baseline=0;}
         // Startup can receive the calendar before a valid quote. Capture once
         // when that quote arrives, still within the bounded release window.
         if(observed==0 && now-latest<=120 && mid>0){observed=now;baseline=mid;}
        }
      return loaded;
     }
   double Evidence(const int side,const datetime now,const double mid,const double spread)
     {return Fresh(now)?GoldReleaseReaction(side,now,observed,baseline,mid,spread):0;}
   string Json(const datetime now)
     {
      string out="{\"fresh\":"+GoldBool(Fresh(now))+",\"observed_response_since\":"+GoldJson(observed>0?TimeToString(observed,TIME_DATE|TIME_SECONDS):"")+",\"events\":[";
      for(int i=0;i<ArraySize(events);i++)
        {
         if(i>0)out+=",";
         out+="{\"name\":"+GoldJson(events[i].name)+",\"time\":"+GoldJson(TimeToString(events[i].time,TIME_DATE|TIME_SECONDS))+
          ",\"actual\":"+GoldJson(events[i].time<=now?events[i].actual:"NA")+",\"forecast\":"+GoldJson(events[i].forecast)+",\"previous\":"+GoldJson(events[i].previous)+
          ",\"unit\":"+GoldJson(events[i].unit)+",\"impact\":"+GoldJson(events[i].impact)+",\"released\":"+GoldBool(events[i].time<=now && events[i].actual!="NA")+"}";
        }
      return out+"]}";
     }
  };
#endif
