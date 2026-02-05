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
    # 1. CLI arguments & Settings
    # ------------------------------------------------------------------ #
    args = parse_args()

    settings = Settings()
    if args.debug:
        # Force debug mode from the CLI if requested
        settings.debug = True

    # ------------------------------------------------------------------ #
    # 2. Logging configuration
    # ------------------------------------------------------------------ #
    configure_logging(settings)
    logger.info("Lancement de Pia-Pia Bot 🦜")

    # ------------------------------------------------------------------ #
    # 3. Bot initialization and Cogs setup
    # ------------------------------------------------------------------ #
    bot = PiaPiaBot(settings)
    bot.add_cog(AudioCog(bot))
    bot.add_cog(AdminCog(bot))

    # ------------------------------------------------------------------ #
    # 4. Run
    # ------------------------------------------------------------------ #
    bot.run(settings.discord_token)
    
    logger.info("Pia-Pia is back on its perch. 🦜")


if __name__ == "__main__":
    main()
