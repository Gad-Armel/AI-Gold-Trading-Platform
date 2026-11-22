# Entrées rapides XAUUSD : revue complémentaire du 19 octobre 2026

## Conclusion opérationnelle

La vitesse d'exécution et la qualité du signal sont deux axes distincts. Accélérer
une entrée après trois bougies ne démontre pas que le mouvement restant couvre
le spread, les commissions et le slippage. La priorité est de mesurer la poursuite
de mouvement et le coût avant de changer la règle 3/5/6 ou d'activer S30.
Les propositions suivantes sont des hypothèses, pas des avantages démontrés.

## Sources supplémentaires et limites

- [N30 Gold Reversion](https://github.com/n30dyn4m1c/gold-pro-scalper), README
  consulté : l'auteur décrit des versions séparées de retour à la moyenne et de
  cassure, un filtrage par coût et un problème de bruit entre simulation OHLC et
  ticks. Aucun résultat de compte n'a été vérifié ici. Ses risques très élevés
  sur petits comptes et ses TP fixes ne sont pas transposés à notre projet.
- [Documentation officielle du testeur MT5](https://www.mql5.com/en/docs/runtime/testing) :
  les modes OHLC et ticks n'ont pas la même résolution. Une courbe avantageuse
  sur seulement quatre prix par minute ne valide pas un scalper intraminute.
  Les ticks générés ne doivent pas être présentés comme des ticks historiques réels.
- [API officielle des ticks](https://www.mql5.com/en/docs/python_metatrader5/mt5copyticksfrom_py) :
  disponibilité bid/ask et règles de temps UTC. Pour notre broker, conserver aussi
  la normalisation d'horloge déjà présente et tester les doublons et trous.
- [TimeSeriesSplit](https://scikit-learn.org/stable/modules/generated/sklearn.model_selection.TimeSeriesSplit.html) :
  découpage chronologique et intervalle gap disponibles. Un gap générique ne
  remplace pas la purge explicite des labels dont les horizons se chevauchent.

## Trois familles d'entrées à comparer séparément

1. **Continuation immédiate** : tendance confirmée, clôtures directionnelles,
   faible rejet et prix exécutable encore proche de la clôture. Mesurer si entrer
   plus tard augmente surtout l'excursion défavorable. Conserver la référence 3/5/6.
2. **Cassure puis retest** : niveau connu avant la cassure, retour au niveau puis
   reprise observée, expiration du candidat si pas de reprise. Le retest peut
   réduire le prix payé mais manquer les tendances sans retour : comparer ces
   occasions manquées, pas seulement les trades finalement pris.
3. **Pullback en tendance** : repli puis reprise directionnelle, sans mélanger
   avec le retour à la moyenne en range. Les détecteurs de pullback, sweep et
   breakout existent déjà dans gold_scalp_setups.py, en observation seulement.

## Modification réalisée

gold_m1_quality.sequence_quality expose quatre mesures supplémentaires dans le
bloc de diagnostic déjà journalisé :

- close_path_efficiency : déplacement net / chemin des clôtures, pas le chemin
  intrabougie réel ; ne mesure pas à lui seul une accélération ou une probabilité.
- distance_to_sequence_extreme_atr : distance directionnelle entre prix exécutable
  et extrême historique de la séquence. Négative si le prix dépasse cet extrême.
- remaining_sequence_range_in_spreads : cette même distance en spreads courants ;
  ce n'est ni une cible future, ni une espérance de gain, ni un coût complet.
- last_body_atr : corps directionnel de la dernière bougie rapporté à l'ATR fourni.

Les mesures n'utilisent que les bougies clôturées et le bid/ask disponibles.
Elles ne changent aucun seuil ni aucune autorisation d'ordre. Le processus déjà
en cours n'est pas redémarré : les nouveaux champs seront chargés au prochain
démarrage contrôlé, et ne sont donc pas annoncés comme déjà collectés en direct.

## Protocole avant activation stratégique

Geler une version, comparer un seul changement à la fois et regrouper les tickets
d'une même campagne. Rejouer bid/ask, délai, coûts et sorties identiques ; modifier
une entrée peut modifier les entrées suivantes. Mesurer espérance nette, drawdown,
excursions favorable/défavorable, taux de remplissage et gains manqués.
Séparer développement et période prospective intacte ; publier les essais négatifs.
Ne pas sélectionner un seuil sur les treize clôtures précédemment examinées.

Démo, 0,01 lot, cinq positions maximum, SL obligatoire et absence de TP fixe
restent inchangés. Aucun changement d'Advisor 1. Aucun gain garanti.

Validation : 21 tests passent sur qualité M1, paliers/S30 et fraîcheur des bougies.
