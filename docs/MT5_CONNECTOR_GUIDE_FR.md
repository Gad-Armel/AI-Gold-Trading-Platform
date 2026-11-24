# Créer un connecteur MT5 — guide de mise en route

Ce guide décrit le connecteur à développer sur un PC Windows. Il ne connecte pas encore votre compte : le projet actuel n'a pas de service de liaison installé.

## Architecture recommandée pour un premier prototype

Pour le compte de démonstration, démarrez par un seul PC Windows : MT5 installé et connecté au compte démo du courtier, un petit service local Python, puis un client local séparé pour piloter/observer. Le terminal MT5 et le service doivent rester sur le même ordinateur. N'exposez jamais le port du service à Internet et ne mettez jamais le mot de passe MT5 ou une clé dans le tableau de bord web/mobile.

Le paquet officiel MetaTrader5 pour Python communique avec le terminal MT5 local. La documentation officielle est ici : https://www.mql5.com/en/docs/python_metatrader5 . Vérifiez les prérequis et fonctions supportés par votre version de Windows, Python, terminal et courtier avant l'installation.

## Kit complet de départ

Le dossier d'exemple avec l'arborescence et le code lecture seule est dans [`MT5_CONNECTOR_PROJECT_FR.md`](./MT5_CONNECTOR_PROJECT_FR.md). Recréez ses fichiers dans un dossier `mt5-connector` sur votre ordinateur Windows, puis suivez « Lancement dans VS Code / PowerShell » dans ce document. Le service démarre sur `127.0.0.1:8787` et expose uniquement des routes GET de statut, compte, symboles et positions.

Avant de créer ce dossier : installez MT5 depuis votre courtier, ouvrez-le et connectez-vous manuellement à un compte démo. Le paquet Python officiel communique avec le terminal local déjà ouvert; ne copiez pas votre mot de passe dans le code. Vérifiez les prérequis de version de Python sur la documentation MetaQuotes : https://www.mql5.com/en/docs/python_metatrader5 .

Ce kit est une base de code à recopier, pas une archive ZIP jointe ni un connecteur déjà connecté à votre compte.

## Important sur le tableau de bord

Un service lié à `127.0.0.1` n'est pas accessible depuis l'application Blink publiée ni depuis votre téléphone : « localhost » désigne l'appareil qui ouvre la page. Pour que PC et mobile communiquent à distance, il faut un service serveur authentifié, une connexion chiffrée, des sessions utilisateurs et une liaison sécurisée au PC MT5 (par exemple via une connexion sortante persistante). Ce composant n'est pas inclus dans ce projet et ne peut pas être remplacé sans risque par une clé ou un mot de passe dans le code du navigateur.

Ne transférez jamais les identifiants du compte MT5 dans un formulaire web, chat, dépôt GitHub ou fichier `.env` partagé. Si vous mettez en place un pont distant, il doit commencer en lecture seule et ne permettre des ordres de démo qu'après validation indépendante des contrôles de risque.
