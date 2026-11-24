#ifndef GOLD_NEWS_PUBLISHER
#define GOLD_NEWS_PUBLISHER
#include "../Experts/GoldScalpAI/GoldScalpFeeds.mqh"
#include "../Experts/GoldScalpAI/GoldScalpWire.mqh"
#include "../Experts/GoldScalpAI/GoldScalpMacro.mqh"
// Calendar requests are remote and may block until the terminal timeout. Keep
// their window deliberately small and retry outside the EA tick path.
int GoldNewsRetrySeconds(const int failure_count)
  {
   int capped=MathMin(6,MathMax(0,failure_count));
   return MathMin(300,5*(1<<capped)); // 10,20,40,80,160,300 seconds after failures
  }
datetime GoldNewsFrom(const datetime server_now){return server_now-6*3600;}
datetime GoldNewsTo(const datetime server_now){return server_now+18*3600;}
void GoldRunNewsPublisher()
  {
   datetime last=0,next_refresh=0;int calendar_failures=0;
   while(!IsStopped())
     {
      datetime now=TimeTradeServer();
      if(now<last){last=0;next_refresh=0;}
      if(TerminalInfoInteger(TERMINAL_CONNECTED) && now>0 && (now>=next_refresh || now<last))
        {
         last=now;MqlCalendarValue values[];datetime events[];
         ResetLastError();
         int count=CalendarValueHistory(values,GoldNewsFrom(now),GoldNewsTo(now),"","USD");
         if(count<0)
           {
            calendar_failures++;next_refresh=now+GoldNewsRetrySeconds(calendar_failures);
            Print("NEWS_REFRESH_FAILED error=",GetLastError()," retry_seconds=",GoldNewsRetrySeconds(calendar_failures));
            continue;
           }
         bool complete=true;int used=0,macro_count=0;string macro_rows="";bool macro_complete=true;
         for(int i=0;i<count;i++)
           {
            MqlCalendarEvent event;
            ResetLastError();
            if(!CalendarEventById(values[i].event_id,event)){complete=false;break;}
            bool important=event.importance==CALENDAR_IMPORTANCE_HIGH;
            if(important || GoldMacroRelevant(event.name))
              {
               if(MathAbs((double)(values[i].time-now))<600)next_refresh=now+5;
               if(macro_count>=64)macro_complete=false;
               else
                 {
                  macro_count++;
                  string actual=values[i].time<=now && values[i].HasActualValue()?DoubleToString(values[i].GetActualValue(),event.digits):"NA";
                  string forecast=values[i].HasForecastValue()?DoubleToString(values[i].GetForecastValue(),event.digits):"NA";
                  string previous=values[i].HasPreviousValue()?DoubleToString(values[i].GetPreviousValue(),event.digits):"NA";
                  macro_rows+=(string)values[i].id+";"+GoldEpoch(values[i].time)+";"+GoldCsvText(event.name)+";"+actual+";"+forecast+";"+previous+";"+
                    EnumToString(event.unit)+" / "+EnumToString(event.multiplier)+";"+EnumToString(values[i].impact_type)+"\n";
                 }
              }
            if(!important)continue;
            if(used>=512){complete=false;break;}
            ArrayResize(events,used+1);events[used++]=values[i].time;
           }
         if(complete)
           {
            string server=AccountInfoString(ACCOUNT_SERVER),name=GoldNewsFile(server),temporary=name+"."+MQLInfoString(MQL_PROGRAM_NAME)+"."+(string)ChartID()+".tmp";
            FolderCreate("GoldScalp",FILE_COMMON);
            int file=FileOpen(temporary,FILE_WRITE|FILE_TXT|FILE_ANSI|FILE_COMMON,0,CP_UTF8);
            bool news_written=false;
            if(file!=INVALID_HANDLE)
              {
               string line=GoldNewsLine(server,now,events);
               news_written=FileWriteString(file,line)>0;FileFlush(file);FileClose(file);
               news_written=news_written && FileMove(temporary,FILE_COMMON,name,FILE_COMMON|FILE_REWRITE);
               if(!news_written)Print("NEWS_PUBLISH_FAILED ",GetLastError());
              }
            if(!news_written){calendar_failures++;next_refresh=now+GoldNewsRetrySeconds(calendar_failures);continue;}
            if(macro_complete)
              {
               name=GoldMacroFile(server);temporary=name+"."+MQLInfoString(MQL_PROGRAM_NAME)+"."+(string)ChartID()+".tmp";
               file=FileOpen(temporary,FILE_WRITE|FILE_TXT|FILE_ANSI|FILE_COMMON,0,CP_UTF8);
               if(file!=INVALID_HANDLE)
                 {
                  bool ok=FileWriteString(file,"GOLD_MACRO_V1;"+server+";"+GoldEpoch(now)+";"+(string)macro_count+"\n"+macro_rows+"END\n")>0;
                  FileFlush(file);FileClose(file);
                  if(!ok || !FileMove(temporary,FILE_COMMON,name,FILE_COMMON|FILE_REWRITE))Print("MACRO_PUBLISH_FAILED ",GetLastError());
                 }
              }
            calendar_failures=0;next_refresh=now+60;
           }
         else
           {
            calendar_failures++;next_refresh=now+GoldNewsRetrySeconds(calendar_failures);
            Print("NEWS_EVENT_METADATA_FAILED error=",GetLastError()," retry_seconds=",GoldNewsRetrySeconds(calendar_failures));
           }
        }
      Sleep(1000); // Independent service thread; never the EA tick thread.
     }
  }

#endif
