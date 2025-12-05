# src/bot/cogs/audio_cog.py

import logging
from typing import Any, Optional

import discord
from discord.ext import commands

from src.bot.helper import BotHelper
from src.bot.piapia_bot import PiaPiaBot

logger = logging.getLogger(__name__)


class AudioCog(commands.Cog):
    """
    Commandes liées à la voix / audio :
      - /connect
      - /scribe
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
        description="Ajoute Pia-Pia à ton salon vocal.",
    )
    async def connect(self, ctx: discord.ApplicationContext) -> None:
        if not self.bot._is_ready:
            await ctx.respond(
                "Ahem, Pia-Pia ajuste encore ses plumes et sa moustache… "
                "Réessaie dans un instant, aventurier.",
                ephemeral=True,
            )
            return

        author_vc = ctx.author.voice
        if not author_vc:
            await ctx.respond(
                "Je ne t'entends pas, aventurier. Il semble que tu ne sois pas dans un salon vocal.",
                ephemeral=True,
            )
            return

        # Déjà connecté ?
        if self.bot.guild_to_helper.get(ctx.guild_id) is not None:
            await ctx.respond(
                "Je suis déjà dans une autre taverne, enfin dans un autre salon vocal. 🦜",
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
                    "Impossible de me connecter : Discord ne m'a pas donné les bons modes audio.",
                    ephemeral=True,
                )
                return
            except Exception as e:
                logger.exception("Erreur lors de la connexion au vocal : %s", e)
                await ctx.respond(
                    f"Une erreur inattendue est survenue : {e}",
                    ephemeral=True,
                )
                return

            helper: Optional[BotHelper] = self.bot.guild_to_helper.get(guild_id)
            if helper is None:
                helper = BotHelper(self.bot)
                self.bot.guild_to_helper[guild_id] = helper

            helper.guild_id = guild_id
            helper.set_vc(vc)

            await ctx.respond(
                "Pia-Pia est là ! 🦜✨ "
                "Je prends place sur ton épaule et j'écoute attentivement vos récits.",
                ephemeral=False,
            )

            # On mute le bot lui-même dans le vocal
            await ctx.guild.change_voice_state(
                channel=author_vc.channel,
                self_mute=True,
            )

        except Exception:
            logger.exception("Exception dans /connect")
            await ctx.respond(
                "Une erreur inattendue est survenue pendant la connexion.",
                ephemeral=True,
            )

    # ------------------------------------------------------------------ #
    # /scribe
    # ------------------------------------------------------------------ #
    @discord.slash_command(
        name="scribe",
        description="Commence la transcription de votre aventure.",
    )
    async def scribe(self, ctx: discord.ApplicationContext) -> None:
        author_vc = ctx.author.voice
        connect_text = "/connect"

        if not author_vc:
            await ctx.respond(
                f"Je ne t'entends pas, aventurier. Rejoins un salon vocal d'abord. "
                f"Ensuite, appelle-moi avec {connect_text}.",
                ephemeral=True,
            )
            return

        helper = self.bot.guild_to_helper.get(ctx.guild_id)
        if not helper:
            await ctx.respond(
                f"Je ne suis pas encore arrivé dans ta taverne. "
                f"Invite-moi avec {connect_text}.",
                ephemeral=True,
            )
            return

        # Déjà en train d'enregistrer ?
        if self.bot.guild_is_recording.get(ctx.guild_id, False):
            await ctx.respond(
                "Doucement, doucement… Je ne peux écrire qu'une chanson à la fois ! ✒️",
                ephemeral=True,
            )
            return
        
        # On DEFER l'interaction immédiatement pour éviter le timeout
        await ctx.defer(ephemeral=False)  # mets True si tu veux que seul l'initiateur voie le message

        # Démarrer l'enregistrement (peut prendre plusieurs secondes, surtout au 1er lancement du modèle)
        self.bot.start_recording(ctx)

        # Si pour une raison quelconque le sink n'a pas été créé (erreur lors du démarrage),
        # on informe l'utilisateur proprement
        if ctx.guild_id not in self.bot.guild_sinks:
            await ctx.followup.send(
                "Je n'ai pas réussi à démarrer la transcription 😢 "
                "Regarde les logs côté Pia-Pia pour plus de détails.",
                ephemeral=True,
            )
            return

        await ctx.followup.send(
            "La plume de Pia-Pia est en marche ! 📜 "
            "Parlez, vos légendes prennent forme.",
            ephemeral=False,
        )

    # ------------------------------------------------------------------ #
    # /stop
    # ------------------------------------------------------------------ #
    @discord.slash_command(
        name="stop",
        description="Arrête la transcription en cours.",
    )
    async def stop(self, ctx: discord.ApplicationContext) -> None:
        guild_id = ctx.guild_id
        helper = self.bot.guild_to_helper.get(guild_id)

        if not helper or not helper.vc:
            await ctx.respond(
                "Hmm… Je ne crois pas être dans ta taverne en ce moment.",
                ephemeral=True,
            )
            return

        if not self.bot.guild_is_recording.get(guild_id, False):
            await ctx.respond(
                "Je ne suis pas en train d'écrire, tu sais. 😐",
                ephemeral=True,
            )
            return

        await ctx.trigger_typing()

        # On arrête juste l'enregistrement. Les transcriptions restent en mémoire
        # pour /generate_pdf.
        self.bot.stop_recording(ctx)
        self.bot.guild_is_recording[guild_id] = False

        await ctx.respond(
            "Pia-Pia repose sa plume. 🖋️ "
            "La chronique de cette partie est en sécurité.",
            ephemeral=False,
        )

    # ------------------------------------------------------------------ #
    # /disconnect
    # ------------------------------------------------------------------ #
    @discord.slash_command(
        name="disconnect",
        description="Fait quitter le salon vocal à Pia-Pia.",
    )
    async def disconnect(self, ctx: discord.ApplicationContext) -> None:
        guild_id = ctx.guild_id
        helper = self.bot.guild_to_helper.get(guild_id)

        if not helper:
            await ctx.respond(
                "On dirait que je ne suis pas dans ton groupe… Dois-je vraiment partir ?",
                ephemeral=True,
            )
            return

        bot_vc = helper.vc
        if not bot_vc:
            await ctx.respond(
                "C'est étrange, je ne trouve plus ma chaise dans la taverne. 🤔",
                ephemeral=True,
            )
            return

        await ctx.trigger_typing()
        await bot_vc.disconnect()

        helper.guild_id = None
        helper.set_vc(None)
        self.bot.guild_to_helper.pop(guild_id, None)
        self.bot.guild_is_recording[guild_id] = False

        await ctx.respond(
            "Pia-Pia plie bagage ! 📖 "
            "Ta légende est en sécurité. À la prochaine aventure !",
            ephemeral=False,
        )
