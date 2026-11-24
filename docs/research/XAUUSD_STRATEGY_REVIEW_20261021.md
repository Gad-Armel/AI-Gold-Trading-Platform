# XAUUSD : recherche, replay causal et observation du 21 octobre 2026

## Périmètre et décision

Travail commencé à **09:56:53 UTC / 10:56:53 Lagos**, avec une durée minimale
demandée de 45 minutes de recherche, tests et observation. Le bilan final de
l'observation est ajouté à la fin de cette session, pas inventé à l'avance.

Ce travail concerne le **main Python `run_gold_consensus_bot.py`**, pas une
réécriture ni une activation de l'EA natif présent ailleurs dans ce dépôt.
Advisor 1 et ses 18 fichiers protégés restent inchangés. Les deux exécutants
ne doivent pas être lancés ensemble pour multiplier artificiellement les ordres.

**Aucune stratégie bénéficiaire après coûts n'a été démontrée.** Le moteur
combiné est implémenté et observé sans ordres. Les nouvelles entrées du main
sont explicitement suspendues ; la gestion des positions existantes et leurs
SL courtier restent active. Il serait trompeur de présenter une variante perdante
comme une amélioration validée, ou de continuer à modifier ses paramètres
jusqu'à obtenir fortuitement un résultat positif.

## 1. Le marché réellement observé aujourd'hui

Source : historique bid/ask du compte démo MetaQuotes, pas un prix consolidé
de tout le marché de l'or. Le décalage de ce serveur, vérifié séparément,
est UTC+3 ; les fichiers conservent aussi les horodatages bruts.

Premier échantillon : **442 032 quotes**, du 20 octobre 09:59:07 UTC au
21 octobre 09:59:06 UTC. Les statistiques du jour ci-dessous sont donc
**incomplètes**, arrêtées avant 10:00 UTC, et non une prévision de clôture.

| Fenêtre du 21 octobre, UTC | Ouverture midpoint | Plus haut | Plus bas | Dernier midpoint | Spread médian |
| --- | ---: | ---: | ---: | ---: | ---: |
| 00:00–09:59 | 4114,075 | 4129,590 | 4106,270 | 4118,330 | 0,38 |
| 00:00–07:00 | 4114,075 | 4129,590 | 4106,270 | 4112,330 | 0,39 |
| 07:00–09:59 | 4112,355 | 4125,945 | 4111,660 | 4118,330 | 0,35 |

Cela décrit une progression nette pendant le début de Londres, mais aussi
des fluctuations dans les deux sens : une hausse sur trois heures n'implique
pas qu'un achat de quelques ticks soit rentable. Les noms de sessions sont des
fenêtres descriptives UTC pour cette date d'octobre, pas des horaires universels.

Une capture élargie demandant 72 heures contient **1 139 451 quotes**. Elle
commence réellement le dimanche 18 à 22:00 UTC, après la fermeture de marché,
et finit le 21 à 10:11:22 UTC. Les deux jeux se chevauchent : ce n'est pas un
second test aveugle indépendant.

### Calendrier vérifié et limites des informations web

- Le BLS programme les **Usual Weekly Earnings, T3** le 21 octobre à
  10:00 Eastern, soit **14:00 UTC / 15:00 Lagos**. Ne pas inventer un CPI ou
  un NFP aujourd'hui : les dates du calendrier sont différentes. La présence
  d'une publication ne signifie pas automatiquement « news majeure ».
  [Calendrier BLS](https://www.bls.gov/schedule/2026/10_sched.htm).
- La réunion FOMC est annoncée les **27–28 octobre**, pas pendant cette
  observation. [Calendrier officiel Fed](https://www.federalreserve.gov/newsevents/2026-october.htm).
- Les enchères de référence LBMA ont lieu à 10:30 et 15:00 Londres, soit
  09:30 et 14:00 UTC à cette date. Ce sont des repères de contexte, pas un
  signal d'achat automatique ni un flux tick gratuit.
  [Méthode LBMA](https://www.lbma.org.uk/prices-and-data/about-lbma-daily-auction-prices).
- Le commentaire WGC du 7 octobre décrit **septembre**, notamment le dollar,
  les rendements et les positions futures. Il ne fournit pas la direction
  intrajournalière du 21 octobre.
  [Commentaire mensuel WGC](https://www.gold.org/goldhub/research/gold-market-commentary).
- Les volumes WGC agrègent plusieurs places et produits, avec estimations et
  délais. Le tick volume du broker n'est pas ce volume mondial.
  [Méthodologie et volumes WGC](https://www.gold.org/goldhub/data/gold-trading-volumes).

Les recherches web n'ont pas fourni de cours primaire tick-by-tick actuel
utilisable en exécution. Les prix d'articles, les graphiques publicitaires et
les opinions contradictoires de particuliers ne remplacent donc pas le flux MT5.
Le calendrier BEA dynamique n'a pas pu être complètement extrait : on ne peut
pas en déduire qu'aucune publication BEA n'existe. Les contrôles calendrier
existants ne sont pas supprimés.

## 2. Pourquoi les « bons signaux » n'ont pas suffi

L'audit des entrées ouvertes après la correction de cohérence entrée/sortie
de 09:04:51 UTC donne **22 positions closes, 7 gains, 15 pertes, net −9,28 USD,
profit factor 0,29**. Gain moyen : 0,5414 ; perte moyenne : 0,8713.
Avec ces tailles moyennes, l'équilibre demanderait environ **61,7 % de gains**,
contre 31,8 % observés. C'est un petit échantillon descriptif, pas une estimation
stable du taux futur.

| Politique d'entrée de cette cohorte | Positions | Net USD |
| --- | ---: | ---: |
| S5 | 8 | −3,37 |
| S15 | 8 | −2,89 |
| S30 | 6 | −3,02 |

Un score de corps de bougie de 85/100 n'est pas une probabilité de réussite de
85 %. Les protections de sortie peuvent limiter une perte ; elles ne créent
pas une espérance positive à partir d'une entrée sans avantage après coûts.
Sur l'historique mélangé, certains trades sortis par giveback étaient même
perdants : un pic positif peut être plus petit que la marge de bruit du trailing,
et le prix d'exécution peut encore glisser. Le nom d'une sortie ne garantit pas
son résultat. Ce constat ne prouve pas qu'attendre plus longtemps aurait aidé.

Frais mesurés en lecture seule à 10:04 UTC : **57 paires réconciliées**,
commission observée 0,00, slippage défavorable p95 aller-retour 0,08 en équivalent
prix, `order_send` p95 163,33 ms. Ce ne sont ni des bornes garanties ni des coûts
connus avant l'ensemble de l'historique. Le profil provisoire déjà autorisé
reste distinct : 0,10 de commission + 0,20 de slippage, spread ajouté séparément.

## 3. Verdict sur « entrée au deuxième tick, sortie au cinquième »

Sur le premier jeu, 110 108 séries atteignent deux changements de midpoint de
même sens ; seulement 10 734 atteignent cinq, soit **9,75 %**. Parmi ces seules
séries réussissant à atteindre cinq, le mouvement du deuxième au cinquième est
de **0,115 médian**, et 0,275 au 90e percentile, pour environ **0,296 seconde**
médiane. C'est une sélection optimiste excluant déjà les séries avortées.
Même là, le déplacement médian est inférieur au spread médian de 0,38.

Les ticks MT5 peuvent modifier seulement le bid ou seulement l'ask ; une hausse
du midpoint ne prouve pas un achat agressif réel. La documentation décrit ces
champs et leurs flags, pas un avantage prédictif.
[Structure MqlTick](https://www.mql5.com/en/docs/constants/structures/mqltick).

L'étude de Cont, Kukanov et Stoikov porte sur le déséquilibre du **carnet** de
50 actions américaines, non sur une série de midpoints d'un CFD XAUUSD. Elle
ne permet pas de baptiser notre compteur de ticks « vrai order flow ».
[Article de recherche](https://arxiv.org/abs/1011.6402).

**Décision : ne pas activer les rafales de deux positions sur cette seule règle.**
Deux positions identiques doublent surtout l'exposition et les coûts du même
pari ; elles ne fournissent pas deux confirmations indépendantes.

## 4. Comparaison des familles de scalping

| Famille | Intérêt structurel | Limite / décision ici |
| --- | --- | --- |
| Séries de ticks | Réaction très rapide | Mouvement trop petit après spread et latence dans nos tests ; rejetée |
| Bougies consécutives | Simple et explicable | Peut acheter/vendre la fin d'une impulsion ; résultats démo négatifs |
| Tendance + repli confirmé | Évite de poursuivre chaque impulsion | Implémentée, mais replay négatif : observation seulement |
| Cassure + retest | Attend une confirmation au niveau repris | Combinée au moteur de repli ; aucun avantage validé |
| Sweep / retour à la moyenne | Hypothèse adaptée à certains ranges | Détecteurs existants conservés en recherche, pas de promotion opportuniste |
| VWAP / carnet / delta | Contexte potentiellement pertinent | Un volume broker ou des flags vides ne sont pas des données centralisées fiables |
| ML / reinforcement learning | Peut combiner des interactions | Nécessite données, labels nets et validation temporelle ; pas de modèle appris présenté comme validé aujourd'hui |

La formation CME décrit moyennes mobiles, supports/résistances et retests
comme outils d'analyse, pas comme garantie de rendement. Leur assemblage est
une **hypothèse testable**, non une preuve d'alpha.
[Supports et résistances, CME](https://www.cmegroup.com/education/courses/technical-analysis/support-and-resistance.hideSubnav.educationIframe.html.html?hideAddThisExt=y&hideFooter=y&hideHeader=y&hideRightRail=y).

Les CFD ont leurs propres spreads et charges ; la liquidité mondiale de l'or
ne supprime pas ces coûts chez notre intermédiaire.
[Revue FCA du 15 octobre 2026](https://www.fca.org.uk/publications/good-and-poor-practice/contracts-difference-firms).

## 5. Moteur combiné implémenté

`services/research/gold_regime_scalper.py` contient `REGIME_PULLBACK_V1` :

1. Bougies **S5 réellement clôturées**, construites depuis bid/ask midpoint.
   Aucune bougie synthétique pour combler un trou de cotation.
2. Contexte M1 et M5 : EMA9/21, pente EMA9 et ATR14, avec jointure temporelle
   uniquement sur les bougies déjà clôturées. Les chaînes datetime du terminal
   et les timestamps numériques de l'export donnent les mêmes features.
3. Sens M1 suffisamment établi, sans forte opposition M5. En absence de régime
   exploitable, **WAIT est un choix de marché**, pas une panne à contourner.
4. Repli vers EMA9 S5 suivi d'une reprise au-delà de la bougie précédente,
   **ou** cassure d'un niveau antérieur suivie d'un retest et d'une confirmation.
5. Filtrage de qualité du corps, couverture réelle, expansion anormale,
   spread courant, ancienneté et entrée déjà trop éloignée du setup.
6. SL structurel derrière les quatre dernières S5 avec buffer. Limite propre à
   cette hypothèse : distance de risque au plus 3,00 en prix ; elle n'a pas été
   ajoutée silencieusement au main historique. Ce n'est pas un plafond de perte
   garanti en présence de gap ou de slippage.
7. Identifiant unique par clôture et direction. Le signal d'entrée et la thèse
   M1 de maintien sont séparés : l'absence d'un nouveau setup ne signifie pas
   automatiquement qu'une position existante doit être inversée.

Le replay complète cette hypothèse par un SL, une sortie de retournement de
thèse, un trailing sans TP fixe et une durée maximale de 180 secondes. Le seuil
du trailing est 0,8R, la marge de giveback au moins 0,45R ou deux spreads. Ces
valeurs sont des paramètres fixés pour le test, **pas des paramètres optimisés**.
Le TP analytique des niveaux n'est pas un TP courtier installé.

Les périodes S5/S15/S30 sont des agrégations du projet : la liste standard MT5
commence à M1. Choisir S1 ne rend pas automatiquement l'exécution plus rapide
que le réseau ou plus rentable que les coûts.
[Timeframes standard MT5](https://www.mql5.com/en/docs/constants/chartconstants/enum_timeframes).

## 6. Replay et résultats honnêtes

`gold_causal_replay.py` utilise la **première quote après** décision + latence,
jamais une quote antérieure. Achat à l'ask, vente au bid, sortie sur le côté
opposé ; spread compté une fois, frais supplémentaires une fois. Un SL traversé
par un gap sort au prix réellement observé, pas au SL fictivement avantageux.
Les excursions avant entrée ne peuvent pas armer le trailing. Les positions
encore ouvertes à la fin sont censurées, pas transformées en gains réalisés.

Une seule position simultanée est simulée pour isoler l'hypothèse. Ce n'est pas
une simulation de compte financé : marge, ruine, rejets et limites de débit
courtier ne sont pas modélisés. Les sommes gigantesques négatives du compteur
de ticks sont des unités théoriques cumulées, **pas une perte réalisable sur un
compte de 100 USD**. Un portefeuille de quatre positions n'est pas validé.

Le premier découpage chronologique est fixé à 60 % développement / 40 % fin
d'échantillon. Aucun seuil n'est choisi parce qu'il gagne sur cette fin. Après
lecture, elle ne peut plus être recyclée en test aveugle. Les comparaisons de
latence et de coût sont des sensibilités, pas une recherche du meilleur score.
Une correction du suivi de l'identifiant des séries de ticks a nécessité un
nouveau replay d'intégrité ; l'ancien résultat est conservé et n'est pas choisi
parce qu'il paraissait meilleur.

Résultats du **replay d'intégrité** sur la fin des 24 heures :

| Hypothèse / scénario | Trades clos | Net prix, unité 1 oz | Profit factor |
| --- | ---: | ---: | ---: |
| Deuxième→cinquième tick, 350 ms + 0,30 de coûts | 19 122 | −13 028,76 | 0,00023 |
| Repli/retest, 350 ms + 0,30 de coûts | 57 | −54,91 | 0,2302 |
| Repli/retest, 150 ms, zéro frais hors spread | 54 | −37,55 | 0,3507 |
| Repli/retest, 350 ms + 0,08 de coûts | 57 | −42,37 | 0,3248 |
| Repli/retest, 2 s + 0,30 de coûts | 55 | −61,13 | 0,1702 |

À deux secondes, les demandes de la règle de ticks expirent avant remplissage :
zéro trade n'est **pas** un résultat rentable. Même le scénario optimiste sans
frais autres que le spread ne valide pas le moteur combiné. Les tests élargis
servent de contrôle de robustesse, pas de nouvelle sélection indépendante.

Le testeur officiel MT5 distingue les vrais ticks des ticks générés et permet
d'ajouter délais et commissions ; notre replay Python reste plus limité qu'un
testeur avec spécifications de compte et réconciliation d'ordres.
[Documentation du testeur MT5](https://www.metatrader5.com/en/terminal/help/algotrading/testing).

Multiplier les variantes jusqu'à obtenir un beau résultat favorise le
surapprentissage. Notre simple découpage ne mesure pas à lui seul la probabilité
de surapprentissage et ne constitue pas une CSCV complète.
[Bailey et al., Probability of Backtest Overfitting](https://www.davidhbailey.com/dhbpapers/backtest-prob.pdf).

## 7. État opérationnel et reproduction

- Le main est connecté en démo, avec **0,01 lot et quatre positions maximum**.
- `data/runtime/gold_entry_research_hold.flag` suspend seulement les nouvelles
  entrées SCALP, après le traitement des sorties. Cette suspension persiste
  après redémarrage ; elle n'est pas un problème de lancement.
- Le dashboard affiche explicitement cette suspension et le rôle sans ordres
  du nouveau moteur. Les catégories INTRADAY/SWING restent masquées.
- Le veto médiane-range/coût supprimé précédemment n'est pas réactivé.
- L'ancien stop de perte de session reste **désactivé**, conformément au réglage
  existant ; ce document ne prétend pas qu'il protège le compte.
- Pas d'auto-promotion après un petit gain ni de passage au réel.

### Lancer ou retrouver le main et son dashboard

```powershell
cd 'C:\Users\Gad Asopjio\Desktop\AI Trading Platform'
powershell -NoProfile -ExecutionPolicy Bypass -File .\tools\start_gold_consensus.ps1
```

Dashboard : `http://127.0.0.1:8765/`. Le lanceur utilise le Python du projet,
traite les chemins avec espaces et ne lance pas volontairement un deuxième
main s'il est déjà détecté. Le verrou d'instance du bot reste la protection
finale. Il ne supprime pas la suspension de recherche et n'active pas l'EA natif.

### Reproduire l'observation de la nouvelle stratégie, sans ordres

```powershell
.\.venv-audit\Scripts\python.exe -u -B .\tools\observe_gold_regime.py --minutes 30 --output data/research/new_regime_forward
```

Le programme n'appelle aucune API d'ordre. Les signaux sont enregistrés à leur
heure d'observation effective, pas rétrospectivement au meilleur prix de clôture.
Le coût papier de 0,30 et la latence de 350 ms sont des hypothèses, pas des fills.
L'observation ne doit pas être relancée dans le même dossier pour mélanger les
journaux de plusieurs essais.

### Artefacts

- `data/research/strategy_20261021/capture/metadata.json`
- `data/research/strategy_20261021/market_sample.json`
- `data/research/strategy_20261021/current_loss_audit.json`
- `data/research/strategy_20261021/measured_costs.json`
- `data/research/strategy_20261021/replay_integrity_v2.json`
- `data/research/strategy_20261021/robustness_capture/metadata.json`
- `data/research/strategy_20261021/robustness_replay.json`
- `data/research/strategy_20261021/forward/latest.json`
- `data/monitoring/20261021T100648Z/observations.jsonl`

Une prochaine promotion demanderait des données nouvelles couvrant plusieurs
jours et régimes, des frais réalistes, une évaluation du risque de portefeuille,
des paramètres gelés, et un suivi prospectif non réutilisé pour choisir les
seuils. **45 minutes, même positives, ne prouveraient pas une rentabilité durable.**

## 8. Reprise et adaptation des deux documents transmis

Après l'interruption de la conversation, une vérification à **17:30 UTC /
18:30 Lagos** confirme le main connecté en démo, aucune position ouverte,
aucune erreur conseiller et suspension d'entrée toujours active. Il ne faut
pas confondre cette vérification avec une surveillance humaine ininterrompue
pendant les heures séparant les deux sessions.

L'observation du matin s'arrête à 10:39 UTC : **4 trades papier, 1 gain,
3 pertes, net −3,11 unités de prix**, aucune position censurée à la dernière
observation. Le moniteur main a enregistré environ 32 minutes. Ce petit test
ne valide pas le modèle combiné ; le main n'a pas reçu d'ordres de cette recherche.

La nouvelle capture du jour, arrêtée à 17:30 UTC, donne un midpoint de 4132,255,
contre 4114,075 au premier tick UTC, un plus haut de 4141,965 et un plus bas de
4106,270. Cela ne justifie pas de figer le bot sur « vendre aujourd'hui » à partir
d'un texte reçu plusieurs heures plus tard. Les niveaux et probabilités de
hausse de taux évoqués dans les documents ne sont pas des données vérifiées
du moteur ; aucune préférence vendeuse permanente n'est codée.

### Ce qui est retenu et ce qui doit être corrigé

| Proposition des documents | Adaptation au projet |
| --- | --- |
| Trois régimes : tendance, cassure, range | Moteur ORBIT distinct implémenté en recherche, paramètres gelés |
| EMA50/200 M15 | Véritable historique étendu nécessaire : le buffer main protégé n'a que 140 M15 ; il n'est pas modifié |
| SMC / OB / sweep / FVG | Détecteurs causaux existants conservés en observation, pas assimilés à une preuve d'ordres institutionnels |
| Confirmation volume | Activité des ticks du broker uniquement ; pas de faux volume COMEX ni de VWAP institutionnel inventé |
| Seuils 70/75/85 ou P≥0,58 | Aucune probabilité apprise/calibrée n'est disponible ; pas de garantie d'espérance positive |
| 25–40 points de spread et SL 12–25 points | Conversion obligatoire avec `point` réel ; stops souvent incompatibles avec le spread observé |
| Clôture partielle de 50 % | Impossible sur 0,01 lot avec minimum/pas de 0,01 ; 0,005 n'est pas envoyé |
| Lots variables et 1–2 positions | Le main conserve la demande utilisateur : exactement 0,01 et plafond global de quatre ; le papier isole une position |
| TP fixes 1R / 2R / 3R | Niveaux analytiques seulement ; pas de TP maximum fixe installé au courtier |
| Horaires GMT fixes | Ne remplacent pas une conversion explicite calendrier/session/serveur tenant compte du changement d'heure |
| 4–6 trades par jour, M1/M5 | Ce n'est pas du HFT ; « production-ready » et « expectancy positive » restent des affirmations non démontrées |
| Resserrer les filtres après chaque perte | Pas d'optimisation sur le même test jusqu'à obtenir un résultat favorable |

Spécifications lues au courtier à 17:34 UTC : `point=0,01`, `tick_size=0,01`,
`volume_min=0,01`, `volume_step=0,01`, contrat 100 oz/lot. Donc 12–25 points
représentent **0,12–0,25 en prix**, à comparer à environ 0,38 de spread lors
de la reprise. Un SL placé entre le bid et l'ask n'est pas une protection
praticable pour ouvrir un scalp au marché. Les distances doivent aussi respecter
les contraintes réelles du symbole, non une convention de « pip gold » supposée.
[Propriétés officielles des symboles MT5](https://www.mql5.com/en/docs/constants/environment_state/marketinfoconstants).

### ORBIT M1/M15, version de recherche

`gold_orbit_research.py` ajoute une hypothèse plus lente et déterministe :
EMA50/200 + pente et ADX M15 ; repli EMA20 M1 avec rejet, cassure/retest de
range antérieur, ou sweep/reclaim en régime latéral. Les seuils ADX 18/22
introduisent une zone de transition sans forcer un mode contradictoire.
Les entrées utilisent uniquement les bougies terminées et une activité relative
des ticks observée. EMA20 est une moyenne de prix, **pas un VWAP de volumes réels**.

Le contrôle de spread est fixé à 15 % au plus de la distance structurelle du
stop, et 0,75 de spread absolu. Aucun seuil n'est abaissé pour faire apparaître
des trades. Le papier utilise au maximum 10 unités de risque structurel,
une sortie temporelle de 900 secondes, break-even après 0,8R et trailing après
1,2R. Ce sont des hypothèses de cette simulation, pas des réglages de risque
appliqués au main ; latence, gaps et coûts peuvent dépasser le résultat attendu.
La partie news et l'exécution limite/queue des documents ne sont pas simulées :
ce n'est donc pas une implémentation certifiée complète de leurs promesses.

L'historique M15 étendu est récupéré séparément, sans toucher au code/dataflow
protégé d'Advisor 1. Le main affiche le bilan ORBIT **sans pouvoir l'utiliser
comme autorisation d'ordre** ; un observateur terminé ou trop ancien est signalé
comme tel et non présenté comme live.

Premier replay ORBIT sur le nouvel intervalle de 24 heures : deux positions
dans la partie développement, net +0,47 avec 0,30 de coûts, mais **zéro trade
dans la fin chronologique**. C'est trop peu pour conclure, et ce n'est pas un
test indépendant des recherches précédentes. Un petit résultat positif dans
deux trades ne justifie ni activation ni sélection automatique de la stratégie.

```powershell
.\.venv-audit\Scripts\python.exe -u -B .\tools\observe_gold_regime.py --strategy orbit --minutes 30 --output data/research/new_orbit_forward
```

### Correction de l'export historique

Une différence de comptage a révélé une erreur dans l'outil de **recherche** :
les appels par blocs de 30 minutes avec des bornes fractionnaires pouvaient
omettre le début d'une seconde à chaque jonction, car l'API utilise des bornes
en secondes. La requête utilise désormais des secondes entières contiguës,
puis filtre précisément les intervalles semi-ouverts et les bornes demandées.
Un test unitaire vérifie la continuité de ces fenêtres.

Sur **exactement le même premier intervalle**, la nouvelle capture contient
**442 103 quotes contre 442 032**, soit 71 quotes récupérées ; toutes les quotes
de l'export initial restent présentes. Les anciens fichiers sont conservés
pour la traçabilité et les replays sont relancés sur la capture corrigée.
Il s'agit d'un correctif de collecte hors ligne, pas d'un gain de performance
financière démontré ni d'une modification du connecteur protégé d'Advisor 1.

Artefacts complémentaires : `corrected_capture`, `corrected_replay.json`,
`ny_capture/proposal_symbol_checks.json`, `orbit_replay.json`,
`ny_corrected_capture`, `orbit_corrected_replay.json`, `orbit_forward/latest.json`
sous `data/research/strategy_20261021/`. Les résultats anciens ne doivent pas
être présentés comme ceux du replay corrigé.

Les replays corrigés sont terminés : le moteur repli/retest conserve exactement
ses résultats négatifs (57 positions, −54,91 à 350 ms + 0,30 dans la fin
chronologique). Le compteur de ticks donne 19 123 positions théoriques et
−13 030,12, toujours sans modèle de marge/ruine. Le nouvel export New York
récupère 141 quotes supplémentaires (401 094 au lieu de 400 953) ; ORBIT
conserve deux positions de développement, +0,47, et zéro en fin chronologique.
La correction d'intégrité ne transforme donc aucune hypothèse en stratégie
validée.

## 9. Bilan final enregistré à 18:53 Lagos

`final_review.json` récapitule **54,36 minutes de suivi du main enregistré**,
en deux fenêtres distinctes (129 puis 89 observations). Aucune surveillance
continue n'est revendiquée pendant l'interruption. Les moniteurs n'ont enregistré
aucune erreur d'observation et aucune position ouverte dans ces fenêtres : le
main était volontairement à plat et suspendu aux nouvelles entrées.

Le premier essai prospectif papier reste à quatre trades et −3,11 unités de
prix. L'essai ORBIT s'est terminé à 18:50 Lagos, après 17 minutes prévues, sans
trade ; sa dernière statistique porte sur les données enregistrées jusqu'à
18:49:57. Zéro trade n'est ni un gain ni une validation de rentabilité. Les
alertes ponctuelles de quotes de plus de trois secondes sont conservées dans
les journaux papier, pas masquées par des cotations synthétiques.

Validation : **96 tests ciblés réussis**, test JavaScript du polling dashboard
réussi, syntaxe du lanceur PowerShell vérifiée. Un groupe plus large de 50 tests
en réussit 49 ; l'ancien test
`test_paper_can_hold_five_profitable_scalps_but_not_six` attend encore cinq
positions, contrairement au plafond utilisateur actuel de quatre. Le plafond
n'est pas relâché pour satisfaire cette ancienne attente.

Les hashes des **18 fichiers protégés d'Advisor 1** sont identiques au relevé de
référence. Le main est `RUNNING`, démo, 0,01 lot, plafond quatre, sans erreur
conseiller à la dernière lecture. **Aucun nouveau modèle n'est promu aux ordres.**
La suspension d'entrée est explicite et persistante ; le lanceur ne la supprime
pas. Les essais prospectifs ponctuels sont terminés, pas promis en surveillance
illimitée après cette réponse.
