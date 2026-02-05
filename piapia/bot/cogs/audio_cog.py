# piapia/bot/cogs/audio_cog.py

import logging
from typing import Optional

import discord
from discord.ext import commands

from piapia.bot.helper import BotHelper
from piapia.bot.piapia_bot import PiaPiaBot

logger = logging.getLogger(__name__)


class AudioCog(commands.Cog):
    """
    Voice / audio commands:
      - /connect
      - /record
      - /stop
      - /disconnect
    """

    def __init__(self, bot: PiaPiaBot) -> None:
        self.bot = bot

    # ------------------------------------------------------------------ #
    # /connect
    # ------------------------------------------------------------------ #
    @discord.slash_command(
        name="connect",
        description="Bring Pia-Pia into your voice channel.",
    )
    @commands.cooldown(1, 10, commands.BucketType.guild)
    async def connect(self, ctx: discord.ApplicationContext) -> None:
        if not self.bot._is_ready:
            await ctx.respond(
                "Ahem, Pia-Pia is still fluffing its feathers… Try again in a moment.",
                ephemeral=True,
            )
            return

        author_vc = ctx.author.voice
        if not author_vc:
            await ctx.respond(
                "I can't hear you, adventurer — you're not in a voice channel.",
                ephemeral=True,
            )
            return

        # Already connected?
        if self.bot.guild_to_helper.get(ctx.guild_id) is not None:
            await ctx.respond(
                "I'm already in another tavern (another voice channel).",
                ephemeral=True,
            )
            return

        await ctx.trigger_typing()

        try:
            guild_id = ctx.guild_id

            try:
                vc = await author_vc.channel.connect(timeout=15, reconnect=True)
            except IndexError:
                await ctx.respond(
                    "I couldn't connect: Discord didn't give me the right audio modes.",
                    ephemeral=True,
                )
                return
            except Exception as e:
                logger.exception("Error while connecting to voice: %s", e)
                await ctx.respond(f"An unexpected error occurred: {e}", ephemeral=True)
                return

            helper: Optional[BotHelper] = self.bot.guild_to_helper.get(guild_id)
            if helper is None:
                helper = BotHelper(self.bot)
                self.bot.guild_to_helper[guild_id] = helper

            helper.guild_id = guild_id
            helper.set_vc(vc)

            await ctx.respond(
                "Pia-Pia is here! 🦜✨ Settling in and listening.",
                ephemeral=False,
            )

            # Mute the bot itself in voice
            await ctx.guild.change_voice_state(channel=author_vc.channel, self_mute=True)

        except Exception:
            logger.exception("Exception in /connect")
            await ctx.respond(
                "An unexpected error occurred while connecting.",
                ephemeral=True,
            )

    # ------------------------------------------------------------------ #
    # /record
    # ------------------------------------------------------------------ #
    @discord.slash_command(
        name="record",
        description="Start an audio recording session.",
    )
    @commands.cooldown(1, 5, commands.BucketType.guild)
    async def record(self, ctx: discord.ApplicationContext, label: Optional[str] = None) -> None:
        author_vc = ctx.author.voice
        connect_text = "/connect"

        if not author_vc:
            await ctx.respond(
                f"Join a voice channel, then summon me with {connect_text}.",
                ephemeral=True,
            )
            return

        helper = self.bot.guild_to_helper.get(ctx.guild_id)
        if not helper or not helper.vc:
            await ctx.respond(
                f"I'm not in your tavern yet. Invite me with {connect_text}.",
                ephemeral=True,
            )
            return

        if self.bot.current_sink_by_guild.get(ctx.guild_id) is not None:
            await ctx.respond(
                "A session is already active on this server. Finish it with /stop.",
                ephemeral=True,
            )
            return

        await ctx.defer(ephemeral=False)

        self.bot.start_record_session(ctx, label=label)

        if self.bot.current_sink_by_guild.get(ctx.guild_id) is None:
            await ctx.followup.send(
                "I couldn't start recording 😢 (check the logs).",
                ephemeral=True,
            )
            return
        
        await ctx.followup.send(
            f"Recording started! 🎙️ Session: `{self.bot.current_session_by_guild[ctx.guild_id].session_id}`",
            ephemeral=False,
        )

    # ------------------------------------------------------------------ #
    # /stop
    # ------------------------------------------------------------------ #
    @discord.slash_command(
        name="stop",
        description="Stop the current recording session.",
    )
    @commands.cooldown(1, 5, commands.BucketType.guild)
    async def stop(self, ctx: discord.ApplicationContext) -> None:
        guild_id = ctx.guild_id
        helper = self.bot.guild_to_helper.get(guild_id)

        if not helper or not helper.vc:
            await ctx.respond("I'm not in your tavern right now.", ephemeral=True)
            return

        if self.bot.current_sink_by_guild.get(guild_id) is None:
            await ctx.respond("No active session to stop. 😐", ephemeral=True)
            return

        await ctx.trigger_typing()

        # stop_recording() triggers the sink callback on the Discord side
        self.bot.stop_current_session(ctx)

        await ctx.respond(
            "Pia-Pia sets down its quill. 🖋️ Session stopped.",
            ephemeral=False,
        )

    # ------------------------------------------------------------------ #
    # /disconnect
    # ------------------------------------------------------------------ #
    @discord.slash_command(
        name="disconnect",
        description="Make Pia-Pia leave the voice channel (stops the session if needed).",
    )
    @commands.cooldown(1, 10, commands.BucketType.guild)
    async def disconnect(self, ctx: discord.ApplicationContext) -> None:
        guild_id = ctx.guild_id
        helper = self.bot.guild_to_helper.get(guild_id)

        if not helper or not helper.vc:
            await ctx.respond(
                "Looks like I'm not with your party… 🤔",
                ephemeral=True,
            )
            return

        await ctx.trigger_typing()
        await self.bot.force_disconnect(ctx)

        await ctx.respond(
            "Pia-Pia packs up! 📖 See you on the next adventure!",
            ephemeral=False,
        )

    # ------------------------------------------------------------------ #
    # Error handler (cooldown)
    # ------------------------------------------------------------------ #
    async def cog_command_error(
        self, ctx: discord.ApplicationContext, error: Exception
    ) -> None:
        if isinstance(error, commands.CommandOnCooldown):
            await ctx.respond(
                f"Easy there, adventurer! Try again in {error.retry_after:.0f}s. ⏳",
                ephemeral=True,
            )
        else:
            raise error