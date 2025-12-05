# src/bot/cogs/pdf_cog.py

import logging
import os
from typing import List

import discord
from discord.ext import commands

from src.bot.piapia_bot import PiaPiaBot
from src.models.transcription import TranscriptionEvent
from src.utils.pdf_generator import pdf_generator

logger = logging.getLogger(__name__)


class PdfCog(commands.Cog):
    """
    Commande de génération de PDF :
      - /generate_pdf
    """

    def __init__(self, bot: PiaPiaBot) -> None:
        self.bot = bot

    @discord.slash_command(
        name="generate_pdf",
        description="Génère un PDF à partir des transcriptions de cette session.",
    )
    async def generate_pdf_cmd(self, ctx: discord.ApplicationContext) -> None:
        guild_id = ctx.guild_id
        helper = self.bot.guild_to_helper.get(guild_id)
        if not helper:
            await ctx.respond(
                "Je ne vois pas de taverne connue ici… As-tu bien invité Pia-Pia ?",
                ephemeral=True,
            )
            return

        # On defer l'interaction car la génération de PDF peut prendre quelques secondes
        await ctx.defer(ephemeral=False)

        # Récupérer toutes les transcriptions pour cette guilde
        events: List[TranscriptionEvent] = await self.bot.get_transcription(ctx)
        if not events:
            await ctx.followup.send(
                "Je n'ai aucune histoire récente à relier en tome. "
                "As-tu bien parlé pendant que j'écoutais ?",
                ephemeral=True,
            )
            return

        try:
            pdf_file_path = await pdf_generator(events, self.bot.settings)
        except Exception as e:
            logger.exception("Erreur lors de la génération du PDF : %s", e)
            await ctx.followup.send(
                "Je n'ai pas réussi à relier les pages de cette histoire… 😢",
                ephemeral=True,
            )
            return

        if not os.path.exists(pdf_file_path):
            await ctx.followup.send(
                "Hmm… Les pages du tome ont refusé de se lier. Aucun PDF n'a été créé. 😔",
                ephemeral=True,
            )
            return

        try:
            with open(pdf_file_path, "rb") as f:
                discord_file = discord.File(
                    f,
                    filename=os.path.basename(pdf_file_path),
                )
                await ctx.followup.send(
                    "Voici la chronique de cette session :",
                    file=discord_file,
                )
        finally:
            # optionnel : tu peux supprimer ou garder le PDF
            try:
                os.remove(pdf_file_path)
            except OSError:
                logger.warning(
                    "Impossible de supprimer le fichier PDF temporaire : %s",
                    pdf_file_path,
                    exc_info=False,  # évite la grosse stacktrace
                )
