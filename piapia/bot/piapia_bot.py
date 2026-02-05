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
    """Pia-Pia Discord bot.

    `PiaPiaBot` is the main coordinator for per-guild voice recording. It manages
    voice connection helpers, recording sessions, audio sinks/archiving, and session
    metadata, while exposing a small API used by the slash-command cogs.

    High-level responsibilities
    ---------------------------
    - Maintain per-guild voice state via `BotHelper` (VoiceClient lifecycle).
    - Start/stop a single active recording session per guild.
    - Create and persist session metadata (`session_meta.json`) through `AudioSessionInfo`.
    - Record per-user audio through `DiscordSink` and optionally archive it via `AudioArchiver`.
    - Load and persist per-guild player mappings (YAML) to label tracks/metadata.
    - Enforce an optional maximum session duration with an async timer (warning + auto-stop).

    Per-guild state model
    ---------------------
    - `guild_to_helper`: maps guild_id -> `BotHelper` (voice connection holder).
    - `current_session_by_guild`: maps guild_id -> `AudioSessionInfo` (one active session).
    - `current_sink_by_guild`: maps guild_id -> `DiscordSink` (active recorder).
    - `player_map`: maps guild_id -> user_id -> { "player": str, "character": str }.

    Session lifecycle
    -----------------
    1) Create a session id and prepare output paths (directories + meta path).
    2) Snapshot the current `player_map` into session metadata.
    3) Start Discord voice recording with a `DiscordSink` and (when enabled) an `AudioArchiver`.
    4) Optionally run a max-duration timer that warns shortly before the limit, then stops.
    5) On stop (manual or automatic): finalize metadata, clean up the sink, and detach state.

    Configuration
    -------------
    Behavior and output paths are driven by `Settings`, including:
    - `audio_format`
    - `logs_dir` / `audio_sessions_subdir`
    - `player_map_dir`
    - `max_session_duration_minutes`

    Reliability notes
    -----------------
    Cleanup and conversion are best-effort. On shutdown, the bot attempts to finalize
    session metadata and clean all active sinks before closing the Discord connection.
    """

    def __init__(self, settings: Settings) -> None:
        self.settings = settings

        intents = discord.Intents.default()
        #intents.message_content = True

        super().__init__(
            intents=intents,
            help_command=None,
        )

        # Per-guild state
        self.guild_to_helper: Dict[int, BotHelper] = {}

        # Session state (only one active session per guild)
        self.current_session_by_guild: Dict[int, AudioSessionInfo] = {}
        self.current_sink_by_guild: Dict[int, DiscordSink] = {}

        # Mapping guild_id -> user_id -> { "player": str, "character": str }
        self.player_map: Dict[int, Dict[int, Dict[str, str]]] = {}

        # Readiness flag
        self._is_ready: bool = False

        # Max session duration timers (guild_id -> asyncio.Task)
        self._session_timers: Dict[int, asyncio.Task] = {}

        # Audio format validation
        fmt = self.settings.audio_format.lower().strip()
        if fmt not in SUPPORTED_AUDIO_FORMATS:
            raise ValueError(
                f"Audio format '{fmt}' is not supported. "
                f"Accepted formats: {', '.join(sorted(SUPPORTED_AUDIO_FORMATS))}"
            )

        # Load player maps from disk (if configured)
        self._load_player_maps()

    # ------------------------------------------------------------------ #
    # Hooks Discord
    # ------------------------------------------------------------------ #
    async def on_ready(self) -> None:
        logger.info("Connected to Discord as %s", self.user)
        self._is_ready = True

    # ------------------------------------------------------------------ #
    # Player map
    # ------------------------------------------------------------------ #
    def _load_player_maps(self) -> None:
        """Load player maps from the YAML folder defined in settings.player_map_dir."""
        player_map_dir = self.settings.player_map_dir
        if not player_map_dir:
            logger.info("PLAYER_MAP_DIR is not set; player maps start empty.")
            return

        dir_path = Path(player_map_dir)
        if not dir_path.is_dir():
            logger.info(
                "PLAYER_MAP_DIR=%s not found; player maps start empty.",
                player_map_dir,
            )
            return

        total = 0
        for file in dir_path.glob("guild_*.yaml"):
            try:
                guild_id = int(file.stem.split("_", 1)[1])
            except (IndexError, ValueError):
                logger.warning("Ignoring player_map filename (invalid format): %s", file.name)
                continue

            try:
                data = yaml.safe_load(file.read_text(encoding="utf-8")) or {}
                if not isinstance(data, dict):
                    logger.warning(
                        "YAML file %s does not contain a dict: %s",
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
                    "Loaded player map for guild %s from %s (%d entries).",
                    guild_id,
                    file.name,
                    len(normalized),
                )
            except Exception as e:
                logger.error(
                    "Error loading player_map from %s : %s", file, e
                )

        logger.info(
            "Player maps loaded from %s: %d guild(s), %d total entries.",
            player_map_dir,
            len(self.player_map),
            total,
        )

    async def update_player_map(self, ctx: Any) -> None:
        """Update the guild player_map and persist it to YAML if configured."""
        guild_id = ctx.guild_id
        guild_map: Dict[int, Dict[str, str]] = {}
        for member in ctx.guild.members:
            guild_map[member.id] = {
                "player": member.name,
                "character": member.display_name,
            }

        logger.info(
            "Updating player_map for guild %s: %d members",
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
                logger.info("Player map saved to %s", file_path)
            except Exception as e:
                logger.error(
                    "Error saving player_map for guild %s : %s",
                    guild_id,
                    e,
                )

    # ------------------------------------------------------------------ #
    # Sink / session management
    # ------------------------------------------------------------------ #
    def _finalize_session_meta_for_guild(self, guild_id: int) -> None:
        """Set ended_at and save session_meta.json if a session exists."""
        session = self.current_session_by_guild.get(guild_id)
        if session is None:
            return

        if session.ended_at is None:
            session.ended_at = datetime.now(timezone.utc)

        try:
            session.save_json()  # uses session.meta_path
            logger.debug("Session meta saved: %s", session.meta_path)
        except Exception as e:
            logger.error(
                "Error saving session_meta for guild %s (%s) : %s",
                guild_id,
                session.meta_path,
                e,
            )

    # ------------------------------------------------------------------ #
    # Max session duration timer
    # ------------------------------------------------------------------ #
    def _start_session_timer(self, guild_id: int, channel_id: int) -> None:
        """Start an async timer that will stop the session after the configured max duration."""
        max_minutes = self.settings.max_session_duration_minutes
        if max_minutes <= 0:
            return

        self._cancel_session_timer(guild_id)
        task = asyncio.create_task(
            self._session_timeout_handler(guild_id, channel_id)
        )
        self._session_timers[guild_id] = task
        logger.debug(
            "Session timer started for guild %s (%d min).",
            guild_id,
            max_minutes,
        )

    def _cancel_session_timer(self, guild_id: int) -> None:
        """Cancel the max-duration timer for a guild (if active)."""
        task = self._session_timers.pop(guild_id, None)
        if task and not task.done():
            task.cancel()

    async def _session_timeout_handler(self, guild_id: int, channel_id: int) -> None:
        """Timeout coroutine: warn 5 minutes before, then stop automatically."""
        max_minutes = self.settings.max_session_duration_minutes
        warning_delay = 5  # minutes

        try:
            # Phase 1: wait until 5 minutes before the end
            wait_before_warning = max(0, (max_minutes - warning_delay) * 60)
            if wait_before_warning > 0:
                await asyncio.sleep(wait_before_warning)

                # Send a warning
                channel = self.get_channel(channel_id)
                if channel:
                    await channel.send(
                        f"⏳ Heads up! This session will stop automatically in "
                        f"{warning_delay} minutes (limit: {max_minutes} min). "
                        f"Use `/stop` then `/record` to start a new one."
                    )

                await asyncio.sleep(warning_delay * 60)
            else:
                # Max duration ≤ 5 min: wait for the full duration
                await asyncio.sleep(max_minutes * 60)

            # Phase 2: automatic stop
            logger.info(
                "Maximum duration reached for guild %s (%d min), stopping automatically.",
                guild_id,
                max_minutes,
            )

            channel = self.get_channel(channel_id)
            if channel:
                await channel.send(
                    f"⏰ Maximum duration of {max_minutes} minutes reached. "
                    f"Session stopped automatically. Audio files are saved."
                )

            # Stop recording via the VoiceClient
            helper = self.guild_to_helper.get(guild_id)
            vc = helper.vc if (helper and helper.vc) else None
            if vc:
                try:
                    vc.stop_recording()
                except Exception as e:
                    logger.error(
                        "Error during automatic stop for guild %s: %s",
                        guild_id,
                        e,
                    )
                    self._close_and_clean_sink_for_guild(guild_id)
            else:
                self._close_and_clean_sink_for_guild(guild_id)

        except asyncio.CancelledError:
            # Timer cancelled normally (session stopped manually)
            pass

    def _close_and_clean_sink_for_guild(self, guild_id: int) -> None:
        """Stop and clean up the sink associated with a guild (best effort)."""
        # 0) Cancel the max-duration timer
        self._cancel_session_timer(guild_id)

        # 1) Finalize meta BEFORE cleanup so the sink can merge its extras.
        try:
            self._finalize_session_meta_for_guild(guild_id)
        except Exception as e:
            logger.error("Error while finalizing meta (guild %s): %s", guild_id, e)

        # 2) Sink cleanup (close WAV + write extras)
        sink = self.current_sink_by_guild.get(guild_id)
        if sink:
            logger.debug("Stopping DiscordSink for guild %s.", guild_id)
            try:
                sink.cleanup()
            except Exception as e:
                logger.error(
                    "Error during sink cleanup for guild %s: %s",
                    guild_id,
                    e,
                )

        # 3) State cleanup
        self.current_sink_by_guild.pop(guild_id, None)
        self.current_session_by_guild.pop(guild_id, None)

    def _create_session_for_guild(
        self,
        guild_id: int,
        *,
        mode: str,
        label: Optional[str] = None,
    ) -> AudioSessionInfo:
        """Create an AudioSessionInfo and fill standardized paths."""
        session_id = make_session_id(guild_id)
        session = AudioSessionInfo(
            session_id=session_id,
            guild_id=guild_id,
            mode=mode,  # type: ignore[arg-type]
            started_at=datetime.now(timezone.utc),
            ended_at=None,
            label=label,
        )

        # Fill base_dir/audio_dir/meta_path + mkdir
        apply_paths_to_session(session=session, settings=self.settings, create=True)

        # Snapshot (best effort) of the player/character mapping at time T
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
        """Start a DiscordSink (record-only) for an already created session."""
        guild_id = ctx.guild_id

        helper: Optional[BotHelper] = self.guild_to_helper.get(guild_id)
        vc = helper.vc if (helper and helper.vc) else ctx.guild.voice_client
        if vc is None:
            raise RuntimeError(
                f"No VoiceClient available for guild {guild_id}; cannot start the session."
            )

        async def on_stop_record_callback(sink: DiscordSink, ctx_any: Any) -> None:
            """Callback invoked by Discord when the recording stops."""
            gid = ctx_any.guild_id
            logger.debug("%s -> on_stop_record_callback", gid)

            # Cancel the max-duration timer
            self._cancel_session_timer(gid)

            # Detach state in the loop (thread-safe)
            sink_obj = self.current_sink_by_guild.pop(gid, None)

            # Finalize + cleanup in a thread (blocking)
            await asyncio.to_thread(self._finalize_session_meta_for_guild, gid)
            if sink_obj:
                await asyncio.to_thread(sink_obj.cleanup)

            # Session ended => remove it
            self.current_session_by_guild.pop(gid, None)

        audio_archiver: Optional[AudioArchiver] = None
        if force_archive:
            base_dir = os.path.join(self.settings.logs_dir, self.settings.audio_sessions_subdir)
            os.makedirs(base_dir, exist_ok=True)

            # Discord Voice Receive (py-cord): PCM 48kHz, 16-bit, stereo
            audio_archiver = AudioArchiver(
                base_dir=base_dir,
                session_id=session.session_id,
                channels=2,
                sample_width=2,
                sample_rate=48000,
                audio_format=self.settings.audio_format,
            )
            logger.info(
                "Audio archiving enabled for guild %s, session %s (format: %s).",
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

        # Store state
        self.current_sink_by_guild[guild_id] = sink
        self.current_session_by_guild[guild_id] = session

        # Start the max-duration timer
        self._start_session_timer(guild_id, ctx.channel_id)

        logger.debug("Session %s started for guild %s.", session.session_id, guild_id)

    # ------------------------------------------------------------------ #
    # API sessions
    # ------------------------------------------------------------------ #
    def start_record_session(self, ctx: Any, label: Optional[str] = None) -> None:
        """Start a recording session (one active session per guild)."""
        guild_id = ctx.guild_id

        if self.current_sink_by_guild.get(guild_id) is not None:
            logger.warning("A session is already active for guild %s.", guild_id)
            return

        session = self._create_session_for_guild(guild_id, mode="record_only", label=label)

        try:
            self._start_sink_for_session(
                ctx,
                session,
                force_archive=True,  # /record forces archiving
            )
        except Exception as e:
            logger.error("Error while starting record_only session: %s", e)

    def stop_current_session(self, ctx: Any) -> None:
        """Stop the current session (if active) and finalize session_meta.json."""
        guild_id = ctx.guild_id

        helper = self.guild_to_helper.get(guild_id)
        vc = helper.vc if (helper and helper.vc) else ctx.guild.voice_client

        if vc:
            try:
                vc.stop_recording()
                logger.debug("Stopping current session for guild %s.", guild_id)
                return
            except Exception as e:
                logger.error(
                    "Error while calling vc.stop_recording() for guild %s : %s",
                    guild_id,
                    e,
                )

        # Fallback
        self._close_and_clean_sink_for_guild(guild_id)

    async def force_disconnect(self, ctx: Any) -> None:
        """Disconnect from voice and stop the session if needed."""
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
                    "Error while calling vc.disconnect() for guild %s : %s", guild_id, e
                )

        if helper:
            helper.guild_id = None
            helper.set_vc(None)

        self.guild_to_helper.pop(guild_id, None)

        # Just in case the callback did not fire
        self._close_and_clean_sink_for_guild(guild_id)

    # ------------------------------------------------------------------ #
    # Shutdown global
    # ------------------------------------------------------------------ #
    async def close(self) -> None:
        """Override: clean up sinks before closing the Discord connection."""
        try:
            # Copy to avoid mutating the dict during iteration
            for guild_id, sink in copy(self.current_sink_by_guild).items():
                # Best effort: finalize the session
                try:
                    self._finalize_session_meta_for_guild(guild_id)
                except Exception as e:
                    logger.error("Error finalizing meta (guild %s): %s", guild_id, e)

                try:
                    await asyncio.to_thread(sink.cleanup)
                    logger.debug(
                        "DiscordSink stopped for guild %s in close.",
                        guild_id,
                    )
                except Exception as e:
                    logger.error(
                        "Error stopping the sink for guild %s: %s",
                        guild_id,
                        e,
                    )

            self.current_sink_by_guild.clear()
            self.current_session_by_guild.clear()

        except Exception as e:
            logger.error("Error during close: %s", e)
        finally:
            logger.info("Full Pia-Pia sink cleanup completed.")

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
        If Pia-Pia leaves a voice channel (kick, move, disconnect...),
        clean up its state for that guild.
        """
        # Wait until bot.user is available
        if not self.user:
            return

        # Is it Pia-Pia whose state changed?
        if member.id == self.user.id:
            # Pia-Pia is no longer in a voice channel
            if after.channel is None and before.channel is not None:
                guild_id = before.channel.guild.id

                helper = self.guild_to_helper.get(guild_id)
                if helper:
                    helper.set_vc(None)
                    self.guild_to_helper.pop(guild_id, None)

                self._close_and_clean_sink_for_guild(guild_id)
                logger.info(
                    "Pia-Pia left the guild %s voice channel; cleanup done.",
                    guild_id,
                )