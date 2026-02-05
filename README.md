# Pia-Pia 🦜 — Bot Discord d'enregistrement vocal

Pia-Pia est un bot Discord conçu pour **rejoindre un salon vocal et enregistrer l'audio**.  
Il archive des **fichiers par participant** et génère une **métadonnée de session** (`session_meta.json`) pour faciliter un traitement offline ultérieur (montage, diarisation, transcription, etc.).

> Objectif : simple, robuste, et "record-only".

---

## Fonctionnalités

- ✅ `/connect` : rejoint ton salon vocal
- ✅ `/record [label]` : démarre une session d'enregistrement
- ✅ `/stop` : arrête la session en cours
- ✅ `/disconnect` : quitte le salon vocal
- ✅ `/update_player_map` : met à jour la liste joueurs/personnages (admin)
- ✅ `/help` : affiche l'aide
- ✅ Archivage audio **par utilisateur** (WAV, MP3, FLAC ou OGG)
- ✅ Support **multi-serveur** (player maps par guilde)
- ✅ **Durée maximale de session** configurable (avec avertissement 5 min avant)
- ✅ **Rate limiting** sur les commandes (anti-spam)
- ✅ `session_meta.json` : infos de session + joueurs + offsets temporels
- ✅ Logs applicatifs avec rotation

---

## Prérequis

### Côté Discord

1. Créer une application/bot sur le [portail développeurs Discord](https://discord.com/developers/applications)
2. Ajouter le bot à ton serveur avec les permissions :
   - `Connect`
   - `Speak` *(même si Pia-Pia est self-mute)*
   - `Use Voice Activity`

### Côté machine

- **Python 3.11+**
- **uv** (gestionnaire de dépendances) — [installation](https://docs.astral.sh/uv/getting-started/installation/)
- **ffmpeg** (optionnel, requis pour MP3/FLAC/OGG) — [installation](https://ffmpeg.org/download.html)

---

## Installation

### Avec uv (recommandé)

```bash
# Cloner le repo
git clone https://github.com/ton-repo/pia-pia.git
cd pia-pia

# Installer les dépendances
uv sync

# Copier et configurer l'environnement
cp .env.example .env
# Éditer .env avec ton token Discord
```

### Avec Docker

```bash
# Copier et configurer l'environnement
cp .env.example .env
# Éditer .env avec ton token Discord

# Build et lancement
docker compose up -d

# Voir les logs
docker compose logs -f

# Arrêter
docker compose down
```

---

## Configuration

### Variables d'environnement

| Variable | Description | Défaut |
|---|---|---|
| `DISCORD_BOT_TOKEN` | Token Discord du bot | *(obligatoire)* |
| `DEBUG` | Logs en mode debug | `False` |
| `LOGS_DIR` | Dossier racine des logs | `.logs` |
| `AUDIO_SESSIONS_SUBDIR` | Sous-dossier des sessions audio | `audio` |
| `PLAYER_MAP_DIR` | Dossier des player maps par guilde | `config/player_maps` |
| `AUDIO_FORMAT` | Format audio : `wav`, `mp3`, `flac`, `ogg` | `wav` |
| `MAX_SESSION_DURATION_MINUTES` | Durée max d'une session (0 = illimité) | `240` |

### Formats audio

| Format | Taille approximative | Qualité | Nécessite ffmpeg |
|---|---|---|---|
| `wav` | ~660 MB/h/utilisateur | Sans perte | Non |
| `flac` | ~250 MB/h/utilisateur | Sans perte | Oui |
| `mp3` | ~50 MB/h/utilisateur | Avec perte | Oui |
| `ogg` | ~40 MB/h/utilisateur | Avec perte | Oui |

---

## Lancer le bot

```bash
# Avec uv
uv run python -m piapia

# Avec le flag debug
uv run python -m piapia --debug
```

---

## Utilisation

### Commandes Discord

| Commande | Description | Cooldown |
|---|---|---|
| `/connect` | Rejoint ton salon vocal | 10s |
| `/record [label]` | Démarre l'enregistrement | 5s |
| `/stop` | Arrête l'enregistrement | 5s |
| `/disconnect` | Quitte le salon vocal | 10s |
| `/update_player_map` | Met à jour les joueurs (admin) | 30s |
| `/help` | Affiche l'aide | - |

### Workflow typique

1. Rejoins un salon vocal sur Discord
2. `/connect` — Pia-Pia te rejoint
3. `/record Session JDR` — Démarre l'enregistrement avec un label
4. *... ta session de jeu ...*
5. `/stop` — Arrête et sauvegarde les fichiers
6. `/disconnect` — Pia-Pia quitte le salon

### Fichiers générés

```
.logs/audio/2026-02-04_20-30-00_g123456789/
├── user_111111111.mp3      # Audio du joueur 1
├── user_222222222.mp3      # Audio du joueur 2
├── user_333333333.mp3      # Audio du joueur 3
└── session_meta.json       # Métadonnées de session
```

---

## Player Map (multi-serveur)

Pia-Pia stocke une **player map** par serveur Discord : `user_id → {player, character}`.

### Structure

```
config/player_maps/
├── guild_123456789.yaml    # Serveur 1
└── guild_987654321.yaml    # Serveur 2
```

### Format YAML

```yaml
111111111:
  player: "Alice"
  character: "Elowen la Magicienne"
222222222:
  player: "Bob"
  character: "Thorgar le Barbare"
```

### Mise à jour

La commande `/update_player_map` (réservée aux admins) rafraîchit automatiquement la liste depuis les membres du serveur.

---

## Tests

```bash
# Installer les dépendances de dev
uv sync --extra dev

# Lancer les tests
uv run pytest

# Avec couverture
uv run pytest --cov=piapia --cov-report=html
```

---

## Architecture

```
piapia/
├── __main__.py              # Point d'entrée
├── bot/
│   ├── piapia_bot.py        # Bot principal
│   ├── helper.py            # Helper par guilde
│   └── cogs/
│       ├── audio_cog.py     # Commandes audio
│       └── admin_cog.py     # Commandes admin
├── config/
│   ├── settings.py          # Configuration Pydantic
│   └── logging_config.py    # Configuration logs
├── domain/
│   └── sessions.py          # Modèles de session
├── sinks/
│   ├── discord_sink.py      # Sink Discord (capture audio)
│   └── audio_archiver.py    # Archivage WAV + conversion
└── utils/
    ├── commandline.py       # Arguments CLI
    └── session_paths.py     # Chemins de session
```

---

## Docker

### Build manuel

```bash
docker build -t pia-pia .
```

### Volumes

| Chemin conteneur | Description |
|---|---|
| `/app/.logs` | Sessions audio (à monter en volume) |
| `/app/config/player_maps` | Player maps par guilde |

### Exemple docker-compose.yml

```yaml
services:
  pia-pia:
    build: .
    container_name: pia-pia
    restart: unless-stopped
    env_file: .env
    volumes:
      - ./.logs:/app/.logs
      - ./config/player_maps:/app/config/player_maps
```

---

## Licence

MIT License — voir [LICENSE](LICENSE)

---

## Crédits

Projet développé pour l'enregistrement vocal Discord 🦜

- [py-cord](https://github.com/Pycord-Development/pycord) — Discord API wrapper
- [pydub](https://github.com/jiaaro/pydub) — Manipulation audio
- [ffmpeg](https://ffmpeg.org/) — Conversion audio