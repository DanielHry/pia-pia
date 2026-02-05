# =============================================================================
# Pia-Pia Bot 🦜 — Dockerfile
# =============================================================================
# Build  : docker build -t pia-pia .
# Run    : docker compose up -d
# =============================================================================

# ---------------------------------------------------------------------------
# Stage 1 — Build : installer les dépendances avec uv
# ---------------------------------------------------------------------------
FROM python:3.12-slim-bookworm AS builder

# Installer uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

# Dépendances système pour compiler les packages Python (PyNaCl, etc.)
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libffi-dev \
    libsodium-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copier les fichiers de dépendances en premier (cache Docker)
COPY pyproject.toml uv.lock ./

# Sync des dépendances (sans le projet lui-même)
RUN uv sync --frozen --no-dev --no-install-project

# Copier le code source
COPY piapia/ ./piapia/

# Installer le projet
RUN uv sync --frozen --no-dev


# ---------------------------------------------------------------------------
# Stage 2 — Runtime : image légère avec ffmpeg
# ---------------------------------------------------------------------------
FROM python:3.12-slim-bookworm

# Dépendances runtime
#   - ffmpeg     : conversion audio (pydub)
#   - libsodium  : chiffrement voix Discord (PyNaCl)
#   - libopus    : codec audio voix Discord
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    libsodium23 \
    libopus0 \
    && rm -rf /var/lib/apt/lists/*

# Utilisateur non-root
RUN useradd --create-home --shell /bin/bash piapia

WORKDIR /app

# Copier le venv et le code depuis le builder
COPY --from=builder --chown=piapia:piapia /app /app

# Créer les dossiers de données (seront montés en volume)
RUN mkdir -p /app/.logs /app/config/player_maps \
    && chown -R piapia:piapia /app/.logs /app/config

USER piapia

# Point d'entrée
CMD ["/app/.venv/bin/python", "-m", "piapia"]