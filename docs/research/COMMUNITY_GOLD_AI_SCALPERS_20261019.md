# Traces communautaires : bots gold, IA et scalping

## Périmètre et livrables

Recherche publique du 19 octobre 2026 : **37 traces, 33 familles, 13 domaines**.
Le catalogue distingue 29 pages lues, un fichier de code lu, un extrait de
recherche, deux vidéos repérées uniquement par métadonnées et quatre accès
indisponibles. Il ne s'agit pas de 37 bots rentables ou de 37 audits de code.
Les variantes de fichiers, crossposts et présentations d'un même auteur ne
sont pas des validations indépendantes.

Canaux explorés : Reddit, Forex Factory, Forex Station, EarnForex, MQL5,
Myfxbook, GitHub, TradingView, Telegram public, articles d'auteurs, vidéos
indexées et résumés de travaux de recherche. Des requêtes multilingues ont
également été tentées ; les résultats effectivement pertinents et accessibles
sont consignés, pas une couverture inventée de chaque langue ou communauté.

Limites : pas d'accès aux groupes privés, de connexion avec des identifiants,
de contournement de 403, de récupération de contenu supprimé, de paywall ou
de visionnage revendiqué lorsque la vidéo est inaccessible. Aucun exécutable,
archive de robot, modèle pickle ou pièce jointe n'a été lancé. Aucun contact
commercial, achat, inscription ou partage de clé API. **« Toute trace du Web »
ne peut pas être garanti ; ce catalogue est une recherche large et bornée.**

Fichiers d'analyse :
- `data/research/community_scalpers_20261019/sources.json` : liens, familles,
  niveau d'accès, nature de la source et limites, avec identifiants S01–S37.
- `experiment_plan.json` : six pistes, métriques et interdictions explicites,
  sans autorité d'exécution ni promotion automatique.
- `broker_cohort.json`, `campaigns.json` : confrontation à notre compte démo.
- `catalogue_validation.json` : unicité des liens/identifiants et comptages.

## Ce que les particuliers partagent réellement

### 1. L'IA qui programme n'est pas nécessairement l'IA qui trade

[S02 — bot créé avec Claude, récit sur quatre jours](https://www.reddit.com/r/CryptoTradingBot/comments/1sgff5x/turned_1000_1398_over_4_days_with_a_gold_trading/)
décrit un assemblage EMA/ADX, impulsions, sessions et sweeps. Les réponses
interrogent les coûts et la brièveté de l'essai. Un gain raconté ne suffit pas
à établir une espérance durable. [S23 — expérience italienne de génération
d'EA](https://algotradinglab.it/blog/sfida-ai-expert-advisor-gold/) compare la
production de code par modèles ; cela teste notamment la programmation,
pas une supériorité prédictive automatique.

Cas concret : [S15 — ai_engine.py de P1Piyush](https://github.com/P1Piyush/XAUUSD-Trading-Bots/blob/main/ai_engine.py)
contient une génération de données aléatoires, un split aléatoire et un timestamp
de signal constant dans son exemple. Il n'est donc pas une validation d'un
modèle entraîné sur le marché réel. Cette observation concerne ce fichier lu,
pas une accusation visant tous les fichiers ou l'auteur. **Ne pas importer des
« poids AI » ou copier un pipeline de démonstration comme s'il était validé.**

### 2. Le décalage test/exécution domine les promesses de précision

[S22 — René Balke, ATR Candle Breakout](https://bmtrading.de/en/blog/atr-candle-breakout-ea/)
publie une logique de bougie d'expansion avec clôture près de son extrême et
une comparaison test/réel. Le compte rendu de l'auteur est plus informatif
qu'un seul taux de réussite, mais reste lié à son activité commerciale et
n'a pas été reproduit ici. Retenir la méthode de comparaison, pas ses rendements
ou ses réglages de taille de position.

[S31 — discussion MQL5 sur un petit compte XAUUSD M5](https://www.mql5.com/en/forum/489085)
insiste sur les prix bid/ask et les différences de broker. Les conseils sont
des retours de participants, pas une preuve d'efficacité sur notre compte.
La conséquence pratique reste testable : mesurer les coûts en unités de prix
et d'ATR, puis confronter les exécutions au scénario de recherche.

### 3. Plus de filtres peut vouloir dire moins d'opportunités, pas plus d'avantage

[S01 — jerry_farmer, stratégie adaptée à l'or](https://www.reddit.com/r/algotrading/comments/1shgpyf/improved_my_algo_again_and_adapted_to_gold/)
rapporte du mean reversion à cinq secondes, la fusion de réglages pour éviter
un double déclenchement et des essais de filtres souvent décevants. Cela reste
un récit non audité, et un système Nasdaq n'est pas validé sur l'or par simple
changement de paramètres.

[S11 — Sentinel](https://www.reddit.com/r/Trading/comments/1rgclqq/scaling_trade_frequency_on_an_mlbased_bot_25k/)
discute d'un empilement ADX/Hurst/probabilité laissant le bot sans trades.
L'intérêt pour nous est d'auditer la redondance des conditions, sans desserrer
les seuils simplement pour produire des ordres. Un filtre peut réduire les pertes
totales en supprimant presque tous les trades sans améliorer l'espérance par séquence.

### 4. Les résultats négatifs apportent une information rare

[S28 — DRL-XAUUSD-Bot](https://github.com/kennycornellius-collab/DRL-XAUUSD-Bot)
documente un SAC M15, plusieurs essais et seeds, et conclut actuellement à une
rentabilité non fiable. Les anciens tableaux favorables ne doivent pas être
isolés de cette conclusion. Pour nous : pas de PPO/SAC ajouté seulement parce
que « reinforcement learning » paraît supérieur ; conserver les échecs et
mesurer la dispersion, pas seulement le meilleur seed.

[S26 — recherche order books et RL](https://arxiv.org/abs/2311.02088), dont le
résumé inclut XAUUSD, reconnaît encore les difficultés de coûts et d'exécution
retail. [S27 — Achilles](https://arxiv.org/abs/2410.21291) annonce un LSTM et un
test de 23 jours dans son résumé. Ces deux résumés ne constituent pas une
réplication, un audit complet des articles ou une validation de notre méthode.

### 5. Les architectures publiques sont utiles, mais il faut vérifier leur statut

[S13 — MooreSi/forex-gold](https://github.com/MooreSi/forex-gold)
décrit un gouverneur déterministe, le rapprochement avec le broker et un suivi
des candidats pris ou non pris. Son README précise que la courbe illustrative
est fictive. Retenir cette transparence et les frontières de responsabilité,
pas les modèles, tailles, templates ou résultats d'illustration. Le document
ne remplace pas une revue de l'ensemble du code ; sa licence doit être respectée.

[S29 — vipersfire/xau-bot](https://github.com/vipersfire/xau-bot) expose notamment
une chaîne scalping microstructure, des métriques de spread et une évaluation
walk-forward. Nous retenons les catégories de mesures, pas les valeurs des
seuils, sessions ou durées. [S33 — architecture Joelisking](https://github.com/Joelisking/xauusd-trader/blob/main/ARCHITECTURE.md)
annonce des **objectifs** de rendement et une cascade de lots croissants :
objectifs non assimilés à des résultats, lots croissants incompatibles avec
notre contrainte de 0,01.

### 6. Les mots « safe », « AI » et « no martingale » ne dispensent pas d'inspection

[S06 — Nexus, présentation de son fondateur](https://www.forexfactory.com/thread/1384847-asso-technologies-nexus-ea-ai-powered-gold)
mentionne à la fois contrôles et grille/récupération. Cette combinaison ne
correspond pas à notre pyramidage en profit. [S07 — fil commercial Gold AI](https://www.forexfactory.com/thread/1378626-gold-ai-swing-scalp-bot)
publie notamment un exemple de signal dont le SL vaut zéro ; nous ne reprenons
pas ce comportement ni sa promesse de rendement hebdomadaire.

Dans [S08 — Forex Station](https://forex-station.com/we-have-developed-a-robot-based-on-artificial-intelligence-test-it-out-t8475958.html),
des utilisateurs rapportent un comportement acheteur et allèguent une martingale.
Nous n'avons ni exécuté ce binaire ni confirmé ces accusations : elles justifient
de demander du code et un historique complet, pas d'accuser ou d'acheter.
[S34 — Aurum](https://github.com/zero-was-here/tradingbot) distingue lui-même sa
documentation de recherche d'un ancien hedger à grille déconseillé. Une même
adresse de dépôt peut contenir plusieurs générations et niveaux de risque.

### 7. Réglages automatiques, indicateurs et groupes : ne pas confondre signal et preuve

[S32 — recalibrage hebdomadaire revendiqué](https://www.reddit.com/r/ai_trading/comments/1skdr5y/weekly_parameter_autooptimization_using_ai/)
propose une amélioration minimale du win rate comme condition de changement.
Notre analyse : un gain de 1,5 point ne fournit pas à lui seul la taille
d'échantillon, l'incertitude, la correction des essais multiples ou l'espérance
nette. Aucune auto-application de paramètres n'en est déduite.

[S35 — Gold AI Hyper-Frequency](https://www.tradingview.com/script/z6KsrpPN-Gold-AI-Hyper-Frequency-1minute-Scalper/)
décrit un indicateur Lorentzian, RSI/MFI/ROC et des cibles extensibles.
Description lue, code Pine non audité. Similarité de motifs, volume affiché
et label « institutionnel » ne prouvent ni flux agressif réel ni calibration.
[S36 — Trading Monster AI](https://www.tradingview.com/script/hZnLAZz9-XAUUSD-1-Min-Pullback-Scalper-by-Trading-Monster-AI/)
est présenté comme indicateur de pullback et d'alertes, pas un historique audité
de positions exécutées. [S37 — canal public Telegram](https://t.me/s/diamondforextrading)
sert de vitrine de produits ; aucun fichier ou signal n'a été importé.

Les deux vidéos et le fil Myfxbook inaccessible restent au catalogue pour
traçabilité, sans inventer leur contenu. Une mention « verified » ou un lien
de signal ne remplace pas notre vérification d'un historique et de ses conditions.

## Confrontation à notre méthode 3/5/6

Lecture broker démo à **08:55:43 UTC / 09:55:43 Lagos**, cohorte définie par
l'entrée après activation à 05:18:47 UTC, initialement sans position :
- 13 tickets clôturés, six gains et sept pertes ; net **-4,70 $**, PF 0,6258.
- Par chevauchement temporel : douze séquences clôturées, cinq positives et
  sept négatives. Le chevauchement est une règle de regroupement, pas la preuve
  que ces douze observations sont statistiquement indépendantes.
- Un coût **supplémentaire hypothétique** de 0,10 $ par ticket porte le total à
  -6,00 $ ; 0,25 $ à -7,95 $ ; 0,50 $ à -11,20 $. Les coûts broker récupérés
  étaient déjà dans le P/L : ce sont des scénarios de surcoût, pas une estimation
  de spread réel ni une simulation de nouveaux fills.

Ces résultats restent un petit échantillon, avec plusieurs versions de corrections
techniques pendant la période et non un essai randomisé. Ils n'établissent ni un
échec définitif des paliers, ni un avantage à ajouter davantage de positions.
Ils rendent prioritaire l'amélioration de l'espérance nette, pas du seul win rate.

L'outil hors ligne `tools/analyze_scalp_campaigns.py` regroupe les tickets,
refuse les doublons, les heures ambiguës et les snapshots non contemporains.
Il exclut des statistiques réglées les séquences contenant une position encore
ouverte ; le flottant n'est pas présenté comme un gain clôturé. Le scénario de
surcoût USD exige un compte USD et n'envoie aucun ordre.

## Ce qui pourrait améliorer notre bot : ordre de travail

| Priorité | Hypothèse à tester | État réel |
| --- | --- | --- |
| 1 | Avantage net après coûts, sans compter les ajouts comme preuves indépendantes | Outil et première mesure disponibles ; résultat actuel négatif |
| 2 | Refuser les fins d'impulsion avec forte mèche de rejet ou entrée trop étendue | Mesures déjà présentes ; nouveau seuil seulement après replay et shadow |
| 3 | Distinguer tendance/range et contrôler les confirmations redondantes | Analyse par régime à approfondir ; pas d'empilement ADX/Hurst automatique |
| 4 | Vérifier l'apport marginal des deuxième à cinquième tickets et leur espacement | Paliers inchangés ; aucun lot augmenté ni rafale d'ordres |
| 5 | S30 pour le timing avec M1/M5 pour le contexte | Observation seulement, coûts et trous de ticks à mesurer |
| 6 | ML/calibration/retraining avec contrôle des essais et des échecs | Pas de poids externes ou d'auto-optimisation promus |

Le plan JSON fixe ces hypothèses et les conditions de validation. Une restriction
retrospective sur les tickets existants ne simule pas l'entrée décalée, les sorties
dynamiques ou les opportunités futures : une variante doit rejouer tout ce cycle.
Les archives de quotes échantillonnées ne sont pas automatiquement un historique
exhaustif de ticks ou de contexte point-in-time.

Références méthodologiques primaires :
- [Bailey et al., risque de surapprentissage des backtests](https://www.davidhbailey.com/dhbpapers/backtest-prob.pdf) :
  enregistrer tous les essais et ne pas sélectionner sur le dernier segment.
- [TimeSeriesSplit](https://scikit-learn.org/stable/modules/generated/sklearn.model_selection.TimeSeriesSplit.html) :
  validation temporelle, complétée ici par purge des horizons de labels et
  regroupement des tickets corrélés. Un split temporel seul ne règle pas tout.
- [MetaQuotes, symbol_info](https://www.mql5.com/en/docs/python_metatrader5/mt5symbolinfo_py) :
  vérifier minimum et pas de volume avant de copier une clôture partielle.
  Si minimum et pas sont de 0,01, un ticket 0,01 ne peut pas être réduit de moitié.

## Décision et validation

**Aucun paramètre ni moteur de trading actif n'a été modifié ou redémarré pendant
cette recherche.** Les paliers autorisés, le lot 0,01, les SL, cinq positions
maximum, les sorties dynamiques et le S30 observateur restent inchangés.
Advisor 1 n'est pas touché. Les ajouts de ce tour concernent le catalogue, le
plan d'expérience et l'analyse hors ligne.

Quatre tests ciblés de l'analyse passent : groupement, coût, séparation de
séquences, positions ouvertes, refus de données incohérentes. La validation
du catalogue contrôle les identifiants, liens uniques et références du plan.
Ce n'est pas une preuve de rentabilité et la suite historique complète n'est
pas présentée comme exécutée.

**Conclusion :** les témoignages élargissent les hypothèses ; les mécanismes
reproductibles et nos propres données décident de leur promotion. La priorité
est de conserver un mouvement gagnant sans entrer trop tard ni multiplier des
positions au même risque, tout en rejetant les variantes dont les coûts mangent
l'espérance. Aucun témoignage consulté ne suffit à garantir ce résultat.
