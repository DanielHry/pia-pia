from typing import Optional

from pydantic import BaseSettings, Field


class Settings(BaseSettings):
    """
    Configuration globale du bot VOLO, chargée depuis l'environnement (.env).
    """

    # Discord
    discord_token: str = Field(..., env="DISCORD_BOT_TOKEN")

    # Général
    debug: bool = Field(False, env="DEBUG")

    # Transcription
    transcription_method: str = Field(
        "local", env="TRANSCRIPTION_METHOD"
    )  # "local" ou "openai"
    whisper_model: str = Field("large-v3", env="WHISPER_MODEL")
    whisper_language: str = Field("fr", env="WHISPER_LANGUAGE")
    whisper_compute_type: str = Field("float16", env="WHISPER_COMPUTE_TYPE")
    whisper_cache_dir: str = Field(
        "default", env="WHISPER_CACHE_DIR"
    )  # "default" ou chemin de cache Hugging Face
    min_audio_duration: float = Field(0.1, env="MIN_AUDIO_DURATION")     # secondes
    silence_threshold: float = Field(1.2, env="SILENCE_THRESHOLD")       # secondes

    # Player map
    player_map_file: Optional[str] = Field(
        None, env="PLAYER_MAP_FILE_PATH"
    )

    # Logging / chemins
    logs_dir: str = Field(".logs", env="LOGS_DIR")
    transcripts_subdir: str = Field("transcripts", env="TRANSCRIPTS_SUBDIR")
    pdf_subdir: str = Field("pdfs", env="PDF_SUBDIR")
    audio_archive_subdir: str = Field("audio", env="AUDIO_ARCHIVE_SUBDIR")

    # Archive audio brute
    archive_audio: bool = Field(False, env="ARCHIVE_AUDIO")

    # Filtres de bruit texte
    enable_subtitle_noise_filter: bool = Field(
        True, env="ENABLE_SUBTITLE_NOISE_FILTER"
    )

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
