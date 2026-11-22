#property strict
#property version "2.00"
#property description "Dashboard layout preview with illustrative values. Never sends orders."
#include "GoldScalpDashboard.mqh"
input bool SaveScreenshot=false;
input bool CloseTerminalAfterScreenshot=false;
CGoldDashboard panel;
GoldDashboardData data;
int ticks=0;
int OnInit()
  {
   panel.Create("GOLD_PREVIEW_",true);
   data.mode="APERCU UI / VALEURS FICTIVES";data.status="Filtre spread glissant actif";
   data.win_rate="54.2% / 48";data.profit_factor="1.12";data.pnl_day="+1.24 USD";data.pnl_week="+3.08 USD";
   data.equity="Equity compte 103.08 USD | flottant EA +0.32";data.drawdown="DD actuel 0.42% / max 2.15%";
   data.spread="0.280 / max 0.300 | moy100 0.170";data.spread_state=2;data.atr="1.340";data.volume="1.23x OK";
   data.candle_seconds=24;data.flow="flux HAUSSE";data.mtf="M1 1 | M5 1 | M15 1 | H1 1 (+1/-1/0)";
   data.session="Overlap configure / OUVERTE";data.news="OK / calendrier natif";data.advisor="REQUIS / BUY 78/100";
   data.risk="0.01 fixe | max 3 | equity -3.0% / 24h";data.execution="En attente / aucune requete dans cet apercu";
   data.learning="Modele OBSERVATION | n=284 | Brier 0.251";
   panel.Render(data);EventSetTimer(1);return INIT_SUCCEEDED;
  }
void OnTick(){}
void OnTimer()
  {
   ticks++;panel.Render(data);
   if(SaveScreenshot && ticks==3)
     {
      bool saved=ChartScreenShot(0,"GoldScalpDashboard.png",1100,780,ALIGN_LEFT);
      Print("DASHBOARD_PREVIEW screenshot=",saved," path=MQL5/Files/GoldScalpDashboard.png");
      if(saved && CloseTerminalAfterScreenshot)TerminalClose(0);
     }
  }
void OnChartEvent(const int id,const long &lparam,const double &dparam,const string &name)
  {
   if(id==CHARTEVENT_CHART_CHANGE){panel.Destroy();panel.Create("GOLD_PREVIEW_",true);panel.Render(data);}
   if(id!=CHARTEVENT_OBJECT_CLICK)return;int action=panel.Action(name);
   if(action==1){data.paused=!data.paused;data.status="Apercu : bascule pause, aucun ordre";}
   if(action==2){data.paused=true;data.status="Apercu : fermeture simulee, aucun ordre";}
   panel.Render(data);
  }
void OnDeinit(const int reason){EventKillTimer();panel.Destroy();}
