# piapia/bot/cogs/admin_cog.py

import logging
from typing import List, Tuple

import discord
from discord.ext import commands

from piapia.bot.piapia_bot import PiaPiaBot

logger = logging.getLogger(__name__)


class AdminCog(commands.Cog):
    """
    Admin / utility commands:
      - /update_player_map
      - /help
    """

    def __init__(self, bot: PiaPiaBot) -> None:
        self.bot = bot

    # ------------------------------------------------------------------ #
    # /update_player_map
    # ------------------------------------------------------------------ #
    @discord.slash_command(
        name="update_player_map",
        description="Update Pia-Pia's player/character map.",
    )
    #@commands.has_permissions(administrator=True) # Uncomment if admin-only access is desired
    @commands.cooldown(1, 30, commands.BucketType.guild)
    async def update_player_map_cmd(self, ctx: discord.ApplicationContext) -> None:
        await ctx.trigger_typing()
        await self.bot.update_player_map(ctx)
        await ctx.respond(
            f"Folders updated for {len(ctx.guild.members)} adventurers and their alter egos. ⚔️",
            ephemeral=True,
        )

    # ------------------------------------------------------------------ #
    # /help
    # ------------------------------------------------------------------ #
    @discord.slash_command(
        name="help",
        description="Show Pia-Pia commands.",
    )
    async def help_cmd(self, ctx: discord.ApplicationContext) -> None:
        commands_info: List[Tuple[str, str]] = [
            ("/connect", "Invite Pia-Pia into your voice channel."),
            ("/record", "Record the voice channel audio."),
            ("/stop", "Stop the recording."),
            ("/disconnect", "Make Pia-Pia leave the voice channel."),
            ("/update_player_map", "Refresh the player ↔ character map from server members."),
        ]

        embed = discord.Embed(
            title="Pia-Pia Help 📖",
            description="Sketches of your legend — from tavern chatter to the grand tome.",
            color=discord.Color.blue(),
        )

        for name, description in commands_info:
            embed.add_field(name=name, value=description, inline=False)

        await ctx.respond(embed=embed, ephemeral=True)
