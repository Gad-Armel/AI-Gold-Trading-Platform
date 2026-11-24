#property strict
#property version "2.02"
#property description "Native news worker started with the EA; separate script thread, no orders."
#include "../Services/GoldScalpNewsPublisher.mqh"
void OnStart(){GoldRunNewsPublisher();}
