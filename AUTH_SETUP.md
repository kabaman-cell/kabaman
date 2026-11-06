# Activer la création de comptes KABAMAN

La page utilise Supabase Auth pour l’inscription par e-mail et les connexions Google, Facebook et Apple. Le site peut rester hébergé sur GitHub Pages. Les boutons ne fonctionneront qu’après les réglages ci-dessous.

## 1. Créer le projet de comptes

1. Crée un projet Supabase.
2. Dans les réglages API du projet, copie le Project URL et la clé anon/publishable.
3. Dans js/config.js, renseigne uniquement ces valeurs :

    supabaseUrl: "https://TON-PROJET.supabase.co",
    supabaseAnonKey: "TA_CLE_ANON_OU_PUBLISHABLE",

La clé anon/publishable est prévue pour le navigateur. **Ne place jamais la clé service_role, un mot de passe ou une clé privée dans le dépôt.**

## 2. Autoriser le retour vers le site

Dans Supabase, ouvre Authentication → URL Configuration :

- Site URL : https://kabaman-cell.github.io/kabaman/
- Redirect URL : https://kabaman-cell.github.io/kabaman/account.html

Ajoute aussi l’adresse locale utilisée pour les essais si nécessaire, par exemple http://localhost:8000/account.html.

## 3. Activer Google, Facebook et Apple

Dans Authentication → Sign In / Providers, active chaque fournisseur et colle son identifiant client et son secret dans Supabase. Ces secrets restent dans le tableau de bord Supabase.

Pour chaque fournisseur, la valeur de rappel à enregistrer dans son portail développeur est :

    https://TON-PROJET.supabase.co/auth/v1/callback

- **Google** : créer un client OAuth Web dans Google Cloud Console.
- **Facebook** : créer une application dans Meta for Developers, activer Facebook Login et autoriser l’adresse e-mail. Le mode Développement ne permet qu’aux administrateurs, développeurs et testeurs de se connecter; il faut passer l’application en mode Live pour les clients.
- **Apple** : créer un identifiant de service Web Sign in with Apple et configurer le domaine ainsi que l’URL de retour dans Apple Developer.

Les trois fournisseurs sont séparés. Avoir l’application WhatsApp Business ne crée pas automatiquement les applications développeur nécessaires.

## 4. Tester

1. Publie les fichiers sur GitHub Pages.
2. Ouvre https://kabaman-cell.github.io/kabaman/account.html.
3. Crée un compte e-mail pour vérifier le message de confirmation.
4. Essaie ensuite les boutons Google, Facebook et Apple après avoir activé chaque fournisseur.

Le profil (nom et téléphone) est conservé dans le compte Supabase. Les commandes de la version actuelle sont encore enregistrées dans le navigateur de l’appareil; elles ne se synchronisent pas entre appareils.
