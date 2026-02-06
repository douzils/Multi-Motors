# Multi-Motors AI

IA de scraping automatique pour alimenter le catalogue de moteurs brushless FPV dans Google Sheets.

## Fonctionnement

L'application tourne en continu et effectue les étapes suivantes en boucle :

1. **Recherche via DuckDuckGo** - Découvre de nouvelles pages produit de moteurs brushless par marque, taille de stator et nouveautés
2. **Scraping de boutiques FPV** - Parcourt les boutiques en ligne spécialisées (GetFPV, RaceDayQuads, Pyrodrone, etc.)
3. **Scraping fabricants** - Visite directement les sites des fabricants (T-Motor, BetaFPV, Emax, iFlight, etc.)
4. **Extraction des specs** - Parse les pages produit pour extraire les spécifications techniques (KV, poids, stator, voltage, etc.)
5. **Ajout au catalogue** - Ajoute les nouveaux moteurs dans le Google Sheet en évitant les doublons

## Colonnes du Google Sheet

| Colonne | Description |
|---------|-------------|
| ID | Identifiant auto |
| REF | Référence unique (ex: EMAX-2207-1900) |
| MARQUE | Fabricant |
| NOM | Nom/série du moteur |
| VERSION | Version |
| CLASSE | Taille stator (ex: 2207) |
| KV | Vitesse en KV |
| POIDS | Poids en grammes |
| H STATOR | Hauteur stator (mm) |
| D STATOR | Diamètre stator (mm) |
| H MOTEUR | Hauteur moteur (mm) |
| D MOTEUR | Diamètre moteur (mm) |
| D SHAFT | Diamètre axe (mm) |
| L SHAFT | Longueur axe (mm) |
| TYPE SHAFT | Type d'axe |
| VIS HEL | Vis hélice |
| VIS FIX | Vis de fixation |
| ENTRAXE FIX | Entraxe fixation (mm) |
| LIPO | Batterie compatible |
| VOLTAGE | Tension |
| L CABLE | Longueur câble |
| TYPE CABLE | Gauge fil |
| HELICE | Taille hélice |
| PUISSANCE | Puissance (W) |
| AMP | Courant max (A) |
| AIMANT | Type d'aimant |
| CLOCHE | Type de cloche |
| CONFIG | Configuration N/P |
| LIEN | Lien produit |
| IMG | URL image |

## Installation

### 1. Prérequis

- Python 3.10+
- Un compte Google Cloud avec l'API Sheets activée

### 2. Configuration Google Sheets

1. Aller sur [Google Cloud Console](https://console.cloud.google.com/)
2. Créer un projet (ou en utiliser un existant)
3. Activer l'API **Google Sheets** et l'API **Google Drive**
4. Créer un **Service Account** :
   - IAM & Admin > Service Accounts > Create
   - Télécharger la clé JSON → la renommer `credentials.json`
5. Partager le Google Sheet avec l'email du service account (droits **Éditeur**)

### 3. Installation des dépendances

```bash
cd Multi-Motors
python -m venv venv
source venv/bin/activate  # Linux/Mac
# ou: venv\Scripts\activate  # Windows

pip install -r multi_motors_ai/requirements.txt
```

### 4. Configuration

```bash
cp .env.example .env
# Éditer .env si nécessaire (les valeurs par défaut pointent vers le bon sheet)
```

Placer le fichier `credentials.json` à la racine du projet.

### 5. Lancement

```bash
python -m multi_motors_ai.main
```

L'IA va :
- Se connecter au Google Sheet
- Lancer un premier scan complet
- Puis scanner automatiquement toutes les 60 minutes (configurable)

### Arrêt propre

`Ctrl+C` pour arrêter proprement après le cycle en cours.

## Configuration avancée

Variables d'environnement (fichier `.env`) :

| Variable | Défaut | Description |
|----------|--------|-------------|
| `SCAN_INTERVAL_MINUTES` | 60 | Intervalle entre les scans |
| `REQUEST_DELAY_MIN` | 2 | Délai minimum entre requêtes (sec) |
| `REQUEST_DELAY_MAX` | 5 | Délai maximum entre requêtes (sec) |
| `MAX_RESULTS_PER_SEARCH` | 30 | Résultats max par recherche |
| `LOG_LEVEL` | INFO | Niveau de log (DEBUG, INFO, WARNING) |

## Architecture

```
multi_motors_ai/
├── __init__.py
├── main.py              # Point d'entrée, boucle principale
├── config.py            # Configuration et constantes
├── models.py            # Modèle de données MotorSpec
├── sheets.py            # Intégration Google Sheets
├── parser.py            # Extraction de specs par regex
└── scrapers/
    ├── __init__.py
    ├── base.py           # Scraper de base avec HTTP/parsing
    ├── search_engine.py  # Découverte via DuckDuckGo
    └── shop_scraper.py   # Scraping boutiques et fabricants
```

## Sources de données

### Moteurs recherchés par marque
3BHOBBY, BetaFPV, BrotherHobby, Cobra, DYS, Emax, FlyFishRC, Flywoo, GepRC, HappyModel, iFlight, T-Motor, Xnova, et 30+ autres.

### Tailles de stator couvertes
0603, 0802, 1103, 1404, 1507, 2004, 2205, 2207, 2306, 2405, 2507, 2806, 3115, etc.

### Boutiques FPV scrapées
GetFPV, RaceDayQuads, Pyrodrone, BetaFPV, iFlight-RC
