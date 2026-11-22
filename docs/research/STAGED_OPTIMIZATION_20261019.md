# Gestion des paliers : inspection, recherche et corrections

## Résultat et limites

Revue du 19 octobre 2026, collecte broker à 05:33–05:36 UTC / 06:33–06:36 Lagos.
Objectif : améliorer la qualité mesurable de la gestion 3/5/6 M1, sans augmenter
les lots, supprimer les stops, ajouter un TP fixe ou activer le S30 comme exécuteur.
L'expression « à son prime » ne correspond pas à un niveau de performance
démontré. Il n'existe pas ici de preuve permettant de promettre une rentabilité.

Les 420 SCALP clôturés récupérables sur quatorze jours, versions mélangées,
totalisent -168,75 $, 188 gains et 232 pertes. Gain moyen 1,7942 $, perte moyenne
2,1813 $, profit factor 0,6665. Le taux de gain observé est environ 44,8 % ;
avec ces gains/pertes moyens, le seuil d'équilibre descriptif serait environ
54,9 %. Ce calcul ne prédit pas les prochaines performances.

Les six entrées postérieures au premier essai trois M1 à 03:41:12 UTC et déjà
clôturées ont trois gains et trois pertes, -0,60 $ net. Ce groupe inclut les
versions intervenues avant les paliers. **Aucun trade ouvert après activation
des paliers à 05:18:47 UTC n'était encore clôturé à 05:35:48 UTC.** Les pertes
historiques ne doivent donc pas être attribuées aux nouveaux paliers.

Lors du contrôle technique, le bot est sans position, sa direction est WAIT et
le contexte de recherche M5 indique RANGE_OR_TRANSITION. Il s'agit d'une
observation ponctuelle du broker démo, pas d'une prévision du marché mondial.

## Ce qui est corrigé et déployé

1. Avant un ajout, chaque position existante doit avoir un SL numérique fini,
   positif et encore du côté protecteur du prix exécutable. Un SL manquant,
   NaN ou déjà traversé bloque l'ajout. Les protections de profit, direction,
   capacité et scores renforcés des quatrième/cinquième restent requises.
2. Des heures d'ouverture manquantes, mixtes ou invalides ne peuvent plus faire
   échouer le calcul du palier ni fournir une ancienne clôture de substitution.
   Le calcul retourne un marqueur invalide qui bloque l'ajout.
3. Les décisions et journaux d'ordre conservent désormais la qualité des M1,
   le palier effectivement observé et le S30 shadow. Le journal précise aussi
   si les paliers étaient activés à l'entrée, au lieu de déduire la version
   uniquement d'un horaire.
4. L'audit broker accepte `--since` avec fuseau explicite. Le groupe est défini
   par l'heure d'entrée, pas par l'heure de clôture : une position préexistante
   ne devient pas un résultat du nouvel essai lorsqu'elle se ferme ensuite.

Redémarrage ciblé à 05:35:50 UTC / 06:35:50 Lagos, compte démo et absence de
positions vérifiés. Statut RUNNING, état des sorties RESTORED, lot 0,01 et cinq
positions maximum. Les paramètres de sortie et seuils 3/5/6 ne sont pas modifiés.
Le S30 n'a toujours aucune autorité d'ouverture. Advisor 1 reste inchangé.

## Qualité des séries : mesures sans nouveau filtre arbitraire

`decision.m1_sequence_quality` expose des caractéristiques observables :
- part des corps dans les ranges et mèche de rejet de la dernière clôture ;
- déplacement de la série et spread normalisés par ATR ;
- spread rapporté au déplacement directionnel de la série ;
- extension du prix d'entrée exécutable par rapport à la dernière clôture.

Seules les bougies déjà clôturées sont utilisées ; les minutes manquantes,
doublons, prix impossibles et données périmées rendent la mesure indisponible.
Cette télémétrie est **RESEARCH_ONLY**, sans seuil bloquant nouveau et sans
probabilité calibrée. Elle ne permet pas d'annoncer immédiatement « moins de
pertes ». Elle prépare une vérification prospective de deux problèmes possibles :
acheter une impulsion déjà épuisée et payer un spread excessif pour un déplacement
trop faible. Une série de bougies ne suffit pas à trancher ces hypothèses.

## Recherche et interprétation pour l'or

Le [World Gold Council, bilan de juillet 2026](https://www.gold.org/goldhub/research/gold-mid-year-outlook-2026)
analyse plusieurs moteurs : activité, risque, coût d'opportunité et momentum.
Il discute aussi des variations entre sessions. **Ces analyses macro et mensuelles
ne justifient pas une entrée M1 ni un biais acheteur permanent en octobre.**
Implication pour le projet : conserver des contextes et des régimes séparés,
plutôt que multiplier les positions parce que les dernières bougies sont vertes.

La [Chicago Fed, What drives gold prices?](https://www.chicagofed.org/-/media/publications/chicago-fed-letter/2021/cfl464-pdf.pdf?sc_lang=en)
étudie notamment les taux réels et les anticipations. Ce cadre aide à interpréter
le contexte ; il ne prouve pas une corrélation stable exploitable à trente secondes.
Les sources macro indisponibles ne doivent pas être transformées en confirmations.

Pour l'évaluation, [TimeSeriesSplit et son gap](https://scikit-learn.org/stable/modules/generated/sklearn.model_selection.TimeSeriesSplit.html)
fournissent un cadre temporel ; il faut en plus purger les labels chevauchants
et tenir compte des positions corrélées. La prochaine étape pertinente est un
replay fidèle des entrées et sorties, avec coûts, puis une collecte prospective
par version et palier, pas une recherche du meilleur seuil sur les pertes récentes.

La documentation [MetaQuotes order_calc_profit](https://www.mql5.com/en/docs/python_metatrader5/mt5ordercalcprofit_py)
prévoit l'évaluation d'un P/L dans la devise du compte. Pour un futur budget de
risque agrégé, cette évaluation broker est préférable à une hypothèse universelle
sur la valeur du contrat. Aucun nouveau plafond monétaire ni calcul de lot n'est
introduit dans cette revue.

## Priorités avant toute nouvelle promotion

1. Accumuler les résultats propres au mode 3/5/6, avec un compte des opportunités
   refusées, des coûts, du drawdown et des gains/pertes moyens.
2. Comparer le premier ticket et les ajouts d'une même séquence comme une grappe
   corrélée, pas comme plusieurs preuves indépendantes.
3. Rejouer la restitution des gains avec les sorties actuelles et les quotes
   exécutables : ne pas resserrer arbitrairement le trailing après quelques pertes.
4. Figer à l'avance une hypothèse de filtre d'épuisement/coût, l'évaluer sur une
   période chronologique distincte, puis en shadow sur de nouvelles données.
   Rejeter les variantes à espérance nette négative ou fragiles aux coûts stressés.

## Preuves et validation

156 tests et cinq sous-tests ciblés réussis. Tests de SL manquant/traversé,
heures malformées, absence de données futures, calculs de coût/rejet,
conservation des diagnostics dans le journal et attribution par heure d'entrée.
Les 18 hashes protégés d'Advisor 1 sont inchangés. La suite historique complète
n'est pas présentée comme validée.

Preuves dans `data/research/staged_optimization_20261019` : `history.json`,
`cohort_baseline.json`, `tests.xml`, `runtime.json`, `advisor1_integrity.json`.
Logs déployés : `logs/monitored-main-20261019T053550Z.*`.
Collecte de vérification : `data/monitoring/20261019T053608Z`.

Le bot reste en démo. Les corrections renforcent la sûreté et la mesure ;
**elles ne démontrent pas encore une amélioration des performances de trading.**
