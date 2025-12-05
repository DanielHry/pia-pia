# src/sinks/audio_buffer.py

from collections import deque
from dataclasses import dataclass
from typing import Deque, Dict, Optional, Tuple
import io
import time
import wave


@dataclass
class SpeakerInfo:
    user_id: int
    player: Optional[str]
    character: Optional[str]
    start_time: float
    last_audio_time: float


class AudioBuffer:
    """
    Gère les buffers audio par utilisateur et détecte la fin de parole
    en fonction d'un seuil de silence.

    - max_speakers < 0 : nombre illimité de speakers
    - data_limit : nombre max de chunks PCM conservés par speaker
    """

    def __init__(
        self,
        max_speakers: int = -1,
        data_limit: int = 200,
        *,
        channels: int = 2,
        sample_width: int = 2,   # bytes per sample (2 = 16 bits)
        sample_rate: int = 48000
    ) -> None:
        self.max_speakers = max_speakers
        self.data_limit = data_limit

        self.channels = channels
        self.sample_width = sample_width
        self.sample_rate = sample_rate

        self.speakers: Dict[int, SpeakerInfo] = {}       # user_id -> SpeakerInfo
        self.buffers: Dict[int, Deque[bytes]] = {}       # user_id -> deque of PCM bytes

    def add_audio(
        self,
        user_id: int,
        data: bytes,
        timestamp: float,
        *,
        player: Optional[str] = None,
        character: Optional[str] = None
    ) -> None:
        """Ajoute des données PCM pour un utilisateur donné."""
        if user_id not in self.speakers:
            if self.max_speakers > 0 and len(self.speakers) >= self.max_speakers:
                # Limite de speakers atteinte, on ignore les nouveaux
                return

            self.speakers[user_id] = SpeakerInfo(
                user_id=user_id,
                player=player,
                character=character,
                start_time=timestamp,
                last_audio_time=timestamp,
            )
            self.buffers[user_id] = deque(maxlen=self.data_limit)

        self.buffers[user_id].append(data)
        self.speakers[user_id].last_audio_time = timestamp

    def is_speaker_done(self, user_id: int, silence_threshold: float = 1.2) -> bool:
        """Retourne True si l'utilisateur est silencieux depuis 'silence_threshold' secondes."""
        info = self.speakers.get(user_id)
        if info is None:
            return False

        return (time.time() - info.last_audio_time) >= silence_threshold

    def flush_speaker(self, user_id: int) -> Tuple[Optional[io.BytesIO], Optional[SpeakerInfo]]:
        """
        Convertit le buffer PCM d'un speaker en WAV (BytesIO) et
        supprime le speaker des structures internes.
        """
        info = self.speakers.get(user_id)
        if info is None:
            return None, None

        pcm_chunks = list(self.buffers.get(user_id, []))
        if not pcm_chunks:
            # Rien à transcrire
            del self.speakers[user_id]
            del self.buffers[user_id]
            return None, info

        wav_io = io.BytesIO()
        with wave.open(wav_io, "wb") as wf:
            wf.setnchannels(self.channels)
            wf.setsampwidth(self.sample_width)
            wf.setframerate(self.sample_rate)
            for chunk in pcm_chunks:
                wf.writeframes(chunk)

        wav_io.seek(0)

        # Cleanup
        del self.speakers[user_id]
        del self.buffers[user_id]

        return wav_io, info
