# piapia/config/settings.py

from typing import Optional

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


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

    # General
    debug: bool = Field(False, validation_alias="DEBUG")

    # Player map
    player_map_dir: Optional[str] = Field(None, validation_alias="PLAYER_MAP_DIR")

    # Logging / paths
    logs_dir: str = Field(".logs", validation_alias="LOGS_DIR")

    # Subdir dedicated to audio sessions (logs/audio/<session_id>/...)
    audio_sessions_subdir: str = Field("audio", validation_alias="AUDIO_SESSIONS_SUBDIR")

    # Maximum session duration in minutes (0 = unlimited)
    max_session_duration_minutes: int = Field(240, validation_alias="MAX_SESSION_DURATION_MINUTES")