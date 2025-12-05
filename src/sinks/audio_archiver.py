# src/sinks/audio_archiver.py

import os
import wave
from typing import Dict


class AudioArchiver:
    """
    Enregistre l'audio brut de chaque utilisateur dans un fichier WAV séparé.

    Arborescence :
      base_dir/session_id/user_<user_id>.wav
    """

    def __init__(
        self,
        base_dir: str,
        session_id: str,
        *,
        channels: int,
        sample_width: int,
        sample_rate: int,
    ) -> None:
        self.base_dir = base_dir
        self.session_id = session_id
        self.channels = channels
        self.sample_width = sample_width
        self.sample_rate = sample_rate

        self.session_path = os.path.join(self.base_dir, self.session_id)
        os.makedirs(self.session_path, exist_ok=True)

        self._files: Dict[int, wave.Wave_write] = {}

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

    def close(self) -> None:
        """Ferme tous les fichiers WAV ouverts."""
        for wf in self._files.values():
            try:
                wf.close()
            except Exception:
                pass
        self._files.clear()
