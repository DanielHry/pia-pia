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
    """Sink Discord pour l'enregistrement audio.

    Objectif de cette version : **record-only**.
    Toute la voie "live transcription" a été retirée.

    Compat :
      - conserve la signature historique (audio_buffer/transcriber/output_queue/log_path/mode),
        mais ces paramètres sont ignorés.
      - si `mode="live"` est fourni, on log un warning et on force `record_only`.
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

        # On force record_only : la transcription a été supprimée.
        if mode != "record_only":
            logger.warning(
                "DiscordSink: mode=%s demandé mais non supporté (transcription supprimée). "
                "Bascule en record_only (guild=%s).",
                mode,
                guild_id,
            )
        self.mode: SinkMode = "record_only"

        self.audio_archiver = audio_archiver
        self.session_meta_path = session_meta_path

        # Métadonnées utiles (timestamps) – conservées car peu coûteuses et pratiques.
        self.start_ts: Optional[float] = None
        self.user_first_offset_seconds: Dict[int, float] = {}

        # `write()` peut être appelé depuis un thread voice (Pycord) => lock pour l'archiver.
        self._archiver_lock = threading.Lock()

        if self.audio_archiver is None:
            logger.info(
                "DiscordSink démarré sans AudioArchiver (aucun fichier audio ne sera écrit) (guild=%s).",
                self.guild_id,
            )
        else:
            logger.debug(
                "DiscordSink démarré en mode record_only (guild=%s).", self.guild_id
            )

    @Filters.container
    def write(self, data: bytes, user_id: int) -> None:
        """Appelé par Discord quand un utilisateur envoie de l'audio."""
        if not data:
            return

        ts = time.time()

        # Init start_ts au tout premier paquet (tous users confondus)
        if self.start_ts is None:
            self.start_ts = ts

        # Offset par user au tout premier paquet
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

        # Optionnel : injecter un snapshot du mapping player/character si fourni
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
        """Appelée par Discord quand le sink doit être fermé."""
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
