# piapia/bot/helper.py

import logging
from typing import Optional

import discord

logger = logging.getLogger(__name__)


class BotHelper:
    """
    Helper tied to a Discord guild.
    """

    def __init__(self, bot: discord.Client) -> None:
        self.bot = bot
        self.guild_id: Optional[int] = None

        self.vc: Optional[discord.VoiceClient] = None

    # ------------------------------------------------------------------ #
    # Voice client
    # ------------------------------------------------------------------ #
    def set_vc(self, voice_client: Optional[discord.VoiceClient]) -> None:
        """
        Attach (or detach) a VoiceClient to this helper.
        When we lose the VC, we also reset internal audio state.
        """
        self.vc = voice_client
        if voice_client is None:
            logger.debug(
                "Voice client set to None."
            )
