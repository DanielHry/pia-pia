# src/bot/piapia_bot.py

import asyncio
import logging
import os
import time
import json
from copy import copy
from datetime import datetime
from typing import Any, Dict, List, Optional

import discord
import yaml

from src.bot.helper import BotHelper
from src.config.settings import Settings
from src.models.transcription import TranscriptionEvent
from src.sinks.audio_archiver import AudioArchiver
from src.sinks.audio_buffer import AudioBuffer
from src.sinks.discord_sink import DiscordSink
from src.sinks.transcriber import Transcriber

logger = logging.getLogger(__name__)


class PiaPiaBot(discord.Bot):
    """
    Bot Discord principal (Pia-Pia 🦜) qui orchestre :

      - les connexions voix/guildes (via BotHelper),
      - la création des DiscordSink (AudioBuffer + Transcriber + AudioArchiver),
      - la gestion des transcriptions par guilde,
      - la persistances des player/character (player_map).
    """

    def __init__(self, loop: asyncio.AbstractEventLoop, settings: Settings) -> None:
        self.loop = loop
        self.settings = settings

        intents = discord.Intents.default()
        intents.message_content = True
        intents.members = True
        intents.voice_states = True

        super().__init__(
            intents=intents,
            activity=discord.CustomActivity(name="Pia-Pia écoute vos récits"),
            loop=loop,
        )

        # État par guilde
        self.guild_to_helper: Dict[int, BotHelper] = {}
        self.guild_is_recording: Dict[int, bool] = {}
        self.guild_sinks: Dict[int, DiscordSink] = {}
        self.guild_transcription_queues: Dict[int, asyncio.Queue] = {}
        self.guild_session_log_paths: dict[int, str] = {}

        # Mapping user_id -> { "player": str, "character": str }
        self.player_map: Dict[int, Dict[str, str]] = {}

        # Pour vérifier que le bot est prêt
        self._is_ready: bool = False

        # Chargement de la player_map depuis le fichier si présent
        self._load_player_map_from_file()

    # ------------------------------------------------------------------ #
    # Hooks Discord
    # ------------------------------------------------------------------ #
    async def on_ready(self) -> None:
        logger.info("Connecté à Discord en tant que %s", self.user)
        self._is_ready = True

    # ------------------------------------------------------------------ #
    # Player map
    # ------------------------------------------------------------------ #
    def _load_player_map_from_file(self) -> None:
        """Charge la player_map à partir du fichier YAML indiqué dans les settings."""
        path = self.settings.player_map_file
        if not path:
            logger.info("Aucun PLAYER_MAP_FILE_PATH défini, player_map vide.")
            return

        if not os.path.exists(path):
            logger.info(
                "PLAYER_MAP_FILE_PATH=%s introuvable, player_map initialement vide.",
                path,
            )
            return

        try:
            with open(path, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f) or {}
            if isinstance(data, dict):
                self.player_map.update(data)
                logger.info("Player map chargée depuis %s (%d entrées).", path, len(data))
            else:
                logger.warning(
                    "Le fichier %s ne contient pas un dict YAML valide, player_map ignorée.",
                    path,
                )
        except yaml.YAMLError as e:
            logger.error("Erreur de parsing YAML pour %s : %s", path, e)
        except Exception as e:
            logger.error("Erreur lors de la lecture de %s : %s", path, e)

    async def update_player_map(self, ctx: Any) -> None:
        """
        Met à jour self.player_map pour la guilde :

          user_id -> { "player": nom, "character": display_name }

        Puis persiste dans le fichier YAML si configuré.
        """
        player_map: Dict[int, Dict[str, str]] = {}
        for member in ctx.guild.members:
            player_map[member.id] = {
                "player": member.name,
                "character": member.display_name,
            }

        logger.info(
            "Mise à jour de la player_map pour la guilde %s : %d membres",
            ctx.guild_id,
            len(player_map),
        )

        # On met à jour le dict existant pour que les sinks qui tiennent
        # une référence dessus voient les changements.
        self.player_map.update(player_map)

        path = self.settings.player_map_file
        if path:
            try:
                os.makedirs(os.path.dirname(path), exist_ok=True)
                with open(path, "w", encoding="utf-8") as f:
                    yaml.dump(
                        self.player_map,
                        f,
                        default_flow_style=False,
                        allow_unicode=True,
                    )
                logger.info("Player map sauvegardée dans %s", path)
            except Exception as e:
                logger.error(
                    "Erreur lors de l’écriture de PLAYER_MAP_FILE_PATH=%s : %s",
                    path,
                    e,
                )

    # ------------------------------------------------------------------ #
    # Gestion des sinks par guilde
    # ------------------------------------------------------------------ #
    def _close_and_clean_sink_for_guild(self, guild_id: int) -> None:
        """
        Coupe et nettoie le sink associé à une guilde :

          - appelle sink.cleanup(),
          - enlève le sink des dicts,
          - réinitialise l'état recording.

        ⚠️ On NE supprime PAS la transcription_queue ici,
        pour permettre /generate_pdf après /stop.
        """
        sink = self.guild_sinks.get(guild_id)
        if not sink:
            return

        logger.debug("Arrêt du DiscordSink pour la guilde %s.", guild_id)
        try:
            sink.cleanup()
        except Exception as e:
            logger.error("Erreur lors du cleanup du sink pour la guilde %s : %s", guild_id, e)

        # On enlève seulement le sink, pas la queue
        self.guild_sinks.pop(guild_id, None)

        # On considère que la guilde n'est plus en enregistrement
        self.guild_is_recording[guild_id] = False

    # ------------------------------------------------------------------ #
    # Enregistrement / arrêt
    # ------------------------------------------------------------------ #
    def start_recording(self, ctx: Any) -> None:
        """
        Lance l'enregistrement audio pour la guilde de ctx :

          - crée un DiscordSink,
          - branche le sink sur le VoiceClient,
          - marque la guilde comme "en enregistrement".
        """
        try:
            self._start_discord_sink_for_guild(ctx)
            self.guild_is_recording[ctx.guild_id] = True
        except Exception as e:
            logger.error("Erreur lors du démarrage du DiscordSink : %s", e)

    def _start_discord_sink_for_guild(self, ctx: Any) -> None:
        """
        Création et branchement d'un DiscordSink pour la guilde de ctx.
        """
        guild_id = ctx.guild_id

        if self.guild_sinks.get(guild_id) is not None:
            logger.debug("Un sink est déjà actif pour la guilde %s.", guild_id)
            return

        helper: Optional[BotHelper] = self.guild_to_helper.get(guild_id)
        if helper is None or helper.vc is None:
            logger.error(
                "Aucun VoiceClient disponible pour la guilde %s ; impossible de démarrer l'enregistrement.",
                guild_id,
            )
            return

        vc = helper.vc

        # --- Création du fichier de log de session ---
        transcripts_dir = os.path.join(
            self.settings.logs_dir,
            self.settings.transcripts_subdir,
        )
        os.makedirs(transcripts_dir, exist_ok=True)

        session_ts = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        log_filename = f"{session_ts}_g{guild_id}_session.log"
        session_log_path = os.path.join(transcripts_dir, log_filename)

        # On mémorise ce fichier comme "log de session" pour cette guilde
        self.guild_session_log_paths[guild_id] = session_log_path

        async def on_stop_record_callback(sink: DiscordSink, ctx_any: Any) -> None:
            """
            Callback appelé par Discord lorsque l'enregistrement s'arrête.
            On en profite pour nettoyer le sink.
            """
            logger.debug("%s -> on_stop_record_callback", ctx_any.channel.guild.id)
            self._close_and_clean_sink_for_guild(ctx_any.guild_id)

        # Queue de sortie pour les transcriptions de cette guilde
        output_queue: asyncio.Queue = asyncio.Queue()

        # AudioBuffer & Transcriber pour ce sink
        audio_buffer = AudioBuffer(
            max_speakers=-1,         # illimité, on gère via Discord
            data_limit=200,
            channels=2,
            sample_width=2,
            sample_rate=48000,
        )

        transcriber = Transcriber(
            mode=self.settings.transcription_method,
            language=self.settings.whisper_language,
            model_name=self.settings.whisper_model,
            min_duration=self.settings.min_audio_duration,
            compute_type=self.settings.whisper_compute_type,
            # whisper_params=...  # tu pourras l'exposer aussi si tu veux
        )

        # Optionnel : archivage brut des WAV par utilisateur
        audio_archiver: Optional[AudioArchiver] = None
        if self.settings.archive_audio:
            base_dir = os.path.join(
                self.settings.logs_dir,
                self.settings.audio_archive_subdir,
            )
            os.makedirs(base_dir, exist_ok=True)
            session_id = (
                f"{int(time.time())}_guild_{guild_id}"
            )  # timestamp + id de guilde

            audio_archiver = AudioArchiver(
                base_dir=base_dir,
                session_id=session_id,
                channels=audio_buffer.channels,
                sample_width=audio_buffer.sample_width,
                sample_rate=audio_buffer.sample_rate,
            )

            logger.info(
                "Archivage audio activé pour la guilde %s, session %s.",
                guild_id,
                session_id,
            )

        sink = DiscordSink(
            audio_buffer=audio_buffer,
            transcriber=transcriber,
            output_queue=output_queue,
            loop=self.loop,
            settings=self.settings,
            guild_id=guild_id,
            log_path=session_log_path,
            player_map=self.player_map,
            audio_archiver=audio_archiver,
        )

        # start_recording est fourni par la lib Discord (py-cord / discord.py)
        vc.start_recording(sink, on_stop_record_callback, ctx)

        self.guild_sinks[guild_id] = sink
        self.guild_transcription_queues[guild_id] = output_queue

        logger.debug("DiscordSink démarré pour la guilde %s.", guild_id)

    def stop_recording(self, ctx: Any) -> None:
        """
        Arrête l'enregistrement pour la guilde :

          - stoppe le VoiceClient,
          - marque la guilde comme non-recording.
        Le cleanup du sink est géré par le callback on_stop_record_callback.
        """
        guild_id = ctx.guild_id
        helper = self.guild_to_helper.get(guild_id)
        vc = helper.vc if helper else ctx.guild.voice_client

        if vc:
            self.guild_is_recording[guild_id] = False
            vc.stop_recording()
            logger.debug("Arrêt de l'enregistrement pour la guilde %s.", guild_id)
        else:
            logger.warning(
                "Aucun VoiceClient trouvé pour la guilde %s lors de l'arrêt de l'enregistrement.",
                guild_id,
            )

    def cleanup_sink(self, ctx: discord.ApplicationContext) -> None:
        """Nettoyage manuel du sink pour la guilde donnée."""
        self._close_and_clean_sink_for_guild(ctx.guild_id)

    # ------------------------------------------------------------------ #
    # Transcriptions
    # ------------------------------------------------------------------ #
    async def get_transcription(self, ctx: discord.ApplicationContext) -> List[TranscriptionEvent]:
        """
        Récupère les transcriptions de la DERNIÈRE session pour cette guilde,
        en lisant le fichier de log associé (self.guild_session_log_paths[guild_id]).
        """

        guild_id = ctx.guild_id

        log_path = self.guild_session_log_paths.get(guild_id)
        if not log_path or not os.path.exists(log_path):
            logger.info(
                "Aucun fichier de session de transcription trouvé pour la guilde %s.",
                guild_id,
            )
            return []

        def _read_events_from_file() -> list[TranscriptionEvent]:
            events: list[TranscriptionEvent] = []

            try:
                with open(log_path, "r", encoding="utf-8") as f:
                    for line in f:
                        line = line.strip()
                        if not line:
                            continue

                        try:
                            data = json.loads(line)
                        except json.JSONDecodeError:
                            logger.warning(
                                "Ligne JSON invalide dans %s : %r", log_path, line
                            )
                            continue

                        if data.get("guild_id") != guild_id:
                            continue

                        text = (data.get("text") or "").strip()
                        if not text:
                            # on ignore les lignes vides
                            continue

                        if data.get("is_noise", False):
                            # on ignore les hallucinations / bruit
                            continue

                        try:
                            event = TranscriptionEvent(
                                guild_id=data["guild_id"],
                                user_id=data["user_id"],
                                player=data.get("player"),
                                character=data.get("character"),
                                event_source=data.get("event_source", "Discord"),
                                start=datetime.fromisoformat(data["start"]),
                                end=datetime.fromisoformat(data["end"]),
                                text=text,
                                is_noise=data.get("is_noise", False),
                                error=data.get("error"),
                            )
                            events.append(event)
                        except Exception as e:
                            logger.warning(
                                "Impossible de construire TranscriptionEvent depuis %r : %s",
                                data,
                                e,
                            )
                            continue

            except OSError as e:
                logger.error(
                    "Erreur lors de la lecture du fichier de transcription %s : %s",
                    log_path,
                    e,
                )

            events.sort(key=lambda ev: ev.start)
            return events

        return await asyncio.to_thread(_read_events_from_file)

    # ------------------------------------------------------------------ #
    # Shutdown global
    # ------------------------------------------------------------------ #
    async def stop_and_cleanup(self) -> None:
        """
        Arrête proprement tous les sinks et nettoie les structures internes.
        À appeler lors de l'arrêt du bot.
        """
        try:
            for guild_id, sink in copy(self.guild_sinks).items():
                try:
                    sink.cleanup()
                    logger.debug(
                        "DiscordSink stoppé pour la guilde %s dans stop_and_cleanup.",
                        guild_id,
                    )
                except Exception as e:
                    logger.error(
                        "Erreur lors de l'arrêt du sink pour la guilde %s : %s",
                        guild_id,
                        e,
                    )

            self.guild_sinks.clear()
            self.guild_transcription_queues.clear()
            self.guild_is_recording.clear()

        except Exception as e:
            logger.error("Erreur lors du stop_and_cleanup : %s", e)
        finally:
            logger.info("Cleanup complet des sinks Pia-Pia.")
