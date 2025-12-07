# src/sinks/transcriber.py

import io
import logging
import wave
from typing import Any, Dict, Optional

from openai import OpenAI

from src.utils.whisper_preload import get_whisper_model

logger = logging.getLogger(__name__)


class Transcriber:
    """
    Transcrit de l'audio WAV avec Faster-Whisper (local) ou OpenAI Whisper API.

    mode:
      - "local"  -> Faster-Whisper
      - "openai" -> OpenAI Whisper API
    """

    def __init__(
        self,
        mode: str = "local",
        language: str = "fr",
        model_name: str = "large-v3",
        *,
        min_duration: float = 0.1,              # durée min (en secondes) avant transcription
        whisper_params: Optional[Dict[str, Any]] = None,
        compute_type: Optional[str] = None,     # ex: "float16", "int8", "float32"
        vram_min_gb: float = 5.0,               # VRAM minimale pour rester sur GPU
    ) -> None:
        self.mode = mode
        self.language = language
        self.min_duration = min_duration

        self.whisper_params = whisper_params or {
            "vad_filter": True,
            # Tu pourras ajuster ici beam_size, best_of, etc.
            # "beam_size": 5,
            # "best_of": 3,
            # "condition_on_previous_text": False,
        }

        if mode == "local":
            # On récupère le modèle *partagé* via le provider
            self.model = get_whisper_model(
                model_name=model_name,
                compute_type=compute_type,
                vram_min_gb=vram_min_gb,
            )
            self.client = None
        else:
            logger.info("Using OpenAI Whisper API for transcription")
            self.client = OpenAI()
            self.model = None

    # --- helpers ---

    def _get_wav_duration(self, wav_io: io.BytesIO) -> float:
        """Retourne la durée en secondes d'un WAV en mémoire."""
        wav_io.seek(0)
        with wave.open(wav_io, "rb") as wf:
            frames = wf.getnframes()
            rate = wf.getframerate()
            if rate == 0:
                return 0.0
            return frames / float(rate)

    # --- public API ---

    def transcribe_wav(self, wav_io: io.BytesIO) -> str:
        """Retourne la transcription texte d'un blob WAV."""
        try:
            duration = self._get_wav_duration(wav_io)
            if duration < self.min_duration:
                logger.debug("Skipping transcription: audio too short (%.3fs)", duration)
                return ""

            wav_io.seek(0)

            if self.mode == "openai":
                if self.client is None:
                    raise RuntimeError("OpenAI client not initialized")

                res = self.client.audio.transcriptions.create(
                    file=("audio.wav", wav_io),
                    model="whisper-1",
                    language=self.language,
                )
                text = res.text or ""
                logger.debug("OpenAI transcription: %s", text)
                return text

            # local / Faster-Whisper
            if self.model is None:
                raise RuntimeError("Whisper model not initialized")

            segments, _ = self.model.transcribe(
                wav_io,
                language=self.language,
                **self.whisper_params,
            )

            text = "".join(segment.text for segment in segments)
            logger.debug("Local transcription: %s", text)
            return text

        except Exception as e:
            logger.error("Transcription error: %s", e)
            return ""
