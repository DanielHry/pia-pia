# piapia/sinks/discord_sink.py

from __future__ import annotations

import os
import json
import logging
import threading
import time
from typing import Any, Dict, Literal, Optional

from discord.sinks.core import Filters, Sink, default_filters

from piapia.config.settings import Settings
from piapia.sinks.audio_archiver import AudioArchiver

logger = logging.getLogger(__name__)

SinkMode = Literal["record_only"]


class DiscordSink(Sink):
    """Audio sink for Discord voice recording.

    `DiscordSink` receives per-user PCM audio frames from a Discord voice client and
    delegates persistence to an `AudioArchiver`. It is designed to be instantiated
    per guild to keep recording state isolated across servers.

    Behavior
    --------
    - Operates in **record-only** mode.
    - If another mode is provided, the sink will emit a warning and fall back to
      `record_only`.
    - Tracks lightweight session metadata (start timestamp and per-user first packet
      offsets) which can be written to a JSON file when `session_meta_path` is set.
    - Thread-safe: `write()` may be called from the voice receive thread; archiver
      operations are protected by a lock.

    Parameters
    ----------
    settings:
        Runtime settings (paths, formats, limits, etc.).
    guild_id:
        Discord guild identifier for which this sink is used.
    mode:
        Requested sink mode. Only ``"record_only"`` is supported; other values are
        coerced to ``"record_only"`` with a warning.
    filters:
        Optional audio filters applied to incoming frames. Defaults to `default_filters`.
    player_map:
        Optional mapping ``user_id -> metadata`` (e.g., display name) used for labeling
        tracks and metadata.
    audio_archiver:
        Component responsible for writing/closing audio files. If None, no audio is
        written, but metadata tracking still occurs.
    session_meta_path:
        Optional path where session metadata (JSON) will be persisted.

    Notes
    -----
    - The sink does not assume it owns the lifecycle of the voice connection; it only
      reacts to frames provided by the caller and finalizes the archiver when requested.
    """

    def __init__(
        self,
        settings: Optional[Settings] = None,
        guild_id: int = 0,
        *,
        mode: SinkMode = "record_only",
        filters=None,
        player_map: Optional[Dict[int, Dict[str, str]]] = None,
        audio_archiver: Optional[AudioArchiver] = None,
        session_meta_path: Optional[str] = None,
    ) -> None:
        if filters is None:
            filters = default_filters

        super().__init__(filters=filters)
        Filters.__init__(self, **filters)

        self.guild_id = guild_id
        self.settings = settings
        self.player_map: Dict[int, Dict[str, str]] = player_map or {}

        # Enforce record_only: this sink only supports recording.
        if mode != "record_only":
            logger.warning(
                "DiscordSink: mode=%s was requested but is not supported. Switching to record_only (guild=%s).",
                mode,
                guild_id,
            )
        self.mode: SinkMode = "record_only"

        self.audio_archiver = audio_archiver
        self.session_meta_path = session_meta_path

        # Useful metadata (timestamps) — kept because it's cheap and handy.
        self.start_ts: Optional[float] = None
        self.user_first_offset_seconds: Dict[int, float] = {}

        # `write()` may be called from a voice thread (Pycord) => lock the archiver.
        self._archiver_lock = threading.Lock()

        if self.audio_archiver is None:
            logger.info(
                "DiscordSink started without AudioArchiver (no audio files will be written) (guild=%s).",
                self.guild_id,
            )
        else:
            logger.debug(
                "DiscordSink started in record_only mode (guild=%s).", self.guild_id
            )

    @Filters.container
    def write(self, data: bytes, user_id: int) -> None:
        """Called by Discord when a user sends audio."""
        if not data:
            return

        ts = time.time()

        # Initialize start_ts on the very first packet received (all users combined).
        if self.start_ts is None:
            self.start_ts = ts

        # Store each user's offset at their first received packet.
        if user_id not in self.user_first_offset_seconds and self.start_ts is not None:
            self.user_first_offset_seconds[user_id] = max(0.0, ts - self.start_ts)

        if self.audio_archiver is None:
            return

        try:
            with self._archiver_lock:
                self.audio_archiver.append(user_id, data)
        except Exception as e:
            logger.error("Error while archiving audio (guild=%s, user=%s): %s", self.guild_id, user_id, e)

    def _write_session_meta_extras(self) -> None:
        """Best-effort: injecte des infos utiles dans session_meta.json."""
        if not self.session_meta_path:
            return

        extras: Dict[str, Any] = {
            "audio_start_ts": self.start_ts,
            "user_first_offset_seconds": {
                str(uid): off for uid, off in self.user_first_offset_seconds.items()
            },
        }

        # Optional: inject a snapshot of the player/character mapping if provided
        if self.player_map:
            extras["player_map"] = {
                str(uid): meta for uid, meta in self.player_map.items()
            }

        data: Dict[str, Any] = {}
        try:
            with open(self.session_meta_path, "r", encoding="utf-8") as f:
                data = json.load(f) or {}
        except FileNotFoundError:
            data = {}
        except Exception as e:
            logger.error("Error reading session meta to merge extras: %s", e)
            data = {}

        cur_extra = data.get("extra")
        if not isinstance(cur_extra, dict):
            cur_extra = {}
        cur_extra.update({k: v for k, v in extras.items() if v is not None})
        data["extra"] = cur_extra

        try:
            os.makedirs(os.path.dirname(self.session_meta_path), exist_ok=True)
            with open(self.session_meta_path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error("Error writing session meta extras: %s", e)

    def cleanup(self) -> None:
        """Called by Discord when the sink must be closed."""
        logger.debug("Cleaning up DiscordSink for guild %s.", self.guild_id)

        # Meta extras : best-effort
        try:
            self._write_session_meta_extras()
        except Exception as e:
            logger.error("Error writing session meta extras during cleanup: %s", e)

        # Close archiver (protégé par lock)
        if self.audio_archiver is not None:
            try:
                with self._archiver_lock:
                    self.audio_archiver.close()
            except Exception as e:
                logger.error("Error closing AudioArchiver: %s", e)

        super().cleanup()
