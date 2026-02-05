# piapia/bot/piapia_bot.py

import asyncio
import logging
import os
from copy import copy
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

import discord
import yaml

from piapia.bot.helper import BotHelper
from piapia.config.settings import Settings, SUPPORTED_AUDIO_FORMATS
from piapia.domain.sessions import AudioSessionInfo, make_session_id
from piapia.sinks.audio_archiver import AudioArchiver
from piapia.sinks.discord_sink import DiscordSink
from piapia.utils.session_paths import apply_paths_to_session

logger = logging.getLogger(__name__)


class PiaPiaBot(discord.Bot):
    """Bot Discord principal (Pia-Pia 🦜).

    Cette version est **record-only** :
      - connexion vocale
      - enregistrement WAV par utilisateur (AudioArchiver)
      - meta de session (session_meta.json)

    Toute la partie transcription temps réel a été retirée.
    """

    def __init__(self, settings: Settings) -> None:
        self.settings = settings

        intents = discord.Intents.default()
        intents.message_content = True

        super().__init__(
            intents=intents,
            help_command=None,
        )

        # État par guilde
        self.guild_to_helper: Dict[int, BotHelper] = {}

        # Notion de "session" (une seule session active par guilde)
        self.current_session_by_guild: Dict[int, AudioSessionInfo] = {}
        self.current_sink_by_guild: Dict[int, DiscordSink] = {}

        # Mapping guild_id -> user_id -> { "player": str, "character": str }
        self.player_map: Dict[int, Dict[int, Dict[str, str]]] = {}

        # Pour vérifier que le bot est prêt
        self._is_ready: bool = False

        # Timers de durée maximale de session (guild_id -> asyncio.Task)
        self._session_timers: Dict[int, asyncio.Task] = {}

        # Validation du format audio
        fmt = self.settings.audio_format.lower().strip()
        if fmt not in SUPPORTED_AUDIO_FORMATS:
            raise ValueError(
                f"Format audio '{fmt}' non supporté. "
                f"Formats acceptés : {', '.join(sorted(SUPPORTED_AUDIO_FORMATS))}"
            )

        # Chargement des player_maps depuis le dossier si présent
        self._load_player_maps()

    # ------------------------------------------------------------------ #
    # Hooks Discord
    # ------------------------------------------------------------------ #
    async def on_ready(self) -> None:
        logger.info("Connecté à Discord en tant que %s", self.user)
        self._is_ready = True

    # ------------------------------------------------------------------ #
    # Player map
    # ------------------------------------------------------------------ #
    def _load_player_maps(self) -> None:
        """Charge les player_maps depuis le dossier YAML défini dans settings.player_map_dir."""
        player_map_dir = self.settings.player_map_dir
        if not player_map_dir:
            logger.info("PLAYER_MAP_DIR non défini, player_maps initialement vides.")
            return

        dir_path = Path(player_map_dir)
        if not dir_path.is_dir():
            logger.info(
                "PLAYER_MAP_DIR=%s introuvable, player_maps initialement vides.",
                player_map_dir,
            )
            return

        total = 0
        for file in dir_path.glob("guild_*.yaml"):
            try:
                guild_id = int(file.stem.split("_", 1)[1])
            except (IndexError, ValueError):
                logger.warning("Nom de fichier player_map ignoré (format invalide) : %s", file.name)
                continue

            try:
                data = yaml.safe_load(file.read_text(encoding="utf-8")) or {}
                if not isinstance(data, dict):
                    logger.warning(
                        "Le fichier YAML %s ne contient pas un dict : %s",
                        file,
                        type(data),
                    )
                    continue

                normalized: Dict[int, Dict[str, str]] = {}
                for k, v in data.items():
                    try:
                        uid = int(k)
                    except Exception:
                        continue
                    if isinstance(v, dict):
                        normalized[uid] = {
                            "player": str(v.get("player", "")),
                            "character": str(v.get("character", "")),
                        }

                self.player_map[guild_id] = normalized
                total += len(normalized)
                logger.debug(
                    "Player map chargée pour la guilde %s depuis %s (%d entrées).",
                    guild_id,
                    file.name,
                    len(normalized),
                )
            except Exception as e:
                logger.error(
                    "Erreur lors du chargement de la player_map depuis %s : %s", file, e
                )

        logger.info(
            "Player maps chargées depuis %s : %d guildes, %d entrées au total.",
            player_map_dir,
            len(self.player_map),
            total,
        )

    async def update_player_map(self, ctx: Any) -> None:
        """Met à jour la player_map de la guilde, puis persiste dans le YAML si configuré."""
        guild_id = ctx.guild_id
        guild_map: Dict[int, Dict[str, str]] = {}
        for member in ctx.guild.members:
            guild_map[member.id] = {
                "player": member.name,
                "character": member.display_name,
            }

        logger.info(
            "Mise à jour de la player_map pour la guilde %s : %d membres",
            guild_id,
            len(guild_map),
        )

        self.player_map[guild_id] = guild_map

        player_map_dir = self.settings.player_map_dir
        if player_map_dir:
            try:
                dir_path = Path(player_map_dir)
                dir_path.mkdir(parents=True, exist_ok=True)

                file_path = dir_path / f"guild_{guild_id}.yaml"
                with open(file_path, "w", encoding="utf-8") as f:
                    yaml.dump(
                        guild_map,
                        f,
                        default_flow_style=False,
                        allow_unicode=True,
                    )
                logger.info("Player map sauvegardée dans %s", file_path)
            except Exception as e:
                logger.error(
                    "Erreur lors de la sauvegarde de la player_map pour la guilde %s : %s",
                    guild_id,
                    e,
                )

    # ------------------------------------------------------------------ #
    # Gestion des sinks / sessions
    # ------------------------------------------------------------------ #
    def _finalize_session_meta_for_guild(self, guild_id: int) -> None:
        """Marque ended_at et sauvegarde session_meta.json si une session existe."""
        session = self.current_session_by_guild.get(guild_id)
        if session is None:
            return

        if session.ended_at is None:
            session.ended_at = datetime.now(timezone.utc)

        try:
            session.save_json()  # utilise session.meta_path
            logger.debug("Session meta sauvegardée: %s", session.meta_path)
        except Exception as e:
            logger.error(
                "Erreur lors de la sauvegarde de session_meta pour la guilde %s (%s) : %s",
                guild_id,
                session.meta_path,
                e,
            )

    # ------------------------------------------------------------------ #
    # Timer de durée maximale de session
    # ------------------------------------------------------------------ #
    def _start_session_timer(self, guild_id: int, channel_id: int) -> None:
        """Lance un timer async qui arrêtera la session après la durée max configurée."""
        max_minutes = self.settings.max_session_duration_minutes
        if max_minutes <= 0:
            return

        self._cancel_session_timer(guild_id)
        task = asyncio.create_task(
            self._session_timeout_handler(guild_id, channel_id)
        )
        self._session_timers[guild_id] = task
        logger.debug(
            "Timer de session démarré pour la guilde %s (%d min).",
            guild_id,
            max_minutes,
        )

    def _cancel_session_timer(self, guild_id: int) -> None:
        """Annule le timer de durée max pour une guilde (si actif)."""
        task = self._session_timers.pop(guild_id, None)
        if task and not task.done():
            task.cancel()

    async def _session_timeout_handler(self, guild_id: int, channel_id: int) -> None:
        """Coroutine de timeout : avertissement 5 min avant, puis arrêt automatique."""
        max_minutes = self.settings.max_session_duration_minutes
        warning_delay = 5  # minutes

        try:
            # Phase 1 : attendre jusqu'à 5 min avant la fin
            wait_before_warning = max(0, (max_minutes - warning_delay) * 60)
            if wait_before_warning > 0:
                await asyncio.sleep(wait_before_warning)

                # Envoyer un avertissement
                channel = self.get_channel(channel_id)
                if channel:
                    await channel.send(
                        f"⏳ Attention ! La session s'arrêtera automatiquement dans "
                        f"{warning_delay} minutes (limite de {max_minutes} min). "
                        f"Faites `/stop` puis `/record` pour relancer."
                    )

                await asyncio.sleep(warning_delay * 60)
            else:
                # Durée max ≤ 5 min : on attend juste la durée totale
                await asyncio.sleep(max_minutes * 60)

            # Phase 2 : arrêt automatique
            logger.info(
                "Durée maximale atteinte pour la guilde %s (%d min), arrêt automatique.",
                guild_id,
                max_minutes,
            )

            channel = self.get_channel(channel_id)
            if channel:
                await channel.send(
                    f"⏰ Durée maximale de {max_minutes} minutes atteinte. "
                    f"Session arrêtée automatiquement. Les fichiers audio sont sauvegardés."
                )

            # Stopper l'enregistrement via le VoiceClient
            helper = self.guild_to_helper.get(guild_id)
            vc = helper.vc if (helper and helper.vc) else None
            if vc:
                try:
                    vc.stop_recording()
                except Exception as e:
                    logger.error(
                        "Erreur lors de l'arrêt automatique pour la guilde %s : %s",
                        guild_id,
                        e,
                    )
                    self._close_and_clean_sink_for_guild(guild_id)
            else:
                self._close_and_clean_sink_for_guild(guild_id)

        except asyncio.CancelledError:
            # Timer annulé normalement (session stoppée manuellement)
            pass

    def _close_and_clean_sink_for_guild(self, guild_id: int) -> None:
        """Coupe et nettoie le sink associé à une guilde (best effort)."""
        # 0) Annuler le timer de durée max
        self._cancel_session_timer(guild_id)

        # 1) Finaliser la meta AVANT cleanup pour que le sink puisse y merger ses extras.
        try:
            self._finalize_session_meta_for_guild(guild_id)
        except Exception as e:
            logger.error("Erreur lors de la finalisation meta (guild %s) : %s", guild_id, e)

        # 2) Cleanup sink (ferme WAV + écrit extras)
        sink = self.current_sink_by_guild.get(guild_id)
        if sink:
            logger.debug("Arrêt du DiscordSink pour la guilde %s.", guild_id)
            try:
                sink.cleanup()
            except Exception as e:
                logger.error(
                    "Erreur lors du cleanup du sink pour la guilde %s : %s",
                    guild_id,
                    e,
                )

        # 3) Nettoyage état
        self.current_sink_by_guild.pop(guild_id, None)
        self.current_session_by_guild.pop(guild_id, None)

    def _create_session_for_guild(
        self,
        guild_id: int,
        *,
        mode: str,
        label: Optional[str] = None,
    ) -> AudioSessionInfo:
        """Crée une AudioSessionInfo et remplit les chemins standardisés."""
        session_id = make_session_id(guild_id)
        session = AudioSessionInfo(
            session_id=session_id,
            guild_id=guild_id,
            mode=mode,  # type: ignore[arg-type]
            started_at=datetime.now(timezone.utc),
            ended_at=None,
            label=label,
        )

        # Remplit base_dir/audio_dir/meta_path + mkdir
        apply_paths_to_session(session=session, settings=self.settings, create=True)

        # Snapshot (best effort) du mapping player/character à l'instant T
        guild_map = self.player_map.get(guild_id, {})
        for uid, meta in guild_map.items():
            try:
                user_id = int(uid)
            except Exception:
                continue
            session.add_or_update_player(
                user_id,
                player=meta.get("player"),
                character=meta.get("character"),
            )

        return session

    def _start_sink_for_session(
        self,
        ctx: Any,
        session: AudioSessionInfo,
        *,
        force_archive: bool,
    ) -> None:
        """Démarre un DiscordSink (record-only) pour une session déjà créée."""
        guild_id = ctx.guild_id

        helper: Optional[BotHelper] = self.guild_to_helper.get(guild_id)
        vc = helper.vc if (helper and helper.vc) else ctx.guild.voice_client
        if vc is None:
            raise RuntimeError(
                f"Aucun VoiceClient disponible pour la guilde {guild_id} ; impossible de démarrer la session."
            )

        async def on_stop_record_callback(sink: DiscordSink, ctx_any: Any) -> None:
            """Callback appelé par Discord lorsque l'enregistrement s'arrête."""
            gid = ctx_any.guild_id
            logger.debug("%s -> on_stop_record_callback", gid)

            # Annuler le timer de durée max
            self._cancel_session_timer(gid)

            # On “détache” l’état dans la loop (thread-safe)
            sink_obj = self.current_sink_by_guild.pop(gid, None)

            # Finalisation + cleanup en thread (bloquant)
            await asyncio.to_thread(self._finalize_session_meta_for_guild, gid)
            if sink_obj:
                await asyncio.to_thread(sink_obj.cleanup)

            # Session terminée => on la retire
            self.current_session_by_guild.pop(gid, None)

        audio_archiver: Optional[AudioArchiver] = None
        if force_archive:
            base_dir = os.path.join(self.settings.logs_dir, self.settings.audio_sessions_subdir)
            os.makedirs(base_dir, exist_ok=True)

            # Discord Voice Receive (py-cord) : PCM 48kHz, 16-bit, stéréo
            audio_archiver = AudioArchiver(
                base_dir=base_dir,
                session_id=session.session_id,
                channels=2,
                sample_width=2,
                sample_rate=48000,
                audio_format=self.settings.audio_format,
            )
            logger.info(
                "Archivage audio activé pour la guilde %s, session %s (format: %s).",
                guild_id,
                session.session_id,
                self.settings.audio_format,
            )

        sink = DiscordSink(
            settings=self.settings,
            guild_id=guild_id,
            mode=session.mode,
            session_meta_path=session.meta_path,
            player_map=self.player_map.get(guild_id, {}),
            audio_archiver=audio_archiver,
        )

        vc.start_recording(sink, on_stop_record_callback, ctx)

        # Stockage état
        self.current_sink_by_guild[guild_id] = sink
        self.current_session_by_guild[guild_id] = session

        # Lancer le timer de durée max
        self._start_session_timer(guild_id, ctx.channel_id)

        logger.debug("Session %s démarrée pour la guilde %s.", session.session_id, guild_id)

    # ------------------------------------------------------------------ #
    # API sessions
    # ------------------------------------------------------------------ #
    def start_record_only_session(self, ctx: Any, label: Optional[str] = None) -> None:
        """Démarre une session 'record_only' : archivage audio sans transcription."""
        guild_id = ctx.guild_id

        if self.current_sink_by_guild.get(guild_id) is not None:
            logger.warning("Une session est déjà active pour la guilde %s.", guild_id)
            return

        session = self._create_session_for_guild(guild_id, mode="record_only", label=label)

        try:
            self._start_sink_for_session(
                ctx,
                session,
                force_archive=True,  # /record force l'archivage
            )
        except Exception as e:
            logger.error("Erreur lors du démarrage de la session record_only : %s", e)

    def stop_current_session(self, ctx: Any) -> None:
        """Arrête la session en cours (si active), finalise session_meta.json."""
        guild_id = ctx.guild_id

        helper = self.guild_to_helper.get(guild_id)
        vc = helper.vc if (helper and helper.vc) else ctx.guild.voice_client

        if vc:
            try:
                vc.stop_recording()
                logger.debug("Arrêt de la session en cours pour la guilde %s.", guild_id)
                return
            except Exception as e:
                logger.error(
                    "Erreur lors de vc.stop_recording() pour la guilde %s : %s",
                    guild_id,
                    e,
                )

        # Fallback
        self._close_and_clean_sink_for_guild(guild_id)

    async def force_disconnect(self, ctx: Any) -> None:
        """Déconnecte du vocal et stoppe la session si besoin."""
        guild_id = ctx.guild_id

        helper = self.guild_to_helper.get(guild_id)
        vc = helper.vc if (helper and helper.vc) else ctx.guild.voice_client

        if self.current_sink_by_guild.get(guild_id) is not None:
            self.stop_current_session(ctx)

        if vc:
            try:
                await vc.disconnect()
            except Exception as e:
                logger.error(
                    "Erreur lors de vc.disconnect() pour la guilde %s : %s", guild_id, e
                )

        if helper:
            helper.guild_id = None
            helper.set_vc(None)

        self.guild_to_helper.pop(guild_id, None)

        # Au cas où le callback ne serait pas passé
        self._close_and_clean_sink_for_guild(guild_id)

    # ------------------------------------------------------------------ #
    # Shutdown global
    # ------------------------------------------------------------------ #
    async def close(self) -> None:
        """Override : cleanup des sinks avant de fermer la connexion Discord."""
        try:
            # On copie pour éviter de modifier le dict pendant l’itération
            for guild_id, sink in copy(self.current_sink_by_guild).items():
                # Best-effort : finaliser la session
                try:
                    self._finalize_session_meta_for_guild(guild_id)
                except Exception as e:
                    logger.error("Erreur finalisation meta (guild %s) : %s", guild_id, e)

                try:
                    await asyncio.to_thread(sink.cleanup)
                    logger.debug(
                        "DiscordSink stoppé pour la guilde %s dans close.",
                        guild_id,
                    )
                except Exception as e:
                    logger.error(
                        "Erreur lors de l'arrêt du sink pour la guilde %s : %s",
                        guild_id,
                        e,
                    )

            self.current_sink_by_guild.clear()
            self.current_session_by_guild.clear()

        except Exception as e:
            logger.error("Erreur lors du close : %s", e)
        finally:
            logger.info("Cleanup complet des sinks Pia-Pia.")

        await super().close()

    # ------------------------------------------------------------------ #
    # 4. Events supplémentaires
    # ------------------------------------------------------------------ #
    async def on_voice_state_update(
            self,
            member: discord.Member,
            before: discord.VoiceState,
            after: discord.VoiceState,
        ) -> None:
        """
        Si Pia-Pia quitte un salon vocal (kick, déplacement, déco...),
        on nettoie son état pour cette guilde.
        """
        # On attend que bot.user soit dispo
        if not self.user:
            return

        # Est-ce que c'est Pia-Pia dont l'état a changé ?
        if member.id == self.user.id:
            # Pia-Pia n'est plus dans un salon vocal
            if after.channel is None and before.channel is not None:
                guild_id = before.channel.guild.id

                helper = self.guild_to_helper.get(guild_id)
                if helper:
                    helper.set_vc(None)
                    self.guild_to_helper.pop(guild_id, None)

                self._close_and_clean_sink_for_guild(guild_id)
                logger.info(
                    "Pia-Pia a quitté le vocal de la guilde %s, cleanup effectué.",
                    guild_id,
                )