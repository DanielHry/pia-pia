# ------------------------------
# Image de base : Python 3.11 slim (léger, suffisant pour CPU)
# ------------------------------
FROM python:3.11-slim

# ------------------------------
# 1) Dépendances système
#    - ffmpeg : pour manipuler l'audio
#    - libopus0 : pour la voix Discord (py-cord[voice] en a besoin)
# ------------------------------
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    libopus0 \
 && rm -rf /var/lib/apt/lists/*

# ------------------------------
# 2) Dossier de travail /app
# ------------------------------
WORKDIR /app

# ------------------------------
# 3) Installation des dépendances Python
#    On copie uniquement requirements.txt d'abord pour profiter du cache Docker
# ------------------------------
COPY requirements.txt .

RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir torch --index-url https://download.pytorch.org/whl/cpu && \
    pip install --no-cache-dir -r requirements.txt

# ------------------------------
# 4) Copie du code de l'application
#    (src/, config/, README, etc.)
# ------------------------------
COPY . .

# On s'assure que le dossier des logs existe (au cas où LOGS_DIR=.logs)
RUN mkdir -p /app/.logs

# ------------------------------
# 5) Variables d'env de base
# ------------------------------
ENV PYTHONUNBUFFERED=1

# ------------------------------
# 6) Commande par défaut :
#    ton entrypoint actuel est `python -m src.main` 
# ------------------------------
CMD ["python", "-m", "src.main"]
