# GoldHFT et adaptation hybride XAUUSD — 20 octobre 2026

## Conclusion

Construire un scalper hybride est faisable : une stratégie M1 prudente et une
branche rapide S30/ticks. Cela ne transforme pas notre connexion MT5 en HFT
institutionnel et ne démontre pas une amélioration de rentabilité. La branche
rapide ajoutée ici est exclusivement observationnelle, sans autorité d'ordre.
Le processus de trading déjà lancé n'a pas été redémarré.

## Ce que montrent réellement les documents fournis

Le texte TraderZO joint est un article général sur le HFT, pas une spécification
d'un robot BTC. Les cours crypto en tête ne définissent pas sa stratégie.
Ses idées d'infrastructure et de carnet ne suffisent pas à reconstruire un EA.

[GoldHFT MT5](https://www.mql5.com/en/market/product/109937) est déjà présenté
pour XAUUSD. Le vendeur annonce un petit réseau neuronal, une optimisation
historique et des performances de backtest spectaculaires. La page consultée
ne donne pas les features, labels, poids ou une validation indépendante
permettant de reproduire ces résultats. Une note utilisateur n'est pas un audit.

[Commentaires, page 1](https://www.mql5.com/en/market/product/109937/comments) :
l'auteur recommande l'optimisation dans le testeur et reconnaît en décembre 2023
que des paramètres surajustés échouent sur d'autres dates. Début 2025, il demande
des optimisations régulières et déconseille les changements improvisés de lots.
Cela justifie une validation chronologique séparée plutôt que choisir le meilleur
résultat sur un très court historique.

[Commentaires, page 2](https://www.mql5.com/en/market/product/109937/comments/page2) :
le vendeur mentionne explicitement une récupération martingale. Un acheteur
rapporte une perte importante effaçant les gains de sa démo ; ce témoignage
n'est pas une mesure vérifiée mais signale un risque à examiner. En août 2026,
l'auteur précise que son exemple n'est pas du vrai HFT.

Le [manuel HedgeRock lié par le vendeur](https://c.mql5.com/31/1363/HedgeRock3-76manual.txt)
décrit un système apparenté : filtres d'indicateurs, niveaux, temporisation,
lots de récupération, clôture de paniers, protection d'équité et réglages de spread.
Il ne prouve pas que chaque réglage ou mécanisme soit identique dans GoldHFT.
Certains modes court-circuitent les contrôles habituels SL/TP ; nous ne les copions
pas. Nous retenons la mesure des frais, l'espacement et les diagnostics explicites,
pas les lots destinés à rembourser les pertes ni un spread fictivement constant.

La [version 1.1](https://www.mql5.com/en/market/product/109937/updates)
ajoute des réglages de prise de profit dynamique et de temporisation des ordres.
Notre bot possède déjà des sorties dynamiques : cette annonce ne justifie pas
de remplacer sa gestion par un produit opaque.

## Limites techniques vérifiées

- [OnTick](https://www.mql5.com/en/docs/event_handlers/ontick) traite des événements
  en série ; un nouveau NewTick n'est pas ajouté si un précédent est déjà en
  file ou en traitement. Un EA natif n'est donc pas automatiquement une capture
  exhaustive de chaque tick ni une garantie de latence.
- [copy_ticks_range](https://www.mql5.com/en/docs/python_metatrader5/mt5copyticksrange_py)
  donne l'historique bid/ask et ses indicateurs ; utiliser des dates conscientes
  du fuseau. Notre adaptateur conserve la conversion explicite du broker déjà
  configurée, sans ajouter de décalage automatique supplémentaire.
- [Timeframes MT5](https://www.mql5.com/en/docs/constants/chartconstants/enum_timeframes) :
  S30 n'est pas une période native standard. Les trente secondes sont reconstruites
  depuis les ticks, pas obtenues en découpant artificiellement une bougie M1.
- Le [rapport SEC sur le trading algorithmique](https://www.sec.gov/file/algo_trading_report_2020pdf)
  traite d'une infrastructure et de risques de marché plus larges. Il ne valide
  pas une stratégie de micro-scalping XAUUSD chez notre broker.

## Adaptation implémentée

`services/research/gold_s30_shadow.py` conserve son rôle SHADOW_ONLY :

1. Trois S30 réellement clôturées et couverture de ticks continue ; aucune bougie
   manquante remplie artificiellement, aucun tick futur utilisé.
2. Ordre d'arrivée conservé pour des cotations distinctes partageant un timestamp.
   Les doublons exacts sont supprimés ; le nombre représente des observations de
   cotation, pas un volume de transactions ni un delta acheteur/vendeur réel.
3. Candidat de continuation : direction commune des S30, mouvement des six dernières
   secondes supérieur au spread, efficacité directionnelle au moins 0,65,
   couverture de cette fenêtre avec quatre observations minimum et trou maximal
   de deux secondes.
4. Rejet d'un spread supérieur à 1,5 fois la médiane des observations des 120 dernières
   secondes, d'un retournement ou d'une extension supérieure à une plage S30 récente.
5. Filtre exploratoire : plage médiane des trois S30 supérieure à trois fois le
   coût aller-retour estimé. Frais et slippage doivent être explicitement renseignés
   en équivalents de prix XAUUSD aller-retour. Inconnus : aucun candidat validé par
   ce filtre. Ce ratio est un écran de faisabilité, PAS une espérance de gain.
6. `execution_enabled=False`, probabilité calibrée et espérance absentes. Un ID par
   S30/direction permet de regrouper des observations répétées ; il ne remplace pas
   une future déduplication persistante des ordres.

Les seuils ci-dessus sont des hypothèses initiales, non optimisées et non validées
financièrement. Le mode rapide ne valide ni tendance M5, ni news, ni risque broker :
il ne constitue pas une stratégie exécutable autonome. Le pipeline principal
appelle déjà `s30_observation` dans son rapport ticks ; ces champs supplémentaires
seront inclus au prochain démarrage, sans modifier la permission d'entrer.

## Capture démo et tests

Capture indépendante en lecture seule :
`data/research/goldhft_20261020/fast_snapshot.json`, 07:57:50 heure de Lagos.
Historique disponible : 5 164 ticks conservés, âge du dernier environ 0,67 seconde.
Les trois S30 ne concordaient pas et le mouvement récent était bruité : WAIT,
aucun ordre. Les commissions/slippage n'étaient pas renseignés : écran de coût
indéterminé. Une capture ne mesure ni taux de réussite ni performance future.

14 tests ciblés réussis (nouveau module et tests S30/ajouts M1 existants).
Le runner d'audit vérifie compte démo et terminal connecté et ne soumet aucun ordre :

```powershell
& ".\.venv-audit\Scripts\python.exe" -B tools/audit_gold_fast_shadow.py --output data/research/goldhft_20261020/fast_snapshot.json
```

## Avant de rendre les deux branches exécutables

- Collecter séparément signaux M1 et candidats rapides avec timestamps, coûts
  effectifs, retards et chemins bid/ask. Ne pas compter chaque cycle comme un trade.
- Rejouer les entrées à la première cotation disponible APRÈS la décision avec
  latence ; achat à ask, vente à bid, sorties inverses. Ne pas recompter le spread
  déjà inclus dans ce P/L. Ajouter commissions et slippage réellement mesurés.
- Tester hors échantillon par sessions et régimes, avec sorties dynamiques
  identiques au bot ; mesurer aussi MAE/MFE, pertes extrêmes, drawdown et campagnes
  corrélées. Stress de coûts et retard. Un taux de réussite élevé seul ne suffit pas.
- Comparer M1 seul, rapide seul et hybride avec un unique arbitre d'ordres. Pas de
  double exécution native/Python, pas de dépassement du plafond global de cinq.
- Une éventuelle activation démo rapide nécessite une politique explicite distincte
  du 3/5/6 M1 existant ; elle ne doit pas supprimer ce contrôle implicitement.
- Garder 0,01 lot, SL broker obligatoire, sorties dynamiques sans plafond de TP,
  blocage news et aucune martingale. Définir un budget de perte de la campagne
  avant activation : le mode ANALYSIS et les arrêts de session actuellement
  désactivés ne constituent pas un plafond monétaire garanti.

## Lancements existants, uniquement si arrêtés

```powershell
cd "C:\Users\Gad Asopjio\Desktop\AI Trading Platform"
& ".\.venv-audit\Scripts\python.exe" -u -B ".\run_gold_consensus_bot.py" --mode demo --confirm I_ACCEPT_DEMO_SCALPING_RISK --max-minutes 0 --smc-policy observe
```

Dashboard avec Advisor 1, console séparée :

```powershell
& ".\.venv-audit\Scripts\python.exe" -u -B ".\run_gold_consensus_dashboard.py" --port 8767
```

Ces commandes n'activent pas d'ordres rapides S30. Ne pas créer d'instances doubles.
