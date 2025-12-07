# src/utils/whisper_preload.py

import logging
import os
import sys
from pathlib import Path
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from src.config.settings import Settings

logger = logging.getLogger(__name__)

# Instance globale partagée du modèle Whisper
_WHISPER_MODEL = None
_WHISPER_MODEL_INFO = None  # juste pour du logging / debug


def get_whisper_model(
    model_name: str,
    *,
    compute_type: Optional[str] = None,
    vram_min_gb: float = 5.0,
):
    """
    Retourne une instance *partagée* de WhisperModel.

    - Si aucun modèle n'est encore chargé, on détecte le device (cuda/cpu),
      on choisit un compute_type, on charge le modèle et on le garde en cache.
    - Si un modèle est déjà chargé, on le réutilise, même si on redemande
      un autre (on log un warning dans ce cas).

    Cela évite de recharger `large-v3` (ou autre) à chaque /scribe.
    """

    global _WHISPER_MODEL, _WHISPER_MODEL_INFO

    if _WHISPER_MODEL is not None:
        # Modèle déjà chargé : on avertit si on redemande autre chose
        if _WHISPER_MODEL_INFO is not None:
            loaded_name = _WHISPER_MODEL_INFO.get("model_name")
            loaded_ct = _WHISPER_MODEL_INFO.get("compute_type")
            if loaded_name != model_name or (
                compute_type is not None and loaded_ct != compute_type
            ):
                logger.warning(
                    "Un modèle Whisper est déjà chargé (%s, compute_type=%s). "
                    "Requêter (%s, compute_type=%s) n'aura pas d'effet : "
                    "l'instance existante sera réutilisée.",
                    loaded_name,
                    loaded_ct,
                    model_name,
                    compute_type,
                )
        return _WHISPER_MODEL

    # Import tardif pour ne pas casser le démarrage si on est en mode 'openai'
    try:
        import torch
        from faster_whisper import WhisperModel
    except ImportError as e:
        logger.error(
            "Impossible de charger Whisper : 'torch' ou 'faster-whisper' "
            "n'est pas installé alors que TRANSCRIPTION_METHOD=local. (%s)",
            e,
        )
        raise

    # Détection du device
    device = "cuda" if torch.cuda.is_available() else "cpu"

    if device == "cuda":
        try:
            props = torch.cuda.get_device_properties(0)
            gpu_ram_gb = props.total_memory / 1024**3
            if gpu_ram_gb < vram_min_gb:
                logger.warning(
                    "GPU has only %.1fGB VRAM (< %.1fGB). Falling back to CPU.",
                    gpu_ram_gb,
                    vram_min_gb,
                )
                device = "cpu"
        except Exception as e:
            logger.warning("Error checking GPU VRAM, falling back to CPU: %s", e)
            device = "cpu"

    # Choix du compute_type
    if compute_type is not None:
        ct = compute_type
    else:
        if device == "cuda":
            ct = "float16"
        else:
            # Sur CPU, float16 est mal supporté → int8 ou float32
            ct = "int8"

    logger.info(
        "Chargement du modèle Whisper partagé '%s' sur device=%s (compute_type=%s)",
        model_name,
        device,
        ct,
    )

    model = WhisperModel(model_name, device=device, compute_type=ct)

    _WHISPER_MODEL = model
    _WHISPER_MODEL_INFO = {
        "model_name": model_name,
        "device": device,
        "compute_type": ct,
    }
    return model


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

    model_name = (
        getattr(settings, "whisper_model", None)
        or getattr(settings, "whisper_model_name", None)
        or "large-v3"
    )
    compute_type = getattr(settings, "whisper_compute_type", "float16")

    logger.info(
        "Préchargement du modèle Whisper '%s' (compute_type=%s)...",
        model_name,
        compute_type,
    )

    try:
        # Appel bloquant :
        # - Si le modèle n'est pas présent, Hugging Face le télécharge puis le met en cache.
        # - Sinon, il se contente de le charger depuis le cache.
        get_whisper_model(
            model_name=model_name,
            compute_type=compute_type,
            vram_min_gb=5.0,  # tu pourras un jour le sortir dans les Settings si tu veux
        )
    except Exception:
        logger.exception(
            "Échec du préchargement du modèle Whisper. "
            "Vérifiez la connexion réseau, l'espace disque, "
            "ou la compatibilité GPU (si device='cuda')."
        )
        sys.exit(1)

    logger.info("Modèle Whisper préchargé avec succès.")
