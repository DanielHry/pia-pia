# =============================================================================
# Pia-Pia Bot 🦜 — Dockerfile
# =============================================================================
# Build  : docker build -t pia-pia .
# Run    : docker compose up -d
# =============================================================================

# ---------------------------------------------------------------------------
# Stage 1 — Build: install dependencies with uv
# ---------------------------------------------------------------------------
FROM python:3.12-slim-bookworm AS builder

# Install uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

# System dependencies to compile Python packages (PyNaCl, etc.)
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libffi-dev \
    libsodium-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy dependency files first (Docker cache)
COPY pyproject.toml uv.lock ./

# Sync dependencies (without installing the project itself)
RUN uv sync --frozen --no-dev --no-install-project

# Copy the source code
COPY piapia/ ./piapia/

# Install the project
RUN uv sync --frozen --no-dev

FROM python:3.12-slim-bookworm

# Runtime dependencies
#   - libsodium : Discord voice encryption (PyNaCl)
#   - libopus   : Discord voice audio codec
RUN apt-get update && apt-get install -y --no-install-recommends \
    libsodium23 \
    libopus0 \
    && rm -rf /var/lib/apt/lists/*

# Non-root user
RUN useradd --create-home --shell /bin/bash piapia

WORKDIR /app

# Copy the venv and code from the builder
COPY --from=builder --chown=piapia:piapia /app /app

# Create data directories (will be mounted as volumes)
RUN mkdir -p /app/.logs /app/config/player_maps \
    && chown -R piapia:piapia /app/.logs /app/config

USER piapia

# Entry point
CMD ["/app/.venv/bin/python", "-m", "piapia"]
