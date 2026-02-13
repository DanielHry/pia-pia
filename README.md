# Pia-Pia 🦜 — Discord Voice Recording Bot

Pia-Pia is a Discord bot designed to **join a voice channel and record audio**.  
It archives **one file per participant** and generates **session metadata** (`session_meta.json`) to make later offline processing easier (editing, diarization, transcription, etc.).

---

## Features

- ✅ `/connect` : joins your voice channel
- ✅ `/record [label]` : starts a recording session
- ✅ `/stop` : stops the current session
- ✅ `/disconnect` : leaves the voice channel
- ✅ `/update_player_map` : refreshes the player/character list (admin)
- ✅ `/help` : shows help
- ✅ Per-user audio archiving (WAV)
- ✅ Multi-server support (one player map per guild)

---

## Prerequisites

### Discord side

1. Create an application/bot in the [Discord Developer Portal](https://discord.com/developers/applications)
2. Add the bot to your server with these permissions:
   - `Connect`
   - `Speak` *(even if Pia-Pia is self-muted)*
   - `Use Voice Activity`

### Machine side

- **Python 3.11+**
- **uv** (dependency manager) — [Astral documentation](https://docs.astral.sh/uv/getting-started/installation/)

---

## Installation and run

```bash
# Clone the repo
git clone https://github.com/your-repo/pia-pia.git
cd pia-pia

# Copy and configure the environment
cp .env.example .env
# Edit .env with your Discord token
```

### With uv (recommended)

```bash
# Install dependencies
uv sync

# Run
uv run python -m piapia

# With debug flag
uv run python -m piapia --debug
```

### With Docker

```bash
# Build and run
docker compose up -d

# View logs
docker compose logs -f

# Stop
docker compose down
```

---

## Configuration

### Environment variables

| Variable | Description | Default |
|---|---|---|
| `DISCORD_BOT_TOKEN` | Bot Discord token | *(required)* |
| `DEBUG` | Debug logging | `False` |
| `LOGS_DIR` | Logs root folder | `.logs` |
| `AUDIO_SESSIONS_SUBDIR` | Audio sessions subfolder | `audio` |
| `PLAYER_MAP_DIR` | Player maps folder (per guild) | `config/player_maps` |
| `MAX_SESSION_DURATION_MINUTES` | Max session duration (0 = unlimited) | `240` |


---

## Usage

### Discord commands

| Command | Description | Cooldown |
|---|---|---|
| `/connect` | Join your voice channel | 10s |
| `/record [label]` | Start recording | 5s |
| `/stop` | Stop recording | 5s |
| `/disconnect` | Leave the voice channel | 10s |
| `/update_player_map` | Refresh players (admin) | 30s |
| `/help` | Show help | - |

### Typical workflow

1. Join a voice channel on Discord
2. `/connect` — Pia-Pia joins you
3. `/record TTRPG Session` — Start recording with a label
4. *... play session ...*
5. `/stop` — Stop and save files
6. `/disconnect` — Pia-Pia leaves the channel

### Generated files

```
.logs/audio/2026-02-04_20-30-00_g123456789/
├── user_111111111.wav      # Player 1 audio
├── user_222222222.wav      # Player 2 audio
├── user_333333333.wav      # Player 3 audio
└── session_meta.json       # Session metadata
```

---

## Player Map (multi-server)

Pia-Pia stores one **player map** per Discord server: `user_id → {player, character}`.

### Structure

```
config/player_maps/
├── guild_123456789.yaml    # Server 1
└── guild_987654321.yaml    # Server 2
```

### YAML format

```yaml
111111111:
  player: "Alice"
  character: "Elowen the Wizard"
222222222:
  player: "Bob"
  character: "Thorgar the Barbarian"
```

> The `/update_player_map` command (typically admin-only) refreshes the list from the server members.

---

## Tests

```bash
# Install dev dependencies
uv sync --extra dev

# Run tests
uv run pytest

# With coverage
uv run pytest --cov=piapia --cov-report=html
```

---

## Architecture

```
piapia/
├── __main__.py              # Entry point
├── bot/
│   ├── piapia_bot.py        # Main bot
│   ├── helper.py            # Per-guild helper
│   └── cogs/
│       ├── audio_cog.py     # Audio commands
│       └── admin_cog.py     # Admin commands
├── config/
│   ├── settings.py          # Pydantic settings
│   └── logging_config.py    # Logging config
├── domain/
│   └── sessions.py          # Session models
├── sinks/
│   ├── discord_sink.py      # Discord sink (audio capture)
│   └── audio_archiver.py    # WAV archive
└── utils/
    ├── commandline.py       # CLI arguments
    └── session_paths.py     # Session paths
```

---

## Licence

MIT License — voir [LICENSE](LICENSE)

---

## Crédits

Projet développé pour l'enregistrement vocal Discord 🦜

- [py-cord](https://github.com/Pycord-Development/pycord) — Discord API wrapper