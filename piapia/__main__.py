# piapia/__main__.py

import logging
import warnings

warnings.filterwarnings("ignore", category=SyntaxWarning, module="pydub")

from piapia.config.settings import Settings
from piapia.config.logging_config import configure_logging
from piapia.utils.commandline import parse_args
from piapia.bot.piapia_bot import PiaPiaBot
from piapia.bot.cogs.audio_cog import AudioCog
from piapia.bot.cogs.admin_cog import AdminCog

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
    # 3. Bot
    # ------------------------------------------------------------------ #
    bot = PiaPiaBot(settings)

    # Ajouter les Cogs
    bot.add_cog(AudioCog(bot))
    bot.add_cog(AdminCog(bot))

    # ------------------------------------------------------------------ #
    # 4. Run
    # ------------------------------------------------------------------ #
    bot.run(settings.discord_token)
    
    logger.info("Pia-Pia est bien rentré au perchoir. 🦜")


if __name__ == "__main__":
    main()
