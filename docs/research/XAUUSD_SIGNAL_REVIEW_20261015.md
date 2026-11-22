# Revue XAUUSD : signaux, confiance et exécution

15 octobre 2026. Début de revue : **06:47:24 UTC / 07:47:24 Lagos**.
La [fiche adaptée](../XAUUSD_SCALPER_SPEC_FR.md) décrit les règles applicables et
les écarts avec le modèle proposé. Ce document distingue défauts corrigés,
résultats exploratoires et travaux restant à valider.

## Conclusion de recherche

Les preuves disponibles ne justifient ni une promesse de meilleurs gains ni
l'activation d'un nouveau modèle. La priorité utile est d'obtenir des signaux
dont la probabilité est mesurée sur des données disponibles à l'instant de la
décision, avec coûts et risque cohérents. Augmenter le score ou le nombre de
positions ne crée pas cet avantage.

La nouvelle expérience hors ligne ne trouve aucun candidat atteignant 0,65 de
probabilité calibrée de profit net sur ses journées de validation. Elle reste
sans effet sur l'exécution. Les améliorations livrées portent sur des défauts
reproductibles et sur la capacité à vérifier de futures hypothèses.

## Étendue et état réel du dépôt

L'inventaire `data/research/review_20261015/project_audit.json` recense les sources
Python/MQL5/PowerShell/JavaScript, leurs empreintes et les sites Python d'envoi
d'ordres. Tous les fichiers Python inventoriés sont analysés syntaxiquement.
La revue manuelle couvre les chemins critiques de données, décisions, entrées,
sorties, exposition, calendrier, apprentissage et tableaux de bord ; cet inventaire
ne signifie pas que chaque ligne historique a fait l'objet d'une preuve formelle.

Les dix-huit fichiers protégés d'Advisor 1 sont vérifiés contre le manifeste
antérieur : aucune différence. Aucun fichier `.env` ni secret n'est inclus dans
les rapports. Les scripts nouveaux ne se connectent pas au courtier.

| Domaine | Constat |
|---|---|
| Architecture | Python, EA natif et V-FINAL coexistent ; ils n'appliquent pas la même stratégie |
| Capacité | Python passé à cinq ; EA encore plafonné à trois avant cette revue |
| Entrées Python | Advisor 1 comme autorité SCALP ; seuil directionnel initial continu très permissif ; autres lanes sans nouveaux ordres |
| Entrées natives | Impulsion 3/8 s ou continuation 20 s, contexte MTF, score heuristique, confirmations distinctes |
| Coûts | Filtres spread et cible présents ; les hypothèses de coûts diffèrent entre moteurs/replays |
| Risque Python | Stop structurel `ANALYSIS` ; le plafond monétaire de 5 $ est volontairement contourné dans ce mode |
| Risque natif | Budget nominal 2 $/trade, 4 $ agrégés, limite de perte glissante 50 $ ; ce n'est pas 0,5 % de 100 $ |
| Sorties | Protections adaptatives déjà présentes ; pas besoin d'un nouveau moteur PPO pour retirer un TP fixe |
| Apprentissage | Modèles historiques non prouvés ; validation chronologique à réparer avant de se fier aux scores |
| Exploitation | Les verrous Python et natifs ne garantissent pas une exclusivité commune ; choisir un seul exécuteur |
| Week-end | Filtre des entrées ne prouve pas fermeture préalable de toute position ; scénario encore à valider |

Les documents anciens annonçant trois positions ou un SL Python systématique de
5 $ décrivent des versions antérieures. `test_gold_analysis_stop.py` confirme
explicitement le comportement structurel actuel ; il ne faut pas le présenter
comme un budget fixe toujours actif.

## Défauts corrigés

### Capacité native et risque journalier désactivé

L'EA possédait plusieurs plafonds codés à trois, y compris dans la validation
des paramètres et juste avant l'envoi. Le défaut est corrigé dans tous ces
chemins : cinq au maximum, positions et ordres du compte comptés ensemble,
réservation asynchrone conservée. Le preset de lancement fixe cinq explicitement.

Avec `DailyEquityLossPercent=0`, le calcul d'allowance journalier restait
`equity - reference`, soit zéro sur un compte à l'équilibre. Il refusait donc
un risque positif malgré la désactivation de cette règle. Le nouveau helper
teste explicitement le cas désactivé ; budgets agrégés, marge et protection de
perte glissante continuent de s'appliquer.

La source native porte la version **3.22**. Les commentaires d'ordre et la
télémétrie distinguent ce cohort de 3.21 : l'ajustement par session ne recycle
pas des résultats d'une autre politique. Les données historiques restent intactes.

### Quatrième et cinquième positions

Python et sa simulation partagent le garde d'ajout. Au-delà des trois premières
positions, il exige une evidence finie d'au moins 85/100. L'EA Expert exige
son critère de signal fort existant : seuil courant +6 et micro-flux aligné.
Profitabilité/protection des positions précédentes, confirmation fraîche et
budgets restent obligatoires. Ces règles limitent l'allocation ; elles ne
constituent pas une démonstration d'espérance positive.

Le plafond dur Python reste cinq même si sa configuration est augmentée au-delà.
Les tests de capacité obsolètes ont été adaptés au cinquième/sixième ordre.
La réconciliation Python des ordres en attente est également refaite dans le
dernier contrôle avant envoi : un ordre apparu pendant `order_check` bloque
l'envoi suivant au lieu d'attendre uniquement le prochain cycle.

### Features causales et interprétation des indicateurs

Dans V-FINAL, un calcul de ticks effectué pour `now` ne coupait pas les ticks
postérieurs à `now`. Ils pouvaient entrer dans le mouvement, le spread et la
qualité. Ils sont désormais exclus avant tous les calculs.

Les baselines de spread au démarrage utilisaient la médiane du jeu entier,
incluant des quotes futures. Elles utilisent maintenant une médiane croissante
causale. Les tests vérifient qu'ajouter une séquence future ne change pas les
features du préfixe historique.

La conversion des timestamps numériques de bougies précisait mal l'unité ;
elle utilise désormais les secondes Unix. Une unique bougie en cours n'est
plus traitée comme clôturée. Le RSI d'une hausse continue avec perte moyenne
nulle renvoyait 50 ; il renvoie 100, une baisse continue 0, une série plate 50.
Les fonctions horaires acceptent explicitement timestamps naïfs et zonés.

Ces corrections concernent la chaîne de recherche ; aucun calcul protégé
d'Advisor 1 n'a été changé.

### Labels et validation temporelle

L'ancienne purge séparait les folds mais pas toutes les frontières de
calibration et de holdout. Son délai fixe de 900 s ne suffisait pas toujours
pour les labels H1/H4. Le helper `purged_history` respecte à la fois le délai
et la fin de l'horizon de chaque label, avant la première observation suivante.

La purge s'applique aux entraînements des folds, à leurs calibrations et au
couple développement/holdout final. Les exemples de développement dont les
labels débordent sur le holdout sont également exclus de la sélection de seuil.
La validation exige les folds réellement terminés, sans remplacer silencieusement
une calibration insuffisante par des probabilités brutes.
Le nombre de trades utilisé pour comparer les seuils et pour le gate final
exclut désormais les labels chevauchants : deux snapshots du même horizon
ne deviennent plus artificiellement deux opérations indépendantes.

Les labels de trajectoires futures tronquées sont marqués `INCOMPLETE_HORIZON`.
Les trous de plus de cinq secondes sont marqués `GAPPED_HORIZON`. Les quotes
inversées/non finies sont rejetées. Les données supervisées conservent uniquement
`VALID` et `TIME_BARRIER` ; les observations brutes restent disponibles.

### Gates de modèle

Une probabilité NaN peut rendre fausses les comparaisons de seuil et d'EV,
laissant accidentellement passer un candidat. Les deux gates V-FINAL refusent
désormais les probabilités/seuils non finis ou hors [0,1], les coûts invalides
et les modèles spécialisés dans l'autre direction.

Les artefacts nouveaux portent le format 2. Les gates refusent les anciens
artefacts de format 1 : leur validation doit être refaite avec les corrections.
Le mécanisme de promotion explicite reste requis ; aucun artefact n'a été promu
dans cette revue.

## Expérience reproductible sur les signaux

Commande hors ligne :

```powershell
.\.venv-audit\Scripts\python.exe -B .\tools\audit_gold_signal_confidence.py
```

Rapport : `data/research/review_20261015/signal_confidence.json`. Il inclut la
liste et les empreintes SHA-256 des fichiers effectivement lus.

Protocole figé dans le script : majorité des directions clôturées M1/M5/M15,
18 features de coût/flux/localisation, régression logistique régularisée C=0,1,
calibration sigmoïde sur des journées ultérieures distinctes, puis comparaison
des seuils 0,55/0,65/0,75. Pas de recherche de seuil gagnant après le résultat.

Entraînement : 12 journées du 8 au 21 septembre, 89 994 observations.
Calibration : 22–24 septembre, 25 686 observations. Validation : 25, 27, 28,
29 et 30 septembre, 34 769 observations directionnelles. Les six fichiers de
période finale d'octobre ne sont pas lus. Les périodes de validation ont déjà
servi à d'autres recherches : elles ne sont pas qualifiées de holdout inédit.

Le résultat prédit est un gain net à 180 s avec SL de 5 $, bid/ask historiques,
latence nominale 100 ms, slippage de 0,05 $ par côté et commission additionnelle
supposée de 0,10 $ par aller-retour. Ce coût est une hypothèse explicite, pas une
mesure actualisée du courtier. Les épisodes simulés ne se chevauchent pas et
attendent trente secondes après fermeture. Ce n'est pas une reconstitution
des sorties adaptatives actuelles ni de l'EA à SL de 2 $.

| Politique | Épisodes validation | Net simulé | Espérance / épisode | Profit factor |
|---|---:|---:|---:|---:|
| Tous les candidats, coûts normaux | 1 021 | -546,82 $ | -0,536 $ | 0,555 |
| Tous les candidats, stress coûts 1,5 | 1 024 | -768,09 $ | -0,750 $ | 0,440 |
| Probabilité calibrée ≥0,55 | 0 | 0 | non estimable | non estimable |
| Probabilité calibrée ≥0,65 | 0 | 0 | non estimable | non estimable |
| Probabilité calibrée ≥0,75 | 0 | 0 | non estimable | non estimable |

Les nombres d'épisodes diffèrent en stress parce que les sorties et donc les
ré-entrées changent. Les montants cumulés d'un replay sans financement ne sont
pas une trajectoire réalisable d'un compte de 100 $.

Le Brier des épisodes est 0,2391 contre 0,2405 pour une probabilité constante
apprise sur le passé. Ce faible écart ne démontre pas un avantage exploitable.
L'intervalle descriptif à 95 % de l'espérance normale, bootstrap par journée,
est [-0,656 ; -0,380] $ ; cinq journées limitent fortement cette estimation.
Une calibration convenable peut parfaitement annoncer honnêtement une faible
probabilité de gain. Le bon comportement est alors l'abstention.

## Recherches externes et conséquences pour notre bot

Sources primaires consultées le 15 octobre 2026. Les conséquences suivantes
sont des choix d'ingénierie ou des hypothèses pour ce projet, pas des promesses
de performance déduites automatiquement des publications.

| Priorité | Recherche / documentation | Conséquence pratique |
|---|---|---|
| 1 | [Scikit-learn : calibration](https://scikit-learn.org/stable/modules/calibration.html) | Une sortie probabiliste doit être comparée aux fréquences observées sur données distinctes ; un Brier faible ne mesure pas la calibration seule |
| 1 | [TimeSeriesSplit](https://scikit-learn.org/stable/modules/generated/sklearn.model_selection.TimeSeriesSplit.html) | Respecter l'ordre temporel ; le `gap` en lignes ne suffit pas aux snapshots irréguliers ou aux horizons variables |
| 1 | [Bailey et al., Probability of Backtest Overfitting](https://www.davidhbailey.com/dhbpapers/backtest-prob.pdf) | Tracer les essais et leur sélection ; réutiliser le meilleur résultat de nombreuses variantes surestime les preuves |
| 1 | [MetaQuotes : copy_rates_from_pos](https://www.mql5.com/en/docs/python_metatrader5/mt5copyratesfrompos_py) | La barre zéro est celle en formation ; séparer confirmation clôturée et quote d'exécution |
| 1 | [MetaQuotes : copy_ticks_from](https://www.mql5.com/en/docs/python_metatrader5/mt5copyticksfrom_py) | Quotes, drapeaux de changement et conventions UTC doivent être conservés ; ne pas inventer le sens agressif à partir de simples quotes |
| 1 | [Propriétés du symbole](https://www.mql5.com/en/docs/constants/environment_state/marketinfoconstants) | Lire minimum/pas de volume, tick, contrat et contraintes de stops ; pas de demi-clôture invalide |
| 1 | [OrderCalcProfit](https://www.mql5.com/en/docs/python_metatrader5/mt5ordercalcprofit_py) | Valoriser le risque en devise du compte, pas via une règle universelle de pip XAUUSD |
| 2 | [Cont, Kukanov, Stoikov : Price Impact of Order Book Events](https://arxiv.org/abs/1011.6402) | L'étude concerne des actions américaines et un carnet observé ; tester notre proxy de quotes séparément, sans prétendre mesurer ce même order flow |
| 2 | [LBMA : données de trading](https://www.lbma.org.uk/prices-and-data/lbma-daily-trade-reporting-data) | Les données OTC agrégées publiées T+1 ne sont pas un carnet spot gratuit en temps réel pour scalper |
| 2 | [Calendrier MQL5](https://www.mql5.com/en/docs/calendar) | Convertir explicitement le temps serveur et contrôler la fraîcheur du cache ; publication réelle différente de date prévue |
| 2 | [BLS : calendrier emploi](https://www.bls.gov/schedule/news_release/empSit.htm) | Employer les horaires officiels plutôt qu'une règle mensuelle supposée ; ne pas supposer la surprise avant publication |
| 2 | [FRED/ALFRED : périodes temps réel](https://fred.stlouisfed.org/docs/api/fred/realtime_period.html) | Backtester avec les vintages disponibles à la date, pas les valeurs révisées aujourd'hui |
| 2 | [BCE : prix de l'or et risques](https://www.ecb.europa.eu/press/financial-stability-publications/fsr/focus/2025/html/ecb.fsrbox202505_02~7f616fcd3f.en.html) | Les relations avec les taux réels changent ; éviter un veto directionnel permanent fondé sur une corrélation historique |
| 3 | [LightGBM : paramètres](https://lightgbm.readthedocs.io/en/stable/Parameters.html) | Les pondérations de classes peuvent dégrader les probabilités ; calibrer et comparer au modèle simple avant toute intégration |
| 1 | [MetaQuotes : OnTick](https://www.mql5.com/en/docs/event_handlers/ontick) | Un nouveau tick n'est pas empilé si un événement tick est déjà en attente/traitement ; éviter le travail lourd dans ce chemin |
| 1 | [OrderSendAsync](https://www.mql5.com/en/docs/trading/ordersendasync) et [OnTradeTransaction](https://www.mql5.com/en/docs/event_handlers/ontradetransaction) | Envoi accepté ne signifie pas position confirmée ; conserver réservation, identifiant de requête et réconciliation |

### Hypothèses prioritaires à tester ensuite

1. **Profit net atteignable après coûts** : combiner qualité du signal et
   distribution des gains/pertes, plutôt qu'augmenter seulement la probabilité
   directionnelle. Comparer un veto de coût à stratégie inchangée.
2. **Reprise après repli versus poursuite tardive** : extension ATR et espace
   structurel, confirmation par bid et ask ; tester BUY et SELL séparément et
   contrôler le résultat par régime.
3. **Persistance du flux sans surcompter les quotes** : persistance temporelle,
   absence de contre-flux significatif et résistance à un spread changeant.
   Mesurer les faux départs, pas seulement le nombre de signaux acceptés.
4. **Régimes locaux** : efficacité, volatilité et activité, avec une stratégie
   de range comparée à celle de tendance. Ne pas choisir les frontières sur la
   période qui doit ensuite servir de preuve finale.
5. **Allocation corrélée** : budgets d'un même mouvement, profits verrouillés
   et risque résiduel réel avant quatrième/cinquième ticket. Mesurer combien
   d'exposition additionnelle apporte de l'information nouvelle.
6. **Données complémentaires** : EURUSD/USDJPY frais du même courtier peuvent
   être évalués comme contexte ; les données quotidiennes de taux/COT restent
   contexte de régime. Tester l'apport marginal au lieu de compter ces sources
   comme des votes indépendants.

EMA, MACD et RSI partagent beaucoup d'information issue des mêmes prix. Les
additionner ne crée pas trois observations indépendantes. PPO et les grands
réseaux sont reportés tant qu'un modèle simple ne montre pas une amélioration
stable après coûts sur une période réellement nouvelle.

## Validation et limites opérationnelles

Les détails finaux des commandes, tests et limites sont consignés dans
`data/research/review_20261015/validation.json` et dans les journaux
`logs/audit-20261015-*`. Les tests ciblés couvrent les fuites temporelles,
l'invalidité des probabilités, les labels tronqués, les limites d'exposition et
l'absence d'ajouts sur des pertes. Les anciens tests génériques supposant
trois lanes actives, arrêt de session activé et SL Python fixe peuvent échouer
avec le profil courant ; ils ne sont pas modifiés pour masquer cet écart.

La compilation locale et les invariants natifs ne prouvent pas la qualité des
fills réels ni la rentabilité. Aucun ordre n'a été envoyé et aucun bot actif
n'a été redémarré pour cette revue. Le binaire 3.22 n'est pas installé par le
simple fait de le compiler dans ce dépôt.

Validation ciblée : **123 tests Python et cinq sous-tests réussis** ; **230
contrôles natifs réussis** ; les cinq programmes MQL5 compilent sans erreur ni
avertissement. Un test HTTP local a rencontré une réinitialisation de connexion
sur un passage global et a réussi lors de sa relance ciblée. Les quatre autres
échecs globaux étaient déjà présents avant ces corrections et correspondent aux
anciens profils décrits ci-dessus. Les tests JavaScript n'ont pas été exécutés :
Node.js est absent de cet environnement et leur code n'a pas été modifié.

À 07:19:31 UTC / 08:19:31 Lagos, le travail de revue avait dépassé **32 minutes**.
L'horodatage final et la durée sont conservés dans `validation.json`.

Le passage du plan théorique de 0,5 % à une politique effectivement appliquée,
la coordination entre moteurs et le scénario de sortie avant week-end restent
des travaux distincts, explicitement listés dans la fiche adaptée. Les contrôles
de budget actuels ne doivent pas être décrits comme ceux de cette future variante.
