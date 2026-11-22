# Aurum Quant AI — tableau de bord PC

## Lancement recommande: Gold Demo Desk

Double-cliquez sur [`Start Gold Demo.cmd`](<./Start Gold Demo.cmd>) ou sur
**Aurum Gold Demo Desk** sur le Bureau. Le lanceur ouvre le tableau de bord,
demarre/connecte MT5, refuse tout compte autre que DEMO, puis demande la phrase
locale de confirmation (saisie masquee) avant de lancer le bot Gold. Live reste
verrouille. Ctrl+C arrete le bot. L'EA natif reste un executeur distinct a
attacher manuellement au graphique XAUUSD; ne lancez pas les deux executeurs
ensemble sans avoir decide lequel tester.

Equivalent PowerShell depuis la racine du depot:

```powershell
python -B tools\launch_gold_demo.py
```

Le tableau de bord seul reste disponible avec `python -B
run_gold_unified_dashboard.py`. Il ne lance pas le bot Python ni les trades.

## Gold Unified Command Center

La seule interface de trading prise en charge regroupe l'EA natif, le bot de
consensus, Advisor 1, l'analyse manuelle et les rapports V-FINAL. Elle montre
les controles d'entree/sortie, les sources et leur fraicheur, les positions,
les comptes, les filtres de risque et les timings de tick/boucle disponibles.
Ces timings MT5 retail ne constituent pas une infrastructure HFT ni une
garantie de latence ou de performance.

```powershell
python -B run_gold_unified_dashboard.py
```

Adresse par défaut : `http://127.0.0.1:8777/`

Cette page lit les snapshots et rapports locaux existants. Elle ne calcule pas
de signaux et n'envoie pas directement d'ordres, mais le choix « MT5 demo »
écrit un fichier de configuration commun qui peut autoriser l'EA natif à
exécuter des ordres démo. L'EA conserve ses contrôles de compte démo et de
permissions MT5. Le bandeau distingue l'écriture du fichier de sa confirmation
par un snapshot EA récent; une erreur d'écriture est affichée. Un profil Live
nécessitera un compte MT5 distinct et une autorisation explicite.

L'analyse native reste fixe en M1. Le calendrier du tableau de bord
peut ajouter une plage UTC sans nouvelles entrées; la sélection actuelle
bloque les nouvelles entrées de 22:00 à 23:00 UTC. Cette restriction ne
remplace pas les filtres de session, d'actualité ou de risque propres à l'EA.

L'EA natif consulte aussi les horaires de session fournis par MT5. Il bloque
les nouvelles entrées et tente de fermer, pendant les cinq minutes precedant
chaque fermeture programmee, toutes les positions ouvertes sur le symbole exact
du graphique XAUUSD, y compris les positions manuelles et celles d'autres
strategies. Un suffixe de symbole different n'est pas cible sauf si l'EA est
attache a ce symbole exact. Les horaires sont ceux du serveur du courtier, pas
UTC; jours feries et changements non programmes peuvent differer. La fermeture
est une tentative, pas une garantie: connexion, cotations, autorisations ou
rejets du courtier peuvent l'empecher. Le dashboard affiche le calendrier connu,
le compte a rebours, le nombre de positions restantes et l'etat des tentatives.
L'horaire attendu du vendredi 22:00 au dimanche 23:00 n'est pas code en dur:
les heures XAUUSD varient selon le courtier, son fuseau serveur et les changements
saisonniers. L'EA lit les sessions du symbole dans MT5 ([`SymbolInfoSessionTrade`](https://www.mql5.com/en/docs/marketinformation/symbolinfosessiontrade));
verifiez les heures visibles apres connexion au compte demo voulu. Le statut
affiche les heures du serveur du courtier, pas necessairement UTC.
