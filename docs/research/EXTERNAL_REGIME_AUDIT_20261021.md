# Revue des quatre fichiers transmis : moteurs A/B/C et simulateurs

## Décision et périmètre

Les fichiers `multi.py`, `sweep.py`, `xau_sim.py` et les 1 249 lignes de
`XAU_RegimeScalper_AI.mq5` ont été examinés. Le texte joint est traité comme
une proposition et des résultats à vérifier, pas comme une instruction
d'installer un nouvel exécutant ni comme une preuve de rentabilité.

Les originaux dans Downloads ne sont pas modifiés. Leurs hashes sont enregistrés
dans `data/research/external_regime_20261021/source_manifest.json`. L'EA fourni
n'est **ni compilé, ni installé, ni activé**. Le main Python reste le seul
exécutant concerné ; le lot 0,01, le plafond global de quatre, les SL obligatoires
et Advisor 1 ne sont pas modifiés. La suspension des nouvelles entrées reste
active : cette revue n'est pas une autorisation de la retirer.

## Problèmes constatés

### `sweep.py` : contamination entre variantes

`run()` exécute `X.P.update(over)` sur un dictionnaire global. Un worker du
ProcessPool peut exécuter plusieurs jobs : une variante qui ne remplace pas
tous les paramètres hérite donc de ceux du job précédent. L'ordre de distribution
des jobs peut influencer le résultat. Ce n'est pas une comparaison isolée fiable.

Le correctif intégré est `run_isolated()` : copie profonde des paramètres de
référence, application des seuls overrides explicites, et restauration même
si une simulation échoue. Les clés inconnues sont refusées. Le lanceur
`tools/check_xau_synthetic.py` utilise cette isolation et ne lance pas un pool
massif de variantes sur le PC du bot.

### `multi.py` et le texte : interprétation statistique trop forte

Le t-stat basé sur l'ensemble des R suppose une indépendance que des trades
temporellement proches ne garantissent pas. Les cas zéro trade, un seul résultat
ou écart-type nul ne sont pas correctement traités par les agrégateurs fournis.
Le fait de perdre sur une marche aléatoire **ne prouve pas** l'absence de fuite
temporelle : il faut des tests ciblés de causalité.

Le texte annonce lui-même un t de 0,56 pour v7 : aucun avantage significatif
n'est établi. De plus, le dictionnaire livré de `xau_sim.py` n'a pas les mêmes
defaults que l'EA : EMA HTF 50/200 contre 21/55, cible A 1,5R contre 3R,
break-even 1R contre 0,8R, durée 12 contre 24 barres et trailing différents.
Les overrides exacts des sept expériences ne sont pas fournis. Il est donc
impossible de reproduire leur tableau ou d'affirmer une parité Python/MQL5
à partir de ces seuls fichiers.

### `xau_sim.py` : diagnostic synthétique, pas validation broker

- Le simulateur conserve des OHLC M1, pas le chemin bid/ask tick par tick.
  Choisir SL avant TP dans une bougie ambiguë ne résout pas tous les biais.
- Un gap traversant le stop est rempli au prix du SL, ce qui peut sous-estimer
  la perte ; notre replay utilise la première quote exécutable observée.
- Le drawdown est mis à jour à la clôture et ne mesure pas le drawdown flottant.
- Les positions virtuelles n'appliquent pas les mêmes break-even et trailing
  que les positions dites réelles. Leurs dénominateurs de R diffèrent aussi.
  Elles ne justifient pas de réactiver la même politique d'exécution.
- Le choix prioritaire d'un moteur actif peut priver les moteurs en pause
  d'observations virtuelles. Le simple reset après 72 heures ne prouve pas
  une amélioration du marché.
- Les lots ne sont pas soumis aux véritables pas/minimums/marges du broker.
  Le générateur continue à évoluer avant de retirer les weekends : les gaps
  synthétiques ne sont pas une reconstruction des sessions de notre broker.
- Le calcul des trades par jour exclut les dates sans trade ; il ne suffit
  pas à démontrer que le bot trade presque tous les jours.

Le nouveau lanceur synthétique conserve ces limites explicitement. Il isole
les paramètres mais **ne transforme pas le simulateur fourni en backtest réaliste**.

### `XAU_RegimeScalper_AI.mq5` : ne pas installer tel quel

1. Pas de garde compte démo : `TradingAllowed()` ne vérifie pas le type de
   compte. Un symbole non gold provoque seulement un avertissement à l'init.
2. `InpFixedLot=0` par défaut active un dimensionnement à 0,5 % de l'equity,
   incompatible avec la consigne de lot strictement 0,01.
   Même avec lot fixe, `realRisk` reprend le budget nominal au lieu du risque
   monétaire du lot réellement ouvert : le R utilisé pour apprendre peut être faux.
3. Le fallback `withStops=false` ouvre expressément sans SL. Si la modification
   ou la fermeture suivante échoue, une exposition non protégée peut rester.
   La promesse « jamais sans protection » du commentaire n'est donc pas garantie.
4. Les retries sur timeout/déconnexion ne réconcilient pas l'ordre précédent
   avant un nouvel envoi : risque de duplication dans un état d'exécution incertain.
5. `PLACED` et `DONE_PARTIAL` sont traités comme une exécution complète. Les
   volumes réellement remplis et les ordres encore actifs nécessitent une
   réconciliation, pas seulement un booléen de succès.
6. `POSITION_IDENTIFIER`, ticket de position et ticket d'ordre sont utilisés
   comme s'ils étaient interchangeables dans `PositionSelectByTicket`, modify
   et close. Ils peuvent diverger ; une clôture partielle pourrait être mal reconnue.
7. `EnsureOR()` mémorise un range invalide quand des données incomplètes arrivent
   sans erreur négative : il peut rester inutilisable toute la journée.
8. `longDone/shortDone` sont consommés lors de la détection, avant filtre de coût,
   sélection du moteur et succès d'ordre. Un setup peut être perdu sans aucun fill.
9. La mémoire persistée n'est pas liée au compte ni à la version des paramètres.
   Elle tronque aussi les R extrêmes : le risque réel peut être masqué dans le score.
10. Le P/L journalier reconstruit au restart et les ajouts à la clôture ne traitent
    pas de façon cohérente commissions d'entrée, partiels et solde de référence.
    Les pauses drawdown/cooldown ne sont pas toutes récupérées au redémarrage.
11. La liste news est vidée avant de vérifier le succès du calendrier. Un échec
    peut être affiché comme une absence de news. Les paramètres ont peu de
    validation et certains échecs de marge ne bloquent pas l'ouverture.
12. Le stop est parfois tronqué à un maximum ATR, donc déplacé à l'intérieur
    de la structure utilisée pour justifier l'entrée. Les TP fixes sont aussi
    contraires au choix de sorties dynamiques sans TP maximum du projet.

Les codes `PLACED`, `DONE` et `DONE_PARTIAL` ont des significations distinctes
dans la [documentation MetaQuotes des retcodes](https://www.mql5.com/en/docs/constants/errorswarnings/enum_trade_return_codes).
La [documentation des propriétés de position](https://www.mql5.com/en/docs/constants/tradingconstants/positionproperties)
distingue ticket et identifiant ; les événements d'exécution doivent être
traités sans supposer un ordre unique de notifications.
[OnTradeTransaction](https://www.mql5.com/en/docs/event_handlers/ontradetransaction).

Cette revue statique ne constitue pas un rapport de compilation ni une preuve
que chaque scénario de panne ci-dessus se produit sur ce broker.

## Éléments utiles réellement intégrés

### Trois moteurs causaux de recherche

`gold_multiengine_research.py` reprend :

- **A** : repli EMA21 M5, reprise EMA9/RSI, biais M15 EMA21/55 et pente.
- **B** : cassure d'un range d'ouverture de 30 minutes avec couverture M1
  complète. Les heures locales Londres/New York utilisent `ZoneInfo`, donc
  les décalages d'heure d'été ne sont pas codés comme une constante annuelle.
- **C** : réentrée dans Bollinger en régime latéral avec RSI d'excès.
- Régime : ADX, Efficiency Ratio et percentile ATR causal sur 288 M5.

Ce sont des hypothèses déterministes, pas un modèle ML entraîné ni des
probabilités calibrées. Les données indisponibles ne sont pas mémorisées comme
un échec permanent : elles sont réessayées. Les stop-loss trop éloignés sont
refusés dans ce modèle au lieu d'être arbitrairement déplacés dans la structure.

### Suivi papier équitable et score indépendant

`gold_engine_paper.py` fait observer **chaque moteur indépendamment**, même
quand son score papier est en pause. Tous utilisent le même kernel de fills,
coûts et sorties : bid/ask, 350 ms supposées, 0,30 de frais supplémentaires,
SL, BE 0,8R, trailing après 1,2R à 1,5 ATR d'entrée et durée maximale 1 heure.
Il n'y a pas de TP fixe installé. La limite structurelle de 10 en prix ne
concerne que ce modèle papier ; elle n'est pas appliquée au main.

Un range n'est consommé qu'après un fill simulé réussi. Les refus, expirations
et erreurs de stop n'interdisent pas un futur essai du même range. Les résultats
conservent leur risque initial, afin de calculer un R net cohérent.

`gold_engine_score.py` garde au plus 20 R récents, avec prior de cinq et minimum
de huit résultats. Les événements sont dédupliqués, ordonnés et les pertes
extrêmes ne sont pas effacées. Après une pause, une reprise papier exige des
résultats nouveaux ; l'expiration seule produit **PAPER_REVIEW_DUE**, jamais
une permission d'ordre. Aucun score papier ne retire la suspension globale.

Le ratio objectif analytique/coût reste **diagnostique**. Le veto de coût que
l'utilisateur avait supprimé n'est pas réintroduit dans le main. Les filtres
news/session existants, lot fixe et plafond de quatre restent inchangés.
Les conditions globales de session/news de l'EA fourni ne sont pas toutes
rejouées dans cet essai ; ce n'est pas une reproduction intégrale de son backtest.

### Résultats et portée

Sur la capture réelle corrigée de 24 h déjà utilisée dans la recherche :

| Moteur | Positions papier closes | Net, unités de prix à 1 oz |
| --- | ---: | ---: |
| A | 2 | −0,16 |
| B | 1 | −9,49 |
| C | 0 | 0,00 |

Ces chemins sont séparés, corrélés et non soumis à une marge de portefeuille.
Les éventuelles positions encore ouvertes sont censurées et signalées dans
le JSON. Ce jeu a déjà servi à la recherche : **pas de nouveau test aveugle**,
pas de comparaison de seuils jusqu'à obtenir du vert, pas d'avantage validé.

Le smoke-test synthétique (cinq jours, seed 1) donne six trades à régimes et
onze en marche aléatoire. Le premier est positif, le second légèrement négatif.
Cela montre que le runner fonctionne ; **cela ne valide pas le trading de l'or**.

## Reproduction et état du main

```powershell
cd 'C:\Users\Gad Asopjio\Desktop\AI Trading Platform'
.\.venv-audit\Scripts\python.exe -B .\tools\evaluate_gold_abc.py
.\.venv-audit\Scripts\python.exe -u -B .\tools\observe_gold_abc.py --minutes 30 --output data/research/new_abc_trial
```

Le deuxième outil exige un compte démo USD, un dossier d'essai vide et une
identité de compte stable. Il ne possède aucun appel d'ordre. Il lit des
bougies déjà clôturées (`start_pos=1`), rafraîchit le contexte à la nouvelle M5,
enregistre l'heure réelle de décision et termine son observation à durée bornée.

Le main affiche les diagnostics A/B/C sans les utiliser pour ouvrir des
positions. Le dashboard distingue replay historique, observation papier live
et observation terminée. Les originaux, l'EA natif existant et Advisor 1 restent
séparés de ce prototype.

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\tools\start_gold_consensus.ps1
```

Cette commande lance/retrouve le main et son dashboard ; **elle ne lève pas
la suspension volontaire des nouvelles entrées**.

Artefacts : `data/research/external_regime_20261021/` contient le manifeste
des sources, `abc_replay.json`, `synthetic_smoke.json` et le smoke-test prospectif
`forward/latest.json`. La rentabilité reste non démontrée.

## Vérifications réalisées

- **107 tests ciblés réussis**, dont causalité HTF, continuité du range,
  réessai des données, isolation des variantes, déduplication, pause/revue,
  slippage/SL gaps et sorties ATR. Ce n'est pas un succès annoncé de toute la
  suite historique du dépôt.
- Test JavaScript du polling dashboard réussi ; les panneaux restent sans
  autorité d'ordre.
- Smoke-test prospectif terminé après **120,38 secondes**, zéro trade papier.
  Six alertes de quote trop ancienne sont enregistrées ; aucun prix artificiel
  n'est utilisé pour provoquer une entrée. Ce test vérifie le fonctionnement,
  pas la performance financière.
- Hashes identiques pour les **18 fichiers protégés d'Advisor 1**.
- Main redémarré en démo, lot 0,01, quatre positions maximum, suspension
  d'entrée conservée. Aucun nouvel EA n'est attaché au terminal.
