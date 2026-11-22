# Validation du mode rapide — 20 octobre 2026

## Mesures réalisées

Rapport : `data/research/goldhft_20261020/validation.json`.
Capture à 08:02 heure de Lagos : deux heures demandées, 40 225 cotations.
Audit en lecture seule sur compte démo USD ; aucun ordre envoyé ou modifié.

288 positions SCALP complètes ont été rapprochées avec leurs deux deals réels et
les prix demandés du journal. Les exécutions partielles, non rapprochées, les
positions avec swap et les volumes différents de 0,01 sont exclus.
La conversion prix/P&L est vérifiée contre le contrat et le profit broker.

- Frais aller-retour observés au percentile 95 : 0 en équivalent prix.
  Il s'agit d'une mesure de ce compte démo, pas d'une hypothèse universelle.
- Slippage défavorable aller-retour au percentile 95 : environ 0,18 en prix XAUUSD.
- Durée de l'appel order_send au percentile 95 : environ 352 ms ; ce n'est ni le
  ping réseau ni toute la latence décisionnelle.

## Écran comparatif initial

Une seconde de délai minimal, achat à ask/vente à bid, liquidation à la cotation
opposée après 60 secondes, puis frais/slippage estimés soustraits une seule fois.
Chaque configuration de bougie/direction est dédupliquée.

- S30 rapide : **0 candidat** passant tous les filtres.
- Benchmark « trois M1 de même direction » : 23 observations, 9 positives,
  somme nette hypothétique −15,08 en unités de prix XAUUSD.

Ce benchmark n'est PAS le bot complet : ni Advisor 1, ni son contrôle d'entrée,
ni ses sorties dynamiques ne sont rejoués. Les observations peuvent se chevaucher ;
la somme n'est donc pas le profit d'un portefeuille réellement exécutable. Le
calibrage des coûts utilise une période historique pouvant recouvrir le test :
ce n'est pas une validation hors échantillon. Le résultat ne prouve pas non plus
qu'une autre configuration S30 serait rentable.

## Décision

**Ne pas activer les ordres rapides.** Les coûts ont maintenant une estimation
mesurée, mais aucune preuve positive ne justifie de contourner le 3/5/6 M1.
Ne pas abaisser les filtres simplement pour produire davantage d'ordres.
Le bot courant n'est ni redémarré ni modifié dans ses permissions d'exécution.

Le nouveau programme `tools/validate_gold_fast.py` rend l'audit reproductible :

```powershell
cd "C:\Users\Gad Asopjio\Desktop\AI Trading Platform"
& ".\.venv-audit\Scripts\python.exe" -B tools/validate_gold_fast.py --hours 2 --output data/research/goldhft_20261020/validation.json
```

21 tests ciblés passent : rapprochement des coûts, sens du slippage, coûts inconnus,
fills partiels, conversion de contrat, bougies closes, couverture, déduplication,
entrée après décision et absence d'autorité d'ordre.
Les 18 fichiers protégés d'Advisor 1 restent identiques à leur référence.

Pour rendre le mode rapide exécutable, il reste à obtenir des candidats sur une
période représentative, conserver des coûts calibrés exclusivement avant le test,
rejouer les sorties et protections réelles, puis évaluer hors échantillon le risque
et les résultats nets avec plafond global de cinq positions. Cette étape ne peut
pas être remplacée honnêtement par un simple changement d'option.
