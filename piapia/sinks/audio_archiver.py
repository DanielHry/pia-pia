# piapia/sinks/audio_archiver.py

import logging
import os
import wave
from typing import Dict

logger = logging.getLogger(__name__)


class AudioArchiver:
    """Per-user audio session archiver.

    `AudioArchiver` writes raw PCM audio for each user into a dedicated WAV file
    during a recording session, then optionally converts each WAV to a target
    format when the session is finalized.

    Design
    ------
    - Streaming-friendly: audio is written incrementally to WAV files during the
      session (simple, reliable, and tolerant to interruptions).
    - Best-effort finalization: on `close()`, all WAV files are closed and then
      converted to the requested output format (e.g., mp3, flac, ogg).
    - Safe cleanup: a source WAV is deleted only if its conversion succeeds. If
      conversion fails (or conversion tooling is unavailable), the WAV is kept.

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
    audio_format:
        Target output format (case-insensitive). Common values include ``"wav"``,
        ``"mp3"``, ``"flac"``, and ``"ogg"``.

    Notes
    -----
    - Conversion uses `pydub` (and therefore FFmpeg). If `pydub` is missing, the
      archiver will log an error and keep WAV files.
    - The archiver tracks the total number of PCM bytes processed across all users,
      useful for diagnostics and logging.
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

    def _convert_to_target_format(self) -> None:
        """Convert all WAV files in the session to the target format via pydub."""
        if self.audio_format == "wav":
            return

        try:
            from pydub import AudioSegment
        except ImportError:
            logger.error(
                "pydub is not installed; cannot convert to %s. "
                "WAV files will be kept.",
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
                    "Converted %s -> %s",
                    filename,
                    target_name,
                )
            except Exception as e:
                logger.error(
                    "Error converting %s to %s: %s. WAV file will be kept.",
                    filename,
                    self.audio_format,
                    e,
                )

    def close(self) -> None:
        """Close all open WAV files, then convert to the target format."""
        if not self._files:
            return
         
        # 1) Close all WAVs
        for wf in self._files.values():
            try:
                wf.close()
            except Exception:
                pass
        self._files.clear()

        # 2) Conversion (best effort)
        try:
            self._convert_to_target_format()
        except Exception as e:
            logger.error("Error during audio conversion: %s", e)

        if self.audio_format != "wav":
            logger.info(
                "Audio conversion completed for session %s (format: %s, %d PCM bytes processed).",
                self.session_id,
                self.audio_format,
                self._bytes_written,
            )
