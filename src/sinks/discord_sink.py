# src/sinks/discord_sink.py

import asyncio
import json
import logging
import threading
import time
from datetime import datetime
from queue import Queue, Empty
from typing import Dict, Optional

from discord.sinks.core import Sink, Filters, default_filters

from src.sinks.audio_buffer import AudioBuffer, SpeakerInfo
from src.sinks.transcriber import Transcriber
from src.sinks.audio_archiver import AudioArchiver
from src.sinks.filters import is_subtitle_noise
from src.models.transcription import TranscriptionEvent
from src.config.settings import Settings

logger = logging.getLogger(__name__)


class DiscordSink(Sink):
    """
    Sink Discord qui :
      - récupère l'audio par utilisateur,
      - segmente par silence (via AudioBuffer),
      - transcrit avec Transcriber,
      - archive éventuellement le PCM brut (AudioArchiver),
      - pousse des TranscriptionEvent dans une asyncio.Queue.

    Paramètres principaux :
      - audio_buffer      : instance d'AudioBuffer
      - transcriber       : instance de Transcriber
      - output_queue      : asyncio.Queue où pousser les TranscriptionEvent
      - loop              : event loop asyncio (pour call_soon_threadsafe)
      - settings          : Settings (config globale)
      - guild_id          : ID de la guild Discord
      - player_map        : dict[user_id] -> {"player": str, "character": str}
      - audio_archiver    : optionnel, pour sauvegarder les WAV bruts par user
    """

    def __init__(
        self,
        audio_buffer: AudioBuffer,
        transcriber: Transcriber,
        output_queue: asyncio.Queue,
        loop: asyncio.AbstractEventLoop,
        settings: Settings,
        guild_id: int,
        *,
        log_path: str,
        filters=None,
        player_map: Optional[Dict[int, Dict[str, str]]] = None,
        audio_archiver: Optional[AudioArchiver] = None,
    ) -> None:
        if filters is None:
            filters = default_filters
        
        super().__init__(filters=filters)

        # Config & dépendances
        self.audio_buffer = audio_buffer
        self.transcriber = transcriber
        self.output_queue = output_queue
        self.loop = loop
        self.settings = settings
        self.guild_id = guild_id

        self.log_path = log_path

        self.player_map: Dict[int, Dict[str, str]] = player_map or {}
        self.audio_archiver = audio_archiver

        self.silence_threshold = settings.silence_threshold
        self.enable_subtitle_noise_filter = settings.enable_subtitle_noise_filter

        # Queue pour l'audio brut venant de Discord
        self.voice_queue: "Queue[tuple[int, bytes, float]]" = Queue()

        self.running = True

        # Initialisation des filters du sink Discord
        Filters.__init__(self, **filters)

        # Thread de monitoring audio ↔ transcription
        self.thread = threading.Thread(target=self._monitor_loop, daemon=True)
        self.thread.start()

    #
    # Méthode appelée par Discord pour chaque chunk audio
    #
    @Filters.container
    def write(self, data: bytes, user_id: int) -> None:
        """
        Appelé par Discord quand un utilisateur envoie de l'audio.

        On ne fait rien de lourd ici : on push juste dans une queue
        pour que le thread de monitoring traite ça à son rythme.
        """
        timestamp = time.time()
        self.voice_queue.put((user_id, data, timestamp))

    #
    # Thread de traitement
    #
    def _monitor_loop(self) -> None:
        """
        Boucle principale du sink :

          1. Lis les items de voice_queue (user_id, data, ts).
          2. Archive le PCM brut si audio_archiver est actif.
          3. Ajoute le PCM dans AudioBuffer (par user).
          4. Pour chaque speaker, détecte la fin de phrase via silence_threshold.
          5. Flush -> WAV -> Transcriber -> TranscriptionEvent.
          6. Loggue et pousse l'événement dans output_queue.
        """
        while self.running:
            try:
                try:
                    # On attend max 0.1s pour ne pas bloquer la gestion des timeouts
                    user_id, data, ts = self.voice_queue.get(timeout=0.1)

                    # 1) Archivage brut (optionnel)
                    if self.audio_archiver is not None:
                        try:
                            self.audio_archiver.append(user_id, data)
                        except Exception as e:
                            logger.error("Error while archiving audio: %s", e)

                    # 2) Ajout dans le buffer de segmentation
                    meta = self.player_map.get(user_id, {})
                    player = meta.get("player")
                    character = meta.get("character")

                    self.audio_buffer.add_audio(
                        user_id,
                        data,
                        ts,
                        player=player,
                        character=character,
                    )

                except Empty:
                    # Pas de nouvel audio dans cette fenêtre, on passe
                    pass

                # 3) Traitement des speakers pour voir si le silence est suffisant
                for uid in list(self.audio_buffer.speakers.keys()):
                    if self.audio_buffer.is_speaker_done(
                        uid,
                        silence_threshold=self.silence_threshold,
                    ):
                        wav_io, speaker = self.audio_buffer.flush_speaker(uid)
                        if not wav_io or not speaker:
                            continue

                        # 4) Transcription
                        text = self.transcriber.transcribe_wav(wav_io)

                        # 5) Construction de l'événement de transcription
                        start_dt = datetime.fromtimestamp(speaker.start_time)
                        end_dt = datetime.fromtimestamp(speaker.last_audio_time)

                        is_noise = False
                        cleaned_text = (text or "").strip()
                        if not cleaned_text:
                            continue  # Pas de texte transcrit, on ignore

                        if cleaned_text and self.enable_subtitle_noise_filter:
                            if is_subtitle_noise(cleaned_text):
                                is_noise = True

                        event = TranscriptionEvent(
                            guild_id=self.guild_id,
                            user_id=speaker.user_id,
                            player=speaker.player,
                            character=speaker.character,
                            event_source="Discord",
                            start=start_dt,
                            end=end_dt,
                            text=cleaned_text,
                            is_noise=is_noise,
                            error=None,
                        )

                        # 6) Log + push dans la queue
                        self._log_transcription(event)

            except Exception as e:
                logger.error("Error in DiscordSink monitor loop: %s", e)

    #
    # Logging / sortie des transcriptions
    #
    def _log_transcription(self, event: TranscriptionEvent) -> None:
        """
        Écrit l'événement de transcription dans le fichier de session (JSONL)
        et pousse aussi l'événement dans la output_queue.
        """

        entry = {
            "guild_id": event.guild_id,
            "user_id": event.user_id,
            "player": event.player,
            "character": event.character,
            "event_source": event.event_source,
            "start": event.start.isoformat(),
            "end": event.end.isoformat(),
            "text": event.text or "",
            "is_noise": event.is_noise,
            "error": event.error,
        }

        line = json.dumps(entry, ensure_ascii=False)

        # --- écriture dans le fichier de session ---
        try:
            with open(self.log_path, "a", encoding="utf-8") as f:
                f.write(line + "\n")
        except Exception as e:
            logger.error(
                "Échec lors de l'écriture du log de transcription dans %s : %s",
                self.log_path,
                e,
            )

        # --- push dans la queue en mémoire (pour usage futur éventuel) ---
        try:
            self.output_queue.put_nowait(event)
        except Exception as e:
            logger.error(
                "Échec lors de l'ajout de l'événement transcription dans la queue : %s",
                e,
            )

    #
    # Cleanup
    #
    def cleanup(self) -> None:
        """Appelée par Discord quand le sink doit être fermé."""
        logger.debug("Cleaning up DiscordSink for guild %s.", self.guild_id)
        self.running = False

        # On attend que la boucle se termine proprement
        if self.thread.is_alive():
            self.thread.join(timeout=1.0)

        # Fermer les fichiers audio archivés
        if self.audio_archiver is not None:
            try:
                self.audio_archiver.close()
            except Exception as e:
                logger.error("Error closing AudioArchiver: %s", e)

        # Appel du cleanup de la classe parente
        super().cleanup()
