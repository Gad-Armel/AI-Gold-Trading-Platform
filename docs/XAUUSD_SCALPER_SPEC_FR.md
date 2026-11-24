# Fiche adaptée : scalper XAUUSD MT5

Révision du 15 octobre 2026. Cette fiche remplace le modèle générique pour ce
dépôt. Le détail des constats, recherches, modifications et résultats figure dans
[l'audit des signaux](research/XAUUSD_SIGNAL_REVIEW_20261015.md).

## 1. Objectif et périmètre

Analyser XAUUSD en continu, exécuter uniquement sur compte MT5 **démo**, protéger
chaque position par un SL courtier et gérer les sorties dynamiquement. Limite
absolue : **cinq positions du moteur**, à **0,01 lot chacune**. Un moteur doit
être le seul à exécuter sur le compte : Python et l'EA natif ne doivent pas
tourner en parallèle en mode ordres. Leurs verrous ne constituent pas un verrou
commun entre les deux technologies.

Cinq est une capacité maximale, pas une obligation de remplir cinq places.
L'absence de signal exploitable doit produire WAIT. Un meilleur score doit
correspondre à une meilleure information mesurée, pas à une augmentation
artificielle de la confiance affichée.

Advisor 1 reste protégé : aucun changement dans son lanceur, son calcul ou ses
dépendances protégées. Le passage au réel reste désactivé et nécessite une
validation et une demande distinctes.

## 2. Architecture existante à conserver

Le dépôt possède déjà deux moteurs et une chaîne de recherche. Créer un second
répertoire `xauusd_ai` dupliquerait les règles et les risques.

| Fonction du modèle fourni | Implémentation du projet |
|---|---|
| Configuration Python | `config/gold_consensus_settings.py` |
| Orchestration Python | `run_gold_consensus_bot.py` |
| Exécution démo Python | `services/execution/gold_consensus_demo_broker.py` |
| Simulation | `services/execution/gold_paper_portfolio.py` |
| Flux, horloge courtier | `services/market_data/`, `gold_broker_clock.py` |
| Signal principal Python | `gold_main_candle_signal.py`, `gold_horizon_policy.py` |
| Confirmation et ajouts | `gold_entry_momentum.py`, `gold_candle_confirmation.py`, `gold_scalp_additions.py` |
| Sorties | `gold_adaptive_exit.py`, `gold_fast_protection.py`, `gold_profit_lock.py`, `gold_flow_exit.py` |
| Moteur natif | `mql5/Experts/GoldScalpAI/GoldScalpAI.mq5` et ses `.mqh` |
| Features, labels, calibration | `vfinal/features/`, `vfinal/data/`, `vfinal/model/` |
| Collecte et recherche | `tools/`, `data/research/` |
| Interface principale | `services/dashboard/gold_unified_web.py`, `run_gold_unified_dashboard.py` |
| Advisor 1 autonome | `run_gold_advisor.py` : lecture seule, protégé |

L'EA prend ses décisions courtes sur les quotes et utilise M1/M5/M15/H1 comme
contexte. Le moteur Python utilise actuellement `ADVISOR1_PRIMARY` pour SCALP ;
INTRADAY et SWING sont des analyses sans nouvelles entrées. Ces stratégies ne
sont pas interchangeables et leurs résultats doivent rester séparés.

## 3. Stack gratuite et données

Conserver Python, le connecteur officiel MetaTrader5, numpy, pandas,
scikit-learn et joblib. Les indicateurs natifs MQL5 couvrent déjà EMA et ATR.
La base SQLite n'est pas nécessaire pour remplacer les JSONL/CSV existants ;
une éventuelle migration doit préserver les preuves et les identifiants de deal.

LightGBM est un challenger facultatif après une régression logistique de
référence. PyTorch, PPO et les ensembles complexes ne sont pas requis. Leur
présence dans une stack ne démontre aucun avantage de trading.

Source d'exécution : bid/ask du courtier MT5 et propriétés réelles du symbole
(taille du tick, contrat, minimum et pas de volume, stops/freeze, marge).
Les API externes gratuites restent optionnelles ; leurs quotas, délais,
conditions d'accès et changements de disponibilité doivent être suivis.

Les timestamps de recherche sont en UTC. La convention mesurée du serveur
actuel reste explicitement gérée par le projet ; ne pas ajouter ou retirer trois
heures à toutes les sources. Séparer heure événement, heure de publication,
heure courtier, heure de réception et horloge monotone d'exécution.

## 4. Analyse et features

M1 : timing et gestion ; M5/M15 : structure et confirmation contextuelle ; H1 :
régime de fond. N'utiliser que des bougies clôturées pour les confirmations.
Le prix courant reste disponible séparément pour exécuter et protéger.

Priorité de recherche :

1. Coût complet relatif au mouvement disponible : spread/ATR, commissions,
   slippage observé, latence et espace jusqu'au prochain niveau.
2. Quotes causales : mouvements bid et ask concordants, efficacité, persistance,
   accélération, interruptions et élargissement du spread.
3. Localisation : extension à l'EMA, reprise après repli, rejet, breakout avorté,
   niveaux de veille et de session connus à cet instant.
4. Régime : tendance, range, activité faible ou volatilité anormale, avec âge et
   qualité des observations. Ajouter un indicateur seulement par comparaison
   contrôlée avec la même stratégie sans cet indicateur.
5. Contexte : calendrier officiel, publications déjà disponibles, observations
   inter-marchés fraîches. Une donnée macro quotidienne ne devient pas un signal
   fiable à trois secondes parce qu'elle est rafraîchie souvent.

Le volume de ticks est une activité du flux courtier, pas le volume mondial
d'or. Un VWAP construit avec ce volume est un proxy local. Le delta agressif et
l'imbalance d'un carnet ne sont utilisables que si ces données existent réellement.
Les noms ASIA/LONDON/OVERLAP de l'EA sont actuellement des tranches UTC grossières,
pas des horaires de places ajustés automatiquement à l'heure d'été.

## 5. Confiance et apprentissage

Afficher séparément : direction, score heuristique, qualité/fraîcheur des
données, coûts et risque. Une probabilité de gain reste absente tant qu'un
modèle valable pour ce label, cet horizon et cette version n'est pas validé.
`85/100` d'evidence n'est pas `85 %` de chances de gagner.

Pour un modèle candidat :

- Définir précisément le résultat prédit : mouvement, toucher une barrière ou
  profit net après coûts. Ces événements ne sont pas équivalents.
- Entraîner sur le passé, calibrer sur une période ultérieure distincte, choisir
  les règles sur des validations chronologiques et réserver une période finale.
- Purger les labels qui débordent sur la calibration, les folds suivants ou la
  période finale ; tenir compte de l'horizon réel, y compris H1/H4.
- Exclure les trajectoires futures incomplètes, ambiguës ou interrompues.
- Comparer Brier, courbe de fiabilité, taux de couverture et référence constante,
  puis espérance nette, drawdown, payoff et résistance aux coûts majorés.
- Compter les épisodes de trading, pas les milliers de snapshots corrélés.
  Produire des résultats par jour et session avec incertitude.

Un seuil de 0,65 est une hypothèse à évaluer. Il ne faut pas baisser le seuil
uniquement parce que le modèle ne propose aucune opération. Ré-entraînement
hebdomadaire éventuel en recherche, jamais promotion hebdomadaire automatique.
Les anciens artefacts V-FINAL de format 1 exigent une revalidation ; les nouveaux
artefacts de format 2 restent soumis à la promotion explicite existante.

## 6. Entrées et cinq positions

Vérifier la capacité au dernier instant avant l'envoi et conserver la réservation
des requêtes incertaines. L'EA compte positions et ordres du compte ; Python
compte ses positions contrôlées et leur volume. Le plafond logiciel cinq reste
applicable même si un paramètre Python est augmenté au-delà.

Les quatrième/cinquième entrées Python exigent au moins **85/100 d'evidence**,
en plus des contrôles d'ajout : même sens et positions déjà profitables au-delà
du bruit de spread. Ce seuil est une règle d'allocation, non un taux de réussite
validé. Les ajouts précédents gardent leur propre seuil et le contexte existants.

Les quatrième/cinquième entrées de l'EA Expert exigent au moins **six points
au-dessus du seuil courant** et un micro-flux frais dans le même sens. Les
positions précédentes doivent aussi être gagnantes et protégées. Chaque envoi
réinitialise la confirmation, qui doit se reformer sur des quotes distinctes.
Les budgets de risque peuvent interdire une quatrième position malgré un bon score.

Pas d'augmentation de lot, martingale, moyenne à la baisse ou couverture inverse
pour contourner ces règles. Conserver spread/coûts, confirmation temporelle,
fraîcheur, news, marge, identité démo et pauses après pertes/fermetures.

## 7. Risque : adapter le modèle fourni sans cacher les différences

Le modèle proposé demande 0,5 % de risque et un lot dynamique. Le projet impose
actuellement **0,01 lot fixe**. La règle cible compatible est de calculer le SL
structurel puis de **refuser l'entrée** si le risque de 0,01 lot dépasse le budget,
plutôt que de modifier le lot ou de rapprocher arbitrairement le SL.

À un budget de stratégie de 100 $, 0,5 % vaut 0,50 $. Les réglages actuels ne
respectent pas cette limite : l'EA conserve un plafond nominal de 2 $ par trade
et 4 $ agrégés ; le SCALP Python utilise `stop_mode=ANALYSIS`, sans plafond fixe
de 5 $ sur ce stop structurel. Son arrêt de perte de session est désactivé.
Ce sont des écarts matériels, pas des protections de 0,5 % déjà actives.

La présente revue conserve ces profils distincts et les signale. Une variante
0,5 %, avec plafond de risque cumulé et arrêt journalier explicite, doit être
mesurée séparément avant adoption ; elle peut produire beaucoup de WAIT à
0,01 lot. Le seuil natif de perte glissante de 50 $ est lui aussi distinct de
0,5 % de 100 $. Aucun réinitialiseur ne doit effacer automatiquement un verrou.

Le risque doit être valorisé par `order_calc_profit`/`OrderCalcProfit` et inclure
frais et réserve de slippage. Un nombre de positions ou une marge disponible
ne remplace pas un budget de perte. Un SL n'assure pas son prix lors d'un gap.

## 8. Sorties dynamiques

Le mode adaptatif Python et `UseBrokerTakeProfit=false` de l'EA ne posent pas
de plafond fixe de gain. Les niveaux TP d'analyse restent utilisables pour
évaluer le coût et la localisation ; ils ne sont pas nécessairement des ordres TP.
Le mode Python `legacy` conserve des règles différentes et doit être identifié
séparément dans les comparaisons.

Conserver les SL courtier, le resserrement sans élargissement du risque, le
break-even après coûts, les sorties sur invalidation confirmée, le reflux de
profit et les protections news. Une pause d'entrée ne suspend pas les sorties.

Une clôture de 50 % de 0,01 lot demande 0,005 lot : elle ne doit pas être envoyée
si le minimum/pas du courtier est 0,01. Dans ce cas, gérer les tickets entiers.
La fermeture avant le week-end doit suivre les sessions réelles du symbole et
être testée avec fuseau/DST, déconnexion et compte portant des positions. Ne pas
la décrire comme déjà garantie : un simple filtre des nouvelles entrées n'y suffit pas.

## 9. Validation et critères d'adoption

Ordre : tests unitaires → compilation → tests natifs isolés → replay causal
avec coûts → évaluation chronologique → observation prospective → exécution démo
limitée. Le test mathématique MQL5 ne constitue pas un backtest de rentabilité.

Mesurer expectancy nette, profit factor, gains/pertes moyens, equity drawdown,
coûts, rejets, slippage, temps de détention, résultats par régime/session et
concentration de risque lorsque plusieurs positions suivent le même mouvement.
Le portefeuille cinq positions exige une simulation spécifique : le test à une
position ne permet pas de multiplier ses profits par cinq.

Avant une nouvelle expérience, figer features, seuils, périodes, version et
critères. Conserver tous les essais, y compris négatifs. Une période finale déjà
consultée devient une période de recherche ; collecter une nouvelle période pour
une nouvelle décision. Refuser toute promotion lorsque les données sont insuffisantes.

## 10. Exécution et exploitation

Python vise actuellement une cadence de 0,5 s ; l'EA est événementiel sur ticks,
avec travail lent au timer. Mesurer p50/p95/p99 du cycle, âge du tick à l'envoi et
latence réelle de remplissage. Une moyenne rapide ne garantit pas un cycle
toujours inférieur à une seconde.

Conserver contrôles avant ordre, mode de remplissage courtier, tolérance de prix,
réconciliation asynchrone et absence de relance aveugle après timeout. La
reconnexion ne doit pas modifier le compte autorisé ou rejouer un ordre ambigu.
Les appels HTTP, l'entraînement et les scans historiques restent hors du chemin
de protection des positions.

La version native **3.22** de cette revue est compilée et testée localement.
Cela ne prouve pas qu'elle est installée dans le terminal : contrôler son identité
au déploiement. Aucun ordre ni redémarrage du bot actif n'est nécessaire pour
exécuter les outils d'audit hors ligne.
