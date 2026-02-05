# piapia/bot/helper.py

import logging
from typing import Optional

import discord

logger = logging.getLogger(__name__)


class BotHelper:
    """
    Helper lié à une guilde Discord.
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
        Associe (ou détache) un VoiceClient à ce helper.
        Quand on perd le VC, on nettoie aussi les états audio internes.
        """
        self.vc = voice_client
        if voice_client is None:
            logger.debug(
                "Voice client set to None."
            )
