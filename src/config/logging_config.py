# src/config/logging_config.py

import logging
import logging.config
import os
from datetime import datetime

from src.config.settings import Settings


def configure_logging(settings: Settings) -> None:
    """
    Configure le logging global de l'application à partir des Settings.

    - Root logger : console (niveau INFO ou DEBUG selon settings.debug)
    - Logger 'transcription' : fichier .log (JSON), un par jour
    """

    # Répertoires de base
    logs_dir = settings.logs_dir
    transcripts_dir = os.path.join(logs_dir, settings.transcripts_subdir)
    pdf_dir = os.path.join(logs_dir, settings.pdf_subdir)
    audio_dir = os.path.join(logs_dir, settings.audio_archive_subdir)

    os.makedirs(transcripts_dir, exist_ok=True)
    os.makedirs(pdf_dir, exist_ok=True)
    os.makedirs(audio_dir, exist_ok=True)

    # Fichier de transcription : .logs/transcripts/YYYY-MM-DD-transcription.log
    current_date = datetime.now().strftime("%Y-%m-%d")
    transcription_log_file = os.path.join(
        transcripts_dir,
        f"{current_date}-transcription.log",
    )

    # Niveau de log global
    level = logging.DEBUG if settings.debug else logging.INFO

    # Config dictConfig
    config = {
        "version": 1,
        "disable_existing_loggers": False,
        "formatters": {
            "standard": {
                "format": "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
                "datefmt": "%Y-%m-%d %H:%M:%S",
            },
            # Pour le logger 'transcription', on écrit déjà du JSON complet,
            # donc on ne garde que le message.
            "transcription": {
                "format": "%(message)s",
            },
        },
        "handlers": {
            "console": {
                "class": "logging.StreamHandler",
                "level": level,
                "formatter": "standard",
                "stream": "ext://sys.stdout",
            },
            "transcription_file": {
                "class": "logging.FileHandler",
                "level": "INFO",
                "formatter": "transcription",
                "filename": transcription_log_file,
                "mode": "a",
                "encoding": "utf-8",
            },
        },
        "loggers": {
            # Logger dédié aux transcriptions (JSON lignes)
            "transcription": {
                "handlers": ["transcription_file"],
                "level": "INFO",
                "propagate": False,
            },
            # Réduire le bruit de certaines libs
            "discord": {
                "handlers": ["console"],
                "level": "WARNING",
                "propagate": False,
            },
            "asyncio": {
                "handlers": ["console"],
                "level": "WARNING",
                "propagate": False,
            },
            "httpx": {
                "handlers": ["console"],
                "level": "WARNING",
                "propagate": False,
            },
            "httpcore": {
                "handlers": ["console"],
                "level": "WARNING",
                "propagate": False,
            },
        },
        "root": {
            "handlers": ["console"],
            "level": level,
        },
    }

    logging.config.dictConfig(config)
