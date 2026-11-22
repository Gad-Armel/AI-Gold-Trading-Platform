# Recherche : 1, 2 ou 3 bougies M1 consécutives

## Conclusion

Interprétation étudiée : achat après des corps haussiers clôturés consécutifs,
vente après des corps baissiers. Ce n'est ni une série de plus hauts, ni une
stratégie contrariante après trois bougies. Clarification demandée à l'utilisateur.

Le profil principal en place demandait une seule bougie M1 concordante.
Après affaiblissement, sa confirmation spéciale SCALP demandait également une
seule nouvelle M1. Les deux M5 concernent les horizons secondaires, pas une
confirmation générale de deux ou trois M1.

**Trois bougies constituent une piste de filtrage, pas une stratégie rentable
démontrée. Deux bougies seules ne montrent pas d'amélioration robuste.**

## Mesure sur les données du projet

Lecture seule du compte démo à 03:38:14 UTC / 04:38:14 Lagos le 19 octobre 2026 :
30 000 bougies M1 broker et 413 positions SCALP clôturées récupérables.
Fichiers reproductibles : `data/research/m1_confirmation_20261019/input.json`
et `comparison.json`. Aucun ordre envoyé par l'outil de recherche.

Pour chaque entrée historique, seules les bougies déjà clôturées à son heure
d'ouverture sont examinées. L'heure broker est normalisée avec l'offset configuré
de 10 800 secondes. Les doublons, trous et bougies en formation ne confirment pas.
Les dojis ne sont ni haussiers ni baissiers.

| Filtre au moment de l'entrée réelle | Trades retenus | Gains / pertes | Net historique | Net / trade | Profit factor |
| --- | ---: | ---: | ---: | ---: | ---: |
| Aucun filtre supplémentaire | 413 | 185 / 228 | -167,07 $ | -0,4045 $ | 0,6669 |
| 1 M1 concordante | 402 | 180 / 222 | -164,40 $ | -0,4090 $ | 0,6609 |
| 2 M1 concordantes | 159 | 70 / 89 | -60,31 $ | -0,3793 $ | 0,6607 |
| 3 M1 concordantes | 90 | 43 / 47 | -15,24 $ | -0,1693 $ | 0,8429 |

Moins de perte totale peut simplement venir de moins de trades. Les indicateurs
par trade restent négatifs et les profit factors inférieurs à un.
Les onze entrées non concordantes avec une M1 appartiennent à un historique
de versions mélangées : leur présence n'établit pas à elle seule une panne actuelle.

Contrôle chronologique descriptif sur les dates du 18–19 octobre : trois M1
retiennent onze trades, sept gains et quatre pertes, mais **-1,34 $** net.
Le gain moyen est 1,1243 $, la perte moyenne 2,3025 $ : même 63,6 % de gains
ne suffisent pas ici. Deux M1 retiennent quinze trades à -7,18 $ net.
Cette période a déjà été observée : ce n'est pas un holdout vierge.

Il s'agit du P/L broker réel des positions conservées par le filtre, avec frais
récupérables. Ce n'est pas une simulation fidèle d'une autre stratégie : attendre
une bougie de plus modifie l'heure et le prix d'entrée, les sorties, les futures
opportunités et le chevauchement des positions. Rien ne permet d'attribuer les
résultats de ces sous-ensembles à un futur robot exécutant la variante.

## Inspection et corrections du code

- `entry_momentum_blocks` accepte un nombre explicite de une à trois M1 : mêmes
  corps directionnels, dates distinctes consécutives, bougies clôturées uniquement.
- Défaut corrigé : l'ancien contrôle pouvait accepter une dernière M1 clôturée
  vieille de presque trois minutes. Si une minute clôturée attendue manque,
  les nouvelles entrées sont désormais bloquées ; les sorties restent indépendantes.
- `SCALP_M1_CONFIRMATION_BARS` expose le choix dans la configuration principale.
  Après accord explicite de l'utilisateur pour essayer cette règle, valeur
  passée à **3**, uniquement en démo. Cela constitue un essai expérimental,
  pas une promotion fondée sur une rentabilité démontrée.
- Le nombre demandé est attaché à la décision et à l'observation d'entrée.
- Redémarrage ciblé le 19 octobre à **03:41:12 UTC / 04:41:12 Lagos**, après
  vérification du compte démo et du SL de la position existante. Le premier
  lancement du script était bloqué par PowerShell et n'avait arrêté aucun bot.
  La seconde exécution a réussi sans changement permanent de politique Windows.
- Statut vérifié : `m1_entry_confirmation_required_bars = 3`, état de sorties
  `RESTORED`, blocage explicite lorsque les trois M1 ne concordent pas.
  La confirmation spéciale après affaiblissement exige également trois
  nouvelles M1 clôturées. Les positions préexistantes ne sont pas liquidées
  simplement parce que la nouvelle règle d'entrée diffère.
- Advisor 1, tailles de lots, plafond de cinq positions, SL et sorties dynamiques
  ne sont pas modifiés. Pas de TP fixe ajouté.

## Pistes prioritaires, à valider plutôt qu'à promettre

1. **Espérance nette avant taux de réussite.** Mesurer gain/perte moyens, coûts,
   MAE/MFE et restitution des gains par cohorte de version. Ne pas fermer tous
   les gagnants plus tôt sans quantifier l'effet sur l'espérance.
2. **Contexte M5/M15 et extension.** Comparer une confirmation 2/3 M1 avec un
   filtre de régime et une limite d'extension normalisée par ATR. Trois bougies
   peuvent confirmer une impulsion, mais aussi provoquer une entrée tardive.
   C'est une hypothèse de recherche, pas un avantage établi sur ces données.
3. **Coûts et timing exécutables.** Rejouer bid/ask, commissions, slippage et
   trous de ticks, puis examiner le spread relativement au mouvement attendu.
   Conserver les stops, plafonds et garde-fous d'ajout ; ne pas augmenter les lots.
4. **Confiance réellement mesurée.** Le mode directionnel continu autorise
   actuellement un plancher 15/100 ; un seuil de lane 82 présent ailleurs dans
   la configuration ne signifie pas que toutes les entrées l'appliquent.
   Les scores Advisor 1 ne sont pas des probabilités calibrées. Estimer la
   probabilité de résultat net positif exige des labels et une calibration
   indépendants, pas le renommage de « 85/100 » en « 85 % de chance ».
5. **Validation fidèle et prospective.** Figer les trois variantes, rejouer
   réellement les entrées décalées et les sorties actuelles, séparer les jours
   chronologiquement avec purge des labels chevauchants, puis observer en shadow
   sur des données nouvelles. Rejeter une variante si son espérance nette reste
   négative ou s'effondre sous coûts stressés. Ne pas sélectionner sur le dernier
   segment puis le présenter comme une validation indépendante.

## Sources primaires consultées

- [MetaQuotes : copy_rates_from_pos](https://www.mql5.com/en/docs/python_metatrader5/mt5copyratesfrompos_py) :
  l'indice zéro est la bougie courante. Elle ne doit pas confirmer une entrée
  présentée comme fondée sur des bougies clôturées.
- [Lu, Chen et Hsu, 2015, page de recherche universitaire](https://researchoutput.ncku.edu.tw/en/publications/trend-definition-or-holding-strategy-what-determines-the-profitab/) :
  les résultats de configurations candlestick dépendent aussi des règles de
  détention/sortie. Étude sur actions et motifs journaliers : aucune preuve
  directe concernant trois bougies M1 sur XAUUSD.
- [Bailey et al. : The Probability of Backtest Overfitting](https://www.davidhbailey.com/dhbpapers/backtest-prob.pdf) :
  multiplier les essais puis retenir le meilleur résultat historique accroît
  le risque de surapprentissage. Le classement rétrospectif ci-dessus n'est
  donc pas une autorisation de déploiement.
- [scikit-learn : TimeSeriesSplit](https://scikit-learn.org/stable/modules/generated/sklearn.model_selection.TimeSeriesSplit.html) :
  séparation temporelle et paramètre gap. Pour des labels chevauchants, la purge
  doit couvrir leurs horizons ; un split aléatoire n'est pas une validation adaptée.
- [scikit-learn : calibration](https://scikit-learn.org/stable/modules/calibration.html) :
  comparer les probabilités annoncées aux fréquences observées. Cette démarche
  n'établit pas, à elle seule, une espérance de trading positive après coûts.

## Reproduction

Recherche hors ligne, sans connexion ni ordre :

```powershell
.\.venv-audit\Scripts\python.exe -B tools/research_m1_confirmation.py --output data/research/m1_confirmation_20261019
```

L'option `--fetch-demo` renouvelle les lectures broker ; elle exige une connexion
démo vérifiée et ne contient aucun appel d'envoi ou modification d'ordre.

Validation ciblée : 143 tests et cinq sous-tests réussis ; `tests.xml` dans le
dossier de recherche. Cela ne signifie pas que toute la suite historique passe.

Collecte de vérification après déploiement : `data/monitoring/20261019T034122Z`.
Du 03:41:22 au 03:43:23 UTC, 25 captures fraîches en 2,02 minutes : aucun
dépassement de capacité, lot inattendu, compte réel, SL manquant ou erreur advisor.
La position préexistante s'est clôturée à -1,08 $ ; aucune nouvelle entrée de
l'essai pendant cette fenêtre. Cette perte n'est pas le résultat d'une entrée
autorisée par la nouvelle règle. La baseline et ses tickets préexistants sont
conservés dans `trial_baseline.json` pour éviter cette attribution incorrecte.
Journaux : `logs/monitored-main-20261019T034112Z.stdout.log` et `.stderr.log`.
L'observateur de vérification n'envoie aucun ordre. Le moteur principal reste
actif après la courte collecte ; aucune surveillance de rentabilité illimitée
n'est garantie par cet essai.
