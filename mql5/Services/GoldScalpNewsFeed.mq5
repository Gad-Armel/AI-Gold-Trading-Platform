#property service
#property version "2.02"
#property description "Free native news publisher; separate thread, no orders."
#include "GoldScalpNewsPublisher.mqh"
void OnStart(){GoldRunNewsPublisher();}
