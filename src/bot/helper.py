# src/bot/helper.py

import logging
from typing import Optional

import discord

logger = logging.getLogger(__name__)

BOT_NAME = "PIA-PIA 💤"
BOT_AWAKE_NAME = "PIA-PIA 💬"
BOT_PROCESSING_NAME = "PIA-PIA 💡"


class BotHelper:
    """
    Helper lié à une guilde Discord.

    - stocke le VoiceClient
    - facilite l'envoi de messages texte
    - peut mettre à jour le pseudo du bot selon un statut ("awake", "processing", "completed")
    """

    def __init__(self, bot: discord.Client) -> None:
        self.bot = bot
        self.guild_id: Optional[int] = None

        # Placeholders pour de futurs usages (TTS, musique, etc.)
        self.tts_queue = None
        self.current_music_source = None
        self.current_music_source_url = None
        self.current_sfx_source = None
        self.user_music_volume = 0.5

        self.voice = None  # réservé si tu veux gérer plusieurs voix TTS
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
            self.tts_queue = None
            self.current_music_source = None
            self.current_sfx_source = None
            logger.debug(
                "Voice client set to None. Clearing TTS queue and current music/sfx sources."
            )

    # ------------------------------------------------------------------ #
    # Messages texte
    # ------------------------------------------------------------------ #
    async def send_message(
        self,
        channel_id: int,
        content: str,
        embed: Optional[discord.Embed] = None,
        tts: bool = False,
    ) -> None:
        """Envoie un message dans un channel texte donné."""
        channel = self.bot.get_channel(channel_id)
        if channel:
            await channel.send(content=content, embed=embed, tts=tts)
        else:
            logger.error("Channel with ID %s not found.", channel_id)

    # ------------------------------------------------------------------ #
    # Hooks "status" (optionnels)
    # ------------------------------------------------------------------ #
    async def _handle_post_node(self, node: dict, channel_id: int) -> None:
        """
        Exemple de handler : poster node['data']['text'] dans un salon.
        Utile si tu ajoutes plus tard un système de pipeline / nodes.
        """
        text = node.get("data", {}).get("text", "")
        if text:
            await self.send_message(channel_id, text)

    async def _handle_request_status_update(self, update: dict) -> None:
        """
        Met à jour le pseudo du bot sur la guilde en fonction du statut reçu.
        update["status"] ∈ {"awake", "processing", "completed"}.
        """
        if self.guild_id is None:
            return

        try:
            status = update.get("status")
            guild = self.bot.get_guild(self.guild_id)
            if not guild:
                logger.error("Guild %s not found while updating status.", self.guild_id)
                return

            if not self.bot.user:
                logger.error("Bot user not set while updating status.")
                return

            member = guild.get_member(self.bot.user.id)
            if not member:
                logger.error("Bot member not found in guild while updating status.")
                return

            if status == "awake":
                await member.edit(nick=BOT_AWAKE_NAME)
            elif status == "processing":
                await member.edit(nick=BOT_PROCESSING_NAME)
            elif status == "completed":
                await member.edit(nick=BOT_NAME)
            else:
                logger.debug("Unknown status '%s' received for nickname update.", status)

        except Exception as e:
            logger.error("Error updating status: %s", e)
            logger.error("Data: %r", update)
