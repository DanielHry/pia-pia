# src/main.py

import asyncio
import logging

import discord

from src.config.settings import Settings
from src.config.logging_config import configure_logging
from src.utils.commandline import parse_args
from src.bot.piapia_bot import PiaPiaBot
from src.bot.cogs.audio_cog import AudioCog
from src.bot.cogs.pdf_cog import PdfCog
from src.bot.cogs.admin_cog import AdminCog
from src.utils.whisper_preload import preload_whisper_model_if_needed  # 👈 nouveau

logger = logging.getLogger(__name__)


def main() -> None:
    # ------------------------------------------------------------------ #
    # 1. Arguments CLI & Settings
    # ------------------------------------------------------------------ #
    args = parse_args()

    settings = Settings()
    if args.debug:
        # On force le mode debug depuis la CLI si demandé
        settings.debug = True

    # ------------------------------------------------------------------ #
    # 2. Configuration du logging
    # ------------------------------------------------------------------ #
    configure_logging(settings)
    logger.info("Lancement de Pia-Pia Bot 🦜")

    # ------------------------------------------------------------------ #
    # 2bis. Préchargement éventuel du modèle Whisper
    # ------------------------------------------------------------------ #
    preload_whisper_model_if_needed(settings)

    # ------------------------------------------------------------------ #
    # 3. Event loop & bot
    # ------------------------------------------------------------------ #
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    bot = PiaPiaBot(loop, settings)

    # Ajouter les Cogs
    bot.add_cog(AudioCog(bot))
    bot.add_cog(PdfCog(bot))
    bot.add_cog(AdminCog(bot))

    # ------------------------------------------------------------------ #
    # 4. Events supplémentaires
    # ------------------------------------------------------------------ #
    @bot.event
    async def on_voice_state_update(member, before, after):
        """
        Si Pia-Pia quitte un salon vocal (kick, déplacement, déco...),
        on nettoie son état pour cette guilde.
        """
        # On attend que bot.user soit dispo
        if not bot.user:
            return

        # Est-ce que c'est Pia-Pia dont l'état a changé ?
        if member.id == bot.user.id:
            # Pia-Pia n'est plus dans un salon vocal
            if after.channel is None and before.channel is not None:
                guild_id = before.channel.guild.id

                helper = bot.guild_to_helper.get(guild_id)
                if helper:
                    helper.set_vc(None)
                    bot.guild_to_helper.pop(guild_id, None)

                bot._close_and_clean_sink_for_guild(guild_id)
                logger.info(
                    "Pia-Pia a quitté le vocal de la guilde %s, cleanup effectué.",
                    guild_id,
                )

    # ------------------------------------------------------------------ #
    # 5. Run & shutdown propre
    # ------------------------------------------------------------------ #
    async def _run_bot():
        await bot.start(settings.discord_token)

    try:
        loop.run_until_complete(_run_bot())
    except KeyboardInterrupt:
        logger.info("^C reçu, arrêt de Pia-Pia en cours...")
    except Exception:
        # Toute autre exception non gérée -> on logue avec stacktrace
        logger.exception("Exception non gérée au niveau main :")
    finally:
        # Arrêt propre des sinks et ressources internes
        loop.run_until_complete(bot.stop_and_cleanup())

        # Annuler les tâches en cours
        pending = [t for t in asyncio.all_tasks(loop) if not t.done()]
        for task in pending:
            task.cancel()
        if pending:
            loop.run_until_complete(
                asyncio.gather(*pending, return_exceptions=True)
            )

        # Fermer la connexion Discord et la boucle
        loop.run_until_complete(bot.close())
        loop.close()
        logger.info("Pia-Pia est bien rentré au perchoir. 🦜")


if __name__ == "__main__":
    main()
