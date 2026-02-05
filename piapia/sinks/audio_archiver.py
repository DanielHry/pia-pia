# piapia/sinks/audio_archiver.py

import logging
import os
import wave
from typing import Dict

logger = logging.getLogger(__name__)


class AudioArchiver:
    """
    Enregistre l'audio brut de chaque utilisateur dans un fichier WAV séparé,
    puis convertit au format cible (mp3, flac, ogg…) à la fermeture.

    Stratégie :
      - Pendant la session : écriture WAV (streaming fiable, pas de perte si crash).
      - À close() : conversion vers le format cible via pydub, suppression du WAV source.
      - Si le format cible est "wav", aucune conversion.

    Arborescence :
      base_dir/session_id/user_<user_id>.<format>
    """

    def __init__(
        self,
        base_dir: str,
        session_id: str,
        *,
        channels: int,
        sample_width: int,
        sample_rate: int,
        audio_format: str = "wav",
    ) -> None:
        self.base_dir = base_dir
        self.session_id = session_id
        self.channels = channels
        self.sample_width = sample_width
        self.sample_rate = sample_rate
        self.audio_format = audio_format.lower().strip()

        self.session_path = os.path.join(self.base_dir, self.session_id)
        os.makedirs(self.session_path, exist_ok=True)

        self._files: Dict[int, wave.Wave_write] = {}
        self._bytes_written: int = 0

    @property
    def bytes_written(self) -> int:
        """Nombre total d'octets PCM écrits depuis le début de la session."""
        return self._bytes_written

    def _get_or_open_file(self, user_id: int) -> wave.Wave_write:
        if user_id in self._files:
            return self._files[user_id]

        path = os.path.join(self.session_path, f"user_{user_id}.wav")
        wf = wave.open(path, "wb")
        wf.setnchannels(self.channels)
        wf.setsampwidth(self.sample_width)
        wf.setframerate(self.sample_rate)

        self._files[user_id] = wf
        return wf

    def append(self, user_id: int, data: bytes) -> None:
        """
        Ajoute des frames PCM pour un utilisateur donné.
        Appelé dans le thread de traitement audio (pas dans l'event loop).
        """
        wf = self._get_or_open_file(user_id)
        wf.writeframes(data)
        self._bytes_written += len(data)

    def _convert_to_target_format(self) -> None:
        """Convertit tous les WAV de la session vers le format cible via pydub."""
        if self.audio_format == "wav":
            return

        try:
            from pydub import AudioSegment
        except ImportError:
            logger.error(
                "pydub n'est pas installé, impossible de convertir en %s. "
                "Les fichiers WAV sont conservés.",
                self.audio_format,
            )
            return

        for filename in os.listdir(self.session_path):
            if not filename.endswith(".wav"):
                continue

            wav_path = os.path.join(self.session_path, filename)
            target_name = filename.replace(".wav", f".{self.audio_format}")
            target_path = os.path.join(self.session_path, target_name)

            try:
                audio = AudioSegment.from_wav(wav_path)
                audio.export(target_path, format=self.audio_format)
                os.remove(wav_path)
                logger.debug(
                    "Converti %s -> %s",
                    filename,
                    target_name,
                )
            except Exception as e:
                logger.error(
                    "Erreur lors de la conversion de %s en %s : %s. "
                    "Le fichier WAV est conservé.",
                    filename,
                    self.audio_format,
                    e,
                )

    def close(self) -> None:
        """Ferme tous les fichiers WAV ouverts, puis convertit au format cible."""
        if not self._files:
            return
         
        # 1) Fermer tous les WAV
        for wf in self._files.values():
            try:
                wf.close()
            except Exception:
                pass
        self._files.clear()

        # 2) Conversion (best-effort)
        try:
            self._convert_to_target_format()
        except Exception as e:
            logger.error("Erreur lors de la conversion audio : %s", e)

        if self.audio_format != "wav":
            logger.info(
                "Conversion audio terminée pour la session %s (format: %s, %d octets PCM traités).",
                self.session_id,
                self.audio_format,
                self._bytes_written,
            )
