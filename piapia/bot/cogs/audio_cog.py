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
    Commandes liées à la voix / audio :
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
        description="Ajoute Pia-Pia à ton salon vocal.",
    )
    @commands.cooldown(1, 10, commands.BucketType.guild)
    async def connect(self, ctx: discord.ApplicationContext) -> None:
        if not self.bot._is_ready:
            await ctx.respond(
                "Ahem, Pia-Pia ajuste encore ses plumes… Réessaie dans un instant.",
                ephemeral=True,
            )
            return

        author_vc = ctx.author.voice
        if not author_vc:
            await ctx.respond(
                "Je ne t'entends pas, aventurier : tu n'es pas dans un salon vocal.",
                ephemeral=True,
            )
            return

        # Déjà connecté ?
        if self.bot.guild_to_helper.get(ctx.guild_id) is not None:
            await ctx.respond(
                "Je suis déjà dans une autre taverne (un autre salon vocal). 🦜",
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
                await ctx.respond(f"Une erreur inattendue est survenue : {e}", ephemeral=True)
                return

            helper: Optional[BotHelper] = self.bot.guild_to_helper.get(guild_id)
            if helper is None:
                helper = BotHelper(self.bot)
                self.bot.guild_to_helper[guild_id] = helper

            helper.guild_id = guild_id
            helper.set_vc(vc)

            await ctx.respond(
                "Pia-Pia est là ! 🦜✨ Je m'installe et j'écoute.",
                ephemeral=False,
            )

            # On mute le bot lui-même dans le vocal
            await ctx.guild.change_voice_state(channel=author_vc.channel, self_mute=True)

        except Exception:
            logger.exception("Exception dans /connect")
            await ctx.respond(
                "Une erreur inattendue est survenue pendant la connexion.",
                ephemeral=True,
            )

    # ------------------------------------------------------------------ #
    # /record
    # ------------------------------------------------------------------ #
    @discord.slash_command(
        name="record",
        description="Démarre une session d'enregistrement audio.",
    )
    @commands.cooldown(1, 5, commands.BucketType.guild)
    async def record(self, ctx: discord.ApplicationContext, label: Optional[str] = None) -> None:
        author_vc = ctx.author.voice
        connect_text = "/connect"

        if not author_vc:
            await ctx.respond(
                f"Rejoins un salon vocal, puis appelle-moi avec {connect_text}.",
                ephemeral=True,
            )
            return

        helper = self.bot.guild_to_helper.get(ctx.guild_id)
        if not helper or not helper.vc:
            await ctx.respond(
                f"Je ne suis pas encore dans ta taverne. Invite-moi avec {connect_text}.",
                ephemeral=True,
            )
            return

        if self.bot.current_sink_by_guild.get(ctx.guild_id) is not None:
            await ctx.respond(
                "Une session est déjà active dans cette guilde. Termine-la avec /stop.",
                ephemeral=True,
            )
            return

        await ctx.defer(ephemeral=False)

        self.bot.start_record_only_session(ctx, label=label)

        if self.bot.current_sink_by_guild.get(ctx.guild_id) is None:
            await ctx.followup.send(
                "Je n'ai pas réussi à démarrer l'enregistrement 😢 (regarde les logs).",
                ephemeral=True,
            )
            return
        
        await ctx.followup.send(
            f"Enregistrement démarré ! Session: `{self.bot.current_session_by_guild[ctx.guild_id].session_id}`",
            ephemeral=False,
        )

    # ------------------------------------------------------------------ #
    # /stop
    # ------------------------------------------------------------------ #
    @discord.slash_command(
        name="stop",
        description="Arrête la session d'enregistrement en cours.",
    )
    @commands.cooldown(1, 5, commands.BucketType.guild)
    async def stop(self, ctx: discord.ApplicationContext) -> None:
        guild_id = ctx.guild_id
        helper = self.bot.guild_to_helper.get(guild_id)

        if not helper or not helper.vc:
            await ctx.respond("Je ne suis pas dans ta taverne en ce moment.", ephemeral=True)
            return

        if self.bot.current_sink_by_guild.get(guild_id) is None:
            await ctx.respond("Aucune session active à arrêter. 😐", ephemeral=True)
            return

        await ctx.trigger_typing()

        # stop_recording() va déclencher le callback du sink côté Discord
        self.bot.stop_current_session(ctx)

        await ctx.respond(
            "Pia-Pia repose sa plume. 🖋️ Session stoppée.",
            ephemeral=False,
        )

    # ------------------------------------------------------------------ #
    # /disconnect
    # ------------------------------------------------------------------ #
    @discord.slash_command(
        name="disconnect",
        description="Fait quitter le salon vocal à Pia-Pia (stoppe la session si besoin).",
    )
    @commands.cooldown(1, 10, commands.BucketType.guild)
    async def disconnect(self, ctx: discord.ApplicationContext) -> None:
        guild_id = ctx.guild_id
        helper = self.bot.guild_to_helper.get(guild_id)

        if not helper or not helper.vc:
            await ctx.respond(
                "On dirait que je ne suis pas dans ton groupe… 🤔",
                ephemeral=True,
            )
            return

        await ctx.trigger_typing()
        await self.bot.force_disconnect(ctx)

        await ctx.respond(
            "Pia-Pia plie bagage ! 📖 À la prochaine aventure !",
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
                f"Doucement aventurier ! Réessaie dans {error.retry_after:.0f}s. ⏳",
                ephemeral=True,
            )
        else:
            raise error