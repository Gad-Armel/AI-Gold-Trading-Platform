# GoldScalpAI 3.29 - architecture, dashboard et validation

> Mise a jour 23 novembre 2026 (fermeture de session courtier): l'EA lit les
> sessions de trading MT5 et bloque les nouvelles entrees dans les cinq
> dernieres minutes d'une session ouverte. Il tente de fermer toutes les
> positions du symbole exact du graphique, y compris celles qui ne sont pas
> gerees par cet EA. L'heure est celle du serveur du courtier. Les jours feries
> et changements non programmes peuvent differer; une deconnexion, une absence
> de cotation ou un rejet courtier peut empecher la fermeture. Le statut et le
> nombre de positions restantes sont publies au dashboard. Il s'agit d'une
> tentative de reduction du risque, pas d'une garantie de fermeture.
>
> L'horaire attendu du vendredi 22:00 au dimanche 23:00 n'est pas impose en
> UTC: les heures XAUUSD varient selon le courtier, son fuseau serveur et les
> changements saisonniers. L'EA lit les sessions MT5 du symbole avec
> `SymbolInfoSessionTrade`; confirmer les heures sur le compte demo connecte.

> Update 22 November 2026 (unified demo schedule): the local unified dashboard
> writes a V2 Common/Files config that can add one daily UTC entry blackout.
> The current selection blocks new entries from 22:00 inclusive to 23:00
> exclusive; open positions continue to be managed. Existing broker-session,
> news, risk and demo-account gates remain active. V1 config files remain
> readable without an added blackout. The EA snapshot acknowledges the parsed
> schedule. Dashboard timeframe selection remains informational and does not
> change the EA analysis periods or the M1 candle export.

> Update 27 October 2026 (3.26, demo frequency experiment): frequent mode now
> uses a score floor of 50, one-second entry pacing, a 60-entry/hour cap,
> lower short-flow impulse floors, and a 50-quote spread warm-up. These changes
> target more eligible entries, not better expected value. Fixed lot, position
> cap, stops, execution-cost/news filters, demo-only policy and loss safeguards
> are unchanged. Forward demo fills are required to evaluate results.

> Update 27 October 2026 (3.25): in scalp mode, entries may be considered in
> every UTC session, including Asia and 21:00-23:00 UTC, whenever the broker
> reports XAUUSD open. The launcher disables the optional Asia entry gate.
> Broker closure, spread, signal, news and risk checks remain active. This
> policy change increases exposure to the previously documented Asia stop-out
> concentration; it does not establish profitability.

> Update 26 October 2026 (3.24): the 3% equity/shock safety lock now cancels
> and closes only this EA's exact-symbol XAUUSD orders/positions. It still
> blocks new entries from this EA for the safety-lock period. The explicit
> account-wide Close All control is unchanged. Build: 0 errors/warnings;
> deterministic self-test: 239 checks, 0 failures. These checks do not prove
> trading profitability.
> The timer path also performs its account-level risk scan once per timer event,
> not twice; quote-driven OnTick checks remain active.

R?vision du 25 septembre 2026. Le programme principal est
`mql5/Experts/GoldScalpAI/GoldScalpAI.mq5` ; son ex?cutable est `GoldScalpAI.ex5`.
Les nouveaux algorithmes, le dashboard et le collecteur de calendrier sont natifs
MQL5, sans DLL, indicateur payant, abonnement ni API externe payante.

Gold Advisor 1 reste inchang? : son programme Python et ses 17 d?pendances sont
prot?g?s par empreintes SHA-256. L'EA consomme son rapport SCALP existant ; les
petits utilitaires de transport/export ne r?impl?mentent aucun de ses calculs.

## Ce qui a chang? et pourquoi

| Domaine | Version pr?c?dente | Version 2.00 |
|---|---|---|
| Interface | Texte `Comment()` | Panneau sombre/or, cartes KPI, filtres, ?tat d'ex?cution, boutons Pause et Close All |
| Entr?es | Flux 6/12 s et M1/M5 | Accord obligatoire M1/M5/M15/H1, rejets de m?ches, d?tection de balayage intrabougie, volume relatif |
| Spread | Plafond absolu et ratio ATR | Ajout d'une moyenne glissante des 100 observations pr?c?dentes, seuil 1,5? ; la nouvelle valeur ne dilue pas son propre contr?le |
| Indicateurs | Rafra?chissement appel? dans OnTick | Handles persistants ; lecture des bougies cl?tur?es depuis le timer, seulement au changement de bougie |
| Calendrier | Appel natif synchrone dans l'EA | Service MQL5 ind?pendant ; lecture locale d'un fichier horodat? par l'EA |
| Ex?cution | Envoi synchrone et attente fixe | `OrderSendAsync` par d?faut, r?servations et corr?lation par request_id, r?conciliation des ordres dans l'historique |
| Requotes | Pas de reprise structur?e | Deux reprises suppl?mentaires maximum, sans Sleep, seulement pour rejets de prix certains, avec revalidation du contexte et du risque |
| Protection | Coupe-circuit local en m?moire | Equity de tout le compte ? ?3 %, pause persistante 24 h, annulation des ordres en attente et liquidation globale |
| Advisor 1 | R?f?rence s?par?e | Confirmation obligatoire par d?faut ; validit? temporelle, symbole exact, proximit? du prix et rejeu historique causal |

La priorit? reste : survie du compte, co?ts r?els, fiabilit? de l'ex?cution,
qualit? des donn?es, sorties, puis pr?cision du signal. Aucun poids de rentabilit?
invent? n'est attribu? ? ces facteurs. Ajouter des filtres peut r?duire les faux
signaux **et** supprimer des opportunit?s rentables : cela reste ? mesurer.

## R?partition des t?ches et vitesse

`OnTick` effectue les contr?les d'equity, le contr?le de choc, les sorties et les
calculs born?s du flux. Le spread glissant utilise un tampon de 100 valeurs avec
une somme maintenue en O(1). Le flux bid/ask est ?chantillonn? au maximum ? 10 Hz ;
les protections de prix restent ?valu?es ? chaque nouvelle cotation trait?e.
Les modifications de SL sont espac?es d'au moins 250 ms et doivent am?liorer
r?ellement le niveau. Les tentatives de fermeture disposent aussi d'un d?lai
minimal pour ?viter un d?luge de requ?tes apr?s un rejet.

Le timer tourne toutes les 250 ms. Les t?ches ordinaires et l'affichage tournent
au maximum une fois par seconde ; les objets graphiques ne re?oivent de nouvelles
valeurs que si leur texte ou couleur change. Il n'y a pas de rendu par tick.
L'historique est reconstruit apr?s transaction, modification du capital, passage
au jour suivant ou toutes les 30 secondes. Les identifiants de positions sont
tri?s puis recherch?s par recherche binaire, au lieu d'une recherche quadratique
pour chaque deal. Un historique anormalement volumineux bloque les entr?es.

Les indicateurs restent calcul?s par MT5 ; seules leurs derni?res valeurs
cl?tur?es sont lues lors d'une nouvelle bougie. L'ATR intrabougie utilise ensuite
les extr?mes observ?s et la cl?ture pr?c?dente, sans recopier les s?ries ? chaque
quote. L'initialisation exige suffisamment de barres sur chaque timeframe.

Le collecteur `GoldScalpNewsFeed` tourne dans son propre thread de service.
Une r?ponse lente du calendrier ne bloque donc plus la file d'?v?nements de l'EA.
L'historique et les objets MT5 utilisent encore le thread de l'EA : ce travail est
r?duit et cadenc?, mais aucune latence totale n'est garantie. Le dashboard mesure
le temps de calcul d'OnTick en microsecondes ; ce chiffre n'inclut pas l'attente
r?seau du courtier ni l'attente dans la file des ?v?nements.

## Signal et sorties

- Sens du flux coh?rent sur 6 et 12 secondes, avec d?placement commun du bid et
  de l'ask. Un simple ?largissement du spread ne constitue pas un achat.
- Tendance M1, M5, M15 et H1 align?e sur EMA 9/21 et cl?tures termin?es.
- Rejet d'une entr?e apr?s excursion au-del? des extr?mes des 20 bougies
  pr?c?dentes puis retour, avec m?che de rejet. Un balayage de la bougie courante
  est ?galement v?rifi?. Il s'agit d'un proxy de pi?ge de prix, pas d'une preuve
  de liquidit? cach?e ou d'ordres institutionnels.
- Volume relatif de la derni?re M1 cl?tur?e compar? aux 20 pr?c?dentes :
  intervalle par d?faut 1,05? ? 6?. Le tick volume du courtier mesure l'activit?
  de cotation, pas le volume mondial ?chang? sur l'or.
- Confirmation temporelle, limite d'extension du prix et contr?le du mouvement
  disponible apr?s spread, commissions et slippage pr?vu.
- En mode requis, Advisor 1 doit produire un SCALP BUY/SELL concordant, encore
  valide, ?g? d'au plus 90 s, pour le symbole exact. Le prix ne peut pas s'?tre
  ?loign? de plus de 0,75 ATR de sa r?f?rence. WAIT reste WAIT.

Le trailing et les seuils d'armement du breakeven s'adaptent ? l'ATR observ? et aux
co?ts. Le SL ne peut ?tre desserr?. Une position peut ?tre ferm?e avant son TP
sur retournement profitable, retournement d?favorable confirm?, restitution
excessive des gains, retour au seuil de conservation ou stagnation.
Le SL courtier reste obligatoire ; le TP ATR peut ?tre d?sactiv? avec
`UseBrokerTakeProfit=false`. Pause, session ferm?e, blocage de spread ou r?f?rence
absente n'emp?chent pas la gestion des positions d?j? ouvertes.

Le petit mod?le logistique local reste en observation par d?faut. Il estime
une direction du milieu bid/ask ? environ 30 secondes, pas une probabilit? de
profit net. Les cibles futures sont masqu?es jusqu'? leur ?ch?ance et les
interruptions invalident les observations en attente. Le veto exp?rimental reste
subordonn? ? 2 000 observations et ? son score de Brier face ? une r?f?rence.
Ces crit?res internes ne prouvent pas une sup?riorit? hors ?chantillon.

## Risque, ex?cution et port?e des boutons

Le volume des nouvelles demandes est fix? dans le code ? **0,01 lot**. Le
plafond est **3 positions/ordres en attente sur le compte**, pas trois par chart.
Le risque pr?vu par entr?e reste limit? ? 2 USD, le risque agr?g? ? 4 USD par
d?faut et la perte r?alis?e-plus-flottante propre ? l'EA sur 24 h ? 5 USD.
Le budget d'equity restant est aussi v?rifi? avant l'entr?e : avec 100 USD,
il peut donc ?tre interdit d'ouvrir une deuxi?me ou troisi?me position.

La protection globale compare l'equity au capital du d?but de journ?e serveur,
reconstitu? ? partir de l'historique et ajust? des d?p?ts, retraits et cr?dits.
Elle inclut les pertes flottantes de **tout le compte**. ? ?3 % par d?faut,
l'EA m?morise un verrou de 24 heures et bloque ses nouvelles entr?es. Il annule
ses propres ordres XAUUSD et ferme uniquement ses propres positions XAUUSD
(symbole exact et Magic correspondant) ; les positions manuelles, les autres
symboles et les autres robots ne sont pas liquid?s. Un choc de prix d?passant le
seuil ATR/spread alors que le compte est expos? peut d?clencher cette m?me
protection limit?e aux positions de cet EA. Le verrou ne bloque pas les entr?es
d'autres Experts Advisors du compte. Une modification du solde impose sa
r?conciliation avant de r?utiliser le budget.

- **Pause Trading** : suspend uniquement les nouvelles entr?es ; les sorties,
  stops et protections restent actifs. Le bouton ne l?ve pas le verrou de s?curit?.
- **Tout fermer / compte** : action manuelle distincte, elle lance l'annulation
  des ordres et la fermeture de toutes les positions du compte ; elle active
  aussi la pause d'entr?e. Si les ordres d?mo sont d?sactiv?s, le panneau
  l'indique et aucune demande n'est envoy?e.

Ces limites ne garantissent pas une perte maximale absolue : gaps, d?connexion,
prix manquant, march? ferm? ou rejet du courtier peuvent retarder les sorties.
Les stops c?t? courtier restent n?cessaires. La d?viation demand?e n'est pas une
promesse de prix sur tous les modes d'ex?cution.

Les requotes et changements de prix certains autorisent deux nouvelles tentatives
au maximum sur une dur?e born?e de trois secondes. Chaque tentative recalcule
prix, SL, TP, co?ts, marge et autorisations. Une entr?e avec timeout/connexion
incertaine n'est **jamais r??mise aveugl?ment** ; son verrou persiste jusqu'?
r?conciliation certaine ou examen manuel. Les remplissages partiels ne sont pas
compl?t?s automatiquement. Les callbacks ne sont pas suppos?s arriver dans un
ordre fixe. Le mode synchrone reste disponible avec `AsyncExecution=false`.

Une seule instance native v2 peut poss?der le verrou du compte. Ne pas ex?cuter
le bot Python et l'EA simultan?ment sur le m?me compte : les v?rifications de
positions ne constituent pas une transaction atomique entre logiciels distincts.
Apr?s un crash, un verrou d'instance peut rester pr?sent dans les variables
globales MT5 (F3). Ne le retirer qu'apr?s avoir v?rifi? l'absence d'instance active.
Ne pas effacer les verrous de protection ou d'entr?e incertaine pour contourner
une fermeture d'urgence ou une r?conciliation inachev?e.

## Dashboard : ce qui est r?ellement mesur?

Le panneau sombre avec accent or comporte deux cartes principales, Win Rate et
Profit Factor, puis P/L quotidien et hebdomadaire, equity, flottant et drawdown.
Sous ces cartes figurent le motif ex?cutif d'attente, le spread color?,
l'ATR/volume, le compte ? rebours M1, les quatre tendances, les sessions, les news,
Advisor 1, le risque et les retours d'ex?cution.

Les trades compt?s pour Win Rate/PF sont des **positions enti?rement cl?tur?es**
appartenant ? l'EA sur 30 jours glissants, avec origine identifi?e. Les ex?cutions
partielles ne gonflent pas ce nombre. Profit, commissions, swaps et frais sont
inclus ; les positions manuelles liquid?es par Close All ne deviennent pas des
trades de l'EA. Sans ?chantillon, le panneau affiche `--`, pas un taux invent?.
Sans perte observ?e, il indique ? sans perte ?, pas un PF arbitraire.

Les P/L quotidiens et hebdomadaires sont les flux r?alis?s nets de l'EA selon le
calendrier serveur. Le drawdown est celui de l'equity du compte **observ?e pendant
le fonctionnement**, avec maximum m?moris?. Il ne reconstitue pas les creux non
observ?s avant installation ou pendant une interruption. Si le capital a chang?
hors ligne, un nouveau segment de drawdown courant commence ; le maximum d?j?
observ? est conserv?. Les flux de financement observ?s en direct ajustent le sommet.

L'EA `GoldScalpDashboardPreview` affiche le m?me composant graphique avec des
**chiffres fictifs explicitement indiqu?s**, sans envoyer d'ordre. Les boutons
y simulent seulement l'?tat visuel. Le terminal isol? a charg? l'aper?u mais
n'a pas produit de capture sans compte connect? : aucun test visuel r?ussi
n'est revendiqu?. L'aper?u peut ?tre ajout? ? un graphique dans votre terminal.

## Compilation, installation et d?marrage

Depuis le dossier du projet :

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\tools\compile_gold_scalp.ps1
powershell -NoProfile -ExecutionPolicy Bypass -File .\tools\test_gold_scalp.ps1
```

Le compilateur est par d?faut `C:\Program Files\MetaTrader\MetaEditor64.exe`.
Le script compile l'EA, les tests, l'aper?u et le service. `-MetaEditor` permet
un autre chemin. Bypass ne s'applique qu'au processus PowerShell lanc?.

Dans MT5, **Fichier ? Ouvrir le dossier des donn?es**, puis utiliser son chemin :

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\tools\install_gold_scalp.ps1 -DataDirectory "CHEMIN_DU_DOSSIER_DE_DONNEES_MT5"
```

Ce script copie les sources et ex?cutables ; il n'attache aucun EA et n'active
pas le trading. Retirer l'ancienne instance avant de charger la nouvelle.

1. Compte **d?mo, USD, hedging**, symbole XAUUSD exact du courtier, graphique M1.
2. Dans le navigateur MT5, ajouter/d?marrer le service `GoldScalpNewsFeed`.
3. Lancer Advisor 1 inchang? dans une console, puis le transport dans une autre :

```powershell
python -B .\run_gold_advisor.py
```

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\tools\publish_advisor1_reference.ps1 -Watch
```

4. Ajouter **GoldScalpAI**, pas SelfTest ou DashboardPreview, au graphique.
   `EnableDemoOrders=false` observe ; `true` permet les ordres d?mo si les autres
   autorisations MT5 sont actives. Les comptes r?els sont refus?s.
5. V?rifier `ServerUTCOffsetMinutes` (180 = UTC+3), les commissions r?elles,
   les caract?ristiques du symbole et le statut de chaque source sur le panneau.

Les fichiers de transport sont dans `%APPDATA%\MetaQuotes\Terminal\Common\Files\GoldScalp`.
Le transport conserve la date d'origine d'Advisor 1 : recopier un vieux rapport
ne le rend pas frais. Le service de news expire apr?s 120 s ; son indisponibilit?
La session UTC 13-16 ne s'applique que si ExpertScalpMode=false.
Depuis la v3.25, le mode scalp autorise les entrees dans toutes les
sessions, y compris l'Asie et 21-23 UTC, si le calendrier de trading du
broker indique XAUUSD ouvert. Le lanceur met BlockAsiaSession=false.
La v3.23 avait bloque l'Asie apres l'etude du 21 octobre 2026, qui y
concentrait 62 des 112 stops (-236 $ sur -398 $), alors que Londres
etait a l'equilibre. Le retour en Asie est un choix de politique explicite,
pas une conclusion de rentabilite. Les filtres de spread, signal, news et
risque restent actifs. Les heures de fermeture du broker bloquent toujours
les nouvelles entrees ; les positions ouvertes restent gerees normalement.

En v3.26, le profil frequente de demo utilise score minimum 50, espacement
minimum d'une seconde, plafond de 60 entrees/heure et seuils de flux court
moins stricts. La reference glissante du spread chauffe sur 50 cotations.
Le plafond absolu, le ratio spread/ATR, le cout par rapport a la cible,
les confirmations, actualites, stops, limites de lots et de risque restent
actifs. Cette sensibilite peut augmenter les faux signaux et les pertes ;
aucune rentabilite n'est revendiquee.

## Strategy Tester et causalit? historique

Choisir **Chaque tick bas? sur des ticks r?els**, d?p?t 100 USD, levier et
commissions du compte, d?lai d'ex?cution r?aliste. Les ordres du testeur sont
simul?s m?me si `EnableDemoOrders=false`. Comparer plusieurs p?riodes et des
d?lais de 150/300 ms, r?server une p?riode chronologique hors ?chantillon et
comparer s?par?ment chaque filtre ; ne pas s?lectionner seulement le meilleur mois.

Exporter les rapports existants d'Advisor 1 :

```powershell
python -B .\tools\export_advisor1_replay.py
Copy-Item -LiteralPath .\mql5\validation\advisor1_replay.csv -Destination "$env:APPDATA\MetaQuotes\Terminal\Common\Files\GoldScalp\advisor1_replay.csv"
```

Configurer `Advisor1ReplayFile=GoldScalp\advisor1_replay.csv` dans le testeur.
L'export effectu? a retenu 11 672 rapports et ?cart? un enregistrement invalide.
Le lecteur avance chronologiquement, garde le prochain rapport futur en attente
et limite le rattrapage ? 500 lignes par appel. Les entr?es attendent la fin du
rattrapage et l'expiration reste applicable. Le testeur ne lit jamais le rapport
courant ? la place d'un historique. Utiliser uniquement les agents locaux.

Sans historique correspondant, `Advisor1Mode=GOLD_ADVISOR_REQUIRED` bloque les
entr?es. `GOLD_ADVISOR_REFERENCE` permet une comparaison explicite sans ce veto ;
ce n'est pas la m?me politique que le mode requis. Ne pas confondre leurs r?sultats.
Les fonctions natives du calendrier ne fonctionnent pas dans le testeur :
`TesterWithoutNews=true` signifie **test sans filtre news**, clairement signal?.
Avec `false` et `UseNativeNews=true`, les entr?es sont bloqu?es. Ce point emp?che
?galement de pr?senter un backtest sans news comme une validation de toute la
politique ex?cut?e en direct.

## Validation et limites des r?sultats

- Quatre programmes compil?s : **0 erreur, 0 avertissement**.
- **79 v?rifications MQL5** ex?cut?es dans le Strategy Tester, sans ?chec.
- **221 tests Python** passent ; les 18 fichiers prot?g?s sont inchang?s.
- Transport r?el du rapport Advisor 1 contr?l? champ par champ.
- Microbenchmark du tampon de spread et tests de replay, requote, timeout,
  remplissage partiel, funding, pause 24 h, retournement et breakeven disponibles.
- Aucune commande de trading r?el activ?e. Le backtest de rentabilit? sur ticks
  r?els avec compte d?mo n'a pas ?t? ex?cut? pendant cette r?vision.

Les journaux et empreintes sont dans `mql5/validation`. Les cotations synth?tiques
servent uniquement aux invariants logiciels. Le microbenchmark ne mesure ni le
slippage r?el ni la rentabilit?. Aucun ? rendement ultime ?, z?ro requote, ou
avantage ?conomique hors ?chantillon n'est revendiqu?.

## Sources officielles gratuites

- [Mod?le de threads MQL5](https://www.mql5.com/en/docs/runtime/running) : un service
  dispose de son propre thread, utilis? ici pour isoler le calendrier.
- [OrderSendAsync](https://www.mql5.com/en/docs/trading/ordersendasync) et
  [OnTradeTransaction](https://www.mql5.com/en/docs/event_handlers/ontradetransaction) :
  un envoi accept? n'est pas une ex?cution garantie ; les ?v?nements peuvent
  arriver dans des ordres diff?rents et leur file est born?e.
- [Retcodes](https://www.mql5.com/en/docs/constants/errorswarnings/enum_trade_return_codes) :
  classification entre rejets certains, acceptation et r?sultat incertain.
- [Propri?t?s des deals](https://www.mql5.com/en/docs/constants/tradingconstants/dealproperties) :
  entry/out, propri?t? de position, commissions, swaps, frais et financement.
- [OnChartEvent](https://www.mql5.com/en/docs/event_handlers/onchartevent) :
  actions des boutons ; rendu sur timer avec objets natifs.
- [Fichiers MQL5](https://www.mql5.com/en/docs/files/fileopen) et
  [FileMove](https://www.mql5.com/en/docs/files/filemove) : ?change local avec
  publication temporaire puis remplacement et respect du sandbox MQL5.
- [Configuration MT5](https://www.metatrader5.com/en/terminal/help/start_advanced/start)
  et [Strategy Tester](https://www.metatrader5.com/en/terminal/help/algotrading/testing) :
  modes de simulation, agents locaux, d?lais, commissions et ticks r?els.

## Nettoyage et protection pr?serv?s

Le nettoyage pr?c?dent a supprim? 104 caches et, apr?s confirmation explicite,
les cinq archives V6. Les historiques et tests utiles restent conserv?s.
Les manifestes sont dans `data/research/project_cleanup`. Aucune nouvelle
suppression de donn?es de recherche ni modification de Gold Advisor 1 n'est
n?cessaire pour cette version.
