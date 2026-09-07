# HomeCheck

Application web locale d'aide à l'analyse d'un bien immobilier avant achat. Le rapport distingue systématiquement données officielles, estimations et informations indisponibles. Il ne remplace ni un diagnostic, ni un certificat d'urbanisme, ni l'avis d'un professionnel.

## Installation Windows

1. Double-cliquer sur `install.bat`.
2. Double-cliquer sur `run.bat`.
3. Ouvrir http://127.0.0.1:8000.

En ligne de commande :

```bat
install.bat
run.bat
```

Le serveur écoute uniquement sur `127.0.0.1`. Les analyses et le cache sont conservés dans `data/homecheck.db`.

## Fonctionnalités du MVP

- formulaire responsive et rapport détaillé ;
- géocodage réel via le service de géocodage de la Géoplateforme (données BAN) ;
- itinéraire voiture réel via OSRM/OpenStreetMap, sans trafic temps réel ;
- interrogation des risques communaux via Géorisques, avec fallback non bloquant ;
- carte Leaflet avec le bien, le travail et l'itinéraire ;
- scoring transparent, pondéré par priorité, qui ignore et redistribue les catégories sans données ;
- points de vigilance et fiabilité des sources ;
- cache par source et historique dans SQLite ;
- pages de consultation des analyses passées.

## Architecture

`app/main.py` orchestre FastAPI. Les intégrations sont isolées dans `app/services`. `app/scoring.py` ne dépend pas du web et reste testable. Les templates Jinja2 et assets sont dans `app/templates` et `app/static`.

### Stack technique

- Backend : Python, FastAPI et Uvicorn (ASGI).
- Interface : templates Jinja2, HTML, CSS et JavaScript, carte Leaflet.
- Appels HTTP : httpx ; validation et configuration : Pydantic / pydantic-settings.
- Persistance : SQLite, pour l'historique et le cache.
- Tests : pytest et pytest-asyncio.
- Aucun build Node.js, React ou npm n'est nécessaire.

## Installation Linux / hébergement

Depuis la racine du projet, avec Python et le module venv installés :

```sh
python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Ouvrir http://127.0.0.1:8000. Les dépendances exactes sont dans `requirements.txt` ; leurs versions ne sont pas encore verrouillées pour un déploiement reproductible.

### Configuration

La configuration par défaut suffit au lancement. Pour la personnaliser, copier `.env.example` vers `.env` ou définir les variables d'environnement correspondantes :

| Variable | Valeur par défaut | Usage |
| --- | --- | --- |
| `HOME_CHECK_HTTP_TIMEOUT` | `8` | Délai HTTP configuré, en secondes ; certaines intégrations ont leurs propres délais |
| `HOME_CHECK_DEMO` | `false` | Option réservée ; ne génère pas de données simulées |

La base `data/homecheck.db` et son répertoire sont créés automatiquement au démarrage. Ne pas publier cette base : elle contient notamment les adresses des biens et lieux de travail saisis.

### Préparation au déploiement cloud

Commande de lancement pour un hébergeur Linux exposant la variable `PORT` :

```sh
python -m uvicorn app.main:app --host 0.0.0.0 --port "${PORT:-8000}"
```

Cette commande ne configure pas à elle seule la persistance ni la sécurité. Avant une mise en ligne publique :

- Protéger l'accès aux analyses, à l'historique et aux routes `/api/debug/*` : l'application ne dispose pas encore d'authentification.
- Prévoir un stockage persistant et des sauvegardes. Le chemin SQLite actuel est fixé dans `app/config.py` ; un disque éphémère n'est pas adapté à l'historique.
- Pour une base PostgreSQL externe, adapter `app/database.py` et la configuration : `DATABASE_URL` n'est pas encore pris en charge.
- Vérifier l'accès sortant aux fournisseurs de données et leurs limites d'utilisation.
- Tester la mémoire, les temps de réponse et les appels concurrents avant de choisir la taille de l'instance.

Le projet est une application locale fonctionnelle, pas encore une application publique multi-utilisateur sécurisée.

## Fichiers à publier sur GitHub

Créer un dépôt dédié à HomeCheck et placer directement ces éléments à sa racine (pas le dossier parent contenant d'autres projets) :

```text
app/                 # Tous les .py, templates et fichiers statiques
tests/               # Tests Python
.env.example         # Exemple de configuration, sans secret
.gitignore
README.md
requirements.txt
pytest.ini
install.bat
run.bat
```

Ne pas envoyer `.venv/`, `venv/`, `__pycache__/`, `.pytest_cache/`, `.env`, `data/`, les bases SQLite, leurs fichiers auxiliaires, les journaux ou des sauvegardes personnelles. Conserver les fichiers `__init__.py`.

Attention : `.gitignore` protège les ajouts effectués avec Git, mais ne filtre pas un téléversement manuel dans le navigateur GitHub. Il ne retire pas non plus les fichiers déjà suivis par Git.

## Sources et limites

- **Connectées :** Géoplateforme/BAN, OSRM/OpenStreetMap, API Géorisques (si le service répond).
- **Urbanisme connecté :** parcelle cadastrale, document, zonage, prescriptions, SUP et recherche d'OAP via API Carto IGN. La route locale `/api/debug/urbanisme?lat=...&lon=...` expose les résultats techniques.
- **Nuisances connectées :** routes, voies ferrées, gares et aérodromes via OpenStreetMap/Overpass ; ICPE via Géorisques ; isophones ferroviaires Lden via Toulouse Métropole lorsqu'ils intersectent le point. La route `/api/debug/noise?lat=...&lon=...` distingue données officielles et estimations.
- **Marché connecté :** exports Geo-DVF officiels par commune et par année, comparables stricts, médiane/moyenne et route `/api/debug/dvf`.
- **Services connectés :** commerces, écoles, santé et transports via Overpass ; couverture FTTH communale issue des données ARCEP via l'API d'agrégation ouverte. Route `/api/debug/services`.
- **Préparées mais non connectées automatiquement :** PEB/PGS nationaux, WFS CBS départementaux hors fournisseurs configurés, éligibilité fibre exacte à l'adresse, GTFS, annuaire Éducation nationale, ANFR et potentiel des parcelles voisines.
- OSRM fournit un temps nominal, jamais un trafic historique ou temps réel.
- Le risque retourné par l'endpoint utilisé est communal : il ne prouve pas l'exposition exacte de la parcelle.
- Aucun indicateur ne conclut à la constructibilité d'une parcelle.

## Évolutions et clés optionnelles

Une intégration Google Maps, HERE, TomTom ou OpenRouteService pourrait ajouter trafic/alternatives ; elle n'est pas implémentée. Les comparables DVF utilisent déjà les exports Geo-DVF par commune. Les secrets devront être placés dans `.env` (voir `.env.example`) et jamais versionnés.

Le mode `HOME_CHECK_DEMO=true` est prévu dans la configuration, mais le MVP ne génère volontairement aucune valeur simulée.

## Tests

```bat
.venv\Scripts\python.exe -m pytest -q
```

Sous Linux, après activation de l'environnement : `python -m pytest -q`.
Certains tests interrogent des services externes : une panne, une limitation ou un changement de leurs données peut affecter les résultats.
