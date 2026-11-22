# Suivi démo du 18 octobre 2026

Statut : collecte automatique initiale terminée ; revue effectuée le 19 octobre
à 03:11–03:14 UTC / 04:11–04:14 Lagos. Bot toujours actif en démo.
Vérifications commencées le 18 octobre à 20:45 UTC / 21:45 Lagos.
Observateur lancé à 20:49:46 UTC / 21:49:46 Lagos pour 120 minutes ; les deux
premières observations portaient encore un ancien statut et sont exclues du bilan.

## Périmètre autorisé

Moteur Python uniquement, compte MetaQuotes-Demo vérifié, lot fixe 0,01,
cinq positions maximum. Advisor 1 reste intact. Aucun moteur natif concurrent
n'a de télémétrie fraîche. Les améliorations ne doivent pas supprimer les SL,
augmenter les lots, activer un compte réel ou réinitialiser les pertes.

## Diagnostic initial

Le terminal était arrêté et la première tentative sous le profil sandbox a
échoué en IPC. Le terminal créé par cette tentative a été identifié puis
relancé dans la session utilisateur. Sa mise à jour automatique a terminé ;
connexion démo confirmée, aucune position ouverte, solde et equity 23 431,15 $.
Ce solde démo n'est pas le budget théorique de stratégie de 100 $.

Au démarrage, le dernier tick XAUUSD était celui du vendredi. Les entrées sont
donc bloquées ; une connexion du terminal ne prouve pas que le marché cote.
Ne pas fabriquer de trades ou modifier les seuils pour contourner ce blocage.

Historique démo récupérable sur quatorze jours, avec politiques historiques
mélangées : 412 trades, -206,81 $ net. SCALP : 365 trades, -140,67 $, 166 gains
et 199 pertes, gain moyen 1,8242 $, perte moyenne -2,2285 $.
Les 117 entrées SCALP dont l'evidence enregistrée atteint 85/100 ont 57 gains,
60 pertes et -13,41 $ net. Cette comparaison descriptive ne prouve pas qu'un
nouveau seuil serait profitable.

Sur les trente derniers SCALP, 23 disposent d'une couverture de quotes archivées
sans trou supérieur à dix secondes. Quatorze sont perdants ; quatre ne montrent
aucun passage positif et quatre ont atteint au moins 0,50 $ sur les quotes
échantillonnées. Ces maxima ne sont pas des prix de sortie garantis et ne
permettent pas de choisir rétrospectivement un trailing optimal.

## Modifications et vérifications

- Dashboard principal : cartes, historiques et lignes économiques INTRADAY/SWING
  masqués ; calculs et données de contexte conservés. Vérification HTTP du
  service réellement lancé et tests de conservation des trois lanes dans l'API.
- Console : affichage SCALP seul, plafond annoncé corrigé de trois à cinq.
- Journaux d'entrée : ajout de l'âge du signal, état effectif du micro-flux,
  fraîcheur du marché et confirmation au moment de l'ordre.
- Rapport de suivi : exclusion des statuts périmés provenant d'un ancien run,
  afin de ne pas transformer ses pertes en faux gain de la nouvelle session.
- Audit de capacité : lecture du plafond réel du statut, au lieu d'un plafond
  historique codé à trois.
- Outil de redémarrage : interpréteur explicite, reconnaissance de l'arbre
  launcher/worker du virtualenv et vérification démo/SL avant arrêt ciblé.

Déploiement du journal enrichi à 20:56:04 UTC, sans position ouverte. L'observateur
continue pendant ce redémarrage. Aucune règle directionnelle ou valeur de seuil
de trading n'a été optimisée sur ces quelques minutes sans marché frais.

## Preuves

- Captures : `data/monitoring/20261018T204946Z/observations.jsonl` et `latest.json`.
- Historique : `historical_baseline.json`, diagnostic `recorded_excursions.json`
  dans ce même dossier.
- Rapports : `summary.json`, `constraints_audit.json` après synthèse.
- Journaux de processus : `logs/live-main-20261018T204944Z.*`,
  `logs/monitored-main-20261018T205604Z.*`, `logs/live-monitor-20261018T204944Z.*`.

## Résultat de la fenêtre initiale

Collecte brute du 18 octobre 20:49:46 au 22:49:53 UTC, soit environ deux heures.
Après exclusion des deux statuts anciens et de deux captures incomplètes,
715 observations restent, du 20:50:06 au 22:49:53 UTC : **119,78 minutes**.
Les deux captures incomplètes correspondent à des refus transitoires de lecture
du statut Windows. Le premier échantillon de cotation fraîche apparaît à
22:00:19 UTC ; il ne s'agit donc pas de deux heures de marché actif.

- Quatre positions clôturées : trois gains, une perte ; réalisé **+4,05 $**.
- Une position encore ouverte en fin de fenêtre : flottant -0,82 $ ; variation
  d'equity et résultat réalisé + flottant **+3,23 $**.
- Drawdown d'equity maximal échantillonné : 3,20 $.
- Maximum observé : deux positions ; aucun dépassement de capacité, compte
  réel, lot différent de 0,01 ou position contrôlée sans SL dans les captures.
- Cadence médiane enregistrée 91,37 ms, p95 680,54 ms ; pas d'erreur advisor
  rapportée dans les statuts frais. Ces mesures n'incluent pas chaque tick.

Le collecteur et le watcher ont continué automatiquement pendant l'intervalle
sans interaction. Cela ne constitue pas une intervention manuelle continue,
ni une optimisation de la stratégie à chaque trade. Quatre clôtures ne
valident ni une probabilité de gain, ni une amélioration de rentabilité.

## Évolution après cette fenêtre

La vérification broker du 19 octobre à 03:11 UTC retrouve **42 clôtures SCALP
supplémentaires depuis le lancement**, dont 16 gains et 26 pertes, net **-26,95 $**.
Ce résultat porte sur toute la période depuis le lancement, et non uniquement
sur la fenêtre initiale positive. Ne pas additionner les deux résultats.
Le bot a continué à exécuter après la fin du collecteur initial.

Sur les 23 trades ouverts le 19 octobre UTC et déjà clôturés à cette vérification :
six gains, dix-sept pertes, -31,78 $, gain moyen 0,87 $, perte moyenne -2,1765 $.
Les régimes enregistrés donnent neuf trades TREND_UP (-8,61 $) et quatorze
RANGE_OR_TRANSITION (-23,17 $). Ce découpage descriptif ne suffit pas à choisir
un nouveau filtre : il mélange circonstances de marché et sélection des sorties.
Des entrées perdantes avaient des quotes fraîches ; un score directionnel ne
prouve donc ni une bonne espérance nette, ni une panne de connexion.

À 03:13:51 UTC / 04:13:51 Lagos : compte démo, solde 23 404,20 $, equity
23 403,77 $, réalisé depuis le lancement -26,95 $, flottant -0,43 $,
total -27,38 $. Deux positions de 0,01 lot avec SL, TP broker nul.
Capture indépendante : `data/monitoring/20261019T031351Z/latest.json`.
Les valeurs flottantes évoluent ensuite ; ce n'est pas un bilan définitif.

## Corrections finales et validation

Le watcher a rencontré une lecture de JSON pendant son écriture. Le collecteur
publie désormais `latest.json` avec le writer atomique existant, sans modifier
son module partagé protégé. Il retente aussi les lectures de statut verrouillées
ou momentanément partielles, avec limite de cinq essais ; une panne persistante
reste visible. Les observations brutes restent append-only.

Le graphique `performance.png` représente uniquement la fenêtre collectée,
la variation de P/L depuis sa propre baseline et les quotes fraîches ; les trous
de cotation ne sont pas interpolés. Les anciens statuts ne fabriquent aucun gain.

Validation ciblée : **113 tests et cinq sous-tests réussis**, rapport `targeted.xml`.
Il ne s'agit pas d'une validation de tous les tests historiques du projet.
Les hashes des 18 fichiers protégés d'Advisor 1 sont inchangés
(`advisor1_integrity.json`). Aucune modification des seuils d'entrée, des lots,
des SL ou de la politique de sortie n'est présentée comme profitable.

La priorité avant tout réel reste une validation hors échantillon avec coûts,
cohortes de versions et régimes séparés. Les pertes récentes ne permettent pas
de garantir davantage de gains que de pertes en retouchant les seuils en direct.
