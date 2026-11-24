# Aurum Quant AI — démarrage PC Windows

1. Installez Python et MetaTrader 5, puis ouvrez MT5 sur un compte **DEMO**.
2. Double-cliquez sur **Aurum Gold Demo Desk** sur le Bureau, ou sur
   `Start Gold Demo.cmd` dans ce dossier.
3. Le tableau de bord unifié s'ouvre avant le contrôle du compte. Le bot ne
   démarre qu'après la vérification DEMO et la saisie masquée de la phrase de
   confirmation locale. Laissez la fenêtre ouverte pendant l'exécution.

Pour ouvrir uniquement le tableau de bord, lancez
`python -B run_gold_unified_dashboard.py` depuis ce dossier ou utilisez
`tools/open_gold_unified_dashboard.ps1`.

L'interface unique est `http://127.0.0.1:8777/`. Les autres anciens lanceurs
de tableaux de bord et le prototype Expo à données d'exemple ont été retirés.
Le mode Live est verrouillé; l'EA natif reste un exécuteur distinct et ne doit
pas être lancé en parallèle du bot Python sans plan d'essai DEMO explicite.

Voir le [README](./README.md) et le [runbook DEMO](./docs/DEMO_RUNBOOK.md) pour
les détails de sécurité et de validation.
