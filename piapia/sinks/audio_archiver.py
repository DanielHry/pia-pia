# piapia/sinks/audio_archiver.py

import logging
import os
import wave
from typing import Dict

logger = logging.getLogger(__name__)


class AudioArchiver:
    """Per-user audio session archiver.

    `AudioArchiver` writes raw PCM audio for each user into a dedicated WAV file
    during a recording session.

    Design
    ------
    - Streaming-friendly: audio is written incrementally to WAV files during the
      session (simple, reliable, and tolerant to interruptions).
    - Best-effort finalization: on `close()`, all WAV files are closed.

    Output layout
    -------------
    Files are stored under a session directory:

        {base_dir}/{session_id}/user_{user_id}.{format}

    During the session, files are always written as WAV. After `close()`, the final
    artifacts are either:
    - WAV files (when `audio_format="wav"` or conversion cannot be performed), or
    - Converted files alongside removed source WAVs (when conversion succeeds).

    Parameters
    ----------
    base_dir:
        Root directory where session folders are created.
    session_id:
        Unique identifier for the current recording session; used as a folder name.
    channels:
        Number of audio channels written to disk (e.g., 2 for stereo).
    sample_width:
        Sample width in bytes (e.g., 2 for 16-bit PCM).
    sample_rate:
        Sample rate in Hz (e.g., 48000).
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
        if self.audio_format != "wav":
            logger.warning(
                "AudioArchiver: audio_format=%s ignored (bot keeps WAV only). "
                "Use an external conversion script if needed.",
                self.audio_format,
            )
        
        self.session_path = os.path.join(self.base_dir, self.session_id)
        os.makedirs(self.session_path, exist_ok=True)

        self._files: Dict[int, wave.Wave_write] = {}
        self._bytes_written: int = 0

    @property
    def bytes_written(self) -> int:
        """Total number of PCM bytes written since the start of the session."""
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
        Append PCM frames for a given user.

        Called from the audio processing thread (not in the event loop).
        """
        wf = self._get_or_open_file(user_id)
        wf.writeframes(data)
        self._bytes_written += len(data)


    def close(self) -> None:
        """Close all open WAV files."""
        if not self._files:
            return
         
        # 1) Close all WAVs
        for wf in self._files.values():
            try:
                wf.close()
            except Exception:
                pass
        self._files.clear()

        logger.info(
            "Audio finalized for session %s (WAV only, %d PCM bytes written).",
            self.session_id,
            self._bytes_written,
        )