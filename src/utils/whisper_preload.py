# src/utils/whisper_preload.py

import logging
import os
import sys
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.config.settings import Settings

logger = logging.getLogger(__name__)


def preload_whisper_model_if_needed(settings: "Settings") -> None:
    """
    Précharge le modèle Whisper au démarrage du bot si :

      - settings.transcription_method == 'local'

    Objectif :
      - Télécharger le modèle (large-v3, medium, etc.) AVANT de lancer la boucle Discord,
      - éviter que la première commande /scribe bloque la boucle event le temps du download.

    Si settings.whisper_cache_dir est défini et différent de "default",
    on force ce répertoire comme cache Hugging Face (HUGGINGFACE_HUB_CACHE).
    """

    transcription_method = getattr(settings, "transcription_method", None)
    if transcription_method != "local":
        logger.debug(
            "transcription_method=%r -> pas de préchargement du modèle Whisper.",
            transcription_method,
        )
        return

    # Gestion optionnelle d'un cache Hugging Face custom
    cache_dir = getattr(settings, "whisper_cache_dir", None)
    if cache_dir and str(cache_dir).lower() != "default":
        cache_path = Path(cache_dir)
        cache_path.mkdir(parents=True, exist_ok=True)
        os.environ["HUGGINGFACE_HUB_CACHE"] = str(cache_path)
        logger.info("Cache Hugging Face forcé sur : %s", cache_path)

    # Import tardif pour ne pas casser le démarrage si on est en mode 'openai'
    try:
        import torch
        from faster_whisper import WhisperModel
    except ImportError:
        logger.error(
            "Impossible de précharger Whisper : 'torch' ou 'faster-whisper' "
            "n'est pas installé alors que TRANSCRIPTION_METHOD=local."
        )
        # En mode 'local', sans ces libs, le bot ne pourra de toute façon pas transcrire.
        sys.exit(1)

    device = "cuda" if torch.cuda.is_available() else "cpu"

    compute_type = getattr(settings, "whisper_compute_type", "float16")
    model_name = (
        getattr(settings, "whisper_model", None)
        or getattr(settings, "whisper_model_name", None)
        or "large-v3"
    )

    logger.info(
        "Préchargement du modèle Whisper '%s' sur device=%s (compute_type=%s)...",
        model_name,
        device,
        compute_type,
    )

    try:
        # Appel bloquant :
        # - Si le modèle n'est pas présent, Hugging Face le télécharge puis le met en cache.
        # - Sinon, il se contente de le charger depuis le cache.
        WhisperModel(model_name, device=device, compute_type=compute_type)
    except Exception:
        logger.exception(
            "Échec du préchargement du modèle Whisper. "
            "Vérifiez la connexion réseau, l'espace disque, "
            "ou la compatibilité GPU (si device='cuda')."
        )
        sys.exit(1)

    logger.info("Modèle Whisper préchargé avec succès.")
