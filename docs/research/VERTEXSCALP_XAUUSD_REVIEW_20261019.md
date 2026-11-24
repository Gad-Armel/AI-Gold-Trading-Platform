# VertexScalp et scalpers comparables : adaptation XAUUSD

Revue du 19 octobre 2026. Recherche publique, sans achat, inscription, accès à un
compte tiers, exécution de logiciel externe ou contact commercial.

## 1. Périmètre réellement exploré

Le lecteur web ne pouvait pas ouvrir VertexScalp. La récupération HTTP directe a
réussi : accueil anglais et français, /buy, les deux variantes produit, scripts
publics de page, de langue, d'avis et d'achat. robots.txt et sitemap.xml ont répondu
404. Les ancres #what, #why, #pricing et #faq sont des sections du même accueil.
La FAQ complète a été lue dans le HTML, pas seulement ses questions repliées.
Les scripts ont été lus comme texte, pas exécutés.

Les liens Telegram publics Vertexscalp et Trader_Marcuss ont été consultés : texte
de l'aperçu, pas audit des fichiers, vidéos ou pièces jointes. Aucun groupe privé
n'a été rejoint ; le lien d'invitation privé n'a pas été utilisé. WhatsApp n'a pas
été contacté. Les fichiers reçus après paiement ne sont pas disponibles.
Les recherches de noms exacts n'ont pas permis d'établir une documentation
indépendante attribuable à ces deux produits. Ce résultat de recherche ne prouve
ni l'absence d'autres documents, ni une fraude.

Copies de travail locales : data/research/vertexscalp_20261019/. Les pages d'achat
ont été consultées en GET seulement ; aucune commande, transaction ou demande
d'accès n'a été envoyée.

## 2. Ce que VertexScalp permet réellement de savoir

[Accueil et FAQ](https://www.vertexscalp.com/), [achat](https://www.vertexscalp.com/buy).
Le vendeur présente Mighty Scalper EA et Glory Profits Scalper Bot, à achat unique,
compatibles avec plusieurs courtiers et utilisant du hedging. Il décrit une
automatisation des règles, mais ne publie pas la formule d'entrée, le timeframe,
les seuils, le modèle entraîné, ses données ou la méthode de validation.
La spécialisation XAUUSD n'est pas établie par les pages examinées.

La FAQ anglaise et la réponse servie en français commencent par « Yes! » à la
question de garantie de gains ; le texte général reconnaît pourtant le risque.
C'est une incohérence de présentation, pas une preuve de performance.
Les avis sont fournis dans les données de page et affichés par rotation ; certains
identifiants commencent par sample, avec sample=false. Cela ne permet pas de
conclure qu'ils sont inventés ou authentifiés.

L'aperçu [Telegram](https://t.me/s/Vertexscalp) comporte surtout des annonces de
livraison. Une livraison ne valide pas une stratégie. Aucun historique de compte
indépendant exploitable n'a été établi ici. La mention de fonctionnement mobile
ne précise pas où le moteur tourne réellement. Bilan : offre commerciale lisible,
stratégie insuffisamment documentée pour la reproduire honnêtement.

## 3. Attention aux homonymes

[Mighty Scalper sur MQL5](https://www.mql5.com/en/market/product/10859) est présenté
comme un EA MT4 d'Ahmet Metin Yilmaz, version 1.10, publié en 2021 : breakout,
clôtures partielles et durée limitée, réglages EURUSD M15/M30. La description dit
ne pas utiliser martingale ou hedging, contrairement à l'annonce VertexScalp.
Sans auteur, licence ou fichier commun vérifiable, ce n'est PAS la preuve qu'il
s'agit du même robot. Aucun résultat de Mighty Gold ou Glory Champion trouvé
par proximité de nom n'est attribué à VertexScalp.

## 4. Comparables techniques : idées et limites

### ScalperX

[Site](https://scalperx.gold/), [aide](https://scalperx.gold/help).
Le vendeur décrit une spécialisation or, plusieurs stratégies, SL prédéfini,
absence de grid/martingale et objectif fixe 2:1. L'aide expose des refus liés au
spread, au régime et aux news. Le lien de suivi mène vers un compte Myfxbook
identifié, mais cette revue ne certifie pas son historique, son contrôle ou son
drawdown : l'ouverture du compte
[Myfxbook](https://www.myfxbook.com/members/goldscalperx/88451364/12088967)
a répondu 403. Les chiffres dynamiques n'étaient pas disponibles dans le lecteur.
La page principale affiche M5, l'aide demande M1 : vérifier la version exacte
avant de transposer. À retenir : expliquer chaque refus et mesurer les coûts.
À écarter chez nous : TP fixe et dépendance obligatoire à une clé distante.

### Gold Scalpers

[Description du vendeur](https://goldscalpers.com/).
M5, Slope Direction Line/EMA50 et confirmation ZeroLag MACD, bougies clôturées,
stop de structure, break-even, filtres de spread/news et vérification au lancement.
Le vendeur distingue son ancien backtest M15 du produit M5 et indique que les
chiffres de panneau sont illustratifs. Il dit aussi que son pyramiding est livré
désactivé après ses propres essais : ce n'est pas une validation indépendante.
À retenir : tester séparément chaque ticket ajouté, garder la traçabilité de
version et vérifier les préconditions. Ne pas copier les indicateurs pour leur
seul nom, les TP fixes ou l'entrée automatique au simple démarrage. Un stop déplacé
au break-even ne garantit pas un résultat net positif en présence de coûts/gaps.

### GOLD-HFT-SCALPER, RobertN1D

[README technique](https://github.com/RobertN1D/XAUUSD-GOLD-SCALPER-MT5-EA-FREE-SOURCE-CODE).
Documentation détaillée de candidats distincts : impulsion, pullback, opening
range, reprise/rejet VWAP, cassure de niveau. Classement avec pénalité de spread,
gestion rapide et raisons de sortie journalisées. Il se décrit explicitement
comme algorithmique, sans ML. Pas d'audit intégral du code ni de performance ici.
À retenir : séparer les familles d'entrées et comparer leurs résultats nets.
À écarter : recopier les scores comme probabilités ou les seuils comme optimums.
La profondeur de marché d'un CFD broker ne constitue pas le carnet global de l'or.

### Singularity / EA_SCALPER_XAUUSD

[Fichier principal examiné](https://github.com/francomascareloai/EA_SCALPER_XAUUSD/blob/main/MQL5/Experts/EA_SCALPER_XAUUSD.mq5).
Lecture ciblée des paramètres et du chemin OnTick, pas audit de toutes dépendances.
Des garde-fous sont présents, mais aussi des entrées de récupération optionnelles.
Dans le chemin observé, le plafond de spread est élargi dans le testeur ; un retour
anticipé sur spread arrive avant ManageAllPositions. Cela peut affecter la parité
test/direct et cette gestion de position ; d'autres protections existent et n'ont
pas été intégralement auditées. Conclusion : ne pas importer un dépôt sur son
marketing. Chez nous, conserver les protections des positions indépendamment des
conditions d'ouverture, et tester leur ordre d'exécution.

### XAUUSD Aggressive Scalper

[Guide de l'auteur](https://github.com/Laxury-H/XAUUSD-Aggressive-Scalper/blob/main/AggressiveScalper/UserGuide_EN.md).
Exemple transparent : stochastique rapide M1, spread, limite de positions, SL et
TP fixes. Le guide annonce des distances de TP inférieures au SL initial. Ce
rapport seul ne donne pas l'espérance réelle avec trailing et coûts ; il illustre
pourquoi le taux de réussite ne suffit pas. Aucun résultat reproduit ici.
Ne pas copier ses lots, conversions pip/point ou conseils de relèvement du spread.

## 5. Adaptation au projet : XAUUSD seulement

Le bot principal utilise déjà settings.SYMBOL=XAUUSD. Des données de devises,
indices et autres métaux peuvent rester du contexte ; cela n'autorise aucun ordre
sur ces instruments. Advisor 1 et ses dépendances protégées restent inchangés.

| Priorité | Hypothèse à vérifier sur notre broker | Adoption |
| --- | --- | --- |
| P0 | Coût réel et distance encore exploitable avant entrée | Diagnostics existants, aucun seuil inventé |
| P0 | Nouvelle entrée après cassure/retest plutôt que poursuite tardive | Nouveau détecteur SHADOW, sans ordre |
| P1 | Pullback et continuation ont des résultats différents selon le régime | Comparaison séparée des détecteurs existants |
| P1 | Tickets 2 à 5 amplifient parfois le même mauvais timing | Analyse par campagne et contribution marginale |
| P1 | Latence/fraîcheur explique l'écart signal/remplissage | Mesurer distributions et refus, pas seulement moyenne |
| P2 | S30 améliore le timing sans multiplier le bruit | Observation seulement, référence M1 conservée |

### Ajout concret : m1_retest_shadow

Nouveau module gold_retest_shadow.py, connecté au diagnostic SCALP du principal
et au contexte d'ouverture journalisé. Il compare une clôture de cassure avec
l'extrême des 20 bougies PRÉCÉDENTES, attend une autre bougie clôturée retestant
le niveau puis clôturant dans le sens de reprise. Un franchissement contraire
invalide, une attente supérieure à trois bougies expire. La tolérance exploratoire
vaut 0,1 fois la moyenne des true ranges précédant la cassure : elle est figée
historiquement, pas recalculée avec la volatilité ultérieure. Ces valeurs servent
à définir un candidat reproductible, PAS un optimum démontré.

États distincts : NO_CANDIDATE, WAIT_RETEST, CONFIRMED_NOW, ALREADY_CONFIRMED,
INVALIDATED et EXPIRED. Un signal déjà confirmé n'est pas présenté comme nouveau.
Les données incomplètes, périmées, dupliquées ou discontinues sont indisponibles.
execution_enabled reste False. Ce détecteur n'affirme ni la présence d'une
liquidité institutionnelle ni un avantage statistique.

Ce candidat demande une bougie de repli : il peut donc être incompatible avec
trois corps consécutifs directionnels. Les deux règles ne sont pas empilées comme
obligations. Le retest sert d'alternative à comparer à la référence 3/5/6 ; aucune
dérogation aux paliers n'est activée.

Le principal en cours n'a PAS été redémarré. Ce nouveau diagnostic sera chargé
au prochain démarrage contrôlé. Aucun changement de décision, lots, SL, TP,
positions ouvertes ou mode réel n'est réalisé par cette recherche.

## 6. Validation avant toute promotion

[Testeur MT5](https://www.mql5.com/en/docs/runtime/testing) : une simulation OHLC
ne suffit pas à qualifier un comportement intraminute. Utiliser les ticks bid/ask
du broker, distinguer ticks réels et générés, simuler délais et rejets.
[Propriétés du symbole](https://www.mql5.com/en/docs/constants/environment_state/marketinfoconstants) :
vérifier point, tick size, contrat, volumes, stops/freeze et profondeur disponible.
[order_calc_profit](https://www.mql5.com/en/docs/python_metatrader5/mt5ordercalcprofit_py)
permet une estimation de résultat dans la devise du compte : ne pas généraliser
une conversion monétaire trouvée sur un site à tous les courtiers.

Geler d'abord la définition des candidats et la version des sorties. Comparer
chronologiquement les entrées immédiates, retests et pullbacks ; conserver aussi
les occasions refusées. Pas de suppression a posteriori des faux signaux ni de
choix de seuil sur le petit échantillon déjà utilisé. Rejouer le système complet :
changer une entrée modifie les positions et ajouts ultérieurs.

Mesures : espérance NETTE, drawdown d'equity incluant positions ouvertes, excursions
favorables/défavorables, remplissages, fréquence, coûts, attribution par setup,
session et campagne. Un backtest meilleur n'autorise pas automatiquement un
changement actif : validation prospective démo et comparaison de versions d'abord.

## 7. Vérifications effectuées

74 tests passent, plus 5 sous-tests, sur retest, géométrie M1, paliers/S30,
fraîcheur, broker démo et fiabilité du flux. Ce n'est pas un backtest de rentabilité.
Les 18 fichiers protégés d'Advisor 1 correspondent à leurs empreintes de référence.
Résultats : data/research/vertexscalp_20261019/tests.xml et advisor1_integrity.json.

Conclusion : VertexScalp n'apporte pas assez de détails pour copier sa stratégie.
Les améliorations défendables sont la sélection du timing, la mesure des coûts,
la séparation des setups et la validation des ajouts, exclusivement sur XAUUSD.
