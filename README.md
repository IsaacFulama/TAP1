# TAP Gestion des Loyers

Application de gestion des souscriptions et paiements de loyers avec interface moderne et sécurisée.

## 📋 Table des matières

- [Caractéristiques](#caractéristiques)
- [Architecture](#architecture)
- [Installation](#installation)
- [Configuration](#configuration)
- [Utilisation](#utilisation)
- [Développement](#développement)
- [Tests](#tests)
- [Sécurité](#sécurité)
- [Dépannage](#dépannage)

## ✨ Caractéristiques

### Fonctionnalités principales
- **Gestion des locataires** : Ajout, modification et suppression de locataires
- **Suivi des paiements** : Enregistrement et suivi des paiements de loyers
- **Gestion des acomptes** : Support des paiements partiels et acomptes
- **Export PDF** : Génération de rapports PDF professionnels
- **Filtrage avancé** : Filtres combinables par nom, mois, statut, devise
- **Tableau de bord** : Vue d'ensemble avec statistiques et graphiques
- **Historique** : Historique complet des paiements par locataire

### Portail mobile et mode hors ligne

Le projet inclut un serveur mobile séparé :

```powershell
$env:TAP_MOBILE_API_KEY = 'remplacer-par-une-cle-longue'
python mobile_server.py
```

Le portail locataire doit être créé pour un identifiant de locataire existant :

```powershell
python mobile_server.py --create-token 12 --days 30
```

Le serveur affiche alors un lien temporaire à transmettre au locataire. Le
portail permet de consulter les paiements, télécharger/imprimer les reçus et
signer depuis un écran tactile. Les actions hors ligne sont stockées dans une
file SQLite locale puis envoyées via `/api/mobile/sync` avec détection des
conflits ; un conflit n'est jamais écrasé automatiquement.

Pour un accès depuis un téléphone sur le même Wi-Fi, utiliser l'adresse IP du
PC dans `TAP_MOBILE_HOST_PUBLIC`. Pour un accès Internet, ajouter HTTPS, un
proxy inverse, une authentification forte et une rotation des clés avant toute
mise en production.

### Sécurité
- **Authentification sécurisée** : Hashage des mots de passe avec scrypt
- **Gestion des tentatives** : Verrouillage après 5 tentatives échouées
- **Logging complet** : Traçabilité de toutes les actions
- **Rapports d'erreurs** : Système de rapport d'erreurs automatique

### Qualité du code
- **Architecture modulaire** : Séparation claire des responsabilités
- **Type hints** : Annotations de types pour une meilleure maintenabilité
- **Tests unitaires** : Suite de tests complète avec pytest
- **Documentation** : Docstrings complètes et documentation utilisateur
- **Validation robuste** : Validation stricte des données entrées

## 🏗️ Architecture

### Structure du projet

```
tap/
├── config/                 # Configuration de l'application
│   ├── settings.py        # Paramètres de configuration
│   └── theme.py           # Thème et couleurs
├── core/                  # Cœur de l'application
│   ├── auth.py           # Système d'authentification
│   ├── auto_status_updater.py  # Mise à jour automatique des statuts
│   ├── date_utils.py     # Utilitaires de dates
│   ├── error_reporter.py # Rapport d'erreurs
│   ├── utils.py          # Utilitaires généraux
│   └── validators.py     # Validation des données
├── infrastructure/        # Infrastructure technique
│   └── database/
│       ├── __init__.py   # Module de base de données
│       ├── connection.py # Gestion des connexions
│       ├── migrations.py # Migrations de schéma
│       └── repository.py # Opérations CRUD
└── presentation/          # Interface utilisateur
    ├── bootstrap.py      # Point d'entrée
    ├── components/       # Composants UI réutilisables
    ├── dialogs/          # Boîtes de dialogue
    └── views/            # Vues principales
```

### Principes de conception

- **Séparation des responsabilités** : Chaque module a une responsabilité unique
- **Injection de dépendances** : Utilisation de l'injection pour la testabilité
- **Gestion d'erreurs** : Exceptions spécifiques et logging approprié
- **Validation des données** : Validation à plusieurs niveaux

## 🚀 Installation

### Prérequis

- Python 3.8 ou supérieur
- MySQL 5.7 ou supérieur
- pip (gestionnaire de paquets Python)

### Étapes d'installation

1. **Cloner le repository**
```bash
git clone <repository-url>
cd Amour Parfait
```

2. **Créer un environnement virtuel**
```bash
python -m venv .venv
source .venv/bin/activate  # Linux/Mac
.venv\Scripts\activate     # Windows
```

3. **Installer les dépendances**
```bash
pip install -r requirements.txt
```

4. **Configurer la base de données**
```bash
# Importer le schéma de base de données
mysql -u root -p < LIVRAISON_CLIENT/init_database.sql
```

5. **Configurer l'application**
```bash
# Copier et modifier le fichier de configuration
cp config.json.example config.json
# Éditer config.json avec vos paramètres MySQL
```

## ⚙️ Configuration

### Fichier config.json

```json
{
  "database": {
    "host": "localhost",
    "database": "gestion_loyers",
    "user": "root",
    "password": "votre_mot_de_passe"
  }
}
```

### Variables d'environnement (optionnel)

Vous pouvez également utiliser des variables d'environnement pour la configuration :

- `DB_HOST` : Hôte de la base de données
- `DB_NAME` : Nom de la base de données
- `DB_USER` : Utilisateur de la base de données
- `DB_PASSWORD` : Mot de passe de la base de données

## 📖 Utilisation

### Démarrage de l'application

```bash
python main.py
```

### Connexion

Aucun mot de passe administrateur par défaut n'est fourni. Configurez un secret
initial d'au moins 12 caractères avant de lancer l'application.

PowerShell (Windows) :
```powershell
$env:TAP_ADMIN_INITIAL_USERNAME = 'TAPADM'
$env:TAP_ADMIN_INITIAL_PASSWORD = 'remplacer-par-un-secret-unique-et-long'
python main.py
```

Le mot de passe initial est lu depuis l'environnement et n'est pas inscrit dans
le code source. Les comptes créés par l'interface sont actuellement conservés
en mémoire : leur persistance après redémarrage reste à implémenter. Ne déployez
pas l'application en production avant d'avoir ajouté ce stockage persistant.

### Fonctionnalités de base

1. **Ajouter un paiement**
   - Cliquez sur "Nouveau Paiement"
   - Remplissez le formulaire avec les informations du locataire
   - Sélectionnez le mois et le montant
   - Cliquez sur "Enregistrer"

2. **Voir l'historique**
   - Double-cliquez sur une ligne du tableau
   - L'historique complet du locataire s'affiche

3. **Exporter en PDF**
   - Cliquez sur "Exporter PDF"
   - Sélectionnez le dossier de destination
   - Le rapport est généré automatiquement

4. **Filtrer les données**
   - Utilisez les filtres combinables
   - Sélectionnez le type de filtre
   - Ajoutez autant de filtres que nécessaire
   - Cliquez sur "Appliquer"

## 🧪 Développement

### Structure de développement

Le projet suit une structure modulaire avec séparation claire des couches :
- **Couche présentation** : Interface utilisateur
- **Couche domaine** : Logique métier
- **Couche infrastructure** : Accès aux données

### Conventions de codage

- **Style** : PEP 8
- **Type hints** : Obligatoires pour toutes les fonctions publiques
- **Docstrings** : Style Google avec description, paramètres, returns
- **Tests** : Couverture minimale de 70%

### Ajout de nouvelles fonctionnalités

1. Créer la fonctionnalité dans le module approprié
2. Ajouter les tests unitaires correspondants
3. Mettre à jour la documentation
4. Créer une pull request avec description

## 🧪 Tests

### Exécuter les tests

```bash
# Exécuter tous les tests
pytest

# Exécuter avec couverture
pytest --cov=tap --cov-report=html

# Exécuter un fichier spécifique
pytest tests/test_validators.py

# Exécuter avec verbosity
pytest -v
```

### Structure des tests

```
tests/
├── __init__.py
├── test_auth.py          # Tests d'authentification
└── test_validators.py    # Tests de validation
```

### Couverture de code

L'application vise une couverture de code minimale de 70%. Le rapport de couverture est généré dans `htmlcov/index.html`.

## 🔒 Sécurité

### Mesures de sécurité

1. **Authentification**
   - Hashage des mots de passe avec SHA-256
   - Sel unique pour chaque utilisateur
   - Verrouillage après tentatives échouées

2. **Base de données**
   - Utilisation de paramètres préparés
   - Pas de concaténation de requêtes SQL
   - Privilèges minimum nécessaires

3. **Logging**
   - Traçabilité complète des actions
   - Rapports d'erreurs automatiques
   - Logs rotatifs pour éviter la saturation

4. **Validation**
   - Validation stricte des entrées utilisateur
   - Expressions régulières pour les formats
   - Nettoyage des données

### Recommandations de sécurité

- Configurez `TAP_ADMIN_INITIAL_PASSWORD` avec un secret unique d’au moins 12 caractères
- Utilisez un utilisateur MySQL avec droits limités
- Activez le logging en production
- Faites des sauvegardes régulières de la base de données
- Gardez les dépendances à jour

## 🔧 Dépannage

### Problèmes courants

**Erreur de connexion à la base de données**
```
Solution : Vérifiez que MySQL est démarré et que les paramètres dans config.json sont corrects
```

**Erreur "database not found"**
```
Solution : Importez le schéma de base de données depuis LIVRAISON_CLIENT/init_database.sql
```

**Erreur de migration**
```
Solution : L'application continuera de fonctionner. Vérifiez les logs pour plus de détails
```

**Interface ne s'affiche pas correctement**
```
Solution : Vérifiez que customtkinter est installé correctement
pip install --upgrade customtkinter
```

### Obtenir de l'aide

Pour plus d'aide :
1. Consultez les logs dans `app.log`
2. Vérifiez les rapports d'erreurs dans `error_reports/`
3. Consultez la documentation dans `GUIDE_UTILISATION.md`

## 📝 Licence

Ce projet est propriétaire. Tous droits réservés.

## 👥 Contributeurs

- Équipe de développement TAP

## 📅 Version

Version actuelle : 3.7

Dernière mise à jour : Juin 2026
