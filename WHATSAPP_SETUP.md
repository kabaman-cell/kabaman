# Connexion WhatsApp de KABAMAN

La page `whatsapp.html` ajoute une boîte de réception réservée à l’administrateur. Elle affiche les conversations reçues, les messages texte et les types de pièces jointes, et permet d’envoyer une réponse texte depuis le tableau de bord.

## Ce qu’il faut avant la mise en service

Le site GitHub Pages sert les fichiers statiques uniquement. Le serveur Python de `server.py` doit aussi être hébergé publiquement avec HTTPS et un dossier de données persistant. Le serveur hébergé doit servir ce dépôt complet, pour que le site et l’API utilisent la même adresse.

Le numéro WhatsApp Business doit être relié à la WhatsApp Business Platform (Cloud API) dans Meta, puis son webhook doit être configuré. Meta indique que les petites entreprises peuvent utiliser l’application WhatsApp Business et la plateforme simultanément, sous réserve de l’éligibilité et du parcours de connexion Meta : [informations Meta](https://about.fb.com/news/2025/09/bringing-new-tools-to-help-businesses-boost-engagement-customer-support-and-discoverability/).

## Variables d’environnement du serveur

Configure ces valeurs dans les paramètres privés de l’hébergeur. Ne les colle pas dans le code ni dans une conversation :

- `KABAMAN_ADMIN_PASSWORD` : mot de passe d’accès administrateur.
- `KABAMAN_HOST` : utiliser `0.0.0.0` sur un hébergeur de serveurs.
- `KABAMAN_SECURE_COOKIES` : utiliser `1` quand le site est servi en HTTPS.
- `KABAMAN_DATA_DIR` : dossier persistant qui contient la base SQLite et les pièces d’identité déjà téléversées.
- `WHATSAPP_VERIFY_TOKEN` : secret choisi pour vérifier l’abonnement webhook.
- `WHATSAPP_APP_SECRET` : secret de l’application Meta, utilisé pour vérifier la signature des événements.
- `WHATSAPP_ACCESS_TOKEN` : jeton d’accès de la WhatsApp Business Platform.
- `WHATSAPP_PHONE_NUMBER_ID` : identifiant du numéro dans Meta.
- `WHATSAPP_GRAPH_VERSION` : version de l’API Graph en vigueur dans Meta.
- `PORT` : fourni par la plupart des hébergeurs.

Le serveur conserve les conversations dans SQLite. Il faut que `KABAMAN_DATA_DIR` soit persistant entre les redémarrages.

## Configuration du webhook Meta

1. Créer ou ouvrir une application Meta pour le compte professionnel KABAMAN et ajouter WhatsApp.
2. Ajouter ou connecter le numéro WhatsApp Business et récupérer le Phone Number ID.
3. Dans les réglages Webhooks, mettre l’URL publique HTTPS du serveur suivie de `/api/whatsapp/webhook`.
4. Saisir le même `WHATSAPP_VERIFY_TOKEN` dans Meta et dans les variables privées de l’hébergeur.
5. S’abonner au champ `messages`.
6. Définir `WHATSAPP_APP_SECRET`, `WHATSAPP_ACCESS_TOKEN`, `WHATSAPP_PHONE_NUMBER_ID` et `WHATSAPP_GRAPH_VERSION` dans l’hébergeur.
7. Ouvrir `/whatsapp.html`, puis se connecter avec le mot de passe administrateur.

Meta demande un point de réception public en HTTPS et utilise une vérification par token pour l’abonnement webhook; la signature de chaque événement est vérifiée avec le secret de l’application. Voir la [documentation WhatsApp Cloud API](https://developers.facebook.com/docs/whatsapp/cloud-api/webhooks).

## Protection des données

Le webhook conserve les textes, l’identifiant WhatsApp, l’heure et le type des messages dans la base privée. Les images et documents ne sont pas téléchargés dans la version actuelle. Le tableau de bord et ses API exigent la session administrateur. Ne stocke pas les identifiants Meta dans le dépôt GitHub.
