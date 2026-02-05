# piapia/bot/cogs/admin_cog.py

import logging
from typing import List, Tuple

import discord
from discord.ext import commands

from piapia.bot.piapia_bot import PiaPiaBot

logger = logging.getLogger(__name__)


class AdminCog(commands.Cog):
    """
    Commandes d'administration / utilitaires :
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
        description="Met à jour la carte joueurs/personnages de Pia-Pia.",
    )
    #@commands.has_permissions(administrator=True) # Uncomment if admin-only access is desired
    @commands.cooldown(1, 30, commands.BucketType.guild)
    async def update_player_map_cmd(self, ctx: discord.ApplicationContext) -> None:
        await ctx.trigger_typing()
        await self.bot.update_player_map(ctx)
        await ctx.respond(
            f"Dossiers mis à jour pour {len(ctx.guild.members)} aventuriers "
            f"et leurs alter-ego. ⚔️",
            ephemeral=True,
        )

    # ------------------------------------------------------------------ #
    # /help
    # ------------------------------------------------------------------ #
    @discord.slash_command(
        name="help",
        description="Affiche les commandes de Pia-Pia.",
    )
    async def help_cmd(self, ctx: discord.ApplicationContext) -> None:
        commands_info: List[Tuple[str, str]] = [
            ("/connect", "Inviter Pia-Pia dans ton salon vocal."),
            ("/record", "Enregistrer l'audio du salon vocal."),
            ("/stop", "Mettre en pause l'enregistrement."),
            ("/disconnect", "Faire quitter le salon vocal à Pia-Pia."),
            (
                "/update_player_map",
                "Mettre à jour la carte des joueurs et de leurs personnages.",
            ),
        ]

        embed = discord.Embed(
            title="Aide de Pia-Pia 📖",
            description="Les croquis de ta légende, de la taverne au grand tome.",
            color=discord.Color.blue(),
        )

        for name, description in commands_info:
            embed.add_field(name=name, value=description, inline=False)

        await ctx.respond(embed=embed, ephemeral=True)
