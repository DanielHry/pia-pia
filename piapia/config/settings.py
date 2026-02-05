# piapia/config/settings.py

from typing import Optional

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

# Formats supportés par pydub (nécessite ffmpeg pour mp3, ogg, flac)
SUPPORTED_AUDIO_FORMATS = {"wav", "mp3", "flac", "ogg"}

class Settings(BaseSettings):
    """
    Configuration globale du bot Pia-pia, chargée depuis l'environnement (.env).
    """
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )
    
    # Discord
    discord_token: str = Field(..., validation_alias="DISCORD_BOT_TOKEN")

    # Général
    debug: bool = Field(False, validation_alias="DEBUG")

    # Player map
    player_map_dir: Optional[str] = Field(None, validation_alias="PLAYER_MAP_DIR")

    # Logging / chemins
    logs_dir: str = Field(".logs", validation_alias="LOGS_DIR")

    # subdir dédié aux sessions audio (logs/audio/<session_id>/...)
    audio_sessions_subdir: str = Field("audio", validation_alias="AUDIO_SESSIONS_SUBDIR")

    # Format audio de sortie (wav, mp3, flac, ogg)
    audio_format: str = Field("wav", validation_alias="AUDIO_FORMAT")

    # Durée maximale d'une session en minutes (0 = illimité)
    max_session_duration_minutes: int = Field(240, validation_alias="MAX_SESSION_DURATION_MINUTES")