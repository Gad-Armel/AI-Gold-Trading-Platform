# Comparaison de scalpers et adaptations au bot

Recherche et déploiement du 19 octobre 2026. Quatre EA commerciaux et deux
frameworks techniques ont été examinés. Aucun logiciel payant n'a été acheté,
téléchargé ou exécuté. Les fiches vendeurs décrivent des mécanismes revendiqués,
pas des performances indépendamment vérifiées. Ce travail ne classe pas leur
rentabilité et ne transpose pas leurs captures de backtest à notre compte.

## Synthèse des sources primaires

| Système et source | Fonctionnement documenté ou revendiqué | Ce que nous retenons / refusons |
| --- | --- | --- |
| [Gold Neural Scalper](https://www.mql5.com/en/market/product/182927) | Le vendeur décrit des filtres multi-horizons et de volatilité, des breakouts, des stops et cibles, sans grille ni martingale. Les poids ne sont pas publiés. | Retenir le contrôle de qualité des contextes. Ne pas reprendre les paramètres SL/TP ni supposer qu'un cadre « neural-style » est un ML entraîné ou calibré. |
| [Neural Network Swing Scalper Price Action](https://www.mql5.com/en/market/product/174979) | Le vendeur décrit un réseau 20–16–8–2, des filtres spread/news, une vérification de marge et la distinction netting/hedging. Les poids initiaux sont présentés comme issus de règles manuelles ; leur remplacement par un entraînement est proposé. | Retenir la validation à l'exécution et la traçabilité de la confiance. Softmax ne démontre pas la calibration. Notre sécurité hedging/marge existe déjà ; aucune conversion en netting. |
| [Gold Mine AI](https://www.mql5.com/en/market/product/158649) | La fiche expose des modes scalping M1/M5 et swing, des EMA/Bollinger/RSI, filtres ATR/spread/session et sorties temporelles. Le nom AI ne fournit pas de preuve d'entraînement. | Retenir le besoin de distinguer régimes et durées. Ne pas ajouter le swing, un TP fixe ou un créneau horaire arbitraire à notre méthode. |
| [Omega Gold Pro](https://www.mql5.com/en/market/product/168039) | La page actuelle précise « rule-based » : moteur tendance et moteur scalping, contexte multi-timeframe, ATR, trailing et pyramidage optionnel. Ce n'est pas une preuve de modèle IA. | Le pyramidage compatible est déjà progressif et réservé aux positions bénéficiaires chez nous. Pas de copie de moteur propriétaire ni d'augmentation de lot. |
| [FreqAI : configuration](https://www.freqtrade.io/en/stable/freqai-configuration/) | Framework ML de Freqtrade, pas un scalper XAUUSD clé en main. Il distingue des entrées hors distribution et des modèles expirés par des états de confiance. | Adapter l'idée d'expiration aux vraies données alimentant notre signal, plutôt qu'à l'heure du rapport. Ne pas assimiler distance statistique et probabilité de gain. |
| [Hummingbot : Position Executor](https://hummingbot.org/strategies/v2-strategies/executors/positionexecutor/) | Framework d'exécution crypto, pas nécessairement IA. Gestion du cycle de position avec barrières prix/temps et trailing. | Le découplage signal/exécution et les protections sont utiles. Ne pas introduire la cible fixe incompatible avec les sorties dynamiques demandées. Une nouvelle sortie temporelle exige un replay avant activation. |

Le contenu comparé correspond au produit nommé, non aux autres produits et
publicités présents plus bas sur les pages Marketplace. Les notes, téléchargements,
prix et noms commerciaux ne servent pas de preuve de performance.

## Pourquoi l'adaptation retenue est utile

Le moteur principal met en cache les signaux Advisor 1 sur bougies clôturées,
mais reconstruit l'heure du rapport et sa validité à chaque passage. Cela permet
de réancrer les niveaux aux prix actuels ; en revanche, **la fraîcheur du rapport
ne certifie pas celle des M5/M15 sous-jacentes**. Le contrôle existant du tick
et celui de la dernière M1 ne suffisaient pas à prouver cette propriété.
Il s'agit d'une faiblesse reproduite par tests, pas de la preuve que les pertes
historiques aient été causées par un flux M5/M15 bloqué.

### Adaptation active : expiration des entrées réelles

`gold_candle_input_health.py` vérifie les dernières clôtures M1/M5/M15 :
- normalisation avec l'offset broker configuré ;
- refus des données absentes, impossibles, dupliquées ou datées dans le futur ;
- séparation entre une vraie clôture et la bougie encore en formation ;
- fraîcheur maximale d'une période plus cinq secondes de grâce de rafraîchissement.

Quand un contexte requis est périmé, le rapport SCALP principal devient inutilisable
pour le consensus. Le nouveau timestamp du cache ne peut plus autoriser une entrée
sur cette seule base. Une donnée manquante n'est pas un vote neutre et ne devient
pas une confirmation inverse. Le garde-fou ne modifie ni Advisor 1, ni ses scores,
ni les stops ou la logique de sorties. Les protections de quotes continuent.

La santé des bougies apparaît dans la décision et le journal d'entrée. Le wrapper
ne modifie pas l'objet caché original ; une source rétablie peut donc récupérer
son statut normal, sans conserver un blocage périmé.

### Adaptation d'audit : stabilité de l'historique et parité du cache

Les outils [lookahead-analysis](https://www.freqtrade.io/en/stable/lookahead-analysis/)
et [recursive-analysis](https://www.freqtrade.io/en/stable/recursive-analysis/)
de Freqtrade documentent deux pièges : utiliser des informations futures et
changer les indicateurs en changeant la profondeur d'historique. Leur existence
ne garantit pas qu'une stratégie soit profitable après validation.

Nous avons ajouté `tools/audit_gold_signal_stability.py`, exécuté en lecture seule
sur le terminal démo : comparaison du cache avec Advisor 1 et des fenêtres de
chauffe plafonnées à 64/128/256 lignes. Aucun signal n'est retuné par cet outil.
Les tests de bougies futures et de causalité du projet sont également conservés.
Ce n'est ni l'exécution de Freqtrade sur MT5, ni un audit exhaustif de lookahead.

À 08:48:56 UTC / 09:48:56 Lagos : les douze vérifications cache/original passent
(biais, score, niveaux et votes pour les trois horizons). Au plafond 64, le score
SCALP varie de -0,04 point, sans inversion de biais ; le score SWING de +2,15.
Ces mesures ne justifient pas de raccourcir l'historique ou de modifier les seuils.
Les historiques réels contiennent 180/160/140/120/100 lignes selon le timeframe :
les plafonds 128/256 sont tronqués à ce qui existe, pas des échantillons garantis
de cette longueur. Aucun résultat de rendement ne découle de ce contrôle ponctuel.

## Ce qui reste déjà présent, ou non promu

- Déjà présent : démo obligatoire, checks marge/volume/stops, spread, news,
  fraîcheur du tick, paliers 3/5/6 et SL obligatoire, cinq positions maximum,
  lot 0,01, sorties dynamiques et suivi du profit.
- Non repris : martingale, grille de récupération, multiplication des lots,
  TP fixe, garantie de rendement, copies de poids opaques ou biais acheteur permanent.
- Non activé : S30 comme exécuteur, filtre appris hors distribution, nouvelle
  limite horaire, modification des sorties ou des seuils ATR. Ces variantes
  nécessitent un test chronologique et une validation prospective sur notre broker.
- Le coupe-circuit journalier désactivé explicitement par l'utilisateur n'est
  pas réactivé en copiant les limites d'un autre produit.

## Déploiement et vérification

Redémarrage ciblé du principal à 08:49:52 UTC / 09:49:52 Lagos, après vérification
du compte démo et du SL de la position ouverte. État de sorties RESTORED.
À 08:50:29 UTC, entrées alimentées par des M1/M5/M15 fraîches, une position SELL
de 0,01 lot avec SL et TP nul. Le deuxième ticket exige toujours cinq M1 et
est alors bloqué par l'absence de confirmation. Le S30 reste sans exécution.
Ce relevé ne prouve pas une amélioration du P/L.

164 tests et cinq sous-tests ciblés passent : expiration réelle, futur interdit,
propagation du refus à la politique de consensus, non-mutation du cache,
conservation de la télémétrie, stabilité et protections existantes.
Les 18 fichiers protégés d'Advisor 1 sont inchangés. Pas de validation revendiquée
de toute la suite historique.

Preuves dans `data/research/web_scalpers_20261019` : `signal_stability.json`,
`tests.xml` et `runtime.json`. Logs : `logs/monitored-main-20261019T084952Z.*`.
Collecte après déploiement : `data/monitoring/20261019T085018Z`.

**Bilan : mécanismes de fiabilité adaptés et testés, pas de gain de performance
financière démontré.** La prochaine comparaison utile porte sur l'espérance nette,
les coûts et le drawdown des seules entrées postérieures à cette version, sans
réattribuer des positions préexistantes ni sélectionner le meilleur seuil a posteriori.
