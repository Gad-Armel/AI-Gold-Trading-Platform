#ifndef GOLD_SCALP_DASHBOARD
#define GOLD_SCALP_DASHBOARD
struct GoldDashboardData
  {
   string mode,status,win_rate,profit_factor,pnl_day,pnl_week,drawdown,equity,spread,atr,flow,mtf,volume,session,news,advisor,risk,execution,learning;
   bool paused,locked;
   int spread_state;
   int candle_seconds;
  };
class CGoldDashboard
  {
private:
   string prefix,last_text[40];
   color last_color[40];
   int width,height,font,row;
   bool enabled,dirty;
   color bg,card,ink,muted,gold,green,orange,red;
   void Rect(const string suffix,const int x,const int y,const int w,const int h,const color fill)
     {
      string name=prefix+suffix;ObjectCreate(0,name,OBJ_RECTANGLE_LABEL,0,0,0);
      ObjectSetInteger(0,name,OBJPROP_XDISTANCE,x);ObjectSetInteger(0,name,OBJPROP_YDISTANCE,y);
      ObjectSetInteger(0,name,OBJPROP_XSIZE,w);ObjectSetInteger(0,name,OBJPROP_YSIZE,h);
      ObjectSetInteger(0,name,OBJPROP_BGCOLOR,fill);ObjectSetInteger(0,name,OBJPROP_BORDER_TYPE,BORDER_FLAT);
      ObjectSetInteger(0,name,OBJPROP_COLOR,fill);ObjectSetInteger(0,name,OBJPROP_CORNER,CORNER_LEFT_UPPER);
      ObjectSetInteger(0,name,OBJPROP_SELECTABLE,false);ObjectSetInteger(0,name,OBJPROP_HIDDEN,true);ObjectSetInteger(0,name,OBJPROP_ZORDER,0);
     }
   void Label(const int id,const int x,const int y,const int size,const string text,const color tint)
     {
      string name=prefix+"L"+(string)id;ObjectCreate(0,name,OBJ_LABEL,0,0,0);
      ObjectSetInteger(0,name,OBJPROP_XDISTANCE,x);ObjectSetInteger(0,name,OBJPROP_YDISTANCE,y);
      ObjectSetInteger(0,name,OBJPROP_CORNER,CORNER_LEFT_UPPER);ObjectSetInteger(0,name,OBJPROP_FONTSIZE,size);
      ObjectSetString(0,name,OBJPROP_FONT,"Segoe UI");ObjectSetInteger(0,name,OBJPROP_SELECTABLE,false);ObjectSetInteger(0,name,OBJPROP_HIDDEN,true);
      last_text[id]="";last_color[id]=clrNONE;Set(id,text,tint);
     }
   void Set(const int id,string text,const color tint)
     {
      if(!enabled)return;
      // Bound long broker/error messages to panel width; full details remain in journal.
      int limit=(width-32)/(font>8?6:5);if(id>=10 && StringLen(text)>limit)text=StringSubstr(text,0,limit-3)+"...";
      string name=prefix+"L"+(string)id;
      if(last_text[id]!=text){ObjectSetString(0,name,OBJPROP_TEXT,text);last_text[id]=text;dirty=true;}
      if(last_color[id]!=tint){ObjectSetInteger(0,name,OBJPROP_COLOR,tint);last_color[id]=tint;dirty=true;}
     }
   void Button(const string suffix,const int x,const int y,const int w,const string text,const color fill)
     {
      string name=prefix+suffix;ObjectCreate(0,name,OBJ_BUTTON,0,0,0);
      ObjectSetInteger(0,name,OBJPROP_XDISTANCE,x);ObjectSetInteger(0,name,OBJPROP_YDISTANCE,y);ObjectSetInteger(0,name,OBJPROP_XSIZE,w);ObjectSetInteger(0,name,OBJPROP_YSIZE,30);
      ObjectSetInteger(0,name,OBJPROP_CORNER,CORNER_LEFT_UPPER);ObjectSetInteger(0,name,OBJPROP_COLOR,ink);ObjectSetInteger(0,name,OBJPROP_BGCOLOR,fill);
      ObjectSetInteger(0,name,OBJPROP_BORDER_COLOR,fill);ObjectSetInteger(0,name,OBJPROP_FONTSIZE,font);ObjectSetString(0,name,OBJPROP_FONT,"Segoe UI Semibold");
      ObjectSetString(0,name,OBJPROP_TEXT,text);ObjectSetInteger(0,name,OBJPROP_ZORDER,100);ObjectSetInteger(0,name,OBJPROP_HIDDEN,true);
     }
public:
   CGoldDashboard(){enabled=false;prefix="";bg=C'15,20,29';card=C'26,34,46';ink=C'230,237,246';muted=C'148,164,185';gold=C'224,185,100';green=C'72,204,157';orange=C'244,180,73';red=C'255,105,115';}
   void Create(const string name,const bool show)
     {
      enabled=show;prefix=name;if(!enabled)return;
      width=(int)MathMin(520,MathMax(320,ChartGetInteger(0,CHART_WIDTH_IN_PIXELS)-24));
      height=(int)MathMin(660,MathMax(470,ChartGetInteger(0,CHART_HEIGHT_IN_PIXELS)-24));
      font=width<440 || height<560?8:9;row=(height-270)/15;
      Rect("BG",12,12,width,height,bg);Rect("LINE",12,12,width,3,gold);
      Label(0,28,26,15,"GOLD / SCALP AI",gold);Label(1,28,53,font,"",muted);
      int half=(width-42)/2;
      Rect("K1",26,78,half,63,card);Rect("K2",36+half,78,half,63,card);
      Label(2,36,85,font,"WIN RATE / POSITIONS CLOSES",muted);Label(3,36,105,17,"--",ink);
      Label(4,46+half,85,font,"PROFIT FACTOR / NET",muted);Label(5,46+half,105,17,"--",ink);
      Label(6,28,154,font,"",green);Label(7,28+half+10,154,font,"",green);
      Label(8,28,177,font,"",muted);Label(9,28,198,font,"",muted);
      for(int i=0;i<15;i++)Label(10+i,28,222+i*row,font,"",ink);
      Button("PAUSE",26,12+height-43,half,"PAUSE ENTREES",card);
      Button("CLOSE",36+half,12+height-43,half,"TOUT FERMER / COMPTE",C'145,45,56');
      dirty=true;
     }
   void Render(const GoldDashboardData &d)
     {
      if(!enabled)return;
      Set(1,d.mode+(d.locked?" | SECURITE 24 H":d.paused?" | PAUSE":" | SURVEILLANCE"),d.locked?red:d.paused?orange:muted);
      Set(3,d.win_rate,ink);Set(5,d.profit_factor,ink);Set(6,"Jour net : "+d.pnl_day,ink);Set(7,"Semaine : "+d.pnl_week,ink);
      Set(8,d.equity,muted);Set(9,d.drawdown,muted);
      Set(10,d.status,gold);Set(11,"Spread : "+d.spread,d.spread_state==2?red:d.spread_state==1?orange:green);
      Set(12,"ATR / volume : "+d.atr+" / "+d.volume,ink);Set(13,"M1 suivante : "+(string)d.candle_seconds+" s | "+d.flow,muted);
      Set(14,"MTF : "+d.mtf,ink);Set(15,"Session : "+d.session,ink);Set(16,"News : "+d.news,ink);
      Set(17,"Advisor 1 : "+d.advisor,ink);Set(18,d.risk,d.locked?red:ink);
      Set(19,d.execution,muted);Set(20,d.learning,muted);
      Set(21,"KPI EA : 30 j glissants / net commissions",muted);Set(22,"DD compte : observe, persiste depuis activation",muted);
      Set(23,"Pause = entrees stoppees, sorties maintenues",muted);Set(24,"Close All = positions + ordres de tout le compte",muted);
      string button=prefix+"PAUSE",text=d.locked?"VERROUILLE 24 H":d.paused?"REPRENDRE ENTREES":"PAUSE ENTREES";
      if(ObjectGetString(0,button,OBJPROP_TEXT)!=text){ObjectSetString(0,button,OBJPROP_TEXT,text);dirty=true;}
      if(dirty){ChartRedraw(0);dirty=false;}
     }
   int Action(const string name)
     {
      if(!enabled)return 0;
      if(name!=prefix+"PAUSE" && name!=prefix+"CLOSE")return 0;
      ObjectSetInteger(0,name,OBJPROP_STATE,false);return name==prefix+"PAUSE"?1:2;
     }
   void Destroy(){if(enabled && prefix!="")ObjectsDeleteAll(0,prefix);enabled=false;}
  };
#endif
