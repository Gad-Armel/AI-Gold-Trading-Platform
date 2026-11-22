#ifndef GOLD_SCALP_WIRE
#define GOLD_SCALP_WIRE
// datetime -> string formats a date in MQL5. Wire timestamps must cast to long first.
string GoldEpoch(const datetime value){return (string)(long)value;}
string GoldJson(const string value)
  {
   string out="\"";
   for(int i=0;i<StringLen(value);i++)
     {
      ushort c=StringGetCharacter(value,i);
      if(c==34)out+="\\\"";
      else if(c==92)out+="\\\\";
      else if(c<32)out+=StringFormat("\\u%04x",(int)c);
      else out+=ShortToString(c);
     }
   return out+"\"";
  }
string GoldNumber(const double value,const int precision=5){return MathIsValidNumber(value)?DoubleToString(value,precision):"null";}
string GoldBool(const bool value){return value?"true":"false";}
string GoldRateJson(const MqlRates &r)
  {return "{\"time\":"+GoldEpoch(r.time)+",\"open\":"+GoldNumber(r.open)+",\"high\":"+GoldNumber(r.high)+",\"low\":"+GoldNumber(r.low)+",\"close\":"+GoldNumber(r.close)+",\"volume\":"+(string)r.tick_volume+"}";}
string GoldNewsLine(const string server,const datetime now,const datetime &events[])
  {
   string line="GOLD_NEWS_V1;"+server+";"+GoldEpoch(now)+";"+(string)ArraySize(events);
   for(int i=0;i<ArraySize(events);i++)line+=";"+GoldEpoch(events[i]);
   return line+";END\r\n";
  }
#endif
